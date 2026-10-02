"""Step 4: Tidemark rung L1 on VAL: the tree member T, the per-dam frailty, the R30 max rule.

Run from the repo folder (after scripts/03_baselines_and_g2.py, whose VAL
baselines and G2 predictions it reuses as references):
    .venv/Scripts/python.exe scripts/04_tidemark_l1.py            # full run, about 30 minutes
    .venv/Scripts/python.exe scripts/04_tidemark_l1.py --quick    # no bootstrap intervals
    .venv/Scripts/python.exe scripts/04_tidemark_l1.py --reuse    # rescore saved predictions, no refits

What it does, for each event kind (D0 first: the R30 headline needs it)
  1. Fits the tree member T (the 29 G2c features, all waterbodies, purged
     TRAIN rows, seed 0, 3 threads) and predicts every at-risk forecast from
     1988 to 2015 (the frailty needs the dam's past forecasts too).
  2. Fuses the members into the anchor. Today T is the only member, so the
     anchor is T; the nets (S, M) and the physics columns plug in later.
  3. Adds each dam's frailty b = R / (V + 100), from its own past forecasts
     whose answer was final (issued at least 120 days earlier).
  4. R30 only: headline = max(p_R30, p_D0).
  5. Scores T alone and L1 on VAL with the shared scorecard, paired against T
     (that difference is the frailty gain) and against G2 (the benchmark).
  6. Compares with the pre-event check values and writes
     artifacts/tree_frailty_val.md (for people) and .json (for code).
     (Named after its parts: on Windows "val_tidemark_l1.md" would be the same file as
     step 8's integrated report artifacts/val_tidemark_L1.md.)

"L1" here is the build plan's Saturday 07:30 rung: tree + random intercept,
without the hazard curve (built later) and without the physics columns (not
built yet). Its like-for-like pre-event twin is "G2c+RE" in the
hierarchical-pooling research (same tree, same frailty, lambda 100).

TEST is never touched: every model learns from rows answered before
2009-01-01, and every table passed to the scorecard holds VAL issues only.
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
from damdays.data.splits import time_block  # noqa: E402
from damdays.evaluation import score  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import baselines, frailty, fusion, rows  # noqa: E402
from damdays.models.predictions import load_predictions, prediction_path, save_predictions  # noqa: E402

BLOCK = "VAL"
KINDS = ("D0", "R30", "D0g")              # D0 before R30: the R30 headline is max(p_R30, p_D0)
PRED_NAME = "tidemark_L1"
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step04_val"
RESULTS_MD = config.ARTIFACTS_DIR / "tree_frailty_val.md"
RESULTS_JSON = config.ARTIFACTS_DIR / "tree_frailty_val.json"
N_BOOT_MAIN, N_BOOT_SIDE = 500, 200       # bootstrap draws: primary sets, other subsets

# P1 subsets: (scorecard subset, population the baselines were fitted on, Oct-Mar issues only?)
P1_SUBSETS = [
    ("primary", "dam_like", True),                       # the pre-registered headline set
    ("persistent+octmar+at_risk", "persistent", True),   # dams that rarely dry out (harder)
    ("dam_like+at_risk", "dam_like", False),             # dam-like, all months
]
# Models scored, as (column suffix, references for paired differences). "T" = tree member alone;
# "L1" = T + frailty (+ the max rule for R30); "L1_premax" = R30 before the max rule.
MODELS = {
    "D0": [("T", ["G2"]), ("L1", ["T", "G2"])],
    "R30": [("T", ["G2"]), ("L1_premax", ["T", "G2"]), ("L1", ["T", "G2", "L1_premax"])],
    "D0g": [("T", ["G2"]), ("L1", ["T", "G2"])],
}
SCORECARD_NAME = {"T": "tidemark_T", "L1": "tidemark_L1", "L1_premax": "tidemark_L1_premax"}
LAMBDA_SWEEP = (25, 50, 100, 200, 400, 800, 1600)   # diagnostic only: lambda is fixed at 100 by the PREREG


# ---------------------------------------------------------------------------
# Check values from the pre-event research (bench/results/hierarchical-pooling, VAL).
# "G2c+RE" there = this L1 without the max rule: the G2c features on all
# waterbodies (this build's G2 recipe), purged TRAIN, + the frailty, lambda 100.
# ---------------------------------------------------------------------------
LADDER_TOLERANCE = 0.006                  # PREREG fallback ladder: reproduce VAL BSS within +-0.006
LEVEL_CHECKS = [
    # (label, (task, subset, model, metric), expected, tolerance, source)
    ("R30 T alone, BSS vs B0", ("P1_R30", "primary", "T", "bss_B0"), 0.1707, LADDER_TOLERANCE,
     "bench G2c (= this build's G2 recipe)"),
    ("D0 T alone, BSS vs B0", ("P1_D0", "primary", "T", "bss_B0"), 0.1755, LADDER_TOLERANCE, "bench G2c"),
    ("D0g T alone, BSS vs B0", ("P1_D0g", "primary", "T", "bss_B0"), 0.1727, LADDER_TOLERANCE,
     "bench G2c (hybrid stage A table)"),
    ("R30 L1 before max rule, BSS vs B0", ("P1_R30", "primary", "L1_premax", "bss_B0"), 0.1727, LADDER_TOLERANCE,
     "bench G2c+RE"),
    ("R30 L1 headline, BSS vs B0", ("P1_R30", "primary", "L1", "bss_B0"), 0.1727, LADDER_TOLERANCE,
     "bench G2c+RE; the max rule moved VAL BSS by 0.0000 in the hybrid"),
    ("R30 L1, BSS vs B2", ("P1_R30", "primary", "L1_premax", "bss_B2"), 0.1014, LADDER_TOLERANCE, "bench G2c+RE"),
    ("R30 L1, AUC", ("P1_R30", "primary", "L1_premax", "auc"), 0.7819, LADDER_TOLERANCE, "bench G2c+RE"),
    ("R30 L1, calibration slope", ("P1_R30", "primary", "L1_premax", "cal_slope"), 0.9692, 0.05, "bench G2c+RE"),
    ("R30 L1 persistent, BSS vs B0", ("P1_R30", "persistent+octmar+at_risk", "L1_premax", "bss_B0"), 0.1383,
     LADDER_TOLERANCE, "bench G2c+RE"),
    ("D0 L1, BSS vs B0", ("P1_D0", "primary", "L1", "bss_B0"), 0.1771, LADDER_TOLERANCE, "bench G2c+RE"),
    ("D0 L1, BSS vs B2", ("P1_D0", "primary", "L1", "bss_B2"), 0.0941, LADDER_TOLERANCE, "bench G2c+RE"),
    ("D0 L1, AUC", ("P1_D0", "primary", "L1", "auc"), 0.8328, LADDER_TOLERANCE, "bench G2c+RE"),
    ("D0 L1, calibration slope", ("P1_D0", "primary", "L1", "cal_slope"), 1.0103, 0.05, "bench G2c+RE"),
    ("D0 L1 persistent, BSS vs B0", ("P1_D0", "persistent+octmar+at_risk", "L1", "bss_B0"), 0.0819,
     LADDER_TOLERANCE, "bench G2c+RE"),
]
GAIN_CHECKS = [
    # (label, (task, subset, model, reference), bench point, bench dam 95% interval or None, like for like?, source)
    ("R30 frailty gain, primary", ("P1_R30", "primary", "L1_premax", "T"), 0.0024, (0.0004, 0.0042), True,
     "bench G2c+RE vs G2c"),
    ("R30 frailty gain, persistent", ("P1_R30", "persistent+octmar+at_risk", "L1_premax", "T"), 0.0039,
     (0.0018, 0.0066), True, "bench G2c+RE vs G2c"),
    ("D0 frailty gain, primary", ("P1_D0", "primary", "L1", "T"), 0.0020, (0.0002, 0.0041), True,
     "bench G2c+RE vs G2c"),
    ("D0 frailty gain, persistent", ("P1_D0", "persistent+octmar+at_risk", "L1", "T"), 0.0033, (0.0006, 0.0063),
     True, "bench G2c+RE vs G2c"),
    ("D0g frailty gain, primary", ("P1_D0g", "primary", "L1", "T"), 0.0005, (-0.0014, 0.0024), False,
     "no twin without nets: the hybrid's frailty removal cost in the full model with nets and dam-like T (stage B)"),
    ("R30 max rule effect, primary", ("P1_R30", "primary", "L1", "L1_premax"), 0.0000, None, False,
     "no twin without nets: hybrid decision log, full model with nets (G2c+RE had no max rule)"),
]
BRIER_CHECKS = {   # bench VAL primary-set Brier: without frailty, then for each lambda of the sweep (log_hp03)
    "R30": dict(none=0.14889, lam={25: 0.148877, 50: 0.148599, 100: 0.148532, 200: 0.148595, 400: 0.148694,
                                   800: 0.148775, 1600: 0.148826}),
    "D0": dict(none=0.08315, lam={25: 0.083138, 50: 0.083012, 100: 0.082988, 200: 0.083022, 400: 0.083068,
                                  800: 0.083105, 1600: 0.083127}),
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


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


def is_octmar(dates):
    """True for issue dates in October to March."""
    return np.isin(pd.DatetimeIndex(pd.to_datetime(dates)).month, config.SEASON_MONTHS)


def fmt(value, digits=4, sign=True):
    """A number for a table cell ("-" when missing)."""
    if value is None or not np.isfinite(value):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


# ---------------------------------------------------------------------------
# 1-4. Predictions
# ---------------------------------------------------------------------------
def kind_predictions(table, kind):
    """T and L1 (before the R30 max rule) on every history row of one kind; plus T's fit info."""
    started = time.time()
    tree, info = fusion.fit_tree_member(table, kind, BLOCK)
    info["seconds"] = round(time.time() - started)
    log(f"P1_{kind} T: fit rows {info['fit_rows']:,} ({info['fit_events']:,} events), "
        f"predicted {info['predicted_rows']:,} history rows, {info['seconds']} s")

    label = table[rows.p1_label(kind)].to_numpy(dtype=float)[tree["row"].to_numpy()]
    is_record = fusion.track_record_mask(table, kind, tree["row"].to_numpy())
    members = {"T": tree["p_T"].to_numpy()}         # later: + {"S": [3 seeds], "M": [3 seeds]}
    history = fusion.anchor_with_frailty(tree, members, label, is_record)
    history["p_T"] = tree["p_T"].to_numpy()
    history["y"] = label
    history["is_record"] = is_record
    info["track_records"] = int(is_record.sum())
    return history, info


