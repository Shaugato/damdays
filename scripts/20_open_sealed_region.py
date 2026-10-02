"""Step 20: the sealed-region runner. It opens the sealed region ONCE, Sat 3 Oct 2026 17:30 AEST.

Plain-language runbook with the exact commands: docs/SEALED_OPENING.md. Run from the repo folder:

    # before the opening (no sealed file is touched)
    .venv/Scripts/python.exe scripts/20_open_sealed_region.py --prepare            # after scripts/13: fingerprint
                                                                                  # the TEST-setting models
    .venv/Scripts/python.exe scripts/20_open_sealed_region.py --prepare --dry-run  # fit the rehearsal's models
    .venv/Scripts/python.exe scripts/20_open_sealed_region.py --dry-run            # the full rehearsal

    # THE OPENING (17:30): the unlock switch, then one command
    set DAMDAYS_OPEN_SEALED=yes          (PowerShell: $env:DAMDAYS_OPEN_SEALED = "yes")
    .venv/Scripts/python.exe scripts/20_open_sealed_region.py --open

What --open does, in order (PREREG "Sealed region protocol"; FINAL_SPEC section E, opening runbook)
  1. Checks (damdays.sealed.checks); it refuses to go on unless ALL hold: the unlock switch is on;
     git is clean and HEAD is pushed; SEALED_HASHES.csv is the copy committed at the start of the
     event, never changed; every sealed file's SHA-256 matches it (100%, exactly 4,711 files).
  2. Loads the frozen TEST-setting models, fitted on the development regions' issues before
     2016-07-01 (damdays.sealed.fitted_models). Their SHA-256 must equal the committed manifest.
     A committed freeze addendum must quote the sealed evaporation hash (else it refuses); the
     config hash of the code being run is recorded and compared with the addendum's.
  3. Builds the sealed region from its raw files through the same data, feature, physics and
     sequence code as the development build (damdays.sealed.region): the manifest must list
     exactly the verified files; SILO from the sealed key, the
     water balance with the development parameters and the typed sealed evaporation shape, the
     dam-like and persistent flags from the region's own pre-2016 looks.
  4. Forecasts every sealed issue 2016-07-01 to 2026-06-30 (P2: seasons 2016-2025) with those models.
     Per-dam quantities (B2, the dam rate, the frailty, the P2 prior) use each sealed dam's own past
     answers as of the issue date.
  5. Scores ONCE with the shared scorecard (damdays.sealed.scoring): G2 and Tidemark on P1 (R30, D0,
     D0g; primary, persistent, all months, sensitivity row), the runway curve, P2 against RAIN, RAIN+
     and B2, band and floor coverage, the PREREG pass bars, the kill rule and the pre-declared
     expectations. Baselines are fitted on the sealed region's own pre-2016-07 history. Every score
     goes on the TEST ledger (artifacts/test_ledger.csv, arena "sealed") and its JSON is written to
     artifacts/sealed/scorecard/ the moment it is computed.
  6. Writes artifacts/sealed/SEALED_RESULTS.md (people) and sealed_results.json (code).

--dry-run runs the SAME steps on a development region treated as unseen (wvic_sesa), with models
fitted on the other development region only (nsw_cw), and scores into a separate dry-run ledger
(artifacts/sealed_dryrun/dryrun_ledger.csv). It is a rehearsal: its numbers are NOT the
development TEST result. It never touches the sealed folder (it refuses to run with the unlock
switch on) and never writes to the real TEST ledger.

Crash safety: the region's tables (step 3) and the forecasts (step 4) are saved as soon as they
exist. A re-run (after a crash fix that does not change predictions, logged with its time) reuses
them, so it scores exactly the same forecasts; the ledger accepts identical forecasts only.
"""
import argparse
import hashlib
import importlib.util
import logging
import pickle
import shutil
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Let "import damdays" work when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damdays import config  # noqa: E402
from damdays.evaluation.ledger import Ledger  # noqa: E402
from damdays.models import nets, physics, rows, tidemark  # noqa: E402
from damdays.sealed import checks, fitted_models, region, report  # noqa: E402
from damdays.sealed.runs import DRY_RUN, OPENING  # noqa: E402
from damdays.sealed.scoring import RegionScoring  # noqa: E402


