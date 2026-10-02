"""Uncertainty: the DamDays floor (LB90) and the season band.

Two products tell a farmer or a lender how far to trust a forecast. Neither
changes any probability; both are shown next to it. docs/SCORECARD.md
(section 4) explains how they are judged, and damdays.evaluation.coverage
does the judging.

1. The DamDays floor: "at least N days above a third, 90% confidence"
---------------------------------------------------------------------
* Answer: T = days from the forecast to the start of the next R30 event (the
  dam below a third of full), capped at 365 days ("no event within a year").
  An R30 event is the PREREG one: it needs the dam to have refilled to 60%
  of full within the previous 180 days ("armed"). A fall below a third
  without that refill is not an event, so the floor promises "no R30 event
  before day N", which is slightly weaker than "above a third for N days".
  (Reviewer check on VAL: judged on any confirmed fall below a third,
  armed or not, the same floors hold 0.866 of the time, primary set 0.881.)
* Model: a LightGBM 10% quantile regression of log(1 + T) on the 29 G2
  features (damdays.features.spec). Its output q10 reads: "in 9 cases out of
  10 like this one, the dam stayed above a third for at least exp(q10) - 1 days".
* Split conformal: on a separate calibration set, measure how far q10
  overshot each answer (score s = q10 - log(1 + T)), take the 90% conformal
  quantile c of those scores, and lower every floor by it:
      floor N = exp(q10 - c) - 1 days   (kept between 0 and 365).
  If new forecasts behave like the calibration set, at least 90% of floors
  hold, whatever the quantile model's mistakes (split conformal prediction).
* Display: whole days, rounded down; a floor of 180 days or more reads "180+".

2. The season band
------------------
All dams in a region share the weather, so a whole region-year can run
wetter or drier than any model expects. A region-year's "offset" is the shift
in log-odds that would have made that year's forecasts right on average
(calibration-in-the-large; damdays.evaluation.region_year_offsets). The band
around a forecast p is

    [sigmoid(logit p + lowest offset), sigmoid(logit p + highest offset)]

with the offsets taken from an INNER BACKTEST: the same model recipe fitted
at an earlier cutoff and scored on a block whose answers were all known
before the real cutoff. It works for any model's probabilities (G2 in
scripts/07 as a stand-in; Tidemark's own band, from its inner backtest with
the frailty and the max rule, is built by damdays.models.tidemark.fit_band
with these same functions). PREREG: the band pools two inner blocks,

    2002-2009  model fitted on answers final before 2002-01-01, scoring
               issues 2002-01-01 to 2008-12-31 answered before 2009-01-01
    2009-2016  model fitted on answers final before 2009-01-01 (the VAL fit),
               scoring issues 2009-01-01 to 2016-06-30 answered before 2016-07-01

and the pooled band is used for TEST and the sealed region. For VAL itself
only the 2002-2009 block existed in time, so VAL is checked with that block alone.

Time rules in this module (no peeking)
--------------------------------------
* A floor answer T looks up to 365 days ahead, and an event that starts on
  day 365 is confirmed by a second look up to 30 days later. So T is final
  only 395 days after the forecast. A forecast is used to fit or calibrate
  the floor only if its 395 days closed before the cutoff.
* A 90-day probability is final 90 + 30 = 120 days after the forecast
  (damdays.data.splits.answer_known_before), as for every P1 model.
* A model fitted at an inner cutoff must not know anything from after that
  cutoff. The stored dam_rate_K feature shrinks toward a regional rate from
  answers final before 2009-01-01; for the 2002 inner fit that rate is
  recomputed from answers final before 2002-01-01 (dam_rate_as_of).
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import answer_known_before
from damdays.evaluation import band_from_offsets, region_year_offsets
from damdays.evaluation.metrics import logit, sigmoid
from damdays.evaluation.rules import is_octmar
from damdays.features import spec
from damdays.models import g2, rows

MAX_THREADS = 3                      # CPU cap for every LightGBM fit in this module
P_MIN, P_MAX = 1e-6, 1 - 1e-6

# ---------------------------------------------------------------------------
# DamDays floor settings (pre-event research: calibration-uncertainty family)
# ---------------------------------------------------------------------------
FLOOR_KIND = "R30"                                   # the floor is about falling below a third
FLOOR_CAP_DAYS = 365                                 # T is capped at one year
FLOOR_ANSWER_FINAL_DAYS = FLOOR_CAP_DAYS + config.PURGE_DAYS   # 395: when a capped answer is final
FLOOR_MISS_RATE = 0.10                               # promise: at most 10% of floors fail (90% target)
FLOOR_DISPLAY_MAX_DAYS = 180                         # floors of 180 days or more are shown as "180+"
LOG_CAP = float(np.log1p(FLOOR_CAP_DAYS))            # the cap on the log(1 + days) scale
FLOOR_PARAMS = dict(                                 # the pre-event quantile-model settings
    objective="quantile", alpha=FLOOR_MISS_RATE, n_estimators=250, learning_rate=0.06, num_leaves=31,
    min_child_samples=100, subsample=0.5, subsample_freq=1, colsample_bytree=0.8, random_state=0,
    verbose=-1, n_jobs=MAX_THREADS, deterministic=True, force_row_wise=True)

# ---------------------------------------------------------------------------
# Season band settings
# ---------------------------------------------------------------------------
# Inner blocks per setting: (first issue date, cutoff). The model for a block is
# fitted on answers final before the first issue date; the block's offsets use
# issues from that date whose answers were final before the cutoff.
BAND_INNER_BLOCKS = {
    "VAL": [("2002-01-01", "2009-01-01")],
    "TEST": [("2002-01-01", "2009-01-01"), ("2009-01-01", "2016-07-01")],
}


# ===========================================================================
# 1. The DamDays floor
# ===========================================================================
def floor_features():
    """The floor model's inputs: the 29 G2 features for R30 (labels and forbidden columns are refused)."""
    return spec.check_feature_list(spec.p1_tree_features(FLOOR_KIND))


