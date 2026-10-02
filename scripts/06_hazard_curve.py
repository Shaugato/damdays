"""Step 6: the runway curve H (discrete-time hazard model), fitted and scored on VAL only.

Run from the repo folder (after scripts/02_build_features.py and 03_baselines_and_g2.py):
    .venv/Scripts/python.exe scripts/06_hazard_curve.py              # full run, about 35 minutes
    .venv/Scripts/python.exe scripts/06_hazard_curve.py --quick      # no bootstrap intervals
    .venv/Scripts/python.exe scripts/06_hazard_curve.py --skip-twin  # skip the all-waterbody twin (saves ~20 min)
    .venv/Scripts/python.exe scripts/06_hazard_curve.py --reuse      # rescore saved curves, no refits
    .venv/Scripts/python.exe scripts/06_hazard_curve.py --anchor NAME   # pair the 90-day slice with
        data_cache/preds/VAL/P1_<kind>/NAME.pkl (column p_NAME, or p) instead of the default anchors

What it does (damdays/models/hazard.py explains the model)
  1. Fits H for R30 and D0 on dam-like TRAIN issues, with censored
     person-period rows (each interval kept only if its answer was final
     before 2009-01-01), and predicts the 30/60/90/180-day curves for every
     at-risk VAL forecast. Applies the max rule (R30 curve >= D0 curve).
     Asserts 0 falling curves and 0 R30-below-D0 crossings after the rule.
  2. Twin diagnostic "H_all": the same recipe trained on ALL waterbodies.
     That is exactly the pre-event survival-hazard model "haz4", so it is
     the like-for-like reproduction check of this code.
  3. Horizon-specific baselines: B0_h (purged per horizon: D + max(h + 30, 90)
     days before 2009-01-01, hazard.baseline_wait_days) and B2_h, for the
     dam-like and persistent populations.
  4. Scores the curves with the shared scorecard (score_curve): the primary
     set (dam-like, Oct-Mar, at risk), all months, and the persistent subset.
  5. Scores the 90-day slice with score() and pairs it with the 90-day
     anchors: G2c (the dam-like direct tree), G2 (the PREREG benchmark) and
     the Tidemark anchor saved by step 4 (tidemark_L1: trees + frailty,
     column p = the 90-day headline, R30 after its own max rule), if present.
  6. Compares everything with the pre-event check values and writes
     artifacts/hazard_curve_val.md (for people) and .json (for code).

TEST is never touched: every fit uses rows answered before 2009-01-01 and
every scored table is checked to hold VAL issues only.
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
from damdays.data.splits import time_block  # noqa: E402
from damdays.evaluation import crossing_share, monotonicity_violations, score, score_curve  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import hazard, rows  # noqa: E402
from damdays.models.predictions import load_predictions, prediction_path, save_predictions  # noqa: E402

BLOCK = "VAL"
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step06_val"
RESULTS_MD = config.ARTIFACTS_DIR / "hazard_curve_val.md"
RESULTS_JSON = config.ARTIFACTS_DIR / "hazard_curve_val.json"
N_BOOT_MAIN, N_BOOT_SIDE = 500, 200     # bootstrap draws: primary set, other subsets
HORIZONS = hazard.HORIZONS
KINDS = hazard.CURVE_KINDS

# Curve subsets: (scorecard subset, population the baselines are fitted on)
CURVE_SUBSETS = [
    ("primary", "dam_like"),                          # dam-like, Oct-Mar, at risk: the headline set
    ("dam_like+at_risk", "dam_like"),                 # dam-like, all months
    ("persistent+octmar+at_risk", "persistent"),      # dams that rarely dry out (H is a dam-like model)
]
# The models fitted here: name -> population the hazard model is trained on.
CURVE_MODELS = {"H": "dam_like", "H_all": "all"}
# Extra 90-day anchors (prediction names in data_cache/preds/VAL/P1_<kind>/), used when the file exists.
DEFAULT_ANCHORS = ["tidemark_L1"]     # step 4: Tidemark rung L1 (trees + frailty), the current anchor

# ---------------------------------------------------------------------------
# Check values from the pre-event research (bench/results/survival-hazard and
# bench/results/hybrid). All VAL, development regions.
# ---------------------------------------------------------------------------
TOLERANCE = 0.006            # the PREREG fallback-ladder reproduction tolerance

# Person-period expansion: (issues, person-period rows, events). Must match exactly.
#   dam_like  hybrid logs/trees_val_a.log (R30) and trees_val_b.log (D0), model "H|g2c+phy|dl"
#   all       survival-hazard work/val_R30_gbm.log and val_D0_haz4.log, model "haz4"
FIT_COUNT_CHECKS = {
    ("H", "R30"): (283_836, 1_000_128, 94_623),
    ("H", "D0"): (365_109, 1_362_265, 60_783),
    ("H_all", "R30"): (674_873, 2_263_705, 309_683),
    ("H_all", "D0"): (896_778, 3_222_863, 251_639),
}
# Primary-set rows and base rate at each horizon (survival-hazard multi_VAL.csv).
PRIMARY_ROWS = {"R30": 66_453, "D0": 86_651}
BASE_RATE_CHECKS = {"R30": (0.0811, 0.1710, 0.2387, 0.3248), "D0": (0.0369, 0.0792, 0.1142, 0.1653)}

# Like for like: "haz4" = hazard GBM, G2c features, ALL waterbodies (our H_all), multi_VAL.csv.
# Its B0_h / B2_h prior were fitted on UNPURGED TRAIN rows, so it is compared with
# H_all scored against baselines built the same way (purge=False).
HAZ4 = {
    "R30": dict(bss_B0=(0.0944, 0.1460, 0.1723, 0.1858), bss_B2=(0.0720, 0.0964, 0.1006, 0.0904),
                auc=(0.7933, 0.7811, 0.7812, 0.7896), cal_slope=(1.097, 1.055, 1.036, 1.061),
                citl=(-0.095, -0.111, -0.217, -0.415), fan=0.1496),
    "D0": dict(bss_B0=(0.0869, 0.1414, 0.1746, 0.2191), bss_B2=(0.0626, 0.0847, 0.0913, 0.0772),
               auc=(0.8430, 0.8349, 0.8310, 0.8355), cal_slope=(1.129, 1.089, 1.059, 1.103),
               citl=(-0.126, -0.159, -0.247, -0.399), fan=0.1555),
}
# Reference, NOT like for like: the frozen Tidemark curve "H|g2c+phy|dl" = dam-like (as our H) but WITH the
# two physics columns, which our H does not have yet (hybrid tables/val_stageC_horizons.csv, "H_alone";
# baselines as for haz4). PHY added +0.0024 (R30) and +0.0093 (D0) to the 90-day dam-like tree (val_stageA.csv).
H_ALONE = {"R30": dict(bss_B0=(0.0987, 0.1509, 0.1759, 0.1988), fan=0.1561),
           "D0": dict(bss_B0=(0.0965, 0.1540, 0.1851, 0.2353), fan=0.1677)}
PHY_GAIN_90D = {"R30": 0.0024, "D0": 0.0093}
# 90-day slice of haz4 against the direct all-waterbody G2c tree (= our G2), paired, dam CI
# (survival-hazard compare_VAL.csv and RESULT.md).
HAZ4_VS_DIRECT_90D = {"R30": (0.0019, (-0.0010, 0.0047)), "D0": (-0.001, (-0.005, 0.003))}
# R30 curve below the D0 curve before the max rule (hybrid val_stageC_monotone.csv): 0.122% of primary rows.
# NOT like for like: measured on the pre-event "anchored fan" (FULL v1), whose curves were pulled through
# the fused 90-day anchors, not on the raw hazard curves H. Only "0 after the max rule" carries over.
CROSSINGS_BEFORE = 0.00122

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def data_end():
    """The date of the last satellite look in the archive (saved by the feature build)."""
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as handle:
        return pd.Timestamp(pickle.load(handle)["data_end"])


def join_column(frame, other, column, name):
    """Copy other[column] into frame[name], matched on uid + issue_date; every frame row must be found."""
    keys = ["uid", "issue_date"]
    right = other[keys + [column]].rename(columns={column: name}).copy()
    right["uid"] = right["uid"].astype(str)
    right["issue_date"] = pd.to_datetime(right["issue_date"]).astype("datetime64[ns]")
    left = frame[keys].copy()
    left["issue_date"] = pd.to_datetime(left["issue_date"]).astype("datetime64[ns]")
    merged = left.merge(right, on=keys, how="left", validate="one_to_one")
    if merged[name].isna().any():
        raise AssertionError(f"{int(merged[name].isna().sum())} rows have no {name}.")
    frame[name] = merged[name].to_numpy()
    return frame


def assert_val_only(frame):
    """Refuse to score anything outside VAL (this script never looks at TEST)."""
    blocks = set(time_block(frame["issue_date"]))
    if blocks != {BLOCK}:
        raise AssertionError(f"Expected VAL issues only, found blocks {sorted(blocks)}")


def keys_frame(table, kind, labels):
    """Keys, flags and the labels at 30/60/90/180 days for every at-risk VAL issue of `kind`."""
    picked = rows.p1_block_rows(table, kind, BLOCK)
    chosen = table.loc[picked]
    frame = pd.DataFrame({
        "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
        "region": chosen["region"].astype(str).to_numpy(),
        "dam_like": chosen["dam_like"].to_numpy(dtype=bool), "persistent": chosen["persistent"].to_numpy(dtype=bool),
        "at_risk": True,     # every row here is at risk for this kind (p1_block_rows)
    })
    for h in HORIZONS:
        frame[f"y_{h}"] = labels[kind].loc[picked, f"y_{h}"].to_numpy()
    return frame


# ---------------------------------------------------------------------------
# 1-2. Fit and predict (or reload) the curves
# ---------------------------------------------------------------------------
def curves_for(table, name, population, frames, reuse):
    """Fit H on `population` (or reload); add its curves to frames[kind]. Returns the fit info."""
    info_path = prediction_path(BLOCK, "R30_curve", f"{name}_fit_info").with_suffix(".json")
    if reuse and info_path.exists() and all(prediction_path(BLOCK, f"{k}_curve", name).exists() for k in KINDS):
        for kind in KINDS:
            saved = load_predictions(BLOCK, f"{kind}_curve", name)
            for column in [c for c in saved.columns if c.startswith(("p_", "raw_p_", "d0_p_"))]:
                join_column(frames[kind], saved, column, f"{name}:{column}")
        log(f"{name}: reloaded saved curves")
        return json.loads(info_path.read_text())

    curves, infos = hazard.fit_and_predict_curves(table, BLOCK, population=population)
    for kind in KINDS:
        log(f"{name} {kind}: {infos[kind]['issues']:,} issues -> {infos[kind]['person_period_rows']:,} "
            f"person-period rows ({infos[kind]['person_period_events']:,} events), {infos[kind]['seconds']} s")
        columns = [c for c in curves[kind].columns if c.startswith(("p_", "raw_p_", "d0_p_"))]
        for column in columns:
            join_column(frames[kind], curves[kind], column, f"{name}:{column}")
        to_save = frames[kind][["uid", "issue_date", "region", "dam_like", "persistent", "at_risk"]
                               + [f"y_{h}" for h in HORIZONS]].copy()
        for column in columns:
            to_save[column] = frames[kind][f"{name}:{column}"].to_numpy()
        save_predictions(to_save, BLOCK, f"{kind}_curve", name)
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(json.dumps(clean_for_json(infos), indent=1))
    return infos


def model_curve(frame, name, prefix="p_"):
    """A model's curve on these rows as an array [n, 4]."""
    return frame[[f"{name}:{prefix}{h}" for h in HORIZONS]].to_numpy(dtype=float)


