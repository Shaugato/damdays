"""Leakage hunt, part 2: rebuild every feature table with the future removed, scrambled, or the statics changed.

test_no_lookahead.py truncates each region once (nsw_cw 2014-07-09, wvic_sesa
2012-07-09). One cut per region cannot probe every boundary, and holding the
PREREG statics fixed hides any feature that uses them. This file rebuilds the
features (damdays.features.build.build_all) on two ~400-dam boxes, many times:

TRUNCATE  delete every look on or after the cut and every rain month not
          finished by the cut; re-derive the events. Nine cuts, each chosen
          to sit on a boundary where an off-by-one would show (see SCENARIOS).
SCRAMBLE  keep every date but shuffle each dam's values from the cut on (and
          scale rain from the cut month on). Dates, the grid and the season
          list stay the same, so this isolates "does a value from the future
          matter?" from "does the length of the data matter?". Cuts on 1 Jul
          check that the 1 Jul season rating sees nothing from that day on.
STATIC    placebo: change the PREREG static "full", wet share and pre-2016
          look count (keeping the events). They define WHAT is scored, never
          a feature value, so no feature may move except the ones derived
          from the at-risk flags (b2*_R30, dam_rate_R30).

In every case, every non-label column of every table (P1, P2 dam, P2 cell,
checkpoints, neighbour grid) dated before the cut must be bit-for-bit equal.
Each scenario also checks that it can fail: a planted look-ahead column (or a
planted static column) must be caught.

Disclosed exception: the shrinkage priors are one TRAIN-block rate per region
(and half-year). A cut inside the TRAIN block leaves a smaller TRAIN block, so
the prior moves. Columns built from a prior are therefore compared strictly
only for cuts on or after the date that prior is final:
    P1 dam_rate_*     2009-01-01 (TRAIN forecasts with t + 120 days < 2009-01-01)
    P2 dam_rate_P2*   2009-05-01 (the 2008 season's events are confirmed by 30 Apr 2009)
Before that they are left out, but the counts they are built from (b2S, b2N)
are still compared strictly. LEAK-1 (the P1 prior used to include TRAIN
answers only final in Jan-Apr 2009) is fixed; its own test is at the bottom.

Runtime: about 3-4 minutes (16 builds, 4 at a time). Summary saved to
artifacts/leakage_hunt.json.
"""
import json
import pickle
from functools import lru_cache

import numpy as np
import pandas as pd
import pytest
from joblib import Parallel, delayed

from damdays import config
from damdays.data.events import build_events
from damdays.features.build import build_all
from damdays.features.spec import LABEL_COLUMNS

SEED = 20261002
BOXES = {   # (region, (lat_min, lat_max, lon_min, lon_max)): about 400 waterbodies each
    "nsw_box": ("nsw_cw", (-32.6, -31.6, 148.4, 149.4)),
    "wvic_box": ("wvic_sesa", (-37.4, -36.4, 141.6, 142.6)),
}
# (box, mode, cut, the boundary it probes)
SCENARIOS = [
    ("nsw_box", "truncate", "1993-03-31", "last day of a month: rain must not use the (unfinished) issue month"),
    ("nsw_box", "truncate", "2001-01-01", "1 Jan, a checkpoint and grid date: a look ON 1 Jan is not in that year's checkpoint"),
    ("nsw_box", "truncate", "2009-02-27", "first 120 days of VAL, when TRAIN answers are still arriving"),
    ("nsw_box", "truncate", "2016-07-02", "the day after the first TEST season rating (1 Jul 2016)"),
    ("nsw_box", "truncate", "2021-11-23", "TEST era, off-grid, mid-season"),
    ("wvic_box", "truncate", "1997-10-16", "a neighbour-grid date"),
    ("wvic_box", "truncate", "2005-06-30", "the day before a season rating"),
    ("wvic_box", "truncate", "2013-12-31", "the last day of a year"),
    ("wvic_box", "truncate", "2019-08-08", "TEST era"),
    ("nsw_box", "scramble", "2012-07-01", "values from 1 Jul 2012 on scrambled: the 2012 rating must not move"),
    ("wvic_box", "scramble", "2018-07-01", "values from 1 Jul 2018 on scrambled (TEST)"),
    ("wvic_box", "scramble", "2003-07-01", "values from 1 Jul 2003 on scrambled (TRAIN)"),
    ("nsw_box", "static", None, "placebo: PREREG static full / wet share / n_pre_obs changed"),
    ("wvic_box", "static", None, "placebo: PREREG static full / wet share / n_pre_obs changed"),
]
# Columns built from a TRAIN-block prior, and the first cut date from which that prior is final.
P1_PRIOR_FINAL = pd.Timestamp(config.VAL_START)     # issues.train_prior_sums uses splits.fit_mask(dates, "VAL")
P1_PRIOR_COLUMNS = {
    "p1": {"dam_rate_D0", "dam_rate_R30", "dam_rate_D0g"},
    "p2_dam": {"dam_rate_D0", "dam_rate_R30"},      # the P1 rates at the 1 Jul state look
    "p2_cell": {"dam_rate_D0_mean"},
    "checkpoints": set(),
}
P2_PRIOR_FINAL = pd.Timestamp("2009-05-01")         # last TRAIN season ends 31 Mar 2009, + 30 days to confirm
P2_PRIOR_COLUMNS = {
    "p1": set(),
    "p2_dam": {"dam_rate_P2", "dam_rate_P2_g"},
    "p2_cell": {"dam_rate_P2_mean", "dam_rate_P2_min"},
    "checkpoints": set(),
}


