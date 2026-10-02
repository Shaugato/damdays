"""Tests for the scorecard's metric functions: hand-worked examples and cross-checks.

Each number is checked against a small example worked out by hand, against
scikit-learn, or against a synthetic world where the right answer is known.
"""
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from damdays.evaluation import metrics as M
from eval_synthetic import overconfident, shifted


# ---------------------------------------------------------------------------
# Brier score and Brier skill
# ---------------------------------------------------------------------------
def test_brier_and_skill_by_hand():
    """Squared gaps 0.04, 0.04, 0.16, 0.16 average 0.1; a 50/50 forecast scores 0.25; skill = 1 - 0.1/0.25."""
    y = np.array([1, 0, 1, 0.0])
    p = np.array([0.8, 0.2, 0.6, 0.4])
    assert M.brier(y, p) == pytest.approx(0.10)
    assert M.brier(y, np.full(4, 0.5)) == pytest.approx(0.25)
    assert M.brier_skill(y, p, np.full(4, 0.5)) == pytest.approx(0.60)
    assert M.brier_skill(y, p, p) == pytest.approx(0.0)        # same as the reference: no skill


def test_brier_skill_is_nan_when_reference_is_perfect():
    """Skill against a perfect reference is undefined (dividing by zero), not a crash."""
    y = np.array([1, 0.0])
    assert np.isnan(M.brier_skill(y, np.array([0.5, 0.5]), y))


# ---------------------------------------------------------------------------
# AUC
# ---------------------------------------------------------------------------
def test_auc_by_hand():
    """Events at 0.35 and 0.8; non-events at 0.1 and 0.4. 3 of the 4 pairs are the right way round."""
    assert M.auc(np.array([0, 0, 1, 1.0]), np.array([0.1, 0.4, 0.35, 0.8])) == pytest.approx(0.75)


def test_auc_counts_ties_as_half():
    """One event and one non-event with the same forecast: a coin flip, 0.5."""
    assert M.auc(np.array([0, 1.0]), np.array([0.3, 0.3])) == pytest.approx(0.5)


def test_auc_matches_sklearn_with_ties_and_weights():
    """Random forecasts with many ties and random weights: same answer as scikit-learn."""
    rng = np.random.default_rng(1)
    p = np.round(rng.random(5000), 2)                    # rounding creates ties
    y = (rng.random(5000) < p).astype(float)
    w = rng.integers(0, 4, 5000).astype(float)           # includes zero weights, like the bootstrap
    assert M.auc(y, p) == pytest.approx(roc_auc_score(y, p), abs=1e-12)
    assert M.auc(y, p, w) == pytest.approx(roc_auc_score(y, p, sample_weight=w), abs=1e-12)


def test_within_group_auc_pools_pairs_inside_groups():
    """Within-group AUC = each group's AUC weighted by its number of (event, non-event) pairs."""
    rng = np.random.default_rng(2)
    groups = rng.integers(0, 7, 3000)
    p = rng.random(3000) + 0.3 * groups                  # groups differ a lot in level
    y = (rng.random(3000) < 0.3).astype(float)
    num = den = 0.0
    for g in np.unique(groups):
        m = groups == g
        pairs = y[m].sum() * (1 - y[m]).sum()
        num += roc_auc_score(y[m], p[m]) * pairs
        den += pairs
    assert M.within_group_auc(y, p, groups) == pytest.approx(num / den, abs=1e-12)


# ---------------------------------------------------------------------------
# Precision at 50% recall
# ---------------------------------------------------------------------------
def test_precision_at_half_recall_by_hand():
    """4 events; half = 2. Flag 0.9 (event), 0.8 (no), 0.7 (event): 2 caught out of 3 flagged."""
    y = np.array([1, 0, 1, 0, 1, 1.0])
    p = np.array([0.9, 0.8, 0.7, 0.6, 0.5, 0.4])
    assert M.precision_at_recall(y, p) == pytest.approx(2 / 3)


def test_precision_flags_whole_tie_blocks():
    """3 events; need 1.5. After 0.9 (1 caught) the whole 0.7 tie block is flagged: 2 caught of 3."""
    y = np.array([1, 0, 1, 1.0])
    p = np.array([0.9, 0.7, 0.7, 0.1])
    assert M.precision_at_recall(y, p) == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# Weights behave like repeated rows (this is what the bootstrap relies on)
