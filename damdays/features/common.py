"""Small helpers shared by the feature code: day numbers, seasons, per-dam slices.

Dates are turned into whole day numbers (days since 1970-01-01) so that
"90 days later" is plain integer arithmetic and cannot be confused by time
zones or clock times. The panel already holds local calendar dates.
"""
import numpy as np
import pandas as pd

from damdays import config

EPOCH = np.datetime64("1970-01-01", "D")


def day_numbers(dates):
    """Whole days since 1970-01-01 for an array or Series of dates (int64)."""
    values = pd.to_datetime(pd.Series(dates)).to_numpy().astype("datetime64[D]")
    return (values - EPOCH).astype(np.int64)


def dates_from_day_numbers(days):
    """Inverse of day_numbers: datetime64[us] array (the panel's date unit)."""
    return (EPOCH + np.asarray(days, dtype=np.int64)).astype("datetime64[us]")


def is_warm_season(months):
    """True for Oct-Mar (the warm half-year, when dams draw down fastest)."""
    return np.isin(np.asarray(months), config.SEASON_MONTHS)


def dam_slices(looks_uids, dam_uids):
    """Row range [start, stop) of each dam's looks in a table sorted by uid then date.

    looks_uids  the uid column of the sorted looks table
    dam_uids    the dams we want, sorted (a dam with no looks gets an empty range)

    Lets a loop work on one dam at a time without a slow pandas groupby.
    """
    looks_uids = np.asarray(looks_uids).astype(str)
    dam_uids = np.asarray(dam_uids).astype(str)
    starts = np.searchsorted(looks_uids, dam_uids, side="left")
    stops = np.searchsorted(looks_uids, dam_uids, side="right")
    return starts, stops


def days_since(flag, days):
    """For each look: days since the most recent look (this one included) where `flag` is True.

    Looks with no such earlier look get the cap (config.DAYS_CAP). Only the
    current and earlier looks are used, so this is causal.
    """
    flag = np.asarray(flag, dtype=bool)
    days = np.asarray(days, dtype=float)
    last_true_day = pd.Series(np.where(flag, days, np.nan)).ffill().to_numpy()
    out = np.minimum(config.DAYS_CAP, days - last_true_day)
    return np.where(np.isnan(last_true_day), float(config.DAYS_CAP), out)


def year_month_before(dates):
    """YYYYMM of the calendar month before each date's month (the last month fully finished)."""
    dates = pd.DatetimeIndex(pd.to_datetime(dates))
    year, month = dates.year.to_numpy(), dates.month.to_numpy()
    return np.where(month == 1, (year - 1) * 100 + 12, year * 100 + month - 1)
