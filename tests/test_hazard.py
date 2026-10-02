"""Small, hand-checkable tests of the runway curve H (damdays/models/hazard.py).

The rules worth proving are about time: an interval is learned from only once
its answer was final before the cutoff (censoring), and a dam's past forecast
counts in B2_h only once its h-day answer was final. The rest check the curve
arithmetic. None of these tests read real data.
"""
import numpy as np
import pandas as pd

from damdays.features.common import day_numbers
from damdays.models import hazard


def day(text):
    """Day number of a date written as text."""
    return int(day_numbers([pd.Timestamp(text)])[0])


# ---------------------------------------------------------------------------
# Censoring: each interval is kept only once its answer is final before the cutoff
# ---------------------------------------------------------------------------
def test_person_period_censors_each_interval_at_the_cutoff():
    cutoff = day("2009-01-01")
    issue_days = np.array([
        day("2008-11-01"),   # +30 +30 = 2008-12-31: first interval only
        day("2008-11-02"),   # +30 +30 = 2009-01-01: not before the cutoff, nothing kept
        day("2008-01-01"),   # +180 +30 is still in 2008: all four intervals
        day("2008-01-01"),   # the same day, but the event starts on day 45: intervals 1 and 2 only
    ])
    tte = np.array([np.inf, np.inf, np.inf, 45.0])
    position, interval, label = hazard.person_period(issue_days, tte, cutoff)
    kept = sorted(zip(position.tolist(), interval.tolist(), label.tolist()))
    assert kept == [(0, 0, 0),
                    (2, 0, 0), (2, 1, 0), (2, 2, 0), (2, 3, 0),
                    (3, 0, 0), (3, 1, 1)]          # the event (day 45) is inside (30, 60]; no rows after it


def test_event_on_an_interval_edge_belongs_to_the_earlier_interval():
    position, interval, label = hazard.person_period(np.array([day("2000-01-01")]), np.array([30.0]),
                                                     day("2009-01-01"))
    assert list(zip(interval.tolist(), label.tolist())) == [(0, 1)]   # (0, 30] includes day 30


# ---------------------------------------------------------------------------
# The curve
# ---------------------------------------------------------------------------
def test_curve_from_hazards_by_hand_and_never_falls():
    hazards = np.array([[0.1, 0.2, 0.5, 0.0]])
    curve = hazard.curve_from_hazards(hazards)
    # 1 - 0.9 = 0.1; 1 - 0.9*0.8 = 0.28; 1 - 0.72*0.5 = 0.64; unchanged with a zero hazard
    assert np.allclose(curve, [[0.1, 0.28, 0.64, 0.64]])
    random = hazard.curve_from_hazards(np.random.default_rng(0).random((1000, 4)))
    assert (np.diff(random, axis=1) >= 0).all()


def test_max_rule_raises_r30_to_the_d0_curve_and_keeps_it_monotone():
    r30 = np.array([[0.10, 0.20, 0.30, 0.40]])
    d0 = np.array([[0.15, 0.18, 0.35, 0.36]])
    out = hazard.max_rule(r30, d0)
    assert np.allclose(out, [[0.15, 0.20, 0.35, 0.40]])
    assert (np.diff(out, axis=1) >= 0).all() and (out >= d0).all()


# ---------------------------------------------------------------------------
# Labels at every horizon
# ---------------------------------------------------------------------------
def test_horizon_labels_known_only_inside_the_data():
    table = pd.DataFrame({
        "issue_date": pd.to_datetime(["2020-01-01", "2020-01-01", "2026-05-01", "2020-01-01"]),
        "lab_tte_R30": [45.0, np.nan, 10.0, 200.0],
        "label_ok": [True, True, True, False],
        "y_R30": [1.0, 0.0, 1.0, 0.0],
    })
    labels = hazard.horizon_labels(table, "R30", data_end="2026-09-14")
    assert labels.loc[0].tolist() == [0.0, 1.0, 1.0, 1.0]       # event on day 45
    assert labels.loc[1].tolist() == [0.0, 0.0, 0.0, 0.0]       # no event in the data
    # 2026-05-01 + 180 days is after the data ends: the 180-day answer is not known yet
    assert labels.loc[2, ["y_30", "y_60", "y_90"]].tolist() == [1.0, 1.0, 1.0] and np.isnan(labels.loc[2, "y_180"])
    assert labels.loc[3].isna().all()                           # label_ok False: nothing is known


