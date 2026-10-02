"""Tests for score(): known-truth checks on synthetic worlds, plus the rules on inputs and outputs.

The synthetic worlds (eval_synthetic.py) know every row's true probability,
so the true Brier skill score and AUC can be worked out exactly. score() must
land close to them, and its 95% intervals must contain them.
"""
import json

import numpy as np
import pandas as pd
import pytest

from damdays.evaluation import p1_pass_bars, score
from damdays.evaluation.metrics import sigmoid, within_group_auc
from eval_synthetic import isolated_artifacts, make_world, true_auc, true_bss  # noqa: F401 (fixture)


@pytest.fixture(scope="module")
def big_world():
    """60,000 VAL rows (1,000 dams x 60 looks) with known true probabilities."""
    return make_world(n_dams=1000, looks_per_dam=60, block="VAL", seed=11)


@pytest.fixture(scope="module")
def small_world():
    """6,000 VAL rows for the quick rule checks."""
    return make_world(n_dams=200, looks_per_dam=30, block="VAL", seed=12)


def quick(world, **kwargs):
    """score() with no bootstrap and no files, for tests that only need the point numbers."""
    options = dict(task="P1_R30", subset="all", model="m", n_boot=0, write=False)
    options.update(kwargs)
    return score(world, **options)


def width(ci):
    """Width of a [low, high] interval."""
    return ci[1] - ci[0]


# ---------------------------------------------------------------------------
# Known truth
# ---------------------------------------------------------------------------
def test_perfect_forecast_scores_close_to_the_known_truth(big_world):
    """The true-probability forecast: BSS and AUC near their exact values, calibration near ideal.

    "Near" is judged two ways: within a fixed tolerance, and within 3.3 standard
    errors as implied by the dam interval (a 1-in-1000 miss if the interval is right).
    """
    w = big_world
    result = score(w, "P1_R30", "all", model="oracle", n_boot=200, write=False)
    point, ci = result["point"], result["ci_dam"]
    expected = dict(bss_B0=true_bss(w.q, w.p_B0, w.q), bss_B2=true_bss(w.q, w.p_B2, w.q), auc=true_auc(w.q, w.q))
    for name, value in expected.items():
        got, standard_error = point[name], width(ci[name]) / 3.92
        assert got == pytest.approx(value, abs=0.015), f"{name}: expected {value:.4f}, got {got:.4f}"
        assert abs(got - value) < 3.3 * standard_error, f"{name}: {got:.4f} vs truth {value:.4f}, CI {ci[name]}"
    assert point["cal_slope"] == pytest.approx(1.0, abs=0.05), f"slope: expected 1.00, got {point['cal_slope']:.3f}"
    assert point["citl"] == pytest.approx(0.0, abs=0.05), f"CITL: expected 0.00, got {point['citl']:.3f}"
    assert point["base_rate"] == pytest.approx(w.y.mean())


def test_dam_interval_covers_the_truth_about_95_percent_of_the_time():
    """Redraw the outcomes 40 times from the same true probabilities: the dam CI should hold the truth ~95% of the time."""
    w = make_world(n_dams=200, looks_per_dam=30, block="VAL", seed=14)
    truth = true_bss(w.q, w.p_B0, w.q)
    rng = np.random.default_rng(15)
    covered = 0
    for _ in range(40):
        redrawn = w.assign(y=(rng.random(len(w)) < w.q).astype(float))
        low, high = quick(redrawn, n_boot=100)["ci_dam"]["bss_B0"]
        covered += low <= truth <= high
    assert covered / 40 >= 0.85, f"expected about 0.95 coverage, got {covered / 40:.3f}"


def test_weaker_forecast_scores_close_to_its_known_truth(big_world):
    """A forecast that ignores the year's weather: lower skill, still near its exact value."""
    w = big_world.assign(p=big_world.p_no_year)
    point = quick(w)["point"]
    for name, base in (("bss_B0", w.p_B0), ("bss_B2", w.p_B2)):
        value = true_bss(w.p_no_year, base, w.q)
        assert point[name] == pytest.approx(value, abs=0.015), f"{name}: expected {value:.4f}, got {point[name]:.4f}"
    value = true_auc(w.p_no_year, w.q)
    assert point["auc"] == pytest.approx(value, abs=0.01), f"auc: expected {value:.4f}, got {point['auc']:.4f}"


def test_paired_difference_against_a_reference(big_world):
    """Paired gain = BSS_B0(model) - BSS_B0(reference), computed on the same rows; its CI excludes 0 here."""
    w = big_world.assign(p_weak=big_world.p_no_year)
    result = score(w, "P1_R30", "all", model="oracle", refs=["weak"], n_boot=200, write=False)
    alone = quick(w.assign(p=w.p_weak))["point"]
    gain = result["point"]["d_bss_B0_vs_weak"]
    assert gain == pytest.approx(result["point"]["bss_B0"] - alone["bss_B0"], abs=1e-12)
    assert result["point"]["d_auc_vs_weak"] == pytest.approx(result["point"]["auc"] - alone["auc"], abs=1e-12)
    expected = true_bss(w.q, w.p_B0, w.q) - true_bss(w.p_weak, w.p_B0, w.q)
    assert gain == pytest.approx(expected, abs=0.01), f"paired gain: expected {expected:.4f}, got {gain:.4f}"
    assert result["ci_dam"]["d_bss_B0_vs_weak"][0] > 0


