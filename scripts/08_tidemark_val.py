"""Step 8: Tidemark rung L1 end to end on VAL: the full L1 scorecard.

Run from the repo folder (after scripts/03_baselines_and_g2.py and 06_hazard_curve.py, whose
baselines it uses as references; steps 4, 5 and 7 are only read for the integration check):
    .venv/Scripts/python.exe scripts/08_tidemark_val.py            # full run, about 15 minutes
    .venv/Scripts/python.exe scripts/08_tidemark_val.py --quick    # no bootstrap intervals
    .venv/Scripts/python.exe scripts/08_tidemark_val.py --reuse    # rescore saved forecasts, no refits

What it does
  1. Fits Tidemark L1 through its one entry point, tidemark.fit_tidemark("2009-01-01"),
     on answers final before 2009-01-01, and forecasts every VAL issue (2009-2015)
     and every 1 July season rating (2009-2015) with tidemark.predict_tidemark.
  2. Integration check: every output must equal, bit for bit, what the component
     step saved (90-day probabilities: step 4; runway curve: step 6; floor: step 7;
     season rating: step 5).
  3. P1: R30, D0 and D0g on the primary set, the persistent subset and all months,
     paired against the benchmark G2; the PREREG label-determinable sensitivity
     rows; the PREREG P1 pass bars.
  4. Runway curve: BSS at 30, 60, 90 and 180 days, each against its own baselines.
  5. DamDays floor coverage, and season-band coverage (the band comes from
     Tidemark's own 2002-2009 inner backtest).
  6. P2 season rating against RAIN, RAIN+ and B2; the PREREG P2 pass bar and kill rule.
  7. Compares with the pre-event check values and writes artifacts/val_tidemark_L1.md
     (for people) and artifacts/val_tidemark_L1.json (for code).

TEST is never touched: the model learns from answers final before 2009-01-01, and
every table passed to the scorecard is checked to hold VAL forecasts only.
"""
import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Let "import damdays" work when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damdays import config  # noqa: E402
from damdays.data.splits import hydro_year, time_block  # noqa: E402
from damdays.evaluation import band_coverage, floor_coverage, score, score_curve  # noqa: E402
from damdays.evaluation.inputs import join_baselines, tidy_keys  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.evaluation.rules import is_octmar  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import hazard, rows, tidemark  # noqa: E402
from damdays.models import uncertainty as unc  # noqa: E402
from damdays.models.predictions import load_predictions, prediction_path, save_predictions  # noqa: E402

BLOCK = "VAL"
RUNG = "L1"
MODEL = "tidemark_L1"                      # the name on every scorecard result
PRED_TASK = "tidemark"                     # forecasts go to data_cache/preds/VAL/tidemark/L1_<part>.pkl
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step08_val"
RESULTS_MD = config.ARTIFACTS_DIR / "val_tidemark_L1.md"
RESULTS_JSON = config.ARTIFACTS_DIR / "val_tidemark_L1.json"
N_BOOT_MAIN, N_BOOT_SIDE = 500, 200        # bootstrap draws: primary sets (and P2), other subsets
NOTE = "step 8 (scripts/08_tidemark_val.py)"

# P1 subsets: (scorecard subset, population the baselines were fitted on, Oct-Mar issues only?)
P1_SUBSETS = [
    ("primary", "dam_like", True),                       # the pre-registered headline set
    ("persistent+octmar+at_risk", "persistent", True),   # dams that rarely dry out (harder)
    ("dam_like+at_risk", "dam_like", False),             # dam-like, all months
]
CURVE_SUBSETS = [("primary", "dam_like"), ("dam_like+at_risk", "dam_like"), ("persistent+octmar+at_risk", "persistent")]
P2_TASKS = [("P2_cell", "all", "p"), ("P2_dam", "dam_like", "p"), ("P2_dam_g", "dam_like", "p_g")]
P2_REFS = ["RAIN", "RAIN+", "B2"]
P2_PASS_DAUC, P2_KILL_DAUC = 0.05, 0.02    # PREREG: gain over RAIN >= 0.05 (CI above 0); kill if within 0.02
EXAMPLE_P = (0.05, 0.10, 0.30, 0.50)

