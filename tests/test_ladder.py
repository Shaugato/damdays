"""Every rung of the PREREG fallback ladder (L0 to L3) runs through Tidemark's one entry point.

What is proved here, on small made-up data (no real data, about a minute; the real nets S and M
are trained on it, with their checkpoints kept out of data_cache):
  * fit_tidemark(cutoff, rung) fits L0, L1, L2 and L3, and predict_tidemark returns the SAME
    columns for every rung (tidemark.p1_output_columns), so scripts/12_ladder_val.py can line
    them up column for column;
  * each rung uses exactly its members: L0 is the tree T alone (no frailty, no max rule), L1 adds
    the frailty and the max rule, L2 adds the nets (their columns are blank on L0 and L1), and
    L3 adds the 2 water-balance columns to T and the runway curve H only;
  * the parts that do not depend on a rung's members are identical across rungs (floor, season
    rating; the curve too, except at L3 where H gets the water-balance columns);
  * the TEST setting (cutoff 2016-07-01) fits every rung too, with the same columns (made-up
    data running to 2018; nothing real is fitted or scored).
"""
import numpy as np
import pytest

from damdays.data.splits import time_block
from damdays.models import fusion, nets, rows, tidemark
from test_nets import synthetic_history
from test_tidemark import synthetic_inputs

VAL_CUTOFF, TEST_CUTOFF = "2009-01-01", "2016-07-01"
RUNGS = ("L0", "L1", "L2", "L3")


def ladder_world(seed, last_issue="2016-06-30", last_season=2015, last_month="2016-12"):
    """Made-up inputs with every column any rung reads: G2 features, net inputs, monthly history, water balance."""
    inputs = synthetic_inputs(seed=seed, n_dams=40, last_issue=last_issue, last_season=last_season)
    p1 = inputs["p1"]
    rng = np.random.default_rng(seed)
    for column in nets.TABULAR_INPUTS:
        if column not in p1.columns:
            p1[column] = rng.normal(size=len(p1)).astype(np.float32)
    p1["full_c"] = rng.uniform(20, 100, len(p1))
    for column in tidemark.PHY_COLUMNS:                     # made-up water-balance outlooks in [0, 1]
        p1[column] = rng.uniform(0, 1, len(p1))
    inputs["monthly_history"] = synthetic_history(p1["uid"].unique(), last_month=last_month, seed=seed)
    return inputs


def fit_every_rung(cutoff, inputs, folder):
    """{rung: predict_tidemark output} for L0 to L3 at `cutoff`, with the nets' checkpoints kept in `folder`."""
    patch = pytest.MonkeyPatch()
    patch.setattr(nets, "CHECKPOINT_DIR", folder)
    patch.setattr(nets, "_TRAINED", {})
    patch.setattr(nets, "_TABLE_INPUTS", {})
    try:
        return {rung: tidemark.predict_tidemark(tidemark.fit_tidemark(cutoff, rung, inputs=inputs), inputs)
                for rung in RUNGS}
    finally:
        patch.undo()


@pytest.fixture(scope="module")
def ladder(tmp_path_factory):
    """All four rungs fitted in the VAL setting on one made-up world."""
    return fit_every_rung(VAL_CUTOFF, ladder_world(seed=6), tmp_path_factory.mktemp("nets"))


def test_every_rung_returns_the_same_columns(ladder):
    contract = tidemark.p1_output_columns()
    for rung, out in ladder.items():
        assert list(out["p1"].columns) == contract, rung
        for part in ("p2_dam", "p2_cell"):
            assert list(out[part].columns) == list(ladder["L1"][part].columns), (rung, part)
        assert np.array_equal(out["p1"]["row"].to_numpy(), ladder["L1"]["p1"]["row"].to_numpy())


def test_each_rung_uses_exactly_its_members(ladder):
    for rung in ("L0", "L1"):                                # no nets: blank columns
        for name in ("S", "M"):
            assert ladder[rung]["p1"][[f"p_{name}_{k}" for k in rows.P1_KINDS]].isna().all().all(), rung
    for rung in ("L2", "L3"):
        for name in ("S", "M"):
            assert ladder[rung]["p1"][f"p_{name}_D0"].notna().all(), rung
    l0 = ladder["L0"]["p1"]
    for kind in rows.P1_KINDS:                               # L0 = T alone (G2), no frailty
        on = l0[f"p90_{kind}"].notna()
        assert np.allclose(l0.loc[on, f"p90_{kind}"], l0.loc[on, f"p_T_{kind}"], rtol=0, atol=1e-12)
        assert (l0.loc[on, f"frailty_b_{kind}"] == 0).all()
    assert np.array_equal(l0["p90_R30"].dropna(), l0["p90_R30_premax"].dropna())          # no max rule at L0
    l2 = ladder["L2"]["p1"]
    anchor = fusion.sigmoid(np.mean([fusion.logit(l2[f"p_{m}_D0"]) for m in ("T", "S", "M")], axis=0))
    assert np.allclose(l2["anchor_D0"], anchor, rtol=0, atol=1e-9)                           # equal thirds


def test_member_independent_parts_are_shared_and_physics_reaches_only_t_and_h(ladder):
    first = ladder["L0"]
    for rung, out in ladder.items():
        for column in ("floor_log_q10", "floor_days", "floor_shown"):
            assert out["p1"][column].equals(first["p1"][column]), (rung, column)
        assert np.array_equal(out["p2_dam"]["p"], first["p2_dam"]["p"])
        assert np.array_equal(out["p2_cell"]["p"], first["p2_cell"]["p"])
    curves = [f"curve_{k}_{h}" for k in tidemark.CURVE_KINDS for h in tidemark.HORIZONS]
    for rung in ("L1", "L2"):                                # no water-balance columns: same T and H as L0
        assert ladder[rung]["p1"][curves].equals(first["p1"][curves]), rung
        assert ladder[rung]["p1"]["p_T_D0"].equals(first["p1"]["p_T_D0"]), rung
    l2, l3 = ladder["L2"]["p1"], ladder["L3"]["p1"]
    assert not l3[curves].equals(l2[curves])                 # H uses the water-balance columns at L3
    assert not l3["p_T_D0"].equals(l2["p_T_D0"])             # ... and so does T
    for name in ("S", "M"):                                  # the nets do not read them
        assert l3[f"p_{name}_D0"].equals(l2[f"p_{name}_D0"]), name


def test_the_test_setting_fits_every_rung_with_the_same_columns(tmp_path):
    inputs = ladder_world(seed=7, last_issue="2018-06-30", last_season=2017, last_month="2018-12")
    outputs = fit_every_rung(TEST_CUTOFF, inputs, tmp_path / "nets")
    for rung, out in outputs.items():
        assert list(out["p1"].columns) == tidemark.p1_output_columns(), rung
        assert set(time_block(out["p1"]["issue_date"])) == {"TEST"}, rung
        assert set(out["p2_dam"]["season"]) == {2016, 2017}, rung
    assert outputs["L3"]["p1"]["p_S_D0"].notna().all() and outputs["L1"]["p1"]["p_S_D0"].isna().all()
