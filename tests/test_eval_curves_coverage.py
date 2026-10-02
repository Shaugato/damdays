"""Tests for runway-curve scoring (30/60/90/180 days) and the band and floor coverage checks.

The curve world has a known daily dry-out hazard per row, so the true chance
of an event by every horizon is known exactly: F(h) = 1 - exp(-hazard * h).
"""
import numpy as np
import pandas as pd
import pytest

from damdays.evaluation import (band_coverage, band_from_offsets, crossing_share, floor_coverage,
                                monotonicity_violations, region_year_offsets, score_curve)
from damdays.evaluation.metrics import logit, sigmoid
from eval_synthetic import isolated_artifacts, make_world, true_bss  # noqa: F401 (fixture)

HORIZONS = (30, 60, 90, 180)


@pytest.fixture(scope="module")
def curve_world():
    """VAL rows with a known daily hazard, event times drawn from it, and a perfect curve.

    The answer at h days is only known when the follow-up lasts at least h days;
    otherwise y_h is blank, whatever happened.
    """
    rows = make_world(n_dams=600, looks_per_dam=50, block="VAL", seed=41)[["uid", "issue_date", "region", "dam_like"]]
    rng = np.random.default_rng(42)
    hazard = np.exp(rng.normal(np.log(1 / 200), 0.9, len(rows)))       # events per day
    event_day = rng.exponential(1 / hazard)
    followup = rng.uniform(100, 400, len(rows))                         # some rows cannot be judged at 180 d
    for h in HORIZONS:
        truth = 1 - np.exp(-hazard * h)
        rows[f"q_{h}"] = truth
        rows[f"p_{h}"] = truth
        rows[f"y_{h}"] = np.where(followup >= h, (event_day <= h).astype(float), np.nan)
        rows[f"p_B0_{h}"] = pd.Series(truth).groupby(rows["region"].to_numpy()).transform("mean").to_numpy()
    return rows


def test_perfect_curve_scores_close_to_the_truth_at_every_horizon(curve_world):
    """BSS vs each horizon's own base rate, near its exact value; the curve never falls."""
    result = score_curve(curve_world, "R30_curve", "all", model="oracle", n_boot=50, write=False)
    for h in result["horizons"]:
        known = curve_world[f"y_{h['horizon']}"].notna()
        part = curve_world[known]
        value = true_bss(part[f"p_{h['horizon']}"], part[f"p_B0_{h['horizon']}"], part[f"q_{h['horizon']}"])
        got = h["point"]["bss_B0"]
        assert got == pytest.approx(value, abs=0.02), f"{h['horizon']} d: expected {value:.4f}, got {got:.4f}"
        assert h["rows"] == int(known.sum())
        assert "bss_B2" not in h["point"]                                # no B2 columns were given
    assert result["monotonicity"]["rows_falling"] == 0
    assert set(result["bss_B0_by_horizon"]) == set(HORIZONS)
    assert result["horizons"][-1]["rows_without_label"] > 0               # the 180-day answers are not all known


def test_curve_subset_and_b2(curve_world):
    """Subsets work on curves, and B2_h columns are used when present."""
    table = curve_world.copy()
    for h in HORIZONS:
        table[f"p_B2_{h}"] = np.clip(table[f"p_{h}"] * 0.8, 0, 1)
    result = score_curve(table, "D0_curve", "dam_like", model="oracle", n_boot=0, write=False)
    assert result["rows_in_subset"] == int(table.dam_like.sum())
    assert all(h["point"]["bss_B2"] > 0 for h in result["horizons"])


def test_curve_task_names_are_checked(curve_world):
    """score_curve only takes curve tasks."""
    with pytest.raises(ValueError, match="not a runway-curve task"):
        score_curve(curve_world, "P1_R30", "all", model="m", n_boot=0, write=False)


def test_monotonicity_violations_by_hand():
    """Row 2 falls from 0.5 to 0.4 between 60 and 90 days; nothing else falls."""
    curves = np.array([[0.1, 0.2, 0.3, 0.4], [0.2, 0.5, 0.4, 0.6], [0.3, 0.3, 0.3, 0.3]])
    check = monotonicity_violations(curves)
    assert check["rows_falling"] == 1 and check["largest_fall"] == pytest.approx(0.1)


def test_crossing_share_by_hand():
    """The R30 curve must stay at or above the D0 curve; one of two rows dips below."""
    r30 = np.array([[0.2, 0.4], [0.3, 0.5]])
    d0 = np.array([[0.1, 0.45], [0.1, 0.2]])
    assert crossing_share(r30, d0) == pytest.approx(0.5)
    assert crossing_share(r30[:, 0], d0[:, 0]) == 0.0


# ---------------------------------------------------------------------------
# Season band
# ---------------------------------------------------------------------------
def band_world(seed=51):
    """Region-years with a known offset each: outcomes drawn from logit(p) + offset."""
    rng = np.random.default_rng(seed)
    offsets = {}
    parts = []
    for region in ("nsw_cw", "wvic_sesa"):
        for year in range(2009, 2015):
            offset = rng.uniform(-0.6, 0.6)
            offsets[f"{region}:{year}"] = offset
            n = 5000
            p = sigmoid(rng.normal(-1.2, 1.0, n))
            y = (rng.random(n) < sigmoid(logit(p) + offset)).astype(float)
            dates = pd.Timestamp(f"{year}-07-01") + pd.to_timedelta(rng.integers(0, 365, n), unit="D")
            parts.append(pd.DataFrame(dict(y=y, p=p, region=region, issue_date=dates)))
    small = pd.DataFrame(dict(y=[1.0, 0.0] * 25, p=0.3, region="nsw_cw", issue_date=pd.Timestamp("2015-08-01")))
    return pd.concat(parts + [small], ignore_index=True), offsets


