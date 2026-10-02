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
    farms.json         optional: the demo farms and this week's texts, for My farm (scripts/16)
    bundle.js          the six files (and farms.json) packed into one script (made by build_bundle.py)
```

To publish a dataset:

1. Write the six JSON files into `app/data/real/`.
2. Run `python app/tools/build_bundle.py app/data/real`. This checks that each file has its main fields, writes `bundle.js`, and lists `real` first in `datasets.js`, so the app uses it from then on.

Why `bundle.js`: when you double-click `index.html`, browsers refuse to read other local files with `fetch()`, but they do run `<script>` files. The bundle is a copy of the JSON wrapped in one script. Never edit it by hand.

To look at the mock data even when real data exists, add `?data=mock` to the address.

## Rules for every file

- **Dates** are `"YYYY-MM-DD"` in local Australian dates (UTC+10, the same as the pipeline). **Months** are `"YYYY-MM"`.
- **Chances** are numbers from 0 to 1, rounded to 3 decimals. The app writes them as "N in 10" (0.58 is "6 in 10"; under 0.05, "less than 1 in 10"), never as a percent: farmers read "%" as how full a dam is.
- **Water levels** are whole-number percentages of the dam's usual full wet area (see `level_pct` below).
- **Missing** values are `null`. Never `NaN` or an empty string.
- **Coordinates** are WGS84 degrees, rounded to 5 decimals.
- `dam_id` and `cell_id` are the keys that join the files. Keep them stable between exports.

**Honesty rules** (these matter more than the format):

- Past forecasts (Rewind) and past seasons (Rating) must be **out of sample**: made by models fitted only on data from before the forecast date (the 2016-2026 TEST predictions of the frozen model, after the one-time TEST scoring; before it, the 2009-2015 predictions of the model fitted before 2009, labelled as validation). Never in-sample fits.
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
| `coverage`, `limits`, `live`, `rewind` | optional | | written by the real exporter for people reading the file (which dams, plain-language limits, how the live and Rewind forecasts were made); the app does not read them |

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
| `source` | string | `"mock"`, `"dev_val"` (development regions, validation block 2009-2015), `"dev_test"` (development regions, test block) or `"sealed"` (the sealed region, opened once) |
| `source_label` | string | shown next to the scoreboard, so nobody mistakes which test this is |
| `note` | string, optional | which years the model learned from and was scored on; the About page shows it in place of its default sentence (which describes the one-time test) |
| `rating.all_seasons` | Score line + `label` | all past seasons pooled |
| `rating.by_season` | array of Score lines + `season` | one per past season in `cells.json` (same `season` text) |
| `runway` | object, optional | the farmer forecast's headline score, shown on the About page |
| `runway.skill_vs_usual_rate` | Range | Brier skill score against the base rate (B0) |
| `runway.n_forecasts` | integer | how many forecasts were scored |
| `panels` | array, optional | one panel per one-time test, shown side by side on the About page; the Rating scoreboard adds the sealed panel's line (see below) |

A **Score line** is `{ "n_cells": int, "n_ran_dry": int, "rain_only_auc": Range or null, "rating_auc": Range or null }`.
A **Range** is `{ "value": number, "ci_low": number, "ci_high": number }`, where `ci_low` and `ci_high` are the 95% confidence range from the pipeline's bootstrap.

The app only shows an AUC when at least 5 cells ran dry that season (`minDryCellsForScore` in `js/settings.js`). It says "too few dry cells to score fairly" otherwise.

### `panels`: the one-time tests (written for a test-season export)

```json
"panels": [
  { "key": "dev_test", "status": "scored", "title": "Development regions, 2016-2026, scored once",
    "label": "NSW Central West and ...; scored once on 2 Oct 2026", "scored_at": "2026-10-02 20:38:10",
    "runway": { "n_forecasts": 140000, "n_dams": 1600, "skill_vs_usual_rate": Range, "skill_vs_own_record": Range,
                "gain_vs_benchmark": Range, "auc": Range, "calibration_slope": Range, "pass_bars_met": true },
    "rating": { "n_cells": 14000, "n_ran_dry": 2300, "rating_auc": Range, "rain_only_auc": Range,
                "gain_vs_rain": Range, "pass_bar_met": true, "kill_rule_triggered": false },
    "floor": { "held": 0.90, "target": 0.9, "worst_year": { "year": 2023, "coverage": 0.87 } },
    "band": { "covered": 20, "region_years": 20 } },
  { "key": "sealed", "status": "pending", "title": "Sealed region: opened Sat 3 Oct 17:30",
    "label": "Southern Downs, Granite Belt and New England", "text": "...",
    "expectations": [ { "what": "Runway skill vs the usual rate (R30 BSS vs B0)", "low": 0.15, "high": 0.23,
                        "field": "runway.skill_vs_usual_rate" } ] }
]
```

| field | meaning |
|---|---|
| `key` | `"dev_test"` (development regions, test years) or `"sealed"` (the sealed region) |
| `status` | `"scored"` (numbers below are filled) or `"pending"` (not opened yet: only `title`, `label`, `text`, `expectations`) |
| `runway` | R30 on the primary set (farm-like dams, October-March forecasts): skill against the usual rate (B0) and the dam's own record (B2), the paired gain over the benchmark G2, AUC, calibration slope, and the pre-registered pass bars (`null` if not checked) |
| `rating` | the 2 km cell rating: its AUC, the rainfall-only AUC, the paired AUC gain, the pre-registered bar (gain at least 0.05 with its range above 0) and the kill rule (rainfall-only within 0.02) |
| `floor`, `band` | optional: DamDays floor coverage and season-band coverage |
| `expectations` | optional: the PREREG pre-declared expectations; `field` names the panel number each is compared with once scored |

Every number in a panel is copied from a scorecard result file (`dev_test`: `artifacts/test_results.json`; `sealed`: the files `scripts/20` writes to `artifacts/sealed/scorecard/sealed_TEST/` at the opening).

---

## farms.json (optional): demo farms and their weekly texts

Not one of the six files above: optional. It is written by `scripts/16_weekly_texts.py` (the weekly text, [`notify/MESSAGE_SPEC.md`](../notify/MESSAGE_SPEC.md)), and `build_bundle.py` packs it into `bundle.js` (as `farms`) when the folder has it. The app's **My farm** view reads it: the demo farms in its picker, their texts, and `date`, the day the text is sent, from which the app counts days of water (My farm, and the live dam card). Without it, My farm starts on an empty map and counts days from the latest satellite look. For a farm with `dams_in_app: false`, My farm uses the farm's own `dams[]` (its radius cannot grow past `radius_km`).

```json
{
  "schema_version": "1.0", "generated_at": "2026-10-02T12:30:00Z", "date": "2026-10-02", "radius_km": 3.0,
  "about": "...", "source": "...",
  "farms": [ { "farm_id": "farm-d", "name": "Farm D (near Dubbo)", "lat": -32.22, "lon": 148.635, "radius_km": 3.0,
               "region": "nsw_cw", "region_name": "NSW Central West", "near_town": "Dubbo", "town_km": 4.7,
               "dams_in_app": true, "data_through": "2026-09-14",
               "dams": [ { "number": 1, "name": "Dam 1", "dam_id": "nsw_cw-0407", "dea_uid": "r638...",
                           "distance_km": 0.94, "lat": -32.21365, "lon": 148.64156, "area_ha": 1.17,
                           "status": "already_low", "issued_on": "2026-09-13", "window_end": "2026-12-12",
                           "level_pct": 0, "chance": null, "damdays_days": null,
                           "text_kind": "low", "days_left": null } ],
               "sms": "Fri 2 Oct (satellite 13 Sep)\n...", "sms_septets": 146, "long": "..." } ]
}
```

| field | meaning |
|---|---|
| `date` | the day the texts are for |
| `farms[].lat`, `lon`, `radius_km` | the homestead point and the radius; a farm's dams are every dam within the radius (there are no property boundaries) |
| `farms[].dams_in_app` | `true` if the farm's dams are in this dataset's `forecasts.json` (the app shows one region; demo farms cover both development regions) |
| `farms[].dams[]` | the farm's dams, closest first: `number` (Dam 1 = closest), the stable `dam_id`, and the dam's live row copied from the forecasts (same fields and units as `forecasts.json`) |
| `dams[].text_kind` | what the text says about the dam on `date`: `"forecast"`, `"low"`, `"not_refilled"` or `"no_look"` (no clear look in the 60 days before `date`) |
| `dams[].days_left` | forecast dams only: the DamDays floor counted from `date` (`damdays_days` minus the days since `issued_on`); 180 or more is shown "6 months+" |
| `farms[].sms` | the weekly SMS: GSM-7 only, 160 places or fewer, lines separated by `\n` |
| `farms[].long` | the longer app/email version (2 to 4 lines) |

In every farmer-facing text, "%" means only how full a dam is, and a chance is written "6 in 10", never as a percent.