def test_region_year_interval_is_wider_when_years_matter():
    """Big unexplained year-to-year swings: resampling region-years gives the wider interval."""
    w = make_world(n_dams=600, looks_per_dam=40, block="VAL", year_shock_sd=0.8, seed=13)
    w = w.assign(p=w.p_no_year)
    result = score(w, "P1_R30", "all", model="m", n_boot=200, write=False)
    dam, ry = result["ci_dam"]["bss_B0"], result["ci_region_year"]["bss_B0"]
    assert width(ry) > width(dam), f"expected the region-year CI {ry} to be wider than the dam CI {dam}"


def test_intervals_are_reproducible_and_ignore_row_order(small_world):
    """Fixed seeds: the same predictions give the same intervals, in any row order; a new seed changes them."""
    first = quick(small_world, n_boot=60)
    shuffled = quick(small_world.sample(frac=1.0, random_state=1), n_boot=60)
    other_seed = quick(small_world, n_boot=60, seed=1)
    assert first["ci_dam"] == shuffled["ci_dam"]
    assert first["ci_region_year"] == shuffled["ci_region_year"]
    assert first["point"] == pytest.approx(shuffled["point"], abs=1e-12)
    assert first["ci_dam"] != other_seed["ci_dam"]
    assert first["bootstrap"]["dam"]["clusters"] == 200
    assert first["bootstrap"]["region_year"]["clusters"] == first["rows"]["region_years"]


# ---------------------------------------------------------------------------
# Subsets
# ---------------------------------------------------------------------------
def test_primary_subset_is_dam_like_octmar_at_risk(small_world):
    """'primary' keeps dam-like dams, at-risk issues and October-March issue months, in any spelling."""
    w = small_world
    months = pd.DatetimeIndex(w.issue_date).month
    expected = int((w.dam_like & w.at_risk & np.isin(months, [10, 11, 12, 1, 2, 3])).sum())
    result = quick(w, subset="primary")
    assert result["rows"]["scored"] == expected
    assert result["subset"] == "dam_like+octmar+at_risk"
    assert quick(w, subset="at_risk+octmar+dam_like")["point"] == result["point"]


def test_persistent_subset(small_world):
    """'persistent' keeps only rows flagged persistent."""
    assert quick(small_world, subset="persistent")["rows"]["scored"] == int(small_world.persistent.sum())


def test_subset_errors(small_world):
    """Unknown parts, missing flag columns, text flags and Oct-Mar on a season rating all refuse."""
    with pytest.raises(ValueError, match="Unknown subset"):
        quick(small_world, subset="damlike")
    with pytest.raises(ValueError, match="Missing column"):
        quick(small_world.drop(columns="at_risk"), subset="at_risk")
    with pytest.raises(ValueError, match="True/False"):
        quick(small_world.assign(dam_like=small_world.dam_like.astype(str)), subset="dam_like")
    with pytest.raises(ValueError, match="do not apply"):
        quick(small_world, task="P2_dam", subset="octmar")


# ---------------------------------------------------------------------------
# Input checks
# ---------------------------------------------------------------------------
def test_bad_tables_are_refused(small_world):
    """Duplicates, impossible probabilities or labels, mixed blocks and unknown names all raise."""
    w = small_world
    cases = {
        "duplicated": pd.concat([w, w.iloc[:1]]),
        "probabilities": w.assign(p=w.p * 1.5),
        "must hold 1": w.assign(y=w.y * 0.5),
        "one scorable block": pd.concat([w, make_world(n_dams=5, looks_per_dam=5, block="TEST", seed=3)
                                         .assign(uid=lambda d: "t" + d.uid)]),
        "not all development": w.assign(region=np.where(w.index < 10, "sealed_sdowns_newengland", w.region)),
    }
    for message, table in cases.items():
        with pytest.raises(ValueError, match=message):
            quick(table)
    with pytest.raises(ValueError, match="one scorable block"):
        quick(w.assign(issue_date=pd.Timestamp("2016-03-01")).drop_duplicates(["uid"]))   # the GAP half-year
    with pytest.raises(ValueError, match="Unknown task"):
        quick(w, task="P1_r30")


def test_rows_without_a_label_are_dropped_and_counted(small_world):
    """Blank labels (answer not known) are left out and reported, not treated as 0."""
    w = small_world.copy()
    w.loc[w.index[:100], "y"] = np.nan
    result = quick(w)
    assert result["rows"]["scored"] == len(w) - 100
    assert result["rows"]["in_subset_without_label"] == 100


