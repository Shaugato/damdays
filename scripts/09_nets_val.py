"""Step 9: Tidemark rung L2 (the tree T + the nets S and M) on VAL.

Run from the repo folder (after scripts/03, 06 and 08: it uses their saved baselines, G2 and L1
forecasts as references):
    .venv/Scripts/python.exe scripts/09_nets_val.py            # full run, about 30-40 minutes
    .venv/Scripts/python.exe scripts/09_nets_val.py --quick    # no bootstrap intervals
    .venv/Scripts/python.exe scripts/09_nets_val.py --reuse    # rescore the saved L2 forecasts, no refits

What it does
  1. The 12 nets L2 needs in the VAL setting: S and M x seeds 0, 1, 2, at the VAL cutoff
     (2009-01-01) and at the season band's inner cutoff (2002-01-01). Each is trained, or
     loaded from data_cache/nets/ when a checkpoint with the same fingerprint exists
     (damdays/models/nets.py). Training progress is logged.
  2. Fits Tidemark L2 through its one entry point, tidemark.fit_tidemark("2009-01-01", rung="L2"),
     and forecasts VAL with tidemark.predict_tidemark. Forecasts are saved to
     data_cache/preds/VAL/tidemark/L2_*.pkl (crash-safe: --reuse rescores them).
  3. Scores L2 (R30, D0, D0g; primary set, persistent dams, all months; the PREREG
     label-determinable sensitivity row), paired against the benchmark G2 and against L1
     (the gain from adding the nets).
  4. Scores each net on its own (each seed and the 3-seed average) and the S + M pair, primary set.
  5. Season-band coverage of L2's own band. Checks that the parts that do not use the 90-day
     members (runway curve, DamDays floor, season rating) equal L1's bit for bit, and scores the
     season rating as step 8 does (scripts/11_export_app.py --rung L2 reads it from the JSON).
  6. Expected (pre-event research) vs got: artifacts/val_tidemark_L2.md (people) and .json (code).

TEST is never touched: every model learns from answers final before 2009-01-01 (or before
2002-01-01 for the band's inner backtest), and every scored table holds VAL forecasts only.
"""
import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Let "import damdays" work when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damdays import config  # noqa: E402
from damdays.data.splits import time_block  # noqa: E402
from damdays.evaluation import band_coverage, score  # noqa: E402
from damdays.evaluation.inputs import join_baselines, tidy_keys  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.evaluation.rules import is_octmar  # noqa: E402
from damdays.models import fusion, nets, rows, tidemark  # noqa: E402
from damdays.models import uncertainty as unc  # noqa: E402
from damdays.models.predictions import load_predictions, prediction_path, save_predictions  # noqa: E402

BLOCK, RUNG = "VAL", "L2"
PRED_TASK = "tidemark"                     # forecasts: data_cache/preds/VAL/tidemark/L2_<part>.pkl
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step09_val"
RESULTS_MD = config.ARTIFACTS_DIR / "val_tidemark_L2.md"
RESULTS_JSON = config.ARTIFACTS_DIR / "val_tidemark_L2.json"
N_BOOT_MAIN, N_BOOT_SIDE = 500, 200        # bootstrap draws: L2 primary sets, other subsets and the pair
NOTE = "step 9 (scripts/09_nets_val.py)"
KINDS = rows.P1_KINDS
NET_CUTOFFS = [config.VAL_START] + [first for first, _ in unc.BAND_INNER_BLOCKS["VAL"]]   # 2009-01-01, 2002-01-01

# P1 subsets: (scorecard subset, population the baselines were fitted on, Oct-Mar issues only?)
P1_SUBSETS = [("primary", "dam_like", True), ("persistent+octmar+at_risk", "persistent", True),
              ("dam_like+at_risk", "dam_like", False)]
# P2 (the season rating), scored as in step 8: (task, subset, rating column), against RAIN, RAIN+ and B2
P2_TASKS = [("P2_cell", "all", "p"), ("P2_dam", "dam_like", "p"), ("P2_dam_g", "dam_like", "p_g")]
P2_REFS = ["RAIN", "RAIN+", "B2"]

# ---------------------------------------------------------------------------
# Check values from the pre-event research (VAL, development regions, primary set unless noted)
# ---------------------------------------------------------------------------
TOL = 0.006                                 # PREREG ladder tolerance
SRC_L3 = "hybrid tables/val_final_scorecard.csv (frozen v1 = L3)"
SRC_PHY = "hybrid tables/val_stageB.csv '-PHY' removal cost"
L3_BSS = {"R30": 0.1818, "D0": 0.1948, "D0g": 0.1947}            # frozen Tidemark v1 (with physics)
PHY_COST = {"R30": 0.0009, "D0": 0.0025, "D0g": 0.0031}          # what dropping the physics cost it
L3_PERSISTENT = {"R30": 0.1538, "D0": 0.1040, "D0g": 0.1227}
PHY_COST_PERSISTENT = {"R30": 0.0007, "D0": 0.0020, "D0g": 0.0028}
L3_GAIN_G2 = {"R30": (0.0111, (0.0075, 0.0147)), "D0": (0.0193, (0.0151, 0.0237)), "D0g": (0.0220, (0.0169, 0.0277))}
NETS_COST = {"R30": (0.0074, (0.0036, 0.0112)), "D0": (0.0099, (0.0054, 0.0151)), "D0g": (0.0135, (0.0073, 0.0204))}
NETS_COST_PERSISTENT = {"R30": (0.0335, (0.0260, 0.0408)), "D0": (0.0234, (0.0145, 0.0328)),
                        "D0g": (0.0306, (0.0201, 0.0421))}
