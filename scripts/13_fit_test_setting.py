"""Step 13: fit every model at the TEST cutoff (2016-07-01) and save its forecasts. NOTHING IS SCORED.

Run from the repo folder (after scripts/01 to 12):
    .venv/Scripts/python.exe scripts/13_fit_test_setting.py            # about 45-75 minutes; resumes from checkpoints
    .venv/Scripts/python.exe scripts/13_fit_test_setting.py --refit    # ignore the checkpoints and fit everything again

Why this step exists
--------------------
PREREG "Sealed region protocol": the models that forecast the sealed region are
fitted on development-region issues before 2016-07-01. The same fitted models
forecast the development TEST block (issues 2016-07-01 to 2026-06-30), which is
scored once, in a later step, through the TEST ledger. This step only FITS and
FORECASTS:
  * no scorecard is called and no TEST answer (label) is scored or saved: the saved
    forecast tables hold keys and probabilities only (checked before saving). TEST-period
    answers enter only where the PREREG makes them causal inputs: a dam's own track record
    (the frailty, B2 and B2_h counts) uses a past forecast once its answer was final on the
    forecast day, exactly as on VAL;
  * nothing is written to the TEST ledger: artifacts/test_ledger.csv is
    fingerprinted before and after, and the summary records that they match;
  * only the development regions are read (data_cache, built by scripts/01-02 and 10);
    the sealed folder is never touched (checked: every P1 row is a development-region row).

What is fitted (each model learns only from answers final before 2016-07-01)
---------------------------------------------------------------------------
1. Tidemark at rung L3 (full Tidemark: the highest rung that passes the PREREG ladder
   rule, artifacts/ladder_val.md), through the same call as on VAL:
       tidemark.fit_tidemark("2016-07-01", "L3")
   It fits, in order:
     T      the tree, one per kind (R30, D0, D0g), on the purged fit rows (TRAIN + VAL issues
            whose 90-day answer + 30 days closed before 2016-07-01), with the 2 water-balance columns
     S, M   the two nets, 3 seeds each, trained afresh at this cutoff (data_cache/nets/2016-07-01/)
     H      the runway-curve hazard model (R30, D0), censored at the cutoff
     floor  the 10% quantile model (answers final before 2009-01-01) plus the split-conformal
            shift from VAL forecasts answered before 2016-07-01
     band   the season band: region-year offsets of TWO inner backtests of this same recipe, pooled (PREREG)
              2002-2009  members fitted at 2002-01-01; offsets from issues 2002-2008 answered before 2009-01-01
              2009-2016  members fitted at 2009-01-01 (the VAL fit); offsets from issues 2009-01 to 2016-06
                         answered before 2016-07-01
            The inner fits reuse the nets saved at those cutoffs (same fingerprint: loaded, not retrained);
            the trees are refitted (deterministic, so identical). Checks below confirm both blocks
            reproduce the VAL run. The single-block band (2009-2016 alone) is recorded too: the
            PREREG reports its sealed coverage alongside the pooled one.
     P2     the season rating, 3 seeds, on seasons answered before 1 July 2016
   Then tidemark.predict_tidemark forecasts every TEST issue (and every TEST season for P2).
2. G2, the PREREG benchmark: G2's LightGBM settings on the 29 G2 features, learned from the
   purged TEST fit rows of all waterbodies. It uses fusion's tree helpers (the same steps as
   g2.fit_and_predict, which do not keep the model) so the fitted model can be saved; on VAL
   this path gave forecasts identical to step 3's G2 (artifacts/ladder_val.md, rung L0).
3. The baselines, each fitted per the PREREG on the purged fit rows of the population it is
   judged with (dam-like; persistent):
     P1      B0, B2 and PERS for R30, D0 and D0g
     curve   B0_h and B2_h at 30, 60, 90 and 180 days for R30 and D0 (horizon-specific references)
     P2      B0, B2, PERS, RAIN and RAIN+ for the dam rating, the gradual dam rating and the 2 km cell
   (The VAL step also fitted "all waterbodies" P1 baselines; no score reads them, so they are not
   fitted here. On the sealed region every baseline is refitted on that region's own history.)

Outputs
-------
  data_cache/models/TEST/tidemark_L3.pkl     the fitted Tidemark model (the sealed opening forecasts with it)
  data_cache/models/TEST/g2.pkl              the fitted G2 trees, one per kind, and their input columns
  data_cache/preds/TEST/<task>/<name>.pkl    the forecasts, float32 (listed in the summary)
  artifacts/test_setting_fit_summary.json    rows, events, run times, fingerprints of models, inputs and forecasts
  data_cache/models/TEST/fit_test_setting.log   the progress log
Checkpoints: each stage saves its results as soon as it finishes and records them in
data_cache/models/TEST/progress.json; a rerun skips finished stages (unless the input
files changed, or --refit is given).

Storage: forecasts are saved as float32 (about 7 significant digits, far finer than any
score), uid and region as categories, to keep the TEST files small (the D: drive is
nearly full). damdays.models.predictions.save_predictions would store float64. The
fingerprints in the summary are of the stored values.
"""
import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch

