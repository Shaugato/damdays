"""Step 15: score the development TEST block ONCE: the frozen model's one look at 2016-2026.

Run from the repo folder, after scripts/13 (which fitted the frozen models and saved their forecasts):
    .venv/Scripts/python.exe scripts/15_score_test.py --check        # build and check every table; score NOTHING
    .venv/Scripts/python.exe scripts/15_score_test.py                # THE ONE LOOK (about 15-30 minutes)
    .venv/Scripts/python.exe scripts/15_score_test.py --report-only  # rewrite the results page from the saved
                                                                     # results (no scoring, no ledger row)

What is scored (PREREG "Forecasts", "Pass bars" and "Reported regardless of outcome")
--------------------------------------------------------------------------------
Every forecast issued 2016-07-01 to 2026-06-30 in the two development regions (season ratings: every
1 July from 2016 to 2025), made by the frozen models of PREREG_ADDENDUM_1.md (rung L3, event build
config hash 7d466291008d) and saved by scripts/13_fit_test_setting.py. Nothing is refitted or
re-forecast here: this step only reads the saved forecasts and the answers, and scores.

  P1, the farmer runway (R30 below a third, D0 fully dry, D0g gradual dry-out), within 90 days:
      G2 (the benchmark), then Tidemark, on the primary set (dam-like, Oct-Mar, at risk), persistent
      dams (Oct-Mar, at risk) and dam-like dams in all months; plus the label-determinable
      sensitivity row (primary set, no 3-look rule). Every Tidemark score carries the PAIRED
      difference Tidemark minus G2 (same rows, same resampled dams and region-years).
  PREREG pass bars: P1 (R30 primary: BSS vs B0 >= +0.10 with the dam CI above 0, BSS vs B2 >= +0.05,
      calibration slope 0.8 to 1.2); P2 (AUC gain over RAIN >= +0.05 with the dam CI above 0) and
      the kill rule (RAIN within 0.02 AUC of the rating: drop the finance claim).
  Runway curve: BSS at 30, 60, 90 and 180 days, each horizon against its own base rate B0_h.
  DamDays floor: the share of "at least N days" floors that held (target 0.90) and the median floor.
  Season band: how many July-June region-years fall inside the shipped (pooled) band, and inside
      the single-block (2009-2016) band that PREREG reports alongside.
  P2, the lender rating (2 km cell, dam, gradual-dry dam): RAIN, RAIN+ and B2, then Tidemark.
  Not part of TEST: grouped-dam CV and leave-one-region-out (VAL only, PREREG "Splits").

One look per model (docs/SCORECARD.md, section 5)
-------------------------------------------------
Every score goes through the shared scorecard (damdays.evaluation.score and score_curve) and the
TEST ledger, artifacts/test_ledger.csv. The first call for each model and task is recorded as
"new" (26 in all: one per model and task). Every further subset of that task passes the SAME
forecast table, so it is recorded as "same_predictions". A re-run of this script reads the same
saved files, so every call is again "same_predictions"; a changed forecast would be refused before
any number is computed. --check builds every table and runs every scorecard input check as a dry
run on a scratch COPY of the ledger (no number is computed, the real ledger is not written), and
prints what the real ledger would record for each call.

The subsets, the bootstrap sizes and the PREREG P2 rule are imported from the sealed-region scorer
(damdays.sealed.scoring), so the development TEST block and the sealed region are judged alike.

Inputs, each checked before anything is scored
----------------------------------------------
  data_cache/preds/TEST/...       step 13's forecasts. Each file's fingerprint must equal the one
                                  step 13 recorded in artifacts/test_setting_fit_summary.json.
  data_cache/models/TEST/...      the frozen model files: SHA-256 must equal the committed
                                  artifacts/sealed_models_manifest.json (PREREG_ADDENDUM_1.md, section 5).
  data_cache/features/...         the answers (labels) and subset flags: the same files step 13
                                  forecast from (same fingerprints).

Outputs
-------
  artifacts/test_results.md, artifacts/test_results.json   the results page and every number
  artifacts/scorecard/step15_test/                          one JSON per score (written by the scorecard
                                                            the moment it is computed), markdown rows, run log
  artifacts/test_ledger.csv                                 one row per scoring call
  data_cache/models/TEST/step15_results.pkl                 every result, saved before the page is written

CPU: no model is fitted or run here (no LightGBM, no torch); the scorecard uses numpy.
"""
import argparse
import hashlib
import json
import math
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Let "import damdays" work when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damdays import config  # noqa: E402
from damdays.data.splits import time_block  # noqa: E402
from damdays.evaluation import band_coverage, crossing_share, floor_coverage, score, score_curve  # noqa: E402
from damdays.evaluation.inputs import join_baselines, tidy_keys  # noqa: E402
from damdays.evaluation.ledger import LEDGER_PATH, Ledger, model_key  # noqa: E402
from damdays.evaluation.report import clean_for_json, number, with_intervals  # noqa: E402
from damdays.evaluation.rules import is_octmar  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import hazard, rows  # noqa: E402
from damdays.models import uncertainty as unc  # noqa: E402
from damdays.sealed.scoring import (CURVE_SUBSETS, N_BOOT_MAIN, N_BOOT_SIDE, P1_SUBSETS,  # noqa: E402
                                    P2_BASELINE_MODELS, P2_TASKS, PRIMARY, p2_rules)

BLOCK, ARENA = "TEST", "dev"
KINDS = rows.P1_KINDS                       # R30, D0, D0g
HORIZONS = hazard.HORIZONS                  # 30, 60, 90, 180 days
N_BOOT = {"main": N_BOOT_MAIN, "side": N_BOOT_SIDE}   # 500 draws on primary sets and P2, 200 on other subsets
FROZEN = dict(rung="L3", config_hash="7d466291008d", addendum="PREREG_ADDENDUM_1.md")
NOTE = "dev TEST one look, scripts/15_score_test.py; frozen L3 (config 7d466291008d); step 13 forecasts"

FIT_SUMMARY = config.ARTIFACTS_DIR / "test_setting_fit_summary.json"     # step 13's record, with fingerprints
MODELS_MANIFEST = config.ARTIFACTS_DIR / "sealed_models_manifest.json"   # the frozen model files' SHA-256
VAL_RESULTS = config.ARTIFACTS_DIR / "val_tidemark_best.json"            # the same model's VAL scores (step 12)
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step15_test"
LOG_FILE = SCORE_DIR / "run_log.txt"
RESULTS_MD = config.ARTIFACTS_DIR / "test_results.md"
RESULTS_JSON = config.ARTIFACTS_DIR / "test_results.json"
SAVED_RESULTS = config.CACHE_DIR / "models" / BLOCK / "step15_results.pkl"
ANSWER_FILES = ["data_cache/features/p1_keys.pkl", "data_cache/features/p2_dam.pkl",
                "data_cache/features/p2_cell.pkl", "data_cache/features/dam_rate_prior.pkl"]

