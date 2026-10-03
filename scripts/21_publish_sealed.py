"""Step 21: publish the sealed-region results everywhere they are shown, with one command.

Run it AFTER the opening (scripts/20_open_sealed_region.py --open, Sat 3 Oct 2026 17:30 AEST), once
the raw results in artifacts/sealed/ are committed and pushed, unedited. From the repo folder:

    .venv/Scripts/python.exe scripts/21_publish_sealed.py --check    # preview: prints everything, changes nothing
    .venv/Scripts/python.exe scripts/21_publish_sealed.py            # publish

What it does
  1. Reads the opening's results, exactly as scripts/20 wrote them:
       artifacts/sealed/sealed_results.json                       every score, the PREREG verdicts, the expectations
       artifacts/sealed/scorecard/sealed_TEST/<task>/<file>.json  one file per score (the app panel copies three)
     It refuses anything that is not the sealed opening (a dry run, or a score whose arena is not
     "sealed"), so a rehearsal can never be published as the sealed result.
  2. App: fills the "Sealed region" panel of app/data/real/scoreboard.json with scripts/11's own
     sealed_panel() (the code behind `scripts/11_export_app.py --panel-only --sealed-scores ...`; its floor
     block, with the frozen on_target flag, is copied from sealed_results.json), rebuilds
     app/data/real/bundle.js and the data parts, and checks that the bundle carries the new panel. Two views show
     that one panel: About, and the "Unseen exam" card at the top of Proof (app/js/views/proof.js, which
     draws it with About's panelHtml). The rebuild must keep proof.json (scripts/17) in the bundle too.
  3. Docs: replaces the text between these markers in README.md, docs/PITCH.md and docs/VIDEO_SCRIPT.md
         <!-- SEALED:START -->         ...  <!-- SEALED:END -->    the result block (markers on their own lines)
         <!-- SEALED:START name -->    ...  <!-- SEALED:END -->    a short fill-in inside a line or a table cell
     with plain-language text: the headline numbers, every pre-registered pass mark with PASS or FAIL,
     every pre-declared expectation (inside, below or above its range), and honest words whichever
     way it went. A pass, a partial pass and a fail are all written by the same rules (see `outcome`).
  4. Prints a short summary for the founder to read on camera.

Every number is copied from the result files and only rounded for reading: nothing is recomputed,
nothing is chosen. Before writing anything it checks that the results are the sealed opening's, that
every marker is in place, and that the app's scoreboard has a sealed panel whose numbers agree with
sealed_results.json. If a check fails it says why and changes nothing (exit code 2). If the app step
fails after the docs were written, it says so and exits with code 1.

Other options
    --skip-app   publish the docs only (if the app step cannot run)
    --reset      put the default text ("opens Sat 3 Oct 17:30 AEST") back between every marker of the
                 three docs. The app is not touched. Used before the opening and by the tests.
"""
import argparse
import functools
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "artifacts" / "sealed"                 # written by scripts/20 at the opening
APP_DATA_DIR = REPO / "app" / "data" / "real"
BUNDLE_TOOL = REPO / "app" / "tools" / "build_bundle.py"
TEST_RESULTS = REPO / "artifacts" / "test_results.json"     # the development test years (scripts/15), for comparison

OPENS = "opens Sat 3 Oct 17:30 AEST"
REGION_NAMES = {"sealed_sdowns_newengland": "Southern Downs, Granite Belt and New England"}
FROZEN_CONFIG_HASH = "7d466291008d"                          # PREREG_ADDENDUM_1.md, section 2

# Scores in sealed_results.json are keyed "task | subset | model" (damdays/sealed/report.py).
PRIMARY = "dam_like+octmar+at_risk"                          # farm-like dams, October-March forecasts, at risk
KEY = dict(tidemark=f"P1_R30 | {PRIMARY} | tidemark", g2=f"P1_R30 | {PRIMARY} | G2",
           rating="P2_cell | all | tidemark", rain="P2_cell | all | RAIN")
HARDER_CASES = [  # PREREG "Reported regardless of outcome": (words, task | subset)
    ("persistent dams", "P1_R30 | persistent+octmar+at_risk"),
    ("fully dry (D0)", f"P1_D0 | {PRIMARY}"),
    ("gradual dry-out (D0g)", f"P1_D0g | {PRIMARY}"),
    ("all months", "P1_R30 | dam_like+at_risk"),
    ("without the 3-look rule", f"P1_R30_sens | {PRIMARY}"),
]
CURVE_KEY = f"R30_curve | {PRIMARY}"

# The four pre-registered pass marks (PREREG.md "Pass bars"). The kill rule is reported beside them.
PASS_MARKS = [  # key, what it measures (README table), the bar, a short name, how a miss is named in a sentence
    dict(key="bss_B0", what="Farmer forecast: skill against the usual rate for the region and month (Brier skill "
                            "score vs B0)", bar="+0.10 or more, 95% range above 0", short="beating the usual rate",
         miss="the mark for beating the usual rate"),
    dict(key="bss_B2", what="Farmer forecast: skill against the dam's own track record (vs B2)", bar="+0.05 or more",
         short="beating each dam's own record", miss="the mark for beating each dam's own record"),
    dict(key="cal_slope", what="Farmer forecast: calibration slope (1.0 = chances exactly as spread out as the "
                               "outcomes)", bar="0.8 to 1.2", short="calibration", miss="the calibration mark"),
    dict(key="p2_cell", what="Lender rating: ranking gain over rainfall-only (AUC, 2 km patches)",
         bar="+0.05 or more, 95% range above 0", short="lender rating", miss="the lender-rating mark"),
]
EXPECTATION_WORDS = {  # damdays/sealed/scoring.py EXPECTATIONS labels, in plain words
    "R30 BSS vs B0": "Skill against the usual rate",
    "R30 BSS vs B2": "Skill against the dam's own record",
    "R30 calibration slope": "Calibration slope",
    "R30 CITL": "Calibration-in-the-large (0 = right on average)",
    "R30 Tidemark minus G2 (BSS vs B0 units)": "Gain over the benchmark G2",
    "P2 cell AUC gain over RAIN": "Lender rating: gain over rainfall-only (AUC)",
}

