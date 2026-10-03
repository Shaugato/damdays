"""Tests of scripts/21_publish_sealed.py (one-command publishing of the sealed results).

They run on a SYNTHETIC results fixture: made-up numbers in exactly the shape that
scripts/20_open_sealed_region.py --open writes (artifacts/sealed/sealed_results.json and the
scorecard files). Nothing sealed is read: the real artifacts/sealed/ folder is never opened here.

What is proved here:
  * a pass, a partial pass (Tidemark not beating G2) and a fail (kill rule triggered) are each
    written honestly: the right verdict, PASS/FAIL per pass mark, the expectations inside/below/above;
  * a dry run, a development-arena score, unfinished results or a missing marker are refused, and
    nothing is written;
  * the real README.md, docs/PITCH.md and docs/VIDEO_SCRIPT.md have every marker, and every
    default text says "opens Sat 3 Oct 17:30 AEST"; --reset after a publish gives the docs back exactly;
  * table rows keep their columns, the pitch and video texts never use "%" (it means only how full
    a dam is), and the video line has at most 12 words;
  * the app: the panel is built by scripts/11's sealed_panel() from the scorecard files, written to
    scoreboard.json and carried by the rebuilt bundle.js and data parts; scorecard files that disagree with
    sealed_results.json are refused;
  * the panel's floor block carries the opening's own on_target flag (damdays/evaluation/coverage.py's rule,
    in floats: 0.893 on target; 0.880, 0.875 and 0.925 not), copied, never recomputed.
"""
import copy
import importlib.util
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 3, 18, 5, tzinfo=timezone(timedelta(hours=10)))
PRIMARY = "dam_like+octmar+at_risk"


