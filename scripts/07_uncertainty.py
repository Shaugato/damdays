"""Step 7: the two uncertainty products, checked on VAL: the DamDays floor (LB90) and the season band.

Run from the repo folder (after scripts/02_build_features.py and scripts/03_baselines_and_g2.py):
    .venv/Scripts/python.exe scripts/07_uncertainty.py            # about 5 minutes
    .venv/Scripts/python.exe scripts/07_uncertainty.py --quick    # no bootstrap intervals

What it does (damdays/models/uncertainty.py explains both products)
  1. DamDays floor. Fits the 10% quantile model of log(1 + days to R30,
     capped at 365) on TRAIN forecasts whose 395-day answer was final before
     2009-01-01, and predicts every at-risk VAL forecast. Then checks the
     split-conformal floor on VAL:
       * leave-one-year-out inside VAL (the pre-event procedure; the check values),
       * a forward split (calibrate on VAL forecasts answered before
         2012-07-01, judge those issued after: the real-time version),
       * the floor as displayed (whole days, "180+"),
       * the label sensitivity row (also forecasts without a determinable label),
       * the pre-event recipe (a 300,000-row subsample),
     and computes the shift frozen for TEST (VAL forecasts answered before 2016-07-01).
  2. Season band, with G2 as a stand-in for Tidemark's anchor (R30, D0, D0g):
       * inner block 2002-2009: G2 refitted on answers final before 2002-01-01
         (its dam_rate prior recomputed as of 2002), offsets on 2002-2008 forecasts;
       * block 2009-2016: G2 refitted at 2009-01-01 (the VAL fit), offsets on
         forecasts issued 2009-01 to 2016-06 and answered before 2016-07-01;
       * VAL coverage: the 2002-2009 band (all that existed before VAL) on the
         16 VAL region-years of the official G2 predictions; leave-one-year-out
         checks; the pooled band constants the PREREG uses for TEST.
  3. Writes artifacts/uncertainty_val.json and artifacts/uncertainty_val.md,
     saves the VAL floors to data_cache/preds/VAL/P1_R30/floor_LB90.pkl and
     prints expected vs got.

TEST is never touched: no TEST forecast is predicted or scored. The 2009-2016
band block uses forecasts up to June 2016 (the unused GAP block), never TEST.
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
from damdays.evaluation import band_coverage, floor_coverage  # noqa: E402
from damdays.evaluation.report import clean_for_json  # noqa: E402
from damdays.evaluation.rules import is_octmar  # noqa: E402
from damdays.features import store  # noqa: E402
from damdays.models import rows  # noqa: E402
from damdays.models import uncertainty as unc  # noqa: E402
from damdays.models.predictions import load_predictions, save_predictions  # noqa: E402

BLOCK = "VAL"
RESULTS_JSON = config.ARTIFACTS_DIR / "uncertainty_val.json"
RESULTS_MD = config.ARTIFACTS_DIR / "uncertainty_val.md"
N_BOOT = 200                          # dam-bootstrap draws for the floor coverage intervals
FORWARD_SPLIT = "2012-07-01"          # floor forward check: calibrate before, judge from this date
PRE_EVENT_SUBSAMPLE = 300_000         # the pre-event floor model's fit subsample (speed only)
BAND_KINDS = ("R30", "D0", "D0g")
EXAMPLE_P = (0.05, 0.10, 0.30, 0.50)

# ---------------------------------------------------------------------------
# Check values from the pre-event research
#   floor: bench/results/calibration-uncertainty/tables/conformal_VAL.json
#          (R30, LB90, "split" variant, VAL leave-one-year-out) and RESULT.md section 5
#   band:  there is no pre-event inner-backtest band for G2. The nearest references are
#          Tidemark v1's 90-day anchor (bench/results/hybrid/tables/val_v1_stageD.json,
#          band_<kind>.anchor90, same 2002-2009 inner block) and the calibration family's
#          G2 + Platt band (calibration-uncertainty/tables/season_band_VAL.json, VAL LOYO).
# ---------------------------------------------------------------------------
FLOOR_CHECKS = [
    # (label, result key, metric, expected, tolerance as a reading aid)
    ("LOYO coverage, all at-risk forecasts", "loyo_all", "coverage", 0.9001, 0.005),
    ("LOYO coverage, primary set", "loyo_primary", "coverage", 0.9102, 0.005),
    ("LOYO worst July-June year (all)", "loyo_all", "worst_year_coverage", 0.878, 0.01),
    ("LOYO median floor, days (all)", "loyo_all", "median_floor_days", 45.03, 3.0),
    ("LOYO median floor, days (primary)", "loyo_primary", "median_floor_days", 44.61, 3.0),
    ("LOYO share of floors >= 90 days (all)", "loyo_all", "share_ge_90", 0.259, 0.02),
    ("raw q10 coverage (no conformal), all", "raw_all", "coverage", 0.8997, 0.005),
    ("raw q10 coverage (no conformal), primary", "raw_primary", "coverage", 0.9098, 0.005),
]
BAND_REFERENCES = {
    "R30": dict(tidemark_anchor_band=[-1.065, 0.761], tidemark_anchor_covered="15/16 (missed nsw_cw:2011 at -1.97)",
                tidemark_anchor_loyo="13/16", g2_platt_loyo="14/16 (0.875)"),
    "D0": dict(tidemark_anchor_band=[-1.130, 0.547],
               tidemark_anchor_covered="13/16 (missed nsw_cw:2011 -1.85, wvic_sesa:2010 -1.15, wvic_sesa:2011 -1.19)",
               tidemark_anchor_loyo="13/16", g2_platt_loyo="14/16 (0.875)"),
    "D0g": dict(tidemark_anchor_band=None, tidemark_anchor_covered="not run", tidemark_anchor_loyo="not run",
                g2_platt_loyo="14/16 (0.875)"),
}

STARTED = time.time()


def log(message):
    """Print a progress line with the minutes since the script started."""
    print(f"[{(time.time() - STARTED) / 60:5.1f} min] {message}", flush=True)


def data_end():
    """The last date in the satellite archive (stored with the feature tables)."""
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as handle:
        return pd.Timestamp(pickle.load(handle)["data_end"])


# ===========================================================================
# 1. DamDays floor
# ===========================================================================
def floor_frame(table, model):
    """Every at-risk VAL forecast for R30, with its q10, its answer and its follow-up."""
    pick = rows.p1_block_rows(table, unc.FLOOR_KIND, BLOCK)
    picked = table.loc[pick]
    frame = pd.DataFrame({
        "uid": picked["uid"].astype(str).to_numpy(), "issue_date": picked["issue_date"].to_numpy(),
        "region": picked["region"].astype(str).to_numpy(), "hydro_year": hydro_year(picked["issue_date"]),
        "dam_like": picked["dam_like"].to_numpy(dtype=bool), "label_ok": picked["label_ok"].to_numpy(dtype=bool),
        "warm": picked["warm"].to_numpy(dtype=bool),
        "days_to_R30": picked[f"lab_tte_{unc.FLOOR_KIND}"].to_numpy(dtype=float),   # NaN: no later event
        "runway_days": unc.runway_days(picked),                                      # capped at 365
        "followup_days": unc.followup_days(picked["issue_date"], data_end()),
    })
    frame["log_q10"] = unc.predict_log_q10(model, table, pick)
    frame["primary"] = frame["dam_like"].to_numpy() & is_octmar(frame["issue_date"])
    return frame


def summarise_floor(frame, floors, mask, n_boot, cap_days=None):
    """Floor coverage (the scorecard's floor_coverage) plus the share of long floors, on the rows in mask."""
    part = frame[mask]
    shown = np.asarray(floors)[mask]
    result = floor_coverage(shown, part["days_to_R30"], part["followup_days"], uid=part["uid"],
                            issue_date=part["issue_date"], cap_days=cap_days, n_boot=n_boot)
    result["share_ge_90"] = float(np.mean(shown >= 90))
    result["share_180_plus"] = float(np.mean(shown >= unc.FLOOR_DISPLAY_MAX_DAYS))
    result["worst_year_coverage"] = result.get("worst_year", {}).get("coverage", np.nan)
    held = np.where(np.isnan(part["days_to_R30"]), np.inf, part["days_to_R30"]) >= shown
    groups = part["region"] + ":" + np.where(part["warm"], "Oct-Mar", "Apr-Sep")
    result["by_region_half_year"] = pd.Series(held).groupby(groups.to_numpy()).mean().round(4).to_dict()
    result.pop("bootstrap", None)
    return result


def floor_results(table, n_boot):
    """Fit the floor model, then every VAL check of the floor. Returns (results dict, frame with floors)."""
    model, fit_info = unc.fit_floor_model(table, config.VAL_START)
    log(f"floor model: {fit_info['fit_rows']:,} fit rows ({fit_info['first_issue']} to {fit_info['last_issue']})")
    frame = floor_frame(table, model)
    labelled = frame["label_ok"].to_numpy()                 # the rows the pre-event research used
    calib = frame[labelled]
    out = {"fit": fit_info, "val_rows_at_risk": len(frame), "val_rows_labelled": int(labelled.sum())}

    # Leave-one-year-out (the pre-event procedure): each VAL year calibrated on the other VAL years.
    shifts = unc.leave_one_year_out_shifts(calib["log_q10"], calib["runway_days"], calib["hydro_year"])
    frame["floor_loyo"] = unc.floor_days(frame["log_q10"], unc.shifts_for_rows(frame["hydro_year"], shifts))
    frame["floor_shown"] = unc.displayed_floor_days(frame["floor_loyo"])
    frame["floor_raw"] = unc.floor_days(frame["log_q10"], 0.0)
    out["loyo_shifts_by_year"] = shifts
    primary = labelled & frame["primary"].to_numpy()
    for name, floors in (("raw", "floor_raw"), ("loyo", "floor_loyo")):
        out[f"{name}_all"] = summarise_floor(frame, frame[floors], labelled, n_boot if name == "loyo" else 0)
        out[f"{name}_primary"] = summarise_floor(frame, frame[floors], primary, n_boot if name == "loyo" else 0)
    out["shown_all"] = summarise_floor(frame, frame["floor_shown"], labelled, 0, cap_days=unc.FLOOR_DISPLAY_MAX_DAYS)
    out["shown_primary"] = summarise_floor(frame, frame["floor_shown"], primary, 0, cap_days=unc.FLOOR_DISPLAY_MAX_DAYS)
    # Sensitivity row: every at-risk forecast, also those without a determinable 90-day label.
    out["loyo_all_incl_unlabelled"] = summarise_floor(frame, frame["floor_loyo"], np.ones(len(frame), bool), 0)
    log(f"floor LOYO: coverage {out['loyo_all']['coverage']:.4f} (all), {out['loyo_primary']['coverage']:.4f} "
        f"(primary), median {out['loyo_all']['median_floor_days']:.1f} days")

    # Forward split (real time): calibrate on VAL forecasts answered before FORWARD_SPLIT.
    floors_later, later, shift, n_cal = unc.forward_split_floors(
        calib["log_q10"], calib["runway_days"], calib["issue_date"], FORWARD_SPLIT)
    forward = np.full(len(frame), np.nan)
    forward[np.flatnonzero(labelled)[later]] = floors_later
    later_rows = labelled & ~np.isnan(forward)
    out["forward"] = dict(split=FORWARD_SPLIT, shift=shift, calibration_rows=n_cal,
                          all=summarise_floor(frame, forward, later_rows, 0),
                          primary=summarise_floor(frame, forward, later_rows & frame["primary"].to_numpy(), 0),
                          loyo_same_rows=summarise_floor(frame, frame["floor_loyo"], later_rows, 0))

    # The shift frozen for TEST: VAL forecasts whose 395-day answer was final before TEST starts.
    frozen, n_frozen = unc.shift_from_answers_before(calib["log_q10"], calib["runway_days"], calib["issue_date"],
                                                     config.TEST_START)
    scores = unc.conformity_scores(calib["log_q10"], calib["runway_days"])
    frozen_scores = scores[unc.runway_answer_final(calib["issue_date"], config.TEST_START)]
    out["frozen_for_test"] = dict(shift=frozen, calibration_rows=n_frozen,
                                  shift_all_val_rows_pre_event_way=unc.conformal_shift(scores), all_val_rows=len(calib),
                                  # Why the shift can be exactly 0: q10 at the 365-day cap with no event within a
                                  # year gives a score of exactly 0, and the 90% rank can land on one of those ties.
                                  share_scores_at_most_zero=float(np.mean(frozen_scores <= 0)),
                                  share_scores_exactly_zero=float(np.mean(frozen_scores == 0)))

    # The pre-event recipe: the same model on a 300,000-row subsample.
    model_ref, info_ref = unc.fit_floor_model(table, config.VAL_START, max_rows=PRE_EVENT_SUBSAMPLE)
    q_ref = unc.predict_log_q10(model_ref, table, rows.p1_block_rows(table, unc.FLOOR_KIND, BLOCK))[labelled]
    shifts_ref = unc.leave_one_year_out_shifts(q_ref, calib["runway_days"], calib["hydro_year"])
    floors_ref = np.full(len(frame), np.nan)
    floors_ref[labelled] = unc.floor_days(q_ref, unc.shifts_for_rows(calib["hydro_year"], shifts_ref))
    out["pre_event_recipe"] = dict(fit=info_ref, all=summarise_floor(frame, floors_ref, labelled, 0),
                                   primary=summarise_floor(frame, floors_ref, primary, 0))
    log("floor: forward split, frozen shift and pre-event recipe done")
    return out, frame


def save_floors(frame):
    """VAL floors for later steps and the app (data_cache/preds/VAL/P1_R30/floor_LB90.pkl)."""
    columns = ["uid", "issue_date", "region", "label_ok", "log_q10", "floor_raw", "floor_loyo", "floor_shown"]
    return save_predictions(frame[columns], BLOCK, f"P1_{unc.FLOOR_KIND}", "floor_LB90")


# ===========================================================================
# 2. Season band (G2 as the stand-in anchor)
# ===========================================================================
def official_g2(table, kind):
    """The official VAL G2 predictions (step 3), placed on the table's rows (NaN elsewhere)."""
    saved = load_predictions(BLOCK, f"P1_{kind}", "models")
    pick = rows.p1_block_rows(table, kind, BLOCK)
    same = (saved["uid"].astype(str).to_numpy() == table.loc[pick, "uid"].astype(str).to_numpy()).all() and \
        (pd.to_datetime(saved["issue_date"]).to_numpy() == pd.to_datetime(table.loc[pick, "issue_date"]).to_numpy()).all()
    if not same:
        raise AssertionError(f"Saved G2 predictions for {kind} are not row-aligned with the P1 table.")
    p = np.full(len(table), np.nan)
    p[pick] = saved["p_G2"].to_numpy(dtype=float)
    return p


def offsets_for(table, kind, mask, p, block):
    """Region-year offsets of predictions p (one per row in mask) on those rows."""
    part = table.loc[mask]
    return unc.block_offsets(part[rows.p1_label(kind)].to_numpy(dtype=float), p, part["region"],
                             part["issue_date"], block)


def band_examples(band):
    """What the band looks like around a few forecasts: {p: [low, high]}."""
    low, high = unc.band_probabilities(np.array(EXAMPLE_P), band)
    return {str(p0): [float(lo), float(hi)] for p0, lo, hi in zip(EXAMPLE_P, low, high)}


def band_for_kind(table, kind):
    """Inner blocks, VAL coverage and band constants for one event kind."""
    out = {}
    # Inner block 2002-2009: G2 fitted at 2002-01-01, its dam_rate prior as of 2002.
    start_a, cutoff_a = unc.BAND_INNER_BLOCKS["VAL"][0]
    mask_a = unc.band_rows(table, kind, start_a, cutoff_a)
    rate_2002 = unc.dam_rate_as_of(table, kind, start_a)
    p_a, out["fit_2002"] = unc.fit_predict_g2_at(table, kind, start_a, mask_a, dam_rate=rate_2002)
    off_a = offsets_for(table, kind, mask_a, p_a, "2002-2009")

    # Block 2009-2016: G2 refitted at 2009-01-01 (the VAL fit), forecasts to June 2016 answered before July 2016.
    start_b, cutoff_b = unc.BAND_INNER_BLOCKS["TEST"][1]
    mask_b = unc.band_rows(table, kind, start_b, cutoff_b)
    p_b, out["fit_2009"] = unc.fit_predict_g2_at(table, kind, start_b, mask_b)
    off_b = offsets_for(table, kind, mask_b, p_b, "2009-2016")

    # VAL region-years of the official G2 predictions (what the band is judged on).
    official = official_g2(table, kind)
    mask_val = mask_b & (time_block(table["issue_date"]) == BLOCK)
    off_val = offsets_for(table, kind, mask_val, official[mask_val], "VAL")
    refit_on_val = np.full(len(table), np.nan)
    refit_on_val[mask_b] = p_b
    out["refit_vs_official_max_abs_diff"] = float(np.nanmax(np.abs(refit_on_val[mask_val] - official[mask_val])))

    band_a = unc.pooled_band(off_a)
    band_b = unc.pooled_band(off_b)
    band_pooled = unc.pooled_band(off_a, off_b)
    out["rows"] = dict(block_2002_2009=int(mask_a.sum()), block_2009_2016=int(mask_b.sum()), val=int(mask_val.sum()))
    out["band_val_setting"] = band_a
    out["band_test_setting_pooled"] = band_pooled
    out["band_test_setting_single_block"] = band_b
    out["coverage_val_forward"] = band_coverage(off_val, *band_a)
    out["coverage_val_loyo_pooled"] = unc.leave_one_year_out_band_coverage(off_val, extra_offsets=off_a)
    out["coverage_val_loyo_val_only"] = unc.leave_one_year_out_band_coverage(off_val)
    out["examples_pooled"] = band_examples(band_pooled)
    out["examples_val_setting"] = band_examples(band_a)
    out["offsets"] = pd.concat([off_a, off_b, off_val], ignore_index=True).to_dict("records")

    if kind == "R30":
        # Diagnostic: the 2002 inner fit with the STORED dam_rate (prior from answers up to 2008), as the
        # pre-event research did. Shows how much the causal prior matters.
        p_stored, info = unc.fit_predict_g2_at(table, kind, start_a, mask_a)
        off_stored = offsets_for(table, kind, mask_a, p_stored, "2002-2009 stored dam_rate")
        band_stored = unc.pooled_band(off_stored)
        out["diagnostic_stored_dam_rate"] = dict(fit=info, band=band_stored,
                                                 coverage_val=band_coverage(off_val, *band_stored))
        stored = table[f"dam_rate_{kind}"].to_numpy(dtype=float)
        rate_2009 = unc.dam_rate_as_of(table, kind, config.VAL_START)
        out["dam_rate_as_of_2009_vs_stored_max_abs_diff"] = float(np.nanmax(np.abs(rate_2009 - stored)))
        out["dam_rate_as_of_2002_vs_stored_median_abs_diff"] = float(np.nanmedian(np.abs(rate_2002 - stored)[mask_a]))
    log(f"band {kind}: VAL-setting band [{band_a[0]:+.3f}, {band_a[1]:+.3f}] covers "
        f"{out['coverage_val_forward']['covered']}/{out['coverage_val_forward']['region_years']} VAL region-years; "
        f"pooled [{band_pooled[0]:+.3f}, {band_pooled[1]:+.3f}]")
    return out


# ===========================================================================
# 3. Report
# ===========================================================================
def fmt(value, digits=3, sign=False):
    """A number for a table cell ("-" when missing)."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def floor_check_rows(floor):
    """Expected (pre-event) vs got (this build) for the floor."""
    out = []
    for label, key, metric, expected, tolerance in FLOOR_CHECKS:
        got = floor[key][metric]
        out.append(dict(check=label, expected=expected, got=got, difference=got - expected, tolerance=tolerance,
                        within=bool(abs(got - expected) <= tolerance)))
    return out


def ci_text(result):
    """The dam-bootstrap interval of a coverage, as text."""
    ci = result.get("ci_dam", {}).get("coverage")
    return f" [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ""


def floor_row(name, result, note=""):
    """One markdown row of the floor table."""
    worst = result.get("worst_year", {})
    return (f"| {name} | {result['rows_judged']:,} | {result['coverage']:.4f}{ci_text(result)} | "
            f"{worst.get('year', '-')} ({fmt(worst.get('coverage'))}) | {result['median_floor_days']:.1f} | "
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


def write_report(floor, checks, band):
    """artifacts/uncertainty_val.md (for people) and artifacts/uncertainty_val.json (for code)."""
    lines = [
        "# VAL results: the DamDays floor and the season band (build step 7)",
        "",
        f"Generated by `scripts/07_uncertainty.py` on {time.strftime('%Y-%m-%d %H:%M')} (AEST). **VAL only** "
        "(forecasts issued 2009-01-01 to 2015-12-31, development regions). TEST was not touched. The method is "
        "explained in `damdays/models/uncertainty.py`; coverage is judged by `damdays.evaluation.coverage`.",
        "",
        "## 1. DamDays floor (LB90): \"at least N days above a third, 90% confidence\"",
        "",
        f"Quantile model: LightGBM 10% quantile of log(1 + days to R30, capped at 365) on the 29 G2 features, fitted "
        f"on {floor['fit']['fit_rows']:,} TRAIN forecasts (at risk, label determinable) whose 395-day answer was final "
        f"before 2009-01-01 (issued {floor['fit']['first_issue']} to {floor['fit']['last_issue']}). Judged on "
        f"{floor['val_rows_labelled']:,} at-risk VAL forecasts with a determinable label (the pre-event rows). Every "
        "VAL forecast has at least 10 years of follow-up, so every floor can be judged.",
        "",
        "| floor | forecasts | coverage [dam 95%] | worst July-June year | median floor (days) | share >= 90 d | "
        "share >= 180 d | note |",
        "|---|---|---|---|---|---|---|---|",
        floor_row("raw q10, no conformal (all)", floor["raw_all"]),
        floor_row("raw q10, no conformal (primary)", floor["raw_primary"]),
        floor_row("**LOYO conformal (all)**", floor["loyo_all"], "pre-event procedure; check values"),
        floor_row("**LOYO conformal (primary)**", floor["loyo_primary"], "dam-like, Oct-Mar, at risk"),
        floor_row("as displayed: whole days, 180+ (all)", floor["shown_all"], "judged at min(N, 180)"),
        floor_row("as displayed: whole days, 180+ (primary)", floor["shown_primary"], ""),
        floor_row(f"forward split: issued from {FORWARD_SPLIT} (all)", floor["forward"]["all"],
                  f"calibrated on {floor['forward']['calibration_rows']:,} forecasts answered before {FORWARD_SPLIT}"),
        floor_row(f"forward split: issued from {FORWARD_SPLIT} (primary)", floor["forward"]["primary"], ""),
        floor_row(f"LOYO on the same forecasts (from {FORWARD_SPLIT})", floor["forward"]["loyo_same_rows"],
                  "for comparison with the forward split"),
        floor_row("sensitivity: all at-risk, incl. no determinable label", floor["loyo_all_incl_unlabelled"],
                  f"{floor['val_rows_at_risk']:,} forecasts"),
        floor_row("pre-event recipe: 300k-row subsample, LOYO (all)", floor["pre_event_recipe"]["all"], ""),
        floor_row("pre-event recipe: 300k-row subsample, LOYO (primary)", floor["pre_event_recipe"]["primary"], ""),
        "",
        "LOYO = leave one July-June year out: each VAL year's shift comes from the other VAL years (the pre-event "
        "check; it uses later years, so it checks the method). The forward split is the real-time version.",
        "",
        "Conformal shifts (log days) by held-out year: " + ", ".join(
            f"{y}: {s:+.4f}" for y, s in floor["loyo_shifts_by_year"].items())
        + f". Forward split shift {floor['forward']['shift']:+.4f}.",
        "",
        f"**Frozen for TEST and the sealed region:** shift c = {floor['frozen_for_test']['shift']:+.4f} log days, from "
        f"the {floor['frozen_for_test']['calibration_rows']:,} VAL forecasts whose 395-day answer was final before "
        f"2016-07-01 (the pre-event way, all {floor['frozen_for_test']['all_val_rows']:,} VAL forecasts, gives "
        f"{floor['frozen_for_test']['shift_all_val_rows_pre_event_way']:+.4f}). The shift is 0 because the raw q10 "
        f"already holds for {floor['frozen_for_test']['share_scores_at_most_zero']:.3%} of those forecasts and "
        f"{floor['frozen_for_test']['share_scores_exactly_zero']:.2%} of the scores are exactly 0 (q10 at the 365-day "
        "cap and no event within a year), so the 90% rank falls on one of those ties. The pre-event research also "
        "found the raw q10 already calibrated (shift 0.002).",
        "",
        "Coverage by region and half-year (LOYO, all): " + ", ".join(
            f"{k} {v:.3f}" for k, v in floor["loyo_all"]["by_region_half_year"].items()) + ".",
        "",
        "### Check values: expected (pre-event, VAL LOYO) vs got",
        "",
        "| check | expected | got | difference | reading aid | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for c in checks:
        lines.append(f"| {c['check']} | {fmt(c['expected'], 4)} | {fmt(c['got'], 4)} | {fmt(c['difference'], 4, True)} | "
                     f"+-{c['tolerance']} | {'within' if c['within'] else 'OUTSIDE'} |")
    lines += [
        "",
        "Pre-event worst year: 2013 (0.878). Pre-event TEST result (not re-scored here): 0.901 all, 0.911 primary, "
        "median 60 days.",
        "",
        "## 2. Season band (G2 as the stand-in anchor)",
        "",
        "Offsets are the calibration-in-the-large of each region x July-June year on the primary set (dam-like, "
        "Oct-Mar, at risk, label determinable), counted when the region-year has at least 200 forecasts and 5 events. "
        "The 2002-2009 block is G2 refitted on answers final before 2002-01-01 (its dam_rate prior recomputed from "
        "those answers only), scored on 2002-2008 forecasts answered before 2009-01-01. The 2009-2016 block is G2 "
        "refitted at 2009-01-01, scored on forecasts issued 2009-01 to 2016-06 and answered before 2016-07-01.",
        "",
        "| kind | VAL-setting band (2002-2009 block) | VAL region-years covered | missed | LOYO, pooled with "
        "2002-2009 | LOYO, VAL only | TEST band, pooled (PREREG) | TEST band, 2009-2016 only |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for kind in BAND_KINDS:
        b = band[kind]
        fwd, lp, lv = b["coverage_val_forward"], b["coverage_val_loyo_pooled"], b["coverage_val_loyo_val_only"]
        lines.append(f"| {kind} | {band_text(b['band_val_setting'])} | {fwd['covered']}/{fwd['region_years']} | "
                     f"{missed_text(fwd)} | {lp['covered']}/{lp['region_years']} | {lv['covered']}/{lv['region_years']} | "
                     f"{band_text(b['band_test_setting_pooled'])} | {band_text(b['band_test_setting_single_block'])} |")
    r30 = band["R30"]
    diag = r30["diagnostic_stored_dam_rate"]
    lines += [
        "",
        "Band width (pooled TEST band, R30): " + ", ".join(
            f"p = {p0} reads {lo:.3f}-{hi:.3f}" for p0, (lo, hi) in r30["examples_pooled"].items()) + ".",
        "",
        "### Nearest pre-event references (not the same model, so no tolerance)",
        "",
        "| kind | Tidemark v1 90-day anchor, 2002-2009 inner band | its VAL coverage | its LOYO (VAL only) | "
        "G2 + Platt, LOYO in VAL |",
        "|---|---|---|---|---|",
    ]
    for kind in BAND_KINDS:
        ref = BAND_REFERENCES[kind]
        ref_band = band_text(ref["tidemark_anchor_band"]) if ref["tidemark_anchor_band"] else "not run"
        lines.append(f"| {kind} | {ref_band} | {ref['tidemark_anchor_covered']} | {ref['tidemark_anchor_loyo']} | "
                     f"{ref['g2_platt_loyo']} |")
    lines += [
        "",
        "### Diagnostics",
        "",
        f"- **Causal dam_rate in the 2002 inner fit (R30).** With the stored dam_rate (its prior counts answers up to "
        f"2008, as the pre-event research used it), the 2002-2009 band is {band_text(diag['band'])} and covers "
        f"{diag['coverage_val']['covered']}/{diag['coverage_val']['region_years']} VAL region-years; with the prior "
        f"recomputed as of 2002 it is {band_text(r30['band_val_setting'])}. Median change in dam_rate on the inner "
        f"rows: {r30['dam_rate_as_of_2002_vs_stored_median_abs_diff']:.4f}.",
        f"- **dam_rate_as_of reproduces the stored feature** at 2009-01-01 to within "
        f"{r30['dam_rate_as_of_2009_vs_stored_max_abs_diff']:.4f} (the stored prior also counts the 1986-87 warm-up "
        "looks, which are not issues).",
        "- **The 2009 refit is the official G2.** Largest difference from the step-3 VAL predictions: " + ", ".join(
            f"{k} {band[k]['refit_vs_official_max_abs_diff']:.2e}" for k in BAND_KINDS)
        + " (LightGBM thread count 3 here, 4 in step 3).",
        "",
        "## Notes",
        "",
        "- **No probability is changed.** The floor and the band are shown next to the forecast.",
        "- **Time rules.** Floor fit rows: issue + 395 days before 2009-01-01. Frozen floor shift: VAL forecasts "
        "whose 395 days closed before 2016-07-01 (the pre-event research used every VAL forecast, some answered "
        "after TEST began). Band blocks: every answer final before the block's cutoff; the 2002 inner fit learns "
        "only from answers final before 2002-01-01 and its dam_rate prior is recomputed from them.",
        "- **The VAL band check uses only the 2002-2009 block.** The PREREG band pools 2002-2009 and 2009-2016 for "
        "TEST and the sealed region; on VAL the 2009-2016 block is the VAL period itself, so the pooled band can only "
        "be checked leave-one-year-out.",
        "- **G2 is a stand-in.** The band constants for the frozen model must be recomputed from Tidemark's own inner "
        "predictions with the same functions (`uncertainty.band_rows`, `block_offsets`, `pooled_band`).",
        "- Floors are saved in `data_cache/preds/VAL/P1_R30/floor_LB90.pkl` (`floor_loyo` continuous, `floor_shown` "
        "as displayed, 180 meaning 180+).",
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")
    summary = dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), block=BLOCK, floor=floor, floor_checks=checks,
                   band=band, band_references=BAND_REFERENCES)
    RESULTS_JSON.write_text(json.dumps(clean_for_json(summary), indent=1), encoding="utf-8")


# ===========================================================================
# Main
# ===========================================================================
def main():
    """Floor and band on VAL, then the report."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="no bootstrap intervals")
    args = parser.parse_args()
    n_boot = 0 if args.quick else N_BOOT

    log("loading the P1 table (keys, dam history, neighbours)")
    table = store.load_p1(groups=("keys", "dam", "nbr"))
    for kind in BAND_KINDS:   # the arbitrary-cutoff fit rows must equal step 3's purged VAL fit rows
        if not np.array_equal(unc.answered_fit_rows(table, kind, config.VAL_START),
                              rows.p1_fit_rows(table, kind, BLOCK)):
            raise AssertionError(f"answered_fit_rows at 2009-01-01 differs from rows.p1_fit_rows for {kind}")

    floor, frame = floor_results(table, n_boot)
    save_floors(frame)
    band = {kind: band_for_kind(table, kind) for kind in BAND_KINDS}

    checks = floor_check_rows(floor)
    write_report(floor, checks, band)
    log(f"wrote {RESULTS_MD.name} and {RESULTS_JSON.name}")
    for c in checks:
        print(f"  floor {c['check']:<45s} expected {c['expected']:.4f} got {c['got']:.4f} "
              f"diff {c['difference']:+.4f} {'ok' if c['within'] else 'OUTSIDE'}")
    for kind in BAND_KINDS:
        b = band[kind]
        print(f"  band {kind}: VAL setting {band_text(b['band_val_setting'])} covers "
              f"{b['coverage_val_forward']['covered']}/{b['coverage_val_forward']['region_years']}; "
              f"pooled TEST band {band_text(b['band_test_setting_pooled'])}")


if __name__ == "__main__":
    main()
