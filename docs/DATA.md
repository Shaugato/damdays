# The data, in plain language

This page explains what data DamDays uses, how it is cleaned, which waterbodies count as farm dams, and what a "dry-out event" is. The code for all of it is in [`damdays/data/`](../damdays/data/). One command rebuilds everything:

```
.venv/Scripts/python.exe scripts/01_build_data.py
```

It takes about one minute on a laptop. It writes to `data_cache/`, which is not committed and can be rebuilt at any time. A short summary goes to [`artifacts/data_checks.json`](../artifacts/data_checks.json).

## 1. Where the data comes from

| Source | What it is | Used for |
|---|---|---|
| **DEA Waterbodies v3** (Geoscience Australia, CC BY 4.0) | Every waterbody in Australia, mapped from Landsat. For each one, a history of how much of it was wet on every clear satellite pass since 1986. | Water history, events, dam shape |
| **DEA Waterbodies polygons** (same source) | The outline of each waterbody. | Area, shape, location |
| **SILO** (Queensland Government, CC BY 4.0) | Monthly rainfall on a 0.05-degree grid (about 5 km), 1960 to Sep 2026. | Rainfall for each dam |

We use two **development regions**: NSW Central West and western Victoria / south-east South Australia. We keep only waterbodies of 5,400 to 100,000 m2, which is 6 to 111 Landsat pixels. Smaller ones are too small to see reliably, and larger ones are not farm dams. That leaves **6,564 waterbodies**.

A third region (Southern Downs / Granite Belt / New England) is **sealed**. Its files were downloaded and fingerprinted before the event but are never read. See section 8.

## 2. From raw files to one clean table (the "panel")

Each waterbody has a CSV with one row per satellite look:

| column | meaning |
|---|---|
| `date` | time of the satellite pass, in UTC |
| `pc_wet` | percent of the outline that was wet |
| `px_wet` | number of wet 30 m pixels |

Cleaning (in [`panel.py`](../damdays/data/panel.py)):

1. **Drop invalid looks.** When cloud or shadow hides too much of a waterbody, DEA leaves `pc_wet` and `px_wet` empty. 4,270,645 of the 9,508,688 raw rows are like this and are dropped.
2. **Drop impossible values** (percent outside 0-100, negative pixels). This is a safety net only; there were none.
3. **Use the local date.** Landsat passes over eastern Australia at about 10 am local time, which is around midnight UTC. So one pass can fall on two UTC dates. We add 10 hours and keep the local calendar date.
4. **Merge same-day scenes.** If two scenes land on the same local date, we average them. This happened on 10,454 days.

Result: **5,227,589 valid looks**, from 18 Aug 1986 to 14 Sep 2026.

## 3. Describing each waterbody, and which ones are "farm dams"

[`attributes.py`](../damdays/data/attributes.py) builds one row per waterbody.

**Size and shape** (from the polygon outline):
- **Pixel count**: area / 900 m2.
- **Pixel compactness**: the shortest outline any blob of the same number of 30 m pixels could have, divided by the real outline. 1 means as compact as possible. Long or ragged shapes score low.
- **PCA elongation**: take the outline's corner points, then compare the spread along the longest direction with the spread across it: sqrt(largest variance / smallest variance). A square is about 1; a long channel is large.

**History before 2016** (from the panel). Only looks before 1 Jan 2016 are used, so these values are fixed before the test years start:
- **wet share**: the share of looks with at least one wet pixel.
- **full**: the dam's own 90th-percentile `pc_wet`. A dam that never fills its whole outline (common) still has a sensible "full" level. Everything else is measured against it: **rel = pc_wet / full**.

**The three populations** (as pre-registered in [PREREG.md](../PREREG.md)):

| population | rule | why | nsw_cw | wvic_sesa | total |
|---|---|---|---|---|---|
| **has_hist** | at least 20 valid looks before 2016, and full > 0 | enough history to judge the dam | 3,091 | 3,384 | **6,475** |
| **dam-like** | has_hist, wet in at least 50% of pre-2016 looks, compactness >= 0.7, elongation <= 3, 6-55 pixels | removes creeks, swamps, channels and lakes; what is left behaves like a farm dam | 894 | 789 | **1,683** |
| **persistent** | has_hist, wet in at least 80% of pre-2016 looks | dams that almost never dry out; a harder subset | 624 | 345 | **969** |

545 waterbodies are both dam-like and persistent.

## 4. Dry-out events: what we forecast

Code: [`events.py`](../damdays/data/events.py). Tests: [`tests/test_events.py`](../tests/test_events.py).

There are two kinds of event:

- **D0, fully dry**: no wet pixels on **2 consecutive looks at most 30 days apart**.
- **R30, below a third**: rel < 0.30 on **2 consecutive looks at most 30 days apart**.

