# PREREG: DamDays

Committed Fri 2 Oct 2026 09:00 AEST, before any event code exists. Never edited after commit. Changes are made only as dated addenda appended **before** the sealed region is opened.

## Project
DamDays: calibrated per-dam drought-runway forecasts for farm dams from 38 years of satellite water history, plus a season-ahead water-security rating that is tested against rainfall-only risk scores.
Forecasting engine: Tidemark (internal name).

## Data (all CC BY 4.0)
- DEA Waterbodies v3 (Geoscience Australia): per-waterbody wet-area time series, 1987 to Sep 2026.
- SILO monthly rainfall grids, 1960-2026 (Queensland Government).
- Development regions: NSW Central West (lat -33.5 to -30.5, lon 147.0 to 150.0) and western Vic / SE SA (lat -38.0 to -35.5, lon 140.5 to 143.5).
- **Sealed test region:** Southern Downs / Granite Belt / New England (lat -31.5 to -26.0, lon 150.5 to 152.6).
  - It holds 4,711 eligible waterbodies.
  - The files were downloaded before the event, hashed (SEALED_HASHES.csv, committed with this file) and never opened.
  - The SILO files also hold a sealed-region key, which is not loaded until the opening.
  - It is opened **once**, Sat 3 Oct 17:30 AEST, after the model is frozen (see "Sealed region protocol").
- Waterbody filter: area 5,400 to 100,000 m2 (at least 6 Landsat pixels).

## Populations (defined from pre-2016 observations only)
- **has_hist:** at least 20 valid pre-2016 observations and full > 0.
- **Dam-like:** wet in at least 50% of valid pre-2016 observations, pixel compactness of at least 0.7, PCA elongation of at most 3, and 6-55 Landsat pixels.
- **Persistent:** wet in at least 80% of valid pre-2016 observations (reported as a harder subset).

## Events
"Full" is the dam's own 90th-percentile wet % over pre-2016 observations. That static value is used for **labels only**; model features use a causal checkpoint version.
- **Arming:** the dam reached at least 60% of full within the previous 180 days. This applies to both D0 and R30.
- **D0, fully dry:** 0 wet pixels on 2 consecutive valid observations no more than 30 days apart, once armed.
- **R30, below a third:** below 30% of full on 2 consecutive valid observations, once armed.
- **Abrupt D0:** the last wet observation before the event had rel >= 0.4 and was no more than 60 days earlier.
- **D0-gradual:** D0 that is not abrupt.
- **Event start:** the first confirming observation. It counts toward an issue at date D if it falls in (D, D+90].
- **Label determinable:** at least 3 valid observations in the window, and D+90 on or before the panel end. A sensitivity row without this condition is always reported.
- R30 drives the farmer runway; D0 drives the finance rating.

## Forecasts
- **P1, farmer runway:** P(event within 90 days), issued at each valid observation. Primary scoring uses Oct-Mar issues.
- **P2, season rating:** issued every 1 Jul from 2016 to 2025. Label: D0 in the following Oct-Mar.
  - A dam's state is taken only from its last observation before 1 Jul, no more than 60 days old.
  - Cells are 2 km hexagons. A cell fails when **all** of its dam-like dams hit D0 (most cells hold one dam). Cell probability = the product of its dam-like dams' probabilities. The most-reliable-dam label is reported as a secondary.

## Model (fixed before the event; the sealed region has not been opened)
**Primary model: Tidemark v1.**
- The configuration was chosen on the 2009-2015 validation block of the development regions only, and frozen as research config fe0ab596d1fe (2 Oct 2026 06:42 AEST).
- It is re-implemented from raw data during the event. The event build's own config hash is filed in a dated addendum before the sealed region is opened.

**Components:**
- **P1, per event kind (R30, D0, D0-gradual):** the 90-day probability is the sigmoid of the equal-weight mean of three logits:
  - (T) LightGBM on the G2c features plus two water-balance features, trained on all waterbodies;
  - (S) a causal dilated TCN on the 24 complete months before the issue, fused with a tabular MLP;
  - (M) an MLP on 64 tabular inputs.
  - S and M are 3-seed averages.
  - A per-dam random intercept b = R/(V+100) is added. It comes from the dam's own past residuals whose windows have closed (t_j + 120 d <= t).
  - The R30 headline is max(p_R30, p_D0).
- **Runway curve (30-180 d):** a discrete-time hazard LightGBM on dam-like rows, with intervals 0-30-60-90-180 d and F(t) = 1 - prod(1 - h). The R30 curve is set to at least the D0 curve.
- **Runway floor ("DamDays"):** a LightGBM 10% quantile of days to R30, plus split conformal (90% target).
- **Season band:** region-year logit offsets from an inner backtest, pooling inner blocks 2002-2009 and 2009-2016. Pooling the second block is a TEST-informed change: the 2009-2016 block alone under-covered dry years on dev TEST. The single-block band's sealed coverage is reported alongside.
- **P2:** LightGBM boosted from the logit of the dam's own shrunk past-season failure rate (k = 5).
  - Settings: 150 trees, 7 leaves, min_child 200, dam-like seasons, 3 seeds, no rain features.
  - Cell p = product of its dam-like dams' p.
  - Gradual label: the same trees with the prior swapped to the gradual rate.
  - The regional feature block explored before the event is dropped. This is a TEST-informed simplification: it did not replicate on dev TEST.
