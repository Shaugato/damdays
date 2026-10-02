"""Load the satellite water history of every development waterbody into one table.

DEA Waterbodies gives one CSV per waterbody. Each row is one Landsat look:
    date    UTC timestamp of the satellite pass, e.g. 1987-09-05T23:48:37Z
    pc_wet  percent of the waterbody's outline that was wet
    px_wet  number of wet 30 m pixels

We turn all of them into one tidy "panel" with one row per waterbody per day:
    uid, region, date (local calendar date), pc_wet, px_wet, n_scenes

Cleaning rules (from PREREG.md and the research notes):
  1. DEA leaves pc_wet / px_wet empty when too little of the waterbody was
     clearly seen (cloud, shadow). Those rows are invalid and dropped.
  2. Rows outside the physical range (pc_wet not in 0-100, px_wet < 0) are
     dropped too. This is a safety net; we report how many there were.
  3. Timestamps are UTC. Landsat passes over eastern Australia at about
     10 am local time, which is around midnight UTC, so one pass can straddle
     two UTC dates. We convert to the local date (UTC+10) and average scenes
     that land on the same local date (n_scenes records how many).
"""
import pandas as pd

from damdays import config
from damdays.data.guard import check_path


def load_manifest():
    """The list of development waterbodies: uid, region, area_m2, lat, lon."""
    path = check_path(config.DEV_MANIFEST)
    manifest = pd.read_csv(path)
    return manifest[["uid", "region", "area_m2", "lat", "lon"]]


def check_downloads(manifest):
    """Confirm every waterbody in the manifest has a non-empty time-series file.

    Returns a small dict: n_manifest, n_present, missing (list of uids).
    """
    folder = check_path(config.DEV_TS_DIR)
    missing = []
    for uid in manifest["uid"]:
        path = check_path(folder / f"{uid}.csv")  # even a file-size check stays out of the sealed folder
        if not path.exists() or path.stat().st_size == 0:
            missing.append(uid)
    return {
        "n_manifest": len(manifest),
        "n_present": len(manifest) - len(missing),
        "missing": missing,
    }


def read_raw_series(uid):
    """One waterbody's raw DEA time series, exactly as downloaded."""
    path = check_path(config.DEV_TS_DIR / f"{uid}.csv")
    return pd.read_csv(path, usecols=["date", "pc_wet", "px_wet"])


def utc_to_local_date(utc_text):
    """Convert DEA UTC timestamps (text) to local calendar dates (UTC+10, no time part)."""
    utc_time = pd.to_datetime(utc_text, utc=True, format="ISO8601")
    local_time = utc_time + pd.Timedelta(hours=config.LOCAL_UTC_OFFSET_HOURS)
    return local_time.dt.tz_localize(None).dt.normalize()


def keep_valid_rows(raw):
    """Drop rows DEA marks invalid (empty values) and rows outside the physical range.

    Returns the kept rows and two boolean masks (invalid, out_of_range) over the
    input rows, so the caller can count what was dropped.
    """
    invalid = raw["pc_wet"].isna() | raw["px_wet"].isna()
    out_of_range = ~invalid & (
        (raw["pc_wet"] < 0) | (raw["pc_wet"] > 100) | (raw["px_wet"] < 0)
    )
    kept = raw[~invalid & ~out_of_range]
    return kept, invalid, out_of_range


def merge_same_day(obs):
    """Average all scenes of a waterbody that fall on the same local date.

    `obs` needs columns uid, date (local), pc_wet, px_wet.
    """
    merged = (
        obs.groupby(["uid", "date"], sort=True, observed=True)
        .agg(pc_wet=("pc_wet", "mean"), px_wet=("px_wet", "mean"), n_scenes=("pc_wet", "size"))
        .reset_index()
    )
    return merged


def read_all_raw(manifest, progress_every=1000):
    """Read every waterbody's raw CSV into one long table with a uid column."""
    pieces = []
    for count, uid in enumerate(manifest["uid"], start=1):
        raw = read_raw_series(uid)
        raw["uid"] = uid
        pieces.append(raw)
        if progress_every and count % progress_every == 0:
            print(f"  read {count} of {len(manifest)} files", flush=True)
    return pd.concat(pieces, ignore_index=True)


def build_panel(manifest=None):
    """Build the clean panel and a per-waterbody quality table.

    Returns (panel, qc):
      panel: uid, region, date, pc_wet, px_wet, n_scenes; sorted by uid then date.
      qc:    per waterbody: n_raw, n_invalid, n_out_of_range, n_kept,
             n_days_with_merged_scenes, first_date, last_date.
    """
    if manifest is None:
        manifest = load_manifest()

    raw = read_all_raw(manifest)
    kept, invalid, out_of_range = keep_valid_rows(raw)

    kept = kept.assign(date=utc_to_local_date(kept["date"]))
    panel = merge_same_day(kept)

    region_of = dict(zip(manifest["uid"], manifest["region"]))
    panel["region"] = panel["uid"].map(region_of)

    # Store as categories / float32: 5 million rows stay small in memory.
    # DEA publishes percentages with 2 decimals, so float32 loses nothing real.
    all_uids = sorted(manifest["uid"])
    panel["uid"] = pd.Categorical(panel["uid"], categories=all_uids)
    panel["region"] = pd.Categorical(panel["region"], categories=sorted(manifest["region"].unique()))
    panel["pc_wet"] = panel["pc_wet"].astype("float32")
    panel["px_wet"] = panel["px_wet"].astype("float32")
    panel["n_scenes"] = panel["n_scenes"].astype("int8")
    panel = panel[["uid", "region", "date", "pc_wet", "px_wet", "n_scenes"]]
    panel = panel.sort_values(["uid", "date"]).reset_index(drop=True)

    qc = quality_table(manifest, raw, invalid, out_of_range, panel)
    return panel, qc


def quality_table(manifest, raw, invalid, out_of_range, panel):
    """Per-waterbody counts of raw, dropped and kept rows, plus first and last date."""
    by_uid_raw = pd.DataFrame({
        "uid": raw["uid"],
        "invalid": invalid.values,
        "out_of_range": out_of_range.values,
    }).groupby("uid")
    kept_by_uid = panel.groupby("uid", observed=False)

    qc = pd.DataFrame({"uid": manifest["uid"], "region": manifest["region"]}).set_index("uid")
    qc["n_raw"] = by_uid_raw.size()
    qc["n_invalid"] = by_uid_raw["invalid"].sum()
    qc["n_out_of_range"] = by_uid_raw["out_of_range"].sum()
    qc["n_kept"] = kept_by_uid.size()
    qc["n_days_with_merged_scenes"] = (panel["n_scenes"] > 1).groupby(panel["uid"], observed=False).sum()
    qc["first_date"] = kept_by_uid["date"].min()
    qc["last_date"] = kept_by_uid["date"].max()

    count_columns = ["n_raw", "n_invalid", "n_out_of_range", "n_kept", "n_days_with_merged_scenes"]
    qc[count_columns] = qc[count_columns].fillna(0).astype(int)
    return qc.reset_index()