# ---------------------------------------------------------------------------
# The markers in each doc, and their default text (before the opening)
# ---------------------------------------------------------------------------
DOCS = {
    "README.md": ("main", "status", "cell"),
    "docs/PITCH.md": ("main", "sentence", "evidence"),
    "docs/VIDEO_SCRIPT.md": ("main", "line", "caption", "source"),
}
README_ANCHOR = "#sealed-region-opened-sat-3-oct-2026-1730-aest"   # the README heading of the sealed section
DEFAULTS = {
    ("README.md", "main"): (
        "> **The sealed region opens Sat 3 Oct 17:30 AEST.** After the opening, `scripts/21_publish_sealed.py` "
        "writes its results here, copied from `artifacts/sealed/sealed_results.json` (the full page, unedited: "
        "`artifacts/sealed/SEALED_RESULTS.md`).\n"
        ">\n"
        "> What we said to expect, before opening it ([PREREG.md](PREREG.md)): skill against the usual rate of "
        "about +0.15 to +0.23 (central +0.19); gain over G2 of +0.01 to +0.03; lender-rating gain over "
        "rainfall-only of +0.15 to +0.30. These are forecasts, not pass marks. Every number is published, "
        "whatever it shows."),
    ("README.md", "status"): "The sealed region opens Sat 3 Oct 17:30 AEST; its results are added below after that.",
    ("README.md", "cell"): "**Opens Sat 3 Oct 17:30 AEST.** Numbers go here.",
    ("docs/PITCH.md", "main"): (
        "[The unseen exam in numbers: opens Sat 3 Oct 17:30 AEST. After the opening, "
        "`scripts/21_publish_sealed.py` writes them here.]"),
    ("docs/PITCH.md", "sentence"): "[Sealed result, one sentence: opens Sat 3 Oct 17:30 AEST.]",
    ("docs/PITCH.md", "evidence"): "[opens Sat 3 Oct 17:30 AEST]",
    ("docs/VIDEO_SCRIPT.md", "main"): (
        "[The sealed-result line: opens Sat 3 Oct 17:30 AEST. After the opening, `scripts/21_publish_sealed.py` "
        "writes it here from the results, by the templates below.]"),
    ("docs/VIDEO_SCRIPT.md", "line"): "[Sealed-result line: opens Sat 3 Oct 17:30 AEST.]",
    ("docs/VIDEO_SCRIPT.md", "caption"): "[sealed numbers: opens Sat 3 Oct 17:30 AEST]",
    ("docs/VIDEO_SCRIPT.md", "source"): "opens Sat 3 Oct 17:30 AEST",
}

MARKER = re.compile(r"<!-- SEALED:START(?: (?P<name>[a-z][a-z0-9-]*))? -->(?P<body>.*?)<!-- SEALED:END -->", re.S)
START = re.compile(r"<!-- SEALED:START(?: [a-z][a-z0-9-]*)? -->")
END = "<!-- SEALED:END -->"


class Refused(Exception):
    """A check before writing failed: nothing was changed."""


# ===========================================================================
# 1. Read the results (refusing anything that is not the sealed opening)
# ===========================================================================
def get(data, *path, default=None):
    """data[path[0]][path[1]]..., or `default` where any step is missing."""
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return default
        data = data[key]
    return data


def load_results(results_dir):
    """sealed_results.json, after checking it is the sealed opening's (not a dry run, every score arena "sealed")."""
    path = Path(results_dir) / "sealed_results.json"
    if not path.exists():
        raise Refused(f"No {path.name} in {results_dir}: the sealed region has not been opened yet "
                      "(scripts/20_open_sealed_region.py --open writes it).")
    r = json.loads(path.read_text(encoding="utf-8"))
    run = r.get("run", {})
    if run.get("rehearsal") is not False or run.get("name") != "sealed":
        raise Refused(f"{path} is not the sealed opening (run {run.get('name')!r}, rehearsal "
                      f"{run.get('rehearsal')!r}). A dry run is never published as the sealed result.")
    wrong = sorted(key for key, s in {**r.get("scores", {}), **r.get("curves", {})}.items()
                   if s.get("arena") != "sealed" or s.get("block") != "TEST")
    if wrong:
        raise Refused(f"{len(wrong)} score(s) in {path.name} are not block TEST, arena 'sealed' (first: {wrong[0]}).")
    if "verdicts" not in r or KEY["tidemark"] not in r.get("scores", {}):
        raise Refused(f"{path.name} has no PREREG verdicts or no headline score: the opening did not finish.")
    return r


def load_dev_test(path=TEST_RESULTS):
    """The development test years' headline numbers (scripts/15), shown beside the sealed ones; None if absent."""
    try:
        t = json.loads(Path(path).read_text(encoding="utf-8"))
        tm, rating, rain = (t["scores"][KEY[k]] for k in ("tidemark", "rating", "rain"))
        return dict(bss_B0=tm["point"]["bss_B0"], bss_B2=tm["point"]["bss_B2"], auc=tm["point"]["auc"],
                    gain_g2=tm["point"]["d_bss_B0_vs_G2"], rating_auc=rating["point"]["auc"],
                    rain_auc=rain["point"]["auc"], floor=t["floor"]["issued_all"]["coverage"])
    except (OSError, KeyError, TypeError, ValueError):
        return None


def facts_from(r, dev=None, crash_fixes=False):
    """Everything the texts need, read from sealed_results.json (plus the dev test numbers, for comparison)."""
    scores, v = r["scores"], r["verdicts"]
    tm, g2 = scores[KEY["tidemark"]], scores.get(KEY["g2"], {})
    rating, rain = scores.get(KEY["rating"], {}), scores.get(KEY["rain"], {})
    bars_tm, bars_g2 = v.get("p1_pass_bars_tidemark", {}), v.get("p1_pass_bars_g2", {})
    p2, p2_dam = v.get("p2_cell", {}), v.get("p2_dam", {})

    marks = []
    for mark in PASS_MARKS:
        key = mark["key"]
        if key == "p2_cell":
            value, ci, passed, g2_value, g2_passed = p2.get("d_auc_vs_RAIN"), p2.get("ci_dam"), p2.get("passed"), None, None
        else:
            value, passed = get(bars_tm, key, "value"), get(bars_tm, key, "passed")
            ci = get(tm, "ci_dam", key)
            g2_value, g2_passed = get(bars_g2, key, "value"), get(bars_g2, key, "passed")
        marks.append(dict(mark, value=value, ci=ci, passed=bool(passed), g2_value=g2_value, g2_passed=g2_passed))
    n_met = sum(m["passed"] for m in marks)
    kill = bool(p2.get("kill_rule_triggered"))

    gain, gain_ci = get(tm, "point", "d_bss_B0_vs_G2"), get(tm, "ci_dam", "d_bss_B0_vs_G2")
    expectations = []
    for e in v.get("expectations", []):
        expectations.append(dict(e, words=EXPECTATION_WORDS.get(e["expectation"], e["expectation"])))

    floor = get(r, "floor", "issued_all", default={}) or {}
    pooled, single = get(r, "band", "R30", "pooled", default={}), get(r, "band", "R30", "single_block_2009_2016", default={})
    checks = r.get("checks", {})
    code_hash = checks.get("config_hash_of_running_code") or ""
    region = get(r, "counts", "region") or get(r, "run", "target_region") or "sealed region"
    return dict(
        scored_at=r.get("finished_at"), region=REGION_NAMES.get(region, region),
        waterbodies=get(r, "counts", "waterbodies_in_manifest"), rung=get(r, "models_manifest", "rung"),
        code_hash=code_hash[:12], code_quoted=bool(get(checks, "freeze_addendum", "config_hash")),
        files_matched=get(checks, "files", "n_matched"), files_listed=get(checks, "files", "n_listed"),
        reused=list(r.get("reused") or []), crash_fixes=bool(crash_fixes), not_scored=list(r.get("not_scored") or []),
        marks=marks, n_met=n_met, n_marks=len(marks), kill=kill, outcome=outcome(n_met, len(marks), kill),
        g2_passed=bars_g2.get("all_passed"), g2_n_met=sum(bool(get(bars_g2, k, "passed")) for k in ("bss_B0", "bss_B2", "cal_slope")),
        p1=dict(bss_B0=get(tm, "point", "bss_B0"), bss_B0_ci=get(tm, "ci_dam", "bss_B0"), bss_B2=get(tm, "point", "bss_B2"),
                auc=get(tm, "point", "auc"), mean_p=get(tm, "point", "mean_p"), base_rate=get(tm, "point", "base_rate"),
                rows=get(tm, "rows", "scored"), events=get(tm, "rows", "events"), dams=get(tm, "rows", "dams"),
                g2_bss_B0=get(g2, "point", "bss_B0")),
        gain=gain, gain_ci=gain_ci, versus_g2=versus_g2(gain, gain_ci),
        p2=dict(auc=get(rating, "point", "auc"), rain_auc=get(rain, "point", "auc"), gain=p2.get("d_auc_vs_RAIN"),
                gain_ci=p2.get("ci_dam"), passed=bool(p2.get("passed")), cells=get(rating, "rows", "scored"),
                dry=get(rating, "rows", "events"), within=get(rating, "point", "auc_within_season"),
                rain_within=get(rain, "point", "auc_within_season"), dam_gain=p2_dam.get("d_auc_vs_RAIN"),
                dam_gain_ci=p2_dam.get("ci_dam"), dam_passed=p2_dam.get("passed")),
        floor=dict(coverage=floor.get("coverage"), n=floor.get("rows_judged"), target=floor.get("target", 0.9),
                   on_target=floor.get("on_target"), worst=floor.get("worst_year")),
        band=dict(covered=pooled.get("covered"), years=pooled.get("region_years"), single_covered=single.get("covered"),
                  single_years=single.get("region_years"), drier=sorted(map(str, pooled.get("drier_than_band") or [])),
                  wetter=sorted(map(str, pooled.get("wetter_than_band") or []))),
        curve=get(r, "curves", CURVE_KEY, "bss_B0_by_horizon", default={}) or {},
        curve_falling=get(r, "curves", CURVE_KEY, "monotonicity", "share_rows_falling"),
        harder=[(words, get(scores, f"{task} | tidemark", "point", "bss_B0"), get(scores, f"{task} | G2", "point", "bss_B0"))
                for words, task in HARDER_CASES if f"{task} | tidemark" in scores],
        expectations=expectations, n_inside=sum(e["verdict"] == "inside" for e in expectations),
        dev=dev)


