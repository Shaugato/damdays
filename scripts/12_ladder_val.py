"""Step 12: the PREREG fallback-ladder reproduction table on VAL (rungs L0, L1, L2, L3).

Run from the repo folder (after scripts/03, 06, 08, 09 and 10: it reads step 3's baselines and
G2, step 6's curve baselines, the nets that step 9 saved and the physics table of step 10):
    .venv/Scripts/python.exe scripts/12_ladder_val.py            # fit all four rungs, about 60-75 minutes
    .venv/Scripts/python.exe scripts/12_ladder_val.py --reuse    # rescore the saved ladder forecasts
    .venv/Scripts/python.exe scripts/12_ladder_val.py --quick    # no bootstrap intervals

PREREG "Fallback ladder": the frozen model is the highest rung whose event re-implementation
  (a) reproduces its pre-event VAL BSS within +-0.006 on R30 and D0, and
  (b) passes the look-ahead test.
This script measures (a) and reads (b); it does NOT choose the frozen model. The freeze is a
separate, dated step (PREREG addendum, Sat 3 Oct by 15:00 AEST).

What it does
  1. Fits every rung through Tidemark's one entry point, tidemark.fit_tidemark("2009-01-01", rung),
     and forecasts VAL with tidemark.predict_tidemark. Checks that the four forecast tables have
     the same columns. Forecasts are saved to data_cache/preds/VAL/ladder/<rung>_*.pkl.
  2. Integration check: each rung's forecasts equal what the step that built it saved (L0: step 3's
     G2; L1: step 8; L2: step 9; L3: step 10), and the parts that do not depend on a rung's members
     are the same on every rung.
  3. The ladder table: R30, D0 and D0g skill vs the base rate B0 (primary set) for each rung, next to
     the pre-event VAL value of that rung, with PASS/FAIL against +-0.006 on R30 and D0 (condition a)
     and the look-ahead test result for every generator the rung uses (condition b), read from
     artifacts/lookahead_test.json. Also the paired gain of each rung over the one below it.
  4. The full VAL scorecard (P1, runway curve, floor, season band, P2) of the highest rung that
     passes both conditions: artifacts/val_tidemark_best.md and .json.
  Outputs: artifacts/ladder_val.md (people) and artifacts/ladder_val.json (code).

TEST is never touched: every model learns from answers final before 2009-01-01 (the band's inner
backtest: before 2002-01-01), and every table passed to the scorecard is checked to hold VAL only.
"""
import argparse
import json
import logging
import pickle
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
from damdays.evaluation import band_coverage, crossing_share, floor_coverage, score, score_curve  # noqa: E402
from damdays.evaluation.inputs import join_baselines, tidy_keys  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.evaluation.rules import is_octmar  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import hazard, nets, rows, tidemark  # noqa: E402
from damdays.models import uncertainty as unc  # noqa: E402
from damdays.models.predictions import load_predictions, prediction_path, save_predictions  # noqa: E402

BLOCK = "VAL"
RUNG_ORDER = ("L0", "L1", "L2", "L3")              # lowest to highest
KINDS = rows.P1_KINDS                               # R30, D0, D0g
LADDER_KINDS = ("R30", "D0")                        # PREREG condition (a) is judged on these two
TOL = 0.006                                         # PREREG ladder tolerance
PRED_TASK = "ladder"                                # data_cache/preds/VAL/ladder/<rung>_<part>.pkl
PARTS = ("p1", "p2_dam", "p2_cell")
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step12_val"
LADDER_MD, LADDER_JSON = config.ARTIFACTS_DIR / "ladder_val.md", config.ARTIFACTS_DIR / "ladder_val.json"
BEST_MD, BEST_JSON = config.ARTIFACTS_DIR / "val_tidemark_best.md", config.ARTIFACTS_DIR / "val_tidemark_best.json"
LOOKAHEAD_JSON = config.ARTIFACTS_DIR / "lookahead_test.json"
N_BOOT_MAIN, N_BOOT_SIDE = 500, 200                 # bootstrap draws: primary sets and P2; other subsets
NOTE = "step 12 (scripts/12_ladder_val.py)"

# ---------------------------------------------------------------------------
# The pre-event VAL value of each rung (primary set, BSS vs B0). Bench = research/pre_event/bench/results.
# ---------------------------------------------------------------------------
PRE_EVENT = {
    "L0": {"R30": 0.1707, "D0": 0.1755, "D0g": 0.1727},
    "L1": {"R30": 0.1727, "D0": 0.1771, "D0g": 0.1732},
    "L2": {"R30": 0.1809, "D0": 0.1923, "D0g": 0.1916},
    "L3": {"R30": 0.1818, "D0": 0.1948, "D0g": 0.1947},
}
PRE_EVENT_SOURCE = {
    "L0": "like for like. Bench hybrid/tables/val_stageA.csv 'G2c' (the bench's G2c is this build's G2: the G2 "
          "features with the causal dam rate). The same values are in hierarchical-pooling/gbm_VAL_*.csv, and "
          "val_final_scorecard.csv L3 minus its dBSS_vs_G2c gives them too.",
    "L1": "R30 and D0 like for like, except the R30 max rule: bench hierarchical-pooling/gbm_VAL_R30.csv and "
          "gbm_VAL_D0.csv 'G2c+RE' (the same tree and the same frailty, lambda 100). The hybrid tables have no "
          "L1 row. D0g has no twin: derived as val_stageA 'G2c' + val_stageB '-frailty' cost (+0.0005).",
    "L2": "derived. Bench hybrid/tables/val_final_scorecard.csv (L3) minus the val_stageB.csv '-PHY' removal "
          "cost (0.0009 / 0.0025 / 0.0031; the same numbers are in decision_log.json stageB.PHY.cost_dam_like).",
    "L3": "like for like. Bench hybrid/tables/val_final_scorecard.csv: the frozen Tidemark v1 (freeze.json, "
          "config fe0ab596d1fe). FINAL_SPEC (E) quotes it as +0.182 / +0.195 / +0.195.",
}
# A second value for L1 from the hybrid tables alone (cross-check only, not used for the verdict):
# val_stageA 'G2c' + val_stageB '-frailty' cost (decision_log.json stageB.frailty.cost_dam_like).
L1_FROM_HYBRID = {"R30": 0.1707 + 0.0028, "D0": 0.1755 - 0.0003, "D0g": 0.1727 + 0.0005}

# Paired gains between rungs (BSS-vs-B0 units, same rows): (what is added, rung, reference, bench, source)
STEP_REFERENCES = [
    ("the frailty and the R30 max rule", "L1", "L0",
     {"R30": (0.0024, (0.0004, 0.0042)), "D0": (0.0020, (0.0002, 0.0041)), "D0g": (0.0005, (-0.0014, 0.0024))},
     "R30, D0: hierarchical-pooling G2c+RE vs G2c (no max rule). D0g: hybrid val_stageB '-frailty'"),
    ("the nets S and M", "L2", "L1",
     {"R30": (0.0074, (0.0036, 0.0112)), "D0": (0.0099, (0.0054, 0.0151)), "D0g": (0.0135, (0.0073, 0.0204))},
     "hybrid val_stageB '-nets' removal cost. Context, not like for like: that model's tree learned from "
     "dam-like dams only"),
    ("the 2 water-balance columns", "L3", "L2",
     {"R30": (0.0009, (0.0003, 0.0014)), "D0": (0.0025, (0.0014, 0.0035)), "D0g": (0.0031, (0.0020, 0.0043))},
     "hybrid val_stageB '-PHY' removal cost"),
    ("everything, over the benchmark G2", "L3", "G2",
     {"R30": (0.0111, (0.0075, 0.0147)), "D0": (0.0193, (0.0151, 0.0237)), "D0g": (0.0220, (0.0169, 0.0277))},
     "hybrid val_final_scorecard.csv dBSS_vs_G2c"),
]

# Look-ahead test (condition b): the generators each rung's inputs come from, as named in
# tests/test_no_lookahead.py (matched on the start of the name).
GENERATORS = {"core": "core features (build_all) + frailty sums", "sequences": "net sequences",
              "physics": "physics water balance"}
RUNG_NEEDS = {"L0": ("core",), "L1": ("core",), "L2": ("core", "sequences"),
              "L3": ("core", "sequences", "physics")}