def load_step21():
    spec = importlib.util.spec_from_file_location("step21_publish_sealed", REPO / "scripts" / "21_publish_sealed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


step21 = load_step21()


# ---------------------------------------------------------------------------
# The synthetic results fixture (made-up numbers; the shape of sealed_results.json)
# ---------------------------------------------------------------------------
OUTCOMES = {
    #           BSS vs B0 [CI],      vs B2, slope, CITL, gain over G2 [CI],      P2 gain [CI],        floor
    "pass": dict(b0=(0.21, 0.19, 0.23), b2=0.12, slope=1.05, citl=0.02, g2=(0.012, 0.006, 0.018),
                 p2=(0.25, 0.22, 0.28), floor=0.905),
    "partial": dict(b0=(0.16, 0.14, 0.18), b2=0.09, slope=1.24, citl=-0.05, g2=(-0.002, -0.008, 0.004),
                    p2=(0.20, 0.17, 0.23), floor=0.89),
    "fail": dict(b0=(0.04, -0.01, 0.09), b2=-0.02, slope=1.45, citl=0.41, g2=(-0.015, -0.022, -0.008),
                 p2=(0.01, -0.02, 0.04), floor=0.80),
}
EXPECTED_RANGES = [("R30 BSS vs B0", 0.15, 0.23, 0.19), ("R30 BSS vs B2", 0.08, 0.15, None),
                   ("R30 calibration slope", 0.9, 1.25, None), ("R30 CITL", -0.3, 0.3, None),
                   ("R30 Tidemark minus G2 (BSS vs B0 units)", 0.01, 0.03, None),
                   ("P2 cell AUC gain over RAIN", 0.15, 0.30, None)]


def scorecard_result(task, subset, model, point, ci, rows, arena="sealed"):
    """One scorecard result, as damdays/evaluation writes it (only the fields the publisher and the app read)."""
    return dict(model=model.lower(), task=task, subset=subset, block="TEST", arena=arena, rows=rows, point=point,
                ci_dam=ci, time="2026-10-03 17:50:01")


def synthetic_results(outcome="pass"):
    """Made-up sealed results for one outcome. The verdicts follow the PREREG rules, as the runner applies them."""
    o = OUTCOMES[outcome]
    b0, b0_low, b0_high = o["b0"]
    gain, gain_low, gain_high = o["g2"]
    p2, p2_low, p2_high = o["p2"]
    bars = {"bss_B0": dict(value=b0, ci_low=b0_low, passed=b0 >= 0.10 and b0_low > 0),
            "bss_B2": dict(value=o["b2"], passed=o["b2"] >= 0.05),
            "cal_slope": dict(value=o["slope"], passed=0.8 <= o["slope"] <= 1.2)}
    bars["all_passed"] = all(bar["passed"] for bar in bars.values())
    g2_bars = {"bss_B0": dict(value=0.19, ci_low=0.17, passed=True), "bss_B2": dict(value=0.11, passed=True),
               "cal_slope": dict(value=1.1, passed=True), "all_passed": True}
    rows = dict(scored=50_000, events=10_000, dams=800)
    tidemark = scorecard_result("P1_R30", PRIMARY, "tidemark", dict(
        bss_B0=b0, bss_B2=o["b2"], auc=0.80, cal_slope=o["slope"], citl=o["citl"], mean_p=0.21, base_rate=0.20,
        d_bss_B0_vs_G2=gain), dict(bss_B0=[b0_low, b0_high], bss_B2=[o["b2"] - 0.01, o["b2"] + 0.01],
                                   auc=[0.79, 0.81], cal_slope=[o["slope"] - 0.05, o["slope"] + 0.05],
                                   citl=[o["citl"] - 0.05, o["citl"] + 0.05], d_bss_B0_vs_G2=[gain_low, gain_high]),
        rows)
    tidemark["prereg_pass_bars"] = bars
    g2 = scorecard_result("P1_R30", PRIMARY, "G2", dict(bss_B0=0.19), dict(bss_B0=[0.17, 0.21]), rows)
    rain = scorecard_result("P2_cell", "all", "RAIN", dict(auc=0.52, auc_within_season=0.50), dict(auc=[0.50, 0.54]),
                            dict(scored=7_000, events=1_200, dams=900))
    rating = scorecard_result("P2_cell", "all", "tidemark", dict(auc=0.52 + p2, d_auc_vs_RAIN=p2, auc_within_season=0.81),
                              dict(auc=[0.50 + p2, 0.54 + p2], d_auc_vs_RAIN=[p2_low, p2_high]),
                              dict(scored=7_000, events=1_200, dams=900))
    got = {"R30 BSS vs B0": (b0, [b0_low, b0_high]), "R30 BSS vs B2": (o["b2"], None),
           "R30 calibration slope": (o["slope"], None), "R30 CITL": (o["citl"], None),
           "R30 Tidemark minus G2 (BSS vs B0 units)": (gain, [gain_low, gain_high]),
           "P2 cell AUC gain over RAIN": (p2, [p2_low, p2_high])}
    expectations = []
    for label, low, high, central in EXPECTED_RANGES:
        value, ci = got[label]
        verdict = "inside" if low <= value <= high else ("below" if value < low else "above")
        expectations.append(dict(expectation=label, low=low, high=high, central=central, got=value, ci_dam=ci,
                                 verdict=verdict))
    p2_rule = dict(d_auc_vs_RAIN=p2, ci_dam=[p2_low, p2_high], passed=p2 >= 0.05 and p2_low > 0,
                   kill_rule_triggered=p2 < 0.02)
    return dict(
        run=dict(name="sealed", about="synthetic", target_region="sealed_sdowns_newengland",
                 fit_regions=["nsw_cw", "wvic_sesa"], rehearsal=False),
        scores={f"P1_R30 | {PRIMARY} | tidemark": tidemark, f"P1_R30 | {PRIMARY} | G2": g2,
                "P2_cell | all | tidemark": rating, "P2_cell | all | RAIN": rain},
        curves={f"R30_curve | {PRIMARY}": dict(block="TEST", arena="sealed", bss_B0_by_horizon={
            "30": 0.08, "60": 0.15, "90": 0.19, "180": 0.20}, monotonicity=dict(share_rows_falling=0.0))},
        verdicts=dict(p1_pass_bars_tidemark=bars, p1_pass_bars_g2=g2_bars, p2_cell=p2_rule, p2_dam=dict(p2_rule),
                      expectations=expectations),
        floor=dict(issued_all=dict(coverage=o["floor"], rows_judged=250_000, target=0.9,
                                   on_target=abs(o["floor"] - 0.9) <= 0.02, worst_year=dict(year=2019, coverage=0.84))),
        band=dict(R30=dict(pooled=dict(covered=9, region_years=10, drier_than_band={"2019": 1}, wetter_than_band={}),
                           single_block_2009_2016=dict(covered=6, region_years=10))),
        counts=dict(region="sealed_sdowns_newengland", waterbodies_in_manifest=4711),
        checks=dict(files=dict(n_matched=4711, n_listed=4711), config_hash_of_running_code="7d466291008dccce",
                    freeze_addendum=dict(config_hash=["PREREG_ADDENDUM_1.md"])),
        models_manifest=dict(rung="L3"), finished_at="2026-10-03T17:52:10+10:00", reused=[], not_scored=[])


def texts_for(outcome):
    return step21.published_texts(step21.facts_from(synthetic_results(outcome)), NOW)


def make_repo(tmp_path, results=None, scorecard=False):
    """A small repo: the real three docs, the results (if given) and, with scorecard=True, the app files."""
    for doc in step21.DOCS:
        (tmp_path / doc).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / doc, tmp_path / doc)
    step21.reset(tmp_path)                              # start from the default text, whatever the real docs hold
    results_dir = tmp_path / "artifacts" / "sealed"
    if results is not None:
        results_dir.mkdir(parents=True)
        (results_dir / "sealed_results.json").write_text(json.dumps(results), encoding="utf-8")
    if scorecard:
        write_scorecard(results_dir, results)
        write_app(tmp_path / "app" / "data" / "real")
    return tmp_path, results_dir


