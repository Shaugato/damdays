"""Features from one dam's own water history, at each of its looks.

A forecast is issued at every valid look (satellite observation). Each feature
at look j uses looks 0..j only: the current look is the newest data point.
Every rolling window ends AT the current look; nothing after it is touched.

Level is measured as rel = pc_wet / full_c, where full_c is the causal
checkpoint "full" for the look's year (damdays.features.checkpoints), never
the PREREG static full. rel is clipped to [0, 1.5].

Features (K = D0 or R30; "low" means 0 wet pixels for D0, rel < 0.3 for R30)
--------
rel, pc               level now (relative to full, and raw percent wet)
last3                 mean rel of the last 3 looks
s60, s120             trend: least-squares slope of rel per day over the last 60 / 120 days
rec                   rate of change since the highest level of the last 120 days
max365, min365        highest / lowest rel in the last 365 days
since_full            days since rel was last >= 0.9
armed, since_arm      was rel >= 0.6 in the last 180 days (the PREREG arming level); days since
anom_own              rel minus this dam's usual level for the calendar month (earlier years only)
clim_dd, clim_fast    the dam's typical and fast drawdown rates for the season (checkpoint)
gap_prev              days since the previous look
sin_doy, cos_doy, month   time of year
full_c, wet_share_c, fill_share_c, n_hist_c   checkpoint history
low365_K              share of low looks in the last 365 days
since_low_K           days since the last low look
dtt_trend_K, dtt_clim_K, dtt_fast_K
                      log(1 + days until the threshold is reached) if the dam keeps falling at
                      its current trend (s60), its typical rate, or its fast rate
"""
import numpy as np
import pandas as pd

from damdays import config
from damdays.features.common import days_since, is_warm_season

KIND_THRESHOLD = {"D0": 0.0, "R30": config.R30_LEVEL}   # threshold in rel units
ARM_WINDOW = config.ARM_WINDOW_DAYS                       # 180
SLOPE_MIN_FALL = 1e-4   # a rate slower than this (rel/day) counts as "not falling"


# ---------------------------------------------------------------------------
# Trailing-window helpers (each value uses the current and earlier looks only)
# ---------------------------------------------------------------------------
def rolling_by_days(values, dates, window_days, how):
    """Mean, max or min of `values` over looks within the last `window_days` days (current included).

    The window is (date - window_days, date], as in pandas time-based rolling.
    Missing values are skipped.
    """
    series = pd.Series(np.asarray(values, dtype=float), index=dates)
    rolling = series.rolling(f"{window_days}D", min_periods=1)
    return getattr(rolling, how)().to_numpy()


def trailing_slope(days, values, window_days):
    """Least-squares slope (per day) of `values` over the looks in (day - window_days, day].

    Uses running sums, so each value depends only on the current and earlier
    looks. Days are measured from the dam's FIRST look (never from a later
    one) so the arithmetic is identical however much later data exists.
    NaN when fewer than 2 usable looks are in the window.
    """
    values = np.asarray(values, dtype=float)
    usable = np.isfinite(values)
    x = np.where(usable, days - days[0], 0.0).astype(float)
    y = np.where(usable, values, 0.0)

    def running(v):
        """Running total with a leading 0, so total[b] - total[a] sums looks a..b-1."""
        return np.concatenate([[0.0], np.cumsum(v)])

    n_sum, x_sum, y_sum = running(usable.astype(float)), running(x), running(y)
    xx_sum, xy_sum = running(x * x), running(x * y)
    start = np.searchsorted(days, days - window_days, side="right")   # first look inside the window
    stop = np.arange(1, len(days) + 1)

    def window(total):
        """Sum over each look's window, from a running total."""
        return total[stop] - total[start]

    n, sx, sy, sxx, sxy = (window(t) for t in (n_sum, x_sum, y_sum, xx_sum, xy_sum))
    spread = n * sxx - sx * sx
    with np.errstate(all="ignore"):
        slope = (n * sxy - sx * sy) / spread
    return np.where((n >= 2) & (spread > 0), slope, np.nan)


def rate_since_recent_peak(days, rel, window_days=120):
    """rec: change in rel per day since the highest level in the last `window_days` days.

    0 when the current look is itself the peak; NaN when rel is unknown.
    """
    out = np.full(len(days), np.nan)
    start = np.searchsorted(days, days - window_days, side="left")   # window [day - 120, day]
    for j in range(len(days)):
        if not np.isfinite(rel[j]):
            continue
        segment = rel[start[j]:j + 1]
        k = start[j] + int(np.nanargmax(segment))   # first look at the peak
        out[j] = 0.0 if k == j else (rel[j] - rel[k]) / max(days[j] - days[k], 1)
    return out


