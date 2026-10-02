"""Leakage hunt, part 1: hand checks, shuffle placebos and perturbation tests on real data.

The look-ahead test (test_no_lookahead.py) deletes the future and rebuilds
everything. This file attacks the same question from other sides:

* HAND CHECKS. For a handful of real dams, recompute every causal feature the
  slow way (tests/leak_bruteforce.py: one issue at a time, an explicit date
  condition for every look used) and compare with the stored feature tables.
* SHUFFLE PLACEBOS. Scramble the labels that a feature must NOT be able to see
  yet (answers not final, or the coming season) and check the feature is
  unchanged. A positive control checks that the scramble did change
  something later on, so the test can fail.
* PERTURBATION TESTS. Change the raw data on and after a date (looks after
  1 January, rain in the issue month and later) and check nothing dated
  before it moves.

Tests that encode a fix still to be made are marked xfail(strict=True) with
the fix in the reason. Remove the marker when the fix lands (the test will
then pass, and strict mode makes a forgotten marker fail loudly).

Needs data_cache/ (scripts/01_build_data.py) and data_cache/features/
(scripts/02_build_features.py); skipped otherwise. About 1-2 minutes.
"""
import pickle

import numpy as np
import pandas as pd
import pytest

import leak_bruteforce as bf
from damdays import config
from damdays.data.events import build_events
from damdays.data.rainfall import haversine_km
from damdays.features import checkpoints, dam_history, issues, neighbours, rain, season, spec, store
from damdays.features.common import day_numbers

SEED = 20261002
# The dam used in docs/DATA.md as the worked real example, plus a seeded random sample.
NAMED_DAM = "r638mm01c_v3"
N_RANDOM_DAMS_PER_REGION = 4


# ---------------------------------------------------------------------------
# Fixtures: the data layer, the stored feature tables, and a sample of dams
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def data_layer():
    """panel, attrs, events and SILO rain from data_cache/ (skip if not built)."""
    needed = ["panel.pkl", "attributes.pkl", "events.pkl", "silo_rain.pkl"]
    if not all((config.CACHE_DIR / name).exists() for name in needed):
        pytest.skip("data_cache/ is not built; run scripts/01_build_data.py first")
    with open(config.CACHE_DIR / "silo_rain.pkl", "rb") as f:
        rain_by_cell = pickle.load(f)
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    panel = panel.assign(uid=panel["uid"].astype(str)).sort_values(["uid", "date"]).reset_index(drop=True)
    return {
        "panel": panel,
        "panel_uids": panel["uid"].to_numpy(),      # sorted: one dam's looks are one contiguous slice
        "attrs": pd.read_pickle(config.CACHE_DIR / "attributes.pkl"),
        "events": pd.read_pickle(config.CACHE_DIR / "events.pkl"),
        "rain": rain_by_cell,
    }


@pytest.fixture(scope="module")
def sample_uids(data_layer):
    """The named example dam plus 4 random has_hist dams per region (seeded)."""
    attrs = data_layer["attrs"]
    rng = np.random.default_rng(SEED)
    uids = [NAMED_DAM]
    for region in sorted(config.DEV_REGIONS):
        pool = np.sort(attrs.loc[attrs["has_hist"] & (attrs["region"] == region), "uid"].astype(str).to_numpy())
        uids += list(rng.choice(pool, N_RANDOM_DAMS_PER_REGION, replace=False))
    return uids


@pytest.fixture(scope="module")
def stored(sample_uids):
    """The stored feature tables, P1 cut down to the sampled dams (skip if not built)."""
    if not (store.FEATURES_DIR / "p1_keys.pkl").exists():
        pytest.skip("feature tables not built; run scripts/02_build_features.py first")
    p1 = store.load_p1()
    p1 = p1[p1["uid"].isin(sample_uids)].reset_index(drop=True)
    with open(store.FEATURES_DIR / "neighbour_grid.pkl", "rb") as f:
        grid = pickle.load(f)
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as f:
        prior = pickle.load(f)
    return {"p1": p1, "p2_dam": store.load_p2("dam"), "p2_cell": store.load_p2("cell"),
            "checkpoints": pd.read_pickle(store.FEATURES_DIR / "checkpoints.pkl"),
            "grid": grid, "prior": prior["prior"], "data_end": prior["data_end"]}


_BUNDLES, _LEVELS = {}, {}


def looks_of(data_layer, uid):
    """(dates, days, pc, px) of one dam's looks, oldest first."""
    first = np.searchsorted(data_layer["panel_uids"], uid, side="left")
    last = np.searchsorted(data_layer["panel_uids"], uid, side="right")
    looks = data_layer["panel"].iloc[first:last]
    dates = pd.DatetimeIndex(looks["date"])
    return dates, bf.day_number(dates), looks["pc_wet"].to_numpy(float), looks["px_wet"].to_numpy(float)


def dam_levels(data_layer, uid):
    """(days, rel, px) of one dam, rel against its brute-force checkpoint full (cached; for neighbours)."""
    if uid not in _LEVELS:
        dates, days, pc, px = looks_of(data_layer, uid)
        _LEVELS[uid] = (days, bf.rel_of_looks(pc, dates, bf.full_by_year(days, pc, px, dates)), px)
    return _LEVELS[uid]


