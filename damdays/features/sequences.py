"""The 24-month input sequences of the sequence net (Tidemark member S).

What the net sees
-----------------
For a forecast issued on day D, the sequence net reads the dam's last 24
COMPLETE calendar months: the months strictly before D's month. A forecast on
9 July 2014 reads July 2012 to June 2014, never July 2014 itself (that month
was not over on 9 July). Each month is 9 numbers ("channels"):

    rel            the dam's mean level in that month, divided by its "full" level
                   (the forecast's own checkpoint full_c), carried forward from the
                   last month that had a look; clipped to [0, 1.5], 0 if never seen
    observed       1 if the dam had a valid satellite look in that month, else 0
    months_since   months since the last month with a look (capped at 36), / 12
    dry_share      share of that month's looks that were fully dry, carried forward
    log_rain       log(1 + rain in mm) at the dam's SILO cell, / 5
    rain_anomaly   log_rain minus the cell's 1960-1986 average for that calendar month
    month_sin      time of year (sine of the calendar month)
    month_cos      time of year (cosine)
    has_level      1 once the dam has been seen at least once, else 0

Why it cannot see the future
----------------------------
* Monthly values come only from looks INSIDE that month, and "carried
  forward" values only from earlier months. The window ends at the month
  before the issue month, so every look it uses is dated before D.
* Rain: the window's months all ended before D. The anomaly baseline is
  1960-1986, before the satellite archive starts, so it is in the past of
  every forecast (the first forecast is in 1988). A rain month that had not
  ended by the newest look in the archive is a partial total and is blanked
  (damdays.features.rain.blank_unfinished_months); a blank month is read as a
  normal month (anomaly 0). No historical forecast has a blank month.
* The normaliser is the forecast's own causal checkpoint full_c (looks before
  1 Jan of its year). Where full_c is unknown, the highest monthly level seen
  inside the window is used instead (also in the past).

tests/test_no_lookahead.py proves it: it deletes every look and rain month
after a cut date, rebuilds the monthly table and every sequence, and checks
that nothing dated before the cut changed (generator "net sequences").

The design follows the pre-event neural-sequence research (TCN input block),
re-implemented here.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from damdays import config
from damdays.features import checkpoints, rain
from damdays.features.build import looks_of, studied_dams

SEQUENCE_MONTHS = 24                    # the window: the 24 complete months before the issue month
FIRST_YEAR = 1986                       # month index 0 = January 1986 (the archive starts in August 1986)
RAIN_CLIMATOLOGY_YEARS = (1960, 1986)   # anomaly baseline: before the archive, so before every forecast
MONTHS_SINCE_CAP = 36                   # "months since the last look" is capped at 3 years
NEVER_SEEN = 99                         # months_since before a dam's first look (capped to 36 in the sequence)
LOG_RAIN_SCALE = 5.0                    # log(1 + mm) is divided by 5 so it sits near 0-1.3
CHANNELS = ("rel", "observed", "months_since", "dry_share", "log_rain", "rain_anomaly",
            "month_sin", "month_cos", "has_level")


# ===========================================================================
# 1. One row per dam and calendar month
# ===========================================================================
@dataclass
class MonthlyHistory:
    """Every studied dam's month-by-month history (arrays of shape dams x months; month 0 = Jan 1986).

    uids          the studied dams (has_hist), sorted
    pc_ffill      mean % wet of the month's looks, carried forward from the last month with a look
    observed      1 if the month had at least one valid look
    months_since  months since the last month with a look (NEVER_SEEN before the first look)
    dry_ffill     share of the month's looks with no water, carried forward
    log_rain      log(1 + rain) at the dam's SILO cell (a blank month holds the climatology)
    rain_anomaly  log_rain minus the cell's 1960-1986 mean for that calendar month (0 for a blank month)
    data_end      the newest look in the archive (rain months still running then are blanked)
    """
    uids: np.ndarray
    pc_ffill: np.ndarray
    observed: np.ndarray
    months_since: np.ndarray
    dry_ffill: np.ndarray
    log_rain: np.ndarray
    rain_anomaly: np.ndarray
    data_end: pd.Timestamp

    @property
    def n_months(self):
        """How many calendar months the arrays hold (Jan 1986 to the month of data_end)."""
        return self.pc_ffill.shape[1]

    def as_table(self):
        """Long table (uid, month, month_complete, channels) for inspection and the look-ahead test.

        month_complete is the first day of the next month: the day the month's values are final.
        """
        n_dams, n_months = self.pc_ffill.shape
        starts = month_start(np.arange(n_months))
        table = pd.DataFrame({"uid": np.repeat(self.uids, n_months),
                              "month": np.tile(starts.strftime("%Y-%m").to_numpy(), n_dams),
                              "month_complete": np.tile((starts + pd.offsets.MonthBegin(1)).to_numpy(), n_dams)})
        for name in ("pc_ffill", "observed", "months_since", "dry_ffill", "log_rain", "rain_anomaly"):
            table[name] = getattr(self, name).reshape(-1)
        return table


def month_index(dates):
    """Months since January 1986 (0 = Jan 1986) of each date."""
    dates = pd.DatetimeIndex(pd.to_datetime(dates))
    return ((dates.year.to_numpy() - FIRST_YEAR) * 12 + dates.month.to_numpy() - 1).astype(np.int64)


def month_start(index):
    """The first day of each month index (inverse of month_index)."""
    index = np.asarray(index)
    years, months = FIRST_YEAR + index // 12, index % 12 + 1
    return pd.DatetimeIndex(pd.to_datetime({"year": years, "month": months, "day": np.ones_like(index)}))


def monthly_sums(dam_of_look, month_of_look, values, n_dams, n_months):
    """Sum of `values` over the looks of each (dam, month); a (dams x months) array."""
    out = np.zeros((n_dams, n_months))
    np.add.at(out, (dam_of_look, month_of_look), values)
    return out


def carry_forward(values, observed):
    """Each month's value, or the last earlier month's value if the month had no look.

    Returns (filled values, months since the last month with a look). Only the
    month itself and earlier months are used, so this is causal.
    """
    n_dams, n_months = values.shape
    last_seen = np.where(observed, np.arange(n_months)[None, :], -1)
    np.maximum.accumulate(last_seen, axis=1, out=last_seen)
    seen = last_seen >= 0
    rows = np.arange(n_dams)[:, None]
    filled = np.where(seen, values[rows, np.maximum(last_seen, 0)], np.nan)
    since = np.where(seen, np.arange(n_months)[None, :] - last_seen, NEVER_SEEN)
    return filled.astype(np.float32), since.astype(np.float32)


def monthly_rain(rain_by_cell, dam_cells, n_months, data_end):
    """log(1 + rain) and its anomaly for each dam (its SILO cell) and month, from January 1986.

    The anomaly baseline is the cell's mean log rain for the same calendar month
    over 1960-1986. A month that is missing or still running on `data_end` is
    blank: it is read as a normal month (log rain = baseline, anomaly 0).
    """
    months = np.asarray(rain_by_cell["months"])
    rain_mm = rain.blank_unfinished_months(rain_by_cell["rain"].astype(np.float64), months, data_end)
    log_mm = np.log1p(rain_mm)
    first, last = RAIN_CLIMATOLOGY_YEARS
    years, calendar = months // 100, months % 100
    in_baseline = (years >= first) & (years <= last)
    baseline = np.stack([np.nanmean(log_mm[:, in_baseline & (calendar == m)], axis=1) for m in range(1, 13)],
                        axis=1)                                            # (cells, 12)

    cell_row = pd.Index(np.asarray(rain_by_cell["cells"]).astype(str)).get_indexer(np.asarray(dam_cells).astype(str))
    if (cell_row < 0).any():
        raise ValueError("Some dams have a SILO cell with no rainfall series.")
    wanted = np.array([(FIRST_YEAR + k // 12) * 100 + k % 12 + 1 for k in range(n_months)])
    column = pd.Index(months).get_indexer(wanted)                          # -1: month not in the rain data
    values = np.full((len(cell_row), n_months), np.nan)
    present = column >= 0
    values[:, present] = log_mm[cell_row][:, column[present]]
    normal = baseline[cell_row][:, np.arange(n_months) % 12]
    blank = ~np.isfinite(values)
    values[blank] = normal[blank]
    return values.astype(np.float32), (values - normal).astype(np.float32)


def build_monthly_history(panel, attrs, rain_by_cell):
    """The MonthlyHistory of every studied dam, from the data layer (scripts/01_build_data.py).

    Dams and looks are chosen exactly as in damdays.features.build (has_hist dams,
    their valid looks, sorted by uid then date).
    """
    dams = studied_dams(attrs)
    dam_uids = dams["uid"].to_numpy()
    looks = looks_of(panel, dam_uids)
    data_end = pd.Timestamp(looks["date"].max())
    n_months = int(month_index([data_end])[0]) + 1
    dam_of_look = pd.Index(dam_uids).get_indexer(looks["uid"].to_numpy())
    month_of_look = month_index(looks["date"])

    count = monthly_sums(dam_of_look, month_of_look, 1.0, len(dam_uids), n_months)
    pc_sum = monthly_sums(dam_of_look, month_of_look, looks["pc_wet"].to_numpy(dtype=float), len(dam_uids), n_months)
    dry_sum = monthly_sums(dam_of_look, month_of_look, (looks["px_wet"].to_numpy() == 0).astype(float),
                           len(dam_uids), n_months)
    observed = count > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        pc_mean, dry_share = pc_sum / count, dry_sum / count
    pc_ffill, months_since = carry_forward(pc_mean, observed)
    dry_ffill, _ = carry_forward(dry_share, observed)
    log_rain, rain_anomaly = monthly_rain(rain_by_cell, dams["silo_cell"].to_numpy(), n_months, data_end)
    return MonthlyHistory(uids=dam_uids, pc_ffill=pc_ffill, observed=observed.astype(np.float32),
                          months_since=months_since, dry_ffill=dry_ffill, log_rain=log_rain,
                          rain_anomaly=rain_anomaly, data_end=data_end)


# ===========================================================================
# 2. One sequence per forecast
# ===========================================================================
def sequence_rows(history, uids, issue_dates):
    """Where each forecast's sequence comes from: (dam row in `history`, issue month index)."""
    dam_row = pd.Index(history.uids).get_indexer(np.asarray(uids).astype(str))
    if (dam_row < 0).any():
        raise ValueError("Some forecasts are for dams that are not in the monthly history.")
    return dam_row.astype(np.int64), month_index(issue_dates)