def val_frame(table, kind):
    """Keys, flags and the scorecard label for every at-risk VAL forecast of `kind` (as in step 3)."""
    picked = table.loc[rows.p1_block_rows(table, kind, BLOCK)]
    return pd.DataFrame({
        "uid": picked["uid"].astype(str).to_numpy(), "issue_date": picked["issue_date"].to_numpy(),
        "region": picked["region"].astype(str).to_numpy(),
        "dam_like": picked["dam_like"].to_numpy(dtype=bool), "persistent": picked["persistent"].to_numpy(dtype=bool),
        "at_risk": True,   # every row here is at risk for this kind (p1_block_rows)
        "y": rows.p1_scored_label(picked, kind),                       # blank where label_ok is False
    })


def build_predictions(table):
    """Every kind's VAL predictions (p_T, p_L1, frailty columns) and fit info; saves them."""
    history, frames, info = {}, {}, {}
    for kind in KINDS:
        history[kind], info[kind] = kind_predictions(table, kind)
    # R30 headline: compare with the D0 forecast for the same issue (same row of the P1 table).
    premax = history["R30"]["p"].to_numpy()
    headline, raised_share = fusion.r30_headline(history["R30"], history["D0"])
    history["R30"]["p_premax"] = premax
    history["R30"]["p"] = headline
    info["R30"]["max_rule_raised_share_history"] = raised_share

    for kind in KINDS:
        val = fusion.block_part(history[kind], BLOCK)
        frame = val_frame(table, kind)
        columns = ["p_T", "p_anchor", "frailty_b", "frailty_R", "frailty_V", "frailty_n", "p"]
        columns += ["p_premax"] if kind == "R30" else []
        attach(frame, val, columns)
        frame["p_L1"] = frame["p"]
        if kind == "R30":
            frame["p_L1_premax"] = frame["p_premax"]
            info[kind]["max_rule_raised_share_val"] = float((frame["p_L1"] > frame["p_L1_premax"]).mean())
        frames[kind] = frame
        save_predictions(frame, BLOCK, f"P1_{kind}", PRED_NAME)
        path = prediction_path(BLOCK, f"P1_{kind}", f"{PRED_NAME}_fit_info").with_suffix(".json")
        path.write_text(json.dumps(clean_for_json(info[kind]), indent=1))
    log("VAL predictions saved to data_cache/preds/VAL/<task>/tidemark_L1.pkl")
    return frames, info


