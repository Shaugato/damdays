"""Step 10: the physics features (rung L3's two water-balance columns) on VAL.

Run from the repo folder (after scripts/02, 03, 06 and 08, whose baselines and forecasts it uses as references):
    .venv/Scripts/python.exe scripts/10_physics_val.py            # full run, about 30 minutes (+ about 20 for L3)
    .venv/Scripts/python.exe scripts/10_physics_val.py --quick    # no bootstrap intervals
    .venv/Scripts/python.exe scripts/10_physics_val.py --reuse    # reuse the saved physics table and forecasts

What it does
  1. Builds the two physics columns for every P1 issue (damdays.models.physics.build_physics: a pooled
     bucket water balance fitted at every yearly checkpoint, a Kalman filter on rel^1.5 and 20 analogue
     rain years) and saves them in P1 order to data_cache/features/physics_p1.pkl, where
     tidemark.load_inputs picks them up. Checks against the pre-event research: the fit pairs per
     checkpoint must match exactly; the fitted balance and the physics-alone AUC are compared.
  2. Fits "L1+PHY" through tidemark.fit_tidemark / predict_tidemark: rung L1 with the 2 columns in the
     tree T and the runway curve H (rung L3 without the nets). Like for like, on the same VAL rows:
       T+PHY  vs T (= G2)    the physics columns inside the tree alone
       L1+PHY vs L1          ... with the per-dam frailty and the R30 max rule
       H+PHY  vs H           ... in the runway curve at 30 / 60 / 90 / 180 days
  3. Rung L3 (T+PHY, the nets S and M, frailty, max rule; H+PHY) through fit_tidemark / predict_tidemark,
     once the 12 VAL nets are trained (data_cache/nets/, scripts/09_nets_val.py). Compared with the
     pre-event full model (VAL primary BSS vs B0: R30 +0.182, D0 +0.195, D0g +0.195; tolerance +-0.006)
     and paired with L2 (the physics gain inside the full model).
  4. Writes artifacts/val_physics.md (for people) and artifacts/val_physics.json (for code).

TEST is never touched: every model learns from answers final before 2009-01-01 (the band's inner
backtest: before 2002-01-01), and every scored table is checked to hold VAL forecasts only.
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
from damdays.evaluation import score, score_curve  # noqa: E402
from damdays.evaluation.bootstrap import cluster_bootstrap  # noqa: E402
from damdays.evaluation.metrics import auc, brier_skill  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.evaluation.rules import is_octmar  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import fusion, hazard, nets, physics, rows, tidemark  # noqa: E402
from damdays.models import uncertainty as unc  # noqa: E402
from damdays.models.predictions import load_predictions, prediction_path  # noqa: E402

BLOCK = "VAL"
KINDS = rows.P1_KINDS
PRED_TASK = "tidemark"                     # forecasts: data_cache/preds/VAL/tidemark/<name>_p1.pkl
SCORE_DIR = config.ARTIFACTS_DIR / "scorecard" / "step10_val"
RESULTS_MD = config.ARTIFACTS_DIR / "val_physics.md"
RESULTS_JSON = config.ARTIFACTS_DIR / "val_physics.json"
PARAMS_FILE = config.CACHE_DIR / "features" / "physics_params.pkl"
N_BOOT_MAIN, N_BOOT_SIDE = 500, 200        # bootstrap draws: primary sets, other subsets
NOTE = "step 10 (scripts/10_physics_val.py)"

# Rung L3 without the nets: what this step can always fit. Not a PREREG rung, a like-for-like diagnostic.
L1_PHY = tidemark.Rung("L1+PHY", "L1 with the 2 water-balance columns in T and H (L3 without the nets S and M)",
                       ("T",), extra_features=tidemark.PHY_COLUMNS)
NET_CUTOFFS = [config.VAL_START] + [first for first, _ in unc.BAND_INNER_BLOCKS["VAL"]]   # 2009-01-01, 2002-01-01

# P1 subsets: (scorecard subset, population the baselines were fitted on, Oct-Mar issues only?)
P1_SUBSETS = [
    ("primary", "dam_like", True),                       # the pre-registered headline set
    ("persistent+octmar+at_risk", "persistent", True),   # dams that rarely dry out (harder)
    ("dam_like+at_risk", "dam_like", False),             # dam-like, all months
]

# ---------------------------------------------------------------------------
# Check values from the pre-event research (VAL, development regions; bench/results/...)
# ---------------------------------------------------------------------------
# hybrid/work/phparams_both.csv (also logs/phys_both_prep.log): pooled fit pairs per checkpoint. The pair
# rule and the panel are the same, so these must match exactly.
PAIR_COUNT_CHECKS = {1993: 90_106, 1998: 223_970, 2002: 350_401, 2009: 614_330, 2016: 875_652}
# Same file, checkpoint 2009 (VAL): threshold 15 mm, c, e, x. Not exact: the evaporation shape changed (BoM
# station climatology here, a rough typed proxy there), which moves e most.
PARAM_CHECK_2009 = dict(threshold_mm=15.0, c=1.5998e-3, e=1.2799e-3, x=2.7740e-3)
# physics-water-balance/RESULT.md, PHYS (raw ensemble probability, per-dam parameters), VAL primary:
# AUC (a ranking; recalibration does not change it) and raw BSS vs B0 (R30 only reported).
PHYS_ALONE = {"R30": dict(auc=0.662, bss_raw=-0.146), "D0": dict(auc=0.704), "D0g": dict(auc=0.752)}
# Paired gain (BSS vs B0 units) from adding physics columns to a G2c tree, VAL primary [dam 95% CI].
# None is exactly like for like (all-waterbody tree + pooled 2-column physics); both bracket the expectation.
T_PHY_REFERENCES = [
    ("physics family HYBp vs BASE: all-waterbody tree + 2 columns from per-dam physics (RESULT.md)",
     {"R30": (0.004, 0.002, 0.007), "D0": (0.013, 0.009, 0.017)}),
    ("physics family HYB vs BASE: the same with 14 physics columns (RESULT.md)",
     {"R30": (0.005, 0.002, 0.008), "D0": (0.013, 0.009, 0.017), "D0g": (0.014, 0.010, 0.019)}),
    ("hybrid stage A, A2_+PHY vs A1: dam-like-trained tree + the 2 pooled columns (val_stageA.csv)",
     {"R30": (0.0024, 0.0005, 0.0041), "D0": (0.0093, 0.0064, 0.0123), "D0g": (0.0121, 0.0084, 0.0162)}),
]
# The closest of these to T+PHY vs T (same 2 pooled columns; its tree was trained on dam-like rows only).
CLOSEST_T_PHY_REFERENCE = T_PHY_REFERENCES[2][1]
# hybrid val_stageB.csv "-PHY": the frozen full model (nets, frailty) minus the same without the 2 columns.
FULL_MODEL_PHY_GAIN = {"R30": (0.0009, 0.0003, 0.0014), "D0": (0.0025, 0.0014, 0.0035), "D0g": (0.0031, 0.0020, 0.0043)}
# hybrid val_final_scorecard.csv: the frozen full model (L3), VAL primary BSS vs B0; FINAL_SPEC (E) freeze check
# (R30 +0.182, D0 +0.195, D0g +0.195), tolerance +-0.006 (PREREG fallback ladder).
L3_REFERENCE = {"R30": 0.1818, "D0": 0.1948, "D0g": 0.1947}
TOLERANCE = 0.006
# hybrid val_stageC_horizons.csv "H_alone" = the frozen curve H|g2c+phy|dl: BSS vs B0_h at 30/60/90/180 days.
H_PHY_REFERENCE = {"R30": (0.0987, 0.1509, 0.1759, 0.1988), "D0": (0.0965, 0.1540, 0.1851, 0.2353)}
# hybrid physics share of the tree's gain (physics family, HYB with 14 columns; RESULT.md): R30 13%, D0 13%, D0g 20%.
PHY_GAIN_SHARE_REFERENCE = {"R30": 0.13, "D0": 0.13, "D0g": 0.20}

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


# ===========================================================================
# 1. The physics columns
# ===========================================================================
def build_physics_columns(reuse):
    """Build (or reload) the physics table and the yearly balance parameters. Returns (params, summary)."""
    if reuse and physics.PHYSICS_FILE.exists() and PARAMS_FILE.exists():
        saved = pd.read_pickle(PARAMS_FILE)
        log("reloaded the saved physics columns and balance parameters")
        return saved["params"], saved["summary"]
    log("building the physics columns (about 4 minutes)")
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    with open(config.CACHE_DIR / "silo_rain.pkl", "rb") as handle:
        rain_by_cell = pickle.load(handle)
    out = physics.build_physics(panel, attrs, rain_by_cell, verbose=True)
    keys = store.load_p1(groups=("keys",))[["uid", "issue_date"]]
    path = physics.save_physics(out["p1_physics"], keys)
    pd.to_pickle({"params": out["physics_params"], "summary": out["filter_summary"]}, PARAMS_FILE)
    log(f"physics columns saved to {path.relative_to(config.REPO_DIR)} (P1 order checked)")
    return out["physics_params"], out["filter_summary"]


def parameter_checks(params):
    """Fit pairs per checkpoint (must equal the pre-event counts) and the 2009 balance vs the research's."""
    by_year = params.set_index("year")
    pairs = [dict(year=year, expected=expected, got=int(by_year.loc[year, "n_pairs"]),
                  match=int(by_year.loc[year, "n_pairs"]) == expected) for year, expected in PAIR_COUNT_CHECKS.items()]
    c2009 = by_year.loc[2009]
    fitted = [dict(parameter=name, expected=value, got=float(c2009[name]),
                   ratio=float(c2009[name]) / value) for name, value in PARAM_CHECK_2009.items()]
    return dict(pairs=pairs, checkpoint_2009=fitted)