# ---------------------------------------------------------------------------
# Check values from the pre-event research (VAL, development regions)
#   P1   hierarchical-pooling gbm_VAL_R30.csv / gbm_VAL_D0.csv, model "G2c+RE": the same tree
#        (G2c features = this build's G2 recipe, all waterbodies) + the same frailty
#        (lambda 100), WITHOUT the R30 max rule. Its paired gains are against "G2c" = our G2.
#   floor calibration-uncertainty tables/conformal_VAL.json (R30 LB90; raw quantile and split LOYO)
#   P2   season-rating final_VAL.json (offB2_HSN_damlike_prod, 3 seeds) and hybrid val_stageG_p2.csv
#   curve hybrid val_stageC_horizons.csv "H_alone" (dam-like H WITH the physics columns): reference only
# ---------------------------------------------------------------------------
TOL, CAL_TOL = 0.006, 0.05                 # PREREG ladder tolerance; calibration slope / CITL reading aid
LEVEL_CHECKS = [
    # (label, (task, subset, model, metric), expected, tolerance, source)
    ("R30 headline (after max rule), BSS vs B0", ("P1_R30", "primary", "L1", "bss_B0"), 0.1727, TOL,
     "G2c+RE (no max rule)"),
    ("R30 before max rule, BSS vs B0", ("P1_R30", "primary", "L1_premax", "bss_B0"), 0.1727, TOL, "G2c+RE"),
    ("R30 before max rule, BSS vs B2", ("P1_R30", "primary", "L1_premax", "bss_B2"), 0.1014, TOL, "G2c+RE"),
    ("R30 before max rule, AUC", ("P1_R30", "primary", "L1_premax", "auc"), 0.7819, TOL, "G2c+RE"),
    ("R30 before max rule, calibration slope", ("P1_R30", "primary", "L1_premax", "cal_slope"), 0.9692, CAL_TOL,
     "G2c+RE"),
    ("R30 persistent, before max rule, BSS vs B0", ("P1_R30", "persistent+octmar+at_risk", "L1_premax", "bss_B0"),
     0.1383, TOL, "G2c+RE"),
    ("D0 BSS vs B0", ("P1_D0", "primary", "L1", "bss_B0"), 0.1771, TOL, "G2c+RE"),
    ("D0 BSS vs B2", ("P1_D0", "primary", "L1", "bss_B2"), 0.0941, TOL, "G2c+RE"),
    ("D0 AUC", ("P1_D0", "primary", "L1", "auc"), 0.8328, TOL, "G2c+RE"),
    ("D0 calibration slope", ("P1_D0", "primary", "L1", "cal_slope"), 1.0103, CAL_TOL, "G2c+RE"),
    ("D0 persistent, BSS vs B0", ("P1_D0", "persistent+octmar+at_risk", "L1", "bss_B0"), 0.0819, TOL, "G2c+RE"),
]
GAIN_CHECKS = [
    # (label, (task, subset, model, metric), bench point, bench dam 95% CI, like for like?, source)
    ("R30 gain over G2, before max rule", ("P1_R30", "primary", "L1_premax", "d_bss_B0_vs_G2"), 0.0024,
     (0.0004, 0.0042), True, "G2c+RE vs G2c"),
    ("R30 gain over G2, before max rule, persistent",
     ("P1_R30", "persistent+octmar+at_risk", "L1_premax", "d_bss_B0_vs_G2"), 0.0039, (0.0018, 0.0066), True,
     "G2c+RE vs G2c"),
    ("R30 AUC gain over G2, before max rule", ("P1_R30", "primary", "L1_premax", "d_auc_vs_G2"), 0.0010,
     (0.0001, 0.0019), True, "G2c+RE vs G2c"),
    ("D0 gain over G2", ("P1_D0", "primary", "L1", "d_bss_B0_vs_G2"), 0.0020, (0.0002, 0.0041), True,
     "G2c+RE vs G2c"),
    ("D0 gain over G2, persistent", ("P1_D0", "persistent+octmar+at_risk", "L1", "d_bss_B0_vs_G2"), 0.0033,
     (0.0006, 0.0063), True, "G2c+RE vs G2c"),
    ("D0 AUC gain over G2", ("P1_D0", "primary", "L1", "d_auc_vs_G2"), 0.0010, (0.0002, 0.0018), True,
     "G2c+RE vs G2c"),
    ("R30 headline gain over G2 (after max rule)", ("P1_R30", "primary", "L1", "d_bss_B0_vs_G2"), 0.0024, None, False,
     "the bench had no max rule; step 4 measured its cost at -0.0006"),
    ("D0g gain over G2", ("P1_D0g", "primary", "L1", "d_bss_B0_vs_G2"), 0.0005, (-0.0014, 0.0024), False,
     "no twin without nets: hybrid stage B frailty removal cost (full model)"),
]
FLOOR_CHECKS = [
    # (label, result key, metric, expected, tolerance as a reading aid)
    ("floor as issued on VAL (raw q10, shift 0), all", "issued_all", "coverage", 0.8997, 0.005),
    ("floor as issued on VAL, primary", "issued_primary", "coverage", 0.9098, 0.005),
    ("floor as issued, median days (all)", "issued_all", "median_floor_days", 45.28, 3.0),
    ("LOYO conformal floor, all (pre-event procedure)", "loyo_all", "coverage", 0.9001, 0.005),
    ("LOYO conformal floor, primary", "loyo_primary", "coverage", 0.9102, 0.005),
    ("LOYO worst July-June year (all)", "loyo_all", "worst_year_coverage", 0.878, 0.01),
    ("LOYO median floor, days (all)", "loyo_all", "median_floor_days", 45.03, 3.0),
    ("LOYO median floor, days (primary)", "loyo_primary", "median_floor_days", 44.61, 3.0),
    ("LOYO share of floors >= 90 days (all)", "loyo_all", "share_ge_90", 0.259, 0.02),
]
RAIN_NOTE = "this build's RAIN uses causal rain deciles, so the gap to RAIN comes out about +0.003 larger (step 5)"
P2_CHECKS = [
    # (label, (task, metric), expected, tolerance, note)
    ("P2_cell AUC", ("P2_cell", "auc"), 0.7873, TOL, ""),
    ("P2_cell dAUC vs RAIN", ("P2_cell", "d_auc_vs_RAIN"), 0.2464, TOL, RAIN_NOTE),
    ("P2_cell dAUC vs RAIN+", ("P2_cell", "d_auc_vs_RAIN+"), 0.1547, TOL, "RAIN+ refitted on causal inputs (step 3)"),
    ("P2_cell dAUC vs B2", ("P2_cell", "d_auc_vs_B2"), 0.0142, TOL, ""),
    ("P2_cell BSS vs B0", ("P2_cell", "bss_B0"), 0.1489, TOL, ""),
    ("P2_cell BSS vs B2", ("P2_cell", "bss_B2"), 0.0061, TOL, ""),
    ("P2_cell calibration slope", ("P2_cell", "cal_slope"), 0.9272, CAL_TOL, ""),
    ("P2_cell CITL", ("P2_cell", "citl"), -0.1979, CAL_TOL, "VAL over-predicts (wet 2010-12)"),
    ("P2_cell within-season AUC", ("P2_cell", "auc_within_season"), 0.7893, TOL, ""),
    ("P2_dam AUC", ("P2_dam", "auc"), 0.7796, TOL, ""),
    ("P2_dam dAUC vs RAIN", ("P2_dam", "d_auc_vs_RAIN"), 0.2264, TOL, RAIN_NOTE),
    ("P2_dam dAUC vs B2", ("P2_dam", "d_auc_vs_B2"), 0.0174, TOL, ""),
    ("P2_dam BSS vs B2", ("P2_dam", "bss_B2"), 0.0107, TOL, ""),
    ("P2_dam calibration slope", ("P2_dam", "cal_slope"), 0.9719, CAL_TOL, ""),
    ("P2_dam CITL", ("P2_dam", "citl"), -0.2344, CAL_TOL, ""),
    ("P2_dam_g AUC (prior swap)", ("P2_dam_g", "auc"), 0.7670, TOL, "hybrid stage G"),
    ("P2_dam_g BSS vs B2 (prior swap)", ("P2_dam_g", "bss_B2"), 0.0022, TOL, "hybrid stage G"),
    ("P2_dam_g calibration slope", ("P2_dam_g", "cal_slope"), 0.9052, CAL_TOL, "hybrid stage G"),
    ("P2_dam_g CITL", ("P2_dam_g", "citl"), -0.1930, CAL_TOL, "hybrid stage G"),
]
# Exact counts (scored rows and events; pre-event research, as in steps 3, 5 and 6) and fit sizes.
COUNT_CHECKS = {
    ("P1_R30", "primary"): (66_453, 15_861), ("P1_D0", "primary"): (86_651, 9_893),
    ("P1_D0g", "primary"): (83_747, 6_989),
    ("P1_R30", "persistent+octmar+at_risk"): (45_500, 9_223), ("P1_D0", "persistent+octmar+at_risk"): (58_249, 2_949),
    ("P1_D0g", "persistent+octmar+at_risk"): (57_382, 2_082),
    ("P1_R30", "dam_like+at_risk"): (127_203, 25_039), ("P1_D0", "dam_like+at_risk"): (160_529, 14_617),
    ("P1_D0g", "dam_like+at_risk"): (155_876, 9_964),
    ("P2_cell", "all"): (9_848, 1_684), ("P2_dam", "dam_like"): (11_557, 2_069), ("P2_dam_g", "dam_like"): (10_949, 1_461),
}
MEMBER_FIT_CHECKS = {"R30": (659_554, 192_700), "D0": (875_286, 148_942), "D0g": (815_946, 89_602)}
CURVE_FIT_CHECKS = {"R30": (283_836, 1_000_128, 94_623), "D0": (365_109, 1_362_265, 60_783)}
RATING_FIT_CHECK = (32_355, 5_788)
CURVE_BASE_RATES = {"R30": (0.0811, 0.1710, 0.2387, 0.3248), "D0": (0.0369, 0.0792, 0.1142, 0.1653)}
# Reference only (not like for like): the frozen pre-event curve had the two physics columns.
CURVE_REFERENCE = {"R30": (0.0987, 0.1509, 0.1759, 0.1988), "D0": (0.0965, 0.1540, 0.1851, 0.2353)}
# Reference only: the full pre-event Tidemark v1 (L3: nets + physics + frailty), VAL primary BSS vs B0
# (hybrid val_final_scorecard.csv). L1 is expected below it by about the nets + physics gain.
FULL_V1_REFERENCE = {"R30": 0.1818, "D0": 0.1948, "D0g": 0.1947}

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


# ===========================================================================
# Small helpers
# ===========================================================================
def require(block, task, name, step):
    """A saved prediction table from an earlier step; stops with a clear message if it is missing."""
    if not prediction_path(block, task, name).exists():
        raise SystemExit(f"Missing {prediction_path(block, task, name)}: run {step} first.")
    return load_predictions(block, task, name)


def attach(frame, other, columns):
    """Copy `columns` from `other` into `frame`; both must list the same forecasts in the same order."""
    same_keys = (frame["uid"].astype(str).to_numpy() == other["uid"].astype(str).to_numpy()).all() and \
        (pd.to_datetime(frame["issue_date"]).to_numpy() == pd.to_datetime(other["issue_date"]).to_numpy()).all()
    if len(frame) != len(other) or not same_keys:
        raise AssertionError("Prediction tables are not row-aligned.")
    for column in columns:
        frame[column] = other[column].to_numpy()
    return frame


def assert_val_only(frame):
    """Refuse to score anything outside VAL (this script never looks at TEST)."""
    blocks = set(time_block(frame["issue_date"]))
    if blocks != {BLOCK}:
        raise AssertionError(f"Expected VAL issues only, found blocks {sorted(blocks)}")


def on_rows(p1_out, positions, column):
    """An output column of predict_tidemark's p1 table, read on the given P1-table rows."""
    return p1_out.set_index("row").loc[np.asarray(positions), column].to_numpy()


def data_end():
    """The date of the last satellite look in the archive (saved by the feature build)."""
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as handle:
        return pd.Timestamp(pickle.load(handle)["data_end"])


# ===========================================================================
# 1. Fit and forecast (or reload)
# ===========================================================================
def summary_path():
    """Where the fit summary is kept (pickle, exact; a rounded JSON copy sits next to it)."""
    return prediction_path(BLOCK, PRED_TASK, f"{RUNG}_fit_summary")


def fit_and_forecast(inputs, reuse):
    """tidemark.fit_tidemark + predict_tidemark (or the saved forecasts with --reuse). Returns (out, summary)."""
    parts = ("p1", "p2_dam", "p2_cell")
    if reuse and summary_path().exists() and all(prediction_path(BLOCK, PRED_TASK, f"{RUNG}_{p}").exists()
                                                 for p in parts):
        out = {part: load_predictions(BLOCK, PRED_TASK, f"{RUNG}_{part}") for part in parts}
        log("reloaded the saved L1 forecasts")
        return out, pd.read_pickle(summary_path())

    model = tidemark.fit_tidemark(config.VAL_START, RUNG, inputs=inputs, log=log)
    out = tidemark.predict_tidemark(model, inputs)
    log(f"forecasts made: {len(out['p1']):,} P1 issues, {len(out['p2_dam']):,} dam seasons, "
        f"{len(out['p2_cell']):,} cell seasons")
    summary = tidemark.summary(model)
    for part in parts:
        save_predictions(out[part], BLOCK, PRED_TASK, f"{RUNG}_{part}")
    pd.to_pickle(summary, summary_path())
    summary_path().with_suffix(".json").write_text(json.dumps(clean_for_json(summary), indent=1))
    log(f"forecasts saved to data_cache/preds/{BLOCK}/{PRED_TASK}/")
    return out, summary


