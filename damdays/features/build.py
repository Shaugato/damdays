"""Build every issue table and causal feature from the data layer, in one pure function.

    tables = build_all(panel, attrs, events, rain_by_cell)

Inputs are exactly what scripts/01_build_data.py writes to data_cache/. No file
is read here, which is what makes the look-ahead test simple: it calls
build_all on data with everything after a cut date deleted, and compares.

Steps
-----
1. Checkpoints   what we knew about each dam on 1 Jan of each year
2. Grid          each dam's as-of level on the 1st and 16th of every month,
                 its own monthly climatology, and its neighbours' summaries
3. Per dam       dam-history features, at-risk flags, labels and the causal
                 track record at every look; the 1 Jul season-rating rows
4. P1 table      at-risk looks from 1988 on, plus dam rates and rain features
5. P2 tables     the dam table (with season track record) and the cell table

Outputs: dict with p1 (one row per at-risk look), p2_dam, p2_cell,
checkpoints (long table) and neighbour_grid (arrays, for inspection).
"""
import time
import warnings

import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import hydro_year, time_block
from damdays.features import checkpoints, dam_history, issues, neighbours, rain, season
from damdays.features.common import (dam_slices, dates_from_day_numbers, day_numbers, is_warm_season,
                                     year_month_before)

EVENT_KEYS = ("D0", "R30", "D0g", "D0ab")
STATIC_COLUMNS = ["region", "dam_like", "persistent", "dam_like_persistent", "fold5", "sfold5", "hex_id",
                  "silo_cell", "n_pixels", "pixel_compactness", "elongation"]


def progress_printer(verbose):
    """A function that prints progress lines with elapsed seconds (or does nothing)."""
    started = time.time()

    def say(message):
        """Print one progress line (only when verbose)."""
        if verbose:
            print(f"  [{time.time() - started:6.0f} s] {message}", flush=True)
    return say


def studied_dams(attrs):
    """The has_hist waterbodies (the PREREG study set), sorted by uid, with static columns ready."""
    dams = attrs[attrs["has_hist"]].copy()
    dams["uid"] = dams["uid"].astype(str)
    dams["log_n_pixels"] = np.log(dams["n_pixels"])
    return dams.sort_values("uid").reset_index(drop=True)


def looks_of(panel, dam_uids):
    """Panel rows of the studied dams as plain arrays, sorted by uid then date."""
    looks = panel[panel["uid"].astype(str).isin(set(dam_uids))]
    looks = looks.assign(uid=looks["uid"].astype(str)).sort_values(["uid", "date"]).reset_index(drop=True)
    return looks


def checkpoint_values(table, dam_index, years):
    """Checkpoint statistics for one dam at each of `years` (NaN before the first checkpoint)."""
    k = checkpoints.checkpoint_index(years)
    return {stat: np.where(k >= 0, table[stat][dam_index, np.maximum(k, 0)], np.nan)
            for stat in checkpoints.STATS}


class DamLooks:
    """Read-only view of the studied dams' looks: one dam at a time, as numpy arrays."""

    def __init__(self, looks, dam_uids):
        """Turn the sorted looks table into flat arrays plus each dam's row range."""
        self.dam_uids = dam_uids
        self.starts, self.stops = dam_slices(looks["uid"], dam_uids)
        self.days = day_numbers(looks["date"])
        self.dates = looks["date"].to_numpy()
        self.pc = looks["pc_wet"].to_numpy(dtype=float)
        self.px = looks["px_wet"].to_numpy(dtype=float)

    def of(self, i):
        """(days, DatetimeIndex, pc, px) of dam i."""
        a, b = self.starts[i], self.stops[i]
        return self.days[a:b], pd.DatetimeIndex(self.dates[a:b]), self.pc[a:b], self.px[a:b]


# ---------------------------------------------------------------------------
# Step 2: the neighbour grid
# ---------------------------------------------------------------------------
def build_grid(dl, ck, dams, data_end):
    """As-of grid, own climatology and neighbour summaries (see damdays.features.neighbours)."""
    grid = neighbours.grid_dates(data_end)

    def per_dam():
        """Yield (dam index, look days, rel, px_wet) for each dam, rel from its causal checkpoint."""
        for i in range(len(dl.dam_uids)):
            days, dates, pc, px = dl.of(i)
            full_c = checkpoint_values(ck, i, dates.year)["full_c"]
            yield i, days, dam_history.relative_level(pc, full_c), px

    asof, zero = neighbours.as_of_grid(per_dam(), len(dl.dam_uids), grid)
    clim, _ = neighbours.own_monthly_climatology(asof, grid)
    nb_lists = neighbours.neighbour_lists(dams["uid"], dams["lat"].to_numpy(), dams["lon"].to_numpy())
    summaries = neighbours.neighbour_features(asof, zero, clim, grid, nb_lists)
    return {"grid": grid, "asof": asof, "zero": zero, "clim": clim, "n_neighbours": np.array([len(n) for n in nb_lists]),
            **summaries}


