"""The P2 season rating on real data: an end-to-end placebo and hand checks on single dams and cells.

* PLACEBO. Replace every answer from season 2012 on with random ones, rebuild
  everything that is computed from answers (the dam's season track record,
  the area index, the B2 starting point and its prior), refit, and predict
  VAL. A rating issued on 1 July 2009-2012 may only use answers final by
  then, so it must not move at all. Positive control: later ratings must move.
* HAND CHECKS. For two named dams, B2 and every area-index value are
  recomputed the slow way (explicit season lists, distances measured
  directly), and a real 8-dam cell's probability is the product of its dams'.

Needs data_cache/attributes.pkl and data_cache/features/ (scripts/01 and 02);
skipped otherwise. About 30 seconds.
"""
import numpy as np
import pandas as pd
import pytest

from damdays import config
from damdays.features import store
from damdays.features.season import add_track_record
from damdays.models import rows
from damdays.models import season_rating as sr

PLACEBO_SEASON = 2012
TRACK_RECORD = ["b2S", "b2N", "b2S_g", "b2N_g", "lag1", "lag2", "rate5", "lag1_R30", "rate_R30",
                "dam_rate_P2", "dam_rate_P2_g"]
LABELS = ["y", "y_g", "y_R30"]
# (dam, season) pairs checked by hand: one dam per region with a few dry seasons behind it.
HAND_CHECKED = [("r60e4sqhj_v3", 2012), ("r17fvthkd_v3", 2012)]


@pytest.fixture(scope="module")
def tables():
    """The stored P2 dam and cell tables and the waterbody attributes (skip if not built)."""
    if not (config.CACHE_DIR / "attributes.pkl").exists() or not (config.CACHE_DIR / "features").exists():
        pytest.skip("data_cache/ is not built; run scripts/01_build_data.py and scripts/02_build_features.py")
    return dict(dams=store.load_p2("dam"), cells=store.load_p2("cell"),
                attrs=pd.read_pickle(config.CACHE_DIR / "attributes.pkl"))


def rebuild_track_record(table, dtypes):
    """add_track_record as scripts/02 runs it: labels as float64, then stored with the table's own dtypes."""
    out = add_track_record(table.astype({c: "float64" for c in LABELS}))
    return out.astype({c: dtypes[c] for c in out.columns if c in dtypes.index})