# The pre-event research's numbers on this same block. They are POST-SELECTION: about ten research
# configurations were scored here before the event and Tidemark's design was informed by them
# (PREREG "Pre-event research status": optimistic by roughly 0.005-0.01). (label, value, source)
PRE_EVENT_TEST = [
    ("R30 BSS vs B0, Tidemark (primary)", 0.233, "PREREG.md, Pre-event research status"),
    ("R30 BSS vs B0, G2 (primary)", 0.211, "PREREG.md, Pre-event research status"),
    ("R30 Tidemark minus G2 (primary)", 0.022, "derived from PREREG.md: +0.233 - +0.211 (two separate scores, not paired)"),
    ("P2 cell AUC, Tidemark", 0.810, "pre-event research results (outside this repository)"),
    ("P2 cell AUC gain over RAIN", 0.296, "pre-event research results (outside this repository)"),
    ("DamDays floor: share that held (all)", 0.901, "artifacts/uncertainty_val.md (pre-event TEST result)"),
    ("DamDays floor: share that held (primary)", 0.911, "artifacts/uncertainty_val.md (pre-event TEST result)"),
    ("DamDays floor: median floor (days)", 60.0, "artifacts/uncertainty_val.md (pre-event TEST result)"),
]
STARTED = time.time()


# ===========================================================================
# Logging, fingerprints, small helpers
# ===========================================================================
def say(message):
    """Print a progress line (clock time, minutes since the start) and append it to the run log."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} [{(time.time() - STARTED) / 60:5.1f} min] {message}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def file_sha256(path):
    """Full SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for piece in iter(lambda: handle.read(2 ** 24), b""):
            digest.update(piece)
    return digest.hexdigest()


def table_fingerprint(frame):
    """Step 13's fingerprint of a saved forecast table (every stored value, the columns and the row order)."""
    row_hashes = pd.util.hash_pandas_object(frame, index=False).to_numpy()
    return hashlib.sha256("|".join(map(str, frame.columns)).encode() + row_hashes.tobytes()).hexdigest()[:16]


def git_state():
    """The repo's commit and whether it has uncommitted changes."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=config.REPO_DIR, capture_output=True, text=True).stdout.strip()
    return dict(commit=git("rev-parse", "HEAD"), uncommitted_changes=bool(git("status", "--porcelain")))


# ===========================================================================
# 1. Load the saved forecasts and the answers, and check they are the frozen ones
# ===========================================================================
def load_forecasts(summary):
    """Every forecast table step 13 saved, keyed "<task>/<name>"; each must match its recorded fingerprint."""
    out = {}
    for record in summary["files"]:
        if "fingerprint" not in record:          # the model files (checked against the manifest instead)
            continue
        frame = pd.read_pickle(config.REPO_DIR / record["path"])
        got = table_fingerprint(frame)
        if got != record["fingerprint"] or len(frame) != record["rows"]:
            raise AssertionError(f"{record['path']}: fingerprint {got} ({len(frame):,} rows), but step 13 recorded "
                                 f"{record['fingerprint']} ({record['rows']:,} rows). Not the frozen forecasts.")
        key = "/".join(Path(record["path"]).with_suffix("").parts[-2:])     # e.g. "P1_R30/g2", "tidemark/L3_p1"
        out[key] = frame
    say(f"forecasts: {len(out)} files from step 13, every fingerprint matches artifacts/test_setting_fit_summary.json")
    return out


def check_frozen_models():
    """The frozen model files' SHA-256 against the committed manifest (PREREG_ADDENDUM_1.md, section 5)."""
    manifest = json.loads(MODELS_MANIFEST.read_text(encoding="utf-8"))
    out = {}
    for name in ("tidemark", "g2"):
        record = manifest["files"][name]
        got = file_sha256(config.REPO_DIR / record["path"])
        if got != record["sha256"]:
            raise AssertionError(f"{record['path']}: SHA-256 {got[:16]}... is not the frozen model in the manifest.")
        out[name] = dict(path=record["path"], sha256=got)
    if manifest["rung"] != FROZEN["rung"]:
        raise AssertionError(f"The manifest's rung is {manifest['rung']}, not the frozen {FROZEN['rung']}.")
    say(f"frozen model files match the committed manifest: tidemark {out['tidemark']['sha256'][:16]}..., "
        f"g2 {out['g2']['sha256'][:16]}...")
    return out


def load_answers(summary):
    """The answers and subset flags: the P1 issue table (keys group), the P2 tables and the archive's end date.

    These are the files step 13 forecast from: their fingerprints must equal the ones it recorded.
    """
    for path in ANSWER_FILES:
        got = file_sha256(config.REPO_DIR / path)[:16]
        if got != summary["inputs"]["files"][path]:
            raise AssertionError(f"{path} changed since step 13 ({got} vs {summary['inputs']['files'][path]}).")
    table = store.load_p1(groups=("keys",))            # one row per P1 issue: keys, flags, labels
    found = set(pd.unique(table["region"].astype(str)))
    if not found <= set(config.DEV_REGIONS):
        raise AssertionError(f"Unexpected regions in the P1 table: {sorted(found)}")
    data_end = pd.Timestamp(pd.read_pickle(store.FEATURES_DIR / "dam_rate_prior.pkl")["data_end"])
    say(f"answers: P1 table {len(table):,} rows (regions {sorted(found)}), archive ends {data_end.date()}; "
        f"files identical to the ones step 13 forecast from")
    return dict(p1=table, p2_dam=store.load_p2("dam"), p2_cell=store.load_p2("cell"), data_end=data_end)


def on_rows(forecasts, positions, column, keys):
    """`column` of a saved P1 forecast table on the given P1-table rows.

    The saved table's "row" column gives each forecast's position in the P1 table; the dam and the
    issue date must also match `keys` row for row, so a forecast can never land on the wrong issue.
    """
    part = forecasts.set_index("row").loc[np.asarray(positions)]
    same = ((part["uid"].astype(str).to_numpy() == keys["uid"].astype(str).to_numpy()).all()
            and (pd.to_datetime(part["issue_date"]).to_numpy() == pd.to_datetime(keys["issue_date"]).to_numpy()).all())
    if not same:
        raise AssertionError(f"Saved forecasts ({column}) do not line up with the P1 table's rows.")
    values = part[column].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise AssertionError(f"{column}: {int((~np.isfinite(values)).sum())} rows have no forecast.")
    return values


