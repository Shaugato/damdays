"""The worked examples of MESSAGE_SPEC.md: made-up farms whose texts show every rule once.

The numbers are MADE UP, only to show the rules. Every example is "sent" on Monday 5 Oct 2026,
and every dam was last seen by the satellite on Monday 28 Sep 2026 (7 days earlier) unless the
example says otherwise. So a floor of 30 days from the look is "at least 23 days" in the text.

Each dam is listed closest first (so the list order is Dam 1, Dam 2, ...), with:
    km      distance from the homestead (the dam is placed due east of it)
    status  "forecast", "already_low", "not_refilled" or "no_recent_look" (app/DATA_CONTRACT.md)
    level   how full at the look, % of the dam's own full level
    floor   the DamDays floor in days from the look (forecast dams only)
    chance  chance of falling below a third within 90 days of the look (forecast dams only)
    look    the satellite look's date, if not 28 Sep

build_examples() turns them into a forecasts.json document and Farm objects, the same inputs
the real texts use. tests/test_weekly_text.py and the JavaScript fixtures
(notify/fixtures/spec_examples.json) use exactly these.
"""
import math
from datetime import date, timedelta

from notify.farms import EARTH_RADIUS_KM, Farm

TODAY = "2026-10-05"
LOOK = "2026-09-28"
HOMESTEAD_LAT = -32.0          # each example's homestead is 1 degree of longitude east of the last
FIRST_LON = 140.0


def F(km, level, floor, chance, look=LOOK):
    """A forecast dam."""
    return dict(km=km, status="forecast", level=level, floor=floor, chance=chance, look=look)


def S(km, status, level, look=LOOK):
    """A dam with no forecast: already low, not refilled, or no recent look."""
    return dict(km=km, status=status, level=level, floor=None, chance=None, look=look)


EXAMPLES = [
    dict(key="all_ok", title="Every dam is fine",
         dams=[F(0.6, 100, 200, 0.02), F(1.4, 85, 140, 0.06), F(2.2, 70, 120, 0.08)]),
    dict(key="one_at_risk", title="One dam at risk, the others fine",
         dams=[F(0.4, 45, 30, 0.62), F(1.1, 100, 150, 0.05), F(2.7, 80, 110, 0.09)]),
    dict(key="already_low", title="A dam already below a third",
         dams=[S(0.8, "already_low", 25), F(1.9, 65, 60, 0.35)]),
    dict(key="two_at_risk", title="Two dams at risk, and the rest summed up (the satellite date is left out to fit)",
         dams=[F(0.5, 90, 75, 0.30), F(1.2, 55, 25, 0.71), F(1.8, 95, 95, 0.20), F(2.6, 60, 40, 0.52)]),
    dict(key="floor_ran_out", title="A floor that ran out since the satellite look, and a dry dam",
         dams=[F(0.3, 35, 5, 0.81), F(1.0, 60, 50, 0.40), S(2.4, "already_low", 0)]),
    dict(key="capped", title="One dam, its floor capped at 6 months",
         dams=[F(0.9, 100, 260, 0.01)]),
    dict(key="all_low", title="Every dam already below a third",
         dams=[S(0.7, "already_low", 0), S(1.6, "already_low", 15)]),
    dict(key="not_refilled", title="A dam with no forecast until it refills",
         dams=[F(1.2, 75, 45, 0.38), S(2.0, "not_refilled", 40)]),
    dict(key="many_dams", title="Twelve dams: lines left out to fit one SMS",
         dams=[F(0.3, 70, 64, 0.33), S(0.6, "already_low", 22), F(0.9, 50, 21, 0.68),
               S(1.1, "already_low", 18), F(1.3, 85, 130, 0.07), S(1.6, "already_low", 9),
               S(1.8, "not_refilled", 41), F(2.0, 58, 36, 0.55), S(2.2, "already_low", 0),
               S(2.5, "already_low", 26), S(2.7, "no_recent_look", 90, look="2026-07-10"),
               F(2.9, 100, 190, 0.02)]),
    dict(key="no_dams", title="No dam the satellites can see within 3 km",
         dams=[]),
]


def east_of(lat, lon, km):
    """The point `km` due east of (lat, lon), rounded to 5 decimals like forecasts.json."""
    return round(lat, 5), round(lon + math.degrees(km / (EARTH_RADIUS_KM * math.cos(math.radians(lat)))), 5)


def build_examples():
    """(forecasts.json document, list of (example, Farm)) for every worked example."""
    dams, rows, farms = [], [], []
    for i, example in enumerate(EXAMPLES, start=1):
        farm = Farm(farm_id=f"example-{i:02d}", lat=HOMESTEAD_LAT, lon=FIRST_LON + i,
                    name=f"Example farm {i}")
        farms.append((example, farm))
        for j, dam in enumerate(example["dams"]):
            dam_id = f"example-{i:02d}-{chr(ord('a') + j)}"
            lat, lon = east_of(farm.lat, farm.lon, dam["km"])
            dams.append(dict(dam_id=dam_id, name=dam_id, lat=lat, lon=lon, area_ha=1.0, dea_uid=None))
            is_forecast = dam["status"] == "forecast"
            look = date.fromisoformat(dam["look"])
            rows.append(dict(dam_id=dam_id, status=dam["status"], issued_on=dam["look"],
                             window_end=str(look + timedelta(days=90)), level_pct=dam["level"],
                             chance=dam["chance"], chance_low=None, chance_high=None,
                             damdays_days=dam["floor"] if is_forecast else None,
                             notes=[], outcome=None, outcome_date=None))
    forecasts = dict(horizon_days=90, dams=dams,
                     issues=[dict(issue_date=LOOK, kind="live", label="Worked examples (made-up numbers)",
                                  note="Made-up numbers for notify/MESSAGE_SPEC.md.", rows=rows)])
    return forecasts, farms
