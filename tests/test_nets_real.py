"""The nets S and M on real data: placebo and truncation checks, and hand checks on single dams.

Written for the independent review of the nets (build step 9). Each test is a
way the nets could peek at the future, checked on the real tables:

* FIT ROWS. At each cutoff the nets learn only from forecasts answered before
  it (issue + 90 days + 30 days to confirm < cutoff), and the band's inner
  cutoff (2002) reads the dam_rate columns recomputed as of that cutoff.
* PLACEBO, END TO END (M). Scramble every answer AND every input of the
  forecasts not answered before 1 Jan 2009 (labels, label_ok, all 43 tabular
  columns) and retrain M seed 0: its input statistics and every weight must be
  bit-for-bit the same. Positive control: flipping 50 fit-row answers does
  change the weights.
* PLACEBO, END TO END (S). Scramble the monthly history from September 2008 on
  (the last fit row is issued on 2 Sep 2008, so no fit row's 24-month window
  reaches these months) and retrain S seed 0: every weight must be bit-for-bit
  the saved checkpoint's.
* THE FUTURE OF A VAL FORECAST. On 3,000 real VAL forecasts, scramble the issue
  month and every later month of the monthly history: the sequences, and S's
  log-odds, must not change. Changing only the month before must change them.
* HAND CHECKS. Two named VAL forecasts: the 24-month sequence is rebuilt from
  the raw panel and the SILO file with plain pandas, and must match exactly.
* REPRODUCTION. The saved L2 forecasts (scripts/09) are recomputed from the
  saved nets (data_cache/nets/) on 5,000 VAL rows.
* THE APP. artifacts/val_tidemark_L2.json holds every number the app export
  reads for rung L2 (scripts/11_export_app.py --rung L2).

Needs data_cache/ (scripts/01 and 02); skipped otherwise. The S placebo and the
reproduction also need the saved nets of scripts/09 (skipped without them).
About 3-4 minutes (three M fits of ~15 s, one S fit of ~1-2 min).
"""
import json
import pickle

import numpy as np
import pandas as pd
import pytest
import torch

from damdays import config
from damdays.data.splits import answer_known_before
from damdays.features import sequences as seq
from damdays.features import store
from damdays.models import nets, rows, tidemark
from damdays.models.predictions import load_predictions, prediction_path

VAL_CUTOFF, INNER_CUTOFF = "2009-01-01", "2002-01-01"
SAVED_NETS = nets.CHECKPOINT_DIR     # data_cache/nets (the tests themselves train into a temporary folder)
LAST_FIT_MONTH = "2008-09"           # the last fit row at the VAL cutoff is issued on 2 Sep 2008
# (dam, VAL issue date) forecasts whose sequences are rebuilt by hand
HAND_CHECKED = [("r638mfjz6_v3", "2011-11-15"), ("r645080fs_v3", "2013-02-13")]
KEY_COLUMNS = ["uid", "region", "issue_date", "warm", "at_risk_D0", "at_risk_R30", "label_ok",
               "y_R30", "y_D0", "y_D0g", "b2S_R30", "b2N_R30", "b2S_D0", "b2N_D0", "b2S_D0g", "b2N_D0g"]


@pytest.fixture(scope="module")
def data():
    """A compact P1 table (keys + the net inputs) and the monthly history (skip if data_cache is not built)."""
    needed = [config.CACHE_DIR / n for n in ("panel.pkl", "attributes.pkl", "silo_rain.pkl")]
    if not all(p.exists() for p in needed) or not (store.FEATURES_DIR / "p1_keys.pkl").exists():
        pytest.skip("data_cache/ is not built; run scripts/01_build_data.py and scripts/02_build_features.py")
    p1 = store.load_p1(groups=("keys", "dam", "nbr", "rain"))
    table = p1[KEY_COLUMNS + [c for c in nets.TABULAR_INPUTS if c not in KEY_COLUMNS]].copy()
    del p1
    return dict(table=table, history=nets.default_monthly_history())


@pytest.fixture()
def fresh_nets(tmp_path, monkeypatch):
    """Train into a temporary folder (never data_cache/nets), with nothing remembered from earlier tests."""
    monkeypatch.setattr(nets, "CHECKPOINT_DIR", tmp_path / "nets")
    monkeypatch.setattr(nets, "_TRAINED", {})
    monkeypatch.setattr(nets, "_TABLE_INPUTS", {})
    return tmp_path / "nets"


def inputs_for(table, history):
    """What nets.trained_net reads: the P1 table and the monthly history."""
    return {"p1": table, "monthly_history": history}