# ===========================================================================
# 2. The scoring calls, through the scorecard and the ledger
# ===========================================================================
class Scoring:
    """Runs every scorecard call, in ledger order, and keeps the results.

    The real run uses the real TEST ledger. --check runs every call as a dry run on a scratch copy
    of the ledger: every input check runs, no number is computed, the real ledger is not written.
    """

    def __init__(self, check):
        self.check = check
        self.results, self.curves, self.not_scored, self.planned = {}, {}, [], []
        if check:
            self.scratch = Path(tempfile.mkdtemp(prefix="damdays_step15_check_"))
            if LEDGER_PATH.exists():
                shutil.copy(LEDGER_PATH, self.scratch / LEDGER_PATH.name)
            self.ledger = Ledger(self.scratch / LEDGER_PATH.name)
        else:
            self.ledger = Ledger()                      # artifacts/test_ledger.csv

    def scorable(self, frame, keys, task, subset, model):
        """A subset needs labelled rows with both events and non-events; otherwise it is listed, not scored.

        `keys` are rows of `frame` (same index), so their answers are frame.loc[keys.index, "y"].
        """
        y = frame.loc[keys.index, "y"].to_numpy(dtype=float)
        if len(y) and 0 < y.sum() < len(y):
            return True
        self.not_scored.append(dict(task=task, subset=subset, model=model, rows=int(len(y)), events=int(y.sum())))
        say(f"  NOT SCORABLE: {task} {subset} {model}: {len(y):,} labelled rows, {int(y.sum()):,} events")
        return False

    def references(self, refs, task):
        """--check only: a dry run cannot make a first look, so it names only references already on the ledger."""
        if not self.check:
            return list(refs)
        return [r for r in refs if self.ledger.first_look(model_key(r), task, ARENA) is not None]

    def record_plan(self, task, subset, model):
        """--check only: what the real ledger would record for this call (read from the dry run's ledger row)."""
        note = self.ledger.entries().iloc[-1]["note"]
        self.planned.append(dict(task=task, subset=subset, model=model, would_be=note.split(";")[0]))

    def score(self, frame, task, subset, model, refs, keys, boot, baselines=None):
        """One score() call. On TEST the ledger decides first; the result is kept under (task, subset, model)."""
        if not self.scorable(frame, keys, task, subset, model):
            return None
        result = score(frame.assign(p=frame[f"p_{model}"]), task, subset, model=model,
                       refs=self.references(refs, task), baselines=baselines, expected_keys=keys,
                       n_boot=N_BOOT[boot], out_dir=SCORE_DIR, ledger=self.ledger, note=NOTE, dry_run=self.check)
        if self.check:
            self.record_plan(task, result["subset"], model)
        self.results[(task, result["subset"], model)] = result
        return result

    def score_curve(self, frame, task, subset, boot, baselines):
        """One score_curve() call (Tidemark's runway curve), through the same ledger."""
        result = score_curve(frame, task, subset, model="tidemark", baselines=baselines, n_boot=N_BOOT[boot],
                             out_dir=SCORE_DIR, ledger=self.ledger, note=NOTE, dry_run=self.check)
        if self.check:
            self.record_plan(task, result["subset"], "tidemark")
        self.curves[(task, result["subset"])] = result
        return result


def expected_keys(frame, population, octmar_only, label="y"):
    """The rows a P1 subset must be scored on, worked out here independently of the scorecard."""
    keep = frame[label].notna().to_numpy() & frame[population].to_numpy(dtype=bool)
    if octmar_only:
        keep = keep & is_octmar(frame["issue_date"])
    return frame.loc[keep, ["uid", "issue_date"]]


def p1_keys_and_flags(table, kind):
    """Every at-risk TEST issue of `kind`: its P1-table positions, the rows, and keys + subset flags."""
    picked = rows.p1_block_rows(table, kind, BLOCK)
    chosen = table.loc[picked]
    frame = pd.DataFrame({
        "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
        "region": chosen["region"].astype(str).to_numpy(),
        "dam_like": chosen["dam_like"].to_numpy(dtype=bool), "persistent": chosen["persistent"].to_numpy(dtype=bool),
        "at_risk": True})                                            # every row here is at risk for this kind
    return np.flatnonzero(picked), chosen, frame


# ---------------------------------------------------------------------------
# P1: G2 then Tidemark, three kinds, three subsets, and the sensitivity row
# ---------------------------------------------------------------------------
def p1_frame(table, saved, kind):
    """Keys, flags, the answer, the sensitivity answer, and the G2 and Tidemark 90-day forecasts."""
    positions, chosen, frame = p1_keys_and_flags(table, kind)
    raw = chosen[rows.p1_label(kind)].to_numpy(dtype=float)
    frame["y"] = rows.p1_scored_label(chosen, kind)                        # blank where label_ok is False
    # PREREG sensitivity label: every issue whose 90-day window has closed, without the 3-look rule.
    frame["y_sens"] = np.where(chosen["window_closed"].to_numpy(dtype=bool), raw, np.nan)
    frame["p_G2"] = on_rows(saved[f"P1_{kind}/g2"], positions, "p", frame)
    frame["p_tidemark"] = on_rows(saved["tidemark/L3_p1"], positions, f"p90_{kind}", frame)
    return frame


def score_p1(scoring, answers, saved):
    """For each kind and subset: G2 first, then Tidemark with G2 as its paired reference; then the sensitivity row."""
    for kind in KINDS:
        task, frame = f"P1_{kind}", p1_frame(answers["p1"], saved, kind)
        for subset, population, octmar_only, boot in P1_SUBSETS:
            keys = expected_keys(frame, population, octmar_only)
            base = saved[f"{task}/baselines_{population}"]               # B0, B2 fitted on that population
            for model, refs in (("G2", []), ("tidemark", ["G2"])):
                scoring.score(frame, task, subset, model, refs, keys, boot, baselines=base)
        sens = frame.assign(y=frame["y_sens"])
        keys = expected_keys(frame, "dam_like", True, "y_sens")
        for model, refs in (("G2", []), ("tidemark", ["G2"])):
            scoring.score(sens, f"{task}_sens", "primary", model, refs, keys, "side",
                          baselines=saved[f"{task}/baselines_dam_like"])
        if not scoring.check:
            got = {m: scoring.results.get((task, PRIMARY, m)) for m in ("tidemark", "G2")}
            say(f"  {task} primary, BSS vs B0: " + ", ".join(
                f"{m} {r['point']['bss_B0']:+.4f}" for m, r in got.items() if r is not None))


# ---------------------------------------------------------------------------
# The runway curve (Tidemark only: G2 has no curve)
# ---------------------------------------------------------------------------
def curve_frame(answers, saved, kind):
    """Keys, flags, the answers at 30/60/90/180 days (blank if not known yet) and Tidemark's curve."""
    table = answers["p1"]
    labels = hazard.horizon_labels(table, kind, answers["data_end"])     # y_90 is checked against the P1 label
    positions, _, frame = p1_keys_and_flags(table, kind)
    picked = rows.p1_block_rows(table, kind, BLOCK)
    for h in HORIZONS:
        frame[f"y_{h}"] = labels.loc[picked, f"y_{h}"].to_numpy()
        frame[f"p_{h}"] = on_rows(saved["tidemark/L3_p1"], positions, f"curve_{kind}_{h}", frame)
    return frame


def score_curves(scoring, answers, saved):
    """Tidemark's curve on each subset, each horizon against its own B0_h and B2_h; and the R30 >= D0 check."""
    for kind in hazard.CURVE_KINDS:
        frame = curve_frame(answers, saved, kind)
        for subset, population, boot in CURVE_SUBSETS:
            result = scoring.score_curve(frame, f"{kind}_curve", subset, boot, saved[f"{kind}_curve/baselines_{population}"])
            if not scoring.check and result["subset"] == PRIMARY:
                say(f"  {kind}_curve primary, BSS vs B0_h: " + ", ".join(
                    f"{h} d {number(v)}" for h, v in result["bss_B0_by_horizon"].items()))
    # A dry dam is also below a third: the R30 curve must never sit below the D0 curve (forecasts only).
    tm = saved["tidemark/L3_p1"]
    r30 = tm[tm["at_risk_R30"].to_numpy(dtype=bool)]
    return crossing_share(r30[[f"curve_R30_{h}" for h in HORIZONS]].to_numpy(dtype=float),
                          r30[[f"curve_D0_{h}" for h in HORIZONS]].to_numpy(dtype=float))


