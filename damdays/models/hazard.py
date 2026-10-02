"""H, the runway curve: one discrete-time hazard model gives P(event within 30, 60, 90 and 180 days).

The question
------------
A farmer wants a curve, not a single number: how likely is the dam to fall
below a third of full (R30), or to run fully dry (D0), within 30, 60, 90 and
180 days of today's satellite look? Such a curve must never go DOWN as the
horizon gets longer (if the dam is likely dry within 60 days, it is at least
as likely dry within 90).

How the model works (PREREG "Runway curve"; a standard discrete-time hazard model)
-------------------------------------------------------------------------------
Cut the 180 days after an issue date D into four intervals:

    (0, 30]    (30, 60]    (60, 90]    (90, 180]        days after D

The "hazard" h_k is the chance that the event starts inside interval k, given
that it had not started before the interval. One LightGBM learns all four
hazards at once. Each training issue is copied once for every interval it
entered event-free ("person-period" rows), with two extra inputs that say
which interval the copy is about:
    iv_start  days from D to the start of the interval (0, 30, 60 or 90)
    iv_len    length of the interval in days (30, 30, 30 or 90)
The copy's label is 1 if the event started inside that interval.

The curve is then read off at the end of each interval:

    F(t) = 1 - (1 - h_1) (1 - h_2) ... (1 - h_k)        t = 30, 60, 90, 180

Every factor (1 - h) is at most 1, so the product can only shrink and F can
only grow: the curve is monotone by construction. It is still checked
(monotonicity_violations must count 0 falling rows).

Max rule: a fully dry dam is also below a third, so the R30 curve is raised
to at least the D0 curve at every horizon: F_R30 = max(F_R30, F_D0). The max
of two rising curves still rises, so the rule keeps the curve monotone.

The time rule: censor, do not purge
-----------------------------------
The 90-day models (G2, Tidemark's trees) drop a training issue unless its
whole answer was final before the block being judged starts (D + 90 days
+ 30 days to confirm an event < cutoff; VAL cutoff 2009-01-01). That is the
purge. The hazard model can keep more: the answer for interval k is final
once D + (end of interval k) + 30 days has passed, because an event starting
by the end of the interval is confirmed by a second look at most 30 days
later. So each interval is kept on its own if

    D + interval end + 30 days < cutoff                       ("censoring")

Example: an issue on 1 Nov 2008 keeps its first interval (1 Nov 2008 + 30
+ 30 = 31 Dec 2008, before 1 Jan 2009) but not its later ones.

Which issues teach the model
----------------------------
Dam-like waterbodies (PREREG: the curve is a dam-like model), issued in the
fit blocks (TRAIN when judged on VAL; TRAIN and VAL when judged on TEST), at
risk for the event kind, with label_ok. Inputs: the 29 G2c columns of
damdays.features.spec (the physics columns are added later through
extra_features), plus iv_start and iv_len. LightGBM settings: G2's (PREREG:
the same hyperparameters), with 3 threads.

Disclosed, as in the pre-event model: label_ok asks for 3 looks in
(D, D+90]. For an issue from early October to early November 2008 that keeps
only its early intervals, that count can include looks from up to 30 days
after the cutoff. It decides only whether the issue is used, never a label
or an input value. fit_hazard counts these issues (issues_selected_with_post_cutoff_looks).
The model keeps this so that it stays the frozen pre-event recipe (the
person-period counts reproduce it exactly); the horizon baselines below do
not have it (baseline_wait_days).

The horizon-specific baselines (judging each horizon fairly)
------------------------------------------------------------
A 30-day forecast must not be compared with a 90-day base rate. So for each
horizon h:
B0_h  month x region rate of "event within h days" over the fit rows of the
      scored population. Purged per horizon: a fit row counts only if its
      answer was final before the cutoff (see baseline_wait_days).
      B0_90 equals the official P1 B0 exactly.
B2_h  the dam's own track record at horizon h: earlier forecasts of the same
      dam, same half-year, whose answer was final by D (see
      baseline_wait_days), shrunk with k = 20 toward the region x half-year
      rate of the B0_h fit rows.
When is a past forecast's h-day answer final? Two things must be known:
  * the answer itself: D_j + h + 30 days (an event starting by day h is
    confirmed within 30 days);
  * that the answer counts at all: label_ok needs 3 looks in (D_j, D_j + 90],
    which is only known 90 days after D_j.
So a baseline waits max(h + 30, 90) days. Only h = 30 is affected (90 days,
not 60). The pre-event research waited h + 30 days; purge=False keeps that
recipe for the like-for-like checks only. (Measured on VAL: the strict rule
moves BSS vs B0_30 by +0.0001 and BSS vs B2_30 by -0.0002 (R30) / -0.0004 (D0).)
"""
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from damdays import config
from damdays.features import spec
from damdays.features.common import day_numbers
from damdays.models import baselines, g2, rows

