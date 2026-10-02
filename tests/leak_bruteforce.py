"""Slow, obviously-correct re-implementations of the causal feature rules (for the leakage hunt).

The feature code (damdays.features) is written to be fast: running sums,
searchsorted, cumulative counts. Fast code is where off-by-one and look-ahead
bugs hide. The functions here compute the same quantities the slow way: for
ONE issue date D at a time, select the looks that the rule allows (written out
as a plain date condition), then summarise them.

They share no code with damdays.features (only the constants in
damdays.config), so a test that compares the two catches a bug in either one.
Every selection below is written so that it can only ever see data dated on
or before D; that is the whole point.
"""
import numpy as np
import pandas as pd

from damdays import config

EPOCH = np.datetime64("1970-01-01", "D")


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def day_number(dates):
    """Whole days since 1970-01-01 (int64) for dates or a single date."""
    values = np.asarray(pd.to_datetime(dates), dtype="datetime64[ns]").astype("datetime64[D]")
    return (values - EPOCH).astype(np.int64)


def first_of_january(year):
    """Day number of 1 January of `year`."""
    return int(day_number([f"{int(year)}-01-01"])[0])


def is_warm_month(month):
    """True for Oct-Mar."""
    return int(month) in config.SEASON_MONTHS


def all_grid_dates(last_date):
    """The neighbour grid written out by hand: the 1st and 16th of each month from 1 Jan 1987."""
    out = []
    for year in range(config.FIRST_CHECKPOINT_YEAR, pd.Timestamp(last_date).year + 1):
        for month in range(1, 13):
            for day in (1, 16):
                date = pd.Timestamp(year, month, day)
                if date <= pd.Timestamp(last_date):
                    out.append(date)
    return out


# ---------------------------------------------------------------------------
# One dam: what was known on 1 January (checkpoints)
# ---------------------------------------------------------------------------
def checkpoint_year(issue_year):
    """The checkpoint a forecast in `issue_year` uses: 1 Jan of that year, never later than 2016."""
    return min(int(issue_year), config.LAST_CHECKPOINT_YEAR)


def checkpoint_stats(days, pc, px, dates, year):
    """full_c, n_hist_c, wet_share_c, fill_share_c, dd_warm_c, dd_fast_c, dd_cool_c from looks before 1 Jan `year`.

    Only looks with day < 1 Jan `year` are selected, so nothing on or after
    that day can matter.
    """
    nan = float("nan")
    if year < config.FIRST_CHECKPOINT_YEAR:
        return dict(full_c=nan, n_hist_c=nan, wet_share_c=nan, fill_share_c=nan,
                    dd_warm_c=nan, dd_fast_c=nan, dd_cool_c=nan)
    known = days < first_of_january(year)
    n = int(known.sum())
    if n == 0:
        return dict(full_c=nan, n_hist_c=0, wet_share_c=nan, fill_share_c=nan,
                    dd_warm_c=nan, dd_fast_c=nan, dd_cool_c=nan)
    pc_k, px_k = pc[known], px[known]
    raw_full = float(np.percentile(pc_k, config.FULL_QUANTILE * 100))
    trusted_full = raw_full if (n >= config.MIN_PRE_OBS and raw_full > 0) else nan

    # fill_share: of the Jul-Jun years with any look so far, how many reached 90% of full?
    dates_k = pd.DatetimeIndex(dates[known])
    jul_jun_year = np.where(dates_k.month >= 7, dates_k.year, dates_k.year - 1)
    seen_years = set(jul_jun_year)
    filled_years = set(jul_jun_year[pc_k >= config.FILL_LEVEL * raw_full]) if raw_full > 0 else set()

    # Drawdown: consecutive pairs of known looks, 8-40 days apart, first look at least 30% full.
    warm_rates, cool_rates = [], []
    if raw_full > 0:
        days_k = days[known]
        for a in range(n - 1):
            gap = days_k[a + 1] - days_k[a]
            if config.DRAWDOWN_GAP_DAYS[0] <= gap <= config.DRAWDOWN_GAP_DAYS[1] \
                    and pc_k[a] >= config.DRAWDOWN_MIN_REL * raw_full:
                rate = (pc_k[a + 1] - pc_k[a]) / gap / raw_full
                (warm_rates if is_warm_month(dates_k[a].month) else cool_rates).append(rate)

    def pct(values, q):
        """q-th percentile with at least DRAWDOWN_MIN_PAIRS values, else NaN."""
        return float(np.percentile(values, q)) if len(values) >= config.DRAWDOWN_MIN_PAIRS else nan

    return dict(full_c=trusted_full, n_hist_c=n, wet_share_c=float(np.mean(px_k > 0)),
                fill_share_c=len(filled_years) / len(seen_years),
                dd_warm_c=pct(warm_rates, 50), dd_fast_c=pct(warm_rates, 20), dd_cool_c=pct(cool_rates, 50))


