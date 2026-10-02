"""Step 5: the P2 season rating (the lender product), fitted on TRAIN seasons and scored on VAL only.

Run from the repo folder (after scripts/02_build_features.py and scripts/03_baselines_and_g2.py,
which saves the P2 baselines this step is compared with):
    .venv/Scripts/python.exe scripts/05_season_rating.py            # full run, about 2 minutes
    .venv/Scripts/python.exe scripts/05_season_rating.py --quick    # no bootstrap intervals

What it does
  1. Adds the area index to the P2 dam table, and checks on the real table
     that it is causal: deleting every answer from season 2012 on must not
     change any value of the ratings issued up to 1 July 2012.
  2. Fits the PREREG rating (damdays/models/season_rating.py) on the TRAIN
     seasons (1989-2008, all answered by April 2009) and predicts every
     dam-like season rated on 1 July 2009 to 1 July 2015. Cells: product.
  3. Checks that the model's starting point is exactly step 3's B2 baseline.
  4. Scores P2_cell, P2_dam and P2_dam_g against RAIN (the PREREG kill-rule
     baseline), RAIN+ (the strongest rain-only model) and B2 with the shared
     scorecard: dam (or cell) and region-year bootstrap intervals.
  5. Within-season and within-dam/cell AUC, with paired differences.
  6. The PREREG P2 pass bar and kill rule against RAIN.
  7. VAL-only ablations (one change each): no area index, no B2 start,
     trained on all waterbodies, min and best-dam cells, gradual label
     without the prior swap.
  8. Compares with the pre-event check values; writes
     artifacts/season_rating_val.md (for people) and .json (for code).

TEST is never touched: every table passed to the scorecard is checked to
hold VAL ratings only.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Let "import damdays" work when this file is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from damdays import config  # noqa: E402
from damdays.data.splits import hydro_year, time_block  # noqa: E402
from damdays.evaluation import score  # noqa: E402
from damdays.evaluation.bootstrap import cluster_bootstrap  # noqa: E402
from damdays.evaluation.inputs import join_baselines, tidy_keys  # noqa: E402
from damdays.evaluation.metrics import Ranking  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import rows  # noqa: E402
from damdays.models import season_rating as sr  # noqa: E402
from damdays.models.predictions import load_predictions, prediction_path, save_predictions  # noqa: E402

BLOCK = "VAL"
MODEL = "season_rating"
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step05_val"
RESULTS_MD = config.ARTIFACTS_DIR / "season_rating_val.md"
RESULTS_JSON = config.ARTIFACTS_DIR / "season_rating_val.json"
N_BOOT = 500
REFS = ["RAIN", "RAIN+", "B2"]                    # paired references for every P2 score
AREA_CHECK_SEASON = 2012                          # the causality check deletes answers from this season on

# PREREG P2 bars (PREREG.md "Pass bars")
PASS_BAR_DAUC = 0.05     # AUC gain over RAIN of at least 0.05, with the 95% interval above 0
KILL_RULE_DAUC = 0.02    # if RAIN comes within 0.02 AUC, the finance claim is dropped

# ---------------------------------------------------------------------------
# Check values from the pre-event research (VAL, fit TRAIN, same config).
#   season-rating/final_VAL.json   offB2_HSN_damlike_prod, 3 seeds (the PREREG P2 without the regional block)
#   hybrid/tables/val_stageG_p2.csv  BASE = the same model; ablations and the gradual prior swap
# Expected values are the pre-event numbers as stored there (4 decimals), not rounded further.
# ---------------------------------------------------------------------------
AUC_TOL, CAL_TOL = 0.006, 0.05
RAIN_NOTE = ("this build's RAIN uses causal rain deciles (step 3: AUC 0.538 cells / 0.549 dams vs 0.541 / 0.553 "
             "pre-event), so the gap to RAIN should come out about +0.003 / +0.004 larger")
RAIN_PLUS_NOTE = "RAIN+ is step 3's refit on causal inputs (cell AUC 0.631 vs 0.633 pre-event)"
CHECKS = [
    # (label, (result name, part, metric), expected, tolerance, note)
    ("P2_cell AUC", ("P2_cell", "point", "auc"), 0.7873, AUC_TOL, "FINAL_SPEC check value about 0.787"),
    ("P2_cell dAUC vs RAIN", ("P2_cell", "point", "d_auc_vs_RAIN"), 0.2464, AUC_TOL, RAIN_NOTE),
    ("P2_cell dAUC vs RAIN+", ("P2_cell", "point", "d_auc_vs_RAIN+"), 0.1547, AUC_TOL, RAIN_PLUS_NOTE),
    ("P2_cell dAUC vs B2", ("P2_cell", "point", "d_auc_vs_B2"), 0.0142, AUC_TOL, ""),
    ("P2_cell BSS vs B0", ("P2_cell", "point", "bss_B0"), 0.1489, AUC_TOL, ""),
    ("P2_cell BSS vs B2", ("P2_cell", "point", "bss_B2"), 0.0061, AUC_TOL, ""),
    ("P2_cell calibration slope", ("P2_cell", "point", "cal_slope"), 0.9272, CAL_TOL, ""),
    ("P2_cell CITL", ("P2_cell", "point", "citl"), -0.1979, CAL_TOL, "VAL over-predicts (wet 2010-12)"),
    ("P2_cell within-season AUC", ("P2_cell", "within", "season:model"), 0.7893, AUC_TOL, ""),
    ("P2_cell within-cell AUC", ("P2_cell", "within", "cell:model"), 0.5169, AUC_TOL, ""),
    ("P2_cell B2 within-season AUC", ("P2_cell", "within", "season:B2"), 0.7814, AUC_TOL, ""),
    ("P2_cell B2 within-cell AUC", ("P2_cell", "within", "cell:B2"), 0.1823, AUC_TOL, ""),
    ("P2_cell within-season AUC, model - B2", ("P2_cell", "within", "season:model_minus_B2"), 0.0079, AUC_TOL,
     "pre-event cell CI [+0.0021, +0.0132]"),
    ("P2_cell RAIN+ within-season AUC", ("P2_cell", "within", "season:RAIN+"), 0.6035, AUC_TOL, RAIN_PLUS_NOTE),
    ("P2_cell within-cell AUC, model - RAIN+", ("P2_cell", "within", "cell:model_minus_RAIN+"), -0.0866, AUC_TOL,
     "pre-event cell CI [-0.1092, -0.0643]; " + RAIN_PLUS_NOTE),
    ("P2_dam AUC", ("P2_dam", "point", "auc"), 0.7796, AUC_TOL, ""),
    ("P2_dam dAUC vs RAIN", ("P2_dam", "point", "d_auc_vs_RAIN"), 0.2264, AUC_TOL, RAIN_NOTE),
    ("P2_dam dAUC vs B2", ("P2_dam", "point", "d_auc_vs_B2"), 0.0174, AUC_TOL, ""),
    ("P2_dam BSS vs B2", ("P2_dam", "point", "bss_B2"), 0.0107, AUC_TOL, ""),
    ("P2_dam calibration slope", ("P2_dam", "point", "cal_slope"), 0.9719, CAL_TOL, ""),
    ("P2_dam CITL", ("P2_dam", "point", "citl"), -0.2344, CAL_TOL, ""),
    ("P2_dam_g AUC (prior swap)", ("P2_dam_g", "point", "auc"), 0.7670, AUC_TOL, "hybrid stage G"),
    ("P2_dam_g BSS vs B2 (prior swap)", ("P2_dam_g", "point", "bss_B2"), 0.0022, AUC_TOL, "hybrid stage G"),
    ("P2_dam_g calibration slope (prior swap)", ("P2_dam_g", "point", "cal_slope"), 0.9052, CAL_TOL,
     "hybrid stage G"),
    ("P2_dam_g CITL (prior swap)", ("P2_dam_g", "point", "citl"), -0.1930, CAL_TOL, "hybrid stage G"),
    ("P2_dam_g AUC, no prior swap", ("P2_dam_g.no_prior_swap", "point", "auc"), 0.7712, AUC_TOL, ""),
    ("P2_dam_g BSS vs B2, no prior swap", ("P2_dam_g.no_prior_swap", "point", "bss_B2"), -0.0518, AUC_TOL, ""),
    ("P2_dam_g CITL, no prior swap", ("P2_dam_g.no_prior_swap", "point", "citl"), -0.5702, CAL_TOL, ""),
    ("ablation plain (no B2 start): cell dAUC vs main", ("plain", "point", "d_auc_vs_main"), -0.0048, AUC_TOL,
     "hybrid stage G, CI [-0.0077, -0.0018]"),
    ("ablation all waterbodies: cell dAUC vs main", ("all_waterbodies", "point", "d_auc_vs_main"), -0.0089,
     AUC_TOL, "hybrid stage G, CI [-0.0134, -0.0040]"),
    ("ablation min cells: cell dAUC vs main", ("cell_min", "point", "d_auc_vs_main"), -0.0035, AUC_TOL,
     "hybrid stage G, CI [-0.0069, -0.0001]"),
    ("ablation best-dam cells: cell dAUC vs main", ("cell_best", "point", "d_auc_vs_main"), -0.0092, AUC_TOL,
     "hybrid stage G, CI [-0.0141, -0.0047]"),
]
COUNT_CHECKS = {   # (rows scored, events) that must match the pre-event research exactly
    "P2_cell": (9_848, 1_684), "P2_dam": (11_557, 2_069), "P2_dam_g": (10_949, 1_461)}
FIT_CHECK = (32_355, 5_788)   # dam-like TRAIN seasons with a known answer (docs/FEATURES.md section 7)

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def load_tables():
    """The P2 dam table with the area index, the cell table, and the waterbody attributes."""
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    dams = sr.add_area_index(store.load_p2("dam"), attrs)
    cells = store.load_p2("cell")
    return dams, cells, attrs


def check_area_index_is_causal(dams, attrs, first_deleted=AREA_CHECK_SEASON):
    """Delete every answer from season `first_deleted` on, recompute, compare (real data).

    The rating issued 1 July of season Y may use answers of seasons before Y
    only. So ratings up to season `first_deleted` must not change at all, and
    some later ones must change (otherwise the check proves nothing).
    """
    truncated = dams.copy()
    later = truncated["season"] >= first_deleted
    truncated.loc[later, "label_ok"] = False
    truncated.loc[later, ["y", "y_g", "y_R30"]] = np.nan
    full, cut = sr.area_index(dams, attrs), sr.area_index(truncated, attrs)
    upto = (dams["season"] <= first_deleted).to_numpy()
    same = (full.to_numpy() == cut.to_numpy()) | (np.isnan(full.to_numpy()) & np.isnan(cut.to_numpy()))
    result = dict(first_season_deleted=first_deleted, values_compared=int(same[upto].size),
                  values_changed_up_to_cut=int((~same[upto]).sum()),
                  values_changed_after_cut=int((~same[~upto]).sum()))
    result["passed"] = result["values_changed_up_to_cut"] == 0 and result["values_changed_after_cut"] > 0
    if not result["passed"]:
        raise AssertionError(f"Area index causality check failed: {result}")
    return result


def step3_baselines(task):
    """The P2 baselines saved by scripts/03_baselines_and_g2.py (B0, B2, PERS, RAIN, RAIN+ and the label)."""
    if not prediction_path(BLOCK, task, "baselines").exists():
        raise SystemExit("Run scripts/03_baselines_and_g2.py first: it fits and saves the P2 baselines.")
    base = load_predictions(BLOCK, task, "baselines")
    return base[["uid", "issue_date", "y", "p_B0", "p_B2", "p_RAIN", "p_RAIN+"]]


def assert_val_only(frame):
    """Refuse to score anything outside VAL (this script never looks at TEST)."""
    blocks = set(time_block(frame["issue_date"]))
    if blocks != {BLOCK}:
        raise AssertionError(f"Expected VAL ratings only, found blocks {sorted(blocks)}")


# ---------------------------------------------------------------------------
# Prediction tables for the scorecard
# ---------------------------------------------------------------------------
def dam_frame(dam_preds, label, p_column):
    """Dam-like VAL ratings: keys, flags, the scorecard label (blank unless label_ok) and p."""
    frame = pd.DataFrame({
        "uid": dam_preds["uid"].to_numpy(), "issue_date": dam_preds["issue_date"].to_numpy(),
        "region": dam_preds["region"].astype(str).to_numpy(), "hex_id": dam_preds["hex_id"].to_numpy(),
        "dam_like": dam_preds["dam_like"].to_numpy(dtype=bool),
        "persistent": dam_preds["persistent"].to_numpy(dtype=bool),
        "y": rows.p2_scored_label(dam_preds, label), "p": dam_preds[p_column].to_numpy(dtype=np.float64)})
    assert_val_only(frame)
    return frame


def cell_frame(cells, dam_preds, column="p", how="product"):
    """VAL cell ratings: keys, the cell label (all dam-like dams dry; blank unless label_ok) and p."""
    picked = cells.loc[rows.p2_block_rows(cells, BLOCK)].reset_index(drop=True)
    frame = pd.DataFrame({
        "uid": picked["uid"].astype(str).to_numpy(), "issue_date": picked["issue_date"].to_numpy(),
        "region": picked["region"].astype(str).to_numpy(), "n_dams": picked["n_dams"].to_numpy(),
        "y": rows.p2_scored_label(picked, "y"), "p": sr.cell_probability(dam_preds, picked, column, how)})
    assert_val_only(frame)
    return frame


def with_baselines(frame, task):
    """Join step 3's baselines on uid + issue_date; the labels of both tables must agree exactly."""
    return join_baselines(tidy_keys(frame), step3_baselines(task))