# ---------------------------------------------------------------------------
# Step 3: one dam
# ---------------------------------------------------------------------------
def one_dam(i, uid, dl, ck, grid, dam, event_days, data_end_day, first_issue_day, seasons):
    """All per-look columns of one dam, its P1 rows, its P2 rows and its TRAIN prior sums."""
    days, dates, pc, px = dl.of(i)
    history = checkpoint_values(ck, i, dates.year)
    own_clim = neighbours.climatology_at(grid["clim"], i, dates.year, dates.month)
    events = {key: event_days.get((uid, key), issues.EMPTY) for key in EVENT_KEYS}

    cols = dam_history.dam_features(days, dates, pc, px, history, own_clim)
    risk = issues.at_risk_flags(pc, px, dam["full"])
    label_cols = issues.labels(days, events, data_end_day)
    cols.update(risk)
    cols.update(label_cols)
    cols.update(issues.track_record(days, dates.month, risk, label_cols))
    for name in ("R_anom", "R_chg3", "R_zero"):
        cols[name] = neighbours.at_issue(grid[name], i, days, grid["grid"])

    prior_sums = issues.train_prior_sums(dam["region"], dates, risk, label_cols)
    p2_rows = season.dam_season_rows(uid, days, cols, events, data_end_day, seasons)

    # P1 keeps every look that is at risk for D0 or R30, from 1988 on. Rows
    # failing label_ok are KEPT (flagged), so the label_ok sensitivity row and
    # the look-ahead test can see them.
    keep = (risk["at_risk_D0"] | risk["at_risk_R30"]) & (days >= first_issue_day)
    p1_rows = {"uid": np.repeat(uid, int(keep.sum())), "issue_day": days[keep]}
    p1_rows.update({name: np.asarray(values)[keep] for name, values in cols.items()})
    return p1_rows, p2_rows, prior_sums


def stack(parts):
    """Concatenate a list of dicts of equal-length arrays into one DataFrame."""
    columns = parts[0].keys()
    return pd.DataFrame({c: np.concatenate([p[c] for p in parts]) for c in columns})


def to_float32(table):
    """Store float64 columns as float32 (halves memory; DEA values have 2 decimals anyway)."""
    for column in table.columns:
        if table[column].dtype == np.float64:
            table[column] = table[column].astype(np.float32)
    return table


# ---------------------------------------------------------------------------
# Steps 4 and 5: assemble the tables
# ---------------------------------------------------------------------------
def finish_p1(p1, dams, prior, rain_feats):
    """Add static columns, calendar keys, dam rates and rain features to the P1 rows."""
    p1["issue_date"] = dates_from_day_numbers(p1.pop("issue_day"))
    static = dams.set_index("uid")
    for column in STATIC_COLUMNS + ["log_n_pixels"]:
        p1[column] = p1["uid"].map(static[column]).to_numpy()
    dates = pd.DatetimeIndex(p1["issue_date"])
    p1["year"] = dates.year
    p1["hydro_year"] = hydro_year(dates)
    p1["warm"] = is_warm_season(dates.month)
    p1["split"] = time_block(dates)
    p1 = issues.add_dam_rates(p1, prior)
    # Rain window ends the month BEFORE the issue month (the last complete month).
    p1["rain_month"] = year_month_before(dates)
    for name, values in rain.lookup(rain_feats, p1["silo_cell"], p1["rain_month"]).items():
        p1[name] = values
    return to_float32(p1)


