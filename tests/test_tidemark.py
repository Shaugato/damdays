"""Tests of the one entry point, damdays.models.tidemark, on a small made-up world (no real data).

What is proved here:
  * the integrated model IS its parts: every output equals the component
    module run on its own (90-day tree + frailty + max rule, hazard curve,
    floor, season rating), bit for bit;
  * the output shapes keep their promises (R30 >= D0, curves never fall,
    R30-only columns blank where the dam is already below a third);
  * the TEST setting runs end to end on made-up data: its floor shift comes
    from VAL-period forecasts answered before 2016-07-01 and its band pools
    two inner blocks (nothing real is scored);
  * the season band's inner backtest is causal: scrambling every answer that
    was not final before the cutoff leaves the band unchanged, and the
    placebo can fail (an earlier scramble does change it);
  * a new member (the nets, later) plugs in through the registry, and the
    fusion averages it with T on the log-odds scale;
  * rungs whose members are not built yet refuse to fit.
"""
import numpy as np
import pandas as pd
import pytest

from damdays.data.splits import hydro_year
from damdays.models import fusion, g2, hazard, rows
from damdays.models import season_rating as sr
from damdays.models import tidemark
from damdays.models import uncertainty as unc

VAL_CUTOFF = "2009-01-01"


# ---------------------------------------------------------------------------
# A small made-up world: 40 dams in two regions, a look every 10 days, 1996 to mid-2016 (or later)
# ---------------------------------------------------------------------------
def synthetic_p1(rng, uids, region_of, dam_like, last_issue="2016-06-30"):
    """P1 issues with every column Tidemark reads. Events come sooner when `rel` is high."""
    dates = pd.date_range("1996-01-01", last_issue, freq="10D")
    p1 = pd.DataFrame({"uid": np.repeat(uids, len(dates)), "issue_date": np.tile(dates, len(uids))})
    n = len(p1)
    p1["region"] = p1["uid"].map(region_of)
    p1["warm"] = np.isin(p1["issue_date"].dt.month, [10, 11, 12, 1, 2, 3])
    p1["hydro_year"] = hydro_year(p1["issue_date"])
    p1["dam_like"] = p1["uid"].map(dam_like)
    p1["persistent"] = p1["uid"].str[-1].isin(["0", "5"])
    p1["at_risk_D0"] = True
    p1["at_risk_R30"] = rng.random(n) > 0.2
    p1["label_ok"] = rng.random(n) > 0.1
    for column in sorted({c for kind in rows.P1_KINDS for c in g2.g2_features(kind)}):
        p1[column] = rng.normal(size=n)
    for kind, scale in (("R30", 150.0), ("D0", 300.0)):
        tte = np.ceil(rng.exponential(scale * np.exp(-0.6 * p1["rel"].to_numpy())))
        p1[f"lab_tte_{kind}"] = np.where(tte > 2000, np.nan, tte)
        p1[f"y_{kind}"] = (tte <= 90).astype(float)
    p1["y_D0g"] = np.where(rng.random(n) < 0.05, np.nan, p1["y_D0"])       # abrupt-only windows: no label
    for kind in rows.P1_KINDS:
        p1[f"b2S_{kind}"] = rng.integers(0, 5, n).astype(float)
        p1[f"b2N_{kind}"] = p1[f"b2S_{kind}"] + rng.integers(0, 15, n)
    return p1


