"""Make MOCK data for the DamDays app, so the screens can be built and tested
before the real forecasts exist.

Everything this script writes is made up:
- about 200 dams are scattered at random around real towns in the NSW Central West;
- their water levels come from a toy month-by-month simulation (rain fills the
  dam, evaporation and stock use empty it, and known drought years are drier);
- the "forecasts" come from a simple made-up formula, not from the DamDays model.

The numbers only need to look plausible and follow app/DATA_CONTRACT.md.
The app shows a large MOCK banner whenever meta.is_mock is true.

Usage (from the repo root):
    python app/tools/make_mock_data.py
"""
import json
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_DIR = TOOLS_DIR.parents[1]
sys.path.insert(0, str(REPO_DIR))  # so "from damdays import config" works when run as a script

from damdays import config  # noqa: E402  (import after the path tweak above)
from build_bundle import write_bundle, write_dataset_list  # noqa: E402

OUT_DIR = REPO_DIR / "app" / "data" / "mock"

# ---------------------------------------------------------------------------
# Settings for the make-believe world
# ---------------------------------------------------------------------------
# Real towns in the NSW Central West (name, lat, lon). Mock dams sit 3-18 km away.
TOWNS = [
    ("Gilgandra", -31.71, 148.66),
    ("Coonabarabran", -31.27, 149.28),
    ("Dubbo", -32.25, 148.60),
    ("Wellington", -32.56, 148.94),
    ("Mudgee", -32.59, 149.59),
    ("Parkes", -33.14, 148.18),
    ("Molong", -33.09, 148.87),
]
DAMS_PER_TOWN = 29                     # 7 towns x 29 = 203 dams

FIRST_YEAR, LAST_YEAR, LAST_MONTH = 1988, 2026, 9   # history runs Jan 1988 to Sep 2026
LIVE_ISSUE = date(2026, 9, 15)
REWIND_ISSUES = [date(2017, 7, 1), date(2017, 10, 1), date(2018, 7, 1), date(2018, 10, 1),
                 date(2020, 7, 1), date(2023, 7, 1), date(2023, 10, 1)]
SEASON_YEARS = list(range(2016, 2027))  # 1 Jul ratings; 2026 is the live season

# Typical rain per calendar month (mm, Jan..Dec) and how much of a full dam
# is lost per month to evaporation and stock (% of full, Jan..Dec).
RAIN_MM = [60, 55, 50, 40, 40, 45, 45, 40, 40, 50, 55, 60]
LOSS_PCT = [14, 12, 9, 5, 3, 2, 2, 3, 5, 8, 11, 13]
RUNOFF_START_MM = 30     # a month needs more rain than this before water runs into the dam
RUNOFF_PCT_PER_MM = 0.35  # each mm above that adds this much (% of full)

# Rough wet (>1) and dry (<1) years, loosely shaped on real Central West history.
YEAR_WETNESS = {
    1990: 1.4, 1991: 0.75, 1994: 0.5, 1997: 0.7, 1998: 1.3, 2000: 1.4, 2002: 0.45,
    2006: 0.5, 2009: 0.7, 2010: 1.6, 2011: 1.4, 2016: 1.6, 2017: 0.6, 2018: 0.4,
    2019: 0.35, 2020: 1.3, 2021: 1.5, 2022: 1.7, 2023: 0.7, 2024: 0.8,
    2026: 0.5,   # set dry so the live mock map shows a range of risks
}

THRESHOLD = config.R30_LEVEL * 100   # "below a third" = below 30% of full
ARM_LEVEL = config.ARM_LEVEL * 100   # a dam must have been 60% full ...
ARM_MONTHS = 6                       # ... within the last ~180 days
HORIZON = config.HORIZON_DAYS
HORIZONS = [30, 60, 90, 180]
CURVE_SHAPE = 1.6                    # >1 means the risk grows as the weeks pass


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def sigmoid(z):
    """Turn any number into a chance between 0 and 1."""
    return 1.0 / (1.0 + math.exp(-z))