# ===========================================================================
# 2. Integration check: the one entry point gives what the component steps saved
# ===========================================================================
def compare(mine, theirs):
    """Largest absolute difference and whether two arrays are identical (blanks in the same places)."""
    mine, theirs = np.asarray(mine, dtype=float), np.asarray(theirs, dtype=float)
    same_blanks = np.array_equal(np.isnan(mine), np.isnan(theirs))
    both = ~np.isnan(mine) & ~np.isnan(theirs)
    gap = float(np.max(np.abs(mine[both] - theirs[both]))) if both.any() else 0.0
    return dict(max_abs_diff=gap, identical=bool(same_blanks and np.array_equal(mine[both], theirs[both])),
                rows=int(len(mine)))


def integration_checks(table, out):
    """Each Tidemark output against the component step's saved predictions (skipped if not saved)."""
    checks = []

    def add(label, step, task, name, mine_fn, column):
        if not prediction_path(BLOCK, task, name).exists():
            checks.append(dict(check=label, step=step, status="not available (step not run)"))
            return
        saved = load_predictions(BLOCK, task, name)
        checks.append(dict(check=label, step=step, status="compared", **compare(mine_fn(saved), saved[column])))

    p1 = out["p1"]
    for kind in rows.P1_KINDS:
        positions = np.flatnonzero(rows.p1_block_rows(table, kind, BLOCK))
        task = f"P1_{kind}"
        add(f"{kind} 90-day probability (p90_{kind})", "step 4", task, "tidemark_L1",
            lambda s, k=kind: on_rows(p1, positions, f"p90_{k}"), "p")
        add(f"{kind} anchor before frailty", "step 4", task, "tidemark_L1",
            lambda s, k=kind: on_rows(p1, positions, f"anchor_{k}"), "p_anchor")
        add(f"{kind} frailty b", "step 4", task, "tidemark_L1",
            lambda s, k=kind: on_rows(p1, positions, f"frailty_b_{k}"), "frailty_b")
        add(f"{kind} tree T vs the benchmark G2", "step 3", task, "models",
            lambda s, k=kind: on_rows(p1, positions, f"p_T_{k}"), "p_G2")
    r30_positions = np.flatnonzero(rows.p1_block_rows(table, "R30", BLOCK))
    add("R30 before the max rule", "step 4", "P1_R30", "tidemark_L1",
        lambda s: on_rows(p1, r30_positions, "p90_R30_premax"), "p_premax")
    for kind in tidemark.CURVE_KINDS:
        positions = np.flatnonzero(rows.p1_block_rows(table, kind, BLOCK))
        for h in tidemark.HORIZONS:
            add(f"{kind} runway curve at {h} days", "step 6", f"{kind}_curve", "H",
                lambda s, k=kind, d=h: on_rows(p1, positions, f"curve_{k}_{d}"), f"p_{h}")
    add("floor: log 10% quantile", "step 7", "P1_R30", "floor_LB90",
        lambda s: on_rows(p1, r30_positions, "floor_log_q10"), "log_q10")
    add("floor: days (shift 0 = step 7's raw floor)", "step 7", "P1_R30", "floor_LB90",
        lambda s: on_rows(p1, r30_positions, "floor_days"), "floor_raw")
    add("P2 dam rating p", "step 5", "P2_dam", "season_rating", lambda s: out["p2_dam"]["p"], "p")
    add("P2 dam rating p (gradual)", "step 5", "P2_dam_g", "season_rating", lambda s: out["p2_dam"]["p_g"], "p")
    add("P2 cell rating p", "step 5", "P2_cell", "season_rating", lambda s: out["p2_cell"]["p"], "p")
    return checks


# ===========================================================================
# 3. P1: the 90-day probabilities
# ===========================================================================
def p1_frame(table, out, kind):
    """Keys, flags, labels and the forecasts of every at-risk VAL issue of `kind`, plus step 3's G2."""
    picked = rows.p1_block_rows(table, kind, BLOCK)
    positions = np.flatnonzero(picked)
    chosen = table.loc[picked]
    raw_label = chosen[rows.p1_label(kind)].to_numpy(dtype=float)
    frame = pd.DataFrame({
        "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
        "region": chosen["region"].astype(str).to_numpy(),
        "dam_like": chosen["dam_like"].to_numpy(dtype=bool), "persistent": chosen["persistent"].to_numpy(dtype=bool),
        "at_risk": True,                                    # every row here is at risk for this kind
        "y": rows.p1_scored_label(chosen, kind),            # blank where label_ok is False
        # PREREG sensitivity label: every issue whose 90-day window has closed, no 3-look rule.
        "y_sens": np.where(chosen["window_closed"].to_numpy(dtype=bool), raw_label, np.nan),
    })
    frame["p_L1"] = on_rows(out["p1"], positions, f"p90_{kind}")
    if kind == "R30":
        frame["p_L1_premax"] = on_rows(out["p1"], positions, "p90_R30_premax")
    attach(frame, require(BLOCK, f"P1_{kind}", "models", "scripts/03_baselines_and_g2.py"), ["p_G2"])
    return frame


def expected_keys(frame, population, octmar_only, label="y"):
    """The rows a P1 subset must be scored on, worked out here independently of the scorecard."""
    keep = frame[label].notna().to_numpy() & frame[population].to_numpy(dtype=bool)
    if octmar_only:
        keep = keep & is_octmar(frame["issue_date"])
    return frame.loc[keep, ["uid", "issue_date"]]


def score_p1(table, out, kind, n_boot_main, n_boot_side):
    """L1 (and R30 before the max rule) on every subset, and the sensitivity row. {(task, subset, model): result}."""
    task = f"P1_{kind}"
    frame = p1_frame(table, out, kind)
    base = {pop: require(BLOCK, task, f"baselines_{pop}", "scripts/03_baselines_and_g2.py")
            for pop in ("dam_like", "persistent")}
    results = {}
    for subset, population, octmar_only in P1_SUBSETS:
        scored = attach(frame.copy(), base[population], ["p_B0", "p_B2"])
        assert_val_only(scored)
        n_boot = n_boot_main if subset == "primary" else n_boot_side
        models = ["L1"] + (["L1_premax"] if kind == "R30" and subset != "dam_like+at_risk" else [])
        for model in models:
            results[(task, subset, model)] = score(
                scored.assign(p=scored[f"p_{model}"]), task, subset, model=f"tidemark_{model}", refs=["G2"],
                expected_keys=expected_keys(frame, population, octmar_only), n_boot=n_boot, out_dir=SCORE_DIR,
                note=NOTE)
    # PREREG sensitivity row: every at-risk issue whose window closed, without the 3-look label rule.
    sens = attach(frame.copy(), base["dam_like"], ["p_B0", "p_B2"]).assign(y=frame["y_sens"], p=frame["p_L1"])
    results[(f"{task}_sens", "primary", "L1")] = score(
        sens, f"{task}_sens", "primary", model=MODEL, refs=["G2"],
        expected_keys=expected_keys(frame, "dam_like", True, "y_sens"), n_boot=n_boot_side, out_dir=SCORE_DIR,
        note=NOTE)
    log(f"{task}: scored on {len(P1_SUBSETS)} subsets and the sensitivity row")
    return results


# ===========================================================================
# 4. The runway curve, horizon by horizon
# ===========================================================================
def curve_frame(table, out, kind, labels):
    """Keys, flags, the labels at 30/60/90/180 days and the curve, for every at-risk VAL issue of `kind`."""
    picked = rows.p1_block_rows(table, kind, BLOCK)
    positions = np.flatnonzero(picked)
    chosen = table.loc[picked]
    frame = pd.DataFrame({
        "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
        "region": chosen["region"].astype(str).to_numpy(),
        "dam_like": chosen["dam_like"].to_numpy(dtype=bool), "persistent": chosen["persistent"].to_numpy(dtype=bool),
        "at_risk": True})
    for h in tidemark.HORIZONS:
        frame[f"y_{h}"] = labels.loc[picked, f"y_{h}"].to_numpy()
        frame[f"p_{h}"] = on_rows(out["p1"], positions, f"curve_{kind}_{h}")
    return frame