def same(a, b):
    """Element-wise exact equality, with missing == missing."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return (a == b) | (np.isnan(a) & np.isnan(b))


def test_ratings_ignore_answers_not_final_on_1_july(tables):
    dams, attrs = tables["dams"], tables["attrs"]
    # The rebuild used below is the real one: on the true answers it gives back the stored columns.
    rebuilt = rebuild_track_record(dams.copy(), dams.dtypes)
    for column in TRACK_RECORD:
        assert same(rebuilt[column], dams[column]).all(), column

    # Placebo: random answers (and random "answer known" flags) from season 2012 on.
    rng = np.random.default_rng(20261003)
    fake = dams.copy()
    later = (fake["season"] >= PLACEBO_SEASON).to_numpy()
    n = int(later.sum())
    fake.loc[later, "label_ok"] = rng.random(n) < 0.9
    fake.loc[later, "y"] = (rng.random(n) < 0.5).astype(np.float32)
    fake.loc[later, "y_g"] = np.where(rng.random(n) < 0.2, np.nan, fake.loc[later, "y"]).astype(np.float32)
    fake.loc[later, "y_R30"] = (rng.random(n) < 0.5).astype(np.float32)
    fake = rebuild_track_record(fake, dams.dtypes)

    real_preds, real_info = sr.fit_and_predict(sr.add_area_index(dams, attrs), "VAL", "main")
    fake_preds, fake_info = sr.fit_and_predict(sr.add_area_index(fake, attrs), "VAL", "main")
    assert real_preds[["uid", "season"]].equals(fake_preds[["uid", "season"]])
    assert (real_info["fit_seasons"], real_info["fit_dry"]) == (fake_info["fit_seasons"], fake_info["fit_dry"])

    upto = (real_preds["season"] <= PLACEBO_SEASON).to_numpy()
    assert upto.any() and (~upto).any()
    for column in ("p", "p_g", "p_start", "p_start_g"):
        unchanged = same(real_preds[column], fake_preds[column])
        assert unchanged[upto].all(), f"{column}: a rating issued by 1 Jul {PLACEBO_SEASON} saw a later answer"
        # Positive control: most later ratings move (the placebo is not vacuous).
        assert (~unchanged[~upto]).mean() > 0.5, column


@pytest.mark.parametrize("uid, season", HAND_CHECKED)
def test_b2_start_and_area_index_by_hand(tables, uid, season):
    dams, attrs = tables["dams"], tables["attrs"]
    me = dams[dams["uid"] == uid].set_index("season")
    region = me["region"].iloc[0]

    # B2 = (dry earlier seasons + 5 x prior) / (earlier seasons with an answer + 5);
    # prior = dry share of this region's dam-like TRAIN seasons (all answered by 30 Apr 2009).
    train = dams[(dams["issue_date"] < config.TRAIN_END) & dams["label_ok"] & dams["dam_like"]
                 & (dams["region"] == region)]
    for label in ("y", "y_g"):
        earlier = me[(me.index < season) & me["label_ok"] & me[label].notna()][label].astype(float)
        prior = train[label].dropna().astype(float).mean()
        by_hand = (earlier.sum() + 5 * prior) / (len(earlier) + 5)
        row = ((dams["uid"] == uid) & (dams["season"] == season)).to_numpy()
        assert sr.b2_rate(dams, label, "VAL")[row][0] == pytest.approx(by_hand, abs=1e-9), label

    # Area index: other waterbodies within the radius, measured directly; their answers before `season`.
    with_index = sr.add_area_index(dams, attrs).set_index(["uid", "season"])
    where = attrs.set_index("uid").loc[dams["uid"].unique(), ["x_albers", "y_albers", "dam_like"]]
    distance_m = np.hypot(where["x_albers"] - where.at[uid, "x_albers"], where["y_albers"] - where.at[uid, "y_albers"])
    for column, radius_km, pool, which in sr.AREA_INDEX:
        near = distance_m.index[(distance_m <= radius_km * 1000) & (distance_m.index != uid)]
        if pool == "dam_like":
            near = [v for v in near if where.at[v, "dam_like"]]
        seasons = [season - 1] if which == "last" else list(range(config.P2_FIRST_SEASON, season))
        theirs = with_index.loc[pd.MultiIndex.from_product([near, seasons])]
        answers = theirs.loc[theirs["label_ok"] & theirs["y"].notna(), "y"].astype(float)
        needed = sr.AREA_MIN_LAST if which == "last" else sr.AREA_MIN_LONG
        got = with_index.at[(uid, season), column]
        if len(answers) < needed:
            assert np.isnan(got), column              # too few answers nearby: left blank
        else:
            assert got == pytest.approx(answers.mean(), abs=1e-12), column


def test_a_real_multi_dam_cell_is_the_product_of_its_dams(tables):
    dams, cells = tables["dams"], tables["cells"]
    # Any per-dam probability will do for this check; use the B2 start of every dam-like VAL rating.
    scored = (rows.p2_block_rows(dams, "VAL") & dams["dam_like"].to_numpy(bool))
    dam_p = dams.loc[scored, ["uid", "hex_id", "season"]].assign(p=sr.b2_rate(dams, "y", "VAL")[scored])
    val_cells = cells[rows.p2_block_rows(cells, "VAL")]
    biggest = val_cells.sort_values(["n_dams", "hex_id", "season"]).iloc[[-1]]
    members = dam_p[(dam_p["hex_id"] == biggest["hex_id"].iloc[0]) & (dam_p["season"] == biggest["season"].iloc[0])]
    assert len(members) == biggest["n_dams"].iloc[0] >= 3
    assert sr.cell_probability(dam_p, biggest)[0] == pytest.approx(np.prod(members["p"].to_numpy()), rel=1e-12)
    # Every VAL cell finds all its dams (cell_probability raises otherwise).
    assert len(sr.cell_probability(dam_p, val_cells)) == len(val_cells)
