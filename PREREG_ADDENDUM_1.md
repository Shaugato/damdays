# PREREG Addendum 1: the freeze

**Committed: 2026-10-02 20:21 AEST**, before the sealed region is opened (Sat 3 Oct 2026 17:30 AEST).

PREREG.md is not edited. This addendum is the dated freeze step that PREREG.md requires ("Fallback ladder", "Model", "Sealed region protocol"). The frozen code is the code in the commit that adds this file.

## 1. Ladder decision: rung L3 (full Tidemark)

**The rule** (PREREG "Fallback ladder"): the frozen model is the highest rung whose event re-implementation (a) reproduces its pre-event VAL BSS within +-0.006 on R30 and D0, and (b) passes the look-ahead test.

**The evidence:** [`artifacts/ladder_val.md`](artifacts/ladder_val.md), written by `scripts/12_ladder_val.py` on 2 Oct 2026 18:01 AEST. Every rung is fitted on answers final before 2009-01-01 and scored on VAL only (2009-2015, development regions). The score is BSS vs B0 on the primary set; for R30 it is the shipped forecast, after the max rule.

| rung | R30: event / pre-event / difference | D0: event / pre-event / difference | (a) | (b) | passes both |
|---|---|---|---|---|---|
| L0 (G2) | +0.1700 / +0.1707 / -0.0007 | +0.1754 / +0.1755 / -0.0001 | PASS | PASS | yes |
| L1 | +0.1714 / +0.1727 / -0.0013 | +0.1770 / +0.1771 / -0.0001 | PASS | PASS | yes |
| L2 | +0.1800 / +0.1809 / -0.0009 | +0.1918 / +0.1923 / -0.0005 | PASS | PASS | yes |
| L3 (full Tidemark) | +0.1803 / +0.1818 / -0.0015 | +0.1940 / +0.1948 / -0.0008 | PASS | PASS | yes |

- (b) is read from [`artifacts/lookahead_test.json`](artifacts/lookahead_test.json) (`tests/test_no_lookahead.py`, run 2 Oct 2026 16:45 AEST): core features and frailty sums, the nets' sequences and the water balance, each in both regions, 0 mismatching values.
- All four rungs pass both conditions (the largest difference is 0.0015). **The frozen rung is L3**, the highest one. The rule was applied mechanically: the decision uses only that table and the rule, and no setting was changed in response to it.
- Two pre-event values are not exactly like for like, as the table's notes say: L1's twin had no R30 max rule (see 6.2), and L2's value is derived (L3's score minus the measured cost of removing the water-balance columns).
- P2 stays on the offset model: its VAL cell AUC is 0.7872 against 0.7873 before the event, within +-0.006, so the B2 fallback is not used.

## 2. Event build config hash

**`7d466291008d`** (SHA-256 `7d466291008dccce8c06568a150b4f9a1196c5fd0ce92f98986d1676bd98ace3`)

