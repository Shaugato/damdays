"""Small, hand-checkable tests of the feature rules that are about time and causality.

Each test builds a tiny made-up series where the right answer is obvious, so
a reader can verify the rule by eye. None of them read real data.
"""
import numpy as np
import pandas as pd
import pytest

from damdays import config
from damdays.features import checkpoints, dam_history, issues, neighbours, rain, season, spec
from damdays.features.common import day_numbers, days_since, year_month_before


# ---------------------------------------------------------------------------
# Labels: an event counts if it starts in (D, D+90]
# ---------------------------------------------------------------------------
def test_event_window_is_open_at_the_issue_and_closed_at_90_days():
    event_days = np.array([100])
    issue_days = np.array([100, 99, 10, 9])   # on the event day, 1 day before, 90 days before, 91 days before
    assert list(issues.any_event_in_window(event_days, issue_days)) == [False, True, True, False]


def test_label_ok_needs_three_looks_and_a_closed_window():
    days = np.array([0, 10, 20, 30, 100])
    events = {k: issues.EMPTY for k in ("D0", "R30", "D0g", "D0ab")}
    out = issues.labels(days, events, data_end_day=100)
    # day 0 sees looks 10, 20, 30 in (0, 90]; day 10 sees 20, 30, 100 in (10, 100]
    assert list(out["n_obs_win"]) == [3, 3, 2, 1, 0]
    assert list(out["window_closed"]) == [True, True, False, False, False]
    assert list(out["label_ok"]) == [True, True, False, False, False]


def test_abrupt_only_window_gives_missing_gradual_label():
    days = np.array([0, 50, 200])
    events = {"D0": np.array([60]), "R30": issues.EMPTY, "D0g": issues.EMPTY, "D0ab": np.array([60])}
    out = issues.labels(days, events, data_end_day=1000)
    assert out["y_D0"][0] == 1 and np.isnan(out["y_D0g"][0])   # only an abrupt D0 in the window
    assert out["y_D0g"][2] == 0


# ---------------------------------------------------------------------------
# Track record: a past forecast counts only once its answer is final (+120 days)
# ---------------------------------------------------------------------------
def test_past_forecast_counts_only_after_its_window_plus_30_days():
    days = np.array([0, 119, 120, 121])
    months = np.full(4, 11)                     # all in the same (warm) half-year
    risk = {"at_risk_D0": np.ones(4, bool), "at_risk_R30": np.ones(4, bool)}
    label_cols = {"label_ok": np.ones(4, bool), "y_D0": np.array([1.0, 0, 0, 0]),
                  "y_R30": np.zeros(4), "y_D0g": np.zeros(4)}
    out = issues.track_record(days, months, risk, label_cols)
    # The day-0 forecast (a hit) becomes usable on day 120 = 0 + 90 + 30, not before.
    assert list(out["b2N_D0"]) == [0, 0, 1, 1]
    assert list(out["b2S_D0"]) == [0, 0, 1, 1]


def test_track_record_keeps_the_half_years_apart():
    days = np.array([0, 200])
    months = np.array([11, 5])                  # November (warm) then May (cool)
    risk = {"at_risk_D0": np.ones(2, bool), "at_risk_R30": np.ones(2, bool)}
    label_cols = {"label_ok": np.ones(2, bool), "y_D0": np.array([1.0, 0]),
                  "y_R30": np.zeros(2), "y_D0g": np.zeros(2)}
    out = issues.track_record(days, months, risk, label_cols)
    assert out["b2N_D0"][1] == 0                # the November forecast does not count for May


# ---------------------------------------------------------------------------
# Dam history: trailing windows end at the current look
# ---------------------------------------------------------------------------
def test_trailing_slope_uses_only_the_window():
    days = np.array([0, 30, 60, 90])
    level = np.array([1.0, 0.7, 0.4, 0.4])
    slope = dam_history.trailing_slope(days, level, 60)       # window (day - 60, day]
    assert np.isnan(slope[0])                                  # one look: no slope
    assert slope[1] == pytest.approx(-0.01)                    # looks 0 and 30
    assert slope[3] == pytest.approx(0.0)                      # looks 60 and 90 only (look 30 is 60 days old);
    #                                                            with look 30 included it would be -0.005