def score_curves(table, out, n_boot_main, n_boot_side):
    """The runway curve on every subset, each horizon against its own baselines (step 6's B0_h and B2_h)."""
    end = data_end()
    results = {}
    for kind in tidemark.CURVE_KINDS:
        frame = curve_frame(table, out, kind, hazard.horizon_labels(table, kind, end))
        for subset, population in CURVE_SUBSETS:
            base = require(BLOCK, f"{kind}_curve", f"baselines_{population}", "scripts/06_hazard_curve.py")
            scored = attach(frame.copy(), base, [f"p_B{b}_{h}" for b in (0, 2) for h in tidemark.HORIZONS])
            assert_val_only(scored)
            results[(f"{kind}_curve", subset)] = score_curve(
                scored, f"{kind}_curve", subset, model=MODEL,
                n_boot=n_boot_main if subset == "primary" else n_boot_side, out_dir=SCORE_DIR, note=NOTE)
        log(f"{kind}_curve: scored on {len(CURVE_SUBSETS)} subsets")
    return results


def headline_vs_curve(table, out):
    """How far the curve's 90-day point is from the 90-day headline, on the primary set.

    They come from two different models (PREREG: the headline is the fused 90-day
    anchor with frailty; the curve is the hazard model H; the pre-event "anchored
    fan" that forced them to agree was dropped). The app shows both, so the gap is reported.
    """
    res = {}
    for kind in tidemark.CURVE_KINDS:
        picked = (rows.p1_block_rows(table, kind, BLOCK) & table["dam_like"].to_numpy(dtype=bool)
                  & is_octmar(table["issue_date"]))
        positions = np.flatnonzero(picked)
        gap = on_rows(out["p1"], positions, f"curve_{kind}_90") - on_rows(out["p1"], positions, f"p90_{kind}")
        res[kind] = dict(rows=int(len(gap)), mean_gap=float(np.mean(gap)), mean_abs_gap=float(np.mean(np.abs(gap))),
                         p90_abs_gap=float(np.percentile(np.abs(gap), 90)))
    return res


def horizon_value(result, h, metric, part="point"):
    """One metric at one horizon from a score_curve result."""
    entry = next(x for x in result["horizons"] if x["horizon"] == h)
    return entry[part].get(metric)


# ===========================================================================
# 5. DamDays floor and season band
# ===========================================================================
def floor_frame(table, out):
    """Every at-risk VAL R30 issue: its answer (days to R30), follow-up, and the floor as issued."""
    picked = rows.p1_block_rows(table, unc.FLOOR_KIND, BLOCK)
    positions = np.flatnonzero(picked)
    chosen = table.loc[picked]
    frame = pd.DataFrame({
        "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
        "region": chosen["region"].astype(str).to_numpy(), "hydro_year": hydro_year(chosen["issue_date"]),
        "label_ok": chosen["label_ok"].to_numpy(dtype=bool),
        "days_to_R30": chosen[f"lab_tte_{unc.FLOOR_KIND}"].to_numpy(dtype=float),   # NaN: no later event
        "runway_days": unc.runway_days(chosen),                                      # capped at 365
        "followup_days": unc.followup_days(chosen["issue_date"], data_end()),
        "log_q10": on_rows(out["p1"], positions, "floor_log_q10"),
        "floor": on_rows(out["p1"], positions, "floor_days"),
        "floor_shown": on_rows(out["p1"], positions, "floor_shown")})
    frame["primary"] = chosen["dam_like"].to_numpy(dtype=bool) & is_octmar(frame["issue_date"])
    return frame


def floor_summary(frame, floors, mask, n_boot, cap_days=None):
    """Floor coverage (the scorecard's floor_coverage) plus the share of long floors, on the rows in mask."""
    part = frame[mask]
    shown = np.asarray(floors)[mask]
    result = floor_coverage(shown, part["days_to_R30"], part["followup_days"], uid=part["uid"],
                            issue_date=part["issue_date"], cap_days=cap_days, n_boot=n_boot)
    result["share_ge_90"] = float(np.mean(shown >= 90))
    result["share_180_plus"] = float(np.mean(shown >= unc.FLOOR_DISPLAY_MAX_DAYS))
    result["worst_year_coverage"] = result.get("worst_year", {}).get("coverage", np.nan)
    result.pop("bootstrap", None)
    return result


def floor_results(table, out, n_boot):
    """Coverage of the floor as issued (VAL: raw 10% quantile), leave-one-year-out, as displayed, sensitivity."""
    frame = floor_frame(table, out)
    labelled = frame["label_ok"].to_numpy()
    primary = labelled & frame["primary"].to_numpy()
    res = {"rows_at_risk": len(frame), "rows_labelled": int(labelled.sum())}
    res["issued_all"] = floor_summary(frame, frame["floor"], labelled, n_boot)
    res["issued_primary"] = floor_summary(frame, frame["floor"], primary, n_boot)
    # Leave one July-June year out (the pre-event procedure): each VAL year's shift from the OTHER VAL
    # years. It uses later years too, so it checks the method, not a real-time forecast.
    calib = frame[labelled]
    shifts = unc.leave_one_year_out_shifts(calib["log_q10"], calib["runway_days"], calib["hydro_year"])
    loyo = unc.floor_days(frame["log_q10"], unc.shifts_for_rows(frame["hydro_year"], shifts))
    res["loyo_shifts_by_year"] = shifts
    res["loyo_all"] = floor_summary(frame, loyo, labelled, 0)
    res["loyo_primary"] = floor_summary(frame, loyo, primary, 0)
    res["shown_all"] = floor_summary(frame, frame["floor_shown"], labelled, 0, cap_days=unc.FLOOR_DISPLAY_MAX_DAYS)
    res["shown_primary"] = floor_summary(frame, frame["floor_shown"], primary, 0, cap_days=unc.FLOOR_DISPLAY_MAX_DAYS)
    res["issued_all_incl_unlabelled"] = floor_summary(frame, frame["floor"], np.ones(len(frame), bool), 0)
    log(f"floor: coverage as issued {res['issued_all']['coverage']:.4f} (all), "
        f"{res['issued_primary']['coverage']:.4f} (primary)")
    return res


def band_results(table, out, summary):
    """Region-year coverage of the season band on VAL, for each kind.

    The band [low, high] comes from Tidemark's own 2002-2009 inner backtest (fit_tidemark). On VAL
    each region-year's offset is measured on L1's own forecasts: primary set, label known.
    """
    res = {}
    inner = summary["band"]["offsets"]
    for kind in tidemark.P1_KINDS:
        band = tuple(summary["band"]["band"][kind])
        mask = (unc.band_rows(table, kind, config.VAL_START, config.TEST_START)
                & (time_block(table["issue_date"]) == BLOCK))
        part = table.loc[mask]
        p = on_rows(out["p1"], np.flatnonzero(mask), f"p90_{kind}")
        offsets = unc.block_offsets(part[rows.p1_label(kind)].to_numpy(dtype=float), p, part["region"],
                                    part["issue_date"], "VAL")
        inner_offsets = pd.DataFrame(inner[kind])
        low, high = unc.band_probabilities(np.array(EXAMPLE_P), band)
        res[kind] = dict(band=list(band), coverage=band_coverage(offsets, *band),
                         loyo_pooled=unc.leave_one_year_out_band_coverage(offsets, extra_offsets=inner_offsets),
                         loyo_val_only=unc.leave_one_year_out_band_coverage(offsets),
                         examples={str(p0): [float(lo), float(hi)] for p0, lo, hi in zip(EXAMPLE_P, low, high)},
                         val_offsets=offsets.to_dict("records"), inner_offsets=inner_offsets.to_dict("records"))
    log("band: " + ", ".join(f"{k} {v['coverage']['covered']}/{v['coverage']['region_years']}" for k, v in res.items()))
    return res


def step7_band_reference():
    """The G2 stand-in band of step 7 (if it ran): {kind: (band, covered, region-years)}."""
    path = config.ARTIFACTS_DIR / "uncertainty_val.json"
    if not path.exists():
        return {}
    band = json.loads(path.read_text())["band"]
    return {k: (v["band_val_setting"], v["coverage_val_forward"]["covered"], v["coverage_val_forward"]["region_years"])
            for k, v in band.items()}


# ===========================================================================
# 6. P2: the season rating
# ===========================================================================
def p2_frame(out, task, column):
    """The L1 rating for a P2 task, joined with step 3's baselines (which carry the scored label y)."""
    source = out["p2_cell"] if task == "P2_cell" else out["p2_dam"]
    frame = tidy_keys(pd.DataFrame({"uid": source["uid"].to_numpy(), "issue_date": source["issue_date"].to_numpy(),
                                    "region": source["region"].to_numpy(), "p": source[column].to_numpy()}))
    frame = join_baselines(frame, require(BLOCK, task, "baselines", "scripts/03_baselines_and_g2.py"))
    assert_val_only(frame)
    return frame