# Let "import damdays" work when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damdays import config  # noqa: E402
from damdays.data.splits import hydro_year, time_block  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import baselines, fusion, g2, hazard, nets, physics, rows, tidemark  # noqa: E402
from damdays.models import season_rating as sr  # noqa: E402
from damdays.models import uncertainty as unc  # noqa: E402
from damdays.models.predictions import prediction_path  # noqa: E402

BLOCK = "TEST"
CUTOFF = config.TEST_START                       # "2016-07-01": every model learns only from answers final before it
RUNG = "L3"                                      # full Tidemark (artifacts/ladder_val.md: highest passing rung)
KINDS = rows.P1_KINDS                            # R30, D0, D0g
SCORED_POPULATIONS = ("dam_like", "persistent")  # the populations the P1 scorecard judges with
P2_TASKS = (("P2_dam", "dam_like"), ("P2_dam_g", "dam_like"), ("P2_cell", "all"))
INNER_BLOCKS = {"2002-2009": "2002-01-01", "2009-2016": "2009-01-01"}   # band inner block -> its fit cutoff

MODEL_DIR = config.CACHE_DIR / "models" / BLOCK
TIDEMARK_FILE = MODEL_DIR / f"tidemark_{RUNG}.pkl"
G2_FILE = MODEL_DIR / "g2.pkl"
PROGRESS_FILE = MODEL_DIR / "progress.json"
LOG_FILE = MODEL_DIR / "fit_test_setting.log"
SUMMARY_JSON = config.ARTIFACTS_DIR / "test_setting_fit_summary.json"
LEDGER_FILE = config.ARTIFACTS_DIR / "test_ledger.csv"
VAL_LADDER_DIR = config.CACHE_DIR / "preds" / "VAL" / "ladder"   # step 12's VAL run of L3 (for the band checks)
DISK_MARGIN_BYTES = 2 ** 30                      # keep at least 1 GB free after every save

# Every file the fits read (fingerprinted, so a changed input invalidates the checkpoints).
INPUT_FILES = ([store.FEATURES_DIR / f"p1_{group}.pkl" for group in store.P1_GROUPS]
               + [physics.PHYSICS_FILE, store.FEATURES_DIR / "physics_params.pkl", store.FEATURES_DIR / "p2_dam.pkl",
                  store.FEATURES_DIR / "p2_cell.pkl", store.FEATURES_DIR / "dam_rate_prior.pkl",
                  config.CACHE_DIR / "attributes.pkl", config.CACHE_DIR / "panel.pkl",
                  config.CACHE_DIR / "silo_rain.pkl"])

STARTED = time.time()


# ===========================================================================
# Logging, files and fingerprints
# ===========================================================================
def log(message):
    """Print a progress line (minutes since the start) and append it to the log file."""
    line = f"[{(time.time() - STARTED) / 60:5.1f} min] {message}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


class NetProgress(logging.Handler):
    """Sends the nets module's progress messages (training, loading checkpoints) to log()."""

    def emit(self, record):
        log(f"    nets: {record.getMessage()}")


def relative(path):
    """A path relative to the repo, with forward slashes (for the summary)."""
    return Path(path).resolve().relative_to(config.REPO_DIR).as_posix()


def short_hash(data):
    """The first 16 hex characters of the SHA-256 of some bytes."""
    return hashlib.sha256(data).hexdigest()[:16]


def file_fingerprint(path):
    """SHA-256 (16 hex) of a file's bytes, read in 16 MB pieces."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for piece in iter(lambda: handle.read(2 ** 24), b""):
            digest.update(piece)
    return digest.hexdigest()[:16]


def table_fingerprint(frame):
    """16 hex characters that change if any stored value, column or the row order changes."""
    row_hashes = pd.util.hash_pandas_object(frame, index=False).to_numpy()
    return short_hash("|".join(map(str, frame.columns)).encode() + row_hashes.tobytes())


def lgbm_fingerprint(model):
    """A fitted LightGBM's fingerprint: its full text dump (every tree, split and leaf value)."""
    return short_hash(model.booster_.model_to_string().encode())


def net_fingerprint(trained):
    """A trained net's fingerprint: its weights and its input scaling."""
    digest = hashlib.sha256()
    for name, tensor in sorted(trained.net.state_dict().items()):
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().numpy().tobytes())
    for array in (trained.scaler.mean, trained.scaler.spread, trained.scaler.flagged):
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()[:16]


def tidemark_fingerprints(model):
    """{part: fingerprint} for every fitted part of a Tidemark model, and "whole" over all of them."""
    parts = {}
    for kind in KINDS:
        for name, fitted in model.members[kind].items():
            for seed, one in zip(model.registry[name].seeds, fitted):
                if isinstance(one, nets.NetHead):            # one multi-task net serves all three kinds
                    parts[f"{name}_seed{seed}"] = net_fingerprint(one.trained)
                else:
                    parts[f"{name}_{kind}"] = lgbm_fingerprint(one)
    for kind, curve_model in model.curves.items():
        parts[f"H_{kind}"] = lgbm_fingerprint(curve_model)
    parts["floor_q10"] = lgbm_fingerprint(model.floor["model"])
    for seed, tree in zip(sr.SEEDS, model.rating["models"]):
        parts[f"P2_seed{seed}"] = lgbm_fingerprint(tree)
    constants = dict(rung=model.rung.name, cutoff=model.cutoff, band={k: list(v) for k, v in model.band.items()},
                     floor_shift=model.floor["shift"])
    parts["band_and_floor_shift"] = short_hash(json.dumps(constants, sort_keys=True).encode())
    parts["whole"] = short_hash(json.dumps(parts, sort_keys=True).encode())
    return parts


