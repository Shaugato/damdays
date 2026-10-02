"""Look-ahead test (audit version): deleting the future must not change any feature of the past.

The idea is simple. If a feature for a forecast issued on day D uses only
information from on or before D, then deleting every piece of data dated
after some cut date cannot change that feature for any D before the cut.

For each development region, at a mid-year cut date that is not on any
calendar grid (nsw_cw 2014-07-09, wvic_sesa 2012-07-09):
  1. Build all feature tables from the region's full data.
  2. Delete every satellite look on or after the cut, every rain month that
     had not ended by the cut, and re-derive the events from what is left.
  3. Rebuild all feature tables from the truncated data.
  4. For every issue before the cut, compare EVERY column (P1, P2 dam,
     P2 cell, checkpoints, neighbour grid) except the labels, which describe
     the future by definition. Values must be bit-for-bit identical.

Fixes from the pre-event leakage audit:
  * ALL at-risk rows are kept, including those whose label is not
    determinable (label_ok False). The rows just before the cut, whose
    90-day window runs past it, are exactly where a leak would show.
  * The cuts are mid-year and off the 1st/16th neighbour grid.
  * It runs on every generator inside build_all, so a new feature added
    there is covered automatically. A generator built outside build_all
    (physics, sequences) should be added to GENERATORS below.
  * Tidemark's per-dam frailty sums (damdays.models.frailty) are rebuilt
    from each P1 table and compared too (table "p1_frailty"). They are
    where future LABELS could leak, so a planted leak (records counted
    without the 120-day wait) must be caught as well.
  * The physics generator (damdays.models.physics: the water-balance columns
    ph_p_R30 / ph_p_D0 and the yearly balance parameters) is tested the same
    way. A version with a planted leak (the Kalman filter reading the issue
    month's own rain before the month is over) is built too and must be caught.
  * The nets' 24-month input sequences (damdays.features.sequences): the
    monthly table (one row per dam and month, compared for months that ended
    before the cut) and every look's sequence (compared through a 64-bit
    fingerprint of its 216 numbers). A planted leak (a window that includes
    the unfinished issue month) must be caught.

PREREG static quantities (the pre-2016 "full", population flags, at-risk
flags) are held fixed: they define WHAT is scored, not model inputs.

Runtime: about 15-25 minutes (4 builds per generator and planted leak, run 4 at a time).
"""
import json
import pickle
import time

import numpy as np
import pandas as pd
import pytest
from joblib import Parallel, delayed

from damdays import config
from damdays.data.events import build_events
from damdays.features import sequences
from damdays.features.build import build_all
from damdays.features.spec import LABEL_COLUMNS
from damdays.models import frailty, fusion, physics, rows

CUTS = {"nsw_cw": "2014-07-09", "wvic_sesa": "2012-07-09"}
HORIZON = pd.Timedelta(days=config.HORIZON_DAYS)


def frailty_sums(p1, final_after_days=config.ANSWER_FINAL_DAYS):
    """The frailty sums R, V, n of every P1 issue, for each event kind (damdays.models.frailty).

    Tidemark's real anchor is a tree's prediction from causal features, which
    this test already proves causal. Any causal probability exercises the
    same time rules, so a stand-in is used: the issue's own dam_rate_<kind>.
    What is tested: a past forecast counts only once its answer is final
    (t_j + 120 days <= t), and the answers of final records survive truncation.
    final_after_days=0 plants a leak (a record counts from its own issue day).
    """
    out = p1[["uid", "issue_date"]].reset_index(drop=True)
    every_row = np.arange(len(p1))
    for kind in rows.P1_KINDS:
        at_risk = p1[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)
        is_record = at_risk & fusion.track_record_mask(p1, kind, every_row)
        y = p1[rows.p1_label(kind)].to_numpy(dtype=float)
        p = np.clip(np.nan_to_num(p1[f"dam_rate_{kind}"].to_numpy(dtype=float), nan=0.5), 0.01, 0.99)
        R, V, n = frailty.matured_residual_sums(p1["uid"], p1["issue_date"], is_record, y, p, final_after_days)
        out[f"frailty_R_{kind}"], out[f"frailty_V_{kind}"], out[f"frailty_n_{kind}"] = R, V, n
    return out


def core_features_and_frailty(*inputs):
    """build_all's tables plus the frailty sums computed from its P1 table."""
    tables = build_all(*inputs, verbose=False)
    tables["p1_frailty"] = frailty_sums(tables["p1"])
    return tables