def window_months(issue_month, window_end_offset=1):
    """Month indices of each forecast's window, oldest first: (n, 24).

    window_end_offset=1 ends the window at the month BEFORE the issue month (the
    last complete month): the time rule. 0 would include the issue month itself,
    which is not over on the issue day; only the look-ahead test uses it, as a
    planted leak that must be caught.
    """
    offsets = np.arange(SEQUENCE_MONTHS - 1 + window_end_offset, window_end_offset - 1, -1)
    months = np.asarray(issue_month)[:, None] - offsets[None, :]
    if (months < 0).any():
        raise ValueError("A forecast's 24-month window starts before January 1986.")
    return months


def level_normaliser(full_c, levels):
    """The level that counts as "full" for each forecast: its checkpoint full_c, else the window's highest level.

    levels  (n, 24) carried-forward monthly levels in the window (% wet)
    The fallback (no trusted checkpoint yet) is at least 1% so rel stays finite.
    """
    full_c = np.asarray(full_c, dtype=np.float64)
    trusted = np.isfinite(full_c) & (full_c > 0)
    window_max = np.max(np.where(np.isfinite(levels), levels, -np.inf), axis=1)
    fallback = np.maximum(np.where(np.isfinite(window_max), window_max, 1.0), 1.0)
    return np.where(trusted, full_c, fallback)