def shape_checks(frames, name, primary_mask):
    """Monotonicity of every curve, and R30-below-D0 crossings before and after the max rule."""
    out = {}
    for kind in KINDS:
        result = monotonicity_violations(model_curve(frames[kind], name))
        if result["rows_falling"] != 0:
            raise AssertionError(f"{name} {kind}: {result['rows_falling']} curves fall as the horizon grows.")
        out[f"{kind}_falling_rows"] = result["rows_falling"]
    r30 = frames["R30"]
    raw = monotonicity_violations(model_curve(r30, name, "raw_p_"))
    if raw["rows_falling"] != 0:
        raise AssertionError(f"{name} R30 before the max rule: {raw['rows_falling']} falling curves.")
    out["R30_raw_falling_rows"] = raw["rows_falling"]
    after = crossing_share(model_curve(r30, name), model_curve(r30, name, "d0_p_"))
    if after != 0:
        raise AssertionError(f"{name}: the R30 curve is below the D0 curve on {after:.4%} of rows after the max rule.")
    for label, mask in (("all_rows", np.ones(len(r30), dtype=bool)), ("primary_rows", primary_mask)):
        out[f"crossings_before_max_rule_{label}"] = crossing_share(model_curve(r30, name, "raw_p_")[mask],
                                                                   model_curve(r30, name, "d0_p_")[mask])
    out["crossings_after_max_rule"] = after
    out["rows_changed_by_max_rule"] = int((model_curve(r30, name) != model_curve(r30, name, "raw_p_")).any(axis=1).sum())
    return out