def dam_bundle(data_layer, uid):
    """One dam's raw looks, brute-force rel, checkpoints and event start days (cached)."""
    if uid in _BUNDLES:
        return _BUNDLES[uid]
    dates, days, pc, px = looks_of(data_layer, uid)
    fulls = bf.full_by_year(days, pc, px, dates)
    ev = data_layer["events"]
    ev = ev[ev["uid"].astype(str) == uid]
    starts = {
        "D0": bf.day_number(ev.loc[ev["kind"] == "D0", "start_date"]),
        "R30": bf.day_number(ev.loc[ev["kind"] == "R30", "start_date"]),
        "D0g": bf.day_number(ev.loc[(ev["kind"] == "D0") & ev["gradual"], "start_date"]),
        "D0ab": bf.day_number(ev.loc[(ev["kind"] == "D0") & ~ev["gradual"], "start_date"]),
    }
    attrs = data_layer["attrs"].assign(uid=data_layer["attrs"]["uid"].astype(str)).set_index("uid")
    bundle = {
        "uid": uid, "dates": dates, "days": days, "pc": pc, "px": px, "months": dates.month.to_numpy(),
        "fulls": fulls, "rel": bf.rel_of_looks(pc, dates, fulls), "starts": starts,
        "full_static": float(attrs.loc[uid, "full"]), "events": ev,
        "checkpoint": {y: bf.checkpoint_stats(days, pc, px, dates, y)
                       for y in range(config.FIRST_CHECKPOINT_YEAR, config.LAST_CHECKPOINT_YEAR + 1)},
    }
    _BUNDLES[uid] = bundle
    return bundle


def assert_close(name, got, expected, rtol=2e-4, atol=2e-6):
    """Compare stored (float32) values with brute-force (float64) ones; NaN must match NaN."""
    got, expected = np.asarray(got, float), np.asarray(expected, float)
    both_nan = np.isnan(got) & np.isnan(expected)
    close = np.isclose(got, expected, rtol=rtol, atol=atol) | both_nan
    bad = np.flatnonzero(~close)
    assert len(bad) == 0, (f"{name}: {len(bad)} of {len(got)} differ; first: got {got[bad[:5]]}, "
                           f"expected {expected[bad[:5]]}")


# ---------------------------------------------------------------------------
# 1. Checkpoints: "full" and friends may only use looks before 1 January
# ---------------------------------------------------------------------------
def test_checkpoints_match_a_hand_count(data_layer, stored, sample_uids):
    """Stored checkpoint stats equal a direct count over looks dated before 1 Jan of the year."""
    ck = stored["checkpoints"]
    for uid in sample_uids:
        b = dam_bundle(data_layer, uid)
        rows = ck[ck["uid"].astype(str) == uid].set_index("year")
        for year in (1988, 1995, 2003, 2009, 2016):
            if year not in rows.index:
                continue
            for stat, expected in b["checkpoint"][year].items():
                assert_close(f"{uid} {year} {stat}", [rows.loc[year, stat]], [expected])


def test_checkpoints_ignore_every_look_from_1_january_on(data_layer, sample_uids):
    """Scrambling all looks from 1 Jan Y on leaves checkpoints 1987..Y unchanged (and changes a later one)."""
    rng = np.random.default_rng(SEED)
    changed_later = False
    for uid in sample_uids:
        b = dam_bundle(data_layer, uid)
        hydro = np.where(b["months"] >= 7, b["dates"].year, b["dates"].year - 1)
        reference = checkpoints.dam_checkpoints(b["days"], b["pc"], b["px"], b["months"], hydro)
        for year in (1996, 2009, 2016):
            future = b["days"] >= bf.first_of_january(year)
            pc, px = b["pc"].copy(), b["px"].copy()
            pc[future] = rng.uniform(0, 100, future.sum())
            px[future] = np.round(pc[future] / 10)
            scrambled = checkpoints.dam_checkpoints(b["days"], pc, px, b["months"], hydro)
            known = checkpoints.CHECKPOINT_YEARS <= year
            for stat in checkpoints.STATS:
                assert np.array_equal(reference[stat][known], scrambled[stat][known], equal_nan=True), \
                    f"{uid}: checkpoint {stat} for a year <= {year} moved when looks from {year} on changed"
                changed_later |= not np.array_equal(reference[stat][~known], scrambled[stat][~known],
                                                    equal_nan=True)
    assert changed_later, "positive control: scrambling the future never changed a later checkpoint"


# ---------------------------------------------------------------------------
# 2. Dam history: every window ends at the issue's own look
# ---------------------------------------------------------------------------
HISTORY_COLUMNS = ["rel", "last3", "max365", "min365", "low365_D0", "low365_R30", "s60", "s120", "rec",
                   "since_full", "since_arm", "armed", "since_low_D0", "since_low_R30", "gap_prev",
                   "clim_dd", "clim_fast", "dtt_trend_D0", "dtt_clim_D0", "dtt_fast_D0",
                   "dtt_trend_R30", "dtt_clim_R30", "dtt_fast_R30"]