L3_OTHER = {"R30": dict(auc=0.7908, bss_B2=0.1113, cal_slope=1.0718, citl=-0.2763),
            "D0": dict(auc=0.8431, bss_B2=0.1135, cal_slope=1.0697, citl=-0.2951),
            "D0g": dict(auc=0.8694, bss_B2=0.1457, cal_slope=1.1439, citl=-0.2917)}
# One seed of the nets (same seeds as here), primary set, BSS vs B0
PAIR_SEEDS = {"R30": (0.1691, 0.1690, 0.1607), "D0": (0.1888, 0.1861, 0.1763), "D0g": (0.1832, 0.1808, 0.1749)}
SRC_PAIR = "hybrid tables/val_stage0_seeds.csv 'nets_pair'"
NS_SEED0 = {"S": {"R30": 0.163, "D0": 0.184, "D0g": 0.178}, "M": {"R30": 0.158, "D0": 0.177, "D0g": 0.170},
            "S+M": {"R30": 0.169, "D0": 0.189, "D0g": 0.183}}
SRC_NS = "neural-sequence logs/VAL_components.log (seed 0, 1 epoch; 3 decimals)"
# Training (hybrid logs/nets.log, same fit-row rule): rows, epoch loss per seed
TRAIN_ROWS = {"2009-01-01": 875_286, "2002-01-01": 512_562}
TRAIN_LOSS = {("2009-01-01", "S"): (0.3515, 0.3553, 0.3512), ("2009-01-01", "M"): (0.3644, 0.3680, 0.3692),
              ("2002-01-01", "S"): (0.3499, None, None), ("2002-01-01", "M"): (0.3618, None, None)}
HEAD_ROWS = {"R30": (659_554, 192_700), "D0": (875_286, 148_942), "D0g": (815_946, 89_602)}  # = T's fit rows (step 8)
PARAMETERS = {"S": "27.5k", "M": "12.7k"}   # neural-sequence RESULT.md

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


class MinuteFormatter(logging.Formatter):
    """Log lines from damdays.models.nets in the same "[minutes]" style as this script."""

    def format(self, record):
        return f"[{(time.time() - STARTED) / 60:5.1f} min]   nets: {record.getMessage()}"


