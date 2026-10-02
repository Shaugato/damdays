"""Build the six JSON files the DamDays app reads (the format is fixed by app/DATA_CONTRACT.md).

    meta.json        what this dataset is, its coverage and its limits
    forecasts.json   each dam's forecast today ("live") and on a few past dates ("past", for Rewind)
    curves.json      each forecast's runway curve (30, 60, 90 and 180 days)
    history.json     each dam's monthly water level since 1988, with its past events
    cells.json       the 2 km cells: rainfall-only score, DamDays Rating, and what happened
    scoreboard.json  the scores, copied from the evaluation outputs

Nothing is fitted here. The numbers come from:
    live forecasts         the production fit (damdays.export.live_model)
    Rewind forecasts and   the VAL-setting model: Tidemark fitted only on answers final before
    season ratings         1 Jan 2009 (scripts/08, data_cache/preds/VAL/tidemark/)
    rainfall-only score    the RAIN baseline of scripts/03 (data_cache/preds/VAL/P2_cell/baselines.pkl)
    scoreboard             artifacts/val_tidemark_<rung>.json (scripts/08) and step 3's RAIN scorecard;
                           the one-season line is computed here by the scorecard itself (damdays.evaluation.score)

Honesty rules, enforced in this module
--------------------------------------
* Rewind and Rating show a VALIDATION season (2009-2015) with forecasts from the
  VAL-setting model, which never learned from those years. TEST seasons
  (2016-2026) are refused until the official one-time TEST scoring.
* What happened ("outcome", "ran_dry") is the PREREG event: R30 (below a third)
  for the runway, D0 (fully dry) for the rating. Unknown answers stay null.
* Scoreboard numbers are copied from evaluation outputs, never typed in.

The water level shown to people
-------------------------------
level_pct = pc_wet / full x 100, where "full" is the PREREG static full (the
dam's 90th-percentile wet share before 2016), as the contract asks. It is a
display and labelling quantity only: the models read the causal checkpoint
"full" (docs/FEATURES.md). For a 2009-2015 Rewind date this display normaliser
knows looks up to 2015; no forecast uses it.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from damdays import config
from damdays.data import cells as hex_cells
from damdays.data.splits import time_block
from damdays.evaluation import score
from damdays.evaluation.metrics import logit, sigmoid
from damdays.export import albers

SCHEMA_VERSION = "1.0"
HORIZONS = (30, 60, 90, 180)                # the runway curve's horizons, in days
RECENT_LOOK_DAYS = 60                       # contract: "no_recent_look" = no valid look in the last 60 days
LEVEL_CAP_PCT = 150                         # contract: water levels are capped at 150% of full
FIRST_MONTH = "1988-01"                     # history starts with the first P1 forecasts (config.FIRST_ISSUE_DATE)
EVENT_NAMES = {"R30": "below_third", "D0": "dry"}
REGION_NAMES = {"nsw_cw": "NSW Central West",
                "wvic_sesa": "Western Victoria and south-east South Australia"}
REGION_SHORT = {"nsw_cw": "NSW", "wvic_sesa": "Vic-SA"}
FRAILTY_NOTES = {"runs drier than similar dams": "Runs drier than similar dams: it fell below a third more "
                                                  "often than the model expected.",
                 "runs wetter than similar dams": "Runs wetter than similar dams: it fell below a third less "
                                                   "often than the model expected."}


# ===========================================================================
# Small helpers: rounding and dates, the way the contract wants them
# ===========================================================================
def chance(value):
    """A probability rounded to 3 decimals; None for a missing value."""
    return None if value is None or not np.isfinite(value) else round(float(value), 3)


def chances(values):
    """A list of probabilities rounded to 3 decimals."""
    return [chance(v) for v in values]


def level_pct(rel):
    """A level (share of full) as a whole-number percentage, capped at 150; None if missing."""
    if rel is None or not np.isfinite(rel):
        return None
    return int(min(round(float(rel) * 100), LEVEL_CAP_PCT))


def day_text(day):
    """A date as "YYYY-MM-DD"; None if missing."""
    return None if day is None or pd.isna(day) else pd.Timestamp(day).strftime("%Y-%m-%d")


def season_label(season):
    """Season year 2013 -> "2013-14" (rated 1 July 2013, judged October 2013 to March 2014)."""
    return f"{season}-{str(season + 1)[-2:]}"


def coordinate(value):
    """A coordinate in degrees, rounded to 5 decimals (about 1 m)."""
    return round(float(value), 5)


# ===========================================================================
# 1. The dams in the app
# ===========================================================================
def app_regions(region):
    """The development regions an export covers: one region key, or "all"."""
    if region == "all":
        return list(config.DEV_REGIONS)
    if region not in config.DEV_REGIONS:
        raise ValueError(f"Unknown region {region!r}; expected one of {list(config.DEV_REGIONS)} or 'all'.")
    return [region]


def app_dams(attrs, regions):
    """The dams the app shows: every dam-like waterbody of the regions (PREREG population).

    dam_id = "<region>-<number>", numbered in DEA id order within the region. The
    dam-like set is fixed from pre-2016 looks, so the ids stay the same between exports.
    """
    parts = []
    for region in regions:
        part = attrs[attrs["dam_like"].to_numpy(dtype=bool) & (attrs["region"].astype(str) == region).to_numpy()]
        part = part.assign(uid=part["uid"].astype(str)).sort_values("uid").reset_index(drop=True)
        number = np.arange(1, len(part) + 1)
        part["dam_id"] = [f"{region}-{n:04d}" for n in number]
        part["name"] = [f"Dam {n}" if len(regions) == 1 else f"{REGION_SHORT[region]} dam {n}" for n in number]
        parts.append(part)
    dams = pd.concat(parts, ignore_index=True)
    return dams[["dam_id", "uid", "name", "region", "lat", "lon", "area_m2", "full", "hex_id", "hex_q", "hex_r"]]


def dams_json(dams):
    """The `dams` list of forecasts.json."""
    return [dict(dam_id=d.dam_id, name=d.name, lat=coordinate(d.lat), lon=coordinate(d.lon),
                 area_ha=round(float(d.area_m2) / 10_000, 2), dea_uid=d.uid) for d in dams.itertuples()]


# ===========================================================================
# 2. Satellite looks: the last look before a date, and whether the dam had refilled
# ===========================================================================
def dam_looks(panel, dams):
    """Every valid look of the app's dams, with rel = pc_wet / static full. Sorted by dam and date."""
    looks = panel[panel["uid"].astype(str).isin(set(dams["uid"]))][["uid", "date", "pc_wet", "px_wet"]].copy()
    looks["uid"] = looks["uid"].astype(str)
    full = dams.set_index("uid")["full"]
    looks["rel"] = looks["pc_wet"].to_numpy(dtype=float) / looks["uid"].map(full).to_numpy(dtype=float)
    return looks.sort_values(["uid", "date"]).reset_index(drop=True)


