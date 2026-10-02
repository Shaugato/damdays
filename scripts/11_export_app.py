"""Step 11: export real forecasts for the app (app/data/real/), then pack them with app/tools/build_bundle.py.

Run from the repo folder:
    # THE SHIPPED APP: the frozen rung L3; Rewind and Rating on the 2018-19 drought season (test years)
    .venv/Scripts/python.exe scripts/11_export_app.py --rung L3 --season 2018 --refit-live

    # After the sealed region is opened (Sat 3 Oct 17:30 AEST): fill the "Sealed region" panel only
    .venv/Scripts/python.exe scripts/11_export_app.py --panel-only --sealed-scores artifacts/sealed/scorecard/sealed_TEST

    # Validation seasons (what the app showed before the one-time TEST scoring)
    .venv/Scripts/python.exe scripts/11_export_app.py --rung L1 --season 2013

What it does
  1. Live (Runway view). Tidemark fitted at the production cutoff: the day after the last
     satellite look (damdays/export/live_model.py). Each dam-like dam gets a forecast from its
     latest look (September 2026). The fit takes about 17 minutes at rung L1 and about 25 at L3;
     its forecasts are saved in data_cache/preds/LIVE/tidemark/ and reused until --refit-live
     (or new data).
  2. Rewind. Forecasts on 1 Nov, 1 Jan and 1 Mar of one season, and what happened next, made by a
     model that never learned from that season:
       a validation season (2009-10 to 2014-15): the VAL-setting model, fitted only on answers
         final before 1 Jan 2009 (scripts/08 saved its forecasts);
       a test season (2016-17 to 2025-26): the FROZEN TEST-setting model, fitted only on answers
         final before 1 Jul 2016 (scripts/13 saved its forecasts). Allowed only after the one-time
         TEST scoring (scripts/15, artifacts/test_results.json), and only with the forecast files
         that were scored: each file's fingerprint must equal the one step 13 recorded.
     The dates start from October, December and February looks, the October-March months of the
     pre-registered headline set. Outcomes are the PREREG R30 labels ("below a third").
  3. Rating. The same season's 2 km cell ratings from the same model, the rainfall-only score
     (the RAIN baseline fitted for that block) and which cells ran dry (the PREREG D0 cell label).
  4. Scoreboard. Validation season: validation scores (artifacts/val_tidemark_<rung>.json).
     Test season: copied from artifacts/test_results.json and labelled "Development regions,
     2016-2026, scored once"; the one-season line is computed by the scorecard on the same frozen
     forecasts (the TEST ledger accepts it only as "same_predictions", see test_season_scores);
     plus a "Sealed region" panel, a placeholder until --sealed-scores points at the opening's
     scorecard files (scripts/20 writes one JSON per score to artifacts/sealed/scorecard/sealed_TEST/).
  5. Writes the six JSON files, checks every contract rule, and runs app/tools/build_bundle.py.

The production fit learns from every answer up to 2026, as a model for today must, but its
forecasts are only shown, never scored. This script never reads the sealed region's data: the
sealed panel reads only the scorecard result files that scripts/20 writes at the opening, and
only when --sealed-scores is given.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Let "import damdays" work when this file is run directly.
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from damdays import config  # noqa: E402
from damdays.data.splits import hydro_year, time_block  # noqa: E402
from damdays.evaluation import score  # noqa: E402
from damdays.evaluation.inputs import KEY, prepare_table  # noqa: E402
from damdays.evaluation.ledger import Ledger, prediction_hash  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.export import app_data as ad  # noqa: E402
from damdays.export import live_model  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import tidemark  # noqa: E402
from damdays.models.predictions import load_predictions, prediction_path, save_predictions  # noqa: E402

OUT_DIR = REPO / "app" / "data" / "real"
BUNDLE_TOOL = REPO / "app" / "tools" / "build_bundle.py"
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step11_app"
RAIN_ALL = config.ARTIFACTS_DIR / "scorecard" / "step03_val" / "dev_VAL" / "P2_cell" / "rain__all.json"
TEST_RESULTS = config.ARTIFACTS_DIR / "test_results.json"                   # scripts/15: the one-time dev TEST scoring
TEST_FIT_SUMMARY = config.ARTIFACTS_DIR / "test_setting_fit_summary.json"   # scripts/13: the frozen fits + fingerprints
SIZE_TARGET_MB = 5.0                     # the six JSON files should stay about this small (bundle.js copies them)

# The sealed region, as PREREG.md describes it (no sealed file is read here).
SEALED_TITLE = "Sealed region: opened Sat 3 Oct 17:30"
SEALED_NAME = "Southern Downs, Granite Belt and New England"
SEALED_FILL_COMMAND = ("scripts/11_export_app.py --panel-only --sealed-scores "
                       "artifacts/sealed/scorecard/sealed_TEST")
# PREREG.md "Pre-declared expectations for the sealed region" (forecasts, not pass bars), restated in
# PREREG_ADDENDUM_1.md section 7. Shown next to the sealed numbers so anyone can compare.
# `field` names the panel number each one is compared with in the app.
SEALED_EXPECTATIONS = [
    dict(what="Runway skill vs the usual rate (R30 BSS vs B0)", low=0.15, high=0.23,
         field="runway.skill_vs_usual_rate"),
    dict(what="Runway skill vs the dam's own record (R30 BSS vs B2)", low=0.08, high=0.15,
         field="runway.skill_vs_own_record"),
    dict(what="Tidemark minus the benchmark G2 (R30)", low=0.01, high=0.03, field="runway.gain_vs_benchmark"),
    dict(what="Rating AUC gain over rainfall-only (P2 cell)", low=0.15, high=0.30, field="rating.gain_vs_rain"),
]
# PREREG.md "Pass bars" for the rating: AUC gain over RAIN at least +0.05 with the 95% range above 0;
# kill rule: if RAIN comes within 0.02 AUC of the rating, drop the finance claim.
P2_BAR, KILL_RULE_GAP = 0.05, 0.02
# The three scorecard result files a panel is built from (file names written by damdays/evaluation/report.py).
PANEL_FILES = {"p1": ("P1_R30", "tidemark__dam_like+octmar+at_risk.json"),
               "p2": ("P2_cell", "tidemark__all.json"),
               "rain": ("P2_cell", "rain__all.json")}

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


def require(path, step):
    """Stop with a clear message if an earlier step's output is missing."""
    if not Path(path).exists():
        raise SystemExit(f"Missing {path}: run {step} first.")
    return Path(path)