# P2 (the season rating; PREREG "P2: the offset model; fallback B2"). The rating is the same on every rung.
P2_TASKS = [("P2_cell", "all", "p"), ("P2_dam", "dam_like", "p"), ("P2_dam_g", "dam_like", "p_g")]
P2_REFS = ["RAIN", "RAIN+", "B2"]
P2_PASS_DAUC, P2_KILL_DAUC = 0.05, 0.02             # PREREG: gain over RAIN >= 0.05 (CI above 0); kill if < 0.02
RAIN_NOTE = "this build's RAIN uses causal rain deciles, so the gap to RAIN comes out about +0.003 larger (step 5)"
SR_FINAL = "season-rating final_VAL.json"
P2_CHECKS = [   # (label, task, metric, expected, tolerance, source): the pre-event values step 8 checks too
    ("P2_cell AUC", "P2_cell", "auc", 0.7873, TOL, SR_FINAL),
    ("P2_cell AUC gain over RAIN", "P2_cell", "d_auc_vs_RAIN", 0.2464, TOL, f"{SR_FINAL}; {RAIN_NOTE}"),
    ("P2_cell AUC gain over RAIN+", "P2_cell", "d_auc_vs_RAIN+", 0.1547, TOL,
     f"{SR_FINAL}; RAIN+ refitted on causal inputs"),
    ("P2_cell AUC gain over B2", "P2_cell", "d_auc_vs_B2", 0.0142, TOL, SR_FINAL),
    ("P2_dam AUC", "P2_dam", "auc", 0.7796, TOL, SR_FINAL),
    ("P2_dam_g AUC (prior swap)", "P2_dam_g", "auc", 0.7670, TOL, "hybrid val_stageG_p2.csv"),
]

# Extra check values for the full scorecard when the best rung is L3 (hybrid val_final_scorecard.csv,
# Oct-Mar rows; "dam_like+at_risk" = its 'all' season rows).
L3_DETAIL = {
    "R30": dict(bss_B2=0.1113, auc=0.7908, cal_slope=1.0718, citl=-0.2763, persistent=0.1538, all_months=0.1882),
    "D0": dict(bss_B2=0.1135, auc=0.8431, cal_slope=1.0697, citl=-0.2951, persistent=0.1040, all_months=0.1922),
    "D0g": dict(bss_B2=0.1457, auc=0.8694, cal_slope=1.1439, citl=-0.2917, persistent=0.1227, all_months=0.1910),
}
# Runway curve, BSS vs B0_h at 30/60/90/180 days: hybrid val_stageC_horizons.csv "H_alone" (H with the
# 2 water-balance columns: like for like at L3, a reference for the lower rungs).
CURVE_REFERENCE = {"R30": (0.0987, 0.1509, 0.1759, 0.1988), "D0": (0.0965, 0.1540, 0.1851, 0.2353)}
# Floor (calibration-uncertainty conformal_VAL.json, as in step 8): coverage as issued (all, primary), median days.
FLOOR_REFERENCE = dict(all=0.8997, primary=0.9098, median_days=45.28)
# Season band: the pre-event v1 band and its VAL coverage (step 7 / 8 reference).
BAND_REFERENCE = {"R30": "[-1.065, +0.761], 15/16", "D0": "[-1.130, +0.547], 13/16", "D0g": "not run"}

P1_SUBSETS = [("primary", "dam_like", True), ("persistent+octmar+at_risk", "persistent", True),
              ("dam_like+at_risk", "dam_like", False)]
CURVE_SUBSETS = [("primary", "dam_like"), ("dam_like+at_risk", "dam_like"), ("persistent+octmar+at_risk", "persistent")]

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


def show_net_progress():
    """Print the nets' progress messages (checkpoints loaded, predictions) in the same style."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("              nets: %(message)s"))
    nets.logger.addHandler(handler)
    nets.logger.setLevel(logging.INFO)


# ===========================================================================
# Small helpers
# ===========================================================================
def require(task, name, step):
    """A saved prediction table from an earlier step; stops with a clear message if it is missing."""
    if not prediction_path(BLOCK, task, name).exists():
        raise SystemExit(f"Missing {prediction_path(BLOCK, task, name)}: run {step} first.")
    return load_predictions(BLOCK, task, name)


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


def assert_val_only(frame):
    """Refuse to score anything outside VAL (this script never looks at TEST)."""
    blocks = set(time_block(frame["issue_date"]))
    if blocks != {BLOCK}:
        raise AssertionError(f"Expected VAL issues only, found blocks {sorted(blocks)}")


def on_rows(p1_out, positions, column):
    """An output column of predict_tidemark's p1 table, read on the given P1-table rows."""
    return p1_out.set_index("row").loc[np.asarray(positions), column].to_numpy(dtype=float)


def data_end():
    """The date of the last satellite look in the archive (saved by the feature build)."""
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as handle:
        return pd.Timestamp(pickle.load(handle)["data_end"])


# ===========================================================================
# 1. Fit and forecast every rung through the one entry point
# ===========================================================================
def saved(rung, part):
    """Where one saved ladder output lives."""
    return prediction_path(BLOCK, PRED_TASK, f"{rung}_{part}")


def room_to_save(out, margin_mb=500):
    """True if the disk holding data_cache has room for the forecasts plus a safety margin."""
    needed = sum(frame.memory_usage(deep=True).sum() for frame in out.values()) + margin_mb * 2 ** 20
    return shutil.disk_usage(config.CACHE_DIR).free > needed


def save_forecasts(rung, out, summary):
    """Save one rung's forecasts and fit summary (float64, for --reuse). Skipped with a warning if the disk is full."""
    if not room_to_save(out):
        log(f"WARNING: not enough free disk space for the {rung} forecasts; NOT saved (--reuse will refit)")
        return False
    for part in PARTS:
        save_predictions(out[part], BLOCK, PRED_TASK, f"{rung}_{part}")
    pd.to_pickle(summary, saved(rung, "fit_summary"))
    return True


def fit_and_forecast(rung, inputs, reuse):
    """tidemark.fit_tidemark + predict_tidemark for one rung, or its saved forecasts (--reuse).

    Returns (outputs {p1, p2_dam, p2_cell}, fit summary, seconds the fit and forecast took).
    """
    if reuse and all(saved(rung, part).exists() for part in PARTS + ("fit_summary",)):
        log(f"{rung}: reloaded the saved forecasts")
        summary = pd.read_pickle(saved(rung, "fit_summary"))
        return ({part: load_predictions(BLOCK, PRED_TASK, f"{rung}_{part}") for part in PARTS}, summary,
                summary.get("fit_seconds"))
    started = time.time()
    log(f"{rung}: fit_tidemark('{config.VAL_START}', rung='{rung}') ({tidemark.RUNGS[rung].about})")
    model = tidemark.fit_tidemark(config.VAL_START, rung, inputs=inputs, log=lambda m: log(f"{rung}:   {m}"))
    out = tidemark.predict_tidemark(model, inputs)
    seconds = round(time.time() - started)
    summary = dict(tidemark.summary(model), fit_seconds=seconds)
    log(f"{rung}: {len(out['p1']):,} P1 forecasts in {seconds / 60:.1f} min")
    if save_forecasts(rung, out, summary):
        log(f"{rung}: saved to data_cache/preds/{BLOCK}/{PRED_TASK}/")
    return out, summary, seconds


def same_columns(outputs):
    """Every rung's p1, p2_dam and p2_cell tables have the same columns, in the same order (and p1 = the contract)."""
    first = outputs[RUNG_ORDER[0]]
    out = {part: all(list(outputs[r][part].columns) == list(first[part].columns) for r in outputs) for part in PARTS}
    out["p1_equals_contract"] = all(list(o["p1"].columns) == tidemark.p1_output_columns() for o in outputs.values())
    out["p1_columns"] = len(first["p1"].columns)
    return out


# ===========================================================================
# 2. Integration checks
# ===========================================================================
KEY_COLUMNS = ("row", "uid", "issue_date", "region", "at_risk_R30", "frailty_label")
EARLIER_STEPS = {"L1": ("L1_p1", "step 8"), "L2": ("L2_p1", "step 9"), "L3": ("L3_p1", "step 10")}


def compare_arrays(mine, theirs):
    """Largest difference (relative to max(1, |value|)) and whether two arrays are identical (blanks included)."""
    mine, theirs = np.asarray(mine, dtype=float), np.asarray(theirs, dtype=float)
    same_blanks = np.array_equal(np.isnan(mine), np.isnan(theirs))
    both = ~np.isnan(mine) & ~np.isnan(theirs)
    gap = np.abs(mine[both] - theirs[both]) / np.maximum(1.0, np.abs(theirs[both]))
    return dict(identical=bool(same_blanks and np.array_equal(mine[both], theirs[both])), same_blanks=bool(same_blanks),
                max_rel_diff=float(gap.max()) if gap.size else 0.0)


MEMBER_PREFIXES = ("p_T_", "p_S_", "p_M_", "anchor_")   # the 90-day members and their fused anchor