def prior_columns_not_yet_final(name, cut):
    """Columns of table `name` built from a prior that was not final at the cut (left out of the strict check)."""
    skip = set()
    if cut < P1_PRIOR_FINAL:
        skip |= P1_PRIOR_COLUMNS[name]
    if cut < P2_PRIOR_FINAL:
        skip |= P2_PRIOR_COLUMNS[name]
    return skip
STATIC_MAY_CHANGE = {   # placebo: columns that come from the at-risk flags (static full) or the label choice
    "p1": {"at_risk_R30", "elig_rescue_R30", "b2S_R30", "b2N_R30", "dam_rate_R30"},
    "p2_dam": {"dam_rate_R30"},
    "p2_cell": {"best_uid", "y_best", "fold5", "sfold5", "tile"},
    "checkpoints": set(),
}
KEYS = {"p1": ["uid", "issue_date"], "p2_dam": ["uid", "season"], "p2_cell": ["hex_id", "season"],
        "checkpoints": ["uid", "year"]}


# ---------------------------------------------------------------------------
# Building one scenario
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def full_inputs():
    """panel, attrs and SILO rain from data_cache/ (cached once per worker process)."""
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    with open(config.CACHE_DIR / "silo_rain.pkl", "rb") as f:
        rain_by_cell = pickle.load(f)
    return panel, attrs, rain_by_cell


def box_inputs(box):
    """panel, attrs and rain of one box (all waterbodies inside it, and only their rain cells)."""
    panel, attrs, rain_by_cell = full_inputs()
    region, (lat0, lat1, lon0, lon1) = BOXES[box]
    attrs = attrs[(attrs["region"] == region) & attrs["lat"].between(lat0, lat1)
                  & attrs["lon"].between(lon0, lon1)].reset_index(drop=True)
    panel = panel[panel["uid"].isin(set(attrs["uid"]))]
    # Plain-text uids sorted alphabetically (a categorical sort could use another order, and
    # scramble() relies on the rows being grouped in the same order as a text sort).
    panel = panel.assign(uid=panel["uid"].astype(str)).sort_values(["uid", "date"]).reset_index(drop=True)
    keep = np.isin(np.asarray(rain_by_cell["cells"]).astype(str), attrs["silo_cell"].astype(str).unique())
    rain_box = {"rain": rain_by_cell["rain"][keep], "months": rain_by_cell["months"],
                "cells": np.asarray(rain_by_cell["cells"])[keep]}
    return panel, attrs, rain_box


def truncate(panel, rain_box, cut):
    """Delete looks on or after the cut and rain months that had not ended by the cut."""
    panel = panel[panel["date"] < cut]
    ended = rain_box["months"] < cut.year * 100 + cut.month
    return panel, {"rain": rain_box["rain"][:, ended], "months": rain_box["months"][ended],
                   "cells": rain_box["cells"]}