def month_index(year, month):
    """Position of a calendar month in the history (Jan 1988 = 0)."""
    return (year - FIRST_YEAR) * 12 + (month - 1)


def index_to_year_month(index):
    """The calendar (year, month) of a history position."""
    return FIRST_YEAR + index // 12, index % 12 + 1


N_MONTHS = month_index(LAST_YEAR, LAST_MONTH) + 1


def mid_month(index):
    """A representative date (the 15th) for a history position."""
    year, month = index_to_year_month(index)
    return date(year, month, 15)


def km_to_degrees(dx_km, dy_km, lat):
    """Convert a small east/north offset in km to degrees of lon/lat."""
    dlat = dy_km / 110.57
    dlon = dx_km / (111.32 * math.cos(math.radians(lat)))
    return dlon, dlat


# ---------------------------------------------------------------------------
# Step 1: place the dams and simulate rain and water levels
# ---------------------------------------------------------------------------
def place_dams(rng):
    """Scatter mock dams around each town and give each a hidden 'dryness'."""
    dams = []
    for town, town_lat, town_lon in TOWNS:
        for _ in range(DAMS_PER_TOWN):
            distance_km = rng.uniform(3, 18)
            angle = rng.uniform(0, 2 * math.pi)
            dlon, dlat = km_to_degrees(distance_km * math.cos(angle),
                                       distance_km * math.sin(angle), town_lat)
            number = len(dams) + 1
            dams.append({
                "dam_id": f"mock-{number:03d}",
                "name": f"Dam {number}",
                "town": town,
                "lat": round(town_lat + dlat, 5),
                "lon": round(town_lon + dlon, 5),
                # Log-uniform area between 0.54 ha and 10 ha (DEA farm-dam sizes).
                "area_ha": round(math.exp(rng.uniform(math.log(0.54), math.log(10))), 2),
                # Hidden trait: >0 means the dam runs drier than its neighbours.
                "dryness": rng.gauss(0, 1),
            })
    return dams


def simulate_town_rain(rng):
    """Monthly rain (mm) for each town, Jan 1988 to Sep 2026."""
    rain = {}
    for town, _, _ in TOWNS:
        series = []
        for index in range(N_MONTHS):
            year, month = index_to_year_month(index)
            wetness = YEAR_WETNESS.get(year, 1.0)
            series.append(RAIN_MM[month - 1] * wetness * rng.lognormvariate(0, 0.55))
        rain[town] = series
    return rain


def simulate_levels(dam, town_rain, rng):
    """Month-by-month water level (% of full) of one dam; None = no clear satellite look."""
    level = 80.0
    levels = []
    for index in range(N_MONTHS):
        month = index % 12 + 1
        local_rain = town_rain[index] * rng.lognormvariate(0, 0.15)
        inflow = RUNOFF_PCT_PER_MM * max(0.0, local_rain - RUNOFF_START_MM)
        inflow *= max(0.3, 1 - 0.2 * dam["dryness"])         # drier dams catch less
        loss = LOSS_PCT[month - 1] * max(0.5, 1 + 0.25 * dam["dryness"])
        level = min(100.0, max(0.0, level + inflow - loss))
        cloudy = rng.random() < 0.10
        levels.append(None if cloudy else round(level))
    return levels


# ---------------------------------------------------------------------------
# Step 2: find past events, and judge what happened after a forecast
# ---------------------------------------------------------------------------
def was_armed(levels, index):
    """True if the dam was at least 60% full in the last six months (event rule)."""
    recent = [v for v in levels[max(0, index - ARM_MONTHS):index + 1] if v is not None]
    return any(v >= ARM_LEVEL for v in recent)


