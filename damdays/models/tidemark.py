"""Tidemark: every DamDays forecast from one entry point.

    from damdays.models import tidemark
    model = tidemark.fit_tidemark("2009-01-01", rung="L1")   # learns only from answers final before the cutoff
    out = tidemark.predict_tidemark(model)                    # forecasts for the block the cutoff opens

    out["p1"]       one row per dam and satellite look ("issue") at which the dam still has water
    out["p2_dam"]   one row per dam-like dam and 1 July season
    out["p2_cell"]  one row per 2 km cell and 1 July season

Every rung (L0 to L3, below) is fitted and forecast by these same two calls, and
returns the same columns (p1_output_columns; a member the rung does not use is
blank). scripts/12_ladder_val.py runs all four on VAL for the PREREG ladder table.

docs/HOW_IT_WORKS.md explains every part in plain language, and PREREG.md
("Model") fixes the recipe. Nothing is tuned here: every setting lives in the
component module named in brackets below.

The parts, in the order they are built
--------------------------------------
1. 90-day members, one model per event kind (R30, D0, D0g), listed in MEMBERS [fusion]
     T  LightGBM on the 29 G2c features (+ the 2 water-balance columns at rung L3)
     S  sequence net (TCN + tabular MLP), 3 seeds    [nets]  (rung L2)
     M  tabular MLP, 3 seeds                         [nets]  (rung L2)
2. Fusion: the plain mean of the members' log-odds [fusion.fuse_members]
3. Frailty: the dam's own correction b = R / (V + 100), learned from its past
   forecasts whose answer was final [frailty]
4. R30 headline: p90_R30 = max(p90_R30, p90_D0), because a dry dam is also
   below a third [fusion.r30_headline]
5. Runway curve: the hazard model H gives 30/60/90/180 days; R30 curve >= D0 curve [hazard]
6. DamDays floor: a 10% quantile of the days to R30, plus a split-conformal shift [uncertainty]
7. Season band: the region-year offsets seen in an inner backtest of THIS recipe [uncertainty]
8. Season rating (P2): LightGBM boosted from the dam's own past dry-season rate [season_rating]

Rungs (PREREG "Fallback ladder"): which members a model fuses
-------------------------------------------------------------
L0  T alone, no frailty, no max rule (the benchmark G2)
L1  T + frailty + max rule                                   <- scripts/08_tidemark_val.py
L2  T + S + M + frailty + max rule                           <- nets [nets]; scripts/09_nets_val.py
L3  L2 with the 2 water-balance columns in T and H           <- physics [physics]; scripts/10_physics_val.py
Parts 5-8 are the same on every rung (at L3, H also gets the water-balance columns).
All four are fitted through fit_tidemark; scripts/12_ladder_val.py builds the PREREG ladder table.

How the nets and the physics plug in
------------------------------------
* Nets: MEMBERS["S"] and MEMBERS["M"] have a fit and a predict function (see
  Member; damdays.models.nets). Fusion averages whatever members a rung lists;
  a member's seeds are averaged on the log-odds scale first.
* Physics: load_inputs adds the columns in PHY_COLUMNS to the P1 table (built by
  damdays.models.physics, a bucket water balance + Kalman filter + 20 analogue
  rain years). Rung L3 passes them to T and H as extra inputs; S and M do not use them.

The time rules (no peeking)
---------------------------
A model fitted at cutoff C only learns from answers that were final before C:
* 90-day members: issue + 90 days + 30 days to confirm an event < C (rows.p1_fit_rows);
* H: each 30/30/30/90-day interval is kept only once its own answer is final (censoring);
* floor: forecasts whose 365-day answer (+ 30 days) was final before its fit cutoff;
* band: an inner backtest fitted at an EARLIER cutoff C' and judged on forecasts
  answered before the next cutoff;
* P2: seasons answered before the block's first 1 July rating.
When forecasting, the frailty of an issue on day t uses the dam's past
forecasts only once their answer is final (t_j + 120 days <= t), and every
input is causal (docs/FEATURES.md, tests/test_no_lookahead.py).
"""
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd

from damdays import config
from damdays.features import store
from damdays.models import frailty, fusion, hazard, nets, physics, rows
from damdays.models import season_rating as sr
from damdays.models import uncertainty as unc

