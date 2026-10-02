"""Unit tests for the physics features (damdays.models.physics), on small made-up inputs.

The look-ahead test (tests/test_no_lookahead.py) checks the real build end to
end; these check each piece does what its docstring says.
"""
import numpy as np
import pandas as pd
import pytest

from damdays.features import spec
from damdays.models import physics, tidemark


def test_the_columns_are_the_ones_rung_l3_reads():
    assert physics.PHY_COLUMNS == tidemark.PHY_COLUMNS == tuple(spec.PHYSICS_FEATURE_SPEC)
    assert tidemark.RUNGS["L3"].extra_features == physics.PHY_COLUMNS
    spec.check_feature_list(physics.PHY_COLUMNS)


def test_evaporation_shapes_are_typed_bom_climatology_scaled_to_one():
    for region, values in physics.EVAPORATION_MM_PER_DAY.items():
        assert len(values) == 12
        shape = physics.evaporation_shape(region)
        assert shape.mean() == pytest.approx(1.0)
        summer, winter = shape[[0, 1, 11]].mean(), shape[[5, 6, 7]].mean()
        assert summer > 2 * winter                     # southern-hemisphere pan evaporation
    with pytest.raises(KeyError):
        physics.evaporation_shape("nowhere")


def test_calendar_helpers():
    days = physics.day_numbers(["1960-01-01", "1960-02-29", "2014-07-09"])
    assert list(physics.month_number(days)) == [0, 1, 54 * 12 + 6]
    assert list(physics.day_of_month(days)) == [1, 29, 9]
    assert list(physics.days_in_month(3)) == [31, 29, 31]
    totals = physics.running_total_before(np.array([1.0, 2.0, 3.0]), np.array([31, 29, 31]))
    assert list(totals) == [0.0, 31.0, 31.0 + 58.0]


def test_earlier_years_mean_never_uses_the_month_itself_or_later_years():
    values = np.arange(36, dtype=float)[None, :]                  # 3 years of months
    mean = physics.same_month_earlier_years_mean(values)
    assert np.isnan(mean[0, :12]).all()                            # no earlier year
    assert mean[0, 12] == 0.0 and mean[0, 24] == 6.0               # Januaries: (0) then (0 + 12) / 2
    changed = values.copy()
    changed[0, 24:] = 999.0                                        # change the last year only
    assert np.array_equal(physics.same_month_earlier_years_mean(changed)[0, :25], mean[0, :25], equal_nan=True)