def physics_features(panel, attrs, events, rain_by_cell):
    """The water-balance columns of every P1 issue and the yearly balance parameters (damdays.models.physics)."""
    out = physics.build_physics(panel, attrs, rain_by_cell)
    return {"p1_physics": out["p1_physics"], "physics_params": out["physics_params"]}


def physics_with_planted_leak(panel, attrs, events, rain_by_cell):
    """build_physics with a planted leak: the filter reads the issue month's OWN rain, before the month is over.

    The honest filter uses that calendar month's average over earlier years.
    This is the most likely physics leak, so the test must catch it.
    """
    honest = physics.same_month_earlier_years_mean
    physics.same_month_earlier_years_mean = lambda values: values     # "average" = the month's own total
    try:
        return physics_features(panel, attrs, events, rain_by_cell)
    finally:
        physics.same_month_earlier_years_mean = honest


def net_sequences(panel, attrs, events, rain_by_cell):
    """The nets' monthly table and every look's 24-month sequence (damdays.features.sequences).

    Also returns the monthly history and the look list (not compared directly):
    sequences_can_fail rebuilds leaky sequences from them.
    """
    return sequences.lookahead_tables(panel, attrs, rain_by_cell)


# Generators to test: name -> function(panel, attrs, events, rain_by_cell) -> dict of tables.
CORE = "core features (build_all) + frailty sums"
PHYSICS = "physics water balance (damdays.models.physics)"
SEQUENCES = "net sequences (damdays.features.sequences)"
GENERATORS = {CORE: core_features_and_frailty, PHYSICS: physics_features, SEQUENCES: net_sequences}
# Deliberately leaky versions, built the same way: the test checks they ARE caught.
PLANTED_LEAKS = {PHYSICS: physics_with_planted_leak}
BUILDERS = dict(GENERATORS, **{f"{name} [planted leak]": f for name, f in PLANTED_LEAKS.items()})

# How to compare each table: (key columns, date column used to select "before the cut").
# A checkpoint for year Y is dated 1 Jan Y (it uses looks before that date).
TABLES = {
    "p1": (["uid", "issue_date"], "issue_date"),
    "p1_frailty": (["uid", "issue_date"], "issue_date"),
    "p2_dam": (["uid", "season"], "issue_date"),
    "p2_cell": (["hex_id", "season"], "issue_date"),
    "checkpoints": (["uid", "year"], None),
    "p1_physics": (["uid", "issue_date"], "issue_date"),
    "physics_params": (["year"], None),     # balance parameters of checkpoint Y: pairs before 1 Jan Y
    "sequence_months": (["uid", "month"], "month_complete"),   # a month counts once it has ended
    "p1_sequences": (["uid", "issue_date"], "issue_date"),
}


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------
def load_inputs():
    """The data layer from data_cache/ (skip the test if it has not been built)."""
    needed = ["panel.pkl", "attributes.pkl", "events.pkl", "silo_rain.pkl"]
    if not all((config.CACHE_DIR / name).exists() for name in needed):
        pytest.skip("data_cache/ is not built; run scripts/01_build_data.py first")
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    with open(config.CACHE_DIR / "silo_rain.pkl", "rb") as f:
        rain_by_cell = pickle.load(f)
    return panel, attrs, rain_by_cell


def region_inputs(region, cut=None):
    """One region's inputs, optionally with everything from the cut date on deleted.

    Events are always re-derived from the (possibly truncated) panel, so no
    event that is only confirmed after the cut can survive.
    """
    panel, attrs, rain_by_cell = load_inputs()
    attrs = attrs[attrs["region"] == region].reset_index(drop=True)
    panel = panel[panel["region"] == region]
    rain_by_cell = dict(rain_by_cell)
    if cut is not None:
        cut = pd.Timestamp(cut)
        panel = panel[panel["date"] < cut]
        # A month's rain total is known only once the month has ended:
        # keep the months that ended before the cut.
        ended = rain_by_cell["months"] < cut.year * 100 + cut.month
        rain_by_cell["months"] = rain_by_cell["months"][ended]
        rain_by_cell["rain"] = rain_by_cell["rain"][:, ended]
    events = build_events(panel, attrs)
    return panel, attrs, events, rain_by_cell


