"""Tests of the nets S and M (damdays.models.nets) and their 24-month inputs (damdays.features.sequences).

What is proved here, on small made-up data (no real data, a few seconds):
  * the sequence window is the 24 months BEFORE the issue month: changing the
    issue month or anything later leaves a sequence unchanged, while changing
    the month before does change it;
  * the TCN is causal: changing later months never changes the summary of earlier ones;
  * input statistics come from the fit rows only, and missing values get a flag;
  * a masked (row, head) pair, such as an abrupt-only D0-gradual window, does
    not affect training;
  * S and M plug into Tidemark: rung L2 fits, each net is trained once per
    seed for all three kinds (one multi-task net), the heads learn from exactly
    Tidemark's fit rows, and fusion averages the seeds on the log-odds scale;
  * a trained net is saved, and a second run with the same data loads it
    instead of training again; changed data trains afresh.
"""
import numpy as np
import pandas as pd
import pytest
import torch

from damdays.features import sequences as seq
from damdays.models import fusion, nets, rows, tidemark
from test_tidemark import synthetic_inputs

VAL_CUTOFF = "2009-01-01"


# ---------------------------------------------------------------------------
# Made-up monthly history and P1 table with every net input
# ---------------------------------------------------------------------------
def synthetic_history(uids, last_month="2016-12", seed=0):
    """A MonthlyHistory with random values for the given dams (January 1986 to last_month)."""
    rng = np.random.default_rng(seed)
    n_months = int(seq.month_index([pd.Timestamp(last_month)])[0]) + 1
    shape = (len(uids), n_months)
    observed = (rng.random(shape) < 0.7).astype(np.float32)
    pc = np.where(observed > 0, rng.uniform(0, 100, shape), np.nan)
    pc_ffill, months_since = seq.carry_forward(pc, observed > 0)
    dry_ffill, _ = seq.carry_forward(rng.random(shape), observed > 0)
    log_rain = rng.uniform(0, 5, shape).astype(np.float32)
    return seq.MonthlyHistory(uids=np.array(sorted(uids)), pc_ffill=pc_ffill, observed=observed,
                              months_since=months_since, dry_ffill=dry_ffill, log_rain=log_rain,
                              rain_anomaly=(log_rain - 2.5).astype(np.float32), data_end=pd.Timestamp(last_month))


def net_world(seed=3, n_dams=12):
    """tidemark-style inputs with every net input column and a monthly history."""
    inputs = synthetic_inputs(seed=seed, n_dams=n_dams)
    p1 = inputs["p1"]
    rng = np.random.default_rng(seed)
    for column in nets.TABULAR_INPUTS:
        if column not in p1.columns:
            p1[column] = rng.normal(size=len(p1)).astype(np.float32)
    p1["full_c"] = rng.uniform(20, 100, len(p1))
    inputs["monthly_history"] = synthetic_history(p1["uid"].unique(), seed=seed)
    return inputs


@pytest.fixture()
def private_checkpoints(tmp_path, monkeypatch):
    """Keep test checkpoints out of data_cache/nets, and start with no nets in memory."""
    monkeypatch.setattr(nets, "CHECKPOINT_DIR", tmp_path / "nets")
    monkeypatch.setattr(nets, "_TRAINED", {})
    monkeypatch.setattr(nets, "_TABLE_INPUTS", {})
    return tmp_path / "nets"


# ---------------------------------------------------------------------------
# Sequences: the window ends the month before the issue month
# ---------------------------------------------------------------------------
def test_window_is_the_24_complete_months_before_the_issue_month():
    issue = seq.month_index([pd.Timestamp("2014-07-09")])
    months = seq.window_months(issue)[0]
    assert len(months) == seq.SEQUENCE_MONTHS == 24
    assert seq.month_start(months[[0, -1]]).strftime("%Y-%m").tolist() == ["2012-07", "2014-06"]
    leaky = seq.window_months(issue, window_end_offset=0)[0]                  # the planted leak in the look-ahead test
    assert seq.month_start(leaky[[-1]]).strftime("%Y-%m").tolist() == ["2014-07"]