# ---------------------------------------------------------------------------
# P2: the season rating against RAIN, RAIN+ and B2
# ---------------------------------------------------------------------------
def p2_frame(answers, saved, task, column):
    """Tidemark's season ratings with their answers, subset flags and every P2 baseline (step 13's)."""
    forecasts = saved["tidemark/L3_p2_cell"] if task == "P2_cell" else saved["tidemark/L3_p2_dam"]
    frame = tidy_keys(pd.DataFrame({"uid": forecasts["uid"].astype(str).to_numpy(),
                                    "issue_date": forecasts["issue_date"].to_numpy(),
                                    "region": forecasts["region"].astype(str).to_numpy(),
                                    "p_tidemark": forecasts[column].to_numpy(dtype=float)}))
    source = answers["p2_cell"] if task == "P2_cell" else answers["p2_dam"]
    rated = source.loc[rows.p2_block_rows(source, BLOCK)]
    truth = pd.DataFrame({"uid": rated["uid"].astype(str).to_numpy(), "issue_date": rated["issue_date"].to_numpy(),
                          "region": rated["region"].astype(str).to_numpy(),
                          "y": rows.p2_scored_label(rated, rows.P2_LABELS[task])})   # blank where label_ok is False
    if task != "P2_cell":
        truth["dam_like"] = rated["dam_like"].to_numpy(dtype=bool)
        truth["persistent"] = rated["persistent"].to_numpy(dtype=bool)
    # join_baselines: every forecast must find its row (else an error); shared columns (region) must agree.
    frame = join_baselines(frame, truth)
    return join_baselines(frame, saved[f"{task}/baselines"])         # p_B0, p_B2, p_PERS, p_RAIN, p_RAIN+


def score_p2(scoring, answers, saved):
    """RAIN, RAIN+ and B2 first (each scored as a model), then Tidemark with all three as paired references."""
    for task, subset, column in P2_TASKS:
        frame = p2_frame(answers, saved, task, column)
        keep = frame["y"].notna().to_numpy()
        if subset == "dam_like":
            keep = keep & frame["dam_like"].to_numpy(dtype=bool)
        keys = frame.loc[keep, ["uid", "issue_date"]]
        for model in P2_BASELINE_MODELS:
            scoring.score(frame, task, subset, model, [], keys, "main")
        result = scoring.score(frame, task, subset, "tidemark", list(P2_BASELINE_MODELS), keys, "main")
        if result is not None and not scoring.check:
            say(f"  {task}: Tidemark AUC {result['point']['auc']:.4f}; gain over " + ", ".join(
                f"{m} {result['point']['d_auc_vs_' + m]:+.4f}" for m in P2_BASELINE_MODELS))


# ===========================================================================
# 3. Season band and DamDays floor (computed on the same, already ledgered, Tidemark forecasts)
# ===========================================================================
def band(answers, saved, constants):
    """Region-year coverage of the pooled band (shipped) and of the single-block 2009-2016 band.

    A region-year's offset is how far, in log-odds, that July-June year's primary-set forecasts were off
    on average (calibration-in-the-large). The band covers the year when its offset lies inside it.
    """
    table, out = answers["p1"], {}
    for kind in KINDS:
        mask = ((time_block(table["issue_date"]) == BLOCK) & table["dam_like"].to_numpy(dtype=bool)
                & is_octmar(table["issue_date"]) & table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)
                & table["label_ok"].to_numpy(dtype=bool) & table[rows.p1_label(kind)].notna().to_numpy())
        part = table.loc[mask]
        p = on_rows(saved["tidemark/L3_p1"], np.flatnonzero(mask), f"p90_{kind}", part)
        offsets = unc.block_offsets(part[rows.p1_label(kind)].to_numpy(dtype=float), p, part["region"],
                                    part["issue_date"], BLOCK)
        out[kind] = dict(pooled=band_coverage(offsets, *constants["pooled"][kind]),
                         single_block_2009_2016=band_coverage(offsets, *constants["2009-2016 alone"][kind]),
                         offsets=offsets.to_dict(orient="records"))
    say("  season band, region-years covered: pooled " + ", ".join(
        f"{k} {v['pooled']['covered']}/{v['pooled']['region_years']}" for k, v in out.items()) + "; single-block "
        + ", ".join(f"{k} {v['single_block_2009_2016']['covered']}/{v['single_block_2009_2016']['region_years']}"
                    for k, v in out.items()))
    return out


def floor(answers, saved):
    """DamDays floor coverage as issued (all labelled forecasts; primary set) and as shown in the app (180+ cap).

    A floor of N days is judged only if the archive watched the dam for at least N days after the
    issue, whatever happened (damdays.evaluation.coverage.floor_coverage explains why).
    """
    table = answers["p1"]
    positions, chosen, keys = p1_keys_and_flags(table, unc.FLOOR_KIND)
    labelled = chosen["label_ok"].to_numpy(dtype=bool)
    primary = labelled & chosen["dam_like"].to_numpy(dtype=bool) & is_octmar(chosen["issue_date"])
    days_to = chosen[f"lab_tte_{unc.FLOOR_KIND}"].to_numpy(dtype=float)
    follow = unc.followup_days(chosen["issue_date"], answers["data_end"])
    uid, dates = keys["uid"].to_numpy(), keys["issue_date"].to_numpy()
    issued = on_rows(saved["tidemark/L3_p1"], positions, "floor_days", keys)
    shown = on_rows(saved["tidemark/L3_p1"], positions, "floor_shown", keys)

    def one(values, mask, boot, cap=None):
        result = floor_coverage(values[mask], days_to[mask], follow[mask], uid=uid[mask], issue_date=dates[mask],
                                cap_days=cap, n_boot=N_BOOT[boot])
        result.pop("bootstrap", None)
        return result
    out = dict(issued_all=one(issued, labelled, "main"), issued_primary=one(issued, primary, "main"),
               shown_all=one(shown, labelled, "side", unc.FLOOR_DISPLAY_MAX_DAYS))
    say(f"  DamDays floor held: {out['issued_all']['coverage']:.4f} (all), {out['issued_primary']['coverage']:.4f} "
        f"(primary); median floor {out['issued_all']['median_floor_days']:.1f} days; target 0.90")
    return out


# ===========================================================================
# 4. PREREG verdicts, and the comparison with the pre-event and VAL numbers
# ===========================================================================
def verdicts(scores):
    """The P1 pass bars (Tidemark and G2) and, for each season rating, the P2 bar and the kill rule."""
    return dict(p1_pass_bars_tidemark=scores[("P1_R30", PRIMARY, "tidemark")]["prereg_pass_bars"],
                p1_pass_bars_g2=scores[("P1_R30", PRIMARY, "G2")]["prereg_pass_bars"],
                **{f"p2_{task.replace('P2_', '')}": p2_rules(scores[(task, subset, "tidemark")], "RAIN")
                   for task, subset, _ in P2_TASKS if (task, subset, "tidemark") in scores})