def last_looks(looks, dams, day):
    """Each dam's latest valid look on or before `day` (one row per dam, in the order of `dams`).

    Columns: uid, date (NaT if the dam has no look yet), rel, px_wet.
    """
    before = looks[looks["date"] <= pd.Timestamp(day)]
    latest = before.groupby("uid", sort=False).tail(1).set_index("uid")
    return latest.reindex(dams["uid"])[["date", "rel", "px_wet"]].reset_index()


def armed_at(looks, events, last):
    """True where the dam was "armed" for R30 at its last look: the PREREG refill rule.

    Armed = some look in the 180 days up to the last look showed at least 60% of
    full, and no R30 event has started since that look (an event disarms the dam
    until it refills again; damdays/data/events.py).
    """
    # merge_asof needs the same date type on both sides, so every date is made datetime64[ns] first.
    target = last.dropna(subset=["date"]).assign(date=lambda t: t["date"].astype("datetime64[ns]"))
    target = target.sort_values("date")
    refills = looks.loc[looks["rel"] >= config.ARM_LEVEL, ["uid", "date"]].rename(columns={"date": "refill"})
    refills = refills.assign(refill=refills["refill"].astype("datetime64[ns]"))
    starts = events.loc[events["kind"] == "R30", ["uid", "start_date"]].rename(columns={"start_date": "event"})
    starts = starts.assign(uid=starts["uid"].astype(str), event=starts["event"].astype("datetime64[ns]"))
    found = pd.merge_asof(target, refills.sort_values("refill"), left_on="date", right_on="refill", by="uid")
    found = pd.merge_asof(found.sort_values("date"), starts.sort_values("event"), left_on="date", right_on="event",
                          by="uid")
    recent = (found["date"] - found["refill"]).dt.days <= config.ARM_WINDOW_DAYS
    no_event_since = found["event"].isna() | (found["event"] <= found["refill"])
    armed = pd.Series((recent & no_event_since).to_numpy(), index=found["uid"].to_numpy())
    return armed.reindex(last["uid"]).fillna(False).to_numpy(dtype=bool)