def show_net_progress():
    """Print the nets' progress messages (training, checkpoints, predictions)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(MinuteFormatter())
    nets.logger.addHandler(handler)
    nets.logger.setLevel(logging.INFO)


# ===========================================================================
# 1. The nets
# ===========================================================================
def train_all_nets(inputs):
    """Train (or load) every net L2 needs for VAL. Returns one info dict per net."""
    infos = []
    for cutoff in NET_CUTOFFS:
        for model in ("M", "S"):
            for seed in nets.SEEDS:
                trained = nets.trained_net(inputs, model, cutoff, seed)
                infos.append({k: trained.info.get(k) for k in (
                    "model", "seed", "cutoff", "rows", "head_rows", "head_events", "n_inputs", "parameters",
                    "epoch_losses", "train_seconds", "replaced_columns", "loaded_from_checkpoint", "torch")})
                log(f"net {model} seed {seed} at {cutoff}: ready (loss {trained.info['epoch_losses']})")
    return infos


# ===========================================================================
# 2. Fit and forecast (or reload)
# ===========================================================================
def saved(part):
    """Path of a saved L2 output part."""
    return prediction_path(BLOCK, PRED_TASK, f"{RUNG}_{part}")


def seed_columns(model, inputs, out):
    """Each net's probability per seed on the block's rows (columns p_<S|M><seed>_<kind>): for the seed spread."""
    table = inputs["p1"]
    for kind in KINDS:
        positions = np.flatnonzero(rows.p1_block_rows(table, kind, BLOCK))
        for name in ("S", "M"):
            for seed, head in enumerate(model.members[kind][name]):
                p = nets.predict_net_member(head, inputs, positions, model.setups[kind])
                out["p1"][f"p_{name}{seed}_{kind}"] = tidemark.place(out["p1"], positions, p)


def room_to_save(out, margin_mb=300):
    """True if the disk holding data_cache has room for the forecasts (float64) plus a safety margin."""
    needed = sum(frame.memory_usage(deep=True).sum() for frame in out.values()) + margin_mb * 2 ** 20
    return shutil.disk_usage(config.CACHE_DIR).free > needed


def save_forecasts(out, summary):
    """Save the L2 forecasts and fit summary (for --reuse). Skipped, with a warning, if the disk is too full.

    A half-written file would be worse than none, so nothing is written unless all of it fits.
    """
    if not room_to_save(out):
        log("WARNING: not enough free disk space for the L2 forecasts; NOT saved (scoring continues from memory, "
            "and --reuse will refit)")
        return False
    for part, frame in out.items():
        save_predictions(frame, BLOCK, PRED_TASK, f"{RUNG}_{part}")
    pd.to_pickle(summary, saved("fit_summary"))
    saved("fit_summary").with_suffix(".json").write_text(json.dumps(clean_for_json(summary), indent=1))
    log(f"forecasts saved to data_cache/preds/{BLOCK}/{PRED_TASK}/")
    return True


def fit_and_forecast(inputs, reuse):
    """tidemark.fit_tidemark + predict_tidemark for rung L2 (or the saved forecasts with --reuse)."""
    parts = ("p1", "p2_dam", "p2_cell")
    if reuse and saved("fit_summary").exists() and all(saved(p).exists() for p in parts):
        log("reloaded the saved L2 forecasts")
        return ({p: load_predictions(BLOCK, PRED_TASK, f"{RUNG}_{p}") for p in parts},
                pd.read_pickle(saved("fit_summary")), True)
    model = tidemark.fit_tidemark(config.VAL_START, RUNG, inputs=inputs, log=log)
    out = tidemark.predict_tidemark(model, inputs)
    seed_columns(model, inputs, out)
    summary = tidemark.summary(model)
    log(f"forecasts made: {len(out['p1']):,} P1 issues")
    return out, summary, save_forecasts(out, summary)


# ===========================================================================
# 3-4. P1 scores
# ===========================================================================
def require(task, name, step):
    """A saved prediction table from an earlier step; stops with a clear message if it is missing."""
    if not prediction_path(BLOCK, task, name).exists():
        raise SystemExit(f"Missing {prediction_path(BLOCK, task, name)}: run {step} first.")
    return load_predictions(BLOCK, task, name)


def on_rows(p1_out, positions, column):
    """A column of a predict_tidemark p1 table, read on the given P1-table rows."""
    return p1_out.set_index("row").loc[np.asarray(positions), column].to_numpy(dtype=float)


def attach(frame, other, columns):
    """Copy `columns` from `other` into `frame`; both must list the same forecasts in the same order."""
    same = (len(frame) == len(other)
            and (frame["uid"].astype(str).to_numpy() == other["uid"].astype(str).to_numpy()).all()
            and (pd.to_datetime(frame["issue_date"]).to_numpy() == pd.to_datetime(other["issue_date"]).to_numpy()).all())
    if not same:
        raise AssertionError("Prediction tables are not row-aligned.")
    for column in columns:
        frame[column] = other[column].to_numpy()
    return frame


def fused(*probabilities):
    """Probability from the plain mean of the log-odds (how fusion combines members)."""
    return np.clip(fusion.sigmoid(np.mean([fusion.logit(p) for p in probabilities], axis=0)), fusion.P_MIN,
                   fusion.P_MAX)


def p1_frame(table, out, l1_out, kind):
    """Every at-risk VAL issue of `kind`: keys, flags, labels, L2 and its parts, L1 and G2 (references)."""
    picked = rows.p1_block_rows(table, kind, BLOCK)
    positions = np.flatnonzero(picked)
    chosen = table.loc[picked]
    raw_label = chosen[rows.p1_label(kind)].to_numpy(dtype=float)
    frame = pd.DataFrame({
        "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
        "region": chosen["region"].astype(str).to_numpy(),
        "dam_like": chosen["dam_like"].to_numpy(dtype=bool), "persistent": chosen["persistent"].to_numpy(dtype=bool),
        "at_risk": True,
        "y": rows.p1_scored_label(chosen, kind),
        "y_sens": np.where(chosen["window_closed"].to_numpy(dtype=bool), raw_label, np.nan)})
    p1 = out["p1"]
    frame["p_L2"] = on_rows(p1, positions, f"p90_{kind}")
    frame["p_L1"] = on_rows(l1_out, positions, f"p90_{kind}")
    if kind == "R30":
        frame["p_L2_premax"] = on_rows(p1, positions, "p90_R30_premax")
        frame["p_L1_premax"] = on_rows(l1_out, positions, "p90_R30_premax")
    for name in ("T", "S", "M"):
        frame[f"p_{name}"] = on_rows(p1, positions, f"p_{name}_{kind}")
    frame["p_anchor"] = on_rows(p1, positions, f"anchor_{kind}")
    frame["p_S+M"] = fused(frame["p_S"], frame["p_M"])
    for seed in nets.SEEDS:
        for name in ("S", "M"):
            frame[f"p_{name}{seed}"] = on_rows(p1, positions, f"p_{name}{seed}_{kind}")
        frame[f"p_S+M{seed}"] = fused(frame[f"p_S{seed}"], frame[f"p_M{seed}"])
    attach(frame, require(f"P1_{kind}", "models", "scripts/03_baselines_and_g2.py"), ["p_G2"])
    return frame


def expected_keys(frame, population, octmar_only, label="y"):
    """The rows a P1 subset must be scored on, worked out here independently of the scorecard."""
    keep = frame[label].notna().to_numpy() & frame[population].to_numpy(dtype=bool)
    if octmar_only:
        keep = keep & is_octmar(frame["issue_date"])
    return frame.loc[keep, ["uid", "issue_date"]]


COMPONENTS = ["T", "S", "M", "S+M", "anchor"] + [f"{n}{s}" for s in nets.SEEDS for n in ("S", "M", "S+M")]


def score_p1(table, out, l1_out, kind, n_boot_main, n_boot_side):
    """L2 on every subset and the sensitivity row, plus each component on the primary set."""
    task = f"P1_{kind}"
    frame = p1_frame(table, out, l1_out, kind)
    base = {pop: require(task, f"baselines_{pop}", "scripts/03_baselines_and_g2.py") for pop in ("dam_like", "persistent")}
    results = {}
    for subset, population, octmar_only in P1_SUBSETS:
        scored = attach(frame.copy(), base[population], ["p_B0", "p_B2"])
        if set(time_block(scored["issue_date"])) != {BLOCK}:
            raise AssertionError("Only VAL forecasts may be scored here.")
        keys = expected_keys(frame, population, octmar_only)
        n_boot = n_boot_main if subset == "primary" else n_boot_side
        results[(task, subset, "L2")] = score(scored.assign(p=scored["p_L2"]), task, subset, model="tidemark_L2",
                                              refs=["G2", "L1"], expected_keys=keys, n_boot=n_boot,
                                              out_dir=SCORE_DIR, note=NOTE)
        if kind == "R30" and subset != "dam_like+at_risk":
            results[(task, subset, "L2_premax")] = score(
                scored.assign(p=scored["p_L2_premax"]), task, subset, model="tidemark_L2_premax",
                refs=["G2", "L1_premax"], expected_keys=keys, n_boot=n_boot_side, out_dir=SCORE_DIR, note=NOTE)
        if subset == "primary":
            for name in COMPONENTS:
                boot = n_boot_side if name == "S+M" else 0
                results[(task, subset, name)] = score(
                    scored.assign(p=scored[f"p_{name}"]), task, subset, model=f"tidemark_L2_part_{name}",
                    refs=["G2"], expected_keys=keys, n_boot=boot, out_dir=SCORE_DIR, note=NOTE, write=boot > 0)
    sens = attach(frame.copy(), base["dam_like"], ["p_B0", "p_B2"]).assign(y=frame["y_sens"], p=frame["p_L2"])
    results[(f"{task}_sens", "primary", "L2")] = score(
        sens, f"{task}_sens", "primary", model="tidemark_L2", refs=["G2", "L1"],
        expected_keys=expected_keys(frame, "dam_like", True, "y_sens"), n_boot=n_boot_side, out_dir=SCORE_DIR,
        note=NOTE)
    log(f"{task}: L2 scored on {len(P1_SUBSETS)} subsets, the sensitivity row and {len(COMPONENTS)} components")
    return results


def score_p2(out, n_boot):
    """The season rating of rung L2, scored as step 8 scores L1's. Returns {(task, subset, "L2"): result}.

    The nets do not touch the rating, so these equal L1's (same_as_l1 checks the ratings bit for bit).
    They are scored here so that val_tidemark_L2.json holds every rung-L2 number the app reads
    (scripts/11_export_app.py --rung L2 reads p2 'P2_cell|all|L2').
    """
    results = {}
    for task, subset, column in P2_TASKS:
        source = out["p2_cell"] if task == "P2_cell" else out["p2_dam"]
        frame = tidy_keys(pd.DataFrame({"uid": source["uid"].to_numpy(), "issue_date": source["issue_date"].to_numpy(),
                                        "region": source["region"].to_numpy(), "p": source[column].to_numpy()}))
        frame = join_baselines(frame, require(task, "baselines", "scripts/03_baselines_and_g2.py"))
        if set(time_block(frame["issue_date"])) != {BLOCK}:
            raise AssertionError("Only VAL season ratings may be scored here.")
        keep = frame["y"].notna().to_numpy()
        if subset == "dam_like":
            keep = keep & frame["dam_like"].to_numpy(dtype=bool)
        results[(task, subset, RUNG)] = score(frame, task, subset, model="tidemark_L2", refs=P2_REFS,
                                              expected_keys=frame.loc[keep, ["uid", "issue_date"]], n_boot=n_boot,
                                              out_dir=SCORE_DIR, note=NOTE)
    log("P2: " + ", ".join(f"{task} AUC {r['point']['auc']:.4f}" for (task, _, _), r in results.items()))
    return results


# ===========================================================================
# 5. Season band, and the parts that must equal L1's
# ===========================================================================
def band_results(table, out, summary):
    """VAL region-year coverage of L2's band (offsets measured on L2's own VAL forecasts)."""
    res = {}
    for kind in KINDS:
        band = tuple(summary["band"]["band"][kind])
        mask = unc.band_rows(table, kind, config.VAL_START, config.TEST_START) & (time_block(table["issue_date"]) == BLOCK)
        part = table.loc[mask]
        p = on_rows(out["p1"], np.flatnonzero(mask), f"p90_{kind}")
        offsets = unc.block_offsets(part[rows.p1_label(kind)].to_numpy(dtype=float), p, part["region"],
                                    part["issue_date"], "VAL")
        res[kind] = dict(band=list(band), coverage=band_coverage(offsets, *band))
    log("band: " + ", ".join(f"{k} {v['coverage']['covered']}/{v['coverage']['region_years']}" for k, v in res.items()))
    return res


def same_as_l1(out, l1):
    """The outputs that do not depend on the 90-day members must equal L1's exactly (and T must too)."""
    checks = []
    p1_columns = ([f"curve_{k}_{h}" for k in tidemark.CURVE_KINDS for h in tidemark.HORIZONS]
                  + ["floor_log_q10", "floor_days", "floor_shown"] + [f"p_T_{k}" for k in KINDS])
    for column in p1_columns:
        a, b = out["p1"][column].to_numpy(dtype=float), l1["p1"][column].to_numpy(dtype=float)
        same = len(a) == len(b) and np.array_equal(np.isnan(a), np.isnan(b)) and np.array_equal(a[~np.isnan(a)],
                                                                                                b[~np.isnan(b)])
        checks.append(dict(output=f"p1 {column}", identical=bool(same)))
    for part, column in (("p2_dam", "p"), ("p2_dam", "p_g"), ("p2_cell", "p")):
        checks.append(dict(output=f"{part} {column}", identical=bool(np.array_equal(
            out[part][column].to_numpy(dtype=float), l1[part][column].to_numpy(dtype=float)))))
    return checks