def find_events(levels):
    """Months when the dam fell below a third, or ran dry, after being refilled."""
    events = []
    ready = {"below_third": False, "dry": False}
    limits = {"below_third": THRESHOLD, "dry": 0.5}
    for index, value in enumerate(levels):
        if value is None:
            continue
        for kind in ready:
            if value >= ARM_LEVEL:
                ready[kind] = True          # refilled: a new event can count again
            elif ready[kind] and value < limits[kind]:
                events.append({"date": mid_month(index).isoformat(), "kind": kind})
                ready[kind] = False         # one event per drawdown
    events.sort(key=lambda e: e["date"])
    return events


def outcome_after(levels, index, months):
    """Did the dam fall below a third in the next few months? True, False or None (unknown)."""
    future = levels[index + 1:index + 1 + months]
    if len(future) < months:
        return None, None                   # the window has not finished yet
    for offset, value in enumerate(future):
        if value is not None and value < THRESHOLD:
            return True, mid_month(index + 1 + offset).isoformat()
    looks = sum(1 for v in future if v is not None)
    return (False, None) if looks >= 2 else (None, None)


# ---------------------------------------------------------------------------
# Step 3: make-believe forecasts (a simple formula, NOT the DamDays model)
# ---------------------------------------------------------------------------
def rain_anomaly(series, end_index, months):
    """Rain over the last few months compared with normal (0 = normal, -0.5 = half)."""
    start = max(0, end_index - months + 1)
    actual = sum(series[start:end_index + 1])
    normal = sum(RAIN_MM[i % 12] for i in range(start, end_index + 1))
    return actual / normal - 1


def season_effect(issue_month):
    """Forecasts made just before summer carry more risk (evaporation is high)."""
    if issue_month in (9, 10, 11, 12):
        return 1.2
    if issue_month in (1, 2):
        return 0.6
    if issue_month in (3, 4, 5):
        return -0.8
    return -1.0


def latest_look(levels, index):
    """The most recent satellite look at or before this month, at most ~60 days old."""
    for back in range(0, 3):
        if index - back >= 0 and levels[index - back] is not None:
            return levels[index - back], index - back
    return None, None


def runway_curve(chance_90):
    """Chance of falling below a third by 30/60/90/180 days, from the 90-day chance."""
    if chance_90 <= 0:
        return [0.0 for _ in HORIZONS]
    survive_90 = 1 - chance_90
    return [round(1 - survive_90 ** ((h / HORIZON) ** CURVE_SHAPE), 3) for h in HORIZONS]


