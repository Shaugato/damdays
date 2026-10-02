"""Tests of the app exporter (damdays.export), on small made-up inputs (plus one check on the real dam list).

What is proved here:
  * the Albers conversion is right: both directions undo each other, and every
    dam's Albers centre lands within 100 m of its DEA latitude/longitude;
  * hexagon corners are 1.155 km from the cell centre (a 2 km flat-to-flat cell), and
    neighbouring hexagons share an edge (they tile the map);
  * Rewind outcomes read the label of the right forecast (and refuse a reordered key table);
  * the runway curve the app draws passes through the headline at 90 days and
    never falls, and the season band always contains the chance;
  * the status rules: an old look gives "no_recent_look", a low look "already_low",
    a dam that has not refilled to 60% (or had an event since) "not_refilled";
  * truncation: looks and events after an issue date never change a status on that date;
  * the production fit refuses a cutoff before 1 Aug 2017 (its floor and band learn
    answers up to 1 Jul 2016);
  * the contract check accepts a correct dataset and names each broken rule.
Checks on the real published files are in tests/test_app_export_real.py.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from damdays import config
from damdays.data import cells as hex_cells
from damdays.export import albers
from damdays.export import app_data as ad


# ---------------------------------------------------------------------------
# Albers and hexagons
# ---------------------------------------------------------------------------
def test_albers_round_trip():
    lat = np.array([-30.5, -33.1, -36.9, -37.99])
    lon = np.array([147.0, 149.9, 140.6, 143.4])
    x, y = albers.to_albers(lat, lon)
    back_lat, back_lon = albers.to_lat_lon(x, y)
    assert np.allclose(back_lat, lat, atol=1e-9) and np.allclose(back_lon, lon, atol=1e-9)


def test_albers_matches_dea_coordinates():
    path = config.CACHE_DIR / "attributes.pkl"
    if not path.exists():
        pytest.skip("needs data_cache/attributes.pkl (scripts/01)")
    attrs = pd.read_pickle(path)
    lat, lon = albers.to_lat_lon(attrs["x_albers"], attrs["y_albers"])
    metres = np.hypot((lat - attrs["lat"]) * 111_000, (lon - attrs["lon"]) * 111_000 * np.cos(np.radians(lat)))
    assert metres.max() < 100


def test_hexagon_corners_sit_on_the_cell_radius():
    corners = np.array(ad.hexagon_corners(1702, -1967))
    assert corners.shape == (6, 2)
    x, y = albers.to_albers(corners[:, 0], corners[:, 1])
    centre_x, centre_y = hex_cells.hex_centre(1702, -1967)
    assert np.allclose(np.hypot(x - centre_x, y - centre_y), hex_cells.HEX_RADIUS_M, atol=2.0)  # 5-decimal rounding


def test_neighbouring_hexagons_share_an_edge():
    """The corners are turned the right way (pointy-top, like cells.py): each of the 6 neighbours shares
    exactly 2 corners with the cell, so the drawn hexagons tile the map without gaps or overlaps."""
    cell = np.array(ad.hexagon_corners(1702, -1967))
    for dq, dr in [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]:
        neighbour = np.array(ad.hexagon_corners(1702 + dq, -1967 + dr))
        shared = sum(np.abs(neighbour - corner).sum(axis=1).min() < 2e-5 for corner in cell)
        assert shared == 2, (dq, dr)


# ---------------------------------------------------------------------------
# The runway curve and the band
# ---------------------------------------------------------------------------
def test_joined_curve_meets_the_headline_and_never_falls():
    curve = np.array([[0.10, 0.25, 0.40, 0.60],     # headline below H at 60 days
                      [0.10, 0.20, 0.30, 0.50],     # headline between H's 90 and 180 days
                      [0.05, 0.10, 0.20, 0.30]])    # headline above H at 180 days
    headline = np.array([0.20, 0.45, 0.35])
    joined, moved = ad.join_curve_to_headline(curve, headline)
    assert np.array_equal(joined[:, 2], headline)
    assert (np.diff(joined, axis=1) >= 0).all()
    assert np.allclose(joined[0], [0.10, 0.20, 0.20, 0.60])
    assert np.allclose(joined[1], [0.10, 0.20, 0.45, 0.50])
    assert np.allclose(joined[2], [0.05, 0.10, 0.35, 0.35])
    assert moved == 2


def test_band_contains_the_chance():
    p = np.array([1e-4, 0.05, 0.3, 0.9, 0.9999])
    low, high = ad.with_band(p, (-1.0, 0.7))
    assert (low <= p).all() and (p <= high).all()
    with pytest.raises(ValueError):
        ad.with_band(p, (0.1, 0.7))


# ---------------------------------------------------------------------------
# Status rules
# ---------------------------------------------------------------------------
def looks_and_events():
    """Four made-up dams, each checked on 1 Oct 2013."""
    rows = [
        ("old", "2013-06-01", 0.9),                                    # last look 122 days earlier
        ("low", "2013-08-01", 0.8), ("low", "2013-09-20", 0.2),        # below a third now
        ("never", "2013-01-01", 0.5), ("never", "2013-09-25", 0.5),    # never 60% full
        ("event", "2013-05-01", 0.9), ("event", "2013-07-01", 0.1),    # refilled, then an event,
        ("event", "2013-09-25", 0.5),                                  # half full again but not refilled
        ("armed", "2013-07-01", 0.7), ("armed", "2013-09-28", 0.5),    # refilled 89 days ago
    ]
    looks = pd.DataFrame(rows, columns=["uid", "date", "rel"])
    looks["date"] = pd.to_datetime(looks["date"])
    looks["px_wet"] = 5.0
    events = pd.DataFrame({"uid": ["event"], "kind": ["R30"], "start_date": pd.to_datetime(["2013-07-01"])})
    dams = pd.DataFrame({"uid": ["old", "low", "never", "event", "armed"]})
    return looks, events, dams


def test_issue_status_rules():
    looks, events, dams = looks_and_events()
    day = pd.Timestamp("2013-10-01")
    last = ad.last_looks(looks, dams, day)
    status = ad.issue_status(last, ad.armed_at(looks, events, last), day)
    assert list(status) == ["no_recent_look", "already_low", "not_refilled", "not_refilled", "forecast"]


def statuses_on(looks, events, dams, day):
    """The status of each dam on `day` (the exporter's own three steps)."""
    last = ad.last_looks(looks, dams, day)
    return list(ad.issue_status(last, ad.armed_at(looks, events, last), day))


def test_status_ignores_what_happens_after_the_issue_date():
    """Truncation: looks and events after the issue date cannot change a status on that date.

    The "armed" dam falls below a third on 5 and 12 Oct 2013 (an R30 event starting 5 Oct).
    On 1 Oct its status must be the same with or without that future. Positive control:
    on 13 Oct, once both looks exist, the status does change.
    """
    looks, events, dams = looks_and_events()
    day = pd.Timestamp("2013-10-01")
    future_looks = pd.DataFrame({"uid": ["armed", "armed"], "date": pd.to_datetime(["2013-10-05", "2013-10-12"]),
                                 "rel": [0.2, 0.1], "px_wet": [5.0, 5.0]})
    future_event = pd.DataFrame({"uid": ["armed"], "kind": ["R30"], "start_date": pd.to_datetime(["2013-10-05"])})
    with_future = pd.concat([looks, future_looks], ignore_index=True).sort_values(["uid", "date"])
    events_with_future = pd.concat([events, future_event], ignore_index=True)
    assert statuses_on(with_future, events_with_future, dams, day) == statuses_on(looks, events, dams, day)
    later = pd.Timestamp("2013-10-13")
    assert statuses_on(with_future, events_with_future, dams, later)[-1] == "already_low"


def test_outcomes_read_the_label_of_the_right_forecast():
    """Rewind outcomes: the PREREG R30 label of each forecast, unknown when the label is not determinable."""
    keys = pd.DataFrame({"uid": ["a", "b", "c"],
                         "issue_date": pd.to_datetime(["2013-10-01", "2013-10-02", "2013-10-03"]),
                         "y_R30": [1.0, 0.0, 1.0], "label_ok": [True, True, False]})
    events = pd.DataFrame({"uid": ["a", "c"], "kind": ["R30", "R30"],
                           "start_date": pd.to_datetime(["2013-11-15", "2013-10-20"])})
    table = pd.DataFrame({"uid": ["a", "b", "c", "d"],
                          "date": pd.to_datetime(["2013-10-01", "2013-10-02", "2013-10-03", "2013-10-04"]),
                          "status": ["forecast", "forecast", "forecast", "already_low"], "row": [0, 1, 2, -1]})
    out = ad.add_outcomes(table.copy(), keys, events)
    assert list(out["outcome"]) == [True, False, None, None]
    assert list(out["outcome_date"]) == ["2013-11-15", None, None, None]
    # The labels are read by position, so a key table in another order must be refused.
    with pytest.raises(AssertionError, match="order"):
        ad.add_outcomes(table.copy(), keys.iloc[::-1].reset_index(drop=True), events)


# ---------------------------------------------------------------------------
# The production fit's cutoff
# ---------------------------------------------------------------------------
def test_production_cutoff_must_follow_the_floor_and_band_answers():
    """The floor and the band learn answers up to 1 Jul 2016; an earlier production cutoff would peek."""
    from damdays.export import live_model
    assert live_model.earliest_production_cutoff() == pd.Timestamp("2017-08-01")
    for too_early in ("2009-01-01", "2016-07-01", "2017-07-31"):
        with pytest.raises(ValueError, match="too early"):
            live_model.check_production_cutoff(too_early)
        with pytest.raises(ValueError, match="too early"):
            live_model.floor_setting(too_early)
    live_model.check_production_cutoff("2017-08-01")
    assert live_model.floor_setting("2026-09-15")["floor_calibration"] == (config.TEST_START, "2026-09-15")


# ---------------------------------------------------------------------------
# The contract check
# ---------------------------------------------------------------------------
def tiny_dataset():
    """A correct dataset with one dam, one live and one past issue, one cell and one season."""
    row = dict(dam_id="d1", status="forecast", issued_on="2026-09-10", window_end="2026-12-09", level_pct=70,
               chance=0.3, chance_low=0.1, chance_high=0.5, damdays_days=40, notes=[], outcome=None,
               outcome_date=None)
    curve = dict(chance=[0.1, 0.2, 0.3, 0.4], low=[0.05, 0.1, 0.1, 0.2], high=[0.2, 0.3, 0.5, 0.6])
    past_row = dict(row, issued_on="2013-09-25", window_end="2013-12-24", outcome=True, outcome_date="2013-11-01")
    return dict(
        meta=dict(is_mock=False),
        forecasts=dict(horizon_days=90, dams=[dict(dam_id="d1")],
                       issues=[dict(issue_date="2026-09-14", kind="live", rows=[row]),
                               dict(issue_date="2013-10-01", kind="past", rows=[past_row])]),
        curves=dict(horizons_days=[30, 60, 90, 180], issues=[dict(issue_date="2026-09-14", by_dam={"d1": curve}),
                                                              dict(issue_date="2013-10-01", by_dam={"d1": curve})]),
        history=dict(first_month="2026-07", last_month="2026-09", by_dam={"d1": dict(level_pct=[90, None, 70],
                                                                                        events=[])}),
        cells=dict(cells=[dict(cell_id="h1_2", corners=[[0, 0]] * 6)],
                   seasons=[dict(season="2013-14", kind="past", rows=[dict(cell_id="h1_2")])]),
        scoreboard=dict(rating=dict(by_season=[dict(season="2013-14")])))


def test_contract_check_accepts_a_correct_dataset():
    assert ad.contract_problems(tiny_dataset()) == []


@pytest.mark.parametrize("break_it, expected", [
    (lambda d: d["curves"]["issues"][0]["by_dam"]["d1"].update(chance=[0.1, 0.05, 0.3, 0.4]), "curve goes down"),
    (lambda d: d["forecasts"]["issues"][0]["rows"][0].update(outcome=True), "live forecast cannot have an outcome"),
    (lambda d: d["forecasts"]["issues"][0]["rows"][0].update(chance=0.35), "differs from the headline"),
    (lambda d: d["meta"].update(is_mock=True), "is_mock must be false"),
    (lambda d: d["history"]["by_dam"]["d1"].update(level_pct=[1, 2]), "one level per month"),
    (lambda d: d["forecasts"]["issues"][0]["rows"][0].update(chance=float("nan")), "NaN"),
])
def test_contract_check_names_each_broken_rule(break_it, expected):
    docs = copy.deepcopy(tiny_dataset())
    break_it(docs)
    problems = ad.contract_problems(docs)
    assert any(expected in problem for problem in problems), problems