def test_baselines_can_be_joined(small_world):
    """Baselines from a separate table give the same numbers; missing or conflicting baselines raise."""
    w = small_world
    base = w[["uid", "issue_date", "p_B0", "p_B2"]]
    joined = quick(w.drop(columns=["p_B0", "p_B2"]), baselines=base)
    assert joined["point"] == quick(w)["point"]
    with pytest.raises(ValueError, match="no matching row"):
        quick(w.drop(columns=["p_B0", "p_B2"]), baselines=base.iloc[1:])
    with pytest.raises(ValueError, match="differs"):
        quick(w, baselines=base.assign(p_B0=0.5))
    with pytest.raises(ValueError, match="Missing column"):
        quick(w.drop(columns="p_B2"))


def test_expected_keys_must_match_exactly(small_world):
    """The official row list passes; one missing row raises."""
    keys = small_world[small_world.dam_like][["uid", "issue_date"]]
    assert quick(small_world, subset="dam_like", expected_keys=keys)["row_set_checked"]
    with pytest.raises(ValueError, match="expected rows have no prediction"):
        quick(small_world.drop(index=keys.index[:1]), subset="dam_like", expected_keys=keys)


# ---------------------------------------------------------------------------
# Season ratings (P2)
# ---------------------------------------------------------------------------
def season_world(seed=21, n_dams=400):
    """P2-style rows: one 1-July issue per dam per season, 2009-2015 (VAL)."""
    rng = np.random.default_rng(seed)
    dam_effect = rng.normal(0, 1, n_dams)
    seasons = np.arange(2009, 2016)
    shock = dict(zip(seasons, rng.normal(0, 0.5, len(seasons))))
    rows = [(f"d{d:04d}", pd.Timestamp(f"{s}-07-01"), dam_effect[d] + shock[s]) for d in range(n_dams) for s in seasons]
    table = pd.DataFrame(rows, columns=["uid", "issue_date", "z"])
    q = sigmoid(-1.5 + table.z)
    return table.assign(region=np.where(table.uid.str[-1].isin(list("02468")), "nsw_cw", "wvic_sesa"),
                        y=(rng.random(len(q)) < q).astype(float), p=q, p_B0=q.mean(),
                        p_B2=sigmoid(-1.5 + table.z - table.issue_date.dt.year.map(shock)))


def test_season_rating_reports_within_season_and_within_dam_auc():
    """P2 results add AUC within each season (which dams) and within each dam (which years)."""
    table = season_world()
    point = quick(table, task="P2_dam")["point"]
    years = table.issue_date.dt.year
    assert point["auc_within_season"] == pytest.approx(within_group_auc(table.y, table.p, years), abs=1e-12)
    assert point["auc_within_dam"] == pytest.approx(within_group_auc(table.y, table.p, table.uid), abs=1e-12)
    assert "auc_within_cell" in quick(table, task="P2_cell")["point"]


# ---------------------------------------------------------------------------
# Outputs and dry runs
# ---------------------------------------------------------------------------
def test_json_and_markdown_are_written(small_world, tmp_path):
    """One JSON file per (model, task, subset), one markdown row per call."""
    result = score(small_world, "P1_R30", "dam_like", model="Demo", n_boot=20, out_dir=tmp_path)
    saved = json.loads(open(result["json_path"], encoding="utf-8").read())
    assert saved["model"] == "demo" and saved["subset"] == "dam_like" and saved["block"] == "VAL"
    assert saved["point"]["bss_B0"] == pytest.approx(result["point"]["bss_B0"], abs=1e-5)
    score(small_world, "P1_R30", "dam_like", model="Demo", n_boot=20, out_dir=tmp_path)
    table = (tmp_path / "scorecard_dev_VAL.md").read_text(encoding="utf-8").splitlines()
    assert table[0].startswith("| time | model") and len(table) == 4      # header, rule, two rows


def test_val_can_skip_files(small_world, tmp_path):
    """write=False writes nothing for VAL (TEST always writes: see the ledger tests)."""
    quick(small_world, out_dir=tmp_path)
    assert not any(tmp_path.iterdir())


def test_dry_run_checks_everything_but_computes_nothing(small_world):
    """A dry run returns row counts and hashes, and no numbers."""
    result = quick(small_world, dry_run=True, subset="primary")
    assert result["dry_run"] and "point" not in result and result["rows"]["scored"] > 0


def test_prereg_pass_bars():
    """The three pre-registered P1 bars, checked mechanically."""
    result = dict(point=dict(bss_B0=0.233, bss_B2=0.153, cal_slope=1.09), ci_dam=dict(bss_B0=[0.220, 0.245]))
    assert p1_pass_bars(result)["all_passed"]
    result["point"]["cal_slope"] = 1.25
    bars = p1_pass_bars(result)
    assert not bars["cal_slope"]["passed"] and not bars["all_passed"]
    result = dict(point=dict(bss_B0=0.12, bss_B2=0.06, cal_slope=1.0), ci_dam=dict(bss_B0=[-0.01, 0.25]))
    assert not p1_pass_bars(result)["bss_B0"]["passed"]                 # CI must be above 0
