"""The production fit: Tidemark fitted on every answer known by the last satellite look.

What it is for
--------------
The app's Runway view shows today's forecast for every dam-like dam. Those
forecasts come from Tidemark fitted at the "production" cutoff of the event
plan: C = the day after the last satellite look in the archive (the last look
is 14 Sep 2026, so C = 15 Sep 2026). The model learns from every answer that
was final by the last look, and forecasts from each dam's latest look.

These forecasts are about the future, so they are never scored. Validation
numbers come from the VAL-setting model (scripts/08), and test numbers from
the TEST-setting model.

Each part, and what "final before C" means for it
--------------------------------------------------
The parts are Tidemark's own (damdays.models.tidemark); only the cutoff is new.
* 90-day members (the rung's MEMBERS, e.g. the tree T): an issue is learned
  from only if issue + 90 days + 30 days to confirm an event < C
  (uncertainty.answered_fit_rows; tidemark.member_fit_rows uses it for any
  cutoff that is not the first day of VAL or TEST). So nothing issued after
  mid-May 2026 is learned from.
* Frailty and the R30 max rule: exactly tidemark.predict_p90. A dam's past
  forecast counts for its frailty once its answer is final (t_j + 120 days <= t).
* Runway curve H: the hazard LightGBM of damdays.models.hazard, on dam-like
  issues before C. Each 30/30/30/90-day interval is kept only once its own
  answer is final (issue + interval end + 30 days < C: censoring).
* DamDays floor: the quantile model learns from answers final before
  1 Jul 2016 (the TRAIN and VAL years); the split-conformal shift comes from
  the forecasts issued from 1 Jul 2016 whose 365-day answer (+30 days) was
  final before C. This is the TEST setting's split, moved one block later.
* Season band: the PREREG band, pooled over the inner blocks 2002-2009 and
  2009-2016 (the same band as the TEST setting).
Because the floor and the band use answers up to 1 Jul 2016, C must be on or
after 1 Aug 2017 (check_production_cutoff refuses an earlier one). For the VAL
and TEST settings use tidemark.fit_tidemark.
Nothing here uses the sealed region.
"""
import pickle
import time
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from damdays import config
from damdays.features import store
from damdays.features.common import day_numbers
from damdays.models import frailty, hazard, rows, tidemark
from damdays.models import uncertainty as unc

PRED_BLOCK, PRED_TASK = "LIVE", "tidemark"     # cache: data_cache/preds/LIVE/tidemark/<rung>_live.pkl
BAND_SETTING = dict(band_blocks=unc.BAND_INNER_BLOCKS["TEST"])   # PREREG: pooled 2002-2009 + 2009-2016


# ---------------------------------------------------------------------------
# The cutoff
# ---------------------------------------------------------------------------
def last_look_date():
    """The date of the newest satellite look in the archive (saved by the feature build)."""
    with open(store.FEATURES_DIR / "dam_rate_prior.pkl", "rb") as handle:
        return pd.Timestamp(pickle.load(handle)["data_end"])


def live_cutoff(last_look):
    """C = the day after the last look: an answer counts if it was final on or before the last look."""
    return pd.Timestamp(last_look) + pd.Timedelta(days=1)


def earliest_production_cutoff():
    """The first cutoff the production recipe may use: TEST_START + 395 days + 1 day (2017-08-01).

    TIME: the floor's quantile model and the band's inner blocks use answers
    final before TEST_START (2016-07-01), and the conformal shift needs at least
    one forecast issued on or after TEST_START whose 365-day answer (+ 30 days)
    is final before the cutoff. An earlier cutoff would either have no
    calibration forecasts or let those parts learn answers from after the cutoff.
    """
    return pd.Timestamp(config.TEST_START) + pd.Timedelta(days=unc.FLOOR_ANSWER_FINAL_DAYS + 1)


def check_production_cutoff(cutoff):
    """Refuse a cutoff the production recipe cannot use without peeking (for VAL or TEST use tidemark.fit_tidemark)."""
    if pd.Timestamp(cutoff) < earliest_production_cutoff():
        raise ValueError(f"Production cutoff {pd.Timestamp(cutoff).date()} is too early: the floor and the band learn "
                         f"from answers up to {config.TEST_START}, so the cutoff must be on or after "
                         f"{earliest_production_cutoff().date()}. For the VAL or TEST setting use "
                         "tidemark.fit_tidemark.")