def outcome(n_met, n_marks, kill):
    """"pass" (every pass mark met, kill rule not triggered), "fail" (none met) or "partial" (anything between)."""
    if n_met == n_marks and not kill:
        return "pass"
    return "fail" if n_met == 0 else "partial"


def versus_g2(gain, ci):
    """Tidemark against G2 on the same forecasts: "ahead" (range above 0), "behind" (below 0) or "level"."""
    if gain is None:
        return None
    low, high = (ci if ci else (gain, gain))
    return "ahead" if low > 0 else ("behind" if high < 0 else "level")


# ===========================================================================
# 2. Words and numbers
# ===========================================================================
def num(x, digits=3, sign=True):
    """+0.201 (or "-" if missing)."""
    if x is None:
        return "-"
    return f"{x:+.{digits}f}" if sign else f"{x:.{digits}f}"


def bracket(ci, digits=3, sign=True):
    """" [+0.182, +0.220]" (or "" without a range)."""
    return f" [{num(ci[0], digits, sign)}, {num(ci[1], digits, sign)}]" if ci else ""


def range_words(ci, digits=3):
    """"95% range +0.182 to +0.220" (or "no range computed")."""
    return f"95% range {num(ci[0], digits)} to {num(ci[1], digits)}" if ci else "no range computed"


def plain_range(ci, digits=3):
    """"range +0.182 to +0.220", for the pitch and video (where "%" means only how full a dam is)."""
    return f"range {num(ci[0], digits)} to {num(ci[1], digits)}" if ci else "no range computed"


def pct(x, digits=1):
    return "-" if x is None else f"{x * 100:.{digits}f}%"


def less_or_more(x):
    """README wording of a skill score: "20.1% less" or "3.0% more"."""
    return f"{pct(x)} less" if x >= 0 else f"{pct(-x)} more"


def in_ten(share):
    return int(share * 10 + 0.5)


def in_thousand(share):
    return int(share * 1000 + 0.5)


def count(n):
    return "-" if n is None else f"{n:,}"


FRACTIONS = [(1 / 3, "a third"), (0.30, "nearly a third"), (0.25, "a quarter"), (0.225, "nearly a quarter"),
             (0.20, "a fifth"), (0.18, "nearly a fifth"), (1 / 6, "a sixth"), (1 / 7, "about a seventh"),
             (0.125, "an eighth"), (0.10, "a tenth"), (0.05, "a twentieth"), (0.0, "a little")]


def fraction_words(skill):
    """A skill score as a fraction of the error, rounded DOWN (docs/VIDEO_SCRIPT.md): 0.235 -> "nearly a quarter"."""
    for low, words in FRACTIONS:
        if skill >= low:
            return words
    return None


def skill_words(skill):
    """"a fifth less error than guessing the usual rate", for the pitch and video (no "%")."""
    if skill is None:
        return "no skill score"
    if skill <= 0:
        return "no less error than guessing the usual rate"
    return f"{fraction_words(skill)} less error than guessing the usual rate"


def human_time(when):
    """"2026-10-03T17:52:10+10:00" -> "Sat 3 Oct 2026, 17:52 AEST"."""
    if not when:
        return "time not recorded"
    moment = datetime.fromisoformat(str(when)) if not isinstance(when, datetime) else when
    offset = moment.utcoffset()
    zone = {timedelta(hours=10): "AEST", timedelta(hours=11): "AEDT"}.get(offset, moment.strftime("%z")) if offset else ""
    return f"{moment:%a} {moment.day} {moment:%b %Y}, {moment:%H:%M} {zone}".rstrip()


def outcome_words(f):
    """"All 4 pre-registered pass marks met" / "3 of 4 ..." / "None of the 4 ...", plus the kill rule."""
    words = {"pass": f"All {f['n_marks']} pre-registered pass marks met",
             "partial": f"{f['n_met']} of {f['n_marks']} pre-registered pass marks met",
             "fail": f"None of the {f['n_marks']} pre-registered pass marks met"}[f["outcome"]]
    return words + ("; kill rule triggered" if f["kill"] else "")


def missed(f):
    """"the calibration mark and the lender-rating mark"."""
    names = [m["miss"] for m in f["marks"] if not m["passed"]]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def g2_parts(f, readme=False):
    """Tidemark against its benchmark G2, honestly: (headline sentence, detail sentences)."""
    gain, ci, how = f["gain"], f["gain_ci"], f["versus_g2"]
    if how is None:
        return "The gain over the benchmark G2 was not computed.", ""
    what = ("the parts added to G2 (the neural nets, the per-dam correction and the water balance)" if readme
            else "the parts added to our simpler benchmark model")
    if how == "ahead":
        return f"Tidemark beat its own benchmark G2 on the same forecasts by {num(gain)} ({range_words(ci)}).", ""
    if how == "level":
        return ("Tidemark did not beat its own benchmark G2 on the sealed region.",
                f"On the same forecasts the gain was {num(gain)} ({range_words(ci)}), not clearly above zero. In a new "
                f"region, {what} added no reliable skill; G2 alone would have done about as well.")
    return ("Tidemark did worse than its own benchmark G2 on the sealed region.",
            f"On the same forecasts the gain was {num(gain)} ({range_words(ci)}). In a new region, {what} cost skill; "
            "G2 alone would have done better.")