def require_room(n_bytes):
    """Raise unless the data_cache disk keeps DISK_MARGIN_BYTES free after writing n_bytes."""
    free = shutil.disk_usage(config.CACHE_DIR).free
    if free < n_bytes + DISK_MARGIN_BYTES:
        raise OSError(f"Not enough disk space: {free / 2**30:.2f} GB free, need {n_bytes / 2**30:.2f} GB "
                      f"plus a {DISK_MARGIN_BYTES / 2**30:.0f} GB margin.")


def save_object(obj, path, expected_bytes=300 * 2 ** 20):
    """Pickle `obj` to `path` (through a temporary file, so a crash never leaves half a file)."""
    require_room(expected_bytes)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    pd.to_pickle(obj, temporary)
    temporary.replace(path)
    return dict(path=relative(path), bytes=path.stat().st_size)


def lean(frame):
    """A compact copy: floats as float32, row numbers as int32, text columns as categories."""
    out = frame.copy()
    for column in out.columns:
        values = out[column]
        if pd.api.types.is_float_dtype(values):
            out[column] = values.astype(np.float32)
        elif column == "row":
            out[column] = values.astype(np.int32)
        elif values.dtype == object or pd.api.types.is_string_dtype(values):
            out[column] = values.astype("category")
    return out


def assert_no_answers(frame, what):
    """Refuse to save a TEST table that holds an answer (label) column: forecasts only."""
    answers = [c for c in frame.columns if c in ("y", "y_g") or c.startswith(("y_", "lab_"))]
    if answers:
        raise AssertionError(f"{what}: TEST forecast tables must not hold answers, found {answers}.")


def save_forecasts(frame, task, name):
    """Save one forecast table (lean) to data_cache/preds/TEST/<task>/<name>.pkl. Returns its file record."""
    assert_no_answers(frame, f"{task}/{name}")
    if set(time_block(frame["issue_date"])) != {BLOCK}:
        raise AssertionError(f"{task}/{name}: expected TEST issues only.")
    table = lean(frame)
    path = prediction_path(BLOCK, task, name)
    require_room(int(table.memory_usage(deep=True).sum()))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    table.to_pickle(temporary)
    temporary.replace(path)
    return dict(path=relative(path), rows=len(table), columns=len(table.columns), bytes=path.stat().st_size,
                fingerprint=table_fingerprint(table))


# ===========================================================================
# Checkpoints: progress.json records each finished stage
# ===========================================================================
def load_progress(refit):
    """What earlier runs finished ({} with --refit or on the first run)."""
    if refit or not PROGRESS_FILE.exists():
        return {}
    return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))


def save_progress(progress):
    """Write progress.json (through a temporary file)."""
    temporary = PROGRESS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(progress, indent=1, default=str), encoding="utf-8")
    temporary.replace(PROGRESS_FILE)


def already_done(progress, stage, inputs_fingerprint, **must_match):
    """True if an earlier run finished `stage` on the same input files, and its saved files are all there."""
    info = progress.get(stage)
    if info is None or info.get("inputs_fingerprint") != inputs_fingerprint:
        return False
    if not all((config.REPO_DIR / f["path"]).exists() for f in info.get("files", [])):
        return False
    return all(info.get(key) == value for key, value in must_match.items())


def run_stage(progress, stage, inputs_fingerprint, work, **must_match):
    """Run one stage (work() returns its info dict) unless an earlier run finished it; record it in progress.json."""
    if already_done(progress, stage, inputs_fingerprint, **must_match):
        log(f"{stage}: finished in an earlier run (checkpoint), skipped")
        return progress[stage]
    log(f"{stage}: started")
    started = time.time()
    info = work()
    info.update(inputs_fingerprint=inputs_fingerprint, seconds=round(time.time() - started),
                finished=datetime.now().astimezone().isoformat(timespec="seconds"), **must_match)
    progress[stage] = info
    save_progress(progress)
    log(f"{stage}: done in {info['seconds'] / 60:.1f} min")
    return info


# ===========================================================================
# 1. Tidemark L3 at the TEST cutoff
# ===========================================================================
def offsets_frame(model_info, kind):
    """The band's region-year offsets of one kind (both inner blocks), as a table."""
    return pd.DataFrame(model_info["band"]["offsets"][kind])


def band_record(model):
    """The band constants (exact, log-odds): pooled (the PREREG band), and each inner block on its own."""
    record = {"pooled": {kind: list(model.band[kind]) for kind in KINDS}}
    for block in INNER_BLOCKS:
        record[f"{block} alone"] = {}
        for kind in KINDS:
            offsets = offsets_frame(model.info, kind)
            record[f"{block} alone"][kind] = list(unc.pooled_band(offsets[offsets["block"] == block]))
    record["note"] = ("pooled = the PREREG band (TEST and sealed region). '2009-2016 alone' is the single-block band "
                      "whose sealed coverage the PREREG reports alongside.")
    return record


