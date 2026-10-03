# Real data

These six JSON files (format: `app/DATA_CONTRACT.md`) and their packed copy `bundle.js` are written by the exporter. To make them again, from the repo root:

    .venv/Scripts/python.exe scripts/11_export_app.py --rung L3 --season 2018 --refit-live

`farms.json` (the demo farms and this week's texts, for the app's My farm view) is written separately, by `scripts/16_weekly_texts.py` from these forecasts; `bundle.js` packs it too. After re-running step 16, run `app/tools/build_bundle.py app/data/real` again.

`proof.json` (the Proof view's three charts) is written by `.venv/Scripts/python.exe scripts/17_proof_data.py`, after steps 13, 15, 11 and 16 (about a minute; it rebuilds `bundle.js` itself).

`track_record.json` (each dam's track record: how often our days-left number held on it over the last 10 years (forecasts for July 2016 to June 2026, re-run with only data from before July 2016)) is written by `.venv/Scripts/python.exe scripts/18_track_record.py`, after step 17 (seconds; it rebuilds `bundle.js` itself).

`--refit-live` refits the production model (about 25 minutes at rung L3); without it the saved fit in `data_cache/preds/LIVE/tidemark/L3_live.pkl` is reused and the export takes under a minute. The exporter writes the JSON files, checks every contract rule (`damdays.export.app_data.contract_problems`), then runs `app/tools/build_bundle.py app/data/real`, which lists "real" first in `app/data/datasets.js`.

**After the sealed region is opened** (Sat 3 Oct 17:30 AEST, `scripts/20_open_sealed_region.py --open`), fill the "Sealed region" panel; nothing else changes and it takes seconds:

    .venv/Scripts/python.exe scripts/11_export_app.py --panel-only --sealed-scores artifacts/sealed/scorecard/sealed_TEST

It reads only three result files that the opening's scorecard writes there (`P1_R30/tidemark__dam_like+octmar+at_risk.json`, `P2_cell/tidemark__all.json`, `P2_cell/rain__all.json`) and refuses any file that is not block TEST, arena "sealed", so a development result can never be shown as the sealed one. Until then the panel says "Sealed region: opened Sat 3 Oct 17:30" and lists the pre-registered expectations.

Code: `scripts/11_export_app.py` (runs it all; the test-season and sealed-panel parts live here), `damdays/export/app_data.py` (the six files), `damdays/export/live_model.py` (the production fit), `damdays/export/albers.py` (hexagon corners to latitude/longitude). Nothing under `damdays/` was changed for this export, so the frozen config hash (7d466291008d) still describes the code; `meta.json` records the hash of the code that ran the export. Tests: `tests/test_app_export.py` (small made-up inputs) and `tests/test_app_export_real.py` (these published files against the raw data: a truncation test with a planted-leak control, hand checks on single dams, the live curve code reproducing the validated L3 curves, an independent recount of the live fit's training rows, and every scoreboard number against the file it is copied from).

## Where each number comes from

| view | what | made by |
|---|---|---|
| Runway | today's forecast for each farm-like dam of NSW Central West, from its latest clear look (28 Aug to 14 Sep 2026): 576 of 894 dams have a forecast | **Production fit of the frozen rung L3**: Tidemark refitted with the frozen recipe on every answer final by the last satellite look (cutoff 15 Sep 2026; nets trained at that cutoff, saved in `data_cache/nets/2026-09-15/`). The season band is the frozen pooled band (recomputed: identical constants) and the floor's conformal shift is 0. Never scored: these forecasts are about the future. |
| Rewind | forecasts on 1 Nov 2018, 1 Jan 2019 and 1 Mar 2019 (the 2018-19 drought), and what happened | The **frozen TEST-setting model** (fitted only on answers final before 1 Jul 2016), forecasts saved by `scripts/13_fit_test_setting.py` and scored once by `scripts/15_score_test.py`. The exporter refuses the file unless its fingerprint is the one step 13 recorded. Outcomes are the PREREG R30 labels. |
| Rating | each 2 km cell's rating (1 Jul 2018) and rainfall-only score, and which cells ran dry October 2018 to March 2019 | Same frozen model; the rainfall-only score is the RAIN baseline fitted for the TEST block (step 13). "Ran dry" is the PREREG cell label (every dam-like dam in the cell had a D0 event, October to March). |
| Scoreboard | "Development regions, 2016-2026, scored once" | Copied from `artifacts/test_results.json` (step 15's one look): runway skill, benchmark gain, rating AUC against rainfall-only, pass bars, floor and band coverage. The 2018-19 line (this region's cells only) is computed by the scorecard on the same frozen forecasts; the TEST ledger accepted it as `same_predictions` (two rows, 2 Oct 21:39), and a rerun reuses the saved result (`artifacts/scorecard/step11_app/dev_TEST/`) instead of asking the ledger again. |
| Scoreboard | "Sealed region: opened Sat 3 Oct 17:30" | A placeholder until `--panel-only --sealed-scores` (above). The Proof view's "Unseen exam" card shows the same panel. |
| My farm, dam cards | "Our record on this dam: held N of M times" (over the last 10 years), season by season, and each demo farm's dams added up | `track_record.json`, by `scripts/18_track_record.py` from the **frozen TEST-setting forecasts** (step 13's `tidemark/L3_p1.pkl`, fingerprint checked) and their PREREG R30 answers: the promise as the app shows it (whole days, "180+" judged at 180 days), judged only when the archive watched the dam for at least N days. Nothing is scored: over every dam of both regions the counts must equal `artifacts/test_results.json` (`floor.shown_all`: 730,449 judged, 0.90932 held, and every year), and the "likely" calls (5 in 10 or more) on the headline set must equal `proof.json`'s groups, or nothing is written. 941 dams (the 894 on the map and the 47 of the western Victoria demo farms); 929 have at least 5 judged forecasts. |
| Proof | what we said vs what happened; skill and the "at least N days" promise by July-June year; the demo farm's dams in 2018-19 | `proof.json`, by `scripts/17_proof_data.py` from the **frozen TEST-setting forecasts** (step 13's files, fingerprints checked) and their PREREG R30 answers, on the headline set step 15 scored (142,938 forecasts). Nothing is scored on the TEST ledger: the totals must equal `artifacts/test_results.json` or nothing is written, and the promise by year is copied from it. Skill by year and the groups' ranges are recomputed from the same forecasts (500 dam re-draws). Drier years: July-June SILO rain, the two regions' ratios to their 1960-2016 average averaged, below 1 (2017-18 to 2019-20 and 2023-24 to 2025-26; in 2023-24 and 2024-25 only western Victoria / SE South Australia was drier than usual, in 2025-26 only NSW Central West). The farm part must agree with Rewind on 1 Nov 2018. |

The 2018-19 season was chosen by hand (`--season 2018`) as the drought season to rewind. It is not the season with the most falls below a third among these dams (2017-18 has 662 R30 starts, 2018-19 has 437, `meta.json` lists every season): by 1 Nov 2018, 561 of the 894 dams were already below a third, so fewer were left to fall.

## What the 2018-19 season shows (honest reading)

- Rewind, forecasts against what happened: 1 Nov 2018, 76 of 258 dams fell below a third, the forecasts added up to 95 (too high); 1 Jan 2019, 106 of 288 against 97; 1 Mar 2019, 62 of 236 against 57.
- Rating, this region's 766 cells: rating AUC 0.81 (0.77 to 0.85) against 0.48 (0.42 to 0.54) for rainfall alone; 99 cells ran dry. The rating ranked the cells well, but its chances were too high on average that season (mean 0.20 against 0.13 that ran dry; CITL -0.64). The region-year range is a single point here (one region, one season), so only the cell range is shown.

## How the curve and the headline agree

The 90-day headline (fused members + per-dam correction + max rule) and the runway curve (the hazard model H) are two models, so H's own 90-day value differs a little. The exporter draws the curve as H's 30, 60 and 180-day values with the headline at 90 days; where H's 30 or 60-day value is above the headline it is lowered to it, and where its 180-day value is below the headline it is raised to it. The curve therefore passes through the headline and never falls. This moved a point on 17 of 576 live curves, and on 7, 7 and 76 of the 259, 289 and 237 Rewind curves (1 Mar 2019 is late in the season, when H's curve and the headline disagree most; `meta.json` has the counts). The shaded band is the season band applied to each point, so its 90-day point equals `chance_low` / `chance_high`.

## Statuses

From each dam's last clear look on or before the issue date: no look in the last 60 days, `no_recent_look`; below a third of full (or dry), `already_low`; not refilled to 60% of full in the last 180 days, or fallen below a third since its last refill (the PREREG arming rule), `not_refilled`; otherwise `forecast`. Levels use the PREREG static "full" (display only; the models use the causal checkpoint full).

## Validation seasons

Before the one-time TEST scoring the app showed a validation season (2009-10 to 2014-15) from the VAL-setting model, with validation scores. That still works: `--rung L1 --season 2013` (the default `--season auto` picks the validation season with the most falls below a third).

## Size

The JSON files total about 3.7 MB; `history.json` is most of it (894 dams x 465 months of levels, plus every event start). `bundle.js` is a copy of all six (3.7 MB on disk, about 0.55 MB as a web server sends it gzipped).