# ===========================================================================
# The screen and the log file
# ===========================================================================
class RunLog:
    """Prints each line with the clock time and minutes since the start, and appends it to the run's log file."""

    def __init__(self, run):
        self.started = time.time()
        self.path = run.log_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.timing = {}
        self.reused = []          # what a resumed run reloaded instead of recomputing (shown on the results page)

    def say(self, message):
        line = f"[{datetime.now():%H:%M:%S} +{(time.time() - self.started) / 60:4.1f} min] {message}"
        print(line, flush=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def stage(self, name):
        """Use as `with log.stage("..."):` to print the stage and record how long it took."""
        log = self

        class Stage:
            def __enter__(self):
                self.t0 = time.time()
                log.say(f"=== {name} ===")

            def __exit__(self, kind, value, tb):
                log.timing[name] = time.time() - self.t0
                if kind is None:
                    log.say(f"=== {name}: done in {log.timing[name] / 60:.1f} min ===")
        return Stage()


def show_net_progress(log):
    """Send the nets' progress messages (predictions, checkpoints) to the run log."""
    class Handler(logging.Handler):
        def emit(self, record):
            log.say(f"    nets: {record.getMessage()}")
    nets.logger.addHandler(Handler())
    nets.logger.setLevel(logging.INFO)
    nets.logger.propagate = False


# ===========================================================================
# Small pieces
# ===========================================================================
def evaporation_record(region_name):
    """The typed BoM evaporation shape the water balance uses for the region, and its SHA-256.

    Hashed text "<region>:<12 values>" as in the freeze addendum (check: printf '%s' '<text>' | sha256sum).
    """
    text = f"{region_name}:" + ",".join(str(v) for v in physics.EVAPORATION_MM_PER_DAY[region_name])
    return dict(text=text, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())


def config_hash_of_running_code():
    """The event build config hash of the code being run (scripts/14_config_hash.py's recipe), or None if it fails.

    The freeze addendum quotes this hash, so the results page can show that the code that opened
    the region is the code that was frozen.
    """
    try:
        spec = importlib.util.spec_from_file_location("step14_config_hash",
                                                      config.REPO_DIR / "scripts" / "14_config_hash.py")
        step14 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(step14)
        return step14.config_hash()[0]
    except Exception:      # a report item only: never stop the opening for it
        return None


def source_fingerprint(run, checked, models):
    """What the region's tables depend on: the verified raw files and the water-balance parameters."""
    files = checked["hash_list"]["list_sha256"] if not run.rehearsal else checks.sha256_of_file(
        run.cache_dir / "DRYRUN_HASHES.csv")
    return f"{files[:16]}-{models['manifest']['files']['physics']['sha256'][:16]}"


def ledger_rows(run):
    """Number of rows on the run's ledger (0 if it does not exist yet)."""
    return len(Ledger(run.ledger_path).entries())


# ===========================================================================
# Steps 3 and 4: the region's tables and its forecasts (each saved for a resume)
# ===========================================================================
def region_tables(run, models, fingerprint, rebuild, verified_files, log):
    """The region's tables: reloaded if they were built from the same raw files, else built from raw files.

    verified_files  the file names whose SHA-256 step 1 verified: the region's manifest must list exactly these
    """
    if not rebuild:
        saved = region.load_tables(run.region_dir, fingerprint)
        if saved is not None:
            log.say(f"reusing the region's tables saved by an earlier run ({run.region_dir})")
            log.reused.append("the region's tables")
            return saved
    log.say(f"building {run.target_region} from its raw files (data layer, then features, physics, months)")
    data = region.build_data_layer(run.target_region, log.say, verified_files)
    tables = region.build_tables(data, models["physics_params"], log.say)
    counts = region.region_counts(data, tables)
    if region.save_tables(tables, counts, run.region_dir, fingerprint):
        log.say(f"tables saved to {run.region_dir}")
    else:
        log.say("WARNING: not enough free disk space to save the tables; a resumed run would rebuild them")
    return tables, counts


def forecasts_for(run, models, tables, fingerprint, rebuild, log):
    """Tidemark's and G2's forecasts for the region: reloaded if made by the same models from the same tables."""
    path, stamp = run.forecasts_dir / "forecasts.pkl", f"{fingerprint}-{models['manifest']['files']['tidemark']['sha256'][:16]}"
    if path.exists() and not rebuild:
        saved = pd.read_pickle(path)
        if saved["stamp"] == stamp:
            log.say(f"reusing the forecasts saved by an earlier run ({path}): the same forecasts are scored")
            log.reused.append("the forecasts")
            return saved
    log.say(f"Tidemark rung {models['tidemark'].rung.name}: predict_tidemark on {len(tables['p1']):,} issues "
            "(every member predicts each dam's earlier issues too: the frailty needs them)")
    out = tidemark.predict_tidemark(models["tidemark"], region.tidemark_inputs(tables))
    log.say(f"G2: {', '.join(rows.P1_KINDS)}")
    g2 = {kind: fitted_models.g2_forecasts(models["g2"], tables["p1"], kind) for kind in rows.P1_KINDS}
    forecasts = dict(stamp=stamp, tidemark=out, g2=g2)
    check_forecasts(run, forecasts)
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path.parent).free > 2 * 2 ** 30:
        with open(path.with_suffix(".tmp"), "wb") as handle:
            pickle.dump(forecasts, handle, protocol=pickle.HIGHEST_PROTOCOL)
        path.with_suffix(".tmp").replace(path)
        log.say(f"forecasts saved to {path}")
    else:
        log.say("WARNING: less than 2 GB free: forecasts not saved (a resumed run would recompute them)")
    return forecasts