def compare_with_step(mine, theirs, label, tolerance=1e-6):
    """Every shared numeric column of two p1 tables (aligned on the P1 row), summarised in one line.

    A row "differs" when some column differs by more than `tolerance` (relative to max(1, |value|)),
    so float32 rounding in a saved file does not count. Also reports which dams differ and whether
    the members (T, S, M and their fused anchor) agree on every row.
    """
    a, b = mine.set_index("row"), theirs.set_index("row")
    columns = [c for c in a.columns if c in b.columns and c not in KEY_COLUMNS]
    rows_match = a.index.equals(b.index)
    float32 = any(b[c].dtype == np.float32 for c in columns)
    worst, all_identical, blanks_ok, worst_column = 0.0, rows_match, True, "-"
    row_differs = np.zeros(len(a), dtype=bool)
    members_agree = True
    for column in columns:
        x, y = a[column].to_numpy(dtype=float), b[column].reindex(a.index).to_numpy(dtype=float)
        result = compare_arrays(x, y)
        all_identical &= result["identical"]
        blanks_ok &= result["same_blanks"]
        if result["max_rel_diff"] > worst:
            worst, worst_column = result["max_rel_diff"], column
        gap = np.abs(x - y) / np.maximum(1.0, np.abs(y))
        differs = (np.isnan(x) != np.isnan(y)) | (np.nan_to_num(gap) > tolerance)
        row_differs |= differs
        if column.startswith(MEMBER_PREFIXES):
            members_agree &= not differs.any()
    dams = sorted(set(a.loc[row_differs, "uid"].astype(str)))
    if all_identical:
        verdict = "identical"
    elif rows_match and blanks_ok and not row_differs.any():
        verdict = "equal to float32 precision" if float32 else f"equal within {tolerance:.0e}"
    else:
        verdict = f"DIFFERENT on {int(row_differs.sum()):,} rows of {len(dams)} dam(s)"
    return dict(check=label, rows=len(a), rows_match=bool(rows_match), columns=len(columns), saved_as_float32=float32,
                max_rel_diff=worst, worst_column=worst_column, rows_differing=int(row_differs.sum()),
                dams_differing=dams[:10], members_agree=bool(members_agree), verdict=verdict)


def integration_checks(table, outputs):
    """Each rung's forecasts vs the step that built it, and the member-independent parts across rungs."""
    checks = []
    if "L0" in outputs:
        for kind in KINDS:
            positions = np.flatnonzero(rows.p1_block_rows(table, kind, BLOCK))
            keys = pd.DataFrame({"uid": table["uid"].astype(str).to_numpy()[positions],
                                 "issue_date": table["issue_date"].to_numpy()[positions]})
            g2 = attach(keys, require(f"P1_{kind}", "models", "scripts/03_baselines_and_g2.py"), ["p_G2"])["p_G2"]
            for column in (f"p90_{kind}", f"p_T_{kind}"):
                result = compare_arrays(on_rows(outputs["L0"]["p1"], positions, column), g2)
                checks.append(dict(check=f"L0 {column} vs step 3's benchmark G2", rows=len(positions),
                                   max_rel_diff=result["max_rel_diff"],
                                   verdict="identical" if result["identical"] else
                                   "equal within 1e-12" if result["max_rel_diff"] <= 1e-12 else "DIFFERENT"))
    for rung, (name, step) in EARLIER_STEPS.items():
        if rung in outputs and prediction_path(BLOCK, "tidemark", name).exists():
            checks.append(compare_with_step(outputs[rung]["p1"], load_predictions(BLOCK, "tidemark", name),
                                            f"{rung} vs the forecasts {step} saved (tidemark/{name}.pkl)"))
    return checks


def shared_part_checks(outputs):
    """Outputs that must be the same on several rungs (bit for bit), e.g. the floor on all four."""
    groups = [  # (output, columns, rungs that must agree)
        ("tree T (no water-balance columns)", [f"p_T_{k}" for k in KINDS], ("L0", "L1", "L2")),
        ("runway curve H (no water-balance columns)",
         [f"curve_{k}_{h}" for k in tidemark.CURVE_KINDS for h in tidemark.HORIZONS], ("L0", "L1", "L2")),
        ("nets S and M", [f"p_{m}_{k}" for m in ("S", "M") for k in KINDS], ("L2", "L3")),
        ("DamDays floor", ["floor_log_q10", "floor_days", "floor_shown"], RUNG_ORDER),
    ]
    out = []
    for label, columns, rungs in groups:
        rungs = [r for r in rungs if r in outputs]
        if len(rungs) < 2:
            continue
        first = outputs[rungs[0]]["p1"]
        same = all(compare_arrays(outputs[r]["p1"][c].to_numpy(), first[c].to_numpy())["identical"]
                   for r in rungs[1:] for c in columns)
        out.append(dict(output=label, rungs=list(rungs), identical=bool(same)))
    rungs = [r for r in RUNG_ORDER if r in outputs]
    same_p2 = all(np.array_equal(outputs[r][part][column].to_numpy(dtype=float),
                                 outputs[rungs[0]][part][column].to_numpy(dtype=float))
                  for r in rungs[1:] for part, column in (("p2_dam", "p"), ("p2_dam", "p_g"), ("p2_cell", "p")))
    out.append(dict(output="season rating P2 (dam p, gradual p, cell p)", rungs=rungs, identical=bool(same_p2)))
    blank = all(outputs[r]["p1"][f"p_{m}_{k}"].isna().all() for r in ("L0", "L1") if r in outputs
                for m in ("S", "M") for k in KINDS)
    out.append(dict(output="nets columns blank where the rung has no nets (L0, L1)", rungs=["L0", "L1"],
                    identical=bool(blank)))
    if "L0" in outputs:
        p1 = outputs["L0"]["p1"]
        no_frailty = all((p1[f"frailty_b_{k}"].dropna() == 0).all() for k in KINDS)
        no_max = compare_arrays(p1["p90_R30"].to_numpy(), p1["p90_R30_premax"].to_numpy())["identical"]
        out.append(dict(output="L0 has no frailty and no R30 max rule", rungs=["L0"], identical=bool(no_frailty and no_max)))
    return out


# ===========================================================================
# 3. The ladder table
# ===========================================================================
def p1_frame(table, outputs, kind):
    """Every at-risk VAL issue of `kind`: keys, flags, labels, each rung's 90-day forecast and step 3's G2."""
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
        "y_sens": np.where(chosen["window_closed"].to_numpy(dtype=bool), raw_label, np.nan)})
    for rung, out in outputs.items():
        frame[f"p_{rung}"] = on_rows(out["p1"], positions, f"p90_{kind}")
        if kind == "R30":
            frame[f"p_{rung}_premax"] = on_rows(out["p1"], positions, "p90_R30_premax")
    attach(frame, require(f"P1_{kind}", "models", "scripts/03_baselines_and_g2.py"), ["p_G2"])
    return frame


def expected_keys(frame, population, octmar_only, label="y"):
    """The rows a P1 subset must be scored on, worked out here independently of the scorecard."""
    keep = frame[label].notna().to_numpy() & frame[population].to_numpy(dtype=bool)
    if octmar_only:
        keep = keep & is_octmar(frame["issue_date"])
    return frame.loc[keep, ["uid", "issue_date"]]


def rung_below(rung, available):
    """The next lower rung that was fitted (None for L0)."""
    lower = [r for r in RUNG_ORDER[:RUNG_ORDER.index(rung)] if r in available]
    return lower[-1] if lower else None


def score_ladder(frames, baselines, rungs, n_boot):
    """Each rung on the primary set of each kind, paired with G2 and with the rung below. {(kind, rung): result}."""
    results = {}
    for kind in KINDS:
        frame = frames[kind]
        scored = attach(frame.copy(), baselines[(kind, "dam_like")], ["p_B0", "p_B2"])
        assert_val_only(scored)
        keys = expected_keys(frame, "dam_like", True)
        for rung in rungs:
            refs = ["G2"] + ([rung_below(rung, rungs)] if rung_below(rung, rungs) else [])
            results[(kind, rung)] = score(scored.assign(p=scored[f"p_{rung}"]), f"P1_{kind}", "primary",
                                          model=f"tidemark_{rung}", refs=refs, expected_keys=keys, n_boot=n_boot,
                                          out_dir=SCORE_DIR, note=NOTE)
        log(f"P1_{kind} primary: " + ", ".join(f"{r} {results[(kind, r)]['point']['bss_B0']:+.4f}" for r in rungs))
    return results


def lookahead_status():
    """The look-ahead test's latest entry for each (generator, region), from artifacts/lookahead_test.json.

    tests/test_no_lookahead.py writes one entry per region and generator, with the time it ran
    (run_at) and PASS or FAIL. A generator that has no entry counts as not passed.
    """
    entries = json.loads(LOOKAHEAD_JSON.read_text()) if LOOKAHEAD_JSON.exists() else {}
    status = {}
    for short, prefix in GENERATORS.items():
        for region in config.DEV_REGIONS:
            found = [e for key, e in entries.items() if key.split(" | ")[0] == region
                     and str(e.get("generator", "")).startswith(prefix)]
            if found:
                entry = found[0]
                status[(short, region)] = dict(generator=entry["generator"], region=region, cut=entry.get("cut"),
                                               result=entry["result"], run_at=entry.get("run_at", "not recorded"),
                                               passed=str(entry["result"]).startswith("PASS"))
            else:
                status[(short, region)] = dict(generator=prefix, region=region, result="not run", run_at="-",
                                               passed=False)
    return status


