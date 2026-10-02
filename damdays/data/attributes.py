"""Describe each waterbody: its size and shape, where it is, and how it behaved before 2016.

One row per waterbody, built from three sources:

  * the manifest:      uid, region, lat, lon (DEA's polygon-centre geohash)
  * the polygon file:  area, perimeter, pixel count, shape, centre in metres
  * the panel:         pre-2016 history (number of looks, wet share, "full")

From these we set the three population flags used everywhere (PREREG.md):

  has_hist    at least 20 valid looks before 2016 and full > 0
  dam_like    has_hist, wet in at least 50% of pre-2016 looks, compact
              (pixel compactness >= 0.7), not elongated (PCA elongation <= 3),
              and 6 to 55 Landsat pixels. This filters out creeks, swamps and
              long channels so that what is left behaves like a farm dam.
  persistent  has_hist and wet in at least 80% of pre-2016 looks

Shape measures, in plain words:

  pixel compactness  The shortest outline any shape made of the same number
                     of 30 m pixels can have, divided by the real outline.
                     1 means as compact as possible; long or ragged shapes
                     score low.
  PCA elongation     Take the outline's corner points, find the direction of
                     most spread and the direction of least spread; elongation
                     is sqrt(most spread / least spread). A square or circle
                     is about 1, a long thin channel is large.

Only data before 2016 (config.STATIC_CUTOFF) is used for "full" and the flags,
so the populations are fixed before the test years begin.
"""
import math
import zipfile

import numpy as np
import pandas as pd
import shapefile  # pyshp

from damdays import config
from damdays.data.guard import check_path

SHAPEFILE_NAME = "ga_ls_wb_3_v3"
SHAPEFILE_PARTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")
PIXEL_SIDE_M = math.sqrt(config.PIXEL_M2)  # 30 m


# ---------------------------------------------------------------------------
# Polygons
# ---------------------------------------------------------------------------
def extract_polygons():
    """Unzip the DEA polygon shapefile into the cache folder (only the first time).

    Returns the path of the .shp file.
    """
    zip_path = check_path(config.POLYGONS_ZIP)
    out_dir = config.CACHE_DIR / "polygons"
    shp_path = out_dir / f"{SHAPEFILE_NAME}.shp"
    if shp_path.exists():
        return shp_path

    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for extension in SHAPEFILE_PARTS:
            archive.extract(SHAPEFILE_NAME + extension, out_dir)
    return shp_path


def find_polygon_records(reader, wanted_uids):
    """Map uid -> (record index, DEA area m2, DEA perimeter m) for the waterbodies we want.

    The national file holds about 325,000 waterbodies; we only need a few thousand.
    """
    wanted = set(wanted_uids)
    found = {}
    fields = ["uid", "area_m2", "perimetr_m"]  # "perimetr_m" is DEA's spelling
    for index, record in enumerate(reader.iterRecords(fields=fields)):
        # Read fields by name: pyshp returns them in file order, not in `fields` order.
        if record["uid"] in wanted:
            found[record["uid"]] = (index, record["area_m2"], record["perimetr_m"])
    return found


def read_polygons(uids):
    """Read area, perimeter and outline points for each uid.

    Returns a list of dicts: uid, area_m2, perimeter_m, points (N x 2 array of
    Albers metres, EPSG:3577), part_starts (index where each ring starts).
    """
    reader = shapefile.Reader(str(extract_polygons()))
    try:
        records = find_polygon_records(reader, uids)
        polygons = []
        for uid, (index, area_m2, perimeter_m) in records.items():
            shape = reader.shape(index)
            polygons.append({
                "uid": uid,
                "area_m2": area_m2,
                "perimeter_m": perimeter_m,
                "points": np.array(shape.points, dtype=float),
                "part_starts": list(shape.parts),
            })
    finally:
        reader.close()
    return polygons


# ---------------------------------------------------------------------------
# Shape measures
# ---------------------------------------------------------------------------
def min_pixel_perimeter_m(n_pixels):
    """Shortest possible outline (metres) of a blob made of `n_pixels` square pixels.

    For n unit squares the minimum perimeter is 2 * ceil(2 * sqrt(n)) sides
    (a known result for polyominoes); each side is 30 m.
    """
    return 2 * math.ceil(2 * math.sqrt(n_pixels)) * PIXEL_SIDE_M


def pixel_compactness(area_m2, perimeter_m):
    """Minimum possible pixel perimeter / real perimeter, capped at 1."""
    n_pixels = area_m2 / config.PIXEL_M2
    return min(1.0, min_pixel_perimeter_m(n_pixels) / perimeter_m)