def physics_alone(table):
    """Each physics column on its own as a forecast on VAL primary rows: AUC and raw BSS vs B0 (no recalibration)."""
    out = {}
    for kind in KINDS:
        column = "ph_p_R30" if kind == "R30" else "ph_p_D0"
        frame, _ = p1_frame(table, kind)
        base = require(f"P1_{kind}", "baselines_dam_like", "scripts/03_baselines_and_g2.py")
        attach(frame, base, ["p_B0", "p_B2"])
        on_primary = frame["dam_like"].to_numpy() & is_octmar(frame["issue_date"]) & frame["y"].notna().to_numpy()
        p = frame[column].to_numpy(dtype=float)
        has = on_primary & np.isfinite(p)
        y = frame.loc[has, "y"].to_numpy(dtype=float)
        out[kind] = dict(column=column, rows_primary=int(on_primary.sum()), rows_with_physics=int(has.sum()),
                         auc=float(auc(y, p[has])), bss_raw=float(brier_skill(y, p[has], frame.loc[has, "p_B0"])),
                         mean_p=float(p[has].mean()), base_rate=float(y.mean()),
                         expected=PHYS_ALONE[kind])
    return out


def physics_coverage(table):
    """Share of P1 issues with physics values, by block (blank before 1993 by design)."""
    has = table["ph_p_R30"].notna().to_numpy()
    blocks = time_block(table["issue_date"])
    before_1993 = pd.to_datetime(table["issue_date"]).to_numpy() < np.datetime64("1993-01-01")
    out = {"issued_before_1993": dict(rows=int(before_1993.sum()), with_physics=int((has & before_1993).sum()))}
    for block in ("TRAIN", "VAL", "TEST"):
        pick = (blocks == block) & ~before_1993
        out[f"{block} (from 1993)"] = dict(rows=int(pick.sum()), share_with_physics=float(has[pick].mean()))
    return out