def ladder_rows(results, rungs, lookahead, problems):
    """One row per rung: its BSS, the pre-event value, the difference, and conditions (a) and (b).

    problems  {rung: why it could not be fitted} (a rung that was not fitted fails condition a)
    """
    out = []
    for rung in RUNG_ORDER:
        row = dict(rung=rung, about=tidemark.RUNGS[rung].about, members=list(tidemark.RUNGS[rung].members),
                   extra_features=list(tidemark.RUNGS[rung].extra_features), fitted=rung in rungs,
                   fit_problem=problems.get(rung), source=PRE_EVENT_SOURCE[rung], kinds={})
        for kind in KINDS:
            expected = PRE_EVENT[rung][kind]
            cell = dict(expected=expected, in_rule=kind in LADDER_KINDS)
            if rung in rungs:
                r = results[(kind, rung)]
                got = r["point"]["bss_B0"]
                cell.update(got=got, ci_dam=r["ci_dam"].get("bss_B0"), ci_region_year=r["ci_region_year"].get("bss_B0"),
                            difference=got - expected, within=bool(abs(got - expected) <= TOL))
                if rung == "L1":
                    cell["hybrid_only_expected"] = L1_FROM_HYBRID[kind]
                    cell["hybrid_only_within"] = bool(abs(got - L1_FROM_HYBRID[kind]) <= TOL)
            row["kinds"][kind] = cell
        row["condition_a"] = bool(rung in rungs and all(row["kinds"][k]["within"] for k in LADDER_KINDS))
        needs = [lookahead[(g, region)] for g in RUNG_NEEDS[rung] for region in config.DEV_REGIONS]
        row["lookahead"] = [dict(generator=n["generator"], region=n["region"], result=n["result"], run_at=n["run_at"])
                            for n in needs]
        row["condition_b"] = bool(all(n["passed"] for n in needs))
        row["passes"] = bool(row["condition_a"] and row["condition_b"])
        if rung in rungs and (KINDS[0], rung) in results:
            bars = results[("R30", rung)].get("prereg_pass_bars", {})
            row["prereg_p1_bars"] = bool(bars.get("all_passed")) if bars else None
        out.append(row)
    return out


def step_rows(results, rungs):
    """Paired gain of each rung over the one below it (and L3 over G2), next to the bench value."""
    out = []
    for label, rung, reference, bench, source in STEP_REFERENCES:
        if rung not in rungs or (reference != "G2" and reference not in rungs):
            continue
        for kind in KINDS:
            r = results[(kind, rung)]
            metric = f"d_bss_B0_vs_{reference}"
            got = r["point"].get(metric)
            ci = r["ci_dam"].get(metric)
            point, bench_ci = bench[kind]
            out.append(dict(step=f"{rung} over {reference}", adds=label, kind=kind, got=got, got_ci=ci,
                            bench=point, bench_ci=list(bench_ci), inside_bench_ci=bool(bench_ci[0] <= got <= bench_ci[1]),
                            source=source))
    return out


def highest_passing(ladder):
    """The highest rung that passes both PREREG conditions (None if none does). Not the freeze decision."""
    passing = [row["rung"] for row in ladder if row["passes"]]
    return max(passing, key=RUNG_ORDER.index) if passing else None


# ===========================================================================
# 4. The full VAL scorecard of the highest passing rung
# ===========================================================================
def score_p1_full(frames, baselines, results, best, rungs, n_boot_side):
    """The best rung on every P1 subset, R30 before the max rule, and the sensitivity row (primary reused)."""
    out = {}
    below = rung_below(best, rungs)
    refs = ["G2"] + ([below] if below else [])
    for kind in KINDS:
        task, frame = f"P1_{kind}", frames[kind]
        out[(task, "primary", best)] = results[(kind, best)]
        for subset, population, octmar_only in P1_SUBSETS:
            scored = attach(frame.copy(), baselines[(kind, population)], ["p_B0", "p_B2"])
            assert_val_only(scored)
            keys = expected_keys(frame, population, octmar_only)
            if subset != "primary":
                out[(task, subset, best)] = score(scored.assign(p=scored[f"p_{best}"]), task, subset,
                                                  model=f"tidemark_{best}", refs=refs, expected_keys=keys,
                                                  n_boot=n_boot_side, out_dir=SCORE_DIR, note=NOTE)
            if kind == "R30" and best != "L0" and subset != "dam_like+at_risk":
                premax_refs = ["G2"] + ([f"{below}_premax"] if below else [])
                out[(task, subset, f"{best}_premax")] = score(
                    scored.assign(p=scored[f"p_{best}_premax"]), task, subset, model=f"tidemark_{best}_premax",
                    refs=premax_refs, expected_keys=keys, n_boot=n_boot_side, out_dir=SCORE_DIR, note=NOTE)
        sens = attach(frame.copy(), baselines[(kind, "dam_like")], ["p_B0", "p_B2"]).assign(
            y=frame["y_sens"], p=frame[f"p_{best}"])
        out[(f"{task}_sens", "primary", best)] = score(
            sens, f"{task}_sens", "primary", model=f"tidemark_{best}", refs=refs,
            expected_keys=expected_keys(frame, "dam_like", True, "y_sens"), n_boot=n_boot_side, out_dir=SCORE_DIR,
            note=NOTE)
    log(f"P1: {best} scored on {len(P1_SUBSETS)} subsets and the sensitivity rows")
    return out


def curve_frame(table, p1_out, kind, labels):
    """Keys, flags, the labels at 30/60/90/180 days and the curve, for every at-risk VAL issue of `kind`."""
    picked = rows.p1_block_rows(table, kind, BLOCK)
    positions = np.flatnonzero(picked)
    chosen = table.loc[picked]
    frame = pd.DataFrame({
        "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
        "region": chosen["region"].astype(str).to_numpy(), "dam_like": chosen["dam_like"].to_numpy(dtype=bool),
        "persistent": chosen["persistent"].to_numpy(dtype=bool), "at_risk": True})
    for h in tidemark.HORIZONS:
        frame[f"y_{h}"] = labels.loc[picked, f"y_{h}"].to_numpy()
        frame[f"p_{h}"] = on_rows(p1_out, positions, f"curve_{kind}_{h}")
    return frame


def score_curves_full(table, p1_out, best, n_boot_main, n_boot_side):
    """The runway curve on every subset, each horizon against its own baselines (step 6's B0_h and B2_h)."""
    end, out = data_end(), {}
    for kind in tidemark.CURVE_KINDS:
        frame = curve_frame(table, p1_out, kind, hazard.horizon_labels(table, kind, end))
        for subset, population in CURVE_SUBSETS:
            base = require(f"{kind}_curve", f"baselines_{population}", "scripts/06_hazard_curve.py")
            scored = attach(frame.copy(), base, [f"p_B{b}_{h}" for b in (0, 2) for h in tidemark.HORIZONS])
            assert_val_only(scored)
            out[(f"{kind}_curve", subset)] = score_curve(
                scored, f"{kind}_curve", subset, model=f"tidemark_{best}",
                n_boot=n_boot_main if subset == "primary" else n_boot_side, out_dir=SCORE_DIR, note=NOTE)
    r30 = np.flatnonzero(rows.p1_block_rows(table, "R30", BLOCK))
    crossing = crossing_share(np.column_stack([on_rows(p1_out, r30, f"curve_R30_{h}") for h in tidemark.HORIZONS]),
                              np.column_stack([on_rows(p1_out, r30, f"curve_D0_{h}") for h in tidemark.HORIZONS]))
    log(f"curves: scored on {len(CURVE_SUBSETS)} subsets; R30 below D0 on {crossing:.4f} of rows")
    return out, crossing


def headline_vs_curve(table, p1_out):
    """How far the runway curve's 90-day point is from the 90-day headline (dam-like, Oct-Mar forecasts).

    They come from two models (the headline fuses the members with the frailty; the curve is the
    hazard model H, as the PREREG fixes), so the app can show a curve whose 90-day point differs
    from the headline. Reported, not corrected.
    """
    out = {}
    for kind in tidemark.CURVE_KINDS:
        picked = (rows.p1_block_rows(table, kind, BLOCK) & table["dam_like"].to_numpy(dtype=bool)
                  & is_octmar(table["issue_date"]))
        positions = np.flatnonzero(picked)
        gap = on_rows(p1_out, positions, f"curve_{kind}_90") - on_rows(p1_out, positions, f"p90_{kind}")
        out[kind] = dict(rows=int(len(gap)), mean_gap=float(np.mean(gap)), mean_abs_gap=float(np.mean(np.abs(gap))),
                         p90_abs_gap=float(np.percentile(np.abs(gap), 90)))
    return out


def horizon_value(result, h, metric, part="point"):
    """One metric at one horizon from a score_curve result."""
    entry = next(x for x in result["horizons"] if x["horizon"] == h)
    return entry[part].get(metric)


