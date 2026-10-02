"""The numbers on the scorecard, as small functions that can be checked by hand.

Every function takes plain numpy arrays:
    y  what happened: 1 if the event happened, 0 if not
    p  the forecast probability of the event, from 0 to 1
    w  optional row weights. Normally every row counts once. The bootstrap
       (bootstrap.py) re-weights rows to mimic drawing a fresh set of dams.

Nothing here knows about dams, dates or files. docs/SCORECARD.md explains
what each number means in plain language.
"""
import numpy as np
from scipy.special import expit

PROB_CLIP = 1e-6   # forecasts are kept inside [1e-6, 1 - 1e-6] before taking log-odds


def row_weights(n, w=None):
    """Weights as a float array; all ones when no weights are given."""
    return np.ones(n) if w is None else np.asarray(w, dtype=float)


def logit(p):
    """Log-odds of a probability, log(p / (1 - p)): 0.5 -> 0, 0.9 -> +2.2, 0.1 -> -2.2."""
    p = np.clip(np.asarray(p, dtype=float), PROB_CLIP, 1 - PROB_CLIP)
    return np.log(p / (1 - p))


def sigmoid(x):
    """The inverse of logit: turns log-odds back into a probability."""
    return expit(x)


def safe_ratio(top, bottom):
    """top / bottom, or NaN when bottom is zero."""
    return float(top / bottom) if bottom > 0 else np.nan


# ---------------------------------------------------------------------------
# Accuracy: Brier score and Brier skill
# ---------------------------------------------------------------------------
def brier(y, p, w=None):
    """Brier score: the average squared gap between forecast and outcome. 0 is perfect; lower is better."""
    w = row_weights(len(y), w)
    return safe_ratio(np.sum(w * (np.asarray(p) - y) ** 2), np.sum(w))


def brier_skill(y, p, p_ref, w=None):
    """Brier skill score of p against a reference forecast: 1 - Brier(p) / Brier(p_ref).

    +1 is perfect, 0 is no better than the reference, below 0 is worse.
    +0.2 means the forecast removes 20% of the reference's squared error.
    """
    return 1 - safe_ratio(brier(y, p, w), brier(y, p_ref, w))


# ---------------------------------------------------------------------------
# Ranking: AUC and precision at a recall level
# ---------------------------------------------------------------------------
class Ranking:
    """Forecasts sorted once, so AUC and precision can be recomputed quickly for many weightings.

    Rows with exactly the same forecast form a "tie block". An event row and a
    non-event row in the same tie block count as half a correctly ordered pair.

    With `groups`, rows are only compared with rows of their own group. This
    gives "within-season" AUC (which dams fail in a given year) and
    "within-dam" AUC (in which years a given dam fails).
    """

    def __init__(self, p, groups=None):
        """Sort the forecasts (by group, then from lowest to highest) and find the tie blocks."""
        p = np.asarray(p, dtype=float)
        n = len(p)
        self.grouped = groups is not None
        if self.grouped:
            group = np.unique(np.asarray(groups), return_inverse=True)[1].ravel()
        else:
            group = np.zeros(n, dtype=np.int64)
        order = np.lexsort((p, group))           # by group, then by forecast, lowest first
        p_sorted, group_sorted = p[order], group[order]
        starts_block = np.ones(n, dtype=bool)
        starts_block[1:] = (p_sorted[1:] != p_sorted[:-1]) | (group_sorted[1:] != group_sorted[:-1])
        block_sorted = np.cumsum(starts_block) - 1
        self.block_of_row = np.empty(n, dtype=np.int64)
        self.block_of_row[order] = block_sorted
        self.n_blocks = int(block_sorted[-1]) + 1 if n else 0
        self.group_of_block = group_sorted[starts_block]
        # Groups are contiguous after sorting; this is each group's first (lowest) tie block.
        self.first_block_of_group = np.flatnonzero(np.r_[True, np.diff(self.group_of_block) != 0])

    def event_counts(self, y, w=None):
        """Weighted number of event rows and of non-event rows in each tie block."""
        w = row_weights(len(y), w)
        events = np.bincount(self.block_of_row, weights=w * y, minlength=self.n_blocks)
        non_events = np.bincount(self.block_of_row, weights=w * (1 - y), minlength=self.n_blocks)
        return events, non_events

    def auc(self, y, w=None, counts=None):
        """Share of (event, non-event) pairs that the forecast puts the right way round; ties count half.

        `counts` may pass in event_counts(y, w) when they are already known.
        """
        events, non_events = counts if counts is not None else self.event_counts(y, w)
        # Non-event weight in lower tie blocks of the same group: a running total
        # of non-events, minus the running total where this block's group started.
        before = np.cumsum(non_events) - non_events
        if self.grouped:
            before = before - before[self.first_block_of_group][self.group_of_block]
        right_way_round = events @ (before + 0.5 * non_events)
        if self.grouped:
            all_pairs = (np.bincount(self.group_of_block, weights=events)
                         @ np.bincount(self.group_of_block, weights=non_events))
        else:
            all_pairs = events.sum() * non_events.sum()
        return safe_ratio(right_way_round, all_pairs)

    def precision_at_recall(self, y, w=None, recall=0.5, counts=None):
        """Precision when the highest forecasts are flagged until `recall` of all events are caught.

        Walk down from the highest forecast, flagging whole tie blocks, until at
        least `recall` (e.g. half) of the events are flagged. Return the share
        of flagged rows that really had the event.
        """
        if self.grouped:
            raise ValueError("precision_at_recall needs one overall ranking, not groups")
        events, non_events = counts if counts is not None else self.event_counts(y, w)
        caught = np.cumsum(events[::-1])                    # highest forecasts first
        flagged = np.cumsum((events + non_events)[::-1])
        if caught[-1] <= 0:
            return np.nan
        k = int(np.searchsorted(caught, recall * caught[-1] * (1 - 1e-12)))   # first block reaching the recall
        return float(caught[k] / flagged[k])


