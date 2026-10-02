# Data contract: the files the app reads

The app has no server. It shows whatever is in six small JSON files. This page says exactly what each file must contain, so the pipeline (Python) and the app (JavaScript) can be built separately and still fit together.

All numbers in the examples on this page are made up, only to show the format.

## Where the files go

```
app/data/
  datasets.js          list of datasets, preferred first ("real" before "mock")
  mock/                made-up data for building the app (make_mock_data.py)
  real/                real forecasts, written by the pipeline's exporter
    meta.json          what this dataset is
    forecasts.json     each dam's forecast, today and on past dates
    curves.json        each dam's runway curve (30, 60, 90, 180 days)
    history.json       each dam's monthly water level since 1988
    cells.json         2 km cells: rainfall-only score, DamDays Rating, what happened
    scoreboard.json    test scores (AUC with ranges)
    bundle.js          the six files packed into one script (made by build_bundle.py)
```

To publish a dataset:

1. Write the six JSON files into `app/data/real/`.
2. Run `python app/tools/build_bundle.py app/data/real`. This checks that each file has its main fields, writes `bundle.js`, and lists `real` first in `datasets.js`, so the app uses it from then on.

Why `bundle.js`: when you double-click `index.html`, browsers refuse to read other local files with `fetch()`, but they do run `<script>` files. The bundle is a copy of the JSON wrapped in one script. Never edit it by hand.

To look at the mock data even when real data exists, add `?data=mock` to the address.

## Rules for every file

- **Dates** are `"YYYY-MM-DD"` in local Australian dates (UTC+10, the same as the pipeline). **Months** are `"YYYY-MM"`.
- **Chances** are numbers from 0 to 1 (0.58 means 58%), rounded to 3 decimals.
- **Water levels** are whole-number percentages of the dam's usual full wet area (see `level_pct` below).
- **Missing** values are `null`. Never `NaN` or an empty string.
- **Coordinates** are WGS84 degrees, rounded to 5 decimals.
- `dam_id` and `cell_id` are the keys that join the files. Keep them stable between exports.

**Honesty rules** (these matter more than the format):

- Past forecasts (Rewind) and past seasons (Rating) must be **out of sample**: made by models fitted only on data from before the forecast date (the 2016-2026 TEST predictions). Never in-sample fits.
- Outcomes use the PREREG event definitions: "below a third" (R30) for the farmer runway, "ran dry" (D0) for the season rating.
- Scoreboard numbers are copied from the evaluation output, never retyped or rounded by hand.
- `meta.is_mock` is `false` only for real exports. When it is `true`, the app shows a large MOCK banner.

---

## meta.json: what this dataset is

| field | type | example | meaning |
|---|---|---|---|
| `schema_version` | string | `"1.0"` | version of this contract |
| `is_mock` | boolean | `false` | `true` shows the MOCK banner on every page |
| `generated_at` | string | `"2026-10-03T09:30:00Z"` | when the export ran (UTC, ISO 8601) |
| `region` | object | see below | the area this dataset covers |
| `region.key` | string | `"nsw_cw"` | short name, as in `damdays/config.py` |
| `region.name` | string | `"NSW Central West"` | shown in the app |
| `region.bbox` | array of 4 numbers | `[-33.5, -30.5, 147.0, 150.0]` | lat_min, lat_max, lon_min, lon_max |
| `data_through` | date | `"2026-09-14"` | the last satellite look used |
| `horizon_days` | integer, days | `90` | how far ahead the farmer forecast looks |
| `threshold_pct` | integer, % of full | `30` | "below a third" means below this level |
| `arm_level_pct` | integer, % of full | `60` | a dam must have refilled to this level in the last 180 days to get a forecast |
| `min_dam_area_ha` | number, hectares | `0.54` | the smallest dam DEA Waterbodies can see (6 Landsat pixels) |
| `model` | object | `{"name": "Tidemark v1", "version": "L3", "config_hash": "abc123"}` | which model made the numbers; `version` and `config_hash` may be `null` |
| `note` | string, optional | | a plain sentence about this dataset |

---

## forecasts.json: each dam's forecast