CURVE_KINDS = ("R30", "D0")
INTERVAL_EDGES = (0, 30, 60, 90, 180)          # days after the issue date; interval k is (edge k, edge k+1]
HORIZONS = INTERVAL_EDGES[1:]                  # the curve is read at each interval's end: 30, 60, 90, 180 days
N_INTERVALS = len(HORIZONS)
INTERVAL_COLUMNS = ["iv_start", "iv_len"]      # the two extra inputs that say which interval a row is about
CONFIRM_DAYS = config.PURGE_DAYS               # an event is confirmed by a second look at most 30 days later
HAZARD_PARAMS = dict(g2.G2_PARAMS, n_jobs=3)   # G2's LightGBM settings (PREREG), capped at 3 threads
P_MIN, P_MAX = baselines.P_MIN, baselines.P_MAX
DAY_SPAN = 100_000                             # larger than any day number (days since 1970), for sort keys


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def cutoff_date(block):
    """The first day of the block being judged. Nothing answered on or after it may be learned from.

    VAL: 2009-01-01. TEST: 2016-07-01.
    """
    return pd.Timestamp({"VAL": config.VAL_START, "TEST": config.TEST_START}[block])


def cutoff_day(block):
    """cutoff_date as a day number (days since 1970-01-01), for plain integer comparisons."""
    return int(day_numbers([cutoff_date(block)])[0])


def answer_final_before(issue_days, horizon, cutoff):
    """True where the answer "did an event start within `horizon` days?" is final before `cutoff`.

    An event starting by D + horizon is confirmed by D + horizon + 30 days at
    the latest, so the answer is final once that day has passed. (Used for the
    hazard model's censoring; the baselines also wait for label_ok, see
    baseline_wait_days.)
    """
    return np.asarray(issue_days) + horizon + CONFIRM_DAYS < cutoff


def baseline_wait_days(horizon, pre_event_recipe=False):
    """Days after an issue D_j before a baseline (B0_h, B2_h) may use its answer at `horizon`.

    The answer is final at D_j + horizon + 30 days, and whether it counts at
    all (label_ok: at least 3 looks in (D_j, D_j + 90]) is known at D_j + 90.
    A baseline waits for both: max(horizon + 30, 90). For 30 days that is 90,
    not 60; for 60, 90 and 180 days nothing changes.
    pre_event_recipe=True returns horizon + 30 (the pre-event research's rule;
    for the like-for-like checks only).
    """
    answer_final = horizon + CONFIRM_DAYS
    return answer_final if pre_event_recipe else max(answer_final, config.HORIZON_DAYS)


# ---------------------------------------------------------------------------
# Labels at every horizon
# ---------------------------------------------------------------------------
def days_to_event(table, kind):
    """Days from each issue to the next start of a `kind` event; infinity if there is none in the data."""
    tte = table[f"lab_tte_{kind}"].to_numpy(dtype=float)
    return np.where(np.isnan(tte), np.inf, tte)


def horizon_labels(table, kind, data_end):
    """y_h for h = 30, 60, 90, 180: 1 if an event starts in (D, D+h], 0 if not, blank if not known.

    The answer at h is known when label_ok holds (at least 3 looks in
    (D, D+90], and D+90 inside the data) and D + h is inside the data
    (data_end = the last satellite look in the archive). The pre-event code
    also asked for 3 looks in (D, D+180] at 180 days; that always holds when
    label_ok does, because (D, D+90] lies inside (D, D+180].
    Returns a DataFrame with columns y_30 ... y_180 (float, NaN = not known).
    """
    tte = days_to_event(table, kind)
    issue_days = day_numbers(table["issue_date"].to_numpy())
    last_day = int(day_numbers([pd.Timestamp(data_end)])[0])
    label_ok = table["label_ok"].to_numpy(dtype=bool)
    out = {}
    for h in HORIZONS:
        known = label_ok & (issue_days + h <= last_day)
        out[f"y_{h}"] = np.where(known, (tte <= h).astype(float), np.nan)
    # The 90-day slice must be the official P1 label, row for row.
    official = rows.p1_scored_label(table, kind)
    if not np.array_equal(np.nan_to_num(out["y_90"], nan=-1), np.nan_to_num(official, nan=-1)):
        raise AssertionError(f"y_90 differs from the official {kind} label.")
    return pd.DataFrame(out, index=table.index)


