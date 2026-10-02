"""Put every waterbody into a 2 km hexagon cell (used by the season rating).

Hex method, stated plainly
--------------------------
* Coordinates: each waterbody's polygon centre in GDA94 Australian Albers
  (EPSG:3577), which is in metres, so distances are true to within ~0.1%.
* Grid: "pointy-top" regular hexagons tiled from the Albers origin (0, 0).
  The cell size is the flat-to-flat width, 2 km (config.HEX_SIZE_KM), which
  is also the distance between neighbouring cell centres. The corner radius
  is width / sqrt(3) = 1.155 km and each cell covers sqrt(3)/2 * width^2
  = 3.46 km2.
* Indexing: standard axial coordinates (q, r) with cube rounding, as in the
  widely used Red Blob Games hexagon guide. The cell id is "h<q>_<r>".

Nothing here depends on the data, so the same point always lands in the same
cell, in any region.
"""
import math

import numpy as np

from damdays import config

HEX_WIDTH_M = config.HEX_SIZE_KM * 1000.0
HEX_RADIUS_M = HEX_WIDTH_M / math.sqrt(3.0)  # centre-to-corner distance


def point_to_fractional_axial(x, y, radius=HEX_RADIUS_M):
    """Convert metres to fractional axial hex coordinates (q, r) for pointy-top hexagons."""
    q = (math.sqrt(3.0) / 3.0 * x - 1.0 / 3.0 * y) / radius
    r = (2.0 / 3.0 * y) / radius
    return q, r


def round_to_hex(q, r):
    """Round fractional axial coordinates to the hexagon that contains the point.

    In cube coordinates (x, y, z) with x + y + z = 0, round each one, then fix
    the coordinate that moved the most so the three still sum to zero.
    """
    cube_x, cube_z = np.asarray(q, float), np.asarray(r, float)
    cube_y = -cube_x - cube_z
    round_x, round_y, round_z = np.round(cube_x), np.round(cube_y), np.round(cube_z)
    moved_x = np.abs(round_x - cube_x)
    moved_y = np.abs(round_y - cube_y)
    moved_z = np.abs(round_z - cube_z)

    x_moved_most = (moved_x > moved_y) & (moved_x > moved_z)
    y_moved_most = ~x_moved_most & (moved_y > moved_z)
    z_moved_most = ~x_moved_most & ~y_moved_most
    q = np.where(x_moved_most, -round_y - round_z, round_x)
    r = np.where(z_moved_most, -round_x - round_y, round_z)
    # When y moved most, only y is corrected, and axial (q, r) does not use y.
    return q.astype(int), r.astype(int)


def hex_centre(q, r, radius=HEX_RADIUS_M):
    """Centre (x, y) in metres of the hexagon with axial coordinates (q, r)."""
    q, r = np.asarray(q, float), np.asarray(r, float)
    x = radius * (math.sqrt(3.0) * q + math.sqrt(3.0) / 2.0 * r)
    y = radius * (1.5 * r)
    return x, y


def hex_cell_ids(x, y):
    """Cell id strings "h<q>_<r>" plus the integer q and r for points in Albers metres."""
    q_frac, r_frac = point_to_fractional_axial(np.asarray(x, float), np.asarray(y, float))
    q, r = round_to_hex(q_frac, r_frac)
    ids = [f"h{a}_{b}" for a, b in zip(q, r)]
    return ids, q, r


def add_hex_cells(attrs):
    """Add hex_id, hex_q, hex_r and hex_dist_m (centre of dam to centre of cell)."""
    ids, q, r = hex_cell_ids(attrs["x_albers"], attrs["y_albers"])
    attrs["hex_id"], attrs["hex_q"], attrs["hex_r"] = ids, q, r
    centre_x, centre_y = hex_centre(q, r)
    attrs["hex_dist_m"] = np.hypot(attrs["x_albers"] - centre_x, attrs["y_albers"] - centre_y)
    return attrs
