"""Small, hand-checkable tests of the baselines and the G2 benchmark.

The rules worth proving are about time: a model judged on VAL may only learn
from forecasts answered before VAL starts (the purge). The rest check the
baseline formulas on numbers small enough to work out by hand. None of these
tests read real data.
"""
import numpy as np
import pandas as pd
import pytest

from damdays.features import spec
from damdays.models import baselines, g2, rows


# ---------------------------------------------------------------------------
# A tiny made-up P1 table
# ---------------------------------------------------------------------------
def synthetic_p1(n_dams=20, seed=0):
    """Two looks a month per dam from 2005 to 2010, with every column the models read."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2005-01-01", "2010-12-31", freq="SMS")
    frame = pd.DataFrame({
        "uid": np.repeat([f"dam{i:02d}" for i in range(n_dams)], len(dates)),
        "issue_date": np.tile(dates, n_dams),
    })
    n = len(frame)
    frame["region"] = np.where(frame["uid"] < "dam10", "nsw_cw", "wvic_sesa")
    frame["warm"] = np.isin(frame["issue_date"].dt.month, [10, 11, 12, 1, 2, 3])
    frame["hydro_year"] = np.where(frame["issue_date"].dt.month >= 7, frame["issue_date"].dt.year,
                                   frame["issue_date"].dt.year - 1)
    frame["dam_like"] = frame["uid"] < "dam15"
    frame["persistent"] = frame["uid"] >= "dam05"
    frame["at_risk_D0"] = rng.random(n) > 0.1
    frame["at_risk_R30"] = rng.random(n) > 0.2
    frame["label_ok"] = rng.random(n) > 0.15
    frame["window_closed"] = True
    for kind in rows.P1_KINDS:
        frame[f"y_{kind}"] = (rng.random(n) < 0.2).astype(float)
        frame[f"b2S_{kind}"] = rng.integers(0, 5, n).astype(float)
        frame[f"b2N_{kind}"] = frame[f"b2S_{kind}"] + rng.integers(0, 10, n)
    frame.loc[rng.random(n) < 0.05, "y_D0g"] = np.nan          # windows with only an abrupt dry-out
    for column in {c for kind in rows.P1_KINDS for c in g2.g2_features(kind)}:
        frame[column] = rng.random(n)
    return frame


# ---------------------------------------------------------------------------
# The purge: P1 fit rows for VAL must be answered before 2009-01-01
# ---------------------------------------------------------------------------
def test_p1_fit_rows_drop_forecasts_answered_after_val_starts():
    table = pd.DataFrame({
        # 2008-09-02 + 120 days = 2008-12-31 (answered in time); 2008-09-03 + 120 = 2009-01-01 (too late)
        "issue_date": pd.to_datetime(["2008-09-02", "2008-09-03", "2009-02-01", "2008-01-01", "2008-01-02"]),
        "at_risk_R30": [True, True, True, True, False],
        "label_ok": [True, True, True, True, True],
        "y_R30": [1.0, 0.0, 1.0, np.nan, 0.0],
        "dam_like": [True] * 5,
    })
    keep = rows.p1_fit_rows(table, "R30", "VAL")
    assert list(keep) == [True, False, False, False, False]   # 2009 is VAL; a blank label and not-at-risk are out
    unpurged = rows.p1_fit_rows(table, "R30", "VAL", purge=False)
    assert list(unpurged) == [True, True, False, False, False]


def test_d0_gradual_is_at_risk_whenever_d0_is():
    assert rows.p1_at_risk_column("D0g") == "at_risk_D0"
    assert rows.p1_at_risk_column("R30") == "at_risk_R30"
    with pytest.raises(ValueError):
        rows.p1_at_risk_column("R50")


def test_p2_fit_rows_are_seasons_answered_before_the_first_val_rating():
    table = pd.DataFrame({
        "issue_date": pd.to_datetime(["2007-07-01", "2008-07-01", "2009-07-01"]),
        "label_ok": [True, True, True], "y": [1.0, 0.0, 1.0],
    })
    # The 2008 season ends 31 Mar 2009 (+30 days to confirm), before the first VAL rating on 1 Jul 2009.
    assert list(rows.p2_fit_rows(table, "y", "VAL")) == [True, True, False]
    assert rows.first_rating_in_block("VAL") == pd.Timestamp("2009-07-01")
    assert rows.first_rating_in_block("TEST") == pd.Timestamp("2016-07-01")


def test_scored_label_is_blank_when_the_answer_is_not_determinable():
    table = pd.DataFrame({"y_R30": [1.0, 0.0, 1.0], "label_ok": [True, True, False]})
    assert np.allclose(rows.p1_scored_label(table, "R30"), [1.0, 0.0, np.nan], equal_nan=True)


# ---------------------------------------------------------------------------
# Baseline formulas
# ---------------------------------------------------------------------------
def test_b0_is_the_month_region_rate_with_a_region_fallback():
    fit = pd.DataFrame({
        "issue_date": pd.to_datetime(["2000-01-15"] * 40 + ["2000-02-15"] * 5),
        "region": ["a"] * 45,
    })
    y = np.r_[np.ones(10), np.zeros(30), np.ones(5)]          # January 10/40; February 5/5 (too few rows)
    table = pd.DataFrame({"issue_date": pd.to_datetime(["2010-01-03", "2010-02-03", "2010-01-03"]),
                          "region": ["a", "a", "b"]})
    b0 = baselines.month_region_rate(fit, y, table)
    assert b0[0] == pytest.approx(10 / 40)                     # month x region
    assert b0[1] == pytest.approx(15 / 45)                     # February has < 30 fit rows: region rate
    assert b0[2] == pytest.approx(15 / 45)                     # unseen region: overall rate


def test_b2_shrinks_the_dams_own_rate_toward_the_prior():
    # 3 events in 10 past forecasts, prior 0.2, k = 20: (3 + 4) / 30
    assert baselines.shrunk_rate(3, 10, 0.2, 20) == pytest.approx(7 / 30)
    assert baselines.shrunk_rate(0, 0, 0.2, 20) == pytest.approx(0.2)    # no history: the prior


def test_p1_baselines_cover_every_at_risk_val_forecast():
    table = synthetic_p1()
    out = baselines.p1_baselines(table, "R30", "VAL", "dam_like")
    scored = table[rows.p1_block_rows(table, "R30", "VAL")]
    assert len(out) == len(scored)
    assert (out["uid"].to_numpy() == scored["uid"].to_numpy()).all()
    assert out.attrs["fit_rows"] == int(rows.p1_fit_rows(table, "R30", "VAL", "dam_like").sum())
    for column in ("p_B0", "p_B2", "p_PERS"):
        assert ((out[column] > 0) & (out[column] < 1)).all()


# ---------------------------------------------------------------------------
# G2
# ---------------------------------------------------------------------------
def test_g2_features_are_the_29_causal_columns():
    for kind in rows.P1_KINDS:
        features = g2.g2_features(kind)
        assert len(features) == 29
        assert f"dam_rate_{kind}" in features
        assert not set(features) & (spec.FORBIDDEN_COLUMNS | spec.LABEL_COLUMNS)
    assert "low365_D0" in g2.g2_features("D0g")                # D0-gradual uses D0's "low" definition


def test_rescue_dam_rate_leaves_out_the_rows_own_year():
    fit = pd.DataFrame({"uid": ["a"] * 4, "warm": [True] * 4, "hydro_year": [2000, 2000, 2001, 2001]})
    y = np.array([1, 1, 0, 0])                                 # pooled warm rate = 0.5
    scored = pd.DataFrame({"uid": ["a", "new"], "warm": [True, True]})
    fit_rate, scored_rate = g2.rescue_dam_rate(fit, y, scored, k=20)
    # A 2000 row sees only 2001 (0 of 2); a 2001 row sees only 2000 (2 of 2).
    assert fit_rate == pytest.approx([10 / 22, 10 / 22, 12 / 22, 12 / 22])
    # Scored rows see the whole fit block; a dam with no fit rows gets the pooled rate.
    assert scored_rate == pytest.approx([12 / 24, 0.5])


@pytest.mark.parametrize("variant", list(g2.VARIANTS))
def test_g2_learns_only_from_purged_fit_rows_and_predicts_every_val_forecast(variant):
    table = synthetic_p1()
    predictions, info = g2.fit_and_predict(table, "R30", "VAL", variant)
    population = g2.VARIANTS[variant]["train_on"]
    assert info["fit_rows"] == int(rows.p1_fit_rows(table, "R30", "VAL", population).sum())
    assert len(predictions) == int(rows.p1_block_rows(table, "R30", "VAL").sum())
    assert pd.DatetimeIndex(predictions["issue_date"]).min() >= pd.Timestamp("2009-01-01")
    assert predictions["p"].dtype == np.float64
    assert ((predictions["p"] > 0) & (predictions["p"] < 1)).all()