CHECKPOINT_COLUMNS = ["full_c", "wet_share_c", "fill_share_c", "n_hist_c"]


def test_dam_history_features_match_a_hand_count(data_layer, stored, sample_uids):
    """Every dam-history feature of the sampled dams' P1 rows equals a brute-force count over looks <= D."""
    p1 = stored["p1"]
    rng = np.random.default_rng(SEED)
    for uid in sample_uids:
        b = dam_bundle(data_layer, uid)
        rows = p1[p1["uid"] == uid]
        # 120 random rows per dam (the brute force is slow), plus the docs/DATA.md example dates.
        example = rows["issue_date"].between(pd.Timestamp("2019-10-01"), pd.Timestamp("2019-12-31")).to_numpy()
        picked = np.zeros(len(rows), bool)
        picked[rng.choice(len(rows), min(120, len(rows)), replace=False)] = True
        rows = rows[picked | example]
        j_of_day = {d: j for j, d in enumerate(b["days"])}
        look_index = np.array([j_of_day[d] for d in bf.day_number(rows["issue_date"])])
        expected = {c: [] for c in HISTORY_COLUMNS + CHECKPOINT_COLUMNS + ["anom_own"]}
        for j in look_index:
            year = bf.checkpoint_year(b["dates"][j].year)
            ck = b["checkpoint"][year]
            feats = bf.history_at(j, b["days"], b["rel"], b["px"], b["months"], ck)
            for c in HISTORY_COLUMNS:
                expected[c].append(feats[c])
            for c in CHECKPOINT_COLUMNS:
                expected[c].append(ck[c])
            clim = bf.own_climatology(b["dates"][j].year, b["dates"][j].month, b["days"], b["rel"], b["px"])
            expected["anom_own"].append(b["rel"][j] - clim)
        for c, values in expected.items():
            # dtt_* is log(1 + days): a relative tolerance on days of ~1e-4 is ~1e-4 absolute here.
            atol = 2e-4 if c.startswith("dtt") else 2e-6
            assert_close(f"{uid} {c}", rows[c].to_numpy(), values, atol=atol)
        for c in ("rel", "s60", "max365", "anom_own", "full_c"):     # not a vacuous NaN == NaN pass
            assert np.isfinite(expected[c]).mean() > 0.5, f"{uid}: {c} mostly unknown, check is too weak"


def test_single_dam_example_from_the_data_docs(data_layer, stored):
    """docs/DATA.md's real example, dam r638mm01c_v3 in spring 2019, checked by hand.

    On 5 Nov 2019 the dam was 26.32% wet. Its "full" (pre-2016; from 2016 on
    the checkpoint equals it) is 84.21%, so rel = 26.32 / 84.21 = 0.3126: still
    at risk for R30. R30 started on 13 Nov (8 days later) and a gradual D0 on
    15 Dec (40 days later), both inside (D, D + 90], so all three labels are 1.
    The rain window ends in October (the month before November).
    Then: cut the dam's own history after 5 Nov and recompute its features
    with the feature code. Nothing on 5 Nov may change.
    """
    row = stored["p1"][(stored["p1"]["uid"] == NAMED_DAM) & (stored["p1"]["issue_date"] == "2019-11-05")].iloc[0]
    assert row["pc"] == pytest.approx(26.32, abs=0.01) and row["full_c"] == pytest.approx(84.21, abs=0.01)
    assert row["rel"] == pytest.approx(26.32 / 84.21, rel=1e-4)
    assert row["at_risk_R30"] and row["label_ok"]
    assert (row["y_R30"], row["y_D0"], row["y_D0g"]) == (1, 1, 1)
    assert (row["lab_tte_R30"], row["lab_tte_D0"]) == (8, 40)
    assert row["rain_month"] == 201910

    b = dam_bundle(data_layer, NAMED_DAM)
    ck = stored["checkpoints"]
    ck = ck[ck["uid"].astype(str) == NAMED_DAM].set_index("year")
    years = [bf.checkpoint_year(y) for y in b["dates"].year]
    history = {s: np.array([ck.loc[y, s] if y in ck.index else np.nan for y in years], float)
               for s in checkpoints.STATS}
    own_clim = np.zeros(len(b["days"]))              # any fixed array: it only enters as rel - own_clim
    full = dam_history.dam_features(b["days"], b["dates"], b["pc"], b["px"], history, own_clim)
    j = int(np.flatnonzero(b["days"] == bf.day_number(["2019-11-05"])[0])[0])
    cut = slice(0, j + 1)                            # looks up to and including 5 Nov 2019
    truncated = dam_history.dam_features(b["days"][cut], b["dates"][cut], b["pc"][cut], b["px"][cut],
                                         {s: v[cut] for s, v in history.items()}, own_clim[cut])
    for name in full:
        assert np.array_equal(np.asarray(full[name], float)[j], np.asarray(truncated[name], float)[j],
                              equal_nan=True), f"{name} on 5 Nov 2019 changed when later looks were cut"


