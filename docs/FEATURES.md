# The features, in plain language

This page lists every number a DamDays model may learn from, and explains why each one is allowed. The code is in [`damdays/features/`](../damdays/features/). The exact list of model inputs, with a one-line comment per column, is `FEATURE_SPEC` in [`damdays/features/spec.py`](../damdays/features/spec.py).

One command rebuilds every table (after `scripts/01_build_data.py`):

```
.venv/Scripts/python.exe scripts/02_build_features.py
```

It takes about 5-8 minutes on a laptop and writes to `data_cache/features/` (not committed). A summary goes to [`artifacts/feature_checks.json`](../artifacts/feature_checks.json).

## 1. The one rule, and how we prove it

**A feature for a forecast issued on day D may only use information that existed on day D.**

- The satellite look on day D is the newest data point. Every rolling window ends there.
- Rain and neighbour features use data from strictly before D.
- Anything summarising the dam's whole history (its "full" level, its typical drawdown) is recomputed each year from looks before 1 January of that year (a **checkpoint**).
- The dam's own track record only counts past forecasts whose answer was final by D.

**The proof is a test you can rerun:** [`tests/test_no_lookahead.py`](../tests/test_no_lookahead.py). For each region it:

1. builds every table from all the data;
2. deletes every look on or after a cut date (NSW 9 Jul 2014, Vic/SA 9 Jul 2012), every rain month not finished by then, and re-derives the events from what is left;
3. rebuilds every table from the truncated data;
4. checks that every feature of every forecast issued before the cut is **bit-for-bit identical**.

It keeps the rows a weaker test would drop: the forecasts just before the cut, whose 90-day answer runs past it, including those whose label cannot be determined. It also checks that it *can* fail: the truncation must change some labels, and a deliberately planted peeking column (the next look's level) must be caught on the same real tables. Only the labels are exempt, because they describe the future by definition.

It compares every column of the P1 table, the P2 dam and cell tables, the yearly checkpoints and the neighbour grid. A new feature added to `build_all` is covered automatically; a generator built elsewhere (physics, sequences) is added with one line to `GENERATORS` in the test. Tidemark's per-dam frailty sums (the dam's matured past residuals) are rebuilt from each P1 table and compared too, and a planted frailty leak (past forecasts counted without the 120-day wait) must be caught. What was compared is saved in [`artifacts/lookahead_test.json`](../artifacts/lookahead_test.json). Run it with `.venv/Scripts/python.exe -m pytest tests/test_no_lookahead.py` (about 5 minutes).

## 2. Forecasts and their answers (P1, the farmer runway)

Every valid satellite look of a has_hist waterbody is a forecast ("issue"), from 1 Jan 1988 on (1986-87 is warm-up history). The table keeps every issue where the dam is **at risk**:

| flag | meaning |
|---|---|
| `at_risk_D0` | the dam has water now, so it can still go dry |
| `at_risk_R30` | the dam is at least 30% full now (PREREG static full), so it can still fall below a third |

The answers are **labels**. They describe the future and are never model inputs:

| label | meaning |
|---|---|
| `y_R30`, `y_D0` | an event of that kind starts in the next 90 days: in (D, D+90] |
| `y_D0g` | a *gradual* dry-out starts then (missing if only an abrupt one does, since those are often satellite artefacts) |
| `lab_tte_*` | days to the next event, for the runway curve |
| `label_ok` | the answer is knowable: at least 3 looks in the window, and the window ends inside the data |
| `window_closed` | only the second half of `label_ok`. Used for the sensitivity row that does not filter on future looks |

Rows with `label_ok` False are **kept** and flagged, not dropped. The pre-event audit found that dropping them is a selection on the future: dropped rows have much lower event rates.

## 3. The features, and why each is allowed

`rel` = how full the dam looks now compared with its own "full" level. In the features, "full" is always the **checkpoint** value `full_c`, never the PREREG static one (see section 4).

### The dam's own recent history (all windows end at today's look)