def issue_sequences(history, dam_row, issue_month, full_c, window_end_offset=1):
    """The (n, 24, 9) float32 input sequences for n forecasts (channels in CHANNELS order).

    dam_row, issue_month   from sequence_rows
    full_c                 each forecast's checkpoint "full" (% wet; NaN where unknown)
    """
    months = window_months(issue_month, window_end_offset)
    dams = np.asarray(dam_row)[:, None]
    levels = history.pc_ffill[dams, months].astype(np.float64)
    full = level_normaliser(full_c, levels)
    rel = np.nan_to_num(np.clip(levels / full[:, None], 0.0, 1.5), nan=0.0)
    angle = 2 * np.pi * (months % 12) / 12.0
    channels = [
        rel,
        history.observed[dams, months],
        np.minimum(history.months_since[dams, months], MONTHS_SINCE_CAP) / 12.0,
        np.nan_to_num(history.dry_ffill[dams, months], nan=0.0),
        history.log_rain[dams, months] / LOG_RAIN_SCALE,
        history.rain_anomaly[dams, months],
        np.sin(angle),
        np.cos(angle),
        np.isfinite(levels).astype(np.float64),
    ]
    return np.stack(channels, axis=-1).astype(np.float32)


# ===========================================================================
# 3. For the look-ahead test
# ===========================================================================
FINGERPRINT_SEED = 2026


