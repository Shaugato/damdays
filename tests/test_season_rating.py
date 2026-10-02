"""Small, hand-checkable tests of the P2 season rating (damdays.models.season_rating).

What is proved here, without reading real data:
  * the area index equals a slow, obvious re-computation (loops over dams,
    seasons and neighbours, distances measured directly);
  * it is causal: deleting every answer from some season on changes nothing
    for the ratings issued up to that season (and does change later ones,
    so the check is not vacuous);
  * the B2 starting point is the shrunk own-history rate with a prior from
    seasons answered before the block;
  * cell probabilities are the product (or min, or best dam) of their dams';
  * the model's input list holds no label, static or identifier column;
  * the within-dam bootstrap of scripts/05_season_rating.py treats a dam drawn
    twice as two separate dams (review fix: it used to count its pairs 4 times).
Real-data checks (placebo, hand checks) are in tests/test_season_rating_real.py.
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from damdays.evaluation.bootstrap import cluster_weights
from damdays.evaluation.metrics import Ranking
from damdays.features import spec
from damdays.models import season_rating as sr

STEP5_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "05_season_rating.py"


def load_step5_script():
    """scripts/05_season_rating.py as a module (its name starts with a digit, so a plain import cannot load it)."""
    spec_ = importlib.util.spec_from_file_location("step05_season_rating", STEP5_SCRIPT)
    module = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# A tiny made-up P2 dam table
# ---------------------------------------------------------------------------
def synthetic_dams(seed=0, seasons=range(2001, 2013)):
    """12 waterbodies on a line (2 km apart, plus two far away), one row per season, random answers."""
    rng = np.random.default_rng(seed)
    x_km = np.r_[np.arange(10) * 2.0, 60.0, 90.0]
    uids = [f"w{i:02d}" for i in range(len(x_km))]
    attrs = pd.DataFrame({"uid": uids, "x_albers": x_km * 1000.0, "y_albers": 0.0,
                          "dam_like": [i % 3 != 0 for i in range(len(x_km))]})
    seasons = np.array(list(seasons))
    dams = pd.DataFrame({"uid": np.repeat(uids, len(seasons)), "season": np.tile(seasons, len(uids))})
    n = len(dams)
    dams["y"] = (rng.random(n) < 0.3).astype(float)
    dams["label_ok"] = rng.random(n) > 0.2
    dams.loc[~dams["label_ok"], "y"] = np.where(rng.random((~dams["label_ok"]).sum()) < 0.5, np.nan, 1.0)
    return dams, attrs


def brute_force_area_index(dams, attrs):
    """The area index the slow, obvious way, for comparison."""
    where = attrs.set_index("uid")
    known = {(u, s): y for u, s, y, ok in dams[["uid", "season", "y", "label_ok"]].itertuples(index=False)
             if ok and np.isfinite(y)}
    out = {column: np.full(len(dams), np.nan) for column in sr.AREA_INDEX_COLUMNS}
    for row, (uid, season) in enumerate(dams[["uid", "season"]].itertuples(index=False)):
        for column, radius_km, pool, which in sr.AREA_INDEX:
            near = [v for v in where.index if v != uid
                    and np.hypot(where.at[v, "x_albers"] - where.at[uid, "x_albers"],
                                 where.at[v, "y_albers"] - where.at[uid, "y_albers"]) <= radius_km * 1000.0
                    and (pool == "all" or where.at[v, "dam_like"])]
            used = [season - 1] if which == "last" else [s for s in dams["season"].unique() if s < season]
            answers = [known[(v, s)] for v in near for s in used if (v, s) in known]
            needed = sr.AREA_MIN_LAST if which == "last" else sr.AREA_MIN_LONG
            if len(answers) >= needed:
                out[column][row] = np.mean(answers)
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Area index
# ---------------------------------------------------------------------------
def test_area_index_matches_brute_force():
    dams, attrs = synthetic_dams()
    fast = sr.area_index(dams, attrs).reset_index(drop=True)
    slow = brute_force_area_index(dams, attrs)
    for column in sr.AREA_INDEX_COLUMNS:
        np.testing.assert_allclose(fast[column].to_numpy(), slow[column].to_numpy(), equal_nan=True,
                                   err_msg=column)
    # Some values must exist and some must be blank (too few neighbours / answers), or the test proves little.
    assert fast.notna().to_numpy().any() and fast.isna().to_numpy().any()


def test_area_index_never_uses_the_rated_season_or_later():
    """Delete every answer from season 2007 on: ratings for seasons up to 2007 must not change."""
    dams, attrs = synthetic_dams(seed=1)
    full = sr.area_index(dams, attrs)
    truncated = dams.copy()
    later = truncated["season"] >= 2007
    truncated.loc[later, "label_ok"] = False
    truncated.loc[later, "y"] = np.nan
    cut = sr.area_index(truncated, attrs)
    upto = (dams["season"] <= 2007).to_numpy()
    np.testing.assert_array_equal(full[upto].to_numpy(), cut[upto].to_numpy())
    changed = ~np.isclose(full[~upto].to_numpy(), cut[~upto].to_numpy(), equal_nan=True)
    assert changed.any(), "truncation changed nothing after the cut: the check would be vacuous"


def test_area_index_needs_a_full_grid():
    dams, attrs = synthetic_dams()
    with pytest.raises(AssertionError):
        sr.area_index(dams.iloc[1:], attrs)


# ---------------------------------------------------------------------------
# B2 starting point
# ---------------------------------------------------------------------------
def test_b2_rate_uses_the_fit_seasons_prior():
    """prior = dry share of TRAIN seasons per region x population; B2 = (S + 5 prior) / (N + 5)."""
    seasons = np.arange(2003, 2012)          # 2003-2008 are TRAIN, 2009-2011 VAL
    dams = pd.DataFrame({"uid": np.repeat(["a", "b"], len(seasons)), "season": np.tile(seasons, 2)})
    dams["issue_date"] = pd.to_datetime(dams["season"].astype(str) + "-07-01")
    dams["region"] = "nsw_cw"
    dams["dam_like"] = True
    dams["label_ok"] = True
    dams["y"] = np.r_[[1, 0, 0, 0, 1, 0, 1, 1, 1], [0, 0, 0, 0, 0, 1, 1, 1, 1]].astype(float)
    dams["y_g"] = dams["y"]
    dams["b2S"] = dams.groupby("uid")["y"].cumsum() - dams["y"]          # earlier seasons only
    dams["b2N"] = dams.groupby("uid").cumcount().astype(float)
    dams["b2S_g"], dams["b2N_g"] = dams["b2S"], dams["b2N"]
    prior = 3 / 12                                                       # 3 dry of the 12 TRAIN seasons
    expected = (dams["b2S"] + 5 * prior) / (dams["b2N"] + 5)
    np.testing.assert_allclose(sr.b2_rate(dams, "y", "VAL"), expected.to_numpy())


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------
def test_cell_probability_product_min_and_best():
    dam_preds = pd.DataFrame({"uid": ["a", "b", "c"], "hex_id": ["h1", "h1", "h2"], "season": 2010,
                              "p": [0.5, 0.2, 0.7]})
    cells = pd.DataFrame({"hex_id": ["h1", "h2"], "season": 2010, "n_dams": [2, 1], "best_uid": ["b", "c"]})
    np.testing.assert_allclose(sr.cell_probability(dam_preds, cells), [0.1, 0.7])
    np.testing.assert_allclose(sr.cell_probability(dam_preds, cells, how="min"), [0.2, 0.7])
    np.testing.assert_allclose(sr.cell_probability(dam_preds, cells, how="best"), [0.2, 0.7])
    with pytest.raises(AssertionError):           # a cell that lost one of its dams is an error
        sr.cell_probability(dam_preds.iloc[1:], cells)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def test_within_dam_bootstrap_counts_a_redrawn_dam_as_separate_copies():
    """Within-dam AUC of a dam-bootstrap replicate = the AUC on explicit copies, each copy its own group.

    A dam drawn k times is k separate dams in the resample: its pairs count k
    times. Plain row weights would count them k x k times (too-wide intervals).
    """
    step5 = load_step5_script()
    rng = np.random.default_rng(3)
    dam = np.repeat(np.arange(30), 8)                      # 30 dams x 8 seasons
    y = (rng.random(len(dam)) < 0.3).astype(float)
    p = rng.random(len(dam))
    names, index = np.unique(dam, return_inverse=True)
    ranking = Ranking(p, dam)
    for _ in range(5):
        state = rng.bit_generator.state
        w = cluster_weights(index, len(names), rng)
        # the same draw, made by hand: copy every drawn dam, and give each copy its own group number
        replay = np.random.default_rng()
        replay.bit_generator.state = state
        drawn = replay.integers(0, len(names), len(names))
        rows = np.concatenate([np.flatnonzero(dam == names[i]) for i in drawn])
        copy_id = np.concatenate([np.full(int((dam == names[i]).sum()), j) for j, i in enumerate(drawn)])
        by_hand = Ranking(p[rows], copy_id).auc(y[rows])
        assert ranking.auc(y, step5.within_unit_weights(w)) == pytest.approx(by_hand, abs=1e-12)
        assert not ranking.auc(y, w) == pytest.approx(by_hand, abs=1e-6)   # plain weights are wrong here
    assert step5.within_unit_weights(None) is None


def test_inputs_hold_no_label_static_or_identifier():
    features = sr.season_features()
    assert not set(features) & (spec.LABEL_COLUMNS | spec.FORBIDDEN_COLUMNS)
    assert not [f for f in features if f.startswith("rain") or f in ("drought10", "clim_ann")], "no rain (PREREG)"
    assert not set(features) & {"reg_zero", "reg_anom", "reg_pct"}, "the regional block is dropped (PREREG)"
    assert set(sr.season_features(with_area_index=False)) == set(spec.P2_FEATURE_SPEC)