def expected_rows(frame, subset):
    """The (uid, issue_date) rows a P2 subset must be scored on: labelled, and dam-like for dams."""
    keep = frame["y"].notna().to_numpy()
    if subset == "dam_like":
        keep = keep & frame["dam_like"].to_numpy(dtype=bool)
    return frame.loc[keep, ["uid", "issue_date"]]


def score_table(frame, task, subset, model, refs, n_boot, write=True):
    """Score column p with the shared scorecard on exactly the expected rows."""
    assert_val_only(frame)
    return score(frame, task, subset, model=model, refs=refs, expected_keys=expected_rows(frame, subset),
                 n_boot=n_boot, out_dir=SCORE_DIR, write=write, note="step 5 (scripts/05_season_rating.py)")


# ---------------------------------------------------------------------------
# Within-season and within-dam/cell AUC, with paired differences
# ---------------------------------------------------------------------------
def within_unit_weights(w):
    """Row weights for AUC pairs taken inside ONE dam (or cell), under the dam (cell) bootstrap.

    The bootstrap gives every row of a dam drawn k times the weight k, and a
    pair of rows counts w_i x w_j times. Within a season the two rows of a pair
    are different dams, so k x m is right. Within one dam both rows carry the
    same k, so its pairs would count k x k times, while k separate copies of
    the dam hold only k times its pairs (copies are never paired with each
    other). Giving each row sqrt(k) makes every pair count k times, exactly as
    k separate copies would. Without this the within-dam interval is too wide.
    """
    return None if w is None else np.sqrt(w)


