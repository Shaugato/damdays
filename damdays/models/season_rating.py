"""P2, the season rating for lenders: will a farm dam (or a 2 km cell) run dry this summer?

The question
------------
Issued every 1 July of season year Y. Will the dam go fully dry (a D0 event
starts) between 1 October Y and 31 March Y+1? The 2 km cell version asks
whether EVERY dam-like dam in the cell goes dry (PREREG).

The recipe (PREREG "Model", P2; fixed before the event)
-------------------------------------------------------
1. Start from the dam's own track record, the B2 baseline:
       B2 = (dry seasons so far + 5 x prior) / (seasons with a known answer so far + 5)
   prior = share of the dam-like fit seasons that went dry, per region.
2. A small LightGBM is "boosted from" logit(B2): B2 is its starting point
   (LightGBM's init_score), so the trees only learn a CORRECTION to it.
   150 trees, learning rate 0.03, 7 leaves, at least 200 seasons per leaf,
   80% row and column sampling. Three seeds; their probabilities are averaged.
3. It learns from dam-like seasons only. Inputs: the "HSN" set of the
   pre-event research (own History, Shape, 1 July State, Neighbours), see
   season_features(). No rain features and no region identifier.
4. Cell p = product of its dam-like dams' p (the cell fails only if all of
   them fail; the dams are treated as independent).
5. Gradual label (a real dry-out, not a sudden satellite glitch): the SAME
   trees, with the starting point swapped to logit(B2 of gradual dry-outs).
The regional dam-state block (reg_zero / reg_anom / reg_pct) explored before
the event is dropped (PREREG, a TEST-informed simplification).

Why boost from B2? (pre-event research, VAL)
--------------------------------------------
Training seasons (1989-2008) have short track records (0 to 19 earlier
seasons); validation and test dams have 20 or more. Trees cannot extrapolate
"what a long record means", but B2's shrinkage formula can. Starting from B2
lets the trees add only what the record does not already say.

The time rules
--------------
* A rating issued 1 July Y only uses information from before 1 July Y. The
  state features come from the last look before 1 July (at most 60 days old);
  see damdays/features/season.py.
* A season's answer is final by 30 April of the next year (window ends 31
  March, plus 30 days to confirm an event), so every EARLIER season's answer
  is known on 1 July. The track record and the area index use only those.
* A model judged on a block learns only from seasons answered before that
  block's first rating (damdays.models.rows.p2_fit_rows checks this).

The area index (built here, part of the reference HSN set)
----------------------------------------------------------
"N" in HSN includes, besides the neighbour levels R_anom / R_chg3 / R_zero, a
dam-based regional failure index: how many waterbodies within 10 or 25 km
went dry LAST season, and over ALL earlier seasons. See area_index().
Disclosed: the waterbody pool (has_hist) and the dam-like flag of the
dam-like-only version are chosen from pre-2016 looks, as for R_zero. For a
2009-2015 rating this leaves out a few waterbodies an observer then could not
yet rule out; TEST and the sealed region are not affected.
"""
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree

from damdays import config
from damdays.evaluation.metrics import logit, sigmoid
from damdays.features import spec
from damdays.models import rows

# The frozen P2 settings (PREREG). The last three lines only cap CPU use and make runs repeatable.
P2_PARAMS = dict(
    n_estimators=150, learning_rate=0.03, num_leaves=7, min_child_samples=200,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
    verbose=-1, n_jobs=3, deterministic=True, force_row_wise=True)
SEEDS = (0, 1, 2)
K_SHRINK = config.B2_SHRINK_P2            # k = 5
P_MIN, P_MAX = 1e-5, 1 - 1e-5             # dam probabilities are kept inside this range

# ---------------------------------------------------------------------------
# Area index: the regional failure index of the reference HSN set
# ---------------------------------------------------------------------------
AREA_MIN_LAST = 3      # "last season" share needs at least 3 nearby waterbodies with a known answer
AREA_MIN_LONG = 10     # "long run" share needs at least 10 nearby waterbody-seasons with a known answer
AREA_INDEX = [
    # (column, radius in km, which nearby waterbodies count, which seasons)   pre-event name
    ("area10_dry_last", 10, "all", "last"),                     # reg10_all_lag1
    ("area10_dry_longrun", 10, "all", "longrun"),               # reg10_all_rate
    ("area25_dry_last", 25, "all", "last"),                     # reg25_all_lag1
    ("area25_dry_longrun", 25, "all", "longrun"),               # reg25_all_rate
    ("area25_damlike_dry_last", 25, "dam_like", "last"),        # reg25_dl_lag1
    ("area25_damlike_dry_longrun", 25, "dam_like", "longrun"),  # reg25_dl_rate
]
AREA_INDEX_COLUMNS = [column for column, *_ in AREA_INDEX]