# ===========================================================================
# 6. Expected vs got
# ===========================================================================
def point(results, task, subset, model, metric):
    """One point value from the results."""
    return results[(task, subset, model)]["point"].get(metric)


def check_rows(results):
    """Level checks: expected (pre-event) vs got, with the tolerance as a reading aid."""
    out = []

    def add(label, key, expected, tolerance, source, ladder=False):
        got = point(results, *key)
        out.append(dict(check=label, expected=expected, got=got, difference=got - expected, tolerance=tolerance,
                        within=bool(abs(got - expected) <= tolerance), source=source, ladder=ladder))
    for kind in KINDS:
        task = f"P1_{kind}"
        add(f"{kind} L2 BSS vs B0 (ladder check)", (task, "primary", "L2", "bss_B0"), L3_BSS[kind] - PHY_COST[kind],
            TOL, f"derived: {SRC_L3} minus {SRC_PHY}", ladder=kind in ("R30", "D0"))
        add(f"{kind} L2 BSS vs B0, persistent", (task, "persistent+octmar+at_risk", "L2", "bss_B0"),
            L3_PERSISTENT[kind] - PHY_COST_PERSISTENT[kind], TOL, "derived, as above")
        for metric, tolerance in (("auc", TOL), ("bss_B2", TOL), ("cal_slope", 0.05), ("citl", 0.05)):
            add(f"{kind} L2 {metric}", (task, "primary", "L2", metric), L3_OTHER[kind][metric], tolerance,
                f"{SRC_L3} (L3; physics moves these by < 0.003)")
        for name in ("S", "M", "S+M"):
            add(f"{kind} {name} alone, seed 0", (task, "primary", name + "0", "bss_B0"), NS_SEED0[name][kind],
                TOL, SRC_NS)
        for seed in nets.SEEDS:
            add(f"{kind} S+M pair, seed {seed}", (task, "primary", f"S+M{seed}", "bss_B0"), PAIR_SEEDS[kind][seed],
                TOL, SRC_PAIR)
    return out


