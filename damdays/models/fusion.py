"""Tidemark's 90-day forecast: members -> equal-weight fusion -> per-dam frailty -> R30 headline.

The recipe (PREREG "Model", P1, one model per event kind: R30, D0, D0g)
----------------------------------------------------------------------
1. Members. Each member gives a probability for every forecast:
     T  LightGBM on the G2c features (+ the two water-balance columns once the
        physics module exists), trained on all waterbodies, one seed (seed 0);
     S  a sequence net (TCN + tabular MLP), the logit average of 3 seeds;
     M  a tabular MLP, the logit average of 3 seeds.
   Today only T exists. The code takes whatever members are passed in, so S
   and M plug in later without changes here.
2. Fusion. The anchor log-odds is the plain average of the members' log-odds
   (equal weights, no stacking, nothing fitted).
3. Frailty. A per-dam shift b (damdays.models.frailty) learned from the dam's
   own past forecasts whose answer is final, added to the anchor log-odds.
4. R30 headline. A dam that is fully dry is also below a third, so
   p(R30) is raised to at least p(D0): p_R30 = max(p_R30, p_D0).

Rows
----
The frailty needs the anchor probability on each dam's PAST forecasts, not
only on the forecasts being scored. So every member predicts the "history
rows": all at-risk forecasts issued before the end of the scored block
(for VAL: 1988 to 2015). The tree itself is still fitted only on the purged
fit rows (damdays.models.rows.p1_fit_rows), so nothing after the cutoff is
learned; the later rows are only predicted.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import time_block
from damdays.features import spec
from damdays.models import frailty, g2, rows

P_MIN, P_MAX = 1e-6, 1 - 1e-6           # keep probabilities strictly inside (0, 1)
TREE_N_JOBS = 3                          # CPU cap for the event build
PREDICT_CHUNK = 500_000                  # rows per prediction call (keeps memory flat)
BLOCK_END = {"VAL": config.VAL_END, "TEST": config.TEST_END}


# ---------------------------------------------------------------------------
# Log-odds helpers
# ---------------------------------------------------------------------------
def logit(p):
    """Log-odds of a probability (clipped to (1e-6, 1 - 1e-6) first)."""
    p = np.clip(np.asarray(p, dtype=float), P_MIN, P_MAX)
    return np.log(p / (1.0 - p))


def sigmoid(z):
    """Probability from log-odds."""
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


# ---------------------------------------------------------------------------
# 1. The tree member T
# ---------------------------------------------------------------------------
def tree_features(kind, extra_features=()):
    """T's inputs: the 29 G2c columns of the kind, plus any extra columns (later: the 2 physics columns)."""
    return spec.check_feature_list(g2.g2_features(kind) + list(extra_features))


def history_rows(table, kind, block):
    """Every forecast at risk for `kind` issued before the end of `block` (the rows T must predict).

    Time note: for VAL this is 1988-2015. The scored block's own rows are
    included because a VAL forecast's frailty uses earlier VAL forecasts once
    their answer is final (t_j + 120 days <= t).
    """
    before_end = pd.to_datetime(table["issue_date"]).to_numpy() < np.datetime64(BLOCK_END[block])
    return before_end & table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)


def tree_inputs(table, row_positions, features, replace=None):
    """The inputs of the table rows at `row_positions` as a float64 array, one column per feature.

    replace  optional {column: one value per TABLE row} used instead of the stored column.
             The inner backtest uses it: its dam_rate must be recomputed as of its own,
             earlier cutoff (damdays.models.uncertainty.dam_rate_as_of).
    """
    columns = [table.columns.get_loc(c) for c in features]
    X = table.iloc[np.asarray(row_positions), columns].to_numpy(dtype=np.float64)
    if replace:
        # A writable copy: with pandas copy-on-write, to_numpy() can hand back a read-only view
        # (e.g. on a consolidated table), and a column is overwritten below.
        X = np.array(X)
    for name, values in (replace or {}).items():
        X[:, features.index(name)] = np.asarray(values, dtype=np.float64)[np.asarray(row_positions)]
    return X


def fit_tree(X_fit, y_fit, seed=0):
    """One LightGBM with G2's settings (PREREG: fixed hyperparameters), at most 3 threads."""
    params = dict(g2.G2_PARAMS, n_jobs=TREE_N_JOBS, random_state=seed)
    return lgb.LGBMClassifier(**params).fit(X_fit, y_fit)


def predict_tree(model, table, row_positions, features, replace=None):
    """P(event) from a fitted tree for the table rows at `row_positions`, clipped to (1e-6, 1 - 1e-6).

    Predicts 500,000 rows at a time so memory stays flat on the 2.6-million-row table.
    """
    row_positions = np.asarray(row_positions)
    p = np.empty(len(row_positions), dtype=np.float64)
    for start in range(0, len(row_positions), PREDICT_CHUNK):
        chunk = row_positions[start:start + PREDICT_CHUNK]
        p[start:start + len(chunk)] = model.predict_proba(tree_inputs(table, chunk, features, replace))[:, 1]
    return np.clip(p, P_MIN, P_MAX)


def gain_shares(model, features, top=8):
    """Each input's share of the tree's total split gain (the largest `top`, rounded)."""
    gain = pd.Series(model.booster_.feature_importance("gain"), index=features)
    return (gain / gain.sum()).sort_values(ascending=False).head(top).round(4).to_dict()