- Made by `scripts/14_config_hash.py` (it reads no data). It hashes:
  - every `damdays/**/*.py` file (56 files, `config.py` and the opening runner's `damdays/sealed/` included, no tests), with line endings read as LF;
  - the frozen constants as sorted JSON: rung L3 and its members and seeds, every LightGBM setting and input list, the nets' settings and inputs, the frailty lambda, the floor and band settings, the season-rating settings, and the physics constants.
- Source hash `f76dc32b108ec58a5dac504335ef0394b8555f2384406ca16ddbac74eb6e4ac1`; constants hash `c3465161e4f36fa7722b4344f3bfb3301a41d16a3c602a69dcdf47e965aa23c9`. Every file hash and every constant is in [`artifacts/config_hash.json`](artifacts/config_hash.json). Check without Python: the source hash is `sha256sum` of the sorted list of lines `<sha256sum of the file with CR removed>  <path>`, and the config hash is `sha256sum` of the two lines `source <source hash>` and `constants <constants hash>`.
- The pre-event research config was `fe0ab596d1fe`. The two hashes differ because the event code was written fresh; the ladder table above is the check that it reproduces the research model.
- The scripts under `scripts/` (including step 13, which fitted the models in section 5, and the opening runner `scripts/20_open_sealed_region.py`) are not in this hash; they are fixed by the commit that adds this addendum. At the opening, the runner recomputes this hash for the code it runs and prints whether this addendum quotes it.

## 3. Sealed-region evaporation shape (typed before opening)

The water balance needs each region's seasonal evaporation shape. For the sealed region it was typed in from public Bureau of Meteorology climatology, not from any sealed file: `EVAPORATION_MM_PER_DAY["sealed_sdowns_newengland"]` in `damdays/models/physics.py`.

- Source: BoM "Climate statistics for Australian locations", row "Mean daily evaporation (mm)", station GLEN INNES AG RESEARCH STN, 056013 (29.70 S, 151.69 E), 44 years 1971-2025, page read 2 Oct 2026.
- Values, mm per day, January to December: **5.4, 4.8, 4.1, 3.0, 2.0, 1.5, 1.7, 2.5, 3.6, 4.5, 5.1, 5.4**.
- The model uses only the shape (values divided by their mean): 1.486, 1.321, 1.128, 0.826, 0.551, 0.413, 0.468, 0.688, 0.991, 1.239, 1.404, 1.486.
- Hashed text: `sealed_sdowns_newengland:5.4,4.8,4.1,3.0,2.0,1.5,1.7,2.5,3.6,4.5,5.1,5.4`
- SHA-256: **`f886f4190d19b044fadb8b08aa0fbe854efa1342abba191316dd10e65096af36`** (check: `printf '%s' '<hashed text>' | sha256sum`).

## 4. Season band constants

The season band around a forecast p is [sigmoid(logit p + low), sigmoid(logit p + high)]. It never changes p. For dev TEST and the sealed region, the frozen L3 uses the pooled band of two inner backtests of its own recipe (PREREG "Model"):

- 2002-2009: fitted on answers final before 2002-01-01; offsets from forecasts issued from 2002-01-01 and answered before 2009-01-01 (14 region-years);
- 2009-2016: fitted on answers final before 2009-01-01; offsets from forecasts issued from 2009-01-01 and answered before 2016-07-01 (16 region-years).

No TEST forecast is used. Computed on 2 Oct 2026 with `tidemark.fit_band(tidemark.load_inputs(), tidemark.RUNGS["L3"], tidemark.SETTINGS["TEST"])`, the same call that `fit_tidemark("2016-07-01", "L3")` makes, so that fit must report these values.

| kind | frozen band: low, high (log-odds) | 2009-2016 block alone (its sealed coverage is reported alongside, PREREG) |
|---|---|---|
| R30 | -1.9600336770207685, +0.7558027436270113 | -1.9600, +0.2738 |
| D0 | -1.8492265708329862, +0.5375721229800186 | -1.8492, +0.2595 |
| D0g | -2.1466287004386064, +0.6366773578433538 | -2.1466, +0.3134 |

Every low end comes from NSW Central West in July 2011-June 2012 (a very wet La Nina year). The high ends come from the 2002-2009 block (NSW Central West 2003-04 for R30 and D0, 2006-07 for D0g); that block alone gives the VAL band in [`artifacts/val_tidemark_best.md`](artifacts/val_tidemark_best.md).

## 5. The frozen models the sealed region is forecast with

The sealed region is forecast with the TEST-setting models fitted by `scripts/13_fit_test_setting.py` (finished 2 Oct 2026 18:57 AEST), on the two development regions only, from answers final before 2016-07-01. Nothing is fitted on sealed data: every per-dam quantity (B2, the dam rate, the frailty, the P2 prior) is a causal feature of the dam's own past; the regional rates they shrink toward come from the sealed region's own history in the same time blocks as for the development regions (the dam rate: answers final before 2009-01-01; the P2 prior: seasons answered before 2016-07-01); and the baselines B0, B2, PERS, RAIN and RAIN+ are fitted on the sealed region's own history before 2016-07-01. Their fingerprints are in [`artifacts/sealed_models_manifest.json`](artifacts/sealed_models_manifest.json), committed with this addendum; the opening (`scripts/20_open_sealed_region.py --open`) refuses to forecast with any file whose SHA-256 differs.

| file | what | SHA-256 |
|---|---|---|
| `data_cache/models/TEST/tidemark_L3.pkl` | Tidemark rung L3: trees, 3 + 3 nets (with their input scaling), runway curve, floor, the band above, season rating | `cc86a5753dde2e38e4bce8eb8e251fe6aa2ce9d452bfcdc43743f66f6344cc41` |
| `data_cache/models/TEST/g2.pkl` | G2, the benchmark (R30, D0, D0g) | `e6a64fca6d0292fa0d1cd9a201b2bc20360c1009c297333fba41bec9c2598285` |
| `data_cache/features/physics_params.pkl` | the water balance, one pooled set per yearly checkpoint 1993-2016 (look pairs before 1 Jan of each year) | `62a5d21dec91c3e6132662ef561eb95e14586f040a26eb0f99780d5e09600263` |

## 6. Deviations and disclosures found during the event

Each is also described where it lives (file in brackets). None changes the pass bars or the expectations.

1. **LEAK-1, fixed.** The regional rate inside the `dam_rate_*` input first counted TRAIN forecasts from Sep-Dec 2008 whose answers were only final in Jan-Apr 2009: a small look-ahead for the 22,156 VAL forecasts issued Jan-Apr 2009. Now only answers final before 2009-01-01 count. The fix moves `dam_rate_*` by at most 0.004. The pre-event research had the same flaw. [docs/FEATURES.md; tests/test_leakage_rebuilds.py]
2. **The R30 max rule costs a little at L1.** The pre-registered rule max(p_R30, p_D0) costs -0.0006 BSS [-0.0009, -0.0002] at L1 on VAL: it raises 1.3% of primary forecasts in years (wet 2010-12) that were already over-predicted. It is kept as pre-registered. L1's pre-event value comes from a model without the rule, so L1's R30 check is not exactly like for like (difference -0.0013, inside +-0.006). [artifacts/tree_frailty_val.md; artifacts/ladder_val.md]
3. **D0-gradual edge case.** PREREG defines D0-gradual as a D0 that is not abrupt, but does not say how to label a 90-day window that holds only an abrupt D0. As in the pre-event research, that label is missing, not 0: the row is left out of D0g fitting (the tree and the nets' D0g head), of the D0g frailty track record and of D0g scoring. The P2 gradual label follows the same rule. Counts match the research exactly (D0g primary VAL: 83,747 rows, 6,989 events). [damdays/features/issues.py; artifacts/val_tidemark_L2.md]
4. **Water balance (physics).** Parameters are refitted every year (checkpoints 1993-2016; the research used 1993, 1998, 2002, 2009 and 2016), on development-region look pairs only. Sealed-region dams are run with those parameters and never change them. Forecasts before 1993 are blank (the research used the 1993 fit for them, a small look-ahead on TRAIN rows). The filter starts at each dam's first 1993 look. The development regions' evaporation shapes are typed from BoM stations (Trangie 051049, Longerenong 079028) instead of the research's rough proxy. All forecasts share one fixed set of 20 noise paths. Fit-pair counts match the research exactly. [damdays/models/physics.py; artifacts/val_physics.md]
5. **Causal rain baseline for RAIN and RAIN+.** Every rain percentile, decile and drought-year count compares a total with the same calendar month in earlier years only (from 1960, never after 2015). The nets' `rain_pctc*` inputs were already causal before the event. The change is in the P2 baselines: the research's RAIN (and the inputs of RAIN+) used the fixed 1960-2015 climatology, which looks ahead for pre-2016 ratings. The two are identical from 2016 on, so dev TEST and the sealed region are unaffected. On VAL the P2 gain over RAIN comes out about +0.003 larger (+0.2493 against +0.2464). [damdays/features/rain.py; artifacts/val_results.md; artifacts/season_rating_val.md]
6. **Fold seeds.** The held-out-dam folds use seed 2026 (`fold5`, by dam) and 2027 (`sfold5`, by 0.5-degree tile); the research used seeds 1 and 2, so fold membership differs. Grouped-dam CV was never run before the event, so no pre-event number depends on it. Fold numbers are never model inputs. Grouped-dam CV and leave-one-region-out (VAL only) have not been run yet; both are reported whatever they show. [damdays/data/splits.py; docs/DATA.md]
7. **`n_hist_c` is a net input.** The nets' tabular block includes the history length `n_hist_c` (log-scaled), as the frozen pre-event nets did. PREREG keeps raw time-growing counts out of the P1 trees only; the trees (T, H) do not use it. [damdays/models/nets.py; artifacts/val_tidemark_L2.md]
8. **"64 tabular inputs".** The nets read 43 causal columns, each standardised on the fit rows, plus a "was missing" flag for every column missing in more than 0.1% of the fit rows. With the VAL fit rows that is 64 inputs. The rule is fixed; the number of flags is set by the fit rows of each cutoff. [damdays/models/nets.py]
9. **Baselines are purged.** B0 and the B2 prior use only fit rows whose answer was final before the cutoff (the research used all TRAIN rows, 2.6% of them unpurged); the horizon baselines B0_h and B2_h wait max(h + 30, 90) days. This moves skill scores by at most 0.0004, the same for every model. [artifacts/val_results.md; artifacts/hazard_curve_val.md]
10. **Floor calibration rows.** For dev TEST and the sealed region, the DamDays floor's conformal shift uses only the 267,279 VAL forecasts whose 365-day answer (+30 days) was final before 2016-07-01; the research used all 304,611. Both give a shift of 0.0 log days (rechecked with the TEST setting, `tidemark.fit_floor`), so the frozen floor is the raw 10% quantile. [artifacts/uncertainty_val.md]
11. **Inherited from the PREREG statics (pre-2016 rows only).** Labels and populations use the static pre-2016 "full" (as PREREG requires); the neighbour pool and the P2 area index use the pre-2016 `has_hist` set; and for TRAIN rows the `dam_rate_*` regional rate is an in-sample constant. These look ahead only for pre-2016 rows; for dev TEST and sealed forecasts the same quantities are entirely in the past. [docs/FEATURES.md; artifacts/season_rating_val.md]
12. **Runway curve training rows.** The hazard model keeps an Oct-Nov 2008 issue for its early intervals only if `label_ok` holds, and `label_ok` can count looks up to 30 days after the cutoff. It decides only whether the issue is used, never a label or an input; the pre-event model did the same. [damdays/models/hazard.py; artifacts/hazard_curve_val.md]
13. **The P2 area index is kept.** The P2 inputs include a dam-based area index (share of waterbodies within 10 and 25 km that went dry last season and over earlier seasons), part of the pre-event "HSN" set. It is not the regional dam-state block (reg_zero, reg_anom, reg_pct) that PREREG drops. [damdays/models/season_rating.py; artifacts/season_rating_val.md]
14. **One ladder integration difference.** L2's per-dam correction differs from the forecasts step 9 saved on 156 VAL rows of one dam (largest difference 1.7e-4), because the correction also reads that dam's pre-2009 forecasts, which step 9 did not save. Every member agrees on every row. The ladder scores use the ladder's own run. [artifacts/ladder_val.md]
15. **Data products.** DEA drew its waterbody outlines from its multi-decade record, and SILO values are final revised values, not what was known in real time. This cannot be fixed in code and applies equally to every period and to the sealed region. [docs/FEATURES.md]
16. **The rehearsal of the opening looked at western Victoria's test years (TEST multiplicity).** The dry run of the opening runner (`--dry-run`, 2 Oct 2026 19:04-19:44 AEST) forecast and scored `wvic_sesa`'s 2016-07 to 2026-06 issues with models fitted on `nsw_cw` only (a region-transfer rehearsal: R30 BSS vs B0 +0.201 on the primary set). These are development TEST-block labels, scored with models other than the frozen ones, on a separate dry-run ledger ([`artifacts/sealed_dryrun/dryrun_ledger.csv`](artifacts/sealed_dryrun/dryrun_ledger.csv): 26 first looks, one per model and task, then 100 rows with identical forecasts from the reruns that tested the crash-resume path). They are counted here as TEST looks. Nothing was chosen or changed because of them: they ran after the ladder decision and after every setting above was fixed. Results: [`artifacts/sealed_dryrun/DRY_RUN_RESULTS.md`](artifacts/sealed_dryrun/DRY_RUN_RESULTS.md). [docs/SEALED_OPENING.md]
17. **The sealed manifest was not hashed.** SEALED_HASHES.csv lists the 4,711 time-series files. The sealed `manifest.csv` (each waterbody's uid, area, latitude and longitude, taken from the public DEA polygon file; no water data) was written by the same download but not hashed. The opening therefore requires it to list exactly the 4,711 verified files, inside the sealed box, before any time series is read. [damdays/sealed/region.py]

Not new at the event, but not stated in PREREG.md: during the pre-event component selection, the research re-specified its keep-rule noise floor (from 2 x the full model's seed SD to 2 x the seed SD of each paired cost) after seeing the ablation numbers, on VAL only and before any TEST look. Under the literal rule only the nets would have been kept, and that configuration scored 0.004 lower on VAL. This is a forking path in the design of Tidemark v1. [pre-event spec, section B; outside this repository]

## 7. Pre-declared expectations for the sealed region (restated unchanged from PREREG)

Forecasts, not pass bars:

- R30 BSS vs B0: about +0.15 to +0.23 (central +0.19).
- R30 BSS vs B2: about +0.08 to +0.15.
- Calibration slope: 0.9 to 1.25. CITL within +-0.3.
- Tidemark minus G2: +0.01 to +0.03.
- P2 cell AUC gain over RAIN: +0.15 to +0.30.

The pass bars in PREREG.md are unchanged.

## 8. What has not happened yet

- **The frozen models have NOT been scored on the development TEST block (2016-07 to 2026-06).** The TEST ledger, [`artifacts/test_ledger.csv`](artifacts/test_ledger.csv), has no entries. The only event-build look at TEST-block labels is the rehearsal in 6.16 (western Victoria, models fitted on NSW Central West only, separate dry-run ledger). (Before the event, about ten research configurations scored the development TEST block once each; PREREG "Pre-event research status".)
- **The sealed region has NOT been opened.** The event build has not read, parsed or listed any sealed file or loaded the sealed SILO key: `damdays/data/guard.py` refuses every path in the sealed folder and `damdays/data/rainfall.py` refuses the key until `DAMDAYS_OPEN_SEALED=yes` is set at the opening. Everything the build knows about the sealed region comes from PREREG.md, public sources (section 3) and the committed [`SEALED_HASHES.csv`](SEALED_HASHES.csv). It is opened once, Sat 3 Oct 2026 17:30 AEST, after this addendum is committed and pushed, with every file hash checked against SEALED_HASHES.csv first.
