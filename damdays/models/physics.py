"""Physics features: a simple water balance for every dam, run over 20 past rain years.

What it gives
-------------
Two numbers for every forecast (P1 issue: a dam with water at a satellite look):

    ph_p_R30   the share of 20 simulated 90-day futures in which the dam falls below 30% of full
    ph_p_D0    the share in which it runs dry

Rung L3 gives them to the tree T and the runway curve H as two extra inputs
(damdays.models.tidemark.PHY_COLUMNS). The spec plans to show them in the app
as the "water-balance outlook" (not shown yet). Both are blank (NaN) for
forecasts before 1993: the balance needs a few years of satellite history
before it can be fitted. LightGBM handles blanks.

How (three standard parts: nothing here is a new method)
--------------------------------------------------------
1. Bucket water balance. The dam's volume v (as a share of full) changes each day by

       dv/dt = c * max(R - thr, 0) / days_in_month     inflow: the month's rain R above a threshold
             - e * s(region, month) * rel               evaporation: seasonal shape s x the surface area
             - x * w(month)                             extraction and seepage: w = 1 Oct-Mar, 0.25 Apr-Sep

   where rel = v ** (1 / 1.5) is the level the satellite sees (the area-volume
   law of a cone- or pyramid-shaped dam) and s is the region's monthly pan
   evaporation from public BoM climatology, scaled to average 1 (EVAPORATION_MM_PER_DAY).
   One pooled set (c, e, x, thr) per yearly checkpoint, shared by every dam.
   It is fitted by robust least squares on pairs of consecutive looks of the
   same dam, in the development regions only (FIT_REGIONS; fit_checkpoint_parameters).
2. Kalman filter. The satellite level is noisy (a 6-55 pixel dam). The filter
   steps the balance forward from look to look and blends its prediction with
   each new look, giving a best estimate of today's volume and its uncertainty
   (kalman_filter).
3. Analogue-year ensemble. 20 futures start from that estimate (spread by its
   uncertainty). Future number l is driven by the rain of the same calendar
   months l years earlier (l = 1..20), and the balance is stepped 3 days at a
   time for 90 days. An event counts as in PREREG: below the threshold while
   "armed" (the dam reached 60% of full within the previous 180 days); each
   arming is used up by one event (simulate_futures).

The time rules (no peeking)
---------------------------
* rel uses the dam's checkpoint full_c (looks before 1 Jan of the look's year).
* Parameters for a look in year Y come from pairs whose SECOND look is before
  1 Jan Y (checkpoint Y; from 2016 on, the 2016 checkpoint, like every other
  checkpoint). The rain those pairs use ended before 1 Jan Y too.
* The filter's step into a look on day D uses the actual rain of months that
  ended before D's month began. D's own month is not over yet, so its days use
  that calendar month's average over EARLIER years (filter_rain_between).
* Future l uses the rain of months 1-20 years before the issue month: all ended
  before the issue (checked in simulate_futures).
* Arming at the issue uses looks up to and including the issue day.
* The random noise is the same 20 noise paths for every forecast (one fixed
  seed), so a forecast never depends on which other forecasts were computed
  with it.
tests/test_no_lookahead.py deletes all data after a cut date, reruns
build_physics and checks that every value before the cut is identical.

The pre-event research (bench/results/hybrid/tm01_phys.py, derived from the
physics-water-balance family) designed this generator; this is a fresh
implementation. Differences, all disclosed: the evaporation shape is now typed
from BoM station climatology (the research used a rough typed proxy); the
parameters are refitted every year (the research used 1993, 1998, 2002, 2009,
2016); forecasts before 1993 are blank (the research used the 1993 fit, a
small look-ahead); the filter starts in 1993; all forecasts share one set of
20 noise paths.
"""
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from damdays import config
from damdays.features import checkpoints, issues, rain, spec
from damdays.features.build import looks_of, studied_dams
from damdays.features.common import day_numbers, dates_from_day_numbers
from damdays.features.dam_history import relative_level

PHY_COLUMNS = tuple(spec.PHYSICS_FEATURE_SPEC)   # ("ph_p_R30", "ph_p_D0"): the two model inputs
PHYSICS_FILE = config.CACHE_DIR / "features" / "physics_p1.pkl"