def days_to_threshold(rel, rate, threshold):
    """log(1 + days until rel reaches `threshold` at `rate` rel/day), capped at 10 years.

    If the dam is not falling (rate missing or slower than SLOPE_MIN_FALL), the
    answer is the cap. Already below the threshold gives 0.
    """
    rel, rate = np.asarray(rel, float), np.asarray(rate, float)
    falling = np.isfinite(rate) & (rate < -SLOPE_MIN_FALL)
    with np.errstate(all="ignore"):
        days = np.where(falling, np.minimum(config.DAYS_CAP, (rel - threshold) / -rate), config.DAYS_CAP)
    days = np.where(np.isfinite(rel), np.maximum(days, 0.0), np.nan)
    return np.log1p(days)


# ---------------------------------------------------------------------------
# All features of one dam
# ---------------------------------------------------------------------------
def relative_level(pc, full_c):
    """rel = pc_wet / full_c, clipped to [0, 1.5]; NaN where the checkpoint full is unknown."""
    with np.errstate(all="ignore"):
        return np.clip(np.asarray(pc, float) / np.asarray(full_c, float), 0.0, config.REL_CLIP_MAX)


def dam_features(days, dates, pc, px, history, own_clim):
    """Every dam-history feature at every look of one dam.

    days      int day numbers of the looks (sorted)
    dates     the same as a DatetimeIndex
    pc, px    pc_wet and px_wet at each look
    history   dict of checkpoint values per look: full_c, wet_share_c,
              fill_share_c, n_hist_c, dd_warm_c, dd_fast_c, dd_cool_c
    own_clim  the dam's usual rel for each look's calendar month (earlier years only)

    Returns a dict column -> array (one value per look).
    """
    rel = relative_level(pc, history["full_c"])
    months = dates.month.to_numpy()
    warm = is_warm_season(months)

    f = {"rel": rel, "pc": pc}
    f["last3"] = pd.Series(rel).rolling(3, min_periods=1).mean().to_numpy()
    f["s60"] = trailing_slope(days, rel, 60)
    f["s120"] = trailing_slope(days, rel, 120)
    f["rec"] = rate_since_recent_peak(days, rel)
    f["max365"] = rolling_by_days(rel, dates, 365, "max")
    f["min365"] = rolling_by_days(rel, dates, 365, "min")
    f["since_full"] = days_since(rel >= config.FULL_REL_LEVEL, days)
    f["armed"] = (rolling_by_days(rel, dates, ARM_WINDOW, "max") >= config.ARM_LEVEL).astype(float)
    f["since_arm"] = days_since(rel >= config.ARM_LEVEL, days)
    f["anom_own"] = rel - own_clim
    f["clim_dd"] = np.where(warm, history["dd_warm_c"], history["dd_cool_c"])
    f["clim_fast"] = history["dd_fast_c"]
    f["gap_prev"] = np.r_[np.nan, np.diff(days).astype(float)]
    day_of_year = dates.dayofyear.to_numpy()
    f["sin_doy"] = np.sin(2 * np.pi * day_of_year / 365.25)
    f["cos_doy"] = np.cos(2 * np.pi * day_of_year / 365.25)
    f["month"] = months.astype(float)
    for name in ("full_c", "wet_share_c", "fill_share_c", "n_hist_c"):
        f[name] = history[name]

    low_by_kind = {
        "D0": (px == 0).astype(float),
        "R30": np.where(np.isfinite(rel), (rel < config.R30_LEVEL).astype(float), np.nan),
    }
    for kind, low in low_by_kind.items():
        threshold = KIND_THRESHOLD[kind]
        f[f"low365_{kind}"] = rolling_by_days(low, dates, 365, "mean")
        f[f"since_low_{kind}"] = days_since(low == 1, days)
        f[f"dtt_trend_{kind}"] = days_to_threshold(rel, f["s60"], threshold)
        f[f"dtt_clim_{kind}"] = days_to_threshold(rel, f["clim_dd"], threshold)
        f[f"dtt_fast_{kind}"] = days_to_threshold(rel, f["clim_fast"], threshold)
    return f