def fit_tree_member(table, kind, block, extra_features=(), seed=0):
    """Fit T for `kind` on the purged fit rows of `block`; predict every history row.

    Same LightGBM settings as G2 (PREREG: fixed), trained on all waterbodies,
    at most 3 threads. With no extra features T is the G2 recipe exactly.
    Returns (predictions: row, uid, issue_date, p_T as float64; info dict).
      row  position of the forecast in `table` (so tables can be aligned without joins)
    damdays.models.tidemark uses the same three steps (tree_inputs, fit_tree, predict_tree)
    and keeps the fitted model.
    """
    features = tree_features(kind, extra_features)
    label = rows.p1_label(kind)
    fit = rows.p1_fit_rows(table, kind, block, population="all")      # purged: answer final before the block
    y_fit = table.loc[fit, label].to_numpy(dtype=int)
    model = fit_tree(tree_inputs(table, np.flatnonzero(fit), features), y_fit, seed)

    predict = np.flatnonzero(history_rows(table, kind, block))
    predictions = pd.DataFrame({"row": predict, "uid": table["uid"].astype(str).to_numpy()[predict],
                                "issue_date": table["issue_date"].to_numpy()[predict],
                                "p_T": predict_tree(model, table, predict, features)})
    info = dict(member="T", kind=kind, block=block, seed=seed, fit_rows=int(fit.sum()), fit_events=int(y_fit.sum()),
                predicted_rows=len(predict), features=features, n_jobs=TREE_N_JOBS,
                top_features_by_gain=gain_shares(model, features))
    return predictions, info


# ---------------------------------------------------------------------------
# 2. Fusion: equal-weight average of the members' log-odds
# ---------------------------------------------------------------------------
def member_logit(seed_probabilities):
    """One member's log-odds. A list of seed runs (S and M use 3 seeds) is averaged on the log-odds scale."""
    if isinstance(seed_probabilities, (list, tuple)):
        return np.mean([logit(p) for p in seed_probabilities], axis=0)
    return logit(seed_probabilities)


def fuse_members(members):
    """The anchor log-odds: the plain mean of the available members' log-odds (equal weights, no stacking).

    members  {name: probabilities} for the same rows in the same order, e.g. {"T": p_T}
             or {"T": p_T, "S": [p_S0, p_S1, p_S2], "M": [p_M0, p_M1, p_M2]}
    """
    if not members:
        raise ValueError("Fusion needs at least one member.")
    logits = [member_logit(probabilities) for probabilities in members.values()]
    if len({len(z) for z in logits}) != 1:
        raise ValueError("All members must predict the same rows.")
    return np.mean(logits, axis=0)


# ---------------------------------------------------------------------------
# 3. Anchor + frailty, for one event kind
# ---------------------------------------------------------------------------
def anchor_with_frailty(history, members, y, is_record, lam=frailty.FRAILTY_LAMBDA):
    """Fuse the members, then add each dam's frailty. Returns a table aligned with `history`.

    history    the history rows (row, uid, issue_date), the same rows the members predicted
    members    {name: probabilities on those rows}
    y          each row's label (NaN where unknown)
    is_record  True where the row may serve as track record: label determinable and known
    Columns added: p_anchor (members only), frailty_b, frailty_R, frailty_V, frailty_n, p (anchor + frailty).
    """
    z_anchor = fuse_members(members)
    p_anchor = sigmoid(z_anchor)
    # The frailty reads the anchor on each dam's matured past forecasts (t_j + 120 days <= t).
    dam_effect = frailty.frailty_for_rows(history["uid"].to_numpy(), history["issue_date"].to_numpy(),
                                          is_record, y, p_anchor, lam)
    out = history[["row", "uid", "issue_date"]].reset_index(drop=True).copy()
    out["p_anchor"] = np.clip(p_anchor, P_MIN, P_MAX)
    out = pd.concat([out, dam_effect], axis=1)
    out["p"] = np.clip(sigmoid(z_anchor + dam_effect["frailty_b"].to_numpy()), P_MIN, P_MAX)
    return out


def track_record_mask(table, kind, row_positions):
    """True where a history row may serve as track record: at risk (already), label determinable and known."""
    label_ok = table["label_ok"].to_numpy(dtype=bool)[row_positions]
    label_known = table[rows.p1_label(kind)].notna().to_numpy()[row_positions]
    return label_ok & label_known


# ---------------------------------------------------------------------------
# 4. The R30 headline: never below the D0 probability
# ---------------------------------------------------------------------------
def r30_headline(p_r30_rows, p_d0_rows):
    """p_R30 raised to at least p_D0 for the same forecast (a fully dry dam is also below a third).

    p_r30_rows, p_d0_rows  tables with row (position in the P1 table) and p.
    Every R30 forecast is also a D0 forecast (a dam at least 30% full has water),
    so each R30 row must find its D0 row; this is checked.
    Returns (p headline aligned with p_r30_rows, share of rows where the D0 value was higher).
    """
    d0 = pd.Series(p_d0_rows["p"].to_numpy(), index=p_d0_rows["row"].to_numpy())
    p_d0 = d0.reindex(p_r30_rows["row"].to_numpy()).to_numpy()
    if np.isnan(p_d0).any():
        raise AssertionError("Some R30 forecasts have no D0 forecast to compare with.")
    p_r30 = p_r30_rows["p"].to_numpy()
    raised = p_d0 > p_r30
    return np.maximum(p_r30, p_d0), float(raised.mean())


def block_part(frame, block):
    """The rows of a history table issued in `block` (e.g. the VAL forecasts to score)."""
    return frame[time_block(frame["issue_date"]) == block].reset_index(drop=True)