def fingerprints(sequences):
    """A 64-bit fingerprint of each forecast's 216 numbers (any change to any bit changes it).

    Each number's bit pattern is multiplied by its own fixed odd 64-bit constant
    and the products are summed (wrapping around at 2^64). Two sequences with
    the same fingerprint are identical except with odds of about 1 in 2^64.
    It lets the look-ahead test compare millions of sequences without storing them.
    """
    flat = np.ascontiguousarray(sequences, dtype=np.float32).reshape(len(sequences), -1).view(np.uint32)
    weights = np.random.default_rng(FINGERPRINT_SEED).integers(0, 2 ** 63, flat.shape[1], dtype=np.uint64) * 2 + 1
    return (flat.astype(np.uint64) * weights[None, :]).sum(axis=1, dtype=np.uint64).view(np.int64)


def every_issue(panel, attrs):
    """Every valid look of a studied dam from 1988 on (a superset of the P1 forecasts), with its full_c.

    full_c is the causal checkpoint "full" for the look's year, built exactly as
    in damdays.features.build (checkpoint of the year, looks before 1 Jan).
    """
    dams = studied_dams(attrs)
    dam_uids = dams["uid"].to_numpy()
    looks = looks_of(panel, dam_uids)
    ck = checkpoints.build_checkpoints(looks, dam_uids)
    looks = looks[looks["date"] >= pd.Timestamp(config.FIRST_ISSUE_DATE)].reset_index(drop=True)
    dam_index = pd.Index(dam_uids).get_indexer(looks["uid"].to_numpy())
    k = checkpoints.checkpoint_index(pd.DatetimeIndex(looks["date"]).year.to_numpy())
    full_c = np.where(k >= 0, ck["full_c"][dam_index, np.maximum(k, 0)], np.nan)
    return pd.DataFrame({"uid": looks["uid"].to_numpy(), "issue_date": looks["date"].to_numpy(), "full_c": full_c})


def sequence_table(history, issues, window_end_offset=1, chunk=100_000):
    """One row per forecast: its sequence fingerprint plus two readable values (last month's rel and rain)."""
    dam_row, issue_month = sequence_rows(history, issues["uid"], issues["issue_date"])
    full_c = issues["full_c"].to_numpy()
    prints, rel_last, rain_last = [], [], []
    for start in range(0, len(issues), chunk):
        part = slice(start, start + chunk)
        seq = issue_sequences(history, dam_row[part], issue_month[part], full_c[part], window_end_offset)
        prints.append(fingerprints(seq))
        rel_last.append(seq[:, -1, CHANNELS.index("rel")])
        rain_last.append(seq[:, -1, CHANNELS.index("log_rain")])
    return pd.DataFrame({"uid": issues["uid"].to_numpy(), "issue_date": issues["issue_date"].to_numpy(),
                         "sequence_fingerprint": np.concatenate(prints),
                         "rel_last_month": np.concatenate(rel_last), "log_rain_last_month": np.concatenate(rain_last)})


def lookahead_tables(panel, attrs, rain_by_cell):
    """What the look-ahead test compares for the sequences (see tests/test_no_lookahead.py).

    sequence_months  the monthly table (one row per dam and month)
    p1_sequences     one fingerprinted sequence per look from 1988 on
    and, for the test's own "can it fail?" checks: the MonthlyHistory and the issue list.
    """
    history = build_monthly_history(panel, attrs, rain_by_cell)
    issues = every_issue(panel, attrs)
    return {"sequence_months": history.as_table(), "p1_sequences": sequence_table(history, issues),
            "monthly_history": history, "sequence_issues": issues}