def build_one(generator, region, cut):
    """Run one generator (or planted-leak version) on one region's full (cut=None) or truncated data."""
    return BUILDERS[generator](*region_inputs(region, cut))


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def same_values(a, b):
    """Element-wise exact equality, with missing == missing."""
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype.kind in "fc" or b.dtype.kind in "fc":
        a, b = a.astype(float), b.astype(float)
        return (a == b) | (np.isnan(a) & np.isnan(b))
    if a.dtype.kind == "M" or b.dtype.kind == "M":
        return pd.to_datetime(a).to_numpy() == pd.to_datetime(b).to_numpy()
    return a.astype(str) == b.astype(str)


def compare(reference, rebuilt, keys):
    """Compare two tables row by row. Returns a dict describing every difference (empty = identical)."""
    problems = {}
    reference = reference.sort_values(keys).reset_index(drop=True)
    rebuilt = rebuilt.sort_values(keys).reset_index(drop=True)
    if len(reference) != len(rebuilt):
        return {"row count": f"{len(reference)} with all data vs {len(rebuilt)} truncated"}
    for key in keys:
        if not same_values(reference[key], rebuilt[key]).all():
            return {"rows": f"different {key} values"}
    only_one_side = sorted(set(reference.columns) ^ set(rebuilt.columns))
    if only_one_side:
        problems["columns on one side only"] = only_one_side
    for column in reference.columns:
        if column in keys or column in LABEL_COLUMNS or column not in rebuilt.columns:
            continue
        different = ~same_values(reference[column], rebuilt[column])
        if different.any():
            problems[column] = int(different.sum())
    return problems


def before_cut(table, name, cut):
    """Rows of a table that belong to issues (or checkpoints) dated before the cut."""
    date_column = TABLES[name][1]
    if date_column is None:   # checkpoints: dated 1 Jan of their year
        dates = pd.to_datetime(table["year"].astype(str) + "-01-01")
    else:
        dates = pd.to_datetime(table[date_column])
    return table[(dates < pd.Timestamp(cut)).to_numpy()]


def compare_grid(reference, rebuilt, cut):
    """Neighbour grid values at grid dates before the cut must be identical."""
    # The truncated grid simply stops earlier; its first n dates are the same dates.
    n = int((pd.to_datetime(reference["grid"]) < pd.Timestamp(cut)).sum())
    assert list(reference["grid"][:n]) == list(rebuilt["grid"][:n])
    assert list(reference["uids"]) == list(rebuilt["uids"])
    problems = {}
    for name in ("asof", "zero", "R_anom", "R_chg3", "R_zero"):
        different = ~same_values(reference[name][:, :n], rebuilt[name][:, :n])
        if different.any():
            problems[f"grid {name}"] = int(different.sum())
    return problems


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def builds():
    """All (generator, region, full/truncated) builds, planted leaks included, run up to 4 at a time."""
    load_inputs()   # skip early if the data layer is missing
    jobs = [(g, region, cut) for g in BUILDERS for region, cut in CUTS.items() for cut in (None, cut)]
    results = Parallel(n_jobs=min(4, len(jobs)), backend="loky")(
        delayed(build_one)(g, region, cut) for g, region, cut in jobs)
    return {job: result for job, result in zip(jobs, results)}


def columns_compared(table, keys):
    """The columns that compare() checks (everything except keys and labels)."""
    return [c for c in table.columns if c not in keys and c not in LABEL_COLUMNS]


def with_planted_peek(p1):
    """P1 plus a deliberately leaky column: the dam's NEXT at-risk look's rel."""
    p1 = p1.sort_values(["uid", "issue_date"]).copy()
    p1["planted_peek"] = p1.groupby("uid")["rel"].shift(-1)
    return p1


def save_summary(key, summary):
    """Record what was compared in artifacts/lookahead_test.json (one entry per region and generator).

    Each entry carries the time it was written (run_at). A failure is recorded too ("FAIL: ..."),
    so the ladder report (scripts/12_ladder_val.py, PREREG condition b) can never read an old
    PASS after a newer run failed.
    """
    path = config.ARTIFACTS_DIR / "lookahead_test.json"
    everything = json.loads(path.read_text()) if path.exists() else {}
    everything[key] = dict(summary, run_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(everything, indent=1, default=int))


