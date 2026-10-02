"""Build one region's forecasting tables from its raw files, with the same code as the development build.

    data = build_data_layer(region, say)                 # the steps of scripts/01_build_data.py, one region
    tables = build_tables(data, physics_params, say)     # scripts/02's features + the physics + the nets' months
    inputs = tidemark_inputs(tables)                     # what tidemark.predict_tidemark reads

Every step calls the function the development build calls (in brackets), on the region's own rows:
 1. raw files   the region's manifest and DEA time series [damdays.data.panel]. The sealed region's
                are dea_sealed/manifest.csv and dea_sealed/ts/ (refused by damdays.data.guard until the
                unlock switch is on); a development region (the dry run) reads dea_dev/, its own rows only.
                The manifest must list exactly the files whose SHA-256 was verified first.
 2. panel       local dates, invalid rows dropped, same-day scenes merged [panel.build_panel]
 3. attributes  outline shape (from the national DEA polygon file), pre-2016 history and the
                population flags has_hist / dam-like / persistent, from the REGION'S OWN looks before
                2016 [attributes.build_attributes]; 2 km hex cells [cells]; the nearest SILO cell, from
                the region's own SILO key [rainfall]; folds [splits]
 4. events      D0, R30, D0-gradual, with the static pre-2016 "full" [events.build_events]
 5. rain        one monthly series per SILO cell, from the region's SILO key [rainfall.rain_by_cell]
 6. features    checkpoints, neighbours (other dams of the same region), rain features, dam history,
                labels, track records (each dam's own past answers, counted only once final; the dam
                rate shrinks toward the region's own TRAIN-block rate) and the P1 and P2 tables
                [features.build.build_all]
 7. physics     the water balance run with GIVEN parameters (fitted on the development regions' look
                pairs, never refitted here) and the region's typed BoM evaporation shape [physics.build_physics]
 8. area index  the P2 share of nearby waterbodies that went dry [season_rating.add_area_index]
 9. months      the nets' month-by-month history [features.sequences.build_monthly_history]
Nothing here is fitted: the tables hold causal inputs, labels and each dam's own past track record.

A region is built on its own, as each development region was: neighbours and area indexes use
the region's own waterbodies. (The two development regions are more than 200 km apart; at the
sealed region's western edge some development dams lie within 100 km, but, as in the
development build, waterbodies of other regions are never neighbours.)

compare_with_development_store (dry run only) checks the claim "same code": the dry run's region,
rebuilt here from raw files, must equal its rows in the development feature store.
"""
import json
import pickle
import shutil
import time

import numpy as np
import pandas as pd

from damdays import config
from damdays.data import attributes, cells, events, panel, rainfall, splits
from damdays.data.splits import time_block
from damdays.features import sequences, store
from damdays.features.build import build_all
from damdays.models import physics
from damdays.models import season_rating as sr
from damdays.sealed.checks import CheckFailed


# ===========================================================================
# 1. Where a region's raw files are
# ===========================================================================
def raw_source(region):
    """(manifest CSV, time-series folder) of a region's raw DEA files."""
    if region in config.SEALED_REGION:
        return config.SEALED_DIR / "manifest.csv", config.SEALED_DIR / "ts"
    if region in config.DEV_REGIONS:
        return config.DEV_MANIFEST, config.DEV_TS_DIR
    raise ValueError(f"Unknown region {region!r}.")


def region_manifest(region):
    """The region's waterbodies (uid, region, area_m2, lat, lon), checked: one region, unique uids, inside its box."""
    manifest_path, _ = raw_source(region)
    manifest = panel.load_manifest(manifest_path)
    manifest = manifest[manifest["region"].astype(str) == region].reset_index(drop=True)
    lat_min, lat_max, lon_min, lon_max = {**config.DEV_REGIONS, **config.SEALED_REGION}[region]
    inside = manifest["lat"].between(lat_min, lat_max) & manifest["lon"].between(lon_min, lon_max)
    if manifest.empty or manifest["uid"].duplicated().any() or not inside.all():
        raise ValueError(f"The {region} manifest is empty, has duplicated uids, or has waterbodies outside "
                         f"the region's box ({int((~inside).sum())}).")
    return manifest


def raw_file_names(region):
    """(file names, folder) of the region's time-series files, from its manifest."""
    _, folder = raw_source(region)
    return [f"{uid}.csv" for uid in region_manifest(region)["uid"]], folder