# ===========================================================================
# 2-3. Fitting through Tidemark's one entry point
# ===========================================================================
def run_name(rung):
    """File-safe name of a rung: "L1+PHY" -> "L1PHY"."""
    return rung.name.replace("+", "")


def nets_ready():
    """True when the 12 nets of the VAL setting (S, M x 3 seeds x 2 cutoffs) are saved in data_cache/nets/."""
    return all(nets.checkpoint_path(model, cutoff, seed).exists()
               for model in ("S", "M") for cutoff in NET_CUTOFFS for seed in nets.SEEDS)


def physics_gain_share(model):
    """Share of the tree T's split gain that goes to the 2 physics columns, per kind."""
    out = {}
    for kind in KINDS:
        tree = model.members[kind]["T"][0]
        features = fusion.tree_features(kind, model.rung.extra_features)
        gain = pd.Series(tree.booster_.feature_importance("gain"), index=features)
        out[kind] = dict(share=float(gain[list(tidemark.PHY_COLUMNS)].sum() / gain.sum()),
                         rank=[int(gain.rank(ascending=False)[c]) for c in tidemark.PHY_COLUMNS])
    return out


def lean_forecasts(p1_out, rung):
    """The forecasts kept on disk and scored: float32 numbers, uid and region as categories.

    L1+PHY is a diagnostic, so only the columns this step scores are kept (row, keys, the tree T,
    the 90-day probability and the runway curve). L3 keeps every predict_tidemark column (the
    integrator and the app read them). Scoring always uses this saved version, so a --reuse run
    gives exactly the same numbers as a fresh one.
    """
    columns = list(p1_out.columns)
    if rung.name != "L3":
        columns = [c for c in columns if c in ("row", "uid", "issue_date")
                   or c.startswith(("p_T_", "p90_", "curve_"))]
    out = p1_out[columns].copy()
    for column in out.columns:
        if out[column].dtype == np.float64:
            out[column] = out[column].astype(np.float32)
    for column in ("uid", "region"):
        if column in out.columns:
            out[column] = out[column].astype("category")
    return out


def fit_and_forecast(rung, inputs, reuse):
    """tidemark.fit_tidemark + predict_tidemark for `rung` (or the saved forecasts). Returns (p1 forecasts, summary).

    Saved to data_cache/preds/VAL/tidemark/<name>_p1.pkl (lean_forecasts) and <name>_fit_summary.pkl/.json.
    """
    name = run_name(rung)
    p1_path = prediction_path(BLOCK, PRED_TASK, f"{name}_p1")
    summary_path = prediction_path(BLOCK, PRED_TASK, f"{name}_fit_summary")
    if reuse and p1_path.exists() and summary_path.exists():
        log(f"reloaded the saved {rung.name} forecasts")
        return pd.read_pickle(p1_path), pd.read_pickle(summary_path)
    model = tidemark.fit_tidemark(config.VAL_START, rung, inputs=inputs, log=log)
    p1_out = lean_forecasts(tidemark.predict_tidemark(model, inputs)["p1"], rung)
    summary = dict(tidemark.summary(model), physics_gain_share=physics_gain_share(model))
    p1_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = p1_path.with_suffix(".tmp")
    p1_out.to_pickle(temporary)
    temporary.replace(p1_path)                       # never leave a half-written file behind
    pd.to_pickle(summary, summary_path)
    summary_path.with_suffix(".json").write_text(json.dumps(clean_for_json(summary), indent=1))
    log(f"{rung.name}: {len(p1_out):,} P1 forecasts saved to {p1_path.relative_to(config.REPO_DIR)}")
    return p1_out, summary


# ===========================================================================
# Frames for the scorecard
# ===========================================================================
def require(task, name, step):
    """A saved prediction table from an earlier step; stops with a clear message if it is missing."""
    if not prediction_path(BLOCK, task, name).exists():
        raise SystemExit(f"Missing {prediction_path(BLOCK, task, name)}: run {step} first.")
    return load_predictions(BLOCK, task, name)


def attach(frame, other, columns):
    """Copy `columns` from `other`; both must list the same forecasts in the same order (checked)."""
    same = len(frame) == len(other) and \
        (frame["uid"].astype(str).to_numpy() == other["uid"].astype(str).to_numpy()).all() and \
        (pd.to_datetime(frame["issue_date"]).to_numpy() == pd.to_datetime(other["issue_date"]).to_numpy()).all()
    if not same:
        raise AssertionError("Prediction tables are not row-aligned.")
    for column in columns:
        frame[column] = other[column].to_numpy()
    return frame


