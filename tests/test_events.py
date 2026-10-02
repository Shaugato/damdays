"""Prove the event rules on tiny made-up series.

Each test builds a dam's looks as (day, pc_wet) pairs. Unless a test says
otherwise the dam's "full" is 100, so rel is simply pc_wet / 100.
px_wet (wet pixels) is 0 exactly when pc_wet is 0.

Rules being tested (PREREG.md, damdays/data/events.py):
  arming        rel >= 0.60 at some look within the 180 days before the first low look
  D0            px_wet == 0 on 2 consecutive looks at most 30 days apart
  R30           rel < 0.30 on 2 consecutive looks at most 30 days apart
  re-arming     after an event the dam must refill to 60% before the next one
  abrupt D0     last wet look before the event had rel >= 0.40 and was <= 60 days earlier
"""
import numpy as np
import pandas as pd

from damdays.data.events import build_events, count_events, describe_abruptness, find_events


def make_series(looks):
    """(day, pc_wet) pairs -> days, pc_wet, px_wet arrays."""
    days = np.array([day for day, _ in looks])
    pc_wet = np.array([pc for _, pc in looks], dtype=float)
    px_wet = np.where(pc_wet > 0, np.maximum(1, np.round(pc_wet / 5)), 0.0)
    return days, pc_wet, px_wet


def start_days(kind, looks, full=100.0):
    """Days on which events of `kind` start."""
    days, pc_wet, px_wet = make_series(looks)
    return [int(days[e.start_index]) for e in find_events(days, pc_wet, px_wet, full, kind)]


def first_d0_is_abrupt(looks, full=100.0):
    """Abrupt flag of the first D0 event in the series."""
    days, pc_wet, px_wet = make_series(looks)
    first = find_events(days, pc_wet, px_wet, full, "D0")[0]
    abrupt, _ = describe_abruptness(days, pc_wet, px_wet, full, first.start_index)
    return abrupt


# ---------------------------------------------------------------------------
# The worked example in docs/DATA.md and events.py
# ---------------------------------------------------------------------------
def test_worked_example_from_the_docs():
    looks = [(0, 40), (14, 20), (28, 10), (42, 0), (56, 0), (70, 35)]  # full = 50
    assert start_days("R30", looks, full=50) == [28]
    assert start_days("D0", looks, full=50) == [42]
    assert first_d0_is_abrupt(looks, full=50) is False  # last wet look: rel 0.2 -> gradual


# ---------------------------------------------------------------------------
# Arming
# ---------------------------------------------------------------------------
def test_no_event_if_the_dam_never_reached_60_percent():
    looks = [(0, 59), (14, 20), (28, 0), (42, 0)]
    assert start_days("D0", looks) == []
    assert start_days("R30", looks) == []


def test_exactly_60_percent_arms_the_dam():
    looks = [(0, 60), (14, 0), (28, 0)]
    assert start_days("D0", looks) == [14]


def test_arming_lasts_180_days():
    within = [(0, 80), (100, 50), (180, 0), (190, 0)]  # first low look exactly 180 days after arming
    too_late = [(0, 80), (100, 50), (181, 0), (190, 0)]  # 181 days: arming has expired
    assert start_days("D0", within) == [180]
    assert start_days("D0", too_late) == []


def test_dam_must_refill_before_the_next_event():
    no_refill = [(0, 80), (14, 0), (28, 0), (42, 20), (56, 0), (70, 0)]
    refilled = [(0, 80), (14, 0), (28, 0), (42, 70), (56, 0), (70, 0)]
    assert start_days("D0", no_refill) == [14]
    assert start_days("D0", refilled) == [14, 56]


def test_d0_and_r30_are_armed_separately():
    # R30 fires first and disarms R30 only; D0 is still armed and fires later.
    looks = [(0, 80), (14, 25), (28, 25), (42, 0), (56, 0)]
    assert start_days("R30", looks) == [14]
    assert start_days("D0", looks) == [42]


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------
def test_one_low_look_is_not_enough():
    looks = [(0, 80), (14, 0), (28, 50), (42, 0)]  # the low looks are not consecutive
    assert start_days("D0", looks) == []


def test_confirming_looks_must_be_at_most_30_days_apart():
    thirty_days = [(0, 80), (14, 0), (44, 0)]
    thirty_one_days = [(0, 80), (14, 0), (45, 0)]
    assert start_days("D0", thirty_days) == [14]
    assert start_days("D0", thirty_one_days) == []


def test_event_date_is_the_first_confirming_look():
    looks = [(0, 80), (20, 10), (35, 5), (50, 5)]
    assert start_days("R30", looks) == [20]


def test_r30_threshold_is_strictly_below_30_percent():
    at_30 = [(0, 80), (14, 30), (28, 30)]
    below_30 = [(0, 80), (14, 29.9), (28, 29.9)]
    assert start_days("R30", at_30) == []
    assert start_days("R30", below_30) == [14]