def compare_offsets(got, expected):
    """Largest |difference| between two offset tables over their shared usable region-years."""
    merged = got.merge(expected, on="region_year", suffixes=("", "_expected"))
    merged = merged[merged["used"].astype(bool) & merged["used_expected"].astype(bool)]
    largest = float(np.max(np.abs(merged["offset"] - merged["offset_expected"]))) if len(merged) else None
    return dict(region_years=len(merged), max_abs_difference=largest)


def band_reuse_checks(model, table):
    """Do the band's two inner blocks reproduce the VAL run of the same recipe (scripts/12)?

    2002-2009: the VAL fit of L3 ran the same inner block; its offsets were saved in its fit summary.
    2009-2016: the members are the VAL fit itself. On the region-years fully inside VAL (July-June
               years 2008-2014) its offsets must equal those of step 12's saved VAL forecasts.
    Both read VAL answers only (issues before 2015-07-01).
    """
    summary_path, forecasts_path = VAL_LADDER_DIR / f"{RUNG}_fit_summary.pkl", VAL_LADDER_DIR / f"{RUNG}_p1.pkl"
    if not (summary_path.exists() and forecasts_path.exists()):
        return {"skipped": f"step 12's VAL files for {RUNG} are missing ({relative(VAL_LADDER_DIR)})"}
    val_summary = pd.read_pickle(summary_path)
    val_forecasts = pd.read_pickle(forecasts_path).set_index("row")
    out = {}
    for kind in KINDS:
        got = offsets_frame(model.info, kind)
        early = pd.DataFrame(val_summary["band"]["offsets"][kind])
        check_2002 = compare_offsets(got[got["block"] == "2002-2009"], early[early["block"] == "2002-2009"])
        # 2009-2016 on the July-June years 2008-2014, rebuilt from step 12's saved VAL forecasts.
        mask = unc.band_rows(table, kind, "2009-01-01", "2016-07-01") & (hydro_year(table["issue_date"]) <= 2014)
        part = table.loc[mask]
        p_val = val_forecasts.loc[np.flatnonzero(mask), f"p90_{kind}"].to_numpy(dtype=float)
        rebuilt = unc.block_offsets(part[rows.p1_label(kind)].to_numpy(dtype=float), p_val, part["region"],
                                    part["issue_date"], "2009-2016")
        check_2009 = compare_offsets(got[got["block"] == "2009-2016"], rebuilt)
        out[kind] = {"2002-2009 vs step 12's inner block": check_2002,
                     "2009-2016 (years 2008-2014) vs step 12's VAL forecasts": check_2009}
    checks = [check for per_kind in out.values() for check in per_kind.values()]
    if any(check["region_years"] == 0 for check in checks):
        out["verdict"] = "NOT CHECKED: no shared region-years"
    else:
        worst = max(check["max_abs_difference"] for check in checks)
        out["verdict"] = ("reproduces the VAL run" if worst < 1e-9
                          else f"DIFFERS (largest offset difference {worst:.2e})")
    return out


def net_checkpoints(fit_started):
    """One record per net used by this fit: the TEST members and the band's inner-block nets."""
    roles = {"2002-01-01": "band inner block 2002-2009", "2009-01-01": "band inner block 2009-2016 (the VAL fit)",
             CUTOFF: "TEST member: forecasts TEST and the sealed region"}
    records = []
    for cutoff, role in roles.items():
        for name in nets.MODELS:
            for seed in nets.SEEDS:
                path = nets.checkpoint_path(name, cutoff, seed)
                info = torch.load(path, weights_only=True)["info"]
                records.append(dict(net=name, seed=seed, cutoff=cutoff, role=role, file=relative(path),
                                    trained_in_this_fit=path.stat().st_mtime >= fit_started,
                                    signature=info["signature"], fit_rows=info["rows"],
                                    head_rows=info["head_rows"], head_events=info["head_events"],
                                    n_inputs=info["n_inputs"], train_seconds=info["train_seconds"]))
    return records


def fit_rows_time_check(table):
    """Each kind's last fit issue and when its answer was final: must be before the cutoff (issue + 120 days)."""
    out = {}
    for kind in KINDS:
        fit = rows.p1_fit_rows(table, kind, BLOCK)
        last = pd.Timestamp(table.loc[fit, "issue_date"].max())
        final = last + pd.Timedelta(days=config.ANSWER_FINAL_DAYS)
        out[kind] = dict(last_fit_issue=str(last.date()), its_answer_final=str(final.date()),
                         before_cutoff=bool(final < pd.Timestamp(CUTOFF)))
    if not all(v["before_cutoff"] for v in out.values()):
        raise AssertionError(f"A fit row's answer is final after the cutoff: {out}")
    return out


