"""Build the issue tables and causal features, and check them against the pre-event counts.

Run from the repo folder (after scripts/01_build_data.py):
    .venv/Scripts/python.exe scripts/02_build_features.py

What it does:
  1. Loads the data layer from data_cache/ (panel, attributes, events, rain).
  2. damdays.features.build.build_all: checkpoints, neighbour grid, rain
     features, per-dam features and labels, P1 and P2 tables.
  3. Saves the tables to data_cache/features/ (rebuildable, not committed).
  4. Prints row counts per time block and compares them with the check values
     from the pre-event research (they must match exactly), and writes
     artifacts/feature_checks.json.

Takes about 5-8 minutes on a laptop, one process.
The look-ahead test (tests/test_no_lookahead.py) compares against these tables.
"""
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Let "import damdays" work when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damdays import config  # noqa: E402
from damdays.features import spec, store  # noqa: E402
from damdays.features.build import build_all  # noqa: E402

BLOCKS = ("TRAIN", "VAL", "GAP", "TEST")

# Counts the pre-event research build produced from the same raw files.
# "required" ones are the hand-off checks for this step; the rest are extra
# cross-checks from the research data notes.
CHECK_VALUES = {
    # P1 issues: at risk (D0 or R30), label determinable, 1988-01-01 to 2026-06-30
    "P1 rows TRAIN": (896_778, "required"),
    "P1 rows VAL": (394_628, "required"),
    "P1 rows GAP": (26_149, "required"),
    "P1 rows TEST": (907_150, "required"),
    # Primary scoring set: dam-like, Oct-Mar issues, at risk, label determinable
    "R30 primary TRAIN": (145_417, "required"),
    "R30 primary VAL": (66_453, "required"),
    "R30 primary TEST": (142_938, "required"),
    "R30 primary positives TRAIN": (37_766, "extra"),
    "R30 primary positives VAL": (15_861, "extra"),
    "R30 primary positives TEST": (29_415, "extra"),
    "D0 primary TRAIN": (190_771, "extra"),
    "D0 primary VAL": (86_651, "extra"),
    "D0 primary TEST": (176_730, "extra"),
    "D0 primary positives TRAIN": (24_215, "extra"),
    "D0 primary positives VAL": (9_893, "extra"),
    "D0 primary positives TEST": (17_191, "extra"),
    "D0g primary TRAIN": (183_075, "extra"),
    "D0g primary VAL": (83_747, "extra"),
    "D0g primary TEST": (170_981, "extra"),
    "D0g primary positives TRAIN": (16_519, "extra"),
    "D0g primary positives VAL": (6_989, "extra"),
    "D0g primary positives TEST": (11_442, "extra"),
    # P2: dam-like dam-seasons with a determinable label (and how many went dry)
    "P2 dam-like seasons TRAIN": (32_355, "extra"),
    "P2 dam-like seasons VAL": (11_557, "extra"),
    "P2 dam-like seasons TEST": (16_811, "extra"),
    "P2 dam-like D0 seasons TRAIN": (5_788, "extra"),
    "P2 dam-like D0 seasons VAL": (2_069, "extra"),
    "P2 dam-like D0 seasons TEST": (2_924, "extra"),
    "P2 cells": (1_435, "extra"),
    "P2 cell-seasons TRAIN": (27_561, "extra"),
    "P2 cell-seasons VAL": (9_848, "extra"),
    "P2 cell-seasons TEST": (14_331, "extra"),
    "P2 failed cell-seasons TRAIN": (4_668, "extra"),
    "P2 failed cell-seasons VAL": (1_684, "extra"),
    "P2 failed cell-seasons TEST": (2_316, "extra"),
}


