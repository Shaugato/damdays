"""A farm and its dams.

A farm is a homestead point (latitude, longitude), a radius and an optional name. We have no
property boundaries, so "the farm's dams" are the farm dams the satellites can see within the
radius of the homestead (3 km by default; a farmer can make it bigger or smaller). On a small
block the circle can take in a neighbour's dams, and on a big station it can miss some; the
farmer fixes that by changing the radius or the point.

The dams come from the live forecasts the app shows (app/data/real/forecasts.json, format in
app/DATA_CONTRACT.md). Every dam in that file is a dam-like waterbody of about 0.5 ha or more
(the satellites cannot see smaller ones), with one row in the live issue: a forecast, or the
reason it has none (already below a third, not refilled lately, no clear satellite look).

Dams are numbered by distance from the homestead: "Dam 1" is the closest. That number is what
the farmer reads in a text; the stable id from forecasts.json (`dam_id`, plus DEA's own id
`dea_uid`) is kept alongside, so a dam can always be traced back to the data.
"""
import math
from dataclasses import asdict, dataclass

DEFAULT_RADIUS_KM = 3.0
EARTH_RADIUS_KM = 6371.0088        # mean Earth radius (IUGG)


@dataclass(frozen=True)
class Farm:
    """A homestead point, a radius (km) and an optional name, e.g. "Farm A (near Dubbo)"."""
    farm_id: str
    lat: float
    lon: float
    radius_km: float = DEFAULT_RADIUS_KM
    name: str | None = None


@dataclass(frozen=True)
class FarmDam:
    """One of a farm's dams: its number by distance, where it is, and its live forecast row.

    The last seven fields are copied unchanged from the dam's row in the live issue of
    forecasts.json (dates as "YYYY-MM-DD"; chance from 0 to 1; damdays_days counted from the
    satellite look `issued_on`, not from today).
    """
    number: int                 # 1 = closest to the homestead
    dam_id: str                 # stable id in forecasts.json, e.g. "nsw_cw-0412"
    dea_uid: str | None         # DEA Waterbodies id, to trace the dam to the source
    distance_km: float          # from the homestead, to the nearest 10 m
    lat: float
    lon: float
    area_ha: float
    status: str                 # "forecast", "already_low", "not_refilled" or "no_recent_look"
    issued_on: str | None       # the satellite look the row starts from
    window_end: str | None      # issued_on + 90 days
    level_pct: int | None       # how full at that look, % of the dam's own full level
    chance: float | None        # chance of falling below a third by window_end
    damdays_days: int | None    # the DamDays floor: at least this many days above a third, 9 times in 10

    @property
    def name(self):
        """What the farmer reads: "Dam 1", "Dam 2", ..."""
        return f"Dam {self.number}"

    def as_json(self):
        """The dam as a plain dict (for the outbox and farms.json), with its name."""
        return dict(asdict(self), name=self.name)


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two points given in degrees (haversine formula)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def to_10_metres(km):
    """A distance rounded to 2 decimals of a km (10 m), halves up: the same in Python and JavaScript."""
    return math.floor(km * 100 + 0.5) / 100


def live_issue(forecasts):
    """The one issue of forecasts.json with kind "live" (today's forecasts)."""
    live = [issue for issue in forecasts["issues"] if issue["kind"] == "live"]
    if len(live) != 1:
        raise ValueError(f"forecasts.json must have exactly one live issue, found {len(live)}")
    return live[0]


def dams_for_farm(farm, forecasts):
    """The farm's dams: every dam in `forecasts` within farm.radius_km of the homestead.

    forecasts  a forecasts.json document (app/DATA_CONTRACT.md); only its live issue is used
    Returns FarmDam objects numbered by distance (Dam 1 = closest; equal distances in dam_id order).
    """
    rows = {row["dam_id"]: row for row in live_issue(forecasts)["rows"]}
    found = []
    for dam in forecasts["dams"]:
        row = rows.get(dam["dam_id"])
        if row is None:          # the contract gives every dam a row; skip one that has none
            continue
        km = to_10_metres(distance_km(farm.lat, farm.lon, dam["lat"], dam["lon"]))
        if km <= farm.radius_km:
            found.append((km, dam["dam_id"], dam, row))
    found.sort(key=lambda item: (item[0], item[1]))
    return [FarmDam(number=number, dam_id=dam["dam_id"], dea_uid=dam.get("dea_uid"), distance_km=km,
                    lat=dam["lat"], lon=dam["lon"], area_ha=dam["area_ha"],
                    status=row["status"], issued_on=row["issued_on"], window_end=row["window_end"],
                    level_pct=row["level_pct"], chance=row["chance"], damdays_days=row["damdays_days"])
            for number, (km, _, dam, row) in enumerate(found, start=1)]