def comparison(scores, floor_result):
    """Each pre-event TEST number next to this run's value on the same quantity, and the VAL value for context."""
    val = json.loads(VAL_RESULTS.read_text(encoding="utf-8"))
    val_r30 = val["p1"]["P1_R30|primary|L3"]["point"]
    tm, g2, cell = (scores[("P1_R30", PRIMARY, "tidemark")], scores[("P1_R30", PRIMARY, "G2")],
                    scores[("P2_cell", "all", "tidemark")])
    got = {
        "R30 BSS vs B0, Tidemark (primary)": (tm["point"]["bss_B0"], tm["ci_dam"].get("bss_B0"), val_r30["bss_B0"]),
        "R30 BSS vs B0, G2 (primary)": (g2["point"]["bss_B0"], g2["ci_dam"].get("bss_B0"),
                                        val_r30["bss_B0"] - val_r30["d_bss_B0_vs_G2"]),
        "R30 Tidemark minus G2 (primary)": (tm["point"]["d_bss_B0_vs_G2"], tm["ci_dam"].get("d_bss_B0_vs_G2"),
                                            val_r30["d_bss_B0_vs_G2"]),
        "P2 cell AUC, Tidemark": (cell["point"]["auc"], cell["ci_dam"].get("auc"), val["p2"]["P2_cell|all|L3"]["point"]["auc"]),
        "P2 cell AUC gain over RAIN": (cell["point"]["d_auc_vs_RAIN"], cell["ci_dam"].get("d_auc_vs_RAIN"),
                                       val["p2_rules"]["d_auc_vs_RAIN"]),
        "DamDays floor: share that held (all)": (floor_result["issued_all"]["coverage"],
                                                 floor_result["issued_all"].get("ci_dam", {}).get("coverage"),
                                                 val["floor"]["issued_all"]["coverage"]),
        "DamDays floor: share that held (primary)": (floor_result["issued_primary"]["coverage"],
                                                     floor_result["issued_primary"].get("ci_dam", {}).get("coverage"),
                                                     val["floor"]["issued_primary"]["coverage"]),
        "DamDays floor: median floor (days)": (floor_result["issued_all"]["median_floor_days"], None,
                                               val["floor"]["issued_all"]["median_floor_days"]),
    }
    return [dict(quantity=label, pre_event_test=pre, source=source, event_test=got[label][0], ci_dam=got[label][1],
                 difference=got[label][0] - pre, val_2009_2015=got[label][2]) for label, pre, source in PRE_EVENT_TEST]


# ===========================================================================
# 5. The results page
# ===========================================================================
def pct(value):
    """A share as a whole percentage, e.g. 0.2331 -> "23%"."""
    return "-" if value is None or not math.isfinite(value) else f"{100 * value:.0f}%"


def yes_no(flag, yes="PASS", no="FAIL"):
    return f"**{yes}**" if flag else f"**{no}**"


def ci_text(ci, digits=3, sign=True):
    return f" [{number(ci[0], digits, sign)}, {number(ci[1], digits, sign)}]" if ci else ""


def paired_verdict(ci_dam, ci_ry, region_years):
    """One sentence on Tidemark minus G2, read off its two 95% ranges."""
    if not ci_dam:
        return "No interval was computed."
    if ci_dam[0] > 0 and ci_ry and ci_ry[0] > 0:
        return "Both ranges sit above zero: Tidemark is reliably better than G2 on these years."
    if ci_dam[0] > 0:
        return (f"The dam range sits above zero but the region-year range does not: better on these dams, but with "
                f"only {region_years} region-years the gain could come from a run of favourable years.")
    if ci_dam[1] < 0:
        return "The dam range sits below zero: G2 is reliably better than Tidemark on these years."
    return "The dam range includes zero: no reliable difference between Tidemark and G2 on these years."


def plain_words(r):
    """The plain-language summary at the top of the page, written from the numbers."""
    s, v = r["scores"], r["verdicts"]
    tm, g2 = s[("P1_R30", PRIMARY, "tidemark")], s[("P1_R30", PRIMARY, "G2")]
    gain, gain_ci = tm["point"]["d_bss_B0_vs_G2"], tm["ci_dam"].get("d_bss_B0_vs_G2")
    gain_ry = tm["ci_region_year"].get("d_bss_B0_vs_G2")
    bars = v["p1_pass_bars_tidemark"]
    cell, curve = v.get("p2_cell"), r["curves"].get(("R30_curve", PRIMARY))
    floor_all = r["floor"]["issued_all"]
    pooled = {k: b["pooled"] for k, b in r["band"].items()}
    lines = ["## In plain words", "",
             f"- **The farmer's headline (will the dam fall below a third of full within 90 days?).** On the test years, "
             f"Tidemark's forecasts remove {pct(tm['point']['bss_B0'])} of the simple seasonal rule's squared error "
             f"(Brier skill {number(tm['point']['bss_B0'])}, 95% range{ci_text(tm['ci_dam'].get('bss_B0'))}); "
             f"the benchmark G2 removes {pct(g2['point']['bss_B0'])} ({number(g2['point']['bss_B0'])}). "
             f"Tidemark ranks a dam that fell below a third above one that did not {pct(tm['point']['auc'])} of the "
             f"time (AUC {number(tm['point']['auc'], 3, False)}).",
             f"- **Tidemark against the benchmark, on exactly the same forecasts:** {number(gain, 4)}{ci_text(gain_ci, 4)} "
             f"(resampling dams; resampling region-years{ci_text(gain_ry, 4)}). "
             + paired_verdict(gain_ci, gain_ry, tm["rows"]["region_years"]),
             f"- **Pre-registered pass bars (R30):** skill vs the simple rule {number(bars['bss_B0']['value'])} "
             f"(bar +0.10) {yes_no(bars['bss_B0']['passed'])}; vs the dam's own track record "
             f"{number(bars['bss_B2']['value'])} (bar +0.05) {yes_no(bars['bss_B2']['passed'])}; calibration slope "
             f"{number(bars['cal_slope']['value'], 2, False)} (bar 0.8 to 1.2) {yes_no(bars['cal_slope']['passed'])}."]
    if cell is not None:
        cell_score = s[("P2_cell", "all", "tidemark")]
        rain = s.get(("P2_cell", "all", "RAIN"))
        lines.append(
            f"- **The lender rating (will every farm dam in a 2 km cell run dry this summer?):** it ranks a cell that "
            f"ran dry above one that did not {pct(cell_score['point']['auc'])} of the time (AUC "
            f"{number(cell_score['point']['auc'], 3, False)}), against {pct(rain['point']['auc']) if rain else '-'} for "
            f"the rainfall-only score RAIN. Gain {number(cell['d_auc_vs_RAIN'])}{ci_text(cell['ci_dam'])} (bar +0.05) "
            f"{yes_no(cell['passed'])}. Kill rule (RAIN within 0.02): "
            + ("**TRIGGERED**: drop the finance claim." if cell["kill_rule_triggered"] else "not triggered."))
    if curve is not None:
        lines.append("- **Runway curve (below a third within 30 / 60 / 90 / 180 days), skill vs each horizon's simple "
                     "rule:** " + " / ".join(number(curve["bss_B0_by_horizon"].get(h)) for h in HORIZONS) + ".")
    worst = floor_all.get("worst_year")
    lines.append(f"- **DamDays floor (\"at least N days, 9 times in 10\"):** held for {number(floor_all['coverage'], 3, False)} "
                 f"of {floor_all['rows_judged']:,} judged forecasts (target 0.90; on target means 0.88 to 0.92: "
                 f"{'yes' if floor_all['on_target'] else 'NO'}); median floor {floor_all['median_floor_days']:.0f} days."
                 + (f" Worst July-June year: {worst['year']}, {worst['coverage']:.3f}." if worst else ""))
    single = {k: b["single_block_2009_2016"] for k, b in r["band"].items()}
    only_drier = all(not b["wetter_than_band"] for b in single.values())
    lines.append("- **Season band (how far a very wet or very dry year moves a forecast):** the shipped (pooled) band "
                 "covered " + ", ".join(f"{b['covered']} of {b['region_years']} region-years for {k}"
                                        for k, b in pooled.items())
                 + "; the single-block band PREREG reports alongside covered "
                 + ", ".join(f"{b['covered']} of {b['region_years']}" for b in single.values())
                 + (" (every miss is a year drier than that band allows)." if only_drier else " (see the band section)."))
    return lines + [""]