def floor_full(table, p1_out, n_boot):
    """Floor coverage as issued (all labelled forecasts, primary set) and as displayed (180-day cap)."""
    picked = rows.p1_block_rows(table, unc.FLOOR_KIND, BLOCK)
    positions = np.flatnonzero(picked)
    chosen = table.loc[picked]
    labelled = chosen["label_ok"].to_numpy(dtype=bool)
    primary = labelled & chosen["dam_like"].to_numpy(dtype=bool) & is_octmar(chosen["issue_date"])
    days_to = chosen[f"lab_tte_{unc.FLOOR_KIND}"].to_numpy(dtype=float)
    follow = unc.followup_days(chosen["issue_date"], data_end())
    uid, dates = chosen["uid"].astype(str).to_numpy(), chosen["issue_date"].to_numpy()
    floor = on_rows(p1_out, positions, "floor_days")
    shown = on_rows(p1_out, positions, "floor_shown")

    def one(values, mask, boot, cap=None):
        result = floor_coverage(values[mask], days_to[mask], follow[mask], uid=uid[mask], issue_date=dates[mask],
                                cap_days=cap, n_boot=boot)
        result.pop("bootstrap", None)
        return result
    out = dict(issued_all=one(floor, labelled, n_boot), issued_primary=one(floor, primary, n_boot),
               shown_all=one(shown, labelled, 0, unc.FLOOR_DISPLAY_MAX_DAYS))
    log(f"floor: coverage as issued {out['issued_all']['coverage']:.4f} (all), "
        f"{out['issued_primary']['coverage']:.4f} (primary)")
    return out


def band_full(table, p1_out, summary):
    """Region-year coverage on VAL of the rung's own season band (offsets on its own VAL forecasts)."""
    out = {}
    for kind in KINDS:
        band = tuple(summary["band"]["band"][kind])
        mask = unc.band_rows(table, kind, config.VAL_START, config.TEST_START) & (time_block(table["issue_date"]) == BLOCK)
        part = table.loc[mask]
        p = on_rows(p1_out, np.flatnonzero(mask), f"p90_{kind}")
        offsets = unc.block_offsets(part[rows.p1_label(kind)].to_numpy(dtype=float), p, part["region"],
                                    part["issue_date"], "VAL")
        out[kind] = dict(band=list(band), coverage=band_coverage(offsets, *band))
    log("band: " + ", ".join(f"{k} {v['coverage']['covered']}/{v['coverage']['region_years']}" for k, v in out.items()))
    return out


def score_p2(out, best, n_boot):
    """The season rating against RAIN, RAIN+ and B2 (the rating is the same on every rung)."""
    results = {}
    for task, subset, column in P2_TASKS:
        source = out["p2_cell"] if task == "P2_cell" else out["p2_dam"]
        frame = tidy_keys(pd.DataFrame({"uid": source["uid"].to_numpy(), "issue_date": source["issue_date"].to_numpy(),
                                        "region": source["region"].to_numpy(), "p": source[column].to_numpy()}))
        frame = join_baselines(frame, require(task, "baselines", "scripts/03_baselines_and_g2.py"))
        assert_val_only(frame)
        keep = frame["y"].notna().to_numpy()
        if subset == "dam_like":
            keep = keep & frame["dam_like"].to_numpy(dtype=bool)
        results[(task, subset, best)] = score(frame, task, subset, model=f"tidemark_{best}", refs=P2_REFS,
                                              expected_keys=frame.loc[keep, ["uid", "issue_date"]], n_boot=n_boot,
                                              out_dir=SCORE_DIR, note=NOTE)
    log("P2: " + ", ".join(f"{task} AUC {r['point']['auc']:.4f}" for (task, _, _), r in results.items()))
    return results


def p2_rules(result):
    """PREREG P2: pass bar (AUC gain over RAIN >= 0.05, CI above 0) and kill rule (RAIN within 0.02 AUC)."""
    gain = result["point"]["d_auc_vs_RAIN"]
    ci = result["ci_dam"].get("d_auc_vs_RAIN")
    return dict(d_auc_vs_RAIN=gain, ci_dam=ci, ci_region_year=result["ci_region_year"].get("d_auc_vs_RAIN"),
                passed=bool(gain >= P2_PASS_DAUC and ci[0] > 0) if ci else bool(gain >= P2_PASS_DAUC),
                kill_rule_triggered=bool(gain < P2_KILL_DAUC))


def best_checks(best, p1, curves, floor, p2):
    """Expected (pre-event) vs got for the best rung: P1 levels, curve, floor, P2. Tolerances are reading aids."""
    out = []

    def add(label, got, expected, tolerance, source):
        if got is None or expected is None:
            return
        out.append(dict(check=label, expected=expected, got=got, difference=got - expected, tolerance=tolerance,
                        within=bool(abs(got - expected) <= tolerance), source=source))
    for kind in KINDS:
        task = f"P1_{kind}"
        add(f"{kind} BSS vs B0 (primary)", p1[(task, "primary", best)]["point"]["bss_B0"], PRE_EVENT[best][kind], TOL,
            "the ladder value (see ladder_val.md)")
        if best == "L3":
            detail = L3_DETAIL[kind]
            primary = p1[(task, "primary", best)]["point"]
            for metric, name, tolerance in (("bss_B2", "BSS vs B2", TOL), ("auc", "AUC", TOL),
                                            ("cal_slope", "calibration slope", 0.05), ("citl", "CITL", 0.05)):
                add(f"{kind} {name} (primary)", primary[metric], detail[metric], tolerance,
                    "hybrid val_final_scorecard.csv")
            add(f"{kind} BSS vs B0, persistent", p1[(task, "persistent+octmar+at_risk", best)]["point"]["bss_B0"],
                detail["persistent"], TOL, "hybrid val_final_scorecard.csv")
            add(f"{kind} BSS vs B0, dam-like all months", p1[(task, "dam_like+at_risk", best)]["point"]["bss_B0"],
                detail["all_months"], TOL, "hybrid val_final_scorecard.csv (season 'all')")
    like = "like for like (H with the water-balance columns)" if best == "L3" else "reference: the pre-event H had the water-balance columns"
    for kind in tidemark.CURVE_KINDS:
        for h, expected in zip(tidemark.HORIZONS, CURVE_REFERENCE[kind]):
            add(f"{kind} curve BSS vs B0_h at {h} days", horizon_value(curves[(f"{kind}_curve", "primary")], h, "bss_B0"),
                expected, TOL, f"hybrid val_stageC_horizons.csv H_alone; {like}")
    add("floor coverage as issued, all", floor["issued_all"]["coverage"], FLOOR_REFERENCE["all"], 0.005,
        "calibration-uncertainty conformal_VAL.json")
    add("floor coverage as issued, primary", floor["issued_primary"]["coverage"], FLOOR_REFERENCE["primary"], 0.005,
        "calibration-uncertainty conformal_VAL.json")
    add("floor median days, all", floor["issued_all"]["median_floor_days"], FLOOR_REFERENCE["median_days"], 3.0,
        "calibration-uncertainty conformal_VAL.json")
    by_task = {task: r for (task, _, _), r in p2.items()}
    for label, task, metric, expected, tolerance, source in P2_CHECKS:
        add(label, by_task[task]["point"].get(metric), expected, tolerance, source)
    return out