def season_features(with_area_index=True):
    """The model inputs: spec.P2_FEATURE_SPEC (own history, shape, 1 July state, neighbour levels),
    plus the area index. Refuses labels and forbidden columns."""
    columns = list(spec.P2_FEATURE_SPEC) + (AREA_INDEX_COLUMNS if with_area_index else [])
    return spec.check_feature_list(columns)


def season_grid(dams, label):
    """The label as a waterbody x season grid: 1 dry, 0 not dry, NaN where the answer is not known.

    Also returns, for every table row, its row and column in the grid.
    Every waterbody must have one row for every season (a full grid).
    """
    uids = np.sort(dams["uid"].astype(str).unique())
    seasons = np.sort(dams["season"].unique())
    if not (np.diff(seasons) == 1).all():
        raise AssertionError("Seasons must be consecutive years.")
    grid_row = pd.Series(np.arange(len(uids)), index=uids).loc[dams["uid"].astype(str)].to_numpy()
    grid_col = (dams["season"].to_numpy() - seasons[0]).astype(int)
    if len(dams) != len(uids) * len(seasons) or pd.Series(grid_row * len(seasons) + grid_col).duplicated().any():
        raise AssertionError("The area index needs exactly one row per waterbody and season.")
    known = dams["label_ok"].to_numpy(dtype=bool) & dams[label].notna().to_numpy()
    grid = np.full((len(uids), len(seasons)), np.nan)
    grid[grid_row[known], grid_col[known]] = dams[label].to_numpy(dtype=float)[known]
    return grid, uids, grid_row, grid_col


def previous_season(values):
    """Each season's column holds the PREVIOUS season's values (the first season gets 0)."""
    out = np.zeros_like(values)
    out[:, 1:] = values[:, :-1]
    return out


def all_earlier_seasons(values):
    """Each season's column holds the sum over ALL EARLIER seasons (not the season itself)."""
    running = np.cumsum(values, axis=1)
    return running - values


def neighbour_matrix(x_m, y_m, radius_km, counts=None):
    """Sparse 0/1 matrix: (i, j) = 1 when waterbody j lies within radius_km of waterbody i.

    A waterbody is never its own neighbour. counts (bool per waterbody), if
    given, keeps only neighbours j with counts[j] True (e.g. dam-like ones).
    """
    pairs = cKDTree(np.c_[x_m, y_m]).query_pairs(radius_km * 1000.0, output_type="ndarray")
    i = np.r_[pairs[:, 0], pairs[:, 1]]
    j = np.r_[pairs[:, 1], pairs[:, 0]]
    if counts is not None:
        keep = np.asarray(counts, dtype=bool)[j]
        i, j = i[keep], j[keep]
    n = len(x_m)
    return csr_matrix((np.ones(len(i)), (i, j)), shape=(n, n))


def nearby_share(neighbours, dry, known, min_known):
    """Share of nearby (waterbody, season) answers that were "dry"; NaN if fewer than min_known answers."""
    n_dry = neighbours @ dry
    n_known = neighbours @ known
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n_known >= min_known, n_dry / n_known, np.nan)


def area_index(dams, attrs, label="y"):
    """The area index for every row of the P2 dam table (a DataFrame with AREA_INDEX_COLUMNS, same order).

    For a rating issued 1 July of season Y, using the other waterbodies in the
    table within 10 or 25 km (never the dam itself):
      *_last     share of them that went dry in season Y-1 (needs 3 known answers)
      *_longrun  share of all their seasons before Y that went dry (needs 10 known answers)
    Time rule: season Y-1's window closed on 31 March Y and its events were
    confirmed by 30 April Y, so on 1 July Y every answer used here was final.
    """
    grid, uids, grid_row, grid_col = season_grid(dams, label)
    where = attrs.set_index(attrs["uid"].astype(str)).loc[uids]
    known = np.isfinite(grid).astype(float)
    dry = np.where(known > 0, grid, 0.0)
    # Season Y may use season Y-1 ("last") and every season before Y ("longrun"), never Y itself.
    seasons_used = {"last": (previous_season(dry), previous_season(known), AREA_MIN_LAST),
                    "longrun": (all_earlier_seasons(dry), all_earlier_seasons(known), AREA_MIN_LONG)}

    out = {}
    matrices = {}
    for column, radius_km, pool, which in AREA_INDEX:
        if (radius_km, pool) not in matrices:
            counts = where["dam_like"].to_numpy(dtype=bool) if pool == "dam_like" else None
            matrices[(radius_km, pool)] = neighbour_matrix(
                where["x_albers"].to_numpy(dtype=float), where["y_albers"].to_numpy(dtype=float), radius_km, counts)
        dry_used, known_used, min_known = seasons_used[which]
        share = nearby_share(matrices[(radius_km, pool)], dry_used, known_used, min_known)
        out[column] = share[grid_row, grid_col]
    return pd.DataFrame(out, index=dams.index)