# ---------------------------------------------------------------------------
# 3. Horizon-specific baselines
# ---------------------------------------------------------------------------
def all_baselines(table, labels):
    """{(kind, population, purged): baseline table} for the populations scored here."""
    out = {}
    for kind in KINDS:
        for population in ("dam_like", "persistent"):
            out[(kind, population, True)] = hazard.curve_baselines(table, kind, BLOCK, labels[kind], population)
            save_predictions(out[(kind, population, True)], BLOCK, f"{kind}_curve", f"baselines_{population}")
        # The pre-event recipe (unpurged), only to compare like for like with the pre-event numbers.
        out[(kind, "dam_like", False)] = hazard.curve_baselines(table, kind, BLOCK, labels[kind], "dam_like",
                                                                purge=False)
        log(f"{kind}: horizon baselines B0_h / B2_h built")
    return out


def baseline_consistency(base):
    """B0_90 must equal the official 90-day B0 of step 3 exactly; B2_90 is compared for information."""
    out = {}
    for kind in KINDS:
        official = load_predictions(BLOCK, f"P1_{kind}", "baselines_dam_like")
        mine = base[(kind, "dam_like", True)]
        check = join_column(mine[["uid", "issue_date"]].copy(), official, "p_B0", "official_B0")
        check = join_column(check, official, "p_B2", "official_B2")
        b0_diff = float(np.max(np.abs(mine["p_B0_90"].to_numpy() - check["official_B0"].to_numpy())))
        if b0_diff > 1e-12:
            raise AssertionError(f"{kind}: B0_90 differs from the official B0 by up to {b0_diff}.")
        b2_gap = np.abs(mine["p_B2_90"].to_numpy() - check["official_B2"].to_numpy())
        out[kind] = dict(b0_90_max_abs_diff=b0_diff, b2_90_share_identical=float(np.mean(b2_gap < 1e-12)),
                         b2_90_max_abs_diff=float(b2_gap.max()), b2_90_mean_abs_diff=float(b2_gap.mean()))
    return out


# ---------------------------------------------------------------------------
# 4. Score the curves
# ---------------------------------------------------------------------------
def curve_table(frame, base, name, prefix="p_"):
    """A score_curve input: keys, flags, labels, the model's curve as p_<h>, and the baselines."""
    table = frame[["uid", "issue_date", "region", "dam_like", "persistent", "at_risk"]
                  + [f"y_{h}" for h in HORIZONS]].copy()
    for h in HORIZONS:
        table[f"p_{h}"] = frame[f"{name}:{prefix}{h}"].to_numpy()
    for column in [f"p_B{b}_{h}" for b in (0, 2) for h in HORIZONS]:
        join_column(table, base, column, column)
    assert_val_only(table)
    return table