def gain_rows(results):
    """Paired gains (same rows): L2 over G2 and L2 over L1 (the nets' gain), with the bench point and interval."""
    out = []
    for kind in KINDS:
        task = f"P1_{kind}"
        l3, ci = L3_GAIN_G2[kind]
        cost = PHY_COST[kind]
        for label, key, expected, bench_ci, source in (
                (f"{kind} L2 gain over G2", (task, "primary", "L2", "d_bss_B0_vs_G2"), l3 - cost,
                 (ci[0] - cost, ci[1] - cost), f"derived: L3 vs G2c ({SRC_L3}) minus {SRC_PHY}"),
                (f"{kind} L2 gain over L1 (the nets)", (task, "primary", "L2", "d_bss_B0_vs_L1"), *NETS_COST[kind],
                 "hybrid val_stageB.csv '-nets' removal cost (seed-0 nets; T dam-like + PHY)"),
                (f"{kind} L2 gain over L1, persistent", (task, "persistent+octmar+at_risk", "L2", "d_bss_B0_vs_L1"),
                 *NETS_COST_PERSISTENT[kind], "as above, persistent subset")):
            r = results[key[:3]]
            got = r["point"][key[3]]
            got_ci = r["ci_dam"].get(key[3])
            out.append(dict(check=label, expected=expected, bench_ci=list(bench_ci), got=got, got_ci=got_ci,
                            inside_bench_ci=bool(bench_ci[0] <= got <= bench_ci[1]), source=source))
    return out


def training_rows(infos):
    """Training checks: rows, head rows and events (exact), inputs and parameters, losses vs the bench logs."""
    out = []
    for info in infos:
        cutoff, model, seed = info["cutoff"], info["model"], info["seed"]
        bench_loss = TRAIN_LOSS.get((cutoff, model), (None,) * 3)[seed]
        heads_exact = (all((info["head_rows"][k], info["head_events"][k]) == HEAD_ROWS[k] for k in KINDS)
                       if cutoff == config.VAL_START else None)     # no pre-event head counts for the inner cutoff
        out.append(dict(net=f"{model} seed {seed}", cutoff=cutoff, rows=info["rows"],
                        rows_expected=TRAIN_ROWS[cutoff], rows_match=info["rows"] == TRAIN_ROWS[cutoff],
                        heads=info["head_rows"], head_events=info["head_events"], heads_match=heads_exact,
                        n_inputs=info["n_inputs"], parameters=info["parameters"], parameters_bench=PARAMETERS[model],
                        loss=info["epoch_losses"][0], loss_bench=bench_loss, seconds=info["train_seconds"],
                        from_checkpoint=bool(info.get("loaded_from_checkpoint"))))
    return out


