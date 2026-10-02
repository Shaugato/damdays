"""Tests for the TEST ledger: one look at TEST per model, every call written down.

All tests use a temporary ledger (see the isolated_artifacts fixture), never
the real artifacts/test_ledger.csv.
"""
import numpy as np
import pandas as pd
import pytest

from damdays.evaluation import Ledger, LedgerError, prediction_hash, score, score_curve
from damdays.evaluation import ledger as ledger_module
from eval_synthetic import isolated_artifacts, make_world  # noqa: F401 (fixture)


@pytest.fixture
def test_world():
    """A small TEST-block world in the development regions."""
    return make_world(n_dams=150, looks_per_dam=20, block="TEST", seed=31)


def on_test(table, model="tidemark", subset="all", **kwargs):
    """Score on TEST quickly (tiny bootstrap); returns the result."""
    return score(table, "P1_R30", subset, model=model, n_boot=10, **kwargs)


def ledger_rows():
    """The temporary ledger, as a table."""
    return Ledger().entries()


def nudge(table, row=0):
    """The same predictions with one value changed in its last binary digit (about the 17th decimal)."""
    changed = table.copy()
    changed.loc[changed.index[row], "p"] = np.nextafter(changed["p"].iloc[row], 1.0)
    return changed


# ---------------------------------------------------------------------------
# The one-look rule
# ---------------------------------------------------------------------------
def test_first_test_call_is_new_and_written_down(test_world):
    """The first TEST call is 'new', with a timestamp and a 16-character prediction hash."""
    result = on_test(test_world)
    rows = ledger_rows()
    assert result["test_ledger"] == "new"
    assert len(rows) == 1
    row = rows.iloc[0]
    assert (row["model"], row["task"], row["arena"], row["block"], row["status"]) == (
        "tidemark", "P1_R30", "dev", "TEST", "new")
    assert row["pred_hash"] == result["pred_hash"] and len(row["pred_hash"]) == 16
    assert pd.Timestamp(row["time"]) is not pd.NaT


def test_same_predictions_on_other_subsets_are_allowed(test_world):
    """The same forecasts may be scored on other subsets, in any row order."""
    on_test(test_world)
    assert on_test(test_world, subset="dam_like")["test_ledger"] == "same_predictions"
    shuffled = test_world.sample(frac=1.0, random_state=2)
    assert on_test(shuffled, subset="persistent")["test_ledger"] == "same_predictions"
    assert list(ledger_rows()["status"]) == ["new", "same_predictions", "same_predictions"]


def test_tiny_change_is_refused_and_the_attempt_is_logged(test_world, isolated_artifacts):
    """Changing one probability in its last digit: refused, logged, and no TEST number is written."""
    on_test(test_world)
    files_before = sorted(isolated_artifacts.rglob("*.json"))
    with pytest.raises(LedgerError, match="already scored on TEST"):
        on_test(nudge(test_world))
    assert list(ledger_rows()["status"]) == ["new", "refused"]
    assert sorted(isolated_artifacts.rglob("*.json")) == files_before


def test_a_prefiltered_table_of_identical_rows_is_allowed(test_world):
    """Passing only some of the first call's rows, unchanged, counts as the same predictions."""
    on_test(test_world)
    result = on_test(test_world[test_world.dam_like])
    assert result["test_ledger"] == "same_predictions"
    assert "row subset" in ledger_rows()["note"].iloc[-1]


def test_new_rows_are_refused(test_world):
    """Adding rows the first call did not have is a new look at TEST: refused."""
    on_test(test_world[test_world.dam_like])
    with pytest.raises(LedgerError, match="rows were not in the first call"):
        on_test(test_world)


def test_without_saved_predictions_only_an_exact_match_passes(test_world):
    """If the saved predictions are lost, the CSV still rules: exact hash passes, a partial table does not."""
    on_test(test_world)
    for saved in Ledger().store_dir.iterdir():
        saved.unlink()
    assert on_test(test_world, subset="dam_like")["test_ledger"] == "same_predictions"
    with pytest.raises(LedgerError, match="hash differs"):
        on_test(test_world[test_world.dam_like])


def test_model_names_are_case_and_space_insensitive(test_world):
    """'Tidemark ' and 'tidemark' are the same model on the ledger; a new name is a new model."""
    on_test(test_world, model="Tidemark ")
    with pytest.raises(LedgerError):
        on_test(nudge(test_world), model="tidemark")
    assert on_test(nudge(test_world), model="tidemark_fix1")["test_ledger"] == "new"