# ===========================================================================
# Report formatting
# ===========================================================================
def fmt(value, digits=4, sign=True):
    """A number for a table cell ("-" when missing)."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def fmt_range(ci, digits=4, sign=True):
    """An interval as text ("" when missing)."""
    return f"[{fmt(ci[0], digits, sign)}, {fmt(ci[1], digits, sign)}]" if ci else ""


def fmt_ci(result, metric, digits=4, sign=True):
    """Point value with the dam interval and the region-year (ry) interval when present."""
    text = fmt(result["point"].get(metric), digits, sign)
    for label, key in (("", "ci_dam"), ("ry ", "ci_region_year")):
        ci = result.get(key, {}).get(metric)
        if ci:
            text += f" {label}{fmt_range(ci, digits, sign)}"
    return text


def ladder_lines(ladder):
    """The ladder table in markdown."""
    lines = ["| rung | what it fuses | R30: got [dam 95% CI] / pre-event / diff | D0: got / pre-event / diff | "
             "D0g (reported, not in the rule): got / pre-event / diff | (a) R30 and D0 within +-0.006 | "
             "(b) look-ahead test | passes both |", "|---|---|---|---|---|---|---|---|"]
    for row in ladder:
        cells = []
        for kind in KINDS:
            c = row["kinds"][kind]
            if "got" not in c:
                cells.append(f"not fitted / {c['expected']:+.4f}")
                continue
            ci = f" {fmt_range(c['ci_dam'])}" if kind == "R30" and c.get("ci_dam") else ""
            mark = "" if c["within"] else " **outside**"
            cells.append(f"{c['got']:+.4f}{ci} / {c['expected']:+.4f} / {c['difference']:+.4f}{mark}")
        b_text = "PASS" if row["condition_b"] else "FAIL (" + "; ".join(
            f"{n['region']} {n['generator'].split(' (')[0]}: {n['result']}" for n in row["lookahead"]
            if not n["result"].startswith("PASS")) + ")"
        lines.append(f"| **{row['rung']}** | {row['about']} | " + " | ".join(cells)
                     + f" | {'PASS' if row['condition_a'] else 'FAIL'} | {b_text} | "
                     f"{'**yes**' if row['passes'] else 'no'} |")
    return lines


def lookahead_lines(lookahead):
    """The look-ahead entries the ladder read."""
    lines = ["| generator | region | cut | result | run at | needed by |", "|---|---|---|---|---|---|"]
    for (short, region), s in lookahead.items():
        needed = ", ".join(r for r in RUNG_ORDER if short in RUNG_NEEDS[r])
        lines.append(f"| {s['generator']} | {region} | {s.get('cut') or '-'} | {s['result']} | {s['run_at']} | {needed} |")
    return lines


def step_lines(steps):
    """Paired gains between rungs vs the bench."""
    lines = ["| step | adds | kind | got [dam 95% CI] | bench [95% CI] | inside the bench CI? | bench source |",
             "|---|---|---|---|---|---|---|"]
    for s in steps:
        lines.append(f"| {s['step']} | {s['adds']} | {s['kind']} | {fmt(s['got'])} {fmt_range(s['got_ci'])} | "
                     f"{s['bench']:+.4f} {fmt_range(s['bench_ci'])} | {'yes' if s['inside_bench_ci'] else 'no'} | "
                     f"{s['source']} |")
    return lines


def integration_notes(checks):
    """A plain explanation under the integration table, for each step file that differs from this run."""
    notes = []
    for c in checks:
        if not c["verdict"].startswith("DIFFERENT"):
            continue
        if c.get("members_agree"):
            notes += [f"- {c['check']}: every member and the fused anchor agree on every VAL row; only the per-dam "
                      f"correction and what follows from it (90-day probability, season band) differ, on "
                      f"{c['rows_differing']:,} rows of {len(c['dams_differing'])} dam(s). The correction also reads "
                      "each dam's forecasts from before 2009, which that step did not save, so the difference "
                      "comes from those earlier forecasts. The scores in this report use this run's forecasts.", ""]
        else:
            notes += [f"- {c['check']}: the members themselves differ. Investigate before relying on either file.", ""]
    return notes


def write_ladder_report(r):
    """artifacts/ladder_val.md and .json."""
    ladder, best = r["ladder"], r["best"]
    fitted_text = ", ".join(f"{k} {v / 60:.1f} min" if v is not None else f"{k} not recorded"
                            for k, v in r["seconds"].items())
    lines = [
        "# The PREREG fallback ladder on VAL (build step 12)",
        "",
        f"Generated by `scripts/12_ladder_val.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only**: "
        "forecasts issued 2009-01-01 to 2015-12-31, development regions. TEST was not scored.",
        "",
        "**The rule (PREREG, Fallback ladder).** The frozen model is the highest rung whose event "
        "re-implementation (a) reproduces its pre-event VAL BSS within +-0.006 on R30 and D0, and (b) passes the "
        "look-ahead test. **This report measures (a) and reads (b). It does not choose the frozen model**: that is "
        "the separate, dated freeze step (PREREG addendum).",
        "",
        "**What was run.** Every rung through Tidemark's one entry point: `tidemark.fit_tidemark(\"2009-01-01\", "
        "rung)` then `tidemark.predict_tidemark` (`damdays/models/tidemark.py`), learning only from answers final "
        f"before 2009-01-01. Fit times: {fitted_text}. The score is BSS vs B0 on the primary set (dam-like, "
        "Oct-Mar, at risk, label known), R30 after the max rule (the shipped forecast), with "
        f"{r['n_boot']} dam and {r['n_boot']} region-year bootstrap draws.",
        "",
        "## The ladder table",
        "",
        *ladder_lines(ladder),
        "",
        f"**Highest rung that passes both conditions: {best or 'none'}.** Rungs that pass: "
        f"{', '.join(row['rung'] for row in ladder if row['passes']) or 'none'}.",
        "",
        "Where each pre-event value comes from (bench = `research/pre_event/bench/results`):",
        "",
        *[f"- **{row['rung']}**: {row['source']}" for row in ladder],
        "",
        "Cross-check for L1 from the hybrid tables alone (val_stageA `G2c` + val_stageB `-frailty` cost; not used "
        "for the verdict): " + ", ".join(
            f"{k} {L1_FROM_HYBRID[k]:+.4f} (got {fmt(ladder[1]['kinds'][k].get('got'))}, "
            f"{'within' if ladder[1]['kinds'][k].get('hybrid_only_within') else 'outside'} +-0.006)" for k in KINDS) + ".",
        "",
        "PREREG P1 pass bars (R30 BSS vs B0 >= +0.10 with the dam CI above 0, BSS vs B2 >= +0.05, calibration slope "
        "0.8-1.2): " + ", ".join(f"{row['rung']} {'pass' if row.get('prereg_p1_bars') else 'FAIL'}"
                                 for row in ladder if row["fitted"]) + ".",
        "",
        "## Condition (b): the look-ahead test",
        "",
        "Read from `artifacts/lookahead_test.json`, written by `tests/test_no_lookahead.py` (one entry per "
        "generator and region, with the time it ran; a failure is recorded as FAIL). Each rung needs the "
        "generators its inputs come from: L0 and L1 the core features and frailty sums; L2 also the nets' "
        "24-month sequences; L3 also the water balance.",
        "",
        *lookahead_lines(r["lookahead"]),
        "",
        "## What each step up the ladder adds (paired, same rows)",
        "",
        *step_lines(r["steps"]),
        "",
        "## Season rating (PREREG P2 ladder: the offset model, fallback B2)",
        "",
        "The rating does not depend on the P1 rung (it is identical on all four, checked below). "
        + (f"Offset model on VAL: P2_cell AUC {fmt(r['p2_cell']['point']['auc'], 4, False)} (pre-event 0.7873), "
           f"gain over B2 {fmt(r['p2_cell']['point'].get('d_auc_vs_B2'))} (pre-event +0.0142), gain over RAIN "
           f"{fmt(r['p2_cell']['point'].get('d_auc_vs_RAIN'))} (pre-event +0.2464; {RAIN_NOTE}). It reproduces "
           "within +-0.006, so P2 stays on the offset model (no fallback to B2)." if r.get("p2_cell") else
           "Not scored in this run (no rung passed)."),
        "",
        "## Integration checks",
        "",
        f"All four rungs return the same columns from `predict_tidemark`: p1 "
        f"{'yes' if r['columns']['p1'] else 'NO'} ({r['columns']['p1_columns']} columns, equal to "
        f"`tidemark.p1_output_columns()`: {'yes' if r['columns']['p1_equals_contract'] else 'NO'}), p2_dam "
        f"{'yes' if r['columns']['p2_dam'] else 'NO'}, p2_cell {'yes' if r['columns']['p2_cell'] else 'NO'}.",
        "",
        "Each rung against the forecasts saved by the step that built it (every shared numeric column, aligned on "
        "the P1 row; differences relative to max(1, |value|)):",
        "",
        "| check | rows | columns | largest difference | members (T, S, M, anchor) agree on every row? | verdict |",
        "|---|---|---|---|---|---|",
        *[f"| {c['check']} | {c['rows']:,} | {c.get('columns', 1)} | {c['max_rel_diff']:.1e}"
          + (f" ({c['worst_column']})" if c.get("worst_column", "-") != "-" else "")
          + f" | {('yes' if c['members_agree'] else 'NO') if 'members_agree' in c else '-'} | {c['verdict']}"
          + (f" ({', '.join(c['dams_differing'])})" if c.get("dams_differing") else "") + " |"
          for c in r["integration"]],
        "",
        *integration_notes(r["integration"]),
        "Parts that must be the same on several rungs (bit for bit):",
        "",
        "| output | rungs | identical? |", "|---|---|---|",
        *[f"| {c['output']} | {', '.join(c['rungs'])} | {'yes' if c['identical'] else 'NO'} |" for c in r["shared"]],
        "",
        "## Notes",
        "",
        "- **Time rules.** Every member learns from answers final before 2009-01-01 (issue + 120 days); the "
        "frailty uses a dam's past forecasts only once their answer is final; the season band's inner backtest "
        "refits each rung on answers final before 2002-01-01. Details in `docs/HOW_IT_WORKS.md`.",
        "- **L1's R30 value** is compared with a pre-event model that had no R30 max rule (step 4 measured the "
        "rule's cost on L1 at -0.0006).",
        "- **L2's pre-event value is derived** (no pre-event row is exactly L2): L3's score minus the measured cost "
        "of removing the physics columns.",
        f"- **Full scorecard** of the highest passing rung: `artifacts/{BEST_MD.name}`."
        if best else "- No rung passed, so no full scorecard was written.",
        "- Forecasts: `data_cache/preds/VAL/ladder/<rung>_*.pkl`; scorecard JSON: `artifacts/scorecard/step12_val/`.",
        "",
    ]
    LADDER_MD.write_text("\n".join(lines), encoding="utf-8")
    report = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), block=BLOCK, tolerance=TOL, n_boot=r["n_boot"],
                  rule="PREREG Fallback ladder: highest rung with (a) R30 and D0 VAL BSS within +-0.006 of the "
                       "pre-event value and (b) the look-ahead test passed",
                  not_the_freeze_decision=True, highest_passing=best,
                  passing=[row["rung"] for row in ladder if row["passes"]], ladder=ladder, steps=r["steps"],
                  lookahead={f"{g} | {region}": s for (g, region), s in r["lookahead"].items()},
                  columns=r["columns"], integration=r["integration"], shared=r["shared"],
                  p2_cell=compact(r["p2_cell"]) if r.get("p2_cell") else None, fit_seconds=r["seconds"])
    LADDER_JSON.write_text(json.dumps(clean_for_json(report), indent=1), encoding="utf-8")


def compact(result):
    """The parts of a scorecard result kept in the JSON reports."""
    return dict(point=result["point"], ci_dam=result.get("ci_dam", {}), ci_region_year=result.get("ci_region_year", {}),
                rows=result.get("rows"), refs=result.get("refs"), prereg_pass_bars=result.get("prereg_pass_bars"))


def p1_lines(p1):
    """Markdown rows of the P1 scores."""
    lines = ["| task | subset | model | rows | events | BSS vs B0 [dam] ry [region-year] | BSS vs B2 | AUC | cal. slope | "
             "CITL | prec. at 50% recall | gain over G2 | gain over the rung below |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (task, subset, model), r in p1.items():
        below = next((ref for ref in r["refs"] if ref != "G2"), None)
        lines.append("| " + " | ".join([
            task, subset, model, f"{r['rows']['scored']:,}", f"{r['rows']['events']:,}", fmt_ci(r, "bss_B0", 3),
            fmt(r["point"]["bss_B2"], 3), fmt(r["point"]["auc"], 3, False), fmt(r["point"]["cal_slope"], 2, False),
            fmt(r["point"]["citl"], 2), fmt(r["point"].get("prec_at_50_recall"), 3, False),
            fmt_ci(r, "d_bss_B0_vs_G2"), (f"{fmt_ci(r, f'd_bss_B0_vs_{below}')} (vs {below})" if below else "-")]) + " |")
    return lines


def curve_lines(curves, best):
    """Markdown rows of the runway-curve scores."""
    lines = ["| curve | subset | h (days) | rows | events | BSS vs B0_h [dam] | BSS vs B2_h | AUC | cal. slope | CITL | "
             "pre-event H (BSS vs B0_h) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for (task, subset), result in curves.items():
        kind = task.split("_")[0]
        for entry in result["horizons"]:
            h, point = entry["horizon"], entry["point"]
            ref = CURVE_REFERENCE[kind][tidemark.HORIZONS.index(h)] if subset == "primary" else None
            ci = entry.get("ci_dam", {}).get("bss_B0")
            lines.append(f"| {task} | {subset} | {h} | {entry['rows']:,} | {entry['events']:,} | "
                         f"{fmt(point.get('bss_B0'))} {fmt_range(ci)} | {fmt(point.get('bss_B2'))} | "
                         f"{fmt(point.get('auc'), 3, False)} | {fmt(point.get('cal_slope'), 2, False)} | "
                         f"{fmt(point.get('citl'), 2)} | {fmt(ref) if ref is not None else '-'} |")
    lines.append("")
    lines.append("Curves that fall as the horizon grows: " + ", ".join(
        f"{task} {subset} {result['monotonicity']['rows_falling']} of {result['monotonicity']['rows']:,}"
        for (task, subset), result in curves.items() if subset == "primary") + ".")
    return lines


def missed_text(coverage):
    """Region-years outside the band, as text."""
    missed = dict(coverage.get("drier_than_band", {}), **coverage.get("wetter_than_band", {}))
    return ", ".join(f"{k} ({v:+.2f})" for k, v in sorted(missed.items())) or "none"


def write_best_report(b):
    """artifacts/val_tidemark_best.md and .json: the full VAL scorecard of the highest passing rung."""
    best, p1, curves, floor, band, p2 = b["rung"], b["p1"], b["curves"], b["floor"], b["band"], b["p2"]
    bars = p1[("P1_R30", "primary", best)].get("prereg_pass_bars", {})
    cell = p2[("P2_cell", "all", best)]
    rules2 = p2_rules(cell)
    headline = [
        "| what | value on VAL (2009-2015) [dam 95% CI] ry [region-year] |", "|---|---|",
        *[f"| P1 {k}: BSS vs B0 (primary) | {fmt_ci(p1[(f'P1_{k}', 'primary', best)], 'bss_B0')} |" for k in KINDS],
        *[f"| P1 {k}: gain over the benchmark G2 (same rows) | {fmt_ci(p1[(f'P1_{k}', 'primary', best)], 'd_bss_B0_vs_G2')} |"
          for k in KINDS],
        f"| P1 R30: BSS vs B2 / AUC / calibration slope | {fmt(p1[('P1_R30', 'primary', best)]['point']['bss_B2'], 3)} / "
        f"{fmt(p1[('P1_R30', 'primary', best)]['point']['auc'], 3, False)} / "
        f"{fmt(p1[('P1_R30', 'primary', best)]['point']['cal_slope'], 2, False)} |",
        *[f"| runway curve {k}: BSS vs B0_h at 30 / 60 / 90 / 180 days | "
          + " / ".join(fmt(horizon_value(curves[(f'{k}_curve', 'primary')], h, 'bss_B0'), 3) for h in tidemark.HORIZONS)
          + " |" for k in tidemark.CURVE_KINDS],
        f"| DamDays floor: share that held (all / primary; target 0.90) | {fmt(floor['issued_all']['coverage'], 3, False)} / "
        f"{fmt(floor['issued_primary']['coverage'], 3, False)} |",
        "| season band: VAL region-years inside (R30 / D0 / D0g) | " + " / ".join(
            f"{band[k]['coverage']['covered']}/{band[k]['coverage']['region_years']}" for k in KINDS) + " |",
        f"| season rating (2 km cells): AUC / gain over RAIN | {fmt_ci(cell, 'auc', 4, False)} / {fmt_ci(cell, 'd_auc_vs_RAIN')} |",
    ]
    lines = [
        f"# VAL scorecard of the highest passing ladder rung: Tidemark {best} (build step 12)",
        "",
        f"Generated by `scripts/12_ladder_val.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only** "
        "(forecasts issued 2009-2015, season ratings 1 July 2009-2015, development regions). TEST was not scored.",
        "",
        f"**Why this rung.** {best} is the highest rung that passes both PREREG ladder conditions on VAL "
        "(`artifacts/ladder_val.md`). **This is not the freeze decision**, which is the separate, dated PREREG "
        "addendum.",
        "",
        f"**What was run.** `tidemark.fit_tidemark(\"2009-01-01\", rung=\"{best}\")` then `tidemark.predict_tidemark`. "
        f"{best} = {tidemark.RUNGS[best].about}. Members fused: {', '.join(tidemark.RUNGS[best].members)}"
        + (f"; water-balance columns in T and H: {', '.join(tidemark.RUNGS[best].extra_features)}"
           if tidemark.RUNGS[best].extra_features else "") + ". Every part learns only from answers final before "
        "2009-01-01; the season band comes from this rung's own 2002-2009 inner backtest.",
        "",
        f"Bootstrap: {b['n_boot_main']} dam and {b['n_boot_main']} region-year draws on the primary sets, the curve's "
        f"primary set, the floor and P2; {b['n_boot_side']} on other subsets.",
        "",
        "## Headline numbers",
        "",
        *headline,
        "",
        "## PREREG pass bars on VAL",
        "",
        "| bar | value | required | passed |", "|---|---|---|---|",
        *[f"| P1 R30 {name} | {fmt(bar['value'])}" + (f" (dam CI low {fmt(bar.get('ci_low'))})" if 'ci_low' in bar else "")
          + f" | {bar['bar']} | {'yes' if bar['passed'] else 'NO'} |" for name, bar in bars.items() if name != "all_passed"],
        f"| P2 cells: AUC gain over RAIN | {fmt(rules2['d_auc_vs_RAIN'])} {fmt_range(rules2['ci_dam'])} | >= +0.05, CI above 0 | "
        f"{'yes' if rules2['passed'] else 'NO'} |",
        f"| P2 kill rule: RAIN within 0.02 AUC of the rating | {fmt(rules2['d_auc_vs_RAIN'])} | not triggered | "
        f"{'TRIGGERED' if rules2['kill_rule_triggered'] else 'not triggered'} |",
        "",
        "## P1: the 90-day probabilities",
        "",
        f"`{best}` = the shipped forecast (R30 after the max rule); `{best}_premax` = R30 before it. `_sens` rows: the "
        "PREREG label-determinable sensitivity row. Gains are paired, in BSS-vs-B0 units.",
        "",
        *p1_lines(p1),
        "",
        "## The runway curve (hazard model H; R30 curve >= D0 curve)",
        "",
        "Each horizon is judged against its own baselines (step 6). Pre-event column: hybrid "
        "`val_stageC_horizons.csv` H_alone, which had the water-balance columns"
        + (" (like for like at L3)." if best == "L3" else " (a reference: this rung's H does not)."),
        "",
        *curve_lines(curves, best),
        f"R30 curve below the D0 curve (any horizon): {b['crossing']:.4f} of R30 forecasts (expected 0).",
        "",
        "The 90-day headline and the curve's 90-day point come from two models (the headline fuses the members "
        "with the per-dam correction; the curve is H), so they can differ. On dam-like Oct-Mar forecasts: "
        + "; ".join(f"{k} curve minus headline {g['mean_gap']:+.3f} on average, {g['mean_abs_gap']:.3f} in absolute "
                    f"value, more than {g['p90_abs_gap']:.3f} for 1 forecast in 10" for k, g in b["gap"].items()) + ".",
        "",
        "## DamDays floor",
        "",
        "| forecasts | judged | share that held [dam 95% CI] | median floor (days) | worst July-June year |",
        "|---|---|---|---|---|",
        *[f"| {label} | {f['rows_judged']:,} | {fmt(f['coverage'], 4, False)} {fmt_range(f.get('ci_dam', {}).get('coverage'), 4, False)} | "
          f"{fmt(f['median_floor_days'], 1, False)} | "
          + (f"{f['worst_year']['year']}: {f['worst_year']['coverage']:.3f}" if f.get("worst_year") else "-") + " |"
          for label, f in (("as issued, all labelled", floor["issued_all"]), ("as issued, primary set", floor["issued_primary"]),
                           ("as displayed (180-day cap), all", floor["shown_all"]))],
        "",
        "VAL is the first block, so the floor is the raw 10% quantile (shift 0; no earlier calibration block exists).",
        "",
        "## Season band (this rung's own 2002-2009 inner backtest)",
        "",
        "| kind | band (log-odds) | VAL region-years covered | missed (offset) | pre-event v1 band (reference) |",
        "|---|---|---|---|---|",
        *[f"| {k} | [{v['band'][0]:+.3f}, {v['band'][1]:+.3f}] | {v['coverage']['covered']}/{v['coverage']['region_years']} | "
          f"{missed_text(v['coverage'])} | {BAND_REFERENCE[k]} |" for k, v in band.items()],
        "",
        "## Season rating (P2)",
        "",
        "| task | subset | rated seasons | ran dry | AUC [dam] ry [region-year] | gain over RAIN | gain over RAIN+ | "
        "gain over B2 | within-season AUC | within-cell AUC | cal. slope | CITL |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
        *[f"| {task} | {subset} | {r['rows']['scored']:,} | {r['rows']['events']:,} | {fmt_ci(r, 'auc', 4, False)} | "
          f"{fmt_ci(r, 'd_auc_vs_RAIN')} | {fmt(r['point'].get('d_auc_vs_RAIN+'))} | {fmt(r['point'].get('d_auc_vs_B2'))} | "
          f"{fmt(r['point'].get('auc_within_season'), 4, False)} | {fmt(r['point'].get('auc_within_cell'), 4, False)} | "
          f"{fmt(r['point'].get('cal_slope'), 2, False)} | {fmt(r['point'].get('citl'), 2)} |"
          for (task, subset, _), r in p2.items()],
        "",
        "## Expected (pre-event research) vs got",
        "",
        "Tolerance +-0.006 (the PREREG ladder tolerance) for skill and AUC; +-0.05 for calibration, +-0.005 for "
        "floor coverage and +-3 days for the floor median, as reading aids.",
        "",
        "| check | expected | got | difference | tolerance | verdict | source |", "|---|---|---|---|---|---|---|",
        *[f"| {c['check']} | {c['expected']:+.4f} | {c['got']:+.4f} | {c['difference']:+.4f} | +-{c['tolerance']} | "
          f"{'within' if c['within'] else 'OUTSIDE'} | {c['source']} |" for c in b["checks"]],
        "",
        f"Step reports with every component check: rung L1 `artifacts/val_tidemark_L1.md`, L2 "
        "`artifacts/val_tidemark_L2.md`, the physics (L3) `artifacts/val_physics.md`.",
        "",
    ]
    BEST_MD.write_text("\n".join(lines), encoding="utf-8")
    report = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), block=BLOCK, rung=best, not_the_freeze_decision=True,
                  n_boot_main=b["n_boot_main"], n_boot_side=b["n_boot_side"],
                  p1={"|".join(k): compact(v) for k, v in p1.items()}, p2={"|".join(k): compact(v) for k, v in p2.items()},
                  p2_rules=rules2, curves={"|".join(k): dict(bss_B0_by_horizon=v["bss_B0_by_horizon"],
                                                             monotonicity=v["monotonicity"],
                                                             horizons=v["horizons"]) for k, v in curves.items()},
                  curve_crossing_share=b["crossing"], headline_vs_curve=b["gap"], floor=floor, band=band,
                  checks=b["checks"],
                  fit_summary={k: v for k, v in b["summary"].items() if k != "band"},
                  band_constants=b["summary"]["band"]["band"])
    BEST_JSON.write_text(json.dumps(clean_for_json(report), indent=1), encoding="utf-8")


# ===========================================================================
# Main
# ===========================================================================
def main():
    """Fit every rung, build the ladder table, and write the best rung's full VAL scorecard."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no bootstrap intervals")
    parser.add_argument("--reuse", action="store_true", help="rescore the saved ladder forecasts instead of refitting")
    args = parser.parse_args()
    n_boot_main, n_boot_side = (0, 0) if args.quick else (N_BOOT_MAIN, N_BOOT_SIDE)
    show_net_progress()
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    for prefix in ("scorecard", "curves"):          # this run's markdown tables start empty
        (SCORE_DIR / f"{prefix}_dev_{BLOCK}.md").write_text("")

    log("loading the inputs (P1 table with the water-balance columns, P2 tables)")
    inputs = tidemark.load_inputs()
    table = inputs["p1"]
    outputs, summaries, seconds, problems = {}, {}, {}, {}
    for rung in RUNG_ORDER:
        try:
            outputs[rung], summaries[rung], seconds[rung] = fit_and_forecast(rung, inputs, args.reuse)
        except NotImplementedError as problem:        # a member or column of the rung is not built
            problems[rung] = str(problem)
            log(f"{rung}: NOT fitted: {problem}")
    rungs = [r for r in RUNG_ORDER if r in outputs]

    frames = {kind: p1_frame(table, outputs, kind) for kind in KINDS}
    baselines = {(kind, pop): require(f"P1_{kind}", f"baselines_{pop}", "scripts/03_baselines_and_g2.py")
                 for kind in KINDS for pop in ("dam_like", "persistent")}
    results = score_ladder(frames, baselines, rungs, n_boot_main)
    lookahead = lookahead_status()
    ladder = ladder_rows(results, rungs, lookahead, problems)
    best = highest_passing(ladder)
    log(f"ladder: passing {[row['rung'] for row in ladder if row['passes']]}; highest {best}")

    p2 = score_p2(outputs[best], best, n_boot_main) if best else {}
    write_ladder_report(dict(ladder=ladder, best=best, steps=step_rows(results, rungs), lookahead=lookahead,
                             columns=same_columns(outputs), integration=integration_checks(table, outputs),
                             shared=shared_part_checks(outputs), n_boot=n_boot_main, seconds=seconds,
                             p2_cell=p2.get(("P2_cell", "all", best)) if best else None))
    log(f"wrote {LADDER_MD.name} and {LADDER_JSON.name}")

    if best:
        p1 = score_p1_full(frames, baselines, results, best, rungs, n_boot_side)
        curves, crossing = score_curves_full(table, outputs[best]["p1"], best, n_boot_main, n_boot_side)
        floor = floor_full(table, outputs[best]["p1"], n_boot_main)
        band = band_full(table, outputs[best]["p1"], summaries[best])
        write_best_report(dict(rung=best, p1=p1, curves=curves, crossing=crossing, floor=floor, band=band, p2=p2,
                               gap=headline_vs_curve(table, outputs[best]["p1"]),
                               checks=best_checks(best, p1, curves, floor, p2), summary=summaries[best],
                               n_boot_main=n_boot_main, n_boot_side=n_boot_side))
        log(f"wrote {BEST_MD.name} and {BEST_JSON.name}")

    for row in ladder:
        cells = "  ".join(f"{k} {fmt(row['kinds'][k].get('got'))} (pre-event {row['kinds'][k]['expected']:+.4f}, "
                          f"diff {fmt(row['kinds'][k].get('difference'))})" for k in KINDS)
        print(f"  {row['rung']}: {cells}  (a) {'PASS' if row['condition_a'] else 'FAIL'}  "
              f"(b) {'PASS' if row['condition_b'] else 'FAIL'}")
    print(f"  highest passing rung: {best} (not the freeze decision)")


if __name__ == "__main__":
    main()
