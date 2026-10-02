"""P1 forecast issues: who is at risk, what happened next (labels), and each dam's track record.

Every valid look of a has_hist dam is a forecast issue, dated D = the look's date.

At risk (which forecasts make sense)
------------------------------------
at_risk_D0    the dam has water now (px_wet > 0): it can still go dry
at_risk_R30   the dam is at least 30% full now (PREREG static full): it can still fall below
elig_rescue_* the stricter issue sets of the pre-event rescue analysis (pc >= 30 and wet;
              rel >= 0.4), kept for the G2 sub-scores
These use the PREREG static full on purpose: they decide WHICH forecasts are
scored, like the population flags. They are never model inputs.

Labels (the future, so NEVER features)
--------------------------------------
y_D0, y_R30   an event of that kind starts in (D, D+90]
y_D0g         1 if a gradual D0 starts in the window; missing (NaN) if only abrupt D0s
              start in it (those are often satellite artefacts); else 0
lab_tte_*     days from D to the next event start (for the runway curve); NaN if none
n_obs_win     valid looks in (D, D+90]
window_closed D+90 is on or before the end of the data (the causal part of label_ok)
label_ok      at least 3 looks in the window AND window_closed (PREREG "label determinable")

Track record (causal B2 counts, used as features)
--------------------------------------------------
For a forecast at D, look back at the same dam's earlier forecasts j:
    * same half-year (Oct-Mar vs Apr-Sep) as D,
    * at risk and label_ok, label known (not NaN),
    * and ANSWER FINAL BY D: j's 90-day window plus 30 days to confirm an
      event has closed, t_j + 120 <= D. Before that, j's answer could still
      change, so using it would peek at the future.
b2N_K counts those forecasts, b2S_K counts how many came true. dam_rate_K
shrinks b2S/b2N toward the region x half-year rate (k = 20); see
add_dam_rates.
"""
import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import fit_mask
from damdays.features.common import day_numbers, is_warm_season

LABEL_KINDS = ("D0", "R30", "D0g")
EMPTY = np.array([], dtype=np.int64)


def event_days_by_dam(events):
    """dict (uid, kind) -> sorted event start day numbers, for D0, R30, D0g and abrupt D0 (D0ab)."""
    events = events.assign(day=day_numbers(events["start_date"]))
    by_dam = {}
    for (uid, kind), group in events.groupby(["uid", "kind"], sort=False):
        by_dam[(uid, kind)] = np.sort(group["day"].to_numpy())
        if kind == "D0":
            gradual = group["gradual"].to_numpy(dtype=bool)
            by_dam[(uid, "D0g")] = np.sort(group["day"].to_numpy()[gradual])
            by_dam[(uid, "D0ab")] = np.sort(group["day"].to_numpy()[~gradual])
    return by_dam


def any_event_in_window(event_days, issue_days, horizon=config.HORIZON_DAYS):
    """True where some event starts in (D, D + horizon]."""
    after_start = np.searchsorted(event_days, issue_days, side="right")
    after_end = np.searchsorted(event_days, issue_days + horizon, side="right")
    return after_end > after_start


def days_to_next_event(event_days, issue_days):
    """Days from each D to the next event start after D (NaN if there is none in the data)."""
    k = np.searchsorted(event_days, issue_days, side="right")
    out = np.full(len(issue_days), np.nan)
    has_next = k < len(event_days)
    out[has_next] = event_days[k[has_next]] - issue_days[has_next]
    return out


def at_risk_flags(pc, px, full_static):
    """at_risk_D0, at_risk_R30, elig_rescue_D0, elig_rescue_R30 for each look."""
    rel_static = pc / full_static
    return {
        "at_risk_D0": px > 0,
        "at_risk_R30": rel_static >= config.R30_LEVEL,
        "elig_rescue_D0": (pc >= 30) & (px > 0),
        "elig_rescue_R30": rel_static >= 0.40,
    }


def labels(days, event_days, data_end_day):
    """All label columns for one dam's looks (see the module docstring)."""
    horizon = config.HORIZON_DAYS
    # Looks in (D, D+90]: position of the last look <= D+90 minus position of D itself.
    n_obs_win = np.searchsorted(days, days + horizon, side="right") - np.arange(1, len(days) + 1)
    window_closed = days + horizon <= data_end_day
    out = {
        "n_obs_win": n_obs_win,
        "window_closed": window_closed,
        "label_ok": (n_obs_win >= config.MIN_LABEL_OBS) & window_closed,
    }
    for kind in ("D0", "R30"):
        out[f"y_{kind}"] = any_event_in_window(event_days[kind], days).astype(float)
        out[f"lab_tte_{kind}"] = days_to_next_event(event_days[kind], days)
    gradual = any_event_in_window(event_days["D0g"], days)
    abrupt = any_event_in_window(event_days["D0ab"], days)
    out["y_D0g"] = np.where(gradual, 1.0, np.where(abrupt, np.nan, 0.0))
    out["lab_tte_D0g"] = days_to_next_event(event_days["D0g"], days)
    return out