def header(r):
    """Title, what this page is, and why it is not the clean test."""
    return [
        "# Development TEST results: the frozen model's one look at 2016-2026", "",
        f"Generated by `scripts/15_score_test.py`; scored {r['scored_at']} (AEST). Page written {r['page_written_at']}.",
        "",
        "> **What this is.** The frozen DamDays model (Tidemark rung **L3**, event build config hash "
        f"**{FROZEN['config_hash']}**, [{FROZEN['addendum']}]({FROZEN['addendum']})) and the benchmark G2, judged "
        "**once** on the development test years: every forecast issued 1 July 2016 to 30 June 2026 in the two "
        "development regions (NSW Central West; western Victoria / SE South Australia), and every 1 July season "
        "rating from 2016 to 2025. The models learned only from answers known before 1 July 2016; the forecasts are "
        "the ones `scripts/13_fit_test_setting.py` saved before this step (fingerprints checked). Every number is "
        "reported, pass or fail.",
        "",
        "> **Not the clean test.** This block was scored before the event by about ten research configurations, "
        "and Tidemark's design was informed by those results; two PREREG choices (the pooled season band, dropping "
        "the regional P2 block) were made after seeing it (PREREG \"Pre-event research status\" and \"Model\"). So "
        "these numbers are post-selection and somewhat optimistic (PREREG: by roughly 0.005-0.01 in skill), and the "
        "band coverage here is not an independent check of the pooled band. The rehearsal of the opening also looked "
        "at western Victoria's test years with other models (Addendum 1, 6.16). **The clean test is the sealed "
        "region**, opened once on Sat 3 Oct 2026 17:30 AEST.",
        "",
        "How to read the numbers: [docs/SCORECARD.md](docs/SCORECARD.md). Skill (BSS) = the share of a simple rule's "
        "squared error the forecast removes (B0: this region in this month; B2: this dam's own track record). "
        "Brackets: 95% range from resampling dams; `ry`: from resampling region-years (only "
        f"{r['scores'][('P1_R30', PRIMARY, 'tidemark')]['rows']['region_years']} on the R30 primary set, so rough).",
        ""]


def verdict_lines(r):
    v, lines = r["verdicts"], ["## PREREG pass bars and the kill rule", "",
                               "| bar | model | value | required | result |", "|---|---|---|---|---|"]
    for who, bars in (("Tidemark", v["p1_pass_bars_tidemark"]), ("G2", v["p1_pass_bars_g2"])):
        lines += [f"| P1 R30 BSS vs B0 (primary) | {who} | {number(bars['bss_B0']['value'], 4)} (dam CI low "
                  f"{number(bars['bss_B0']['ci_low'], 4)}) | >= +0.10, CI above 0 | {yes_no(bars['bss_B0']['passed'])} |",
                  f"| P1 R30 BSS vs B2 (primary) | {who} | {number(bars['bss_B2']['value'], 4)} | >= +0.05 "
                  f"| {yes_no(bars['bss_B2']['passed'])} |",
                  f"| P1 R30 calibration slope (primary) | {who} | {number(bars['cal_slope']['value'], 3, False)} "
                  f"| 0.8 to 1.2 | {yes_no(bars['cal_slope']['passed'])} |"]
    for task, subset, _ in P2_TASKS:
        p2 = v.get(f"p2_{task.replace('P2_', '')}")
        if p2 is None:
            continue
        lines += [f"| {task}: AUC gain over RAIN | Tidemark | {number(p2['d_auc_vs_RAIN'], 4)}{ci_text(p2['ci_dam'], 4)} "
                  f"| >= +0.05, CI above 0 | {yes_no(p2['passed'])} |",
                  f"| {task}: kill rule (RAIN within 0.02 AUC) | Tidemark | {number(p2['d_auc_vs_RAIN'], 4)} | gain >= +0.02 "
                  f"| {'**TRIGGERED**' if p2['kill_rule_triggered'] else 'not triggered'} |"]
    return lines + ["", "PREREG defines the P2 bar and kill rule on the season rating; the cell rating is the "
                        "headline, the dam and gradual-dam ratings are reported alongside.", ""]


def comparison_lines(r):
    lines = ["## Against the pre-event numbers on this block (post-selection) and the validation years", "",
             "The pre-event research scored this same block before the event, and its numbers are post-selection (see "
             "the note at the top), so they are expected to be slightly optimistic (PREREG: by roughly 0.005-0.01 in "
             "skill). VAL = the frozen recipe on 2009-2015 (`artifacts/val_tidemark_best.md`), for context.", "",
             "| quantity | pre-event TEST (post-selection) | this run, TEST [dam 95% CI] | difference | VAL 2009-2015 | "
             "pre-event source |", "|---|---|---|---|---|---|"]
    for c in r["comparison"]:
        days = "days" in c["quantity"]
        digits, sign = (1, False) if days else (3, any(word in c["quantity"] for word in ("BSS", "gain", "minus")))
        lines.append(f"| {c['quantity']} | {number(c['pre_event_test'], digits, sign)} "
                     f"| {number(c['event_test'], digits + (0 if days else 1), sign)}{ci_text(c['ci_dam'], 3, sign)} "
                     f"| {number(c['difference'], digits + (0 if days else 1))} "
                     f"| {number(c['val_2009_2015'], digits, sign)} | {c['source']} |")
    return lines + [""]


SUBSET_LABELS = {PRIMARY: "primary (dam-like, Oct-Mar, at risk)", "persistent+octmar+at_risk": "persistent (Oct-Mar, at risk)",
                 "dam_like+at_risk": "dam-like, all months (at risk)"}


