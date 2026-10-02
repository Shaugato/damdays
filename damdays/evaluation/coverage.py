"""Checking the two uncertainty products: the season band and the DamDays floor.

Season band
    Every forecast is shown with a band, because some years are wetter or
    drier than any model expects. The band shifts the forecast's log-odds by
    the smallest and largest "year offsets" seen in an earlier backtest.
    A region-year's offset is the shift that would have made that year's
    forecasts right on average (calibration-in-the-large on its rows). The
    band "covers" a region-year when that year's own offset lies inside it.

DamDays floor
    "At least N days above a third, with 90% confidence." The floor covers a
    forecast when the dam did not fall below a third before day N. About 90%
    of forecasts should be covered.
"""
import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import hydro_year
from damdays.evaluation.bootstrap import cluster_bootstrap
from damdays.evaluation.metrics import calibration_in_the_large

MIN_ROWS_PER_REGION_YEAR = 200   # fewer rows than this: the year offset is too noisy to use
MIN_EVENTS_PER_REGION_YEAR = 5
FLOOR_TARGET = 0.90              # the floor promises 90% coverage
FLOOR_TOLERANCE = 0.02           # coverage from 0.88 to 0.92 counts as on target


# ---------------------------------------------------------------------------
# Season band
# ---------------------------------------------------------------------------
def region_year_offsets(y, p, region, issue_date, min_rows=MIN_ROWS_PER_REGION_YEAR,
                        min_events=MIN_EVENTS_PER_REGION_YEAR):
    """One row per region and July-June year: how far off, in log-odds, the forecasts were that year.

    offset > 0: more events than forecast (a drier year than the model expected).
    offset < 0: fewer events than forecast (a wetter year).
    Region-years with too few rows or events get used = False and no offset.
    """
    table = pd.DataFrame(dict(y=np.asarray(y, dtype=float), p=np.asarray(p, dtype=float),
                              region=pd.Series(region).astype(str).to_numpy(),
                              hydro_year=hydro_year(issue_date)))
    rows = []
    for (reg, year), part in table.groupby(["region", "hydro_year"], sort=True):
        events = int(part["y"].sum())
        used = len(part) >= min_rows and events >= min_events
        offset = calibration_in_the_large(part["y"].to_numpy(), part["p"].to_numpy()) if used else np.nan
        rows.append(dict(region_year=f"{reg}:{year}", region=reg, hydro_year=int(year), rows=len(part),
                         events=events, base_rate=part["y"].mean(), mean_p=part["p"].mean(),
                         offset=offset, used=used))
    return pd.DataFrame(rows)


def band_from_offsets(offsets):
    """The band (lowest, highest) offset over the usable region-years of a backtest."""
    used = offsets.loc[offsets["used"], "offset"]
    if used.empty:
        raise ValueError("No usable region-years to build a band from.")
    return float(used.min()), float(used.max())


def band_coverage(offsets, band_low, band_high):
    """How many usable region-years have their own offset inside [band_low, band_high].

    A year whose offset is above the band had more dry-outs than even the top
    of the band allowed ("drier than the band"); below the band, fewer ("wetter").
    """
    used = offsets[offsets["used"]]
    above = used[used["offset"] > band_high]
    below = used[used["offset"] < band_low]
    covered = len(used) - len(above) - len(below)
    return dict(band=[band_low, band_high], region_years=len(used), covered=covered,
                coverage=covered / len(used) if len(used) else np.nan,
                drier_than_band={r: o for r, o in zip(above["region_year"], above["offset"])},
                wetter_than_band={r: o for r, o in zip(below["region_year"], below["offset"])},
                not_used=int((~offsets["used"]).sum()))


# ---------------------------------------------------------------------------
# DamDays floor
# ---------------------------------------------------------------------------
def floor_coverage(floor_days, days_to_event, followup_days, *, uid=None, issue_date=None,
                   cap_days=None, target=FLOOR_TARGET, tolerance=FLOOR_TOLERANCE,
                   n_boot=500, seed=config.RANDOM_SEED, min_year_rows=500):
    """Share of forecasts whose floor held: the event did not start before day N.

    floor_days     N, the promised "at least N days" (inf = no event expected in range)
    days_to_event  days from the issue to the start of the next event; NaN or inf if none was seen
    followup_days  how many days after the issue we could watch the dam (data end, determinable span)
    cap_days       optional: floors above this are judged at this many days (e.g. 180)

    Which rows can be judged (a subtle point about time). A row is judged only
    when we watched the dam for at least N days, whatever happened. Example:
    N = 60, but the data stops 30 days after the issue. If the dam fell below a
    third on day 10, we know the floor failed; if it did not, we cannot tell.
    Counting such a row only when it failed would make the floor look worse
    than it is. So the decision to count a row looks only at the follow-up,
    never at the outcome.
    """
    floor = np.asarray(floor_days, dtype=float)
    if cap_days is not None:
        floor = np.minimum(floor, cap_days)
    event_day = np.asarray(days_to_event, dtype=float)
    event_day = np.where(np.isnan(event_day), np.inf, event_day)   # none seen = not before any day
    followup = np.asarray(followup_days, dtype=float)

    judged = followup >= floor          # decided by the follow-up alone, never by the outcome
    held = event_day >= floor           # the dam stayed above a third for at least N days
    coverage = float(held[judged].mean()) if judged.any() else np.nan
    out = dict(rows=int(len(floor)), rows_judged=int(judged.sum()),
               share_not_judged=float(1 - judged.mean()) if len(floor) else np.nan,
               coverage=coverage, target=target,
               on_target=bool(abs(coverage - target) <= tolerance) if judged.any() else False,
               median_floor_days=float(np.median(floor[judged])) if judged.any() else np.nan)
    if uid is not None and judged.any() and n_boot > 0:
        hit = held[judged].astype(float)

        def share_held(w):
            """Coverage on one dam-bootstrap replicate."""
            return dict(coverage=np.sum(w * hit) / np.sum(w)) if np.sum(w) > 0 else None

        out["ci_dam"], out["bootstrap"] = cluster_bootstrap(share_held, np.asarray(uid)[judged], n_boot, seed)
    if issue_date is not None and judged.any():
        years = pd.DataFrame(dict(year=hydro_year(np.asarray(issue_date)[judged]), held=held[judged]))
        by_year = years.groupby("year")["held"].agg(["mean", "size"])
        out["by_year"] = {int(y): dict(coverage=float(r["mean"]), rows=int(r["size"])) for y, r in by_year.iterrows()}
        big = by_year[by_year["size"] >= min_year_rows]
        if len(big):
            out["worst_year"] = dict(year=int(big["mean"].idxmin()), coverage=float(big["mean"].min()))
    return out
