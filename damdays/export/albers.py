"""Australian Albers (EPSG:3577, metres) to latitude/longitude, without an extra library.

Why this exists: the 2 km hexagon cells (damdays/data/cells.py) are laid out in
GDA94 Australian Albers metres. The web map needs each hexagon's corners in
latitude/longitude. The formulas are the standard ones for the Albers
equal-area conic projection on an ellipsoid (J. P. Snyder, "Map Projections:
A Working Manual", USGS 1987, pages 101-102), with the EPSG:3577 settings:

    ellipsoid GRS80 (the GDA94 datum)    a = 6,378,137 m, flattening 1 / 298.257222101
    standard parallels 18 S and 36 S     origin latitude 0, central meridian 132 E
    no false easting or northing

GDA94 and WGS84 differ by under 2 m, far less than a 2 km cell, so the result
is used as WGS84 directly. tests/test_app_export.py checks that both directions
undo each other and that every dam's Albers centre lands within 100 m of its
DEA latitude/longitude.
"""
import numpy as np

A = 6_378_137.0                        # GRS80 semi-major axis, metres
FLATTENING = 1 / 298.257222101         # GRS80
E2 = 2 * FLATTENING - FLATTENING ** 2  # eccentricity squared
E = np.sqrt(E2)
LAT_1, LAT_2 = np.radians(-18.0), np.radians(-36.0)   # standard parallels
LAT_0, LON_0 = np.radians(0.0), np.radians(132.0)     # origin


def _m(lat):
    """Snyder's m: the parallel's radius as a share of a."""
    return np.cos(lat) / np.sqrt(1 - E2 * np.sin(lat) ** 2)


def _q(lat):
    """Snyder's q: proportional to the area between the equator and the parallel."""
    s = np.sin(lat)
    return (1 - E2) * (s / (1 - E2 * s ** 2) - np.log((1 - E * s) / (1 + E * s)) / (2 * E))


N = (_m(LAT_1) ** 2 - _m(LAT_2) ** 2) / (_q(LAT_2) - _q(LAT_1))   # cone constant (negative: southern parallels)
C = _m(LAT_1) ** 2 + N * _q(LAT_1)
RHO_0 = A * np.sqrt(C - N * _q(LAT_0)) / N


def to_albers(lat_deg, lon_deg):
    """Latitude/longitude in degrees -> Albers x, y in metres (forward projection; used to check the inverse)."""
    lat, lon = np.radians(np.asarray(lat_deg, dtype=float)), np.radians(np.asarray(lon_deg, dtype=float))
    rho = A * np.sqrt(C - N * _q(lat)) / N
    theta = N * (lon - LON_0)
    return rho * np.sin(theta), RHO_0 - rho * np.cos(theta)


def to_lat_lon(x, y, iterations=8):
    """Albers x, y in metres -> latitude, longitude in degrees (inverse projection).

    Latitude has no closed form on the ellipsoid; a few fixed-point steps
    (Snyder eq. 3-16) converge to far below a millimetre.
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    sign = np.sign(N)                                  # with N < 0, rho and the angle flip sign (Snyder p. 101)
    rho = sign * np.hypot(x, RHO_0 - y)
    theta = np.arctan2(sign * x, sign * (RHO_0 - y))
    q = (C - (rho * N / A) ** 2) / N
    lat = np.arcsin(np.clip(q / 2, -1, 1))             # the sphere's answer, as a starting point
    for _ in range(iterations):
        s = np.sin(lat)
        lat = lat + (1 - E2 * s ** 2) ** 2 / (2 * np.cos(lat)) * (
            q / (1 - E2) - s / (1 - E2 * s ** 2) + np.log((1 - E * s) / (1 + E * s)) / (2 * E))
    return np.degrees(lat), np.degrees(LON_0 + theta / N)