def write_scorecard(results_dir, results, arena="sealed"):
    """The three scorecard files the app panel copies, as scripts/20 writes them (scorecard/sealed_TEST/...)."""
    folder = results_dir / "scorecard" / "sealed_TEST"
    for task, name, key in (("P1_R30", f"tidemark__{PRIMARY}.json", f"P1_R30 | {PRIMARY} | tidemark"),
                            ("P2_cell", "tidemark__all.json", "P2_cell | all | tidemark"),
                            ("P2_cell", "rain__all.json", "P2_cell | all | RAIN")):
        (folder / task).mkdir(parents=True, exist_ok=True)
        (folder / task / name).write_text(json.dumps(dict(results["scores"][key], arena=arena)), encoding="utf-8")


def write_app(app_dir):
    """A tiny app dataset: the six files build_bundle.py needs, with a test-season scoreboard (sealed panel pending)."""
    app_dir.mkdir(parents=True)
    parts = dict(meta=dict(schema_version="1.0", is_mock=False, region={}, horizon_days=90),
                 forecasts=dict(dams=[], issues=[]), curves=dict(horizons_days=[30, 60, 90, 180], issues=[]),
                 history=dict(first_month="1988-01", last_month="2026-09", by_dam={}),
                 cells=dict(cells=[], seasons=[]),
                 scoreboard=dict(source="dev_test", rating=dict(all_seasons={}, by_season=[]), panels=[
                     dict(key="dev_test", status="scored", title="Development regions"),
                     dict(key="sealed", status="pending", title="Sealed region: opened Sat 3 Oct 17:30")]))
    for name, content in parts.items():
        (app_dir / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")


def first_part(app_dir):
    """The "first" data part that parts.js lists, as the app loads it (app/tools/build_bundle.py write_parts)."""
    text = (app_dir / "parts.js").read_text(encoding="utf-8")
    listing = json.loads(text[text.index("] = ") + 4:text.index("};\n") + 1])
    part = (app_dir / listing["files"]["first"]).read_text(encoding="utf-8")
    return json.loads(part[part.index("] = ") + 4:].strip().rstrip(";"))


def table_cells(line):
    return line.replace("\\|", "").count("|")


# ---------------------------------------------------------------------------
# Honest words, whichever way it went
# ---------------------------------------------------------------------------
def test_outcome_rule():
    assert step21.outcome(4, 4, False) == "pass"
    assert step21.outcome(3, 4, False) == "partial"
    assert step21.outcome(1, 4, True) == "partial"
    assert step21.outcome(0, 4, True) == "fail"


def test_pass_is_written_as_a_pass():
    t = texts_for("pass")
    main = t[("README.md", "main")]
    assert main.startswith("**All 4 pre-registered pass marks met.**")
    assert main.count("**PASS**") == 7 and "**FAIL**" not in main          # 4 for Tidemark, 3 for G2
    assert "ahead by +0.012 (95% range +0.006 to +0.018)" in main
    assert "| Skill against the usual rate | +0.15 to +0.23 (central +0.19) | +0.210 [+0.190, +0.230] | inside |" in main
    assert "6 of 6 results came out inside" in main and "kill rule not triggered" in main
    assert t[("README.md", "cell")].startswith("**All pass marks met.**")
    assert t[("docs/VIDEO_SCRIPT.md", "line")] == "It passed every mark: a fifth less error than the usual guess."
    assert t[("docs/PITCH.md", "sentence")].startswith("DamDays met all 4 pass marks we wrote before any code")


def test_partial_says_tidemark_did_not_beat_g2():
    t = texts_for("partial")
    main = t[("README.md", "main")]
    assert main.startswith("**3 of 4 pre-registered pass marks met.**")
    assert "**Tidemark did not beat its own benchmark G2 on the sealed region.**" in main
    assert "not clearly above zero" in main and "G2 alone would have done about as well" in main
    assert "| 0.8 to 1.2 | 1.24 **FAIL** | 1.10 **PASS** |" in main          # the calibration mark: Tidemark, then G2
    assert "Did not beat G2." in t[("README.md", "cell")]
    sentence = t[("docs/PITCH.md", "sentence")]
    assert "(missed: calibration)" in sentence and "did not beat our simpler benchmark model" in sentence
    assert "every number is published" in sentence
    assert t[("docs/VIDEO_SCRIPT.md", "line")] == "It met 3 of 4 marks; we published the miss."
    assert "gain over the benchmark G2 was below its range" in main


def test_fail_with_the_kill_rule_is_published_honestly():
    t = texts_for("fail")
    main = t[("README.md", "main")]
    assert main.startswith("**None of the 4 pre-registered pass marks met; kill rule triggered.**")
    assert main.count("**FAIL**") == 4
    assert "**Kill rule triggered**" in main and "the lender claim is dropped" in main
    assert "**Tidemark did worse than its own benchmark G2 on the sealed region.**" in main
    assert "below target" in main                                        # the floor held 0.80
    assert "drier than the band: 2019" in main
    assert t[("docs/VIDEO_SCRIPT.md", "line")] == "It fell short of our marks. Every number is published, as promised."
    assert "Kill rule triggered" in t[("docs/VIDEO_SCRIPT.md", "main")]
    assert "claim dropped" in t[("docs/VIDEO_SCRIPT.md", "caption")]
    assert t[("docs/PITCH.md", "sentence")].startswith("DamDays met none of the 4 pass marks")


@pytest.mark.parametrize("outcome", sorted(OUTCOMES))
def test_texts_follow_the_writing_rules(outcome):
    t = texts_for(outcome)
    for (doc, name), text in t.items():
        if name != "main":
            assert "\n" not in text and "|" not in text, (doc, name)    # fill-ins sit inside lines and table cells
        if doc != "README.md":
            assert "%" not in text, (doc, name)                        # "%" means only how full a dam is
    assert len(t[("docs/VIDEO_SCRIPT.md", "line")].split()) <= 12
    lines = step21.camera_summary(step21.facts_from(synthetic_results(outcome)))
    assert any("artifacts/sealed/SEALED_RESULTS.md" in line for line in lines)


def test_fraction_words_round_down():
    assert step21.fraction_words(0.235) == "nearly a quarter"
    assert step21.fraction_words(0.25) == "a quarter"
    assert step21.fraction_words(0.201) == "a fifth"
    assert step21.fraction_words(0.15) == "about a seventh"
    assert step21.fraction_words(0.10) == "a tenth"
    assert step21.skill_words(-0.02) == "no less error than guessing the usual rate"
    assert step21.human_time("2026-10-03T17:52:10+10:00") == "Sat 3 Oct 2026, 17:52 AEST"


# ---------------------------------------------------------------------------
# Refusals: nothing is written
# ---------------------------------------------------------------------------
def test_refuses_a_dry_run_a_dev_score_and_unfinished_results(tmp_path):
    for broken, words in ((dict(run=dict(name="dryrun", rehearsal=True)), "not the sealed opening"),
                          ("dev-arena", "not block TEST, arena 'sealed'"),
                          ("no-verdicts", "did not finish")):
        results = synthetic_results("pass")
        if broken == "dev-arena":
            results["scores"][f"P1_R30 | {PRIMARY} | G2"]["arena"] = "dev"
        elif broken == "no-verdicts":
            results.pop("verdicts")
        else:
            results.update(broken)
        folder = tmp_path / str(len(list(tmp_path.iterdir())))
        folder.mkdir()
        (folder / "sealed_results.json").write_text(json.dumps(results), encoding="utf-8")
        with pytest.raises(step21.Refused, match=words):
            step21.load_results(folder)
    with pytest.raises(step21.Refused, match="has not been opened yet"):
        step21.load_results(tmp_path / "nowhere")


def test_publish_refuses_before_opening_and_with_a_missing_marker(tmp_path):
    repo, _ = make_repo(tmp_path)                       # no results yet
    before = {doc: (repo / doc).read_bytes() for doc in step21.DOCS}
    out = []
    assert step21.publish(repo, skip_app=True, now=NOW, out=out.append) == 2
    assert "has not been opened yet" in out[0]
    (repo / "artifacts" / "sealed").mkdir(parents=True)
    (repo / "artifacts" / "sealed" / "sealed_results.json").write_text(json.dumps(synthetic_results()), encoding="utf-8")
    pitch = (repo / "docs/PITCH.md").read_text(encoding="utf-8")
    broken = pitch.replace("<!-- SEALED:START evidence -->", "", 1).replace("<!-- SEALED:END --> |", " |", 1)
    (repo / "docs/PITCH.md").write_text(broken, encoding="utf-8")
    out = []
    assert step21.publish(repo, skip_app=True, now=NOW, out=out.append) == 2
    assert "Missing: ['evidence']" in out[0]
    assert (repo / "README.md").read_bytes() == before["README.md"]         # nothing was written


# ---------------------------------------------------------------------------
# The real docs, the markers and --reset
# ---------------------------------------------------------------------------
def test_the_real_docs_have_every_marker():
    for doc in step21.DOCS:
        step21.check_markers(step21.read_doc(REPO, doc), doc)


def test_every_default_says_when_it_opens():
    assert set(step21.DEFAULTS) == {(doc, name) for doc, names in step21.DOCS.items() for name in names}
    for text in step21.DEFAULTS.values():
        assert step21.OPENS.lower() in text.lower()


@pytest.mark.parametrize("outcome", sorted(OUTCOMES))
def test_publish_then_reset_gives_the_docs_back(tmp_path, outcome):
    repo, _ = make_repo(tmp_path, synthetic_results(outcome))
    defaults = {doc: (repo / doc).read_bytes() for doc in step21.DOCS}
    assert step21.publish(repo, skip_app=True, now=NOW, out=lambda line: None) == 0
    for doc in step21.DOCS:
        published, default = (repo / doc).read_text(encoding="utf-8"), defaults[doc].decode("utf-8")
        assert published != default and step21.OPENS not in published
        # Table rows that hold a marker keep their number of columns.
        rows_before = [line for line in default.splitlines() if line.startswith("|") and "SEALED:START" in line]
        rows_after = [line for line in published.splitlines() if line.startswith("|") and "SEALED:START" in line]
        assert len(rows_before) == len(rows_after)
        assert [table_cells(row) for row in rows_before] == [table_cells(row) for row in rows_after]
    assert step21.publish(repo, skip_app=True, now=NOW, out=lambda line: None) == 0   # running twice is fine
    assert sorted(step21.reset(repo)) == sorted(step21.DOCS)
    assert {doc: (repo / doc).read_bytes() for doc in step21.DOCS} == defaults


def test_line_endings_are_kept(tmp_path):
    repo, _ = make_repo(tmp_path, synthetic_results())
    text = (repo / "README.md").read_text(encoding="utf-8")
    with open(repo / "README.md", "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", "\r\n"))
    assert step21.publish(repo, skip_app=True, now=NOW, out=lambda line: None) == 0
    published = (repo / "README.md").read_bytes()
    assert published.count(b"\n") == published.count(b"\r\n")