P1_KINDS = rows.P1_KINDS                     # ("R30", "D0", "D0g")
CURVE_KINDS = hazard.CURVE_KINDS             # ("R30", "D0"): the runway curve
HORIZONS = hazard.HORIZONS                   # (30, 60, 90, 180) days
PHY_COLUMNS = physics.PHY_COLUMNS            # ("ph_p_R30", "ph_p_D0"): the two water-balance columns (rung L3)
P_MIN, P_MAX = fusion.P_MIN, fusion.P_MAX


# ===========================================================================
# Settings: what a cutoff means
# ===========================================================================
# Each cutoff opens one block of forecasts. Everything fitted for it only knows answers final before it.
#   floor_fit_cutoff   the floor's quantile model learns from answers final before this date
#   floor_calibration  (first issue, cutoff) of the forecasts that set the conformal shift; they must
#                      not be the quantile model's own fit rows (split conformal). None: no such block
#                      exists (VAL: the quantile model already uses every forecast answered before
#                      2009), so the floor is the raw 10% quantile (shift 0).
#   band_blocks        inner backtests (first issue, cutoff) whose region-year offsets form the band
SETTINGS = {
    "VAL": dict(cutoff=config.VAL_START, floor_fit_cutoff=config.VAL_START, floor_calibration=None,
                band_blocks=unc.BAND_INNER_BLOCKS["VAL"]),
    "TEST": dict(cutoff=config.TEST_START, floor_fit_cutoff=config.VAL_START,
                 floor_calibration=(config.VAL_START, config.TEST_START),
                 band_blocks=unc.BAND_INNER_BLOCKS["TEST"]),
}


def setting_for(cutoff):
    """The block a cutoff opens: "2009-01-01" (or "VAL") -> "VAL"; "2016-07-01" (or "TEST") -> "TEST"."""
    if cutoff in SETTINGS:
        return cutoff
    block = block_opened_by(cutoff)
    if block is not None:
        return block
    raise ValueError(f"No setting for cutoff {cutoff!r}. Known: "
                     + ", ".join(f"{s['cutoff']} ({n})" for n, s in SETTINGS.items())
                     + ". A production cutoff (the latest labelled date) is not built yet.")


def block_opened_by(cutoff):
    """"VAL" or "TEST" if `cutoff` is the first day of that block, else None (an inner-backtest cutoff)."""
    try:
        day = pd.Timestamp(cutoff)
    except (ValueError, TypeError):
        raise ValueError(f"Cutoff {cutoff!r} is not a date (or VAL / TEST).") from None
    for name, setting in SETTINGS.items():
        if day == pd.Timestamp(setting["cutoff"]):
            return name
    return None


# ===========================================================================
# Members and rungs
# ===========================================================================
@dataclass(frozen=True)
class Member:
    """One 90-day forecaster that fusion averages.

    fit(inputs, kind, fit_rows, setup, seed)        -> a fitted model
    predict(fitted, inputs, row_positions, setup)   -> P(event) for those rows of the P1 table
      inputs    the tables (load_inputs)
      fit_rows  positions in the P1 table of the rows it may learn from (answers final before the cutoff)
      setup     member_setup(): the kind, the cutoff, extra inputs (PHY) and replaced columns
    A member without functions is listed but not built yet; a rung that needs it refuses to fit.
    """
    name: str
    about: str
    seeds: tuple
    fit: Optional[Callable] = None
    predict: Optional[Callable] = None

    @property
    def built(self):
        """True once the member has both a fit and a predict function."""
        return self.fit is not None and self.predict is not None


def fit_tree_member(inputs, kind, fit_rows, setup, seed):
    """T: one LightGBM with G2's settings on the G2c features (+ any extra inputs), learned from fit_rows."""
    table = inputs["p1"]
    features = fusion.tree_features(kind, setup["extra_features"])
    y = table[rows.p1_label(kind)].to_numpy()[fit_rows].astype(int)
    return fusion.fit_tree(fusion.tree_inputs(table, fit_rows, features, setup["replace"]), y, seed)


def predict_tree_member(model, inputs, row_positions, setup):
    """T's probability for the P1 rows at row_positions."""
    features = fusion.tree_features(setup["kind"], setup["extra_features"])
    return fusion.predict_tree(model, inputs["p1"], row_positions, features, setup["replace"])