def read_json(path, step):
    """A JSON file written by an earlier step."""
    return json.loads(require(path, step).read_text(encoding="utf-8"))


def human_day(when):
    """"2026-10-02 20:36" -> "2 Oct 2026"."""
    day = pd.Timestamp(when)
    return f"{day.day} {day.strftime('%b %Y')}"


# ===========================================================================
# Which season to rewind, and which block it is in
# ===========================================================================
def seasons_in(block):
    """Seasons (July-June start years) whose 1 July rating and whole October-March fall in the block.

    VAL: 2009-10 to 2014-15. TEST: 2016-17 to 2025-26.
    """
    if block == "VAL":
        return list(range(pd.Timestamp(config.VAL_START).year, pd.Timestamp(config.VAL_END).year - 1))
    return list(range(pd.Timestamp(config.TEST_START).year, pd.Timestamp(config.TEST_END).year))


def r30_starts_per_season(events, dams, block):
    """How many times the app's dams fell below a third (R30 starts) in each season of the block."""
    r30 = events[(events["kind"] == "R30") & events["uid"].astype(str).isin(set(dams["uid"]))]
    counts = pd.Series(hydro_year(r30["start_date"])).value_counts().reindex(seasons_in(block), fill_value=0)
    log(f"R30 starts per {block} season among the app's dams: "
        + ", ".join(f"{ad.season_label(s)} {n}" for s, n in counts.items()))
    return {ad.season_label(s): int(n) for s, n in counts.items()}


def driest_val_season(counts):
    """The validation season with the most R30 starts (the default when --season is "auto")."""
    label = max(counts, key=counts.get)
    return int(label[:4])


def rewind_days(season, months):
    """The Rewind issue dates: the 1st of each month in `months` (July-June order) of the season."""
    return [pd.Timestamp(season if m >= 7 else season + 1, m, 1) for m in months]


def season_block(season, days):
    """"VAL" or "TEST": the block of the season's Rewind dates and 1 July rating date (they must agree).

    Every Rewind date must start from looks inside the block (60 days back), so the forecasts are
    all made by the one model that never learned from it.
    """
    blocks = set(time_block(days)) | set(time_block([pd.Timestamp(season, 7, 1)]))
    if len(blocks) != 1 or not blocks <= {"VAL", "TEST"}:
        raise SystemExit(
            f"Season {ad.season_label(season)} falls in {sorted(blocks)}. Pick a validation season "
            "(2009 to 2014, i.e. 2009-10 to 2014-15) or a test season (2016 to 2025).")
    block = blocks.pop()
    first_day = pd.Timestamp(config.VAL_START if block == "VAL" else config.TEST_START)
    for day in days:
        if day - pd.Timedelta(days=ad.RECENT_LOOK_DAYS) < first_day:
            raise SystemExit(f"Rewind date {day.date()} could start from a look before {block}; pick later months.")
    if block == "TEST":
        require(TEST_RESULTS, "scripts/15_score_test.py (the one-time TEST scoring; a test season is shown only "
                              "after it)")
    return block


# ===========================================================================
# 1. Live forecasts (the production fit)
# ===========================================================================
def live_forecasts(rung, looks_all, dams_all, last_day, refit, inputs_holder):
    """Today's forecasts for every dam-like dam (both regions), from the production fit or its saved copy."""
    name = f"{rung}_live"
    path = prediction_path(live_model.PRED_BLOCK, live_model.PRED_TASK, name)
    summary_path = path.with_name(f"{name}_summary.json")
    cutoff = live_model.live_cutoff(last_day)
    if path.exists() and summary_path.exists() and not refit:
        summary = json.loads(summary_path.read_text())
        if summary["cutoff"] == str(cutoff.date()):
            log(f"reusing the saved live forecasts ({path.relative_to(REPO)}; cutoff {summary['cutoff']})")
            return load_predictions(live_model.PRED_BLOCK, live_model.PRED_TASK, name), summary
        log(f"the saved live fit has cutoff {summary['cutoff']}, the data now gives {cutoff.date()}: refitting")

    inputs = inputs_holder()
    last = ad.last_looks(looks_all, dams_all, last_day)
    positions = live_model.latest_positions(inputs["p1"], last.dropna(subset=["date"]))
    log(f"production fit of Tidemark {rung} at cutoff {cutoff.date()} (about 17 minutes at L1, 25 at L3)")
    model = live_model.fit_live(inputs, rung, cutoff, log=log)
    preds = live_model.predict_live(model, inputs, positions)
    summary = clean_for_json(dict(model.info, data_through=str(pd.Timestamp(last_day).date()),
                                  forecasts=len(preds), floor_shift=model.floor["shift"],
                                  made=time.strftime("%Y-%m-%d %H:%M:%S")))
    # clean_for_json rounds to 5 decimals; the band constants are kept exact (they recompute the band).
    summary["band_exact"] = {kind: [float(low), float(high)] for kind, (low, high) in model.band.items()}
    save_predictions(preds, live_model.PRED_BLOCK, live_model.PRED_TASK, name)
    summary_path.write_text(json.dumps(summary, indent=1))
    log(f"live forecasts saved: {len(preds):,} dams, {path.relative_to(REPO)}")
    return preds, summary


