"""The per-dam random intercept ("frailty"): does this dam run drier or wetter than the model expects?

The idea
--------
Some dams dry out more often (or less often) than the model predicts for dams
that look like them: a leaky floor, heavy stock use, a farmer who pumps hard.
The model's features cannot see that, but the dam's own track record can.
Every past forecast for the dam whose answer is now final leaves a residual

    y - p    (y = 1 if the event happened, 0 if not; p = the probability the model gave)

If the dam's residuals add up to more than zero, it has been drier than the
model thought, so its next forecast is nudged up. If they add up to less than
zero, it is nudged down.

The formula (PREREG "Model": b = R / (V + 100))
-----------------------------------------------
    R = sum of (y_j - p_j)        over the dam's past forecasts j whose answer is final
    V = sum of p_j (1 - p_j)      over the same forecasts (how much surprise was possible)
    b = R / (V + lambda)          lambda = 100
    new log-odds = anchor log-odds + b          (done in damdays.models.fusion)

This is one Newton step for a per-dam intercept in a logistic model with a
Gaussian prior on that intercept; lambda is the prior's strength. With little
history V is small next to 100, so b stays near 0 and the dam is treated like
any other. With a long history the dam's own evidence takes over. lambda = 100
was chosen on VAL in the pre-event research (hierarchical-pooling family) and
is fixed by the PREREG.

The time rule (the only thing that can go wrong here)
-----------------------------------------------------
A past forecast j may count for a forecast issued on day t only once its
answer is final: its 90-day window plus 30 days to confirm an event, so

    t_j + 120 days <= t        (config.ANSWER_FINAL_DAYS)

This is the same rule as the dam_rate feature and the B2 baseline. A forecast
from 100 days ago still has an open window, so it is ignored. The answer used
is the forecast's label: y_j where label_ok (at least 3 looks in its window),
otherwise the record is skipped.

Which p_j
---------
p_j is the anchor probability for that past forecast BEFORE any frailty is
added (the fused members), from the model fitted at the block's cutoff. That
model can be computed on the issue date, and so can its prediction for any
earlier forecast. For past forecasts inside the fit block this is an in-sample
prediction, exactly as in the pre-event research.
"""
import numpy as np
import pandas as pd

from damdays import config

FRAILTY_LAMBDA = 100.0                      # PREREG: b = R / (V + 100)
ANSWER_FINAL_DAYS = config.ANSWER_FINAL_DAYS  # 120: a past forecast counts once t_j + 120 days <= t
DAY_SPAN = 1_000_000                        # spacing of the (dam, day) sort key; far more days than the archive spans


def day_numbers(dates):
    """Whole days since 1970-01-01 (int64) for an array of dates."""
    days = pd.to_datetime(np.asarray(dates)).to_numpy().astype("datetime64[D]").astype(np.int64)
    if (days < 0).any() or (days + ANSWER_FINAL_DAYS >= DAY_SPAN).any():
        raise ValueError("Dates must fall between 1970 and about 4700 for the (dam, day) sort key.")
    return days


def matured_residual_sums(dam_ids, issue_dates, is_record, y, p, final_after_days=ANSWER_FINAL_DAYS):
    """For every row: R, V and the number of the same dam's past forecasts whose answer is final.

    dam_ids, issue_dates  one entry per forecast (any order; a dam may have many forecasts)
    is_record             True for forecasts that may serve as track record (label known)
    y, p                  the label and the anchor probability of each forecast (only read where is_record)
    final_after_days      a record dated t_j counts for a forecast dated t when t_j + final_after_days <= t

    Returns (R, V, n), arrays aligned with the input rows:
      R  sum of (y_j - p_j)       over the matured records of the same dam
      V  sum of p_j (1 - p_j)     over the same records
      n  how many records that is
    """
    dam = pd.factorize(pd.Series(np.asarray(dam_ids)).astype(str))[0].astype(np.int64)
    day = day_numbers(issue_dates)
    is_record = np.asarray(is_record, dtype=bool)
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    if np.isnan(y[is_record]).any() or np.isnan(p[is_record]).any():
        raise ValueError("Every record needs a known label y and a probability p.")

    # 1. The records, sorted by dam and then by the day their answer became final.
    #    One integer key does both: dam number x DAY_SPAN + day the answer was final.
    record = np.flatnonzero(is_record)
    final_day = day[record] + final_after_days
    record_key = dam[record] * DAY_SPAN + final_day
    order = np.argsort(record_key, kind="stable")
    record_key = record_key[order]
    record_dam = dam[record][order]
    residual = (y[record] - p[record])[order]
    variance = (p[record] * (1.0 - p[record]))[order]

    # 2. Running totals WITHIN each dam, oldest record first: running_R[k] = the sum over the
    #    dam's sorted records up to and including record k. Each dam starts again from 0, so a
    #    dam's sums are added up from its own records only. (One running total across all dams,
    #    differenced per dam, is the same mathematically, but its rounding would then depend on
    #    other dams and on records not yet final, by about 1e-10. The look-ahead test demands
    #    bit-identical values when later data are deleted.)
    running_R = pd.Series(residual).groupby(record_dam).cumsum().to_numpy()
    running_V = pd.Series(variance).groupby(record_dam).cumsum().to_numpy()

    # 3. For each forecast on day t, the same dam's matured records are a contiguous run of
    #    the sorted list: from the dam's first record up to the last one final ON OR BEFORE t.
    first = np.searchsorted(record_key, dam * DAY_SPAN, side="left")
    after_last = np.searchsorted(record_key, dam * DAY_SPAN + day, side="right")   # final_day <= t
    n = after_last - first
    has_history = n > 0
    R = np.zeros(len(day))
    V = np.zeros(len(day))
    R[has_history] = running_R[after_last[has_history] - 1]    # the dam's total up to its last matured record
    V[has_history] = running_V[after_last[has_history] - 1]
    return R, V, n


def frailty_offset(R, V, lam=FRAILTY_LAMBDA):
    """The per-dam shift on the log-odds scale: b = R / (V + lambda)."""
    return np.asarray(R, dtype=float) / (np.asarray(V, dtype=float) + lam)


def frailty_for_rows(dam_ids, issue_dates, is_record, y, p_anchor, lam=FRAILTY_LAMBDA):
    """The frailty b for every row, plus the evidence behind it, as a table.

    p_anchor is the fused probability before any frailty (see the module notes).
    Columns: frailty_b (log-odds shift), frailty_R, frailty_V, frailty_n (matured records used).
    """
    R, V, n = matured_residual_sums(dam_ids, issue_dates, is_record, y, p_anchor)
    return pd.DataFrame({"frailty_b": frailty_offset(R, V, lam), "frailty_R": R, "frailty_V": V,
                         "frailty_n": n.astype(np.int64)})


def frailty_label(b, threshold=0.1):
    """Plain-language label for the app: "drier", "wetter" or "typical" than similar dams.

    b > 0 means the dam's events came more often than the model expected (it runs drier).
    A shift of 0.1 in log-odds is about a 10% change in the odds.
    """
    b = np.asarray(b, dtype=float)
    return np.where(b > threshold, "runs drier than similar dams",
                    np.where(b < -threshold, "runs wetter than similar dams", "typical for similar dams"))