# ---------------------------------------------------------------------------
# The hazard model
# ---------------------------------------------------------------------------
def hazard_features(kind, extra_features=()):
    """The input columns before the two interval columns: G2c for the kind, plus any extra (e.g. PHY)."""
    return spec.check_feature_list(g2.g2_features(kind) + list(extra_features))


def hazard_fit_issues(table, kind, block, population="dam_like"):
    """Issues that may teach the hazard model judged on `block`, before censoring.

    Issued in the fit blocks (TRAIN for VAL; TRAIN and VAL for TEST), at risk
    for `kind`, label_ok, in `population`. NOT purged: person_period keeps
    each interval only once its own answer is final before the cutoff.
    """
    return (rows.in_fit_blocks(table["issue_date"], block)
            & table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)
            & table["label_ok"].to_numpy(dtype=bool)
            & rows.population_mask(table, population))


def person_period(issue_days, tte, cutoff):
    """Expand issues into person-period rows: one per interval an issue entered event-free, if its answer is final.

    For interval k = (a, b] days after an issue on day D the copy is kept when
      * no event had started by day a (tte > a): the dam was still "at risk"
        when the interval began, and
      * the interval's answer was final before the cutoff: D + b + 30 < cutoff (censoring).
    Its label is 1 if the event started inside the interval (tte <= b).
    Returns (issue position, interval number 0-3, label) arrays.
    """
    positions, intervals, labels = [], [], []
    for k in range(N_INTERVALS):
        start, end = INTERVAL_EDGES[k], INTERVAL_EDGES[k + 1]
        keep = (tte > start) & answer_final_before(issue_days, end, cutoff)
        positions.append(np.flatnonzero(keep))
        intervals.append(np.full(int(keep.sum()), k, dtype=np.int8))
        labels.append((tte[keep] <= end).astype(np.int8))
    return np.concatenate(positions), np.concatenate(intervals), np.concatenate(labels)


def with_interval_columns(X, interval_numbers):
    """The issue inputs X with iv_start and iv_len of each row's interval appended (float32)."""
    start = np.asarray(INTERVAL_EDGES[:-1], dtype=np.float32)[interval_numbers]
    length = np.diff(np.asarray(INTERVAL_EDGES, dtype=np.float32))[interval_numbers]
    return np.column_stack([X, start, length]).astype(np.float32)


def fit_hazard(table, kind, block, population="dam_like", extra_features=()):
    """Fit the hazard LightGBM for `kind`, to be judged on `block`. Returns (model, info dict).

    table  the P1 table with the keys, dam and nbr groups (damdays.features.store.load_p1)
    """
    started = time.time()
    features = hazard_features(kind, extra_features)
    cutoff = cutoff_day(block)
    issues = hazard_fit_issues(table, kind, block, population)
    issue_days = day_numbers(table.loc[issues, "issue_date"].to_numpy())
    tte = days_to_event(table.loc[issues], kind)
    X_issues = table.loc[issues, features].to_numpy(dtype=np.float32)

    position, interval, label = person_period(issue_days, tte, cutoff)
    model = lgb.LGBMClassifier(**HAZARD_PARAMS).fit(with_interval_columns(X_issues[position], interval), label)

    used = np.unique(position)
    # Issues kept for early intervals only, whose label_ok window (D, D+90] reaches past the cutoff (disclosed).
    post_cutoff_looks = int((issue_days[used] + config.HORIZON_DAYS >= cutoff).sum())
    gain = pd.Series(model.booster_.feature_importance("gain"), index=features + INTERVAL_COLUMNS)
    info = dict(
        kind=kind, block=block, cutoff=str(cutoff_date(block).date()), population=population,
        features=features + INTERVAL_COLUMNS, issues=int(issues.sum()), issues_used=int(len(used)),
        person_period_rows=int(len(label)), person_period_events=int(label.sum()),
        rows_per_interval={f"({INTERVAL_EDGES[k]},{INTERVAL_EDGES[k + 1]}]": int((interval == k).sum())
                           for k in range(N_INTERVALS)},
        events_per_interval={f"({INTERVAL_EDGES[k]},{INTERVAL_EDGES[k + 1]}]": int(label[interval == k].sum())
                             for k in range(N_INTERVALS)},
        issues_selected_with_post_cutoff_looks=post_cutoff_looks,
        top_features_by_gain=(gain / gain.sum()).sort_values(ascending=False).head(8).round(4).to_dict(),
        seconds=round(time.time() - started))
    return model, info