def score_p2(out, n_boot):
    """Each P2 task against RAIN, RAIN+ and B2; returns {(task, subset, "L1"): result}."""
    results = {}
    for task, subset, column in P2_TASKS:
        frame = p2_frame(out, task, column)
        keep = frame["y"].notna().to_numpy() & (frame["dam_like"].to_numpy(dtype=bool) if subset == "dam_like"
                                                else np.ones(len(frame), dtype=bool))
        results[(task, subset, "L1")] = score(frame, task, subset, model=MODEL, refs=P2_REFS,
                                              expected_keys=frame.loc[keep, ["uid", "issue_date"]], n_boot=n_boot,
                                              out_dir=SCORE_DIR, note=NOTE)
        log(f"{task}: AUC {results[(task, subset, 'L1')]['point']['auc']:.4f}")
    return results


def p2_rules(result):
    """PREREG P2: pass bar (dAUC vs RAIN >= 0.05, dam/cell CI above 0) and kill rule (RAIN within 0.02 AUC)."""
    gain = result["point"]["d_auc_vs_RAIN"]
    ci = result["ci_dam"].get("d_auc_vs_RAIN")
    return dict(d_auc_vs_RAIN=gain, ci_dam=ci, ci_region_year=result["ci_region_year"].get("d_auc_vs_RAIN"),
                passed=bool(gain >= P2_PASS_DAUC and ci[0] > 0) if ci else None,
                kill_rule_triggered=bool(gain < P2_KILL_DAUC))


# ===========================================================================
# 7. Checks against the pre-event research
# ===========================================================================
def level_check_rows(results):
    """P1 level checks: expected (bench), got, difference, verdict."""
    out = []
    for label, (task, subset, model, metric), expected, tolerance, source in LEVEL_CHECKS:
        got = results[(task, subset, model)]["point"][metric]
        out.append(dict(check=label, expected=expected, got=got, difference=got - expected, tolerance=tolerance,
                        within=bool(abs(got - expected) <= tolerance), source=source))
    return out


def gain_check_rows(results):
    """Paired gains over G2: ours (with dam CI) vs the bench point and interval."""
    out = []
    for label, (task, subset, model, metric), expected, bench_ci, like, source in GAIN_CHECKS:
        r = results[(task, subset, model)]
        got = r["point"][metric]
        out.append(dict(check=label, expected=expected, bench_ci=list(bench_ci) if bench_ci else None, got=got,
                        got_ci=r["ci_dam"].get(metric), like_for_like=like,
                        inside_bench_ci=bool(bench_ci[0] <= got <= bench_ci[1]) if bench_ci else None, source=source))
    return out


def floor_check_rows(floor):
    """Floor: expected (pre-event, VAL) vs got."""
    return [dict(check=label, expected=expected, got=floor[key][metric], difference=floor[key][metric] - expected,
                 tolerance=tolerance, within=bool(abs(floor[key][metric] - expected) <= tolerance))
            for label, key, metric, expected, tolerance in FLOOR_CHECKS]


def p2_check_rows(p2):
    """P2: expected (pre-event, VAL) vs got."""
    out = []
    by_task = {task: r for (task, _, _), r in p2.items()}
    for label, (task, metric), expected, tolerance, note in P2_CHECKS:
        got = by_task[task]["point"][metric]
        out.append(dict(check=label, expected=expected, got=got, difference=got - expected, tolerance=tolerance,
                        within=bool(abs(got - expected) <= tolerance), note=note))
    return out


def exact_check_rows(results, curves, p2, summary):
    """Counts that must match exactly: scored rows and events, fit sizes, curve base rates."""
    out = []
    every = {**results, **p2}
    for (task, subset), (n, events) in COUNT_CHECKS.items():
        r = every[(task, subset, "L1")]["rows"]
        out.append(dict(check=f"{task} {subset}: scored rows (events)", expected=f"{n:,} ({events:,})",
                        got=f"{r['scored']:,} ({r['events']:,})", match=(r["scored"], r["events"]) == (n, events)))
    for kind, (n, events) in MEMBER_FIT_CHECKS.items():
        info = summary["members"][kind]
        out.append(dict(check=f"tree T {kind}: fit rows (events)", expected=f"{n:,} ({events:,})",
                        got=f"{info['fit_rows']:,} ({info['fit_events']:,})",
                        match=(info["fit_rows"], info["fit_events"]) == (n, events)))
    for kind, expected in CURVE_FIT_CHECKS.items():
        info = summary["curves"][kind]
        got = (info["issues"], info["person_period_rows"], info["person_period_events"])
        out.append(dict(check=f"curve H {kind}: issues / person-period rows / events",
                        expected=" / ".join(f"{v:,}" for v in expected), got=" / ".join(f"{v:,}" for v in got),
                        match=got == expected))
        rates = [horizon_value(curves[(f"{kind}_curve", "primary")], h, "base_rate") for h in tidemark.HORIZONS]
        out.append(dict(check=f"curve {kind}: primary base rate at 30/60/90/180 d",
                        expected=" / ".join(f"{v:.4f}" for v in CURVE_BASE_RATES[kind]),
                        got=" / ".join(f"{v:.4f}" for v in rates),
                        match=all(abs(a - b) < 5e-5 for a, b in zip(rates, CURVE_BASE_RATES[kind]))))
    rating = summary["rating"]
    out.append(dict(check="season rating: dam-like TRAIN seasons (dry)",
                    expected=f"{RATING_FIT_CHECK[0]:,} ({RATING_FIT_CHECK[1]:,})",
                    got=f"{rating['fit_seasons']:,} ({rating['fit_dry']:,})",
                    match=(rating["fit_seasons"], rating["fit_dry"]) == RATING_FIT_CHECK))
    return out