def issue_status(last, armed, issue_day):
    """The contract's status of each dam on an issue date, from its last look.

    no_recent_look  no valid look in the 60 days up to the issue date
    already_low     the last look was below a third of full (or dry)
    not_refilled    not armed: no refill to 60% of full in the last 180 days (or an event since)
    forecast        otherwise: the dam gets a forecast
    """
    age = (pd.Timestamp(issue_day) - last["date"]).dt.days.to_numpy(dtype=float)
    rel = last["rel"].to_numpy(dtype=float)
    status = np.where(~(age <= RECENT_LOOK_DAYS), "no_recent_look",
                      np.where(~(rel >= config.R30_LEVEL), "already_low",
                               np.where(~armed, "not_refilled", "forecast")))
    return status


# ===========================================================================
# 3. Forecast values, the runway curve and the season band
# ===========================================================================
def join_curve_to_headline(curve, headline):
    """The curve the app draws: the hazard model's 30, 60 and 180-day values, and the headline at 90 days.

    The headline (the fused 90-day chance with the per-dam correction) and the
    hazard curve H come from two models, so H's own 90-day value differs a
    little (mean gap 0.036 on VAL). The contract asks them to agree, so:
      90 days:      the headline;
      30, 60 days:  H, lowered to the headline where H is higher;
      180 days:     H, raised to the headline where H is lower.
    H never falls with the horizon, so the joined curve never falls either.
    Returns (joined curve [n, 4], how many curves had a 30/60/180-day value moved).
    """
    curve = np.asarray(curve, dtype=float)
    headline = np.asarray(headline, dtype=float)
    joined = curve.copy()
    joined[:, 0] = np.minimum(curve[:, 0], headline)
    joined[:, 1] = np.minimum(curve[:, 1], headline)
    joined[:, 2] = headline
    joined[:, 3] = np.maximum(curve[:, 3], headline)
    moved = int(np.any(joined[:, [0, 1, 3]] != curve[:, [0, 1, 3]], axis=1).sum())
    return joined, moved


def with_band(p, band):
    """The season band around probabilities p: sigmoid(logit p + low), sigmoid(logit p + high).

    The band's low offset is below 0 and its high offset above 0, so low <= p <= high.
    """
    low_offset, high_offset = band
    if not low_offset <= 0 <= high_offset:
        raise ValueError(f"A season band must contain 0, got {band}.")
    z = logit(np.asarray(p, dtype=float))
    return sigmoid(z + low_offset), sigmoid(z + high_offset)


def forecast_values(preds, band):
    """Everything the app shows for one forecast, from a model output table (one row per forecast).

    preds  rows of predict_tidemark's p1 output (VAL) or predict_live's output (live), with
           p90_R30, band_low_R30, band_high_R30, curve_R30_30 ... curve_R30_180, floor_days, frailty_label
    band   the model's R30 band constants (low, high), used for the curve's band
    Returns (a table indexed like preds, number of curves moved by the join).
    """
    p = preds["p90_R30"].to_numpy(dtype=float)
    low, high = with_band(p, band)
    # The stored band must be this band (same constants, same formula).
    same_band = (np.allclose(low, preds["band_low_R30"], atol=1e-9)
                 and np.allclose(high, preds["band_high_R30"], atol=1e-9))
    if not same_band:
        raise AssertionError("The model's stored season band does not match its band constants.")
    curve, moved = join_curve_to_headline(preds[[f"curve_R30_{h}" for h in HORIZONS]].to_numpy(dtype=float), p)
    curve_low, curve_high = with_band(curve, band)
    out = pd.DataFrame({"chance": p, "chance_low": low, "chance_high": high,
                        # DamDays floor in whole days, rounded down (the cautious way); the app shows 180+.
                        "damdays_days": np.floor(preds["floor_days"].to_numpy(dtype=float)).astype(int),
                        "frailty_label": preds["frailty_label"].to_numpy()}, index=preds.index)
    out["curve"] = list(curve)
    out["curve_low"] = list(curve_low)
    out["curve_high"] = list(curve_high)
    return out, moved


def forecast_notes(frailty_label):
    """Plain sentences for the card: the per-dam correction's label, when it is not "typical"."""
    note = FRAILTY_NOTES.get(str(frailty_label))
    return [note] if note else []