MEMBERS = {
    "T": Member("T", "LightGBM on the 29 G2c features (+ PHY at L3), all waterbodies, G2's settings",
                seeds=(0,), fit=fit_tree_member, predict=predict_tree_member),
    # The nets are multi-task: one net per seed serves all three kinds (trained on the first kind's call).
    "S": Member("S", "causal TCN on the 24 complete months before the issue + tabular MLP, 3 seeds [nets]",
                seeds=nets.SEEDS, fit=nets.fit_sequence_member, predict=nets.predict_net_member),
    "M": Member("M", "MLP on the 64 tabular inputs, 3 seeds [nets]",
                seeds=nets.SEEDS, fit=nets.fit_tabular_member, predict=nets.predict_net_member),
}


@dataclass(frozen=True)
class Rung:
    """One rung of the PREREG fallback ladder: which members are fused and which extras are on."""
    name: str
    about: str
    members: tuple
    frailty: bool = True
    max_rule: bool = True
    extra_features: tuple = ()


RUNGS = {
    "L0": Rung("L0", "the benchmark G2: T alone", ("T",), frailty=False, max_rule=False),
    "L1": Rung("L1", "T + per-dam frailty + R30 max rule + hazard curve (no nets)", ("T",)),
    "L2": Rung("L2", "L1 + the nets S and M (no water-balance columns)", ("T", "S", "M")),
    "L3": Rung("L3", "full Tidemark: L2 + the 2 water-balance columns in T and H", ("T", "S", "M"),
               extra_features=PHY_COLUMNS),
}


def ready_rung(rung, registry=MEMBERS, table=None):
    """The Rung to fit (given by name or as a Rung); refuses one whose members or columns are not built yet."""
    if isinstance(rung, str):
        if rung not in RUNGS:
            raise ValueError(f"Unknown rung {rung!r}; expected one of {sorted(RUNGS)}")
        rung = RUNGS[rung]
    missing = [name for name in rung.members if name not in registry or not registry[name].built]
    if missing:
        raise NotImplementedError(f"Rung {rung.name} needs member(s) {missing}, which are not built yet. "
                                  "Give them fit and predict functions in tidemark.MEMBERS.")
    if table is not None:
        absent = [c for c in rung.extra_features if c not in table.columns]
        if absent:
            raise NotImplementedError(f"Rung {rung.name} needs the P1 column(s) {absent} (physics module).")
    return rung


# ===========================================================================
# Inputs
# ===========================================================================
def load_inputs():
    """Every table Tidemark reads, from data_cache/features (built by scripts/01 and 02).

    p1       the P1 issue table (keys, dam history, neighbours, rain): one row per at-risk satellite look
             (the rain percentiles are read by the nets S and M only), plus the 2 water-balance
             columns PHY_COLUMNS once scripts/10_physics_val.py has built them (damdays.models.physics)
    p2_dam   the P2 season table with the area index added (one row per waterbody and 1 July)
    p2_cell  the P2 2 km cell table
    The nets also read each dam's monthly history (damdays.features.sequences); it
    is built from data_cache on first use (nets.default_monthly_history).
    """
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    p1 = physics.with_physics_columns(store.load_p1(groups=("keys", "dam", "nbr", "rain")))
    return dict(p1=p1,
                p2_dam=sr.add_area_index(store.load_p2("dam"), attrs),
                p2_cell=store.load_p2("cell"))


# ===========================================================================
# 1-4. The 90-day probabilities
# ===========================================================================
def member_fit_rows(table, kind, cutoff):
    """Positions of the P1 rows the 90-day members learn from when fitted at `cutoff`.

    At a block's first day (VAL 2009-01-01, TEST 2016-07-01) these are the
    official purged fit rows (rows.p1_fit_rows). At an inner-backtest cutoff
    (e.g. 2002-01-01) they are the at-risk, labelled rows answered before it.
    TIME: either way, issue + 90 days + 30 days to confirm an event < cutoff.
    """
    block = block_opened_by(cutoff)
    if block is not None:
        return np.flatnonzero(rows.p1_fit_rows(table, kind, block))
    return np.flatnonzero(unc.answered_fit_rows(table, kind, cutoff))


