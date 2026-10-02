"""Small checks of the data helpers: sealed guard, dates, shapes, hex cells, splits, SILO cells.

None of these tests read real data, and none touch the sealed folder: the guard
only does text checks on paths.
"""
import numpy as np
import pandas as pd
import pytest

from damdays import config
from damdays.data import attributes, cells, panel, rainfall, splits
from damdays.data.guard import check_path


# ---------------------------------------------------------------------------
# Sealed-region guard
# ---------------------------------------------------------------------------
def test_guard_blocks_sealed_paths(monkeypatch):
    monkeypatch.delenv(config.SEALED_UNLOCK_ENV, raising=False)
    with pytest.raises(PermissionError):
        check_path(config.SEALED_DIR / "any_file.csv")
    with pytest.raises(PermissionError):
        check_path(config.DEV_TS_DIR / ".." / ".." / "dea_sealed" / "any_file.csv")


def test_guard_allows_dev_paths(monkeypatch):
    monkeypatch.delenv(config.SEALED_UNLOCK_ENV, raising=False)
    assert check_path(config.DEV_MANIFEST) == config.DEV_MANIFEST


def test_guard_opens_only_with_the_exact_unlock_value(monkeypatch):
    monkeypatch.setenv(config.SEALED_UNLOCK_ENV, "true")  # not "yes": still sealed
    with pytest.raises(PermissionError):
        check_path(config.SEALED_DIR / "any_file.csv")
    monkeypatch.setenv(config.SEALED_UNLOCK_ENV, "yes")
    assert check_path(config.SEALED_DIR / "any_file.csv") == config.SEALED_DIR / "any_file.csv"


def test_silo_sealed_key_is_refused(monkeypatch):
    monkeypatch.delenv(config.SEALED_UNLOCK_ENV, raising=False)
    sealed_region = next(iter(config.SEALED_REGION))
    with pytest.raises(PermissionError):
        rainfall.check_region_allowed(sealed_region)
    rainfall.check_region_allowed("nsw_cw")  # development regions are fine


# ---------------------------------------------------------------------------
# Panel cleaning
# ---------------------------------------------------------------------------
def test_utc_is_converted_to_local_date():
    utc = pd.Series(["2019-07-01T23:50:00Z", "2019-07-01T13:00:00Z"])
    local = panel.utc_to_local_date(utc)
    # 23:50 UTC is 09:50 the next morning in eastern Australia; 13:00 UTC is 23:00 the same day.
    assert list(local) == [pd.Timestamp("2019-07-02"), pd.Timestamp("2019-07-01")]


def test_invalid_rows_are_dropped():
    raw = pd.DataFrame({"pc_wet": [50.0, np.nan, 20.0, 120.0], "px_wet": [5.0, 3.0, np.nan, 12.0]})
    kept, invalid, out_of_range = panel.keep_valid_rows(raw)
    assert list(kept.index) == [0]
    assert invalid.sum() == 2 and out_of_range.sum() == 1


def test_scenes_on_the_same_local_day_are_averaged():
    obs = pd.DataFrame({
        "uid": ["A", "A", "A"],
        "date": pd.to_datetime(["2019-07-02", "2019-07-02", "2019-07-18"]),
        "pc_wet": [40.0, 60.0, 30.0],
        "px_wet": [4.0, 6.0, 3.0],
    })
    merged = panel.merge_same_day(obs)
    assert list(merged["pc_wet"]) == [50.0, 30.0]
    assert list(merged["n_scenes"]) == [2, 1]


# ---------------------------------------------------------------------------
# Shape measures
# ---------------------------------------------------------------------------
def test_pixel_compactness():
    # 9 pixels as a 3 x 3 square: perimeter 360 m, the shortest possible -> 1.
    assert attributes.pixel_compactness(9 * 900, 360) == 1.0
    # 9 pixels in a 1 x 9 line: perimeter 600 m -> 360 / 600 = 0.6.
    assert attributes.pixel_compactness(9 * 900, 600) == pytest.approx(0.6)


def test_pca_elongation():
    square = np.array([[0, 0], [0, 100], [100, 100], [100, 0]], dtype=float)
    long_rectangle = np.array([[0, 0], [0, 100], [400, 100], [400, 0]], dtype=float)
    assert attributes.pca_elongation(square) == pytest.approx(1.0)
    assert attributes.pca_elongation(long_rectangle) == pytest.approx(4.0)