def scramble(panel, rain_box, cut, rng):
    """Shuffle each dam's (pc_wet, px_wet) among its own looks from the cut on; scale rain from the cut month on."""
    panel = panel.copy()
    later = np.flatnonzero((panel["date"] >= cut).to_numpy())
    uids = panel["uid"].astype(str).to_numpy()[later]
    # Sort the later looks by (dam, random number): a random order within each dam, same group sizes.
    shuffled = later[np.lexsort((rng.random(len(later)), uids))]
    for column in ("pc_wet", "px_wet"):
        values = panel[column].to_numpy().copy()
        values[later] = values[shuffled]          # panel is sorted by dam then date, so groups line up
        panel[column] = values
    rain = rain_box["rain"].copy()
    from_month = rain_box["months"] >= cut.year * 100 + cut.month
    rain[:, from_month] *= rng.uniform(0.2, 3.0, (rain.shape[0], from_month.sum())).astype(rain.dtype)
    return panel, dict(rain_box, rain=rain)


def change_statics(attrs, rng):
    """Placebo: new random PREREG static full, wet share and pre-2016 look count (flags kept)."""
    attrs = attrs.copy()
    attrs["full"] = attrs["full"] * np.exp(rng.uniform(-0.7, 0.7, len(attrs)))
    attrs["wet_share"] = rng.uniform(0, 1, len(attrs))
    attrs["n_pre_obs"] = attrs["n_pre_obs"] + rng.integers(0, 50, len(attrs))
    return attrs


def build_scenario(box, mode, cut):
    """Build all feature tables for one box under one scenario ("reference", "truncate", "scramble", "static")."""
    panel, attrs, rain_box = box_inputs(box)
    rng = np.random.default_rng(SEED)
    events = build_events(panel, attrs)          # the reference events (kept as-is by "static")
    if mode == "truncate":
        panel, rain_box = truncate(panel, rain_box, pd.Timestamp(cut))
        events = build_events(panel, attrs)
    elif mode == "scramble":
        panel, rain_box = scramble(panel, rain_box, pd.Timestamp(cut), rng)
        events = build_events(panel, attrs)
    elif mode == "static":
        attrs = change_statics(attrs, rng)
    tables = build_all(panel, attrs, events, rain_box, verbose=False)
    tables["static_full"] = attrs.set_index(attrs["uid"].astype(str))["full"]
    return tables


@pytest.fixture(scope="module")
def builds():
    """The reference build of each box plus every scenario, 4 at a time."""
    needed = ["panel.pkl", "attributes.pkl", "events.pkl", "silo_rain.pkl"]
    if not all((config.CACHE_DIR / name).exists() for name in needed):
        pytest.skip("data_cache/ is not built; run scripts/01_build_data.py first")
    jobs = [(box, "reference", None) for box in BOXES] + [(box, mode, cut) for box, mode, cut, _ in SCENARIOS]
    results = Parallel(n_jobs=4, backend="loky")(delayed(build_scenario)(*job) for job in jobs)
    return dict(zip(jobs, results))


# ---------------------------------------------------------------------------
# Comparing two builds
# ---------------------------------------------------------------------------
def same(a, b):
    """Element-wise exact equality, with missing == missing."""
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype.kind in "fcbiu" and b.dtype.kind in "fcbiu":
        a, b = a.astype(float), b.astype(float)
        return (a == b) | (np.isnan(a) & np.isnan(b))
    if a.dtype.kind == "M" or b.dtype.kind == "M":
        return pd.to_datetime(a).to_numpy() == pd.to_datetime(b).to_numpy()
    return pd.Series(a).astype(str).to_numpy() == pd.Series(b).astype(str).to_numpy()


def compare_tables(reference, other, keys, skip):
    """{column: number of differing rows} over the rows both tables share (by key). Labels are skipped."""
    joined = reference.merge(other, on=keys, how="inner", suffixes=("", "__other"))
    problems = {}
    for column in reference.columns:
        if column in keys or column in LABEL_COLUMNS or column in skip:
            continue
        if f"{column}__other" not in joined:
            problems[column] = "missing in the rebuilt table"
            continue
        different = ~same(joined[column], joined[f"{column}__other"])
        if different.any():
            problems[column] = int(different.sum())
    return problems, len(joined)


def dated(table, name):
    """The issue date of each row (checkpoints: 1 Jan of their year, the day they are 'as of')."""
    if name == "checkpoints":
        return pd.to_datetime(table["year"].astype(str) + "-01-01")
    return pd.to_datetime(table["issue_date"])


