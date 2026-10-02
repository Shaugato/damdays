"""What are the dams around this one doing? Regional features from neighbouring waterbodies.

A single dam's history is noisy. If most dams within 100 km are falling fast,
that says something about the season that one dam cannot.

How it works (all causal)
-------------------------
1. A fixed calendar grid: the 1st and 16th of every month from 1 Jan 1987.
2. For each dam and grid date g: its "as-of" level = rel of its last look
   STRICTLY BEFORE g, if that look is at most 30 days old (else unknown).
   Also whether that look was fully dry (zero wet pixels).
3. Own monthly climatology: the dam's average as-of level in the same calendar
   month of EARLIER years only (years before min(year, 2016)), needing at
   least 3 years. anomaly = as-of level - that climatology.
4. Neighbours of a dam: the other has_hist waterbodies within 100 km, at most
   300 of them (a fixed random sample seeded by the dam's uid, so the sample
   never depends on table order). The dam itself is never its own neighbour.
   Disclosed: has_hist is a pre-2016 selection (89 mostly-dry or rarely seen
   waterbodies are left out), so for pre-2016 forecasts the pool is chosen
   with later knowledge. TEST and the sealed region are unaffected.
5. For each dam and grid date (needing at least 5 neighbours with a value):
       R_anom   median anomaly of the neighbours
       R_chg3   median 3-month change in the neighbours' as-of level
       R_zero   share of neighbours whose last look was fully dry
6. A forecast issued on day D uses the last grid date g <= D. Since grid
   values only use looks strictly before g, every neighbour look used is
   strictly earlier than D and at most 30 days older than g.
"""
import hashlib

import numpy as np
import pandas as pd

from damdays import config
from damdays.data.rainfall import haversine_km
from damdays.features.common import day_numbers

GRID_FIRST_YEAR = config.FIRST_CHECKPOINT_YEAR
CHANGE_STEPS = 6   # 6 half-month steps = 3 months, for R_chg3


# ---------------------------------------------------------------------------
# The calendar grid
# ---------------------------------------------------------------------------
def grid_dates(last_date):
    """The 1st and 16th of every month from 1 Jan GRID_FIRST_YEAR up to last_date (inclusive)."""
    last_date = pd.Timestamp(last_date)
    dates = [pd.Timestamp(year, month, day)
             for year in range(GRID_FIRST_YEAR, last_date.year + 1)
             for month in range(1, 13)
             for day in (1, 16)]
    return pd.DatetimeIndex([d for d in dates if d <= last_date])


def last_look_before(look_days, grid_days, max_age_days=config.NEIGHBOUR_MAX_AGE_DAYS):
    """Index of each grid date's last look strictly before it, or -1 if none within max_age_days."""
    j = np.searchsorted(look_days, grid_days, side="left") - 1   # "left": a look ON the grid date is excluded
    has_look = j >= 0
    age = grid_days - look_days[np.maximum(j, 0)]
    return np.where(has_look & (age <= max_age_days), j, -1)


def as_of_grid(dam_looks, n_dams, grid):
    """As-of level and dryness of every dam at every grid date.

    dam_looks  iterable of (dam index, look days, rel, px_wet) per dam
    Returns (asof, zero): float32 arrays (n_dams, n_grid), NaN where unknown.
    """
    grid_days = day_numbers(grid)
    asof = np.full((n_dams, len(grid)), np.nan, np.float32)
    zero = np.full((n_dams, len(grid)), np.nan, np.float32)
    for i, days, rel, px in dam_looks:
        j = last_look_before(days, grid_days)
        known = j >= 0
        asof[i, known] = rel[j[known]]
        zero[i, known] = (px[j[known]] == 0)
    return asof, zero


# ---------------------------------------------------------------------------
# Each dam's own monthly climatology, from earlier years only
# ---------------------------------------------------------------------------
def own_monthly_climatology(asof, grid):
    """clim[dam, year index, month-1] = mean as-of level in that calendar month over earlier years.

    "Earlier" means years before min(year, 2016) (2016 on: the fixed pre-2016
    climatology, as for every other history normaliser). Needs at least
    OWN_CLIM_MIN_YEARS years, else NaN. Year index 0 = GRID_FIRST_YEAR.
    """
    years = np.arange(GRID_FIRST_YEAR, grid.year.max() + 1)
    n_dams = asof.shape[0]
    monthly = np.full((n_dams, len(years), 12), np.nan, np.float32)
    grid_year, grid_month = grid.year.to_numpy(), grid.month.to_numpy()
    for y, year in enumerate(years):
        for month in range(1, 13):
            points = (grid_year == year) & (grid_month == month)
            if points.any():
                with np.errstate(all="ignore"):
                    monthly[:, y, month - 1] = np.nanmean(asof[:, points], axis=1)

    # Running sums over years: total[:, y] = sum over years strictly before year index y.
    have = np.isfinite(monthly)
    zeros = np.zeros((n_dams, 1, 12))
    total = np.concatenate([zeros, np.cumsum(np.where(have, monthly, 0.0), axis=1)], axis=1)
    count = np.concatenate([zeros, np.cumsum(have, axis=1)], axis=1)
    # Years from 2016 on use only the years before 2016.
    baseline_end = np.minimum(np.arange(len(years)), config.LAST_CHECKPOINT_YEAR - GRID_FIRST_YEAR)
    with np.errstate(all="ignore"):
        clim = np.where(count[:, baseline_end] >= config.OWN_CLIM_MIN_YEARS,
                        total[:, baseline_end] / count[:, baseline_end], np.nan)
    return clim.astype(np.float32), years


