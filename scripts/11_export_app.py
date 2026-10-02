"""Step 11: export real forecasts for the app (app/data/real/), then pack them with app/tools/build_bundle.py.

Run from the repo folder (after scripts/01 to 08):
    .venv/Scripts/python.exe scripts/11_export_app.py                  # rung L1, NSW Central West
    .venv/Scripts/python.exe scripts/11_export_app.py --refit-live     # refit the production model first
    .venv/Scripts/python.exe scripts/11_export_app.py --rung L2        # once rung L2 has its VAL results
    .venv/Scripts/python.exe scripts/11_export_app.py --season 2009    # another validation season

What it does
  1. Live (Runway view). Tidemark fitted at the production cutoff: the day after the last
     satellite look (damdays/export/live_model.py). Each dam-like dam gets a forecast from its
     latest look (September 2026). The fit takes about 17 minutes (rung L1); its forecasts are saved in
     data_cache/preds/LIVE/tidemark/ and reused until --refit-live (or new data).
  2. Rewind. Forecasts on 1 Nov, 1 Jan and 1 Mar of one validation season, from the VAL-setting
     model (fitted only on answers final before 1 Jan 2009; scripts/08 saved its forecasts), and
     what happened next. These dates start from October, December and February looks, the
     October-March months of the pre-registered headline set. By default the season is the
     validation season with the most falls below a third among the app's dams (the most telling
     one to rewind, not a typical one).
  3. Rating. The same season's 2 km cell ratings from the VAL-setting model, the rainfall-only
     score (RAIN, scripts/03) and which cells ran dry.
  4. Scoreboard. Validation-period scores copied from artifacts/val_tidemark_<rung>.json and step
     3's RAIN scorecard; the one-season line is computed by the scorecard (artifacts/scorecard/step11_app/).
  5. Writes the six JSON files, checks every contract rule, and runs app/tools/build_bundle.py.

Nothing is scored on the test years. The production fit learns from every answer up to 2026, as
a model for today must, but its forecasts are only shown, never scored. Rewind and Rating refuse a
TEST season (2016 on) until the official one-time TEST scoring has produced the TEST-setting
forecasts and scores (see app/data/real/README.md).
"""
import argparse
import gzip
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
SIZE_TARGET_MB = 5.0                     # the six JSON files should stay about this small (bundle.js copies them)

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


def require(path, step):
    """Stop with a clear message if an earlier step's output is missing."""
    if not Path(path).exists():
        raise SystemExit(f"Missing {path}: run {step} first.")
    return path


# ===========================================================================
# Which season to rewind
# ===========================================================================
def val_seasons():
    """Validation seasons whose whole October-March is in VAL: 2009-10 to 2014-15 (season = July-June year)."""
    first, last = pd.Timestamp(config.VAL_START).year, pd.Timestamp(config.VAL_END).year - 2
    return list(range(first, last + 1))


def driest_season(events, dams):
    """The validation season with the most R30 starts (falls below a third) among the app's dams."""
    r30 = events[(events["kind"] == "R30") & events["uid"].astype(str).isin(set(dams["uid"]))]
    counts = pd.Series(hydro_year(r30["start_date"])).value_counts().reindex(val_seasons(), fill_value=0)
    log("R30 starts per validation season among the app's dams: "
        + ", ".join(f"{ad.season_label(s)} {n}" for s, n in counts.items()))
    return int(counts.idxmax()), {ad.season_label(s): int(n) for s, n in counts.items()}


def rewind_days(season, months):
    """The Rewind issue dates: the 1st of each month in `months` (July-June order) of the season."""
    return [pd.Timestamp(season if m >= 7 else season + 1, m, 1) for m in months]


