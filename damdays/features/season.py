"""P2, the season rating: one forecast per dam (and per 2 km cell) every 1 July.

Question: will the dam go fully dry (D0) in the coming Oct-Mar?

What the forecast may use (issued 1 Jul of season year Y)
---------------------------------------------------------
* The dam's state from its LAST look strictly before 1 Jul, and only if that
  look is at most 60 days old (else the state is unknown: state_stale). All
  state features are the P1 dam-history features at that look, so they too
  use nothing after it.
* Checkpoint history for year Y (looks before 1 Jan Y), neighbours at the
  1 Jul grid date (looks strictly before 1 Jul), rain up to the end of June.
* Its record in EARLIER seasons: a season's window ends 31 Mar and any event
  in it is confirmed by 30 Apr, so every earlier season is final by 1 Jul.
Nothing from the coming Oct-Mar is used (checked by assert_no_season_data).

Labels (never features)
-----------------------
y          a D0 event starts between 1 Oct Y and 31 Mar Y+1
y_g        1 if a gradual D0 starts then; NaN if only abrupt D0s do; else 0
y_R30      an R30 event starts then
n_obs_win  valid looks in that window; label_ok = at least 3 and the window is in the data

Cells (2 km hexagons, dam-like dams only)
-----------------------------------------
y       the cell fails only if ALL its dam-like dams hit D0 (PREREG)
y_best  secondary label: D0 of the cell's most reliable dam (highest pre-2016 wet share,
        ties to the larger dam). The pre-2016 choice only decides which label is
        reported, never a feature value.
"""
import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import time_block
from damdays.features.common import day_numbers

# State features copied from the last look before 1 Jul.
STATE_COLUMNS = [
    "rel", "pc", "last3", "s60", "s120", "rec", "max365", "min365", "since_full", "anom_own", "armed",
    "since_arm", "low365_D0", "since_low_D0", "dtt_trend_D0", "dtt_clim_D0", "dtt_fast_D0", "low365_R30",
    "since_low_R30", "b2S_D0", "b2N_D0", "b2S_R30", "b2N_R30",
]


def season_years(data_end):
    """Season years Y whose 1 Jul issue date is on or before the end of the data."""
    data_end = pd.Timestamp(data_end)
    last = data_end.year if data_end >= pd.Timestamp(data_end.year, 7, 1) else data_end.year - 1
    return np.arange(config.P2_FIRST_SEASON, last + 1)


def issue_days(years):
    """Day numbers of 1 Jul of each season year."""
    return day_numbers(pd.to_datetime([f"{y}-07-01" for y in years]))


def window_days(years):
    """(first, last) day numbers of each season's label window: 1 Oct Y to 31 Mar Y+1."""
    first = day_numbers(pd.to_datetime([f"{y}-10-01" for y in years]))
    last = day_numbers(pd.to_datetime([f"{y + 1}-03-31" for y in years]))
    return first, last


def state_look(look_days, season_issue_days):
    """Index of the last look strictly before each 1 Jul (-1 if none) and its age in days."""
    j = np.searchsorted(look_days, season_issue_days, side="left") - 1
    age = np.where(j >= 0, season_issue_days - look_days[np.maximum(j, 0)], np.nan)
    return j, age


def season_labels(look_days, event_days, years, data_end_day):
    """y, y_g, y_R30, n_obs_win and label_ok for one dam's seasons."""
    first, last = window_days(years)

    def starts_in_window(days):
        """How many of the sorted `days` fall in each season's window [1 Oct, 31 Mar]."""
        return np.searchsorted(days, last, side="right") - np.searchsorted(days, first, side="left")

    gradual = starts_in_window(event_days["D0g"]) > 0
    abrupt = starts_in_window(event_days["D0ab"]) > 0
    n_obs_win = starts_in_window(look_days)          # same counting, applied to looks
    return {
        "y": (starts_in_window(event_days["D0"]) > 0).astype(float),
        "y_g": np.where(gradual, 1.0, np.where(abrupt, np.nan, 0.0)),
        "y_R30": (starts_in_window(event_days["R30"]) > 0).astype(float),
        "n_obs_win": n_obs_win,
        "label_ok": (n_obs_win >= config.MIN_LABEL_OBS) & (last <= data_end_day),
    }


