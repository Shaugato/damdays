"""FEATURE_SPEC: exactly which columns a model may use, with the reason each is allowed.

Rule for every column below: at an issue dated D it uses only information that
existed on D (the look on D is the newest data point; rain and neighbour
values use data from strictly before D). docs/FEATURES.md explains each one in
plain language, and tests/test_no_lookahead.py proves it by rebuilding the
features with all later data deleted.

Kind placeholders: {K} is the event kind whose "low" definition applies (D0 or
R30; D0-gradual uses D0's), {R} is the kind whose track record applies (D0,
R30 or D0g).

Never model inputs:
  * LABEL_COLUMNS: they describe the future.
  * FORBIDDEN_COLUMNS: the PREREG static pre-2016 quantities (full, wet_share,
    fill_share, ...) and every column computed from them (the R30 at-risk
    flags, the dam_like / persistent population flags). They see up to 2015,
    so before 2016 they would leak. The static values themselves are not even
    in the feature tables; the causal "_c" versions are used.
  * Raw counts that grow with the archive (n_hist_c, b2S_*, b2N_*) are not P1
    tree inputs (PREREG); they are kept in the tables for the B2 baseline.
  * Region names, ids and location (uid, hex, tile, lat/lon, fold numbers):
    PREREG says no region identifier is a model input.
Not forbidden on purpose: the P2 cell column n_dams (how many dam-like dams
the cell has). It counts a pre-2016 population, but that same population IS
the question being asked: a cell fails when ALL of those dams go dry, and the
cell probability is the product over exactly those dams.
"""

# ---------------------------------------------------------------------------
# P1 farmer runway: the G2c set used by the Tidemark tree member (T) and by
# the G2 benchmark (which now also uses the causal dam_rate, see PREREG).
# ---------------------------------------------------------------------------
FEATURE_SPEC = [
    "rel",                # level now: pc_wet / full_c (causal checkpoint full), clipped to [0, 1.5]
    "last3",              # mean rel of the last 3 looks, current included (smooths one-off misreads)
    "s60",                # trend: least-squares slope of rel per day over looks in the last 60 days
    "s120",               # trend over the last 120 days
    "max365",             # highest rel among looks in the last 365 days
    "min365",             # lowest rel among looks in the last 365 days
    "low365_{K}",         # share of looks in the last 365 days that were "low" for kind K
    "log_n_pixels",       # dam size: log of the outline's Landsat pixel count (static geometry)
    "month",              # calendar month of the issue date
    "dtt_trend_{K}",      # log(1 + days to K's threshold) if rel keeps falling at the s60 trend
    "dam_rate_{R}",       # the dam's own past event rate (only forecasts whose answer was final by D), shrunk to the region rate
    "clim_dd",            # the dam's typical drawdown rate this half-year (checkpoint: looks before 1 Jan)
    "clim_fast",          # the dam's fast (20th percentile) Oct-Mar drawdown rate (checkpoint)
    "dtt_clim_{K}",       # log(1 + days to threshold) at the typical drawdown rate
    "dtt_fast_{K}",       # log(1 + days to threshold) at the fast drawdown rate
    "rec",                # change in rel per day since the highest look of the last 120 days
    "since_full",         # days since rel was last >= 0.9 (capped at 3650)
    "since_low_{K}",      # days since the last low look (capped at 3650)
    "anom_own",           # rel minus the dam's usual level for this calendar month in earlier years
    "sin_doy",            # time of year (sine of day of year)
    "cos_doy",            # time of year (cosine of day of year)
    "gap_prev",           # days since the previous valid look (how stale the history is)
    "full_c",             # the dam's "full" (90th pct of pc_wet) from looks before 1 Jan of the issue year
    "wet_share_c",        # share of looks before 1 Jan of the issue year that showed any water
    "fill_share_c",       # share of Jul-Jun years before 1 Jan of the issue year that reached 90% of full_c
    "pixel_compactness",  # outline compactness (static geometry; 1 = as compact as possible)
    "R_anom",             # median level anomaly of up to 300 neighbours within 100 km (their looks strictly before D)
    "R_chg3",             # median 3-month change in the neighbours' levels
    "R_zero",             # share of neighbours whose last look was fully dry
]


def p1_tree_features(kind):
    """FEATURE_SPEC filled in for one event kind: "R30", "D0" or "D0g"."""
    low_kind = "D0" if kind == "D0g" else kind
    return [c.replace("{K}", low_kind).replace("{R}", kind) for c in FEATURE_SPEC]


# ---------------------------------------------------------------------------
# P1 water-balance columns: rung L3 adds them to T and H (damdays.models.physics).
# Blank before 1993. The simulation starts from a Kalman-filtered level that
# uses looks up to D, actual rain of months that ended before D's month and the
# earlier-years average for D's own month; the 20 futures use the rain of the
# same calendar months 1-20 years earlier (all before D); the balance's
# parameters come from look pairs before 1 Jan of D's year.
# ---------------------------------------------------------------------------
PHYSICS_FEATURE_SPEC = [
    "ph_p_R30",           # share of 20 simulated 90-day futures that fall below 30% of full (while armed)
    "ph_p_D0",            # share that run dry (below half a pixel of the full wet area, while armed)
]