def g2_sentence(f, readme=False):
    return " ".join(part for part in g2_parts(f, readme) if part)


def expectation_value(e, x, declared=False):
    """Calibration slope without a sign; CITL with 2 decimals; everything else signed with 3 (2 when declared)."""
    if "slope" in e["expectation"]:
        return num(x, 2, sign=False)
    return num(x, 2) if (declared or "CITL" in e["expectation"]) else num(x, 3)


def declared_words(e, central=False):
    """"+0.15 to +0.23", or with central=True "+0.15 to +0.23 (central +0.19)" (tables only: no nested brackets)."""
    text = f"{expectation_value(e, e['low'], True)} to {expectation_value(e, e['high'], True)}"
    return text + (f" (central {num(e['central'], 2)})" if central and e.get("central") is not None else "")


def outside_expectations(f):
    """"skill against the usual rate was below its range (+0.120; declared +0.15 to +0.23)", one per miss."""
    return [f"{e['words'][0].lower() + e['words'][1:]} was {e['verdict']} its range "
            f"({expectation_value(e, e['got'])}; declared {declared_words(e)})"
            for e in f["expectations"] if e["verdict"] in ("below", "above")]


def expectations_sentence(f):
    n = len(f["expectations"])
    text = f"{f['n_inside']} of {n} results came out inside the ranges we declared before opening"
    outside = outside_expectations(f)
    not_computed = [e["words"] for e in f["expectations"] if e["verdict"] not in ("inside", "below", "above")]
    if outside:
        text += "; " + "; ".join(outside)
    if not_computed:
        text += "; not computed: " + ", ".join(not_computed)
    return text + "."


def lender_words(f, short=False):
    """The lender rating against rainfall alone, as "N times in 10" (or the kill rule)."""
    p2 = f["p2"]
    if p2["auc"] is None or p2["rain_auc"] is None:
        return "the lender rating was not scored"
    if f["kill"]:
        return "the lender rating did no better than rainfall alone, so the lender claim is dropped"
    words = (f"the lender rating picked the right 2 km patch {in_ten(p2['auc'])} times in 10, against "
             f"{in_ten(p2['rain_auc'])} in 10 for rainfall alone")
    if short:
        words = (f"lender rating: the right 2 km patch {in_ten(p2['auc'])} times in 10 · rainfall "
                 f"{in_ten(p2['rain_auc'])} in 10")
    return words + ("" if p2["passed"] or short else ", short of our mark")