def on_rows(p1_out, positions, column):
    """An output column of a predict_tidemark p1 table, read on the given P1-table rows."""
    return p1_out.set_index("row").loc[np.asarray(positions), column].to_numpy()


def assert_val_only(frame):
    """Refuse to score anything outside VAL (this script never looks at TEST)."""
    if set(time_block(frame["issue_date"])) != {BLOCK}:
        raise AssertionError("Expected VAL issues only.")


def p1_frame(table, kind):
    """Keys, flags, the scored label and the physics columns of every at-risk VAL issue of `kind`.

    Returns (frame, positions): positions are the frame rows' places in the P1 table.
    """
    picked = rows.p1_block_rows(table, kind, BLOCK)
    chosen = table.loc[picked]
    frame = pd.DataFrame({
        "uid": chosen["uid"].astype(str).to_numpy(), "issue_date": chosen["issue_date"].to_numpy(),
        "region": chosen["region"].astype(str).to_numpy(),
        "dam_like": chosen["dam_like"].to_numpy(dtype=bool), "persistent": chosen["persistent"].to_numpy(dtype=bool),
        "at_risk": True, "y": rows.p1_scored_label(chosen, kind)})
    for column in tidemark.PHY_COLUMNS:
        frame[column] = chosen[column].to_numpy(dtype=float)
    return frame, np.flatnonzero(picked)


def expected_keys(frame, population, octmar_only):
    """The rows a P1 subset must be scored on, worked out here independently of the scorecard."""
    keep = frame["y"].notna().to_numpy() & frame[population].to_numpy(dtype=bool)
    if octmar_only:
        keep = keep & is_octmar(frame["issue_date"])
    return frame.loc[keep, ["uid", "issue_date"]]


def forecast_columns(table, kind, runs, references):
    """The P1 frame of `kind` with one p_<model> column per model and reference.

    runs        {run name: predict_tidemark p1 table} of this step (L1+PHY, maybe L3)
    references  {name: p1 table} of earlier steps (L1 from step 8, L2 from step 9 if saved)
    Columns: p_TPHY (T+PHY alone), p_L1PHY, p_L3, p_G2 (step 3), p_L1, p_L2.
    """
    frame, positions = p1_frame(table, kind)
    frame["p_TPHY"] = on_rows(runs["L1+PHY"], positions, f"p_T_{kind}")
    frame["p_L1PHY"] = on_rows(runs["L1+PHY"], positions, f"p90_{kind}")
    if "L3" in runs:
        frame["p_L3"] = on_rows(runs["L3"], positions, f"p90_{kind}")
    for name, p1_out in references.items():
        frame[f"p_{name}"] = on_rows(p1_out, positions, f"p90_{kind}")
    attach(frame, require(f"P1_{kind}", "models", "scripts/03_baselines_and_g2.py"), ["p_G2"])
    return frame


# ===========================================================================
# Scoring
# ===========================================================================
# (scorecard model name, forecast column, references for the paired gains)
def models_to_score(frame):
    """Which forecasts are scored, against which references (only those present in the frame)."""
    present = [r for r in ("L2", "L1", "G2") if f"p_{r}" in frame.columns]
    out = [("physics_T+PHY", "TPHY", ["G2"]), ("tidemark_L1+PHY", "L1PHY", ["L1", "G2"])]
    if "p_L3" in frame.columns:
        out.append(("tidemark_L3", "L3", present))
    return out


def score_p1(table, kind, runs, references, n_boot_main, n_boot_side):
    """Every model on every subset for one kind. Returns {(task, subset, column): scorecard result}."""
    task = f"P1_{kind}"
    frame = forecast_columns(table, kind, runs, references)
    base = {pop: require(task, f"baselines_{pop}", "scripts/03_baselines_and_g2.py") for pop in ("dam_like", "persistent")}
    results = {}
    for subset, population, octmar_only in P1_SUBSETS:
        scored = attach(frame.copy(), base[population], ["p_B0", "p_B2"])
        assert_val_only(scored)
        n_boot = n_boot_main if subset == "primary" else n_boot_side
        for model, column, refs in models_to_score(frame):
            results[(task, subset, column)] = score(
                scored.assign(p=scored[f"p_{column}"]), task, subset, model=model, refs=refs,
                expected_keys=expected_keys(frame, population, octmar_only), n_boot=n_boot, out_dir=SCORE_DIR,
                note=NOTE)
    log(f"{task}: {len(models_to_score(frame))} models scored on {len(P1_SUBSETS)} subsets")
    return results


def curve_frame(table, kind, p1_out, labels):
    """Keys, flags, labels at 30/60/90/180 days and the curve read from a predict_tidemark p1 table."""
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
        frame[f"p_{h}"] = on_rows(p1_out, positions, f"curve_{kind}_{h}")
    return frame


def data_end():
    """The date of the last satellite look in the archive (saved by the feature build)."""
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as handle:
        return pd.Timestamp(pickle.load(handle)["data_end"])