def saved_net_path(model, cutoff, seed):
    """data_cache/nets/<cutoff>/<model>_seed<seed>.pt, saved by scripts/09 (skip if it is not there)."""
    path = SAVED_NETS / cutoff / f"{model}_seed{seed}.pt"
    if not path.exists():
        pytest.skip(f"{path} not found; run scripts/09_nets_val.py first")
    return path


def saved_net(model, cutoff, seed):
    """The checkpoint contents of a net saved by scripts/09."""
    return torch.load(saved_net_path(model, cutoff, seed), weights_only=True)


def same_weights(a, b):
    """True if two state dicts hold exactly the same numbers."""
    return a.keys() == b.keys() and all(torch.equal(a[k], b[k]) for k in a)


# ---------------------------------------------------------------------------
# Fit rows
# ---------------------------------------------------------------------------
def test_fit_rows_are_answered_before_each_cutoff(data, fresh_nets):
    table = data["table"]
    dates = pd.to_datetime(table["issue_date"])
    for cutoff in (VAL_CUTOFF, INNER_CUTOFF):
        plan = nets.training_plan(inputs_for(table, data["history"]), cutoff)
        last = dates.iloc[plan.rows].max()
        assert last + pd.Timedelta(days=config.ANSWER_FINAL_DAYS) < pd.Timestamp(cutoff)
        for j, kind in enumerate(nets.KINDS):        # each head learns exactly Tidemark's rows for its kind
            assert np.array_equal(plan.rows[plan.heads[:, j]], tidemark.member_fit_rows(table, kind, cutoff))
        expected_replaced = [] if cutoff == VAL_CUTOFF else ["dam_rate_D0", "dam_rate_D0g", "dam_rate_R30"]
        assert sorted(plan.replace) == expected_replaced


# ---------------------------------------------------------------------------
# Placebo: the future cannot change what the nets learn
# ---------------------------------------------------------------------------
def scrambled_future(table, cutoff, seed=0):
    """A copy of the table in which every forecast NOT answered before `cutoff` has random answers and inputs."""
    rng = np.random.default_rng(seed)
    out = table.copy()
    future = ~answer_known_before(out["issue_date"], cutoff)
    n = int(future.sum())
    for kind in nets.KINDS:
        out.loc[future, f"y_{kind}"] = rng.choice([0.0, 1.0, np.nan], n).astype(np.float32)
    out.loc[future, "label_ok"] = rng.random(n) < 0.5
    for column in nets.TABULAR_INPUTS:
        values = out[column].to_numpy(dtype=np.float64, copy=True)
        values[future] = rng.normal(0, 100, n)
        out[column] = values.astype(out[column].dtype)
    return out, future


def test_placebo_scrambled_future_does_not_change_m(data, fresh_nets):
    table, history = data["table"], data["history"]
    honest = nets.trained_net(inputs_for(table, history), "M", VAL_CUTOFF, 0)

    scrambled, future = scrambled_future(table, VAL_CUTOFF)
    assert future.sum() > 1_000_000                                   # the scramble touches most of the table
    nets._TRAINED.clear()
    nets.checkpoint_path("M", VAL_CUTOFF, 0).unlink()                 # train again, do not reload
    placebo = nets.trained_net(inputs_for(scrambled, history), "M", VAL_CUTOFF, 0)
    assert not placebo.info.get("loaded_from_checkpoint")
    assert placebo.info["signature"] == honest.info["signature"]     # the fingerprint of what it learns from
    assert np.array_equal(honest.scaler.mean, placebo.scaler.mean)     # statistics from the fit rows only
    assert np.array_equal(honest.scaler.spread, placebo.scaler.spread)
    assert same_weights(honest.net.state_dict(), placebo.net.state_dict())

    # Positive control: 50 fit-row answers flipped -> different weights (the comparison can fail).
    flipped = table.copy()
    plan = nets.training_plan(inputs_for(table, history), VAL_CUTOFF)
    some = plan.rows[plan.heads[:, nets.KINDS.index("D0")]][:50]
    flipped.loc[flipped.index[some], "y_D0"] = 1.0 - flipped["y_D0"].to_numpy()[some]
    nets._TRAINED.clear()
    control = nets.trained_net(inputs_for(flipped, history), "M", VAL_CUTOFF, 0)
    assert not same_weights(honest.net.state_dict(), control.net.state_dict())


