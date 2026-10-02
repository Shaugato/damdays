"""G2, the pre-registered benchmark (LightGBM), and two VAL-only diagnostics.

What G2 is (PREREG "Benchmark model")
-------------------------------------
LightGBM with the pre-event "rescue" settings (400 trees, learning rate
0.03, 15 leaves, at least 40 rows per leaf, 80% row and column sampling), on
the 29 causal columns of damdays.features.spec.FEATURE_SPEC (the "G2c
feature set"). One of them is the dam's own track record, dam_rate_K, in its
causal form: a past forecast counts only once its answer was final on the
issue date. G2 learns from the purged fit rows (damdays.models.rows) of every
has_hist waterbody, pooled over both development regions. No region
identifier is an input. One model per event kind (R30, D0, D0g).

The three variants, and their names in the pre-event research
--------------------------------------------------------------
G2         the PREREG benchmark described above. The pre-event research ran
           this exact recipe as a diagnostic called "G2c" (VAL R30 +0.171);
           the PREREG then made it the benchmark.
G2c        the same features, trained on dam-like rows only (the population
           the headline is scored on). A VAL diagnostic requested by the build plan.
G2_rescue  the pre-event research's "G2" (VAL R30 +0.163). On its TRAINING
           rows the dam rate was the dam's rate over its OTHER fit years
           (leave one July-June year out), which uses the same dam's later
           years. The leakage audit flagged this, and the PREREG replaced it
           with the causal rate. Kept only to show that the pre-event check
           value is reproduced. Never used on TEST.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from damdays import config
from damdays.features import spec
from damdays.models import rows

# The pre-event "rescue" LightGBM settings (PREREG: fixed). The last three only
# make runs repeatable and cap CPU use (the build plan allows at most 4 threads).
G2_PARAMS = dict(
    n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=40,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=0, verbose=-1,
    n_jobs=4, deterministic=True, force_row_wise=True)

VARIANTS = {
    "G2": dict(train_on="all", dam_rate="causal",
               about="PREREG benchmark: causal dam rate, all waterbodies"),
    "G2c": dict(train_on="dam_like", dam_rate="causal",
                about="diagnostic: causal dam rate, trained on dam-like rows only"),
    "G2_rescue": dict(train_on="all", dam_rate="rescue",
                      about="diagnostic: the pre-event G2 (leave-one-year-out dam rate on training rows)"),
}
P_MIN, P_MAX = 1e-6, 1 - 1e-6


def g2_features(kind):
    """The 29 input columns for one event kind; refuses labels and forbidden columns."""
    return spec.check_feature_list(spec.p1_tree_features(kind))


def rescue_dam_rate(fit, fit_y, scored, k=config.B2_SHRINK_P1):
    """The pre-event "rescue" dam rate, for G2_rescue only. Returns (rate on fit rows, rate on scored rows).

    Everything is grouped by dam and half-year (Oct-Mar or Apr-Sep), and
    shrunk toward the pooled half-year rate of the fit rows with k = 20:
      fit rows     the dam's rate over its fit rows in OTHER July-June years.
                   NOT causal: a 1995 training row sees the dam's 1996-2008
                   outcomes. That is why the PREREG G2 uses the causal rate.
      scored rows  the dam's rate over ALL its fit rows (frozen at the end of
                   the fit block). Causal for VAL: every fit answer is final
                   before VAL starts.
    """
    frame = pd.DataFrame({"uid": fit["uid"].astype(str).to_numpy(), "warm": fit["warm"].to_numpy(dtype=bool),
                          "year": fit["hydro_year"].to_numpy(), "y": np.asarray(fit_y, dtype=float)})
    pooled = frame.groupby("warm")["y"].mean()
    per_dam = frame.groupby(["uid", "warm"])["y"].agg(dam_hits="sum", dam_n="size").reset_index()
    per_year = frame.groupby(["uid", "warm", "year"])["y"].agg(year_hits="sum", year_n="size").reset_index()

    # Fit rows: the dam's totals minus the row's own July-June year.
    own = frame.merge(per_dam, on=["uid", "warm"], how="left").merge(per_year, on=["uid", "warm", "year"], how="left")
    hits = own["dam_hits"] - own["year_hits"]
    count = own["dam_n"] - own["year_n"]
    fit_rate = (hits + k * frame["warm"].map(pooled)) / (count + k)

    # Scored rows: the dam's totals over the whole fit block (0 if the dam has no fit rows).
    target = pd.DataFrame({"uid": scored["uid"].astype(str).to_numpy(), "warm": scored["warm"].to_numpy(dtype=bool)})
    seen = target.merge(per_dam, on=["uid", "warm"], how="left")
    prior = target["warm"].map(pooled).fillna(frame["y"].mean())
    scored_rate = (seen["dam_hits"].fillna(0) + k * prior) / (seen["dam_n"].fillna(0) + k)
    return fit_rate.to_numpy(dtype=float), scored_rate.to_numpy(dtype=float)


def fit_and_predict(table, kind, block, variant="G2"):
    """Fit one G2 variant for `kind` on the purged fit rows; predict every at-risk forecast issued in `block`.

    table  the P1 table with the keys, dam and nbr groups (damdays.features.store.load_p1)
    Returns (predictions: uid, issue_date, p as float64; info dict with fit sizes and feature importance).
    """
    settings = VARIANTS[variant]
    features = g2_features(kind)
    label = rows.p1_label(kind)
    needed = ["uid", "issue_date", "warm", "hydro_year", label] + features

    fit = table.loc[rows.p1_fit_rows(table, kind, block, settings["train_on"]), needed]
    scored = table.loc[rows.p1_block_rows(table, kind, block), needed]
    y_fit = fit[label].to_numpy(dtype=int)
    X_fit = fit[features].to_numpy(dtype=np.float64)
    X = scored[features].to_numpy(dtype=np.float64)
    if settings["dam_rate"] == "rescue":
        column = features.index(f"dam_rate_{kind}")
        X_fit[:, column], X[:, column] = rescue_dam_rate(fit, y_fit, scored)

    model = lgb.LGBMClassifier(**G2_PARAMS).fit(X_fit, y_fit)
    p = np.clip(model.predict_proba(X)[:, 1].astype(np.float64), P_MIN, P_MAX)

    predictions = pd.DataFrame({"uid": scored["uid"].astype(str).to_numpy(),
                                "issue_date": scored["issue_date"].to_numpy(), "p": p})
    gain = pd.Series(model.booster_.feature_importance("gain"), index=features)
    info = dict(variant=variant, kind=kind, block=block, about=settings["about"], train_on=settings["train_on"],
                dam_rate=settings["dam_rate"], fit_rows=len(fit), fit_events=int(y_fit.sum()),
                predicted_rows=len(scored), features=features,
                top_features_by_gain=(gain / gain.sum()).sort_values(ascending=False).head(8).round(4).to_dict())
    return predictions, info