def load_saved(kind):
    """Saved VAL predictions and fit info of one kind (for --reuse)."""
    frame = load_predictions(BLOCK, f"P1_{kind}", PRED_NAME)
    info = json.loads(prediction_path(BLOCK, f"P1_{kind}", f"{PRED_NAME}_fit_info").with_suffix(".json").read_text())
    return frame, info


# ---------------------------------------------------------------------------
# References from step 3: the baselines and the G2 benchmark
# ---------------------------------------------------------------------------
def step3_references(table, kind, frame):
    """{population: baselines} and G2's predictions, all row-aligned with `frame`; refitted if step 3's are missing."""
    task = f"P1_{kind}"
    base = {}
    for population in ("dam_like", "persistent"):
        if prediction_path(BLOCK, task, f"baselines_{population}").exists():
            base[population] = load_predictions(BLOCK, task, f"baselines_{population}")
        else:
            base[population] = baselines.p1_baselines(table, kind, BLOCK, population)
    attach(frame, load_predictions(BLOCK, task, "models"), ["p_G2"])
    return base


def tree_vs_g2(frame):
    """How close T is to the step-3 G2 (same recipe; only the thread count differs: 3 here, 4 there)."""
    gap = np.abs(frame["p_T"].to_numpy() - frame["p_G2"].to_numpy())
    return dict(max_abs_diff=float(gap.max()), mean_abs_diff=float(gap.mean()), identical_rows=float((gap == 0).mean()))


