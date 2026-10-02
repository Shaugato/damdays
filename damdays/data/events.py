"""Find the dry-out events we forecast, exactly as defined in PREREG.md.

Terms
-----
full   the dam's own 90th-percentile pc_wet before 2016 (attributes.py).
rel    pc_wet / full: how full the dam looks compared with its usual "full".
look   one valid satellite observation (one row of the panel).

The two event kinds
-------------------
D0   fully dry:    0 wet pixels on 2 consecutive looks at most 30 days apart.
R30  below a third: rel < 0.30 on 2 consecutive looks at most 30 days apart.

Both only count when the dam is ARMED: it showed rel >= 0.60 at some look in
the 180 days before the first low look. Arming stops us counting the same
long dry spell again and again: after an event, the dam must refill to 60%
(re-arm) before another event of that kind can start. D0 and R30 are tracked
separately, each with its own arming.

The event date ("start") is the first of the two confirming looks.

Abrupt vs gradual D0
--------------------
A D0 is ABRUPT when the last look with any water before it still showed
rel >= 0.40 and was at most 60 days earlier. Evaporation cannot empty that
much water that fast, so such events are often satellite artefacts (turbid
water, shadow) rather than a real dry-out. D0-gradual (D0g) = D0 that is not
abrupt.

Worked example (full = 50% wet, one look every ~2 weeks):
    day     0   14   28   42   56   70
    pc_wet 40   20   10    0    0   35
    rel   0.8  0.4  0.2  0.0  0.0  0.7
  - day 0 arms the dam (rel 0.8 >= 0.6).
  - R30: days 28 and 42 are both below 0.3, 14 days apart, armed 28 days ago
    -> R30 event starting day 28.
  - D0:  days 42 and 56 have 0 wet pixels -> D0 event starting day 42.
    The last wet look was day 28 with rel 0.2 < 0.4 -> gradual (D0g).
  - day 70 re-arms both kinds.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import hydro_year

EVENT_KINDS = ("D0", "R30")

# Columns of one event row, as made by events_for_one_dam. Listed here so that
# an empty result (no dam had an event) still has the right columns.
EVENT_ROW_COLUMNS = (
    "uid", "kind", "start_date", "confirm_date", "arm_date",
    "rel_at_start", "abrupt", "last_wet_date", "last_wet_rel",
)


@dataclass
class Event:
    """One event in a single dam's series, by position in that series."""
    start_index: int     # first confirming look (the event date)
    confirm_index: int   # second confirming look
    arm_day: int         # day number of the most recent arming look


def is_low(pc_wet, px_wet, full, kind):
    """For each look: is the dam "low" for this event kind?"""
    if kind == "D0":
        return px_wet == 0
    if kind == "R30":
        return (pc_wet / full) < config.R30_LEVEL
    raise ValueError(f"unknown event kind: {kind}")


def find_events(days, pc_wet, px_wet, full, kind):
    """Run the armed event state machine over one dam's looks.

    days    whole-day numbers of each look, sorted ascending (any day origin)
    pc_wet  percent wet at each look
    px_wet  wet pixels at each look
    full    the dam's static "full" level (must be > 0)
    kind    "D0" or "R30"

    Returns a list of Event.
    """
    if len(days) < 2 or not full > 0:
        return []

    # Plain Python lists are much faster than numpy for a step-by-step loop.
    days = [int(d) for d in days]
    rel = (np.asarray(pc_wet, dtype=float) / full).tolist()
    low = is_low(np.asarray(pc_wet, dtype=float), np.asarray(px_wet, dtype=float), full, kind).tolist()

    events = []
    last_arm_day = None  # None means "not armed"
    for i in range(len(days) - 1):
        if rel[i] >= config.ARM_LEVEL:
            last_arm_day = days[i]  # the dam is (re)filled: arm it
            continue
        if last_arm_day is None:
            continue

        armed_recently = days[i] - last_arm_day <= config.ARM_WINDOW_DAYS
        two_low_looks = low[i] and low[i + 1]
        close_together = days[i + 1] - days[i] <= config.CONFIRM_GAP_DAYS
        if armed_recently and two_low_looks and close_together:
            events.append(Event(start_index=i, confirm_index=i + 1, arm_day=last_arm_day))
            last_arm_day = None  # must refill before the next event of this kind
    return events