def test_days_since_counts_from_the_last_flagged_look():
    days = np.array([0, 10, 25, 40])
    flag = np.array([False, True, False, False])
    assert list(days_since(flag, days)) == [config.DAYS_CAP, 0, 15, 30]


def test_days_to_threshold_is_capped_when_not_falling():
    out = dam_history.days_to_threshold(np.array([0.9, 0.9, 0.2]), np.array([-0.01, 0.0, -0.01]), 0.3)
    assert out[0] == pytest.approx(np.log1p(60))     # (0.9 - 0.3) / 0.01 = 60 days
    assert out[1] == pytest.approx(np.log1p(config.DAYS_CAP))
    assert out[2] == 0                               # already below the threshold


# ---------------------------------------------------------------------------
# Checkpoints: only looks before 1 Jan of the year
# ---------------------------------------------------------------------------
def test_checkpoint_ignores_looks_from_its_own_year_on():
    dates = pd.to_datetime([f"1998-{m:02d}-01" for m in range(1, 13)] + ["1999-01-01"])
    days = day_numbers(dates)
    pc = np.r_[np.full(12, 50.0), 100.0]           # the big 1 Jan 1999 look must not count for 1999
    px = pc / 10
    out = checkpoints.dam_checkpoints(days, pc, px, dates.month.to_numpy(), np.full(13, 1998))
    k = 1999 - config.FIRST_CHECKPOINT_YEAR
    assert out["n_hist_c"][k] == 12
    assert np.isnan(out["full_c"][k])             # fewer than 20 looks: full is not trusted yet
    assert checkpoints.checkpoint_index(np.array([1986, 1987, 2020]))[[0, 2]].tolist() == [-1, 2016 - 1987]


# ---------------------------------------------------------------------------
# Neighbours: strictly earlier looks, at most 30 days old
# ---------------------------------------------------------------------------
def test_grid_uses_looks_strictly_before_the_grid_date_and_at_most_30_days_old():
    look_days = np.array([100, 130])
    grid_days = np.array([100, 101, 131, 161])
    j = neighbours.last_look_before(look_days, grid_days)
    # day 100: the look ON day 100 is excluded; day 161: the day-130 look is 31 days old
    assert list(j) == [-1, 0, 1, -1]


def test_fast_column_median_matches_numpy():
    rng = np.random.default_rng(1)
    values = rng.normal(size=(50, 40))
    values[rng.random(values.shape) < 0.3] = np.nan
    values[:, 0] = np.r_[np.full(45, np.nan), np.arange(5.0)]      # a column with 5 known values
    assert np.allclose(neighbours.column_medians(values), np.nanmedian(values, axis=0))


def test_dam_is_never_its_own_neighbour():
    lat = np.array([-33.0, -33.01, -33.02])
    lon = np.array([148.0, 148.0, 148.0])
    lists = neighbours.neighbour_lists(["a", "b", "c"], lat, lon)
    assert [list(x) for x in lists] == [[1, 2], [0, 2], [0, 1]]


# ---------------------------------------------------------------------------
# Rain: window ends the month before the issue month; baselines are earlier years
# ---------------------------------------------------------------------------
def test_rain_window_ends_the_month_before_the_issue():
    assert list(year_month_before(pd.to_datetime(["2014-07-09", "2015-01-01"]))) == [201406, 201412]