# ---------------------------------------------------------------------------
# 5. Scoring
# ---------------------------------------------------------------------------
def expected_keys(frame, population, octmar_only):
    """The rows a P1 subset must be scored on, worked out here independently of the scorecard."""
    keep = frame["y"].notna().to_numpy() & frame[population].to_numpy(dtype=bool)
    if octmar_only:
        keep = keep & is_octmar(frame["issue_date"])
    return frame.loc[keep, ["uid", "issue_date"]]


def score_kind(kind, frame, base, n_boot_main, n_boot_side):
    """Every model of one kind on every subset; returns {(task, subset, model): result}."""
    task = f"P1_{kind}"
    results = {}
    for subset, population, octmar_only in P1_SUBSETS:
        table = attach(frame.copy(), base[population], ["p_B0", "p_B2"])
        assert_val_only(table)
        expected = expected_keys(frame, population, octmar_only)
        n_boot = n_boot_main if subset == "primary" else n_boot_side
        for model, refs in MODELS[kind]:
            scored = table.assign(p=table[f"p_{model}"])
            results[(task, subset, model)] = score(
                scored, task, subset, model=SCORECARD_NAME[model], refs=refs, expected_keys=expected,
                n_boot=n_boot, out_dir=SCORE_DIR, note="step 4 (scripts/04_tidemark_l1.py)")
        log(f"{task} {subset}: scored {len(MODELS[kind])} models")
    return results


def primary_mask(frame):
    """Labelled rows of the primary set (dam-like, Oct-Mar, at risk) in a VAL frame."""
    return frame["y"].notna().to_numpy() & frame["dam_like"].to_numpy(dtype=bool) & is_octmar(frame["issue_date"])