def runway_days(table):
    """T: days to the next R30 start, capped at 365. No later event in the archive counts as 365.

    Only meaningful where the answer is final (runway_answer_final): before
    then, "no event seen yet" does not mean "no event within a year".
    """
    days = table[f"lab_tte_{FLOOR_KIND}"].to_numpy(dtype=float)
    return np.minimum(np.where(np.isnan(days), FLOOR_CAP_DAYS, days), FLOOR_CAP_DAYS)


def runway_answer_final(issue_dates, cutoff):
    """True where the capped answer T was final before `cutoff`: issue + 395 days < cutoff.

    TIME: T looks 365 days ahead, plus 30 days for a second look to confirm
    an event that starts on day 365.
    """
    dates = pd.DatetimeIndex(pd.to_datetime(issue_dates))
    return np.asarray(dates + pd.Timedelta(days=FLOOR_ANSWER_FINAL_DAYS) < pd.Timestamp(cutoff))


def floor_fit_rows(table, cutoff=config.VAL_START):
    """Forecasts the floor model may learn from, for use after `cutoff`.

    At risk of R30 and label determinable (the same rows every P1 model uses,
    and the rows the pre-event research used), and the capped answer final
    before the cutoff. For the VAL cutoff (2009-01-01) these are TRAIN issues
    up to early December 2007.
    """
    return (runway_answer_final(table["issue_date"], cutoff)
            & table[rows.p1_at_risk_column(FLOOR_KIND)].to_numpy(dtype=bool)
            & table["label_ok"].to_numpy(dtype=bool))