def live_issue(dams, looks, events, last_day, preds, summary, rung):
    """The live issue (forecasts.json) and its curves."""
    band = tuple(summary["band_exact"]["R30"])
    table, moved = ad.issue_tables(dams, looks, events, last_day, preds, band)
    note = (f"Tidemark {rung} fitted on every answer known by {ad.day_text(last_day)} (production fit). "
            "Each dam's forecast starts from its latest clear satellite look.")
    issue = ad.issue_json(table, last_day, "live", "Latest forecast", note)
    log(f"live: {np.sum(table['status'] == 'forecast'):,} of {len(table):,} dams have a forecast; "
        f"{moved} curves had a 30/60/180-day point moved to meet the headline")
    return issue, ad.curves_json(table), table, moved


# ===========================================================================
# 2. The model that never saw the season: VAL-setting (scripts/08) or frozen TEST-setting (scripts/13)
# ===========================================================================
def val_model_outputs(rung):
    """The VAL-setting model's saved forecasts (scripts/08), the VAL RAIN scores, and its R30 band constants."""
    step = f"scripts/08_tidemark_val.py (rung {rung})"
    for part in ("p1", "p2_cell", "fit_summary"):
        require(prediction_path("VAL", "tidemark", f"{rung}_{part}"), step)
    p1 = load_predictions("VAL", "tidemark", f"{rung}_p1")
    cells = load_predictions("VAL", "tidemark", f"{rung}_p2_cell")
    summary = pd.read_pickle(prediction_path("VAL", "tidemark", f"{rung}_fit_summary"))
    rain = load_predictions("VAL", "P2_cell", "baselines")
    return p1, cells, rain, tuple(summary["band_constants"]["R30"])


def table_fingerprint(frame):
    """Step 13's fingerprint of a saved forecast table (every stored value, the columns and the row order).

    The same recipe as scripts/13 and scripts/15, so a file can be matched to the one that was scored.
    """
    row_hashes = pd.util.hash_pandas_object(frame, index=False).to_numpy()
    return hashlib.sha256("|".join(map(str, frame.columns)).encode() + row_hashes.tobytes()).hexdigest()[:16]


def scored_forecasts(task, name, fit_summary):
    """A forecast table saved by scripts/13, refused unless it is byte for byte the one scripts/15 scored."""
    path = prediction_path("TEST", task, name)
    relative = path.relative_to(REPO).as_posix()
    record = next((f for f in fit_summary["files"] if f["path"] == relative), None)
    if record is None:
        raise SystemExit(f"{relative} is not among the forecasts step 13 recorded (artifacts/test_setting_fit_summary"
                         ".json); only the frozen, scored TEST forecasts can be shown.")
    frame = pd.read_pickle(require(path, "scripts/13_fit_test_setting.py"))
    if table_fingerprint(frame) != record["fingerprint"] or len(frame) != record["rows"]:
        raise SystemExit(f"{relative}: its fingerprint is not the one step 13 recorded; not the frozen forecasts.")
    return frame


def test_model_outputs(rung):
    """The frozen TEST-setting model's forecasts (scripts/13) and its R30 band, after the one-time scoring.

    Returns the same four things as val_model_outputs, plus the TEST results (scripts/15).
    """
    results = read_json(TEST_RESULTS, "scripts/15_score_test.py")
    frozen = results["frozen"]["rung"]
    if rung != frozen:
        raise SystemExit(f"Test seasons are shown with the frozen model only (rung {frozen}): use --rung {frozen}.")
    fit_summary = read_json(TEST_FIT_SUMMARY, "scripts/13_fit_test_setting.py")
    p1 = scored_forecasts("tidemark", f"{rung}_p1", fit_summary)
    cells = scored_forecasts("tidemark", f"{rung}_p2_cell", fit_summary)
    rain = scored_forecasts("P2_cell", "baselines", fit_summary)
    # The shipped (pooled) season band, PREREG_ADDENDUM_1.md section 4; scripts/15 recorded the same constants
    # (rounded to 5 decimals in its JSON).
    band = tuple(fit_summary["tidemark"]["season_band"]["constants"]["pooled"]["R30"])
    if not np.allclose(band, results["inputs"]["band_constants"]["pooled"]["R30"], rtol=0, atol=1e-5):
        raise SystemExit("The band constants of step 13 and step 15 differ.")
    log(f"frozen TEST-setting forecasts loaded; fingerprints match step 13's record (the forecasts step 15 scored "
        f"on {results['scored_at']})")
    return p1, cells, rain, band, results


REWIND_NOTE = {
    "VAL": ("Forecasts as they would have been made on this day by Tidemark {rung} fitted only on answers known "
            "before 1 Jan 2009 (validation years: the model never learned from them)."),
    "TEST": ("Forecasts as they would have been made on this day by the frozen Tidemark {rung}, fitted only on "
             "answers known before 1 Jul 2016. Test years: the model never learned from them, and they were "
             "scored once, on {scored}."),
}