def stage_tidemark_fit(inputs):
    """fit_tidemark("2016-07-01", "L3"); save the model; check the saved file reloads to the same model."""
    table = inputs["p1"]
    fit_started = time.time()
    model = tidemark.fit_tidemark(CUTOFF, RUNG, inputs=inputs, log=lambda message: log(f"  tidemark: {message}"))
    fingerprints = tidemark_fingerprints(model)
    file_record = save_object(model, TIDEMARK_FILE)
    if tidemark_fingerprints(pd.read_pickle(TIDEMARK_FILE)) != fingerprints:
        raise AssertionError("The saved Tidemark model does not reload to the same fitted model.")
    log(f"  tidemark: model saved to {file_record['path']} ({file_record['bytes'] / 2**20:.1f} MB), "
        f"fingerprint {fingerprints['whole']}")
    checks = band_reuse_checks(model, table)
    log(f"  band inner blocks vs the VAL run: {checks.get('verdict', checks.get('skipped'))}")
    return dict(fit=clean_for_json(tidemark.summary(model)), fit_seconds=round(time.time() - fit_started),
                band_exact=band_record(model), floor_shift_exact=model.floor["shift"],
                band_reuse_checks=clean_for_json(checks), nets=net_checkpoints(fit_started),
                fit_rows_time_check=fit_rows_time_check(table), fingerprints=fingerprints,
                model_fingerprint=fingerprints["whole"], files=[file_record])


# ===========================================================================
# 2. Tidemark's TEST forecasts
# ===========================================================================
def inside_unit_interval(values):
    """True if every value is a number strictly between 0 and 1."""
    values = np.asarray(values, dtype=float)
    return bool(np.isfinite(values).all() and (values > 0).all() and (values < 1).all())


def forecast_checks(out, table):
    """Shape checks on the TEST forecasts. They read no answer (no label, no score). {check: passed}."""
    p1 = out["p1"]
    r30 = p1["at_risk_R30"].to_numpy(dtype=bool)
    on_rows = {"R30": r30, "D0": np.ones(len(p1), dtype=bool), "D0g": np.ones(len(p1), dtype=bool)}
    checks = {
        "p1 has one row per at-risk D0 TEST issue": len(p1) == int(rows.p1_block_rows(table, "D0", BLOCK).sum()),
        "R30 rows = at-risk R30 TEST issues": int(r30.sum()) == int(rows.p1_block_rows(table, "R30", BLOCK).sum()),
        "only TEST issues": set(time_block(p1["issue_date"])) == {BLOCK},
    }
    for kind in KINDS:
        rows_k = on_rows[kind]
        p = p1[f"p90_{kind}"].to_numpy()[rows_k]
        checks[f"p90_{kind} set and inside (0, 1)"] = inside_unit_interval(p)
        for member in tidemark.RUNGS[RUNG].members:
            checks[f"member {member} forecasts every {kind} row"] = inside_unit_interval(
                p1[f"p_{member}_{kind}"].to_numpy()[rows_k])
        checks[f"band_low <= p90 <= band_high ({kind})"] = bool(
            (p1[f"band_low_{kind}"].to_numpy()[rows_k] <= p).all() and (p <= p1[f"band_high_{kind}"].to_numpy()[rows_k]).all())
    checks["R30 headline >= D0 (max rule)"] = bool((p1["p90_R30"].to_numpy()[r30] >= p1["p90_D0"].to_numpy()[r30]).all())
    curves = {kind: p1[[f"curve_{kind}_{h}" for h in tidemark.HORIZONS]].to_numpy()[on_rows[kind]]
              for kind in tidemark.CURVE_KINDS}
    for kind, curve in curves.items():
        checks[f"{kind} curve set and never falls"] = bool(np.isfinite(curve).all() and (np.diff(curve, axis=1) >= 0).all())
    d0_on_r30 = p1[[f"curve_D0_{h}" for h in tidemark.HORIZONS]].to_numpy()[r30]
    checks["R30 curve >= D0 curve"] = bool((curves["R30"] >= d0_on_r30).all())
    floor = p1["floor_days"].to_numpy()[r30]
    checks["floor set, 0 to 365 days"] = bool(np.isfinite(floor).all() and (floor >= 0).all() and (floor <= 365).all())
    for part in ("p2_dam", "p2_cell"):
        checks[f"{part}: p and p_g inside (0, 1), TEST seasons only"] = (
            inside_unit_interval(out[part]["p"]) and inside_unit_interval(out[part]["p_g"])
            and set(time_block(out[part]["issue_date"])) == {BLOCK})
    return checks


def stage_tidemark_forecasts(model, inputs):
    """predict_tidemark on TEST; check the forecasts' shape; save them."""
    out = tidemark.predict_tidemark(model, inputs)
    checks = forecast_checks(out, inputs["p1"])
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AssertionError(f"TEST forecast checks failed: {failed}")
    log(f"  {len(out['p1']):,} P1 forecasts ({int(out['p1']['at_risk_R30'].sum()):,} for R30), "
        f"{len(out['p2_dam']):,} dam seasons, {len(out['p2_cell']):,} cell seasons; all {len(checks)} checks pass")
    files = [save_forecasts(out[part], "tidemark", f"{RUNG}_{part}") for part in ("p1", "p2_dam", "p2_cell")]
    p1 = out["p1"]
    return dict(rows={part: len(frame) for part, frame in out.items()}, rows_R30=int(p1["at_risk_R30"].sum()),
                issues=[str(pd.Timestamp(p1["issue_date"].min()).date()), str(pd.Timestamp(p1["issue_date"].max()).date())],
                seasons=sorted(int(s) for s in out["p2_dam"]["season"].unique()),
                checks=checks, files=files)