def test_val_never_touches_the_ledger():
    """VAL is for choosing: score it as often as you like."""
    val = make_world(n_dams=100, looks_per_dam=20, block="VAL", seed=32)
    score(val, "P1_R30", "all", model="tidemark", n_boot=0, write=False)
    score(nudge(val), "P1_R30", "all", model="tidemark", n_boot=0, write=False)
    assert len(ledger_rows()) == 0


def test_test_results_are_always_written(test_world, isolated_artifacts):
    """write=False cannot hide a TEST result: the JSON and markdown row are written anyway."""
    result = on_test(test_world, write=False)
    assert result["json_path"]
    assert (isolated_artifacts / "scorecard" / "scorecard_dev_TEST.md").exists()


def test_dry_run_is_logged_but_does_not_use_the_look(test_world):
    """A dry run checks everything, computes nothing, and leaves the one look unused."""
    result = on_test(test_world, dry_run=True)
    assert result["test_ledger"] == "dry_run" and "point" not in result
    assert on_test(test_world)["test_ledger"] == "new"
    assert list(ledger_rows()["status"]) == ["dry_run", "new"]


def test_sealed_region_is_a_separate_test(test_world):
    """The same model gets its own single look at the sealed region."""
    on_test(test_world)
    sealed = test_world.assign(region="sealed_sdowns_newengland")
    assert on_test(sealed)["test_ledger"] == "new"
    assert list(ledger_rows()["arena"]) == ["dev", "sealed"]


# ---------------------------------------------------------------------------
# Reference models for paired differences
# ---------------------------------------------------------------------------
def test_reference_must_be_on_the_ledger_with_the_same_predictions(test_world):
    """A paired comparison needs the reference's own ledgered predictions, unchanged."""
    table = test_world.assign(p_G2=test_world.p_no_year)
    with pytest.raises(LedgerError, match="no TEST score"):
        on_test(table, refs=["G2"])
    on_test(table.assign(p=table.p_G2), model="G2")                        # G2 takes its own one look
    result = on_test(table, refs=["G2"])
    assert result["test_ledger"] == "new" and "d_bss_B0_vs_G2" in result["point"]
    weakened = table.assign(p_G2=np.clip(table.p_G2 * 0.9, 0, 1))
    with pytest.raises(LedgerError, match="Reference model 'g2'"):
        on_test(weakened, refs=["G2"])
    assert list(ledger_rows()["status"]) == ["refused", "new", "new", "refused"]


# ---------------------------------------------------------------------------
# Runway curves share the ledger
# ---------------------------------------------------------------------------
def test_curves_get_one_look_too(test_world):
    """A runway curve on TEST is ledgered like any other forecast."""
    curve = test_world[["uid", "issue_date", "region"]].copy()
    for h, scale in zip((30, 60, 90, 180), (0.4, 0.7, 1.0, 1.5)):
        curve[f"p_{h}"] = np.clip(test_world.q * scale, 0, 1)
        curve[f"y_{h}"] = (test_world.q * scale > 0.5).astype(float)
        curve[f"p_B0_{h}"] = curve[f"p_{h}"].mean()
    assert score_curve(curve, "R30_curve", "all", model="tidemark", n_boot=5)["test_ledger"] == "new"
    changed = curve.assign(p_180=np.clip(curve.p_180 * 1.01, 0, 1))
    with pytest.raises(LedgerError):
        score_curve(changed, "R30_curve", "all", model="tidemark", n_boot=5)


# ---------------------------------------------------------------------------
# The fingerprint
# ---------------------------------------------------------------------------
def test_prediction_hash_ignores_order_but_sees_every_bit(test_world):
    """Row order does not change the hash; one bit, or swapping two rows' values, does."""
    table = test_world[["uid", "issue_date", "p"]]
    original = prediction_hash(table)
    assert prediction_hash(table.iloc[::-1]) == original
    assert prediction_hash(nudge(table)) != original
    swapped = table.copy()
    swapped.loc[swapped.index[[0, 1]], "p"] = swapped["p"].iloc[[1, 0]].to_numpy()
    assert prediction_hash(swapped) != original
    assert prediction_hash(table.rename(columns={"p": "p_other"}), ["p_other"]) == original


def test_bad_model_names_are_refused():
    """Ledger names are plain words, so the CSV and file names stay unambiguous."""
    with pytest.raises(ValueError):
        ledger_module.model_key("tide mark,v2")