def member_setup(table, kind, cutoff, extra_features=()):
    """What every member needs to know about one kind and cutoff (passed to Member.fit and .predict).

    replace  columns a member must read instead of the stored ones. TIME: the
             stored dam_rate_K shrinks toward a regional rate made from answers
             final before 2009-01-01. A model fitted at an EARLIER cutoff (the
             inner backtest) must not know those later answers, so it gets the
             rate recomputed as of its own cutoff (uncertainty.dam_rate_as_of).
    """
    replace = {}
    if pd.Timestamp(cutoff) < pd.Timestamp(config.VAL_START):
        replace[f"dam_rate_{kind}"] = unc.dam_rate_as_of(table, kind, cutoff)
    return dict(kind=kind, cutoff=str(pd.Timestamp(cutoff).date()), extra_features=tuple(extra_features),
                replace=replace)


def fit_members(inputs, rung, cutoff, registry=MEMBERS):
    """Fit every member of the rung, for every kind, at `cutoff`.

    Returns (fitted {kind: {member: [one model per seed]}}, setups {kind: setup}, info {kind: sizes}).
    """
    table = inputs["p1"]
    fitted, setups, info = {}, {}, {}
    for kind in P1_KINDS:
        setups[kind] = member_setup(table, kind, cutoff, rung.extra_features)
        fit_rows = member_fit_rows(table, kind, cutoff)
        fitted[kind] = {name: [registry[name].fit(inputs, kind, fit_rows, setups[kind], seed)
                               for seed in registry[name].seeds] for name in rung.members}
        y = table[rows.p1_label(kind)].to_numpy()[fit_rows]
        info[kind] = dict(cutoff=setups[kind]["cutoff"], fit_rows=int(len(fit_rows)), fit_events=int(np.sum(y)),
                          members=list(rung.members), dam_rate="as of the cutoff" if setups[kind]["replace"]
                          else "stored (regional prior from answers final before 2009-01-01)")
    return fitted, setups, info


def history_positions(table, kind, until):
    """Positions of every at-risk `kind` issue dated before `until`.

    TIME: these are the rows the members predict. The frailty of an issue needs
    the anchor on the same dam's EARLIER issues (from 1988 on), so they are all
    predicted, not only the block being forecast. Predicting an old issue uses
    nothing it should not: its inputs are causal and the models are fixed.
    """
    before = pd.to_datetime(table["issue_date"]).to_numpy() < np.datetime64(pd.Timestamp(until))
    return np.flatnonzero(before & table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool))


def member_probabilities(fitted, setup, inputs, row_positions, rung, registry=MEMBERS):
    """{member: probabilities} on the given rows. A member with several seeds gives a list (one per seed)."""
    out = {}
    for name in rung.members:
        seeds = [registry[name].predict(model, inputs, row_positions, setup) for model in fitted[name]]
        out[name] = seeds[0] if len(seeds) == 1 else seeds
    return out


def anchor_and_frailty(keys, member_p, table, kind, rung):
    """Fuse the members into the anchor, then add the dam's frailty (if the rung uses it).

    keys  row, uid, issue_date of the predicted rows
    Returns keys + p_<member>, p_anchor, frailty_b, frailty_R, frailty_V, frailty_n and p.
    """
    positions = keys["row"].to_numpy()
    if rung.frailty:
        y = table[rows.p1_label(kind)].to_numpy(dtype=float)[positions]
        is_record = fusion.track_record_mask(table, kind, positions)     # label determinable and known
        out = fusion.anchor_with_frailty(keys, member_p, y, is_record)
    else:
        out = keys[["row", "uid", "issue_date"]].reset_index(drop=True).copy()
        out["p_anchor"] = np.clip(fusion.sigmoid(fusion.fuse_members(member_p)), P_MIN, P_MAX)
        for column in ("frailty_b", "frailty_R", "frailty_V"):
            out[column] = 0.0
        out["frailty_n"] = 0
        out["p"] = out["p_anchor"].to_numpy()
    for name, p in member_p.items():              # each member alone (seeds fused), for diagnostics
        out[f"p_{name}"] = p if not isinstance(p, list) else np.clip(fusion.sigmoid(fusion.member_logit(p)),
                                                                     P_MIN, P_MAX)
    return out