| feature | plain meaning | why it is allowed |
|---|---|---|
| `rel`, `pc` | level now (relative, and raw % wet) | today's look is known today |
| `last3` | average level of the last 3 looks | today's and earlier looks |
| `s60`, `s120` | trend: how fast the level changed over the last 60 / 120 days (least-squares slope) | window ends today |
| `rec` | rate of change since the highest level of the last 120 days | window ends today |
| `max365`, `min365` | highest / lowest level in the past year | window ends today |
| `since_full` | days since the dam was last at 90% of full | looks back only |
| `armed`, `since_arm` | was the dam at least 60% full in the last 180 days (the PREREG arming level), and days since | looks back only |
| `low365_K` | share of "low" looks in the past year (K = D0: no water; K = R30: below 30%) | window ends today |
| `since_low_K` | days since the last low look | looks back only |
| `dtt_trend_K` | days until the threshold if the dam keeps falling at its current trend (log scale) | uses `s60` and `rel` only |
| `gap_prev` | days since the previous look | looks back only |
| `month`, `sin_doy`, `cos_doy` | time of year | the calendar is known |

### What we knew about the dam on 1 January (checkpoints)

| feature | plain meaning | why it is allowed |
|---|---|---|
| `full_c` | the dam's own "full": 90th percentile of % wet over looks before 1 Jan of the issue year (needs 20 looks) | only looks before 1 Jan |
| `wet_share_c` | share of those looks that showed any water | same |
| `fill_share_c` | share of the Jul-Jun years seen so far in which the dam reached 90% of full | same |
| `clim_dd`, `clim_fast` | the dam's typical and fast drawdown rates for this half of the year | look pairs whose second look is before 1 Jan |
| `dtt_clim_K`, `dtt_fast_K` | days to the threshold at those rates | checkpoint rates and today's level |
| `anom_own` | today's level minus this dam's usual level for the calendar month | "usual" averages only **earlier years**, and at least 3 of them |

From 2016 on, every checkpoint is the fixed pre-2016 value, exactly as the PREREG says. The build script checks that `full_c` for 2016 equals the PREREG "full" (section 7).

### The dam's track record (`dam_rate_K`)

How often did this dam's past forecasts come true? For a forecast on day D we count the same dam's earlier forecasts in the same half of the year (Oct-Mar or Apr-Sep) that were at risk and had a knowable answer, **but only those whose answer was final by D**: their 90-day window plus 30 days to confirm an event had closed (issued at least 120 days before D). A forecast from 100 days ago still has an open window, so its answer is not used.

`dam_rate_K = (hits + 20 x regional rate) / (count + 20)`. With little history the rate stays near the regional rate; with a long history it becomes the dam's own.

**The regional rate** is one number per region and half-year (four in all), from the TRAIN-block forecasts whose answer was **final before validation starts**: issued before 2009 *and* at least 120 days before 1 January 2009 (the same purged rows a model fitted for validation may use, `splits.fit_mask(dates, "VAL")`). A forecast from 20 September 2008 is left out: its answer is only final on 18 January 2009, and a validation forecast on 2 January 2009 could not have known it. So for validation (2009-15), test (2016-26) and the sealed region the regional rate is fully in the past.

*Fixed during the event (LEAK-1):* the first build counted every TRAIN forecast issued before 2009, including those whose answer was only final between January and April 2009. That moved `dam_rate_*` on 22,156 validation forecasts from January-April 2009 by at most 0.004. The pre-event research had the same flaw.

**Disclosed:** for a TRAIN-block forecast the regional rate is an in-sample constant (it includes later TRAIN answers).

The raw counts behind it (`b2S_*`, `b2N_*`) grow as the archive grows, so the PREREG keeps them out of the P1 trees. They stay in the table for the B2 baseline.

### Neighbours (`R_anom`, `R_chg3`, `R_zero`)

Are the dams around this one falling too?