def auc(y, p, w=None):
    """AUC: the chance that a random event row got a higher forecast than a random non-event row."""
    return Ranking(p).auc(np.asarray(y, dtype=float), w)


def within_group_auc(y, p, groups, w=None):
    """AUC counting only pairs inside the same group (pairs are pooled over groups)."""
    return Ranking(p, groups).auc(np.asarray(y, dtype=float), w)


def precision_at_recall(y, p, w=None, recall=0.5):
    """Precision at a given recall (see Ranking.precision_at_recall)."""
    return Ranking(p).precision_at_recall(np.asarray(y, dtype=float), w, recall)


# ---------------------------------------------------------------------------
# Calibration: do the probabilities mean what they say?
# ---------------------------------------------------------------------------
def has_both_outcomes(y, w):
    """True if the weighted rows hold at least one event and at least one non-event."""
    events = np.sum(w * y)
    return events > 0 and np.sum(w * (1 - y)) > 0


def calibration_fit(y, p, w=None, start=(0.0, 1.0)):
    """Calibration intercept a and slope b from the fit  logit P(event) = a + b * logit(p).

    Fitted by weighted logistic regression. Perfectly calibrated forecasts
    give a = 0 and b = 1. A slope below 1 means the forecasts are too extreme
    (overconfident); above 1 means they are too cautious. Returns (nan, nan)
    when the fit is impossible, e.g. if every forecast is the same or there
    are no events.
    """
    y = np.asarray(y, dtype=float)
    w = row_weights(len(y), w)
    x = logit(p)
    if not has_both_outcomes(y, w) or np.ptp(x[w > 0]) == 0:
        return np.nan, np.nan
    return fit_calibration_line(y, x, w, start)


def fit_calibration_line(y, x, w, start=(0.0, 1.0), max_iter=50):
    """Newton's method for  logit P(event) = a + b * x, where x is the forecast's log-odds.

    Each step solves a 2 x 2 linear system built from weighted sums. It
    usually settles in 3 or 4 steps. Returns (nan, nan) if it does not settle
    (which happens when events and non-events are perfectly separated).
    """
    a, b = start
    for _ in range(max_iter):
        mu = sigmoid(a + b * x)
        residual = w * (y - mu)                  # gradient pieces
        curvature = w * mu * (1 - mu)            # Hessian pieces
        gradient = np.array([residual.sum(), residual @ x])
        cx = curvature @ x
        hessian = np.array([[curvature.sum(), cx], [cx, curvature @ (x * x)]])
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            return np.nan, np.nan
        a, b = a + step[0], b + step[1]
        if np.max(np.abs(step)) < 1e-9:
            return float(a), float(b)
    return np.nan, np.nan


def calibration_in_the_large(y, p, w=None):
    """CITL: the shift a, in log-odds, that makes the forecasts right on average.

    Fits logit P(event) = a + logit(p) with the slope held at 1. 0 is ideal.
    Negative: the forecasts were too high on average (more alarm than events).
    Positive: too low. A shift of +0.3 means the odds of an event were about
    1.35 times what was forecast.
    """
    y = np.asarray(y, dtype=float)
    w = row_weights(len(y), w)
    if not has_both_outcomes(y, w):
        return np.nan
    return fit_calibration_shift(y, logit(p), w)


def fit_calibration_shift(y, x, w, max_iter=50):
    """Newton's method for  logit P(event) = a + x  (slope fixed at 1); returns a, or nan if it does not settle."""
    a = 0.0
    for _ in range(max_iter):
        mu = sigmoid(a + x)
        step = (w @ (y - mu)) / (w @ (mu * (1 - mu)))
        a += step
        if abs(step) < 1e-10:
            return float(a)
    return np.nan