def rewind_issues(dams, looks, events, days, p1, band, keys, rung, block, scored=None):
    """The past issues (oldest first) and their curves."""
    issues, curves, tallies = [], [], {}
    note = REWIND_NOTE[block].format(rung=rung, scored=scored)
    for day in days:
        table, moved = ad.issue_tables(dams, looks, events, day, p1, band)
        issued = table.loc[table["status"] == "forecast", "date"]
        if set(time_block(issued)) != {block}:
            raise AssertionError(f"Rewind {day.date()}: some forecasts start from a look outside {block}.")
        ad.add_outcomes(table, keys, events)
        label = f"{day.day} {day.strftime('%b %Y')}"
        issues.append(ad.issue_json(table, day, "past", label, note))
        curves.append(dict(issue_date=ad.day_text(day), by_dam=ad.curves_json(table)))
        forecast = table[table["status"] == "forecast"]
        judged = forecast[forecast["outcome"].notna()]
        tallies[ad.day_text(day)] = dict(
            forecasts=len(forecast), judged=len(judged), fell_below_third=int(judged["outcome"].astype(bool).sum()),
            expected=round(float(judged["chance"].sum()), 1), curves_moved=moved)
        log(f"rewind {day.date()}: {len(forecast)} forecasts, {len(judged)} with a known answer, "
            f"{tallies[ad.day_text(day)]['fell_below_third']} fell below a third "
            f"(forecasts added up to {tallies[ad.day_text(day)]['expected']})")
    return issues, curves, tallies


# ===========================================================================
# 3. Rating: one season's cells, and its line on the scoreboard
# ===========================================================================
def scorecard_frame(table):
    """The season's cells as the scorecard reads them (y is blank where the answer is not determinable)."""
    return pd.DataFrame({"uid": table["uid"], "issue_date": table["issue_date"], "region": table["region"],
                         "y": table["y_scored"], "p": table["p"], "p_B0": table["p_B0"], "p_B2": table["p_B2"],
                         "p_RAIN": table["p_RAIN"]})


def saved_result_if_same(path, table, columns):
    """The saved scorecard result at `path` if it was made from exactly these forecasts; else None."""
    if not path.exists():
        return None
    saved = json.loads(path.read_text(encoding="utf-8"))
    same = (saved.get("pred_hash") == prediction_hash(table, ["p"])
            and saved.get("baseline_hash") == prediction_hash(table, columns)
            and saved.get("rows", {}).get("passed_in") == len(table))
    return saved if same else None


def test_season_scores(table, season, n_boot):
    """The test season's line: AUC of the rating and of RAIN on this season's app cells (dev TEST).

    TEST is scored once per model (docs/SCORECARD.md, section 5). These are the SAME frozen forecasts
    scripts/15 scored, on a subset of its rows, so the TEST ledger accepts them only as
    "same_predictions" (every row identical to the first look). That is checked here first,
    read-only, so a mismatch stops the export before anything is written to the ledger. A rerun
    reuses the saved result instead of asking the ledger again.
    Returns the two scorecard results (rating, RAIN), as the scorecard saved them.
    """
    frame = scorecard_frame(table)
    if set(time_block(frame["issue_date"])) != {"TEST"}:
        raise AssertionError("test_season_scores is for test seasons only.")
    baseline_columns = ["p_B0", "p_B2"]
    prepared = prepare_table(frame, required=["p"], label_columns=["y"],
                             probability_columns=["p", *baseline_columns, "p_RAIN"])
    rain_frame = frame.assign(p=frame["p_RAIN"])
    rain_prepared = prepare_table(rain_frame, required=["p"], label_columns=["y"],
                                  probability_columns=["p", *baseline_columns])
    folder = SCORE_DIR / "dev_TEST" / "P2_cell"
    saved = (saved_result_if_same(folder / "tidemark__all.json", prepared, baseline_columns),
             saved_result_if_same(folder / "rain__all.json", rain_prepared, baseline_columns))
    if all(saved):
        log(f"rating {ad.season_label(season)}: reusing the saved one-season scores ({folder.relative_to(REPO)}; "
            "same forecasts, so no new ledger row)")
        return saved

    ledger = Ledger()
    for model, column in (("tidemark", "p"), ("rain", "p_RAIN")):
        first = ledger.first_look(model, "P2_cell", "dev")
        if first is None:
            raise SystemExit(f"{model} has no dev TEST score for P2_cell on the ledger: run scripts/15 first.")
        same, how = ledger.matches_first_look(first, prepared[KEY + [column]].rename(columns={column: "p"}))
        if not same:
            raise SystemExit(f"The {model} season ratings are not the ones scored by scripts/15 ({how}); "
                             "nothing was scored.")
    note = (f"step 11 (app export): season {ad.season_label(season)}, the app's cells only; the frozen forecasts "
            "scripts/15 scored (same_predictions)")
    rating = score(frame, "P2_cell", "all", model="tidemark", refs=["RAIN"], n_boot=n_boot, note=note,
                   out_dir=SCORE_DIR)
    rain = score(rain_frame, "P2_cell", "all", model="rain", n_boot=n_boot, note=note, out_dir=SCORE_DIR)
    log(f"rating {ad.season_label(season)}: scored by the scorecard; TEST ledger: tidemark {rating['test_ledger']}, "
        f"rain {rain['test_ledger']}")
    # Read the numbers back from the saved result files, so the app shows exactly what the scorecard wrote.
    return tuple(json.loads(Path(result["json_path"]).read_text(encoding="utf-8")) for result in (rating, rain))