# ---------------------------------------------------------------------------
# B2_h: a past forecast counts only once its answer was final
# ---------------------------------------------------------------------------
def test_baselines_wait_for_the_answer_and_for_label_ok():
    # The h-day answer is final after h + 30 days; label_ok (3 looks in 90 days) after 90 days.
    assert [hazard.baseline_wait_days(h) for h in hazard.HORIZONS] == [90, 90, 120, 210]
    assert [hazard.baseline_wait_days(h, pre_event_recipe=True) for h in hazard.HORIZONS] == [60, 90, 120, 210]


def test_own_past_counts_wait_for_the_answer():
    dates = pd.to_datetime(["2000-10-01", "2000-11-01", "2001-01-15", "2001-02-05", "2001-05-01"])
    table = pd.DataFrame({
        "uid": ["damA"] * 5, "issue_date": dates,
        "warm": np.isin(dates.month, [10, 11, 12, 1, 2, 3]),
        "at_risk_R30": [True, True, True, True, True],
    })
    y_30 = np.array([1.0, 0.0, 0.0, 1.0, 1.0])
    hits, count = hazard.own_past_counts(table, "R30", y_30, horizon=30)
    # A 30-day answer counts 90 days after its issue (label_ok needs the whole 90-day window).
    # 2000-10-01 + 90 = 2000-12-30: final on 2001-01-15. 2000-11-01 + 90 = 2001-01-30: final on 2001-02-05.
    # The May issue is in the other half-year, so it sees none of the Oct-Mar forecasts.
    assert count.tolist() == [0, 0, 1, 2, 0]
    assert hits.tolist() == [0, 0, 1, 1, 0]
    # The pre-event recipe waited only 30 + 30 days: on 2001-01-15 both 2000 forecasts already counted.
    hits, count = hazard.own_past_counts(table, "R30", y_30, horizon=30, pre_event_recipe=True)
    assert count.tolist() == [0, 0, 2, 2, 0]
    assert hits.tolist() == [0, 0, 1, 1, 0]


def random_issue_table(seed, n_dams=6, per_dam=150):
    """Made-up issues: several dams, random dates 1995-2012, random at-risk flags."""
    rng = np.random.default_rng(seed)
    uids = np.repeat([f"dam{i}" for i in range(n_dams)], per_dam)
    days = rng.integers(day("1995-01-01"), day("2012-12-31"), len(uids))
    dates = pd.to_datetime(days, unit="D")
    return pd.DataFrame({"uid": uids, "issue_date": dates, "warm": np.isin(dates.month, [10, 11, 12, 1, 2, 3]),
                         "at_risk_R30": rng.random(len(uids)) < 0.8}), rng


def test_own_past_counts_equal_a_slow_count():
    table, rng = random_issue_table(seed=3)
    y_h = np.where(rng.random(len(table)) < 0.2, np.nan, (rng.random(len(table)) < 0.3).astype(float))
    days = day_numbers(table["issue_date"].to_numpy())
    for h in hazard.HORIZONS:
        hits, count = hazard.own_past_counts(table, "R30", y_h, h)
        wait = hazard.baseline_wait_days(h)
        for i in range(len(table)):
            earlier = ((table["uid"] == table["uid"].iloc[i]) & (table["warm"] == table["warm"].iloc[i])
                       & table["at_risk_R30"] & ~np.isnan(y_h) & (days + wait <= days[i])).to_numpy()
            assert count[i] == earlier.sum() and hits[i] == y_h[earlier].sum()


def test_own_past_counts_ignore_answers_that_are_not_final_yet():
    """Placebo: scramble every answer (and whether it is known) that is not final on day T; B2_h up to T must not move."""
    table, rng = random_issue_table(seed=4)
    y_h = (rng.random(len(table)) < 0.3).astype(float)
    days = day_numbers(table["issue_date"].to_numpy())
    t = day("2005-07-09")
    for h in hazard.HORIZONS:
        not_final = days + hazard.baseline_wait_days(h) > t
        scrambled = y_h.copy()
        scrambled[not_final] = np.where(rng.random(not_final.sum()) < 0.5, np.nan, rng.integers(0, 2, not_final.sum()))
        before = hazard.own_past_counts(table, "R30", y_h, h)
        after = hazard.own_past_counts(table, "R30", scrambled, h)
        up_to_t = days <= t
        for a, b in zip(before, after):
            assert np.array_equal(a[up_to_t], b[up_to_t])
        assert any(not np.array_equal(a[~up_to_t], b[~up_to_t]) for a, b in zip(before, after))   # it can fail


