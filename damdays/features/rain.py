"""Rainfall features from SILO monthly rain, all causal.

The rain window for a forecast issued on day D ends in month L = the month
BEFORE D's month: the last month whose total was complete when D arrived.
(A forecast on 9 July uses rain up to the end of June, never July's partial total.)

Features at an end month L, for windows of w = 1, 3, 6, 12, 24 months
--------------------------------------------------------------------
rain_sum{w}    mm of rain over the w months ending at L
rain_pctc{w}   where that total sits among the same cell's w-month totals that
               ended in the same calendar month in EARLIER years: years from
               1960 up to the year before L, and never later than 2015
               (mid-rank percentile, 0 = driest, 1 = wettest; needs 10 years).
               From 2016 on this is the PREREG fixed 1960-2015 climatology,
               so TEST and the sealed region use exactly that. Before 2016 it
               uses only years that had already happened.

Season-rating extras (P2 issue 1 Jul Y, so L = June Y)
------------------------------------------------------
rain_decile12, rain_decile24   deciles (1-10) of rain_pctc12 / rain_pctc24
drought10      how many of the last 10 Jul-Jun years had less rain than the
               cell's 20th percentile (that percentile, too, from years before Y, up to 2015)
clim_ann, clim_cv, clim_om     mean and coefficient of variation of Jul-Jun totals,
               and mean Oct-Mar total, over Jul-Jun years completed before 1 Jul Y
rain12_anom    rain_sum12 / clim_ann

No feature uses a month after L, and no baseline uses a year after L's year.
A month that had not ended by the newest look in the archive is a partial
total and is blanked before anything is computed (blank_unfinished_months).
"""
import numpy as np
import pandas as pd

from damdays import config

BASE_FIRST, BASE_LAST = config.RAIN_BASELINE_YEARS


def window_sums(rain, w):
    """(cells, months) totals of the w months ending at each month; NaN if any month is missing."""
    n_cells, n_months = rain.shape
    filled = np.where(np.isfinite(rain), rain, 0.0).astype(np.float64)
    running = np.concatenate([np.zeros((n_cells, 1)), np.cumsum(filled, axis=1)], axis=1)
    missing = np.concatenate([np.zeros((n_cells, 1)), np.cumsum(~np.isfinite(rain), axis=1)], axis=1)
    sums = np.full((n_cells, n_months), np.nan)
    if n_months >= w:
        sums[:, w - 1:] = running[:, w:] - running[:, :-w]
        any_missing = (missing[:, w:] - missing[:, :-w]) > 0
        sums[:, w - 1:][any_missing] = np.nan
    return sums


def midrank_percentile(x, baseline):
    """Mid-rank percentile of x[c] among the finite values of baseline[c, :] (needs RAIN_MIN_BASELINE)."""
    valid = np.isfinite(baseline)
    n = valid.sum(axis=1)
    below = ((baseline < x[:, None]) & valid).sum(axis=1)
    equal = ((baseline == x[:, None]) & valid).sum(axis=1)
    with np.errstate(all="ignore"):
        pct = (below + 0.5 * equal) / n
    return np.where((n >= config.RAIN_MIN_BASELINE) & np.isfinite(x), pct, np.nan)


def causal_percentiles(sums, months):
    """rain_pctc for every cell and end month: percentile against earlier same-calendar-month totals."""
    years, cal_months = months // 100, months % 100
    pct = np.full(sums.shape, np.nan)
    for L in range(len(months)):
        same_month = cal_months == cal_months[L]
        # Baseline years: from 1960, before L's year, and never after 2015.
        in_baseline = same_month & (years >= BASE_FIRST) & (years < min(years[L], BASE_LAST + 1))
        pct[:, L] = midrank_percentile(sums[:, L], sums[:, in_baseline])
    return pct


def blank_unfinished_months(rain, months, data_end):
    """Set to NaN every month that had not ended before `data_end`, the date of the newest look.

    The data are a snapshot, and we take the newest satellite look as the
    snapshot date. A SILO month still running on that date holds a partial,
    month-to-date total: September 2026 (the archive ends on 14 Sep) averages
    11.8 mm over our cells, below the driest September of 1990-2025 (15.4 mm;
    median 46.2 mm). Read as a full month,
    it would make a live forecast in October look far too dry. A NaN month
    also blanks every window that contains it (window_sums), so no feature can
    use it. No historical forecast is affected: their rain windows end at
    least one month before their issue date.
    """
    month_ends = pd.to_datetime(months.astype(str), format="%Y%m") + pd.offsets.MonthEnd(0)
    still_running = np.asarray(month_ends >= pd.Timestamp(data_end))
    rain = rain.copy()
    rain[:, still_running] = np.nan
    return rain


def build_rain_features(rain_by_cell, data_end=None):
    """All monthly rain features: dict name -> (cells, months) float32 array, plus months and cells.

    With `data_end` (build_all passes the newest look's date), months that had
    not ended by then are blanked first (see blank_unfinished_months).
    """
    rain = rain_by_cell["rain"].astype(np.float64)
    months = np.asarray(rain_by_cell["months"])
    if data_end is not None:
        rain = blank_unfinished_months(rain, months, data_end)
    feats = {}
    for w in config.RAIN_WINDOWS_MONTHS:
        sums = window_sums(rain, w)
        feats[f"rain_sum{w}"] = sums.astype(np.float32)
        feats[f"rain_pctc{w}"] = causal_percentiles(sums, months).astype(np.float32)
    return {"features": feats, "months": months, "cells": np.asarray(rain_by_cell["cells"]).astype(str),
            "rain": rain}


