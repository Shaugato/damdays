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

# ---------------------------------------------------------------------------
# Features (damdays.features). Every feature at an issue date D uses only
# information that existed on D. See docs/FEATURES.md.
# ---------------------------------------------------------------------------
FIRST_ISSUE_DATE = "1988-01-01"   # first P1 forecast: the archive starts Aug 1986, so 1986-87 is warm-up history
FIRST_CHECKPOINT_YEAR = 1987      # checkpoint Y = what we knew about a dam on 1 Jan Y (looks before that date)
LAST_CHECKPOINT_YEAR = 2016       # issues in 2016 or later use the 1 Jan 2016 checkpoint (= the PREREG pre-2016 values)
FILL_LEVEL = 0.90                 # fill_share: share of Jul-Jun years in which the dam reached 90% of its full level
DRAWDOWN_GAP_DAYS = (8, 40)       # drawdown rates use pairs of consecutive looks 8-40 days apart
DRAWDOWN_MIN_REL = 0.30           # ... starting from at least 30% of full (a near-empty dam cannot draw down)
DRAWDOWN_MIN_PAIRS = 5            # ... and need at least 5 such pairs
FULL_REL_LEVEL = 0.90             # since_full: days since the dam was last at 90% of full
DAYS_CAP = 3650                   # "days since" features are capped at 10 years
REL_CLIP_MAX = 1.5                # rel = pc_wet / full_c is clipped to [0, 1.5]

# A past forecast may only be used (as "this dam's track record") once its
# answer is final: its 90-day window plus 30 days to confirm an event.
ANSWER_FINAL_DAYS = HORIZON_DAYS + PURGE_DAYS   # 120
B2_SHRINK_P1 = 20                 # dam_rate: shrink the dam's own rate toward the region x season rate (PREREG k = 20)
B2_SHRINK_P2 = 5                  # season rating: k = 5 (PREREG)

NEIGHBOUR_RADIUS_KM = 100         # neighbours: other has_hist waterbodies within 100 km ...
NEIGHBOUR_MAX = 300               # ... at most 300 of them (a fixed random sample per dam) ...
NEIGHBOUR_MIN = 5                 # ... and at least 5 with a recent look, or the feature is missing
NEIGHBOUR_MAX_AGE_DAYS = 30       # a neighbour's look counts only if it is at most 30 days old
OWN_CLIM_MIN_YEARS = 3            # anom_own needs the same calendar month in at least 3 earlier years

RAIN_WINDOWS_MONTHS = (1, 3, 6, 12, 24)
RAIN_BASELINE_YEARS = (1960, 2015)  # percentile baseline: same calendar month, these years, earlier than the issue
RAIN_MIN_BASELINE = 10            # at least 10 baseline years for a percentile
DROUGHT_QUANTILE = 0.20           # a "drought year": Jul-Jun rain below the cell's 20th percentile
DROUGHT_YEARS = 10                # drought10 = drought years among the last 10 Jul-Jun years

P2_FIRST_SEASON = 1989            # first 1 Jul season rating
P2_MAX_STATE_AGE_DAYS = 60        # the dam's state must come from a look at most 60 days before 1 Jul