def rating_season(dams, cell_preds, rain, season, rung, n_boot, block):
    """cells.json for one season, and the scorecard's line for that season (the app's region only)."""
    cells = ad.app_cells(dams)
    labels = store.load_p2("cell")
    table = ad.season_table(cells, cell_preds, rain, labels, season)
    if block == "VAL":
        rating, rain_result = ad.season_scores(table, season, rung, SCORE_DIR, n_boot)
    else:
        rating, rain_result = test_season_scores(table, season, n_boot)
    line = ad.score_line(rating, rain_result)
    log(f"rating {ad.season_label(season)}: {line['n_ran_dry']} of {line['n_cells']} cells ran dry; AUC rating "
        f"{line['rating_auc']['value']:.3f}, rainfall-only {line['rain_only_auc']['value']:.3f}")
    doc = dict(cell_size_km=config.HEX_SIZE_KM, season_months="Oct-Mar", cells=ad.cells_list_json(cells),
               seasons=[ad.season_json(table, season)])
    return doc, line, cells


# ===========================================================================
# 4. Scoreboard for a test season: dev TEST (scored once) and the sealed-region panel
# ===========================================================================
def range_of(result, metric):
    """A contract Range {value, ci_low, ci_high} (95% dam-bootstrap range) from a scorecard result; None if absent."""
    if metric not in result.get("point", {}) or metric not in result.get("ci_dam", {}):
        return None
    low, high = result["ci_dam"][metric]
    return dict(value=result["point"][metric], ci_low=low, ci_high=high)


def headline_panel(key, title, label, p1, p2, rain):
    """One scoreboard panel from three scorecard results (copied, never retyped).

    p1    R30 on the primary set (dam-like, Oct-Mar, at risk), Tidemark, with G2 as the paired reference
    p2    the 2 km cell rating (P2_cell), Tidemark, with RAIN as a reference
    rain  RAIN scored on its own on the same cells
    The P1 pass bars are the scorecard's own check (prereg_pass_bars). The P2 bar and kill rule are
    the PREREG rules (P2_BAR, KILL_RULE_GAP) applied to the copied AUC gain.
    """
    gain = range_of(p2, "d_auc_vs_RAIN")
    return dict(
        key=key, status="scored", title=title, label=label, scored_at=p1["time"],
        runway=dict(
            label="Below a third within 90 days: farm-like dams, forecasts made October to March",
            n_forecasts=p1["rows"]["scored"], n_fell_below_third=p1["rows"]["events"], n_dams=p1["rows"]["dams"],
            skill_vs_usual_rate=range_of(p1, "bss_B0"), skill_vs_own_record=range_of(p1, "bss_B2"),
            gain_vs_benchmark=range_of(p1, "d_bss_B0_vs_G2"), auc=range_of(p1, "auc"),
            calibration_slope=range_of(p1, "cal_slope"),
            pass_bars_met=p1.get("prereg_pass_bars", {}).get("all_passed")),
        rating=dict(
            label="Every dam in a 2 km cell runs dry, October to March; rated each 1 July",
            n_cells=p2["rows"]["scored"], n_ran_dry=p2["rows"]["events"],
            rating_auc=range_of(p2, "auc"), rain_only_auc=range_of(rain, "auc"), gain_vs_rain=gain,
            pass_bar_met=None if gain is None else bool(gain["value"] >= P2_BAR and gain["ci_low"] > 0),
            kill_rule_triggered=None if gain is None else bool(gain["value"] < KILL_RULE_GAP)))


def dev_test_panel(results):
    """The development-regions panel, from artifacts/test_results.json (scripts/15's one look)."""
    scores = results["scores"]
    p1 = scores["P1_R30 | dam_like+octmar+at_risk | tidemark"]
    p2, rain = scores["P2_cell | all | tidemark"], scores["P2_cell | all | RAIN"]
    panel = headline_panel("dev_test", "Development regions, 2016-2026, scored once",
                           "NSW Central West and western Victoria / SE South Australia; forecasts issued July 2016 "
                           f"to June 2026; scored once on {human_day(results['scored_at'])}", p1, p2, rain)
    # The P2 verdicts above mirror the PREREG rule; they must agree with scripts/15's own verdicts.
    verdict = results["verdicts"]["p2_cell"]
    if (panel["rating"]["pass_bar_met"], panel["rating"]["kill_rule_triggered"]) != (
            verdict["passed"], verdict["kill_rule_triggered"]):
        raise AssertionError("The P2 pass-bar check disagrees with scripts/15's verdict.")
    floor, band = results["floor"]["issued_all"], results["band"]["R30"]["pooled"]
    panel["floor"] = dict(label="DamDays floor ('at least N days, 9 times in 10'): share that held",
                          held=floor["coverage"], ci_low=floor["ci_dam"]["coverage"][0],
                          ci_high=floor["ci_dam"]["coverage"][1], target=floor["target"],
                          n_forecasts=floor["rows_judged"], worst_year=floor["worst_year"])
    panel["band"] = dict(label="Season band (R30): July-June region-years inside the likely range",
                         covered=band["covered"], region_years=band["region_years"])
    panel["sources"] = ["artifacts/test_results.json", "artifacts/test_results.md",
                        "artifacts/scorecard/step15_test/dev_TEST/"]
    return panel


def sealed_placeholder():
    """The sealed-region panel before the opening: what it is, when it opens, what we expect."""
    return dict(
        key="sealed", status="pending", title=SEALED_TITLE, label=SEALED_NAME,
        text=("A third region, 4,711 waterbodies, was downloaded before the event and locked away (its file "
              "fingerprints are in SEALED_HASHES.csv). It is opened once, on camera, on Sat 3 Oct 2026 at "
              "17:30 AEST, forecast with the frozen model and scored once. Its results will appear here."),
        expectations=SEALED_EXPECTATIONS, fill_with=SEALED_FILL_COMMAND)