def check_season_block(season, days):
    """Rewind and Rating must show a validation season (this is where the VAL-setting model applies)."""
    blocks = set(time_block(days)) | set(time_block([pd.Timestamp(season, 7, 1)]))
    if blocks != {"VAL"}:
        raise SystemExit(
            f"Season {ad.season_label(season)} falls in {sorted(blocks)}, not VAL. Only validation seasons "
            "(2009-10 to 2014-15) can be shown now. A TEST season (e.g. 2018-19) needs the official one-time "
            "TEST scoring first: its TEST-setting forecasts (data_cache/preds/TEST/tidemark/) and TEST scores; "
            "see app/data/real/README.md.")
    for day in days:
        if day - pd.Timedelta(days=ad.RECENT_LOOK_DAYS) < pd.Timestamp(config.VAL_START):
            raise SystemExit(f"Rewind date {day.date()} could start from a look before VAL; pick later months.")


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
    log(f"production fit of Tidemark {rung} at cutoff {cutoff.date()} (about 17 minutes at rung L1)")
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
# 2. Rewind (VAL-setting forecasts)
# ===========================================================================
def val_model_outputs(rung):
    """The VAL-setting model's saved forecasts (scripts/08) and its R30 band constants."""
    step = f"scripts/08_tidemark_val.py (rung {rung})"
    for part in ("p1", "p2_cell", "fit_summary"):
        require(prediction_path("VAL", "tidemark", f"{rung}_{part}"), step)
    p1 = load_predictions("VAL", "tidemark", f"{rung}_p1")
    cells = load_predictions("VAL", "tidemark", f"{rung}_p2_cell")
    summary = pd.read_pickle(prediction_path("VAL", "tidemark", f"{rung}_fit_summary"))
    return p1, cells, tuple(summary["band_constants"]["R30"])


def rewind_issues(dams, looks, events, days, val_p1, band, keys, rung):
    """The past issues (oldest first) and their curves."""
    issues, curves, tallies = [], [], {}
    note = (f"Forecasts as they would have been made on this day by Tidemark {rung} fitted only on answers known "
            "before 1 Jan 2009 (validation years: the model never learned from them).")
    for day in days:
        table, moved = ad.issue_tables(dams, looks, events, day, val_p1, band)
        issued = table.loc[table["status"] == "forecast", "date"]
        if set(time_block(issued)) != {"VAL"}:
            raise AssertionError(f"Rewind {day.date()}: some forecasts start from a look outside VAL.")
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
# 3-4. Rating and scoreboard
# ===========================================================================
def rating_season(dams, val_cells, season, rung, n_boot):
    """cells.json for one validation season, and the scorecard's line for that season."""
    cells = ad.app_cells(dams)
    rain = load_predictions("VAL", "P2_cell", "baselines")
    labels = store.load_p2("cell")
    table = ad.season_table(cells, val_cells, rain, labels, season)
    rating, rain_result = ad.season_scores(table, season, rung, SCORE_DIR, n_boot)
    line = ad.score_line(rating, rain_result)
    log(f"rating {ad.season_label(season)}: {line['n_ran_dry']} of {line['n_cells']} cells ran dry; AUC rating "
        f"{line['rating_auc']['value']:.3f}, rainfall-only {line['rain_only_auc']['value']:.3f}")
    doc = dict(cell_size_km=config.HEX_SIZE_KM, season_months="Oct-Mar", cells=ad.cells_list_json(cells),
               seasons=[ad.season_json(table, season)])
    return doc, line, cells