def fit_floor_model(table, cutoff=config.VAL_START, max_rows=None, seed=0):
    """Fit the 10% quantile of log(1 + T). Returns (model, info).

    max_rows  optional seeded random subsample of the fit rows. The pre-event
              research used 300,000 rows to save time on a shared machine;
              the event build uses every row (max_rows=None).
    """
    fit = np.flatnonzero(floor_fit_rows(table, cutoff))
    available = len(fit)
    if max_rows is not None and available > max_rows:
        fit = np.sort(np.random.default_rng(seed).choice(fit, size=max_rows, replace=False))
    picked = table.iloc[fit]
    X = picked[floor_features()].to_numpy(dtype=np.float64)
    target = np.log1p(runway_days(picked))
    model = lgb.LGBMRegressor(**FLOOR_PARAMS).fit(X, target)
    info = dict(cutoff=str(cutoff), fit_rows=len(fit), fit_rows_available=available,
                share_no_event_within_365=float(np.mean(target >= LOG_CAP - 1e-12)),
                first_issue=str(picked["issue_date"].min().date()), last_issue=str(picked["issue_date"].max().date()))
    return model, info


def predict_log_q10(model, table, mask):
    """The model's 10% quantile of log(1 + T) for the rows in `mask`, kept inside [0, log(366)]."""
    X = table.loc[mask, floor_features()].to_numpy(dtype=np.float64)
    return np.clip(model.predict(X), 0.0, LOG_CAP)


def conformity_scores(log_q10, days):
    """How far q10 overshot each answer, in log days: s = q10 - log(1 + T).

    s > 0 means the dam fell below a third sooner than q10 said.
    """
    return np.asarray(log_q10, dtype=float) - np.log1p(np.asarray(days, dtype=float))


def conformal_shift(scores, miss_rate=FLOOR_MISS_RATE):
    """The split-conformal correction c: the ceil((n + 1) x (1 - miss_rate))-th smallest score.

    Lowering every floor by c means that, for a new forecast exchangeable
    with the n calibration forecasts, the floor fails with probability at
    most miss_rate (the "+1" is the finite-sample correction).
    """
    ordered = np.sort(np.asarray(scores, dtype=float))
    n = len(ordered)
    if n == 0:
        raise ValueError("No calibration rows for the conformal shift.")
    k = int(np.ceil((n + 1) * (1 - miss_rate)))
    return float(ordered[min(k, n) - 1])


def floor_days(log_q10, shift):
    """The floor N = exp(q10 - c) - 1 days, kept between 0 and 365 (shift: one number, or one per row)."""
    return np.expm1(np.clip(np.asarray(log_q10, dtype=float) - shift, 0.0, LOG_CAP))


def displayed_floor_days(floor):
    """What the app shows, as a number: whole days rounded down (the cautious way), 180 meaning "180+"."""
    return np.minimum(np.floor(np.asarray(floor, dtype=float)), FLOOR_DISPLAY_MAX_DAYS)


def floor_label(days):
    """The floor as text for one forecast: "180+ days" when N >= 180, otherwise e.g. "45 days"."""
    if days >= FLOOR_DISPLAY_MAX_DAYS:
        return f"{FLOOR_DISPLAY_MAX_DAYS}+ days"
    shown = int(np.floor(days))
    return f"{shown} day" if shown == 1 else f"{shown} days"


def shift_from_answers_before(log_q10, days, issue_dates, cutoff, miss_rate=FLOOR_MISS_RATE):
    """The conformal shift from calibration forecasts whose capped answer was final before `cutoff`.

    TIME: this is the shift to freeze for forecasts issued from `cutoff` on.
    For TEST (from 2016-07-01) only VAL forecasts issued before about
    2 June 2015 qualify: later ones were still being answered in July 2016.
    Returns (shift, number of calibration rows).
    """
    usable = runway_answer_final(issue_dates, cutoff)
    scores = conformity_scores(np.asarray(log_q10)[usable], np.asarray(days)[usable])
    return conformal_shift(scores, miss_rate), int(usable.sum())


def leave_one_year_out_shifts(log_q10, days, years, miss_rate=FLOOR_MISS_RATE):
    """One conformal shift per July-June year, each calibrated on the OTHER years of the block only.

    The pre-event research's check (cross-conformal by year): a year's floors
    never use that year's own answers, but they do use later years, so it is
    a check of the method, not a forecast made in real time
    (forward_split_floors is the real-time version). Returns {year: shift}.
    """
    scores = conformity_scores(log_q10, days)
    years = np.asarray(years)
    return {int(year): conformal_shift(scores[years != year], miss_rate) for year in np.unique(years)}


