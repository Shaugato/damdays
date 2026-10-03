"""Tests of scripts/18_track_record.py (each dam's track record, app/data/real/track_record.json).

What is proved here:
  * THE COUNTING. A forecast's promise ("at least N days above a third") is JUDGED only when the archive watched
    the dam for at least N days, whatever happened, and HELD when the dam did not fall below a third before day N;
    "180+" is judged at 180 days. Row by row this is exactly the rule the test was scored with
    (damdays.evaluation.coverage.floor_coverage), on the edges and on 20,000 random forecasts.
  * PER DAM. Held, judged and not-judged counts, the seasons (July-June), the typical promise and the "likely"
    calls (a chance of 5 in 10 or more, rounded as the text rounds it) are right for made-up dams; "not enough
    history" under 5 judged forecasts.
  * PER FARM. A farm's record adds up only its dams with enough history, names the others, and finds the dam
    with the lowest record (the closest one on a tie).
  * THE SPREAD. The median and the counts below 9 in 10 / 8 in 10.
  * THE PUBLISHED FILE (no data_cache needed): every dam the app shows has a record or "not enough history";
    every record adds up (held <= judged <= forecasts, the seasons add up); the farm roll-ups equal their dams;
    the checks equal artifacts/test_results.json ("as shown in the app" floor result) and proof.json; the summary
    is right; only the two development regions; bundle.js carries it unchanged.
  * With data_cache/ built, scripts/18 rebuilds the same file from the saved test forecasts.
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from damdays.evaluation.coverage import floor_coverage
from notify.message import NAME_IF_IN_TEN, TRACK_RECORD_MIN, TRACK_RECORD_YEARS, in_ten

REPO = Path(__file__).resolve().parents[1]
APP_REAL = REPO / "app" / "data" / "real"
TRACK = APP_REAL / "track_record.json"
BUNDLE = APP_REAL / "bundle.js"
TEST_RESULTS = REPO / "artifacts" / "test_results.json"


def load_step18():
    spec = importlib.util.spec_from_file_location("step18_track_record", REPO / "scripts" / "18_track_record.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


step18 = load_step18()


# ===========================================================================
# The counting: one forecast's promise
# ===========================================================================
@pytest.mark.parametrize("floor, event, followup, judged, held", [
    (10, 9, 400, True, False),          # fell on day 9 of a 10-day promise: missed
    (10, 10, 400, True, True),          # fell on day 10: the promise (at least 10 days) held
    (10, np.nan, 400, True, True),      # no fall seen: held
    (10, np.inf, 400, True, True),
    (10, 5, 9, False, False),           # watched only 9 days: not judged, even though it fell on day 5
    (10, np.nan, 9, False, False),      # ... and not judged when nothing happened either
    (10, 3, 10, True, False),           # watched exactly 10 days: judged
    (0, 0, 0, True, True),              # a promise of 0 days always holds
    (200, 185, 180, True, True),        # "180+" is judged at 180 days: watched 180, no fall before day 180
    (200, 170, 180, True, False),       # ... fell on day 170: missed
    (200, np.nan, 179, False, False),   # watched 179 days: not judged
    (179, 178, 179, True, False),
])
def test_one_promise(floor, event, followup, judged, held):
    j, h = step18.judge_floors([floor], [event], [followup])
    assert (bool(j[0]), bool(h[0])) == (judged, held)


def test_judging_never_looks_at_the_outcome():
    """Two forecasts with the same promise and follow-up are both judged or both not, whatever happened."""
    j, _ = step18.judge_floors([30, 30, 30, 30], [1, np.nan, 1, np.nan], [29, 29, 31, 31])
    assert list(j) == [False, False, True, True]


def test_a_forecast_without_a_promise_is_refused():
    with pytest.raises(ValueError):
        step18.judge_floors([np.nan], [5], [100])


def test_counting_equals_the_scorecard_rule_on_random_forecasts():
    """Row by row the same as damdays.evaluation.coverage.floor_coverage (the rule the test was scored with)."""
    rng = np.random.default_rng(18)
    n = 20_000
    floor = np.floor(rng.uniform(0, 400, n))                     # whole days, as shown; some above 180
    event = rng.uniform(0, 500, n)
    event[rng.random(n) < 0.3] = np.nan                          # no fall seen
    edge = rng.random(n) < 0.1
    event[edge] = np.minimum(floor[edge], 180) - rng.integers(0, 2, edge.sum())   # falls on (or a day before) day N
    follow = rng.uniform(-10, 450, n)
    exact = rng.random(n) < 0.05                                 # some watched exactly N days
    follow[exact] = np.minimum(floor[exact], 180)
    judged, held = step18.judge_floors(floor, event, follow)
    ref = floor_coverage(floor, event, follow, cap_days=180, n_boot=0)
    assert int(judged.sum()) == ref["rows_judged"]
    assert held.sum() / judged.sum() == pytest.approx(ref["coverage"], abs=1e-12)
    # and per dam: the sum of the dams' counts is the whole
    uid = rng.integers(0, 300, n)
    per_dam = pd.DataFrame(dict(uid=uid, judged=judged, held=held)).groupby("uid")[["judged", "held"]].sum()
    assert per_dam["judged"].sum() == ref["rows_judged"]


@pytest.mark.parametrize("p", [0.0, 0.004, 0.0449, 0.045, 0.049, 0.05, 0.149, 0.15, 0.4449, 0.445, 0.449, 0.45,
                               0.4999, 0.5, 0.55, 0.949, 0.95, 1.0])
def test_likely_uses_the_texts_rounding(p):
    assert int(step18.in_ten([p])[0]) == in_ten(p)


# ===========================================================================
# Per dam
# ===========================================================================
def frame_of(rows):
    """Made-up forecasts: (uid, year, floor, judged, held, likely, known, fell)."""
    return pd.DataFrame(rows, columns=["uid", "year", "floor", "judged", "held", "likely", "known", "fell"])


def test_dam_records_count_each_dam():
    rows = (
        # dam "a": 2016-17 held 2 of 3 judged (+1 not judged); 2018-19 held 3 of 3
        [("a", 2016, 30, True, True, False, True, False)] * 2
        + [("a", 2016, 30, True, False, True, True, True)]
        + [("a", 2016, 200, False, False, True, True, False)]          # not judged; a likely call that did not fall
        + [("a", 2018, 180, True, True, True, False, False)] * 3       # likely but answer unknown: not counted
        # dam "b": 4 judged, all held
        + [("b", 2020, 10, True, True, False, True, False)] * 4
    )
    records = step18.dam_records(frame_of(rows))
    a, b = records["a"], records["b"]
    assert (a["forecasts"], a["judged"], a["held"], a["not_judged"]) == (7, 6, 5, 1)
    assert a["by_season"] == {"2016": [2, 3], "2018": [3, 3]}
    assert a["enough"] is True
    assert a["median_days"] == 105                                    # median of 30, 30, 30, 180, 180, 180
    assert (a["likely_said"], a["likely_fell"]) == (2, 1)              # the two with a known answer
    assert (b["judged"], b["held"], b["enough"]) == (4, 4, False)      # fewer than 5: not enough history
    assert step18.held_words(a) == "held 5 of 6 times"
    assert step18.held_words(b) == "not enough history"


def test_a_dam_with_nothing_judged():
    records = step18.dam_records(frame_of([("c", 2025, 90, False, False, False, False, False)] * 3))
    c = records["c"]
    assert (c["judged"], c["held"], c["not_judged"], c["by_season"], c["median_days"]) == (0, 0, 3, {}, None)
    assert not step18.has_record(c)


def test_min_judged_is_the_texts():
    assert step18.MIN_JUDGED == TRACK_RECORD_MIN == 5
    assert step18.LIKELY_IN_TEN == NAME_IF_IN_TEN == 5
    assert step18.has_record(dict(judged=5, held=0)) and not step18.has_record(dict(judged=4, held=4))
    assert not step18.has_record(None)


# ===========================================================================
# Per farm, and the spread
# ===========================================================================
def test_farm_rollup_adds_up_dams_with_enough_history():
    records = {"x1": dict(held=18, judged=20, by_season={"2016": [18, 20]}),
               "x2": dict(held=3, judged=4, by_season={"2017": [3, 4]}),          # not enough history
               "x3": dict(held=40, judged=50, by_season={"2019": [40, 50]}),
               "x4": dict(held=8, judged=10, by_season={"2020": [8, 10]})}       # same share as x3: a tie
    dams = [dict(dam_id=f"x{i}", name=f"Dam {i}") for i in (1, 2, 3, 4)] + [dict(dam_id="nope", name="Dam 5")]
    roll = step18.farm_rollup(dams, records)
    assert (roll["dams"], roll["dams_with_record"], roll["held"], roll["judged"]) == (5, 3, 66, 80)
    assert roll["not_enough_history"] == ["Dam 2", "Dam 5"]
    assert roll["lowest"] == dict(name="Dam 3", dam_id="x3", held=40, judged=50)    # the closer of the tie
    assert roll["seasons"] == [2016, 2019, 2020]


def test_farm_rollup_without_any_record():
    roll = step18.farm_rollup([dict(dam_id="a", name="Dam 1")], {})
    assert (roll["dams_with_record"], roll["held"], roll["judged"], roll["lowest"]) == (0, 0, 0, None)


def test_distribution():
    records = {str(i): dict(held=h, judged=10) for i, h in enumerate([10, 10, 9, 9, 8, 7, 4])}
    records["few"] = dict(held=0, judged=4)                           # not counted: not enough history
    d = step18.distribution(records)
    assert d["dams_with_record"] == 7
    assert d["median_share_held"] == 0.9 and d["median_in_1000"] == 900
    assert (d["dams_held_every_time"], d["dams_at_or_above_9_in_10"], d["dams_below_9_in_10"],
            d["dams_below_8_in_10"], d["dams_below_half"]) == (2, 4, 3, 2, 1)
    assert (d["lowest_in_1000"], d["highest_in_1000"]) == (400, 1000)


# ===========================================================================
# The published file (no data_cache needed)
# ===========================================================================
@pytest.fixture(scope="module")
def track():
    if not TRACK.exists():
        pytest.skip("app/data/real/track_record.json is not built (run scripts/18_track_record.py)")
    return json.loads(TRACK.read_text(encoding="utf-8"))


def read(name):
    return json.loads((APP_REAL / name).read_text(encoding="utf-8"))


def test_every_dam_the_app_shows_is_there(track):
    forecasts, farms = read("forecasts.json"), read("farms.json")
    app_ids = {d["dam_id"] for d in forecasts["dams"]} | {d["dam_id"] for f in farms["farms"] for d in f["dams"]}
    assert set(track["dams"]) == app_ids
    uid_of = {d["dam_id"]: d["dea_uid"] for d in forecasts["dams"]}
    uid_of.update({d["dam_id"]: d["dea_uid"] for f in farms["farms"] for d in f["dams"]})
    assert all(track["dams"][k]["dea_uid"] == uid_of[k] for k in app_ids)
    assert {r["region"] for r in track["dams"].values()} <= {"nsw_cw", "wvic_sesa"}   # development regions only


def test_every_record_adds_up(track):
    assert track["min_judged"] == TRACK_RECORD_MIN and track["years"] == TRACK_RECORD_YEARS
    for dam_id, r in track["dams"].items():
        assert 0 <= r["held"] <= r["judged"] <= r["forecasts"], dam_id
        assert r["not_judged"] == r["forecasts"] - r["judged"], dam_id
        assert r["enough"] == (r["judged"] >= TRACK_RECORD_MIN), dam_id
        assert sum(h for h, _ in r["by_season"].values()) == r["held"], dam_id
        assert sum(n for _, n in r["by_season"].values()) == r["judged"], dam_id
        assert all(0 < n and 0 <= h <= n for h, n in r["by_season"].values()), dam_id
        assert set(r["by_season"]) <= {str(y) for y in range(2016, 2026)}, dam_id
        assert 0 <= r["likely_fell"] <= r["likely_said"] <= r["forecasts"], dam_id
        assert (r["median_days"] is None) == (r["judged"] == 0), dam_id
        assert r["median_days"] is None or 0 <= r["median_days"] <= 180, dam_id


def test_farm_rollups_equal_their_dams(track):
    farms = read("farms.json")
    assert [f["farm_id"] for f in track["farms"]] == [f["farm_id"] for f in farms["farms"]]
    for farm, roll in zip(farms["farms"], track["farms"]):
        dams = [dict(dam_id=d["dam_id"], name=d["name"]) for d in farm["dams"]]
        assert roll == dict(farm_id=farm["farm_id"], name=farm["name"], region=farm["region"],
                            radius_km=farm["radius_km"], **step18.farm_rollup(dams, track["dams"]))


def test_checks_equal_the_test_results_and_proof(track):
    results = json.loads(TEST_RESULTS.read_text(encoding="utf-8"))
    shown = results["floor"]["shown_all"]
    checks = {c["what"]: c for c in track["checks"]["equal_to_test_results"]}
    assert checks["forecasts judged"]["value"] == shown["rows_judged"] == checks["forecasts judged"]["test_results"]
    assert checks["share that held"]["value"] == shown["coverage"]
    for year, row in shown["by_year"].items():
        label = step18.season_label(int(year))
        assert checks[f"{label}: judged"]["value"] == row["rows"]
        assert checks[f"{label}: share held"]["value"] == round(row["coverage"], 5)
    proof = read("proof.json")
    bins = [b for b in proof["calibration"]["bins"] if b["in_ten"] >= NAME_IF_IN_TEN]
    pchecks = {c["what"]: c["value"] for c in track["checks"]["equal_to_proof"]}
    assert pchecks["headline set: likely calls (5 in 10 or more)"] == sum(b["forecasts"] for b in bins)
    assert pchecks["headline set: likely calls followed by a fall"] == sum(b["fell"] for b in bins)


def test_summary_is_right(track):
    s = track["summary"]
    shown = [r for r in track["dams"].values() if r["judged"] >= TRACK_RECORD_MIN]
    assert s["dams_in_app"] == len(track["dams"])
    assert s["distribution"] == step18.distribution(track["dams"])
    assert s["distribution"]["dams_with_record"] == len(shown)
    assert (s["held"], s["judged"]) == (sum(r["held"] for r in shown), sum(r["judged"] for r in shown))
    assert s["likely_said"] == sum(r["likely_said"] for r in shown)
    assert s["likely_fell"] == sum(r["likely_fell"] for r in shown)
    rates = sorted(r["held"] / r["judged"] for r in shown)
    assert s["distribution"]["median_share_held"] == round(float(np.median(rates)), 5)


def test_words_use_no_percent(track):
    """"%" only ever means how full a dam is: the track record never uses it."""
    for text in [track["tip"], track["about"], track["caveat"], *track["how"]]:
        assert "%" not in text


def test_bundle_carries_the_track_record_unchanged(track):
    text = BUNDLE.read_text(encoding="utf-8")
    bundle = json.loads(text[text.index("=") + 1:].strip().rstrip(";"))
    assert bundle["track_record"] == track


# ===========================================================================
# With data_cache/: rebuilt from the saved test forecasts, the same numbers
# ===========================================================================
def test_rebuild_from_the_saved_test_forecasts(track):
    needed = [REPO / step18.FORECASTS_FILE, REPO / step18.ANSWER_FILE]
    if not all(p.exists() for p in needed):
        pytest.skip("needs data_cache/ (the test forecasts of scripts/13 and the answers of scripts/02)")
    rebuilt = step18.build()
    for part in ("dams", "farms", "summary", "checks", "min_judged", "label", "tip"):
        assert rebuilt[part] == track[part], part