# ---------------------------------------------------------------------------
# "The test must be able to fail": one check per generator
# ---------------------------------------------------------------------------
def core_can_fail(builds, region, cut):
    """Core tables: risky rows were compared, truncation removed information, planted leaks are caught."""
    full, truncated = builds[(CORE, region, None)], builds[(CORE, region, cut)]
    p1_full = before_cut(full["p1"], "p1", cut).sort_values(["uid", "issue_date"])
    p1_trunc = before_cut(truncated["p1"], "p1", cut).sort_values(["uid", "issue_date"])
    near_cut = p1_full["issue_date"] >= pd.Timestamp(cut) - HORIZON
    assert near_cut.sum() > 1000, "too few issues within 90 days of the cut were compared"
    assert (~p1_full["label_ok"]).sum() > 0, "rows failing label_ok must be kept and compared"
    labels_changed = ~same_values(p1_full["y_R30"].to_numpy(), p1_trunc["y_R30"].to_numpy())
    labels_changed |= ~same_values(p1_full["label_ok"].to_numpy(), p1_trunc["label_ok"].to_numpy())
    assert labels_changed.any(), "truncation removed no future information: the test would be vacuous"
    planted = compare(before_cut(with_planted_peek(full["p1"]), "p1", cut),
                      before_cut(with_planted_peek(truncated["p1"]), "p1", cut), TABLES["p1"][0])
    assert "planted_peek" in planted, "a planted look-ahead column was not caught"
    # Same for the frailty: counting records without the 120-day wait reads future labels.
    leaky = compare(before_cut(frailty_sums(full["p1"], final_after_days=0), "p1_frailty", cut),
                    before_cut(frailty_sums(truncated["p1"], final_after_days=0), "p1_frailty", cut),
                    TABLES["p1_frailty"][0])
    assert "frailty_R_R30" in leaky, "a planted frailty leak (no 120-day wait) was not caught"
    return {
        "p1_rows_within_90_days_before_cut": int(near_cut.sum()),
        "p1_rows_failing_label_ok_compared": int((~p1_full["label_ok"]).sum()),
        "p1_rows_whose_labels_changed_after_truncation": int(labels_changed.sum()),
        "planted_peek_rows_caught": planted["planted_peek"],
        "planted_frailty_leak_rows_caught": leaky["frailty_R_R30"],
        "neighbour_grid_dates_compared": int((pd.to_datetime(full["neighbour_grid"]["grid"])
                                              < pd.Timestamp(cut)).sum()),
    }


def physics_can_fail(builds, region, cut):
    """Physics: values near the cut were compared, and two planted leaks are caught.

    1. a column holding the dam's NEXT forecast's ph_p_R30;
    2. the realistic one: the filter reading the issue month's own (unfinished) rain.
    """
    full, truncated = builds[(PHYSICS, region, None)], builds[(PHYSICS, region, cut)]
    reference = before_cut(full["p1_physics"], "p1_physics", cut)
    near_cut = (reference["issue_date"] >= pd.Timestamp(cut) - HORIZON) & reference["ph_p_R30"].notna()
    assert near_cut.sum() > 1000, "too few physics values within 90 days of the cut were compared"

    def with_next_value(table):
        table = table.sort_values(["uid", "issue_date"]).copy()
        table["planted_peek"] = table.groupby("uid")["ph_p_R30"].shift(-1)
        return table

    planted = compare(before_cut(with_next_value(full["p1_physics"]), "p1_physics", cut),
                      before_cut(with_next_value(truncated["p1_physics"]), "p1_physics", cut),
                      TABLES["p1_physics"][0])
    assert "planted_peek" in planted, "a planted look-ahead column was not caught in the physics table"
    leak_name = f"{PHYSICS} [planted leak]"
    leaky = compare(before_cut(builds[(leak_name, region, None)]["p1_physics"], "p1_physics", cut),
                    before_cut(builds[(leak_name, region, cut)]["p1_physics"], "p1_physics", cut),
                    TABLES["p1_physics"][0])
    assert leaky, "a planted physics leak (the issue month's own rain) was not caught"
    return {
        "physics_values_within_90_days_before_cut": int(near_cut.sum()),
        "checkpoint_years_compared": int(len(before_cut(full["physics_params"], "physics_params", cut))),
        "planted_peek_rows_caught": planted["planted_peek"],
        "planted_current_month_rain_leak_caught": leaky,
    }