def within_auc(frame, task, subset, refs, n_boot, seed=config.RANDOM_SEED):
    """Within-group AUCs of the model and each reference, plus paired differences with dam/cell intervals.

    within season    pairs are only compared inside one July-June season: "which dams fail this summer?"
    within dam/cell  pairs only inside one dam (or cell): "in which summers does this dam fail?"
    The intervals redraw whole dams (cells), as the scorecard's dam bootstrap does; a dam drawn
    twice counts as two separate dams (see within_unit_weights).
    """
    keep = frame["y"].notna().to_numpy()
    if subset == "dam_like":
        keep = keep & frame["dam_like"].to_numpy(dtype=bool)
    scored = frame.loc[keep].reset_index(drop=True)
    y = scored["y"].to_numpy(dtype=float)
    unit = "cell" if task == "P2_cell" else "dam"
    groups = {"season": hydro_year(scored["issue_date"]), unit: scored["uid"].to_numpy()}
    columns = {"model": "p", **{ref: f"p_{ref}" for ref in refs}}
    rankings = {(name, g): Ranking(scored[col].to_numpy(dtype=float), labels)
                for name, col in columns.items() for g, labels in groups.items()}

    def metrics(w=None):
        """Every within-group AUC and every paired difference for row weights w."""
        out = {}
        for g in groups:
            weights = within_unit_weights(w) if g == unit else w
            for name in columns:
                out[f"{g}:{name}"] = rankings[(name, g)].auc(y, weights)
            for ref in refs:
                out[f"{g}:model_minus_{ref}"] = out[f"{g}:model"] - out[f"{g}:{ref}"]
        return out

    point = metrics()
    ci, _ = cluster_bootstrap(metrics, scored["uid"].to_numpy(), n_boot, seed) if n_boot > 0 else ({}, None)
    return dict(point=point, ci=ci, unit=unit)