# ===========================================================================
# 3. G2, the benchmark
# ===========================================================================
def fit_g2(table, kind):
    """G2 for one kind: fit on the purged TEST fit rows (all waterbodies), forecast every at-risk TEST issue."""
    features = g2.g2_features(kind)
    fit = np.flatnonzero(rows.p1_fit_rows(table, kind, BLOCK, population="all"))
    y = table[rows.p1_label(kind)].to_numpy()[fit].astype(int)
    model = fusion.fit_tree(fusion.tree_inputs(table, fit, features), y, seed=0)     # G2_PARAMS, 3 threads
    scored = np.flatnonzero(rows.p1_block_rows(table, kind, BLOCK))
    forecasts = pd.DataFrame({"row": scored, "uid": table["uid"].astype(str).to_numpy()[scored],
                              "issue_date": table["issue_date"].to_numpy()[scored],
                              "p": fusion.predict_tree(model, table, scored, features)})
    info = dict(fit_rows=len(fit), fit_events=int(y.sum()), predicted_rows=len(scored), n_features=len(features),
                fingerprint=lgbm_fingerprint(model), top_features_by_gain=fusion.gain_shares(model, features))
    return model, features, forecasts, info


def stage_g2(inputs):
    """G2 for R30, D0 and D0g: save the three trees and their TEST forecasts."""
    table = inputs["p1"]
    models, features, info, files = {}, {}, {}, []
    for kind in KINDS:
        started = time.time()
        models[kind], features[kind], forecasts, info[kind] = fit_g2(table, kind)
        info[kind]["seconds"] = round(time.time() - started)
        if not inside_unit_interval(forecasts["p"]):
            raise AssertionError(f"G2 {kind}: a forecast is outside (0, 1).")
        files.append(save_forecasts(forecasts, f"P1_{kind}", "g2"))
        log(f"  G2 {kind}: {info[kind]['fit_rows']:,} fit rows ({info[kind]['fit_events']:,} events), "
            f"{info[kind]['predicted_rows']:,} TEST forecasts, {info[kind]['seconds']} s")
    files.insert(0, save_object(dict(models=models, features=features, cutoff=CUTOFF,
                                     about="G2 (PREREG benchmark) fitted at the TEST cutoff; predict with "
                                           "fusion.predict_tree(models[kind], table, positions, features[kind])"),
                                G2_FILE, expected_bytes=50 * 2 ** 20))
    return dict(models=info, files=files)


# ===========================================================================
# 4-6. Baselines
# ===========================================================================
def stage_p1_baselines(inputs):
    """B0, B2 and PERS for each kind, fitted on the dam-like and on the persistent purged fit rows."""
    table = inputs["p1"]
    info, files = {}, []
    for kind in KINDS:
        for population in SCORED_POPULATIONS:
            base = baselines.p1_baselines(table, kind, BLOCK, population)
            info[f"{kind} {population}"] = dict(base.attrs, predicted_rows=len(base))
            files.append(save_forecasts(base, f"P1_{kind}", f"baselines_{population}"))
            log(f"  P1 {kind} {population}: B0, B2, PERS from {base.attrs['fit_rows']:,} fit rows "
                f"({base.attrs['fit_events']:,} events); {len(base):,} TEST forecasts")
    return dict(baselines=info, files=files)


def data_end():
    """The date of the last satellite look in the archive (saved by the feature build)."""
    return pd.Timestamp(pd.read_pickle(store.FEATURES_DIR / "dam_rate_prior.pkl")["data_end"])


def stage_curve_baselines(inputs):
    """B0_h and B2_h at 30/60/90/180 days for the runway curve (R30, D0), dam-like and persistent.

    TIME: horizon_labels builds every horizon's answer in memory. The baselines read
    them only on purged fit rows (B0_h, the B2_h prior) and, for B2_h's own past counts,
    only once each earlier answer was final on the forecast day (hazard.own_past_counts).
    """
    table = inputs["p1"]
    info, files = {}, []
    for kind in hazard.CURVE_KINDS:
        labels = hazard.horizon_labels(table, kind, data_end())
        for population in SCORED_POPULATIONS:
            base = hazard.curve_baselines(table, kind, BLOCK, labels, population)
            info[f"{kind} {population}"] = dict(base.attrs, predicted_rows=len(base))
            files.append(save_forecasts(base, f"{kind}_curve", f"baselines_{population}"))
            counts = ", ".join(f"{h} d {c['fit_rows']:,}" for h, c in base.attrs["fit_counts"].items())
            log(f"  curve {kind} {population}: B0_h, B2_h (fit rows {counts}); {len(base):,} TEST forecasts")
    return dict(baselines=info, files=files)