def small_rain_tables(n_months=48, rain_mm=40.0):
    """RainTables for one cell with the same rain every month (and a different rain in month 30)."""
    rain = np.full(n_months, rain_mm)
    rain[30] = 400.0
    by_cell = {"rain": rain[None, :], "months": np.array([196001 + (m // 12) * 100 + m % 12 for m in range(n_months)]),
               "cells": np.array(["c"])}
    return physics.build_rain_tables(by_cell, np.array(["c"]), n_months, pd.Timestamp("2030-01-01"))


def test_filter_rain_uses_the_average_for_the_unfinished_month():
    tables = small_rain_tables()
    k = np.array([0])                                              # threshold 0 mm
    cell = np.array([0])
    # Both looks inside month 30 (a very wet month): only the earlier-years average is used.
    within = physics.filter_rain_between(tables, k, cell, np.array([30]), np.array([3]), np.array([30]), np.array([13]))
    assert within[0] == pytest.approx(10 * 40.0 / physics.days_in_month(31)[30])
    # From month 29 into month 30: the rest of month 29 is actual rain, the days of month 30 the average.
    n_days = physics.days_in_month(31)
    across = physics.filter_rain_between(tables, k, cell, np.array([29]), np.array([20]), np.array([30]), np.array([5]))
    expected = (n_days[29] - 20) * 40.0 / n_days[29] + 5 * 40.0 / n_days[30]
    assert across[0] == pytest.approx(expected)
    # From month 30 into month 31: month 30's actual (400 mm) is used once it has ended.
    after = physics.filter_rain_between(tables, k, cell, np.array([30]), np.array([n_days[30]]), np.array([31]),
                                        np.array([1]))
    assert after[0] == pytest.approx(tables.climate[0, 0, 31])
    full_month = physics.filter_rain_between(tables, k, cell, np.array([29]), np.array([n_days[29]]), np.array([31]),
                                             np.array([1]))
    assert full_month[0] == pytest.approx(400.0 + tables.climate[0, 0, 31])


def test_huber_ridge_recovers_the_balance_despite_misreads():
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 1, (5000, 3))
    truth = np.array([0.002, 0.0013, 0.003])
    y = X @ truth + rng.normal(0, 1e-4, 5000)
    y[:200] += rng.normal(0, 0.05, 200)                            # satellite misreads
    coef, loss = physics.huber_ridge(X, y)
    assert np.allclose(coef, truth, rtol=0.05)
    assert loss > 0


def futures(start_rel, armed_left, rain_mm=0.0, x=0.01, n=3):
    """simulate_futures for n identical forecasts on a made-up cell with constant rain."""
    tables = small_rain_tables(n_months=400, rain_mm=rain_mm)
    calendar = physics.build_calendar_tables(["nsw_cw"], 420)
    issue_day = physics.day_numbers(["1990-11-15"]).repeat(n)
    one = np.ones(n)
    return physics.simulate_futures(
        start_mean=one * start_rel ** physics.VOLUME_EXPONENT, start_var=one * 1e-6, c=one * 0.002, e=one * 0.001,
        x=one * x, k=np.zeros(n, dtype=int), cell=np.zeros(n, dtype=int), region=np.zeros(n, dtype=int),
        issue_day=issue_day, armed_left=one * armed_left, d0_level=one * 0.05, rain_tables=tables,
        calendar=calendar, noise=physics.member_noise())


def test_a_draining_armed_dam_hits_both_events_and_an_unarmed_one_none():
    p_r30, p_d0 = futures(start_rel=0.5, armed_left=100.0)
    assert (p_r30 == 1.0).all() and (p_d0 == 1.0).all()            # 0.9% of full a day, no rain: dry in 90 days
    p_r30, p_d0 = futures(start_rel=0.5, armed_left=-1.0)
    assert (p_r30 == 0.0).all() and (p_d0 == 0.0).all()            # never armed, never refilled: no event
    p_r30, p_d0 = futures(start_rel=0.9, armed_left=100.0, rain_mm=400.0, x=0.0)
    assert (p_r30 == 0.0).all()                                     # a wet run keeps it full


def test_each_forecast_is_independent_of_the_others_computed_with_it():
    tables = small_rain_tables(n_months=400)
    calendar = physics.build_calendar_tables(["nsw_cw"], 420)
    rng = np.random.default_rng(1)
    n = 6
    args = dict(start_mean=rng.uniform(0.2, 1.0, n), start_var=rng.uniform(0.001, 0.05, n), c=np.full(n, 0.002),
                e=np.full(n, 0.0012), x=np.full(n, 0.003), k=np.zeros(n, dtype=int), cell=np.zeros(n, dtype=int),
                region=np.zeros(n, dtype=int), issue_day=physics.day_numbers(["1990-10-01"] * n) + np.arange(n) * 9,
                armed_left=np.full(n, 50.0), d0_level=np.full(n, 0.05))
    together = physics.simulate_futures(**args, rain_tables=tables, calendar=calendar, noise=physics.member_noise())
    for i in range(n):
        alone = physics.simulate_futures(**{key: value[i:i + 1] for key, value in args.items()},
                                         rain_tables=tables, calendar=calendar, noise=physics.member_noise())
        assert alone[0][0] == together[0][i] and alone[1][0] == together[1][i]


def test_analogue_years_must_be_before_the_issue():
    tables = small_rain_tables(n_months=400)
    calendar = physics.build_calendar_tables(["nsw_cw"], 420)
    one = np.ones(1)
    with pytest.raises(AssertionError):                            # 1970: 20 years back is before the rain record
        physics.simulate_futures(one * 0.5, one * 0.01, one * 0.002, one * 0.001, one * 0.003, np.zeros(1, int),
                                 np.zeros(1, int), np.zeros(1, int), physics.day_numbers(["1970-06-01"]), one * 50,
                                 one * 0.05, tables, calendar, physics.member_noise())


def test_kalman_filter_blends_prediction_and_look_and_restarts():
    z = np.array([0.5, 0.5, np.nan, 0.8])
    restart = np.array([True, False, False, True])
    zeros = np.zeros(4)
    mean, var = physics.kalman_filter(z, restart, np.array([0.0, 10.0, 10.0, 90.0]), zeros, zeros, zeros,
                                      zeros, zeros, zeros)
    assert mean[0] == 0.5 and var[0] == physics.OBS_VARIANCE
    assert mean[1] == pytest.approx(0.5) and var[1] < var[0] + 10 * physics.PROCESS_VARIANCE_PER_DAY
    assert mean[2] == pytest.approx(0.5) and var[2] > var[1]       # no look: keep the prediction, more unsure
    assert mean[3] == 0.8 and var[3] == physics.OBS_VARIANCE       # restart from the look


def test_dry_level_is_half_a_pixel_of_the_full_area():
    assert physics.dry_level([10.0], [100.0])[0] == pytest.approx(0.05)
    assert physics.dry_level([1000.0], [100.0])[0] == physics.D0_LEVEL_RANGE[0]
    assert physics.dry_level([1.0], [50.0])[0] == physics.D0_LEVEL_RANGE[1]


def made_up_inputs(regions):
    """A tiny data layer for build_physics: one made-up dam per region, a look every 10 days 1987-1996.

    Each dam fills in winter and draws down in summer (plus noise), on its own made-up rain cell.
    """
    rng = np.random.default_rng(3)
    dates = pd.date_range("1987-01-05", "1996-12-20", freq="10D")
    season = np.cos(2 * np.pi * (dates.dayofyear.to_numpy() - 240) / 365.25)    # high in late winter
    panel, attrs = [], []
    for i, region in enumerate(regions):
        uid = f"dam{i}_{region}"
        pc = np.clip(55 + 40 * season + rng.normal(0, 8, len(dates)), 0, 100)
        panel.append(pd.DataFrame({"uid": uid, "region": region, "date": dates, "pc_wet": pc,
                                   "px_wet": np.round(pc / 100 * 20)}))
        attrs.append(dict(uid=uid, region=region, has_hist=True, n_pixels=20.0, full=95.0, silo_cell=f"cell{i}"))
    months = np.array([y * 100 + m for y in range(1960, 1997) for m in range(1, 13)])
    rain = {"rain": rng.gamma(2.0, 25.0, (len(regions), len(months))), "months": months,
            "cells": np.array([f"cell{i}" for i in range(len(regions))])}
    return pd.concat(panel, ignore_index=True), pd.DataFrame(attrs), rain


def test_a_new_region_is_simulated_with_the_development_balance_but_never_changes_it():
    """The pooled balance is fitted on the development regions only (FINAL_SPEC, PREREG sealed protocol)."""
    dev = list(physics.FIT_REGIONS)
    panel, attrs, rain = made_up_inputs(dev + ["sealed_sdowns_newengland"])
    is_dev = attrs["region"].isin(dev).to_numpy()
    dev_panel = panel[panel["region"].isin(dev)]
    dev_rain = {"rain": rain["rain"][is_dev], "months": rain["months"], "cells": rain["cells"][is_dev]}

    alone = physics.build_physics(dev_panel, attrs[is_dev], dev_rain)
    together = physics.build_physics(panel, attrs, rain)
    # Same balance, so every development forecast is unchanged ...
    assert alone["physics_params"].equals(together["physics_params"])
    dev_rows = together["p1_physics"]["uid"].isin(attrs.loc[is_dev, "uid"])
    for column in physics.PHY_COLUMNS:
        assert np.array_equal(together["p1_physics"].loc[dev_rows, column].to_numpy(),
                              alone["p1_physics"][column].to_numpy(), equal_nan=True)
    # ... and the new region's dam still gets its own forecasts from it (blank before 1993 only).
    new = together["p1_physics"].loc[~dev_rows]
    from_1993 = pd.to_datetime(new["issue_date"]) >= "1993-01-01"
    assert new.loc[from_1993, "ph_p_R30"].notna().all() and new.loc[~from_1993, "ph_p_R30"].isna().all()
    # A build with no development-region looks has nothing to fit the balance on: it refuses.
    sealed_panel = panel[~panel["region"].isin(dev)]
    sealed_rain = {"rain": rain["rain"][~is_dev], "months": rain["months"], "cells": rain["cells"][~is_dev]}
    with pytest.raises(ValueError, match="development regions"):
        physics.build_physics(sealed_panel, attrs[~is_dev], sealed_rain)


def test_attaching_refuses_a_table_out_of_p1_order(tmp_path):
    p1 = pd.DataFrame({"uid": ["a", "a", "b"], "issue_date": pd.to_datetime(["2000-01-01", "2000-02-01", "2000-01-05"])})
    table = p1.assign(ph_p_R30=[0.1, 0.2, 0.3], ph_p_D0=[0.0, 0.1, 0.0])
    path = tmp_path / "physics.pkl"
    physics.save_physics(table, p1, path)
    attached = physics.with_physics_columns(p1, path)
    assert list(attached["ph_p_R30"]) == pytest.approx([0.1, 0.2, 0.3])
    with pytest.raises(AssertionError):
        physics.with_physics_columns(p1.iloc[::-1].reset_index(drop=True), path)
    assert physics.with_physics_columns(p1, tmp_path / "missing.pkl") is p1