# ---------------------------------------------------------------------------
# PREREG P2 bars
# ---------------------------------------------------------------------------
def prereg_p2_rules(result):
    """The pass bar (dAUC over RAIN >= 0.05, CI above 0) and the kill rule (RAIN within 0.02 AUC)."""
    gain = result["point"]["d_auc_vs_RAIN"]
    ci_dam = result["ci_dam"].get("d_auc_vs_RAIN")
    ci_ry = result["ci_region_year"].get("d_auc_vs_RAIN")
    # Without bootstrap intervals (--quick) the pass bar cannot be judged: it is left as None.
    passed = bool(gain >= PASS_BAR_DAUC and ci_dam[0] > 0) if ci_dam else None
    return dict(
        d_auc_vs_RAIN=gain, ci_dam=ci_dam, ci_region_year=ci_ry,
        pass_bar=dict(rule=f"dAUC vs RAIN >= {PASS_BAR_DAUC} with the dam/cell 95% interval above 0",
                      passed=passed, region_year_interval_above_0=bool(ci_ry[0] > 0) if ci_ry else None),
        kill_rule=dict(rule=f"triggered if RAIN comes within {KILL_RULE_DAUC} AUC of the rating",
                       triggered=bool(gain < KILL_RULE_DAUC)),
        gain_over_B2=dict(d_auc=result["point"]["d_auc_vs_B2"], ci_dam=result["ci_dam"].get("d_auc_vs_B2"),
                          bss_B2=result["point"]["bss_B2"], bss_B2_ci_dam=result["ci_dam"].get("bss_B2")))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def verdict(passed):
    """PASS / FAIL, or a note when the bar could not be judged (no intervals in --quick mode)."""
    return "not judged (no intervals: --quick)" if passed is None else ("PASS" if passed else "FAIL")


def fmt(value, digits=3, sign=True):
    """A number for a table cell ("-" when missing)."""
    if value is None or not np.isfinite(value):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def fmt_ci(result, metric, digits=3, sign=True):
    """Point value, then the dam (or cell) interval and the region-year interval (ry) when present."""
    text = fmt(result["point"].get(metric), digits, sign)
    for label, part in (("", "ci_dam"), ("ry ", "ci_region_year")):
        ci = result.get(part, {}).get(metric)
        if ci:
            text += f" {label}[{fmt(ci[0], digits, sign)}, {fmt(ci[1], digits, sign)}]"
    return text