# ===========================================================================
# Main
# ===========================================================================
def size_report(folder):
    """Sizes of the six JSON files (KB), their total (MB), and bundle.js (their copy) on disk and gzipped (MB)."""
    sizes = {p.name: round(p.stat().st_size / 1024) for p in sorted(folder.glob("*.json"))}
    bundle = folder / "bundle.js"
    bundle_mb = gzip_mb = None
    if bundle.exists():
        bundle_mb = round(bundle.stat().st_size / 2 ** 20, 2)
        gzip_mb = round(len(gzip.compress(bundle.read_bytes())) / 2 ** 20, 2)   # what a web server sends
    return sizes, round(sum(sizes.values()) / 1024, 2), bundle_mb, gzip_mb


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rung", default="L1", choices=sorted(tidemark.RUNGS), help="Tidemark rung (default L1)")
    parser.add_argument("--region", default="nsw_cw", choices=[*config.DEV_REGIONS, "all"],
                        help="which development region the app shows (default nsw_cw; 'all' is about twice as large)")
    parser.add_argument("--season", default="auto",
                        help="Rewind and Rating season as its July-June start year, e.g. 2009 for 2009-10 "
                             "(default: the validation season with the most falls below a third)")
    parser.add_argument("--rewind-months", default="11,1,3",
                        help="Rewind dates: the 1st of these months (default 11,1,3: from Oct, Dec, Feb looks)")
    parser.add_argument("--refit-live", action="store_true", help="refit the production model even if saved")
    parser.add_argument("--history-from", default=ad.FIRST_MONTH,
                        help="first month of the water history (default 1988-01; later = smaller files)")
    parser.add_argument("--n-boot", type=int, default=500, help="bootstrap draws for the one-season scores")
    parser.add_argument("--no-bundle", action="store_true", help="do not run app/tools/build_bundle.py")
    args = parser.parse_args()

    log("loading dams, satellite looks and events")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    events = pd.read_pickle(config.CACHE_DIR / "events.pkl")
    last_day = live_model.last_look_date()
    regions = ad.app_regions(args.region)
    dams = ad.app_dams(attrs, regions)
    looks = ad.dam_looks(panel, dams)
    log(f"{len(dams):,} dam-like dams in {', '.join(regions)}; last satellite look {last_day.date()}")

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

    # 2. Rewind: a validation season, VAL-setting forecasts only.
    if args.season == "auto":
        season, r30_counts = driest_season(events, dams)
    else:
        season, r30_counts = int(args.season), None
    days = rewind_days(season, [int(m) for m in args.rewind_months.split(",")])
    check_season_block(season, days)
    val_p1, val_cells, val_band = val_model_outputs(args.rung)
    keys = holder["inputs"]["p1"] if "inputs" in holder else store.load_p1(groups=("keys",))
    past, past_curves, tallies = rewind_issues(dams, looks, events, days, val_p1, val_band, keys, args.rung)

    # 3. Rating (same season) and 4. scoreboard.
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    (SCORE_DIR / "scorecard_dev_VAL.md").write_text("")           # this run's markdown table starts empty
    cells_doc, season_line, cells = rating_season(dams, val_cells, season, args.rung, args.n_boot)
    results_path = require(config.ARTIFACTS_DIR / f"val_tidemark_{args.rung}.json",
                           f"scripts/08_tidemark_val.py (rung {args.rung})")
    results = json.loads(Path(results_path).read_text())
    rain_all = json.loads(Path(require(RAIN_ALL, "scripts/03_baselines_and_g2.py")).read_text())
    board = ad.scoreboard_json(results, rain_all, args.rung, season, season_line,
                               "both development regions")

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
    rewind_info = dict(season=ad.season_label(season), block="VAL", model_cutoff=config.VAL_START,
                       chosen="most R30 starts among the app's dams" if r30_counts else "given with --season",
                       r30_starts_per_season=r30_counts, dates=[ad.day_text(d) for d in days], tallies=tallies,
                       band_R30=list(val_band))
    note = (f"Real DamDays forecasts. Runway: Tidemark {args.rung} refitted on all answers known by "
            f"{ad.day_text(last_day)}. Rewind and Rating: the validation season {ad.season_label(season)}, "
            "from the model fitted only on answers known before 2009. Scores are validation-period numbers.")
    docs = dict(
        meta=ad.meta_json(regions, last_day, args.rung, live_info, rewind_info, coverage, results, note),
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
        subprocess.run([sys.executable, str(BUNDLE_TOOL), str(OUT_DIR)], check=True, cwd=REPO)
    sizes, total, bundle_mb, gzip_mb = size_report(OUT_DIR)
    log(f"JSON files (KB): {sizes}; total {total} MB. bundle.js (a copy of them): {bundle_mb} MB, "
        f"{gzip_mb} MB gzipped as a web server sends it")
    if total > SIZE_TARGET_MB:
        log(f"WARNING: the JSON files total {total} MB, above the ~{SIZE_TARGET_MB} MB target "
            "(a later --history-from makes history.json smaller)")


if __name__ == "__main__":
    main()
