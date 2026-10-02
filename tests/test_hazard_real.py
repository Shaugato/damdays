"""The runway curve H on real data: truncation and placebo tests, and hand checks on single dams.

* LABELS. Every 30/60/90/180-day label equals "an event of that kind starts
  in (D, D + h]", read straight from the event list (data_cache/events.pkl).
* TRUNCATION. Keep only the events that were CONFIRMED before 1 Jan 2009 (what
  an observer on that day could know). The censored person-period rows that
  teach H for VAL must not change at all. Positive control: without
  censoring, the same truncation does change them.
* PLACEBO, END TO END. Replace every answer from 2009 on with random noise and
  refit H for R30: the VAL curves must be bit-for-bit the same.
* PLACEBO FOR B2_h. Scramble every answer (and whether it is known) that was
  not final by 9 Jul 2012: B2_h for forecasts up to that day must not move.
  Positive control: under the pre-event counting rule the 30-day B2 does move,
  which is why the baselines wait for label_ok (hazard.baseline_wait_days).
* HAND CHECKS. For two named VAL forecasts the four hazards are predicted one
  interval at a time and the curve is multiplied out by hand.

Needs data_cache/events.pkl and data_cache/features/ (scripts/01 and 02);
skipped otherwise. About 2 minutes (two LightGBM fits).
"""
import pickle

import numpy as np
import pandas as pd
import pytest

from damdays import config
from damdays.features import store
from damdays.features.common import day_numbers
from damdays.models import hazard, rows

CUTOFF = hazard.cutoff_day("VAL")                   # 2009-01-01
PLACEBO_DAY = "2012-07-09"
# (dam, VAL issue date) forecasts checked by hand: one per region, both with an R30 event 2-3 months later.
HAND_CHECKED = [("r1hzbg6g9_v3", "2015-10-14"), ("r61mrfnfz_v3", "2009-01-09")]


@pytest.fixture(scope="module")
def data():
    """The P1 table, the event list and the data end date (skip if not built)."""
    if not (config.CACHE_DIR / "events.pkl").exists() or not (store.FEATURES_DIR / "p1_keys.pkl").exists():
        pytest.skip("data_cache/ is not built; run scripts/01_build_data.py and scripts/02_build_features.py")
    table = store.load_p1(groups=("keys", "dam", "nbr"))
    events = pd.read_pickle(config.CACHE_DIR / "events.pkl")
    events = events.assign(start=day_numbers(events["start_date"]), confirm=day_numbers(events["confirm_date"]))
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as handle:
        data_end = pd.Timestamp(pickle.load(handle)["data_end"])
    return dict(table=table, events=events, data_end=data_end,
                issue_days=day_numbers(table["issue_date"].to_numpy()), uid=table["uid"].astype(str).to_numpy())


def days_to_next_start(data, starts):
    """Days from every issue to the next event start in `starts` (a sorted day array per dam); inf if none."""
    out = np.full(len(data["table"]), np.inf)
    for uid, positions in pd.Series(np.arange(len(out))).groupby(data["uid"]).indices.items():
        dam_starts = starts.get(uid)
        if dam_starts is None or len(dam_starts) == 0:
            continue
        issue = data["issue_days"][positions]
        k = np.searchsorted(dam_starts, issue, side="right")    # first start strictly after the issue
        has_next = k < len(dam_starts)
        out[positions[has_next]] = dam_starts[k[has_next]] - issue[has_next]
    return out


def event_starts(events, kind, confirmed_before=None):
    """Sorted event start days per dam, optionally only events confirmed before a day."""
    chosen = events[events["kind"] == kind]
    if confirmed_before is not None:
        chosen = chosen[chosen["confirm"] < confirmed_before]
    return {uid: np.sort(g["start"].to_numpy()) for uid, g in chosen.groupby(chosen["uid"].astype(str))}


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", hazard.CURVE_KINDS)
def test_horizon_labels_match_the_event_list(data, kind):
    labels = hazard.horizon_labels(data["table"], kind, data["data_end"])
    to_next = days_to_next_start(data, event_starts(data["events"], kind))
    for h in hazard.HORIZONS:
        y = labels[f"y_{h}"].to_numpy()
        known = ~np.isnan(y)
        assert np.array_equal(y[known], (to_next[known] <= h).astype(float)), h
    assert (data["events"]["confirm"] - data["events"]["start"]).max() <= hazard.CONFIRM_DAYS


# ---------------------------------------------------------------------------
# Truncation: only what was known on 1 Jan 2009 can teach the VAL model
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", hazard.CURVE_KINDS)
def test_training_rows_unchanged_when_later_events_are_deleted(data, kind):
    issues = hazard.hazard_fit_issues(data["table"], kind, "VAL", "dam_like")
    issue_days = data["issue_days"][issues]
    full = hazard.days_to_event(data["table"].loc[issues], kind)
    truncated = days_to_next_start(data, event_starts(data["events"], kind, confirmed_before=CUTOFF))[issues]
    for a, b in zip(hazard.person_period(issue_days, full, CUTOFF), hazard.person_period(issue_days, truncated, CUTOFF)):
        assert np.array_equal(a, b)
    # Positive control: with no censoring the deleted events would have changed the training rows.
    far_future = CUTOFF + 10_000
    uncensored = [hazard.person_period(issue_days, tte, far_future) for tte in (full, truncated)]
    assert len(uncensored[0][2]) != len(uncensored[1][2])


