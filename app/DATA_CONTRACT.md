# Data contract: the files the app reads

The app has no server. It shows whatever is in six small JSON files. This page says exactly what each file must contain, so the pipeline (Python) and the app (JavaScript) can be built separately and still fit together.

All numbers in the examples on this page are made up, only to show the format.

## Where the files go

```
app/data/
  datasets.js          list of datasets, preferred first ("real" before "mock"), and which are split into parts
  mock/                made-up data for building the app (make_mock_data.py)
  real/                real forecasts, written by the pipeline's exporter
    meta.json          what this dataset is
    forecasts.json     each dam's forecast, today and on past dates
    curves.json        each dam's runway curve (30, 60, 90, 180 days)
    history.json       each dam's monthly water level since 1988
    cells.json         2 km cells: rainfall-only score, DamDays Rating, what happened
    scoreboard.json    test scores (AUC with ranges)
    farms.json         optional: the demo farms and this week's texts, for My farm (scripts/16)
    proof.json         optional: what accuracy looks like, for the Proof view (scripts/17)
    track_record.json  optional: each dam's track record over the last 10 years (scripts/18)
    bundle.js          the six files (and the optional ones there) packed into one script (made by build_bundle.py)
    parts.js           the same data split into parts, and their file names (made by build_bundle.py)
    <part>.<hash>.js   first, farms, core, rewind, rating, history-00 to -11 (made by build_bundle.py)
```

To publish a dataset:

1. Write the six JSON files into `app/data/real/`.
2. Run `python app/tools/build_bundle.py app/data/real`. This checks that each file has its main fields, writes `bundle.js` and the parts, lists `real` first in `datasets.js`, so the app uses it from then on, and re-stamps `app/sw-version.js`.

Why `bundle.js`: when you double-click `index.html`, browsers refuse to read other local files with `fetch()`, but they do run `<script>` files. The bundle is a copy of the JSON wrapped in one script. Never edit it by hand.