def full_by_year(days, pc, px, dates):
    """dict checkpoint year -> trusted full_c (looks before 1 Jan of that year), for 1987..2016."""
    out = {}
    for year in range(config.FIRST_CHECKPOINT_YEAR, config.LAST_CHECKPOINT_YEAR + 1):
        known = pc[days < first_of_january(year)]
        full = float(np.percentile(known, config.FULL_QUANTILE * 100)) if len(known) else np.nan
        out[year] = full if (len(known) >= config.MIN_PRE_OBS and full > 0) else np.nan
    return out


def rel_of_looks(pc, dates, fulls):
    """rel of each look against the checkpoint full of the look's own year (NaN before 1987)."""
    years = pd.DatetimeIndex(dates).year
    full = np.array([fulls.get(checkpoint_year(y), np.nan) if y >= config.FIRST_CHECKPOINT_YEAR else np.nan
                     for y in years], dtype=float)
    with np.errstate(all="ignore"):
        return np.clip(pc / full, 0.0, config.REL_CLIP_MAX)


# ---------------------------------------------------------------------------
# One dam: features at one look, from that look and earlier ones only
# ---------------------------------------------------------------------------
def days_since_last(flag, days, j):
    """Days from look j back to the latest look 0..j where flag is True (capped; cap if none)."""
    hits = np.flatnonzero(flag[: j + 1])
    if len(hits) == 0:
        return float(config.DAYS_CAP)
    return float(min(config.DAYS_CAP, days[j] - days[hits[-1]]))


def least_squares_slope(x, y):
    """Slope of the straight line through (x, y) points; NaN with fewer than 2 points or no spread."""
    keep = np.isfinite(y)
    x, y = np.asarray(x, float)[keep], np.asarray(y, float)[keep]
    if len(x) < 2 or np.ptp(x) == 0:
        return np.nan
    return float(np.polyfit(x, y, 1)[0])


def log_days_to(rel_now, rate, threshold):
    """log(1 + days until `threshold` at `rate` rel/day); the cap when not falling; 0 when already below."""
    if not np.isfinite(rel_now):
        return np.nan
    if np.isfinite(rate) and rate < -1e-4:
        days = min(config.DAYS_CAP, (rel_now - threshold) / -rate)
    else:
        days = config.DAYS_CAP
    return float(np.log1p(max(days, 0.0)))