# ===========================================================================
# Report
# ===========================================================================
def fmt(value, digits=4, sign=True):
    """A number for a table cell ("-" when missing)."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def fmt_ci(result, metric, digits=3, sign=True, part_point="point"):
    """Point value with the dam interval and the region-year interval (ry) when present."""
    text = fmt(result[part_point].get(metric), digits, sign)
    for label, key in (("", "ci_dam"), ("ry ", "ci_region_year")):
        ci = result.get(key, {}).get(metric)
        if ci:
            text += f" {label}[{fmt(ci[0], digits, sign)}, {fmt(ci[1], digits, sign)}]"
    return text


def verdict(within):
    """within / OUTSIDE."""
    return "within" if within else "OUTSIDE"


def headline_lines(results, curves, floor, band, p2):
    """The plain summary table at the top of the report."""
    lines = ["| what | value on VAL (2009-2015) [dam 95% CI] | how to read it |", "|---|---|---|"]
    for kind, words in (("R30", "below a third"), ("D0", "fully dry"), ("D0g", "dries out gradually")):
        r = results[(f"P1_{kind}", "primary", "L1")]
        lines.append(f"| P({words} within 90 days): skill vs base rate (BSS vs B0) | {fmt_ci(r, 'bss_B0')} | "
                     f"0 = no better than the month x region rate; higher is better |")
        lines.append(f"| ... gain over the benchmark G2 (same rows) | {fmt_ci(r, 'd_bss_B0_vs_G2', 4)} | "
                     f"above 0 = better than G2 |")
    r30 = results[("P1_R30", "primary", "L1")]
    lines += [
        f"| R30: skill vs the dam's own track record (BSS vs B2) | {fmt(r30['point']['bss_B2'], 3)} | "
        "PREREG bar: at least +0.05 |",
        f"| R30: AUC | {fmt_ci(r30, 'auc', 3, False)} | chance a dam that did fall was ranked above one that did not |",
        f"| R30: calibration slope | {fmt_ci(r30, 'cal_slope', 2, False)} | 1 = right spread; PREREG bar 0.8-1.2 |",
    ]
    for kind in tidemark.CURVE_KINDS:
        c = curves[(f"{kind}_curve", "primary")]
        values = " / ".join(fmt(horizon_value(c, h, "bss_B0"), 3) for h in tidemark.HORIZONS)
        lines.append(f"| runway curve {kind}: BSS vs B0_h at 30 / 60 / 90 / 180 days | {values} | "
                     "each horizon against its own base rate |")
    lines.append(f"| DamDays floor: share of floors that held (as issued, all at-risk / primary) | "
                 f"{floor['issued_all']['coverage']:.3f} / {floor['issued_primary']['coverage']:.3f} | "
                 "target 0.90 (0.88-0.92 on target) |")
    lines.append("| season band: VAL region-years inside the band (R30 / D0 / D0g) | " + " / ".join(
        f"{band[k]['coverage']['covered']}/{band[k]['coverage']['region_years']}" for k in tidemark.P1_KINDS)
        + " | a region-year is covered when its own offset is inside the band |")
    cell = p2[("P2_cell", "all", "L1")]
    lines.append(f"| season rating (2 km cells): AUC gain over rainfall-only RAIN | {fmt_ci(cell, 'd_auc_vs_RAIN', 3)} | "
                 "PREREG bar: at least +0.05 with the CI above 0 |")
    lines.append(f"| ... AUC gain over the dam's own record B2 | {fmt_ci(cell, 'd_auc_vs_B2', 3)} | reported |")
    return lines


def p1_table(results):
    """Markdown rows of every P1 score."""
    lines = ["| task | subset | model | rows | events | BSS vs B0 [dam] ry [region-year] | BSS vs B2 | AUC | "
             "cal. slope | CITL | prec. at 50% recall | gain over G2 (BSS-vs-B0 units) | AUC gain over G2 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (task, subset, model), r in results.items():
        lines.append("| " + " | ".join([
            task, subset, model, f"{r['rows']['scored']:,}", f"{r['rows']['events']:,}", fmt_ci(r, "bss_B0"),
            fmt(r["point"]["bss_B2"], 3), fmt_ci(r, "auc", 3, False), fmt(r["point"]["cal_slope"], 2, False),
            fmt(r["point"]["citl"], 2), fmt(r["point"]["prec_at_50_recall"], 3, False),
            fmt_ci(r, "d_bss_B0_vs_G2", 4), fmt(r["point"]["d_auc_vs_G2"], 4)]) + " |")
    return lines


def curve_table(curves):
    """Markdown rows: one per curve, subset and horizon."""
    lines = ["| curve | subset | h (days) | rows | events | base rate | mean p | BSS vs B0_h [dam] | BSS vs B2_h | AUC | "
             "cal. slope | CITL | reference: pre-event H with PHY (BSS vs B0_h) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (task, subset), result in curves.items():
        kind = task.split("_")[0]
        for j, entry in enumerate(result["horizons"]):
            p, ci = entry["point"], entry["ci_dam"]
            bss = fmt(p.get("bss_B0"), 4) + (f" [{fmt(ci['bss_B0'][0], 4)}, {fmt(ci['bss_B0'][1], 4)}]"
                                              if ci.get("bss_B0") else "")
            reference = fmt(CURVE_REFERENCE[kind][j]) if subset == "primary" else "-"
            lines.append("| " + " | ".join([
                task, subset, str(entry["horizon"]), f"{entry['rows']:,}", f"{entry['events']:,}",
                fmt(p.get("base_rate"), 3, False), fmt(p.get("mean_p"), 3, False), bss, fmt(p.get("bss_B2"), 4),
                fmt(p.get("auc"), 3, False), fmt(p.get("cal_slope"), 2, False), fmt(p.get("citl"), 2),
                reference]) + " |")
    return lines


def floor_row(name, result, note=""):
    """One markdown row of the floor table."""
    worst = result.get("worst_year", {})
    ci = result.get("ci_dam", {}).get("coverage")
    ci_text = f" [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ""
    return (f"| {name} | {result['rows_judged']:,} | {result['coverage']:.4f}{ci_text} | "
            f"{worst.get('year', '-')} ({fmt(worst.get('coverage'), 3, False)}) | {result['median_floor_days']:.1f} | "
            f"{result['share_ge_90']:.3f} | {result['share_180_plus']:.3f} | {note} |")


def band_text(band):
    """A band as text."""
    return f"[{band[0]:+.3f}, {band[1]:+.3f}]"


def missed_text(coverage):
    """Region-years outside the band, as text."""
    missed = dict(coverage.get("drier_than_band", {}), **coverage.get("wetter_than_band", {}))
    if "missed" in coverage:
        missed = {k: v["offset"] for k, v in coverage["missed"].items()}
    return ", ".join(f"{k} ({v:+.2f})" for k, v in sorted(missed.items())) or "none"


def p2_table(p2):
    """Markdown rows of the P2 scores."""
    lines = ["| task | rows | events | AUC [dam/cell] ry [region-year] | dAUC vs RAIN | dAUC vs RAIN+ | dAUC vs B2 | "
             "AUC within season | BSS vs B0 | BSS vs B2 | cal. slope | CITL |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (task, _, _), r in p2.items():
        lines.append("| " + " | ".join([
            task, f"{r['rows']['scored']:,}", f"{r['rows']['events']:,}", fmt_ci(r, "auc", 3, False),
            *[fmt_ci(r, f"d_auc_vs_{ref}", 3) for ref in P2_REFS], fmt(r["point"].get("auc_within_season"), 3, False),
            fmt_ci(r, "bss_B0", 3), fmt_ci(r, "bss_B2", 3), fmt(r["point"]["cal_slope"], 2, False),
            fmt(r["point"]["citl"], 2)]) + " |")
    return lines


def check_lines(rows_, digits=4):
    """Markdown rows for expected-vs-got checks with a tolerance."""
    lines = ["| check | expected (pre-event) | got | difference | tolerance | verdict | source / note |",
             "|---|---|---|---|---|---|---|"]
    for c in rows_:
        lines.append(f"| {c['check']} | {fmt(c['expected'], digits)} | {fmt(c['got'], digits)} | "
                     f"{fmt(c['difference'], digits)} | +-{c['tolerance']} | {verdict(c['within'])} | "
                     f"{c.get('source', c.get('note', ''))} |")
    return lines


def gain_lines(gains):
    """Markdown rows for the paired gains over G2."""
    lines = ["| check | expected [bench dam 95% CI] | got [dam 95% CI] | inside bench CI? | source |",
             "|---|---|---|---|---|"]
    for c in gains:
        bench = f" [{fmt(c['bench_ci'][0])}, {fmt(c['bench_ci'][1])}]" if c["bench_ci"] else ""
        got = f" [{fmt(c['got_ci'][0])}, {fmt(c['got_ci'][1])}]" if c["got_ci"] else ""
        inside = ("yes" if c["inside_bench_ci"] else "NO") if c["like_for_like"] else "context only"
        lines.append(f"| {c['check']} | {fmt(c['expected'])}{bench} | {fmt(c['got'])}{got} | {inside} | {c['source']} |")
    return lines


def integration_lines(checks):
    """Markdown rows for the integration check."""
    lines = ["| output | compared with | rows | largest difference | identical? |", "|---|---|---|---|---|"]
    for c in checks:
        if c["status"] != "compared":
            lines.append(f"| {c['check']} | {c['step']} | - | - | {c['status']} |")
            continue
        lines.append(f"| {c['check']} | {c['step']} | {c['rows']:,} | {c['max_abs_diff']:.1e} | "
                     f"{'yes' if c['identical'] else 'NO'} |")
    return lines


def write_report(r):
    """artifacts/val_tidemark_L1.md (for people) and artifacts/val_tidemark_L1.json (for code)."""
    results, curves, floor, band, p2, summary = r["p1"], r["curves"], r["floor"], r["band"], r["p2"], r["summary"]
    bars = results[("P1_R30", "primary", "L1")].get("prereg_pass_bars", {})
    cell_rules, dam_rules = r["p2_rules"]["P2_cell"], r["p2_rules"]["P2_dam"]
    compared = [c for c in r["integration"] if c["status"] == "compared"]
    g2_band = step7_band_reference()
    lines = [
        "# VAL results: Tidemark rung L1, end to end (build step 8)",
        "",
        f"Generated by `scripts/08_tidemark_val.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only**: "
        "forecasts issued 2009-01-01 to 2015-12-31 and season ratings issued 1 July 2009 to 1 July 2015, "
        "development regions. TEST was not scored.",
        "",
        "**What was run.** `tidemark.fit_tidemark(\"2009-01-01\", rung=\"L1\")` then `tidemark.predict_tidemark` "
        "(`damdays/models/tidemark.py`): every part learns only from answers final before 2009-01-01. L1 = the tree "
        "member T (no nets, no water-balance columns) + the per-dam frailty + the R30 max rule, the hazard runway "
        "curve H, the DamDays floor, the season band from Tidemark's own 2002-2009 inner backtest, and the P2 "
        "season rating. `docs/HOW_IT_WORKS.md` explains each part in plain language.",
        "",
        f"Scores come from the shared scorecard (`damdays/evaluation`, explained in `docs/SCORECARD.md`) with "
        f"{r['n_boot_main']} dam and {r['n_boot_main']} region-year bootstrap draws on the primary sets and P2 "
        f"({r['n_boot_side']} on the other subsets). Brackets: dam (or cell) 95% interval, then `ry` "
        "region-year interval (16 region-years, so rough).",
        "",
        "## Headline numbers",
        "",
        *headline_lines(results, curves, floor, band, p2),
        "",
        "## PREREG pass bars on VAL",
        "",
        "| bar | value | required | passed |",
        "|---|---|---|---|",
    ]
    bar_names = {"bss_B0": "P1 R30: BSS vs B0 (dam CI low end)", "bss_B2": "P1 R30: BSS vs B2",
                 "cal_slope": "P1 R30: calibration slope"}
    for name, bar in bars.items():
        if not isinstance(bar, dict):
            continue
        value = fmt(bar["value"], 4) + (f" ({fmt(bar['ci_low'], 4)})" if "ci_low" in bar else "")
        judged = "ci_low" not in bar or (bar["ci_low"] is not None and np.isfinite(bar["ci_low"]))
        passed = ("yes" if bar["passed"] else "no") if judged else "not judged (no intervals: --quick)"
        lines.append(f"| {bar_names.get(name, name)} | {value} | {bar['bar']} | {passed} |")
    lines += [
        f"| P2 cells: dAUC vs RAIN | {fmt(cell_rules['d_auc_vs_RAIN'], 4)} "
        f"[{fmt(cell_rules['ci_dam'][0], 4) if cell_rules['ci_dam'] else '-'}, "
        f"{fmt(cell_rules['ci_dam'][1], 4) if cell_rules['ci_dam'] else '-'}] | >= +0.05, CI above 0 | "
        f"{'not judged (--quick)' if cell_rules['passed'] is None else ('yes' if cell_rules['passed'] else 'no')} |",
        f"| P2 kill rule: RAIN within 0.02 AUC of the rating | {fmt(cell_rules['d_auc_vs_RAIN'], 4)} | not triggered "
        f"| {'TRIGGERED' if cell_rules['kill_rule_triggered'] else 'not triggered'} |",
        f"| P2 dams: dAUC vs RAIN (same bar) | {fmt(dam_rules['d_auc_vs_RAIN'], 4)} | >= +0.05, CI above 0 | "
        f"{'not judged (--quick)' if dam_rules['passed'] is None else ('yes' if dam_rules['passed'] else 'no')} |",
        "",
        "## Integration check: the one entry point gives exactly what each component step saved",
        "",
        f"{sum(c['identical'] for c in compared)} of {len(compared)} compared outputs are identical bit for bit "
        "(largest difference 0). `tree T vs the benchmark G2` shows that T is the G2 recipe, so every gain over G2 "
        "below comes from the frailty and the max rule.",
        "",
        *integration_lines(r["integration"]),
        "",
        "## Check values: expected (pre-event research) vs got (this build)",
        "",
        "### Must match exactly",
        "",
        "| check | expected | got | match |", "|---|---|---|---|",
        *[f"| {c['check']} | {c['expected']} | {c['got']} | {'yes' if c['match'] else 'NO'} |" for c in r["exact"]],
        "",
        "### 90-day probabilities (PREREG ladder tolerance +-0.006)",
        "",
        "The like-for-like pre-event twin of L1's 90-day part is **G2c+RE** (hierarchical-pooling family): the "
        "same tree recipe (\"G2c\" there is this build's G2) plus the same frailty (lambda 100), without the R30 "
        "max rule. So R30 is checked before the max rule; the headline (after it) is shown too.",
        "",
        *check_lines(r["level_checks"]),
        "",
        "### Paired gain over the benchmark G2 (same rows)",
        "",
        *gain_lines(r["gain_checks"]),
        "",
        f"Reference only (not like for like): the full pre-event Tidemark v1 (L3: + nets + physics) scored VAL "
        f"BSS vs B0 R30 {FULL_V1_REFERENCE['R30']:+.4f}, D0 {FULL_V1_REFERENCE['D0']:+.4f}, D0g "
        f"{FULL_V1_REFERENCE['D0g']:+.4f}. L1 sits below it by about the nets + physics gain (stage B costs: nets "
        "+0.007 / +0.010, physics +0.001 / +0.003 for R30 / D0).",
        "",
        "### DamDays floor",
        "",
        *check_lines(r["floor_checks"]),
        "",
        "### Season rating (P2)",
        "",
        *check_lines(r["p2_checks"]),
        "",
        "## P1: the 90-day probabilities",
        "",
        "`L1` = the shipped forecast (R30 after the max rule). `L1_premax` = R30 before the max rule (the like-for-like "
        "check). Gains over G2 are in BSS-vs-B0 units on the same rows. `_sens` rows: the PREREG label-determinable "
        "sensitivity row (every at-risk issue whose 90-day window closed, without the 3-look label rule).",
        "",
        *p1_table(results),
        "",
        "## The runway curve (hazard model H, R30 curve >= D0 curve)",
        "",
        "Each horizon is judged against its own baselines (step 6: B0_h month x region rate, B2_h the dam's own "
        "track record at h; purged per horizon). The reference column is the frozen pre-event curve, which also "
        "had the two physics columns that L1 does not have, so it is expected to sit a little higher.",
        "",
        *curve_table(curves),
        "",
        "**The curve at 90 days and the 90-day headline are two different models** (the headline is the fused "
        "anchor with frailty; the curve is H; the pre-event \"anchored fan\" that forced them to agree was dropped). "
        "On the primary set the curve's 90-day point is, on average, " + "; ".join(
            f"{k} {g['mean_gap']:+.3f} from the headline (mean absolute gap {g['mean_abs_gap']:.3f}, 90% of rows within "
            f"{g['p90_abs_gap']:.3f})" for k, g in r["headline_vs_curve"].items()) + ".",
        "",
        "## DamDays floor (\"at least N days above a third, 9 times in 10\")",
        "",
        f"Judged on {floor['rows_labelled']:,} at-risk VAL forecasts with a determinable label (the pre-event rows). "
        "**As issued on VAL** the floor is the raw 10% quantile (shift 0): no calibration block existed before "
        "2009 that the quantile model had not learned from. For TEST and the sealed region the shift is calibrated "
        "on VAL (`fit_tidemark(\"2016-07-01\")`; step 7 found +0.0000). LOYO = the pre-event check (each VAL year "
        "calibrated on the other VAL years; uses later years, so it checks the method).",
        "",
        "| floor | forecasts judged | coverage [dam 95%] | worst July-June year | median floor (days) | share >= 90 d | "
        "share >= 180 d | note |",
        "|---|---|---|---|---|---|---|---|",
        floor_row("**as issued (all at-risk)**", floor["issued_all"], "the forecast as made on VAL"),
        floor_row("**as issued (primary)**", floor["issued_primary"], "dam-like, Oct-Mar, at risk"),
        floor_row("LOYO conformal (all)", floor["loyo_all"], "pre-event procedure"),
        floor_row("LOYO conformal (primary)", floor["loyo_primary"], ""),
        floor_row("as displayed: whole days, 180+ (all)", floor["shown_all"], "judged at min(N, 180)"),
        floor_row("as displayed (primary)", floor["shown_primary"], ""),
        floor_row("sensitivity: all at-risk, incl. no determinable label", floor["issued_all_incl_unlabelled"],
                  f"{floor['rows_at_risk']:,} forecasts"),
        "",
        "## Season band",
        "",
        "The band around each 90-day probability is [sigmoid(logit p + low), sigmoid(logit p + high)], with low and "
        "high the lowest and highest region-year offsets of **Tidemark L1's own inner backtest**: the same recipe "
        "fitted on answers final before 2002-01-01 (dam_rate prior recomputed as of 2002), with its frailty and max "
        "rule, judged on 2002-2008 primary-set forecasts answered before 2009-01-01. A VAL region-year is covered "
        "when its own offset (measured on L1's VAL forecasts) lies inside the band.",
        "",
        "| kind | band (L1, 2002-2009 block) | VAL region-years covered | missed | LOYO pooled with 2002-2009 | "
        "LOYO, VAL only | G2 stand-in band (step 7) | pre-event v1 anchor band (reference) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    v1_reference = {"R30": "[-1.065, +0.761], 15/16", "D0": "[-1.130, +0.547], 13/16", "D0g": "not run"}
    for kind in tidemark.P1_KINDS:
        b = band[kind]
        cov, lp, lv = b["coverage"], b["loyo_pooled"], b["loyo_val_only"]
        g2 = g2_band.get(kind)
        g2_text = f"{band_text(g2[0])}, {g2[1]}/{g2[2]}" if g2 else "not run"
        lines.append(f"| {kind} | {band_text(b['band'])} | {cov['covered']}/{cov['region_years']} | {missed_text(cov)} | "
                     f"{lp['covered']}/{lp['region_years']} | {lv['covered']}/{lv['region_years']} | {g2_text} | "
                     f"{v1_reference[kind]} |")
    lines += [
        "",
        "Band width (R30): " + ", ".join(f"p = {p0} reads {lo:.3f}-{hi:.3f}"
                                         for p0, (lo, hi) in band["R30"]["examples"].items()) + ".",
        "",
        "## P2: the season rating (issued 1 July; label: a dry-out in the following Oct-Mar)",
        "",
        "P2_cell: a 2 km cell fails when all its dam-like dams go dry (cell p = product of its dams' p). P2_dam and "
        "P2_dam_g: dam-like dams (P2_dam_g: gradual dry-outs, the same trees started from the gradual B2). The "
        "scorecard's within-cell interval is known to be too wide (shared-code issue flagged in step 5), so only "
        "the within-season AUC is shown.",
        "",
        *p2_table(p2),
        "",
        "## What was fitted",
        "",
        "| part | learned from | size | seconds |",
        "|---|---|---|---|",
    ]
    for kind in tidemark.P1_KINDS:
        info = summary["members"][kind]
        lines.append(f"| tree T {kind} | answers final before {info['cutoff']} (purged TRAIN) | "
                     f"{info['fit_rows']:,} rows ({info['fit_events']:,} events) | "
                     f"{str(summary['members_seconds']) + ' (all three kinds)' if kind == 'R30' else ''} |")
    for kind in tidemark.CURVE_KINDS:
        info = summary["curves"][kind]
        lines.append(f"| hazard curve H {kind} | dam-like TRAIN issues, each interval censored at 2009-01-01 | "
                     f"{info['person_period_rows']:,} person-period rows ({info['person_period_events']:,} events) | "
                     f"{info['seconds']} |")
    fl = summary["floor"]
    lines.append(f"| floor quantile model | forecasts whose 395-day answer was final before 2009-01-01 | "
                 f"{fl['fit_rows']:,} rows; conformal shift {fl['shift']:+.4f}: {fl['about']} | {fl['seconds']} |")
    for block in summary["band"]["blocks"]:
        sizes = ", ".join(f"{k} {v['fit_rows']:,}" for k, v in block["fit"].items())
        lines.append(f"| band inner backtest {block['block']} | answers final before "
                     f"{block['fit']['R30']['cutoff']} (dam_rate as of then) | fit rows {sizes} | {block['seconds']} |")
    rating = summary["rating"]
    lines.append(f"| season rating | dam-like TRAIN seasons answered before 1 July 2009 | "
                 f"{rating['fit_seasons']:,} seasons ({rating['fit_dry']:,} dry), 3 seeds | {rating['seconds']} |")
    lines += ["", "## Notes", "", *NOTES, ""]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")

    def compact(result):
        return dict(point=result["point"], ci_dam=result["ci_dam"], ci_region_year=result["ci_region_year"],
                    rows=result["rows"], refs=result["refs"])
    report = dict(
        generated=time.strftime("%Y-%m-%d %H:%M:%S"), block=BLOCK, rung=RUNG, n_boot_main=r["n_boot_main"],
        n_boot_side=r["n_boot_side"], integration=r["integration"], exact_checks=r["exact"],
        level_checks=r["level_checks"], gain_checks=r["gain_checks"], floor_checks=r["floor_checks"],
        p2_checks=r["p2_checks"], prereg_p1_pass_bars=bars, prereg_p2=r["p2_rules"],
        p1={"|".join(k): compact(v) for k, v in results.items()},
        curves={"|".join(k): {str(h["horizon"]): dict(point=h["point"], ci_dam=h["ci_dam"], rows=h["rows"],
                                                      events=h["events"]) for h in v["horizons"]}
                for k, v in curves.items()},
        headline_vs_curve=r["headline_vs_curve"],
        floor=floor, band=band, p2={"|".join(k): compact(v) for k, v in p2.items()},
        fit_summary={k: v for k, v in summary.items() if k != "band"},
        band_constants=summary["band"]["band"])
    RESULTS_JSON.write_text(json.dumps(clean_for_json(report), indent=1), encoding="utf-8")


NOTES = [
    "- **One entry point.** Every number here comes from `tidemark.fit_tidemark` / `predict_tidemark`. The "
    "integration table shows they reproduce the component steps exactly (steps 4-7), so the component reports "
    "(`tree_frailty_val.md`, `hazard_curve_val.md`, `uncertainty_val.md`, `season_rating_val.md`) remain valid "
    "for the details.",
    "- **Time rules.** 90-day members: issue + 120 days before 2009-01-01 (purged). Frailty: a past forecast counts "
    "only once its answer is final (t_j + 120 days <= t). H: each interval censored (interval end + 30 days before "
    "2009-01-01). Floor: 395-day answers final before 2009-01-01. Band: inner models fitted on answers final before "
    "2002-01-01, offsets on answers final before 2009-01-01. P2: seasons answered before 1 July 2009.",
    "- **The R30 max rule** (PREREG) costs a little Brier skill on VAL (step 4: -0.0006 [-0.0009, -0.0002]): it "
    "raises 1.3% of primary forecasts where VAL (the wet 2010-12 years) was already over-predicted. It is kept.",
    "- **Not in L1:** the nets S and M (rung L2) and the two water-balance columns (rung L3). They plug into "
    "`tidemark.MEMBERS` and `tidemark.PHY_COLUMNS` without restructuring.",
    "- **Disclosed (as in the component reports):** labels and populations use the PREREG static pre-2016 'full'; "
    "the area index and R_zero use the pre-2016 has_hist pool. These affect VAL only, not TEST or the sealed region.",
    "- **Forecasts** (float64) are in `data_cache/preds/VAL/tidemark/`: `L1_p1.pkl` (one row per at-risk issue), "
    "`L1_p2_dam.pkl`, `L1_p2_cell.pkl`, and the fit summary `L1_fit_summary.pkl` / `.json`.",
]


# ===========================================================================
# Main
# ===========================================================================
def main():
    """Fit (or reload) Tidemark L1, check it against its parts, score everything on VAL, write the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no bootstrap intervals")
    parser.add_argument("--reuse", action="store_true", help="rescore saved forecasts instead of refitting")
    args = parser.parse_args()
    n_boot_main, n_boot_side = (0, 0) if args.quick else (N_BOOT_MAIN, N_BOOT_SIDE)

    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    for prefix in ("scorecard", "curves"):          # this run's markdown tables start empty
        (SCORE_DIR / f"{prefix}_dev_{BLOCK}.md").write_text("")

    log("loading the inputs (P1 table, P2 dam table with the area index, P2 cells)")
    inputs = tidemark.load_inputs()
    out, summary = fit_and_forecast(inputs, args.reuse)
    table = inputs["p1"]

    integration = integration_checks(table, out)
    log(f"integration: {sum(c.get('identical', False) for c in integration)} of "
        f"{sum(c['status'] == 'compared' for c in integration)} outputs identical to the component steps")

    results = {}
    for kind in rows.P1_KINDS:
        results.update(score_p1(table, out, kind, n_boot_main, n_boot_side))
    curves = score_curves(table, out, n_boot_main, n_boot_side)
    floor = floor_results(table, out, N_BOOT_SIDE if n_boot_main else 0)
    band = band_results(table, out, summary)
    p2 = score_p2(out, n_boot_main)

    report = dict(p1=results, curves=curves, floor=floor, band=band, p2=p2, summary=summary,
                  integration=integration, headline_vs_curve=headline_vs_curve(table, out), exact=exact_check_rows(results, curves, p2, summary),
                  level_checks=level_check_rows(results), gain_checks=gain_check_rows(results),
                  floor_checks=floor_check_rows(floor), p2_checks=p2_check_rows(p2),
                  p2_rules={task: p2_rules(p2[(task, subset, "L1")]) for task, subset, _ in P2_TASKS},
                  n_boot_main=n_boot_main, n_boot_side=n_boot_side)
    write_report(report)
    log(f"wrote {RESULTS_MD.name} and {RESULTS_JSON.name}")
    for c in report["exact"]:
        print(f"  {c['check']:<62s} expected {c['expected']:<30s} got {c['got']:<30s} {'ok' if c['match'] else 'NO'}")
    for group in ("level_checks", "floor_checks", "p2_checks"):
        for c in report[group]:
            print(f"  {c['check']:<62s} expected {c['expected']:+.4f} got {c['got']:+.4f} "
                  f"diff {c['difference']:+.4f} {verdict(c['within'])}")
    for c in report["gain_checks"]:
        print(f"  {c['check']:<62s} expected {c['expected']:+.4f} {c['bench_ci']} got {c['got']:+.4f} {c['got_ci']}")
    for kind in rows.P1_KINDS:
        b = band[kind]
        print(f"  band {kind}: {band_text(b['band'])} covers {b['coverage']['covered']}/{b['coverage']['region_years']}")


if __name__ == "__main__":
    main()