# ---------------------------------------------------------------------------
# P2 season rating (dam level, issued 1 Jul). The PREREG "HSN" set without
# the dropped regional block and without rain. State columns come from the
# last look before 1 Jul (at most 60 days old).
# ---------------------------------------------------------------------------
P2_FEATURE_SPEC = [
    # track record over earlier seasons (all final by 1 Jul)
    "dam_rate_P2",        # the dam's own past D0-season rate, shrunk to the region's TRAIN-season rate (k = 5)
    "b2N",                # number of earlier seasons with a known answer (history length)
    "dam_rate_D0",        # P1 dam_rate for D0 at the state look
    "dam_rate_R30",       # P1 dam_rate for R30 at the state look
    "lag1",               # did the dam go dry last season (NaN if that season's answer is unknown)
    "lag2",               # ... two seasons ago
    "rate5",              # share of the last 5 seasons (with a known answer) in which it went dry
    "rate_R30",           # smoothed share of earlier seasons in which it fell below a third
    "lag1_R30",           # did it fall below a third last season
    "full_c",             # checkpoint full for the season year (looks before 1 Jan)
    "wet_share_c",        # checkpoint wet share
    "fill_share_c",       # checkpoint fill share
    "n_hist_c",           # checkpoint number of looks (history length; P2 only)
    # shape (static geometry)
    "log_n_pixels",       # dam size
    "pixel_compactness",  # outline compactness
    "elongation",         # outline elongation
    # state at the last look before 1 Jul
    "rel", "pc", "last3", "s60", "s120", "rec", "max365", "min365", "since_full", "anom_own",
    "armed",              # was the dam at least 60% full in the 180 days before that look
    "since_arm",          # days since it was last 60% full
    "low365_D0", "since_low_D0", "dtt_trend_D0", "dtt_clim_D0", "dtt_fast_D0",
    "low365_R30", "since_low_R30",
    "age",                # days between that look and 1 Jul (at most 60)
    # neighbours at 1 Jul (their looks strictly before 1 Jul)
    "R_anom", "R_chg3", "R_zero",
]

# ---------------------------------------------------------------------------
# Baseline inputs (rainfall-only references and persistence)
# ---------------------------------------------------------------------------
PERS_INPUTS = ["rel"]                                            # PERS uses rel and rel squared
RAIN_INPUTS = ["rain_decile12", "rain_decile24", "drought10"]    # PREREG RAIN (defines the kill rule)
RAIN_PLUS_INPUTS = (                                             # RAIN+ (strongest rain-only reference)
    [f"rain_pctc{w}" for w in (1, 3, 6, 12, 24)] + [f"rain_sum{w}" for w in (3, 12, 24)]
    + ["drought10", "clim_ann", "clim_cv", "clim_om", "rain12_anom"]
)
P1_RAIN_COLUMNS = [f"rain_sum{w}" for w in (1, 3, 6, 12, 24)] + [f"rain_pctc{w}" for w in (1, 3, 6, 12, 24)]

# ---------------------------------------------------------------------------
# Columns that must never be model inputs
# ---------------------------------------------------------------------------
LABEL_COLUMNS = {
    # P1
    "y_D0", "y_R30", "y_D0g", "lab_tte_D0", "lab_tte_R30", "lab_tte_D0g",
    "n_obs_win", "window_closed", "label_ok",
    # P2 dam and cell
    "y", "y_g", "y_R30", "y_best", "y_any", "frac_fail", "n_label_ok",
}
FORBIDDEN_COLUMNS = {
    # PREREG static pre-2016 quantities: before 2016 they know the future.
    "full", "wet_share", "fill_share", "n_pre_obs", "full_static", "rel_static",
    # ... and columns computed from them. They decide WHICH rows are scored, never a feature value.
    "at_risk_R30", "elig_rescue_R30",                  # at-risk flags use the static full
    "dam_like", "persistent", "dam_like_persistent",   # population flags use the pre-2016 wet share
    # Identifiers and location (PREREG: no region identifier is a model input).
    "region", "is_nsw", "uid", "best_uid", "silo_cell", "hex_id", "hex_q", "hex_r", "tile",
    "lat", "lon", "fold5", "sfold5",                   # fold numbers are a function of uid / map tile
    # Bookkeeping: the P2 state look's absolute day number (the model uses its age instead).
    "state_day",
}


def check_feature_list(columns):
    """Raise if a proposed model input list contains a label or a forbidden column."""
    bad = sorted((set(columns) & LABEL_COLUMNS) | (set(columns) & FORBIDDEN_COLUMNS))
    if bad:
        raise ValueError(f"These columns must never be model inputs: {bad}")
    return list(columns)


# Every spec must pass its own check when this module is imported.
for _kind in ("R30", "D0", "D0g"):
    check_feature_list(p1_tree_features(_kind))
check_feature_list(P2_FEATURE_SPEC)
check_feature_list(RAIN_INPUTS + RAIN_PLUS_INPUTS + PERS_INPUTS)
check_feature_list(PHYSICS_FEATURE_SPEC)

# ---------------------------------------------------------------------------
# How the P1 table is stored: column groups with the same row order
# ---------------------------------------------------------------------------
P1_KEY_COLUMNS = [
    "uid", "region", "issue_date", "year", "hydro_year", "warm", "split", "fold5", "sfold5",
    "dam_like", "persistent", "dam_like_persistent", "hex_id", "silo_cell", "rain_month",
    "at_risk_D0", "at_risk_R30", "elig_rescue_D0", "elig_rescue_R30",
    "n_obs_win", "window_closed", "label_ok",
    "y_D0", "y_R30", "y_D0g", "lab_tte_D0", "lab_tte_R30", "lab_tte_D0g",
    "b2S_D0", "b2N_D0", "b2S_R30", "b2N_R30", "b2S_D0g", "b2N_D0g",
]
P1_NEIGHBOUR_COLUMNS = ["R_anom", "R_chg3", "R_zero"]