# ---------------------------------------------------------------------------
# Typed-in constants
# ---------------------------------------------------------------------------
# Mean daily pan evaporation (mm), January to December, from the Bureau of
# Meteorology's "Climate statistics for Australian locations", row "Mean daily
# evaporation (mm)", all-years table http://www.bom.gov.au/climate/averages/tables/cw_<station>_All.shtml
# (pages read 2 Oct 2026). Only the SHAPE is used: each row is divided by its mean.
# One station near the middle of each region.
EVAPORATION_MM_PER_DAY = {
    # NSW Central West: TRANGIE RESEARCH STATION AWS, BoM 051049 (31.99 S, 147.95 E), 33 years 1971-2007.
    "nsw_cw": (9.8, 8.8, 6.9, 4.6, 2.6, 1.8, 1.8, 2.7, 4.0, 6.0, 8.1, 9.7),
    # Western Victoria / SE South Australia: LONGERENONG, BoM 079028 (36.67 S, 142.30 E), 32 years 1965-2001.
    "wvic_sesa": (8.4, 7.9, 5.7, 3.5, 1.9, 1.2, 1.3, 1.8, 2.8, 4.2, 5.9, 7.6),
    # Sealed region (Southern Downs / Granite Belt / New England): GLEN INNES AG RESEARCH STN, BoM 056013
    # (29.70 S, 151.69 E), 44 years 1971-2025. Public climatology, typed in before the region is opened
    # (PREREG "Sealed region protocol"); its hash goes in the freeze addendum.
    "sealed_sdowns_newengland": (5.4, 4.8, 4.1, 3.0, 2.0, 1.5, 1.7, 2.5, 3.6, 4.5, 5.1, 5.4),
}
# Extraction and seepage weight by calendar month (Jan..Dec): stock and pumping draw most in Oct-Mar.
DRAW_WEIGHT = (1.0, 1.0, 1.0, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 1.0, 1.0, 1.0)

VOLUME_EXPONENT = 1.5                      # v = rel ** 1.5 (area-volume law of a cone or pyramid)
V_MAX = config.REL_CLIP_MAX ** VOLUME_EXPONENT
RAIN_THRESHOLDS_MM = (0.0, 15.0, 30.0, 50.0)   # monthly rain below the threshold makes no inflow; one is
                                               # chosen per checkpoint (the best robust fit)
FIRST_PHYSICS_YEAR = 1993                  # first checkpoint fitted; earlier forecasts are blank
# The one pooled balance is fitted on the development regions' look pairs only (FINAL_SPEC: "both regions
# pooled"; PREREG sealed protocol: models are fitted on development-region data). A new region's dams are
# filtered and simulated with it, but never change it: adding them leaves every development forecast as it was.
FIT_REGIONS = tuple(config.DEV_REGIONS)
PAIR_GAP_DAYS = (1, 40)                    # fit pairs: consecutive looks 1-40 days apart ...
PAIR_REL_RANGE = (0.02, 1.05)              # ... both neither dry nor spilling
HUBER_K, HUBER_ITERATIONS, RIDGE = 1.5, 3, 1e-6
OBS_VARIANCE = 0.03                        # satellite noise on v (pre-event estimate from fit residuals)
PROCESS_VARIANCE_PER_DAY = 5e-4            # how fast the balance's own error grows
FILTER_RESTART_GAP_DAYS = 60               # a gap longer than this restarts the filter from the look
N_MEMBERS = 20                             # analogue rain years: 1..20 years before the issue
STEP_DAYS, N_STEPS = 3, 30                 # 30 steps of 3 days = 90 days
HALF_PIXEL = 0.5                           # "dry" in the simulation: below half a pixel of the full wet area
D0_LEVEL_RANGE = (0.01, 0.20)
PHYSICS_SEED = config.RANDOM_SEED
CHUNK_ROWS = 50_000                        # forecasts simulated at a time (keeps memory small)
FIRST_RAIN_MONTH = np.datetime64("1960-01", "M")


# ===========================================================================
# Calendar helpers (months are counted from January 1960, the first SILO month)
# ===========================================================================
def month_number(days):
    """Months since January 1960 of each day number (days since 1970-01-01)."""
    months = (np.datetime64("1970-01-01", "D") + np.asarray(days, dtype="int64")).astype("datetime64[M]")
    return (months - FIRST_RAIN_MONTH).astype(np.int64)


def day_of_month(days):
    """Day of the month (1-31) of each day number."""
    dates = np.datetime64("1970-01-01", "D") + np.asarray(days, dtype="int64")
    return (dates - dates.astype("datetime64[M]").astype("datetime64[D]")).astype(np.int64) + 1


def days_in_month(n_months):
    """Number of days in each of the first n_months months from January 1960."""
    starts = FIRST_RAIN_MONTH + np.arange(n_months + 1)
    return np.diff(starts.astype("datetime64[D]")).astype(np.int64)


def calendar_month(months):
    """0 = January ... 11 = December, for months counted from January 1960."""
    return np.asarray(months) % 12


def running_total_before(daily_rate, n_days):
    """For each month: the total (rate x days) of all EARLIER months, along the last axis.

    With it, the amount from day t0 to day t1 is a difference of two lookups
    (see *_to_date below), instead of a loop over the months in between.
    """
    totals = np.cumsum(daily_rate * n_days, axis=-1)
    return np.concatenate([np.zeros(daily_rate.shape[:-1] + (1,)), totals[..., :-1]], axis=-1)