def damdays_floor(chance_90):
    """Days until the curve reaches 10%: 'at least N days, 9 times in 10'."""
    if chance_90 <= 0:
        return 365
    ratio = math.log(0.9) / math.log(1 - chance_90)
    days = HORIZON * ratio ** (1 / CURVE_SHAPE)
    return min(365, int(days // 5 * 5))      # round down to 5 days, cap at a year


def forecast_row(dam, levels, rain, issue, state_index, rng, issued_on):
    """One dam's forecast on one issue date, following the contract's row fields."""
    row = {"dam_id": dam["dam_id"], "issued_on": issued_on.isoformat(),
           "window_end": (issued_on + timedelta(days=HORIZON)).isoformat(),
           "level_pct": None, "status": "forecast", "chance": None,
           "chance_low": None, "chance_high": None, "damdays_days": None,
           "notes": [], "outcome": None, "outcome_date": None}
    level, look_index = latest_look(levels, state_index)
    if level is None:
        row["status"] = "no_recent_look"
        return row
    row["level_pct"] = level
    if level < THRESHOLD:
        row["status"] = "already_low"
        return row
    if not was_armed(levels, look_index):
        row["status"] = "not_refilled"
        return row

    # A made-up formula: low or falling water, a dry dam, summer ahead and a
    # dry last six months all raise the chance. The weights were tuned once so
    # the mock chances roughly match the mock outcomes.
    drop = (levels[look_index - 3] or level) - level if look_index >= 3 else 0
    z = (-3.0 + 0.15 * (50 - level) + 1.0 * dam["dryness"]
         + season_effect(issue.month) + 0.04 * max(0, drop)
         - 2.1 * rain_anomaly(rain, state_index, 6) + rng.gauss(0, 0.4))
    row["chance"] = round(sigmoid(z), 3)
    row["chance_low"] = round(sigmoid(z - 0.7), 3)
    row["chance_high"] = round(sigmoid(z + 0.7), 3)
    row["damdays_days"] = damdays_floor(row["chance"])
    if dam["dryness"] > 1.0:
        row["notes"].append("Runs drier than similar dams nearby.")
    outcome, when = outcome_after(levels, state_index, 3)
    row["outcome"], row["outcome_date"] = outcome, when
    return row


def make_issue(dams, levels, rain, issue, kind, rng):
    """All dams' forecasts and runway curves for one issue date."""
    state_index = month_index(issue.year, issue.month)
    if issue.day == 1:
        state_index -= 1                    # a 1st-of-month issue uses last month's look
    rows, curves = [], {}
    for dam in dams:
        issued_on = issue - timedelta(days=rng.randint(1, 20))
        row = forecast_row(dam, levels[dam["dam_id"]], rain[dam["town"]],
                           issue, state_index, rng, issued_on)
        if kind == "live":
            row["outcome"], row["outcome_date"] = None, None   # the future is unknown
        rows.append(row)
        if row["status"] == "forecast":
            curves[dam["dam_id"]] = {
                "chance": runway_curve(row["chance"]),
                "low": runway_curve(row["chance_low"]),
                "high": runway_curve(row["chance_high"]),
            }
    label = "Latest forecast" if kind == "live" else issue.strftime("%d %b %Y").lstrip("0")
    note = ("MOCK: made-up forecasts for testing the screens."
            if kind == "live" else
            "MOCK: made-up forecasts and outcomes for testing the screens.")
    issue_entry = {"issue_date": issue.isoformat(), "kind": kind, "label": label,
                   "note": note, "rows": rows}
    return issue_entry, {"issue_date": issue.isoformat(), "by_dam": curves}


# ---------------------------------------------------------------------------
# Step 4: 2 km hexagon cells and the season rating
# ---------------------------------------------------------------------------
HEX_SIZE = config.HEX_SIZE_KM / math.sqrt(3)   # centre-to-corner, so flat-to-flat = 2 km
ORIGIN_LAT, ORIGIN_LON = -32.0, 148.5          # local flat-map origin (fine for mock)


def to_km(lat, lon):
    """Flat-map position in km from the origin (good enough over a few hundred km)."""
    x = (lon - ORIGIN_LON) * 111.32 * math.cos(math.radians(ORIGIN_LAT))
    y = (lat - ORIGIN_LAT) * 110.57
    return x, y


def to_lat_lon(x, y):
    """Inverse of to_km."""
    lat = ORIGIN_LAT + y / 110.57
    lon = ORIGIN_LON + x / (111.32 * math.cos(math.radians(ORIGIN_LAT)))
    return round(lat, 5), round(lon, 5)


def hex_of(lat, lon):
    """Axial (q, r) of the pointy-top hexagon containing a point."""
    x, y = to_km(lat, lon)
    q = (math.sqrt(3) / 3 * x - y / 3) / HEX_SIZE
    r = (2 / 3 * y) / HEX_SIZE
    # Round in cube coordinates so the point lands in the right hexagon.
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = round(cx), round(cy), round(cz)
    dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy <= dz:
        rz = -rx - ry
    return rx, rz


def hex_shape(q, r):
    """Centre and six corners (lat, lon) of a hexagon."""
    cx = HEX_SIZE * math.sqrt(3) * (q + r / 2)
    cy = HEX_SIZE * 1.5 * r
    corners = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        corners.append(list(to_lat_lon(cx + HEX_SIZE * math.cos(angle),
                                       cy + HEX_SIZE * math.sin(angle))))
    return to_lat_lon(cx, cy), corners


def make_cells(dams):
    """Group dams into 2 km hexagons. Returns cell records and a dam -> cell map."""
    members = {}
    for dam in dams:
        q, r = hex_of(dam["lat"], dam["lon"])
        members.setdefault((q, r), []).append(dam)
    cells, cell_of_dam = [], {}
    for (q, r), cell_dams in sorted(members.items()):
        cell_id = f"h{q}_{r}"
        (lat, lon), corners = hex_shape(q, r)
        cells.append({"cell_id": cell_id, "lat": lat, "lon": lon,
                      "corners": corners, "n_dams": len(cell_dams),
                      "town": cell_dams[0]["town"]})
        for dam in cell_dams:
            cell_of_dam[dam["dam_id"]] = cell_id
    return cells, cell_of_dam


def dam_ran_dry(levels, year):
    """Did the dam run completely dry between Oct and Mar of this season?"""
    june = month_index(year, 6)
    if not was_armed(levels, june):
        return False                        # not refilled, so no event can count
    season = levels[month_index(year, 10):month_index(year + 1, 3) + 1]
    if len(season) < 6:
        return None                         # the season has not finished yet
    looks = [v for v in season if v is not None]
    if any(v <= 0.5 for v in looks):
        return True
    return False if len(looks) >= 3 else None


def past_dry_rate(levels, year):
    """Share of past seasons (before this one) in which the dam ran dry, shrunk to 10%."""
    dry_seasons = sum(1 for y in range(FIRST_YEAR, year) if dam_ran_dry(levels, y))
    seasons = year - FIRST_YEAR
    return (dry_seasons + 0.1 * 5) / (seasons + 5)


def dam_season_chance(dam, levels, rain, year, rng):
    """Made-up rating: chance this dam runs dry in Oct-Mar, as seen on 1 Jul."""
    june = month_index(year, 6)
    if not was_armed(levels, june):
        return 0.002                        # not refilled lately, so it cannot "run dry" again
    level, _ = latest_look(levels, june)
    level = 50 if level is None else level
    rate = past_dry_rate(levels, year)
    # Made-up weights, tuned once so mock chances roughly match mock outcomes.
    z = (5.85 + 0.076 * (50 - level) + 2.1 * math.log(rate / (1 - rate))
         - 2.85 * rain_anomaly(rain, june, 12) + rng.gauss(0, 0.5))
    return sigmoid(z)


def rain_only_chance(cell, rain, year, towns):
    """Made-up rainfall-only score: depends on the area's last 12 months of rain only."""
    june = month_index(year, 6)
    anomaly = rain_anomaly(rain[cell["town"]], june, 12)
    town_lat = towns[cell["town"]][0]
    gradient = 0.4 * (town_lat - cell["lat"])   # a gentle north-south slope, like real rain
    return sigmoid(-2.4 - 3.0 * anomaly + gradient)


def make_season(cells, dams_in_cell, levels, rain, year, rng):
    """Every cell's rainfall-only score, DamDays rating and outcome for one season."""
    towns = {name: (lat, lon) for name, lat, lon in TOWNS}
    rows = []
    for cell in cells:
        rating = 1.0
        outcomes = []
        for dam in dams_in_cell[cell["cell_id"]]:
            dam_levels = levels[dam["dam_id"]]
            rating *= dam_season_chance(dam, dam_levels, rain[dam["town"]], year, rng)
            outcomes.append(dam_ran_dry(dam_levels, year))
        if year == LAST_YEAR or any(o is None for o in outcomes):
            ran_dry = None                   # live season, or not enough satellite looks
        else:
            ran_dry = all(outcomes)          # a cell fails only if all its dams run dry
        rows.append({"cell_id": cell["cell_id"],
                     "rain_only_chance": round(rain_only_chance(cell, rain, year, towns), 3),
                     "rating_chance": round(rating, 3),
                     "ran_dry": ran_dry})
    kind = "live" if year == LAST_YEAR else "past"
    return {"season": f"{year}-{str(year + 1)[2:]}", "issue_date": f"{year}-07-01",
            "kind": kind, "rows": rows}


# ---------------------------------------------------------------------------
# Step 5: scoreboard numbers, computed from the mock data (never typed in)
# ---------------------------------------------------------------------------
def auc(scores, labels):
    """Chance a random 'ran dry' cell scores higher than a random 'did not' cell."""
    pairs = sorted(zip(scores, labels))
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    # Rank-sum method; tied scores share the average rank.
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        average_rank = (i + 1 + j) / 2
        rank_sum += average_rank * sum(1 for k in range(i, j) if pairs[k][1])
        i = j
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def auc_with_ci(scores, labels, rng, reps=400):
    """AUC plus a 95% range from resampling cells (a simple bootstrap)."""
    value = auc(scores, labels)
    if value is None:
        return None
    samples = []
    n = len(scores)
    for _ in range(reps):
        picks = [rng.randrange(n) for _ in range(n)]
        sample = auc([scores[p] for p in picks], [labels[p] for p in picks])
        if sample is not None:
            samples.append(sample)
    samples.sort()
    low = samples[int(0.025 * len(samples))]
    high = samples[int(0.975 * len(samples)) - 1]
    return {"value": round(value, 3), "ci_low": round(low, 3), "ci_high": round(high, 3)}


def season_scores(rows, rng):
    """AUC of both scores on the cells whose outcome is known."""
    known = [r for r in rows if r["ran_dry"] is not None]
    labels = [1 if r["ran_dry"] else 0 for r in known]
    return {
        "n_cells": len(known),
        "n_ran_dry": sum(labels),
        "rain_only_auc": auc_with_ci([r["rain_only_chance"] for r in known], labels, rng),
        "rating_auc": auc_with_ci([r["rating_chance"] for r in known], labels, rng),
    }


def runway_skill(issues, rng, reps=400):
    """How much better the mock forecasts are than always guessing the average rate."""
    pairs = [(r["chance"], 1 if r["outcome"] else 0)
             for issue in issues if issue["kind"] == "past"
             for r in issue["rows"] if r["status"] == "forecast" and r["outcome"] is not None]

    def skill(sample):
        rate = sum(y for _, y in sample) / len(sample)
        brier = sum((p - y) ** 2 for p, y in sample) / len(sample)
        reference = sum((rate - y) ** 2 for _, y in sample) / len(sample)
        return 1 - brier / reference

    samples = sorted(skill([rng.choice(pairs) for _ in pairs]) for _ in range(reps))
    return {"value": round(skill(pairs), 3),
            "ci_low": round(samples[int(0.025 * reps)], 3),
            "ci_high": round(samples[int(0.975 * reps) - 1], 3)}, len(pairs)


def make_scoreboard(seasons, issues, rng):
    """Scoreboard file: per-season and all-season AUCs, plus the runway skill."""
    past = [s for s in seasons if s["kind"] == "past"]
    by_season = [dict(season=s["season"], **season_scores(s["rows"], rng)) for s in past]
    all_rows = [r for s in past for r in s["rows"]]
    pooled = season_scores(all_rows, rng)
    pooled["label"] = f"All past seasons {past[0]['season'][:4]}-{past[-1]['season'][:4]}"
    skill, n_forecasts = runway_skill(issues, rng)
    return {
        "source": "mock",
        "source_label": "MOCK numbers computed from made-up data",
        "rating": {"all_seasons": pooled, "by_season": by_season},
        "runway": {"label": "MOCK: all rewind dates pooled",
                   "skill_vs_usual_rate": skill, "n_forecasts": n_forecasts},
    }


# ---------------------------------------------------------------------------
# Step 6: write the files
# ---------------------------------------------------------------------------
def month_label(index):
    year, month = index_to_year_month(index)
    return f"{year}-{month:02d}"


# Small files are indented so people can read them; big ones are compact to keep the repo small.
READABLE_FILES = ("meta", "scoreboard")


def write_json(name, content):
    """Write one of the contract's JSON files into the mock folder."""
    path = OUT_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        if name in READABLE_FILES:
            json.dump(content, f, indent=2, ensure_ascii=False)
        else:
            json.dump(content, f, separators=(",", ":"), ensure_ascii=False)
    print(f"Wrote {path}")


def main():
    rng = random.Random(config.RANDOM_SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dams = place_dams(rng)
    rain = simulate_town_rain(rng)
    levels = {d["dam_id"]: simulate_levels(d, rain[d["town"]], rng) for d in dams}

    issues, curve_issues = [], []
    for issue, kind in [(LIVE_ISSUE, "live")] + [(d, "past") for d in REWIND_ISSUES]:
        issue_entry, curve_entry = make_issue(dams, levels, rain, issue, kind, rng)
        issues.append(issue_entry)
        curve_issues.append(curve_entry)

    cells, cell_of_dam = make_cells(dams)
    dams_in_cell = {c["cell_id"]: [] for c in cells}
    for dam in dams:
        dams_in_cell[cell_of_dam[dam["dam_id"]]].append(dam)
    seasons = [make_season(cells, dams_in_cell, levels, rain, y, rng) for y in SEASON_YEARS]

    lat_min, lat_max, lon_min, lon_max = config.DEV_REGIONS["nsw_cw"]
    write_json("meta", {
        "schema_version": "1.0",
        "is_mock": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": {"key": "nsw_cw", "name": "NSW Central West",
                   "bbox": [lat_min, lat_max, lon_min, lon_max]},
        "data_through": (LIVE_ISSUE - timedelta(days=1)).isoformat(),
        "horizon_days": HORIZON,
        "threshold_pct": round(THRESHOLD),
        "arm_level_pct": round(ARM_LEVEL),
        "min_dam_area_ha": round(config.AREA_MIN_M2 / 10_000, 2),
        "model": {"name": "None (mock data)", "version": None, "config_hash": None},
        "note": "Made-up data for building and testing the app. These are not forecasts.",
    })
    public_dams = [{k: d[k] for k in ("dam_id", "name", "lat", "lon", "area_ha")} | {"dea_uid": None}
                   for d in dams]
    write_json("forecasts", {"horizon_days": HORIZON, "dams": public_dams, "issues": issues})
    write_json("curves", {"horizons_days": HORIZONS, "issues": curve_issues})
    write_json("history", {
        "first_month": month_label(0),
        "last_month": month_label(N_MONTHS - 1),
        "by_dam": {d["dam_id"]: {"level_pct": levels[d["dam_id"]],
                                 "events": find_events(levels[d["dam_id"]])} for d in dams},
    })
    public_cells = [{k: c[k] for k in ("cell_id", "lat", "lon", "corners", "n_dams")} for c in cells]
    write_json("cells", {"cell_size_km": config.HEX_SIZE_KM, "season_months": "Oct-Mar",
                         "cells": public_cells, "seasons": seasons})
    write_json("scoreboard", make_scoreboard(seasons, issues, rng))

    write_bundle(OUT_DIR)
    write_dataset_list(OUT_DIR.parent)
    print_summary(issues, seasons)


def print_summary(issues, seasons):
    """A quick sanity print: are the mock numbers in a plausible range?"""
    for issue in issues:
        rows = [r for r in issue["rows"] if r["status"] == "forecast"]
        known = [r for r in rows if r["outcome"] is not None]
        mean_chance = sum(r["chance"] for r in rows) / max(1, len(rows))
        happened = sum(1 for r in known if r["outcome"]) / max(1, len(known))
        print(f"{issue['issue_date']} {issue['kind']:4s}: {len(rows):3d} forecast, "
              f"mean chance {mean_chance:.2f}, happened {happened:.2f} of {len(known)} known")
    for season in seasons:
        known = [r for r in season["rows"] if r["ran_dry"] is not None]
        dry = sum(1 for r in known if r["ran_dry"])
        print(f"season {season['season']}: {dry:3d} of {len(known)} cells ran dry")


if __name__ == "__main__":
    main()
