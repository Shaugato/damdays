"""Build the DamDays data layer and check it against the pre-event counts.

Run from the repo folder:
    .venv/Scripts/python.exe scripts/01_build_data.py

What it does, in order:
  1. Download check   every waterbody in the manifest has a time-series file
  2. Panel            one clean row per waterbody per local day
  3. Attributes       shape, pre-2016 history, population flags,
                      2 km hex cell, nearest SILO cell, folds
  4. Events           D0, R30 and D0-gradual, as defined in PREREG.md
  5. Rainfall         one monthly SILO rain series per grid cell
  6. Summary          counts, compared with the check values from the
                      pre-event research (they must match exactly)

Outputs go to data_cache/ (rebuildable, not committed):
    panel.pkl, panel_qc.csv, attributes.pkl/.csv, events.pkl/.csv,
    silo_rain.pkl, download_check.json
and a small summary to artifacts/data_checks.json (committed).

The sealed test region is never read (damdays.data.guard).
"""
import json
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

# Let "import damdays" work when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damdays import config  # noqa: E402
from damdays.data import attributes, cells, events, panel, rainfall, splits  # noqa: E402

# Counts the pre-event research build produced from the same raw files.
CHECK_VALUES = {
    "valid observations": 5_227_589,
    "has_hist waterbodies": 6_475,
    "dam-like waterbodies": 1_683,
    "persistent waterbodies": 969,
    "dam-like D0 events": 15_949,
    "dam-like R30 events": 31_344,
    "dam-like D0g events": 10_213,
}