def lambda_sweep(frame):
    """Primary-set Brier score for each lambda (diagnostic only; the PREREG fixes lambda = 100).

    Rebuilt from the saved R, V and the anchor, so it needs no refit.
    """
    keep = primary_mask(frame)
    y = frame.loc[keep, "y"].to_numpy(dtype=float)
    z = fusion.logit(frame.loc[keep, "p_anchor"].to_numpy())
    R, V = frame.loc[keep, "frailty_R"].to_numpy(), frame.loc[keep, "frailty_V"].to_numpy()
    out = {"none": float(np.mean((fusion.sigmoid(z) - y) ** 2))}
    for lam in LAMBDA_SWEEP:
        p = fusion.sigmoid(z + frailty.frailty_offset(R, V, lam))
        out[lam] = float(np.mean((p - y) ** 2))
    return out


def frailty_summary(frame):
    """What the frailty looks like on the primary set: how much history, how big the shifts."""
    keep = primary_mask(frame)
    b, n = frame.loc[keep, "frailty_b"].to_numpy(), frame.loc[keep, "frailty_n"].to_numpy()
    labels = pd.Series(frailty.frailty_label(b)).value_counts(normalize=True).round(3).to_dict()
    return dict(rows=int(keep.sum()), median_records=float(np.median(n)), share_no_records=float((n == 0).mean()),
                b_mean=float(b.mean()), b_sd=float(b.std()), b_p05=float(np.percentile(b, 5)),
                b_p95=float(np.percentile(b, 95)), b_min=float(b.min()), b_max=float(b.max()), label_shares=labels)


# ---------------------------------------------------------------------------
# 6. Report
# ---------------------------------------------------------------------------
def level_check_rows(results):
    """Level checks: expected (bench), got, difference, verdict."""
    out = []
    for label, (task, subset, model, metric), expected, tolerance, source in LEVEL_CHECKS:
        got = results[(task, subset, model)]["point"][metric]
        out.append(dict(check=label, expected=expected, got=got, difference=got - expected, tolerance=tolerance,
                        within=bool(abs(got - expected) <= tolerance), source=source))
    return out


def gain_check_rows(results):
    """Paired-gain checks: this build's gain and dam interval vs the bench's point and interval."""
    out = []
    for label, (task, subset, model, ref), expected, bench_ci, like_for_like, source in GAIN_CHECKS:
        result = results[(task, subset, model)]
        metric = f"d_bss_B0_vs_{ref}"
        got = result["point"][metric]
        inside = bool(bench_ci[0] <= got <= bench_ci[1]) if bench_ci else None
        out.append(dict(check=label, expected=expected, bench_ci=list(bench_ci) if bench_ci else None, got=got,
                        got_ci=result["ci_dam"].get(metric), like_for_like=like_for_like,
                        inside_bench_ci=inside, source=source))
    return out


def gain_verdict(check):
    """"yes" / "NO" for like-for-like gains (is ours inside the bench interval?); "context" otherwise."""
    if not check["like_for_like"]:
        return "context only"
    return "yes" if check["inside_bench_ci"] else "NO"


def max_rule_diagnostic(table, r30):
    """Where the R30 max rule raised the forecast (primary set), and what actually happened there.

    r30  the VAL R30 frame (p_L1 after the rule, p_L1_premax before it), in P1 table order.
    y_D0 comes from the same forecasts' D0 label: a D0 event without an R30 event is possible
    because the two kinds are armed separately (an R30 event uses up the R30 arming).
    """
    picked = table.loc[rows.p1_block_rows(table, "R30", BLOCK)]
    y_d0 = rows.p1_scored_label(picked, "D0")
    keep = primary_mask(r30)
    raised = keep & (r30["p_L1"].to_numpy() > r30["p_L1_premax"].to_numpy())
    y = r30["y"].to_numpy(dtype=float)
    return dict(primary_rows=int(keep.sum()), raised_rows=int(raised.sum()), raised_share=float(raised.sum() / keep.sum()),
                raised_mean_p_before=float(r30["p_L1_premax"].to_numpy()[raised].mean()),
                raised_mean_p_after=float(r30["p_L1"].to_numpy()[raised].mean()),
                raised_r30_event_rate=float(y[raised].mean()),
                d0_without_r30_share_primary=float(np.mean((y_d0[keep] == 1) & (y[keep] == 0))))


def fmt_ci(result, metric, digits=4, sign=True):
    """Point value with the dam interval and the region-year interval (ry) when present."""
    text = fmt(result["point"].get(metric), digits, sign)
    for label, ci in (("", result["ci_dam"].get(metric)), ("ry ", result["ci_region_year"].get(metric))):
        if ci:
            text += f" {label}[{fmt(ci[0], digits, sign)}, {fmt(ci[1], digits, sign)}]"
    return text