# ===========================================================================
# Rain and calendar tables
# ===========================================================================
@dataclass
class RainTables:
    """Rain above each threshold, per SILO cell and month, in the three forms the balance needs.

    excess[k, cell, month]   mm per day of rain above threshold k (the month's total spread evenly)
    before[k, cell, month]   excess-rain total (mm) of all earlier months (for sums over date ranges)
    climate[k, cell, month]  mean of `excess` in the same calendar month of EARLIER years (1960 on)
    """
    excess: np.ndarray
    before: np.ndarray
    climate: np.ndarray


def monthly_rain_grid(rain_by_cell, cells, n_months, data_end):
    """Rain (mm) for the given cells, one column per month from January 1960 (NaN where unknown).

    TIME: a month still running on the newest look's date holds a partial total,
    so it is blanked (damdays.features.rain.blank_unfinished_months), as for
    the rain features.
    """
    finished = rain.blank_unfinished_months(np.asarray(rain_by_cell["rain"], dtype=np.float64),
                                            rain_by_cell["months"], data_end)
    index = pd.Index(np.asarray(rain_by_cell["cells"]).astype(str))
    rows = index.get_indexer(cells)
    if (rows < 0).any():
        raise KeyError("Some dams' SILO cells are not in the rain table.")
    yyyymm = np.asarray(rain_by_cell["months"])
    columns = (yyyymm // 100 - 1960) * 12 + (yyyymm % 100 - 1)
    grid = np.full((len(cells), n_months), np.nan)
    keep = (columns >= 0) & (columns < n_months)
    grid[:, columns[keep]] = finished[rows][:, keep]
    return grid


def same_month_earlier_years_mean(values):
    """For each month: the mean of the same calendar month over EARLIER years (NaN if none), last axis.

    TIME: the month itself and later years are never included.
    """
    n_months = values.shape[-1]
    n_years = -(-n_months // 12)
    padded = np.full(values.shape[:-1] + (n_years * 12,), np.nan)
    padded[..., :n_months] = values
    by_year = padded.reshape(values.shape[:-1] + (n_years, 12))
    known = np.isfinite(by_year)
    sums = np.cumsum(np.where(known, by_year, 0.0), axis=-2)
    counts = np.cumsum(known, axis=-2)
    mean = np.full(by_year.shape, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean[..., 1:, :] = sums[..., :-1, :] / counts[..., :-1, :]   # years strictly before
    mean[..., 1:, :][counts[..., :-1, :] == 0] = np.nan
    return mean.reshape(values.shape[:-1] + (n_years * 12,))[..., :n_months]


def build_rain_tables(rain_by_cell, cells, n_months, data_end):
    """RainTables for the given cells and months (see the class)."""
    rain_mm = monthly_rain_grid(rain_by_cell, cells, n_months, data_end)
    n_days = days_in_month(n_months)
    thresholds = np.asarray(RAIN_THRESHOLDS_MM)[:, None, None]
    excess = np.maximum(rain_mm[None] - thresholds, 0.0) / n_days        # NaN stays NaN
    return RainTables(excess=excess, before=running_total_before(excess, n_days),
                      climate=same_month_earlier_years_mean(excess))


@dataclass
class CalendarTables:
    """Evaporation shape and extraction weight per month (no data, only the typed-in constants).

    evaporation[region, month], evaporation_before[region, month]: per-day shape and running total
    draw[month], draw_before[month]: per-day extraction weight and running total
    """
    evaporation: np.ndarray
    evaporation_before: np.ndarray
    draw: np.ndarray
    draw_before: np.ndarray


def evaporation_shape(region):
    """The region's monthly pan evaporation scaled to average 1 (Jan..Dec)."""
    if region not in EVAPORATION_MM_PER_DAY:
        raise KeyError(f"No evaporation shape for region {region!r}: type in its BoM climatology "
                       "in EVAPORATION_MM_PER_DAY first.")
    values = np.asarray(EVAPORATION_MM_PER_DAY[region], dtype=float)
    return values / values.mean()


def build_calendar_tables(regions, n_months):
    """CalendarTables for the given region names (row order = region index) and months."""
    n_days = days_in_month(n_months)
    month_of_year = calendar_month(np.arange(n_months))
    evaporation = np.stack([evaporation_shape(r)[month_of_year] for r in regions])
    draw = np.asarray(DRAW_WEIGHT, dtype=float)[month_of_year]
    return CalendarTables(evaporation=evaporation, evaporation_before=running_total_before(evaporation, n_days),
                          draw=draw, draw_before=running_total_before(draw, n_days))


def rain_to_date(tables, k, cell, month, dom):
    """Actual excess rain (mm) from January 1960 to the end of day `dom` of `month`."""
    return tables.before[k, cell, month] + dom * tables.excess[k, cell, month]


def evaporation_to_date(calendar, region, month, dom):
    """Running total of the evaporation shape (shape-days) to the end of day `dom` of `month`."""
    return calendar.evaporation_before[region, month] + dom * calendar.evaporation[region, month]


def draw_to_date(calendar, month, dom):
    """Running total of the extraction weight (weight-days) to the end of day `dom` of `month`."""
    return calendar.draw_before[month] + dom * calendar.draw[month]


def filter_rain_between(tables, k, cell, month0, dom0, month1, dom1):
    """Excess rain (mm) the filter adds between a look (month0, dom0) and the next look (month1, dom1).

    TIME: months before the second look's month have ended, so their actual
    rain is used. The second look's own month is not over yet: its days use
    that calendar month's average over earlier years.
    """
    # Rain from the day after the first look to the end of the month before the second look's month.
    ended_months = tables.before[k, cell, month1] - rain_to_date(tables, k, cell, month0, dom0)
    actual = np.where(month1 > month0, ended_months, 0.0)
    days_this_month = np.where(month1 > month0, dom1, dom1 - dom0)
    return actual + days_this_month * tables.climate[k, cell, month1]


# ===========================================================================
# The looks
# ===========================================================================
@dataclass
class Looks:
    """Every look of the studied dams, sorted by dam then date, as flat arrays.

    dam (index into the dam table), day (days since 1970), month (since Jan 1960),
    dom (day of month), year, rel (level vs the checkpoint full; NaN if unknown),
    z = rel ** 1.5 (volume), full_c, region and cell (indexes), pc and px (raw).
    """
    dam: np.ndarray
    day: np.ndarray
    month: np.ndarray
    dom: np.ndarray
    year: np.ndarray
    rel: np.ndarray
    z: np.ndarray
    full_c: np.ndarray
    region: np.ndarray
    cell: np.ndarray
    pc: np.ndarray
    px: np.ndarray


def checkpoint_full_per_look(looks_table, dam_index, dam_uids):
    """full_c for each look: the dam's checkpoint for the look's year (looks before 1 Jan of that year)."""
    table = checkpoints.build_checkpoints(looks_table, dam_uids)
    k = checkpoints.checkpoint_index(pd.DatetimeIndex(looks_table["date"]).year.to_numpy())
    return np.where(k >= 0, table["full_c"][dam_index, np.maximum(k, 0)], np.nan)


def build_looks(looks_table, dams, regions, cells):
    """The Looks arrays from the sorted panel rows of the studied dams."""
    dam_uids = dams["uid"].to_numpy()
    dam_index = pd.Index(dam_uids).get_indexer(looks_table["uid"].astype(str))
    day = day_numbers(looks_table["date"])
    pc = looks_table["pc_wet"].to_numpy(dtype=float)
    px = looks_table["px_wet"].to_numpy(dtype=float)
    full_c = checkpoint_full_per_look(looks_table, dam_index, dam_uids)
    rel = relative_level(pc, full_c)
    region = pd.Index(regions).get_indexer(dams["region"].astype(str).to_numpy())[dam_index]
    cell = pd.Index(cells).get_indexer(dams["silo_cell"].astype(str).to_numpy())[dam_index]
    return Looks(dam=dam_index, day=day, month=month_number(day), dom=day_of_month(day),
                 year=pd.DatetimeIndex(looks_table["date"]).year.to_numpy(), rel=rel, z=rel ** VOLUME_EXPONENT,
                 full_c=full_c, region=region, cell=cell, pc=pc, px=px)


# ===========================================================================
# 1. Fitting the balance (one pooled parameter set per checkpoint year)
# ===========================================================================
def fit_pairs(looks, in_fit_region):
    """Positions i of looks whose NEXT look (i + 1) forms a fit pair.

    Same dam, in a fit region (in_fit_region: one flag per look), 1-40 days
    apart, both looks between 2% and 105% full (a dry or spilling dam does not
    follow the balance).
    """
    same_dam = looks.dam[1:] == looks.dam[:-1]
    gap = looks.day[1:] - looks.day[:-1]
    low, high = PAIR_REL_RANGE
    with np.errstate(invalid="ignore"):
        in_range = (looks.rel > low) & (looks.rel < high)
    ok = (same_dam & in_fit_region[:-1] & (gap >= PAIR_GAP_DAYS[0]) & (gap <= PAIR_GAP_DAYS[1])
          & in_range[:-1] & in_range[1:])
    return np.flatnonzero(ok)


def pair_regressors(looks, first, rain_tables, calendar):
    """The balance written as a linear model for each fit pair: X @ (c, e, x) = change in volume.

    Returns (X [threshold, pair, 3], y [pair]):
      column 0  excess rain (mm) between the two looks (actual rain: the pair is in the past)
      column 1  minus the evaporation shape-days x the pair's mean level
      column 2  minus the extraction weight-days
    """
    i0, i1 = first, first + 1
    k = np.arange(len(RAIN_THRESHOLDS_MM))[:, None]
    rain_in = (rain_to_date(rain_tables, k, looks.cell[i1][None], looks.month[i1][None], looks.dom[i1][None])
               - rain_to_date(rain_tables, k, looks.cell[i0][None], looks.month[i0][None], looks.dom[i0][None]))
    evap_days = (evaporation_to_date(calendar, looks.region[i1], looks.month[i1], looks.dom[i1])
                 - evaporation_to_date(calendar, looks.region[i0], looks.month[i0], looks.dom[i0]))
    draw_days = draw_to_date(calendar, looks.month[i1], looks.dom[i1]) - draw_to_date(calendar, looks.month[i0],
                                                                                        looks.dom[i0])
    mean_level = 0.5 * (looks.rel[i0] + looks.rel[i1])
    X = np.stack([rain_in, np.broadcast_to(-evap_days * mean_level, rain_in.shape),
                  np.broadcast_to(-draw_days, rain_in.shape)], axis=-1)
    return X, looks.z[i1] - looks.z[i0]


def huber_ridge(X, y):
    """Robust least squares. Returns (coefficients, Huber loss).

    Fit; then give less weight to pairs whose error is more than 1.5 robust
    standard deviations (most big errors are satellite misreads); refit (3
    rounds). A tiny ridge keeps the solve stable.
    """
    penalty = RIDGE * np.diag(np.diag(X.T @ X))
    weights = np.ones(len(y))
    for _ in range(HUBER_ITERATIONS):
        weighted = X * weights[:, None]
        coef = np.linalg.solve(weighted.T @ X + penalty, weighted.T @ y)
        residual = y - X @ coef
        scale = 1.4826 * np.median(np.abs(residual)) + 1e-6
        weights = np.minimum(1.0, HUBER_K * scale / np.maximum(np.abs(residual), 1e-12))
    r = np.abs(residual) / scale
    loss = float(np.sum(np.where(r <= HUBER_K, 0.5 * r ** 2, HUBER_K * r - 0.5 * HUBER_K ** 2)) * scale ** 2)
    return coef, loss


def checkpoint_years(last_year):
    """The checkpoint years to fit: 1993 to min(last_year, 2016)."""
    return np.arange(FIRST_PHYSICS_YEAR, min(last_year, config.LAST_CHECKPOINT_YEAR) + 1)


def fit_checkpoint_parameters(looks, rain_tables, calendar, in_fit_region):
    """One pooled (threshold, c, e, x) per checkpoint year Y. Returns a table, one row per year.

    TIME: checkpoint Y uses only pairs whose second look is before 1 Jan Y (so
    the rain they use ended before then too). For each threshold the balance is
    fitted by huber_ridge; the threshold with the lowest loss is kept, and
    negative coefficients are set to 0 (inflow, evaporation and extraction
    cannot change sign).
    Only the looks flagged in_fit_region are fitted on (the development
    regions: see FIT_REGIONS).
    """
    first = fit_pairs(looks, in_fit_region)
    if len(first) == 0:
        raise ValueError(f"No look pairs in the fit regions {FIT_REGIONS}: the balance is fitted on the "
                         "development regions, so their looks must be part of the build.")
    X_all, y_all = pair_regressors(looks, first, rain_tables, calendar)
    usable = np.isfinite(y_all) & np.isfinite(X_all).all(axis=(0, 2))    # drops pairs touching a blank month
    second_day = looks.day[first + 1]
    out = []
    for year in checkpoint_years(int(looks.year.max())):
        pick = usable & (second_day < day_numbers([f"{year}-01-01"])[0])
        best = None
        for k in range(len(RAIN_THRESHOLDS_MM)):
            coef, loss = huber_ridge(X_all[k][pick], y_all[pick])
            if best is None or loss < best[1]:
                best = (k, loss, np.maximum(coef, 0.0))
        k, loss, (c, e, x) = best
        out.append(dict(year=int(year), n_pairs=int(pick.sum()), threshold_index=int(k),
                        threshold_mm=RAIN_THRESHOLDS_MM[k], c=float(c), e=float(e), x=float(x), loss=loss))
    return pd.DataFrame(out)


def parameters_per_look(params, years):
    """(c, e, x, threshold index) for looks in each year: checkpoint min(year, 2016); NaN before 1993."""
    table = params.set_index("year")
    use = np.minimum(np.asarray(years), config.LAST_CHECKPOINT_YEAR)
    known = np.isin(use, table.index.to_numpy())
    lookup = table.reindex(np.where(known, use, table.index[0]))
    out = {name: np.where(known, lookup[name].to_numpy(dtype=float), np.nan) for name in ("c", "e", "x")}
    out["k"] = np.where(known, lookup["threshold_index"].to_numpy(), 0).astype(np.int64)
    out["known"] = known
    return out


# ===========================================================================
# 2. The Kalman filter (today's volume and its uncertainty at every look)
# ===========================================================================
def kalman_filter(z, restart, gap, rain_in, evap_days, draw_days, c, e, x):
    """The scalar Kalman filter on v = rel ** 1.5, one look at a time. Returns (mean, variance) per look.

    Predict: step the balance from the previous look's estimate over the gap
             (evaporation uses the surface area at the start of the gap);
             the uncertainty grows by PROCESS_VARIANCE_PER_DAY x gap.
    Update:  blend the prediction with the new look, weighted by their
             uncertainties (the satellite's is OBS_VARIANCE).
    A restart (or a look with no estimate yet) starts from the look itself.
    Looks with an unknown level (no checkpoint full yet) keep the prediction.
    """
    n = len(z)
    mean_out, var_out = np.full(n, np.nan), np.full(n, np.nan)
    z_, restart_, gap_ = z.tolist(), restart.tolist(), gap.tolist()
    rain_, evap_, draw_ = rain_in.tolist(), evap_days.tolist(), draw_days.tolist()
    c_, e_, x_ = c.tolist(), e.tolist(), x.tolist()
    m = P = float("nan")
    for i in range(n):
        observed = z_[i] == z_[i]                       # False for NaN
        if restart_[i] or m != m:
            m, P = (z_[i], OBS_VARIANCE) if observed else (float("nan"), float("nan"))
        else:
            area = m ** (1.0 / VOLUME_EXPONENT) if m > 0 else 0.0
            predicted = m + c_[i] * rain_[i] - e_[i] * evap_[i] * area - x_[i] * draw_[i]
            predicted = min(max(predicted, 0.0), V_MAX)
            predicted_var = P + PROCESS_VARIANCE_PER_DAY * gap_[i]
            if observed:
                gain = predicted_var / (predicted_var + OBS_VARIANCE)
                m, P = predicted + gain * (z_[i] - predicted), (1.0 - gain) * predicted_var
            else:
                m, P = predicted, predicted_var
        mean_out[i], var_out[i] = m, P
    return mean_out, var_out


def run_filter(looks, params, rain_tables, calendar):
    """The filter's (mean, variance) of v at every look; blank before 1993 (no parameters yet).

    The filter restarts from the look itself at each dam's first look from 1993
    on (the previous look has no parameters), and after a gap of more than 60 days.
    """
    par = parameters_per_look(params, looks.year)
    prev = np.r_[0, np.arange(len(looks.day) - 1)]
    gap = looks.day - looks.day[prev]
    continues = (looks.dam == looks.dam[prev]) & par["known"][prev] & (gap <= FILTER_RESTART_GAP_DAYS)
    continues[0] = False
    rain_in = filter_rain_between(rain_tables, par["k"], looks.cell, looks.month[prev], looks.dom[prev],
                                  looks.month, looks.dom)
    evap_days = (evaporation_to_date(calendar, looks.region, looks.month, looks.dom)
                 - evaporation_to_date(calendar, looks.region, looks.month[prev], looks.dom[prev]))
    draw_days = draw_to_date(calendar, looks.month, looks.dom) - draw_to_date(calendar, looks.month[prev],
                                                                                looks.dom[prev])
    z = np.where(par["known"], looks.z, np.nan)          # no filter before the first checkpoint
    mean, var = kalman_filter(z, ~continues, gap.astype(float), rain_in, evap_days, draw_days,
                              par["c"], par["e"], par["x"])
    mean[~par["known"]] = np.nan
    var[~par["known"]] = np.nan
    return mean, var


# ===========================================================================
# 3. The analogue-year ensemble (20 futures per forecast)
# ===========================================================================
@dataclass
class Noise:
    """The 20 noise paths every forecast shares (fixed seed): start [member], steps [step, member]."""
    start: np.ndarray
    steps: np.ndarray


def member_noise(seed=PHYSICS_SEED):
    """Standard normal draws for the 20 futures: one for the starting volume, one per 3-day step."""
    rng = np.random.default_rng(seed)
    return Noise(start=rng.standard_normal(N_MEMBERS), steps=rng.standard_normal((N_STEPS, N_MEMBERS)))


def armed_days_left(looks):
    """Days the dam stays "armed" after each look: last day it was >= 60% full (up to this look) + 180 - today.

    Negative (or -inf) means not armed. TIME: uses this and earlier looks of the same dam only.
    """
    with np.errstate(invalid="ignore"):
        full_enough = looks.rel >= config.ARM_LEVEL
    last_full_day = pd.Series(np.where(full_enough, looks.day.astype(float), -np.inf)).groupby(looks.dam).cummax()
    return last_full_day.to_numpy() + config.ARM_WINDOW_DAYS - looks.day


def dry_level(n_pixels, full_c):
    """The simulated "dry" level: half a pixel of the dam's full wet area, as a share of full (0.01-0.2)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        level = HALF_PIXEL / (np.asarray(n_pixels, float) * np.asarray(full_c, float) / 100.0)
    return np.clip(level, *D0_LEVEL_RANGE)


def simulate_futures(start_mean, start_var, c, e, x, k, cell, region, issue_day, armed_left, d0_level,
                     rain_tables, calendar, noise):
    """The share of the 20 futures with an R30 event and with a D0 event within 90 days, per forecast.

    Future l (l = 1..20) uses the rain of the same calendar months l years
    before. Each 3-day step adds inflow - evaporation - extraction plus noise.
    A future is "armed" while it is within 180 days of being at least 60%
    full; an event (below 30% for R30, below the dry level for D0) counts only
    while armed and then uses up the arming, as in the PREREG event rules.
    """
    n = len(start_mean)
    years_back = np.arange(1, N_MEMBERS + 1)[None, :]
    issue_month = month_number(issue_day)
    v = np.clip(start_mean[:, None] + np.sqrt(np.maximum(start_var, 0.0))[:, None] * noise.start[None, :],
                0.0, V_MAX)
    level = v ** (1.0 / VOLUME_EXPONENT)
    armed_until = {kind: np.repeat(armed_left[:, None], N_MEMBERS, axis=1) for kind in ("R30", "D0")}
    threshold = {"R30": config.R30_LEVEL, "D0": d0_level[:, None]}
    hit = {kind: np.zeros((n, N_MEMBERS), dtype=bool) for kind in ("R30", "D0")}
    step_sd = np.sqrt(PROCESS_VARIANCE_PER_DAY * STEP_DAYS)
    for step in range(N_STEPS):
        month = month_number(issue_day + STEP_DAYS * step + STEP_DAYS // 2)       # month of the step's middle
        source_month = month[:, None] - 12 * years_back
        # TIME: every analogue month ended before the issue month began. (An explicit check, not an
        # `assert`, so it still runs under `python -O`.)
        if not ((source_month < issue_month[:, None]).all() and (source_month >= 0).all()):
            raise AssertionError("An analogue rain month is not before the issue month.")
        inflow = c[:, None] * rain_tables.excess[k[:, None], cell[:, None], source_month]
        evaporation = e[:, None] * calendar.evaporation[region, month][:, None] * level
        draw = x[:, None] * calendar.draw[month][:, None]
        v = np.clip(v + STEP_DAYS * (inflow - evaporation - draw) + step_sd * noise.steps[step][None, :], 0.0, V_MAX)
        level = v ** (1.0 / VOLUME_EXPONENT)
        day = STEP_DAYS * (step + 1)
        for kind in ("R30", "D0"):
            armed_until[kind] = np.where(level >= config.ARM_LEVEL, day + config.ARM_WINDOW_DAYS, armed_until[kind])
            event = (level < threshold[kind]) & (day <= armed_until[kind])
            armed_until[kind] = np.where(event, -np.inf, armed_until[kind])            # the arming is used up
            hit[kind] |= event
    return hit["R30"].mean(axis=1), hit["D0"].mean(axis=1)


# ===========================================================================
# The generator
# ===========================================================================
def p1_issue_mask(looks, full_static, first_issue_day):
    """The looks that are P1 issues, exactly as damdays.features.build: at risk (D0 or R30), from 1988 on.

    full_static (PREREG) only CHOOSES the rows, as in the feature build; it is never a value used here.
    """
    risk = issues.at_risk_flags(looks.pc, looks.px, full_static)
    return (risk["at_risk_D0"] | risk["at_risk_R30"]) & (looks.day >= first_issue_day)


def build_physics(panel, attrs, rain_by_cell, verbose=False, params=None):
    """The physics columns for every P1 issue, from the data layer only (pure: reads no file).

    Inputs are those of damdays.features.build.build_all (the events are not needed).
    params  optional: an already fitted balance (the "physics_params" table of an earlier
            build_physics run). Then nothing is fitted here: the dams are filtered and simulated
            with that balance. This is how a new region (the sealed region, or the dry run's
            region treated as unseen) gets its columns: with the balance fitted on the
            development regions' look pairs, never refitted on the new region's own looks.
            Same result as building the new region together with the development regions
            (tests/test_physics.py checks this), without rerunning the development regions.
    Returns a dict:
      p1_physics      uid, issue_date, ph_p_R30, ph_p_D0: one row per P1 issue, in P1 order
                      (sorted by uid, then date); blank before 1993
      physics_params  one row per checkpoint year: n_pairs, threshold_mm, c, e, x, loss
      filter_summary  counts for reports
    """
    started = time.time()

    def say(message):
        if verbose:
            print(f"  [physics {time.time() - started:5.0f} s] {message}", flush=True)

    dams = studied_dams(attrs)
    looks_table = looks_of(panel, dams["uid"].to_numpy())
    data_end = pd.Timestamp(looks_table["date"].max())
    regions = sorted(dams["region"].astype(str).unique())
    cells = np.asarray(sorted(dams["silo_cell"].astype(str).unique()))
    looks = build_looks(looks_table, dams, regions, cells)
    n_months = int(looks.month.max()) + 1
    rain_tables = build_rain_tables(rain_by_cell, cells, n_months, data_end)
    calendar = build_calendar_tables(regions, n_months + 12)     # the futures run up to 90 days past the last look
    say(f"{len(looks.day):,} looks of {len(dams):,} dams; rain for {len(cells):,} cells")

    if params is None:
        in_fit_region = np.isin(np.asarray(regions)[looks.region], FIT_REGIONS)
        params = fit_checkpoint_parameters(looks, rain_tables, calendar, in_fit_region)
        say(f"balance fitted for checkpoints {params['year'].min()}-{params['year'].max()} "
            f"on the look pairs of {sorted(set(regions) & set(FIT_REGIONS))}")
    else:
        say(f"balance given (checkpoints {params['year'].min()}-{params['year'].max()}): not refitted")
    mean, var = run_filter(looks, params, rain_tables, calendar)
    say(f"Kalman filter run on {int(np.isfinite(mean).sum()):,} looks")

    full_static = dams["full"].to_numpy(dtype=float)[looks.dam]
    first_issue_day = int(day_numbers([config.FIRST_ISSUE_DATE])[0])
    is_issue = p1_issue_mask(looks, full_static, first_issue_day)
    d0_level = dry_level(dams["n_pixels"].to_numpy(dtype=float)[looks.dam], looks.full_c)
    armed_left = armed_days_left(looks)
    par = parameters_per_look(params, looks.year)
    simulate = np.flatnonzero(is_issue & np.isfinite(mean) & np.isfinite(d0_level) & par["known"])

    p_r30, p_d0 = np.full(len(looks.day), np.nan), np.full(len(looks.day), np.nan)
    noise = member_noise()
    for start in range(0, len(simulate), CHUNK_ROWS):
        rows = simulate[start:start + CHUNK_ROWS]
        p_r30[rows], p_d0[rows] = simulate_futures(
            mean[rows], var[rows], par["c"][rows], par["e"][rows], par["x"][rows], par["k"][rows],
            looks.cell[rows], looks.region[rows], looks.day[rows], armed_left[rows], d0_level[rows],
            rain_tables, calendar, noise)
    say(f"20 futures simulated for {len(simulate):,} forecasts")

    issue_rows = np.flatnonzero(is_issue)
    table = pd.DataFrame({"uid": dams["uid"].to_numpy()[looks.dam[issue_rows]],
                          "issue_date": dates_from_day_numbers(looks.day[issue_rows]),
                          "ph_p_R30": p_r30[issue_rows].astype(np.float32),
                          "ph_p_D0": p_d0[issue_rows].astype(np.float32)})
    summary = dict(looks=int(len(looks.day)), looks_with_filter_state=int(np.isfinite(mean).sum()),
                   p1_issues=int(len(issue_rows)), issues_with_physics=int(len(simulate)),
                   data_end=str(data_end.date()), regions=regions, seconds=round(time.time() - started))
    return {"p1_physics": table, "physics_params": params, "filter_summary": summary}


# ===========================================================================
# Saving and attaching the columns to the P1 table
# ===========================================================================
def save_physics(table, p1_keys, path=PHYSICS_FILE):
    """Write the physics columns in P1-table order (checked against the P1 keys). Returns the path."""
    check_aligned(table, p1_keys)
    out = table[["uid", "issue_date", *PHY_COLUMNS]].copy()
    out["uid"] = out["uid"].astype("category")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    out.to_pickle(temporary)
    temporary.replace(path)            # a reader never sees a half-written file
    return path


def check_aligned(table, p1):
    """Raise unless `table` lists exactly the P1 issues of `p1`, in the same order."""
    same = len(table) == len(p1)
    if same:
        same = (np.array_equal(table["uid"].astype(str).to_numpy(), p1["uid"].astype(str).to_numpy())
                and np.array_equal(pd.to_datetime(table["issue_date"]).to_numpy(),
                                   pd.to_datetime(p1["issue_date"]).to_numpy()))
    if not same:
        raise AssertionError("The physics table does not list the P1 issues in P1 order: rebuild it "
                             "(scripts/10_physics_val.py) after rebuilding the features.")


def with_physics_columns(p1, path=PHYSICS_FILE):
    """p1 with ph_p_R30 and ph_p_D0 added (in place, no copy of the large table) if the physics table has
    been built; p1 unchanged otherwise."""
    if not path.exists():
        return p1
    table = pd.read_pickle(path)
    check_aligned(table, p1)
    for column in PHY_COLUMNS:
        p1[column] = table[column].to_numpy()
    return p1
