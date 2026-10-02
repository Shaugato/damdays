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
    (physics, sequences, frailty sums) should be added to GENERATORS below.

PREREG static quantities (the pre-2016 "full", population flags, at-risk
flags) are held fixed: they define WHAT is scored, not model inputs.

Runtime: about 5 minutes (4 builds, run 4 at a time).
"""
import json
import pickle

import numpy as np
import pandas as pd
import pytest
from joblib import Parallel, delayed

from damdays import config
from damdays.data.events import build_events
from damdays.features.build import build_all
from damdays.features.spec import LABEL_COLUMNS

CUTS = {"nsw_cw": "2014-07-09", "wvic_sesa": "2012-07-09"}
HORIZON = pd.Timedelta(days=config.HORIZON_DAYS)

# Generators to test: name -> function(panel, attrs, events, rain_by_cell) -> dict of tables.
GENERATORS = {"core features (build_all)": lambda *inputs: build_all(*inputs, verbose=False)}

# How to compare each table: (key columns, date column used to select "before the cut").
# A checkpoint for year Y is dated 1 Jan Y (it uses looks before that date).
TABLES = {
    "p1": (["uid", "issue_date"], "issue_date"),
    "p2_dam": (["uid", "season"], "issue_date"),
    "p2_cell": (["hex_id", "season"], "issue_date"),
    "checkpoints": (["uid", "year"], None),
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
    """Run one generator on one region's full (cut=None) or truncated data."""
    return GENERATORS[generator](*region_inputs(region, cut))


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
    """All (generator, region, full/truncated) builds, run up to 4 at a time."""
    load_inputs()   # skip early if the data layer is missing
    jobs = [(g, region, cut) for g in GENERATORS for region, cut in CUTS.items() for cut in (None, cut)]
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


def save_summary(region, summary):
    """Record what was compared in artifacts/lookahead_test.json (one entry per region)."""
    path = config.ARTIFACTS_DIR / "lookahead_test.json"
    everything = json.loads(path.read_text()) if path.exists() else {}
    everything[region] = summary
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(everything, indent=1, default=int))


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
    assert not report, f"look-ahead found in {generator}, {region}, cut {cut}: {report}"

    # The test must be able to fail. Check that it compared the risky rows,
    # that the truncation really removed future information, and that a
    # planted leak in these very tables is caught.
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

    save_summary(region, {
        "generator": generator, "cut": cut, "result": "PASS: 0 mismatching values",
        "tables_compared": compared,
        "p1_rows_within_90_days_before_cut": int(near_cut.sum()),
        "p1_rows_failing_label_ok_compared": int((~p1_full["label_ok"]).sum()),
        "p1_rows_whose_labels_changed_after_truncation": int(labels_changed.sum()),
        "planted_peek_rows_caught": planted["planted_peek"],
        "neighbour_grid_dates_compared": int((pd.to_datetime(full["neighbour_grid"]["grid"])
                                              < pd.Timestamp(cut)).sum()),
    })


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