def scorecard_lines(results):
    """Markdown table of every score."""
    lines = ["| task | subset | model | rows | events | BSS vs B0 [dam] ry [region-year] | BSS vs B2 | AUC | "
             "cal. slope | CITL | prec. at 50% recall | paired (BSS-vs-B0 units) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for (task, subset, model), r in results.items():
        paired = "; ".join(f"vs {ref}: {fmt_ci(r, 'd_bss_B0_vs_' + ref)}" for ref in r["refs"]) or "-"
        lines.append("| " + " | ".join([
            task, subset, model, f"{r['rows']['scored']:,}", f"{r['rows']['events']:,}", fmt_ci(r, "bss_B0", 3),
            fmt(r["point"]["bss_B2"], 3), fmt_ci(r, "auc", 3, sign=False), fmt(r["point"]["cal_slope"], 2, False),
            fmt(r["point"]["citl"], 2), fmt(r["point"]["prec_at_50_recall"], 3, False), paired]) + " |")
    return lines


def write_report(results, levels, gains, max_rule, sweeps, summaries, g2_gap, info, n_boot_main):
    """artifacts/tree_frailty_val.md (for people) and .json (for code)."""
    lines = [
        "# VAL results: Tidemark rung L1 (tree + per-dam frailty), build step 4",
        "",
        f"Generated by `scripts/04_tidemark_l1.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only** "
        "(forecasts issued 2009-01-01 to 2015-12-31, development regions). TEST was not scored.",
        "",
        "**What L1 is here.** The tree member T (LightGBM on the 29 G2c features, trained on all waterbodies, "
        "purged TRAIN rows, seed 0), fused (today T is the only member), plus each dam's frailty "
        "b = R / (V + 100) from its own forecasts whose answer was final (issued at least 120 days earlier). "
        "For R30 the headline is max(p_R30, p_D0). Not yet included: the hazard runway curve (L1's third part, "
        "built later), the physics columns (L2/L3) and the nets (L3).",
        "",
        f"Scores come from the shared scorecard with {n_boot_main} dam and {n_boot_main} region-year bootstrap "
        "draws on the primary sets. Paired differences are in BSS-vs-B0 units: \"vs T\" is the frailty gain, "
        "\"vs G2\" the gain over the benchmark.",
        "",
        "## Check values: expected (pre-event research) vs got (this build)",
        "",
        "The like-for-like pre-event twin is **G2c+RE** (hierarchical-pooling family): the same tree recipe and "
        "the same frailty (lambda 100), without the R30 max rule. The PREREG ladder tolerance is +-0.006.",
        "",
        "| check | expected | got | difference | tolerance | verdict | source |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in levels:
        lines.append(f"| {c['check']} | {fmt(c['expected'])} | {fmt(c['got'])} | {fmt(c['difference'])} | "
                     f"+-{c['tolerance']:.3f} | {'within' if c['within'] else 'OUTSIDE'} | {c['source']} |")
    lines += [
        "",
        "### Frailty gain (paired, same rows) vs the pre-event gain",
        "",
        "| check | expected [bench dam 95% CI] | got [dam 95% CI] | inside bench CI? | source |",
        "|---|---|---|---|---|",
    ]
    for c in gains:
        got_ci = f" [{fmt(c['got_ci'][0])}, {fmt(c['got_ci'][1])}]" if c["got_ci"] else ""
        bench_ci = f" [{fmt(c['bench_ci'][0])}, {fmt(c['bench_ci'][1])}]" if c["bench_ci"] else ""
        lines.append(f"| {c['check']} | {fmt(c['expected'])}{bench_ci} | {fmt(c['got'])}{got_ci} | "
                     f"{gain_verdict(c)} | {c['source']} |")
    m = max_rule
    lines += [
        "",
        f"**The R30 max rule on the primary set.** It raised {m['raised_rows']:,} of {m['primary_rows']:,} forecasts "
        f"({100 * m['raised_share']:.1f}%), from a mean of {m['raised_mean_p_before']:.3f} to {m['raised_mean_p_after']:.3f}. "
        f"The R30 event rate on those rows was {m['raised_r30_event_rate']:.3f}: VAL is over-predicted there "
        "(the wet 2010-12 years), so pushing them up costs a little Brier skill. A D0 event without an R30 event "
        f"happened on {100 * m['d0_without_r30_share_primary']:.2f}% of primary rows (the two kinds are armed "
        "separately). The rule is pre-registered and stays. The pre-event -0.0000 came from the full model with "
        "nets, so it is context, not a like-for-like check.",
    ]
    lines += [
        "",
        "### Lambda sweep (diagnostic only; the PREREG fixes lambda = 100)",
        "",
        "Primary-set Brier score with no frailty and with each lambda. The pre-event research picked lambda on "
        "this same curve; reproducing it checks the frailty sums end to end.",
        "",
        "| kind | source | no frailty | " + " | ".join(f"lambda {lam}" for lam in LAMBDA_SWEEP) + " |",
        "|---|---|---|" + "---|" * len(LAMBDA_SWEEP),
    ]
    for kind in KINDS:
        sweep = sweeps[kind]
        lines.append(f"| {kind} | this build | {sweep['none']:.6f} | "
                     + " | ".join(f"{sweep[lam]:.6f}" for lam in LAMBDA_SWEEP) + " |")
        if kind in BRIER_CHECKS:
            bench = BRIER_CHECKS[kind]
            lines.append(f"| {kind} | pre-event | {bench['none']:.5f} | "
                         + " | ".join(f"{bench['lam'][lam]:.6f}" for lam in LAMBDA_SWEEP) + " |")
    lines += [
        "",
        "### T against the step-3 G2 (same recipe; 3 threads here, 4 there)",
        "",
        "| kind | max abs difference in p | mean abs difference | share of rows identical |",
        "|---|---|---|---|",
    ]
    for kind in KINDS:
        gap = g2_gap[kind]
        lines.append(f"| {kind} | {gap['max_abs_diff']:.2e} | {gap['mean_abs_diff']:.2e} | {gap['identical_rows']:.4f} |")
    lines += [
        "",
        "## What the frailty looks like (primary set)",
        "",
        "| kind | rows | median past forecasts used | share with none yet | mean b | sd b | 5% / 95% of b | min / max b |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for kind in KINDS:
        s = summaries[kind]
        lines.append(f"| {kind} | {s['rows']:,} | {s['median_records']:.0f} | {s['share_no_records']:.3f} | "
                     f"{s['b_mean']:+.3f} | {s['b_sd']:.3f} | {s['b_p05']:+.3f} / {s['b_p95']:+.3f} | "
                     f"{s['b_min']:+.3f} / {s['b_max']:+.3f} |")
    r30 = info["R30"]
    lines += [
        "",
        f"R30 max rule: p_D0 was above p_R30 on {100 * r30['max_rule_raised_share_val']:.2f}% of the VAL R30 "
        "forecasts (all months, all waterbodies), so the headline was raised there.",
        "",
        "## Scorecard",
        "",
        *scorecard_lines(results),
        "",
        "## T fits",
        "",
        "| kind | fit rows | events | history rows predicted | track records | seconds | top features by gain |",
        "|---|---|---|---|---|---|---|",
    ]
    for kind in KINDS:
        i = info[kind]
        top = ", ".join(f"{name} {share:.2f}" for name, share in list(i["top_features_by_gain"].items())[:5])
        lines.append(f"| {kind} | {i['fit_rows']:,} | {i['fit_events']:,} | {i['predicted_rows']:,} | "
                     f"{i['track_records']:,} | {i.get('seconds', '-')} | {top} |")
    lines += ["", "## Notes", "", *NOTES, ""]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")

    summary = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), block=BLOCK, n_boot_main=n_boot_main,
                   level_checks=levels, gain_checks=gains, max_rule_primary=max_rule, lambda_sweep={k: {str(a): b for a, b in v.items()}
                                                                          for k, v in sweeps.items()},
                   bench_lambda_sweep=BRIER_CHECKS, tree_vs_g2=g2_gap, frailty_summary=summaries, fit_info=info,
                   scores={"|".join(k): dict(point=v["point"], ci_dam=v["ci_dam"], ci_region_year=v["ci_region_year"],
                                             rows=v["rows"], refs=v["refs"]) for k, v in results.items()})
    RESULTS_JSON.write_text(json.dumps(clean_for_json(summary), indent=1), encoding="utf-8")


NOTES = [
    "- **Time rule.** A past forecast shapes a dam's frailty only once its answer is final: issued at least 120 "
    "days earlier (90-day window + 30 days to confirm). The unit tests in `tests/test_frailty_fusion.py` prove "
    "the boundary (exactly 120 days counts, 119 does not) and that an unfinished record cannot move b: the sums "
    "stay bit-identical when unfinished records (or other dams' records) change. `tests/test_no_lookahead.py` "
    "rebuilds the sums from data truncated at a cut date and finds them bit-identical before the cut, and it "
    "catches a planted leak (records counted without the 120-day wait).",
    "- **Track records** are the dam's at-risk forecasts with a determinable, known label (label_ok). The "
    "probability used is the anchor before frailty, from the tree fitted on purged TRAIN; for TRAIN forecasts "
    "that is an in-sample prediction, as in the pre-event research.",
    "- **Baselines and G2** are step 3's (purged). The pre-event B0 was fitted on unpurged TRAIN rows; step 3 "
    "showed this moves BSS vs B0 by about 0.0003.",
    "- **D0-gradual** frailty uses the D0g label: windows holding only an abrupt dry-out have no label and are "
    "not track records.",
    "- **Predictions** (float64) are in `data_cache/preds/VAL/<task>/tidemark_L1.pkl`: p_T, p_anchor, frailty_b, "
    "frailty_R, frailty_V, frailty_n, p (= p_L1; for R30 after the max rule) and p_premax (R30).",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    """Fit, predict and score L1 on VAL, then write the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no bootstrap intervals")
    parser.add_argument("--reuse", action="store_true", help="rescore saved predictions instead of refitting")
    args = parser.parse_args()
    n_boot_main, n_boot_side = (0, 0) if args.quick else (N_BOOT_MAIN, N_BOOT_SIDE)

    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    (SCORE_DIR / f"scorecard_dev_{BLOCK}.md").write_text("")   # this run's markdown table starts empty

    log("loading the P1 table (keys, dam history, neighbours)")
    table = store.load_p1(groups=("keys", "dam", "nbr"))
    if args.reuse:
        loaded = {kind: load_saved(kind) for kind in KINDS}
        frames, info = {k: v[0] for k, v in loaded.items()}, {k: v[1] for k, v in loaded.items()}
    else:
        frames, info = build_predictions(table)

    results, sweeps, summaries, g2_gap = {}, {}, {}, {}
    for kind in KINDS:
        frame = frames[kind]
        base = step3_references(table, kind, frame)
        g2_gap[kind] = tree_vs_g2(frame)
        sweeps[kind] = lambda_sweep(frame)
        summaries[kind] = frailty_summary(frame)
        results.update(score_kind(kind, frame, base, n_boot_main, n_boot_side))
    max_rule = max_rule_diagnostic(table, frames["R30"])
    del table

    levels, gains = level_check_rows(results), gain_check_rows(results)
    write_report(results, levels, gains, max_rule, sweeps, summaries, g2_gap, info, n_boot_main)
    log(f"wrote {RESULTS_MD.name} and {RESULTS_JSON.name}")
    for c in levels:
        print(f"  {c['check']:<40s} expected {c['expected']:+.4f} got {c['got']:+.4f} "
              f"diff {c['difference']:+.4f} {'ok' if c['within'] else 'OUTSIDE'}")
    for c in gains:
        print(f"  {c['check']:<40s} expected {c['expected']:+.4f} {c['bench_ci']} got {c['got']:+.4f} {c['got_ci']} "
              f"inside bench CI: {gain_verdict(c)}")
    print(f"  max rule (primary): {max_rule}")
    for kind in KINDS:
        print(f"  {kind} lambda sweep: " + ", ".join(f"{k}: {v:.6f}" for k, v in sweeps[kind].items()))


if __name__ == "__main__":
    main()
