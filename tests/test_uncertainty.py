"""Small, hand-checkable tests of the DamDays floor and the season band.

The rules worth proving are about time (a floor answer is final only 395
days after the forecast; an inner-backtest model knows nothing after its
cutoff) and the formulas (the finite-sample conformal rank, the display
rule, the band). None of these tests read real data.
"""
import numpy as np
import pandas as pd
import pytest

from damdays.evaluation import floor_coverage
from damdays.models import g2, rows
from damdays.models import uncertainty as unc


# ---------------------------------------------------------------------------
# A tiny made-up P1 table
# ---------------------------------------------------------------------------
def synthetic_p1(n_dams=10, seed=0):
    """Two looks a month per dam from 2000 to 2010, with every column the floor and band code reads."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2000-01-01", "2010-12-31", freq="SMS")
    frame = pd.DataFrame({"uid": np.repeat([f"dam{i:02d}" for i in range(n_dams)], len(dates)),
                          "issue_date": np.tile(dates, n_dams)})
    n = len(frame)
    frame["region"] = np.where(frame["uid"] < "dam05", "nsw_cw", "wvic_sesa")
    frame["warm"] = np.isin(frame["issue_date"].dt.month, [10, 11, 12, 1, 2, 3])
    frame["dam_like"] = True
    frame["at_risk_D0"] = True
    frame["at_risk_R30"] = rng.random(n) > 0.2
    frame["label_ok"] = rng.random(n) > 0.1
    for kind in rows.P1_KINDS:
        frame[f"y_{kind}"] = (rng.random(n) < 0.2).astype(float)
        frame[f"b2S_{kind}"] = rng.integers(0, 5, n).astype(float)
        frame[f"b2N_{kind}"] = frame[f"b2S_{kind}"] + rng.integers(0, 10, n)
    frame["lab_tte_R30"] = np.where(rng.random(n) < 0.3, np.nan, rng.integers(1, 600, n).astype(float))
    for column in {c for kind in rows.P1_KINDS for c in g2.g2_features(kind)}:
        frame[column] = rng.random(n)
    return frame


# ---------------------------------------------------------------------------
# Floor: time rules
# ---------------------------------------------------------------------------
def test_floor_answer_is_final_only_after_395_days():
    # 2007-12-01 + 395 days = 2008-12-30, before 2009-01-01: usable.
    # 2007-12-02 + 395 days = 2008-12-31, still before. 2007-12-03 + 395 = 2009-01-01: not before, so not usable.
    dates = pd.to_datetime(["2007-12-01", "2007-12-02", "2007-12-03", "2008-06-01"])
    assert unc.runway_answer_final(dates, "2009-01-01").tolist() == [True, True, False, False]


def test_floor_fit_rows_respect_the_cutoff_and_the_at_risk_rule():
    table = synthetic_p1()
    fit = unc.floor_fit_rows(table, "2009-01-01")
    last_usable = pd.Timestamp("2009-01-01") - pd.Timedelta(days=unc.FLOOR_ANSWER_FINAL_DAYS + 1)
    assert fit.any()
    assert (table.loc[fit, "issue_date"] <= last_usable).all()
    assert table.loc[fit, "at_risk_R30"].all() and table.loc[fit, "label_ok"].all()


def test_followup_leaves_30_days_to_confirm_a_fall():
    # Data end 2026-09-14. A fall starting after 2026-08-15 may still lack its confirming look.
    # Issue 2026-06-01: 75 days of usable follow-up (to 2026-08-15), not 105.
    follow = unc.followup_days(pd.to_datetime(["2026-06-01", "2016-07-01"]), "2026-09-14")
    assert follow[0] == 75
    assert follow[1] == (pd.Timestamp("2026-08-15") - pd.Timestamp("2016-07-01")).days


def test_late_unconfirmed_fall_is_not_counted_as_a_held_floor():
    # The dam really fell below a third on day 80 (2026-08-20), but the confirming look would be
    # on day 110, after the data end (2026-09-14): the archive shows no event (NaN).
    # A 90-day floor must then be "not judged", not "held".
    follow = unc.followup_days(pd.to_datetime(["2026-06-01"]), "2026-09-14")
    result = floor_coverage(np.array([90.0]), np.array([np.nan]), follow, n_boot=0)
    assert result["rows_judged"] == 0
    # With the raw span to the data end (105 days) it would have been judged and counted as held.
    assert floor_coverage(np.array([90.0]), np.array([np.nan]), np.array([105.0]), n_boot=0)["coverage"] == 1.0


def test_runway_days_caps_at_one_year_and_reads_no_event_as_one_year():
    table = pd.DataFrame({"lab_tte_R30": [30.0, 400.0, np.nan]})
    assert unc.runway_days(table).tolist() == [30.0, 365.0, 365.0]


# ---------------------------------------------------------------------------
# Floor: formulas
# ---------------------------------------------------------------------------
def test_conformal_shift_uses_the_finite_sample_rank():
    # n = 10, 90%: rank ceil(11 x 0.9) = 10, the largest score.
    assert unc.conformal_shift(np.arange(1, 11)) == 10
    # n = 19: rank ceil(20 x 0.9) = 18.
    assert unc.conformal_shift(np.arange(1, 20)) == 18


def test_floor_days_lowers_by_the_shift_and_stays_in_range():
    q10 = np.log1p([100.0, 100.0, 10_000.0])
    floors = unc.floor_days(q10, np.array([0.0, 50.0, 0.0]))
    assert floors[0] == pytest.approx(100.0)
    assert floors[1] == 0.0                       # a huge shift: no floor at all
    assert floors[2] == pytest.approx(365.0)      # never above the one-year cap


def test_display_rounds_down_and_shows_180_plus():
    assert unc.displayed_floor_days([0.5, 44.8, 179.99, 200.0]).tolist() == [0.0, 44.0, 179.0, 180.0]
    assert unc.floor_label(44.8) == "44 days"
    assert unc.floor_label(1.5) == "1 day"
    assert unc.floor_label(179.99) == "179 days"
    assert unc.floor_label(180.0) == "180+ days"
    assert unc.floor_label(365.0) == "180+ days"


def test_conformal_floor_reaches_90_percent_when_the_quantile_model_is_wrong():
    # True runways are log-normal; the "model" says their median, which is far too optimistic for a
    # 10% floor. Calibrating on one half and judging the other must bring coverage to about 90%.
    rng = np.random.default_rng(1)
    log_days = rng.normal(4.0, 0.8, 40_000)
    days = np.minimum(np.expm1(log_days), 365)
    q10 = np.clip(np.full(len(days), 4.0), 0, unc.LOG_CAP)
    calibrate, judge = slice(0, 20_000), slice(20_000, None)
    shift = unc.conformal_shift(unc.conformity_scores(q10[calibrate], days[calibrate]))
    held = days[judge] >= unc.floor_days(q10[judge], shift)
    assert held.mean() == pytest.approx(0.90, abs=0.01)
    assert np.mean(days[judge] >= np.expm1(q10[judge])) < 0.6      # without the shift: far below 90%


def test_leave_one_year_out_shifts_never_use_the_held_out_year():
    # Year 2001 has huge scores. Its own shift must ignore them; the other year's shift must see them.
    log_q10 = np.full(20, 3.0)
    days = np.r_[np.full(10, np.expm1(3.0)), np.full(10, 0.0)]       # scores 0 (year 2000) and 3 (year 2001)
    years = np.r_[np.full(10, 2000), np.full(10, 2001)]
    shifts = unc.leave_one_year_out_shifts(log_q10, days, years)
    assert shifts[2001] == pytest.approx(0.0)
    assert shifts[2000] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Season band
# ---------------------------------------------------------------------------
def test_answered_fit_rows_match_the_official_purge_at_2009():
    table = synthetic_p1()
    for kind in rows.P1_KINDS:
        assert np.array_equal(unc.answered_fit_rows(table, kind, "2009-01-01"), rows.p1_fit_rows(table, kind, "VAL"))


def test_dam_rate_as_of_ignores_answers_after_the_cutoff():
    table = synthetic_p1()
    # 2001-09-02 + 120 days = 2001-12-31: final before 2002-01-01. From 2001-09-03 on, not final.
    late = table["issue_date"] >= "2001-09-03"
    table.loc[late, "y_R30"] = 1.0
    table.loc[~late, "y_R30"] = 0.0
    rate = unc.dam_rate_as_of(table, "R30", "2002-01-01")
    k = 20
    expected = table["b2S_R30"] / (table["b2N_R30"] + k)               # prior = 0: only early answers count
    assert np.allclose(rate, expected, atol=1e-6)


def test_band_rows_keep_only_answers_final_before_the_cutoff():
    table = synthetic_p1()
    mask = unc.band_rows(table, "R30", "2002-01-01", "2009-01-01")
    dates = table.loc[mask, "issue_date"]
    assert (dates >= "2002-01-01").all()
    assert (dates + pd.Timedelta(days=120) < pd.Timestamp("2009-01-01")).all()
    assert np.isin(dates.dt.month, [10, 11, 12, 1, 2, 3]).all()


def test_band_probabilities_shift_the_log_odds():
    low, high = unc.band_probabilities(np.array([0.5]), (-1.0, 1.0))
    assert low[0] == pytest.approx(1 / (1 + np.e))
    assert high[0] == pytest.approx(np.e / (1 + np.e))


def test_leave_one_year_out_band_coverage_by_hand():
    offsets = pd.DataFrame({
        "region_year": ["a:2009", "b:2009", "a:2010", "b:2010", "a:2011", "b:2011"],
        "hydro_year": [2009, 2009, 2010, 2010, 2011, 2011],
        "offset": [-0.2, 0.1, -1.5, 0.0, 0.3, -0.1], "used": True})
    # 2010's band from 2009 and 2011 is [-0.2, 0.3]: a:2010 (-1.5) is outside, b:2010 inside.
    # 2011's band from 2009 and 2010 is [-1.5, 0.1]: a:2011 (+0.3) is outside.
    result = unc.leave_one_year_out_band_coverage(offsets)
    assert result["covered"] == 4 and set(result["missed"]) == {"a:2010", "a:2011"}
    # Adding an inner block that reaches -2 and +0.5 covers every year.
    inner = pd.DataFrame({"region_year": ["a:2003", "b:2003"], "hydro_year": [2003, 2003],
                          "offset": [-2.0, 0.5], "used": True})
    assert unc.leave_one_year_out_band_coverage(offsets, extra_offsets=inner)["covered"] == 6


# ---------------------------------------------------------------------------
# Placebo tests: scramble every answer that was NOT final at a cutoff; whatever
# is computed "as of the cutoff" must not change by a single bit.
# ---------------------------------------------------------------------------
def scramble_open_answers(table, cutoff, seed=5):
    """A copy of the table where every answer not final before `cutoff` is replaced by noise.

    * days to R30: an event start counts as known only if confirmed (+30 days) before the cutoff;
      later starts are erased ("no event seen"), which is the same as moving them further out.
    * 90-day labels and label_ok: replaced by coin flips where the window + 30 days is still open.
    """
    rng = np.random.default_rng(seed)
    out = table.copy()
    days = out["lab_tte_R30"].to_numpy(dtype=float)
    start = out["issue_date"] + pd.to_timedelta(np.nan_to_num(days, nan=1e5), unit="D")
    unknown = np.asarray(start + pd.Timedelta(days=30) >= pd.Timestamp(cutoff))
    out["lab_tte_R30"] = np.where(unknown, np.nan, days)
    open_window = ~unc.answer_known_before(out["issue_date"], cutoff)
    for kind in rows.P1_KINDS:
        labels = out[f"y_{kind}"].to_numpy(dtype=float).copy()
        labels[open_window] = rng.integers(0, 2, open_window.sum())
        out[f"y_{kind}"] = labels
    label_ok = out["label_ok"].to_numpy(dtype=bool).copy()
    label_ok[open_window] = rng.random(open_window.sum()) < 0.5
    out["label_ok"] = label_ok
    return out


def test_floor_model_ignores_answers_not_final_before_the_cutoff():
    table = synthetic_p1()
    later = np.asarray(table["issue_date"] >= "2009-01-01")
    model, info = unc.fit_floor_model(table, "2009-01-01")
    scrambled = scramble_open_answers(table, "2009-01-01")
    assert np.sum(scrambled["lab_tte_R30"].isna() & table["lab_tte_R30"].notna()) > 100   # the scramble bites
    model_s, info_s = unc.fit_floor_model(scrambled, "2009-01-01")
    assert info["fit_rows"] == info_s["fit_rows"]
    assert np.array_equal(unc.predict_log_q10(model, table, later), unc.predict_log_q10(model_s, table, later))


def test_floor_placebo_can_fail():
    # Same scramble, but 400 days too early: answers that WERE final now change, so the model must change.
    table = synthetic_p1()
    later = np.asarray(table["issue_date"] >= "2009-01-01")
    model, _ = unc.fit_floor_model(table, "2009-01-01")
    model_s, _ = unc.fit_floor_model(scramble_open_answers(table, "2007-11-28"), "2009-01-01")
    assert not np.array_equal(unc.predict_log_q10(model, table, later), unc.predict_log_q10(model_s, table, later))


def test_frozen_shift_ignores_answers_not_final_before_test():
    rng = np.random.default_rng(3)
    dates = pd.to_datetime("2009-01-01") + pd.to_timedelta(rng.integers(0, 7 * 365, 5_000), unit="D")
    log_q10 = rng.normal(4.0, 0.5, 5_000)
    days = np.minimum(np.expm1(rng.normal(4.2, 0.8, 5_000)), 365)
    open_answer = ~unc.runway_answer_final(dates, "2016-07-01")
    scrambled = np.where(open_answer, rng.integers(1, 366, 5_000), days)
    shift, n = unc.shift_from_answers_before(log_q10, days, dates, "2016-07-01")
    assert (shift, n) == unc.shift_from_answers_before(log_q10, scrambled, dates, "2016-07-01")
    # Using every VAL answer (the pre-event way) does see the scrambled answers.
    assert unc.conformal_shift(unc.conformity_scores(log_q10, days)) != \
        unc.conformal_shift(unc.conformity_scores(log_q10, scrambled))


def test_inner_g2_fit_ignores_labels_not_final_before_its_cutoff():
    table = synthetic_p1()
    mask = unc.band_rows(table, "R30", "2002-01-01", "2009-01-01")
    p, _ = unc.fit_predict_g2_at(table, "R30", "2002-01-01", mask,
                                 dam_rate=unc.dam_rate_as_of(table, "R30", "2002-01-01"))
    scrambled = scramble_open_answers(table, "2002-01-01")
    p_s, _ = unc.fit_predict_g2_at(scrambled, "R30", "2002-01-01", mask,
                                   dam_rate=unc.dam_rate_as_of(scrambled, "R30", "2002-01-01"))
    assert np.array_equal(p, p_s)


def test_inner_g2_fit_works_on_a_consolidated_table():
    # table.copy() merges the feature columns into one block; pandas copy-on-write then hands back
    # read-only arrays from to_numpy(). Overwriting the dam_rate column must still work.
    table = synthetic_p1().copy()
    mask = unc.band_rows(table, "R30", "2002-01-01", "2009-01-01")
    p, info = unc.fit_predict_g2_at(table, "R30", "2002-01-01", mask,
                                    dam_rate=unc.dam_rate_as_of(table, "R30", "2002-01-01"))
    assert len(p) == mask.sum() == info["predicted_rows"]
    assert np.all((p > 0) & (p < 1))