def test_placebo_scrambled_monthly_history_after_the_fit_rows_does_not_change_s(data, fresh_nets):
    saved = saved_net("S", VAL_CUTOFF, 0)
    table, history = data["table"], data["history"]
    plan = nets.training_plan(inputs_for(table, history), VAL_CUTOFF)
    last_fit_issue = pd.to_datetime(table["issue_date"]).iloc[plan.rows].max()
    assert last_fit_issue.strftime("%Y-%m") == LAST_FIT_MONTH        # its window ends in August 2008
    first = int(seq.month_index([pd.Timestamp(LAST_FIT_MONTH + "-01")])[0])
    rng = np.random.default_rng(1)
    parts = {name: getattr(history, name).copy() for name in
             ("pc_ffill", "observed", "months_since", "dry_ffill", "log_rain", "rain_anomaly")}
    for values in parts.values():
        values[:, first:] = rng.uniform(-50, 150, values[:, first:].shape)
    scrambled = seq.MonthlyHistory(uids=history.uids, data_end=history.data_end, **parts)
    placebo = nets.trained_net(inputs_for(table, scrambled), "S", VAL_CUTOFF, 0)
    assert not placebo.info.get("loaded_from_checkpoint")
    assert placebo.info["signature"] != saved["info"]["signature"]   # it really saw a different history
    assert same_weights(saved["state_dict"], placebo.net.state_dict())


# ---------------------------------------------------------------------------
# The future of a VAL forecast
# ---------------------------------------------------------------------------
def test_scrambling_the_issue_month_and_later_leaves_s_unchanged(data, fresh_nets):
    table, history = data["table"], data["history"]
    prepared = nets.table_inputs(inputs_for(table, history))
    dates = pd.DatetimeIndex(pd.to_datetime(table["issue_date"]))
    val = np.flatnonzero((dates >= VAL_CUTOFF) & (dates < config.VAL_END) & table["at_risk_D0"].to_numpy(bool))
    sample = np.sort(np.random.default_rng(7).choice(val, 3000, replace=False))
    # The issue month, worked out here from the calendar (not with the module's own helper).
    issue_month = (dates.year[sample] - seq.FIRST_YEAR) * 12 + dates.month[sample] - 1
    assert np.array_equal(issue_month, prepared.issue_month[sample])
    honest = prepared.sequences(sample)

    rng = np.random.default_rng(8)
    scrambled = np.empty_like(honest)
    for month in np.unique(issue_month):
        parts = {name: getattr(history, name).copy() for name in
                 ("pc_ffill", "observed", "months_since", "dry_ffill", "log_rain", "rain_anomaly")}
        for values in parts.values():
            values[:, month:] = rng.uniform(-50, 150, values[:, month:].shape)
        future_scrambled = seq.MonthlyHistory(uids=history.uids, data_end=history.data_end, **parts)
        pick = issue_month == month
        scrambled[pick] = seq.issue_sequences(future_scrambled, prepared.dam_row[sample][pick], issue_month[pick],
                                              prepared.full_c[sample][pick])
    assert np.array_equal(honest, scrambled)

    parts = {name: getattr(history, name).copy() for name in
             ("pc_ffill", "observed", "months_since", "dry_ffill", "log_rain", "rain_anomaly")}
    parts["log_rain"][prepared.dam_row[sample], issue_month - 1] += 1.0          # the month BEFORE the issue month
    month_before = seq.issue_sequences(seq.MonthlyHistory(uids=history.uids, data_end=history.data_end, **parts),
                                       prepared.dam_row[sample], issue_month, prepared.full_c[sample])
    assert (month_before != honest).any(axis=(1, 2)).all()

    # Through the network (any weights: causality does not depend on training).
    torch.manual_seed(0)
    net = nets.new_net("S", n_tabular=len(nets.TABULAR_INPUTS)).eval()
    X = torch.from_numpy(np.nan_to_num(nets.raw_tabular(prepared.tabular_columns({}), sample)))
    with torch.no_grad():
        z_honest = net(X, torch.from_numpy(honest))
        z_scrambled = net(X, torch.from_numpy(scrambled))
        z_before = net(X, torch.from_numpy(month_before))
    assert torch.equal(z_honest, z_scrambled)
    assert not torch.equal(z_honest, z_before)