def test_no_row_uses_the_last_silo_month(data_layer, stored):
    """The last SILO month (Sep 2026) is a partial total (11.8 mm against a 1990-2025 minimum of 15.4 mm).

    No P1 or P2 row may use it. True by construction today (the panel ends
    14 Sep 2026, so the latest window ends in August); this keeps it true if
    looks after September are ever added without refreshing the rain.
    """
    last_month = int(np.max(data_layer["rain"]["months"]))
    assert stored["p1"]["rain_month"].max() < last_month
    assert (stored["p2_dam"]["season"].max() * 100 + 6) < last_month


# ---------------------------------------------------------------------------
# 3. Labels: an event counts if it starts in (D, D + 90]
# ---------------------------------------------------------------------------
def test_labels_match_a_hand_count(data_layer, stored, sample_uids):
    """y_D0, y_R30, y_D0g, n_obs_win and label_ok equal a direct count over the events table."""
    p1 = stored["p1"]
    data_end_day = int(bf.day_number([stored["data_end"]])[0])
    for uid in sample_uids:
        b = dam_bundle(data_layer, uid)
        rows = p1[p1["uid"] == uid]
        expected = [bf.labels_at(D, b["days"], b["starts"], data_end_day) for D in bf.day_number(rows["issue_date"])]
        for c in ("y_D0", "y_R30", "y_D0g", "n_obs_win", "label_ok"):
            assert_close(f"{uid} {c}", rows[c].to_numpy(float), [e[c] for e in expected], rtol=0, atol=0)


# ---------------------------------------------------------------------------
# 4. Track record (B2): a past forecast counts only once its answer is final
# ---------------------------------------------------------------------------
def test_events_are_confirmed_within_30_days_of_their_start(data_layer):
    """Why +120 days is enough: every event is confirmed at most 30 days after it starts.

    A forecast on day t has its window end at t + 90; an event starting then
    is confirmed by t + 120. If confirmation could take longer, the B2 counts
    could use an answer that was not yet final.
    """
    events = data_layer["events"]
    lag = (events["confirm_date"] - events["start_date"]).dt.days
    assert lag.max() <= config.CONFIRM_GAP_DAYS
    assert config.ANSWER_FINAL_DAYS == config.HORIZON_DAYS + config.CONFIRM_GAP_DAYS


def all_look_labels(b, data_end_day):
    """At-risk flags and labels of EVERY look of a dam (also pre-1988 and not-at-risk ones), brute force."""
    labels = [bf.labels_at(D, b["days"], b["starts"], data_end_day) for D in b["days"]]
    at_risk = {"D0": b["px"] > 0, "R30": b["pc"] / b["full_static"] >= config.R30_LEVEL}
    at_risk["D0g"] = at_risk["D0"]
    return labels, at_risk


def test_track_record_matches_a_hand_count(data_layer, stored, sample_uids):
    """b2S_K / b2N_K at sampled rows equal a one-forecast-at-a-time count (answer final by D)."""
    p1 = stored["p1"]
    data_end_day = int(bf.day_number([stored["data_end"]])[0])
    rng = np.random.default_rng(SEED)
    for uid in sample_uids:
        b = dam_bundle(data_layer, uid)
        labels, at_risk = all_look_labels(b, data_end_day)
        rows = p1[p1["uid"] == uid].reset_index(drop=True)
        j_of_day = {d: j for j, d in enumerate(b["days"])}
        issue_days = bf.day_number(rows["issue_date"])
        # 30 random rows, plus rows that sit exactly 120 days after an earlier look (the boundary).
        boundary = np.flatnonzero(np.isin(issue_days, b["days"] + config.ANSWER_FINAL_DAYS))[:10]
        picked = np.unique(np.r_[rng.choice(len(rows), min(30, len(rows)), replace=False), boundary])
        for r in picked:
            i = j_of_day[issue_days[r]]
            for kind in ("D0", "R30", "D0g"):
                hits, total = bf.track_record_at(i, b["days"], b["months"], at_risk[kind], labels, kind)
                assert rows.loc[r, f"b2N_{kind}"] == total, f"{uid} row {r} b2N_{kind}"
                assert rows.loc[r, f"b2S_{kind}"] == hits, f"{uid} row {r} b2S_{kind}"