def predict_p90(fitted, setups, inputs, rung, until, registry=MEMBERS):
    """The 90-day probabilities on every at-risk issue before `until`, for each kind.

    Returns {kind: table}: row (position in the P1 table), uid, issue_date,
    p_<member>, p_anchor (fused members), frailty_b/R/V/n, p (the final 90-day
    probability; R30 after the max rule) and, for R30, p_premax.
    """
    table = inputs["p1"]
    history = {}
    for kind in P1_KINDS:
        positions = history_positions(table, kind, until)
        keys = pd.DataFrame({"row": positions, "uid": table["uid"].astype(str).to_numpy()[positions],
                             "issue_date": table["issue_date"].to_numpy()[positions]})
        member_p = member_probabilities(fitted[kind], setups[kind], inputs, positions, rung, registry)
        history[kind] = anchor_and_frailty(keys, member_p, table, kind, rung)
    # R30 headline: never below the D0 probability of the same issue (same row of the P1 table).
    history["R30"]["p_premax"] = history["R30"]["p"].to_numpy()
    if rung.max_rule:
        history["R30"]["p"], _ = fusion.r30_headline(history["R30"], history["D0"])
    return history


def values_on_rows(history, row_positions, column="p"):
    """A history column read on the given P1 rows (every row must be in the history)."""
    lookup = pd.Series(history[column].to_numpy(), index=history["row"].to_numpy())
    values = lookup.reindex(np.asarray(row_positions)).to_numpy()
    if np.isnan(values.astype(float)).any():
        raise AssertionError(f"Some rows have no {column} in the history table.")
    return values


# ===========================================================================
# 6. The DamDays floor
# ===========================================================================
def calibration_rows(table, first_issue, cutoff):
    """At-risk R30 forecasts with a determinable label issued from `first_issue` up to `cutoff` (the
    conformal calibration candidates; shift_from_answers_before keeps those answered before the cutoff)."""
    dates = pd.to_datetime(table["issue_date"])
    return (np.asarray((dates >= pd.Timestamp(first_issue)) & (dates < pd.Timestamp(cutoff)))
            & table[rows.p1_at_risk_column(unc.FLOOR_KIND)].to_numpy(dtype=bool)
            & table["label_ok"].to_numpy(dtype=bool))


def fit_floor(table, setting):
    """The floor's quantile model and its conformal shift for one setting. Returns (floor dict, info).

    TIME: the quantile model learns from forecasts whose 365-day answer (+ 30
    days to confirm) was final before its fit cutoff. The shift comes from
    LATER forecasts (not the fit rows: split conformal) whose answer was final
    before the setting's cutoff.
    """
    started = time.time()
    model, info = unc.fit_floor_model(table, setting["floor_fit_cutoff"])
    shift, n_calibration, about = 0.0, 0, "no calibration block before this cutoff, so the raw 10% quantile"
    if setting["floor_calibration"] is not None:
        first_issue, cutoff = setting["floor_calibration"]
        calib = calibration_rows(table, first_issue, cutoff)
        log_q10 = unc.predict_log_q10(model, table, calib)
        shift, n_calibration = unc.shift_from_answers_before(
            log_q10, unc.runway_days(table.loc[calib]), table.loc[calib, "issue_date"], cutoff)
        about = f"split conformal on forecasts issued {first_issue} to {cutoff} and answered before {cutoff}"
    floor = dict(model=model, shift=float(shift), calibration_rows=int(n_calibration), about=about,
                 fit_cutoff=str(setting["floor_fit_cutoff"]))
    info.update(shift=float(shift), calibration_rows=int(n_calibration), about=about,
                seconds=round(time.time() - started))
    return floor, info


def predict_floor(floor, table, mask):
    """log q10, the floor in days, and the floor as displayed (whole days, 180 meaning "180+") for rows in mask."""
    log_q10 = unc.predict_log_q10(floor["model"], table, mask)
    days = unc.floor_days(log_q10, floor["shift"])
    return log_q10, days, unc.displayed_floor_days(days)