def test_d0_needs_zero_wet_pixels_not_just_a_low_level():
    looks = [(0, 80), (14, 1), (28, 1)]  # nearly dry but still 1 wet pixel
    assert start_days("D0", looks) == []
    assert start_days("R30", looks) == [14]


# ---------------------------------------------------------------------------
# Abrupt vs gradual D0
# ---------------------------------------------------------------------------
def test_abrupt_when_dam_looked_fairly_full_shortly_before():
    looks = [(0, 80), (30, 45), (44, 0), (58, 0)]  # rel 0.45, 14 days before
    assert first_d0_is_abrupt(looks) is True


def test_abrupt_boundaries_are_inclusive():
    looks = [(0, 80), (10, 40), (70, 0), (80, 0)]  # rel exactly 0.40, exactly 60 days before
    assert first_d0_is_abrupt(looks) is True


def test_gradual_when_last_wet_look_was_low():
    looks = [(0, 80), (30, 35), (44, 0), (58, 0)]  # rel 0.35 < 0.40
    assert first_d0_is_abrupt(looks) is False


def test_gradual_when_last_wet_look_was_long_before():
    looks = [(0, 80), (10, 50), (71, 0), (80, 0)]  # rel 0.5 but 61 days before
    assert first_d0_is_abrupt(looks) is False


# ---------------------------------------------------------------------------
# The full table builder
# ---------------------------------------------------------------------------
def tiny_panel_and_attrs():
    """Two dams. A has history and dries out twice; B has no usable history (not has_hist)."""
    looks_a = [
        ("2019-05-01", 80),  # full enough: arms D0 and R30
        ("2019-06-01", 40),
        ("2019-07-10", 0),   # D0 and R30 start (confirmed by the next look)
        ("2019-07-25", 0),
        ("2019-11-01", 90),  # refilled: re-arms both kinds
        ("2019-12-15", 20),  # R30 starts (confirmed by the next look)
        ("2020-01-10", 10),
        ("2020-02-01", 0),   # D0 starts (confirmed by the next look)
        ("2020-02-20", 0),
    ]
    looks_b = [("2019-05-01", 80), ("2019-07-10", 0), ("2019-07-25", 0)]

    rows = [("A", day, pc) for day, pc in looks_a] + [("B", day, pc) for day, pc in looks_b]
    panel = pd.DataFrame(rows, columns=["uid", "date", "pc_wet"])
    panel["date"] = pd.to_datetime(panel["date"])
    panel["px_wet"] = np.where(panel["pc_wet"] > 0, 10.0, 0.0)

    attrs = pd.DataFrame({
        "uid": ["A", "B"],
        "region": ["nsw_cw", "nsw_cw"],
        "full": [100.0, 100.0],
        "has_hist": [True, False],
        "dam_like": [True, False],
        "persistent": [False, False],
    })
    return panel, attrs


def test_build_events_skips_waterbodies_without_history():
    panel, attrs = tiny_panel_and_attrs()
    events = build_events(panel, attrs)
    assert set(events["uid"]) == {"A"}


def test_build_events_dates_and_abruptness():
    panel, attrs = tiny_panel_and_attrs()
    events = build_events(panel, attrs)

    r30 = events[events["kind"] == "R30"]
    assert list(r30["start_date"]) == list(pd.to_datetime(["2019-07-10", "2019-12-15"]))

    d0 = events[events["kind"] == "D0"].reset_index(drop=True)
    assert list(d0["start_date"]) == list(pd.to_datetime(["2019-07-10", "2020-02-01"]))
    assert list(d0["confirm_date"]) == list(pd.to_datetime(["2019-07-25", "2020-02-20"]))
    # First D0: last wet look 1 Jun (rel 0.40), 39 days before -> abrupt.
    # Second D0: last wet look 10 Jan (rel 0.10) -> gradual.
    assert list(d0["abrupt"]) == [True, False]
    assert list(d0["gradual"]) == [False, True]
    assert list(d0["last_wet_date"]) == list(pd.to_datetime(["2019-06-01", "2020-01-10"]))


def test_build_events_hydro_year_and_counts():
    panel, attrs = tiny_panel_and_attrs()
    events = build_events(panel, attrs)

    # July 2019 to June 2020 is hydro year 2019, so all four events share it.
    assert set(events["hydro_year"]) == {2019}
    assert events["dam_like"].all()
    assert count_events(events) == {"D0": 2, "R30": 2, "D0g": 1}
    assert count_events(events, "persistent") == {"D0": 0, "R30": 0, "D0g": 0}


def test_build_events_with_no_events_still_has_all_columns():
    # A dam that never drops below 40% full: the table is empty but keeps its
    # columns, so code that filters or counts it does not crash.
    panel, attrs = tiny_panel_and_attrs()
    never_low = panel[panel["pc_wet"] >= 40]
    events = build_events(never_low, attrs)
    assert len(events) == 0
    assert {"start_date", "kind", "gradual", "hydro_year", "dam_like"} <= set(events.columns)
    assert count_events(events) == {"D0": 0, "R30": 0, "D0g": 0}