def test_ring_centroid_of_a_square():
    ring = np.array([[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]], dtype=float)
    assert attributes.ring_centroid(ring) == pytest.approx((5.0, 5.0))


def test_population_flags():
    attrs = pd.DataFrame({
        "n_pre_obs": [30, 30, 10, 30],
        "full": [60.0, 60.0, 60.0, 60.0],
        "wet_share": [0.9, 0.6, 0.9, 0.9],
        "pixel_compactness": [0.8, 0.8, 0.8, 0.5],
        "elongation": [1.5, 1.5, 1.5, 1.5],
        "n_pixels": [20.0, 20.0, 20.0, 20.0],
    })
    flags = attributes.add_population_flags(attrs)
    assert list(flags["has_hist"]) == [True, True, False, True]
    assert list(flags["dam_like"]) == [True, True, False, False]  # last one is not compact
    assert list(flags["persistent"]) == [True, False, False, True]


# ---------------------------------------------------------------------------
# Hex cells
# ---------------------------------------------------------------------------
def test_hex_neighbours_are_2_km_apart():
    ids, q, r = cells.hex_cell_ids([0.0, 2000.0], [0.0, 0.0])
    assert ids == ["h0_0", "h1_0"]


def test_every_point_lies_within_its_hex():
    rng = np.random.default_rng(0)
    x = rng.uniform(-50_000, 50_000, 5_000)
    y = rng.uniform(-50_000, 50_000, 5_000)
    _, q, r = cells.hex_cell_ids(x, y)
    centre_x, centre_y = cells.hex_centre(q, r)
    distance = np.hypot(x - centre_x, y - centre_y)
    assert distance.max() <= cells.HEX_RADIUS_M + 1e-6


def test_hex_centre_maps_back_to_its_own_cell():
    q = np.array([-3, 0, 5, 12])
    r = np.array([7, 0, -2, 4])
    centre_x, centre_y = cells.hex_centre(q, r)
    _, q_back, r_back = cells.hex_cell_ids(centre_x, centre_y)
    assert list(q_back) == list(q) and list(r_back) == list(r)


# ---------------------------------------------------------------------------
# Splits and folds
# ---------------------------------------------------------------------------
def test_time_blocks():
    dates = ["2008-12-31", "2009-01-01", "2015-12-31", "2016-03-01", "2016-07-01", "2026-06-30", "2026-07-01"]
    assert list(splits.time_block(dates)) == ["TRAIN", "VAL", "VAL", "GAP", "TEST", "TEST", "AFTER"]


def test_purge_keeps_only_rows_whose_answer_is_known():
    # 2008-09-02 + 90 + 30 days = 2008-12-31 (closes before VAL starts); 2008-09-03 -> 2009-01-01 (too late).
    dates = ["2008-09-02", "2008-09-03"]
    assert list(splits.fit_mask(dates, "VAL")) == [True, False]


def test_dam_folds_are_fixed_and_balanced():
    uids = [f"dam{k}" for k in range(100)]
    folds = splits.dam_folds(uids)
    assert sorted(np.bincount(folds)) == [20, 20, 20, 20, 20]
    # Same folds whatever order the uids come in.
    reversed_folds = splits.dam_folds(list(reversed(uids)))
    assert list(reversed_folds) == list(reversed(folds))


# ---------------------------------------------------------------------------
# SILO nearest cell
# ---------------------------------------------------------------------------
def test_nearest_silo_cell_falls_back_to_a_cell_with_data():
    grid_lat = np.array([-31.0, -30.95, -30.9])
    grid_lon = np.array([148.0, 148.05, 148.1])
    has_data = np.ones((3, 3), dtype=bool)
    assert rainfall.nearest_cell_index(-30.96, 148.04, grid_lat, grid_lon, has_data) == (1, 1)
    has_data[1, 1] = False  # the nearest cell has gaps -> use the nearest one with data
    i, j = rainfall.nearest_cell_index(-30.96, 148.04, grid_lat, grid_lon, has_data)
    assert (i, j) != (1, 1) and has_data[i, j]


def test_silo_months_must_be_continuous():
    rainfall.check_months_are_continuous(np.array([201911, 201912, 202001, 202002]))
    with pytest.raises(ValueError):
        rainfall.check_months_are_continuous(np.array([201812, 202001]))  # all of 2019 missing