def paired_curve_gain(with_phy, without, n_boot):
    """Per horizon, on the primary rows with a known answer: (Brier without - Brier with) / Brier of B0_h.

    Positive = the physics columns helped. 95% interval: dam bootstrap (whole dams redrawn).
    """
    primary = with_phy["dam_like"].to_numpy() & is_octmar(with_phy["issue_date"])
    out = {}
    for h in tidemark.HORIZONS:
        known = primary & with_phy[f"y_{h}"].notna().to_numpy()
        y = with_phy.loc[known, f"y_{h}"].to_numpy(dtype=float)
        err_with = (with_phy.loc[known, f"p_{h}"].to_numpy() - y) ** 2
        err_without = (without.loc[known, f"p_{h}"].to_numpy() - y) ** 2
        err_b0 = (with_phy.loc[known, f"p_B0_{h}"].to_numpy() - y) ** 2

        def gain(w):
            return {"d_bss": float(np.sum(w * (err_without - err_with)) / np.sum(w * err_b0))}

        ci, _ = cluster_bootstrap(gain, with_phy.loc[known, "uid"].to_numpy(), n_boot, config.RANDOM_SEED) \
            if n_boot else ({}, None)
        out[h] = dict(rows=int(known.sum()), d_bss=gain(np.ones(int(known.sum())))["d_bss"],
                      ci_dam=ci.get("d_bss", [np.nan, np.nan]))
    return out


def score_curves(table, runs, references, n_boot):
    """H+PHY (and L3's curve) on the primary set, and the paired gain over step 8's H (no physics)."""
    labels_end = data_end()
    out = {}
    for kind in tidemark.CURVE_KINDS:
        labels = hazard.horizon_labels(table, kind, labels_end)
        base = require(f"{kind}_curve", "baselines_dam_like", "scripts/06_hazard_curve.py")
        columns = [f"p_B{b}_{h}" for b in (0, 2) for h in tidemark.HORIZONS]
        with_phy = attach(curve_frame(table, kind, runs["L1+PHY"], labels), base, columns)
        without = attach(curve_frame(table, kind, references["L1"], labels), base, columns)
        assert_val_only(with_phy)
        result = score_curve(with_phy, f"{kind}_curve", "primary", model="tidemark_H+PHY", n_boot=n_boot,
                             out_dir=SCORE_DIR, note=NOTE)
        out[kind] = dict(result=result, paired=paired_curve_gain(with_phy, without, n_boot))
        if "L3" in runs:   # L3's curve is H+PHY too: it must be the same model
            l3 = curve_frame(table, kind, runs["L3"], labels)
            out[kind]["L3_curve_equals_H+PHY"] = bool(np.array_equal(
                l3[[f"p_{h}" for h in tidemark.HORIZONS]].to_numpy(),
                with_phy[[f"p_{h}" for h in tidemark.HORIZONS]].to_numpy()))
        log(f"{kind}_curve: H+PHY scored, paired against H")
    return out


# ===========================================================================
# The report
# ===========================================================================
def fmt(value, digits=4, sign=True):
    """A number as text (blank-safe)."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def fmt_ci(ci, digits=4):
    """[low, high] as text."""
    if not ci or ci[0] is None or not np.isfinite(ci[0]):
        return ""
    return f"[{ci[0]:+.{digits}f}, {ci[1]:+.{digits}f}]"


def gain_of(result, ref):
    """(paired dBSS vs B0, dam CI, region-year CI) of a scorecard result against a reference."""
    key = f"d_bss_B0_vs_{ref}"
    return (result["point"].get(key), result.get("ci_dam", {}).get(key), result.get("ci_region_year", {}).get(key))


def gain_row(label, result, ref, expected=None):
    """One markdown row: a paired gain with both intervals, and the research's value if given."""
    value, ci_dam, ci_ry = gain_of(result, ref)
    exp = "" if expected is None else f"{expected[0]:+.4f} [{expected[1]:+.4f}, {expected[2]:+.4f}]"
    return f"| {label} | {fmt(value)} {fmt_ci(ci_dam)} | {fmt_ci(ci_ry)} | {exp} |"


def level_row(label, result, expected=None):
    """One markdown row: BSS vs B0 [dam CI], BSS vs B2, AUC, calibration slope, and the research's level."""
    point, ci = result["point"], result.get("ci_dam", {})
    exp = "" if expected is None else (f"{expected:+.4f} (diff {point['bss_B0'] - expected:+.4f}, "
                                       f"{'within' if abs(point['bss_B0'] - expected) <= TOLERANCE else 'OUTSIDE'} "
                                       f"+-{TOLERANCE})")
    return (f"| {label} | {fmt(point['bss_B0'])} {fmt_ci(ci.get('bss_B0'))} | {fmt(point['bss_B2'])} | "
            f"{fmt(point['auc'], 4, False)} | {fmt(point['cal_slope'], 3, False)} | {exp} |")


