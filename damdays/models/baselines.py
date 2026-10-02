"""The pre-registered baselines: simple, honest references every model must beat.

All of them learn only from the fit rows of damdays.models.rows (purged), and
only from the population being scored. For example, the B0 used to judge
dam-like dams is the base rate of dam-like dams. (The pre-event research did
the same, but fitted B0 and the B2 prior on unpurged rows; that is fixed here.)

P1, the farmer runway (one forecast at every valid look)
--------------------------------------------------------
B0    base rate: the share of fit forecasts in the same calendar month and
      region that had the event. (A month x region with fewer than 30 fit rows
      uses the region's rate.) Knows the season and the region, nothing about the dam.
B2    the dam's own track record: (past hits + k x prior) / (past forecasts + k),
      k = 20. Past forecasts count only once their answer was final
      (b2S, b2N; see damdays/features/issues.py). The prior is the fit rows'
      region x half-year (Oct-Mar or Apr-Sep) rate.
PERS  persistence: logistic regression on today's level (rel and rel squared).

P2, the season rating (one forecast per dam or cell every 1 July)
-----------------------------------------------------------------
B0    region rate (every rating is issued in July, so month x region = region).
B2    the dam's (or cell's) own past-season failure rate, k = 5, prior = region rate.
PERS  logistic regression on the 1 July level (cells: the most reliable dam's
      level and the highest level in the cell, each with its square).
RAIN  the PREREG rainfall-only score, which defines the kill rule: logistic
      regression on the 12- and 24-month rainfall deciles and the number of
      drought years in the last 10.
RAIN+ the strongest rainfall-only model found before the event (season-rating
      research): a small LightGBM on causal rain percentiles and totals, the
      drought count, the cell's rain climatology and the region. The research
      fitted it on cells; here the same recipe is also fitted on dam ratings.

Baselines may know the region (B0 is a region rate by definition). The PREREG
ban on region identifiers applies to the forecasting models, not to these references.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from damdays import config
from damdays.features.spec import PERS_INPUTS, RAIN_INPUTS, RAIN_PLUS_INPUTS
from damdays.models import rows

P_MIN, P_MAX = 1e-6, 1 - 1e-6          # keep probabilities strictly inside (0, 1)
MIN_ROWS_PER_MONTH = 30                # B0: a month x region needs this many fit rows, else the region rate
RAIN_PLUS_PARAMS = dict(               # the season-rating research's RAIN+ GBM, as found before the event
    n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=100, subsample=0.8,
    subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=0, n_jobs=3, verbose=-1,
    deterministic=True, force_row_wise=True)   # 3 threads (was 4): VAL forecasts checked bit-identical


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
def clip(p):
    """Probabilities as float64, kept strictly inside (0, 1)."""
    return np.clip(np.asarray(p, dtype=np.float64), P_MIN, P_MAX)


def group_rate(fit_keys, fit_y, keys, min_rows=1, fallback=None):
    """Event rate of the fit rows in each group, looked up for each predicted row.

    fit_keys, keys  DataFrames with the same grouping columns (fit rows, rows to predict)
    min_rows        a group with fewer fit rows than this is treated as missing
    fallback        values to use where the group is missing (default: the overall fit rate)
    """
    columns = list(fit_keys.columns)
    fit = fit_keys.assign(_y=np.asarray(fit_y, dtype=float))
    stats = fit.groupby(columns)["_y"].agg(["mean", "size"]).reset_index()
    looked_up = keys[columns].merge(stats, on=columns, how="left")
    too_few = looked_up["size"].fillna(0).to_numpy() < min_rows
    rate = np.where(too_few, np.nan, looked_up["mean"].to_numpy(dtype=float))
    if fallback is None:
        fallback = np.full(len(keys), fit["_y"].mean())
    return np.where(np.isfinite(rate), rate, fallback)


def month_region_rate(fit, fit_y, table):
    """B0: month x region rate of the fit rows; the region rate if the month has < 30 fit rows."""
    def keys(t):
        return pd.DataFrame({"month": pd.DatetimeIndex(t["issue_date"]).month,
                             "region": t["region"].astype(str).to_numpy()})
    region_only = group_rate(keys(fit)[["region"]], fit_y, keys(table)[["region"]])
    return group_rate(keys(fit), fit_y, keys(table), min_rows=MIN_ROWS_PER_MONTH, fallback=region_only)


def region_season_rate(fit, fit_y, table, season_column=None):
    """The B2 prior: region x half-year rate of the fit rows (P2: region rate, season_column=None)."""
    def keys(t):
        out = pd.DataFrame({"region": t["region"].astype(str).to_numpy()})
        if season_column is not None:
            out["season"] = t[season_column].to_numpy()
        return out
    return group_rate(keys(fit), fit_y, keys(table))


def shrunk_rate(hits, count, prior, k):
    """(hits + k x prior) / (count + k): the dam's own rate, pulled toward the prior when history is short."""
    hits, count = np.asarray(hits, dtype=float), np.asarray(count, dtype=float)
    return (hits + k * prior) / (count + k)


def with_squares(X):
    """The inputs plus the square of each (lets a logistic regression bend)."""
    return pd.concat([X, (X ** 2).add_suffix("_sq")], axis=1)


def logistic_fit_predict(X_fit, y_fit, X):
    """Logistic regression fitted on (X_fit, y_fit), predicted on X. Blanks take the fit rows' median."""
    median = X_fit.median()
    model = LogisticRegression(max_iter=5000).fit(X_fit.fillna(median).to_numpy(), np.asarray(y_fit, dtype=int))
    return model.predict_proba(X.fillna(median).to_numpy())[:, 1]