def step(message):
    """Print a step heading with the time, so long runs are easy to follow."""
    print(f"\n[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def save_table(table, name, also_csv=False):
    """Save a DataFrame as pickle (fast, keeps types) and optionally CSV (readable)."""
    table.to_pickle(config.CACHE_DIR / f"{name}.pkl")
    if also_csv:
        table.to_csv(config.CACHE_DIR / f"{name}.csv", index=False)


def build():
    """Run every step; returns the objects needed for the summary."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    step("1. Download check")
    manifest = panel.load_manifest()
    download = panel.check_downloads(manifest)
    print(f"  {download['n_present']} of {download['n_manifest']} files present, "
          f"{len(download['missing'])} missing")
    with open(config.CACHE_DIR / "download_check.json", "w") as f:
        json.dump(download, f, indent=1)
    if download["missing"]:
        raise SystemExit("Some time-series files are missing; download them before building.")

    step("2. Panel (about 1-2 minutes)")
    the_panel, qc = panel.build_panel(manifest)
    save_table(the_panel, "panel")
    qc.to_csv(config.CACHE_DIR / "panel_qc.csv", index=False)

    step("3. Attributes, hex cells, SILO cells and folds")
    attrs = attributes.build_attributes(the_panel, manifest)
    attrs = cells.add_hex_cells(attrs)
    grids, months = rainfall.load_silo_grids()
    attrs = rainfall.assign_silo_cells(attrs, grids)
    attrs = splits.add_folds(attrs)
    save_table(attrs, "attributes", also_csv=True)

    step("4. Events")
    the_events = events.build_events(the_panel, attrs)
    save_table(the_events, "events", also_csv=True)

    step("5. Monthly rain per SILO cell")
    rain = rainfall.rain_by_cell(attrs, grids, months)
    with open(config.CACHE_DIR / "silo_rain.pkl", "wb") as f:
        pickle.dump(rain, f)

    return the_panel, qc, attrs, the_events, rain


def event_table(the_events):
    """Events per population and kind, split by the time block of the start date."""
    the_events = the_events.assign(block=splits.time_block(the_events["start_date"]))
    rows = []
    for population in ("all has_hist", "dam_like", "persistent"):
        subset = the_events if population == "all has_hist" else the_events[the_events[population]]
        kinds = {
            "D0": subset["kind"] == "D0",
            "D0g": subset["gradual"],
            "R30": subset["kind"] == "R30",
        }
        for kind, is_kind in kinds.items():
            chosen = subset[is_kind]
            row = {"population": population, "kind": kind, "events": len(chosen), "dams": chosen["uid"].nunique()}
            for block in ("TRAIN", "VAL", "TEST"):
                row[block] = int((chosen["block"] == block).sum())
            rows.append(row)
    return pd.DataFrame(rows)


def summarise(the_panel, qc, attrs, the_events, rain):
    """Print the summary, compare with the check values, save artifacts/data_checks.json."""
    step("6. Summary")
    print(f"  raw rows {qc['n_raw'].sum():,}; invalid (empty) {qc['n_invalid'].sum():,}; "
          f"out of range {qc['n_out_of_range'].sum():,}; "
          f"days with merged scenes {qc['n_days_with_merged_scenes'].sum():,}")
    print(f"  panel dates {the_panel['date'].min().date()} to {the_panel['date'].max().date()}")
    print("\n  Waterbodies by region:")
    flags = ["has_hist", "dam_like", "persistent", "dam_like_persistent"]
    by_region = attrs.groupby("region")[flags].sum()
    by_region.loc["total"] = by_region.sum()
    print(by_region.to_string())

    dam_like = attrs[attrs["dam_like"]]
    print(f"\n  2 km hex cells holding a dam-like dam: {dam_like['hex_id'].nunique():,}")
    print(f"  SILO cells used: {len(rain['cells']):,}; months {rain['months'][0]} to {rain['months'][-1]}; "
          f"farthest dam from its cell centre: {attrs['silo_dist_km'].max():.2f} km")

    table = event_table(the_events)
    print("\n  Events (TRAIN / VAL / TEST by start date):")
    print(table.to_string(index=False))
    d0 = the_events[the_events["kind"] == "D0"]
    abrupt_share_all = d0["abrupt"].astype(float).mean()
    abrupt_share_dam_like = d0.loc[d0["dam_like"], "abrupt"].astype(float).mean()
    print(f"  D0 abrupt share: all {abrupt_share_all:.2f}, dam-like {abrupt_share_dam_like:.2f}")

    dam_like_counts = events.count_events(the_events, "dam_like")
    got = {
        "valid observations": len(the_panel),
        "has_hist waterbodies": int(attrs["has_hist"].sum()),
        "dam-like waterbodies": int(attrs["dam_like"].sum()),
        "persistent waterbodies": int(attrs["persistent"].sum()),
        "dam-like D0 events": dam_like_counts["D0"],
        "dam-like R30 events": dam_like_counts["R30"],
        "dam-like D0g events": dam_like_counts["D0g"],
    }
    print("\n  Check values (expected from the pre-event research vs this build):")
    all_match = True
    checks = []
    for name, expected in CHECK_VALUES.items():
        match = got[name] == expected
        all_match = all_match and match
        checks.append({"check": name, "expected": expected, "got": got[name], "match": match})
        print(f"    {'OK  ' if match else 'DIFF'} {name:<24} expected {expected:>10,}  got {got[name]:>10,}")

    report = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "all_checks_match": all_match,
        "checks": checks,
        "waterbodies_by_region": by_region.astype(int).to_dict(orient="index"),
        "events": table.to_dict(orient="records"),
        "hex_cells_with_dam_like": int(dam_like["hex_id"].nunique()),
        "silo_cells": int(len(rain["cells"])),
    }
    with open(config.ARTIFACTS_DIR / "data_checks.json", "w") as f:
        json.dump(report, f, indent=1, default=int)
    print(f"\n  {'ALL CHECKS MATCH' if all_match else 'SOME CHECKS DIFFER'}; "
          f"saved {config.ARTIFACTS_DIR / 'data_checks.json'}")
    return all_match


def main():
    started = time.time()
    outputs = build()
    all_match = summarise(*outputs)
    print(f"\nDone in {(time.time() - started) / 60:.1f} min. Outputs in {config.CACHE_DIR}")
    if not all_match:
        sys.exit(1)


if __name__ == "__main__":
    main()