def test_sequences_ignore_the_issue_month_and_later():
    history = synthetic_history(["a", "b"])
    dam_row, issue_month = seq.sequence_rows(history, ["a", "b"], pd.to_datetime(["2010-03-05", "2010-03-25"]))
    before = seq.issue_sequences(history, dam_row, issue_month, [50.0, np.nan])
    later = issue_month[0]                                  # March 2010 and every month after it
    for name in ("pc_ffill", "observed", "months_since", "dry_ffill", "log_rain", "rain_anomaly"):
        getattr(history, name)[:, later:] = 7.0
    assert np.array_equal(before, seq.issue_sequences(history, dam_row, issue_month, [50.0, np.nan]))
    history.log_rain[:, later - 1] += 1.0                   # February 2010 IS in the window
    assert not np.array_equal(before, seq.issue_sequences(history, dam_row, issue_month, [50.0, np.nan]))
    assert before.shape == (2, 24, len(seq.CHANNELS))


def test_level_normaliser_falls_back_to_the_window_maximum():
    levels = np.array([[10.0, 40.0, np.nan], [np.nan, np.nan, np.nan]])
    assert np.allclose(seq.level_normaliser([np.nan, 0.0], levels), [40.0, 1.0])
    assert np.allclose(seq.level_normaliser([80.0, 60.0], levels), [80.0, 60.0])


def test_fingerprints_change_when_any_number_changes():
    x = np.random.default_rng(0).normal(size=(5, 24, 9)).astype(np.float32)
    y = x.copy()
    y[3, 17, 4] = np.nextafter(y[3, 17, 4], np.float32(np.inf))           # the smallest possible change
    a, b = seq.fingerprints(x), seq.fingerprints(y)
    assert (a == b).tolist() == [True, True, True, False, True]


# ---------------------------------------------------------------------------
# The networks
# ---------------------------------------------------------------------------
def test_tcn_never_looks_at_later_months():
    torch.manual_seed(0)
    tcn = nets.CausalTCN(n_channels=9, width=8, kernel=3, dilations=(1, 2, 4, 8))
    x = torch.randn(4, 24, 9)
    changed = x.clone()
    changed[:, 15:] = torch.randn(4, 9, 9)                  # months 15-23 change
    with torch.no_grad():
        a, b = tcn.every_month(x), tcn.every_month(changed)
    assert torch.equal(a[:, :, :15], b[:, :, :15])          # months 0-14 are untouched
    assert not torch.equal(a[:, :, 15:], b[:, :, 15:])


def test_scaler_statistics_come_from_the_fit_rows_only():
    fit = np.array([[1.0, np.nan], [3.0, 2.0], [5.0, 4.0]], dtype=np.float32)
    scaler = nets.TabularScaler.fit(fit)
    assert np.allclose(scaler.mean, [3.0, 3.0]) and scaler.flagged.tolist() == [1]     # column 1 is missing once
    other = np.array([[1e6, np.nan]], dtype=np.float32)                  # a later, extreme row
    out = scaler.transform(other)
    assert out.shape == (1, 3) and out[0, 0] == nets.NET_SETTINGS["clip_spreads"] and out[0, 1] == 0 and out[0, 2] == 1