def score_curves(frames, base, n_boot_main, n_boot_side, twin):
    """Every curve score; returns {(model, kind, subset, baselines): score_curve result}."""
    results = {}
    note = "step 6 (scripts/06_hazard_curve.py)"
    for kind in KINDS:
        task = f"{kind}_curve"
        # The official curve H (R30 after the max rule) on every subset.
        for subset, population in CURVE_SUBSETS:
            n_boot = n_boot_main if subset == "primary" else n_boot_side
            table = curve_table(frames[kind], base[(kind, population, True)], "H")
            results[("H", kind, subset, "official")] = score_curve(
                table, task, subset, model="H", n_boot=n_boot, out_dir=SCORE_DIR, note=note)
        # Diagnostics on the primary set, point values only. "pre_event" = scored against
        # baselines fitted the pre-event way (unpurged); never saved, used only for the checks.
        # (label, which fitted model, which curve columns: p_ = final, raw_p_ = R30 before the max rule)
        diagnostics = [("H", "H", "p_")]
        if kind == "R30":
            diagnostics.append(("H_raw", "H", "raw_p_"))
        if twin:
            diagnostics.append(("H_all", "H_all", "p_"))
        for label, fitted, prefix in diagnostics:
            for base_name, purged in (("official", True), ("pre_event", False)):
                if label == "H" and base_name == "official":
                    continue                                  # already scored above, with intervals
                table = curve_table(frames[kind], base[(kind, "dam_like", purged)], fitted, prefix)
                results[(label, kind, "primary", base_name)] = score_curve(
                    table, task, "primary", model=label, n_boot=0, out_dir=SCORE_DIR, note=note,
                    write=base_name == "official")
        log(f"{task}: scored")
    return results


# ---------------------------------------------------------------------------
# 5. The 90-day slice against the 90-day anchors
# ---------------------------------------------------------------------------
def slice_90(frame, kind, name, anchors, prefix="p_"):
    """A score() input for the 90-day slice of a curve, with official B0/B2 and the anchors as p_<anchor>."""
    task = f"P1_{kind}"
    table = frame[["uid", "issue_date", "region", "dam_like", "persistent", "at_risk"]].copy()
    table["y"] = frame["y_90"].to_numpy()
    table["p"] = frame[f"{name}:{prefix}90"].to_numpy()
    official = load_predictions(BLOCK, task, "baselines_dam_like")
    for column in ("p_B0", "p_B2"):
        join_column(table, official, column, column)
    models = load_predictions(BLOCK, task, "models")
    for column in ("p_G2", "p_G2c"):
        join_column(table, models, column, column)
    for anchor in anchors:
        other = load_predictions(BLOCK, task, anchor)
        join_column(table, other, f"p_{anchor}" if f"p_{anchor}" in other.columns else "p", f"p_{anchor}")
    assert_val_only(table)
    return table


def score_slices(frames, anchors, n_boot_main, n_boot_side, twin):
    """The 90-day slice of H (and H_all) paired with the 90-day anchors; returns {(model, kind): result}."""
    results = {}
    note = "step 6: 90-day slice of the hazard curve"
    for kind in KINDS:
        available = [a for a in anchors if prediction_path(BLOCK, f"P1_{kind}", a).exists()]
        expected = frames[kind].loc[frames[kind]["y_90"].notna() & frames[kind]["dam_like"]
                                    & rows_octmar(frames[kind]), ["uid", "issue_date"]]
        runs = [("H_90d", "H", "p_", ["G2c", "G2"] + available, n_boot_main)]
        if kind == "R30":
            runs.append(("H_raw_90d", "H", "raw_p_", ["G2c", "G2"], 0))
        if twin:
            runs.append(("H_all_90d", "H_all", "p_", ["G2", "G2c"], n_boot_side))
        for label, name, prefix, refs, n_boot in runs:
            table = slice_90(frames[kind], kind, name, available, prefix)
            results[(label, kind)] = score(table, f"P1_{kind}", "primary", model=label, refs=refs,
                                           expected_keys=expected, n_boot=n_boot, out_dir=SCORE_DIR, note=note)
        log(f"P1_{kind}: 90-day slices scored against {', '.join(['G2c', 'G2'] + available)}")
    return results


def rows_octmar(frame):
    """True for issues in October to March."""
    return np.isin(pd.DatetimeIndex(frame["issue_date"]).month, config.SEASON_MONTHS)


# ---------------------------------------------------------------------------
# 6. Checks and report
# ---------------------------------------------------------------------------
def fmt(value, digits=3, sign=True):
    """A number for a table cell ("-" when missing)."""
    if value is None or not np.isfinite(value):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def fmt_ci(point, ci, digits=3, sign=True):
    """A point value with its interval, when there is one."""
    text = fmt(point, digits, sign)
    if ci:
        text += f" [{fmt(ci[0], digits, sign)}, {fmt(ci[1], digits, sign)}]"
    return text


def horizon_point(result, h, metric):
    """One metric at one horizon from a score_curve result."""
    entry = next(x for x in result["horizons"] if x["horizon"] == h)
    return entry["point"].get(metric)