Two looks are needed because a single dry-looking pass is often a satellite glitch.

**Arming.** An event only counts if the dam was recently full enough: it showed **rel >= 0.60 at some look within the 180 days** before the first low look. After an event, the dam must refill to 60% (re-arm) before the next event of the same kind can count. Without this rule, one long drought would be counted as dozens of events. D0 and R30 are armed separately.

**Event date.** The event "starts" on the first of the two confirming looks.

**Abrupt and gradual D0.** Water does not evaporate from 40% full to bone dry in a few weeks. So a D0 is called **abrupt** when the last look with water before it still showed **rel >= 0.40, at most 60 days earlier**. Such events are often artefacts (muddy water, shadow) rather than real dry-outs. **D0-gradual (D0g)** is every D0 that is not abrupt. It is the cleanest "the dam really dried up" signal. 36% of D0 events on dam-like dams are abrupt.

### Worked example (made-up numbers)

A dam whose "full" is 50% wet, seen every two weeks:

| day | 0 | 14 | 28 | 42 | 56 | 70 |
|---|---|---|---|---|---|---|
| pc_wet | 40 | 20 | 10 | 0 | 0 | 35 |
| rel | 0.8 | 0.4 | 0.2 | 0.0 | 0.0 | 0.7 |

- Day 0 **arms** the dam (0.8 >= 0.6).
- **R30**: days 28 and 42 are both below 0.3 and 14 days apart, and the dam was armed 28 days earlier. So an R30 event starts on **day 28**.
- **D0**: days 42 and 56 both have zero wet pixels, so a D0 event starts on **day 42**. The last look with water was day 28 at rel 0.2, which is below 0.4, so the event is **gradual** (D0g).
- Day 70 (rel 0.7) re-arms both kinds for the next dry spell.

The first test in `tests/test_events.py` checks exactly this example.

### A real example

Dam `r638mm01c_v3`, NSW Central West, 19 pixels, full = 84.2% wet. Spring 2019, during the 2017-2019 drought:

| local date | pc_wet | px_wet | rel | what happens |
|---|---|---|---|---|
| 2019-10-12 | 52.6 | 10 | 0.62 | armed (>= 0.6) |
| 2019-10-20 | 31.6 | 6 | 0.38 | |
| 2019-11-05 | 26.3 | 5 | 0.31 | |
| 2019-11-13 | 15.8 | 3 | 0.19 | **R30 starts** (below 0.3) ... |
| 2019-11-21 | 21.0 | 4 | 0.25 | ... confirmed 8 days later |
| 2019-12-07 | 10.5 | 2 | 0.13 | last look with water |
| 2019-12-15 | 0 | 0 | 0 | **D0 starts** ... |
| 2019-12-31 | 0 | 0 | 0 | ... confirmed 16 days later |

The last wet look (7 Dec) was at rel 0.13, below 0.4, so this D0 is **gradual**: the dam really drained over two months.

### How many events there are

Counted by the start date's time block (section 7):

| population | kind | events | dams | TRAIN | VAL | TEST |
|---|---|---|---|---|---|---|
| has_hist | D0 | 95,444 | 6,112 | 49,685 | 17,676 | 27,197 |
| has_hist | D0g | 55,731 | 5,887 | 29,937 | 10,322 | 14,960 |
| has_hist | R30 | 135,482 | 6,444 | 70,018 | 25,264 | 38,840 |
| dam-like | D0 | **15,949** | 1,506 | 8,413 | 3,071 | 4,255 |
| dam-like | D0g | **10,213** | 1,396 | 5,457 | 2,020 | 2,583 |
| dam-like | R30 | **31,344** | 1,670 | 16,311 | 6,047 | 8,587 |
| persistent | D0 | 4,092 | 745 | 2,217 | 738 | 1,062 |
| persistent | D0g | 2,649 | 622 | 1,397 | 489 | 705 |
| persistent | R30 | 16,045 | 952 | 8,710 | 2,990 | 4,065 |

Note: "full" for events uses the fixed pre-2016 value, as the PREREG says. That is fine for **defining** events. Model **features** must never use it, because for years before 2016 it contains information from later years. The feature code uses a version of "full" that only looks backwards in time.

## 5. Rainfall

[`rainfall.py`](../damdays/data/rainfall.py) reads one SILO file per year and takes only the development-region arrays from it. Each waterbody gets its **nearest SILO grid cell**. If that cell had any missing month, the nearest cell with complete data would be used instead, but this was never needed. The farthest any dam sits from its cell centre is 3.6 km. 2,499 grid cells are used, each with a monthly series from Jan 1960 to Sep 2026 (801 months).

## 6. 2 km hexagon cells

The season rating for lenders is given per 2 km hexagon ([`cells.py`](../damdays/data/cells.py)):