def test_causal_percentile_does_not_change_when_later_years_change():
    months = np.array([y * 100 + 1 for y in range(1960, 1990)])     # January of 30 years
    rng = np.random.default_rng(0)
    totals = rng.uniform(0, 100, size=(1, len(months)))
    changed = totals.copy()
    changed[0, -5:] = 1000.0                                          # make 1985-1989 extremely wet
    before = rain.causal_percentiles(totals, months)
    after = rain.causal_percentiles(changed, months)
    early = months < 198500
    assert np.array_equal(before[:, early], after[:, early], equal_nan=True)
    assert np.isnan(before[0, 5])                                     # 1965: only 5 earlier years (< 10)


def test_rain_month_still_running_at_the_newest_look_is_never_used():
    """With the archive ending on 14 Sep 2026, September 2026 is a partial total: blanked, with every window
    that contains it. August 2026 ended before the newest look and is kept."""
    months = np.array([202606, 202607, 202608, 202609])
    rain_by_cell = {"rain": np.array([[40.0, 50.0, 30.0, 5.0]]), "months": months, "cells": np.array(["c"])}
    feats = rain.build_rain_features(rain_by_cell, data_end=pd.Timestamp("2026-09-14"))
    assert feats["features"]["rain_sum1"][0, 2] == 30.0                # August: complete, kept
    assert feats["features"]["rain_sum3"][0, 2] == 120.0               # Jun-Aug window: complete, kept
    assert np.isnan(feats["features"]["rain_sum1"][0, 3])              # September: still running, blanked
    assert np.isnan(rain.lookup(feats, ["c"], [202609])["rain_sum1"][0])
    # A look ON the last day of a month does not finish that month either.
    on_last_day = rain.build_rain_features(rain_by_cell, data_end=pd.Timestamp("2026-08-31"))
    assert np.isnan(on_last_day["features"]["rain_sum1"][0, 2])


# ---------------------------------------------------------------------------
# Season rating: state from the last look before 1 Jul, at most 60 days old
# ---------------------------------------------------------------------------
def test_season_state_comes_from_before_1_july():
    issue = season.issue_days([2010, 2011])
    look_days = np.array([issue[0] - 61, issue[1] - 10, issue[1]])  # the 1 Jul 2011 look itself is not used
    j, age = season.state_look(look_days, issue)
    assert list(j) == [0, 1] and list(age) == [61, 10]


# ---------------------------------------------------------------------------
# FEATURE_SPEC
# ---------------------------------------------------------------------------
def test_feature_spec_has_no_labels_or_static_prereg_columns():
    for kind in ("R30", "D0", "D0g"):
        columns = spec.p1_tree_features(kind)
        assert len(columns) == len(set(columns)) == 29
        assert not set(columns) & (spec.LABEL_COLUMNS | spec.FORBIDDEN_COLUMNS)
        assert not {"n_hist_c", "b2S_D0", "b2N_D0", "b2S_R30", "b2N_R30"} & set(columns)  # PREREG: no raw counts in P1 trees
    assert "dam_rate_D0g" in spec.p1_tree_features("D0g") and "low365_D0" in spec.p1_tree_features("D0g")
    with pytest.raises(ValueError):
        spec.check_feature_list(["rel", "full"])
    with pytest.raises(ValueError):
        spec.check_feature_list(["rel", "y_R30"])


def test_every_spec_column_exists_in_the_built_tables():
    """FEATURE_SPEC must name real columns (skipped until scripts/02_build_features.py has run)."""
    from damdays.features import store
    if not (store.FEATURES_DIR / "p1_dam.pkl").exists():
        pytest.skip("needs data_cache/features/p1_dam.pkl (not in git; scripts/02_build_features.py builds it)")
    p1_columns = set(store.load_p1(groups=("dam", "nbr")).columns)
    for kind in ("R30", "D0", "D0g"):
        assert set(spec.p1_tree_features(kind)) <= p1_columns
    assert set(spec.P2_FEATURE_SPEC) <= set(store.load_p2("dam").columns)
    assert set(spec.RAIN_INPUTS + spec.RAIN_PLUS_INPUTS) <= set(store.load_p2("cell").columns)
    assert not p1_columns & {"full", "wet_share", "fill_share"}    # the static PREREG values are not even present