# ---------------------------------------------------------------------------
# Hand checks
# ---------------------------------------------------------------------------
def sequence_by_hand(looks, rain_mm, rain_months, issue, full_c):
    """The 24-month sequence of one forecast, from the dam's raw looks and its SILO cell's monthly rain."""
    log_rain = np.log1p(rain_mm.astype(float))
    months = [issue.to_period("M") - 24 + k for k in range(24)]           # the 24 months before the issue month
    out = []
    for month in months:
        seen = looks[looks["date"].dt.to_period("M") <= month]
        last_month = seen["date"].dt.to_period("M").max()
        last = seen[seen["date"].dt.to_period("M") == last_month]         # carried forward from the last month seen
        code = month.year * 100 + month.month
        normal = log_rain[(rain_months // 100 >= 1960) & (rain_months // 100 <= 1986)
                          & (rain_months % 100 == month.month)].mean()
        this = log_rain[list(rain_months).index(code)]
        out.append([min(max(last["pc_wet"].mean() / full_c, 0.0), 1.5),
                    1.0 if last_month == month else 0.0,
                    min((month - last_month).n, 36) / 12,
                    float((last["px_wet"] == 0).mean()),
                    this / 5.0, this - normal,
                    np.sin(2 * np.pi * (month.month - 1) / 12), np.cos(2 * np.pi * (month.month - 1) / 12),
                    1.0])
    return np.array(out)


def test_hand_checked_sequences(data, fresh_nets):
    table, history = data["table"], data["history"]
    prepared = nets.table_inputs(inputs_for(table, history))
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl").set_index("uid")
    with open(config.CACHE_DIR / "silo_rain.pkl", "rb") as handle:
        rain = pickle.load(handle)
    cells = list(np.asarray(rain["cells"]).astype(str))
    for uid, day in HAND_CHECKED:
        row = np.flatnonzero((table["uid"].astype(str) == uid).to_numpy()
                             & (pd.to_datetime(table["issue_date"]) == pd.Timestamp(day)).to_numpy())
        assert len(row) == 1, f"{uid} {day} is not a P1 forecast"
        looks = panel[panel["uid"].astype(str) == uid].sort_values("date")
        rain_mm = rain["rain"][cells.index(str(attrs.loc[uid, "silo_cell"]))]
        hand = sequence_by_hand(looks, rain_mm, np.asarray(rain["months"]), pd.Timestamp(day),
                                float(table["full_c"].iloc[row[0]]))
        assert np.allclose(prepared.sequences(row)[0], hand, rtol=0, atol=1e-6), f"{uid} {day}"


# ---------------------------------------------------------------------------
# Reproduction of the saved L2 forecasts
# ---------------------------------------------------------------------------
def test_saved_l2_forecasts_reproduce_from_the_saved_nets(data, fresh_nets):
    if not prediction_path("VAL", "tidemark", "L2_p1").exists():
        pytest.skip("run scripts/09_nets_val.py first")
    table, history = data["table"], data["history"]
    saved = load_predictions("VAL", "tidemark", "L2_p1")
    pick = np.sort(np.random.default_rng(9).choice(len(saved), 5000, replace=False))
    positions = saved["row"].to_numpy()[pick]
    inputs = inputs_for(table, history)
    for model in ("S", "M"):
        for seed in nets.SEEDS:
            state = saved_net(model, VAL_CUTOFF, seed)
            trained = nets.load_checkpoint(saved_net_path(model, VAL_CUTOFF, seed), state["info"]["signature"])
            for kind in ("D0", "D0g"):                   # every L2 P1 row is at risk of D0 (R30 rows are a subset)
                p = trained.probabilities(inputs, positions, kind)
                assert np.allclose(p, saved[f"p_{model}{seed}_{kind}"].to_numpy()[pick], rtol=0, atol=1e-6)
    assert rows.P1_KINDS == nets.KINDS


# ---------------------------------------------------------------------------
# The rung-L2 results file holds what the app reads
# ---------------------------------------------------------------------------
def test_l2_results_hold_what_the_app_reads():
    """scripts/11_export_app.py --rung L2 reads the rung's VAL scores from artifacts/val_tidemark_L2.json.

    Regression (review of step 9): the file had no season-rating (p2) section, so the export crashed.
    """
    path = config.ARTIFACTS_DIR / "val_tidemark_L2.json"
    if not path.exists():
        pytest.skip("run scripts/09_nets_val.py first")
    from damdays.export import app_data
    results = json.loads(path.read_text(encoding="utf-8"))
    lines = app_data.limits_text(results, "L2")
    assert not any("nan" in line.lower() for line in lines)
    assert results["p1"]["P1_R30|primary|L2"]["rows"]["scored"] > 0
    l1_path = config.ARTIFACTS_DIR / "val_tidemark_L1.json"
    if l1_path.exists():                       # the nets do not touch the rating: its scores are L1's
        l1 = json.loads(l1_path.read_text(encoding="utf-8"))
        for task, subset in (("P2_cell", "all"), ("P2_dam", "dam_like"), ("P2_dam_g", "dam_like")):
            assert results["p2"][f"{task}|{subset}|L2"]["point"] == l1["p2"][f"{task}|{subset}|L1"]["point"]