# ===========================================================================
# 3. The texts, one per marker
# ===========================================================================
def readme_main(f, now):
    p1, p2, fl, band, dev = f["p1"], f["p2"], f["floor"], f["band"], f["dev"]
    lines = [f"**{outcome_words(f)}.** The frozen model (Tidemark {f['rung'] or ''}) was scored once on the sealed "
             f"region ({f['region']}), a region it never learned from: {count(f['waterbodies'])} waterbodies, every "
             f"forecast issued from July 2016 to June 2026. Scored {human_time(f['scored_at'])}. Every number below is "
             "copied from [`artifacts/sealed/sealed_results.json`](artifacts/sealed/sealed_results.json) by "
             f"`scripts/21_publish_sealed.py` ({human_time(now)}) and only rounded; the full results page, unedited, is "
             "[`artifacts/sealed/SEALED_RESULTS.md`](artifacts/sealed/SEALED_RESULTS.md).", ""]

    lines.append("**In plain words**")
    lines.append("")
    if p1["bss_B0"] is not None:
        dev_text = f" (development test years: {pct(dev['bss_B0'])} less)" if dev else ""
        line = (f"- **Farmer forecast** (will this dam fall below a third in the next 90 days?): {less_or_more(p1['bss_B0'])} "
                f"error than guessing the usual rate for the region and month{dev_text}, and "
                f"{less_or_more(p1['bss_B2'])} than the dam's own track record.")
        if p1["auc"] is not None:
            line += (f" Shown a dam that fell below a third and one that did not, it gave the right one the higher "
                     f"chance {in_ten(p1['auc'])} times in 10 (AUC {p1['auc']:.2f}).")
        if p1["mean_p"] is not None and p1["base_rate"] is not None:
            line += f" Average chance given {p1['mean_p']:.2f}; share that fell below a third {p1['base_rate']:.2f}."
        line += (f" {count(p1['rows'])} forecasts made October to March for {count(p1['dams'])} farm-like dams; "
                 f"{count(p1['events'])} fell below a third.")
        lines.append(line)
    expected_gain = next((e for e in f["expectations"] if "minus G2" in e["expectation"]), None)
    expected_text = (f" We expected {declared_words(expected_gain)}: {expected_gain['verdict']} that range."
                     if expected_gain and expected_gain["got"] is not None else "")
    if f["versus_g2"] == "ahead":
        lines.append(f"- **Against our own benchmark G2** (the decision-tree model alone), on exactly the same "
                     f"forecasts: ahead by {num(f['gain'])} ({range_words(f['gain_ci'])}).{expected_text}")
    else:
        headline, detail = g2_parts(f, readme=True)
        line = f"- **{headline}** {detail}{expected_text}"
        if f["g2_passed"] is not None:
            line += (" G2 itself met all three farmer-forecast pass marks." if f["g2_passed"] else
                     f" G2 itself met {f['g2_n_met']} of the three farmer-forecast pass marks.")
        lines.append(line)
    if fl["coverage"] is not None:
        verdict = ("on target" if fl["on_target"] else
                   ("below target: here the days given were too many too often" if fl["coverage"] < fl["target"] else
                    "above target: here the days given were more cautious than needed"))
        # Off target by the frozen flag (coverage.py, in floats) though it reads 88.0% or 92.0%: say so, so the
        # sentence does not seem to contradict the range beside it (the app says it the same way).
        if not fl["on_target"] and 88.0 <= round(fl["coverage"] * 100, 1) <= 92.0:
            verdict = "just " + verdict.replace(": here", ", at the very edge: by the test's exact check it is just "
                                                         "outside the range, and here", 1)
        line = (f"- **The DamDays number** (\"at least N days above a third, 9 times in 10\"): held for "
                f"{pct(fl['coverage'])} of {count(fl['n'])} forecasts, {verdict} (the target is {pct(fl['target'], 0)}, "
                "and 88% to 92% counts as on target" + (f"; development test years: {pct(dev['floor'])}" if dev else "")
                + ")")
        if fl["worst"]:
            year = int(fl["worst"]["year"])
            line += f". Worst year: July {year} to June {year + 1}, {pct(fl['worst']['coverage'])}"
        lines.append(line + ".")
    if p2["auc"] is not None and p2["rain_auc"] is not None:
        line = (f"- **Lender rating** (will every farm dam in a 2 km patch run dry between October and March?): shown a "
                f"patch that ran dry and one that did not, it picked the right one {in_ten(p2['auc'])} times in 10 "
                f"(AUC {p2['auc']:.2f}), against {in_ten(p2['rain_auc'])} in 10 for rainfall alone "
                f"({p2['rain_auc']:.2f}; a coin toss is 5 in 10)")
        if dev:
            line += f"; development test years {dev['rating_auc']:.2f} against {dev['rain_auc']:.2f}"
        line += f". {count(p2['cells'])} patch-seasons rated on 1 July 2016 to 2025; {count(p2['dry'])} ran dry. "
        if f["kill"]:
            line += (f"**Kill rule triggered**: rainfall alone came within 0.02 of the rating (gain {num(p2['gain'])}). "
                     "As pre-registered, the lender claim is dropped and DamDays is pitched as the farmer forecast alone.")
        elif p2["passed"]:
            line += f"Gain over rainfall-only {num(p2['gain'])} ({range_words(p2['gain_ci'])}): pass mark met; kill rule not triggered."
        else:
            line += (f"Gain over rainfall-only {num(p2['gain'])} ({range_words(p2['gain_ci'])}): below the pre-registered "
                     "mark (+0.05 with its range above 0), so the lender claim is not supported here; kill rule not triggered.")
        if p2["within"] is not None and p2["rain_within"] is not None:
            line += f" Within a single season: {p2['within']:.2f} against {p2['rain_within']:.2f} for rainfall."
        if p2["dam_gain"] is not None:
            line += (f" The dam-by-dam rating's gain over rainfall-only: {num(p2['dam_gain'])}"
                     f"{bracket(p2['dam_gain_ci'])}, {'met' if p2['dam_passed'] else 'not met'}.")
        lines.append(line)
    if band["years"]:
        line = (f"- **Season band** (how far a very wet or very dry year can move a forecast): covered {band['covered']} "
                f"of {band['years']} July-June years in the region, an independent check here")
        if band["single_years"]:
            line += (f" (the single-block band, reported alongside as pre-registered: {band['single_covered']} of "
                     f"{band['single_years']})")
        outside = ([f"drier than the band: {', '.join(band['drier'])}"] if band["drier"] else []) + (
            [f"wetter than the band: {', '.join(band['wetter'])}"] if band["wetter"] else [])
        lines.append(line + (f"; {'; '.join(outside)}" if outside else "") + ".")
    if f["curve"]:
        cells = ", ".join(f"{num(f['curve'].get(h))} at {h} days" for h in ("30", "60", "90", "180") if h in f["curve"])
        falling = ("none went down as the days went up" if not f["curve_falling"] else
                   f"a share of {f['curve_falling']:.4f} of curves went down as the days went up")
        lines.append(f"- **Runway curve** (chance of falling below a third within 30, 60, 90 and 180 days), skill "
                     f"against each horizon's usual rate: {cells}; {falling}.")
    if f["harder"]:
        parts = [f"{words} {num(t)}" + (f" (G2 {num(g)})" if g is not None else "") for words, t, g in f["harder"]]
        lines.append("- **Harder cases, reported whatever they show** (skill against the usual rate): "
                     + "; ".join(parts) + ".")
    if f["not_scored"]:
        lines.append("- **Could not be scored** (no labelled forecasts, or no events): "
                     + "; ".join(f"{n['task']} {n['subset']} {n['model']}" for n in f["not_scored"]) + ".")
    opened = (f"- **How it was opened:** {count(f['files_matched'])} of {count(f['files_listed'])} sealed files matched "
              "their published fingerprints before anything was read. ")
    if f["code_hash"]:
        opened += (f"Code fingerprint of the run: `{f['code_hash']}`, "
                   + ("the frozen one (quoted in [PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md))." if f["code_quoted"] else
                      f"not the frozen `{FROZEN_CONFIG_HASH}` (a logged crash fix changed the code)."))
    if f["crash_fixes"]:
        opened += " Crash fixes are logged in [`artifacts/sealed/CRASH_FIXES.md`](artifacts/sealed/CRASH_FIXES.md)."
    if f["reused"]:
        opened += (f" The run resumed after a crash: {' and '.join(f['reused'])} were reloaded, so exactly the same "
                   "forecasts were scored.")
    lines += [opened.rstrip(), ""]

    lines += ["**Pass marks** (written before any code: [PREREG.md](PREREG.md), \"Pass bars\"):", "",
              "| pass mark | bar | DamDays (Tidemark) | benchmark G2 |", "|---|---|---|---|"]
    for m in f["marks"]:
        digits, sign = (2, False) if m["key"] == "cal_slope" else (3, True)
        tm = f"{num(m['value'], digits, sign)}{bracket(m['ci'], digits, sign) if m['key'] != 'cal_slope' else ''} " \
             f"**{'PASS' if m['passed'] else 'FAIL'}**"
        g2 = ("(G2 has no lender rating)" if m["key"] == "p2_cell" else
              f"{num(m['g2_value'], digits, sign)} **{'PASS' if m['g2_passed'] else 'FAIL'}**")
        lines.append(f"| {m['what']} | {m['bar']} | {tm} | {g2} |")
    lines.append(f"| Kill rule: rainfall-only within 0.02 of the rating | must not trigger | "
                 f"{'**TRIGGERED**: lender claim dropped' if f['kill'] else 'not triggered'} | |")
    lines += ["", f"**What we said to expect, before opening** (forecasts, not pass marks: [PREREG.md](PREREG.md), "
                  f"\"Pre-declared expectations\"). {expectations_sentence(f)}", "",
              "| expectation | declared before opening | got [95% range] | |", "|---|---|---|---|"]
    for e in f["expectations"]:
        got = expectation_value(e, e["got"])
        if e.get("ci_dam"):
            got += f" [{expectation_value(e, e['ci_dam'][0])}, {expectation_value(e, e['ci_dam'][1])}]"
        lines.append(f"| {e['words']} | {declared_words(e, central=True)} | {got} | {e['verdict']} |")
    return "\n".join(lines)


def readme_status(f, now):
    return (f"The sealed region was opened and scored once on {human_time(f['scored_at'])}; its results were added "
            f"below on {human_time(now)}.")


def readme_cell(f):
    text = {"pass": "**All pass marks met.**", "partial": f"**{f['n_met']} of {f['n_marks']} pass marks met.**",
            "fail": f"**Pass marks not met** (0 of {f['n_marks']})."}[f["outcome"]]
    if f["kill"]:
        text += " Kill rule triggered."
    if f["versus_g2"] in ("level", "behind"):
        text += " Did not beat G2."
    return text + f" [Details below]({README_ANCHOR})."


def pitch_sentence(f):
    skill = skill_words(f["p1"]["bss_B0"])
    lender = lender_words(f)
    if f["outcome"] == "pass":
        text = f"DamDays met all {f['n_marks']} pass marks we wrote before any code: {skill}, and {lender}"
    elif f["outcome"] == "partial":
        shorts = [m["short"] for m in f["marks"] if not m["passed"]]
        misses = shorts[0] if len(shorts) == 1 else ", ".join(shorts[:-1]) + " and " + shorts[-1]
        text = (f"DamDays met {f['n_met']} of the {f['n_marks']} pass marks we wrote before any code (missed: "
                f"{misses}): {skill}, and {lender}")
    else:
        text = f"DamDays met none of the {f['n_marks']} pass marks we wrote before any code ({skill}, and {lender})"
    if f["versus_g2"] == "level":
        text += "; it did not beat our simpler benchmark model there"
    elif f["versus_g2"] == "behind":
        text += "; our simpler benchmark model did better there"
    if f["outcome"] != "pass":
        text += "; every number is published, as promised"
    return text + "."