def predict_hazards(model, X):
    """The four interval hazards for each row of X (issue inputs, without the interval columns): array [n, 4]."""
    hazards = np.empty((len(X), N_INTERVALS))
    for k in range(N_INTERVALS):
        hazards[:, k] = model.predict_proba(with_interval_columns(X, np.full(len(X), k)))[:, 1]
    return hazards


def curve_from_hazards(hazards):
    """F at 30, 60, 90 and 180 days: F_k = 1 - (1 - h_1)...(1 - h_k). Monotone by construction."""
    curve = 1.0 - np.cumprod(1.0 - np.asarray(hazards, dtype=float), axis=1)
    return np.clip(curve, P_MIN, P_MAX)     # clipping is monotone too, so the curve still never falls


def max_rule(curve_r30, curve_d0):
    """Raise the R30 curve to at least the D0 curve at every horizon (a dry dam is also below a third)."""
    return np.maximum(curve_r30, curve_d0)


def fit_curves(table, block, population="dam_like", extra_features=()):
    """Fit H for R30 and for D0, to be judged on `block`. Returns ({kind: model}, {kind: info})."""
    models, infos = {}, {}
    for kind in CURVE_KINDS:
        models[kind], infos[kind] = fit_hazard(table, kind, block, population, extra_features)
    return models, infos


def fit_and_predict_curves(table, block, population="dam_like", extra_features=()):
    """Fit H for R30 and D0; predict both curves on every at-risk issue in `block`; apply the max rule.

    Returns (curves, infos):
      curves["D0"]   DataFrame uid, issue_date, p_30 ... p_180 for every at-risk D0 issue in the block
      curves["R30"]  the same for every at-risk R30 issue, after the max rule, plus raw_p_30 ... raw_p_180
                     (before the max rule) and d0_p_30 ... d0_p_180 (the D0 curve on the same rows)
      infos[kind]    fit_hazard's info dict
    """
    models, infos = fit_curves(table, block, population, extra_features)
    return predict_curves(models, table, block, extra_features), infos


def predict_curves(models, table, block, extra_features=()):
    """Both curves from fitted hazard models on every at-risk issue in `block`, with the max rule.

    Returns the `curves` dict described in fit_and_predict_curves. Every at-risk
    R30 issue is also an at-risk D0 issue (a dam at least 30% full has water),
    so the D0 curve is available on every R30 row (asserted).
    """
    block_rows = {kind: rows.p1_block_rows(table, kind, block) for kind in CURVE_KINDS}
    if (block_rows["R30"] & ~block_rows["D0"]).any():
        raise AssertionError("Some at-risk R30 issues are not at-risk D0 issues.")
    curves = {}
    for kind in CURVE_KINDS:
        X = table.loc[block_rows[kind], hazard_features(kind, extra_features)].to_numpy(dtype=np.float32)
        curves[kind] = curve_from_hazards(predict_hazards(models[kind], X))

    d0_on_r30 = curves["D0"][block_rows["R30"][block_rows["D0"]]]     # D0 curve on the R30 rows, same order
    out = {}
    for kind in CURVE_KINDS:
        picked = table.loc[block_rows[kind]]
        frame = pd.DataFrame({"uid": picked["uid"].astype(str).to_numpy(),
                              "issue_date": picked["issue_date"].to_numpy()})
        final = max_rule(curves["R30"], d0_on_r30) if kind == "R30" else curves[kind]
        for j, h in enumerate(HORIZONS):
            frame[f"p_{h}"] = final[:, j]
        if kind == "R30":
            for j, h in enumerate(HORIZONS):
                frame[f"raw_p_{h}"] = curves["R30"][:, j]
                frame[f"d0_p_{h}"] = d0_on_r30[:, j]
        out[kind] = frame
    return out


def curve_columns(frame, prefix="p_"):
    """The curve as an array [n, 4] (30, 60, 90, 180 days) from columns <prefix>30 ... <prefix>180."""
    return frame[[f"{prefix}{h}" for h in HORIZONS]].to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# Horizon-specific baselines B0_h and B2_h