def dam_season_rows(uid, look_days, look_features, event_days, data_end_day, years):
    """One dam's P2 rows: state at the last look before 1 Jul plus labels (dict of arrays)."""
    issue = issue_days(years)
    j, age = state_look(look_days, issue)
    fresh = (j >= 0) & (age <= config.P2_MAX_STATE_AGE_DAYS)
    rows = {"uid": np.repeat(uid, len(years)), "season": years, "age": age, "state_stale": ~fresh}
    rows["state_day"] = np.where(j >= 0, look_days[np.maximum(j, 0)], -1)   # for the no-peeking check
    for column in STATE_COLUMNS:
        values = np.full(len(years), np.nan)
        values[fresh] = look_features[column][j[fresh]]
        rows[column] = values
    rows.update(season_labels(look_days, event_days, years, data_end_day))
    return rows


def assert_no_season_data(p2):
    """Fail loudly if any state look is on or after its 1 Jul issue date (it never should be)."""
    issue = day_numbers(p2["issue_date"])
    used = p2["state_day"].to_numpy()
    bad = (used >= 0) & (used >= issue)
    if bad.any():
        raise AssertionError(f"{int(bad.sum())} season ratings use a look on or after 1 Jul")


# ---------------------------------------------------------------------------
# Track record across seasons (causal: only earlier seasons)
# ---------------------------------------------------------------------------
def past_season_counts(table, label, group="uid"):
    """For each row: (sum, count) of `label` over EARLIER label_ok seasons of the same dam or cell."""
    usable = table["label_ok"].to_numpy(bool) & table[label].notna().to_numpy()
    value = np.where(usable, table[label].to_numpy(float), 0.0)
    helper = pd.DataFrame({group: table[group].to_numpy(), "v": value, "n": usable.astype(float)})
    by = helper.groupby(group, sort=False)
    # cumulative sum including this season, minus this season = earlier seasons only
    return (by["v"].cumsum() - helper["v"]).to_numpy(), (by["n"].cumsum() - helper["n"]).to_numpy()


def last_seasons(table, label, n_back, group="uid"):
    """Label of the season n_back years earlier (NaN if that season was not label_ok)."""
    value = table[label].where(table["label_ok"])
    return value.groupby(table[group].to_numpy()).shift(n_back).to_numpy()


def mean_of_last(table, label, window, group="uid"):
    """Mean of the label over the previous `window` seasons that were label_ok (NaN if none)."""
    value = table[label].where(table["label_ok"])
    shifted = value.groupby(table[group].to_numpy()).shift(1)
    return shifted.groupby(table[group].to_numpy()).transform(
        lambda s: s.rolling(window, min_periods=1).mean()).to_numpy()


def add_track_record(p2):
    """b2 counts, lags and shrunk past-season rates for the dam table (sorted by uid, season)."""
    p2["b2S"], p2["b2N"] = past_season_counts(p2, "y")
    p2["b2S_g"], p2["b2N_g"] = past_season_counts(p2, "y_g")
    p2["b2S_R30_seasons"], p2["b2N_R30_seasons"] = past_season_counts(p2, "y_R30")
    p2["lag1"] = last_seasons(p2, "y", 1)
    p2["lag2"] = last_seasons(p2, "y", 2)
    p2["rate5"] = mean_of_last(p2, "y", 5)
    p2["lag1_R30"] = last_seasons(p2, "y_R30", 1)
    p2["rate_R30"] = (p2["b2S_R30_seasons"] + 1.0) / (p2["b2N_R30_seasons"] + 2.0)   # Laplace-smoothed past R30-season rate

    # Shrink the dam's own past D0-season rate toward the region's TRAIN-season
    # rate (k = 5, PREREG). TRAIN seasons (issued 1989-2008) all end long before VAL.
    k = config.B2_SHRINK_P2
    train = (p2["split"] == "TRAIN") & p2["label_ok"]
    for suffix, label in (("", "y"), ("_g", "y_g")):
        prior = p2[train & p2[label].notna()].groupby("region")[label].mean()
        prior_rate = p2["region"].map(prior).astype(float)
        p2[f"dam_rate_P2{suffix}"] = (p2[f"b2S{suffix}"] + k * prior_rate) / (p2[f"b2N{suffix}"] + k)
    return p2


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------
def most_reliable_dam(attrs):
    """uid of each cell's most reliable dam-like dam: highest pre-2016 wet share, ties to the larger dam."""
    dam_like = attrs[attrs["dam_like"]].sort_values(
        ["hex_id", "wet_share", "n_pixels", "uid"], ascending=[True, False, False, True])
    return dam_like.groupby("hex_id")["uid"].first()