def pitch_evidence(f):
    p1, p2 = f["p1"], f["p2"]
    text = (f"{f['n_met']} of {f['n_marks']} pass marks met; below-a-third skill {num(p1['bss_B0'])} "
            f"({plain_range(p1['bss_B0_ci'])}); gain over G2 {num(f['gain'])}")
    if p2["auc"] is not None and p2["rain_auc"] is not None:
        text += f"; lender rating {p2['auc']:.2f} against rainfall-only {p2['rain_auc']:.2f}"
    return text + ("; kill rule triggered" if f["kill"] else "")


def pitch_main(f, now):
    p1, p2, fl = f["p1"], f["p2"], f["floor"]
    expect = {e["expectation"]: e for e in f["expectations"]}
    lines = [f"**The unseen exam in numbers** (the sealed region, scored once on {human_time(f['scored_at'])}; "
             f"from `artifacts/sealed/SEALED_RESULTS.md`): **{outcome_words(f)}.**", ""]
    e = expect.get("R30 BSS vs B0")
    lines.append(f"- Below-a-third forecasts: {skill_words(p1['bss_B0'])} (skill {num(p1['bss_B0'])}, "
                 f"{plain_range(p1['bss_B0_ci'])}" + (f"; we expected {declared_words(e)}" if e else "") + ").")
    e = expect.get("R30 Tidemark minus G2 (BSS vs B0 units)")
    how = {"ahead": "ahead by", "level": "no clear gain:", "behind": "behind:"}.get(f["versus_g2"], "not computed:")
    lines.append(f"- Against our own benchmark model G2, on the same forecasts: {how} {num(f['gain'])} "
                 f"({plain_range(f['gain_ci'])}" + (f"; we expected {declared_words(e)}" if e else "") + ").")
    if fl["coverage"] is not None:
        lines.append(f"- \"At least N days\" held {in_thousand(fl['coverage'])} times in 1,000 (target "
                     f"{in_thousand(fl['target'])}).")
    if p2["auc"] is not None and p2["rain_auc"] is not None:
        rule = "kill rule TRIGGERED: the lender claim is dropped" if f["kill"] else "kill rule not triggered"
        lines.append(f"- Lender rating: the right 2 km patch {in_ten(p2['auc'])} times in 10, rainfall alone "
                     f"{in_ten(p2['rain_auc'])} in 10 (gain {num(p2['gain'])}; mark +0.05; {rule}).")
    lines.append("- Pass marks: " + "; ".join(f"{m['short']} {'PASS' if m['passed'] else 'FAIL'}"
                                              for m in f["marks"]) + ".")
    lines.append(f"- {expectations_sentence(f)}")
    return "\n".join(lines)


def video_line(f):
    """The beat-5 line, at most 12 words, by the templates in docs/VIDEO_SCRIPT.md."""
    if f["outcome"] == "pass":
        skill = f["p1"]["bss_B0"]
        for text in (f"It passed every mark: {fraction_words(skill)} less error than the usual guess.",
                     f"Every mark passed: {fraction_words(skill)} less error than the usual guess.",
                     "It passed every mark we set before writing code."):
            if len(text.split()) <= 12:
                return text
    if f["outcome"] == "partial":
        misses = f["n_marks"] - f["n_met"]
        return f"It met {f['n_met']} of {f['n_marks']} marks; we published the {'miss' if misses == 1 else 'misses'}."
    return "It fell short of our marks. Every number is published, as promised."


def video_caption(f):
    fl = f["floor"]
    first = {"pass": f"**All {f['n_marks']} pass marks met**", "partial": f"**{f['n_met']} of {f['n_marks']} pass marks met**",
             "fail": f"**Pass marks not met (0 of {f['n_marks']})**"}[f["outcome"]]
    second = skill_words(f["p1"]["bss_B0"])
    if fl["coverage"] is not None:
        second += f" · \"at least N days\" held {in_ten(fl['coverage'])} times in 10"
    third = ("lender rating: no better than rainfall · claim dropped" if f["kill"] else lender_words(f, short=True))
    return f"{first}<br>{second}<br>{third}"


def video_source(f):
    p1, p2, fl = f["p1"], f["p2"], f["floor"]
    e = next((e for e in f["expectations"] if e["expectation"] == "R30 BSS vs B0"), None)
    text = (f"{f['n_met']} of {f['n_marks']} pass marks; skill {num(p1['bss_B0'])}"
            + (f" (expected {declared_words(e)})" if e else ""))
    if p2["auc"] is not None and p2["rain_auc"] is not None:
        text += f"; rating AUC {p2['auc']:.3f} against rainfall-only {p2['rain_auc']:.3f}"
    if fl["coverage"] is not None:
        text += f"; floor held {fl['coverage']:.3f}"
    return text


def video_main(f, now):
    fl = f["floor"]
    line = video_line(f)
    captions = [f"\"{skill_words(f['p1']['bss_B0'])}\""]
    if fl["coverage"] is not None:
        captions.append(f"\"'at least N days' held {in_ten(fl['coverage'])} times in 10\"")
    if f["p2"]["auc"] is not None and f["p2"]["rain_auc"] is not None and not f["kill"]:
        captions.append(f"\"the lender rating picks the right 2 km patch {in_ten(f['p2']['auc'])} times in 10, rainfall "
                        f"{in_ten(f['p2']['rain_auc'])} in 10\"")
    g2 = {"ahead": "It also beat our own simpler model, G2, by a small margin.",
          "level": "It did not beat our simpler benchmark model there.",
          "behind": "Our simpler benchmark model did better there."}.get(f["versus_g2"], "")
    outcome_text = outcome_words(f)
    lines = [f"**Written from the results by `scripts/21_publish_sealed.py`** on {human_time(now)} "
             f"(outcome: {outcome_text[0].lower() + outcome_text[1:]}). Read it against "
             "`artifacts/sealed/SEALED_RESULTS.md` before recording.", "",
             f"- **The line (beat 5), {len(line.split())} words:** \"{line}\"",
             f"- **Caption words:** {'; '.join(captions)}."]
    if g2:
        lines.append(f"- **About the benchmark G2, if it comes up:** \"{g2}\"")
    if f["kill"]:
        lines.append("- **Kill rule triggered:** rainfall alone came within 0.02 of the lender rating. As pre-registered, "
                     "drop the lender claim: cut or reword beat 8 to say so.")
    lines.append(f"- **Expectations:** {expectations_sentence(f)}")
    return "\n".join(lines)


def published_texts(f, now):
    """The text for every marker of every doc, once the results are in."""
    return {
        ("README.md", "main"): readme_main(f, now), ("README.md", "status"): readme_status(f, now),
        ("README.md", "cell"): readme_cell(f),
        ("docs/PITCH.md", "main"): pitch_main(f, now), ("docs/PITCH.md", "sentence"): pitch_sentence(f),
        ("docs/PITCH.md", "evidence"): pitch_evidence(f),
        ("docs/VIDEO_SCRIPT.md", "main"): video_main(f, now), ("docs/VIDEO_SCRIPT.md", "line"): video_line(f),
        ("docs/VIDEO_SCRIPT.md", "caption"): video_caption(f), ("docs/VIDEO_SCRIPT.md", "source"): video_source(f),
    }