def stage_p2_baselines(inputs):
    """B0, B2, PERS, RAIN and RAIN+ for the dam, gradual-dam and cell ratings (as in step 3, at TEST)."""
    dams = inputs["p2_dam"]                                      # step 3's table plus the area index columns
    cells = baselines.add_best_dam_level(inputs["p2_cell"], dams)
    info, files = {}, []
    for task, population in P2_TASKS:
        source, pers = (cells, baselines.CELL_PERS_INPUTS) if task == "P2_cell" else (dams, ["rel"])
        base = baselines.p2_baselines(source, task, BLOCK, population, pers_inputs=pers)
        info[task] = dict(base.attrs, predicted_rows=len(base))
        files.append(save_forecasts(base, task, "baselines"))
        log(f"  {task}: B0, B2, PERS, RAIN, RAIN+ from {base.attrs['fit_rows']:,} fit seasons "
            f"({base.attrs['fit_events']:,} dry); {len(base):,} TEST ratings")
    return dict(baselines=info, files=files)


# ===========================================================================
# The "no scoring" evidence, the inputs, and the summary
# ===========================================================================
def ledger_state():
    """Fingerprint and row count of the TEST ledger, and any TEST scorecard output (there must be none)."""
    exists = LEDGER_FILE.exists()
    test_outputs = sorted(relative(p) for p in (config.ARTIFACTS_DIR / "scorecard").rglob("*") if "TEST" in p.name)
    return dict(ledger=relative(LEDGER_FILE), fingerprint=file_fingerprint(LEDGER_FILE) if exists else None,
                rows=len(pd.read_csv(LEDGER_FILE)) if exists else 0, test_scorecard_outputs=test_outputs)


def input_fingerprints():
    """{file: fingerprint} for every input file, and one fingerprint over all of them."""
    files = {relative(path): file_fingerprint(path) for path in INPUT_FILES}
    return files, short_hash(json.dumps(files, sort_keys=True).encode())


def development_regions_only(table):
    """Every P1 row comes from a development region (the sealed region is never part of these tables)."""
    found = sorted(pd.unique(table["region"].astype(str)))
    if not set(found) <= set(config.DEV_REGIONS):
        raise AssertionError(f"Unexpected regions in the P1 table: {found}")
    return found


def physics_parameters():
    """The water-balance parameters every TEST-period look uses: the 2016 checkpoint (pairs before 2016-01-01)."""
    params = pd.read_pickle(store.FEATURES_DIR / "physics_params.pkl")["params"]
    row = params[params["year"] == config.LAST_CHECKPOINT_YEAR].to_dict("records")[0]
    return {k: (int(v) if isinstance(v, (int, np.integer)) else float(v)) for k, v in row.items()}


def git_state():
    """The repo's commit and whether it has uncommitted changes."""
    def git(*args):
        result = subprocess.run(["git", *args], cwd=config.REPO_DIR, capture_output=True, text=True)
        return result.stdout.strip()
    return dict(commit=git("rev-parse", "HEAD"), uncommitted_changes=bool(git("status", "--porcelain")))


def write_summary(progress, before, after, inputs_files, regions, run_seconds):
    """artifacts/test_setting_fit_summary.json: what was fitted, on what, how long it took, and fingerprints."""
    fit, forecasts = progress["tidemark_fit"], progress["tidemark_forecasts"]
    stages = ("tidemark_fit", "tidemark_forecasts", "g2", "p1_baselines", "curve_baselines", "p2_baselines")
    files = [f for stage in stages for f in progress[stage]["files"]]
    summary = {
        "step": "13: test-setting fits (scripts/13_fit_test_setting.py)",
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "what": ("Every model fitted at the TEST cutoff on the development regions, and its forecasts for every "
                 "TEST issue (2016-07-01 to 2026-06-30). NOT SCORED: no scorecard call, no ledger entry, no TEST "
                 "answer scored or saved. TEST-period answers enter only as causal per-dam inputs (the frailty, "
                 "B2 and B2_h track records count a past forecast once its answer was final), as on VAL."),
        "cutoff": CUTOFF, "block": BLOCK, "rung": RUNG, "git": git_state(),
        "no_scoring_evidence": dict(
            ledger_before=before, ledger_after=after,
            ledger_unchanged=before["fingerprint"] == after["fingerprint"] and before["rows"] == after["rows"],
            test_scorecard_outputs=after["test_scorecard_outputs"],
            forecast_tables_hold_answers=False,
            regions_read=regions, sealed_region_read=False),
        "run_times_minutes": {stage: round(progress[stage]["seconds"] / 60, 1) for stage in stages},
        "total_fit_minutes": round(sum(progress[stage]["seconds"] for stage in stages) / 60, 1),
        "summary_run_minutes": round(run_seconds / 60, 1),    # the run that wrote this file (finished stages are skipped)
        "inputs": dict(files=inputs_files, fingerprint=fit["inputs_fingerprint"],
                       physics_parameters_for_test_looks=physics_parameters()),
        "tidemark": dict(
            call=f'tidemark.fit_tidemark("{CUTOFF}", "{RUNG}") then tidemark.predict_tidemark(model)',
            model_file=relative(TIDEMARK_FILE), model_fingerprint=fit["model_fingerprint"],
            fingerprints=fit["fingerprints"], fit_minutes=round(fit["fit_seconds"] / 60, 1),
            members={kind: fit["fit"]["members"][kind] for kind in KINDS},
            fit_rows_time_check=fit["fit_rows_time_check"], nets=fit["nets"],
            runway_curve={kind: {k: v for k, v in info.items() if k != "features"}
                          for kind, info in fit["fit"]["curves"].items()},
            floor=dict(fit["fit"]["floor"], shift_exact=fit["floor_shift_exact"],
                       note=("A shift of exactly 0 means the 90% conformal quantile of the calibration scores is "
                             "0: it falls on the tied scores of forecasts whose 10% quantile sits at the 365-day "
                             "cap with no event within a year, so the raw 10% quantile already held for about 90% "
                             "of the VAL calibration forecasts." if fit["floor_shift_exact"] == 0 else "")),
            season_band=dict(constants=fit["band_exact"], inner_blocks=fit["fit"]["band"]["blocks"],
                             offsets=fit["fit"]["band"]["offsets"], reuse_checks=fit["band_reuse_checks"]),
            season_rating={k: v for k, v in fit["fit"]["rating"].items() if k not in ("features", "params")},
            forecasts=dict(rows=forecasts["rows"], rows_R30=forecasts["rows_R30"], issues=forecasts["issues"],
                           p2_seasons=forecasts["seasons"], checks=forecasts["checks"])),
        "g2": dict(model_file=relative(G2_FILE), models=progress["g2"]["models"]),
        "baselines": dict(p1=progress["p1_baselines"]["baselines"], runway_curve=progress["curve_baselines"]["baselines"],
                          p2=progress["p2_baselines"]["baselines"],
                          note=("Fitted on the purged fit rows of the population each is judged with. On the sealed "
                                "region every baseline is refitted on that region's own pre-2016-07 history (PREREG).")),
        "files": files,
        "storage": "forecasts float32, uid/region as categories; file fingerprints are of the stored values",
        "how_to_load": {
            "tidemark": f'model = pd.read_pickle("{relative(TIDEMARK_FILE)}"); out = tidemark.predict_tidemark(model, inputs)',
            "g2": (f'g = pd.read_pickle("{relative(G2_FILE)}"); '
                   'p = fusion.predict_tree(g["models"][kind], table, positions, g["features"][kind])'),
            "forecasts": 'pd.read_pickle("data_cache/preds/TEST/<task>/<name>.pkl") (see "files")'},
    }
    out = clean_for_json(summary)                     # rounds floats to 5 decimals, NaN -> null
    out["tidemark"]["season_band"]["constants"] = fit["band_exact"]          # the band and the floor shift
    out["tidemark"]["floor"]["shift_exact"] = fit["floor_shift_exact"]       # at full precision
    SUMMARY_JSON.write_text(json.dumps(out, indent=1, allow_nan=False, default=str), encoding="utf-8")


