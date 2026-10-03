"""Tests of scripts/17_proof_data.py (the data behind the app's Proof view, app/data/real/proof.json).

What is proved here:
  * THE GROUPS. A forecast's group is its chance rounded exactly as the weekly text and the app round it
    (notify.message.in_ten): "less than 1 in 10" under 0.05, "1 in 10" from 0.05, ... "more than 9 in 10"
    from 0.95, on the edges too. Each group's counts, falls, share and average chance are right, the groups
    add up to every forecast, and a group with fewer than 100 forecasts is listed but not drawn.
  * THE WORDS. The takeaways say what the numbers say, whichever way they go (every group matched, or not;
    every year beat the usual rate, or not; the promise short of target in a year, or more cautious than needed).
  * THE YEARS. The drier-year rule on rainfall (complete July-June years only, against the base years' average).
  * THE PUBLISHED FILE (no data_cache needed): proof.json's totals equal artifacts/test_results.json, the promise
    by year is the one in the test results, the groups and years add up, "%" only ever means how full a dam
    is, and bundle.js carries proof.json unchanged.
  * With data_cache/ built, scripts/17 rebuilds the same numbers from the saved test forecasts.
"""
import importlib.util
import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

from notify.message import chance_text, in_ten

REPO = Path(__file__).resolve().parents[1]
PROOF = REPO / "app" / "data" / "real" / "proof.json"
BUNDLE = REPO / "app" / "data" / "real" / "bundle.js"
TEST_RESULTS = REPO / "artifacts" / "test_results.json"