def fan_score(result):
    """Mean BSS vs B0_h over the four horizons (the pre-event selection score)."""
    return float(np.mean([horizon_point(result, h, "bss_B0") for h in HORIZONS]))


def exact_checks(infos, curve_results):
    """Checks that must match exactly: person-period counts, scored rows and base rates."""
    out = []
    for (name, kind), (issues, pp_rows, events) in FIT_COUNT_CHECKS.items():
        if name not in infos:
            continue
        info = infos[name][kind]
        got = (info["issues"], info["person_period_rows"], info["person_period_events"])
        out.append(dict(check=f"{name} {kind}: issues, person-period rows, events",
                        expected=f"{issues:,} / {pp_rows:,} / {events:,}", got=f"{got[0]:,} / {got[1]:,} / {got[2]:,}",
                        match=got == (issues, pp_rows, events)))
    for kind in KINDS:
        result = curve_results[("H", kind, "primary", "official")]
        n = [next(x for x in result["horizons"] if x["horizon"] == h)["rows"] for h in HORIZONS]
        out.append(dict(check=f"{kind} primary rows at 30/60/90/180 d", expected=f"{PRIMARY_ROWS[kind]:,} at each",
                        got=" / ".join(f"{v:,}" for v in n), match=all(v == PRIMARY_ROWS[kind] for v in n)))
        rates = [horizon_point(result, h, "base_rate") for h in HORIZONS]
        out.append(dict(check=f"{kind} primary base rate at 30/60/90/180 d",
                        expected=" / ".join(f"{v:.4f}" for v in BASE_RATE_CHECKS[kind]),
                        got=" / ".join(f"{v:.4f}" for v in rates),
                        match=all(abs(a - b) < 5e-5 for a, b in zip(rates, BASE_RATE_CHECKS[kind]))))
    return out


def score_checks(curve_results, twin):
    """Expected vs got at every horizon. Like for like (H_all vs haz4) has a verdict; H vs H_alone is a reference."""
    out = []
    for kind in KINDS:
        for j, h in enumerate(HORIZONS):
            if twin:
                like = curve_results[("H_all", kind, "primary", "pre_event")]
                official = curve_results[("H_all", kind, "primary", "official")]
                for metric in ("bss_B0", "bss_B2", "auc", "cal_slope", "citl"):
                    expected = HAZ4[kind][metric][j]
                    got = horizon_point(like, h, metric)
                    tolerance = TOLERANCE if metric in ("bss_B0", "bss_B2", "auc") else 0.05
                    out.append(dict(kind=kind, horizon=h, model="H_all (like for like: pre-event haz4)",
                                    metric=metric, expected=expected, got=got, difference=got - expected,
                                    tolerance=tolerance, verdict="within" if abs(got - expected) <= tolerance
                                    else "OUTSIDE", official_purged=horizon_point(official, h, metric)))
            reference = curve_results[("H", kind, "primary", "pre_event")]
            got = horizon_point(reference, h, "bss_B0")
            out.append(dict(kind=kind, horizon=h, model="H (reference: pre-event H with PHY)", metric="bss_B0",
                            expected=H_ALONE[kind]["bss_B0"][j], got=got, difference=got - H_ALONE[kind]["bss_B0"][j],
                            tolerance=None, verdict="reference (PHY not in yet)",
                            official_purged=horizon_point(curve_results[("H", kind, "primary", "official")], h,
                                                          "bss_B0")))
    return out


def fan_rows(curve_results, twin):
    """Fan scores (mean BSS vs B0_h over the four horizons), against the pre-event values."""
    out = []
    for kind in KINDS:
        out.append(dict(kind=kind, model="H", baselines="official (purged)",
                        got=fan_score(curve_results[("H", kind, "primary", "official")]), expected=None))
        out.append(dict(kind=kind, model="H", baselines="pre-event recipe",
                        got=fan_score(curve_results[("H", kind, "primary", "pre_event")]),
                        expected=H_ALONE[kind]["fan"], note="pre-event H with PHY (reference)"))
        if twin:
            out.append(dict(kind=kind, model="H_all", baselines="pre-event recipe",
                            got=fan_score(curve_results[("H_all", kind, "primary", "pre_event")]),
                            expected=HAZ4[kind]["fan"], note="pre-event haz4 (like for like)"))
    return out


def checks_table(checks):
    """Markdown rows for the per-horizon score checks."""
    lines = ["| kind | h (days) | model | metric | expected (pre-event) | got | difference | tolerance | verdict | "
             "got, official purged baselines |", "|---|---|---|---|---|---|---|---|---|---|"]
    for c in checks:
        digits = 2 if c["metric"] in ("cal_slope", "citl") else 4
        tol = f"+-{c['tolerance']:.3f}" if c["tolerance"] is not None else "-"
        lines.append(f"| {c['kind']} | {c['horizon']} | {c['model']} | {c['metric']} | {fmt(c['expected'], digits)} | "
                     f"{fmt(c['got'], digits)} | {fmt(c['difference'], 4)} | {tol} | {c['verdict']} | "
                     f"{fmt(c['official_purged'], digits)} |")
    return lines