# ===========================================================================
# Main
# ===========================================================================
def main():
    """Fit every model at the TEST cutoff, forecast TEST, save everything; score nothing."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refit", action="store_true", help="ignore the checkpoints and fit everything again")
    args = parser.parse_args()
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    nets.logger.addHandler(NetProgress())
    nets.logger.setLevel(logging.INFO)
    nets.logger.propagate = False

    log(f"step 13: fits at the TEST cutoff {CUTOFF} (rung {RUNG}, G2, baselines). No scoring.")
    log(f"free disk space: {shutil.disk_usage(config.CACHE_DIR).free / 2**30:.1f} GB")
    before = ledger_state()
    log(f"TEST ledger: {before['rows']} rows, fingerprint {before['fingerprint']} (must be unchanged at the end)")
    inputs_files, inputs_fingerprint = input_fingerprints()
    log(f"input files fingerprinted ({len(inputs_files)} files): {inputs_fingerprint}")
    progress = load_progress(args.refit)

    log("loading the inputs (P1 table with the water-balance columns, P2 tables)")
    inputs = tidemark.load_inputs()
    regions = development_regions_only(inputs["p1"])
    log(f"P1 table: {len(inputs['p1']):,} rows, regions {regions}")

    fit = run_stage(progress, "tidemark_fit", inputs_fingerprint, lambda: stage_tidemark_fit(inputs))
    model = pd.read_pickle(TIDEMARK_FILE)
    if tidemark_fingerprints(model)["whole"] != fit["model_fingerprint"]:
        raise AssertionError("The Tidemark model file differs from the one this run recorded.")
    run_stage(progress, "tidemark_forecasts", inputs_fingerprint, lambda: stage_tidemark_forecasts(model, inputs),
              model_fingerprint=fit["model_fingerprint"])
    run_stage(progress, "g2", inputs_fingerprint, lambda: stage_g2(inputs))
    run_stage(progress, "p1_baselines", inputs_fingerprint, lambda: stage_p1_baselines(inputs))
    run_stage(progress, "curve_baselines", inputs_fingerprint, lambda: stage_curve_baselines(inputs))
    run_stage(progress, "p2_baselines", inputs_fingerprint, lambda: stage_p2_baselines(inputs))

    after = ledger_state()
    if after["fingerprint"] != before["fingerprint"] or after["test_scorecard_outputs"]:
        raise AssertionError("The TEST ledger changed or a TEST score was written during this step.")
    write_summary(progress, before, after, inputs_files, regions, time.time() - STARTED)
    log(f"wrote {relative(SUMMARY_JSON)}; TEST ledger unchanged ({after['rows']} rows); "
        f"free disk space {shutil.disk_usage(config.CACHE_DIR).free / 2**30:.1f} GB")


if __name__ == "__main__":
    main()