def add_area_index(dams, attrs):
    """A copy of the P2 dam table with the area index columns added."""
    return pd.concat([dams.drop(columns=AREA_INDEX_COLUMNS, errors="ignore"), area_index(dams, attrs)], axis=1)


# ---------------------------------------------------------------------------
# The starting point: B2, the dam's own shrunk past-season rate
# ---------------------------------------------------------------------------
def b2_rate(dams, label, block):
    """B2 for every row: (past dry seasons + 5 x prior) / (past known seasons + 5).

    label  "y" (any dry-out) or "y_g" (gradual dry-outs); the matching past
           counts are b2S/b2N or b2S_g/b2N_g (earlier seasons only, see features/season.py)
    prior  share of the fit seasons that went dry, per region and population
           (dam-like or not). Only seasons answered before the block starts are used.
    For dam-like rows this is exactly the B2 baseline of damdays.models.baselines.
    """
    hits, count = ("b2S_g", "b2N_g") if label == "y_g" else ("b2S", "b2N")
    fit = dams.loc[rows.p2_fit_rows(dams, label, block, "all"), ["region", "dam_like", label]]
    # Labels are stored as float32; average them in float64, exactly as the step 3 B2 baseline does.
    prior_table = fit.astype({label: np.float64}).groupby(["region", "dam_like"])[label].mean()
    keys = pd.MultiIndex.from_arrays([dams["region"].astype(str), dams["dam_like"].astype(bool)])
    prior = prior_table.reindex(keys).to_numpy(dtype=float)
    if np.isnan(prior).any():
        raise AssertionError("A region x population group has no fit seasons for the B2 prior.")
    return (dams[hits].to_numpy(dtype=float) + K_SHRINK * prior) / (dams[count].to_numpy(dtype=float) + K_SHRINK)


# ---------------------------------------------------------------------------
# Fitting and predicting
# ---------------------------------------------------------------------------
VARIANTS = {
    "main": dict(offset=True, area_index=True, population="dam_like",
                 about="PREREG P2: LightGBM boosted from logit(B2), HSN inputs, dam-like seasons, 3 seeds"),
    # VAL-only ablations (each changes one thing), to show why each part is there.
    "no_area_index": dict(offset=True, area_index=False, population="dam_like",
                          about="main without the area index (inputs = spec.P2_FEATURE_SPEC only)"),
    "plain": dict(offset=False, area_index=True, population="dam_like",
                  about="main without the B2 starting point (a plain LightGBM)"),
    "all_waterbodies": dict(offset=True, area_index=True, population="all",
                            about="main trained on the seasons of all has_hist waterbodies"),
}


def fit_trees(X, y, offset, seeds=SEEDS):
    """One LightGBM per seed. With an offset, each starts from it (init_score) and learns a correction."""
    models = []
    for seed in seeds:
        model = lgb.LGBMClassifier(**dict(P2_PARAMS, random_state=seed))
        if offset is None:
            model.fit(X, y)
        else:
            model.fit(X, y, init_score=offset)
        models.append(model)
    return models


def tree_scores(models, X):
    """Each seed's tree output in log-odds (without any starting point): shape (seeds, rows)."""
    return np.stack([model.predict(X, raw_score=True) for model in models])


def probability(scores, offset):
    """Average over seeds of sigmoid(trees + starting point), kept inside [P_MIN, P_MAX]."""
    start = 0.0 if offset is None else offset
    return np.clip(sigmoid(scores + start).mean(axis=0), P_MIN, P_MAX)


def feature_gain(models, features):
    """Share of the total split gain per feature, averaged over seeds (largest first)."""
    gains = np.mean([m.booster_.feature_importance("gain") for m in models], axis=0)
    return (pd.Series(gains, index=features) / gains.sum()).sort_values(ascending=False)