def curve_table_md(curve_results, keys):
    """Markdown rows: one per (model, kind, subset) and horizon."""
    lines = ["| model | kind | subset | h (days) | rows | events | base rate | mean p | BSS vs B0_h [dam] | BSS vs B2_h | "
             "AUC | cal. slope | CITL |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in keys:
        result = curve_results[key]
        for entry in result["horizons"]:
            p, ci = entry["point"], entry["ci_dam"]
            lines.append("| " + " | ".join([
                key[0], key[1], key[2], str(entry["horizon"]), f"{entry['rows']:,}", f"{entry['events']:,}",
                fmt(p.get("base_rate"), 3, False), fmt(p.get("mean_p"), 3, False),
                fmt_ci(p.get("bss_B0"), ci.get("bss_B0")), fmt(p.get("bss_B2")),
                fmt_ci(p.get("auc"), ci.get("auc"), 3, False), fmt(p.get("cal_slope"), 2, False),
                fmt(p.get("citl"), 2)]) + " |")
    return lines


def slice_table(slice_results):
    """Markdown rows for the 90-day slices and their paired differences."""
    lines = ["| model | task | rows | events | BSS vs B0 [dam] | BSS vs B2 | AUC | cal. slope | CITL | "
             "paired vs anchors (BSS-vs-B0 units) [dam] ry [region-year] |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for (label, kind), r in slice_results.items():
        p = r["point"]
        paired = "; ".join(
            f"{ref}: {fmt_ci(p.get('d_bss_B0_vs_' + ref), r['ci_dam'].get('d_bss_B0_vs_' + ref), 4)}"
            + (f" ry [{fmt(r['ci_region_year']['d_bss_B0_vs_' + ref][0], 4)}, "
               f"{fmt(r['ci_region_year']['d_bss_B0_vs_' + ref][1], 4)}]"
               if r["ci_region_year"].get("d_bss_B0_vs_" + ref) else "")
            for ref in r["refs"])
        lines.append("| " + " | ".join([
            label, f"P1_{kind}", f"{r['rows']['scored']:,}", f"{r['rows']['events']:,}",
            fmt_ci(p["bss_B0"], r["ci_dam"].get("bss_B0")), fmt(p["bss_B2"]),
            fmt(p["auc"], 3, False), fmt(p["cal_slope"], 2, False), fmt(p["citl"], 2), paired]) + " |")
    return lines


def write_report(infos, shapes, consistency, curve_results, slice_results, exact, checks, fans, twin, n_boot_main):
    """artifacts/hazard_curve_val.md (for people) and artifacts/hazard_curve_val.json (for code)."""
    main_keys = [("H", k, s, "official") for k in KINDS for s, _ in CURVE_SUBSETS]
    diag_keys = [key for key in curve_results if key[3] == "official" and key[0] != "H"]
    lines = [
        "# VAL results: the runway curve H (build step 6)",
        "",
        f"Generated by `scripts/06_hazard_curve.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only** "
        "(forecasts issued 2009-01-01 to 2015-12-31, development regions). TEST was not scored.",
        "",
        "H is a discrete-time hazard LightGBM (`damdays/models/hazard.py`): intervals (0,30], (30,60], (60,90], "
        "(90,180] days; inputs the 29 G2c columns plus the interval's start and length; G2's settings; trained on "
        "dam-like TRAIN issues. Each interval is kept only if its answer was final before 2009-01-01 (interval end + "
        "30 days; censoring, not purging). Curve F(t) = 1 - prod(1 - h). R30 curve = max(R30 curve, D0 curve). "
        "The physics columns (PHY) are not in yet: this is H without PHY.",
        "",
        "Each horizon is judged against its own baselines: B0_h = month x region rate of an event within h days "
        "(dam-like fit rows, purged per horizon: issue + max(h + 30, 90) days before 2009-01-01), B2_h = the "
        "dam's own track record at h (k = 20; a past forecast counts max(h + 30, 90) days after it was issued). "
        "Brackets: dam-bootstrap 95% intervals "
        f"({n_boot_main} draws on the primary set).",
        "",
        "## Check values: expected (pre-event research) vs got (this build)",
        "",
        "### Must match exactly",
        "",
        "| check | expected | got | match |", "|---|---|---|---|",
        *[f"| {r['check']} | {r['expected']} | {r['got']} | {'yes' if r['match'] else 'NO'} |" for r in exact],
        f"| B0_90 equals the official 90-day B0 (step 3) | max difference 0 | "
        f"{', '.join(f'{k}: {consistency[k]['b0_90_max_abs_diff']:.1e}' for k in KINDS)} | yes |",
        "",
        "### Curve shape (expected 0 everywhere after the max rule)",
        "",
        "| model | R30 curves falling | D0 curves falling | R30 raw curves falling | R30 below D0 before max rule "
        "(all VAL rows / primary rows) | after | rows changed by the max rule |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in shapes.items():
        lines.append(f"| {name} | {s['R30_falling_rows']} | {s['D0_falling_rows']} | {s['R30_raw_falling_rows']} | "
                     f"{s['crossings_before_max_rule_all_rows']:.4%} / {s['crossings_before_max_rule_primary_rows']:.4%}"
                     f" | {s['crossings_after_max_rule']:.4%} | {s['rows_changed_by_max_rule']:,} |")
    lines += [f"| pre-event FULL v1 anchored fan (not like for like) | 0 | 0 | 0 | - / {CROSSINGS_BEFORE:.4%} | 0 | - |",
              "",
              "Two separately fitted hazard models can cross; the max rule removes every crossing. The pre-event "
              "0.122% was measured on a different curve (the anchored fan, pulled through the fused 90-day "
              "anchors), so only 'falling = 0' and 'after = 0' are checks here.", "",
              "### Scores at each horizon (primary set)", "",
              "Like for like: `H_all` (this code trained on all waterbodies) against the pre-event `haz4`, both "
              "scored against baselines fitted the pre-event way (unpurged TRAIN rows). Reference: `H` (dam-like) "
              "against the frozen pre-event `H|g2c+phy|dl`, which also had the two physics columns.", "",
              *checks_table(checks), "",
              "### Fan score (mean BSS vs B0_h over 30/60/90/180 days, primary set)", "",
              "| kind | model | baselines | expected (pre-event) | got | note |", "|---|---|---|---|---|---|",
              *[f"| {f['kind']} | {f['model']} | {f['baselines']} | {fmt(f['expected'], 4)} | {fmt(f['got'], 4)} | "
                f"{f.get('note', '')} |" for f in fans], "",
              "## The runway curve H on VAL (official: purged horizon baselines)", "",
              *curve_table_md(curve_results, main_keys), "",
              "### Diagnostics (primary set, point values)", "",
              *curve_table_md(curve_results, diag_keys), "",
              "## The 90-day slice against the 90-day anchors (shared scorecard, official P1 B0 and B2)", "",
              "`H_90d` is the curve's 90-day value (R30 after the max rule). Paired differences are in BSS-vs-B0 "
              "units on the same rows: positive means the curve's 90-day slice beats the anchor. G2c = the direct "
              "90-day tree on dam-like rows (same features, same population: the closest twin); G2 = the PREREG "
              "benchmark (all waterbodies). tidemark_L1 = the current Tidemark anchor from step 4 (trees + frailty; "
              "the nets are not in yet).",
              "", *slice_table(slice_results), "",
              f"Pre-event: haz4's 90-day slice vs the direct all-waterbody tree (our G2): R30 "
              f"{HAZ4_VS_DIRECT_90D['R30'][0]:+.4f} [{HAZ4_VS_DIRECT_90D['R30'][1][0]:+.4f}, "
              f"{HAZ4_VS_DIRECT_90D['R30'][1][1]:+.4f}], D0 {HAZ4_VS_DIRECT_90D['D0'][0]:+.4f} "
              f"[{HAZ4_VS_DIRECT_90D['D0'][1][0]:+.4f}, {HAZ4_VS_DIRECT_90D['D0'][1][1]:+.4f}].", "",
              "## B2_h at 90 days vs the official B2", "",
              "| kind | identical rows | max difference | mean difference |", "|---|---|---|---|",
              *[f"| {k} | {consistency[k]['b2_90_share_identical']:.1%} | {consistency[k]['b2_90_max_abs_diff']:.4f} | "
                f"{consistency[k]['b2_90_mean_abs_diff']:.5f} |" for k in KINDS], "",
              "B2_h counts the dam's earlier P1 issues (from 1988), like the pre-event B2_h; the official 90-day B2 "
              "also counts the dam's 1986-87 warm-up looks. The 90-day slice above is scored against the official B2.",
              "", "## Fits", "",
              "| model | kind | issues | used | person-period rows | events | rows per interval | issues kept with "
              "post-cutoff looks in label_ok | top inputs by gain | seconds |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for name, by_kind in infos.items():
        for kind, info in by_kind.items():
            top = ", ".join(f"{k} {v:.2f}" for k, v in list(info["top_features_by_gain"].items())[:5])
            per = " / ".join(f"{v:,}" for v in info["rows_per_interval"].values())
            lines.append(f"| {name} | {kind} | {info['issues']:,} | {info['issues_used']:,} | "
                         f"{info['person_period_rows']:,} | {info['person_period_events']:,} | {per} | "
                         f"{info['issues_selected_with_post_cutoff_looks']:,} | {top} | {info['seconds']} |")
    lines += ["", "## Notes", "", *NOTES, ""]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")

    def compact(result):
        return {str(h["horizon"]): dict(point=h["point"], ci_dam=h["ci_dam"], ci_region_year=h["ci_region_year"],
                                        rows=h["rows"], events=h["events"]) for h in result["horizons"]}
    summary = dict(
        generated=time.strftime("%Y-%m-%d %H:%M:%S"), block=BLOCK, twin=twin, n_boot_main=n_boot_main,
        exact_checks=exact, score_checks=checks, fan_scores=fans, shape_checks=shapes,
        baseline_consistency=consistency, fits=infos,
        curves={"|".join(k): compact(v) for k, v in curve_results.items()},
        slices_90d={"|".join(k): dict(point=v["point"], ci_dam=v["ci_dam"], ci_region_year=v["ci_region_year"],
                                      rows=v["rows"], refs=v["refs"]) for k, v in slice_results.items()})
    RESULTS_JSON.write_text(json.dumps(clean_for_json(summary), indent=1), encoding="utf-8")


NOTES = [
    "- **Censoring, not purging.** The 90-day trees learn only from TRAIN issues whose whole answer was final "
    "before 2009-01-01 (issue + 120 days). H keeps each 30/30/30/90-day interval on its own once that interval's "
    "answer was final (issue + interval end + 30 days < 2009-01-01), so late-2008 issues still teach it about "
    "their first weeks.",
    "- **Disclosed (as before the event).** The training issues need label_ok (3 looks in the issue's 90 days). "
    "For an issue from October-November 2008 that is kept only for its early intervals, that count can see up to "
    "30 days of looks after the cutoff. It decides only whether the issue is used, never a label or an input. "
    "The 'Fits' table counts these issues.",
    "- **Baselines are purged per horizon.** The pre-event B0_h and B2_h prior were fitted on all TRAIN rows. "
    "Here a row counts for horizon h only if issue + max(h + 30, 90) days is before 2009-01-01: the h-day "
    "answer is final h + 30 days after the issue, and whether it counts at all (label_ok: 3 looks in the "
    "90-day window) is known only after 90 days. B2_h waits the same max(h + 30, 90) days before it counts a "
    "past forecast (the pre-event B2_h waited h + 30). Only h = 30 changes (independent review; measured "
    "effect: BSS vs B0_30 +0.0001, BSS vs B2_30 -0.0002 R30 / -0.0004 D0). Rows scored against the "
    "pre-event recipe are labelled 'pre-event' and used only for the like-for-like checks.",
    "- **PHY pending.** The frozen Tidemark curve has the two water-balance columns; this H does not yet "
    "(`hazard.fit_and_predict_curves(..., extra_features=PHY)` adds them). Its reference numbers are therefore "
    "expected to sit a little below the pre-event H, by about the physics gain (90-day tree: +0.002 R30, "
    "+0.009 D0).",
    "- **Predictions** are in `data_cache/preds/VAL/<kind>_curve/`: `H.pkl` (and `H_all.pkl`) with p_30 ... p_180 "
    "(R30 after the max rule), raw_p_* (R30 before it) and d0_p_* (the D0 curve on the same rows); "
    "`baselines_<population>.pkl` with p_B0_h and p_B2_h. All float64.",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    """Fit, predict and score the runway curve on VAL, then write the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no bootstrap intervals")
    parser.add_argument("--skip-twin", action="store_true", help="skip the all-waterbody twin H_all")
    parser.add_argument("--reuse", action="store_true", help="rescore saved curves instead of refitting")
    parser.add_argument("--anchor", action="append", default=None,
                        help=f"90-day anchor prediction name (default: {DEFAULT_ANCHORS}, when present)")
    args = parser.parse_args()
    n_boot_main, n_boot_side = (0, 0) if args.quick else (N_BOOT_MAIN, N_BOOT_SIDE)
    twin = not args.skip_twin

    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    for prefix in ("scorecard", "curves"):          # this run's markdown tables start empty
        (SCORE_DIR / f"{prefix}_dev_{BLOCK}.md").write_text("")

    log("loading the P1 table (keys, dam history, neighbours)")
    table = store.load_p1(groups=("keys", "dam", "nbr"))
    end = data_end()
    labels = {kind: hazard.horizon_labels(table, kind, end) for kind in KINDS}
    frames = {kind: keys_frame(table, kind, labels) for kind in KINDS}

    infos, shapes = {}, {}
    for name, population in CURVE_MODELS.items():
        if name == "H_all" and not twin:
            continue
        infos[name] = curves_for(table, name, population, frames, args.reuse)
        primary = frames["R30"]["dam_like"].to_numpy() & rows_octmar(frames["R30"])
        shapes[name] = shape_checks(frames, name, primary)
        log(f"{name}: 0 falling curves; R30 below D0 before the max rule on "
            f"{shapes[name]['crossings_before_max_rule_all_rows']:.4%} of rows, after: 0")

    base = all_baselines(table, labels)
    consistency = baseline_consistency(base)
    del table

    curve_results = score_curves(frames, base, n_boot_main, n_boot_side, twin)
    slice_results = score_slices(frames, args.anchor or DEFAULT_ANCHORS, n_boot_main, n_boot_side, twin)

    exact = exact_checks(infos, curve_results)
    checks = score_checks(curve_results, twin)
    fans = fan_rows(curve_results, twin)
    write_report(infos, shapes, consistency, curve_results, slice_results, exact, checks, fans, twin, n_boot_main)
    log(f"wrote {RESULTS_MD.name} and {RESULTS_JSON.name}")
    for r in exact:
        print(f"  {r['check']:<58s} expected {r['expected']:<32s} got {r['got']:<32s} {'ok' if r['match'] else 'NO'}")
    for c in checks:
        print(f"  {c['kind']:<3s} h={c['horizon']:<3d} {c['model'][:12]:<12s} {c['metric']:<9s} "
              f"expected {c['expected']:+.4f} got {c['got']:+.4f} diff {c['difference']:+.4f} {c['verdict']}")
    for f in fans:
        print(f"  fan {f['kind']:<3s} {f['model']:<6s} {f['baselines']:<18s} expected {fmt(f['expected'], 4)} "
              f"got {f['got']:+.4f}")
    for (label, kind), r in slice_results.items():
        paired = ", ".join(f"vs {ref} {r['point']['d_bss_B0_vs_' + ref]:+.4f}" for ref in r["refs"])
        print(f"  90-day slice {label:<10s} {kind:<3s} BSS vs B0 {r['point']['bss_B0']:+.4f}  {paired}")


if __name__ == "__main__":
    main()