def finish_p2(p2, dams, ck, grid, prior, rain_feats):
    """Add static, checkpoint, neighbour, rain and track-record columns to the P2 dam rows."""
    p2["issue_date"] = pd.to_datetime([f"{y}-07-01" for y in p2["season"]]).astype("datetime64[us]")
    static = dams.set_index("uid")
    for column in STATIC_COLUMNS + ["log_n_pixels"]:
        p2[column] = p2["uid"].map(static[column]).to_numpy()
    p2["split"] = time_block(p2["issue_date"])
    dam_index = p2["uid"].map(pd.Series(np.arange(len(dams)), index=dams["uid"])).to_numpy()

    # History checkpoint for the season year (looks before 1 Jan of that year).
    k = checkpoints.checkpoint_index(p2["season"].to_numpy())
    for stat in ("full_c", "wet_share_c", "fill_share_c", "n_hist_c"):
        p2[stat] = np.where(k >= 0, ck[stat][dam_index, np.maximum(k, 0)], np.nan)

    # Neighbours at the 1 Jul grid date (their looks strictly before 1 Jul).
    issue = day_numbers(p2["issue_date"])
    g = np.searchsorted(day_numbers(grid["grid"]), issue, side="right") - 1
    for name in ("R_anom", "R_chg3", "R_zero"):
        p2[name] = np.where(g >= 0, grid[name][dam_index, np.maximum(g, 0)], np.nan)

    # P1 dam rates at the state look, with that look's half-year prior.
    state_day = p2["state_day"].to_numpy()
    state_month = pd.DatetimeIndex(dates_from_day_numbers(np.maximum(state_day, 0))).month
    p2["warm"] = is_warm_season(state_month)
    p2 = issues.add_dam_rates(p2, prior, kinds=("D0", "R30"))
    p2 = p2.drop(columns=["warm", "b2S_D0", "b2N_D0", "b2S_R30", "b2N_R30"])   # P1 counts were only needed for the rates

    for name, values in rain.season_rain_features(rain_feats, p2["silo_cell"], p2["season"].to_numpy()).items():
        p2[name] = values
    p2 = p2.sort_values(["uid", "season"]).reset_index(drop=True)
    p2 = season.add_track_record(p2)
    season.assert_no_season_data(p2)
    return to_float32(p2)


def build_all(panel, attrs, events, rain_by_cell, verbose=True):
    """Build P1, P2 dam and P2 cell tables from the data layer (see the module docstring)."""
    say = progress_printer(verbose)
    warnings.filterwarnings("ignore", category=RuntimeWarning)   # nanmean of empty slices -> NaN, as intended
    dams = studied_dams(attrs)
    dam_uids = dams["uid"].to_numpy()
    looks = looks_of(panel, dam_uids)
    data_end = pd.Timestamp(looks["date"].max())
    data_end_day = int(day_numbers([data_end])[0])
    dl = DamLooks(looks, dam_uids)

    ck = checkpoints.build_checkpoints(looks, dam_uids)
    say(f"checkpoints for {len(dam_uids):,} dams")
    grid = build_grid(dl, ck, dams, data_end)
    say(f"neighbour grid: {len(grid['grid'])} dates, median {int(np.median(grid['n_neighbours']))} "
                    "neighbours per dam")
    # Rain months still running on the newest look's date are partial totals: blanked.
    rain_feats = rain.build_rain_features(rain_by_cell, data_end)
    say("rain window sums and causal percentiles")

    event_days = issues.event_days_by_dam(events)
    first_issue_day = int(day_numbers([config.FIRST_ISSUE_DATE])[0])
    seasons = season.season_years(data_end)
    p1_parts, p2_parts, prior_parts = [], [], []
    for i, uid in enumerate(dam_uids):
        dam = dams.iloc[i]
        p1_rows, p2_rows, prior_sums = one_dam(i, uid, dl, ck, grid, dam, event_days, data_end_day,
                                               first_issue_day, seasons)
        p1_parts.append(p1_rows)
        p2_parts.append(p2_rows)
        prior_parts.append(prior_sums)
        if (i + 1) % 1000 == 0:
            say(f"{i + 1:,} of {len(dam_uids):,} dams")
    prior = issues.combine_prior_sums(prior_parts)

    p1 = finish_p1(stack(p1_parts), dams, prior, rain_feats)
    say(f"P1 table: {len(p1):,} at-risk issues")
    p2_dam = finish_p2(stack(p2_parts), dams, ck, grid, prior, rain_feats)
    p2_cell = season.build_cell_table(p2_dam, attrs.assign(uid=attrs["uid"].astype(str)))
    p2_cell = to_float32(p2_cell)
    say(f"P2 tables: {len(p2_dam):,} dam-seasons, {len(p2_cell):,} cell-seasons")

    return {
        "p1": p1, "p2_dam": p2_dam, "p2_cell": p2_cell,
        "checkpoints": checkpoints.checkpoints_as_table(ck, dam_uids),
        "neighbour_grid": {"grid": grid["grid"].to_numpy(), "uids": dam_uids, "asof": grid["asof"],
                           "zero": grid["zero"], "R_anom": grid["R_anom"], "R_chg3": grid["R_chg3"],
                           "R_zero": grid["R_zero"], "n_neighbours": grid["n_neighbours"]},
        "dam_rate_prior": prior,
        "data_end": data_end,
    }