def sealed_panel(folder, arena="sealed"):
    """The sealed-region panel from the opening's scorecard files (scripts/20 --open writes one JSON per score).

    Reads only these three result files; every one must say block TEST and arena "sealed", so a
    development result can never be shown as the sealed one.
    """
    folder = Path(folder)
    found = {}
    for part, (task, name) in PANEL_FILES.items():
        result = read_json(folder / task / name, "scripts/20_open_sealed_region.py --open (Sat 3 Oct 17:30)")
        if result.get("block") != "TEST" or result.get("arena") != arena:
            raise SystemExit(f"{folder / task / name} is block {result.get('block')}, arena {result.get('arena')}; "
                             f"the sealed panel needs block TEST, arena {arena!r}.")
        found[part] = result
    panel = headline_panel("sealed", "Sealed region, opened Sat 3 Oct 17:30, scored once",
                           f"{SEALED_NAME}; forecasts issued July 2016 to June 2026; scored once on "
                           f"{human_day(found['p1']['time'])}", found["p1"], found["p2"], found["rain"])
    panel["expectations"] = SEALED_EXPECTATIONS
    shown = folder.resolve().relative_to(REPO) if folder.resolve().is_relative_to(REPO) else folder
    panel["sources"] = [f"{shown.as_posix()}/{task}/{name}" for task, name in PANEL_FILES.values()]
    return panel


def test_scoreboard_json(results, season, season_line, sealed):
    """scoreboard.json for a test season: dev TEST numbers copied from test_results.json, plus the sealed panel."""
    dev = dev_test_panel(results)
    scores = results["scores"]
    p1 = scores["P1_R30 | dam_like+octmar+at_risk | tidemark"]
    p2, rain = scores["P2_cell | all | tidemark"], scores["P2_cell | all | RAIN"]
    first, last = seasons_in("TEST")[0], seasons_in("TEST")[-1]
    return dict(
        source="dev_test", is_validation=False, block="TEST",
        source_label="Development regions, 2016-2026, scored once",
        note=(f"The frozen model (Tidemark {results['frozen']['rung']}, config {results['frozen']['config_hash']}) "
              "learned only from answers known before 1 Jul 2016. It was scored once, on "
              f"{human_day(results['scored_at'])}, on every forecast issued from July 2016 to June 2026 in the two "
              "development regions. These years were also looked at before the event, so these scores are "
              "slightly optimistic (PREREG.md); the sealed region, opened once on Sat 3 Oct, is the clean test."),
        rating=dict(
            all_seasons=dict(label=f"All test seasons {ad.season_label(first)} to {ad.season_label(last)} "
                                   "(both development regions)",
                             n_cells=p2["rows"]["scored"], n_ran_dry=p2["rows"]["events"],
                             rain_only_auc=range_of(rain, "auc"), rating_auc=range_of(p2, "auc")),
            by_season=[dict(season=ad.season_label(season), **season_line)]),
        runway=dict(label=("Test years 2016-2026: below a third within 90 days, farm-like dams, October-March "
                           "forecasts, both development regions"),
                    skill_vs_usual_rate=range_of(p1, "bss_B0"), n_forecasts=p1["rows"]["scored"]),
        panels=[dev, sealed],
        sources=dict(test_results="artifacts/test_results.json (scripts/15)",
                     by_season="artifacts/scorecard/step11_app/dev_TEST/P2_cell/ (the scorecard, same frozen "
                               "forecasts; TEST ledger 'same_predictions')"))


def test_limits_text(results):
    """Plain-language limits for a test-season export, with the numbers read from the TEST results."""
    p2 = results["scores"]["P2_cell | all | tidemark"]["point"]
    p1 = results["scores"]["P1_R30 | dam_like+octmar+at_risk | tidemark"]["point"]
    worst = results["floor"]["issued_all"]["worst_year"]
    return [
        "Only dams of at least about 0.54 ha (6 Landsat pixels) are visible; smaller dams, tanks and bores are not.",
        "Water area, not depth: 'below a third' means below a third of the dam's usual full wet area.",
        "Test numbers: the scores were measured once on July 2016 to June 2026, years the model never learned "
        "from. The pre-event research had looked at these years, so they are slightly optimistic; the sealed "
        "region is the clean test.",
        f"It ranks farms better than it times droughts: the rating tells which cells run dry in a season "
        f"(ranking accuracy {p2['auc_within_season']:.2f} within a season), but not well which seasons a given "
        f"cell runs dry ({p2['auc_within_cell']:.2f} within a cell's own history).",
        f"On average the runway chances were a little high (average forecast {p1['mean_p']:.2f}, actual rate "
        f"{p1['base_rate']:.2f}). The DamDays floor held for {results['floor']['issued_all']['coverage']:.1%} of "
        f"forecasts (target 90%), but only {worst['coverage']:.1%} in its worst July-June year ({worst['year']}).",
        "Live forecasts start from each dam's latest clear satellite look; some looks are weeks old.",
        f"This is the frozen rung {results['frozen']['rung']} (PREREG_ADDENDUM_1.md, config "
        f"{results['frozen']['config_hash']}).",
    ]


# ===========================================================================
# Main
# ===========================================================================
def config_hash_of_running_code():
    """The event build config hash of the code being run (scripts/14_config_hash.py's recipe; reads no data)."""
    spec = importlib.util.spec_from_file_location("step14_config_hash", REPO / "scripts" / "14_config_hash.py")
    step14 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(step14)
    return step14.config_hash()[0][:12]


def size_report(folder):
    """Sizes of the six JSON files (KB), their total (MB), and bundle.js (their copy) on disk and gzipped (MB)."""
    sizes = {p.name: round(p.stat().st_size / 1024) for p in sorted(folder.glob("*.json"))}
    bundle = folder / "bundle.js"
    bundle_mb = gzip_mb = None
    if bundle.exists():
        bundle_mb = round(bundle.stat().st_size / 2 ** 20, 2)
        gzip_mb = round(len(gzip.compress(bundle.read_bytes())) / 2 ** 20, 2)   # what a web server sends
    return sizes, round(sum(sizes.values()) / 1024, 2), bundle_mb, gzip_mb