# ===========================================================================
# 4. One issue date: rows for forecasts.json, by_dam for curves.json
# ===========================================================================
def issue_tables(dams, looks, events, issue_day, preds, band):
    """Every dam's row on one issue date, joined to the model's forecast where it has one.

    preds  the model's forecasts keyed by uid and issue_date (the look date)
    Returns (rows table, number of curves moved by the join). The rows table has
    one row per dam with status, issued_on, rel and, for forecasts, the values
    of forecast_values plus `row` (the P1 table position, for outcomes).
    """
    last = last_looks(looks, dams, issue_day)
    last["status"] = issue_status(last, armed_at(looks, events, last), issue_day)
    last["dam_id"] = dams["dam_id"].to_numpy()
    wanted = last[last["status"] == "forecast"][["uid", "date"]].rename(columns={"date": "issue_date"})
    wanted["issue_date"] = wanted["issue_date"].astype("datetime64[ns]")
    keyed = preds.assign(uid=preds["uid"].astype(str), issue_date=preds["issue_date"].astype("datetime64[ns]"))
    found = wanted.merge(keyed, on=["uid", "issue_date"], how="left", validate="one_to_one")
    if found["p90_R30"].isna().any():
        missing = found.loc[found["p90_R30"].isna(), ["uid", "issue_date"]].head(3).to_dict("records")
        raise AssertionError(f"Forecast-status dams without a model forecast on {day_text(issue_day)}: {missing}")
    values, moved = forecast_values(found, band)
    values["uid"], values["row"] = found["uid"].to_numpy(), found["row"].to_numpy()
    table = last.merge(values, on="uid", how="left")
    return table, moved


def add_outcomes(table, keys, events):
    """Rewind only: what happened after each forecast (the PREREG R30 label of that forecast).

    outcome       True if an R30 event started in (issued_on, issued_on + 90 days], False if
                  not, None if the answer is not determinable (label_ok False: fewer than 3 looks)
    outcome_date  the event's start date (its first confirming look)
    keys          the P1 key table (labels); `row` in `table` points into it
    """
    table["outcome"], table["outcome_date"] = None, None
    is_forecast = (table["status"] == "forecast").to_numpy()
    positions = table.loc[is_forecast, "row"].to_numpy(dtype=np.int64)
    # `row` is a position, so the key table must be the P1 table in the order the model saw it.
    same_dam = keys["uid"].astype(str).to_numpy()[positions] == table.loc[is_forecast, "uid"].to_numpy()
    same_day = (pd.to_datetime(keys["issue_date"]).to_numpy()[positions]
                == table.loc[is_forecast, "date"].to_numpy(dtype="datetime64[ns]"))
    if not (same_dam & same_day).all():
        raise AssertionError("The P1 key table is not in the order of the forecasts' `row` positions.")
    y = keys["y_R30"].to_numpy(dtype=float)[positions]
    known = keys["label_ok"].to_numpy(dtype=bool)[positions]
    outcome = [bool(v) if k else None for v, k in zip(y, known)]
    r30 = events[events["kind"] == "R30"]
    starts = {uid: np.sort(days.to_numpy()) for uid, days in r30.groupby(r30["uid"].astype(str))["start_date"]}
    dates = []
    for uid, issued, happened in zip(table.loc[is_forecast, "uid"], table.loc[is_forecast, "date"], outcome):
        if not happened:
            dates.append(None)
            continue
        # The first R30 start after the look and within its 90-day window.
        days = starts.get(uid, np.array([], dtype="datetime64[us]"))
        first = days[days > np.datetime64(issued)]
        if len(first) == 0 or first[0] > np.datetime64(issued + pd.Timedelta(days=config.HORIZON_DAYS)):
            raise AssertionError(f"{uid} on {day_text(issued)}: the label says an R30 event started, but none found.")
        dates.append(day_text(first[0]))
    table.loc[is_forecast, "outcome"] = pd.Series(outcome, index=table.index[is_forecast], dtype=object)
    table.loc[is_forecast, "outcome_date"] = pd.Series(dates, index=table.index[is_forecast], dtype=object)
    return table


def rows_json(table):
    """The `rows` of one issue in forecasts.json (every dam, forecast or not)."""
    out = []
    for r in table.itertuples():
        is_forecast = r.status == "forecast"
        has_look = not pd.isna(r.date)
        out.append(dict(
            dam_id=r.dam_id, status=r.status,
            issued_on=day_text(r.date) if has_look else None,
            window_end=day_text(r.date + pd.Timedelta(days=config.HORIZON_DAYS)) if has_look else None,
            level_pct=level_pct(r.rel) if has_look else None,
            chance=chance(r.chance) if is_forecast else None,
            chance_low=chance(r.chance_low) if is_forecast else None,
            chance_high=chance(r.chance_high) if is_forecast else None,
            damdays_days=int(r.damdays_days) if is_forecast else None,
            notes=forecast_notes(r.frailty_label) if is_forecast else [],
            outcome=getattr(r, "outcome", None) if is_forecast else None,
            outcome_date=getattr(r, "outcome_date", None) if is_forecast else None))
    return out


def curves_json(table):
    """`by_dam` of one issue in curves.json: chance, low and high at 30, 60, 90 and 180 days (forecasts only)."""
    picked = table[table["status"] == "forecast"]
    return {r.dam_id: dict(chance=chances(r.curve), low=chances(r.curve_low), high=chances(r.curve_high))
            for r in picked.itertuples()}