# ===========================================================================
# 7. The season band (inner backtest of this same recipe)
# ===========================================================================
def fit_band(inputs, rung, setting, registry=MEMBERS, log=None):
    """Band constants {kind: (low, high)} from inner backtests of this rung. Returns (band, info).

    For each inner block (first issue S, cutoff C): the 90-day members are fitted
    at S, the frailty and max rule are added as usual, and each region-year's
    offset (the log-odds shift that would have made its forecasts right on
    average) is measured on the primary-set forecasts issued from S and answered
    before C. The band is [lowest, highest] offset over all blocks (PREREG).
    TIME: the inner models learn only from answers final before S (their
    dam_rate prior recomputed as of S); every offset uses answers final before C.
    """
    table = inputs["p1"]
    offsets = {kind: [] for kind in P1_KINDS}
    info = {"blocks": []}
    for first_issue, cutoff in setting["band_blocks"]:
        started = time.time()
        fitted, setups, fit_info = fit_members(inputs, rung, first_issue, registry)
        history = predict_p90(fitted, setups, inputs, rung, until=cutoff, registry=registry)
        name = f"{first_issue[:4]}-{cutoff[:4]}"
        for kind in P1_KINDS:
            mask = unc.band_rows(table, kind, first_issue, cutoff)
            p = values_on_rows(history[kind], np.flatnonzero(mask))
            part = table.loc[mask]
            offsets[kind].append(unc.block_offsets(part[rows.p1_label(kind)].to_numpy(dtype=float), p,
                                                   part["region"], part["issue_date"], name))
        info["blocks"].append(dict(block=name, fit=fit_info, seconds=round(time.time() - started)))
        if log:
            log(f"band: inner block {name} fitted and scored ({info['blocks'][-1]['seconds']} s)")
    band = {kind: unc.pooled_band(*offsets[kind]) for kind in P1_KINDS}
    info["band"] = band
    info["offsets"] = {kind: pd.concat(offsets[kind], ignore_index=True).to_dict("records") for kind in P1_KINDS}
    return band, info


# ===========================================================================
# The fitted model, and the two entry points
# ===========================================================================
@dataclass
class TidemarkModel:
    """Everything fit_tidemark learned at one cutoff; predict_tidemark turns it into forecasts."""
    rung: Rung
    setting: str          # "VAL" or "TEST": the block this model forecasts
    cutoff: str
    members: dict         # {kind: {member: [one fitted model per seed]}}
    setups: dict          # {kind: member_setup()}
    registry: dict        # the Member registry the members came from
    curves: dict          # {kind: hazard model} for R30 and D0
    floor: dict           # fit_floor()
    band: dict            # {kind: (low, high)} log-odds offsets
    rating: dict          # season_rating.fit_rating()
    info: dict            # fit sizes, offsets and timings, for reports


def fit_tidemark(cutoff, rung="L1", inputs=None, registry=MEMBERS, log=None):
    """Fit every part of Tidemark on answers final before `cutoff`. Returns a TidemarkModel.

    cutoff   "2009-01-01" (or "VAL": the validation setting) or "2016-07-01" (or "TEST")
    rung     "L0" to "L3" (PREREG fallback ladder), or a Rung
    inputs   the tables (load_inputs()); loaded from data_cache when not given
    registry the Member registry (MEMBERS; tests can add a made-up member)
    log      optional function that receives progress messages
    """
    say = log or (lambda message: None)
    setting_name = setting_for(cutoff)
    setting = SETTINGS[setting_name]
    inputs = inputs if inputs is not None else load_inputs()
    table = inputs["p1"]
    rung = ready_rung(rung, registry, table)
    info = dict(rung=rung.name, rung_about=rung.about, setting=setting_name, cutoff=setting["cutoff"])

    started = time.time()
    fitted, setups, info["members"] = fit_members(inputs, rung, setting["cutoff"], registry)
    info["members_seconds"] = round(time.time() - started)
    say(f"90-day members {list(rung.members)} fitted for {list(P1_KINDS)} ({info['members_seconds']} s)")

    started = time.time()
    curves, info["curves"] = hazard.fit_curves(table, setting_name, "dam_like", rung.extra_features)
    say(f"runway curve H fitted for {list(CURVE_KINDS)} ({round(time.time() - started)} s)")

    floor, info["floor"] = fit_floor(table, setting)
    say(f"floor model fitted on {info['floor']['fit_rows']:,} forecasts; shift {floor['shift']:+.4f}")

    band, info["band"] = fit_band(inputs, rung, setting, registry, log)
    say("season band: " + ", ".join(f"{k} [{lo:+.3f}, {hi:+.3f}]" for k, (lo, hi) in band.items()))

    started = time.time()
    rating, info["rating"] = sr.fit_rating(inputs["p2_dam"], setting_name, "main")
    info["rating"]["seconds"] = round(time.time() - started)
    say(f"season rating fitted on {info['rating']['fit_seasons']:,} seasons ({info['rating']['seconds']} s)")
    return TidemarkModel(rung=rung, setting=setting_name, cutoff=setting["cutoff"], members=fitted, setups=setups,
                         registry=registry, curves=curves, floor=floor, band=band, rating=rating, info=info)