# ---------------------------------------------------------------------------
# The app: scoreboard.json and bundle.js (loads scripts/11, a few seconds)
# ---------------------------------------------------------------------------
def test_app_panel_is_filled_and_bundled(tmp_path):
    results = synthetic_results("partial")
    repo, results_dir = make_repo(tmp_path, results, scorecard=True)
    app_dir = repo / "app" / "data" / "real"
    out = []
    assert step21.publish(repo, now=NOW, out=out.append) == 0
    board = json.loads((app_dir / "scoreboard.json").read_text(encoding="utf-8"))
    panel = next(p for p in board["panels"] if p["key"] == "sealed")
    assert panel["status"] == "scored" and panel["runway"]["pass_bars_met"] is False
    assert panel["runway"]["gain_vs_benchmark"] == dict(value=-0.002, ci_low=-0.008, ci_high=0.004)
    assert panel["rating"]["pass_bar_met"] is True and panel["rating"]["kill_rule_triggered"] is False
    assert [p["key"] for p in board["panels"]] == ["dev_test", "sealed"]
    bundle = (app_dir / "bundle.js").read_text(encoding="utf-8")
    shipped = json.loads(bundle[bundle.index("=") + 1:].strip().rstrip(";"))
    assert next(p for p in shipped["scoreboard"]["panels"] if p["key"] == "sealed") == panel
    # The app reads the split parts (js/data.js), not bundle.js: the "first" part parts.js lists must carry it too.
    assert next(p for p in first_part(app_dir)["scoreboard"]["panels"] if p["key"] == "sealed") == panel
    # The real About page says "Ahead of ... G2" for any gain: the founder is told to check it.
    assert any(line.startswith("CHECK THE APP'S WORDING") for line in out) or "Not clearly ahead of" in (
        REPO / "app" / "js" / "views" / "about.js").read_text(encoding="utf-8")