def test_baseline_fit_rows_wait_for_label_ok_before_the_cutoff():
    table = pd.DataFrame({
        "issue_date": pd.to_datetime(["2008-10-01", "2008-10-15", "2008-09-01", "2009-02-01"]),
        "at_risk_R30": [True, True, True, True], "dam_like": [True, True, True, True],
    })
    y = np.zeros(4)
    keep_30 = hazard.horizon_baseline_fit_rows(table, "R30", "VAL", 30, y, "dam_like")
    keep_90 = hazard.horizon_baseline_fit_rows(table, "R30", "VAL", 90, y, "dam_like")
    # 2008-10-15: its 30-day answer is final on 2008-12-14, but its 90-day look count (label_ok) only on
    # 2009-01-13, after the cutoff: not used. 2009-02-01 is a VAL issue: never a fit row.
    assert keep_30.tolist() == [True, False, True, False]
    assert keep_90.tolist() == [False, False, True, False]     # 90 + 30 days: 2008-09-01 + 120 = 2008-12-30


# ---------------------------------------------------------------------------
# Censoring placebo: answers that were not final before the cutoff never reach the model
# ---------------------------------------------------------------------------
def test_person_period_ignores_answers_after_the_cutoff():
    rng = np.random.default_rng(5)
    cutoff = day("2009-01-01")
    issue_days = rng.integers(day("2007-01-01"), day("2008-12-31"), 5000)
    tte = np.where(rng.random(5000) < 0.3, np.inf, rng.integers(1, 400, 5000).astype(float))
    # Replace every event that was not confirmed before the cutoff (start + 30 days) with noise.
    unknown = issue_days + tte + hazard.CONFIRM_DAYS >= cutoff
    noise = tte.copy()
    noise[unknown] = (cutoff - issue_days[unknown] - hazard.CONFIRM_DAYS) + rng.integers(0, 300, unknown.sum())
    for a, b in zip(hazard.person_period(issue_days, tte, cutoff), hazard.person_period(issue_days, noise, cutoff)):
        assert np.array_equal(a, b)
    # Positive control: without censoring (a cutoff far in the future) the noise does change the training rows.
    far = cutoff + 10_000
    changed = [not np.array_equal(a, b) for a, b in zip(hazard.person_period(issue_days, tte, far),
                                                         hazard.person_period(issue_days, noise, far))]
    assert any(changed)


# ---------------------------------------------------------------------------
# The whole fit on a tiny made-up table: the D0 curve is matched to the right R30 rows
# ---------------------------------------------------------------------------
def tiny_p1_table(seed=6, n_dams=12, per_dam=160):
    """Made-up P1 rows (2001-2012) with every hazard input; R30 at-risk rows are a random subset of D0's."""
    rng = np.random.default_rng(seed)
    n = n_dams * per_dam
    days = np.concatenate([rng.choice(np.arange(day("2001-01-01"), day("2012-12-31")), per_dam, replace=False)
                           for _ in range(n_dams)])                     # one issue per dam and day
    table = pd.DataFrame({"uid": np.repeat([f"dam{i}" for i in range(n_dams)], per_dam),
                          "issue_date": pd.to_datetime(days, unit="D"),
                          "label_ok": rng.random(n) < 0.9, "dam_like": True,
                          "at_risk_D0": True, "at_risk_R30": rng.random(n) < 0.6})
    columns = sorted(set(hazard.hazard_features("R30")) | set(hazard.hazard_features("D0")))
    for column in columns:
        table[column] = rng.normal(size=n)
    for kind, scale in (("R30", 120.0), ("D0", 250.0)):
        # Events come sooner when the first input is high, so the model has something to learn.
        tte = rng.exponential(scale * np.exp(-0.5 * table["rel"].to_numpy()))
        table[f"lab_tte_{kind}"] = np.ceil(tte)
    return table


def test_fit_and_predict_curves_matches_each_r30_row_with_its_own_d0_curve():
    table = tiny_p1_table()
    curves, infos = hazard.fit_and_predict_curves(table, "VAL")
    r30, d0 = curves["R30"], curves["D0"]
    assert infos["R30"]["person_period_rows"] > 0 and len(r30) < len(d0)
    joined = r30.merge(d0, on=["uid", "issue_date"], suffixes=("", "_from_d0"), validate="one_to_one")
    assert len(joined) == len(r30)
    for h in hazard.HORIZONS:
        assert np.array_equal(joined[f"d0_p_{h}"], joined[f"p_{h}_from_d0"])            # same dam, same day
        assert np.array_equal(joined[f"p_{h}"], np.maximum(joined[f"raw_p_{h}"], joined[f"d0_p_{h}"]))
    for frame in (r30, d0):
        assert (np.diff(hazard.curve_columns(frame), axis=1) >= 0).all()
        assert set(pd.DatetimeIndex(frame["issue_date"]).year) <= set(range(2009, 2016))