def write_report(r):
    """artifacts/val_physics.md and artifacts/val_physics.json."""
    p1, curves, checks, alone = r["p1"], r["curves"], r["parameter_checks"], r["physics_alone"]
    params = r["params"]
    l3_ran = any(column == "L3" for (_, _, column) in p1)
    lines = [
        "# VAL results: the physics features (rung L3's water-balance columns), build step 10",
        "",
        f"Generated by `scripts/10_physics_val.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only**: "
        "forecasts issued 2009-01-01 to 2015-12-31, development regions; every model learns from answers final "
        "before 2009-01-01. TEST was not scored.",
        "",
        "**What the physics is.** `damdays/models/physics.py`: a bucket water balance (rain-driven inflow, a BoM "
        "pan-evaporation seasonal shape, an extraction term), one pooled parameter set per yearly checkpoint fitted "
        "on look pairs before that checkpoint; a Kalman filter on rel^1.5; and 20 futures driven by the rain of the "
        "same months 1-20 years earlier. Output: `ph_p_R30` and `ph_p_D0`, the share of futures with each event "
        "within 90 days; blank before 1993. Rung L3 adds them to the tree T and the runway curve H.",
        "",
        "**What was run.** `tidemark.fit_tidemark(\"2009-01-01\", rung)` then `predict_tidemark`, with rung "
        "`L1+PHY` (L1 with the 2 columns in T and H = L3 without the nets)"
        + (" and rung `L3` (with the nets S and M)." if l3_ran else
           ". Rung L3 was **not run**: the 12 VAL nets are not all trained yet (scripts/09_nets_val.py)."),
        "Paired gains use the same rows and the shared scorecard; brackets are the dam 95% interval, then the "
        f"region-year interval (16 region-years, rough). Bootstrap draws: {r['n_boot_main']} (primary), "
        f"{r['n_boot_side']} (other subsets).",
        "",
        "## 1. The fitted balance",
        "",
        "| check | expected (pre-event) | got | |",
        "|---|---|---|---|",
    ]
    for row in checks["pairs"]:
        lines.append(f"| fit pairs, checkpoint {row['year']} | {row['expected']:,} | {row['got']:,} | "
                     f"{'exact' if row['match'] else 'DIFFERENT'} |")
    for row in checks["checkpoint_2009"]:
        lines.append(f"| checkpoint 2009: {row['parameter']} | {row['expected']:.4g} | {row['got']:.4g} | "
                     f"ratio {row['ratio']:.2f} |")
    lines += [
        "",
        "Fit pairs: consecutive looks of the same dam 1-40 days apart, both 2-105% full, second look before 1 Jan of "
        "the checkpoint year. Parameters for every checkpoint (c: share of full volume per mm of excess rain; e: per "
        "day at mean evaporation and full area; x: per day of full-weight extraction):",
        "",
        "| checkpoint | pairs | threshold (mm) | c | e | x |",
        "|---|---|---|---|---|---|",
    ]
    for _, row in params.iterrows():
        lines.append(f"| {int(row['year'])} | {int(row['n_pairs']):,} | {row['threshold_mm']:.0f} | {row['c']:.2e} | "
                     f"{row['e']:.2e} | {row['x']:.2e} |")
    summary, coverage = r["physics_summary"], r["coverage"]
    shares = "; ".join(f"{block} {v['share_with_physics']:.1%} of {v['rows']:,}" for block, v in coverage.items()
                       if "share_with_physics" in v)
    lines += [
        "",
        f"Kalman filter state at {summary['looks_with_filter_state']:,} of {summary['looks']:,} looks; physics values "
        f"for {summary['issues_with_physics']:,} of {summary['p1_issues']:,} P1 issues. Issues before 1993: "
        f"{coverage['issued_before_1993']['with_physics']} of {coverage['issued_before_1993']['rows']:,} have a value "
        f"(blank by design). Share with a value, issues from 1993: {shares}. The rest are blank because the dam's "
        "checkpoint full is not known yet (fewer than 20 earlier looks), so its level cannot be read.",
        "",
        "## 2. Physics alone (a weak forecaster, as expected)",
        "",
        "| kind | column | rows (VAL primary) | AUC | expected AUC | raw BSS vs B0 | expected raw BSS |",
        "|---|---|---|---|---|---|---|",
    ]
    for kind, a in alone.items():
        lines.append(f"| {kind} | {a['column']} | {a['rows_with_physics']:,} of {a['rows_primary']:,} | {a['auc']:.3f} | "
                     f"{a['expected']['auc']:.3f} | {a['bss_raw']:+.3f} | "
                     f"{fmt(a['expected'].get('bss_raw'), 3)} |")
    lines += [
        "",
        "Expected values: the physics family's PHYS (per-dam parameters; AUC does not depend on recalibration).",
        "",
        "## 3. Like for like: what the 2 columns add (VAL primary: dam-like, Oct-Mar, at risk)",
        "",
        "| kind | gain | paired dBSS vs B0 [dam] | [region-year] | pre-event reference |",
        "|---|---|---|---|---|",
    ]
    for kind in KINDS:
        task = f"P1_{kind}"
        lines.append(gain_row(f"{kind} | T+PHY vs T (= G2)", p1[(task, "primary", "TPHY")], "G2",
                              CLOSEST_T_PHY_REFERENCE[kind]))
        lines.append(gain_row(f"{kind} | L1+PHY vs L1", p1[(task, "primary", "L1PHY")], "L1"))
        if l3_ran and f"d_bss_B0_vs_L2" in p1[(task, "primary", "L3")]["point"]:
            lines.append(gain_row(f"{kind} | L3 vs L2 (inside the full model)", p1[(task, "primary", "L3")], "L2",
                                  FULL_MODEL_PHY_GAIN[kind]))
        else:
            lines.append(f"| {kind} | L3 vs L2 (inside the full model) | not run | | "
                         f"{FULL_MODEL_PHY_GAIN[kind][0]:+.4f} [{FULL_MODEL_PHY_GAIN[kind][1]:+.4f}, "
                         f"{FULL_MODEL_PHY_GAIN[kind][2]:+.4f}] |")
    lines += ["", "Pre-event references for T+PHY vs T (none is exactly like for like; the table shows the third):", ""]
    for label, values in T_PHY_REFERENCES:
        lines.append(f"- {label}: " + ", ".join(f"{k} {v[0]:+.4f} [{v[1]:+.4f}, {v[2]:+.4f}]" for k, v in values.items()))
    lines += [
        f"- The L3 vs L2 reference is the hybrid's stage B removal cost of PHY from the frozen full model "
        "(val_stageB.csv); there the tree is one third of the fused log-odds, so its gain is diluted.",
        "",
        "Levels on the same rows:",
        "",
        "| kind | model | BSS vs B0 [dam] | BSS vs B2 | AUC | cal. slope | pre-event level |",
        "|---|---|---|---|---|---|---|",
    ]
    for kind in KINDS:
        task = f"P1_{kind}"
        lines.append(level_row(f"{kind} | T+PHY", p1[(task, "primary", "TPHY")]))
        lines.append(level_row(f"{kind} | L1+PHY", p1[(task, "primary", "L1PHY")]))
        if l3_ran:
            lines.append(level_row(f"{kind} | **L3 (full)**", p1[(task, "primary", "L3")], L3_REFERENCE[kind]))
    if not l3_ran:
        lines.append("| all | L3 (full) | not run (nets not trained yet) | | | | R30 +0.1818, D0 +0.1948, D0g +0.1947 |")
    lines += [
        "",
        "Other subsets (paired gain over the model without physics):",
        "",
        "| kind | subset | T+PHY vs T | L1+PHY vs L1 |" + (" L3 vs L2 |" if l3_ran else ""),
        "|---|---|---|---|" + ("---|" if l3_ran else ""),
    ]
    for kind in KINDS:
        for subset, _, _ in P1_SUBSETS[1:]:
            task = f"P1_{kind}"
            cells = [f"{fmt(gain_of(p1[(task, subset, 'TPHY')], 'G2')[0])} {fmt_ci(gain_of(p1[(task, subset, 'TPHY')], 'G2')[1])}",
                     f"{fmt(gain_of(p1[(task, subset, 'L1PHY')], 'L1')[0])} {fmt_ci(gain_of(p1[(task, subset, 'L1PHY')], 'L1')[1])}"]
            if l3_ran:
                g = gain_of(p1[(task, subset, "L3")], "L2")
                cells.append(f"{fmt(g[0])} {fmt_ci(g[1])}")
            lines.append(f"| {kind} | {subset} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Physics share of the tree's split gain (L1+PHY fit): "
        + ", ".join(f"{k} {v['share']:.1%} (ranks {v['rank']})" for k, v in r["gain_share"].items())
        + ". Pre-event (physics family, 14 columns): R30 13%, D0 13%, D0g 20%.",
        "",
        "## 4. Runway curve: H+PHY vs H (VAL primary), each horizon against its own base rate",
        "",
        "| kind | horizon | H+PHY BSS vs B0_h [dam] | paired gain over H [dam] | pre-event H+PHY level |",
        "|---|---|---|---|---|",
    ]
    for kind in tidemark.CURVE_KINDS:
        res, paired = curves[kind]["result"], curves[kind]["paired"]
        for j, entry in enumerate(res["horizons"]):
            h = entry["horizon"]
            expected = H_PHY_REFERENCE[kind][j]
            got = entry["point"].get("bss_B0")
            lines.append(f"| {kind} | {h} d | {fmt(got)} {fmt_ci(entry.get('ci_dam', {}).get('bss_B0'))} | "
                         f"{fmt(paired[h]['d_bss'])} {fmt_ci(paired[h]['ci_dam'])} | {expected:+.4f} "
                         f"(diff {got - expected:+.4f}) |")
        mono = res["monotonicity"]
        lines.append(f"| {kind} | curves that fall | {mono['rows_falling']} of {mono['rows']:,} | | 0 |")
    lines += ["", "## 5. Notes", ""] + NOTES
    RESULTS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    RESULTS_JSON.write_text(json.dumps(clean_for_json(json_summary(r)), indent=1), encoding="utf-8")