def floor_rule(held):
    """coverage.py's own verdict for a share `held` of 1,000 judged forecasts (the frozen rule, run in floats)."""
    from damdays.evaluation import coverage
    n = 1000
    kept = round(held * n)
    floor_days, followup = np.full(n, 30.0), np.full(n, 365.0)        # every row judged (followed for 365 days)
    days_to_event = np.where(np.arange(n) < kept, np.inf, 10.0)         # `kept` rows never fell; the rest on day 10
    return coverage.floor_coverage(floor_days, days_to_event, followup, n_boot=0), coverage


# 0.880 is the float edge: |0.88 - 0.9| is 0.020000000000000018 in floats, above FLOOR_TOLERANCE, so off target.
@pytest.mark.parametrize("held, on_target", [(0.893, True), (0.880, False), (0.875, False), (0.925, False)])
def test_app_panel_carries_the_floor_and_its_frozen_on_target_flag(tmp_path, held, on_target):
    """The sealed panel's floor block: held, target, tolerance and the opening's own on_target flag (never
    recomputed), ci and n; the README's words and the app panel agree on it."""
    rule, coverage = floor_rule(held)
    assert rule["coverage"] == pytest.approx(held, abs=1e-12) and rule["on_target"] is on_target
    assert rule["on_target"] is (abs(held - coverage.FLOOR_TARGET) <= coverage.FLOOR_TOLERANCE)
    results = synthetic_results("pass")
    results["floor"]["issued_all"].update(coverage=held, target=rule["target"], on_target=rule["on_target"],
                                          ci_dam=dict(coverage=[held - 0.004, held + 0.004]))
    repo, _ = make_repo(tmp_path, results, scorecard=True)
    app_dir = repo / "app" / "data" / "real"
    out = []
    assert step21.publish(repo, now=NOW, out=out.append) == 0, out
    board = json.loads((app_dir / "scoreboard.json").read_text(encoding="utf-8"))
    panel = next(p for p in board["panels"] if p["key"] == "sealed")
    floor = panel["floor"]
    assert floor["held"] == held and floor["on_target"] is on_target
    assert floor["target"] == coverage.FLOOR_TARGET and floor["tolerance"] == coverage.FLOOR_TOLERANCE
    assert (floor["ci_low"], floor["ci_high"]) == (held - 0.004, held + 0.004)
    assert floor["n_forecasts"] == 250_000 and floor["worst_year"] == dict(year=2019, coverage=0.84)
    assert any(source.endswith("sealed_results.json (floor.issued_all)") for source in panel["sources"])
    # what the app loads (the "first" data part) carries the same block
    assert next(p for p in first_part(app_dir)["scoreboard"]["panels"] if p["key"] == "sealed")["floor"] == floor
    # README reads the same flag: on target, or below / above target ("just below" at the edge, where 88.0% would
    # otherwise seem to contradict "88% to 92% counts as on target")
    main = (repo / "README.md").read_text(encoding="utf-8")
    verdict = "on target" if on_target else ("below target" if held < 0.9 else "above target")
    if held == 0.880:
        verdict = "just below target, at the very edge: by the test's exact check it is just outside the range"
    assert f"held for {held * 100:.1f}% of 250,000 forecasts, {verdict}" in main