def pca_elongation(points):
    """sqrt(largest / smallest variance) of the outline's vertex coordinates."""
    centred = points - points.mean(axis=0)
    variances = np.linalg.eigvalsh(np.cov(centred.T))  # sorted smallest first
    smallest = max(variances[0], 1e-9)  # guard against a perfectly flat outline
    return math.sqrt(variances[1] / smallest)


def ring_centroid(ring):
    """Area-weighted centre (x, y) of one closed ring, using the shoelace formula."""
    x, y = ring[:, 0], ring[:, 1]
    x_next, y_next = np.roll(x, -1), np.roll(y, -1)
    cross = x * y_next - x_next * y
    twice_area = cross.sum()
    if twice_area == 0:
        return x.mean(), y.mean()
    centre_x = ((x + x_next) * cross).sum() / (3 * twice_area)
    centre_y = ((y + y_next) * cross).sum() / (3 * twice_area)
    return centre_x, centre_y


def shape_row(polygon):
    """All shape measures for one polygon, as a dict."""
    points = polygon["points"]
    starts = polygon["part_starts"] + [len(points)]
    outer_ring = points[starts[0]:starts[1]]  # the first ring is the main outline
    centre_x, centre_y = ring_centroid(outer_ring)
    return {
        "uid": polygon["uid"],
        "area_m2": polygon["area_m2"],
        "perimeter_m": polygon["perimeter_m"],
        "n_pixels": polygon["area_m2"] / config.PIXEL_M2,
        "n_parts": len(polygon["part_starts"]),
        "pixel_compactness": pixel_compactness(polygon["area_m2"], polygon["perimeter_m"]),
        "elongation": pca_elongation(points),
        "x_albers": centre_x,
        "y_albers": centre_y,
    }


def shape_table(uids):
    """One row of shape measures per uid."""
    return pd.DataFrame([shape_row(polygon) for polygon in read_polygons(uids)])


# ---------------------------------------------------------------------------
# History before a cut-off date
# ---------------------------------------------------------------------------
def history_summary(panel, before):
    """Per waterbody, using only valid looks dated before `before`:

      n_obs      number of valid looks
      wet_share  share of looks with at least one wet pixel
      full       90th-percentile pc_wet: the dam's own "full" level

    Kept general (any cut-off date) so causal yearly versions can reuse it.
    """
    early = panel[panel["date"] < pd.Timestamp(before)]
    uid = early["uid"].astype(str)
    summary = pd.DataFrame({
        "n_obs": early.groupby(uid).size(),
        "wet_share": (early["px_wet"] > 0).groupby(uid).mean(),
        "full": early["pc_wet"].groupby(uid).quantile(config.FULL_QUANTILE),
    })
    summary.index.name = "uid"
    return summary


# ---------------------------------------------------------------------------
# Population flags
# ---------------------------------------------------------------------------
def add_population_flags(attrs):
    """Add has_hist, dam_like, persistent and dam_like_persistent (PREREG.md)."""
    rules = config.DAM_LIKE
    attrs["has_hist"] = (attrs["n_pre_obs"] >= config.MIN_PRE_OBS) & (attrs["full"] > 0)

    is_mostly_wet = attrs["wet_share"] >= rules["min_wet_share"]
    is_compact = attrs["pixel_compactness"] >= rules["min_compact"]
    is_not_elongated = attrs["elongation"] <= rules["max_elong"]
    is_dam_sized = attrs["n_pixels"].between(rules["min_px"], rules["max_px"])
    attrs["dam_like"] = attrs["has_hist"] & is_mostly_wet & is_compact & is_not_elongated & is_dam_sized

    attrs["persistent"] = attrs["has_hist"] & (attrs["wet_share"] >= config.PERSISTENT_MIN_WET_SHARE)
    attrs["dam_like_persistent"] = attrs["dam_like"] & attrs["persistent"]
    return attrs


# ---------------------------------------------------------------------------
# Everything together
# ---------------------------------------------------------------------------
def build_attributes(panel, manifest):
    """One row per waterbody with location, shape, pre-2016 history and flags."""
    attrs = manifest[["uid", "region", "lat", "lon"]].copy()
    shapes = shape_table(attrs["uid"])
    attrs = attrs.merge(shapes, on="uid", how="left")

    history = history_summary(panel, before=config.STATIC_CUTOFF)
    history = history.rename(columns={"n_obs": "n_pre_obs"})
    attrs = attrs.merge(history, left_on="uid", right_index=True, how="left")
    attrs["n_pre_obs"] = attrs["n_pre_obs"].fillna(0).astype(int)

    # Comparisons with missing values (no history / no polygon) give False,
    # so such waterbodies simply fall outside every population.
    return add_population_flags(attrs)