def json_summary(r):
    """The report's numbers as plain data."""
    p1 = {f"{task}|{subset}|{column}": dict(point=res["point"], ci_dam=res.get("ci_dam"),
                                             ci_region_year=res.get("ci_region_year"), rows=res["rows"])
          for (task, subset, column), res in r["p1"].items()}
    curves = {kind: dict(bss_B0_by_horizon=v["result"]["bss_B0_by_horizon"], paired_gain_over_H=v["paired"],
                         monotonicity=v["result"]["monotonicity"],
                         **({"L3_curve_equals_H+PHY": v["L3_curve_equals_H+PHY"]} if "L3_curve_equals_H+PHY" in v else {}))
              for kind, v in r["curves"].items()}
    return dict(generated=time.strftime("%Y-%m-%d %H:%M"), block=BLOCK, params=r["params"].to_dict("records"),
                parameter_checks=r["parameter_checks"], physics_summary=r["physics_summary"], coverage=r["coverage"],
                physics_alone=r["physics_alone"], p1=p1, curves=curves, gain_share=r["gain_share"],
                references=dict(T_PHY=T_PHY_REFERENCES, full_model_phy_gain=FULL_MODEL_PHY_GAIN, L3=L3_REFERENCE,
                                H_PHY=H_PHY_REFERENCE, tolerance=TOLERANCE),
                fit_summaries=r["fit_summaries"], n_boot_main=r["n_boot_main"], n_boot_side=r["n_boot_side"])


