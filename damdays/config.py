"""Every path, date and threshold used by DamDays, in one readable place.

If you want to know "what does the model mean by X?", the answer should be here.
Values follow PREREG.md, which was committed before any code was written.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Where things live
# ---------------------------------------------------------------------------
REPO_DIR = Path(__file__).resolve().parents[1]

# Raw downloads sit outside the repo (they are large and come from public sources).
# Override with the DAMDAYS_RAW environment variable if you keep them elsewhere.
RAW_DIR = Path(os.environ.get(
    "DAMDAYS_RAW", r"D:/Climate Hack-tion 2026/research/pre_event"))

DEV_TS_DIR = RAW_DIR / "dea_dev" / "ts"          # one CSV of water history per waterbody
DEV_MANIFEST = RAW_DIR / "dea_dev" / "manifest.csv"
POLYGONS_ZIP = RAW_DIR / "dea_polygons" / "wb.zip"  # DEA Waterbodies v3 outlines
SILO_DIR = RAW_DIR / "silo"                       # monthly rainfall, one file per year

# The sealed test region. Code must never read it until the scheduled opening
# (Sat 3 Oct 17:30 AEST). damdays.data.guard enforces this.
SEALED_DIR = RAW_DIR / "dea_sealed"
SEALED_UNLOCK_ENV = "DAMDAYS_OPEN_SEALED"          # set to "yes" only at the opening

# Everything we compute goes here (git-ignored, rebuildable from raw data).
CACHE_DIR = REPO_DIR / "data_cache"
ARTIFACTS_DIR = REPO_DIR / "artifacts"           # small results we commit (tables, JSON)

# ---------------------------------------------------------------------------
# Study regions (lat_min, lat_max, lon_min, lon_max)
# ---------------------------------------------------------------------------
DEV_REGIONS = {
    "nsw_cw": (-33.5, -30.5, 147.0, 150.0),       # NSW Central West
    "wvic_sesa": (-38.0, -35.5, 140.5, 143.5),    # western Victoria / south-east SA
}
SEALED_REGION = {"sealed_sdowns_newengland": (-31.5, -26.0, 150.5, 152.6)}

# Which waterbodies count: at least 6 Landsat pixels, at most farm-dam size.
AREA_MIN_M2 = 5_400
AREA_MAX_M2 = 100_000
PIXEL_M2 = 900                                   # one 30 m x 30 m Landsat pixel

# Satellite dates are UTC; Australia's east coast is UTC+10, so we use local dates.
LOCAL_UTC_OFFSET_HOURS = 10

# ---------------------------------------------------------------------------
# Populations (decided from history before 2016 only)
# ---------------------------------------------------------------------------
STATIC_CUTOFF = "2016-01-01"     # "full" level and dam types use data before this date
MIN_PRE_OBS = 20                 # need at least 20 good observations to judge a dam
FULL_QUANTILE = 0.90             # a dam's "full" = its 90th-percentile wet share
DAM_LIKE = dict(min_wet_share=0.50, min_compact=0.70, max_elong=3.0, min_px=6, max_px=55)
PERSISTENT_MIN_WET_SHARE = 0.80

# ---------------------------------------------------------------------------
# Events (what we forecast)
# ---------------------------------------------------------------------------
ARM_LEVEL = 0.60          # a dam must have refilled to 60% of full ...
ARM_WINDOW_DAYS = 180     # ... within the last 180 days before an event can count
CONFIRM_GAP_DAYS = 30     # two confirming observations must be at most 30 days apart
R30_LEVEL = 0.30          # R30 = "below a third of full"
ABRUPT_REL = 0.40         # a dry-out is "abrupt" if the last wet look was still >= 40% full
ABRUPT_GAP_DAYS = 60      #   ... and at most 60 days earlier (could be a satellite artefact)
HORIZON_DAYS = 90         # the farmer forecast looks 90 days ahead
MIN_LABEL_OBS = 3         # need 3 good observations in the window to know the answer

# ---------------------------------------------------------------------------
# Time blocks (no peeking: models learn from the past, are judged on the future)
# ---------------------------------------------------------------------------
TRAIN_END = "2009-01-01"          # TRAIN: issues before this date
VAL_START, VAL_END = "2009-01-01", "2016-01-01"   # VAL: used for every choice we make
TEST_START, TEST_END = "2016-07-01", "2026-07-01" # TEST: scored once per model
PURGE_DAYS = 30                   # gap so a training answer never overlaps the next block

# Season rating (the lender product): issued 1 July, judged on Oct-Mar dry-outs.
SEASON_ISSUE_MONTH_DAY = (7, 1)
SEASON_MONTHS = (10, 11, 12, 1, 2, 3)
HEX_SIZE_KM = 2.0

RANDOM_SEED = 2026
N_JOBS = 2                        # keep the laptop responsive