# ---------------------------------------------------------------------------
# Placebo, end to end: random answers from 2009 on do not move the VAL curve
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def r30_fits(data):
    """H for R30 fitted on the real table and on a copy whose answers from 2009 on are random noise."""
    rng = np.random.default_rng(2026)
    table = data["table"]
    scrambled = table.copy()
    late = data["issue_days"] >= CUTOFF
    for kind in hazard.CURVE_KINDS:
        # Events confirmed only after the cutoff are dropped; answers of issues from 2009 on become noise.
        tte = days_to_next_start(data, event_starts(data["events"], kind, confirmed_before=CUTOFF))
        tte[late] = rng.integers(1, 400, late.sum())
        scrambled[f"lab_tte_{kind}"] = np.where(np.isinf(tte), np.nan, tte)
        scrambled.loc[late, f"y_{kind}"] = rng.integers(0, 2, late.sum()).astype(float)
    real_model, _ = hazard.fit_hazard(table, "R30", "VAL")
    placebo_model, _ = hazard.fit_hazard(scrambled, "R30", "VAL")
    X = table.loc[rows.p1_block_rows(table, "R30", "VAL"), hazard.hazard_features("R30")].to_numpy(dtype=np.float32)
    return dict(model=real_model, real=hazard.predict_hazards(real_model, X),
                placebo=hazard.predict_hazards(placebo_model, X))


def test_val_curve_unchanged_when_answers_after_the_cutoff_are_noise(r30_fits):
    assert np.array_equal(r30_fits["real"], r30_fits["placebo"])


# ---------------------------------------------------------------------------
# Hand checks on single forecasts
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("uid, issue_date", HAND_CHECKED)
def test_curve_by_hand_for_one_forecast(data, r30_fits, uid, issue_date):
    table = data["table"]
    val_rows = table.loc[rows.p1_block_rows(table, "R30", "VAL")]
    position = int(np.flatnonzero((val_rows["uid"].astype(str) == uid).to_numpy()
                                  & (val_rows["issue_date"] == pd.Timestamp(issue_date)).to_numpy())[0])
    inputs = val_rows.iloc[position][hazard.hazard_features("R30")].to_numpy(dtype=np.float32)
    survive, curve = 1.0, []
    for start, end in zip(hazard.INTERVAL_EDGES[:-1], hazard.INTERVAL_EDGES[1:]):
        one_row = np.array([list(inputs) + [start, end - start]], dtype=np.float32)
        survive *= 1.0 - float(r30_fits["model"].predict_proba(one_row)[0, 1])   # no event in this interval
        curve.append(1.0 - survive)
    assert np.allclose(curve, hazard.curve_from_hazards(r30_fits["real"][[position]])[0], rtol=0, atol=1e-12)
    # The labels by hand: the dam's next R30 start, read from the event list.
    starts = event_starts(data["events"], "R30")[uid]
    issue_day = int(day_numbers([pd.Timestamp(issue_date)])[0])
    wait = starts[starts > issue_day][0] - issue_day
    labels = hazard.horizon_labels(val_rows.iloc[[position]], "R30", data["data_end"])
    assert labels.iloc[0].tolist() == [float(wait <= h) for h in hazard.HORIZONS]


# ---------------------------------------------------------------------------
# Placebo for B2_h: answers not final on a day cannot move B2_h on or before that day
# ---------------------------------------------------------------------------
def scramble_not_final(y_h, issue_days, wait_days, day, rng):
    """Random answers (and random 'not known') for every forecast whose answer is not final on `day`."""
    out = y_h.copy()
    not_final = issue_days + wait_days > day
    out[not_final] = np.where(rng.random(not_final.sum()) < 0.3, np.nan, rng.integers(0, 2, not_final.sum()))
    return out


@pytest.mark.parametrize("kind", hazard.CURVE_KINDS)
def test_b2_h_unchanged_when_answers_not_final_yet_are_scrambled(data, kind):
    rng = np.random.default_rng(7)
    table, issue_days = data["table"], data["issue_days"]
    placebo_day = int(day_numbers([pd.Timestamp(PLACEBO_DAY)])[0])
    up_to_day = issue_days <= placebo_day
    labels = hazard.horizon_labels(table, kind, data["data_end"])
    for h in hazard.HORIZONS:
        y_h = labels[f"y_{h}"].to_numpy()
        scrambled = scramble_not_final(y_h, issue_days, hazard.baseline_wait_days(h), placebo_day, rng)
        for a, b in zip(hazard.own_past_counts(table, kind, y_h, h), hazard.own_past_counts(table, kind, scrambled, h)):
            assert np.array_equal(a[up_to_day], b[up_to_day]), h
    # Positive control. Forecasts issued 60-90 days before the day have a final 30-day answer, but whether
    # their 90-day window gets 3 looks (label_ok) is not known yet. Pretend those windows came out short
    # (label unknown): the pre-event rule (count after 60 days) changes B2_30 up to the day; the rule used now does not.
    y_30 = labels["y_30"].to_numpy()
    pending = (issue_days + 60 <= placebo_day) & (issue_days + 90 > placebo_day) & ~np.isnan(y_30)
    short_windows = np.where(pending, np.nan, y_30)
    pre_event = [hazard.own_past_counts(table, kind, y, 30, pre_event_recipe=True)[1] for y in (y_30, short_windows)]
    now = [hazard.own_past_counts(table, kind, y, 30)[1] for y in (y_30, short_windows)]
    assert not np.array_equal(pre_event[0][up_to_day], pre_event[1][up_to_day])
    assert np.array_equal(now[0][up_to_day], now[1][up_to_day])
