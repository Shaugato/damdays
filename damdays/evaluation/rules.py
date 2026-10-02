"""The rules of the game: what can be scored, on which rows, and in which time block.

Tasks
    Each task is one forecast question (below). A task name is checked against
    this list, so a typo such as "P1_r30" cannot quietly open a fresh entry on
    the TEST ledger.

Time blocks (dates from damdays/config.py, logic from damdays/data/splits.py)
    VAL   issues 2009-01-01 to 2015-12-31: used for every design choice
    TEST  issues 2016-07-01 to 2026-06-30: each model is scored here once
    One scoring call holds rows from one block only. The block is read from the
    issue dates themselves, so nobody can score TEST rows while calling it
    something else.

Arenas
    dev     the two development regions (NSW Central West, western Vic / SE SA)
    sealed  the sealed region, opened once on Saturday
    TEST in the dev regions and TEST in the sealed region are two separate
    one-shot tests, so the ledger keeps them apart.

Subsets (combine with "+", for example "dam_like+octmar")
    all         every row passed in
    dam_like    dams that behave like farm dams         (column dam_like)
    persistent  dams that almost never dry out          (column persistent)
    octmar      forecasts issued October to March       (read from issue_date)
    at_risk     the dam was not already low at issue    (column at_risk)
    primary     = dam_like + octmar + at_risk, the pre-registered headline set
"""
import numpy as np
import pandas as pd

from damdays import config
from damdays.data.splits import hydro_year, time_block

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
TASKS = {
    # P1: the farmer runway. One forecast at every valid satellite look.
    "P1_R30": "P(the dam falls below a third of full within 90 days)",
    "P1_D0": "P(the dam is fully dry within 90 days)",
    "P1_D0g": "P(a gradual dry-out, i.e. a D0 that is not abrupt, within 90 days)",
    # Label-determinable sensitivity rows (PREREG "reported regardless"): every
    # at-risk issue whose 90 days have passed, without the 3-look rule; no event
    # seen counts as 0. A different label, so a separate ledger entry.
    "P1_R30_sens": "P1_R30 on all at-risk issues, no 3-look label rule",
    "P1_D0_sens": "P1_D0 on all at-risk issues, no 3-look label rule",
    "P1_D0g_sens": "P1_D0g on all at-risk issues, no 3-look label rule",
    # P2: the season rating for lenders. Issued 1 July, judged on Oct-Mar.
    "P2_dam": "P(the dam runs fully dry in the coming Oct-Mar), issued 1 Jul",
    "P2_dam_g": "P(a gradual dry-out in the coming Oct-Mar), issued 1 Jul",
    "P2_cell": "P(every dam-like dam in the 2 km cell runs dry in the coming Oct-Mar)",
    # Runway curves: one forecast per horizon (30, 60, 90, 180 days).
    "R30_curve": "Runway curve: P(below a third within 30 / 60 / 90 / 180 days)",
    "D0_curve": "Runway curve: P(fully dry within 30 / 60 / 90 / 180 days)",
}


def task_kind(task):
    """"p1", "p2" or "curve": which family of forecast a task belongs to."""
    check_task(task)
    if task.endswith("_curve"):
        return "curve"
    return "p2" if task.startswith("P2_") else "p1"


def check_task(task):
    """Raise if `task` is not one of the known task names (case matters)."""
    if task not in TASKS:
        known = ", ".join(TASKS)
        raise ValueError(f"Unknown task {task!r}. Known tasks: {known}")


# ---------------------------------------------------------------------------
# Time blocks and arenas
# ---------------------------------------------------------------------------
SCORABLE_BLOCKS = ("VAL", "TEST")


def block_of(issue_dates):
    """The one time block (VAL or TEST) that all these issue dates fall in.

    Raises if the dates are spread over several blocks, or fall in TRAIN, the
    GAP half-year or after TEST, none of which may be scored.
    """
    blocks = pd.unique(time_block(issue_dates))
    if len(blocks) != 1 or blocks[0] not in SCORABLE_BLOCKS:
        raise ValueError(
            f"Issue dates must all lie in one scorable block (VAL 2009-01-01..2015-12-31 or "
            f"TEST 2016-07-01..2026-06-30); these fall in {sorted(blocks)}. Score each block separately.")
    return str(blocks[0])


