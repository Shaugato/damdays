"""Made-up forecasting worlds where the right scores are known, for testing the scorecard.

In real data nobody knows a dam's true chance of running dry. Here we make it
up: every row gets a true probability q, the outcome y is drawn from q, and the
forecasts are built from q. Because q is known, so are the "true" scores.

For any forecast f that does not peek at the outcome, the expected Brier score is
    mean of (f - q)^2 + q (1 - q)
so the true Brier skill score can be worked out without any sampling noise.
The true AUC is the chance that an event row outranks a non-event row, with
every row counting as an event with weight q and a non-event with weight 1 - q.
"""
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from damdays.data.splits import hydro_year
from damdays.evaluation import ledger as ledger_module
from damdays.evaluation import report as report_module
from damdays.evaluation.metrics import logit, sigmoid


@pytest.fixture(autouse=True)
def isolated_artifacts(tmp_path, monkeypatch):
    """Point the default TEST ledger and results folder at a temporary folder.

    Imported (and so switched on) by every scorecard test module, so no test can
    ever write to the real artifacts/test_ledger.csv.
    """
    monkeypatch.setattr(ledger_module, "LEDGER_PATH", tmp_path / "test_ledger.csv")
    monkeypatch.setattr(report_module, "OUT_DIR", tmp_path / "scorecard")
    return tmp_path

BLOCK_DATES = {"VAL": ("2009-01-01", "2015-12-31"), "TEST": ("2016-07-01", "2026-06-30")}
DEV_REGIONS = ("nsw_cw", "wvic_sesa")
INTERCEPT = -1.5        # sets the event rate at roughly 25%


def make_world(n_dams=1500, looks_per_dam=40, block="TEST", year_shock_sd=0.4, seed=0,
               regions=DEV_REGIONS):
    """A table of made-up forecasts with known true probabilities.

    True log-odds of an event = INTERCEPT + dam effect + region-year shock + issue noise.
    Columns: uid, issue_date, region, y, q (truth), p (= q, a perfect forecast),
    p_no_year (knows everything except the year's weather), p_B0 (region base
    rate), p_B2 (knows only the dam), dam_like, persistent, at_risk.
    """
    rng = np.random.default_rng(seed)
    start, end = (pd.Timestamp(d) for d in BLOCK_DATES[block])
    span_days = (end - start).days + 1
    dam_effect = rng.normal(0, 0.8, n_dams)
    dam_like = rng.random(n_dams) < 0.5
    persistent = rng.random(n_dams) < 0.3

    dam = np.repeat(np.arange(n_dams), looks_per_dam)
    day = np.concatenate([rng.choice(span_days, looks_per_dam, replace=False) for _ in range(n_dams)])
    issue_date = start + pd.to_timedelta(day, unit="D")
    region = np.array(regions)[dam % len(regions)]
    region_year = pd.Series(region).str.cat(hydro_year(issue_date).astype(str), sep=":")
    shocks = {ry: rng.normal(0, year_shock_sd) for ry in sorted(region_year.unique())}
    year_shock = region_year.map(shocks).to_numpy()

    noise = rng.normal(0, 1, len(dam))
    q = sigmoid(INTERCEPT + dam_effect[dam] + year_shock + noise)
    world = pd.DataFrame(dict(
        uid=[f"d{i:05d}" for i in dam], issue_date=issue_date, region=region,
        y=(rng.random(len(dam)) < q).astype(float), q=q, p=q,
        p_no_year=sigmoid(INTERCEPT + dam_effect[dam] + noise),
        p_B2=sigmoid(INTERCEPT + dam_effect[dam]),
        dam_like=dam_like[dam], persistent=persistent[dam], at_risk=rng.random(len(dam)) < 0.85))
    world["p_B0"] = world.groupby("region")["q"].transform("mean")
    return world


def expected_brier(f, q):
    """Expected Brier score of forecast f when the true probabilities are q."""
    f, q = np.asarray(f, dtype=float), np.asarray(q, dtype=float)
    return float(np.mean((f - q) ** 2 + q * (1 - q)))


def true_bss(f, f_ref, q):
    """Brier skill score of f against f_ref, as it would be with endless data."""
    return 1 - expected_brier(f, q) / expected_brier(f_ref, q)


def true_auc(f, q):
    """AUC of f with endless data: each row is an event with weight q and a non-event with weight 1 - q."""
    f, q = np.asarray(f, dtype=float), np.asarray(q, dtype=float)
    labels = np.r_[np.ones(len(f)), np.zeros(len(f))]
    return float(roc_auc_score(labels, np.r_[f, f], sample_weight=np.r_[q, 1 - q]))


def overconfident(q, factor=2.0):
    """A forecast that stretches the true log-odds by `factor` (true calibration slope = 1 / factor)."""
    return sigmoid(factor * logit(q))


def shifted(q, shift):
    """A forecast whose log-odds are `shift` too high (true CITL = -shift)."""
    return sigmoid(logit(q) + shift)