def lookup(rain_feats, cells, end_months, names=None):
    """Feature values for each (cell, end month YYYYMM) pair; NaN when the month is not in the data."""
    month_pos = {int(m): k for k, m in enumerate(rain_feats["months"])}
    cell_pos = {c: k for k, c in enumerate(rain_feats["cells"])}
    rows = np.array([cell_pos[c] for c in np.asarray(cells).astype(str)])
    cols = np.array([month_pos.get(int(m), -1) for m in end_months])
    known = cols >= 0
    out = {}
    for name in names or rain_feats["features"]:
        values = np.full(len(rows), np.nan, np.float32)
        values[known] = rain_feats["features"][name][rows[known], cols[known]]
        out[name] = values
    return out


# ---------------------------------------------------------------------------
# Season-rating (P2) extras, evaluated at L = June of the season year
# ---------------------------------------------------------------------------
def decile(pct):
    """Percentile (0-1) to decile 1-10."""
    return np.clip(np.floor(np.asarray(pct) * 10) + 1, 1, 10)


def drought_year_count(rain_feats, season_year):
    """drought10 for every cell at L = June of season_year (NaN if June is not in the data).

    A Jul-Jun year is a "drought year" when its total is below the cell's 20th
    percentile of Jul-Jun totals over baseline years before season_year (from
    1960, at most 2015). We count drought years among the 10 ending at L.
    """
    months = rain_feats["months"]
    sum12 = rain_feats["features"]["rain_sum12"].astype(np.float64)
    years = months // 100
    june = months % 100 == 6
    L = np.flatnonzero(months == season_year * 100 + 6)
    if len(L) == 0:
        return np.full(sum12.shape[0], np.nan)
    L = int(L[0])
    in_baseline = june & (years >= BASE_FIRST) & (years < min(season_year, BASE_LAST + 1))
    with np.errstate(all="ignore"):
        q20 = np.nanpercentile(sum12[:, in_baseline], config.DROUGHT_QUANTILE * 100, axis=1)
    last_years = [L - 12 * k for k in range(config.DROUGHT_YEARS) if L - 12 * k >= 0]
    totals = sum12[:, last_years]
    is_dry = (totals < q20[:, None]) & np.isfinite(totals)
    return is_dry.sum(axis=1).astype(float)


def season_climatology(rain_feats, season_year):
    """clim_ann, clim_cv, clim_om for every cell from Jul-Jun years completed before 1 Jul season_year."""
    rain, months = rain_feats["rain"], rain_feats["months"]
    years, cal_months = months // 100, months % 100
    hydro = np.where(cal_months >= 7, years, years - 1)        # Jul-Jun year of each month
    warm = np.isin(cal_months, config.SEASON_MONTHS)
    annual, oct_mar = [], []
    for h in range(int(hydro.min()), season_year):            # Jul-Jun years ending by 30 Jun season_year
        in_year = hydro == h
        if in_year.sum() == 12:                                # complete years only
            annual.append(rain[:, in_year].sum(axis=1))
            oct_mar.append(rain[:, in_year & warm].sum(axis=1))
    if not annual:
        nan = np.full(rain.shape[0], np.nan)
        return {"clim_ann": nan, "clim_cv": nan, "clim_om": nan}
    annual, oct_mar = np.stack(annual, axis=1), np.stack(oct_mar, axis=1)
    with np.errstate(all="ignore"):
        mean = np.nanmean(annual, axis=1)
        return {"clim_ann": mean, "clim_cv": np.nanstd(annual, axis=1) / mean,
                "clim_om": np.nanmean(oct_mar, axis=1)}


def season_rain_features(rain_feats, cells, season_years):
    """All P2 rain columns for (cell, season) pairs."""
    cells = np.asarray(cells).astype(str)
    season_years = np.asarray(season_years)
    out = lookup(rain_feats, cells, season_years * 100 + 6)
    out["rain_decile12"] = decile(out["rain_pctc12"])
    out["rain_decile24"] = decile(out["rain_pctc24"])
    cell_pos = {c: k for k, c in enumerate(rain_feats["cells"])}
    rows = np.array([cell_pos[c] for c in cells])
    extra = {name: np.full(len(cells), np.nan) for name in ("drought10", "clim_ann", "clim_cv", "clim_om")}
    for year in np.unique(season_years):
        pick = season_years == year
        extra["drought10"][pick] = drought_year_count(rain_feats, int(year))[rows[pick]]
        for name, values in season_climatology(rain_feats, int(year)).items():
            extra[name][pick] = values[rows[pick]]
    out.update(extra)
    with np.errstate(all="ignore"):
        out["rain12_anom"] = out["rain_sum12"] / out["clim_ann"]
    return {name: np.asarray(values, dtype=np.float32) for name, values in out.items()}