# ===========================================================================
# Report
# ===========================================================================
def fmt(value, digits=4, sign=True):
    """A number for a table cell ("-" when missing)."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def fmt_ci(result, metric, digits=4, sign=True):
    """Point value with the dam interval and the region-year (ry) interval when present."""
    text = fmt(result["point"].get(metric), digits, sign)
    for label, key in (("", "ci_dam"), ("ry ", "ci_region_year")):
        ci = result.get(key, {}).get(metric)
        if ci:
            text += f" {label}[{fmt(ci[0], digits, sign)}, {fmt(ci[1], digits, sign)}]"
    return text


def p1_table(results, models):
    """Markdown rows of the P1 scores for the given model names."""
    lines = ["| task | subset | model | rows | events | BSS vs B0 [dam] ry [region-year] | BSS vs B2 | AUC | cal. slope | "
             "CITL | gain over G2 | gain over L1 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (task, subset, model), r in results.items():
        if model not in models:
            continue
        over_l1 = next((fmt_ci(r, f"d_bss_B0_vs_{ref}") for ref in ("L1", "L1_premax") if ref in r["refs"]), "-")
        lines.append("| " + " | ".join([
            task, subset, model, f"{r['rows']['scored']:,}", f"{r['rows']['events']:,}", fmt_ci(r, "bss_B0"),
            fmt(r["point"]["bss_B2"], 4), fmt(r["point"]["auc"], 4, False), fmt(r["point"]["cal_slope"], 3, False),
            fmt(r["point"]["citl"], 3), fmt_ci(r, "d_bss_B0_vs_G2"), over_l1]) + " |")
    return lines


COMPONENT_NAMES = {"T": "T (the tree; the G2 recipe)", "S": "S (3 seeds)", "M": "M (3 seeds)",
                   "S+M": "S + M (3 seeds each)", "anchor": "T + S + M (the anchor, before frailty)",
                   "L2": "**L2** (anchor + frailty + max rule)",
                   **{f"{n}{s}": f"{n.replace('+', ' + ')}, seed {s}" for n in ("S", "M", "S+M") for s in nets.SEEDS}}


def component_table(results):
    """One row per component and kind: BSS vs B0 (primary) and its gain over G2."""
    lines = ["| component | R30 BSS vs B0 | D0 | D0g | R30 gain over G2 | D0 | D0g |", "|---|---|---|---|---|---|---|"]
    for name in COMPONENTS + ["L2"]:
        cells = [fmt(point(results, f"P1_{k}", "primary", name, "bss_B0")) for k in KINDS]
        cells += [fmt(point(results, f"P1_{k}", "primary", name, "d_bss_B0_vs_G2")) for k in KINDS]
        lines.append(f"| {COMPONENT_NAMES[name]} | " + " | ".join(cells) + " |")
    return lines


def seed_spread(results):
    """Standard deviation over the 3 seeds of the S + M pair's BSS vs B0, per kind."""
    return {k: float(np.std([point(results, f"P1_{k}", "primary", f"S+M{s}", "bss_B0") for s in nets.SEEDS], ddof=1))
            for k in KINDS}


V1_BAND_REFERENCE = {"R30": "[-1.065, +0.761], 15/16", "D0": "[-1.130, +0.547], 13/16", "D0g": "not run"}  # step 8


def missed_text(coverage):
    """Region-years outside the band, as text."""
    missed = dict(coverage.get("drier_than_band", {}), **coverage.get("wetter_than_band", {}))
    return ", ".join(f"{k} ({v:+.2f})" for k, v in sorted(missed.items())) or "none"


def l1_band_text():
    """L1's band and VAL coverage from step 8's report, as text per kind ({} if step 8's JSON is missing)."""
    path = config.ARTIFACTS_DIR / "val_tidemark_L1.json"
    if not path.exists():
        return {}
    l1 = json.loads(path.read_text())
    return {k: f"[{lo:+.3f}, {hi:+.3f}], {l1['band'][k]['coverage']['covered']}/"
               f"{l1['band'][k]['coverage']['region_years']}" for k, (lo, hi) in l1["band_constants"].items()}