def issue_json(table, issue_day, kind, label, note):
    """One entry of forecasts.json's `issues`."""
    return dict(issue_date=day_text(issue_day), kind=kind, label=label, note=note, rows=rows_json(table))


# ===========================================================================
# 5. Water history
# ===========================================================================
def month_list(first_month, last_month):
    """Every month from first to last, inclusive, as pandas Periods."""
    return pd.period_range(first_month, last_month, freq="M")


def monthly_levels(looks, dams, months):
    """{dam_id: [level_pct per month]}: the median of the month's valid looks, None if no look that month."""
    month = looks["date"].dt.to_period("M")
    in_range = (month >= months[0]) & (month <= months[-1])
    median = (looks[in_range].assign(month=month[in_range]).groupby(["uid", "month"])["rel"].median()
              .unstack("month").reindex(index=dams["uid"], columns=months))
    values = median.to_numpy(dtype=float)
    return {dam_id: [level_pct(v) for v in row] for dam_id, row in zip(dams["dam_id"], values)}


def event_lists(events, dams, months):
    """{dam_id: [{date, kind}]}: every R30 ("below_third") and D0 ("dry") start in the history's months."""
    dam_id = dict(zip(dams["uid"], dams["dam_id"]))
    picked = events[events["uid"].astype(str).isin(dam_id) & events["kind"].isin(EVENT_NAMES)]
    month = picked["start_date"].dt.to_period("M")
    picked = picked[(month >= months[0]) & (month <= months[-1])].sort_values(["start_date", "kind"])
    out = {d: [] for d in dams["dam_id"]}
    for uid, start, kind in zip(picked["uid"].astype(str), picked["start_date"], picked["kind"]):
        out[dam_id[uid]].append(dict(date=day_text(start), kind=EVENT_NAMES[kind]))
    return out


def history_json(looks, events, dams, last_day, first_month=FIRST_MONTH):
    """history.json: monthly levels and event starts for every dam, from first_month (1988-01) to the last look."""
    months = month_list(first_month, pd.Timestamp(last_day).strftime("%Y-%m"))
    levels = monthly_levels(looks, dams, months)
    marks = event_lists(events, dams, months)
    return dict(first_month=str(months[0]), last_month=str(months[-1]),
                by_dam={d: dict(level_pct=levels[d], events=marks[d]) for d in dams["dam_id"]})


# ===========================================================================
# 6. The 2 km cells and the season rating
# ===========================================================================
def hexagon_corners(q, r):
    """The 6 corners of a pointy-top 2 km hexagon as [lat, lon] pairs (cells.py lays the grid out in Albers)."""
    centre_x, centre_y = hex_cells.hex_centre(q, r)
    angles = np.radians(30 + 60 * np.arange(6))
    lat, lon = albers.to_lat_lon(centre_x + hex_cells.HEX_RADIUS_M * np.cos(angles),
                                 centre_y + hex_cells.HEX_RADIUS_M * np.sin(angles))
    return [[coordinate(a), coordinate(b)] for a, b in zip(lat, lon)]


def app_cells(dams):
    """One row per 2 km cell holding at least one of the app's dams: cell_id, q, r, n_dams, centre."""
    cells = (dams.groupby("hex_id").agg(q=("hex_q", "first"), r=("hex_r", "first"), n_dams=("uid", "size"))
             .reset_index().rename(columns={"hex_id": "cell_id"}))
    centre_x, centre_y = hex_cells.hex_centre(cells["q"].to_numpy(), cells["r"].to_numpy())
    cells["lat"], cells["lon"] = albers.to_lat_lon(centre_x, centre_y)
    return cells


def cells_list_json(cells):
    """The `cells` list of cells.json."""
    return [dict(cell_id=c.cell_id, lat=coordinate(c.lat), lon=coordinate(c.lon),
                 corners=hexagon_corners(c.q, c.r), n_dams=int(c.n_dams)) for c in cells.itertuples()]