def check_forecasts(run, forecasts):
    """Every forecast is a probability, every row is in the run's target region and in the TEST block."""
    p1 = forecasts["tidemark"]["p1"]
    if set(p1["region"].astype(str)) != {run.target_region}:
        raise AssertionError(f"Forecasts are not all for {run.target_region}.")
    for kind in rows.P1_KINDS:
        values = np.concatenate([forecasts["g2"][kind][1], p1[f"p90_{kind}"].dropna().to_numpy()])
        if not ((values > 0) & (values < 1)).all():
            raise AssertionError(f"A {kind} forecast is not strictly between 0 and 1.")
    for part in ("p2_dam", "p2_cell"):
        if not ((forecasts["tidemark"][part]["p"] > 0) & (forecasts["tidemark"][part]["p"] < 1)).all():
            raise AssertionError(f"A {part} forecast is not strictly between 0 and 1.")


# ===========================================================================
# The modes
# ===========================================================================
def prepare(run, rung, log):
    """Before the opening / dry run: the TEST-setting models and their manifest (nothing sealed is touched)."""
    log.say(f"PREPARE ({run.name}): TEST-setting models, rung {rung}, fitted on {list(run.fit_regions)}")
    with log.stage("models"):
        if run.rehearsal:
            manifest = fitted_models.fit_rehearsal_models(run, rung, log.say)
        else:
            manifest = fitted_models.package_development_models(run, rung, log.say)
    for name, entry in manifest["files"].items():
        log.say(f"  {name}: {entry['path']} ({entry['bytes'] / 2 ** 20:.1f} MB) SHA-256 {entry['sha256']}")
    log.say(f"manifest written: {run.models_manifest}")
    if not run.rehearsal:
        log.say("NEXT: commit and push this manifest with the freeze addendum, before 17:30.")