# ---------------------------------------------------------------------------
def test_weight_two_equals_a_duplicated_row():
    """Giving rows weight 2 (or 0) gives exactly the numbers of copying (or dropping) them."""
    rng = np.random.default_rng(3)
    p = rng.random(400)
    y = (rng.random(400) < p).astype(float)
    w = rng.integers(0, 3, 400).astype(float)
    copies = np.repeat(np.arange(400), w.astype(int))
    y2, p2 = y[copies], p[copies]
    assert M.brier(y, p, w) == pytest.approx(M.brier(y2, p2), abs=1e-12)
    assert M.auc(y, p, w) == pytest.approx(M.auc(y2, p2), abs=1e-12)
    assert M.precision_at_recall(y, p, w) == pytest.approx(M.precision_at_recall(y2, p2), abs=1e-12)
    assert M.calibration_fit(y, p, w) == pytest.approx(M.calibration_fit(y2, p2), abs=1e-8)
    assert M.calibration_in_the_large(y, p, w) == pytest.approx(M.calibration_in_the_large(y2, p2), abs=1e-8)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def truth():
    """200,000 rows with known true probabilities q, and outcomes drawn from them."""
    rng = np.random.default_rng(4)
    q = M.sigmoid(rng.normal(-1.2, 1.2, 200_000))
    y = (rng.random(len(q)) < q).astype(float)
    return q, y


def test_calibrated_forecast_has_slope_one_and_no_shift(truth):
    """Forecasting the true probability: slope 1, intercept 0, CITL 0 (up to sampling noise)."""
    q, y = truth
    a, b = M.calibration_fit(y, q)
    assert b == pytest.approx(1.0, abs=0.03), f"expected slope 1.00, got {b:.3f}"
    assert a == pytest.approx(0.0, abs=0.03), f"expected intercept 0.00, got {a:.3f}"
    assert M.calibration_in_the_large(y, q) == pytest.approx(0.0, abs=0.03)


def test_overconfident_forecast_has_slope_one_half(truth):
    """Log-odds stretched x2 (too extreme): the true slope is exactly 0.5."""
    q, y = truth
    a, b = M.calibration_fit(y, overconfident(q, 2.0))
    assert b == pytest.approx(0.5, abs=0.02), f"expected slope 0.50, got {b:.3f}"
    assert a == pytest.approx(0.0, abs=0.03)


def test_forecast_too_high_has_negative_citl(truth):
    """Log-odds 0.5 too high: CITL (the shift that fixes it) is -0.5, the slope stays 1."""
    q, y = truth
    p = shifted(q, 0.5)
    citl = M.calibration_in_the_large(y, p)
    assert citl == pytest.approx(-0.5, abs=0.03), f"expected CITL -0.50, got {citl:.3f}"
    assert M.calibration_fit(y, p)[1] == pytest.approx(1.0, abs=0.03)


def test_calibration_fit_matches_sklearn():
    """The Newton fit agrees with scikit-learn's unpenalised logistic regression on the log-odds."""
    rng = np.random.default_rng(5)
    p = M.sigmoid(rng.normal(-1, 1, 20_000))
    y = (rng.random(len(p)) < M.sigmoid(0.3 + 0.8 * M.logit(p))).astype(float)
    a, b = M.calibration_fit(y, p)
    model = LogisticRegression(C=np.inf, tol=1e-10, max_iter=1000).fit(M.logit(p)[:, None], y)   # no penalty
    assert a == pytest.approx(model.intercept_[0], abs=1e-4)
    assert b == pytest.approx(model.coef_[0, 0], abs=1e-4)


def test_calibration_is_nan_when_impossible():
    """No slope for a constant forecast; no CITL without both events and non-events."""
    y = np.array([1, 0, 0, 1.0])
    assert all(np.isnan(M.calibration_fit(y, np.full(4, 0.3))))
    assert np.isnan(M.calibration_in_the_large(np.zeros(4), np.full(4, 0.3)))
