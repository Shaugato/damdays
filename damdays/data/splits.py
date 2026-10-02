"""Time blocks and dam folds: how data is split so no model sees its own answers.

Time blocks, by the date a forecast is issued (PREREG.md):
    TRAIN  before 2009-01-01                  models learn here
    VAL    2009-01-01 to 2015-12-31           every design choice is made here
    GAP    2016-01-01 to 2016-06-30           unused buffer
    TEST   2016-07-01 to 2026-06-30           scored once per model
    AFTER  from 2026-07-01                    too recent to know the answer

Purge: a forecast issued on day D is only answered once its 90-day window
has passed, plus 30 days to confirm an event. A row may be used for fitting
only if D + 90 + 30 days falls before the block being scored. Otherwise the
answer would overlap the scored period.

Folds (for held-out-dam checks), both with fixed seeds so they never change:
    fold5   grouped by dam: every dam is in exactly one of 5 folds
    sfold5  spatial: 0.5-degree map tiles are shuffled into 5 folds, so
            nearby dams (which share weather) land in the same fold
"""
import numpy as np
import pandas as pd

from damdays import config

N_FOLDS = 5
TILE_DEGREES = 0.5
FOLD_SEED = config.RANDOM_SEED
SPATIAL_FOLD_SEED = config.RANDOM_SEED + 1


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------
def hydro_year(dates):
    """July-June year: 1 Jul 2019 to 30 Jun 2020 is hydro year 2019."""
    dates = pd.DatetimeIndex(pd.to_datetime(dates))
    return np.where(dates.month >= 7, dates.year, dates.year - 1)


def time_block(issue_dates):
    """Name the time block (TRAIN, VAL, GAP, TEST, AFTER) of each issue date."""
    dates = pd.DatetimeIndex(pd.to_datetime(issue_dates))
    blocks = np.full(len(dates), "AFTER", dtype=object)
    # Assign from the latest block back to the earliest; each step overwrites
    # the dates before its start.
    blocks[dates < pd.Timestamp(config.TEST_END)] = "TEST"
    blocks[dates < pd.Timestamp(config.TEST_START)] = "GAP"
    blocks[dates < pd.Timestamp(config.VAL_END)] = "VAL"
    blocks[dates < pd.Timestamp(config.TRAIN_END)] = "TRAIN"
    return blocks


def answer_known_before(issue_dates, cutoff):
    """True where the forecast window (+ purge days) closes before `cutoff`."""
    dates = pd.DatetimeIndex(pd.to_datetime(issue_dates))
    window_closes = dates + pd.Timedelta(days=config.HORIZON_DAYS + config.PURGE_DAYS)
    return np.asarray(window_closes < pd.Timestamp(cutoff))


def fit_mask(issue_dates, scored_block):
    """Rows a model may be fitted on when it will be scored on `scored_block`.

    VAL:  TRAIN rows whose answer is known before VAL starts.
    TEST: TRAIN and VAL rows whose answer is known before TEST starts.
    """
    blocks = time_block(issue_dates)
    if scored_block == "VAL":
        in_fit_blocks = blocks == "TRAIN"
        cutoff = config.VAL_START
    elif scored_block == "TEST":
        in_fit_blocks = np.isin(blocks, ["TRAIN", "VAL"])
        cutoff = config.TEST_START
    else:
        raise ValueError(f"scored_block must be VAL or TEST, not {scored_block}")
    return in_fit_blocks & answer_known_before(issue_dates, cutoff)


# ---------------------------------------------------------------------------
# Folds
# ---------------------------------------------------------------------------
def shuffled_folds(keys, seed, n_folds=N_FOLDS):
    """Give each distinct key a fold number 0..n_folds-1, in a seeded random order.

    Keys are sorted first so the result does not depend on input order.
    """
    unique_keys = np.array(sorted(set(keys)))
    order = np.random.default_rng(seed).permutation(len(unique_keys))
    fold_of_key = {unique_keys[k]: rank % n_folds for rank, k in enumerate(order)}
    return np.array([fold_of_key[key] for key in keys], dtype=int)


def dam_folds(uids):
    """fold5: grouped-by-dam folds (each uid in exactly one fold)."""
    return shuffled_folds(list(uids), seed=FOLD_SEED)


def map_tile(region, lat, lon):
    """Name of the 0.5-degree map tile a point falls in, e.g. "nsw_cw:-62:296"."""
    row = int(np.floor(lat / TILE_DEGREES))
    col = int(np.floor(lon / TILE_DEGREES))
    return f"{region}:{row}:{col}"


def spatial_folds(attrs):
    """sfold5: folds of whole map tiles. Returns (tile names, fold numbers)."""
    tiles = [map_tile(r, la, lo) for r, la, lo in zip(attrs["region"], attrs["lat"], attrs["lon"])]
    return tiles, shuffled_folds(tiles, seed=SPATIAL_FOLD_SEED)


def add_folds(attrs):
    """Add fold5, tile and sfold5 columns to the attributes table."""
    attrs["fold5"] = dam_folds(attrs["uid"])
    attrs["tile"], attrs["sfold5"] = spatial_folds(attrs)
    return attrs