def shifts_for_rows(years, shifts):
    """Each row's shift, looked up by its July-June year."""
    return np.array([shifts[int(year)] for year in np.asarray(years)], dtype=float)


def forward_split_floors(log_q10, days, issue_dates, split_date, miss_rate=FLOOR_MISS_RATE):
    """The real-time check: calibrate on forecasts answered before `split_date`, floor the ones issued after.

    Returns (floors for the later forecasts, mask of those forecasts, shift, calibration rows).
    """
    later = np.asarray(pd.DatetimeIndex(pd.to_datetime(issue_dates)) >= pd.Timestamp(split_date))
    shift, n_calibration = shift_from_answers_before(log_q10, days, issue_dates, split_date, miss_rate)
    return floor_days(np.asarray(log_q10)[later], shift), later, shift, n_calibration


def followup_days(issue_dates, data_end):
    """Days after each forecast in which a fall below a third would show up in the archive.

    The scorecard judges a floor of N days only if this follow-up is at least N.
    TIME: an R30 start is only recorded once a second look confirms it, up to
    30 days later. A start in the archive's last 30 days can therefore be
    missing, so the dam counts as watched only up to (data end - 30 days).
    Without this, a forecast issued near the data end could count as "held"
    when the dam had in fact started to fall below a third (TEST only: every
    VAL forecast has at least 10 years of follow-up).
    """
    dates = pd.DatetimeIndex(pd.to_datetime(issue_dates))
    last_confirmable_start = pd.Timestamp(data_end) - pd.Timedelta(days=config.PURGE_DAYS)
    return np.asarray((last_confirmable_start - dates).days, dtype=float)


# ===========================================================================
# 2. The season band
# ===========================================================================
def answered_fit_rows(table, kind, cutoff):
    """P1 rows a model fitted at `cutoff` may learn from: answer final before it (issue + 120 days < cutoff),
    at risk, label determinable and known. Equal to rows.p1_fit_rows(table, kind, "VAL") at 2009-01-01."""
    label = rows.p1_label(kind)
    return (answer_known_before(table["issue_date"], cutoff)
            & table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)
            & table["label_ok"].to_numpy(dtype=bool)
            & table[label].notna().to_numpy())


def dam_rate_as_of(table, kind, cutoff):
    """dam_rate_K as a model fitted at `cutoff` would know it.

    dam_rate_K = (b2S_K + 20 x prior) / (b2N_K + 20). The dam's own counts
    b2S/b2N are causal already. The stored prior is the region x half-year
    rate of answers final before 2009-01-01; here it is recomputed from
    answers final before `cutoff`.
    TIME: a model fitted at 2002-01-01 must not know the 2002-2008 answers
    inside the stored prior. (The 1986-87 warm-up looks, which the stored
    prior also counts, are not issues in the P1 table and are left out.)
    """
    k = config.B2_SHRINK_P1
    answered = answered_fit_rows(table, kind, cutoff)
    label = table[rows.p1_label(kind)].to_numpy(dtype=float)
    region = table["region"].astype(str).to_numpy()
    warm = table["warm"].to_numpy(dtype=bool)
    prior = np.full(len(table), np.nan)
    for name in np.unique(region):
        for half in (True, False):
            group = (region == name) & (warm == half)
            prior[group] = label[answered & group].mean()
    hits, count = table[f"b2S_{kind}"].to_numpy(dtype=float), table[f"b2N_{kind}"].to_numpy(dtype=float)
    return ((hits + k * prior) / (count + k)).astype(np.float32)