def synthetic_p2(rng, uids, region_of, dam_like, last_season=2015):
    """P2 dam seasons (1996 to last_season) with every rating input, and the 2 km cells of the dam-like dams."""
    seasons = np.arange(1996, last_season + 1)
    dams = pd.DataFrame({"uid": np.repeat(uids, len(seasons)), "season": np.tile(seasons, len(uids))})
    n = len(dams)
    dams["issue_date"] = pd.to_datetime(dams["season"].astype(str) + "-07-01")
    dams["region"] = dams["uid"].map(region_of)
    dams["dam_like"] = dams["uid"].map(dam_like)
    dams["persistent"] = False
    dams["hex_id"] = "h" + (dams["uid"].str[3:].astype(int) // 2).astype(str)     # two dams per cell
    dams["label_ok"] = rng.random(n) > 0.1
    dams["y"] = (rng.random(n) < 0.25).astype(float)
    dams["y_g"] = dams["y"] * (rng.random(n) < 0.7)
    for label, hits, count in (("y", "b2S", "b2N"), ("y_g", "b2S_g", "b2N_g")):
        dams[hits] = dams.groupby("uid")[label].cumsum() - dams[label]          # earlier seasons only
        dams[count] = dams.groupby("uid").cumcount().astype(float)
    for column in sr.season_features():
        dams[column] = rng.normal(size=n)
    dam_like_rows = dams[dams["dam_like"]]
    cells = (dam_like_rows.groupby(["hex_id", "season"])
             .agg(n_dams=("uid", "size"), best_uid=("uid", "first"), region=("region", "first"),
                  issue_date=("issue_date", "first"), y=("y", "min")).reset_index())
    cells["uid"] = cells["hex_id"]
    cells["label_ok"] = True
    return dams, cells


def synthetic_inputs(seed=0, n_dams=40, last_issue="2016-06-30", last_season=2015):
    """The three tables of tidemark.load_inputs(), made up."""
    rng = np.random.default_rng(seed)
    uids = [f"dam{i:02d}" for i in range(n_dams)]
    region_of = {u: ("nsw_cw" if i < n_dams // 2 else "wvic_sesa") for i, u in enumerate(uids)}
    dam_like = {u: i % 4 != 3 for i, u in enumerate(uids)}
    dams, cells = synthetic_p2(rng, uids, region_of, dam_like, last_season)
    return dict(p1=synthetic_p1(rng, uids, region_of, dam_like, last_issue), p2_dam=dams, p2_cell=cells)


@pytest.fixture(scope="module")
def world():
    """One fitted L1 model on the made-up world, and its forecasts."""
    inputs = synthetic_inputs()
    model = tidemark.fit_tidemark(VAL_CUTOFF, "L1", inputs=inputs)
    return dict(inputs=inputs, model=model, out=tidemark.predict_tidemark(model, inputs))


# ---------------------------------------------------------------------------
# The integrated model is its parts
# ---------------------------------------------------------------------------
def component_p90(table):
    """The 90-day probabilities the step-4 way: fusion.fit_tree_member, then frailty, then the R30 max rule."""
    history = {}
    for kind in rows.P1_KINDS:
        tree, _ = fusion.fit_tree_member(table, kind, "VAL")
        positions = tree["row"].to_numpy()
        y = table[rows.p1_label(kind)].to_numpy(dtype=float)[positions]
        history[kind] = fusion.anchor_with_frailty(tree, {"T": tree["p_T"].to_numpy()}, y,
                                                   fusion.track_record_mask(table, kind, positions))
    history["R30"]["p"], _ = fusion.r30_headline(history["R30"], history["D0"])
    return {kind: fusion.block_part(h, "VAL") for kind, h in history.items()}


def test_90_day_probabilities_equal_the_component_path(world):
    p1, table = world["out"]["p1"], world["inputs"]["p1"]
    reference = component_p90(table)
    for kind in rows.P1_KINDS:
        ref = reference[kind]
        mine = p1.set_index("row").loc[ref["row"].to_numpy(), f"p90_{kind}"].to_numpy()
        assert np.array_equal(mine, ref["p"].to_numpy()), kind                    # bit for bit
    assert set(time_blocks(p1)) == {"VAL"}


def time_blocks(frame):
    """The time blocks of a frame's issue dates."""
    from damdays.data.splits import time_block
    return time_block(frame["issue_date"])


def test_curves_floor_and_rating_equal_their_modules(world):
    inputs, p1 = world["inputs"], world["out"]["p1"]
    table = inputs["p1"]
    curves, _ = hazard.fit_and_predict_curves(table, "VAL")
    for kind in tidemark.CURVE_KINDS:
        positions = np.flatnonzero(rows.p1_block_rows(table, kind, "VAL"))
        for h in tidemark.HORIZONS:
            mine = p1.set_index("row").loc[positions, f"curve_{kind}_{h}"].to_numpy()
            assert np.array_equal(mine, curves[kind][f"p_{h}"].to_numpy()), (kind, h)

    floor_model, _ = unc.fit_floor_model(table, VAL_CUTOFF)
    mask = rows.p1_block_rows(table, "R30", "VAL")
    log_q10 = unc.predict_log_q10(floor_model, table, mask)
    mine = p1.set_index("row").loc[np.flatnonzero(mask)]
    assert np.array_equal(mine["floor_log_q10"].to_numpy(), log_q10)
    assert np.array_equal(mine["floor_days"].to_numpy(), unc.floor_days(log_q10, 0.0))    # VAL: shift 0

    dams, _ = sr.fit_and_predict(inputs["p2_dam"], "VAL", "main")
    assert np.array_equal(world["out"]["p2_dam"]["p"].to_numpy(), dams["p"].to_numpy())
    assert np.array_equal(world["out"]["p2_dam"]["p_g"].to_numpy(), dams["p_g"].to_numpy())


def test_output_promises(world):
    p1 = world["out"]["p1"]
    r30 = p1["at_risk_R30"].to_numpy()
    # R30-only columns are blank exactly where the dam is already below a third.
    for column in ("p90_R30", "curve_R30_90", "floor_days"):
        assert p1.loc[r30, column].notna().all() and p1.loc[~r30, column].isna().all(), column
    for column in ("p90_D0", "p90_D0g", "curve_D0_90", "band_low_D0"):
        assert p1[column].notna().all(), column
    on = p1[r30]
    assert (on["p90_R30"] >= on["p90_D0"]).all()                                   # a dry dam is below a third
    assert np.array_equal(on["p90_R30"], np.maximum(on["p90_R30_premax"], on["p90_D0"]))
    for kind in tidemark.CURVE_KINDS:
        rows_ = p1 if kind == "D0" else on
        curve = rows_[[f"curve_{kind}_{h}" for h in tidemark.HORIZONS]].to_numpy()
        assert (np.diff(curve, axis=1) >= 0).all(), kind                            # never falls
    assert (on[[f"curve_R30_{h}" for h in tidemark.HORIZONS]].to_numpy()
            >= on[[f"curve_D0_{h}" for h in tidemark.HORIZONS]].to_numpy()).all()
    for kind in rows.P1_KINDS:
        assert (p1[f"band_low_{kind}"].dropna() <= p1[f"band_high_{kind}"].dropna()).all()
    shown = on["floor_shown"].to_numpy()
    assert (shown == np.floor(shown)).all() and shown.max() <= 180
    cells = world["out"]["p2_cell"]
    dams = world["out"]["p2_dam"]
    product = dams.groupby(["hex_id", "season"])["p"].prod()
    assert np.allclose(cells["p"].to_numpy(), product.loc[list(zip(cells["uid"], cells["season"]))].to_numpy())


def test_summary_is_plain_data(world):
    import json
    from damdays.evaluation.report import clean_for_json
    summary = tidemark.summary(world["model"])
    text = json.dumps(clean_for_json(summary))
    assert "band_constants" in text and "floor_shift" in text
    assert summary["band"]["band"] == world["model"].band            # the offsets and blocks are kept too
    assert {"blocks", "offsets"} <= set(summary["band"])


def test_test_setting_calibrates_the_floor_on_val_and_pools_two_band_blocks():
    """The TEST setting (cutoff 2016-07-01), on made-up data that runs to 2018. Nothing real is scored."""
    inputs = synthetic_inputs(seed=4, last_issue="2018-06-30", last_season=2017)
    table = inputs["p1"]
    model = tidemark.fit_tidemark("2016-07-01", "L1", inputs=inputs)
    # Floor: the quantile model is the one fitted at 2009-01-01; the shift comes from VAL-period forecasts
    # whose 395-day answer was final before 2016-07-01 (split conformal, step 7's frozen shift).
    floor_model, _ = unc.fit_floor_model(table, "2009-01-01")
    calib = tidemark.calibration_rows(table, "2009-01-01", "2016-07-01")
    shift, n = unc.shift_from_answers_before(unc.predict_log_q10(floor_model, table, calib),
                                             unc.runway_days(table.loc[calib]), table.loc[calib, "issue_date"],
                                             "2016-07-01")
    assert (model.floor["shift"], model.floor["calibration_rows"]) == (shift, n) and n > 0
    # Band: two inner blocks (2002-2009 and 2009-2016), pooled.
    blocks = [b["block"] for b in model.info["band"]["blocks"]]
    assert blocks == ["2002-2009", "2009-2016"]
    offsets = pd.DataFrame(model.info["band"]["offsets"]["R30"])
    assert set(offsets["block"]) == {"2002-2009", "2009-2016"}
    assert model.band["R30"] == unc.pooled_band(offsets)
    out = tidemark.predict_tidemark(model, inputs)
    assert set(time_blocks(out["p1"])) == {"TEST"} and set(out["p2_dam"]["season"]) == {2016, 2017}
    assert info_fit_rows_equal_official(model, table)


def info_fit_rows_equal_official(model, table):
    """The TEST members learned from exactly rows.p1_fit_rows(..., "TEST") (TRAIN and VAL, purged; never GAP)."""
    return all(model.info["members"][k]["fit_rows"] == int(rows.p1_fit_rows(table, k, "TEST").sum())
               for k in rows.P1_KINDS)


# ---------------------------------------------------------------------------
# The band's inner backtest only knows answers final before the cutoff
# ---------------------------------------------------------------------------
def scramble_open_answers(inputs, cutoff, seed=9):
    """A copy of the inputs where every P1 answer not final before `cutoff` is replaced by noise."""
    rng = np.random.default_rng(seed)
    p1 = inputs["p1"].copy()
    open_window = ~unc.answer_known_before(p1["issue_date"], cutoff)      # issue + 120 days >= cutoff
    for kind in rows.P1_KINDS:
        labels = p1[f"y_{kind}"].to_numpy(dtype=float).copy()
        labels[open_window] = rng.integers(0, 2, open_window.sum())
        p1[f"y_{kind}"] = labels
    label_ok = p1["label_ok"].to_numpy(dtype=bool).copy()
    label_ok[open_window] = rng.random(open_window.sum()) < 0.5
    p1["label_ok"] = label_ok
    return dict(inputs, p1=p1)


def test_band_ignores_answers_not_final_before_the_cutoff():
    inputs = synthetic_inputs(seed=1)
    rung = tidemark.RUNGS["L1"]
    setting = tidemark.SETTINGS["VAL"]
    band, _ = tidemark.fit_band(inputs, rung, setting)
    same, _ = tidemark.fit_band(scramble_open_answers(inputs, VAL_CUTOFF), rung, setting)
    assert band == same                                                          # bit for bit
    # The placebo can fail: scrambling answers that WERE final before 2009 moves the band.
    moved, _ = tidemark.fit_band(scramble_open_answers(inputs, "2006-01-01"), rung, setting)
    assert band != moved


# ---------------------------------------------------------------------------
# Members and rungs
# ---------------------------------------------------------------------------
def test_a_new_member_plugs_in_and_is_fused_on_the_log_odds_scale():
    inputs = synthetic_inputs(seed=2, n_dams=12)
    constant = tidemark.Member("X", "made-up: 0.5 for every issue, two seeds", seeds=(0, 1),
                               fit=lambda inputs_, kind, fit_rows, setup, seed: seed,
                               predict=lambda fitted, inputs_, positions, setup: np.full(len(positions), 0.5))
    registry = dict(tidemark.MEMBERS, X=constant)
    rung = tidemark.Rung("LX", "T + X, no frailty, no max rule", ("T", "X"), frailty=False, max_rule=False)
    fitted, setups, _ = tidemark.fit_members(inputs, rung, VAL_CUTOFF, registry)
    assert len(fitted["R30"]["X"]) == 2                                          # one fit per seed
    history = tidemark.predict_p90(fitted, setups, inputs, rung, until="2016-01-01", registry=registry)
    for kind in rows.P1_KINDS:
        h = history[kind]
        expected = fusion.sigmoid((fusion.logit(h["p_T"].to_numpy()) + 0.0) / 2)   # logit(0.5) = 0
        assert np.allclose(h["p"].to_numpy(), expected, rtol=0, atol=1e-12)


def test_rungs_without_their_members_refuse_to_fit():
    with pytest.raises(NotImplementedError, match="S"):
        tidemark.ready_rung("L2")
    with pytest.raises(NotImplementedError):
        tidemark.ready_rung("L3")
    with pytest.raises(ValueError):
        tidemark.ready_rung("L9")
    built = dict(tidemark.MEMBERS, **{name: tidemark.Member(name, "stub", (0,), fit=print, predict=print)
                                      for name in ("S", "M")})
    with pytest.raises(NotImplementedError, match="ph_p_R30"):                  # the physics columns
        tidemark.ready_rung("L3", built, table=pd.DataFrame({"rel": [0.5]}))
    assert tidemark.ready_rung("L1").members == ("T",)


def test_cutoffs_map_to_their_blocks():
    assert tidemark.setting_for("2009-01-01") == tidemark.setting_for("VAL") == "VAL"
    assert tidemark.setting_for(pd.Timestamp("2016-07-01")) == "TEST"
    assert tidemark.block_opened_by("2002-01-01") is None
    with pytest.raises(ValueError):
        tidemark.setting_for("2012-03-04")
    with pytest.raises(ValueError):
        tidemark.setting_for("TRAIN")


def test_inner_cutoff_uses_the_dam_rate_as_of_that_cutoff():
    inputs = synthetic_inputs(seed=3, n_dams=12)
    table = inputs["p1"]
    inner = tidemark.member_setup(table, "R30", "2002-01-01")
    assert np.array_equal(inner["replace"]["dam_rate_R30"], unc.dam_rate_as_of(table, "R30", "2002-01-01"))
    assert tidemark.member_setup(table, "R30", VAL_CUTOFF)["replace"] == {}       # stored rate is causal from 2009
    # Inner fit rows: answered before the inner cutoff; block fit rows: the official purged rows.
    assert np.array_equal(tidemark.member_fit_rows(table, "D0", "2002-01-01"),
                          np.flatnonzero(unc.answered_fit_rows(table, "D0", "2002-01-01")))
    assert np.array_equal(tidemark.member_fit_rows(table, "D0", VAL_CUTOFF),
                          np.flatnonzero(rows.p1_fit_rows(table, "D0", "VAL")))