def describe_abruptness(days, pc_wet, px_wet, full, start_index):
    """For a D0 event: look back to the last look with water before it.

    Returns (abrupt, last_wet_index). last_wet_index is None if the dam never
    showed water before the event (then the event is not called abrupt).
    """
    earlier_wet = np.flatnonzero(np.asarray(px_wet[:start_index]) > 0)
    if len(earlier_wet) == 0:
        return False, None
    j = int(earlier_wet[-1])
    still_fairly_full = pc_wet[j] / full >= config.ABRUPT_REL
    recent = days[start_index] - days[j] <= config.ABRUPT_GAP_DAYS
    return bool(still_fairly_full and recent), j


def events_for_one_dam(uid, dates, pc_wet, px_wet, full):
    """All D0 and R30 events of one dam, as a list of row dicts."""
    days = dates.astype("datetime64[D]").astype(np.int64)
    rows = []
    for kind in EVENT_KINDS:
        for event in find_events(days, pc_wet, px_wet, full, kind):
            i = event.start_index
            row = {
                "uid": uid,
                "kind": kind,
                "start_date": dates[i],
                "confirm_date": dates[event.confirm_index],
                "arm_date": np.datetime64(event.arm_day, "D"),
                "rel_at_start": pc_wet[i] / full,
                "abrupt": np.nan,
                "last_wet_date": pd.NaT,
                "last_wet_rel": np.nan,
            }
            if kind == "D0":
                abrupt, j = describe_abruptness(days, pc_wet, px_wet, full, i)
                row["abrupt"] = abrupt
                if j is not None:
                    row["last_wet_date"] = dates[j]
                    row["last_wet_rel"] = pc_wet[j] / full
            rows.append(row)
    return rows


def build_events(panel, attrs):
    """Find every event of every has_hist waterbody.

    Returns one row per event with columns:
      uid, region, kind (D0 | R30), start_date, confirm_date, arm_date,
      rel_at_start, abrupt (D0 only), gradual (True for D0g), last_wet_date,
      last_wet_rel, hydro_year (Jul-Jun year of the start), dam_like, persistent.
    """
    full_of = dict(zip(attrs["uid"], attrs["full"]))
    studied = set(attrs.loc[attrs["has_hist"], "uid"])
    panel = panel.sort_values(["uid", "date"])  # the state machine walks each dam's looks in time order

    rows = []
    for uid, looks in panel.groupby("uid", observed=True, sort=True):
        if uid not in studied:
            continue
        rows += events_for_one_dam(
            uid,
            looks["date"].to_numpy(),
            looks["pc_wet"].to_numpy(dtype=float),
            looks["px_wet"].to_numpy(dtype=float),
            full_of[uid],
        )

    events = pd.DataFrame(rows, columns=list(EVENT_ROW_COLUMNS))
    for column in ("start_date", "confirm_date", "arm_date", "last_wet_date"):
        events[column] = pd.to_datetime(events[column]).astype("datetime64[us]")  # same unit as the panel
    events["gradual"] = (events["kind"] == "D0") & (events["abrupt"] == False)  # noqa: E712
    events["hydro_year"] = hydro_year(events["start_date"])

    flags = attrs[["uid", "region", "dam_like", "persistent"]]
    events = events.merge(flags, on="uid", how="left")
    return events.sort_values(["uid", "kind", "start_date"]).reset_index(drop=True)


def count_events(events, population=None):
    """Number of D0, R30 and D0g events, optionally within one population flag column."""
    if population is not None:
        events = events[events[population]]
    return {
        "D0": int((events["kind"] == "D0").sum()),
        "R30": int((events["kind"] == "R30").sum()),
        "D0g": int(events["gradual"].sum()),
    }