def lookup(results, within, key):
    """A check's value: (name, part, metric) in the score results or the within-AUC results."""
    name, part, metric = key
    return within[name]["point"][metric] if part == "within" else results[name][part][metric]


def check_rows(results, within):
    """Every check: expected (pre-event), got (this build), difference and verdict."""
    out = []
    for label, key, expected, tolerance, note in CHECKS:
        got = lookup(results, within, key)
        out.append(dict(check=label, expected=expected, got=got, difference=got - expected, tolerance=tolerance,
                        within_tolerance=bool(abs(got - expected) <= tolerance), note=note))
    return out


def count_rows(results, fit_info):
    """Rows and events scored, and the fit size, against the pre-event counts (must match exactly)."""
    out = []
    for task, (n_rows, n_events) in COUNT_CHECKS.items():
        got = results[task]["rows"]
        out.append(dict(check=f"{task} scored rows (events)", expected=f"{n_rows:,} ({n_events:,})",
                        got=f"{got['scored']:,} ({got['events']:,})",
                        match=(got["scored"], got["events"]) == (n_rows, n_events)))
    got = (fit_info["fit_seasons"], fit_info["fit_dry"])
    out.append(dict(check="fit: dam-like TRAIN seasons (dry)", expected=f"{FIT_CHECK[0]:,} ({FIT_CHECK[1]:,})",
                    got=f"{got[0]:,} ({got[1]:,})", match=got == FIT_CHECK))
    return out