def test_masked_pairs_do_not_count_in_the_loss():
    logits = torch.tensor([[0.3, -1.0, 2.0], [1.5, 0.2, -0.7]])
    labels = torch.tensor([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    heads = torch.tensor([[1.0, 1.0, 0.0], [1.0, 1.0, 1.0]])           # row 0's D0g head is masked
    flipped = labels.clone()
    flipped[0, 2] = 1.0
    assert torch.equal(nets.masked_loss(logits, labels, heads), nets.masked_loss(logits, flipped, heads))


def test_the_tabular_inputs_are_allowed_and_causal_columns():
    assert len(nets.TABULAR_INPUTS) == 43
    assert not {"full", "wet_share", "fill_share", "dam_like", "region", "uid"} & set(nets.TABULAR_INPUTS)


# ---------------------------------------------------------------------------
# S and M inside Tidemark (rung L2)
# ---------------------------------------------------------------------------
def test_nets_plug_into_tidemark_as_multitask_members(private_checkpoints):
    inputs = net_world()
    rung = tidemark.ready_rung("L2")
    fitted, setups, info = tidemark.fit_members(inputs, rung, VAL_CUTOFF)
    for name in ("S", "M"):
        trained = [head.trained for head in fitted["R30"][name]]
        assert len(trained) == 3                                                  # 3 seeds
        for kind in rows.P1_KINDS:                                                # one net per seed, all kinds
            assert all(h.trained is t for h, t in zip(fitted[kind][name], trained))
            assert [h.kind for h in fitted[kind][name]] == [kind] * 3
        plan = nets.training_plan(inputs, VAL_CUTOFF)
        for j, kind in enumerate(rows.P1_KINDS):                                  # heads learn Tidemark's rows
            expected = tidemark.member_fit_rows(inputs["p1"], kind, VAL_CUTOFF)
            assert np.array_equal(plan.rows[plan.heads[:, j]], expected)
        missing_d0g = np.isnan(inputs["p1"]["y_D0g"].to_numpy()[plan.rows])
        assert missing_d0g.any() and not plan.heads[missing_d0g, 2].any()        # abrupt-only D0g: masked
    history = tidemark.predict_p90(fitted, setups, inputs, rung, until="2016-01-01")
    for kind in rows.P1_KINDS:
        h = history[kind]
        positions = h["row"].to_numpy()
        seeds = [nets.predict_net_member(head, inputs, positions, setups[kind]) for head in fitted[kind]["S"]]
        s_fused = fusion.sigmoid(np.mean([fusion.logit(p) for p in seeds], axis=0))
        assert np.allclose(h["p_S"].to_numpy(), np.clip(s_fused, fusion.P_MIN, fusion.P_MAX), rtol=0, atol=1e-12)
        anchor = fusion.sigmoid(np.mean([fusion.logit(h[f"p_{m}"]) for m in ("T", "S", "M")], axis=0))
        assert np.allclose(h["p_anchor"].to_numpy(), anchor, rtol=0, atol=1e-9)   # equal thirds on log-odds


def test_a_saved_net_is_reloaded_and_changed_data_retrains(private_checkpoints):
    inputs = net_world(seed=4)
    first = nets.trained_net(inputs, "M", VAL_CUTOFF, 0)
    assert nets.checkpoint_path("M", VAL_CUTOFF, 0).exists()
    nets._TRAINED.clear()
    again = nets.trained_net(inputs, "M", VAL_CUTOFF, 0)
    assert again.info.get("loaded_from_checkpoint")
    positions = np.arange(50)
    assert np.array_equal(first.probabilities(inputs, positions, "D0"), again.probabilities(inputs, positions, "D0"))
    inputs["p1"] = inputs["p1"].assign(rel=inputs["p1"]["rel"] + 0.5)           # the data changed (a new table)
    nets._TRAINED.clear()
    changed = nets.trained_net(inputs, "M", VAL_CUTOFF, 0)
    assert not changed.info.get("loaded_from_checkpoint")


def test_a_new_monthly_history_is_read_even_with_the_same_table(private_checkpoints):
    """Regression (review of step 9): the cached inputs were keyed by the table only, so the same table with a
    different monthly history silently kept the OLD sequences (and the old cached log-odds)."""
    inputs = net_world(seed=5)
    positions = np.arange(40)
    first = nets.table_inputs(inputs).sequences(positions)
    trained = nets.trained_net(inputs, "S", VAL_CUTOFF, 0)
    p_first = trained.probabilities(inputs, positions, "D0")
    other = dict(inputs, monthly_history=synthetic_history(inputs["p1"]["uid"].unique(), seed=99))
    assert not np.array_equal(first, nets.table_inputs(other).sequences(positions))
    assert not np.array_equal(p_first, trained.probabilities(other, positions, "D0"))
    assert np.array_equal(p_first, trained.probabilities(inputs, positions, "D0"))     # and back again


def test_the_tcn_summary_reads_all_24_months():
    torch.manual_seed(0)
    tcn = nets.CausalTCN(n_channels=9, width=8, kernel=3, dilations=nets.NET_SETTINGS["tcn_dilations"])
    x = torch.randn(4, seq.SEQUENCE_MONTHS, 9)
    oldest = x.clone()
    oldest[:, 0] += 1.0                                      # only the oldest month changes
    with torch.no_grad():
        assert not torch.equal(tcn(x), tcn(oldest))         # the last month's summary still sees it


def test_training_is_repeatable(private_checkpoints):
    inputs = net_world(seed=6)
    first = nets.trained_net(inputs, "S", VAL_CUTOFF, 1)
    nets._TRAINED.clear()
    nets.checkpoint_path("S", VAL_CUTOFF, 1).unlink()                              # train again, do not reload
    again = nets.trained_net(inputs, "S", VAL_CUTOFF, 1)
    assert not again.info.get("loaded_from_checkpoint")
    a, b = first.net.state_dict(), again.net.state_dict()
    assert all(torch.equal(a[k], b[k]) for k in a)