# ---------------------------------------------------------------------------
def own_past_counts(table, kind, y_h, horizon, pre_event_recipe=False):
    """(hits, count) of each dam's earlier forecasts at `horizon`, as B2_h uses them.

    For a forecast on day D, count the same dam's earlier forecasts j that are
      * in the same half-year (Oct-Mar or Apr-Sep) as D,
      * at risk for `kind`, with a known answer at this horizon (y_h not blank),
      * and FINAL by D: day_j + baseline_wait_days(horizon) <= D, that is
        max(horizon + 30, 90) days. Before that, j's answer (or whether it
        counts at all, label_ok) could still change, so using it would peek
        at the future.
    Only issues in the P1 table count (from 1988), like the pre-event B2_h; the
    official 90-day B2 also counts the dam's 1986-87 warm-up looks.
    pre_event_recipe=True waits only horizon + 30 days (like-for-like checks only).
    """
    wait_days = baseline_wait_days(horizon, pre_event_recipe)
    issue_days = day_numbers(table["issue_date"].to_numpy())
    if issue_days.min() <= wait_days or issue_days.max() >= DAY_SPAN:
        raise AssertionError("Day numbers out of the range the sort keys assume.")
    # One sort key per row: a block per (dam, half-year), days in order inside it.
    dam_number = pd.factorize(table["uid"].astype(str))[0].astype(np.int64)
    group = 2 * dam_number + table["warm"].to_numpy(dtype=np.int64)
    key = group * DAY_SPAN + issue_days

    counted = table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool) & ~np.isnan(y_h)
    order = np.argsort(key[counted], kind="stable")
    counted_keys = key[counted][order]
    running_hits = np.r_[0.0, np.cumsum(y_h[counted][order])]
    # Counted rows of the same group from its first row up to day D - wait_days.
    first = np.searchsorted(counted_keys, group * DAY_SPAN, side="left")
    last = np.searchsorted(counted_keys, key - wait_days, side="right")
    return running_hits[last] - running_hits[first], (last - first).astype(float)


def horizon_baseline_fit_rows(table, kind, block, horizon, y_h, population, purge=True):
    """Rows the horizon-h baselines learn from.

    Fit-block issues, at risk, answer known at h, in `population`, and (purge)
    answer final before the block starts: D + max(h + 30, 90) days < cutoff
    (baseline_wait_days). For h = 90 these are exactly the official P1 fit rows.
    purge=False is the pre-event recipe (no purge; a diagnostic only).
    """
    keep = (rows.in_fit_blocks(table["issue_date"], block)
            & table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)
            & ~np.isnan(y_h)
            & rows.population_mask(table, population))
    if purge:
        issue_days = day_numbers(table["issue_date"].to_numpy())
        keep &= issue_days + baseline_wait_days(horizon) < cutoff_day(block)
    return keep


def curve_baselines(table, kind, block, labels, population="dam_like", purge=True):
    """B0_h and B2_h at 30, 60, 90 and 180 days for every at-risk `kind` issue in `block`.

    labels  horizon_labels(table, kind, data_end) for the whole table
    purge   True (official): every answer used waits baseline_wait_days.
            False: the pre-event recipe (unpurged B0_h fit rows and prior,
            B2_h counts that wait h + 30 days), for the like-for-like checks only.
    Returns uid, issue_date, p_B0_30 ... p_B0_180, p_B2_30 ... p_B2_180 (float64);
    the fit-row counts per horizon are in .attrs.
    """
    needed = ["uid", "issue_date", "region", "warm"]          # all the rate lookups need
    scored_rows = rows.p1_block_rows(table, kind, block)
    scored = table.loc[scored_rows, needed]
    out = pd.DataFrame({"uid": scored["uid"].astype(str).to_numpy(), "issue_date": scored["issue_date"].to_numpy()})
    fit_counts = {}
    for h in HORIZONS:
        y_h = labels[f"y_{h}"].to_numpy(dtype=float)
        fit_rows = horizon_baseline_fit_rows(table, kind, block, h, y_h, population, purge)
        fit, fit_y = table.loc[fit_rows, needed], y_h[fit_rows]
        out[f"p_B0_{h}"] = baselines.clip(baselines.month_region_rate(fit, fit_y, scored))
        prior = baselines.region_season_rate(fit, fit_y, scored, season_column="warm")
        hits, count = own_past_counts(table, kind, y_h, h, pre_event_recipe=not purge)
        out[f"p_B2_{h}"] = baselines.clip(baselines.shrunk_rate(hits[scored_rows], count[scored_rows], prior,
                                                                config.B2_SHRINK_P1))
        fit_counts[h] = dict(fit_rows=int(fit_rows.sum()), fit_events=int(np.nansum(fit_y)))
    out.attrs.update(fit_counts=fit_counts, population=population, purged=purge)
    return out