# ===========================================================================
# 4. Markers: check, then fill
# ===========================================================================
def check_markers(text, doc):
    """Refuse unless the doc has every marker it needs, each START closed by an END, and no unknown name."""
    starts, ends, blocks = len(START.findall(text)), text.count(END), list(MARKER.finditer(text))
    if not (starts == ends == len(blocks)):
        raise Refused(f"{doc}: unbalanced SEALED markers ({starts} START, {ends} END). Fix them by hand first.")
    names = {m.group("name") or "main" for m in blocks}
    wanted = set(DOCS[doc])
    if names != wanted:
        raise Refused(f"{doc}: SEALED markers {sorted(names)}, expected {sorted(wanted)}. Missing: "
                      f"{sorted(wanted - names) or 'none'}; unknown: {sorted(names - wanted) or 'none'}.")
    for m in blocks:
        if (m.group("name") or "main") == "main":
            before, after = text[:m.start()], text[m.end():]
            if (before and not before.endswith("\n")) or (after and not after.startswith(("\n", "\r\n"))):
                raise Refused(f"{doc}: the main SEALED markers must each be on a line of their own.")


def fill(text, doc, contents):
    """The doc with every marker's text replaced by contents[(doc, name)] (markers kept, line endings kept)."""
    check_markers(text, doc)
    newline = "\r\n" if "\r\n" in text else "\n"

    def replace(m):
        name = m.group("name") or "main"
        body = contents[(doc, name)]
        start = f"<!-- SEALED:START{'' if name == 'main' else ' ' + name} -->"
        if name == "main":       # a blank line before END, so a table at the end of the block ends there
            return start + newline + body.replace("\n", newline) + newline + newline + END
        if "\n" in body or "|" in body.replace("\\|", ""):
            raise Refused(f"{doc}: the text for marker '{name}' must be one line without '|' (it sits in a table).")
        return start + body + END
    return MARKER.sub(replace, text)