def sequences_can_fail(builds, region, cut):
    """Sequences: looks near the cut were compared, truncation changed the cut's month, a planted leak is caught.

    The planted leak is the realistic one: a window that ends AT the issue month
    (whose looks and rain are not over on the issue day) instead of the month before.
    """
    full, truncated = builds[(SEQUENCES, region, None)], builds[(SEQUENCES, region, cut)]
    reference = before_cut(full["p1_sequences"], "p1_sequences", cut)
    near_cut = reference["issue_date"] >= pd.Timestamp(cut) - HORIZON
    assert near_cut.sum() > 1000, "too few sequences within 90 days of the cut were compared"

    cut_month = pd.Timestamp(cut).strftime("%Y-%m")       # the month the cut falls in: not over at the cut
    changed = compare(full["sequence_months"].query("month == @cut_month"),
                      truncated["sequence_months"].query("month == @cut_month"), TABLES["sequence_months"][0])
    assert changed, "truncation changed nothing in the cut's own month: the test would be vacuous"

    issues = before_cut(full["sequence_issues"], "p1_sequences", cut)
    issues = issues[issues["issue_date"] >= pd.Timestamp(cut) - HORIZON]
    leaky = compare(sequences.sequence_table(full["monthly_history"], issues, window_end_offset=0),
                    sequences.sequence_table(truncated["monthly_history"], issues, window_end_offset=0),
                    TABLES["p1_sequences"][0])
    assert "sequence_fingerprint" in leaky, "a planted sequence leak (the unfinished issue month) was not caught"
    return {
        "sequences_within_90_days_before_cut": int(near_cut.sum()),
        "cut_month_values_changed_by_truncation": changed,
        "planted_issue_month_leak_rows_caught": leaky["sequence_fingerprint"],
    }


# A generator added to GENERATORS needs an entry here: a test that cannot fail proves nothing.
CAN_FAIL = {CORE: core_can_fail, PHYSICS: physics_can_fail, SEQUENCES: sequences_can_fail}


@pytest.mark.parametrize("generator", list(GENERATORS))
@pytest.mark.parametrize("region", list(CUTS))
def test_features_before_the_cut_do_not_change(builds, generator, region):
    """Every non-label column of every table is identical for issues before the cut."""
    cut = CUTS[region]
    full = builds[(generator, region, None)]
    truncated = builds[(generator, region, cut)]

    report, compared = {}, {}
    for name, (keys, _) in TABLES.items():
        if name not in full:
            continue
        reference = before_cut(full[name], name, cut)
        problems = compare(reference, before_cut(truncated[name], name, cut), keys)
        compared[name] = {"rows": len(reference), "columns": len(columns_compared(reference, keys))}
        if problems:
            report[name] = problems
    if "neighbour_grid" in full:
        problems = compare_grid(full["neighbour_grid"], truncated["neighbour_grid"], cut)
        if problems:
            report["neighbour_grid"] = problems
    key = region if generator == CORE else f"{region} | {generator}"
    if report:
        save_summary(key, {"generator": generator, "cut": cut, "result": f"FAIL: look-ahead found: {report}"})
    assert not report, f"look-ahead found in {generator}, {region}, cut {cut}: {report}"

    # The test must be able to fail. Check that it compared the risky rows,
    # that the truncation really removed future information, and that a
    # planted leak in these very tables is caught.
    try:
        evidence = CAN_FAIL[generator](builds, region, cut)
    except AssertionError as problem:
        save_summary(key, {"generator": generator, "cut": cut, "result": f"FAIL: the test could not fail: {problem}"})
        raise
    save_summary(key, dict({"generator": generator, "cut": cut, "result": "PASS: 0 mismatching values",
                            "tables_compared": compared}, **evidence))


def test_comparison_catches_a_peeking_feature():
    """A feature that peeks one look ahead must be caught by the same comparison."""
    days = np.arange(0, 400, 16)
    level = np.sin(days / 40.0)

    def table(n_looks):
        """The two features computed from the first n_looks looks only."""
        part = pd.Series(level[:n_looks])
        return pd.DataFrame({
            "uid": "dam",
            "issue_date": pd.Timestamp("2000-01-01") + pd.to_timedelta(days[:n_looks], unit="D"),
            "honest": part.rolling(3, min_periods=1).mean(),       # current and earlier looks only
            "peeking": part.shift(-1),                             # the NEXT look: a leak
        })

    full, truncated = table(len(days)), table(15)
    cut = full["issue_date"].iloc[15]
    problems = compare(full[full["issue_date"] < cut], truncated, ["uid", "issue_date"])
    assert "honest" not in problems
    assert problems.get("peeking") == 1
