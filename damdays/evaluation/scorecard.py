"""score(): the one function every forecast is judged by.

    from damdays.evaluation import score
    result = score(pred_df, "P1_R30", "primary", model="tidemark", refs=["G2"])

pred_df has one row per forecast:
    uid, issue_date, region   which dam (or 2 km cell), when, and where
    y                         what happened: 1 event, 0 no event, blank = not known (dropped, counted)
    p                         the model's probability of the event
    p_B0, p_B2                the two baselines (or pass `baselines=` to join them on uid + issue_date)
    dam_like, persistent, at_risk   yes/no columns, needed only if the subset uses them
    p_<name>                  for each reference model named in `refs`, e.g. p_G2

What happens, in order:
 1. The table is checked (inputs.py). The time block (VAL or TEST) and the
    arena (dev or sealed) are read from the rows themselves (rules.py).
 2. TEST only: the ledger is asked (ledger.py). A second look at TEST with
    different predictions stops here, before any number is computed.
 3. The subset of rows is selected and every number is computed (metrics.py).
 4. The numbers are recomputed on resampled dams and on resampled
    region-years, for 95% intervals (bootstrap.py).
 5. A JSON file and a markdown row are written (report.py). TEST results are
    always written; VAL can opt out with write=False.

docs/SCORECARD.md explains every number in plain language.
"""
import time
from datetime import datetime

import numpy as np

from damdays import config
from damdays.data.splits import hydro_year
from damdays.evaluation import report, rules
from damdays.evaluation.bootstrap import cluster_bootstrap
from damdays.evaluation.inputs import KEY, check_expected_keys, prepare_table
from damdays.evaluation.ledger import Ledger, model_key, prediction_hash
from damdays.evaluation.metrics import (Ranking, fit_calibration_line, fit_calibration_shift, logit,
                                        row_weights, safe_ratio)

DEFAULT_N_BOOT = 500
BASELINES = ("B0", "B2")   # B0: month x region base rate; B2: the dam's own past event rate (PREREG)

# Pre-registered P1 pass bars (PREREG.md), for R30 on the primary subset.
P1_BARS = dict(bss_B0_min=0.10, bss_B2_min=0.05, slope_low=0.8, slope_high=1.2)


# ---------------------------------------------------------------------------
# All the numbers, for any row weights
# ---------------------------------------------------------------------------
class RowScorer:
    """Every scorecard number for one fixed set of rows, for any row weights.

    Built once per scoring call. The bootstrap then calls metrics(w) hundreds
    of times, so everything that does not depend on the weights (sorting for
    AUC, squared errors, log-odds) is worked out here, once. The answers are
    exact, not approximations.
    """

    def __init__(self, y, p, baselines, refs=None, groups=None):
        """y, p: arrays. baselines and refs: {name: probabilities}. groups: {name: labels} for within-group AUC."""
        self.y = np.asarray(y, dtype=float)
        self.p = np.asarray(p, dtype=float)
        self.log_odds = logit(self.p)
        self.baseline_names = list(baselines)
        self.ref_names = list(refs or {})
        # Squared error of every forecast on every row: a weighted Brier score is then one dot product.
        forecasts = {"model": self.p, **baselines, **(refs or {})}
        self.squared_error = {name: (np.asarray(f, dtype=float) - self.y) ** 2 for name, f in forecasts.items()}
        self.ranking = Ranking(self.p)
        self.ref_rankings = {name: Ranking(refs[name]) for name in self.ref_names}
        self.group_rankings = {name: Ranking(self.p, g) for name, g in (groups or {}).items()}
        self.calibration_start = (0.0, 1.0)   # the bootstrap starts from the point estimate instead

    def metrics(self, w=None):
        """Every number for these rows weighted by w; None if there are no events or no non-events."""
        y = self.y
        w = row_weights(len(y), w)
        total, events = w.sum(), w @ y
        if events <= 0 or events >= total:
            return None
        brier = {name: (w @ err) / total for name, err in self.squared_error.items()}
        out = dict(base_rate=events / total, mean_p=(w @ self.p) / total, brier=brier["model"])
        for name in self.baseline_names:
            out[f"bss_{name}"] = 1 - safe_ratio(brier["model"], brier[name])

        counts = self.ranking.event_counts(y, w)
        out["auc"] = self.ranking.auc(y, w, counts=counts)
        out["prec_at_50_recall"] = self.ranking.precision_at_recall(y, w, recall=0.5, counts=counts)
        for name, ranking in self.group_rankings.items():
            out[f"auc_within_{name}"] = ranking.auc(y, w)

        # Calibration fits only need rows with weight (a resample leaves about a third out).
        used = w > 0
        y_used, x_used, w_used = y[used], self.log_odds[used], w[used]
        out["cal_intercept"], out["cal_slope"] = (
            fit_calibration_line(y_used, x_used, w_used, self.calibration_start)
            if np.ptp(x_used) > 0 else (np.nan, np.nan))     # one forecast for every row: no slope
        out["citl"] = fit_calibration_shift(y_used, x_used, w_used)

        for name in self.ref_names:
            out[f"bss_vs_{name}"] = 1 - safe_ratio(brier["model"], brier[name])
            if "B0" in brier:
                # Paired gain in "BSS vs B0" units: BSS_B0(model) - BSS_B0(ref).
                # Both are computed on the same rows and the same resample, so
                # shared luck (an easy year, an easy dam) cancels out.
                out[f"d_bss_B0_vs_{name}"] = safe_ratio(brier[name] - brier["model"], brier["B0"])
            out[f"d_auc_vs_{name}"] = out["auc"] - self.ref_rankings[name].auc(y, w)
        return out