def test_track_record_ignores_answers_that_are_not_final(data_layer, sample_uids):
    """Shuffle placebo: scramble every answer not final by day T; B2 counts up to day T must not move.

    A forecast on day t_j is final on t_j + 120. Scrambling the labels of all
    forecasts with t_j + 120 > T may change counts after T (positive control)
    but never at a look dated T or earlier.
    """
    rng = np.random.default_rng(SEED)
    changed_after = 0
    for uid in sample_uids:
        b = dam_bundle(data_layer, uid)
        risk = issues.at_risk_flags(b["pc"], b["px"], b["full_static"])
        events = {k: np.sort(v) for k, v in b["starts"].items()}
        label_cols = issues.labels(b["days"], events, int(b["days"].max()))
        reference = issues.track_record(b["days"], b["months"], risk, label_cols)
        for T in rng.choice(b["days"][len(b["days"]) // 4:], 3, replace=False):
            not_final = b["days"] + config.ANSWER_FINAL_DAYS > T
            scrambled = {k: np.array(v, copy=True) for k, v in label_cols.items()}
            for kind in ("D0", "R30", "D0g"):
                scrambled[f"y_{kind}"][not_final] = rng.integers(0, 2, not_final.sum()).astype(float)
            scrambled["label_ok"][not_final] = True
            out = issues.track_record(b["days"], b["months"], risk, scrambled)
            known = b["days"] <= T
            for name in reference:
                assert np.array_equal(reference[name][known], out[name][known]), \
                    f"{uid}: {name} at a look on or before day {T} used an answer that was not final"
                changed_after += int((reference[name][~known] != out[name][~known]).sum())
    assert changed_after > 0, "positive control: scrambling later answers never changed a later count"


def test_dam_rate_is_built_only_from_the_track_record_and_the_prior(stored):
    """dam_rate_K = (b2S_K + 20 * prior) / (b2N_K + 20): no other input can sneak in."""
    p1 = stored["p1"]
    for kind in ("D0", "R30", "D0g"):
        prior = np.array([stored["prior"][(kind, r, bool(w))] for r, w in zip(p1["region"], p1["warm"])])
        expected = (p1[f"b2S_{kind}"].to_numpy(float) + config.B2_SHRINK_P1 * prior) / \
                   (p1[f"b2N_{kind}"].to_numpy(float) + config.B2_SHRINK_P1)
        assert_close(f"dam_rate_{kind}", p1[f"dam_rate_{kind}"].to_numpy(), expected, rtol=1e-6, atol=1e-7)


def test_dam_rate_prior_uses_only_answers_final_before_validation():
    """A TRAIN forecast whose answer is only final after 1 Jan 2009 must not feed the regional prior.

    LEAK-1, fixed: the prior used every TRAIN forecast issued before 2009, so VAL issues in
    Jan-Apr 2009 saw answers not yet final. train_prior_sums now uses splits.fit_mask(dates, "VAL").
    """
    # Both in the cool half-year (Apr-Sep). Final on 2008-07-30 and on 2009-01-18 (= 2008-09-20 + 120 days).
    dates = pd.to_datetime(["2008-04-01", "2008-09-20"])
    at_risk = {"at_risk_D0": np.array([True, True]), "at_risk_R30": np.array([True, True])}
    label_cols = {"label_ok": np.array([True, True]), "y_D0": np.array([0.0, 1.0]),
                  "y_R30": np.array([0.0, 1.0]), "y_D0g": np.array([0.0, 1.0])}
    sums = issues.train_prior_sums("nsw_cw", dates, at_risk, label_cols)
    for kind in ("D0", "R30", "D0g"):
        hits, count = sums[(kind, "nsw_cw", False)]
        assert (hits, count) == (0.0, 1), f"{kind}: the 2008-09-20 forecast (final only on 2009-01-18) was counted"


# ---------------------------------------------------------------------------
# 5. Neighbours: never the dam itself, only looks strictly before the issue
# ---------------------------------------------------------------------------
def test_neighbour_features_match_a_hand_count(data_layer, stored):
    """R_anom, R_chg3, R_zero for a few (dam, issue) pairs, recomputed from every neighbour's raw looks."""
    attrs = data_layer["attrs"]
    studied = attrs[attrs["has_hist"]].assign(uid=lambda a: a["uid"].astype(str)).sort_values("uid")
    studied = studied.reset_index(drop=True)
    uids, lat, lon = studied["uid"].to_numpy(), studied["lat"].to_numpy(), studied["lon"].to_numpy()
    p1 = stored["p1"]
    grid_dates = bf.all_grid_dates(stored["data_end"])
    cases = [(NAMED_DAM, "2019-11-13"), (NAMED_DAM, "2002-12-05")]
    # Plus one sampled wvic dam at the middle and at 90% of its issues that have all three values
    # (in cloudy summers fewer than 5 neighbours have looks, and NaN == NaN would test nothing).
    other = p1[(p1["uid"] != NAMED_DAM) & (p1["region"] == "wvic_sesa")]
    other = other[other["uid"] == other["uid"].iloc[0]]
    other = other[other[["R_anom", "R_chg3", "R_zero"]].notna().all(axis=1)].sort_values("issue_date")
    cases += [(other["uid"].iloc[0], str(d.date())) for d in
              other["issue_date"].iloc[[len(other) // 2, int(len(other) * 0.9)]]]
    lists = neighbours.neighbour_lists(uids, lat, lon)   # the build's own (seeded) lists
    for uid, issue in cases:
        row = p1[(p1["uid"] == uid) & (p1["issue_date"] == pd.Timestamp(issue))]
        if row.empty:      # the date might not be a look of this dam; take its next look
            row = p1[(p1["uid"] == uid) & (p1["issue_date"] >= pd.Timestamp(issue))].iloc[[0]]
        i = int(np.flatnonzero(uids == uid)[0])
        nb = lists[i]
        # Independent checks of the list itself: never the dam, all within 100 km, and every
        # candidate kept when there are at most 300 (sampling to 300 is not a causality question).
        distance = haversine_km(lat[i], lon[i], lat, lon)
        candidates = set(np.flatnonzero(distance < config.NEIGHBOUR_RADIUS_KM)) - {i}
        assert i not in set(nb)
        assert set(nb) <= candidates
        assert len(nb) == min(len(candidates), config.NEIGHBOUR_MAX)
        series = [dam_levels(data_layer, uids[n]) for n in nb]
        expected = bf.neighbour_summary(grid_dates, row["issue_date"].iloc[0], series)
        assert expected["grid_date"] <= row["issue_date"].iloc[0]
        for c in ("R_anom", "R_chg3", "R_zero"):
            assert np.isfinite(expected[c]), f"{uid} {issue} {c} unknown: pick a case where it is known"
            assert_close(f"{uid} {issue} {c}", row[c].to_numpy(), [expected[c]], rtol=1e-4, atol=2e-5)


@pytest.mark.filterwarnings("ignore:Mean of empty slice")   # months with no known level -> NaN, as in build_all
def test_a_dam_is_never_its_own_neighbour_placebo(data_layer, stored):
    """Scramble one dam's own as-of levels: its R_* must not move; its neighbours' R_* must (control)."""
    grid = stored["grid"]
    attrs = data_layer["attrs"].assign(uid=lambda a: a["uid"].astype(str)).set_index("uid")
    # A 0.6-degree box of the NSW region keeps this fast; neighbour lists come from the box only.
    in_box = [k for k, u in enumerate(grid["uids"])
              if -32.3 <= attrs.loc[u, "lat"] <= -31.7 and 148.6 <= attrs.loc[u, "lon"] <= 149.2]
    uids = np.asarray(grid["uids"])[in_box]
    asof, zero = grid["asof"][in_box].copy(), grid["zero"][in_box].copy()
    grid_dates = pd.DatetimeIndex(grid["grid"])
    lists = neighbours.neighbour_lists(uids, attrs.loc[uids, "lat"].to_numpy(), attrs.loc[uids, "lon"].to_numpy())
    clim, _ = neighbours.own_monthly_climatology(asof, grid_dates)
    reference = neighbours.neighbour_features(asof, zero, clim, grid_dates, lists)

    target = 0
    rng = np.random.default_rng(SEED)
    asof[target] = rng.uniform(0, 1.5, asof.shape[1]).astype(np.float32)
    zero[target] = rng.integers(0, 2, zero.shape[1]).astype(np.float32)
    clim2, _ = neighbours.own_monthly_climatology(asof, grid_dates)
    out = neighbours.neighbour_features(asof, zero, clim2, grid_dates, lists)
    for name in reference:
        assert np.array_equal(reference[name][target], out[name][target], equal_nan=True), \
            f"{name} of a dam changed when only its OWN levels changed: it is its own neighbour"
    its_neighbours = [k for k, nb in enumerate(lists) if target in set(nb)]
    assert its_neighbours, "the target dam should be somebody's neighbour"
    assert not np.array_equal(reference["R_zero"][its_neighbours], out["R_zero"][its_neighbours],
                              equal_nan=True), "positive control: the neighbours' R_zero should move"


# ---------------------------------------------------------------------------
# 6. Rain: the window ends the month before the issue; baselines are earlier years
# ---------------------------------------------------------------------------
def test_rain_features_match_a_hand_count(data_layer, stored):
    """rain_month, rain_sum{w} and rain_pctc{w} of random rows equal sums/ranks over the raw monthly rain."""
    raw = data_layer["rain"]
    cell_row = {c: k for k, c in enumerate(np.asarray(raw["cells"]).astype(str))}
    p1 = stored["p1"]
    rows = p1.iloc[np.random.default_rng(SEED).choice(len(p1), 120, replace=False)]
    for _, row in rows.iterrows():
        L = bf.month_before(row["issue_date"])
        assert row["rain_month"] == L
        series = dict(zip(raw["months"].tolist(), raw["rain"][cell_row[row["silo_cell"]]].astype(float).tolist()))
        for w in config.RAIN_WINDOWS_MONTHS:
            assert_close(f"rain_sum{w}", [row[f"rain_sum{w}"]], [bf.rain_total(series, L, w)], rtol=1e-6, atol=1e-3)
            assert_close(f"rain_pctc{w}", [row[f"rain_pctc{w}"]], [bf.rain_percentile(series, L, w)], rtol=0, atol=1e-6)


def perturbed_rain(raw, cells, from_month, rng):
    """Rain for some cells with every month from `from_month` (YYYYMM) on multiplied by random factors."""
    keep = np.isin(np.asarray(raw["cells"]).astype(str), cells)
    clean = {"rain": raw["rain"][keep].astype(np.float64), "months": raw["months"],
             "cells": np.asarray(raw["cells"])[keep]}
    noisy = dict(clean, rain=clean["rain"].copy())
    later = raw["months"] >= from_month
    noisy["rain"][:, later] *= rng.uniform(0.2, 3.0, (keep.sum(), later.sum()))
    return clean, noisy


@pytest.mark.parametrize("from_month", [199003, 200907, 201512, 202003])
def test_rain_features_ignore_the_issue_month_and_later(data_layer, from_month):
    """Perturb rain from month M on: every P1 rain feature for end months before M is unchanged.

    A forecast issued in month M has its window end at M - 1, so this is the
    same as "rain in the issue month or later never matters".
    """
    raw = data_layer["rain"]
    cells = np.asarray(raw["cells"]).astype(str)[::60]
    clean, noisy = perturbed_rain(raw, cells, from_month, np.random.default_rng(SEED))
    a, b = rain.build_rain_features(clean), rain.build_rain_features(noisy)
    before = raw["months"] < from_month
    for name in a["features"]:
        assert np.array_equal(a["features"][name][:, before], b["features"][name][:, before], equal_nan=True), \
            f"{name} at an end month before {from_month} moved when later rain changed"
    assert not np.array_equal(a["features"]["rain_pctc12"][:, ~before], b["features"]["rain_pctc12"][:, ~before],
                              equal_nan=True), "positive control: later percentiles should move"


@pytest.mark.parametrize("season_year", [1995, 2012, 2016, 2021])
def test_season_rain_features_ignore_july_on(data_layer, season_year):
    """P2 rain columns for the 1 Jul issue (deciles, drought10, climatology) ignore rain from July on."""
    raw = data_layer["rain"]
    cells = np.asarray(raw["cells"]).astype(str)[::60]
    clean, noisy = perturbed_rain(raw, cells, season_year * 100 + 7, np.random.default_rng(SEED))
    a = rain.season_rain_features(rain.build_rain_features(clean), cells, np.full(len(cells), season_year))
    b = rain.season_rain_features(rain.build_rain_features(noisy), cells, np.full(len(cells), season_year))
    for name in a:
        assert np.array_equal(a[name], b[name], equal_nan=True), f"P2 {name} for {season_year} saw July rain or later"
    later = rain.season_rain_features(rain.build_rain_features(noisy), cells, np.full(len(cells), season_year + 1))
    earlier = rain.season_rain_features(rain.build_rain_features(clean), cells, np.full(len(cells), season_year + 1))
    assert not np.array_equal(later["rain_sum12"], earlier["rain_sum12"], equal_nan=True), "positive control"


# ---------------------------------------------------------------------------
# 7. Season rating (P2): state from before 1 July, track record from earlier seasons
# ---------------------------------------------------------------------------
P2_STATE_CHECKED = ["rel", "max365", "min365", "armed", "low365_D0", "since_low_D0", "since_full",
                    "dtt_trend_D0", "s60"]


def test_season_rating_uses_only_data_from_before_1_july(data_layer, stored, sample_uids):
    """For the sampled dams' P2 rows: state look < 1 Jul and <= 60 days old, values as hand-computed."""
    p2 = stored["p2_dam"]
    grid = stored["grid"]
    grid_days = bf.day_number(grid["grid"])
    raw = data_layer["rain"]
    cell_row = {c: k for k, c in enumerate(np.asarray(raw["cells"]).astype(str))}
    for uid in sample_uids:
        b = dam_bundle(data_layer, uid)
        rows = p2[p2["uid"].astype(str) == uid]
        k = int(np.flatnonzero(np.asarray(grid["uids"]) == uid)[0])
        rain_series = dict(zip(raw["months"].tolist(), raw["rain"][cell_row[rows["silo_cell"].iloc[0]]].tolist()))
        for _, row in rows.iterrows():
            issue = int(bf.day_number([row["issue_date"]])[0])
            before = np.flatnonzero(b["days"] < issue)
            fresh = len(before) > 0 and issue - b["days"][before[-1]] <= config.P2_MAX_STATE_AGE_DAYS
            assert bool(row["state_stale"]) == (not fresh)
            if fresh:
                j = before[-1]
                assert row["state_day"] == b["days"][j] < issue
                feats = bf.history_at(j, b["days"], b["rel"], b["px"], b["months"],
                                      b["checkpoint"][bf.checkpoint_year(b["dates"][j].year)])
                for c in P2_STATE_CHECKED:
                    assert_close(f"{uid} {row['season']} {c}", [row[c]], [feats[c]], atol=2e-4)
            else:
                assert np.isnan(row["rel"])
            ck = b["checkpoint"][bf.checkpoint_year(int(row["season"]))]
            assert_close(f"{uid} {row['season']} full_c", [row["full_c"]], [ck["full_c"]])
            g = np.searchsorted(grid_days, issue, side="right") - 1     # the 1 Jul grid date itself
            assert grid_days[g] == issue
            assert_close("R_zero", [row["R_zero"]], [grid["R_zero"][k, g]], rtol=0, atol=0)
            assert_close("rain_sum12", [row["rain_sum12"]],
                         [bf.rain_total(rain_series, int(row["season"]) * 100 + 6, 12)], rtol=1e-6, atol=1e-3)


def test_season_rating_dam_rates_equal_the_p1_rates_at_the_state_look(stored):
    """dam_rate_D0/R30 on a P2 row are the P1 values at its state look (when that look is a P1 row)."""
    p1 = stored["p1"].assign(state_day=lambda t: day_numbers(t["issue_date"]))
    p2 = stored["p2_dam"]
    p2 = p2[p2["uid"].isin(set(p1["uid"])) & ~p2["state_stale"]]
    both = p2.merge(p1[["uid", "state_day", "dam_rate_D0", "dam_rate_R30"]], on=["uid", "state_day"],
                    suffixes=("", "_p1"))
    assert len(both) > 50
    for kind in ("D0", "R30"):
        assert_close(f"P2 dam_rate_{kind}", both[f"dam_rate_{kind}"], both[f"dam_rate_{kind}_p1"], rtol=1e-6, atol=1e-7)


SEASON_RECORD_COLUMNS = ["b2S", "b2N", "b2S_g", "b2N_g", "b2S_R30_seasons", "b2N_R30_seasons", "lag1", "lag2",
                         "rate5", "lag1_R30", "rate_R30", "dam_rate_P2", "dam_rate_P2_g"]
CELL_RECORD_COLUMNS = ["b2S", "b2N", "cell_lag1", "cell_rate5"]


def scramble_seasons_from(table, first_season, rng):
    """Copy of the P2 dam table with the labels of season `first_season` and later replaced by noise."""
    out = table.copy()
    later = out["season"] >= first_season
    for label in ("y", "y_g", "y_R30"):
        out.loc[later, label] = rng.integers(0, 2, later.sum()).astype(np.float32)
    out.loc[later, "label_ok"] = rng.random(later.sum()) < 0.9
    return out


@pytest.mark.parametrize("season_year", [2012, 2019])
def test_season_track_record_ignores_the_coming_season(data_layer, stored, season_year):
    """Shuffle placebo: scramble the answers of season Y and later; the record for seasons <= Y must not move.

    The row for season Y is issued on 1 Jul Y, before its own Oct-Mar answer;
    a record that used it (or anything later) would be a leak. Checked for the
    dam table and the cell table. (Y >= 2009 so the TRAIN-season prior is untouched.)
    """
    rng = np.random.default_rng(SEED)
    p2 = stored["p2_dam"].sort_values(["uid", "season"]).reset_index(drop=True)
    reference = season.add_track_record(p2.copy())
    scrambled = season.add_track_record(scramble_seasons_from(p2, season_year, rng))
    known = (reference["season"] <= season_year).to_numpy()
    for c in SEASON_RECORD_COLUMNS:
        assert np.array_equal(reference[c].to_numpy(float)[known], scrambled[c].to_numpy(float)[known],
                              equal_nan=True), f"P2 {c} for a season <= {season_year} saw season {season_year}+"
    assert not np.array_equal(reference["b2S"].to_numpy(float)[~known], scrambled["b2S"].to_numpy(float)[~known]), \
        "positive control: later records should move"

    attrs = data_layer["attrs"].assign(uid=lambda a: a["uid"].astype(str))
    cells_ref = season.build_cell_table(reference, attrs)
    cells_new = season.build_cell_table(scrambled, attrs)
    known = (cells_ref["season"] <= season_year).to_numpy()
    for c in CELL_RECORD_COLUMNS:
        assert np.array_equal(cells_ref[c].to_numpy(float)[known], cells_new[c].to_numpy(float)[known],
                              equal_nan=True), f"cell {c} for a season <= {season_year} saw season {season_year}+"


# ---------------------------------------------------------------------------
# 8. Events (the source of every label and of B2): known on their confirm date
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cut", ["1994-02-11", "2006-11-30", "2019-12-22"])
def test_events_from_truncated_data_are_the_full_events_confirmed_before_the_cut(data_layer, cut):
    """The event state machine never looks ahead: deleting looks from the cut on removes exactly the events
    not yet confirmed by the cut, and changes nothing about the others."""
    attrs = data_layer["attrs"]
    box = attrs[attrs["lat"].between(-32.6, -31.6) & attrs["lon"].between(148.4, 149.4)]
    panel = data_layer["panel"]
    panel = panel[panel["uid"].isin(set(box["uid"]))]
    full = build_events(panel, box)
    truncated = build_events(panel[panel["date"] < pd.Timestamp(cut)], box)
    expected = full[full["confirm_date"] < pd.Timestamp(cut)].reset_index(drop=True)
    pd.testing.assert_frame_equal(truncated.reset_index(drop=True), expected, check_dtype=False)
    assert len(full) > len(expected), "positive control: some events come after the cut"


# ---------------------------------------------------------------------------
# 9. The feature-list guard
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("column", ["at_risk_R30", "elig_rescue_R30", "dam_like", "persistent",
                                    "dam_like_persistent", "lat", "lon", "hex_q", "hex_r", "tile"])
def test_feature_guard_rejects_static_and_location_columns(column):
    """check_feature_list must refuse columns that leak the static pre-2016 values or the location.

    GUARD-1, fixed: these columns were added to spec.FORBIDDEN_COLUMNS.
    """
    with pytest.raises(ValueError):
        spec.check_feature_list(["rel", column])