def season_table(cells, cell_preds, rain, cell_labels, season):
    """Every app cell's rating, rainfall-only score and outcome for one season (rated 1 July `season`).

    cell_preds   the model's cell ratings (uid = cell id, issue_date, p)
    rain         the RAIN baseline (uid, issue_date, p_RAIN, plus p_B0 and p_B2 for the scorecard)
    cell_labels  the P2 cell table (hex_id, issue_date, y, label_ok, n_dams, region)
    ran_dry is the PREREG cell label: every dam-like dam in the cell had a D0 event from
    October to March; None where it is not determinable.
    """
    def keyed(frame, uid_column, columns):
        """The frame's uid (as text), issue_date (as datetime64[ns]) and the wanted columns."""
        return frame.assign(uid=frame[uid_column].astype(str),
                            issue_date=frame["issue_date"].astype("datetime64[ns]"))[["uid", "issue_date", *columns]]

    keys = pd.DataFrame({"uid": cells["cell_id"].to_numpy(),
                         "issue_date": np.full(len(cells), np.datetime64(f"{season}-07-01", "ns"))})
    mine = keyed(cell_preds, "uid", ["p"])
    base = keyed(rain, "uid", ["p_RAIN", "p_B0", "p_B2"])
    labels = keyed(cell_labels, "hex_id", ["y", "label_ok", "n_dams", "region"]).rename(columns={"n_dams": "n_dams_p2"})
    table = (keys.merge(mine, on=["uid", "issue_date"], how="left", validate="one_to_one")
             .merge(base, on=["uid", "issue_date"], how="left", validate="one_to_one")
             .merge(labels, on=["uid", "issue_date"], how="left", validate="one_to_one"))
    if table[["p", "p_RAIN", "n_dams_p2"]].isna().any().any():
        raise AssertionError(f"Some cells have no rating, RAIN score or P2 row in season {season}.")
    if not (table["n_dams_p2"].to_numpy() == cells["n_dams"].to_numpy()).all():
        raise AssertionError("The app's dams per cell differ from the P2 cell table.")
    known = table["label_ok"].to_numpy(dtype=bool) & table["y"].notna().to_numpy()
    table["ran_dry"] = [bool(v) if k else None for v, k in zip(table["y"].to_numpy(dtype=float), known)]
    table["y_scored"] = np.where(known, table["y"].to_numpy(dtype=float), np.nan)
    return table


def season_json(table, season, kind="past"):
    """One entry of cells.json's `seasons`."""
    rows = [dict(cell_id=r.uid, rain_only_chance=chance(r.p_RAIN), rating_chance=chance(r.p), ran_dry=r.ran_dry)
            for r in table.itertuples()]
    return dict(season=season_label(season), issue_date=day_text(pd.Timestamp(season, 7, 1)), kind=kind, rows=rows)


# ===========================================================================
# 7. Scoreboard
# ===========================================================================
def score_range(result, metric="auc"):
    """A contract Range {value, ci_low, ci_high} from a scorecard result (95% dam-bootstrap interval)."""
    low, high = result["ci_dam"][metric]
    return dict(value=result["point"][metric], ci_low=low, ci_high=high)


def season_scores(table, season, rung, out_dir, n_boot):
    """The scorecard's AUC of the rating and of RAIN on one season's cells (the app's region only).

    Computed by damdays.evaluation.score itself (VAL only; the result files go to
    out_dir). The interval is the 95% dam (here: cell) bootstrap. Returns the two results.
    """
    frame = pd.DataFrame({"uid": table["uid"], "issue_date": table["issue_date"], "region": table["region"],
                          "y": table["y_scored"], "p": table["p"], "p_B0": table["p_B0"], "p_B2": table["p_B2"],
                          "p_RAIN": table["p_RAIN"]})
    if set(time_block(frame["issue_date"])) != {"VAL"}:
        raise AssertionError("Season scores are only computed here for validation seasons.")
    note = f"step 11 (app export): season {season_label(season)}, app cells only"
    rating = score(frame, "P2_cell", "all", model=f"tidemark_{rung}_app_{season}", refs=["RAIN"], n_boot=n_boot,
                   note=note, out_dir=out_dir)
    rain = score(frame.assign(p=frame["p_RAIN"]), "P2_cell", "all", model=f"rain_app_{season}", n_boot=n_boot,
                 note=note, out_dir=out_dir)
    # Read the numbers back from the saved result files, so the app shows exactly what the scorecard wrote.
    return tuple(json.loads(Path(result["json_path"]).read_text(encoding="utf-8")) for result in (rating, rain))


def score_line(rating, rain):
    """A contract Score line from two scorecard results on the same rows."""
    if rating["rows"] != rain["rows"]:
        raise AssertionError("The rating and RAIN results must be scored on the same rows.")
    return dict(n_cells=rating["rows"]["scored"], n_ran_dry=rating["rows"]["events"],
                rain_only_auc=score_range(rain), rating_auc=score_range(rating))