- Each dam's polygon centre is taken in **GDA94 Australian Albers (EPSG:3577)**, a map projection in metres.
- The map is tiled with **pointy-top regular hexagons** starting at the projection's origin.
- Each hexagon is **2 km across, flat side to flat side**. This is also the distance between neighbouring centres. Its area is 3.46 km2.
- Cells are numbered with standard axial coordinates (q, r) and named `h<q>_<r>`.

1,435 cells hold at least one dam-like dam: 1,256 hold one, 142 hold two and 37 hold three to eight.

## 7. Time blocks and folds

[`splits.py`](../damdays/data/splits.py) sets the time blocks. Each forecast belongs to the block of the date it is issued:

| block | issue dates | use |
|---|---|---|
| TRAIN | before 2009-01-01 | models learn here |
| VAL | 2009-01-01 to 2015-12-31 | every design choice is made here |
| GAP | 2016-01-01 to 2016-06-30 | unused buffer |
| TEST | 2016-07-01 to 2026-06-30 | scored once per model |

**Purge.** A forecast's answer is only known 90 days later, plus up to 30 days to confirm an event. A row may be used for fitting only if those 120 days close before the block being scored starts.

**Folds** for held-out-dam checks use fixed seeds (config `RANDOM_SEED` = 2026):
- `fold5`: every dam is shuffled into one of 5 folds.
- `sfold5`: 0.5-degree map tiles are shuffled into 5 folds. Neighbouring dams share weather, so this is the stricter "unseen area" check.

## 8. The sealed region stays sealed

[`guard.py`](../damdays/data/guard.py) has one job. Every loader passes its file paths through `check_path`, which raises an error for anything inside the sealed folder. The SILO files also contain a sealed-region array; [`rainfall.py`](../damdays/data/rainfall.py) refuses to read it. Both locks open only when the environment variable `DAMDAYS_OPEN_SEALED` is set to `yes`, which happens once, at the scheduled opening (Sat 3 Oct 17:30 AEST).

## 9. Files in `data_cache/`

| file | one row per | key columns |
|---|---|---|
| `panel.pkl` | waterbody x local day | `uid`, `region`, `date`, `pc_wet`, `px_wet`, `n_scenes` |
| `panel_qc.csv` | waterbody | `n_raw`, `n_invalid`, `n_out_of_range`, `n_kept`, `n_days_with_merged_scenes`, `first_date`, `last_date` |
| `attributes.pkl` / `.csv` | waterbody | `uid`, `region`, `lat`, `lon`, `area_m2`, `perimeter_m`, `n_pixels`, `n_parts`, `pixel_compactness`, `elongation`, `x_albers`, `y_albers`, `n_pre_obs`, `wet_share`, `full`, `has_hist`, `dam_like`, `persistent`, `dam_like_persistent`, `hex_id`, `hex_q`, `hex_r`, `hex_dist_m`, `silo_cell`, `silo_lat`, `silo_lon`, `silo_dist_km`, `fold5`, `tile`, `sfold5` |
| `events.pkl` / `.csv` | event | `uid`, `region`, `kind` (D0 or R30), `start_date`, `confirm_date`, `arm_date`, `rel_at_start`, `abrupt` (D0 only), `gradual` (True = D0g), `last_wet_date`, `last_wet_rel`, `hydro_year` (July-June year), `dam_like`, `persistent` |
| `silo_rain.pkl` | (dict) | `rain` (cells x months, mm), `months` (YYYYMM), `cells` (ids matching `attributes.silo_cell`), `cell_lat`, `cell_lon` |
| `download_check.json` | - | manifest files present and missing |

Load them with `pandas.read_pickle`. Each `.pkl` is a pandas table except `silo_rain.pkl`, which is a plain dict; read it with `pickle.load`.

## 10. Checks against the pre-event research

The pre-event research produced these counts from the same raw files. The fresh event build must match them exactly. It does:

| check | expected | this build |
|---|---|---|
| valid looks | 5,227,589 | 5,227,589 |
| has_hist waterbodies | 6,475 | 6,475 |
| dam-like waterbodies | 1,683 | 1,683 |
| persistent waterbodies | 969 | 969 |
| dam-like D0 events | 15,949 | 15,949 |
| dam-like R30 events | 31,344 | 31,344 |
| dam-like D0g events | 10,213 | 10,213 |

The full event table in section 4, the 1,435 hex cells and the 2,499 SILO cells also match the research notes exactly. The build script prints this comparison and exits with an error if anything differs.

Tests: `.venv/Scripts/python.exe -m pytest tests`. These use tiny made-up series to prove the arming, confirmation and abrupt/gradual rules, plus checks of the guard, dates, shapes, hex cells and splits.
