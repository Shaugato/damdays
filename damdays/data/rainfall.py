"""Monthly rainfall from SILO, joined to each waterbody.

SILO (Queensland Government) publishes gridded rainfall on a 0.05-degree grid
(about 5 km). We downloaded one file per year, silo_monthly_rain_<year>.npz,
cropped to our study regions. Each file holds three arrays per region:

    <region>__rain   rain in mm, shape (months in that year, n_lat, n_lon)
    <region>__lat    grid latitudes
    <region>__lon    grid longitudes

The files also hold the sealed test region. We only ever read the keys of the
development regions; the sealed key is refused until the official opening.

What this module gives you:
  * each waterbody's nearest SILO grid cell (silo_cell, silo_lat, silo_lon,
    silo_dist_km). If the nearest cell has missing data, the nearest cell
    that has data is used instead.
  * one monthly rain series per grid cell that is used by any waterbody.
Rain features (sums, percentiles) are built later in damdays.features.
"""
import re

import numpy as np

from damdays import config
from damdays.data.guard import check_path, sealed_unlocked

EARTH_RADIUS_KM = 6371.0
FILE_PATTERN = re.compile(r"silo_monthly_rain_(\d{4})\.npz$")


# ---------------------------------------------------------------------------
# Reading the yearly files
# ---------------------------------------------------------------------------
def check_region_allowed(region):
    """Refuse the sealed region's SILO key unless the sealed data has been opened."""
    if region in config.DEV_REGIONS:
        return
    if region in config.SEALED_REGION and sealed_unlocked():
        return
    raise PermissionError(f"Refusing to load SILO key for region {region!r} (not a development region).")


def available_years():
    """Years for which a SILO file exists, sorted."""
    folder = check_path(config.SILO_DIR)
    years = []
    for path in folder.iterdir():
        match = FILE_PATTERN.search(path.name)
        if match:
            years.append(int(match.group(1)))
    return sorted(years)


def load_silo_year(year, regions=tuple(config.DEV_REGIONS)):
    """Rain grids for one year: {region: {"rain", "lat", "lon"}}. Reads only the named keys."""
    path = check_path(config.SILO_DIR / f"silo_monthly_rain_{year}.npz")
    grids = {}
    with np.load(path) as npz:  # an .npz is read lazily, key by key
        for region in regions:
            check_region_allowed(region)
            grids[region] = {
                "rain": npz[f"{region}__rain"],
                "lat": npz[f"{region}__lat"],
                "lon": npz[f"{region}__lon"],
            }
    return grids


def load_silo_grids(regions=tuple(config.DEV_REGIONS)):
    """All years stacked in time.

    Returns (grids, months):
      grids[region] = {"rain": (n_months, n_lat, n_lon) float32, "lat", "lon"}
      months        = int array of YYYYMM, one per month, oldest first
    """
    rain_by_region = {region: [] for region in regions}
    lat_lon = {}
    months = []
    for year in available_years():
        one_year = load_silo_year(year, regions)
        n_months = one_year[regions[0]]["rain"].shape[0]  # 12, or fewer for the current year
        months += [year * 100 + month for month in range(1, n_months + 1)]
        for region in regions:
            rain_by_region[region].append(one_year[region]["rain"])
            lat_lon[region] = (one_year[region]["lat"], one_year[region]["lon"])

    months = np.array(months)
    check_months_are_continuous(months)

    grids = {}
    for region in regions:
        lat, lon = lat_lon[region]
        grids[region] = {
            "rain": np.concatenate(rain_by_region[region], axis=0).astype(np.float32),
            "lat": lat,
            "lon": lon,
        }
    return grids, months


def check_months_are_continuous(months):
    """Raise if a month is missing, for example because one yearly file was not downloaded.

    Rain windows ("the 12 months before an issue") are later found by position
    in this array, so a gap would silently shift every window after it.
    """
    month_numbers = (months // 100) * 12 + (months % 100)
    if not (np.diff(month_numbers) == 1).all():
        raise ValueError("SILO months are not continuous: is a yearly file missing?")


# ---------------------------------------------------------------------------
# Nearest grid cell per waterbody
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between points given in degrees."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, float)) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def nearest_cell_index(lat, lon, grid_lat, grid_lon, has_data):
    """(i, j) of the grid cell nearest to (lat, lon); falls back to the nearest cell with data."""
    i = int(np.argmin(np.abs(grid_lat - lat)))
    j = int(np.argmin(np.abs(grid_lon - lon)))
    if has_data[i, j]:
        return i, j

    rows, cols = np.nonzero(has_data)
    squared_distance = (grid_lat[rows] - lat) ** 2 + (grid_lon[cols] - lon) ** 2
    best = int(np.argmin(squared_distance))
    return int(rows[best]), int(cols[best])


def cell_name(region, i, j):
    """Readable id of a SILO grid cell, e.g. "nsw_cw:12:40" (row i, column j)."""
    return f"{region}:{i}:{j}"


def assign_silo_cells(attrs, grids):
    """Add silo_cell, silo_lat, silo_lon and silo_dist_km to the attributes table."""
    names, cell_lats, cell_lons = [], [], []
    has_data = {
        region: np.isfinite(grid["rain"]).all(axis=0)  # data in every month
        for region, grid in grids.items()
    }
    for region, lat, lon in zip(attrs["region"], attrs["lat"], attrs["lon"]):
        grid = grids[region]
        i, j = nearest_cell_index(lat, lon, grid["lat"], grid["lon"], has_data[region])
        names.append(cell_name(region, i, j))
        cell_lats.append(float(grid["lat"][i]))
        cell_lons.append(float(grid["lon"][j]))

    attrs["silo_cell"] = names
    attrs["silo_lat"] = cell_lats
    attrs["silo_lon"] = cell_lons
    attrs["silo_dist_km"] = haversine_km(attrs["lat"], attrs["lon"], attrs["silo_lat"], attrs["silo_lon"])
    return attrs


# ---------------------------------------------------------------------------
# One monthly series per cell
# ---------------------------------------------------------------------------
def rain_by_cell(attrs, grids, months):
    """Monthly rain for every SILO cell used by at least one waterbody.

    Returns a dict:
      rain      (n_cells, n_months) float32, mm per month
      months    YYYYMM per column
      cells     cell id per row (sorted), matching attrs["silo_cell"]
      cell_lat, cell_lon
    """
    cells = sorted(set(attrs["silo_cell"]))
    rain = np.empty((len(cells), len(months)), dtype=np.float32)
    cell_lat = np.empty(len(cells))
    cell_lon = np.empty(len(cells))
    for row, cell in enumerate(cells):
        region, i, j = cell.split(":")
        i, j = int(i), int(j)
        grid = grids[region]
        rain[row] = grid["rain"][:, i, j]
        cell_lat[row] = grid["lat"][i]
        cell_lon[row] = grid["lon"][j]
    return {"rain": rain, "months": months, "cells": np.array(cells), "cell_lat": cell_lat, "cell_lon": cell_lon}