def load_step17():
    spec = importlib.util.spec_from_file_location("step17_proof_data", REPO / "scripts" / "17_proof_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


step17 = load_step17()


# ===========================================================================
# The groups ("N in 10"), the same rounding as the text and the app
# ===========================================================================
EDGES = [0.0, 0.0001, 0.0449, 0.04949, 0.0495, 0.05, 0.0999, 0.1449, 0.1495, 0.15, 0.25, 0.2949, 0.3, 0.45,
         0.5, 0.849, 0.8495, 0.9, 0.9449, 0.94949, 0.9495, 0.95, 0.9999, 1.0]


def test_groups_round_like_the_text_on_every_edge():
    got = step17.chance_bins(EDGES)
    assert list(got) == [in_ten(p) for p in EDGES]
    words = [chance_text(k / 10) for k in got]
    assert words[:4] == ["less than 1 in 10"] * 4                      # under 0.05 (after rounding to 0.001)
    assert words[4:6] == ["1 in 10", "1 in 10"]                         # 0.0495 rounds to 0.050: "1 in 10"
    assert chance_text(0.15) == "2 in 10" and step17.chance_bins([0.1449])[0] == 1
    assert words[-4:] == ["more than 9 in 10"] * 4 and words[-6] == "9 in 10"


def test_groups_match_the_text_on_random_chances():
    rng = np.random.default_rng(7)
    p = np.concatenate([rng.random(20_000), np.round(rng.random(5_000), 3), rng.random(2_000) ** 6])
    assert (step17.chance_bins(p) == np.array([in_ten(x) for x in p])).all()


def test_groups_refuse_a_missing_chance():
    with pytest.raises(ValueError):
        step17.chance_bins([0.2, float("nan")])


def made_up(n_per_group, share_fell, chance_in_group=None):
    """Forecasts for each group k: n_per_group[k] forecasts at chance k/10 (or chance_in_group[k]); the first
    round(share_fell[k] * n) of them fell."""
    y, p = [], []
    for k, n in n_per_group.items():
        chance = chance_in_group.get(k, k / 10) if chance_in_group else k / 10
        fell = int(round(share_fell[k] * n))
        y += [1.0] * fell + [0.0] * (n - fell)
        p += [chance] * n
    return np.array(y), np.array(p)


def test_calibration_bins_count_and_share():
    y, p = made_up({0: 400, 3: 1000, 7: 200, 10: 3}, {0: 0.02, 3: 0.31, 7: 0.66, 10: 1.0}, {0: 0.03, 10: 0.97})
    bins = step17.calibration_bins(y, p)
    by = {b["in_ten"]: b for b in bins}
    assert list(by) == [0, 3, 7, 10]
    assert sum(b["forecasts"] for b in bins) == len(y) and sum(b["fell"] for b in bins) == int(y.sum())
    assert by[3]["forecasts"] == 1000 and by[3]["fell"] == 310 and by[3]["share_fell"] == 0.31
    assert by[3]["said"] == "3 in 10" and by[3]["happened_in_ten"] == 3 and by[3]["mean_chance"] == 0.3
    assert by[0]["said"] == "less than 1 in 10" and by[0]["mean_chance"] == 0.03
    assert by[7]["happened_in_ten"] == 7                                  # 0.66 rounds to 7 in 10
    assert by[10]["said"] == "more than 9 in 10" and by[10]["plotted"] is False   # 3 forecasts: listed, not drawn
    assert all(b["plotted"] for k, b in by.items() if k != 10)
    assert "share_fell_ci" not in by[3]                                   # no uid: no range


def test_calibration_bins_ranges_from_redrawn_dams():
    y, p = made_up({2: 600, 5: 600}, {2: 0.2, 5: 0.5})
    uid = np.array([f"dam{i % 60}" for i in range(len(y))])
    bins = step17.calibration_bins(y, p, uid=uid, n_boot=50, seed=1)
    for b in bins:
        low, high = b["share_fell_ci"]
        assert 0 <= low <= high <= 1


def test_calibration_bins_refuse_answers_that_are_not_0_or_1():
    with pytest.raises(ValueError):
        step17.calibration_bins([0, 1, 0.5], [0.1, 0.2, 0.3])


def test_calibration_words_when_every_group_matches():
    y, p = made_up({1: 500, 3: 500, 6: 500, 9: 50}, {1: 0.09, 3: 0.28, 6: 0.63, 9: 0.9})
    takeaway, detail, lean, not_plotted = step17.calibration_words(step17.calibration_bins(y, p), 1.09)
    assert takeaway.startswith("When we said 3 in 10, the dam fell below a third about 3 times in 10")
    assert "in all three groups what happened matched what we said" in takeaway      # 9 in 10 is too small to plot
    assert detail.startswith("3 in 10: 140 of 500 forecasts")
    assert "Below 6 in 10, slightly fewer dams fell than we said; from 6 in 10 up, slightly more." in lean
    assert "calibration slope 1.09" in lean
    assert not_plotted == "Not drawn, too few to read: 50 forecasts said 9 in 10 (45 fell)."


def test_calibration_words_name_a_group_that_did_not_match():
    y, p = made_up({2: 500, 3: 500, 5: 500}, {2: 0.2, 3: 0.45, 5: 0.5})
    takeaway, _, lean, not_plotted = step17.calibration_words(step17.calibration_bins(y, p), 1.0)
    assert "about 5 times in 10" in takeaway                                # said 3 in 10, happened 5 in 10
    assert "in 2 of 3 groups" in takeaway and "but not in 3 in 10 (happened 5 in 10)" in takeaway
    assert lean.startswith("The small gaps go both ways") or "slightly" in lean
    assert not_plotted == ""


# ===========================================================================
# Skill, years, rain
# ===========================================================================
def test_brier_skill():
    y = np.array([0, 1, 1, 0], dtype=float)
    assert step17.brier_skill(y, y, np.full(4, 0.5)) == 1.0
    assert step17.brier_skill(y, np.full(4, 0.5), np.full(4, 0.5)) == 0.0
    p, ref = np.array([0.2, 0.7, 0.6, 0.1]), np.full(4, 0.5)
    expected = 1 - np.mean((p - y) ** 2) / np.mean((ref - y) ** 2)
    assert math.isclose(step17.brier_skill(y, p, ref), expected)
    w = np.array([2, 0, 1, 1.0])
    assert math.isclose(step17.brier_skill(y, p, ref, w),
                        1 - np.sum(w * (p - y) ** 2) / np.sum(w * (ref - y) ** 2))


def test_rain_rule_uses_complete_july_june_years_against_the_base_years():
    months = np.array([y * 100 + m for y in range(2000, 2004) for m in range(1, 13)] + [200401, 200402])
    cells = ["a:1", "a:2", "b:1"]
    rain = np.zeros((3, len(months)))
    hydro = np.array([(m // 100) if m % 100 >= 7 else (m // 100) - 1 for m in months])
    rain[0] = np.where(hydro == 2002, 5.0, 10.0)          # region a: 2002-03 at half its usual monthly rain
    rain[1] = np.where(hydro == 2002, 5.0, 10.0)
    rain[2] = np.where(hydro == 2001, 30.0, 10.0)          # region b: 2001-02 three times its usual rain
    ratios = step17.rain_by_year(rain, months, cells, ["a", "b"], base_years=(2000, 2001))
    assert set(ratios["a"]) == {2000, 2001, 2002}           # 1999-00 and 2003-04 are not complete
    assert math.isclose(ratios["a"][2002], 0.5) and math.isclose(ratios["a"][2000], 1.0)
    assert math.isclose(ratios["b"][2001], 30 / 20) and math.isclose(ratios["b"][2000], 10 / 20)
    # The two regions' ratios averaged: 2000 (1.0, 0.5) and 2002 (0.5, 1/2) are drier; 2001 (1.0, 1.5) is not.
    assert step17.drier_years(ratios, [2000, 2001, 2002]) == [2000, 2002]


def test_one_region_words_name_years_dry_in_one_region_only():
    rows = [dict(label="2017-18", drier=True, rain_vs_usual=dict(nsw_cw=0.59, wvic_sesa=0.96)),
            dict(label="2020-21", drier=False, rain_vs_usual=dict(nsw_cw=1.3, wvic_sesa=0.99)),
            dict(label="2023-24", drier=True, rain_vs_usual=dict(nsw_cw=1.04, wvic_sesa=0.71)),
            dict(label="2024-25", drier=True, rain_vs_usual=dict(nsw_cw=1.04, wvic_sesa=0.75)),
            dict(label="2025-26", drier=True, rain_vs_usual=dict(nsw_cw=0.78, wvic_sesa=1.06))]
    assert step17.one_region_words(rows) == (
        " In 2023-24 and 2024-25 only western Victoria / SE South Australia was drier than usual; in 2025-26 only "
        "NSW Central West was drier than usual.")
    assert step17.one_region_words(rows[:2]) == ""


def test_runs_and_labels():
    assert step17.runs([2023, 2017, 2018, 2019, 2025, 2024]) == [(2017, 2019), (2023, 2025)]
    assert step17.runs([2016]) == [(2016, 2016)]
    assert step17.run_label(2017, 2019) == "2017-20" and step17.run_label(2023, 2025) == "2023-26"
    assert step17.year_label(2016) == "2016-17" and step17.year_words(2023) == "July 2023 to June 2024"
    assert step17.in_thousand(0.87199) == 872 and step17.in_thousand(0.9005) == 901


def year_row(year, skill, held, drier=False):
    return dict(year=year, label=step17.year_label(year), words=step17.year_words(year), skill=skill, drier=drier,
                floor=dict(held=held, held_in_1000=step17.in_thousand(held), judged=1000))


def test_year_words_every_year_and_the_promise():
    rows = [year_row(2016 + i, 0.21 + 0.007 * i, 0.90, drier=i in (1, 2, 3, 7, 8, 9)) for i in range(10)]
    rows[7]["floor"].update(held=0.872, held_in_1000=872)
    rows[4]["floor"].update(held=0.927, held_in_1000=927)
    takeaway, floor_takeaway, floor_detail = step17.year_words_all(rows, 0.235, {}, 0.9, 0.02)
    assert takeaway.startswith("In every one of the ten years, the forecasts had less error than guessing the usual "
                               "rate: from a fifth (2016-17) to a quarter (2025-26) less")
    assert "in the six drier years (2017-20 and 2023-26) as well as the four wetter ones" in takeaway
    assert floor_takeaway == ('The "at least N days" promise held about 9 times in 10 in every year (from 872 to 927 '
                              "times in 1,000); it fell a little short of the 880 mark in July 2023 to June 2024 (872).")
    assert "Short of target: July 2023 to June 2024, 872 in 1,000." in floor_detail
    assert "More cautious than needed: July 2020 to June 2021, 927 in 1,000." in floor_detail


def test_year_words_when_a_year_does_not_beat_the_usual_rate():
    rows = [year_row(2016 + i, 0.2, 0.9) for i in range(10)]
    rows[3]["skill"] = -0.02
    rows[5]["floor"].update(held=0.83, held_in_1000=830)                # 830 rounds to 8 in 10
    takeaway, floor_takeaway, _ = step17.year_words_all(rows, 0.18, {}, 0.9, 0.02)
    assert takeaway.startswith("In 9 of the 10 years") and "in 2019-20 they did not" in takeaway
    assert floor_takeaway.startswith('The "at least N days" promise held from 830 to 900 times in 1,000 a year')


def test_dam_and_farm_words():
    forecasts = [dict(date="2018-09-23", chance=0.289, fell=True), dict(date="2018-10-01", chance=0.37, fell=True),
                 dict(date="2019-03-10", chance=0.048, fell=False)]
    text = step17.dam_summary("Dam 1", forecasts, ["2018-12-04"], closest=True)
    assert text == ("Dam 1 (the dam closest to the homestead): 3 forecasts from July 2018 to June 2019; the highest "
                    "chance was 4 in 10 (1 Oct 2018). It fell below a third on 4 Dec 2018; 2 of the 3 forecasts were "
                    "followed by a fall within 90 days.")
    quiet = step17.dam_summary("Dam 2", [dict(date="2018-08-14", chance=0.336, fell=False)], [])
    assert "did not fall below a third between July 2018 and September 2019; none of the 1 forecasts" in quiet
    assert "no forecast" in step17.dam_summary("Dam 9", [], [])
    rows = [dict(name="Dam 1", chance=0.37, outcome=True), dict(name="Dam 2", chance=0.085, outcome=False),
            dict(name="Dam 3", chance=0.604, outcome=False), dict(name="Dam 4", chance=None, outcome=None)]
    farm = step17.farm_words("Farm D (near Dubbo)", rows)
    assert farm == ("On 1 Nov 2018, the three dams on one farm, Farm D (near Dubbo), each got their own chance, from "
                    "1 in 10 to 6 in 10; the chances added up to about 1, and 1 fell below a third within 90 days "
                    "(Dam 1).")


# ===========================================================================
# The published proof.json (no data_cache needed)
# ===========================================================================
@pytest.fixture(scope="module")
def proof():
    if not PROOF.exists():
        pytest.skip("app/data/real/proof.json is not there (scripts/17_proof_data.py writes it).")
    return json.loads(PROOF.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def results():
    return json.loads(TEST_RESULTS.read_text(encoding="utf-8"))


def test_published_totals_equal_the_test_results(proof, results):
    scored = results["scores"][step17.PRIMARY_KEY]
    test = proof["test"]
    assert (test["forecasts"], test["fell"], test["dams"]) == (
        scored["rows"]["scored"], scored["rows"]["events"], scored["rows"]["dams"]) == (142_938, 29_415, 1_644)
    assert test["skill_vs_usual_rate"] == dict(value=scored["point"]["bss_B0"], ci_low=scored["ci_dam"]["bss_B0"][0],
                                               ci_high=scored["ci_dam"]["bss_B0"][1], words="nearly a quarter")
    assert test["calibration_slope"] == scored["point"]["cal_slope"]
    checked = {c["what"]: c["value"] for c in proof["checks"]["equal_to_test_results"]}
    assert checked["skill against the usual rate (BSS vs B0)"] == scored["point"]["bss_B0"] == 0.23501
    assert checked["average chance given"] == scored["point"]["mean_p"]
    assert checked["share that fell"] == scored["point"]["base_rate"]


def test_published_groups_add_up(proof):
    bins = proof["calibration"]["bins"]
    assert sum(b["forecasts"] for b in bins) == proof["test"]["forecasts"]
    assert sum(b["fell"] for b in bins) == proof["test"]["fell"]
    for b in bins:
        assert b["said"] == chance_text(b["in_ten"] / 10)
        assert math.isclose(b["share_fell"], b["fell"] / b["forecasts"], abs_tol=5e-6)
        assert b["happened_in_ten"] == in_ten(b["share_fell"])
        assert b["plotted"] == (b["forecasts"] >= step17.MIN_FORECASTS_TO_PLOT)
        low, high = b["share_fell_ci"]
        assert low <= b["share_fell"] <= high
    # Average chance over the groups = the test results' average chance.
    mean = sum(b["mean_chance"] * b["forecasts"] for b in bins) / proof["test"]["forecasts"]
    assert abs(mean - 0.21629) < 1e-4


def test_published_years_add_up_and_the_promise_is_copied(proof, results):
    floor = results["floor"]["issued_all"]
    years = proof["by_year"]["years"]
    assert [y["year"] for y in years] == list(range(2016, 2026))
    assert sum(y["forecasts"] for y in years) == proof["test"]["forecasts"]
    assert sum(y["fell"] for y in years) == proof["test"]["fell"]
    for y in years:
        assert y["floor"]["held"] == floor["by_year"][str(y["year"])]["coverage"]
        assert y["floor"]["judged"] == floor["by_year"][str(y["year"])]["rows"]
        assert y["floor"]["held_in_1000"] == step17.in_thousand(y["floor"]["held"])
        low, high = y["skill_ci"]
        assert low <= y["skill"] <= high
        assert y["drier"] == (y["rain_vs_usual_mean"] < 1)
    assert sum(y["floor"]["judged"] for y in years) == floor["rows_judged"] == 729_749
    worst = min(years, key=lambda y: y["floor"]["held"])
    assert (worst["year"], worst["floor"]["held"]) == (floor["worst_year"]["year"], floor["worst_year"]["coverage"])
    assert worst["floor"]["held_in_1000"] == 872 and worst["label"] == "2023-24"
    all_years = proof["by_year"]["all_years"]
    assert (all_years["floor_held"], all_years["floor_judged"]) == (floor["coverage"], floor["rows_judged"])
    assert [r["label"] for r in proof["by_year"]["drier_runs"]] == ["2017-20", "2023-26"]


def test_published_farm_matches_rewind(proof):
    part = proof["dam_by_dam"]
    published = json.loads((REPO / "app" / "data" / "real" / "forecasts.json").read_text(encoding="utf-8"))
    rewind = next(i for i in published["issues"] if i["issue_date"] == part["rewind_date"])
    rows = {r["dam_id"]: r for r in rewind["rows"]}
    for dam in part["dams"]:
        rw = rows[dam["dam_id"]]
        assert (dam["rewind"]["chance"], dam["rewind"]["outcome"]) == (rw["chance"], rw["outcome"])
        if rw["status"] == "forecast":
            same = [f for f in dam["forecasts"] if f["date"] == rw["issued_on"]]
            assert len(same) == 1 and same[0]["chance"] == rw["chance"] and same[0]["fell"] == rw["outcome"]
        for f in dam["forecasts"]:
            assert part["season"]["forecasts_from"] <= f["date"] <= part["season"]["forecasts_to"]
            assert (f["fell_on"] in dam["falls"]) if f["fell"] else f["fell_on"] is None
    assert part["default_dam"] == part["dams"][0]["dam_id"] and part["dams"][0]["name"] == "Dam 1"


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def test_published_words_use_percent_only_for_how_full(proof):
    for text in strings(proof):
        for match in re.finditer("%", text):
            after = text[match.end():match.end() + 20]
            assert after.startswith((" full", " of its usual full", " of full")), text
    words = " ".join(strings({k: proof[k] for k in ("calibration", "by_year", "dam_by_dam", "unseen_exam")}))
    assert "AUC" not in words and "Brier skill score against the usual rate" in words   # the one technical name, explained


def test_bundle_carries_proof_unchanged(proof):
    text = BUNDLE.read_text(encoding="utf-8")
    bundle = json.loads(text[text.index("=") + 1:].strip().rstrip(";"))
    assert bundle["proof"] == proof


# ===========================================================================
# With data_cache/: rebuilt from the saved test forecasts, the same numbers
# ===========================================================================
def test_rebuild_from_the_saved_test_forecasts(proof):
    needed = [REPO / step17.FORECASTS_FILE, REPO / step17.BASELINES_FILE, REPO / "data_cache" / "panel.pkl",
              REPO / "data_cache" / "silo_rain.pkl"]
    if not all(p.exists() for p in needed):
        pytest.skip("needs data_cache/ (the test forecasts of scripts/13 and the cleaned data of scripts/01-02)")
    rebuilt = step17.build()
    for part in ("test", "calibration", "by_year", "dam_by_dam", "unseen_exam"):
        assert rebuilt[part] == proof[part], part