def arena_of(regions):
    """"dev" if every row is in a development region, "sealed" if every row is in the sealed region."""
    found = set(pd.unique(pd.Series(regions).astype(str)))
    if found <= set(config.DEV_REGIONS):
        return "dev"
    if found <= set(config.SEALED_REGION):
        return "sealed"
    raise ValueError(
        f"Regions {sorted(found)} are not all development regions {sorted(config.DEV_REGIONS)} "
        f"or all the sealed region {sorted(config.SEALED_REGION)}. Score them separately.")


def region_year(regions, issue_dates):
    """Label for each row's region and July-June year, e.g. "nsw_cw:2019".

    These labels are the clusters of the region-year bootstrap: all dams in one
    region share that year's weather.
    """
    years = hydro_year(issue_dates)
    return pd.Series(regions).astype(str).to_numpy() + ":" + years.astype(str)


# ---------------------------------------------------------------------------
# Subsets
# ---------------------------------------------------------------------------
SUBSET_PARTS = {
    "dam_like": "dams that behave like farm dams (pre-2016 shape and wetness rules)",
    "persistent": "dams wet in at least 80% of pre-2016 looks (rarely dry out)",
    "octmar": "forecasts issued in October to March",
    "at_risk": "the dam was not already in the low state when the forecast was issued",
}
SUBSET_ALIASES = {"primary": ("dam_like", "octmar", "at_risk")}
FLAG_COLUMNS = ("dam_like", "persistent", "at_risk")   # parts that are read from a column
NOT_FOR_P2 = ("octmar", "at_risk")                     # P2 is always issued on 1 July


def parse_subset(subset, task):
    """Turn a subset name such as "primary" or "dam_like+octmar" into its parts, in a fixed order.

    "all" means no filter and gives an empty tuple. The fixed order means that
    "octmar+dam_like" and "dam_like+octmar" are the same subset.
    """
    names = [part.strip() for part in str(subset).split("+") if part.strip()]
    if names == ["all"]:
        return ()
    parts = set()
    for name in names:
        if name in SUBSET_ALIASES:
            parts.update(SUBSET_ALIASES[name])
        elif name in SUBSET_PARTS:
            parts.add(name)
        else:
            known = ", ".join(["all", *SUBSET_ALIASES, *SUBSET_PARTS])
            raise ValueError(f"Unknown subset part {name!r} in {subset!r}. Known: {known}")
    if task_kind(task) == "p2" and parts & set(NOT_FOR_P2):
        raise ValueError(f"Subsets {NOT_FOR_P2} do not apply to {task}: season ratings are issued on 1 July.")
    return tuple(part for part in SUBSET_PARTS if part in parts)


def subset_name(parts):
    """Canonical name of a parsed subset: "all", or the parts joined with "+"."""
    return "+".join(parts) if parts else "all"


def flag_columns_needed(parts):
    """The yes/no columns the table must have for these subset parts."""
    return [part for part in parts if part in FLAG_COLUMNS]


def as_flag(values, name):
    """A yes/no column as a numpy bool array; refuses blanks and anything other than True/False or 1/0.

    (Text such as "False" would otherwise count as True, because any non-empty text does.)
    """
    series = pd.Series(values)
    if series.isna().any():
        raise ValueError(f"Column {name!r} has blank values; every row needs True or False.")
    if pd.api.types.is_bool_dtype(series):
        return series.to_numpy(dtype=bool)
    if pd.api.types.is_numeric_dtype(series) and series.isin([0, 1]).all():
        return series.to_numpy() == 1
    raise ValueError(f"Column {name!r} must hold True/False (or 1/0), not {series.dtype}.")


def is_octmar(issue_dates):
    """True for forecasts issued in October to March (the farmer's dry-season months)."""
    months = pd.DatetimeIndex(pd.to_datetime(issue_dates)).month
    return np.isin(months, config.SEASON_MONTHS)


def subset_mask(table, parts):
    """True for the rows of `table` that belong to every part of the subset."""
    keep = np.ones(len(table), dtype=bool)
    for part in parts:
        if part == "octmar":
            keep &= is_octmar(table["issue_date"])
        else:
            keep &= as_flag(table[part], part)
    return keep