def track_record(days, months, at_risk, label_cols):
    """Causal B2 counts b2S_K and b2N_K for K in D0, R30, D0g (see the module docstring)."""
    warm = is_warm_season(months)
    # n_final[i] = how many earlier forecasts have a FINAL answer by day i:
    # those j with t_j + 120 <= t_i. Looks are sorted, so this is a prefix.
    n_final = np.searchsorted(days + config.ANSWER_FINAL_DAYS, days, side="right")
    risk_for = {"D0": at_risk["at_risk_D0"], "R30": at_risk["at_risk_R30"], "D0g": at_risk["at_risk_D0"]}
    out = {}
    for kind in LABEL_KINDS:
        y = label_cols[f"y_{kind}"]
        counts = risk_for[kind] & label_cols["label_ok"] & np.isfinite(y)
        successes, totals = np.zeros(len(days)), np.zeros(len(days))
        for same_half in (warm, ~warm):
            # Running totals over looks of this half-year only.
            hits = np.r_[0.0, np.cumsum(np.where(counts & same_half, y, 0.0))]
            seen = np.r_[0.0, np.cumsum(counts & same_half)]
            successes[same_half] = hits[n_final[same_half]]
            totals[same_half] = seen[n_final[same_half]]
        out[f"b2S_{kind}"], out[f"b2N_{kind}"] = successes, totals
    return out


def train_prior_sums(region, issue_dates, at_risk, label_cols):
    """Sums for the dam_rate prior: per (kind, region, warm), positives and counts of TRAIN forecasts.

    The prior is the region x half-year event rate over the TRAIN-block
    forecasts whose answer was FINAL BEFORE VALIDATION STARTS (1 Jan 2009):
    issued before 2009 AND t + 120 days before 1 Jan 2009. This is exactly the
    purged fit set splits.fit_mask(dates, "VAL").

    Why the purge matters: a forecast issued on 20 Sep 2008 only has a final
    answer on 18 Jan 2009 (its 90-day window plus 30 days to confirm an
    event). A validation forecast on 2 Jan 2009 could not have known that
    answer, so it must not be inside the prior. With the purge, the prior is
    fully in the past for every VAL, TEST and sealed-region forecast.

    For a TRAIN-block forecast the prior is still one constant per region and
    half-year that includes later TRAIN answers (in-sample; disclosed in
    docs/FEATURES.md). The 1986-87 warm-up looks are included, as in the
    pre-event research: their answers are final long before 2009.
    """
    dates = pd.DatetimeIndex(issue_dates)
    in_train = fit_mask(dates, "VAL")      # TRAIN block AND answer final before 2009-01-01
    warm = is_warm_season(dates.month)
    risk_for = {"D0": at_risk["at_risk_D0"], "R30": at_risk["at_risk_R30"], "D0g": at_risk["at_risk_D0"]}
    sums = {}
    for kind in LABEL_KINDS:
        y = label_cols[f"y_{kind}"]
        use = in_train & risk_for[kind] & label_cols["label_ok"] & np.isfinite(y)
        for is_warm in (True, False):
            pick = use & (warm == is_warm)
            sums[(kind, region, is_warm)] = (float(y[pick].sum()), int(pick.sum()))
    return sums


def combine_prior_sums(all_sums):
    """Add up per-dam prior sums; returns dict (kind, region, warm) -> TRAIN event rate."""
    totals = {}
    for sums in all_sums:
        for key, (hits, n) in sums.items():
            old_hits, old_n = totals.get(key, (0.0, 0))
            totals[key] = (old_hits + hits, old_n + n)
    return {key: hits / n if n else np.nan for key, (hits, n) in totals.items()}


def add_dam_rates(table, prior, kinds=LABEL_KINDS):
    """dam_rate_K = (b2S_K + k * prior) / (b2N_K + k), k = 20, for each K in `kinds`.

    The dam's own past event rate, pulled toward the regional rate when it has
    little history. Built only from b2S/b2N (causal) and the purged TRAIN
    prior (see train_prior_sums).
    """
    k = config.B2_SHRINK_P1
    region = table["region"].astype(str).to_numpy()
    warm = table["warm"].to_numpy(dtype=bool)
    for kind in kinds:
        prior_rate = np.full(len(table), np.nan)
        for (prior_kind, prior_region, prior_warm), rate in prior.items():
            if prior_kind == kind:
                prior_rate[(region == prior_region) & (warm == prior_warm)] = rate
        b2s, b2n = table[f"b2S_{kind}"].to_numpy(float), table[f"b2N_{kind}"].to_numpy(float)
        table[f"dam_rate_{kind}"] = ((b2s + k * prior_rate) / (b2n + k)).astype(np.float32)
    return table