def open_region(run, args, log):
    """Steps 1-6 of the module docstring, for the opening or the dry run."""
    log.say(run.about)
    rows_before = ledger_rows(run)
    with log.stage("1. checks before touching the region"):
        if run.rehearsal:
            names, folder = region.raw_file_names(run.target_region)
            checked, verified_files = checks.rehearsal_preflight(run, (names, folder),
                                                                 run.cache_dir / "DRYRUN_HASHES.csv", log.say)
        else:
            checked, verified_files = checks.opening_preflight(run, region.raw_source(run.target_region)[1], log.say)

    with log.stage("2. the frozen TEST-setting models and the freeze addendum"):
        try:
            models = fitted_models.load_models(run, log.say)
        except (FileNotFoundError, ValueError) as problem:      # no manifest, or a file that differs from it
            raise checks.CheckFailed(str(problem)) from None
        if (set(models["manifest"]["fit_regions"]) != set(run.fit_regions)
                or models["manifest"]["run"] != run.name):
            raise checks.CheckFailed(f"The manifest {run.models_manifest.name} is for the run "
                                     f"'{models['manifest']['run']}' fitted on {models['manifest']['fit_regions']}, "
                                     f"not for '{run.name}' fitted on {list(run.fit_regions)}.")
        frozen = fitted_models.frozen_rung()
        if models["manifest"]["rung"] != frozen:
            message = f"the models are rung {models['manifest']['rung']}, but the frozen rung is {frozen}"
            if not run.rehearsal:
                raise checks.CheckFailed(message.capitalize() + ".")
            log.say(f"WARNING: {message}")
        evaporation = evaporation_record(run.target_region)
        log.say(f"  rung {models['manifest']['rung']}, fitted on {models['manifest']['fit_regions']} at "
                f"{models['manifest']['cutoff']}; evaporation shape {evaporation['text']} "
                f"(SHA-256 {evaporation['sha256'][:16]}...)")
        code_hash = config_hash_of_running_code()
        checked["config_hash_of_running_code"] = code_hash
        if not run.rehearsal:
            # PREREG: opened after the freeze addendum is committed and pushed; the evaporation shape is hashed in it.
            quoted = checks.freeze_addendum_quotes(evaporation["sha256"], code_hash)
            checked["freeze_addendum"] = quoted
            log.say(f"  the evaporation SHA-256 is quoted in {quoted['evaporation']}")
            log.say(f"  config hash of the code being run: {(code_hash or 'not computed')[:12]}; "
                    + (f"quoted in {quoted['config_hash']}" if quoted["config_hash"] else
                       "WARNING: no addendum quotes it (expected only after a logged crash fix)"))

    fingerprint = source_fingerprint(run, checked, models)
    with log.stage(f"3. build {run.target_region} from raw files"):
        tables, counts = region_tables(run, models, fingerprint, args.rebuild, verified_files, log)
        log.say(f"  {counts['waterbodies_in_manifest']:,} waterbodies; {counts['has_hist']:,} with history; "
                f"{counts['dam_like']:,} dam-like; {counts['persistent']:,} persistent; TEST issues "
                f"{counts['p1_issues_by_block']['TEST']:,}; last look {counts['last_look']}")
    store_comparison = None
    if run.rehearsal and not args.skip_store_check:
        with log.stage("3b. same-code check: the rebuilt region vs the development feature store"):
            store_comparison = region.compare_with_development_store(tables, log.say)

    with log.stage("4. forecasts with the frozen models"):
        forecasts = forecasts_for(run, models, tables, fingerprint, args.rebuild, log)

    with log.stage("5. score once (shared scorecard, ledger " + Path(run.ledger_path).name + ")"):
        scorer = RegionScoring(run, tables, forecasts, models, log.say, quick=args.quick)
        results = scorer.score_everything()

    with log.stage("6. results page"):
        entries = Ledger(run.ledger_path).entries().iloc[rows_before:]
        r = dict(results, run=dict(name=run.name, about=run.about, target_region=run.target_region,
                                   fit_regions=list(run.fit_regions), rehearsal=run.rehearsal),
                 counts=counts, checks=checked, models_manifest=models["manifest"],
                 manifest_path=Path(run.models_manifest).relative_to(config.REPO_DIR).as_posix(),
                 evaporation=evaporation, timing=dict(log.timing), reused=list(log.reused),
                 store_comparison=store_comparison,
                 ledger_path=Path(run.ledger_path).relative_to(config.REPO_DIR).as_posix(),
                 ledger_rows_written=int(len(entries)), ledger_statuses=dict(Counter(entries["status"])),
                 finished_at=datetime.now().astimezone().isoformat(timespec="seconds"), name=run.model_name,
                 quick=bool(args.quick))
        report.write(r, run)
    log.say(f"results: {run.results_md}")
    for line in summary_lines(r):
        log.say(line)