def fit_rating(dams, block, variant="main"):
    """Fit one variant on the seasons answered before `block`. Returns (fitted, info).

    dams    the P2 dam table with the area index (add_area_index)
    fitted  what predict_rating needs: the variant, its input columns and one LightGBM per seed
    """
    settings = VARIANTS[variant]
    features = season_features(settings["area_index"])
    fit = rows.p2_fit_rows(dams, "y", block, settings["population"])
    start_y = logit(b2_rate(dams, "y", block)) if settings["offset"] else None
    X_fit = dams.loc[fit, features].to_numpy(dtype=np.float64)
    y_fit = dams.loc[fit, "y"].to_numpy(dtype=int)
    models = fit_trees(X_fit, y_fit, None if start_y is None else start_y[fit])
    fitted = dict(variant=variant, block=block, features=features, models=models)
    info = dict(variant=variant, about=settings["about"], block=block, population=settings["population"],
                fit_seasons=int(fit.sum()), fit_dry=int(y_fit.sum()),
                features=features, n_features=len(features), seeds=list(SEEDS), params=P2_PARAMS,
                top_features_by_gain=feature_gain(models, features).head(10).round(4).to_dict())
    return fitted, info


def predict_rating(fitted, dams, block):
    """Every dam-like season rated in `block`, from a fitted rating (fit_rating).

    One row per dam-like season (with or without a known answer, so cells can
    be built), with p (any dry-out) and p_g (gradual: the same trees, started
    from the gradual B2). For a variant without the B2 start, p_g equals p.
    The B2 start is recomputed from `dams` itself: its prior comes from that
    table's own seasons answered before the block (for the sealed region: its
    own history, as the PREREG requires).
    """
    settings = VARIANTS[fitted["variant"]]
    features = fitted["features"]
    scored = rows.p2_block_rows(dams, block) & dams["dam_like"].to_numpy(dtype=bool)
    start_y = logit(b2_rate(dams, "y", block)) if settings["offset"] else None
    start_g = logit(b2_rate(dams, "y_g", block)) if settings["offset"] else None

    scores = tree_scores(fitted["models"], dams.loc[scored, features].to_numpy(dtype=np.float64))
    out = dams.loc[scored, ["uid", "issue_date", "season", "region", "hex_id", "dam_like", "persistent",
                            "label_ok", "y", "y_g"]].reset_index(drop=True)
    out["uid"] = out["uid"].astype(str)
    out["p"] = probability(scores, None if start_y is None else start_y[scored])
    out["p_g"] = probability(scores, None if start_g is None else start_g[scored])
    if settings["offset"]:
        out["p_start"] = np.clip(sigmoid(start_y[scored]), P_MIN, P_MAX)      # B2 alone, for checks
        out["p_start_g"] = np.clip(sigmoid(start_g[scored]), P_MIN, P_MAX)
    return out


def fit_and_predict(dams, block, variant="main"):
    """Fit one variant on the seasons answered before `block`; predict every dam-like season in `block`.

    Returns (predictions, info): see predict_rating and fit_rating.
    """
    started = time.time()
    fitted, info = fit_rating(dams, block, variant)
    out = predict_rating(fitted, dams, block)
    info.update(predicted_seasons=len(out), seconds=round(time.time() - started, 1))
    return out, info


# ---------------------------------------------------------------------------
# From dams to 2 km cells
# ---------------------------------------------------------------------------
def cell_probability(dam_preds, cells, column="p", how="product"):
    """P(the cell fails) for every cell-season in `cells`, from its dam-like dams' probabilities.

    how  "product" (PREREG: all dams must fail, treated as independent),
         "min" (the cell is only as likely to fail as its safest dam), or
         "best" (the cell's most reliable dam alone; best_uid in the cell table).
    Every cell must find all of its dams (n_dams of them).
    """
    keys = ["hex_id", "season"]
    if how == "best":
        best = dam_preds[["uid", "season", column]].rename(columns={"uid": "best_uid", column: "p_cell"})
        merged = cells[keys + ["n_dams", "best_uid"]].merge(best, on=["best_uid", "season"], how="left")
        merged["found"] = merged["n_dams"]       # only the best dam is used: just check it was found (p not NaN)
    else:
        reduce = {"product": "prod", "min": "min"}[how]
        grouped = dam_preds.groupby(keys)[column].agg(p_cell=reduce, found="size").reset_index()
        merged = cells[keys + ["n_dams"]].merge(grouped, on=keys, how="left")
    if merged["p_cell"].isna().any() or (merged["found"] != merged["n_dams"]).any():
        raise AssertionError("Some cells did not find all of their dam-like dams.")
    return merged["p_cell"].to_numpy(dtype=np.float64)
