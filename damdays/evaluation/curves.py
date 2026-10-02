"""Scoring the runway curve: the chance of an event within 30, 60, 90 and 180 days.

A runway curve is cumulative: the chance of falling below a third within 60
days can never be smaller than within 30 days. So, besides scoring each
horizon, we count how often a curve breaks that rule ("falls").

Each horizon is judged against its own baseline: B0_h is the base rate of an
event within h days, so the 30-day forecast is not flattered by comparing it
with a 90-day base rate.

curve_df has one row per forecast, and for every horizon h in (30, 60, 90, 180):
    p_<h>     the curve's probability of an event within h days
    y_<h>     1 / 0, or blank if the answer at h days is not known yet
              (for example the issue is less than h days before the data ends)
    p_B0_<h>  the horizon's base-rate baseline
    p_B2_<h>  optional: the dam's own past rate at that horizon
plus uid, issue_date, region and any subset flags.

On TEST the curve goes through the same ledger as score(): one look per model.
"""
import time

import numpy as np

from damdays import config
from damdays.evaluation import report, rules
from damdays.evaluation.inputs import KEY, prepare_table
from damdays.evaluation.ledger import Ledger, model_key, prediction_hash
from damdays.evaluation.scorecard import DEFAULT_N_BOOT, RowScorer, intervals, now_text, warm_start

HORIZONS = (30, 60, 90, 180)


def monotonicity_violations(curves, tolerance=1e-12):
    """How often a cumulative curve goes down as the horizon gets longer.

    curves: one row per forecast, one column per horizon (shortest first).
    Returns the share of rows where the curve falls anywhere, and the largest fall.
    """
    curves = np.asarray(curves, dtype=float)
    falls = curves[:, :-1] - curves[:, 1:]            # positive = the curve went down
    falling_rows = (falls > tolerance).any(axis=1)
    return dict(rows=int(len(curves)), rows_falling=int(falling_rows.sum()),
                share_rows_falling=float(falling_rows.mean()) if len(curves) else np.nan,
                largest_fall=float(max(falls.max(), 0.0)) if falls.size else 0.0)


def crossing_share(curve_upper, curve_lower, tolerance=1e-12):
    """Share of rows where `curve_upper` dips below `curve_lower` at any horizon.

    Used for the "max rule": a dam that is fully dry is also below a third, so
    the R30 curve must never be below the D0 curve. Expected after the rule: 0.
    """
    upper = np.asarray(curve_upper, dtype=float)
    lower = np.asarray(curve_lower, dtype=float)
    if upper.ndim == 1:                     # a single horizon: one value per row
        upper, lower = upper[:, None], lower[:, None]
    crossed = ((lower - upper) > tolerance).any(axis=1)
    return float(crossed.mean()) if len(crossed) else np.nan


def horizon_columns(horizons, with_b2):
    """Names of the probability and label columns for these horizons."""
    probabilities = [f"p_{h}" for h in horizons] + [f"p_B0_{h}" for h in horizons]
    if with_b2:
        probabilities += [f"p_B2_{h}" for h in horizons]
    return probabilities, [f"y_{h}" for h in horizons]


def score_one_horizon(rows, h, with_b2, n_boot, seed):
    """Every scorecard number for one horizon, on the rows whose answer at h days is known."""
    known = rows[rows[f"y_{h}"].notna()].reset_index(drop=True)
    events = int(known[f"y_{h}"].sum())
    out = dict(horizon=h, rows=len(known), events=events,
               rows_without_label=int(len(rows) - len(known)))
    if events == 0 or events == len(known):
        return dict(out, point={}, ci_dam={}, ci_region_year={}, note="needs both events and non-events")
    baselines = {"B0": known[f"p_B0_{h}"]}
    if with_b2:
        baselines["B2"] = known[f"p_B2_{h}"]
    scorer = RowScorer(known[f"y_{h}"], known[f"p_{h}"], baselines)
    point = scorer.metrics()
    warm_start(scorer, point)
    ci_dam, ci_ry, boot_info = intervals(scorer, known["uid"].to_numpy(),
                                         rules.region_year(known["region"], known["issue_date"]), n_boot, seed)
    return dict(out, point=point, ci_dam=ci_dam, ci_region_year=ci_ry, bootstrap=boot_info)


def score_curve(curve_df, task, subset="primary", *, model, horizons=HORIZONS, baselines=None,
                n_boot=DEFAULT_N_BOOT, seed=config.RANDOM_SEED, note="", out_dir=None, ledger=None,
                dry_run=False, write=True):
    """Score a runway curve at each horizon; returns the result as a dict.

    The arguments mean the same as for score(). The result holds one entry per
    horizon (with BSS against that horizon's own baselines), a short summary
    `bss_B0_by_horizon`, and the monotonicity check.
    """
    started = time.time()
    rules.check_task(task)
    if rules.task_kind(task) != "curve":
        raise ValueError(f"{task} is not a runway-curve task: use score().")
    model = model_key(model)
    horizons = tuple(int(h) for h in horizons)
    if list(horizons) != sorted(set(horizons)):
        raise ValueError("horizons must be distinct and in increasing order")
    parts = rules.parse_subset(subset, task)
    subset_label = rules.subset_name(parts)

    with_b2 = all(f"p_B2_{h}" in curve_df.columns for h in horizons) or (
        baselines is not None and all(f"p_B2_{h}" in baselines.columns for h in horizons))
    probability_columns, label_columns = horizon_columns(horizons, with_b2)
    table = prepare_table(curve_df, required=[], probability_columns=probability_columns,
                          label_columns=label_columns, flag_columns=rules.flag_columns_needed(parts),
                          baselines=baselines)
    block = rules.block_of(table["issue_date"])
    arena = rules.arena_of(table["region"])
    rows = table[rules.subset_mask(table, parts)].reset_index(drop=True)
    if len(rows) == 0:
        raise ValueError(f"Subset {subset_label!r} has no rows.")

    curve_columns = [f"p_{h}" for h in horizons]
    pred_hash = prediction_hash(table, curve_columns)
    ledger_status = None
    if block == "TEST":
        ledger = ledger if ledger is not None else Ledger()
        ledger_status = ledger.admit(model=model, task=task, arena=arena, preds=table[KEY + curve_columns],
                                     subset=subset_label, note=note, dry_run=dry_run,
                                     baseline_hash=prediction_hash(table, [f"p_B0_{h}" for h in horizons]))
    summary = dict(model=model, task=task, task_description=rules.TASKS[task], block=block, arena=arena,
                   subset=subset_label, rows_passed_in=len(table), rows_in_subset=len(rows),
                   pred_hash=pred_hash, test_ledger=ledger_status, note=note)
    if dry_run:
        return dict(summary, dry_run=True, time=now_text())

    per_horizon = [score_one_horizon(rows, h, with_b2, n_boot, seed) for h in horizons]
    result = dict(summary, horizons=per_horizon,
                  bss_B0_by_horizon={h["horizon"]: h["point"].get("bss_B0") for h in per_horizon},
                  monotonicity=monotonicity_violations(rows[curve_columns].to_numpy()),
                  time=now_text(), seconds=round(time.time() - started, 1))
    if write or block == "TEST":
        result["json_path"] = str(report.write_json(result, out_dir, kind="curve"))
        report.append_markdown(result, out_dir, report.CURVE_HEADER, report.curve_rows(result), "curves")
    return result