def write_report(r):
    """artifacts/val_tidemark_L2.md and .json."""
    results, checks, gains, band = r["p1"], r["checks"], r["gains"], r["band"]
    ladder = [c for c in checks if c["ladder"]]
    spread = seed_spread(results)
    lines = [
        "# VAL results: Tidemark rung L2 (tree + nets), build step 9",
        "",
        f"Generated by `scripts/09_nets_val.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only** "
        "(forecasts issued 2009-2015, development regions). TEST was not scored.",
        "",
        "**What was run.** `tidemark.fit_tidemark(\"2009-01-01\", rung=\"L2\")` then `tidemark.predict_tidemark`. "
        "L2 = the tree T + the sequence net S + the tabular net M, fused as the plain mean of their log-odds "
        "(S and M are each the log-odds mean of 3 seeds), then the per-dam frailty and the R30 max rule. No "
        "water-balance columns (those are rung L3). The nets are in `damdays/models/nets.py`, their 24-month "
        "inputs in `damdays/features/sequences.py`. Every member learns only from answers final before "
        "2009-01-01; the season band's inner backtest refits all three members on answers final before 2002-01-01.",
        "",
        f"Bootstrap: {r['n_boot_main']} dam and {r['n_boot_main']} region-year draws for L2 on the primary sets, "
        f"{r['n_boot_side']} on other subsets, the sensitivity row and the S + M pair; components without "
        "intervals. Brackets: dam 95% interval, then `ry` region-year interval (16 region-years, so rough).",
        "",
        "## PREREG ladder check for rung L2 (R30 and D0 within +-0.006 of the pre-event VAL BSS)",
        "",
        "The pre-event research had no row that is exactly L2 (its frozen model had the physics columns). The "
        "expected value is derived: the frozen v1 (L3) score minus the measured cost of removing the physics.",
        "",
        "| kind | expected (derived) | got | difference | within +-0.006? |", "|---|---|---|---|---|",
        *[f"| {c['check'].split()[0]} | {c['expected']:+.4f} | {c['got']:+.4f} | {c['difference']:+.4f} | "
          f"{'yes' if c['within'] else 'NO'} |" for c in ladder],
        "",
        f"Ladder condition (a) for L2: **{'met' if all(c['within'] for c in ladder) else 'NOT met'}**. Condition (b), "
        "the look-ahead test with the sequence generator, is reported in `artifacts/lookahead_test.json`.",
        "",
        "## P1: rung L2",
        "",
        "`L2` = the shipped forecast (R30 after the max rule); `L2_premax` = R30 before it. `gain over L1` = what "
        "adding the nets S and M gives on the same rows (L1 = step 8's forecasts). `_sens` = the PREREG "
        "label-determinable sensitivity row.",
        "",
        *p1_table(results, {"L2", "L2_premax"}),
        "",
        "## The members on their own (primary set, BSS vs B0, no intervals)",
        "",
        *component_table(results),
        "",
        "Seed spread of the S + M pair (standard deviation of BSS vs B0 over seeds 0, 1, 2): "
        + ", ".join(f"{k} {v:.4f}" for k, v in spread.items())
        + " (pre-event: R30 0.0048, D0 0.0066, D0g 0.0043; hybrid decision_log.json). This is why the PREREG "
        "requires 3 seeds.",
        "",
        "## Expected (pre-event research) vs got",
        "",
        "Tolerance +-0.006 (the PREREG ladder tolerance) for skill and AUC; +-0.05 for calibration, as a reading "
        "aid. One-seed values carry seed noise of about 0.005 on their own.",
        "",
        "| check | expected | got | difference | tolerance | verdict | source |", "|---|---|---|---|---|---|---|",
        *[f"| {c['check']} | {c['expected']:+.4f} | {c['got']:+.4f} | {c['difference']:+.4f} | +-{c['tolerance']} | "
          f"{'within' if c['within'] else 'OUTSIDE'} | {c['source']} |" for c in checks],
        "",
        "### Paired gains (same rows)",
        "",
        "| check | expected [bench 95% CI] | got [dam 95% CI] | inside the bench CI? | source |", "|---|---|---|---|---|",
        *[f"| {g['check']} | {g['expected']:+.4f} [{g['bench_ci'][0]:+.4f}, {g['bench_ci'][1]:+.4f}] | "
          f"{g['got']:+.4f}" + (f" [{g['got_ci'][0]:+.4f}, {g['got_ci'][1]:+.4f}]" if g["got_ci"] else "")
          + f" | {'yes' if g['inside_bench_ci'] else 'no'} | {g['source']} |" for g in gains],
        "",
        "The '-nets' rows are context, not like for like: the pre-event model they come from trained its tree on "
        "dam-like dams only, which was much weaker on persistent dams (hybrid stage A: -0.026 on R30 persistent). "
        "There the nets also repaired that weakness, so its persistent gain (+0.03) is larger than what the nets "
        "add on top of L1, whose tree learns from all waterbodies (as the PREREG fixes).",
        "",
        "## Training the nets",
        "",
        "Rows must match the pre-event research exactly (the same fit-row rule); losses are a reading aid "
        "(bench `hybrid/logs/nets.log`, same seeds).",
        "",
        "| net | cutoff | rows (expected) | head rows R30 / D0 / D0g (events) | inputs | parameters (bench) | "
        "loss (bench) | seconds |", "|---|---|---|---|---|---|---|---|",
        *[f"| {t['net']} | {t['cutoff']} | {t['rows']:,} ({t['rows_expected']:,}) {'ok' if t['rows_match'] else 'NO'} | "
          + " / ".join(f"{t['heads'][k]:,} ({t['head_events'][k]:,})" for k in KINDS)
          + {True: " ok", False: " NO", None: ""}[t["heads_match"]] + f" | {t['n_inputs']} | {t['parameters']:,} ({t['parameters_bench']}) | "
          f"{t['loss']:.4f} ({fmt(t['loss_bench'], 4, False)}) | "
          f"{t['seconds']}{' (loaded from checkpoint)' if t['from_checkpoint'] else ''} |" for t in r["training"]],
        "",
        "## Season band (L2's own 2002-2009 inner backtest)",
        "",
        "The band is rebuilt for each rung (its offsets are measured on that rung's own inner-backtest forecasts). "
        "A region-year is covered when its own offset lies inside the band; every miss below is a wet year "
        "(forecasts too high).",
        "",
        "| kind | band | VAL region-years covered | missed (offset) | L1 band, covered (step 8) | pre-event v1 band (reference) |",
        "|---|---|---|---|---|---|",
        *[f"| {k} | [{b['band'][0]:+.3f}, {b['band'][1]:+.3f}] | {b['coverage']['covered']}/"
          f"{b['coverage']['region_years']} | {missed_text(b['coverage'])} | {r['l1_band'].get(k, '-')} | "
          f"{V1_BAND_REFERENCE[k]} |" for k, b in band.items()],
        "",
        "## The parts that do not use the 90-day members equal L1's",
        "",
        f"{sum(c['identical'] for c in r['same_as_l1'])} of {len(r['same_as_l1'])} outputs identical bit for bit "
        "(runway curve, DamDays floor, season rating, and the tree T itself).",
        "",
        "Season rating (P2) of rung L2, scored as in step 8 (so the app can read every rung-L2 number from "
        "`val_tidemark_L2.json`); the ratings are L1's, so these are L1's scores:",
        "",
        "| task | subset | rated seasons | ran dry | AUC [dam] ry [region-year] | AUC gain over RAIN | "
        "within-season AUC | within-cell AUC |", "|---|---|---|---|---|---|---|---|",
        *[f"| {task} | {subset} | {p['rows']['scored']:,} | {p['rows']['events']:,} | {fmt_ci(p, 'auc', 4, False)} | "
          f"{fmt_ci(p, 'd_auc_vs_RAIN')} | {fmt(p['point'].get('auc_within_season'), 4, False)} | "
          f"{fmt(p['point'].get('auc_within_cell'), 4, False)} |" for (task, subset, _), p in r["p2"].items()],
        "",
        "## Notes",
        "",
        "- **Time rules.** Each net learns from Tidemark's own fit rows for each kind (answers final before the "
        "cutoff); its input means and spreads come from those rows only. The 24-month sequence ends at the month "
        "before the issue month. For the band's inner backtest (cutoff 2002-01-01) the three dam_rate inputs are "
        "recomputed as of 2002-01-01, as for the tree.",
        "- **Masked heads.** A D0-gradual label is missing when the window holds only an abrupt dry-out; those rows "
        "are left out of the D0g head, not counted as 0.",
        "- **Disclosed.** The tabular block includes the history length n_hist_c (log-scaled), as the frozen "
        "pre-event nets did; the PREREG keeps time-growing counts out of the P1 trees only.",
        f"- **Software.** torch {r['torch']} (CPU wheel), at most {nets.TORCH_THREADS} threads.",
        ("- **Forecasts** are in `data_cache/preds/VAL/tidemark/L2_*.pkl`; the nets in `data_cache/nets/`."
         if r["forecasts_saved"] else
         "- **Forecasts were NOT saved** (the disk holding data_cache was full); the scores above were computed "
         "from memory. The nets are in `data_cache/nets/`, so a rerun refits only the trees and parts 5-8."),
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")

    def compact(result):
        return dict(point=result["point"], ci_dam=result["ci_dam"], ci_region_year=result["ci_region_year"],
                    rows=result["rows"], refs=result["refs"])
    report = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), block=BLOCK, rung=RUNG, torch=r["torch"],
                  n_boot_main=r["n_boot_main"], n_boot_side=r["n_boot_side"], ladder=ladder, checks=checks,
                  gains=gains, training=r["training"], seed_spread=spread, band=band, same_as_l1=r["same_as_l1"],
                  p1={"|".join(k): compact(v) for k, v in results.items()},
                  p2={"|".join(k): compact(v) for k, v in r["p2"].items()},
                  fit_summary={k: v for k, v in r["summary"].items() if k != "band"},
                  band_constants=r["summary"]["band"]["band"])
    RESULTS_JSON.write_text(json.dumps(clean_for_json(report), indent=1), encoding="utf-8")