def floor_setting(cutoff):
    """Where the floor's quantile model and its conformal shift learn from (see the module notes)."""
    check_production_cutoff(cutoff)
    return dict(floor_fit_cutoff=config.TEST_START,
                floor_calibration=(config.TEST_START, str(pd.Timestamp(cutoff).date())))


# ---------------------------------------------------------------------------
# The runway curve H at the production cutoff
# ---------------------------------------------------------------------------
def hazard_fit_issues(table, kind, cutoff, population="dam_like"):
    """Issues that may teach H at `cutoff`: issued before it, at risk, label_ok, in the population.

    Not purged: hazard.person_period keeps each interval only once its own answer is final.
    """
    before = pd.to_datetime(table["issue_date"]).to_numpy() < np.datetime64(pd.Timestamp(cutoff))
    return (before
            & table[rows.p1_at_risk_column(kind)].to_numpy(dtype=bool)
            & table["label_ok"].to_numpy(dtype=bool)
            & rows.population_mask(table, population))


def fit_live_hazard(table, kind, cutoff, extra_features=()):
    """H for `kind` fitted at `cutoff` with damdays.models.hazard's recipe. Returns (model, info).

    TIME: interval k of an issue on day D is learned from only if
    D + (end of interval k) + 30 days < cutoff (hazard.person_period).
    """
    started = time.time()
    features = hazard.hazard_features(kind, extra_features)
    issues = hazard_fit_issues(table, kind, cutoff)
    picked = table.loc[issues]
    issue_days = day_numbers(picked["issue_date"].to_numpy())
    cutoff_day = int(day_numbers([pd.Timestamp(cutoff)])[0])
    position, interval, label = hazard.person_period(issue_days, hazard.days_to_event(picked, kind), cutoff_day)
    X = picked[features].to_numpy(dtype=np.float32)
    model = lgb.LGBMClassifier(**hazard.HAZARD_PARAMS).fit(hazard.with_interval_columns(X[position], interval),
                                                           label)
    info = dict(kind=kind, cutoff=str(pd.Timestamp(cutoff).date()), issues=int(issues.sum()),
                last_issue_used=str(picked["issue_date"].iloc[np.unique(position)].max().date()),
                person_period_rows=int(len(label)), person_period_events=int(label.sum()),
                seconds=round(time.time() - started))
    return model, info


def live_curves(models, table, positions, extra_features=()):
    """The R30 runway curve (30, 60, 90, 180 days) on the given P1 rows, after the max rule. Array [n, 4].

    Every row must be at risk of R30 (so also of D0: a dam at least 30% full has water).
    """
    curves = {}
    for kind in tidemark.CURVE_KINDS:
        X = table.iloc[positions][hazard.hazard_features(kind, extra_features)].to_numpy(dtype=np.float32)
        curves[kind] = hazard.curve_from_hazards(hazard.predict_hazards(models[kind], X))
    return hazard.max_rule(curves["R30"], curves["D0"])


# ---------------------------------------------------------------------------
# Fit and predict
# ---------------------------------------------------------------------------
@dataclass
class LiveModel:
    """Everything fitted at the production cutoff."""
    rung: tidemark.Rung
    cutoff: pd.Timestamp
    members: dict          # {kind: {member: [one fitted model per seed]}}
    setups: dict           # {kind: tidemark.member_setup()}
    registry: dict
    curves: dict           # {kind: hazard model} for R30 and D0
    floor: dict            # tidemark.fit_floor()
    band: dict             # {kind: (low, high)} log-odds offsets
    info: dict


def fit_live(inputs, rung="L1", cutoff=None, registry=tidemark.MEMBERS, log=None):
    """Fit every P1 part of Tidemark at the production cutoff (default: the day after the last look)."""
    say = log or (lambda message: None)
    table = inputs["p1"]
    rung = tidemark.ready_rung(rung, registry, table)
    cutoff = pd.Timestamp(cutoff) if cutoff is not None else live_cutoff(last_look_date())
    check_production_cutoff(cutoff)          # fail before the 17-minute fit, not after it
    cutoff_text = str(cutoff.date())
    info = dict(rung=rung.name, rung_about=rung.about, cutoff=cutoff_text)

    started = time.time()
    members, setups, info["members"] = tidemark.fit_members(inputs, rung, cutoff_text, registry)
    say(f"live: 90-day members {list(rung.members)} fitted at {cutoff_text} ({round(time.time() - started)} s)")

    curves, info["curves"] = {}, {}
    for kind in tidemark.CURVE_KINDS:
        curves[kind], info["curves"][kind] = fit_live_hazard(table, kind, cutoff, rung.extra_features)
    say(f"live: runway curve H fitted ({sum(c['seconds'] for c in info['curves'].values())} s)")

    floor, info["floor"] = tidemark.fit_floor(table, floor_setting(cutoff))
    say(f"live: floor fitted on {info['floor']['fit_rows']:,} forecasts, conformal shift {floor['shift']:+.4f} "
        f"from {info['floor']['calibration_rows']:,} later forecasts")

    band, band_info = tidemark.fit_band(inputs, rung, BAND_SETTING, registry, log)
    info["band"] = {kind: list(v) for kind, v in band.items()}
    info["band_blocks"] = [b["block"] for b in band_info["blocks"]]
    say("live: season band " + ", ".join(f"{k} [{lo:+.3f}, {hi:+.3f}]" for k, (lo, hi) in band.items()))
    return LiveModel(rung=rung, cutoff=cutoff, members=members, setups=setups, registry=registry,
                     curves=curves, floor=floor, band=band, info=info)