def region_columns(fit_regions, regions):
    """One 0/1 column per region seen in the fit rows (for RAIN+ only)."""
    names = sorted(pd.unique(pd.Series(fit_regions).astype(str)))
    regions = pd.Series(regions).astype(str).to_numpy()
    return pd.DataFrame({f"region_{name}": (regions == name).astype(float) for name in names})


def rain_plus_fit_predict(fit, fit_y, table, inputs=RAIN_PLUS_INPUTS):
    """RAIN+: the small rain-only LightGBM (rain features + climatology + region)."""
    def design(t):
        X = t[list(inputs)].astype(float).reset_index(drop=True)
        return pd.concat([X, region_columns(fit["region"], t["region"])], axis=1)
    X_fit, X = design(fit), design(table)
    model = lgb.LGBMClassifier(**RAIN_PLUS_PARAMS).fit(X_fit.to_numpy(), np.asarray(fit_y, dtype=int))
    return model.predict_proba(X.to_numpy())[:, 1]


# ---------------------------------------------------------------------------
# P1 baselines
# ---------------------------------------------------------------------------
def p1_baselines(table, kind, block, population, purge=True):
    """B0, B2 and PERS for every at-risk forecast of `kind` issued in `block`.

    table       the P1 table (keys + dam groups of damdays.features.store.load_p1)
    population  which dams the baselines are fitted on: "all", "dam_like" or "persistent".
                Use the population you score: dam-like rows are judged against dam-like base rates.
    Returns uid, issue_date, p_B0, p_B2, p_PERS (float64), plus the fit-row count in .attrs.
    """
    fit = table[rows.p1_fit_rows(table, kind, block, population, purge=purge)]
    fit_y = fit[rows.p1_label(kind)].to_numpy(dtype=float)
    scored = table[rows.p1_block_rows(table, kind, block)]

    b0 = month_region_rate(fit, fit_y, scored)
    prior = region_season_rate(fit, fit_y, scored, season_column="warm")
    b2 = shrunk_rate(scored[f"b2S_{kind}"], scored[f"b2N_{kind}"], prior, config.B2_SHRINK_P1)
    pers = logistic_fit_predict(with_squares(fit[PERS_INPUTS].astype(float)), fit_y,
                                with_squares(scored[PERS_INPUTS].astype(float)))

    out = pd.DataFrame({"uid": scored["uid"].astype(str).to_numpy(), "issue_date": scored["issue_date"].to_numpy(),
                        "p_B0": clip(b0), "p_B2": clip(b2), "p_PERS": clip(pers)})
    out.attrs.update(fit_rows=len(fit), fit_events=int(fit_y.sum()), population=population, purged=purge)
    return out


# ---------------------------------------------------------------------------
# P2 baselines
# ---------------------------------------------------------------------------
def p2_track_record_columns(task):
    """The past-season counts B2 uses: (hits, count) columns for the task's label."""
    return ("b2S_g", "b2N_g") if task == "P2_dam_g" else ("b2S", "b2N")


CELL_PERS_INPUTS = ["best_rel", "rel_max"]


def add_best_dam_level(cells, dams):
    """Add best_rel to the cell table: the 1 July level of each cell's most reliable dam (for cell PERS)."""
    best = dams[["uid", "season", "rel"]].rename(columns={"uid": "best_uid", "rel": "best_rel"})
    out = cells.merge(best, on=["best_uid", "season"], how="left")
    if len(out) != len(cells):
        raise AssertionError("Joining the best dam's level changed the number of cell rows.")
    return out


def p2_baselines(table, task, block, population="all", pers_inputs=PERS_INPUTS):
    """B0, B2, PERS, RAIN and RAIN+ for every season rating issued in `block`.

    table        the P2 dam table, or the cell table (for P2_cell, with the level columns in pers_inputs)
    task         P2_dam, P2_dam_g or P2_cell (decides the label and the track-record columns)
    population   "dam_like" for dam ratings (the PREREG population); "all" for cells (all cells are dam-like)
    pers_inputs  level columns for PERS (dams: rel; cells: best_rel and rel_max)
    """
    label = rows.P2_LABELS[task]
    fit = table[rows.p2_fit_rows(table, label, block, population)]
    fit_y = fit[label].to_numpy(dtype=float)
    scored = table[rows.p2_block_rows(table, block)]

    b0 = month_region_rate(fit, fit_y, scored)
    prior = region_season_rate(fit, fit_y, scored)
    hits, count = p2_track_record_columns(task)
    b2 = shrunk_rate(scored[hits], scored[count], prior, config.B2_SHRINK_P2)
    pers = logistic_fit_predict(with_squares(fit[list(pers_inputs)].astype(float)), fit_y,
                                with_squares(scored[list(pers_inputs)].astype(float)))
    rain = logistic_fit_predict(fit[RAIN_INPUTS].astype(float), fit_y, scored[RAIN_INPUTS].astype(float))
    rain_plus = rain_plus_fit_predict(fit, fit_y, scored)

    out = pd.DataFrame({"uid": scored["uid"].astype(str).to_numpy(), "issue_date": scored["issue_date"].to_numpy(),
                        "p_B0": clip(b0), "p_B2": clip(b2), "p_PERS": clip(pers),
                        "p_RAIN": clip(rain), "p_RAIN+": clip(rain_plus)})
    out.attrs.update(fit_rows=len(fit), fit_events=int(fit_y.sum()), population=population)
    return out