def require_manifest_matches_files(manifest, verified_files):
    """Refuse unless the manifest lists exactly the time-series files whose SHA-256 was verified.

    The sealed manifest (waterbody outlines' metadata: uid, area, lat, lon) is not in SEALED_HASHES.csv,
    which lists the 4,711 time-series files. This check ties the two together: every file the build
    reads was verified, and no verified waterbody is silently left out.
    """
    listed = {f"{uid}.csv" for uid in manifest["uid"].astype(str)}
    verified = set(verified_files)
    if listed != verified:
        raise CheckFailed(f"The manifest lists {len(listed):,} waterbodies but {len(verified):,} files were verified: "
                          f"{len(listed - verified)} listed but not verified (e.g. {sorted(listed - verified)[:3]}), "
                          f"{len(verified - listed)} verified but not listed (e.g. {sorted(verified - listed)[:3]}).")


# ===========================================================================
# 2-5. The data layer (scripts/01_build_data.py, one region)
# ===========================================================================
def build_data_layer(region, say, verified_files=None):
    """Panel, attributes, events and rain for one region, from its raw files. Returns a dict.

    verified_files  the time-series file names whose SHA-256 was checked first; if given, the
                    manifest must list exactly these (require_manifest_matches_files)
    """
    started = time.time()
    manifest = region_manifest(region)
    if verified_files is not None:
        require_manifest_matches_files(manifest, verified_files)
        say(f"  manifest lists exactly the {len(verified_files):,} verified time-series files")
    _, folder = raw_source(region)
    download = panel.check_downloads(manifest, folder)
    if download["missing"]:
        raise FileNotFoundError(f"{len(download['missing'])} time-series files are missing, e.g. "
                                f"{download['missing'][:3]}")
    say(f"  manifest: {len(manifest):,} waterbodies, every time-series file present")

    the_panel, qc = panel.build_panel(manifest, folder)
    say(f"  panel: {len(the_panel):,} valid looks, {the_panel['date'].min().date()} to "
        f"{the_panel['date'].max().date()} ({time.time() - started:.0f} s)")

    attrs = attributes.build_attributes(the_panel, manifest)
    attrs = cells.add_hex_cells(attrs)
    grids, months = rainfall.load_silo_grids(regions=(region,))     # this region's SILO key only
    attrs = rainfall.assign_silo_cells(attrs, grids)
    attrs = splits.add_folds(attrs)
    say(f"  attributes: {int(attrs['has_hist'].sum()):,} with history, {int(attrs['dam_like'].sum()):,} dam-like, "
        f"{int(attrs['persistent'].sum()):,} persistent (flags from the region's own pre-2016 looks)")

    the_events = events.build_events(the_panel, attrs)
    rain_by_cell = rainfall.rain_by_cell(attrs, grids, months)
    say(f"  events: {len(the_events):,}; SILO cells: {len(rain_by_cell['cells']):,} "
        f"({time.time() - started:.0f} s)")
    return dict(region=region, manifest=manifest, panel=the_panel, qc=qc, attrs=attrs, events=the_events,
                rain_by_cell=rain_by_cell)


# ===========================================================================
# 6-9. The tables the models read
# ===========================================================================
def build_tables(data, physics_params, say):
    """P1 (with the physics columns), P2 dam (with the area index), P2 cell and the nets' monthly history."""
    started = time.time()
    built = build_all(data["panel"], data["attrs"], data["events"], data["rain_by_cell"], verbose=False)
    p1 = built["p1"]
    say(f"  features: {len(p1):,} P1 issues, {len(built['p2_dam']):,} P2 dam-seasons, "
        f"{len(built['p2_cell']):,} P2 cell-seasons ({time.time() - started:.0f} s)")

    out = physics.build_physics(data["panel"], data["attrs"], data["rain_by_cell"], params=physics_params)
    physics.check_aligned(out["p1_physics"], p1)
    for column in physics.PHY_COLUMNS:
        p1[column] = out["p1_physics"][column].to_numpy()
    say(f"  physics: {out['filter_summary']['issues_with_physics']:,} issues simulated with the given balance "
        f"and the {data['region']} evaporation shape ({time.time() - started:.0f} s)")

    p2_dam = sr.add_area_index(built["p2_dam"], data["attrs"])
    history = sequences.build_monthly_history(data["panel"], data["attrs"], data["rain_by_cell"])
    say(f"  P2 area index and the nets' monthly history ({time.time() - started:.0f} s)")
    return dict(region=data["region"], p1=p1, p2_dam=p2_dam, p2_cell=built["p2_cell"], monthly_history=history,
                data_end=built["data_end"], physics_summary=out["filter_summary"])


def tidemark_inputs(tables):
    """The inputs tidemark.predict_tidemark reads (its load_inputs() for the development tables)."""
    return dict(p1=tables["p1"], p2_dam=tables["p2_dam"], p2_cell=tables["p2_cell"],
                monthly_history=tables["monthly_history"])