```json
{
  "horizon_days": 90,
  "dams": [ { "dam_id": "nsw_cw-0003", "name": "Dam 3", "lat": -32.12345, "lon": 148.45678,
              "area_ha": 1.3, "dea_uid": "r3dp1..." } ],
  "issues": [
    { "issue_date": "2026-09-15", "kind": "live", "label": "Latest forecast", "note": null,
      "rows": [ { "dam_id": "nsw_cw-0003", "status": "forecast",
                  "issued_on": "2026-09-12", "window_end": "2026-12-11", "level_pct": 64,
                  "chance": 0.58, "chance_low": 0.41, "chance_high": 0.73, "damdays_days": 60,
                  "notes": ["Runs drier than similar dams nearby."],
                  "outcome": null, "outcome_date": null } ] }
  ]
}
```

**`dams`**: one entry per dam shown in the app.

| field | type | meaning |
|---|---|---|
| `dam_id` | string | stable key used by every file |
| `name` | string | short plain name shown to people, e.g. `"Dam 3"` |
| `lat`, `lon` | number, degrees | the dam's centre |
| `area_ha` | number, hectares | the dam's DEA polygon area |
| `dea_uid` | string or null | DEA Waterbodies id, so anyone can trace the dam back to the source |

**`issues`**: one entry per forecast date. Exactly one has `kind: "live"` (today's forecasts, shown in Runway). Any number have `kind: "past"` (shown in Rewind, oldest first).

| field | type | meaning |
|---|---|---|
| `issue_date` | date | the date the forecasts are "as of" |
| `kind` | `"live"` or `"past"` | |
| `label` | string | short name for menus |
| `note` | string or null | shown under the Rewind date picker (for example, which model and block made these) |
| `rows` | array | one row per dam in `dams` (every dam, even when it has no forecast) |

**`rows`**: one dam on one issue date.

| field | type | unit | meaning |
|---|---|---|---|
| `dam_id` | string | | |
| `status` | string | | `"forecast"`, `"already_low"` (below a third now), `"not_refilled"` (not at `arm_level_pct` in the last 180 days), or `"no_recent_look"` (no valid satellite look in the last 60 days) |
| `issued_on` | date | | the satellite look the forecast starts from: the last valid look on or before `issue_date` |
| `window_end` | date | | `issued_on` + `horizon_days` |
| `level_pct` | integer or null | % of full | the level at that look |
| `chance` | number or null | 0 to 1 | chance the dam falls below a third (an R30 event starts) after `issued_on` and by `window_end` |
| `chance_low`, `chance_high` | number or null | 0 to 1 | the season band: the chance in an unusually wet or unusually dry season |
| `damdays_days` | integer or null | days | the DamDays number (the LB90 floor): at least this many days above a third, 9 times in 10. May be over 180; the app shows "180+" |
| `notes` | array of strings | | plain sentences shown on the card, e.g. "Runs drier than similar dams nearby." or "Outside the conditions the model was tested on." Empty array if none |
| `outcome` | boolean or null | | past issues only: `true` if an R30 event started in the window, `false` if not, `null` if unknown (fewer than 3 valid looks, or the window has not ended). Always `null` for the live issue |
| `outcome_date` | date or null | | the first confirming look of that event |

The four `chance...` and `damdays_days` fields are `null` unless `status` is `"forecast"`.

---

## curves.json: the runway curve

```json
{
  "horizons_days": [30, 60, 90, 180],
  "issues": [
    { "issue_date": "2026-09-15",
      "by_dam": { "nsw_cw-0003": { "chance": [0.12, 0.31, 0.58, 0.77],
                                   "low":    [0.07, 0.19, 0.41, 0.60],
                                   "high":   [0.19, 0.45, 0.73, 0.89] } } }
  ]
}
```

- Each array lines up with `horizons_days`: the chance of falling below a third by 30, 60, 90 and 180 days.
- Values never go down along the array, and `low <= chance <= high`.
- Only dams whose row has `status: "forecast"`. One entry per issue date in `forecasts.json` (the same `issue_date`).
- The app draws the line from this file and marks the 90-day headline from `forecasts.json`. If the two differ, the headline dot sits off the line. The exporter should make them agree and say in the README how.

---

## history.json: monthly water level

```json
{
  "first_month": "1988-01",
  "last_month": "2026-09",
  "by_dam": { "nsw_cw-0003": { "level_pct": [96, 88, null, 71],
                               "events": [ { "date": "2019-01-14", "kind": "below_third" },
                                           { "date": "2019-11-02", "kind": "dry" } ] } }
}
```

- `level_pct` has one value per month from `first_month` to `last_month`, inclusive: the median of that month's valid looks, as a whole-number % of the dam's usual full wet area (the PREREG static "full"), capped at 150. `null` means no valid look that month.
- `events` lists past event starts using the PREREG definitions: `"below_third"` (R30) and `"dry"` (D0). Empty array if none.
- In Rewind, the app hides months after the forecast's `issued_on` until "Reveal" is pressed.

---

## cells.json: the season rating on 2 km cells

```json
{
  "cell_size_km": 2,
  "season_months": "Oct-Mar",
  "cells": [ { "cell_id": "h123_-45", "lat": -32.1, "lon": 148.5,
               "corners": [[-32.10, 148.51], [-32.09, 148.51], [-32.09, 148.50],
                           [-32.10, 148.49], [-32.11, 148.49], [-32.11, 148.50]],
               "n_dams": 1 } ],
  "seasons": [
    { "season": "2018-19", "issue_date": "2018-07-01", "kind": "past",
      "rows": [ { "cell_id": "h123_-45", "rain_only_chance": 0.12,
                  "rating_chance": 0.31, "ran_dry": true } ] }
  ]
}
```

**`cells`**: the 2 km hexagons that hold at least one dam-like dam.

| field | type | meaning |
|---|---|---|
| `cell_id` | string | the pipeline's `hex_id` (`h<q>_<r>`, pointy-top hexagons on EPSG:3577) |
| `lat`, `lon` | number, degrees | the cell centre |
| `corners` | array of 6 `[lat, lon]` pairs | the hexagon's corners, converted to WGS84 |
| `n_dams` | integer | dam-like dams in the cell |

**`seasons`**: one entry per rated season, oldest first. Past seasons are `kind: "past"`. The coming season, if included, is `kind: "live"` with every `ran_dry` set to `null`.

| field | type | meaning |
|---|---|---|
| `season` | string | `"2018-19"`: rated on 1 July 2018, judged October 2018 to March 2019 |
| `issue_date` | date | the rating date (1 July) |
| `kind` | `"past"` or `"live"` | |
| `rows[].cell_id` | string | |
| `rows[].rain_only_chance` | number, 0 to 1 | the RAIN baseline: rainfall-only chance from SILO 12- and 24-month deciles |
| `rows[].rating_chance` | number, 0 to 1 | the DamDays Rating: the product of the cell's dam-like dams' chances |
| `rows[].ran_dry` | boolean or null | `true` if every dam-like dam in the cell ran dry (D0) between October and March; `false` if not; `null` if unknown or not yet happened |

---

## scoreboard.json: the test scores

```json
{
  "source": "sealed",
  "source_label": "Sealed region, scored once on 3 Oct 2026",
  "rating": {
    "all_seasons": { "label": "All test seasons 2016-2025", "n_cells": 5000, "n_ran_dry": 400,
                     "rain_only_auc": { "value": 0.55, "ci_low": 0.52, "ci_high": 0.58 },
                     "rating_auc":    { "value": 0.81, "ci_low": 0.78, "ci_high": 0.84 } },
    "by_season": [ { "season": "2018-19", "n_cells": 500, "n_ran_dry": 80,
                     "rain_only_auc": { "value": 0.53, "ci_low": 0.46, "ci_high": 0.60 },
                     "rating_auc":    { "value": 0.79, "ci_low": 0.73, "ci_high": 0.85 } } ]
  },
  "runway": { "label": "R30, dam-like dams, October to March issues, 2016-2026",
              "skill_vs_usual_rate": { "value": 0.19, "ci_low": 0.17, "ci_high": 0.21 },
              "n_forecasts": 140000 }
}
```

| field | type | meaning |
|---|---|---|
| `source` | string | `"mock"`, `"dev_test"` (development regions, test block) or `"sealed"` (the sealed region, opened once) |
| `source_label` | string | shown next to the scoreboard, so nobody mistakes which test this is |
| `rating.all_seasons` | Score line + `label` | all past seasons pooled |
| `rating.by_season` | array of Score lines + `season` | one per past season in `cells.json` (same `season` text) |
| `runway` | object, optional | the farmer forecast's headline score, shown on the About page |
| `runway.skill_vs_usual_rate` | Range | Brier skill score against the base rate (B0) |
| `runway.n_forecasts` | integer | how many forecasts were scored |

A **Score line** is `{ "n_cells": int, "n_ran_dry": int, "rain_only_auc": Range or null, "rating_auc": Range or null }`.
A **Range** is `{ "value": number, "ci_low": number, "ci_high": number }`, where `ci_low` and `ci_high` are the 95% confidence range from the pipeline's bootstrap.

The app only shows an AUC when at least 5 cells ran dry that season (`minDryCellsForScore` in `js/settings.js`). It says "too few dry cells to score fairly" otherwise.