def p1_lines(r):
    s = r["scores"]
    lines = ["## P1, the farmer runway: G2 and Tidemark (90-day forecasts)", "",
             "`sens` = the PREREG label-determinable sensitivity row (every forecast whose 90 days have passed, "
             "without the 3-look rule). Tidemark minus G2 is paired (same rows, same resamples), in BSS-vs-B0 units.", "",
             "| kind | subset | rows | events | base rate | G2: BSS vs B0 [dam] | Tidemark: BSS vs B0 [dam] ry [region-year] "
             "| Tidemark minus G2 [dam] ry [region-year] | Tidemark: BSS vs B2 | Tidemark AUC (G2) | cal. slope | CITL "
             "| prec. at 50% recall |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for task in [f"P1_{k}" for k in KINDS] + [f"P1_{k}_sens" for k in KINDS]:
        for subset, label in SUBSET_LABELS.items():
            tm, g2 = s.get((task, subset, "tidemark")), s.get((task, subset, "G2"))
            if tm is None or g2 is None:
                continue
            p = tm["point"]
            lines.append(
                f"| {task.replace('P1_', '').replace('_sens', ' sens')} | {label} | {tm['rows']['scored']:,} "
                f"| {tm['rows']['events']:,} | {number(p['base_rate'], 3, False)} "
                f"| {number(g2['point']['bss_B0'])}{ci_text(g2['ci_dam'].get('bss_B0'))} "
                f"| {with_intervals(tm, 'bss_B0')} | {with_intervals(tm, 'd_bss_B0_vs_G2', 4)} "
                f"| {number(p['bss_B2'])}{ci_text(tm['ci_dam'].get('bss_B2'))} "
                f"| {number(p['auc'], 3, False)} ({number(g2['point']['auc'], 3, False)}) "
                f"| {number(p['cal_slope'], 2, False)} | {number(p['citl'], 2)} | {number(p['prec_at_50_recall'], 3, False)} |")
    return lines + [""]


def curve_lines(r):
    lines = ["## Runway curve (Tidemark), each horizon against its own simple rule", "",
             "| curve | subset | days | rows | events | BSS vs B0_h [dam] | BSS vs B2_h | AUC | cal. slope | CITL |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for (task, subset), result in r["curves"].items():
        for h in result["horizons"]:
            p, ci = h["point"], h["ci_dam"]
            lines.append(f"| {task} | {SUBSET_LABELS.get(subset, subset)} | {h['horizon']} | {h['rows']:,} | {h['events']:,} "
                         f"| {number(p.get('bss_B0'))}{ci_text(ci.get('bss_B0'))} | {number(p.get('bss_B2'))} "
                         f"| {number(p.get('auc'), 3, False)} | {number(p.get('cal_slope'), 2, False)} "
                         f"| {number(p.get('citl'), 2)} |")
    falls = ", ".join(f"{task} {SUBSET_LABELS.get(subset, subset)}: {res['monotonicity']['rows_falling']:,} of "
                      f"{res['monotonicity']['rows']:,}" for (task, subset), res in r["curves"].items() if subset == PRIMARY)
    return lines + ["", f"Curves that fall as the horizon grows (expected 0): {falls}. R30 curve below the D0 curve "
                        f"(any horizon, every R30 forecast; expected 0): {r['curve_crossing_share']:.4f}.", ""]


def floor_lines(r):
    lines = ["## DamDays floor (\"at least N days above a third, 9 times in 10\")", "",
             "A floor of N days is judged only if the archive (to 14 Sep 2026, less 30 days to confirm) watched the "
             "dam for at least N days after the forecast, whatever happened.", "",
             "| forecasts | judged | not judged (too recent) | share that held [dam 95% CI] | on target (0.88-0.92) "
             "| median floor (days) | worst July-June year |", "|---|---|---|---|---|---|---|"]
    for label, key in (("as issued, all labelled", "issued_all"), ("as issued, primary set", "issued_primary"),
                       ("as shown in the app (180+ cap), all", "shown_all")):
        f = r["floor"][key]
        worst = f.get("worst_year")
        worst_text = "{}: {:.3f}".format(worst["year"], worst["coverage"]) if worst else "-"
        lines.append(f"| {label} | {f['rows_judged']:,} | {f['rows'] - f['rows_judged']:,} "
                     f"| {number(f['coverage'], 4, False)}{ci_text(f.get('ci_dam', {}).get('coverage'), 4, False)} "
                     f"| {'yes' if f['on_target'] else 'NO'} | {number(f['median_floor_days'], 1, False)} "
                     f"| {worst_text} |")
    by_year = r["floor"]["issued_all"].get("by_year", {})
    if by_year:
        lines += ["", "By July-June year (all labelled): " + ", ".join(
            f"{y} {v['coverage']:.3f} ({v['rows']:,})" for y, v in sorted(by_year.items(), key=lambda kv: int(kv[0])))
            + "."]
    return lines + [""]


def band_lines(r):
    lines = ["## Season band", "",
             "A region-year (one region, one July-June year) is covered when its offset (how far that year's primary-set "
             "forecasts were off on average, in log-odds; positive = drier than forecast) lies inside the band. The shipped "
             "band pools two inner backtests (2002-2009 and 2009-2016); PREREG also reports the 2009-2016 block alone.", "",
             "| kind | shipped (pooled) band | covered | outside it | single-block band (2009-2016) | covered | outside it |",
             "|---|---|---|---|---|---|---|"]

    def outside(coverage):
        """The region-years outside a band, with their offsets."""
        return ", ".join([f"{ry} ({o:+.2f}, drier)" for ry, o in coverage["drier_than_band"].items()]
                         + [f"{ry} ({o:+.2f}, wetter)" for ry, o in coverage["wetter_than_band"].items()]) or "-"
    for kind, b in r["band"].items():
        pooled, single = b["pooled"], b["single_block_2009_2016"]
        lines.append(f"| {kind} | [{number(pooled['band'][0], 2)}, {number(pooled['band'][1], 2)}] "
                     f"| {pooled['covered']}/{pooled['region_years']} | {outside(pooled)} "
                     f"| [{number(single['band'][0], 2)}, {number(single['band'][1], 2)}] "
                     f"| {single['covered']}/{single['region_years']} | {outside(single)} |")
    lines += ["", "Every TEST region-year's offset (rows, events):", "",
              "| region-year | " + " | ".join(r["band"]) + " |", "|---|" + "---|" * len(r["band"])]
    years = sorted({o["region_year"] for b in r["band"].values() for o in b["offsets"]})
    for ry in years:
        cells = []
        for kind, b in r["band"].items():
            o = next((x for x in b["offsets"] if x["region_year"] == ry), None)
            cells.append("-" if o is None else (f"{o['offset']:+.2f} ({o['rows']:,}, {o['events']:,})" if o["used"]
                                                else f"not used ({o['rows']:,}, {o['events']:,})"))
        lines.append(f"| {ry} | " + " | ".join(cells) + " |")
    return lines + [""]


def p2_lines(r):
    s = r["scores"]
    lines = ["## P2, the season rating (issued 1 July 2016 to 2025; dry in the following Oct-Mar)", "",
             "| rating | rated | ran dry | Tidemark AUC [dam] ry [region-year] | gain over RAIN [dam] ry | gain over RAIN+ [dam] "
             "| gain over B2 [dam] | AUC: RAIN / RAIN+ / B2 | within-season AUC: Tidemark / RAIN | cal. slope | CITL |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for task, subset, _ in P2_TASKS:
        tm = s.get((task, subset, "tidemark"))
        if tm is None:
            continue
        base = {m: s.get((task, subset, m)) for m in P2_BASELINE_MODELS}
        aucs = " / ".join(number(b["point"]["auc"], 3, False) if b else "-" for b in base.values())
        lines.append(f"| {task} | {tm['rows']['scored']:,} | {tm['rows']['events']:,} | {with_intervals(tm, 'auc', sign=False)} "
                     f"| {with_intervals(tm, 'd_auc_vs_RAIN')} "
                     f"| {number(tm['point']['d_auc_vs_RAIN+'])}{ci_text(tm['ci_dam'].get('d_auc_vs_RAIN+'))} "
                     f"| {number(tm['point']['d_auc_vs_B2'])}{ci_text(tm['ci_dam'].get('d_auc_vs_B2'))} | {aucs} "
                     f"| {number(tm['point'].get('auc_within_season'), 3, False)} / "
                     f"{number(base['RAIN']['point'].get('auc_within_season'), 3, False) if base['RAIN'] else '-'} "
                     f"| {number(tm['point']['cal_slope'], 2, False)} | {number(tm['point']['citl'], 2)} |")
    return lines + [""]


def ledger_lines(r):
    led = r["ledger"]
    lines = ["## The TEST ledger", "",
             f"This run wrote {led['rows_written']} rows to [`artifacts/test_ledger.csv`](artifacts/test_ledger.csv) "
             f"(statuses: {', '.join(f'{k} {v}' for k, v in led['statuses'].items())}). One \"new\" row per model and task "
             f"({led['first_looks']} in all); every other row is a further subset of the same forecasts "
             "(\"same_predictions\"). A re-run of this script would add only \"same_predictions\" rows; "
             "`scripts/15_score_test.py --check` shows what each call would record, without writing to the ledger.", ""]
    if r.get("not_scored"):
        lines += ["Subsets that could not be scored (they need both events and non-events):", ""]
        lines += [f"- {n['task']} {n['subset']} {n['model']}: {n['rows']:,} labelled rows, {n['events']:,} events"
                  for n in r["not_scored"]]
        lines.append("")
    return lines


def run_lines(r):
    i = r["inputs"]
    return ["## What was run, and the checks before scoring", "",
            f"- **Frozen models**: `{i['models']['tidemark']['path']}` SHA-256 {i['models']['tidemark']['sha256'][:16]}..., "
            f"`{i['models']['g2']['path']}` {i['models']['g2']['sha256'][:16]}...; both equal the committed "
            "`artifacts/sealed_models_manifest.json` (Addendum 1, section 5).",
            f"- **Forecasts**: {i['forecast_files']} files saved by step 13 (`data_cache/preds/TEST/`), each matching the "
            f"fingerprint step 13 recorded in `artifacts/test_setting_fit_summary.json` (step 13 finished "
            f"{i['step13_generated']}; nothing was scored there). Season band constants: as recorded by step 13 and quoted "
            "in Addendum 1, section 4.",
            "- **Answers**: the P1 and P2 feature tables and the archive end date, the same files step 13 forecast "
            "from (fingerprints checked).",
            f"- **Scoring**: the shared scorecard (`damdays.evaluation`), {N_BOOT_MAIN} dam and {N_BOOT_MAIN} region-year "
            f"draws on primary sets, the floor and P2; {N_BOOT_SIDE} on other subsets (as on VAL and for the sealed region). "
            "One JSON per score: `artifacts/scorecard/step15_test/dev_TEST/`.",
            f"- **Code**: git {r['git']['commit'][:12]} (uncommitted changes: {r['git']['uncommitted_changes']}; this "
            "script is new in this step). Run time " + f"{r['minutes']:.1f} minutes.",
            "- **Not part of TEST**: grouped-dam CV and leave-one-region-out are VAL-only checks (PREREG \"Splits\").", ""]


def markdown(r):
    return "\n".join(header(r) + plain_words(r) + verdict_lines(r) + comparison_lines(r) + p1_lines(r) + curve_lines(r)
                     + floor_lines(r) + band_lines(r) + p2_lines(r) + ledger_lines(r) + run_lines(r)) + "\n"


def write_page(r):
    """artifacts/test_results.md (people) and artifacts/test_results.json (every number; scores keyed "task | subset | model").

    The verdicts and the comparison are read off the saved scores here, so --report-only rebuilds them too.
    """
    r = dict(r, verdicts=verdicts(r["scores"]), comparison=comparison(r["scores"], r["floor"]),
             page_written_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
    RESULTS_MD.write_text(markdown(r), encoding="utf-8")
    plain = dict(r, scores={" | ".join(k): v for k, v in r["scores"].items()},
                 curves={" | ".join(k): v for k, v in r["curves"].items()})
    RESULTS_JSON.write_text(json.dumps(clean_for_json(plain), indent=1, default=str), encoding="utf-8")
    say(f"wrote {RESULTS_MD.relative_to(config.REPO_DIR).as_posix()} and {RESULTS_JSON.relative_to(config.REPO_DIR).as_posix()}")


# ===========================================================================
# Main
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="build and check every table as a dry run on a scratch copy of the ledger; score nothing")
    parser.add_argument("--report-only", action="store_true",
                        help="rewrite the results page from the saved results (no scoring, no ledger row)")
    args = parser.parse_args()

    if args.report_only:
        with open(SAVED_RESULTS, "rb") as handle:
            write_page(pickle.load(handle))
        return

    mode = "CHECK (dry run on a scratch copy of the ledger; nothing is scored)" if args.check else "THE ONE LOOK"
    say(f"step 15: score the development TEST block, {mode}")
    summary = json.loads(FIT_SUMMARY.read_text(encoding="utf-8"))
    if summary["rung"] != FROZEN["rung"] or summary["block"] != BLOCK:
        raise AssertionError(f"Step 13's summary is for rung {summary['rung']}, block {summary['block']}.")
    models = check_frozen_models()
    saved = load_forecasts(summary)
    answers = load_answers(summary)

    scoring = Scoring(check=args.check)
    ledger_before = len(Ledger().entries())
    scored_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    say("P1: G2, then Tidemark with G2 as its paired reference")
    score_p1(scoring, answers, saved)
    say("runway curve")
    crossing = score_curves(scoring, answers, saved)
    say("P2 season rating: RAIN, RAIN+, B2, then Tidemark")
    score_p2(scoring, answers, saved)

    if args.check:
        say(f"CHECK passed: {len(scoring.planned)} scoring calls built and checked; the real ledger would record:")
        for plan in scoring.planned:
            say(f"    {plan['task']:12s} {plan['subset']:27s} {plan['model']:9s} {plan['would_be']}")
        shutil.rmtree(scoring.scratch, ignore_errors=True)
        return

    say("season band and DamDays floor (on the same Tidemark forecasts)")
    band_result = band(answers, saved, summary["tidemark"]["season_band"]["constants"])
    floor_result = floor(answers, saved)
    written = Ledger().entries().iloc[ledger_before:]
    statuses = Counter(written["status"])
    results = dict(
        scored_at=scored_at, frozen=FROZEN, block=BLOCK, arena=ARENA, git=git_state(),
        minutes=round((time.time() - STARTED) / 60, 1),
        inputs=dict(models=models, forecast_files=len(saved), step13_generated=summary["generated"],
                    band_constants=summary["tidemark"]["season_band"]["constants"]),
        scores=scoring.results, curves=scoring.curves, curve_crossing_share=crossing, band=band_result,
        floor=floor_result, not_scored=scoring.not_scored,
        ledger=dict(rows_written=len(written), statuses=dict(statuses), first_looks=int(statuses.get("new", 0)),
                    rows=written.to_dict(orient="records")))
    SAVED_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(SAVED_RESULTS, "wb") as handle:
        pickle.dump(results, handle)
    say(f"all results saved to {SAVED_RESULTS.relative_to(config.REPO_DIR).as_posix()}; ledger: "
        f"{len(written)} rows written ({dict(statuses)})")
    write_page(results)


if __name__ == "__main__":
    main()