def predict_live(model, inputs, positions):
    """Today's forecasts on the given P1 rows (each dam's latest look; all must be at risk of R30).

    Returns one row per position, with the same column names as predict_tidemark's p1 output:
    row, uid, issue_date, p90_R30 (the headline, after the max rule), p90_R30_premax, p90_D0,
    band_low_R30, band_high_R30, frailty_b_R30, frailty_n_R30, frailty_label,
    curve_R30_30 ... curve_R30_180 (H after the max rule), floor_days, floor_shown.
    """
    table = inputs["p1"]
    positions = np.asarray(positions)
    if not table["at_risk_R30"].to_numpy(dtype=bool)[positions].all():
        raise ValueError("Live forecasts are made only where the dam is at least a third full (at risk of R30).")
    # The members predict every earlier issue too: the frailty reads each dam's matured past forecasts.
    history = tidemark.predict_p90(model.members, model.setups, inputs, model.rung, until=model.cutoff,
                                   registry=model.registry)
    out = pd.DataFrame({"row": positions, "uid": table["uid"].astype(str).to_numpy()[positions],
                        "issue_date": table["issue_date"].to_numpy()[positions]})
    out["p90_R30"] = tidemark.values_on_rows(history["R30"], positions, "p")
    out["p90_R30_premax"] = tidemark.values_on_rows(history["R30"], positions, "p_premax")
    out["p90_D0"] = tidemark.values_on_rows(history["D0"], positions, "p")
    out["band_low_R30"], out["band_high_R30"] = unc.band_probabilities(out["p90_R30"].to_numpy(), model.band["R30"])
    out["frailty_b_R30"] = tidemark.values_on_rows(history["R30"], positions, "frailty_b")
    out["frailty_n_R30"] = tidemark.values_on_rows(history["R30"], positions, "frailty_n")
    out["frailty_label"] = frailty.frailty_label(out["frailty_b_R30"].to_numpy())
    curve = live_curves(model.curves, table, positions, model.rung.extra_features)
    for j, h in enumerate(tidemark.HORIZONS):
        out[f"curve_R30_{h}"] = curve[:, j]
    mask = np.zeros(len(table), dtype=bool)
    mask[positions] = True
    _, days, shown = tidemark.predict_floor(model.floor, table, mask)
    # predict_floor returns rows in table order; put them back in the order of `positions`.
    order = pd.Series(np.arange(mask.sum()), index=np.flatnonzero(mask)).loc[positions].to_numpy()
    out["floor_days"], out["floor_shown"] = days[order], shown[order]
    return out


def latest_positions(table, last_look):
    """Each dam's P1 row on the date of its latest look, where that row is at risk of R30.

    last_look  DataFrame with uid and date (the dam's latest valid look). Dams whose
               latest look was dry or below a third have no such row and are skipped.
    """
    keys = pd.DataFrame({"uid": table["uid"].astype(str).to_numpy(),
                         "issue_date": pd.to_datetime(table["issue_date"]).to_numpy(),
                         "at_risk_R30": table["at_risk_R30"].to_numpy(dtype=bool),
                         "row": np.arange(len(table))})
    wanted = pd.DataFrame({"uid": last_look["uid"].astype(str).to_numpy(),
                           "issue_date": pd.to_datetime(last_look["date"]).to_numpy()})
    found = wanted.merge(keys, on=["uid", "issue_date"], how="inner")
    return np.sort(found.loc[found["at_risk_R30"], "row"].to_numpy())