NOTES = [
    "- **Time rules** (each checked by `tests/test_no_lookahead.py`, generator \"physics water balance\", which "
    "also plants a leak, the filter reading the issue month's own rain, and requires it to be caught): rel uses "
    "the checkpoint full; checkpoint Y's parameters use look pairs before 1 Jan Y; the filter's step into a look "
    "on day D uses actual rain of months that ended before D's month and the earlier-years average for D's own "
    "month; future l uses the rain of the same months l years earlier; every forecast shares one fixed set of 20 "
    "noise paths.",
    "- **Differences from the pre-event generator (tm01_phys.py), disclosed:** the evaporation shape is typed from "
    "BoM station climatology (Trangie Research Station 051049 for NSW, Longerenong 079028 for Vic/SA) instead of a "
    "rough proxy; parameters are refitted every year (the research: 1993, 1998, 2002, 2009, 2016); forecasts "
    "before 1993 are blank (the research used the 1993 fit, a small look-ahead on TRAIN rows); the filter starts "
    "at each dam's first 1993 look; all forecasts share one set of 20 noise paths (the research drew noise per "
    "block of rows). These can move the gains by a few thousandths; the fit-pair counts match exactly.",
    "- **Fit regions.** As in the research (and FINAL_SPEC: \"both regions pooled\"), the balance is fitted on "
    "the development regions' look pairs only (`physics.FIT_REGIONS`). Today every dam is in one, so this "
    "changes nothing here; it keeps the balance (and so every development forecast) unchanged when the sealed "
    "region's looks are added at its opening.",
    "- **L1+PHY is not a PREREG rung.** It is L3 without the nets, used here to measure the physics like for like. "
    "The PREREG ladder decides between L3, L2, L1 and L0 (on the +-0.006 reproduction rule and the look-ahead test).",
    "- **Forecasts** are in `data_cache/preds/VAL/tidemark/` as float32: `L1PHY_p1.pkl` (only the scored "
    "columns: T, the 90-day probability, the curve), `L3_p1.pkl` when run (every predict_tidemark column), with "
    "fit summaries; the physics columns are in `data_cache/features/physics_p1.pkl` (float32, P1 order).",
]


# ===========================================================================
# Main
# ===========================================================================
def main():
    """Build the physics columns, fit L1+PHY (and L3 when the nets are ready), score on VAL, write the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no bootstrap intervals")
    parser.add_argument("--reuse", action="store_true", help="reuse the saved physics table and forecasts")
    parser.add_argument("--l3", choices=("auto", "yes", "no"), default="auto",
                        help="fit rung L3: auto = only when the 12 VAL nets are saved (default)")
    args = parser.parse_args()
    n_boot_main, n_boot_side = (0, 0) if args.quick else (N_BOOT_MAIN, N_BOOT_SIDE)
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    for prefix in ("scorecard", "curves"):          # this run's markdown tables start empty
        (SCORE_DIR / f"{prefix}_dev_{BLOCK}.md").write_text("")

    params, physics_summary = build_physics_columns(args.reuse)
    log("loading the inputs (P1 table with the physics columns, P2 tables)")
    inputs = tidemark.load_inputs()
    table = inputs["p1"]
    if not set(tidemark.PHY_COLUMNS) <= set(table.columns):
        raise SystemExit("The physics columns did not reach the P1 table.")

    runs, fit_summaries = {}, {}
    runs["L1+PHY"], fit_summaries["L1+PHY"] = fit_and_forecast(L1_PHY, inputs, args.reuse)
    run_l3 = args.l3 == "yes" or (args.l3 == "auto" and nets_ready())
    if run_l3:
        runs["L3"], fit_summaries["L3"] = fit_and_forecast(tidemark.RUNGS["L3"], inputs, args.reuse)
    else:
        log("rung L3 skipped: the 12 VAL nets are not all saved in data_cache/nets/ (scripts/09_nets_val.py)")
    references = {"L1": require(PRED_TASK, "L1_p1", "scripts/08_tidemark_val.py")}
    if prediction_path(BLOCK, PRED_TASK, "L2_p1").exists():
        references["L2"] = load_predictions(BLOCK, PRED_TASK, "L2_p1")

    results = {}
    for kind in KINDS:
        results.update(score_p1(table, kind, runs, references, n_boot_main, n_boot_side))
    report = dict(params=params, physics_summary=physics_summary, parameter_checks=parameter_checks(params),
                  coverage=physics_coverage(table), physics_alone=physics_alone(table), p1=results,
                  curves=score_curves(table, runs, references, n_boot_main),
                  gain_share=fit_summaries["L1+PHY"].get("physics_gain_share", {}),
                  fit_summaries={name: {k: v for k, v in s.items() if k in ("rung", "rung_about", "members")}
                                 for name, s in fit_summaries.items()},
                  n_boot_main=n_boot_main, n_boot_side=n_boot_side)
    write_report(report)
    log(f"wrote {RESULTS_MD.name} and {RESULTS_JSON.name}")
    for row in report["parameter_checks"]["pairs"]:
        print(f"  fit pairs {row['year']}: expected {row['expected']:,} got {row['got']:,} "
              f"{'exact' if row['match'] else 'DIFFERENT'}")
    for kind in KINDS:
        task = f"P1_{kind}"
        for column, ref in (("TPHY", "G2"), ("L1PHY", "L1")) + ((("L3", "L2"),) if run_l3 and "L2" in references else ()):
            value, ci, _ = gain_of(results[(task, "primary", column)], ref)
            print(f"  {kind}: {column} vs {ref}: {fmt(value)} {fmt_ci(ci)}  "
                  f"(BSS vs B0 {results[(task, 'primary', column)]['point']['bss_B0']:+.4f})")


if __name__ == "__main__":
    main()
