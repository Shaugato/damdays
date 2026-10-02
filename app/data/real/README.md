# Real data

These six JSON files (format: `app/DATA_CONTRACT.md`) and their packed copy `bundle.js` are written by the exporter. To make them again, from the repo root:

    .venv/Scripts/python.exe scripts/11_export_app.py

It writes the JSON files, checks every contract rule (`damdays.export.app_data.contract_problems`), then runs `app/tools/build_bundle.py app/data/real`, which lists "real" first in `app/data/datasets.js`. Options: `--rung L2` (once that rung has its validation results), `--region wvic_sesa` or `all`, `--season 2009` (another validation season), `--refit-live`, `--history-from 2000-01` (smaller files).

Code: `damdays/export/app_data.py` (the six files), `damdays/export/live_model.py` (the production fit), `damdays/export/albers.py` (hexagon corners to latitude/longitude), `scripts/11_export_app.py` (runs it all). Tests: `tests/test_app_export.py` (small made-up inputs) and `tests/test_app_export_real.py` (these published files against the raw data: a truncation test with a planted-leak control, hand checks on single dams, the live curve code reproducing the validated curves bit for bit, and an independent recount of the live fit's training rows).

## Where each number comes from

| view | what | made by |
|---|---|---|
| Runway | today's forecast for each dam-like dam, from its latest clear look (September 2026) | **Production fit**: Tidemark refitted on every answer final by the last satellite look (cutoff 15 Sep 2026). Same recipe and time rules as the validation model; see the docstring of `live_model.py`. Never scored: these forecasts are about the future. |
| Rewind | forecasts on 1 Nov, 1 Jan and 1 Mar of one season, and what happened | The **validation-setting model** (fitted only on answers final before 1 Jan 2009), forecasts saved by `scripts/08_tidemark_val.py`. Outcomes are the PREREG R30 labels. |
| Rating | each 2 km cell's rating and rainfall-only score, and which cells ran dry | Same validation-setting model and season; the rainfall-only score is the RAIN baseline of `scripts/03`. "Ran dry" is the PREREG cell label (every dam-like dam in the cell had a D0 event, October to March). |
| Scoreboard | AUC of rating and rainfall-only, runway skill | Copied from `artifacts/val_tidemark_L1.json` and step 3's RAIN scorecard; the one-season line is computed by the scorecard itself (`artifacts/scorecard/step11_app/`). All are **validation-period** numbers (2009-2015), and the file says so (`source: "dev_val"`, `is_validation: true`). |

The Rewind and Rating season is chosen by the exporter: the validation season with the most falls below a third among the app's dams (2013-14 for NSW Central West: 623 R30 starts). It is the most telling season to rewind, not a typical one. The three dates start from October, December and February looks, the October-March months of the pre-registered headline set.

## How the curve and the headline agree

The 90-day headline (fused members + per-dam correction + max rule) and the runway curve (the hazard model H) are two models, so H's own 90-day value differs a little (mean gap 0.036 on validation). The exporter draws the curve as H's 30, 60 and 180-day values with the headline at 90 days; where H's 30 or 60-day value is above the headline it is lowered to it, and where its 180-day value is below the headline it is raised to it. The curve therefore passes through the headline and never falls. This moved a point on 3 of 576 live curves (and on 5 to 33 curves per Rewind date; `meta.json` has the counts). The shaded band is the season band applied to each point, so its 90-day point equals `chance_low` / `chance_high`.

## Statuses

From each dam's last clear look on or before the issue date: no look in the last 60 days, `no_recent_look`; below a third of full (or dry), `already_low`; not refilled to 60% of full in the last 180 days, or fallen below a third since its last refill (the PREREG arming rule), `not_refilled`; otherwise `forecast`. Levels use the PREREG static "full" (display only; the models use the causal checkpoint full).

## Switching Rewind and Rating to a test season (after the official TEST scoring)

The exporter refuses a season outside 2009-10 to 2014-15 today. To show 2018-19 after the one-time TEST scoring: point `val_model_outputs` and `rating_season` in `scripts/11_export_app.py` at the TEST-setting forecasts (`data_cache/preds/TEST/tidemark/`, `data_cache/preds/TEST/P2_cell/baselines.pkl`), take the scoreboard from the official TEST results, and do not recompute per-season TEST scores here (the TEST ledger refuses a second look with different rows, by design).

## Size

The JSON files total about 3.8 MB; `history.json` is most of it (894 dams x 465 months of levels, plus 28,262 event starts). `bundle.js` is a copy of all six (3.8 MB on disk, about 0.6 MB as a web server sends it gzipped).