def scoreboard_json(results, rain_all, rung, season, season_line, n_regions_label):
    """scoreboard.json: validation-period scores, labelled so nobody mistakes them for the test.

    results   artifacts/val_tidemark_<rung>.json (scripts/08)
    rain_all  step 3's scorecard result for RAIN on P2_cell (all VAL seasons)
    """
    p2 = results["p2"][f"P2_cell|all|{rung}"]
    p1 = results["p1"][f"P1_R30|primary|{rung}"]
    if p2["rows"]["scored"] != rain_all["rows"]["scored"] or p2["rows"]["events"] != rain_all["rows"]["events"]:
        raise AssertionError("The all-season rating and RAIN scores are not on the same cell-seasons.")
    all_seasons = dict(label=f"All validation seasons 2009-10 to 2015-16 ({n_regions_label})",
                       n_cells=p2["rows"]["scored"], n_ran_dry=p2["rows"]["events"],
                       rain_only_auc=dict(value=rain_all["point"]["auc"], ci_low=rain_all["ci_dam"]["auc"][0],
                                          ci_high=rain_all["ci_dam"]["auc"][1]),
                       rating_auc=score_range(p2))
    return dict(
        source="dev_val", is_validation=True, block="VAL",
        source_label="Validation years 2009-2015, development regions (not the one-time test)",
        note=("Validation-period numbers: the model learned only from answers known before 1 Jan 2009 and is "
              "scored on 2009-2015. Every design choice was made on these years. The test years (2016-2026) "
              "and the sealed region are scored once, separately."),
        rating=dict(all_seasons=all_seasons, by_season=[dict(season=season_label(season), **season_line)]),
        runway=dict(label=("Validation years 2009-2015: below a third within 90 days, farm-like dams, "
                           "October-March forecasts, both development regions"),
                    skill_vs_usual_rate=score_range(p1, "bss_B0"), n_forecasts=p1["rows"]["scored"]),
        sources=dict(rating_all_seasons=f"artifacts/val_tidemark_{rung}.json p2 'P2_cell|all|{rung}'",
                     rain_all_seasons="artifacts/scorecard/step03_val/dev_VAL/P2_cell/rain__all.json",
                     by_season="artifacts/scorecard/step11_app/dev_VAL/P2_cell/ (computed by the scorecard)",
                     runway=f"artifacts/val_tidemark_{rung}.json p1 'P1_R30|primary|{rung}'"))


# ===========================================================================
# 8. Meta: what this dataset is, its coverage and its limits
# ===========================================================================
def region_json(regions):
    """meta.region: one region, or the union of the development regions."""
    boxes = np.array([config.DEV_REGIONS[r] for r in regions])
    key = regions[0] if len(regions) == 1 else "all"
    name = " and ".join(REGION_NAMES[r] for r in regions)
    bbox = [float(boxes[:, 0].min()), float(boxes[:, 1].max()), float(boxes[:, 2].min()), float(boxes[:, 3].max())]
    return dict(key=key, name=name, bbox=bbox)


def limits_text(results, rung):
    """Plain-language limits, with the numbers read from the validation results."""
    p2 = results["p2"][f"P2_cell|all|{rung}"]["point"]
    p1 = results["p1"][f"P1_R30|primary|{rung}"]["point"]
    return [
        "Only dams of at least about 0.54 ha (6 Landsat pixels) are visible; smaller dams, tanks and bores are not.",
        "Water area, not depth: 'below a third' means below a third of the dam's usual full wet area.",
        "Validation numbers: every score shown was measured on 2009-2015, years the model never learned from. "
        "The test years and the sealed region are scored once, separately.",
        f"It ranks farms better than it times droughts: the rating tells which cells run dry in a season "
        f"(ranking accuracy {p2['auc_within_season']:.2f} within a season), but not which seasons a given cell "
        f"runs dry ({p2['auc_within_cell']:.2f} within a cell's own history, close to a coin toss).",
        f"Very wet or very dry years: on 2009-2015 the runway forecasts were too high on average "
        f"(average forecast {p1['mean_p']:.2f}, actual rate {p1['base_rate']:.2f}), mostly in the wet 2010-12 years. "
        "The likely range (season band) shows how far a wet or dry season can move a chance.",
        "Live forecasts start from each dam's latest clear satellite look; some looks are weeks old.",
        f"This is rung {rung} of the pre-registered plan (PREREG.md, fallback ladder).",
    ]


def meta_json(regions, last_day, rung, live_info, rewind_info, coverage, results, note):
    """meta.json."""
    return dict(
        schema_version=SCHEMA_VERSION, is_mock=False,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        region=region_json(regions), data_through=day_text(last_day), horizon_days=config.HORIZON_DAYS,
        threshold_pct=int(round(config.R30_LEVEL * 100)), arm_level_pct=int(round(config.ARM_LEVEL * 100)),
        min_dam_area_ha=config.AREA_MIN_M2 / 10_000,
        model=dict(name="Tidemark", version=rung, config_hash=None),
        note=note, coverage=coverage, limits=limits_text(results, rung), live=live_info, rewind=rewind_info)