def history_at(j, days, rel, px, months, checkpoint):
    """Dam-history features at look j. Every window is (D - w, D] with D = day of look j.

    `days[:j + 1]` are the only looks ever selected: a look after j has a
    larger day number and fails every "<= D" condition below anyway.
    """
    D = days[j]
    past = np.arange(len(days)) <= j

    def window(w, left_closed=False):
        """Looks in (D - w, D] (or [D - w, D])."""
        lower = (days >= D - w) if left_closed else (days > D - w)
        return past & lower & (days <= D)

    with np.errstate(all="ignore"):
        low_r30 = np.where(np.isfinite(rel), (rel < config.R30_LEVEL).astype(float), np.nan)
        w365, w180 = window(365), window(config.ARM_WINDOW_DAYS)
        out = {
            "rel": rel[j],
            "last3": np.nanmean(rel[max(0, j - 2): j + 1]) if np.isfinite(rel[max(0, j - 2): j + 1]).any() else np.nan,
            "max365": np.nanmax(rel[w365]) if np.isfinite(rel[w365]).any() else np.nan,
            "min365": np.nanmin(rel[w365]) if np.isfinite(rel[w365]).any() else np.nan,
            "low365_D0": float(np.mean(px[w365] == 0)),
            "low365_R30": np.nanmean(low_r30[w365]) if np.isfinite(low_r30[w365]).any() else np.nan,
            "s60": least_squares_slope(days[window(60)], rel[window(60)]),
            "s120": least_squares_slope(days[window(120)], rel[window(120)]),
            "since_full": days_since_last(rel >= config.FULL_REL_LEVEL, days, j),
            "since_arm": days_since_last(rel >= config.ARM_LEVEL, days, j),
            "armed": float(np.isfinite(rel[w180]).any() and np.nanmax(rel[w180]) >= config.ARM_LEVEL),
            "since_low_D0": days_since_last(px == 0, days, j),
            "since_low_R30": days_since_last(low_r30 == 1, days, j),
            "gap_prev": float(D - days[j - 1]) if j > 0 else np.nan,
        }
    # rec: change per day since the highest look in [D - 120, D] (first one if tied).
    if np.isfinite(rel[j]):
        idx = np.flatnonzero(window(120, left_closed=True))
        k = idx[int(np.nanargmax(rel[idx]))]
        out["rec"] = 0.0 if k == j else (rel[j] - rel[k]) / max(D - days[k], 1)
    else:
        out["rec"] = np.nan
    warm = is_warm_month(months[j])
    out["clim_dd"] = checkpoint["dd_warm_c"] if warm else checkpoint["dd_cool_c"]
    out["clim_fast"] = checkpoint["dd_fast_c"]
    for kind, threshold in (("D0", 0.0), ("R30", config.R30_LEVEL)):
        out[f"dtt_trend_{kind}"] = log_days_to(rel[j], out["s60"], threshold)
        out[f"dtt_clim_{kind}"] = log_days_to(rel[j], out["clim_dd"], threshold)
        out[f"dtt_fast_{kind}"] = log_days_to(rel[j], out["clim_fast"], threshold)
    return out


# ---------------------------------------------------------------------------
# One dam: labels and the track record (B2)
# ---------------------------------------------------------------------------
def labels_at(D, look_days, starts, data_end_day):
    """Labels of a forecast on day D. `starts` = dict kind -> event start days of this dam.

    An event counts if it STARTS in (D, D + 90]. label_ok needs 3 looks in
    that window and the window inside the data.
    """
    def started_in_window(event_days):
        """Any event day in (D, D + 90]?"""
        event_days = np.asarray(event_days)
        return bool(((event_days > D) & (event_days <= D + config.HORIZON_DAYS)).any())

    n_obs = int(((look_days > D) & (look_days <= D + config.HORIZON_DAYS)).sum())
    gradual, abrupt = started_in_window(starts["D0g"]), started_in_window(starts["D0ab"])
    return {
        "y_D0": float(started_in_window(starts["D0"])),
        "y_R30": float(started_in_window(starts["R30"])),
        "y_D0g": 1.0 if gradual else (np.nan if abrupt else 0.0),
        "n_obs_win": n_obs,
        "label_ok": n_obs >= config.MIN_LABEL_OBS and D + config.HORIZON_DAYS <= data_end_day,
    }


def track_record_at(i, days, months, at_risk, labels_of_looks, kind):
    """b2S, b2N of kind at look i, counting earlier looks j one condition at a time.

    j counts only if: same half-year as look i, at risk for the kind, its
    label is determinable and known, and its answer was FINAL by day D_i:
    D_j + 90 (window) + 30 (time to confirm an event) <= D_i.
    """
    hits = total = 0
    for j in range(len(days)):
        answer_final = days[j] + config.HORIZON_DAYS + config.PURGE_DAYS <= days[i]
        same_half = is_warm_month(months[j]) == is_warm_month(months[i])
        label = labels_of_looks[j][f"y_{kind}"]
        usable = at_risk[j] and labels_of_looks[j]["label_ok"] and np.isfinite(label)
        if answer_final and same_half and usable:
            hits += label
            total += 1
    return hits, total


# ---------------------------------------------------------------------------
# Neighbours: as-of levels on the grid, own climatology
# ---------------------------------------------------------------------------
def asof_at(grid_day, days, rel, px):
    """(level, dry) of a dam's last look STRICTLY before grid_day, if at most 30 days old; else (NaN, NaN).

    The level can still be NaN when the dam's checkpoint "full" is not known
    yet; whether the look was dry does not need "full", so it is known anyway.
    """
    before = np.flatnonzero(days < grid_day)
    if len(before) == 0:
        return np.nan, np.nan
    k = before[-1]
    if grid_day - days[k] > config.NEIGHBOUR_MAX_AGE_DAYS:
        return np.nan, np.nan
    return rel[k], float(px[k] == 0)