def intervals(scorer, uids, region_years, n_boot, seed):
    """Dam-bootstrap and region-year-bootstrap 95% intervals, with fixed seeds (seed, seed + 1)."""
    if n_boot <= 0:
        return {}, {}, {}
    ci_dam, info_dam = cluster_bootstrap(scorer.metrics, uids, n_boot, seed)
    ci_ry, info_ry = cluster_bootstrap(scorer.metrics, region_years, n_boot, seed + 1)
    return ci_dam, ci_ry, dict(dam=info_dam, region_year=info_ry)


def warm_start(scorer, point):
    """Start the bootstrap's calibration fits from the point estimate (same answer, faster)."""
    if np.isfinite(point["cal_intercept"]) and np.isfinite(point["cal_slope"]):
        scorer.calibration_start = (point["cal_intercept"], point["cal_slope"])


def now_text():
    """Current local time, e.g. "2026-10-02 17:45:03"."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def p2_groups(task, rows):
    """Within-group AUCs for season ratings: within each season, and within each dam (or cell)."""
    unit = "cell" if task == "P2_cell" else "dam"
    return {"season": hydro_year(rows["issue_date"]), unit: rows["uid"].to_numpy()}


# ---------------------------------------------------------------------------
# score()
# ---------------------------------------------------------------------------
def score(pred_df, task, subset="primary", *, model, refs=(), baselines=None, expected_keys=None,
          n_boot=DEFAULT_N_BOOT, seed=config.RANDOM_SEED, note="", out_dir=None, ledger=None,
          dry_run=False, write=True):
    """Score one model's probabilities on one task and subset; returns the result as a dict.

    model         the model family's name; on TEST this is the ledger key
    refs          reference models for paired differences, e.g. ["G2"] (needs column p_G2)
    baselines     optional table (uid, issue_date, p_B0, p_B2, ...) joined onto pred_df
    expected_keys optional table of the exact (uid, issue_date) rows that must be scored
    n_boot        bootstrap replicates for each of the two interval types (0 = no intervals)
    dry_run       run every check (and on TEST, the ledger check) but compute no numbers
    """
    started = time.time()
    rules.check_task(task)
    if rules.task_kind(task) == "curve":
        raise ValueError(f"{task} is a runway-curve task: use score_curve().")
    model = model_key(model)
    ref_names = [str(r).strip() for r in refs]
    parts = rules.parse_subset(subset, task)
    subset_label = rules.subset_name(parts)

    # 1. Check the table; read the block and arena from the rows.
    baseline_columns = [f"p_{b}" for b in BASELINES]
    table = prepare_table(pred_df, required=["p"], label_columns=["y"],
                          probability_columns=["p", *baseline_columns, *[f"p_{r}" for r in ref_names]],
                          flag_columns=rules.flag_columns_needed(parts), baselines=baselines)
    block = rules.block_of(table["issue_date"])
    arena = rules.arena_of(table["region"])
    in_subset = rules.subset_mask(table, parts)
    labelled = table["y"].notna().to_numpy()
    rows = table[in_subset & labelled].reset_index(drop=True)
    if expected_keys is not None:
        check_expected_keys(rows, expected_keys)
    if len(rows) == 0 or rows["y"].sum() == 0 or rows["y"].sum() == len(rows):
        raise ValueError(f"Subset {subset_label!r} has {len(rows)} labelled rows and "
                         f"{int(rows['y'].sum())} events; it needs both events and non-events.")

    # 2. TEST only: the ledger decides, before any number is computed.
    pred_hash = prediction_hash(table, ["p"])
    baseline_hash = prediction_hash(table, baseline_columns)
    ledger_status = None
    if block == "TEST":
        ledger = ledger if ledger is not None else Ledger()
        ref_preds = {model_key(r): table[KEY + [f"p_{r}"]].rename(columns={f"p_{r}": "p"}) for r in ref_names}
        ledger_status = ledger.admit(model=model, task=task, arena=arena, preds=table[KEY + ["p"]],
                                     refs=ref_preds, subset=subset_label, baseline_hash=baseline_hash,
                                     note=note, dry_run=dry_run)

    summary = dict(
        model=model, task=task, task_description=rules.TASKS[task], block=block, arena=arena,
        subset=subset_label, subset_rules={part: rules.SUBSET_PARTS[part] for part in parts},
        rows=dict(passed_in=len(table), in_subset=int(in_subset.sum()),
                  in_subset_without_label=int((in_subset & ~labelled).sum()), scored=len(rows),
                  events=int(rows["y"].sum()), dams=int(rows["uid"].nunique()),
                  dams_with_event=int(rows.loc[rows["y"] == 1, "uid"].nunique()),
                  region_years=int(len(set(rules.region_year(rows["region"], rows["issue_date"]))))),
        refs=ref_names, baselines=list(BASELINES), pred_hash=pred_hash, baseline_hash=baseline_hash,
        test_ledger=ledger_status, row_set_checked=expected_keys is not None, note=note)
    if dry_run:
        return dict(summary, dry_run=True, time=now_text())

    # 3. The numbers on the chosen rows.
    groups = p2_groups(task, rows) if rules.task_kind(task) == "p2" else None
    scorer = RowScorer(rows["y"], rows["p"], {b: rows[f"p_{b}"] for b in BASELINES},
                       refs={r: rows[f"p_{r}"] for r in ref_names}, groups=groups)
    point = scorer.metrics()

    # 4. 95% intervals: resample dams, then resample region-years.
    warm_start(scorer, point)
    ci_dam, ci_ry, boot_info = intervals(scorer, rows["uid"].to_numpy(),
                                         rules.region_year(rows["region"], rows["issue_date"]), n_boot, seed)

    result = dict(summary, point=point, ci_dam=ci_dam, ci_region_year=ci_ry,
                  bootstrap=dict(boot_info, n_boot=n_boot, ci_level=0.95), time=now_text(),
                  seconds=round(time.time() - started, 1))
    if task == "P1_R30" and parts == rules.SUBSET_ALIASES["primary"]:
        result["prereg_pass_bars"] = p1_pass_bars(result)

    # 5. Save. TEST results are always saved, so a TEST score cannot go unrecorded.
    if write or block == "TEST":
        result["json_path"] = str(report.write_json(result, out_dir))
        report.append_markdown(result, out_dir, report.SCORE_HEADER, report.score_row(result), "scorecard")
    return result


def p1_pass_bars(result):
    """The pre-registered P1 pass bars (PREREG.md), checked mechanically on a score() result.

    They are defined for R30 on the primary subset (dam-like dams, Oct-Mar issues, at risk):
      BSS vs B0 at least +0.10, with its 95% dam-bootstrap interval above 0
      BSS vs B2 at least +0.05
      calibration slope between 0.8 and 1.2
    """
    point, ci = result["point"], result["ci_dam"]
    bss_b0, b0_low = point["bss_B0"], ci.get("bss_B0", [np.nan])[0]
    bars = dict(
        bss_B0=dict(value=bss_b0, ci_low=b0_low, bar=">= +0.10 and dam CI above 0",
                    passed=bool(bss_b0 >= P1_BARS["bss_B0_min"] and b0_low > 0)),
        bss_B2=dict(value=point["bss_B2"], bar=">= +0.05", passed=bool(point["bss_B2"] >= P1_BARS["bss_B2_min"])),
        cal_slope=dict(value=point["cal_slope"], bar="0.8 to 1.2",
                       passed=bool(P1_BARS["slope_low"] <= point["cal_slope"] <= P1_BARS["slope_high"])),
    )
    bars["all_passed"] = all(bar["passed"] for bar in bars.values())
    return bars