# ===========================================================================
# Counts for the screen and the results page
# ===========================================================================
def region_counts(data, tables):
    """The region's size: waterbodies, looks, populations, events, issues per block, seasons, cells."""
    attrs, the_events, p1 = data["attrs"], data["events"], tables["p1"]
    labelled = p1["label_ok"].to_numpy(dtype=bool)
    primary = (p1["dam_like"].to_numpy(dtype=bool) & p1["warm"].to_numpy(dtype=bool) & labelled
               & p1["at_risk_R30"].to_numpy(dtype=bool) & p1["y_R30"].notna().to_numpy())
    blocks = time_block(p1["issue_date"])
    dam_like_events = the_events[the_events["dam_like"]]
    p2 = tables["p2_dam"]
    p2_test = p2[(p2["split"] == "TEST") & p2["dam_like"] & p2["label_ok"]]
    cells_test = tables["p2_cell"][(tables["p2_cell"]["split"] == "TEST") & tables["p2_cell"]["label_ok"]]
    return dict(
        region=data["region"], waterbodies_in_manifest=int(len(data["manifest"])),
        with_polygon=int(attrs["n_pixels"].notna().sum()), valid_looks=int(len(data["panel"])),
        first_look=str(data["panel"]["date"].min().date()), last_look=str(tables["data_end"].date()),
        has_hist=int(attrs["has_hist"].sum()), dam_like=int(attrs["dam_like"].sum()),
        persistent=int(attrs["persistent"].sum()),
        dam_like_events=dict(D0=int((dam_like_events["kind"] == "D0").sum()),
                             R30=int((dam_like_events["kind"] == "R30").sum()),
                             D0g=int(dam_like_events["gradual"].sum())),
        p1_issues_by_block={b: int((blocks == b).sum()) for b in ("TRAIN", "VAL", "GAP", "TEST", "AFTER")},
        r30_primary_test_rows=int((primary & (blocks == "TEST")).sum()),
        r30_primary_test_events=int(p1.loc[primary & (blocks == "TEST"), "y_R30"].sum()),
        p2_dam_like_test_seasons=int(len(p2_test)), p2_dry_test_seasons=int(p2_test["y"].sum()),
        p2_cells=int(tables["p2_cell"]["hex_id"].nunique()), p2_test_cell_seasons=int(len(cells_test)),
        silo_cells=int(len(data["rain_by_cell"]["cells"])))


# ===========================================================================
# Keeping the built tables (so a crash after this point does not rebuild them)
# ===========================================================================
TABLE_FILES = ("p1", "p2_dam", "p2_cell", "monthly_history", "meta")


def save_tables(tables, counts, folder, source_fingerprint, margin_bytes=2 ** 30):
    """Save the region's tables to `folder` (pickles), stamped with the fingerprint of the raw files they came from.

    Skipped with a warning (returns False) if the disk would have less than 1 GB left.
    """
    needed = sum(tables[name].memory_usage(deep=True).sum() for name in ("p1", "p2_dam", "p2_cell"))
    folder.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(folder).free < needed + margin_bytes:
        return False
    meta = dict(region=tables["region"], data_end=tables["data_end"], physics_summary=tables["physics_summary"],
                counts=counts, source_fingerprint=source_fingerprint)
    for name in TABLE_FILES:
        obj = meta if name == "meta" else tables[name]
        with open(folder / f"{name}.tmp", "wb") as handle:
            pickle.dump(obj, handle, protocol=pickle.HIGHEST_PROTOCOL)
    for name in TABLE_FILES:                       # rename only once every file is fully written
        (folder / f"{name}.tmp").replace(folder / f"{name}.pkl")
    (folder / "stamp.json").write_text(json.dumps(dict(source_fingerprint=source_fingerprint,
                                                       saved_at=time.strftime("%Y-%m-%d %H:%M:%S"))))
    return True


def load_tables(folder, source_fingerprint):
    """(tables, counts) saved by save_tables from the same raw files, or None if there are none."""
    stamp = folder / "stamp.json"
    if not stamp.exists() or json.loads(stamp.read_text())["source_fingerprint"] != source_fingerprint:
        return None
    if not all((folder / f"{name}.pkl").exists() for name in TABLE_FILES):
        return None
    loaded = {name: pd.read_pickle(folder / f"{name}.pkl") for name in TABLE_FILES}
    meta = loaded.pop("meta")
    tables = dict(loaded, region=meta["region"], data_end=meta["data_end"], physics_summary=meta["physics_summary"])
    return tables, meta["counts"]


# ===========================================================================
# Dry run only: does the region build reproduce the development feature store?
# ===========================================================================
# Columns that may differ for a known reason: the held-out-dam fold numbers are shuffled over the set of
# dams in the build (damdays.data.splits), so a one-region build numbers them differently. No model reads them.
FOLD_COLUMNS = ("fold5", "sfold5")