def test_region_year_offsets_recover_the_known_offsets():
    """Each region-year's offset comes back within 0.1; a 50-row year is too small to use."""
    table, truth = band_world()
    found = region_year_offsets(table.y, table.p, table.region, table.issue_date).set_index("region_year")
    for region_year, offset in truth.items():
        got = found.loc[region_year, "offset"]
        assert got == pytest.approx(offset, abs=0.1), f"{region_year}: expected {offset:+.3f}, got {got:+.3f}"
    assert not found.loc["nsw_cw:2015", "used"] and np.isnan(found.loc["nsw_cw:2015", "offset"])


def test_band_coverage_by_hand():
    """Band [-0.3, +0.3] from a backtest; of five years, one is drier and one wetter than the band."""
    backtest = pd.DataFrame(dict(region_year=["a:1", "a:2", "b:1"], offset=[-0.3, 0.1, 0.3], used=True))
    low, high = band_from_offsets(backtest)
    assert (low, high) == (-0.3, 0.3)
    scored = pd.DataFrame(dict(region_year=["a:3", "a:4", "b:3", "b:4", "b:5", "b:6"],
                               offset=[-0.4, -0.1, 0.0, 0.2, 0.5, np.nan],
                               used=[True, True, True, True, True, False]))
    check = band_coverage(scored, low, high)
    assert (check["region_years"], check["covered"], check["not_used"]) == (5, 3, 1)
    assert check["coverage"] == pytest.approx(0.6)
    assert list(check["drier_than_band"]) == ["b:5"] and list(check["wetter_than_band"]) == ["a:3"]


# ---------------------------------------------------------------------------
# DamDays floor
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def floor_world():
    """100,000 forecasts whose floor is exactly the true 10% point of the time to the event.

    Event times are exponential with a known rate, so P(event day >= floor) = 0.90 exactly.
    """
    rng = np.random.default_rng(61)
    n = 100_000
    rate = np.exp(rng.normal(np.log(1 / 150), 0.7, n))
    floor = -np.log(0.9) / rate
    event_day = rng.exponential(1 / rate)
    uid = np.array([f"d{i % 2000:04d}" for i in range(n)])
    dates = pd.Timestamp("2010-01-01") + pd.to_timedelta(rng.integers(0, 5 * 365, n), unit="D")
    return dict(floor=floor, event_day=event_day, uid=uid, dates=dates, rng=rng)


def test_floor_coverage_is_90_percent_when_the_floor_is_right(floor_world):
    """Watched long enough, a correct floor holds 90% of the time."""
    f = floor_world
    check = floor_coverage(f["floor"], f["event_day"], np.full(len(f["floor"]), np.inf), uid=f["uid"],
                           issue_date=f["dates"], n_boot=100)
    assert check["coverage"] == pytest.approx(0.90, abs=0.005), f"expected 0.900, got {check['coverage']:.4f}"
    assert check["on_target"]
    assert check["ci_dam"]["coverage"][0] <= 0.90 <= check["ci_dam"]["coverage"][1]
    assert check["worst_year"]["coverage"] <= check["coverage"] and len(check["by_year"]) >= 5


def test_floor_coverage_stays_honest_when_follow_up_is_short(floor_world):
    """Half the rows are watched for less than their floor. Judging only rows watched long enough
    keeps coverage at 0.90; also counting short-watch rows that failed would wrongly drag it down."""
    f = floor_world
    followup = f["rng"].uniform(0, 2, len(f["floor"])) * f["floor"]
    check = floor_coverage(f["floor"], f["event_day"], followup, n_boot=0)
    assert check["coverage"] == pytest.approx(0.90, abs=0.007), f"expected 0.900, got {check['coverage']:.4f}"
    assert check["share_not_judged"] == pytest.approx(0.5, abs=0.01)
    # The outcome-dependent rule, for contrast: also count rows where a failure happened to be seen.
    seen_failure = (f["event_day"] < f["floor"]) & (f["event_day"] <= followup)
    judged_badly = (followup >= f["floor"]) | seen_failure
    biased = (f["event_day"] >= f["floor"])[judged_badly].mean()
    assert biased < 0.88, f"the outcome-dependent rule should look worse; got {biased:.4f}"


def test_floor_cap_and_missing_events():
    """'No event seen' (NaN) holds; an uncapped infinite floor can never be judged; a 180-day cap can."""
    check = floor_coverage([np.inf, np.inf, 50.0], [np.nan, 100.0, 20.0], [400, 400, 400], n_boot=0)
    assert check["rows_judged"] == 1 and check["coverage"] == 0.0           # only the 50-day floor, which failed
    capped = floor_coverage([np.inf, np.inf, 50.0], [np.nan, 100.0, 20.0], [400, 400, 400], cap_days=180, n_boot=0)
    assert capped["rows_judged"] == 3 and capped["coverage"] == pytest.approx(1 / 3)
