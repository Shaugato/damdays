"""Causal yearly checkpoints: what did we know about each dam on 1 January of year Y?

Why this exists
---------------
Every dam is measured against its own "full" level (rel = pc_wet / full). The
PREREG "full" uses all looks before 2016. That is fine for DEFINING events,
but a model feature for, say, a 1998 forecast must not know how full the dam
got in 2003. So features use a checkpoint version instead:

    checkpoint Y = statistics of the dam's looks dated before 1 Jan Y

A forecast issued in year Y uses checkpoint min(Y, 2016). From 2016 on, the
checkpoint is the PREREG pre-2016 value, exactly as the PREREG requires.
Forecasts before 1987 have no checkpoint (the archive starts Aug 1986).

Statistics per checkpoint (suffix _c = "causal checkpoint"):
    n_hist_c      number of valid looks so far
    wet_share_c   share of those looks with at least one wet pixel
    full_c        90th percentile of pc_wet (the dam's own "full");
                  treated as unknown (NaN) when there are fewer than 20 looks or it is 0
    fill_share_c  share of the Jul-Jun years seen so far in which the dam reached 90% of full_c
    dd_warm_c     typical (median) Oct-Mar drawdown rate, in rel per day (negative = falling)
    dd_fast_c     a fast (20th percentile) Oct-Mar drawdown rate
    dd_cool_c     typical (median) Apr-Sep drawdown rate

Drawdown rates come from pairs of consecutive looks 8-40 days apart that
started at least 30% full. A pair counts only once its SECOND look is before
the checkpoint date.
"""
import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import hydro_year
from damdays.features.common import dam_slices, day_numbers, is_warm_season

CHECKPOINT_YEARS = np.arange(config.FIRST_CHECKPOINT_YEAR, config.LAST_CHECKPOINT_YEAR + 1)
STATS = ("n_hist_c", "wet_share_c", "full_c", "fill_share_c", "dd_warm_c", "dd_fast_c", "dd_cool_c")


def checkpoint_index(years):
    """Position in CHECKPOINT_YEARS used by a forecast in each of `years`; -1 = no checkpoint yet.

    Years after 2016 are capped at 2016 (the PREREG pre-2016 history).
    """
    capped = np.minimum(np.asarray(years), config.LAST_CHECKPOINT_YEAR)
    index = capped - config.FIRST_CHECKPOINT_YEAR
    return np.where(index >= 0, index, -1)


def history_stats(pc, px, hydro_years):
    """n_hist, wet_share, full and fill_share of one dam's looks (already cut at the checkpoint)."""
    n = len(pc)
    if n == 0:
        return 0, np.nan, np.nan, np.nan
    wet_share = float(np.mean(px > 0))
    full = float(np.percentile(pc, config.FULL_QUANTILE * 100))
    seen_years = np.unique(hydro_years).size
    if full > 0:
        filled_years = np.unique(hydro_years[pc >= config.FILL_LEVEL * full]).size
    else:
        filled_years = 0
    return n, wet_share, full, filled_years / seen_years


def drawdown_stats(days, pc, warm, n_known, full):
    """Typical drawdown rates from consecutive look pairs whose second look is among the first n_known.

    Returns (dd_warm, dd_fast, dd_cool) in rel per day; NaN where fewer than
    DRAWDOWN_MIN_PAIRS pairs exist or full is not positive.
    """
    if not full > 0 or n_known < 2:
        return np.nan, np.nan, np.nan
    days, pc, warm = days[:n_known], pc[:n_known], warm[:n_known]
    gap = np.diff(days).astype(float)
    rate = np.diff(pc) / gap / full                     # change in rel per day
    lo, hi = config.DRAWDOWN_GAP_DAYS
    usable = (gap >= lo) & (gap <= hi) & (pc[:-1] >= config.DRAWDOWN_MIN_REL * full)
    warm_pair = warm[:-1]                               # the season of the pair's first look
    warm_rates = rate[usable & warm_pair]
    cool_rates = rate[usable & ~warm_pair]

    def pct(values, q):
        """The q-th percentile, or NaN with too few pairs."""
        return float(np.percentile(values, q)) if len(values) >= config.DRAWDOWN_MIN_PAIRS else np.nan

    return pct(warm_rates, 50), pct(warm_rates, 20), pct(cool_rates, 50)


def dam_checkpoints(days, pc, px, months, hydro_years):
    """Every checkpoint of one dam: dict stat -> array over CHECKPOINT_YEARS."""
    out = {stat: np.full(len(CHECKPOINT_YEARS), np.nan) for stat in STATS}
    cut_days = day_numbers(pd.to_datetime([f"{year}-01-01" for year in CHECKPOINT_YEARS]))
    n_before = np.searchsorted(days, cut_days, side="left")   # looks strictly before 1 Jan Y
    warm = is_warm_season(months)
    for k, n in enumerate(n_before):
        n_hist, wet_share, full, fill_share = history_stats(pc[:n], px[:n], hydro_years[:n])
        dd_warm, dd_fast, dd_cool = drawdown_stats(days, pc, warm, n, full)
        out["n_hist_c"][k] = n_hist
        out["wet_share_c"][k] = wet_share
        # "full" is only trusted with enough history (the same rule as has_hist).
        out["full_c"][k] = full if (n_hist >= config.MIN_PRE_OBS and full > 0) else np.nan
        out["fill_share_c"][k] = fill_share
        out["dd_warm_c"][k], out["dd_fast_c"][k], out["dd_cool_c"][k] = dd_warm, dd_fast, dd_cool
    return out


def build_checkpoints(looks, dam_uids):
    """Checkpoints for every dam.

    looks     panel rows of the studied dams, sorted by uid then date
    dam_uids  sorted uids of the studied dams

    Returns dict stat -> array (n_dams, n_checkpoints), rows in dam_uids order.
    """
    table = {stat: np.full((len(dam_uids), len(CHECKPOINT_YEARS)), np.nan) for stat in STATS}
    starts, stops = dam_slices(looks["uid"], dam_uids)
    days_all = day_numbers(looks["date"])
    pc_all = looks["pc_wet"].to_numpy(dtype=float)
    px_all = looks["px_wet"].to_numpy(dtype=float)
    dates = pd.DatetimeIndex(looks["date"])
    months_all = dates.month.to_numpy()
    hydro_all = hydro_year(dates)
    for i, (a, b) in enumerate(zip(starts, stops)):
        one = dam_checkpoints(days_all[a:b], pc_all[a:b], px_all[a:b], months_all[a:b], hydro_all[a:b])
        for stat in STATS:
            table[stat][i] = one[stat]
    return table


def checkpoints_as_table(table, dam_uids):
    """Long table (uid, year, stats...) for saving and inspection."""
    n_dams, n_years = len(dam_uids), len(CHECKPOINT_YEARS)
    out = pd.DataFrame({
        "uid": np.repeat(np.asarray(dam_uids), n_years),
        "year": np.tile(CHECKPOINT_YEARS, n_dams),
    })
    for stat in STATS:
        out[stat] = table[stat].reshape(-1).astype(np.float32)
    return out[out["n_hist_c"] > 0].reset_index(drop=True)