def rows_to_compare(table, name, mode, cut, data_end):
    """Rows whose features must be identical after the change.

    P1 issues strictly before the cut (the look ON the cut day is itself
    deleted or scrambled). Season ratings and checkpoints only use data
    strictly before their date, so with dates kept (scramble) they are
    compared up to and including the cut. A truncated build has no season
    rating dated after its last look.
    """
    if mode == "static":
        return table
    date = dated(table, name)
    if name == "p1":
        keep = date < cut
    elif name == "checkpoints":
        keep = date <= cut
    elif mode == "scramble":
        keep = date <= cut
    else:
        keep = (date < cut) & (date <= data_end)
    return table[keep.to_numpy()]


def with_planted_columns(p1, static_full):
    """Two deliberately bad columns: the NEXT look's rel (look-ahead) and pc / static full (a static leak)."""
    p1 = p1.sort_values(["uid", "issue_date"]).copy()
    p1["planted_peek"] = p1.groupby("uid")["rel"].shift(-1)
    p1["planted_static"] = p1["pc"] / p1["uid"].map(static_full).to_numpy()
    return p1


def compare_scenario(builds, box, mode, cut):
    """Compare one scenario with its box's reference build. Returns (problems, facts for the summary)."""
    reference = builds[(box, "reference", None)]
    other = builds[(box, mode, cut)]
    cut_ts = pd.Timestamp(cut) if cut else None
    problems, facts = {}, {}
    for name, keys in KEYS.items():
        if mode == "static":
            skip = STATIC_MAY_CHANGE[name]
        else:
            skip = prior_columns_not_yet_final(name, cut_ts)
        ref_rows = rows_to_compare(reference[name], name, mode, cut_ts, other["data_end"])
        new_rows = rows_to_compare(other[name], name, mode, cut_ts, other["data_end"])
        found, n_joined = compare_tables(ref_rows, new_rows, keys, skip)
        facts[name] = {"rows_compared": n_joined, "rows_expected": len(ref_rows)}
        if mode != "static" and n_joined != len(ref_rows):
            found["rows"] = f"{len(ref_rows)} expected, {n_joined} present in the rebuilt table"
        if found:
            problems[name] = found
    problems.update(compare_grids(reference["neighbour_grid"], other["neighbour_grid"], mode, cut_ts))
    return problems, facts


def compare_grids(reference, other, mode, cut):
    """Neighbour-grid arrays at the grid dates both builds share (and, unless static, up to the cut)."""
    n = min(len(reference["grid"]), len(other["grid"]))
    assert list(reference["grid"][:n]) == list(other["grid"][:n])
    assert list(reference["uids"]) == list(other["uids"])
    if mode == "scramble":
        n = int((pd.to_datetime(reference["grid"]) <= cut).sum())
    problems = {}
    for name in ("asof", "zero", "R_anom", "R_chg3", "R_zero"):
        different = ~same(reference[name][:, :n], other[name][:, :n])
        if different.any():
            problems[f"neighbour_grid {name}"] = int(different.sum())
    return problems


def save_summary(key, summary):
    """Add one scenario's result to artifacts/leakage_hunt.json."""
    path = config.ARTIFACTS_DIR / "leakage_hunt.json"
    try:
        everything = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        everything = {}
    everything[key] = summary
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(everything, indent=1, default=str))


# ---------------------------------------------------------------------------
# The tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("box, mode, cut, probes", [s for s in SCENARIOS if s[1] != "static"],
                         ids=[f"{s[1]}-{s[0]}-{s[2]}" for s in SCENARIOS if s[1] != "static"])