def score_lines(results, names):
    """Markdown rows: AUC, paired AUC gains over RAIN / RAIN+ / B2, skill and calibration."""
    lines = ["| task | model | rows | events | AUC [dam/cell] ry [region-year] | dAUC vs RAIN | dAUC vs RAIN+ | "
             "dAUC vs B2 | BSS vs B0 | BSS vs B2 | cal. slope | CITL | prec. at 50% recall |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in names:
        r = results[name]
        lines.append("| " + " | ".join([
            r["task"], r["model"], f"{r['rows']['scored']:,}", f"{r['rows']['events']:,}",
            fmt_ci(r, "auc", sign=False),
            *[fmt_ci(r, f"d_auc_vs_{ref}") if ref in r["refs"] else "-" for ref in REFS],
            fmt_ci(r, "bss_B0"), fmt_ci(r, "bss_B2"), fmt_ci(r, "cal_slope", 2, False), fmt(r["point"]["citl"], 2),
            fmt(r["point"]["prec_at_50_recall"], 3, False)]) + " |")
    return lines


def within_lines(within):
    """Markdown rows: within-season and within-dam/cell AUC of the model and each reference."""
    lines = ["| task | grouping | model [dam/cell CI] | B2 | RAIN | RAIN+ | model - RAIN | model - RAIN+ | model - B2 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for task, w in within.items():
        for g in ("season", w["unit"]):
            def cell(metric, sign=False):
                ci = w["ci"].get(metric)
                text = fmt(w["point"][metric], 3, sign)
                return text + (f" [{fmt(ci[0], 3, sign)}, {fmt(ci[1], 3, sign)}]" if ci else "")
            lines.append("| " + " | ".join([
                task, f"within {g}", cell(f"{g}:model"), fmt(w["point"][f"{g}:B2"], 3, False),
                fmt(w["point"][f"{g}:RAIN"], 3, False), fmt(w["point"][f"{g}:RAIN+"], 3, False),
                *[cell(f"{g}:model_minus_{ref}", True) for ref in REFS]]) + " |")
    return lines


def ablation_lines(results):
    """Markdown rows for the VAL ablations (P2_cell, paired against the main rating)."""
    lines = ["| ablation (one change) | cell AUC | dAUC vs main [cell] ry [region-year] | BSS vs B2 | cal. slope | "
             "pre-event dAUC vs main |", "|---|---|---|---|---|---|"]
    pre = {label.split(":")[0].replace("ablation ", ""): exp for label, key, exp, _, _ in CHECKS
           if label.startswith("ablation")}
    names = {"no_area_index": "no area index", "plain": "plain (no B2 start)",
             "all_waterbodies": "all waterbodies", "cell_min": "min cells", "cell_best": "best-dam cells"}
    for name, label in names.items():
        r = results[name]
        expected = next((fmt(v, 4) for k, v in pre.items() if k == label), "-")
        lines.append(f"| {label} | {fmt(r['point']['auc'], 4, False)} | {fmt_ci(r, 'd_auc_vs_main', 4)} | "
                     f"{fmt(r['point']['bss_B2'])} | {fmt(r['point']['cal_slope'], 2, False)} | {expected} |")
    return lines


def write_report(results, within, rules_cell, rules_dam, checks, counts, area_check, fit_info, n_boot):
    """artifacts/season_rating_val.md (for people) and artifacts/season_rating_val.json (for code)."""
    kill = rules_cell["kill_rule"]["triggered"]
    lines = [
        "# VAL results: the P2 season rating (build step 5)",
        "",
        f"Generated by `scripts/05_season_rating.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only**: "
        "ratings issued 1 July 2009 to 1 July 2015 in the development regions, fitted on the TRAIN seasons "
        "(1989-2008, every answer final by 30 April 2009). TEST was not scored.",
        "",
        "Model (`damdays/models/season_rating.py`, PREREG P2): LightGBM boosted from logit(B2), the dam's own "
        "past dry-season rate shrunk to the region rate (k = 5); 150 trees, 7 leaves, at least 200 seasons per "
        f"leaf, learning rate 0.03, 80% row and column sampling; 3 seeds averaged; dam-like seasons; "
        f"{fit_info['n_features']} HSN inputs (own history, shape, 1 July state, neighbour levels and the area "
        "index), no rain, no region identifier. Cell p = product of its dam-like dams' p. Gradual label: same "
        "trees, starting point swapped to the gradual B2. The regional dam-state block is dropped (PREREG).",
        "",
        f"Scores from the shared scorecard (`damdays/evaluation`), {n_boot} dam (or cell) and {n_boot} region-year "
        "bootstrap draws. Brackets: dam/cell 95% interval, then `ry` region-year interval (16 region-years: rough).",
        "",
        "## PREREG P2 bars on VAL (P2_cell)",
        "",
        "| rule | value | result |",
        "|---|---|---|",
        f"| pass bar: dAUC vs RAIN >= 0.05, CI above 0 | {fmt_ci(results['P2_cell'], 'd_auc_vs_RAIN')} | "
        f"{verdict(rules_cell['pass_bar']['passed'])} |",
        f"| kill rule: RAIN within 0.02 AUC | dAUC {fmt(rules_cell['d_auc_vs_RAIN'])} | "
        f"{'TRIGGERED: drop the finance claim' if kill else 'not triggered'} |",
        f"| gain over B2 (reported) | dAUC {fmt_ci(results['P2_cell'], 'd_auc_vs_B2')}; BSS vs B2 "
        f"{fmt_ci(results['P2_cell'], 'bss_B2')} | - |",
        f"| same bars on P2_dam | dAUC vs RAIN {fmt_ci(results['P2_dam'], 'd_auc_vs_RAIN')} | "
        f"{verdict(rules_dam['pass_bar']['passed'])}; kill rule "
        f"{'TRIGGERED' if rules_dam['kill_rule']['triggered'] else 'not triggered'} |",
        "",
        "## Check values: expected (pre-event research) vs got (this build)",
        "",
        "### Must match exactly",
        "",
        "| check | expected | got | match |",
        "|---|---|---|---|",
        *[f"| {c['check']} | {c['expected']} | {c['got']} | {'yes' if c['match'] else 'NO'} |" for c in counts],
        f"| area index unchanged up to season {area_check['first_season_deleted']} after deleting later answers "
        f"({area_check['values_compared']:,} values) | 0 changed | {area_check['values_changed_up_to_cut']} changed "
        f"({area_check['values_changed_after_cut']:,} later values changed) | "
        f"{'yes' if area_check['passed'] else 'NO'} |",
        f"| starting point = step 3's B2 baseline (dam-like VAL ratings) | 0 | max difference "
        f"{fit_info['start_vs_step3_B2']:.1e} (gradual {fit_info['start_g_vs_step3_B2']:.1e}) | "
        f"{'yes' if max(fit_info['start_vs_step3_B2'], fit_info['start_g_vs_step3_B2']) < 1e-12 else 'NO'} |",
        "",
        "### Scores",
        "",
        "| check | expected (pre-event) | got (this build) | difference | tolerance | verdict | note |",
        "|---|---|---|---|---|---|---|",
        *[f"| {c['check']} | {fmt(c['expected'], 4)} | {fmt(c['got'], 4)} | {fmt(c['difference'], 4)} | "
          f"+-{c['tolerance']:.3f} | {'within' if c['within_tolerance'] else 'OUTSIDE'} | {c['note']} |"
          for c in checks],
        "",
        "## Scores (VAL)",
        "",
        "P2_cell: a 2 km cell fails when all its dam-like dams go dry. P2_dam and P2_dam_g: dam-like dams. "
        "`season_rating` on P2_dam_g uses the prior swap; `no_prior_swap` keeps the any-dry-out start.",
        "",
        *score_lines(results, ["P2_cell", "P2_dam", "P2_dam_g", "P2_dam_g.no_prior_swap"]),
        "",
        "## Which property vs which year",
        "",
        "Within season: pairs compared only inside one summer (which dams fail this year; what a lender needs). "
        "Within dam/cell: pairs only inside one dam or cell (which summers it fails). Intervals redraw whole "
        "dams or cells; a dam drawn twice counts as two separate dams, so its own pairs count twice, not four "
        "times (`within_unit_weights`).",
        "",
        *within_lines(within),
        "",
        "## Ablations (VAL, P2_cell, paired against the main rating)",
        "",
        *ablation_lines(results),
        "",
        "## Main fit",
        "",
        f"Fit: {fit_info['fit_seasons']:,} dam-like TRAIN seasons ({fit_info['fit_dry']:,} dry); predicted "
        f"{fit_info['predicted_seasons']:,} dam-like VAL seasons; {fit_info['seconds']} s.",
        "",
        "Top inputs by split gain (share, mean of 3 seeds): " + ", ".join(
            f"{k} {v:.3f}" for k, v in fit_info["top_features_by_gain"].items()) + ".",
        "",
        "## Notes",
        "",
        *NOTES,
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")
    summary = dict(
        generated=time.strftime("%Y-%m-%d %H:%M:%S"), block=BLOCK, n_boot=n_boot, model=MODEL,
        prereg_P2_cell=rules_cell, prereg_P2_dam=rules_dam, checks=checks, exact_checks=counts,
        area_index_causality=area_check, fit=fit_info,
        within=within,
        scores={name: dict(task=r["task"], point=r["point"], ci_dam=r["ci_dam"], ci_region_year=r["ci_region_year"],
                           rows=r["rows"], refs=r["refs"]) for name, r in results.items()})
    RESULTS_JSON.write_text(json.dumps(clean_for_json(summary), indent=1), encoding="utf-8")


NOTES = [
    "- **The inputs.** The reference \"HSN\" set is own history, shape, 1 July state and neighbours, where "
    "\"neighbours\" includes a dam-based area index (share of waterbodies within 10 / 25 km that went dry last "
    "season and over all earlier seasons; built in `season_rating.area_index`). The PREREG drops a different "
    "block, the hybrid's regional dam-state block (reg_zero / reg_anom / reg_pct). The `no area index` ablation "
    "shows what the area index adds; its inputs are exactly `spec.P2_FEATURE_SPEC`.",
    "- **Disclosed (area index):** the waterbody pool (has_hist) and the dam-like flag of the dam-like version "
    "are chosen from pre-2016 looks, as for R_zero. This affects VAL (2009-2015) ratings only, not TEST or the "
    "sealed region. Past answers use the static pre-2016 full (PREREG), as do lag1 and the B2 counts.",
    "- **RAIN on VAL** uses causal rain deciles (only earlier years), as in step 3. The pre-event RAIN used a "
    "fixed 1960-2015 climatology, which peeks ahead on VAL; the two are identical from 2016 on.",
    "- **Gradual label.** The prior swap starts the same trees from the gradual B2 (past gradual dry-outs), which "
    "fixes most of the calibration gap (CITL) of the any-dry-out start; the ranking changes little.",
    "- **Calibration vs pre-event.** CITL is +0.004 to +0.005 higher than pre-event on all four tasks (mean p "
    "about 0.0006 lower) and the slope 0.003 to 0.005 lower; both well inside tolerance. The B2 start is "
    "identical to step 3's B2 and float32 vs float64 inputs change nothing, so the shift sits in the trees' "
    "corrections; most likely small step 2 feature differences (for example the purged dam-rate prior). "
    "Not traced further.",
    "- **Time checks beyond the one above** (`tests/test_season_rating_real.py`, independent review): random "
    "answers from season 2012 on, with the track record, area index, B2 start and prior all rebuilt and the "
    "model refitted, leave every rating issued up to 1 July 2012 bit-identical (most later ratings move); B2 "
    "and every area-index value are recomputed by hand for two dams.",
    "- **Predictions** (float64) are in `data_cache/preds/VAL/<task>/season_rating.pkl` for P2_dam, P2_dam_g and "
    "P2_cell; the fit summary is `data_cache/preds/VAL/P2_dam/season_rating_fit_info.json`.",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def max_gap(frame, task, column):
    """Largest |model start - step 3's B2| over the frame's rows (the two must be the same number)."""
    joined = tidy_keys(frame).merge(tidy_keys(step3_baselines(task)[["uid", "issue_date", "p_B2"]]),
                                    on=["uid", "issue_date"])
    if len(joined) != len(frame):
        raise AssertionError("Some ratings have no step 3 baseline row.")
    return float(np.abs(joined[column] - joined["p_B2"]).max())


def main():
    """Fit, predict and score the season rating on VAL, then write the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no bootstrap intervals")
    args = parser.parse_args()
    n_boot = 0 if args.quick else N_BOOT
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    (SCORE_DIR / f"scorecard_dev_{BLOCK}.md").write_text("")   # this run's markdown table starts empty

    log("loading the P2 tables and adding the area index")
    dams, cells, attrs = load_tables()
    area_check = check_area_index_is_causal(dams, attrs)
    log(f"area index causal: {area_check['values_compared']:,} values unchanged up to season "
        f"{area_check['first_season_deleted']}, {area_check['values_changed_after_cut']:,} later values changed")

    # 1. The PREREG rating.
    dam_preds, fit_info = sr.fit_and_predict(dams, BLOCK, "main")
    keys = dam_preds[["uid", "issue_date"]].assign(issue_date=pd.to_datetime(dam_preds["issue_date"]))
    fit_info["start_vs_step3_B2"] = max_gap(keys.assign(p=dam_preds["p_start"]), "P2_dam", "p")
    fit_info["start_g_vs_step3_B2"] = max_gap(keys.assign(p=dam_preds["p_start_g"]), "P2_dam_g", "p")
    log(f"main rating fitted on {fit_info['fit_seasons']:,} seasons ({fit_info['seconds']} s); start = B2 "
        f"to {max(fit_info['start_vs_step3_B2'], fit_info['start_g_vs_step3_B2']):.1e}")

    frames = {
        "P2_cell": with_baselines(cell_frame(cells, dam_preds), "P2_cell"),
        "P2_dam": with_baselines(dam_frame(dam_preds, "y", "p"), "P2_dam"),
        "P2_dam_g": with_baselines(dam_frame(dam_preds, "y_g", "p_g"), "P2_dam_g"),
        "P2_dam_g.no_prior_swap": with_baselines(dam_frame(dam_preds, "y_g", "p"), "P2_dam_g"),
    }
    subsets = {"P2_cell": "all", "P2_dam": "dam_like", "P2_dam_g": "dam_like", "P2_dam_g.no_prior_swap": "dam_like"}
    results, within = {}, {}
    for name, frame in frames.items():
        task = name.split(".")[0]
        model = MODEL if name == task else f"{MODEL}.{name.split('.')[1]}"
        results[name] = score_table(frame, task, subsets[name], model, REFS, n_boot)
        if name == task:
            within[name] = within_auc(frame, task, subsets[name], REFS, n_boot)
        log(f"{name}: AUC {results[name]['point']['auc']:.4f}, dAUC vs RAIN "
            f"{results[name]['point']['d_auc_vs_RAIN']:+.4f}")
    save_predictions(frames["P2_cell"][["uid", "issue_date", "region", "n_dams", "y", "p"]], BLOCK, "P2_cell", MODEL)
    for task in ("P2_dam", "P2_dam_g"):
        saved = frames[task][["uid", "issue_date", "region", "hex_id", "dam_like", "persistent", "y", "p"]]
        save_predictions(saved, BLOCK, task, MODEL)
    fit_path = prediction_path(BLOCK, "P2_dam", f"{MODEL}_fit_info").with_suffix(".json")
    fit_path.write_text(json.dumps(clean_for_json(fit_info), indent=1))

    # 2. Ablations on P2_cell, each paired against the main rating.
    main_cell = frames["P2_cell"]
    ablation_cells = {"cell_min": cell_frame(cells, dam_preds, how="min"),
                      "cell_best": cell_frame(cells, dam_preds, how="best")}
    for variant in ("no_area_index", "plain", "all_waterbodies"):
        variant_preds, _ = sr.fit_and_predict(dams, BLOCK, variant)
        ablation_cells[variant] = cell_frame(cells, variant_preds)
    for name, frame in ablation_cells.items():
        frame = with_baselines(frame, "P2_cell")
        if not frame[["uid", "issue_date"]].equals(main_cell[["uid", "issue_date"]]):
            raise AssertionError("Ablation and main cell tables are not row-aligned.")
        frame["p_main"] = main_cell["p"].to_numpy()
        results[name] = score_table(frame, "P2_cell", "all", f"{MODEL}.{name}", ["main", "RAIN"], n_boot,
                                    write=False)
        log(f"ablation {name}: cell AUC {results[name]['point']['auc']:.4f}, dAUC vs main "
            f"{results[name]['point']['d_auc_vs_main']:+.4f}")

    # 3. Rules, checks and the report.
    rules_cell, rules_dam = prereg_p2_rules(results["P2_cell"]), prereg_p2_rules(results["P2_dam"])
    checks = check_rows(results, within)
    counts = count_rows(results, fit_info)
    write_report(results, within, rules_cell, rules_dam, checks, counts, area_check, fit_info, n_boot)
    log(f"wrote {RESULTS_MD.name} and {RESULTS_JSON.name}")
    print(f"  PREREG P2 pass bar (cell): {verdict(rules_cell['pass_bar']['passed'])}; kill rule: "
          f"{'TRIGGERED' if rules_cell['kill_rule']['triggered'] else 'not triggered'}")
    for c in counts:
        print(f"  {c['check']:<55s} expected {c['expected']:<18s} got {c['got']:<18s} "
              f"{'ok' if c['match'] else 'MISMATCH'}")
    for c in checks:
        print(f"  {c['check']:<55s} expected {c['expected']:+.4f} got {c['got']:+.4f} "
              f"diff {c['difference']:+.4f} {'ok' if c['within_tolerance'] else 'OUTSIDE'}")


if __name__ == "__main__":
    main()
