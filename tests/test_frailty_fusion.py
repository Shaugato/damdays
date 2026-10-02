"""Hand-checkable tests of the per-dam frailty and the fusion step (no real data).

The rule worth proving is about time: a past forecast may shape a dam's
frailty only once its answer is final, 120 days after it was issued
(90-day window + 30 days to confirm an event).
"""
import numpy as np
import pandas as pd
import pytest

from damdays.models import frailty, fusion

DAY0 = pd.Timestamp("2000-01-01")


def days(*offsets):
    """Dates DAY0 + offset days."""
    return np.array([DAY0 + pd.Timedelta(days=d) for d in offsets], dtype="datetime64[ns]")


# ---------------------------------------------------------------------------
# Frailty sums
# ---------------------------------------------------------------------------
def test_hand_worked_example_and_the_120_day_boundary():
    # One dam. Records on day 0 (event, p = 0.2) and day 50 (no event, p = 0.5); issues on days 169 and 170.
    # Day 0 + 120 = 120: final for both issues. Day 50 + 120 = 170: final for the day-170 issue only.
    dates = days(0, 50, 169, 170)
    is_record = np.array([True, True, False, False])
    y = np.array([1.0, 0.0, np.nan, np.nan])
    p = np.array([0.2, 0.5, 0.3, 0.3])
    R, V, n = frailty.matured_residual_sums(["a"] * 4, dates, is_record, y, p)
    assert n.tolist() == [0, 0, 1, 2]
    assert R[2] == pytest.approx(0.8) and V[2] == pytest.approx(0.16)
    assert R[3] == pytest.approx(0.8 - 0.5) and V[3] == pytest.approx(0.16 + 0.25)
    b = frailty.frailty_offset(R, V)
    assert b[3] == pytest.approx(0.3 / (0.41 + 100))
    assert b[0] == 0.0                                    # no history: no shift


def test_an_unfinished_record_cannot_move_the_frailty():
    # The day-100 record is only final on day 220, after the day-200 issue.
    dates = days(0, 100, 200)
    is_record = np.array([True, True, False])
    p = np.array([0.3, 0.3, 0.3])
    first = frailty.matured_residual_sums(["a"] * 3, dates, is_record, np.array([1.0, 0.0, np.nan]), p)
    flipped = frailty.matured_residual_sums(["a"] * 3, dates, is_record, np.array([1.0, 1.0, np.nan]), p)
    assert first[0][2] == flipped[0][2] and first[2][2] == 1


def test_other_dams_and_row_order_do_not_matter():
    dates = days(0, 0, 300, 300)
    dams = ["a", "b", "a", "b"]
    is_record = np.array([True, True, False, False])
    y = np.array([1.0, 0.0, np.nan, np.nan])
    p = np.array([0.4, 0.4, 0.4, 0.4])
    R, V, n = frailty.matured_residual_sums(dams, dates, is_record, y, p)
    assert R[2] == pytest.approx(0.6) and R[3] == pytest.approx(-0.4) and n[2] == n[3] == 1
    shuffle = np.array([3, 1, 2, 0])
    R2, _, _ = frailty.matured_residual_sums(np.array(dams)[shuffle], dates[shuffle], is_record[shuffle],
                                             y[shuffle], p[shuffle])
    assert np.allclose(R2, R[shuffle])


def test_records_need_known_labels():
    with pytest.raises(ValueError):
        frailty.matured_residual_sums(["a"], days(0), [True], [np.nan], [0.5])


def random_history(n_dams=40, looks_per_dam=120, seed=0):
    """Made-up track records: random look days over ~5 years per dam, rows shuffled."""
    rng = np.random.default_rng(seed)
    dam = np.repeat([f"dam{i:02d}" for i in range(n_dams)], looks_per_dam)
    offsets = np.concatenate([rng.choice(1800, looks_per_dam, replace=False) for _ in range(n_dams)])
    shuffle = rng.permutation(len(dam))
    return dict(dam=dam[shuffle], dates=days(*offsets[shuffle]), offsets=offsets[shuffle],
                is_record=rng.random(len(dam)) < 0.8, y=(rng.random(len(dam)) < 0.25).astype(float),
                p=rng.uniform(0.02, 0.9, len(dam)))


def test_matches_a_plain_loop_over_every_dam_and_day():
    h = random_history()
    R, V, n = frailty.matured_residual_sums(h["dam"], h["dates"], h["is_record"], h["y"], h["p"])
    for i in range(0, len(h["dam"]), 7):                       # every 7th forecast, checked by hand
        same_dam_final = (h["dam"] == h["dam"][i]) & h["is_record"] & (h["offsets"] + 120 <= h["offsets"][i])
        assert n[i] == same_dam_final.sum()
        assert R[i] == pytest.approx((h["y"] - h["p"])[same_dam_final].sum(), abs=1e-12)
        assert V[i] == pytest.approx((h["p"] * (1 - h["p"]))[same_dam_final].sum(), abs=1e-12)