def summary_lines(r):
    """The few lines printed on screen at the end."""
    v = r["verdicts"]
    lines = [f"P1 pass bars (R30 primary): Tidemark {'PASS' if v['p1_pass_bars_tidemark']['all_passed'] else 'FAIL'}, "
             f"G2 {'PASS' if v['p1_pass_bars_g2']['all_passed'] else 'FAIL'}",
             f"P2 pass bar (cell): {'PASS' if v['p2_cell']['passed'] else 'FAIL'}; kill rule "
             f"{'TRIGGERED' if v['p2_cell']['kill_rule_triggered'] else 'not triggered'}"]
    lines += [f"expectation {e['expectation']}: got {e['got']:+.3f} (declared {e['low']:+.2f} to {e['high']:+.2f}): "
              f"{e['verdict']}" for e in v["expectations"] if e["got"] is not None]
    lines += [f"time: {stage}: {seconds / 60:.1f} min" for stage, seconds in r["timing"].items()]
    lines.append(f"time: total {sum(r['timing'].values()) / 60:.1f} min")
    return lines


def archive_dry_run(run, log):
    """--fresh-ledger (dry run only): move the old dry-run ledger and scorecard aside, keeping them."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for path in (run.ledger_path, run.scorecard_dir, run.ledger_path.parent / (run.ledger_path.stem + "_preds")):
        if Path(path).exists():
            target = Path(path).with_name(f"{Path(path).name}.old_{stamp}")
            Path(path).rename(target)
            log.say(f"dry run: archived {path} -> {target.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     epilog="Runbook: docs/SEALED_OPENING.md")
    parser.add_argument("--open", action="store_true", help="THE opening of the sealed region (once, Sat 17:30 AEST)")
    parser.add_argument("--dry-run", action="store_true", help="the rehearsal on wvic_sesa (models fitted on nsw_cw)")
    parser.add_argument("--prepare", action="store_true",
                        help="before the run: fingerprint the opening's models (alone) or fit the rehearsal's "
                             "models (with --dry-run)")
    parser.add_argument("--rung", default=None, help="rung of the models to prepare (default: the frozen rung)")
    parser.add_argument("--quick", action="store_true", help="dry run only: no bootstrap intervals (faster)")
    parser.add_argument("--rebuild", action="store_true", help="dry run only: ignore saved region tables and forecasts")
    parser.add_argument("--fresh-ledger", action="store_true",
                        help="dry run only: archive the old dry-run ledger and scorecard first")
    parser.add_argument("--skip-store-check", action="store_true", help="dry run only: skip the same-code check")
    args = parser.parse_args()
    if args.open == (args.dry_run or args.prepare):
        parser.error("choose --open, or --dry-run, or --prepare (with or without --dry-run).")
    run = DRY_RUN if args.dry_run else OPENING
    if run is OPENING and (args.quick or args.rebuild or args.fresh_ledger or args.skip_store_check):
        parser.error("--quick, --rebuild, --fresh-ledger and --skip-store-check are for the dry run only.")
    log = RunLog(run)
    log.say(f"scripts/20_open_sealed_region.py {' '.join(sys.argv[1:])} (run '{run.name}')")
    show_net_progress(log)
    try:
        if args.prepare:
            prepare(run, args.rung or fitted_models.frozen_rung(), log)
        else:
            if args.fresh_ledger:
                archive_dry_run(run, log)
            open_region(run, args, log)
    except checks.CheckFailed as refusal:
        log.say(f"REFUSED: {refusal}")
        log.say("No water history was read and nothing was scored. Fix the cause (docs/SEALED_OPENING.md, "
                "'If a check refuses') and run again.")
        sys.exit(2)
    except Exception:
        for line in traceback.format_exc().rstrip().splitlines():
            log.say("  " + line)
        log.say("CRASHED. See docs/SEALED_OPENING.md, 'If it crashes': fix the crash only, log the fix with its time, "
                "commit and push, and run the same command again (saved tables and forecasts are reused).")
        sys.exit(1)


if __name__ == "__main__":
    main()