def fit_predict_g2_at(table, kind, cutoff, predict_mask, dam_rate=None):
    """The G2 recipe (damdays.models.g2) fitted on answers final before `cutoff`; predicts the rows in predict_mask.

    dam_rate  optional replacement for the dam_rate_K column (one value per
              table row), e.g. dam_rate_as_of(table, kind, cutoff).
    Returns (p for the predicted rows as float64, info dict).
    """
    features = g2.g2_features(kind)
    fit = answered_fit_rows(table, kind, cutoff)
    # np.array(...) makes writable copies: with pandas copy-on-write, to_numpy() can hand back a
    # read-only view (e.g. on a consolidated table), and the dam_rate column is overwritten below.
    X_fit = np.array(table.loc[fit, features], dtype=np.float64)
    X = np.array(table.loc[predict_mask, features], dtype=np.float64)
    if dam_rate is not None:
        column = features.index(f"dam_rate_{kind}")
        X_fit[:, column], X[:, column] = dam_rate[fit], dam_rate[np.asarray(predict_mask)]
    y_fit = table.loc[fit, rows.p1_label(kind)].to_numpy(dtype=int)
    model = lgb.LGBMClassifier(**dict(g2.G2_PARAMS, n_jobs=MAX_THREADS)).fit(X_fit, y_fit)
    p = np.clip(model.predict_proba(X)[:, 1].astype(np.float64), P_MIN, P_MAX)
    info = dict(kind=kind, cutoff=str(cutoff), fit_rows=int(fit.sum()), fit_events=int(y_fit.sum()),
                predicted_rows=int(np.sum(predict_mask)), dam_rate="as of cutoff" if dam_rate is not None else "stored")
    return p, info


def band_rows(table, kind, start, cutoff):
    """Rows whose offsets form one band block: the primary set, issued from `start`, answered before `cutoff`.

    Primary set = dam-like, issued October to March, at risk (the
    pre-registered headline set), with a determinable and known label.
    TIME: issue + 120 days < cutoff, so every answer was final before the cutoff.
    """
    dates = table["issue_date"]
    return (np.asarray(pd.to_datetime(dates) >= pd.Timestamp(start))
            & answer_known_before(dates, cutoff)
            & table["dam_like"].to_numpy(dtype=bool)
            & is_octmar(dates)
            & table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)
            & table["label_ok"].to_numpy(dtype=bool)
            & table[rows.p1_label(kind)].notna().to_numpy())


def block_offsets(y, p, region, issue_date, block=""):
    """One row per region and July-June year with its log-odds offset (the scorecard's region_year_offsets)."""
    offsets = region_year_offsets(y, p, region, issue_date)
    offsets.insert(0, "block", block)
    return offsets


def pooled_band(*offset_tables):
    """The band [lowest, highest] offset over the usable region-years of one or more blocks."""
    return band_from_offsets(pd.concat(offset_tables, ignore_index=True))


def band_probabilities(p, band):
    """The season band around each forecast: (sigmoid(logit p + low), sigmoid(logit p + high))."""
    z = logit(p)
    low, high = band
    return sigmoid(z + low), sigmoid(z + high)


def leave_one_year_out_band_coverage(eval_offsets, extra_offsets=None):
    """Each year's region-years judged against a band built WITHOUT that year.

    The band for July-June year Y pools the usable offsets of every other
    year in eval_offsets, plus extra_offsets (for example the 2002-2009
    inner block). Like the floor's leave-one-year-out check, it uses later
    years too, so it checks the method rather than a real-time forecast.
    """
    used = eval_offsets[eval_offsets["used"]]
    extra = extra_offsets[extra_offsets["used"]] if extra_offsets is not None else used.iloc[:0]
    covered, missed = 0, {}
    for _, row in used.iterrows():
        others = pd.concat([extra, used[used["hydro_year"] != row["hydro_year"]]], ignore_index=True)
        low, high = others["offset"].min(), others["offset"].max()
        if low <= row["offset"] <= high:
            covered += 1
        else:
            missed[row["region_year"]] = dict(offset=row["offset"], band=[low, high])
    return dict(region_years=len(used), covered=covered,
                coverage=covered / len(used) if len(used) else np.nan, missed=missed)