def test_features_before_the_cut_ignore_the_future(builds, box, mode, cut, probes):
    """Deleting (truncate) or scrambling (scramble) everything from the cut on changes no feature before it."""
    problems, facts = compare_scenario(builds, box, mode, cut)

    # The test must be able to fail: a planted next-look column must be caught, and the
    # change must have removed real future information (some label before the cut moved).
    cut_ts = pd.Timestamp(cut)
    reference, other = builds[(box, "reference", None)], builds[(box, mode, cut)]
    planted, _ = compare_tables(
        rows_to_compare(with_planted_columns(reference["p1"], reference["static_full"]), "p1", mode, cut_ts, None),
        rows_to_compare(with_planted_columns(other["p1"], other["static_full"]), "p1", mode, cut_ts, None),
        KEYS["p1"], skip=set(reference["p1"].columns) - set(KEYS["p1"]))
    ref_p1 = rows_to_compare(reference["p1"], "p1", mode, cut_ts, None)
    new_p1 = rows_to_compare(other["p1"], "p1", mode, cut_ts, None)
    both = ref_p1.merge(new_p1, on=KEYS["p1"], suffixes=("", "__other"))
    labels_moved = int((~same(both["y_R30"], both["y_R30__other"]) | ~same(both["label_ok"], both["label_ok__other"])
                        | ~same(both["y_D0"], both["y_D0__other"])).sum())
    near_cut = int((ref_p1["issue_date"] >= cut_ts - pd.Timedelta(days=config.HORIZON_DAYS)).sum())

    save_summary(f"{mode} {box} {cut}", {
        "probes": probes, "result": "PASS" if not problems else "FAIL", "mismatches": problems, "tables": facts,
        "p1_rows_within_90_days_before_cut": near_cut, "p1_rows_whose_labels_changed": labels_moved,
        "planted_peek_rows_caught": planted.get("planted_peek", 0),
        "prior_columns_compared_strictly": {"P1 dam_rate_*": bool(cut_ts >= P1_PRIOR_FINAL),
                                            "P2 dam_rate_P2*": bool(cut_ts >= P2_PRIOR_FINAL)},
    })
    assert not problems, f"look-ahead found ({mode} {box} at {cut}, probing: {probes}): {problems}"
    assert near_cut > 0 and labels_moved > 0, "the change removed no future information: the test is vacuous"
    assert planted.get("planted_peek", 0) > 0, "a planted look-ahead column was not caught"


@pytest.mark.parametrize("box", list(BOXES))
def test_prereg_static_values_never_reach_a_feature(builds, box):
    """Placebo: random new static full / wet share / n_pre_obs move only at-risk-derived columns.

    test_no_lookahead.py holds these statics fixed, so it cannot see a
    feature that (wrongly) uses them. This one can.
    """
    problems, facts = compare_scenario(builds, box, "static", None)
    reference, other = builds[(box, "reference", None)], builds[(box, "static", None)]
    planted, _ = compare_tables(with_planted_columns(reference["p1"], reference["static_full"]),
                                with_planted_columns(other["p1"], other["static_full"]),
                                KEYS["p1"], skip=set(reference["p1"].columns) - set(KEYS["p1"]))
    save_summary(f"static {box}", {
        "probes": "placebo: PREREG static full, wet share and n_pre_obs randomised, events kept",
        "result": "PASS" if not problems else "FAIL", "mismatches": problems, "tables": facts,
        "allowed_to_change": {k: sorted(v) for k, v in STATIC_MAY_CHANGE.items()},
        "planted_static_rows_caught": planted.get("planted_static", 0),
    })
    assert not problems, f"a feature depends on the PREREG static values ({box}): {problems}"
    assert facts["p1"]["rows_compared"] > 0.5 * facts["p1"]["rows_expected"]
    assert planted.get("planted_static", 0) > 0, "a planted static-full column was not caught"
    # Sanity: the placebo really changed what it should (the R30 at-risk flags).
    both = reference["p1"].merge(other["p1"], on=KEYS["p1"], suffixes=("", "__other"))
    assert (~same(both["at_risk_R30"], both["at_risk_R30__other"])).any()


def test_dam_rate_on_validation_rows_ignores_answers_not_final_by_the_issue(builds):
    """dam_rate_* on VAL rows before a 2009-02-27 cut must not change when the data after the cut is deleted.

    LEAK-1, fixed: the prior used to include TRAIN answers only final in Jan-Apr 2009, so these
    rows moved. issues.train_prior_sums now counts only TRAIN forecasts with t + 120 days < 2009-01-01.
    """
    cut = "2009-02-27"
    reference, other = builds[("nsw_box", "reference", None)], builds[("nsw_box", "truncate", cut)]
    columns = sorted(P1_PRIOR_COLUMNS["p1"])

    def val_rows(p1):
        """VAL rows issued before the cut."""
        return p1[(p1["split"] == "VAL") & (p1["issue_date"] < pd.Timestamp(cut))][KEYS["p1"] + columns]

    found, n = compare_tables(val_rows(reference["p1"]), val_rows(other["p1"]), KEYS["p1"], skip=set())
    save_summary("LEAK-1 dam_rate on VAL rows, nsw_box cut 2009-02-27",
                 {"rows_compared": n, "mismatching_rows_per_column": found})
    assert n > 0
    assert not found, f"dam_rate on VAL rows used answers that were not final: {found}"