def step(message):
    """Print a step heading with the time."""
    print(f"\n[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_inputs():
    """The data layer outputs from data_cache/."""
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    events = pd.read_pickle(config.CACHE_DIR / "events.pkl")
    with open(config.CACHE_DIR / "silo_rain.pkl", "rb") as f:
        rain_by_cell = pickle.load(f)
    return panel, attrs, events, rain_by_cell


def scored_p1(p1):
    """P1 rows that count as issues in the research tables: label determinable and before 2026-07-01."""
    return p1[p1["label_ok"] & (p1["issue_date"] < pd.Timestamp(config.TEST_END))]


def count_values(tables):
    """Every count that has a check value, from the built tables."""
    got = {}
    p1 = scored_p1(tables["p1"])
    primary = p1[p1["dam_like"] & p1["warm"]]
    for block in BLOCKS:
        got[f"P1 rows {block}"] = int((p1["split"] == block).sum())
    for kind, at_risk in (("R30", "at_risk_R30"), ("D0", "at_risk_D0"), ("D0g", "at_risk_D0")):
        rows = primary[primary[at_risk] & primary[f"y_{kind}"].notna()]
        for block in ("TRAIN", "VAL", "TEST"):
            in_block = rows[rows["split"] == block]
            got[f"{kind} primary {block}"] = len(in_block)
            got[f"{kind} primary positives {block}"] = int(in_block[f"y_{kind}"].sum())

    p2 = tables["p2_dam"]
    seasons = p2[p2["dam_like"] & p2["label_ok"]]
    cells = tables["p2_cell"]
    ok_cells = cells[cells["label_ok"]]
    got["P2 cells"] = int(cells["hex_id"].nunique())
    for block in ("TRAIN", "VAL", "TEST"):
        got[f"P2 dam-like seasons {block}"] = int((seasons["split"] == block).sum())
        got[f"P2 dam-like D0 seasons {block}"] = int(seasons.loc[seasons["split"] == block, "y"].sum())
        got[f"P2 cell-seasons {block}"] = int((ok_cells["split"] == block).sum())
        got[f"P2 failed cell-seasons {block}"] = int(ok_cells.loc[ok_cells["split"] == block, "y"].sum())
    return got


def consistency_checks(tables, attrs):
    """Extra sanity checks: the 2016 checkpoint equals the PREREG static full; no forbidden columns."""
    ck = tables["checkpoints"]
    last = ck[ck["year"] == config.LAST_CHECKPOINT_YEAR].set_index("uid")["full_c"]
    static = attrs.set_index("uid")["full"].astype(float)
    both = pd.concat([last.astype(float), static], axis=1, join="inner").dropna()
    max_diff = float((both.iloc[:, 0] - both.iloc[:, 1]).abs().max())
    present_forbidden = sorted((set(tables["p1"].columns) | set(tables["p2_dam"].columns))
                               & {"full", "wet_share", "fill_share"})
    return {"max |full_c(2016) - PREREG full|": max_diff, "forbidden static columns in tables": present_forbidden}


def summarise(tables, attrs):
    """Print the counts and the comparison with the check values; save artifacts/feature_checks.json."""
    step("Check values (expected from the pre-event research vs this build)")
    got = count_values(tables)
    checks, all_required_match, all_match = [], True, True
    for name, (expected, kind) in CHECK_VALUES.items():
        match = got[name] == expected
        all_match = all_match and match
        if kind == "required":
            all_required_match = all_required_match and match
        checks.append({"check": name, "kind": kind, "expected": expected, "got": got[name], "match": match})
        print(f"  {'OK  ' if match else 'DIFF'} {kind:8s} {name:<32} expected {expected:>10,}  got {got[name]:>10,}")

    p1 = tables["p1"]
    extra = {
        "P1 at-risk rows stored (all, incl. label_ok False and after 2026-06)": len(p1),
        "P1 at-risk rows failing label_ok, by block": {
            b: int(((p1["split"] == b) & ~p1["label_ok"]).sum()) for b in BLOCKS},
        "P2 dam rows": len(tables["p2_dam"]),
        "P2 cell rows": len(tables["p2_cell"]),
        "P2 seasons": [int(tables["p2_dam"]["season"].min()), int(tables["p2_dam"]["season"].max())],
        "data end": str(tables["data_end"].date()),
    }
    extra.update(consistency_checks(tables, attrs))
    for key, value in extra.items():
        print(f"  {key}: {value}")

    report = {"built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "all_required_match": all_required_match,
              "all_match": all_match, "checks": checks, "other": extra,
              "feature_spec_R30": spec.p1_tree_features("R30"), "p2_feature_spec": spec.P2_FEATURE_SPEC}
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.ARTIFACTS_DIR / "feature_checks.json", "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"\n  {'ALL REQUIRED CHECKS MATCH' if all_required_match else 'SOME REQUIRED CHECKS DIFFER'}"
          f"{'' if all_match else ' (some extra checks differ, see above)'}; "
          f"saved {config.ARTIFACTS_DIR / 'feature_checks.json'}")
    return all_required_match


def main():
    """Load, build, save, check."""
    started = time.time()
    step("1. Load the data layer")
    panel, attrs, events, rain_by_cell = load_inputs()
    step("2. Build features (checkpoints, neighbours, rain, per-dam features, P1, P2)")
    tables = build_all(panel, attrs, events, rain_by_cell)
    step(f"3. Save to {store.FEATURES_DIR}")
    store.save_tables(tables)
    ok = summarise(tables, attrs)
    print(f"\nDone in {(time.time() - started) / 60:.1f} min.")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