def read_doc(repo, doc):
    path = Path(repo) / doc
    if not path.exists():
        raise Refused(f"{doc} not found in {repo}.")
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def write_doc(repo, doc, text):
    with open(Path(repo) / doc, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def fill_all(repo, contents):
    """{doc: (old text, new text)} for the three docs; refuses (nothing written) if any marker is wrong."""
    return {doc: (old, fill(old, doc, contents)) for doc, old in ((d, read_doc(repo, d)) for d in DOCS)}


# ===========================================================================
# 5. The app: the sealed panel of scoreboard.json, then bundle.js
# ===========================================================================
@functools.lru_cache(maxsize=1)
def load_step11():
    """scripts/11_export_app.py as a module (its sealed_panel() is the one definition of the panel).

    Loaded only for the app step: it imports the model code (torch), which takes a few seconds.
    """
    spec = importlib.util.spec_from_file_location("step11_export_app", REPO / "scripts" / "11_export_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_panel(scorecard_dir, step11, results=None):
    """The scored sealed panel, from the three scorecard files scripts/20 wrote (block TEST, arena sealed), plus the
    floor block (held, target, tolerance, the frozen on_target flag) from `results`, the sealed_results.json read here."""
    try:
        return step11.sealed_panel(scorecard_dir, results=results)
    except SystemExit as problem:            # scripts/11 stops with a message if a file is missing or not sealed
        raise Refused(f"App panel: {problem}") from None


def check_board(app_dir):
    """The published scoreboard, refused unless it is a test-season export with a sealed panel."""
    path = Path(app_dir) / "scoreboard.json"
    if not path.exists():
        raise Refused(f"No {path}: export the app first (scripts/11_export_app.py --rung L3 --season 2018).")
    board = json.loads(path.read_text(encoding="utf-8"))
    if board.get("source") != "dev_test" or not any(p.get("key") == "sealed" for p in board.get("panels", [])):
        raise Refused(f"{path} has no sealed panel (it is not a test-season export): run the full export first.")
    return board


def same(a, b):
    """Equal flags, or numbers equal to 6 decimals (both files keep 5)."""
    if a is None or b is None or isinstance(a, bool) or isinstance(b, bool):
        return a == b
    return abs(a - b) < 1e-6


def panel_disagreements(panel, f):
    """Numbers the app panel (scorecard files) and the docs (sealed_results.json) must share; any that differ."""
    p1_passed = all(m["passed"] for m in f["marks"] if m["key"] != "p2_cell")
    pairs = [("runway skill vs the usual rate", get(panel, "runway", "skill_vs_usual_rate", "value"), f["p1"]["bss_B0"]),
             ("runway gain over G2", get(panel, "runway", "gain_vs_benchmark", "value"), f["gain"]),
             ("runway pass bars", get(panel, "runway", "pass_bars_met"), p1_passed),
             ("rating gain over rainfall-only", get(panel, "rating", "gain_vs_rain", "value"), f["p2"]["gain"]),
             ("rating pass bar", get(panel, "rating", "pass_bar_met"), f["p2"]["passed"]),
             ("kill rule", get(panel, "rating", "kill_rule_triggered"), f["kill"]),
             ("floor held", get(panel, "floor", "held"), f["floor"]["coverage"]),
             ("floor on target", get(panel, "floor", "on_target"), f["floor"]["on_target"])]
    return [f"{what}: app {a!r}, results {b!r}" for what, a, b in pairs if not same(a, b)]


def app_wording_warnings(panel, about_js=""):
    """Lines of app/js/views/about.js worded only for a good result that would read wrongly with this panel.

    about_js is the text of about.js: a line already worded both ways is not warned about.
    """
    warnings = []
    gain = get(panel, "runway", "gain_vs_benchmark")
    if gain and gain["ci_low"] <= 0 and "Not clearly ahead of" not in about_js:
        warnings.append(f"The About page always says 'Ahead of the pre-registered benchmark model G2'; here the gain is "
                        f"{gain['value']:+.3f} (95% range {gain['ci_low']:+.3f} to {gain['ci_high']:+.3f}), not clearly "
                        "ahead. Say so on camera, or reword that line in app/js/views/about.js.")
    for field in ("skill_vs_usual_rate", "skill_vs_own_record"):
        skill = get(panel, "runway", field)
        if skill and skill["value"] < 0 and "% more" not in about_js:
            warnings.append(f"The About page words {field} as '... % less forecast error'; here it is negative "
                            f"({skill['value']:+.3f}): reword that line in app/js/views/about.js.")
    return warnings


def write_panel(app_dir, board, panel):
    """Put the panel into scoreboard.json, rebuild bundle.js (app/tools/build_bundle.py), check the bundle carries it."""
    app_dir = Path(app_dir).resolve()          # build_bundle.py runs from the repo folder: never a relative path
    board = dict(board, panels=[panel if p.get("key") == "sealed" else p for p in board["panels"]])
    (app_dir / "scoreboard.json").write_text(json.dumps(board, indent=1, ensure_ascii=False, allow_nan=False),
                                             encoding="utf-8")
    subprocess.run([sys.executable, str(BUNDLE_TOOL), str(app_dir)], check=True, cwd=REPO, capture_output=True,
                   text=True)
    text = (app_dir / "bundle.js").read_text(encoding="utf-8")
    bundle = json.loads(text[text.index("=") + 1:].strip().rstrip(";"))
    shipped = next(p for p in bundle["scoreboard"]["panels"] if p.get("key") == "sealed")
    if shipped != json.loads(json.dumps(panel)):
        raise RuntimeError("bundle.js does not carry the new sealed panel.")
    if (app_dir / "proof.json").exists() and "proof" not in bundle:     # the Proof view's charts (scripts/17)
        raise RuntimeError("bundle.js lost proof.json (the Proof view): check app/tools/build_bundle.py.")
    # The app reads the split data parts (parts.js lists them), not bundle.js: the "first" part must carry it too.
    first = first_part(app_dir)
    if first is not None and next((p for p in first.get("scoreboard", {}).get("panels", [])
                                   if p.get("key") == "sealed"), None) != shipped:
        raise RuntimeError("The app's first data part (parts.js) does not carry the new sealed panel.")
    return shipped


def first_part(app_dir):
    """The "first" data part that app_dir/parts.js lists, as the app loads it; None without parts.js."""
    listing_path = Path(app_dir) / "parts.js"
    if not listing_path.exists():
        return None
    text = listing_path.read_text(encoding="utf-8")
    listing = json.loads(text[text.index("] = ") + 4:text.index("};\n") + 1])
    part = (Path(app_dir) / listing["files"]["first"]).read_text(encoding="utf-8")
    return json.loads(part[part.index("] = ") + 4:].strip().rstrip(";"))


# ===========================================================================
# 6. What to say on camera
# ===========================================================================
def camera_summary(f):
    p1, p2, fl = f["p1"], f["p2"], f["floor"]
    e = next((e for e in f["expectations"] if e["expectation"] == "R30 BSS vs B0"), None)
    lines = ["THE SEALED REGION, SCORED ONCE: WHAT TO SAY ON CAMERA", "",
             f"  {outcome_words(f)}.",
             f"  - Farmer forecast: {skill_words(p1['bss_B0'])} (skill {num(p1['bss_B0'])}"
             + (f"; we expected {declared_words(e)}: {e['verdict']}" if e else "") + ").",
             f"  - Benchmark G2: {g2_sentence(f)}"]
    if p2["auc"] is not None and p2["rain_auc"] is not None:
        lines.append(f"  - Lender rating: the right 2 km patch {in_ten(p2['auc'])} times in 10; rainfall alone "
                     f"{in_ten(p2['rain_auc'])} in 10. Kill rule: "
                     + ("TRIGGERED, so the lender claim is dropped." if f["kill"] else "not triggered."))
    if fl["coverage"] is not None:
        lines.append(f"  - \"At least N days\": held {in_thousand(fl['coverage'])} times in 1,000 (target "
                     f"{in_thousand(fl['target'])}).")
    if f["outcome"] != "pass":
        lines.append(f"  - Missed: {missed(f) or 'none'}.")
    lines += [f"  - Expectations: {expectations_sentence(f)}",
              f"  Video line: \"{video_line(f)}\"",
              "  Every number is published, as promised: artifacts/sealed/SEALED_RESULTS.md"]
    return lines


# ===========================================================================
# Main
# ===========================================================================
def reset(repo=REPO):
    """Put the default text back between every marker of the three docs; returns the docs that changed."""
    changed = []
    for doc, (old, new) in fill_all(repo, DEFAULTS).items():
        if new != old:
            write_doc(repo, doc, new)
            changed.append(doc)
    return changed


def publish(repo=REPO, results_dir=None, app_dir=None, check=False, skip_app=False, now=None, out=print):
    """Steps 1-4 of the module docstring. Returns the exit code (0 done, 1 app step failed, 2 refused)."""
    results_dir = Path(results_dir or Path(repo) / "artifacts" / "sealed")
    app_dir = Path(app_dir or Path(repo) / "app" / "data" / "real")
    now = now or datetime.now().astimezone()
    try:
        r = load_results(results_dir)
        f = facts_from(r, load_dev_test(Path(repo) / "artifacts" / "test_results.json"),
                       crash_fixes=(results_dir / "CRASH_FIXES.md").exists())
        texts = published_texts(f, now)
        docs = fill_all(repo, texts)
        panel, board, warnings = None, None, []
        if not skip_app:
            board = check_board(app_dir)
            panel = build_panel(results_dir / "scorecard" / "sealed_TEST", load_step11(), r)
            differ = panel_disagreements(panel, f)
            if differ:
                raise Refused("The app's scorecard files and sealed_results.json disagree (" + "; ".join(differ)
                              + "). Find out why before publishing; --skip-app publishes the docs alone.")
            about_js = Path(repo) / "app" / "js" / "views" / "about.js"
            warnings = app_wording_warnings(panel, about_js.read_text(encoding="utf-8") if about_js.exists() else "")
    except Refused as problem:
        out(f"REFUSED: {problem}")
        out("Nothing was changed.")
        return 2

    if check:
        out("CHECK ONLY: nothing is written. The new text for each marker:")
        for (doc, name), text in texts.items():
            out(f"\n----- {doc} [{name}] -----\n{text}")
        out("")
    else:
        for doc, (old, new) in docs.items():
            if new != old:
                write_doc(repo, doc, new)
        out("Docs updated: " + ", ".join(f"{doc} ({len(DOCS[doc])} markers)" for doc in docs))
    status = 0
    if panel is not None and not check:
        try:
            write_panel(app_dir, board, panel)
            out(f"App updated: {app_dir / 'scoreboard.json'} (sealed panel: scored) and bundle.js rebuilt and checked.")
        except Exception as problem:            # the docs are written; say what failed and how to finish
            status = 1
            out(f"APP NOT UPDATED: {problem}")
            out("The docs are published. Fill the app panel by hand: .venv/Scripts/python.exe "
                "scripts/11_export_app.py --panel-only --sealed-scores artifacts/sealed/scorecard/sealed_TEST")
    elif panel is not None:
        out("App: the sealed panel was built from the scorecard files and agrees with sealed_results.json "
            "(not written: --check).")
    out("")
    out("=" * 78)
    for line in camera_summary(f):
        out(line)
    out("=" * 78)
    for warning in warnings:
        out(f"CHECK THE APP'S WORDING: {warning}")
    if not check:
        out("\nNext, by hand: read the changes (git diff), then commit and push them:")
        # -A: the rebuild writes new hashed data parts (app/data/real/first.<hash>.js ...), deletes the old ones,
        # rewrites parts.js and restamps app/sw-version.js; the app reads the parts, not bundle.js.
        out("  git add -A README.md docs/PITCH.md docs/VIDEO_SCRIPT.md app/data app/sw-version.js")
        out("  git status   (expect the new app/data/real/first.<hash>.js added and the old one deleted)")
        out('  git commit -m "Sealed results published (scripts/21_publish_sealed.py)"')
        out("  git push")
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], epilog="Runbook: docs/SEALED_OPENING.md")
    parser.add_argument("--check", action="store_true", help="preview: print every new text and the summary; write nothing")
    parser.add_argument("--skip-app", action="store_true", help="publish the docs only (leave the app untouched)")
    parser.add_argument("--reset", action="store_true",
                        help=f"put the default text ('{OPENS}') back between the docs' markers (the app is not touched)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.reset:
        try:
            changed = reset(REPO)
        except Refused as problem:
            print(f"REFUSED: {problem}\nNothing was changed.")
            return 2
        print("Default text restored in: " + (", ".join(changed) if changed else "nothing (already the default)"))
        return 0
    return publish(REPO, RESULTS_DIR, APP_DATA_DIR, check=args.check, skip_app=args.skip_app)


if __name__ == "__main__":
    sys.exit(main())