# ===========================================================================
# Main
# ===========================================================================
def main():
    """Train the nets, fit and forecast L2 on VAL, score it, write the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no bootstrap intervals")
    parser.add_argument("--reuse", action="store_true", help="rescore the saved L2 forecasts instead of refitting")
    args = parser.parse_args()
    n_boot_main, n_boot_side = (0, 0) if args.quick else (N_BOOT_MAIN, N_BOOT_SIDE)
    show_net_progress()
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    (SCORE_DIR / f"scorecard_dev_{BLOCK}.md").write_text("")        # this run's markdown table starts empty

    log("loading the inputs")
    inputs = tidemark.load_inputs()
    table = inputs["p1"]
    infos = train_all_nets(inputs)
    out, summary, forecasts_saved = fit_and_forecast(inputs, args.reuse)
    l1 = {part: require(PRED_TASK, f"L1_{part}", "scripts/08_tidemark_val.py") for part in ("p1", "p2_dam", "p2_cell")}

    results = {}
    for kind in KINDS:
        results.update(score_p1(table, out, l1["p1"], kind, n_boot_main, n_boot_side))
    report = dict(p1=results, p2=score_p2(out, n_boot_main), checks=check_rows(results), gains=gain_rows(results),
                  training=training_rows(infos),
                  band=band_results(table, out, summary), same_as_l1=same_as_l1(out, l1), summary=summary,
                  n_boot_main=n_boot_main, n_boot_side=n_boot_side, torch=nets.torch.__version__,
                  forecasts_saved=forecasts_saved, l1_band=l1_band_text())
    write_report(report)
    log(f"wrote {RESULTS_MD.name} and {RESULTS_JSON.name}")
    for c in report["checks"]:
        print(f"  {c['check']:<44s} expected {c['expected']:+.4f} got {c['got']:+.4f} diff {c['difference']:+.4f} "
              f"{'within' if c['within'] else 'OUTSIDE'}")
    for g in report["gains"]:
        print(f"  {g['check']:<44s} expected {g['expected']:+.4f} {g['bench_ci']} got {g['got']:+.4f} {g['got_ci']}")
    print(f"  same as L1: {sum(c['identical'] for c in report['same_as_l1'])}/{len(report['same_as_l1'])} identical")


if __name__ == "__main__":
    main()