def own_climatology(year, month, days, rel, px):
    """A dam's usual as-of level in `month`: mean over earlier years (1987 to min(year, 2016) - 1).

    Each earlier year contributes the mean of its as-of levels on the 1st and
    16th of that month (skipping unknown ones). Needs at least 3 such years.
    """
    yearly = []
    for y in range(config.FIRST_CHECKPOINT_YEAR, min(year, config.LAST_CHECKPOINT_YEAR)):
        values = [asof_at(int(day_number([f"{y}-{month:02d}-{d:02d}"])[0]), days, rel, px)[0] for d in (1, 16)]
        values = [v for v in values if np.isfinite(v)]
        if values:
            yearly.append(np.mean(values))
    return float(np.mean(yearly)) if len(yearly) >= config.OWN_CLIM_MIN_YEARS else np.nan


def neighbour_summary(grid_dates, issue_date, neighbour_series):
    """R_anom, R_chg3 and R_zero for an issue, from neighbour (days, rel, px) series.

    The grid date used is the last 1st/16th on or before the issue date; every
    neighbour look used is strictly before it.
    """
    g_index = max(k for k, g in enumerate(grid_dates) if g <= pd.Timestamp(issue_date))
    g = grid_dates[g_index]
    g_day = int(day_number([g])[0])
    g3_day = int(day_number([grid_dates[g_index - 6]])[0]) if g_index >= 6 else None
    anomalies, changes, dry = [], [], []
    for days, rel, px in neighbour_series:
        level, is_dry = asof_at(g_day, days, rel, px)
        if np.isfinite(is_dry):
            dry.append(is_dry)
        if np.isfinite(level):
            anomalies.append(level - own_climatology(g.year, g.month, days, rel, px))
            if g3_day is not None:
                changes.append(level - asof_at(g3_day, days, rel, px)[0])
    anomalies = [a for a in anomalies if np.isfinite(a)]
    changes = [c for c in changes if np.isfinite(c)]

    def summary(values, how):
        """Median or mean, or NaN with fewer than NEIGHBOUR_MIN values."""
        if len(values) < config.NEIGHBOUR_MIN:
            return np.nan
        return float(np.median(values) if how == "median" else np.mean(values))

    return {"R_anom": summary(anomalies, "median"), "R_chg3": summary(changes, "median"),
            "R_zero": summary(dry, "mean"), "grid_date": g}


# ---------------------------------------------------------------------------
# Rain
# ---------------------------------------------------------------------------
def month_before(date):
    """YYYYMM of the calendar month before `date`'s month."""
    date = pd.Timestamp(date)
    return (date.year - 1) * 100 + 12 if date.month == 1 else date.year * 100 + date.month - 1


def months_ending_at(end_yyyymm, w):
    """The w months (YYYYMM) ending at end_yyyymm, oldest first."""
    year, month = divmod(int(end_yyyymm), 100)
    out = []
    for _ in range(w):
        out.append(year * 100 + month)
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out[::-1]


def rain_total(series, end_yyyymm, w):
    """Total rain of the w months ending at end_yyyymm; NaN if any month is missing. series: dict YYYYMM -> mm."""
    months = months_ending_at(end_yyyymm, w)
    if not all(m in series for m in months):
        return np.nan
    return float(sum(series[m] for m in months))


def rain_percentile(series, end_yyyymm, w):
    """Mid-rank percentile of the w-month total among the same calendar month's totals in EARLIER years.

    Earlier years: from 1960 up to the year before end_yyyymm's year, never after 2015.
    Needs 10 such totals.
    """
    year, month = divmod(int(end_yyyymm), 100)
    now = rain_total(series, end_yyyymm, w)
    baseline_years = range(config.RAIN_BASELINE_YEARS[0], min(year, config.RAIN_BASELINE_YEARS[1] + 1))
    past = [rain_total(series, y * 100 + month, w) for y in baseline_years]
    past = np.array([p for p in past if np.isfinite(p)])
    if len(past) < config.RAIN_MIN_BASELINE or not np.isfinite(now):
        return np.nan
    return float(((past < now).sum() + 0.5 * (past == now).sum()) / len(past))
