"""Which rows a model may learn from ("fit rows"), and which rows it must predict.

The time rule (PREREG "Splits")
-------------------------------
A model judged on a block may only learn from forecasts whose ANSWER was
final before that block starts. A P1 forecast issued on day D is answered by
what happens in (D, D+90], and an event in that window is confirmed up to
30 days later. So a P1 row may be learned from only if D + 90 + 30 days falls
before the block starts (damdays.data.splits.fit_mask). This is the "purge":

    judged on VAL (from 2009-01-01)   learn from TRAIN issues with D + 120 days < 2009-01-01
    judged on TEST (from 2016-07-01)  learn from TRAIN and VAL issues (all answered by then)

A P2 season rating issued on 1 July of year Y is answered by 31 March of
Y+1 (+30 days to confirm). Every season issued in the fit blocks is answered
before the first rating of the next block (1 July), which p2_fit_rows checks.

The other fit-row rules
-----------------------
* at risk for the event kind (the dam can still have the event),
* label determinable (label_ok: at least 3 looks in the window),
* label known (for D0-gradual, windows holding only an abrupt dry-out have no label),
* in the population the model is meant for (all waterbodies, dam-like, persistent).
"""
import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import fit_mask, time_block

P1_KINDS = ("R30", "D0", "D0g")
POPULATIONS = ("all", "dam_like", "persistent")


# ---------------------------------------------------------------------------
# P1: one forecast at every valid look
# ---------------------------------------------------------------------------
def p1_label(kind):
    """The label column of a P1 event kind, e.g. "y_R30"."""
    check_kind(kind)
    return f"y_{kind}"


def p1_at_risk_column(kind):
    """The at-risk flag of a kind. D0-gradual is at risk whenever D0 is (the dam has water)."""
    check_kind(kind)
    return "at_risk_R30" if kind == "R30" else "at_risk_D0"


def check_kind(kind):
    """Raise unless kind is one of R30, D0, D0g."""
    if kind not in P1_KINDS:
        raise ValueError(f"Unknown P1 kind {kind!r}; expected one of {P1_KINDS}")


def population_mask(table, population):
    """True for rows in the population: "all", "dam_like" or "persistent"."""
    if population == "all":
        return np.ones(len(table), dtype=bool)
    if population not in POPULATIONS:
        raise ValueError(f"Unknown population {population!r}; expected one of {POPULATIONS}")
    return table[population].to_numpy(dtype=bool)


def in_fit_blocks(issue_dates, block):
    """True for issues in the blocks a model judged on `block` learns from, WITHOUT the purge.

    Only used to show how much the purge changes (a diagnostic); models use p1_fit_rows.
    """
    blocks = time_block(issue_dates)
    allowed = {"VAL": ["TRAIN"], "TEST": ["TRAIN", "VAL"]}[block]
    return np.isin(blocks, allowed)


def p1_fit_rows(table, kind, block, population="all", purge=True):
    """Rows a P1 model for `kind` may learn from when it is judged on `block` (VAL or TEST).

    purge=False drops only the purge (kept for one diagnostic: the pre-event
    research fitted its baseline rates on unpurged TRAIN rows).
    """
    dates = table["issue_date"]
    answered_before_block = fit_mask(dates, block) if purge else in_fit_blocks(dates, block)
    return (answered_before_block
            & table[p1_at_risk_column(kind)].to_numpy(dtype=bool)
            & table["label_ok"].to_numpy(dtype=bool)
            & table[p1_label(kind)].notna().to_numpy()
            & population_mask(table, population))


def p1_block_rows(table, kind, block):
    """Every forecast issued in `block` for which the dam is at risk of `kind`.

    This includes forecasts whose label cannot be determined (label_ok False):
    they are predicted too, so the PREREG sensitivity row can be scored later.
    The scorecard drops rows without a label and counts them.
    """
    return (time_block(table["issue_date"]) == block) & table[p1_at_risk_column(kind)].to_numpy(dtype=bool)


def p1_scored_label(table, kind):
    """The label as the scorecard should see it: the answer where label_ok, blank otherwise."""
    label = table[p1_label(kind)].astype(float)
    return label.where(table["label_ok"].to_numpy(dtype=bool)).to_numpy()


# ---------------------------------------------------------------------------
# P2: one season rating every 1 July
# ---------------------------------------------------------------------------
P2_LABELS = {"P2_dam": "y", "P2_dam_g": "y_g", "P2_cell": "y"}


def first_rating_in_block(block):
    """The first 1 July season rating of a block (VAL: 2009-07-01, TEST: 2016-07-01)."""
    start = pd.Timestamp({"VAL": config.VAL_START, "TEST": config.TEST_START}[block])
    month, day = config.SEASON_ISSUE_MONTH_DAY
    first = pd.Timestamp(start.year, month, day)
    return first if first >= start else pd.Timestamp(start.year + 1, month, day)


def season_answer_final(issue_dates):
    """When a season rating's answer is final: 31 March after the season, plus the 30 days to confirm an event."""
    years = pd.DatetimeIndex(pd.to_datetime(issue_dates)).year
    window_end = pd.to_datetime([f"{y + 1}-03-31" for y in years])
    return window_end + pd.Timedelta(days=config.PURGE_DAYS)


def p2_fit_rows(table, label, block, population="all"):
    """Season ratings a P2 model may learn from when it is judged on `block` (VAL or TEST).

    Seasons issued in the fit blocks (TRAIN for VAL; TRAIN and VAL for TEST)
    with a determinable, known label. Their answers are all final before the
    block's first rating; this is asserted, not assumed.
    """
    dates = table["issue_date"]
    fit = in_fit_blocks(dates, block)
    answers_final = season_answer_final(dates[fit])
    if not (answers_final < first_rating_in_block(block)).all():
        raise AssertionError("A P2 fit season would be answered after the block's first rating.")
    return (fit
            & table["label_ok"].to_numpy(dtype=bool)
            & table[label].notna().to_numpy()
            & population_mask(table, population))


def p2_block_rows(table, block):
    """Every season rating issued in `block`."""
    return time_block(table["issue_date"]) == block


def p2_scored_label(table, label):
    """The P2 label as the scorecard should see it: the answer where label_ok, blank otherwise."""
    return table[label].astype(float).where(table["label_ok"].to_numpy(dtype=bool)).to_numpy()