def test_truncation_placebo_is_bit_identical():
    # Scramble every record whose answer is not final by the cut (issued on or after cut - 120 days),
    # and every record of another dam. Every forecast before the cut must keep EXACTLY the same sums.
    h = random_history()
    base = frailty.matured_residual_sums(h["dam"], h["dates"], h["is_record"], h["y"], h["p"])
    cut = 1000
    not_final = h["offsets"] >= cut - 120
    other_dam = h["dam"] == "dam07"
    scrambled_y, scrambled_p = h["y"].copy(), h["p"].copy()
    scrambled_y[not_final | other_dam] = 1.0 - scrambled_y[not_final | other_dam]
    scrambled_p[not_final | other_dam] = 0.5
    after = frailty.matured_residual_sums(h["dam"], h["dates"], h["is_record"], scrambled_y, scrambled_p)
    keep = (h["offsets"] < cut) & ~other_dam
    for before_values, after_values in zip(base, after):
        assert (before_values[keep] == after_values[keep]).all()      # bit for bit, not approx
    assert (base[0][~keep] != after[0][~keep]).any()                  # the scramble did change something
    # Deleting those rows outright (as a real truncation would) gives the same bits too.
    kept = frailty.matured_residual_sums(h["dam"][keep], h["dates"][keep], h["is_record"][keep],
                                         h["y"][keep], h["p"][keep])
    for before_values, kept_values in zip(base, kept):
        assert (before_values[keep] == kept_values).all()


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------
def test_one_member_fusion_is_that_member():
    p_T = np.array([0.1, 0.5, 0.9])
    assert np.allclose(fusion.sigmoid(fusion.fuse_members({"T": p_T})), p_T)


def test_equal_weights_and_seed_averaging_on_the_logit_scale():
    p_T = np.array([0.2])
    seeds = [np.array([0.3]), np.array([0.5]), np.array([0.7])]       # logits -0.847, 0, +0.847: mean 0
    z = fusion.fuse_members({"T": p_T, "S": seeds})
    assert z[0] == pytest.approx(np.log(0.2 / 0.8) / 2)


def test_anchor_with_frailty_adds_b_on_the_log_odds_scale():
    history = pd.DataFrame({"row": [0, 1], "uid": ["a", "a"], "issue_date": days(0, 200)})
    out = fusion.anchor_with_frailty(history, {"T": np.array([0.2, 0.3])}, np.array([1.0, np.nan]),
                                     np.array([True, False]))
    b = 0.8 / (0.16 + 100)
    assert out["frailty_b"].iloc[1] == pytest.approx(b)
    assert out["p"].iloc[1] == pytest.approx(fusion.sigmoid(np.log(0.3 / 0.7) + b))
    assert out["p"].iloc[0] == pytest.approx(0.2)                     # nothing final yet: unchanged


def synthetic_table(n_dams=12, seed=0):
    """Two looks a month per dam, 2005-2017, with random features and labels (no real data)."""
    from damdays.models import g2
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2005-01-01", "2017-06-30", freq="SMS")
    table = pd.DataFrame({"uid": np.repeat([f"dam{i:02d}" for i in range(n_dams)], len(dates)),
                          "issue_date": np.tile(dates, n_dams)})
    n = len(table)
    table["at_risk_D0"] = rng.random(n) > 0.1
    table["label_ok"] = rng.random(n) > 0.15
    table["y_D0"] = (rng.random(n) < 0.2).astype(float)
    table["warm"] = np.isin(table["issue_date"].dt.month, [10, 11, 12, 1, 2, 3])   # read by g2.fit_and_predict
    table["hydro_year"] = table["issue_date"].dt.year
    for column in g2.g2_features("D0"):
        table[column] = rng.random(n)
    return table


def test_tree_member_is_the_g2_recipe_and_history_stops_at_the_block_end():
    from damdays.models import g2
    table = synthetic_table()
    tree, info = fusion.fit_tree_member(table, "D0", "VAL")
    issued = pd.to_datetime(tree["issue_date"])
    assert issued.min() < pd.Timestamp("2009-01-01") and issued.max() < pd.Timestamp("2016-01-01")
    assert info["fit_rows"] == int(fusion.rows.p1_fit_rows(table, "D0", "VAL").sum())
    reference, _ = g2.fit_and_predict(table, "D0", "VAL", "G2")
    val = fusion.block_part(tree, "VAL")
    assert (val["uid"].to_numpy() == reference["uid"].to_numpy()).all()
    assert np.allclose(val["p_T"].to_numpy(), reference["p"].to_numpy(), atol=1e-9)


def test_r30_headline_is_never_below_d0():
    r30 = pd.DataFrame({"row": [5, 7], "p": [0.30, 0.10]})
    d0 = pd.DataFrame({"row": [7, 5, 9], "p": [0.20, 0.05, 0.50]})
    p, share = fusion.r30_headline(r30, d0)
    assert p.tolist() == [0.30, 0.20] and share == 0.5
    with pytest.raises(AssertionError):
        fusion.r30_headline(pd.DataFrame({"row": [1], "p": [0.1]}), d0)