def compare_frames(mine, theirs, keys):
    """Row keys equal, then every shared column equal (NaN = NaN). Returns {rows_equal, differing: {column: rows}}."""
    if len(mine) != len(theirs):
        return dict(rows_equal=False, rows=(len(mine), len(theirs)), differing={})
    for key in keys:
        if not np.array_equal(mine[key].astype(str).to_numpy(), theirs[key].astype(str).to_numpy()):
            return dict(rows_equal=False, rows=(len(mine), len(theirs)), differing={}, key=key)
    differing = {}
    for column in sorted(set(mine.columns) & set(theirs.columns)):
        a, b = mine[column], theirs[column]
        if a.dtype.kind in "fc" or b.dtype.kind in "fc":
            same = np.isclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float), rtol=0, atol=0, equal_nan=True)
        else:
            same = (a.astype(str).to_numpy() == b.astype(str).to_numpy())
        if not same.all():
            differing[column] = int((~same).sum())
    return dict(rows_equal=True, rows=(len(mine), len(theirs)), differing=differing,
                columns_compared=len(set(mine.columns) & set(theirs.columns)),
                only_in_region_build=sorted(set(mine.columns) - set(theirs.columns)),
                only_in_store=sorted(set(theirs.columns) - set(mine.columns)))


def development_data_end():
    """The newest look of the development build (over both development regions)."""
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as handle:
        return pd.Timestamp(pickle.load(handle)["data_end"])


def compare_with_development_store(tables, say):
    """Compare a development region's rebuilt tables with its rows in data_cache/features (dry run only).

    Expected: identical P1 and P2 tables, with three known exceptions:
      * the fold numbers (FOLD_COLUMNS), shuffled over the set of dams in the build;
      * the physics columns, not compared (the dry run simulates the region with a balance fitted
        on the other region only);
      * the data end. A region built on its own ends at ITS newest look, the development build at
        the newest look of both regions. An issue whose 90-day window ends between the two dates
        has a determinable label in one build and not in the other (label_ok, window_closed).
        Those P1 rows are counted and compared separately; every other row must be identical.
    """
    region = tables["region"]
    out = {}
    store_p1 = store.load_p1()
    store_p1 = store_p1[store_p1["region"].astype(str) == region].reset_index(drop=True)
    window_end = pd.to_datetime(store_p1["issue_date"]) + pd.Timedelta(days=config.HORIZON_DAYS)
    end_effect = ((window_end > tables["data_end"]) & (window_end <= development_data_end())).to_numpy()
    mine = tables["p1"].drop(columns=list(physics.PHY_COLUMNS))
    if len(mine) == len(store_p1):
        out["p1"] = compare_frames(mine.loc[~end_effect].reset_index(drop=True),
                                   store_p1.loc[~end_effect].reset_index(drop=True), ["uid", "issue_date"])
        out["p1_data_end_rows"] = dict(compare_frames(mine.loc[end_effect].reset_index(drop=True),
                                                      store_p1.loc[end_effect].reset_index(drop=True),
                                                      ["uid", "issue_date"]),
                                       about=f"issues whose 90-day window ends after this region's last look "
                                             f"({tables['data_end'].date()}) but by the development build's "
                                             f"({development_data_end().date()}): reported, not required equal")
    else:
        out["p1"] = compare_frames(mine, store_p1, ["uid", "issue_date"])
    del store_p1
    for level, keys in (("dam", ["uid", "season"]), ("cell", ["hex_id", "season"])):
        theirs = store.load_p2(level)
        theirs = theirs[theirs["region"].astype(str) == region].reset_index(drop=True)
        mine = tables["p2_dam" if level == "dam" else "p2_cell"]
        mine = mine.drop(columns=[c for c in sr.AREA_INDEX_COLUMNS if c in mine.columns]) if level == "dam" else mine
        out[f"p2_{level}"] = compare_frames(mine.reset_index(drop=True), theirs, keys)
    checked = {name: result for name, result in out.items() if name != "p1_data_end_rows"}
    unexplained = {name: {c: n for c, n in result["differing"].items() if c not in FOLD_COLUMNS}
                   for name, result in checked.items()}
    out["identical_apart_from_folds"] = all(r["rows_equal"] for r in checked.values()) and not any(unexplained.values())
    out["unexplained_differences"] = unexplained
    say(f"  region build vs the development feature store: "
        f"{'IDENTICAL' if out['identical_apart_from_folds'] else 'DIFFERENT'} (fold numbers aside); "
        + "; ".join(f"{name}: {r['rows'][0]:,} rows, {r.get('columns_compared', 0)} columns compared"
                    for name, r in checked.items()))
    if "p1_data_end_rows" in out:
        say(f"  {out['p1_data_end_rows']['rows'][0]:,} P1 rows near the data end differ only in "
            f"{sorted(out['p1_data_end_rows']['differing'])} ({out['p1_data_end_rows']['about']})")
    return out