# ===========================================================================
# 9. Checks: does the dataset keep the contract's promises?
# ===========================================================================
def contract_problems(docs):
    """Every broken contract rule in the six documents, as plain sentences (empty list = all good)."""
    problems = []
    meta, forecasts, curves, history, cells, board = (docs[k] for k in
                                                      ("meta", "forecasts", "curves", "history", "cells",
                                                       "scoreboard"))
    for name, doc in docs.items():
        try:
            json.dumps(doc, allow_nan=False)
        except ValueError:
            problems.append(f"{name}: contains NaN or infinity")
    if meta["is_mock"] is not False:
        problems.append("meta: is_mock must be false for real data")
    dam_ids = [d["dam_id"] for d in forecasts["dams"]]
    if len(set(dam_ids)) != len(dam_ids):
        problems.append("forecasts: dam_id is not unique")
    if sum(i["kind"] == "live" for i in forecasts["issues"]) != 1:
        problems.append("forecasts: there must be exactly one live issue")
    curve_issues = {c["issue_date"]: c["by_dam"] for c in curves["issues"]}
    for issue in forecasts["issues"]:
        where = f"forecasts {issue['issue_date']}"
        if [r["dam_id"] for r in issue["rows"]] != dam_ids:
            problems.append(f"{where}: rows must list every dam, in the order of `dams`")
        by_dam = curve_issues.get(issue["issue_date"])
        if by_dam is None:
            problems.append(f"{where}: no curves for this issue")
            continue
        for r in issue["rows"]:
            values = [r["chance"], r["chance_low"], r["chance_high"], r["damdays_days"]]
            if r["status"] != "forecast":
                if any(v is not None for v in values) or r["dam_id"] in by_dam:
                    problems.append(f"{where} {r['dam_id']}: a {r['status']} row must have no forecast")
                continue
            if any(v is None for v in values) or not 0 <= r["chance_low"] <= r["chance"] <= r["chance_high"] <= 1:
                problems.append(f"{where} {r['dam_id']}: chance and band missing or out of order")
            if issue["kind"] == "live" and r["outcome"] is not None:
                problems.append(f"{where} {r['dam_id']}: a live forecast cannot have an outcome")
            curve = by_dam.get(r["dam_id"])
            if curve is None:
                problems.append(f"{where} {r['dam_id']}: forecast without a curve")
                continue
            c, lo, hi = curve["chance"], curve["low"], curve["high"]
            if any(b < a for a, b in zip(c, c[1:])) or any(b < a for a, b in zip(lo, lo[1:])) \
                    or any(b < a for a, b in zip(hi, hi[1:])):
                problems.append(f"{where} {r['dam_id']}: curve goes down")
            if not all(a <= b <= d for a, b, d in zip(lo, c, hi)):
                problems.append(f"{where} {r['dam_id']}: curve band out of order")
            if c[HORIZONS.index(90)] != r["chance"] or lo[2] != r["chance_low"] or hi[2] != r["chance_high"]:
                problems.append(f"{where} {r['dam_id']}: curve at 90 days differs from the headline")
    n_months = len(month_list(history["first_month"], history["last_month"]))
    for dam_id in dam_ids:
        levels = history["by_dam"].get(dam_id, {}).get("level_pct")
        if levels is None or len(levels) != n_months:
            problems.append(f"history {dam_id}: needs one level per month")
    cell_ids = {c["cell_id"] for c in cells["cells"]}
    if any(len(c["corners"]) != 6 for c in cells["cells"]):
        problems.append("cells: every hexagon needs 6 corners")
    for season in cells["seasons"]:
        if not {r["cell_id"] for r in season["rows"]} <= cell_ids:
            problems.append(f"cells {season['season']}: rows for unknown cells")
    board_seasons = {line["season"] for line in board["rating"]["by_season"]}
    if board_seasons != {s["season"] for s in cells["seasons"] if s["kind"] == "past"}:
        problems.append("scoreboard: by_season must list the past seasons of cells.json")
    return problems


def write_documents(docs, folder):
    """Write the six JSON files. Small files are indented for reading; large ones are compact."""
    folder.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name, doc in docs.items():
        indent = 1 if name in ("meta", "scoreboard") else None
        separators = None if indent else (",", ":")
        path = folder / f"{name}.json"
        path.write_text(json.dumps(doc, indent=indent, separators=separators, ensure_ascii=False, allow_nan=False),
                        encoding="utf-8")
        sizes[name] = path.stat().st_size
    return sizes