- Neighbours are the other has_hist waterbodies within 100 km, at most 300 (a fixed random sample seeded by the dam's id). **The dam is never its own neighbour.**
- On a fixed calendar grid (the 1st and 16th of every month), each neighbour's level is its **last look strictly before the grid date**, if that look is at most 30 days old.
- `R_anom`: median of the neighbours' levels compared with their own usual level for the month (earlier years only).
- `R_chg3`: median change in their level over 3 months.
- `R_zero`: share of neighbours that were fully dry.
- A forecast on day D uses the last grid date on or before D, and at least 5 neighbours with a value.

So every neighbour look used is strictly earlier than D and at most 30 days older than the grid date.

**Disclosed:** the pool of possible neighbours is the PREREG `has_hist` set, which is chosen from pre-2016 history. 89 of the 6,564 waterbodies are not in it: 71 showed water in fewer than 10% of their pre-2016 looks (so their pre-2016 "full" is 0), and 18 had fewer than 20 looks before 2016. For a pre-2016 forecast, `R_zero` (the share of dry neighbours) therefore leaves out a few mostly-dry waterbodies that an observer at the time could not yet know would stay mostly dry until 2015. Test and sealed-region forecasts are not affected: for them the pool is fixed from data in their past.

### Dam shape (static)

`log_n_pixels` (size), `pixel_compactness`, `elongation`: from the DEA outline. **Disclosed:** DEA drew the outlines from its multi-decade water record, which we cannot avoid. It applies equally to every period and to the sealed region.

### Rain (`rain_sum{w}`, `rain_pctc{w}`)

- The window always ends in **the month before the issue month**: the last month whose total was complete. A forecast on 9 July uses rain up to the end of June.
- `rain_sum{w}` is the rain over the w months to then (w = 1, 3, 6, 12, 24).
- `rain_pctc{w}` ranks that total against the same cell's totals for the same calendar months in **earlier years only**: 1960 up to the year before, and never after 2015. From 2016 on this is the PREREG 1960-2015 climatology. Before 2016, a fixed 1960-2015 baseline would peek at later years, so we do not build it at all.
- **Partial months are blanked.** A rain month that had not ended by the newest satellite look in the archive (14 September 2026) can only hold a partial, month-to-date total. September 2026 averages 11.8 mm over our cells, below the driest September of 1990-2025 (15.4 mm). Such a month is set to missing before anything is computed, so a live forecast in October gets a missing value, not a fake drought. No historical forecast used it. Planned for the app (not yet built): lag rain by one more month for forecasts issued on days 1-2 of a month, since SILO values settle over a few days.

Rain features are in the tables for baselines and the nets. They are not in the frozen P1 tree set (the pre-event ablation dropped them).

## 4. What a model never sees

| column | why not |
|---|---|
| the PREREG static `full`, `wet_share`, `fill_share`, `n_pre_obs` | computed from all pre-2016 looks: for a 1998 forecast they know 2015. They define *what is scored* (events, populations, at-risk flags), so they stay in `attributes.pkl`, but they are **not even present** in the feature tables. The causal `_c` versions are used instead. |
| columns computed from those statics: `at_risk_R30`, `elig_rescue_R30` (static full), `dam_like`, `persistent`, `dam_like_persistent` (pre-2016 wet share) | they choose *which* rows are scored, so they are in the tables, but as inputs they would carry the same pre-2016 knowledge |
| labels (`y_*`, `lab_tte_*`, `n_obs_win`, `label_ok`, `window_closed`) | they are the future |
| `n_hist_c`, `b2S_*`, `b2N_*` in P1 trees | grow with the archive (PREREG) |
| region names, ids and location: `region`, `uid`, `best_uid`, `hex_id`, `hex_q`, `hex_r`, `silo_cell`, `tile`, `lat`, `lon`, `fold5`, `sfold5` | PREREG: no region identifier is a model input |
| `state_day` (P2) | the absolute day number of the state look; the model uses its age (`age`) instead |

`spec.check_feature_list` raises an error if any of these appear in a model's input list. It runs on every spec when the module is imported. One column is allowed on purpose: the P2 cell column `n_dams` (how many dam-like dams the cell has). It counts a pre-2016 population, but that population *is* the question being asked: a cell fails when all of those dams go dry.

**Disclosed, inherent to the PREREG:** past events are defined with the static pre-2016 "full" (as the PREREG requires), so the track-record counts for pre-2016 forecasts inherit that normaliser. This does not affect TEST or the sealed region.

## 5. The season rating (P2)

One forecast per dam every **1 July** (1989-2026): will it go fully dry in the coming October-March?

- **State** comes from the dam's last look **strictly before 1 July**, and only if it is at most 60 days old. Otherwise the state is unknown (`state_stale`). The state features are the P1 features at that look, so they too stop there. `age` is how old that look is.
- **History**: the checkpoint for that year, neighbours at the 1 July grid date (their looks strictly before 1 July), rain to the end of June.
- **Track record over seasons**: `dam_rate_P2` (own past dry-season rate shrunk toward the region's TRAIN rate, k = 5), `b2N`, `lag1`, `lag2`, `rate5`, `rate_R30`, `lag1_R30`. A season's window ends 31 March and any event in it is confirmed by 30 April, so every **earlier** season is final by 1 July.
- **Nothing from the coming October-March is used.** The build asserts that no state look is on or after its 1 July issue date.

**Labels:** `y` = a dry-out (D0) starts between 1 October and 31 March; `y_g` = gradual version; `y_R30`. `label_ok` needs at least 3 looks in that window.

**Cells** (2 km hexagons, dam-like dams only): the cell fails (`y`) only if **all** its dam-like dams go dry (PREREG). The secondary label `y_best` is the most reliable dam's outcome, the one with the highest pre-2016 wet share. That pre-2016 choice only decides which label is reported, never a feature value. The cell probability is the product of its dams' probabilities, done in the model step.

**Rain baselines** use the same causal rule. `rain_decile12/24` come from the causal percentiles. `drought10` counts drought years among the last 10, using a threshold from earlier years only. The climatology (`clim_ann`, `clim_cv`, `clim_om`) comes from Jul-Jun years completed before 1 July.

## 6. Files in `data_cache/features/`

| file | one row per | content |
|---|---|---|
| `p1_keys.pkl` | at-risk issue | ids, time block, populations, at-risk flags, labels, B2 counts |
| `p1_dam.pkl` | same rows | dam-history features, checkpoints, `dam_rate_*`, shape |
| `p1_nbr.pkl` | same rows | `R_anom`, `R_chg3`, `R_zero` |
| `p1_rain.pkl` | same rows | `rain_sum*`, `rain_pctc*` |
| `p2_dam.pkl` | waterbody x 1 Jul | state, history, neighbours, rain, track record, labels |
| `p2_cell.pkl` | 2 km cell x 1 Jul | cell labels, cell aggregates, cell track record, folds |
| `checkpoints.pkl` | waterbody x year | the yearly checkpoints |
| `neighbour_grid.pkl` | (dict) | the semi-monthly grid arrays |

Load P1 with `damdays.features.store.load_p1(groups=("keys", "dam", "nbr", "rain"))`. Load P2 with `store.load_p2("dam")` or `store.load_p2("cell")`.

## 7. Checks against the pre-event research

The pre-event research built the same tables from the same raw files. The fresh event build must reproduce its counts exactly, and it does (`scripts/02_build_features.py` prints this comparison and exits with an error if a required check differs):

| check | expected | this build |
|---|---|---|
| P1 issues TRAIN (at risk, label determinable, 1988 to 2008) | 896,778 | 896,778 |
| P1 issues VAL (2009-2015) | 394,628 | 394,628 |
| P1 issues GAP (2016-01 to 2016-06) | 26,149 | 26,149 |
| P1 issues TEST (2016-07 to 2026-06) | 907,150 | 907,150 |
| primary R30 set TRAIN (dam-like, Oct-Mar, at risk, label determinable) | 145,417 | 145,417 |
| primary R30 set VAL | 66,453 | 66,453 |
| primary R30 set TEST | 142,938 | 142,938 |

Also matching exactly: the positives in those sets (R30 37,766 / 15,861 / 29,415), the D0 and D0g primary sets and their positives, the P2 dam-like dam-seasons (32,355 / 11,557 / 16,811, of which 5,788 / 2,069 / 2,924 went dry), the 1,435 cells, and the P2 cell-seasons (27,561 / 9,848 / 14,331, of which 4,668 / 1,684 / 2,316 failed). Every value is in [`artifacts/feature_checks.json`](../artifacts/feature_checks.json).

The table stores **2,585,626** at-risk issues in all. That includes the rows that fail `label_ok` (TRAIN 219,578, VAL 67,211, GAP 2,734, TEST 45,915) and the issues after June 2026 used for live forecasts. The share failing `label_ok` falls over time as satellites look more often: this is the observability filter the audit flagged, and the reason the sensitivity row exists.

The 2016 checkpoint `full_c` equals the PREREG "full" for every dam (largest difference 4e-6, float rounding).