**Data parts** (`parts.js` and `<part>.<hash>.js`, written by `build_bundle.py`'s `write_parts()`; UI_SPEC 8.2): the same JSON again, split by how soon the app needs it, so a phone on a slow connection downloads about 28 KB (compressed) of data before this week's text shows, not the whole 0.65 MB `bundle.js`. `first` holds `meta`, `scoreboard`, `farms`, `proof` and, for the demo farms' dams only, their `forecasts.json` entries, today's rows and curves and their track records (plus every other field of `track_record.json`); `farms` the demo farms' dams' water history; `core` every other dam (entries, today's rows and curves, track records) and which `history-NN` part holds its history; `rewind` the past forecast dates and their curves; `rating` the cells; `history-00` to `history-11` the other dams' history, grouped by map area. Like `bundle.js` they are copies (the JSON files stay the source of truth), each a `<script>` that adds itself to `self.DAMDAYS_PART_DATA["<dataset>/<part>"]`, so a double-clicked `index.html` still works. The hash in each name is of its content: a new export writes new names and deletes the old files, and the service worker keeps a part for good. `js/data.js` merges them into the same object `bundle.js` gives (`DamDays.data.need("first")`, `need("core")`, `history(damId)`, and `load()` for everything but the history shards); a dataset without `parts.js` (e.g. `mock`) loads its `bundle.js`.

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
| `floor`, `band` | optional: DamDays floor coverage and season-band coverage. `floor`: `held` (share of "at least N days" floors that held), `target` (0.9), `ci_low`/`ci_high`, `n_forecasts`, `worst_year`. The scored sealed panel also carries `tolerance` (0.02, `damdays/evaluation/coverage.py` FLOOR_TOLERANCE) and `on_target`, the opening's own flag (`abs(held - target) <= tolerance`, computed on the unrounded share; copied from `sealed_results.json` `floor.issued_all`, never recomputed). The app (`format.floorCheck`) follows `on_target` when present; otherwise it applies the same rule in floats with proof.json's `by_year.floor_tolerance` |
| `expectations` | optional: the PREREG pre-declared expectations; `field` names the panel number each is compared with once scored |

Every number in a panel is copied from a scorecard result file (`dev_test`: `artifacts/test_results.json`; `sealed`: the files `scripts/20` writes to `artifacts/sealed/scorecard/sealed_TEST/` at the opening).

---

## farms.json (optional): demo farms and their weekly texts

Not one of the six files above: optional. It is written by `scripts/16_weekly_texts.py` (the weekly text, [`notify/MESSAGE_SPEC.md`](../notify/MESSAGE_SPEC.md)), and `build_bundle.py` packs it into `bundle.js` (as `farms`) when the folder has it. The app's **My farm** view reads it: the demo farms in its picker, their texts, and `date`, the day the text is sent, from which the app counts days of water (My farm, and the live dam card). Without it, My farm starts on an empty map and counts days from the latest satellite look. For a farm with `dams_in_app: false`, My farm uses the farm's own `dams[]` (its radius cannot grow past `radius_km`).

```json
{
  "schema_version": "1.0", "generated_at": "2026-10-02T12:30:00Z", "date": "2026-10-02", "radius_km": 3.0,
  "about": "...", "source": "...",
  "farms": [ { "farm_id": "farm-e", "name": "Farm E (near Mudgee)", "lat": -32.526, "lon": 149.609, "radius_km": 3.0,
               "region": "nsw_cw", "region_name": "NSW Central West", "near_town": "Mudgee", "town_km": 7.3,
               "dams_in_app": true, "data_through": "2026-09-14",
               "dams": [ { "number": 1, "name": "Dam 1", "dam_id": "nsw_cw-0659", "dea_uid": "r64q...",
                           "distance_km": 0.47, "lat": -32.52548, "lon": 149.60403, "area_ha": 0.63,
                           "status": "forecast", "issued_on": "2026-09-13", "window_end": "2026-12-12",
                           "level_pct": 80, "chance": 0.089, "damdays_days": 87,
                           "text_kind": "forecast", "days_left": 68 } ],
               "sms": "Fri 2 Oct (dams seen 13 Sep)\n...", "sms_septets": 159, "long": "..." } ],
  "set_aside": [ { "farm_id": "farm-d", "name": "Farm D (near Dubbo)", "region": "nsw_cw", "reason": "Set aside: ..." } ]
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
| `set_aside[]` | demo farms found the same way but left out, with the `reason` (e.g. aerial photos show its waterbodies are not farm dams); the app may name them in its limits, never in a picker |

In every farmer-facing text, "%" means only how full a dam is, and a chance is written "6 in 10", never as a percent.

## proof.json (optional): what accuracy looks like, for the Proof view

Not one of the six files above: optional. It is written by `scripts/17_proof_data.py` from the frozen model's **test** forecasts and their answers (July 2016 to June 2026, already scored once by `scripts/15`; nothing is scored again), and `build_bundle.py` packs it into `bundle.js` (as `proof`) when the folder has it. The app's **Proof** view (`#proof`) draws its three charts from it. Without it, Proof shows only the unseen-exam card (from `scoreboard.json`'s sealed panel) and says the charts need this file. Every sentence with a number in it (`takeaway`, `detail`, `summary`, ...) is written by the script from the numbers; the view types none.

```json
{
  "schema_version": "1.0", "generated_at": "2026-10-03T10:30:00+10:00", "made_by": "scripts/17_proof_data.py",
  "test": { "label": "...", "scored_at": "2026-10-02 20:36", "intro": "...", "caveat": "...",
            "forecasts": 142938, "fell": 29415, "dams": 1644,
            "skill_vs_usual_rate": { "value": 0.23501, "ci_low": 0.2235, "ci_high": 0.2483, "words": "nearly a quarter" },
            "calibration_slope": 1.09455, "model": "..." },
  "unseen_exam": { "panel_key": "sealed", "heading_pending": "Unseen exam: opens Sun 4 Oct 2026 (AEDT)",
                   "heading_scored": "...", "expect": "...", "text": "..." },
  "calibration": { "title": "...", "takeaway": "...", "detail": "...", "lean": "...", "not_plotted": "...",
                   "how_to_read": "...", "min_forecasts_to_plot": 100,
                   "bins": [ { "in_ten": 3, "said": "3 in 10", "forecasts": 17013, "fell": 4864, "share_fell": 0.2859,
                               "share_fell_ci": [0.27285, 0.29752], "mean_chance": 0.29638, "happened_in_ten": 3,
                               "plotted": true } ] },
  "by_year": { "title": "...", "takeaway": "...", "floor_takeaway": "...", "floor_detail": "...", "skill_note": "...",
               "drier_rule": "...", "refit_note": "...", "floor_note": "...",
               "drier_runs": [ { "first": 2017, "last": 2019, "label": "2017-20" } ],
               "all_years": { "skill": 0.23501, "skill_ci": [0.2235, 0.2483], "skill_words": "nearly a quarter",
                              "floor_held": 0.90016, "floor_judged": 729749, "floor_worst": { "year": 2023, "coverage": 0.87199 } },
               "floor_target": 0.9, "floor_tolerance": 0.02,
               "years": [ { "year": 2023, "label": "2023-24", "words": "July 2023 to June 2024", "forecasts": 14329,
                            "fell": 2392, "dams": 1510, "share_fell": 0.16693, "mean_chance": 0.17602, "usual_rate": 0.2357,
                            "skill": 0.2148, "skill_ci": [0.18561, 0.24439], "skill_words": "a fifth",
                            "rain_vs_usual": { "nsw_cw": 1.041, "wvic_sesa": 0.71 }, "rain_vs_usual_mean": 0.876,
                            "drier": true, "floor": { "held": 0.87199, "held_in_1000": 872, "judged": 81580 } } ] },
  "dam_by_dam": { "title": "...", "takeaway": "...", "farm": { "farm_id": "farm-e", "name": "Farm E (near Mudgee)", "...": "..." },
                  "rewind_date": "2018-11-01",
                  "season": { "forecasts_from": "2018-07-01", "forecasts_to": "2019-06-30", "show_to": "2019-09-30" },
                  "rewind_dates": [ { "date": "2018-11-01", "forecasts": 3, "chance_sum": 0.368, "fell": ["Dam 1"], "unknown": [] } ],
                  "all_dates_takeaway": "...",
                  "threshold_pct": 30, "default_dam": "nsw_cw-0659", "how_chosen": "...", "how_to_read": "...",
                  "dams": [ { "dam_id": "nsw_cw-0659", "name": "Dam 1", "area_ha": 0.63, "dea_uid": "r64q...",
                              "rewind": { "status": "forecast", "issued_on": "2018-10-26", "level_pct": 120, "chance": 0.145,
                                          "said": "1 in 10", "outcome": true, "outcome_date": "2018-12-20" },
                              "looks": [ ["2018-07-13", 60] ],
                              "forecasts": [ { "date": "2018-10-26", "chance": 0.145, "fell": true, "fell_on": "2018-12-20" } ],
                              "falls": ["2018-12-20"], "summary": "..." } ] },
  "sources": { "...": "..." }, "checks": { "equal_to_test_results": [ { "what": "...", "value": 142938 } ], "ledger": "..." }
}
```

| field | meaning |
|---|---|
| `test` | the set every chart is drawn from: R30 within 90 days, farm-like dams, forecasts made October to March, at risk, with a known answer (the headline set of `artifacts/test_results.json`). `forecasts`, `fell`, `dams`, `skill_vs_usual_rate` and `calibration_slope` equal the test results (the script refuses to write otherwise) |
| `calibration.bins[]` | one group per chance as the text rounds it (`in_ten` 0 = "less than 1 in 10", 10 = "more than 9 in 10"): how many forecasts, how many fell below a third within 90 days, the share that fell (`share_fell_ci`: 95% range from re-drawing whole dams 500 times), the average chance given. A group with fewer than `min_forecasts_to_plot` forecasts is listed (`plotted: false`), not drawn |
| `by_year.years[]` | one July-June year each (`year` 2016 = July 2016 to June 2017): `skill` is the Brier skill score against the usual rate B0 on that year's forecasts (`skill_ci`: re-drawing that year's dams 500 times); `floor` is how often "at least N days" held that year, copied from `test_results.json` (`floor.issued_all.by_year`: all judged forecasts, all months); `drier` is the rain rule in `drier_rule` (July-June SILO rain, averaged over the two regions' ratios to their 1960-2016 average, below 1) |
| `dam_by_dam.dams[]` | the demo farm's dams (Dam 1 = closest to the homestead): `looks` are `[date, level_pct]` at each clear satellite look (level as in `forecasts.json`, % of the dam's usual full level), `forecasts` every test forecast made for the dam between `season.forecasts_from` and `season.forecasts_to` (`fell`: the R30 answer, `null` if not known), `falls` the days it fell below a third, `rewind` its row in `forecasts.json` on `rewind_date` (the script checks they agree) |
| `dam_by_dam.rewind_dates[]`, `all_dates_takeaway` | the same farm on every Rewind date in `forecasts.json`: how many forecasts, the sum of their chances (the falls expected), which dams fell below a third within 90 days (`unknown`: no answer yet); and one sentence over all the dates |

"%" appears only as how full a dam is; a chance is "N in 10"; how often something held is "N in 1,000".

---

## track_record.json (optional): each dam's track record, so a farmer can judge our accuracy

Written by `scripts/18_track_record.py` (seconds, after steps 13, 15, 11, 16 and 17; it rebuilds `bundle.js` itself, and also writes the same numbers as a page, `artifacts/track_record.md`). The dam sheet (for today's forecast, in My farm and Runway) and My farm's rows show it: "Our record on this dam: held 18 of 20 times" (over the last 10 years). Without it, the cards and the table leave it out. The weekly text's long version can carry it too (`notify.message.long_text(..., track_record=doc["dams"])`); the SMS never does.

The backtest is the ten test years: the frozen model learned only from data before July 2016 and made a forecast at every clear satellite look from July 2016 to June 2026 (scripts/13), scored once by scripts/15. This file only counts those saved forecasts dam by dam. Added up over every dam of both development regions, the counts must equal `artifacts/test_results.json` (`floor.shown_all`: forecasts judged, share held, by year), and the "likely" calls on the headline set must equal `proof.json`'s groups, or the script writes nothing.

```json
{
  "schema_version": "1.0", "generated_at": "2026-10-03T10:30:00+10:00", "made_by": "scripts/18_track_record.py",
  "years": "2016-2026", "label": "the last 10 years", "first_season": "2016-17", "last_season": "2025-26",
  "first_season_year": 2016, "last_season_year": 2025, "min_judged": 5, "cap_days": 180, "likely_in_ten": 5,
  "tip": "We re-ran our forecasts for July 2016 to June 2026 using only data from before July 2016, ...",
  "about": "...", "caveat": "...", "how": ["..."],
  "dams": { "nsw_cw-0659": { "dea_uid": "r64q...", "region": "nsw_cw", "forecasts": 429, "judged": 428, "held": 380,
                             "not_judged": 1, "enough": true, "by_season": { "2016": [37, 37], "2025": [32, 48] },
                             "median_days": 105, "likely_said": 4, "likely_fell": 0 } },
  "farms": [ { "farm_id": "farm-e", "name": "Farm E (near Mudgee)", "region": "nsw_cw", "radius_km": 3.0, "dams": 5,
               "dams_with_record": 5, "held": 1640, "judged": 1767, "not_enough_history": [],
               "lowest": { "name": "Dam 4", "dam_id": "nsw_cw-0660", "held": 212, "judged": 246 }, "seasons": [2016] } ],
  "summary": { "dams_in_app": 941, "distribution": { "dams_with_record": 929, "median_in_1000": 912, "...": "..." } },
  "checks": { "equal_to_test_results": [ { "what": "forecasts judged", "value": 730449, "test_results": 730449 } ],
              "equal_to_proof": [ "..." ], "ledger": "nothing scored on the TEST ledger" },
  "sources": { "...": "..." }
}
```

| field | meaning |
|---|---|
| `dams` | one record per dam the app shows (every dam of `forecasts.json`, and the demo farms' dams in `farms.json` outside the map's region), keyed by `dam_id` |
| `forecasts` | the dam's at-risk R30 forecasts of the backtest with a known answer (one per clear satellite look while it was above a third and had refilled) |
| `judged`, `held`, `not_judged` | the promise "at least N days above a third", N as the app and the text show it (whole days; "180+" judged at 180 days). JUDGED when the archive watched the dam for at least N days, whatever happened (`not_judged`: too recent). HELD when the dam stayed above a third for at least N days |
| `enough` | `judged >= min_judged` (5). Below that the app shows "not enough history" |
| `by_season` | `{"2016": [held, judged], ...}`, July-June years (2016 = July 2016 to June 2017), only the years with a judged forecast: the seasons covered |
| `median_days` | the typical promise (judged forecasts, whole days rounded down; 180 = "180+"), or `null` |
| `likely_said`, `likely_fell` | forecasts that gave a chance of 5 in 10 or more (rounded as the text rounds it) with a known 90-day answer, and how many were followed by a fall below a third within those 90 days |
| `farms[]` | one roll-up per demo farm of `farms.json`: its dams with enough history added up (`held`, `judged`), the others named in `not_enough_history`, and the dam with the lowest share held (the closest one on a tie) |
| `summary` | `dams_in_app`, the spread of the share held over dams with enough history (`distribution`: median, quartiles and counts below 9 in 10, 8 in 10, ...), and the app dams' totals |

A record is a count ("held 18 of 20 times"), never a percent: "%" means only how full a dam is.