- **General rules:**
  - No region identifier is a model input.
  - All models are pooled over both development regions.
  - Raw time-growing counts (n_hist, b2S, b2N) are not inputs to P1 trees.
  - The hyperparameters listed above are fixed.

**Benchmark model: G2.** LightGBM with the rescue features, using the causal dam rate: a past event counts only once its window has closed by the issue date. G2 is scored everywhere Tidemark is, and the paired difference is reported.

## Fallback ladder (decided mechanically by Sat 3 Oct 15:00 AEST)
The frozen model is the highest rung whose event re-implementation (a) reproduces its pre-event VAL BSS within +-0.006 on R30 and D0, and (b) passes the look-ahead test.
- **L3:** full Tidemark.
- **L2:** without the water-balance features.
- **L1:** tree + random intercept + hazard curve (no nets).
- **L0:** G2.
- **P2:** the offset model; fallback B2.

## Splits
- **TRAIN:** issues before 2009-01-01.
- **VAL:** 2009-2015, used for all selection.
- **GAP:** 2016-01 to 2016-06, unused.
- **TEST:** 2016-07 to 2026-06.
- **Purge:** a fit row's label window + 30 days must close before the cutoff.
- **Held-out dams:** 5-fold grouped by dam (fold5, sfold5) on the VAL block. This was not run before the event and is run at the event.
- **Leave-one-region-out** between the two development regions.
- The sealed region is never used for training or tuning.

## Baselines
- **B0:** base rate (month x region) from the fit block.
- **PERS:** level-persistence logistic regression.
- **B2:** the dam's own past event frequency, shrunk to a region x season prior (k = 20 for P1, k = 5 for P2).
- **RAIN (P2; defines the kill rule):** SILO 12- and 24-month rainfall deciles plus a drought-year count, in a logistic model. This is the rainfall-only score that DAS-style and NAB-style tools use.
- **RAIN+ (secondary):** the strongest rainfall-only model found before the event.
- **Sealed region:** every baseline and prior is fitted on the sealed region's **own** pre-2016-07 history.

## Metrics
- Brier skill score (BSS) against B0 and against B2.
- AUC.
- Calibration slope and calibration-in-the-large (CITL).
- Precision at 50% recall.
- Paired differences vs G2.
- Horizon-specific BSS for the runway curve.
- Band coverage and floor coverage.
- Within-season and within-cell AUC for P2.
- 95% CIs from a dam bootstrap and a region-year bootstrap.

## Pass bars (unchanged from the original draft)
- **P1:** for R30 on dam-like dams (Oct-Mar issues): BSS vs B0 >= +0.10 with the 95% CI above 0; BSS vs B2 >= +0.05; calibration slope between 0.8 and 1.2.
- **P2:** AUC improvement over RAIN >= 0.05 with the 95% CI above 0. The gain over B2 is also reported.
- **Kill rule:** if RAIN comes within 0.02 AUC of the rating, drop the finance claim and pitch the farmer runway alone.
- **Trap avoided:** "within the same rainfall decile" comparisons are not used as the headline, because they win by construction.

## Pre-event research status (disclosed)
- Before the event, research agents built a benchmark on the two development regions and compared nine model families plus Tidemark.
- Selection used VAL (2009-2015). The development test block (2016-07 to 2026-06) was scored once per family, about ten configurations in all, including Tidemark: R30 BSS vs B0 +0.233, against G2 +0.211.
- Tidemark's design was informed by those results, so its development test score is post-selection and optimistic by roughly 0.005-0.01.
- The sealed region's files were downloaded and hashed before the event and have never been opened, parsed or used.
- **The sealed region is the only clean test.**

## Sealed region protocol
- It is opened once, Sat 3 Oct 17:30 AEST, after the freeze addendum is committed and pushed. Every file hash is checked against SEALED_HASHES.csv first.
- Models are fitted on development-region issues before 2016-07-01. They score sealed issues from 2016-07-01 to 2026-06-30 (P2 seasons 2016-2025).
- Per-dam quantities that use a sealed dam's own past labels as of the issue date (B2, the dam rate, the random intercept, the P2 prior) are causal features, not training.
- Region-level priors and the baselines B0, B2, RAIN and RAIN+ use the sealed region's own history, in the same time blocks as for the development regions.
- The water-balance evaporation shape for the sealed region is typed in from public BoM climatology and hashed in the addendum before opening.
- G2 and Tidemark are each scored once. All numbers are published whatever they show. Nothing changes after opening except crash fixes that do not change predictions, each logged with its time.

## Pre-declared expectations for the sealed region (forecasts, not pass bars)
- R30 BSS vs B0: about +0.15 to +0.23 (central +0.19).
- R30 BSS vs B2: about +0.08 to +0.15.
- Calibration slope: 0.9 to 1.25. CITL within +-0.3.
- Tidemark minus G2: +0.01 to +0.03.
- P2 cell AUC gain over RAIN: +0.15 to +0.30.

## Reported regardless of outcome
- The persistent-dam subset (expected weaker).
- D0-gradual.
- The label-determinable sensitivity row.
- Grouped-dam CV.
- Leave-one-region-out results.
- Coverage (the DEA size floor).
- The runway-curve choice (the hazard model alone).
- TEST multiplicity.
- Failure cases.
- All numbers, including failures.