CELL_MEAN_COLUMNS = ["R_anom", "R_chg3", "R_zero", "rain_sum1", "rain_sum3", "rain_sum6", "rain_sum12",
                     "rain_sum24", "rain_pctc1", "rain_pctc3", "rain_pctc6", "rain_pctc12", "rain_pctc24",
                     "drought10", "clim_ann", "clim_cv", "clim_om", "rain12_anom"]


def build_cell_table(p2_dam, attrs):
    """One row per 2 km cell x season, over the cell's dam-like dams (see the module docstring)."""
    dams = p2_dam[p2_dam["dam_like"]].copy()
    dams["y_l"] = dams["y"].where(dams["label_ok"])
    best = most_reliable_dam(attrs)
    dams["is_best"] = dams["uid"].isin(set(best.to_numpy()))

    agg = {
        "region": ("region", "first"), "issue_date": ("issue_date", "first"), "split": ("split", "first"),
        "n_dams": ("uid", "size"), "n_label_ok": ("label_ok", "sum"),
        "y_all": ("y_l", "min"), "y_any": ("y_l", "max"), "frac_fail": ("y_l", "mean"),
        "rel_max": ("rel", "max"), "rel_mean": ("rel", "mean"), "rel_min": ("rel", "min"),
        "armed_mean": ("armed", "mean"), "low365_D0_mean": ("low365_D0", "mean"),
        "min365_max": ("min365", "max"), "dam_rate_P2_mean": ("dam_rate_P2", "mean"),
        "dam_rate_P2_min": ("dam_rate_P2", "min"), "dam_rate_D0_mean": ("dam_rate_D0", "mean"),
    }
    agg.update({c: (c, "mean") for c in CELL_MEAN_COLUMNS})
    cells = dams.groupby(["hex_id", "season"], sort=True).agg(**agg).reset_index()

    best_rows = dams[dams["is_best"]][["hex_id", "season", "uid", "y_l"]].rename(
        columns={"uid": "best_uid", "y_l": "y_best"})
    cells = cells.merge(best_rows, on=["hex_id", "season"], how="left")
    cells["label_ok"] = cells["n_label_ok"] == cells["n_dams"]
    cells["y"] = cells["y_all"].where(cells["label_ok"])    # all dams failed (min of 0/1 labels)
    cells = cells.drop(columns=["y_all"])
    cells["rain_decile12"] = np.clip(np.floor(cells["rain_pctc12"] * 10) + 1, 1, 10)
    cells["rain_decile24"] = np.clip(np.floor(cells["rain_pctc24"] * 10) + 1, 1, 10)

    # Cell geometry and folds. Folds come from the cell's most reliable dam, so
    # they never depend on which other cells are in the table.
    best_attrs = attrs.set_index("uid").loc[best.to_numpy()]
    geo = pd.DataFrame({
        "hex_id": best.index, "hex_q": best_attrs["hex_q"].to_numpy(), "hex_r": best_attrs["hex_r"].to_numpy(),
        "fold5": best_attrs["fold5"].to_numpy(), "sfold5": best_attrs["sfold5"].to_numpy(),
        "tile": best_attrs["tile"].to_numpy(),
    })
    centre = attrs[attrs["dam_like"]].groupby("hex_id")[["lat", "lon"]].mean()
    cells = cells.merge(geo, on="hex_id", how="left").merge(centre, left_on="hex_id", right_index=True, how="left")

    cells = cells.sort_values(["hex_id", "season"]).reset_index(drop=True)
    cells["b2S"], cells["b2N"] = past_season_counts(cells, "y", group="hex_id")
    cells["cell_lag1"] = last_seasons(cells, "y", 1, group="hex_id")
    cells["cell_rate5"] = mean_of_last(cells, "y", 5, group="hex_id")
    cells["uid"] = cells["hex_id"]          # the scorecard's id column
    return cells
