"""The DamDays scorecard: one shared way to judge every forecast.

Every model (Tidemark, the G2 benchmark, the baselines) is scored by the same
code, on the same rows, with the same numbers. docs/SCORECARD.md explains each
number in plain language. The scorecard does not depend on how forecasts are
made: it only needs a table of forecasts and outcomes.

Main entry points
    score(pred_df, task, subset, model=...)         one probability per row (P1, P2)
    score_curve(curve_df, task, subset, model=...)  runway curves at 30/60/90/180 days
    region_year_offsets, band_from_offsets, band_coverage   season-band coverage
    floor_coverage                                  "at least N days" floor coverage
    p1_pass_bars(result)                            the pre-registered P1 pass bars

TEST is protected by a ledger (artifacts/test_ledger.csv): each model is scored
on TEST once. See ledger.py.

Modules, in the order a scoring call uses them
    rules.py      tasks, time blocks, arenas (dev / sealed) and row subsets
    inputs.py     checks and joins on the prediction table
    ledger.py     the TEST ledger
    metrics.py    the numbers (Brier skill, AUC, calibration, precision)
    bootstrap.py  95% intervals by resampling dams or region-years
    report.py     JSON and markdown output
    scorecard.py  score(): puts the pieces together
    curves.py     score_curve() and the monotonicity check
    coverage.py   band and floor coverage
"""
from damdays.evaluation.coverage import band_coverage, band_from_offsets, floor_coverage, region_year_offsets
from damdays.evaluation.curves import HORIZONS, crossing_share, monotonicity_violations, score_curve
from damdays.evaluation.ledger import Ledger, LedgerError, prediction_hash
from damdays.evaluation.scorecard import p1_pass_bars, score

__all__ = [
    "score", "score_curve", "p1_pass_bars", "HORIZONS", "monotonicity_violations", "crossing_share",
    "region_year_offsets", "band_from_offsets", "band_coverage", "floor_coverage",
    "Ledger", "LedgerError", "prediction_hash",
]