def predict_tidemark(model, inputs=None):
    """Every forecast for the block the model's cutoff opens (VAL: issues 2009-2015).

    Returns {"p1": ..., "p2_dam": ..., "p2_cell": ...}; the module docstring
    lists the columns. The 90-day members also predict the dams' earlier issues,
    which the frailty needs (only answers final by each issue date count).
    """
    inputs = inputs if inputs is not None else load_inputs()
    table = inputs["p1"]
    block = model.setting
    history = predict_p90(model.members, model.setups, inputs, model.rung, until=fusion.BLOCK_END[block],
                          registry=model.registry)
    p1 = p1_frame(table, block)
    add_p90(p1, history, model)
    add_curves(p1, hazard.predict_curves(model.curves, table, block, model.rung.extra_features), table, block)
    add_floor(p1, model.floor, table, block)
    p2_dam, p2_cell = predict_season_rating(model.rating, inputs, block)
    return dict(p1=in_output_order(p1, model.registry), p2_dam=p2_dam, p2_cell=p2_cell)


def p1_output_columns(registry=MEMBERS):
    """The columns of predict_tidemark's p1 table, in order. They are the same on every rung (L0 to L3).

    A member the rung does not use has a blank column (the nets at L0 and L1), and a rung
    without the frailty has frailty 0 (L0), so the tables of different rungs line up column for
    column (scripts/12_ladder_val.py compares them).
    """
    columns = ["row", "uid", "issue_date", "region", "at_risk_R30"]
    for kind in P1_KINDS:
        columns += [f"p90_{kind}"] + (["p90_R30_premax"] if kind == "R30" else []) + [f"anchor_{kind}"]
        columns += [f"p_{name}_{kind}" for name in registry]
        columns += [f"frailty_b_{kind}", f"frailty_n_{kind}", f"band_low_{kind}", f"band_high_{kind}"]
    columns += ["frailty_label"]
    columns += [f"curve_{kind}_{h}" for kind in CURVE_KINDS for h in HORIZONS]
    columns += ["floor_log_q10", "floor_days", "floor_shown"]
    return columns


def in_output_order(p1, registry):
    """The p1 table with exactly the columns of p1_output_columns, in that order (checked)."""
    expected = p1_output_columns(registry)
    if sorted(p1.columns) != sorted(expected):
        raise AssertionError(f"predict_tidemark's p1 columns differ from p1_output_columns: "
                             f"extra {sorted(set(p1.columns) - set(expected))}, "
                             f"missing {sorted(set(expected) - set(p1.columns))}")
    return p1[expected]


# ===========================================================================
# Assembling the outputs
# ===========================================================================
def p1_frame(table, block):
    """One row per issue in `block` at which the dam has water (at risk of D0): the rows every P1 output shares.

    Every at-risk R30 issue is one of them (a dam at least 30% full has water);
    columns that only apply to R30 (the R30 probability and curve, the floor)
    are blank on the other rows.
    """
    positions = np.flatnonzero(rows.p1_block_rows(table, "D0", block))
    if (rows.p1_block_rows(table, "R30", block) & ~rows.p1_block_rows(table, "D0", block)).any():
        raise AssertionError("Some at-risk R30 issues are not at-risk D0 issues.")
    return pd.DataFrame({"row": positions, "uid": table["uid"].astype(str).to_numpy()[positions],
                         "issue_date": table["issue_date"].to_numpy()[positions],
                         "region": table["region"].astype(str).to_numpy()[positions],
                         "at_risk_R30": table["at_risk_R30"].to_numpy(dtype=bool)[positions]})