def build_bundle():
    """Pack the JSON files into bundle.js (app/tools/build_bundle.py) and report the sizes."""
    subprocess.run([sys.executable, str(BUNDLE_TOOL), str(OUT_DIR)], check=True, cwd=REPO)
    sizes, total, bundle_mb, gzip_mb = size_report(OUT_DIR)
    log(f"JSON files (KB): {sizes}; total {total} MB. bundle.js (a copy of them): {bundle_mb} MB, "
        f"{gzip_mb} MB gzipped as a web server sends it")
    if total > SIZE_TARGET_MB:
        log(f"WARNING: the JSON files total {total} MB, above the ~{SIZE_TARGET_MB} MB target "
            "(a later --history-from makes history.json smaller)")


def update_sealed_panel_only(folder):
    """--panel-only: put the sealed panel into the published scoreboard.json and rebuild bundle.js (seconds)."""
    path = require(OUT_DIR / "scoreboard.json", "scripts/11_export_app.py (a full export with a test season)")
    board = json.loads(path.read_text(encoding="utf-8"))
    if board.get("source") != "dev_test" or "panels" not in board:
        raise SystemExit("The published scoreboard is not a test-season export; run the full export first.")
    panel = sealed_panel(folder)
    board["panels"] = [panel if p["key"] == "sealed" else p for p in board["panels"]]
    path.write_text(json.dumps(board, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    log(f"sealed panel filled from {folder}: R30 skill vs the usual rate "
        f"{panel['runway']['skill_vs_usual_rate']['value']:+.3f}; rating AUC {panel['rating']['rating_auc']['value']:.3f} "
        f"against rainfall-only {panel['rating']['rain_only_auc']['value']:.3f}")
    build_bundle()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rung", default="L1", choices=sorted(tidemark.RUNGS),
                        help="Tidemark rung (default L1; the frozen model is L3)")
    parser.add_argument("--region", default="nsw_cw", choices=[*config.DEV_REGIONS, "all"],
                        help="which development region the app shows (default nsw_cw; 'all' is about twice as large)")
    parser.add_argument("--season", default="auto",
                        help="Rewind and Rating season as its July-June start year: a validation season 2009-2014 "
                             "or, after the one-time TEST scoring, a test season 2016-2025 (e.g. 2018 for the "
                             "2018-19 drought). Default: the validation season with the most falls below a third")
    parser.add_argument("--rewind-months", default="11,1,3",
                        help="Rewind dates: the 1st of these months (default 11,1,3: from Oct, Dec, Feb looks)")
    parser.add_argument("--refit-live", action="store_true", help="refit the production model even if saved")
    parser.add_argument("--history-from", default=ad.FIRST_MONTH,
                        help="first month of the water history (default 1988-01; later = smaller files)")
    parser.add_argument("--n-boot", type=int, default=500, help="bootstrap draws for the one-season scores")
    parser.add_argument("--sealed-scores", default=None,
                        help="after the opening only: the folder of the sealed scorecard files "
                             "(artifacts/sealed/scorecard/sealed_TEST); fills the 'Sealed region' panel")
    parser.add_argument("--panel-only", action="store_true",
                        help="with --sealed-scores: update only the published scoreboard's sealed panel, then "
                             "rebuild bundle.js (nothing else is re-exported)")
    parser.add_argument("--no-bundle", action="store_true", help="do not run app/tools/build_bundle.py")
    args = parser.parse_args()
    if args.panel_only:
        if not args.sealed_scores:
            parser.error("--panel-only needs --sealed-scores.")
        update_sealed_panel_only(args.sealed_scores)
        return

    log("loading dams, satellite looks and events")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    events = pd.read_pickle(config.CACHE_DIR / "events.pkl")
    last_day = live_model.last_look_date()
    regions = ad.app_regions(args.region)
    dams = ad.app_dams(attrs, regions)
    looks = ad.dam_looks(panel, dams)
    log(f"{len(dams):,} dam-like dams in {', '.join(regions)}; last satellite look {last_day.date()}")

    # Which season, and which model may show it. Checked first, so a bad choice fails before the live fit.
    if args.season == "auto":
        r30_counts = r30_starts_per_season(events, dams, "VAL")
        season = driest_val_season(r30_counts)
    else:
        season, r30_counts = int(args.season), None
    days = rewind_days(season, [int(m) for m in args.rewind_months.split(",")])
    block = season_block(season, days)
    if r30_counts is None:
        r30_counts = r30_starts_per_season(events, dams, block)
    if block == "VAL":
        p1_past, cell_preds, rain, band = val_model_outputs(args.rung)
        test_results = None
    else:
        p1_past, cell_preds, rain, band, test_results = test_model_outputs(args.rung)

    # The P1 table is large: load it only when needed (live refit, Rewind labels).
    holder = {}

    def inputs():
        if "inputs" not in holder:
            log("loading the Tidemark inputs (P1 table, P2 tables)")
            holder["inputs"] = tidemark.load_inputs()
        return holder["inputs"]

    # 1. Live: the production fit covers every dam-like dam of both regions, so one fit serves any --region.
    dams_all = ad.app_dams(attrs, list(config.DEV_REGIONS))
    live_preds, live_summary = live_forecasts(args.rung, ad.dam_looks(panel, dams_all), dams_all, last_day,
                                              args.refit_live, inputs)
    live, live_curves, live_table, live_moved = live_issue(dams, looks, events, last_day, live_preds, live_summary,
                                                           args.rung)

    # 2. Rewind: forecasts of the model that never learned from the season.
    keys = holder["inputs"]["p1"] if "inputs" in holder else store.load_p1(groups=("keys",))
    scored = None if test_results is None else human_day(test_results["scored_at"])
    past, past_curves, tallies = rewind_issues(dams, looks, events, days, p1_past, band, keys, args.rung, block,
                                               scored)

    # 3. Rating (same season) and 4. scoreboard.
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    if block == "VAL":
        (SCORE_DIR / "scorecard_dev_VAL.md").write_text("")       # this run's markdown table starts empty
    cells_doc, season_line, cells = rating_season(dams, cell_preds, rain, season, args.rung, args.n_boot, block)
    if block == "VAL":
        results_path = require(config.ARTIFACTS_DIR / f"val_tidemark_{args.rung}.json",
                               f"scripts/08_tidemark_val.py (rung {args.rung})")
        results = json.loads(Path(results_path).read_text())
        rain_all = read_json(RAIN_ALL, "scripts/03_baselines_and_g2.py")
        board = ad.scoreboard_json(results, rain_all, args.rung, season, season_line, "both development regions")
    else:
        sealed = sealed_panel(args.sealed_scores) if args.sealed_scores else sealed_placeholder()
        board = test_scoreboard_json(test_results, season, season_line, sealed)
        # meta_json writes its limits from validation results; a test export states the test numbers instead.
        scores = test_results["scores"]
        results = dict(p1={f"P1_R30|primary|{args.rung}": scores["P1_R30 | dam_like+octmar+at_risk | tidemark"]},
                       p2={f"P2_cell|all|{args.rung}": scores["P2_cell | all | tidemark"]})

    # 5. Meta, then write and check everything.
    n_forecast = int(np.sum(live_table["status"] == "forecast"))
    status_counts = live_table["status"].value_counts().to_dict()
    # Dam-like dams are 6 to 55 Landsat pixels (PREREG), so read their size range from the data.
    smallest_ha, largest_ha = dams["area_m2"].min() / 10_000, dams["area_m2"].max() / 10_000
    coverage = dict(
        dams=len(dams), dams_with_live_forecast=n_forecast, live_status_counts=status_counts, cells=len(cells),
        text=(f"{len(dams):,} farm-like dams (DEA Waterbodies outlines of {smallest_ha:.2f} to {largest_ha:.2f} ha "
              f"that look and behave like farm dams) in {ad.region_json(regions)['name']}. "
              f"{n_forecast:,} of them have a forecast today; "
              "the others are already below a third, have not refilled lately, or have no clear look in the "
              f"last {ad.RECENT_LOOK_DAYS} days. Smaller dams, tanks and bores are not visible."))
    live_info = dict(cutoff=live_summary["cutoff"], about="production fit: every answer known by the last look",
                     band_R30=live_summary["band"]["R30"], floor_shift=live_summary["floor_shift"],
                     curves_moved_to_headline=live_moved)
    model_cutoff = config.VAL_START if block == "VAL" else config.TEST_START
    rewind_info = dict(season=ad.season_label(season), block=block, model_cutoff=model_cutoff,
                       chosen="most R30 starts among the app's dams" if args.season == "auto" else "given with --season",
                       r30_starts_per_season=r30_counts, dates=[ad.day_text(d) for d in days], tallies=tallies,
                       band_R30=list(band))
    if block == "VAL":
        note = (f"Real DamDays forecasts. Runway: Tidemark {args.rung} refitted on all answers known by "
                f"{ad.day_text(last_day)}. Rewind and Rating: the validation season {ad.season_label(season)}, "
                "from the model fitted only on answers known before 2009. Scores are validation-period numbers.")
    else:
        rewind_info["forecast_files"] = "data_cache/preds/TEST/ (scripts/13; fingerprints match the scored ones)"
        note = (f"Real DamDays forecasts. Runway: Tidemark {args.rung} refitted on all answers known by "
                f"{ad.day_text(last_day)}. Rewind and Rating: the test season {ad.season_label(season)}, from the "
                "frozen model fitted only on answers known before 1 Jul 2016. Scores: development regions, "
                "2016-2026, scored once; the sealed region is opened Sat 3 Oct 17:30.")
    meta = ad.meta_json(regions, last_day, args.rung, live_info, rewind_info, coverage, results, note)
    meta["model"]["config_hash"] = config_hash_of_running_code()
    if test_results is not None:
        meta["limits"] = test_limits_text(test_results)
        if meta["model"]["config_hash"] != test_results["frozen"]["config_hash"]:
            log(f"WARNING: the running code's config hash {meta['model']['config_hash']} is not the frozen "
                f"{test_results['frozen']['config_hash']}")
    docs = dict(
        meta=meta,
        forecasts=dict(horizon_days=config.HORIZON_DAYS, dams=ad.dams_json(dams), issues=[live, *past]),
        curves=dict(horizons_days=list(ad.HORIZONS),
                    issues=[dict(issue_date=live["issue_date"], by_dam=live_curves), *past_curves]),
        history=ad.history_json(looks, events, dams, last_day, args.history_from),
        cells=cells_doc,
        scoreboard=board)
    problems = ad.contract_problems(docs)
    if problems:
        raise SystemExit("Contract check failed:\n  " + "\n  ".join(problems[:20]))
    log("contract check passed (every rule in damdays.export.app_data.contract_problems)")
    ad.write_documents(docs, OUT_DIR)
    if not args.no_bundle:
        build_bundle()


if __name__ == "__main__":
    main()