def test_app_panel_copies_the_flag_not_a_recomputation(tmp_path):
    """sealed_results.json keeps 5 decimals: a coverage stored as 0.88 may have been 0.880004 (on target) when it
    was judged. The panel copies the opening's flag; it never judges the rounded number again."""
    results = synthetic_results("pass")
    results["floor"]["issued_all"].update(coverage=0.88, on_target=True)
    repo, _ = make_repo(tmp_path, results, scorecard=True)
    assert step21.publish(repo, now=NOW, out=lambda line: None) == 0
    board = json.loads((repo / "app" / "data" / "real" / "scoreboard.json").read_text(encoding="utf-8"))
    assert next(p for p in board["panels"] if p["key"] == "sealed")["floor"]["on_target"] is True


def test_app_rebuild_keeps_the_proof_view(tmp_path):
    """The Proof view (proof.json, scripts/17) shows the same sealed panel; the rebuilt bundle must still carry it."""
    results = synthetic_results("pass")
    repo, _ = make_repo(tmp_path, results, scorecard=True)
    app_dir = repo / "app" / "data" / "real"
    stub = dict(schema_version="1.0", test={}, unseen_exam=dict(panel_key="sealed"), calibration={}, by_year={},
                dam_by_dam={})
    (app_dir / "proof.json").write_text(json.dumps(stub), encoding="utf-8")
    assert step21.publish(repo, now=NOW, out=lambda line: None) == 0
    bundle = (app_dir / "bundle.js").read_text(encoding="utf-8")
    shipped = json.loads(bundle[bundle.index("=") + 1:].strip().rstrip(";"))
    assert shipped["proof"] == stub
    assert next(p for p in shipped["scoreboard"]["panels"] if p["key"] == "sealed")["status"] == "scored"


def test_app_refuses_disagreeing_or_dev_scorecard_files(tmp_path):
    results = synthetic_results("pass")
    repo, results_dir = make_repo(tmp_path, results, scorecard=True)
    shifted = copy.deepcopy(results)
    shifted["scores"][f"P1_R30 | {PRIMARY} | tidemark"]["point"]["bss_B0"] = 0.30
    write_scorecard(results_dir, shifted)                         # the files no longer match sealed_results.json
    before = (repo / "README.md").read_bytes()
    out = []
    assert step21.publish(repo, now=NOW, out=out.append) == 2
    assert "disagree" in out[0] and (repo / "README.md").read_bytes() == before
    write_scorecard(results_dir, results, arena="dev")           # a development result is never shown as sealed
    out = []
    assert step21.publish(repo, now=NOW, out=out.append) == 2
    assert "arena 'sealed'" in out[0]
    assert step21.publish(repo, skip_app=True, now=NOW, out=out.append) == 0    # the docs alone can still go out