def place(frame, row_positions, values):
    """values (one per row position) placed on the frame's rows; blank where the frame row is not listed."""
    where = pd.Index(frame["row"].to_numpy()).get_indexer(np.asarray(row_positions))
    if (where < 0).any():
        raise AssertionError("Some rows are not in the P1 output frame.")
    out = np.full(len(frame), np.nan)
    out[where] = np.asarray(values, dtype=float)
    return out


def add_p90(p1, history, model):
    """The 90-day probabilities, their parts and their season band, for each kind (columns ..._<kind>).

    Every member of the registry gets a column p_<member>_<kind>, also on rungs that do not use it
    (blank there: e.g. the nets S and M at L0 and L1), so every rung returns the same columns.
    """
    block_rows = {kind: fusion.block_part(history[kind], model.setting) for kind in P1_KINDS}
    for kind in P1_KINDS:
        part = block_rows[kind]
        positions = part["row"].to_numpy()
        p1[f"p90_{kind}"] = place(p1, positions, part["p"])
        if kind == "R30":
            p1["p90_R30_premax"] = place(p1, positions, part["p_premax"])
        p1[f"anchor_{kind}"] = place(p1, positions, part["p_anchor"])
        for name in model.registry:
            used = name in model.rung.members
            p1[f"p_{name}_{kind}"] = place(p1, positions, part[f"p_{name}"]) if used else np.nan
        for column in ("frailty_b", "frailty_n"):
            p1[f"{column}_{kind}"] = place(p1, positions, part[column])
        low, high = unc.band_probabilities(part["p"].to_numpy(), model.band[kind])
        p1[f"band_low_{kind}"] = place(p1, positions, low)
        p1[f"band_high_{kind}"] = place(p1, positions, high)
    # Plain-language per-dam label: the farmer's headline kind (R30) where it applies, else D0.
    b = np.where(p1["at_risk_R30"].to_numpy(), p1["frailty_b_R30"].to_numpy(), p1["frailty_b_D0"].to_numpy())
    p1["frailty_label"] = frailty.frailty_label(b)


def add_curves(p1, curves, table, block):
    """The runway curve at 30/60/90/180 days for R30 (after the max rule) and D0."""
    for kind in CURVE_KINDS:
        positions = np.flatnonzero(rows.p1_block_rows(table, kind, block))
        for h in HORIZONS:
            p1[f"curve_{kind}_{h}"] = place(p1, positions, curves[kind][f"p_{h}"])


def add_floor(p1, floor, table, block):
    """The DamDays floor for every at-risk R30 issue: log q10, days, and days as displayed."""
    mask = rows.p1_block_rows(table, unc.FLOOR_KIND, block)
    log_q10, days, shown = predict_floor(floor, table, mask)
    positions = np.flatnonzero(mask)
    p1["floor_log_q10"] = place(p1, positions, log_q10)
    p1["floor_days"] = place(p1, positions, days)
    p1["floor_shown"] = place(p1, positions, shown)


def predict_season_rating(rating, inputs, block):
    """P2 for every dam-like dam and every 2 km cell rated in `block` (cell p = product of its dams' p)."""
    dams = sr.predict_rating(rating, inputs["p2_dam"], block)
    cells = inputs["p2_cell"].loc[rows.p2_block_rows(inputs["p2_cell"], block)].reset_index(drop=True)
    p2_cell = pd.DataFrame({"uid": cells["uid"].astype(str).to_numpy(), "issue_date": cells["issue_date"].to_numpy(),
                            "season": cells["season"].to_numpy(), "region": cells["region"].astype(str).to_numpy(),
                            "n_dams": cells["n_dams"].to_numpy(),
                            "p": sr.cell_probability(dams, cells, "p"), "p_g": sr.cell_probability(dams, cells, "p_g")})
    p2_dam = dams[["uid", "issue_date", "season", "region", "hex_id", "p", "p_g", "p_start", "p_start_g"]].copy()
    return p2_dam, p2_cell


def summary(model):
    """A JSON-friendly description of a fitted model (no fitted objects): rung, fit sizes, band, floor shift.

    info["band"] holds the inner-backtest blocks and every region-year offset; band_constants the band itself.
    """
    return dict(model.info, band_constants={k: list(v) for k, v in model.band.items()},
                floor_shift=model.floor["shift"], members_about={n: model.registry[n].about for n in model.rung.members})