def climatology_at(clim, dam_index, years, months):
    """Look up a dam's own climatology for each (year, month); years before the grid use the first year."""
    y = np.clip(np.asarray(years) - GRID_FIRST_YEAR, 0, clim.shape[1] - 1)
    return clim[dam_index, y, np.asarray(months) - 1]


# ---------------------------------------------------------------------------
# Neighbours and their summaries
# ---------------------------------------------------------------------------
def uid_seed(uid):
    """A fixed random seed made from the uid text (same on every machine and every run)."""
    return int(hashlib.md5(uid.encode()).hexdigest()[:8], 16)


def neighbour_lists(uids, lat, lon):
    """For each dam: indices of its neighbours (within 100 km, not itself, at most 300 sampled)."""
    uids = np.asarray(uids).astype(str)
    lists = []
    for i in range(len(uids)):
        distance = haversine_km(lat[i], lon[i], lat, lon)
        nearby = np.flatnonzero(distance < config.NEIGHBOUR_RADIUS_KM)
        nearby = nearby[nearby != i]                       # never the dam itself
        if len(nearby) > config.NEIGHBOUR_MAX:
            # Sample from the candidates in uid order, so the sample does not
            # depend on how the table happens to be sorted or subset.
            in_uid_order = nearby[np.argsort(uids[nearby])]
            rng = np.random.default_rng(uid_seed(uids[i]))
            picked = rng.choice(len(in_uid_order), config.NEIGHBOUR_MAX, replace=False)
            nearby = np.sort(in_uid_order[picked])
        lists.append(nearby)
    return lists


def column_medians(values):
    """Median of each column, skipping missing values (same answer as np.nanmedian, about 4x faster).

    Missing values sort to the end, so with n known values in a column the
    median is the mean of the sorted values at positions (n-1)//2 and n//2.
    """
    ordered = np.sort(values, axis=0)
    n = np.isfinite(values).sum(axis=0)
    low = np.take_along_axis(ordered, ((n - 1) // 2)[None, :], axis=0)[0]
    high = np.take_along_axis(ordered, (n // 2)[None, :], axis=0)[0]
    return (low + high) / 2


def summarise_neighbours(values, neighbours, how):
    """Median or mean of the neighbours' values at each grid date (NaN if fewer than 5 known)."""
    out = np.full((len(neighbours), values.shape[1]), np.nan, np.float32)
    reducer = column_medians if how == "median" else (lambda v: np.nanmean(v, axis=0))
    for i, nb in enumerate(neighbours):
        if len(nb) < config.NEIGHBOUR_MIN:
            continue
        sub = values[nb]
        enough = np.isfinite(sub).sum(axis=0) >= config.NEIGHBOUR_MIN
        if enough.any():
            with np.errstate(all="ignore"):
                out[i, enough] = reducer(sub[:, enough])
    return out


def neighbour_features(asof, zero, clim, grid, neighbours):
    """R_anom, R_chg3 and R_zero for every dam and grid date (dict of float32 arrays)."""
    grid_year, grid_month = grid.year.to_numpy(), grid.month.to_numpy()
    anomaly = asof - clim[:, grid_year - GRID_FIRST_YEAR, grid_month - 1]
    change3 = np.full_like(asof, np.nan)
    change3[:, CHANGE_STEPS:] = asof[:, CHANGE_STEPS:] - asof[:, :-CHANGE_STEPS]
    return {
        "R_anom": summarise_neighbours(anomaly, neighbours, "median"),
        "R_chg3": summarise_neighbours(change3, neighbours, "median"),
        "R_zero": summarise_neighbours(zero, neighbours, "mean"),
    }


def at_issue(grid_values, dam_index, issue_days, grid):
    """Value of a grid feature for one dam at each issue day: the last grid date on or before it."""
    g = np.searchsorted(day_numbers(grid), issue_days, side="right") - 1
    out = np.full(len(issue_days), np.nan, np.float32)
    ok = g >= 0
    out[ok] = grid_values[dam_index, g[ok]]
    return out
