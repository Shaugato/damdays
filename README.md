# DamDays

**How many days of water does this farm dam have left?** DamDays answers that for every visible farm dam, using 38 years of satellite water history, and says how sure it is.

Climate Hack-tion 2026 · Build for 2035 · COP31 track: **Awareness Across All Areas** (helping farmers and land managers adapt, and making climate information easy to use).

> Work in progress during the event (2-4 Oct 2026). This page is updated as the build progresses.

## Start here (2-minute tour for judges and mentors)

1. **The problem.** In a drought, graziers must decide when to cart water, move stock or sell, before the dam runs dry. Banks and valuers judging farm drought risk see rainfall, but not how much water a farm has stored.
2. **What we built.** A forecast for each dam ("58% chance this dam falls below a third by 1 February; at least 60 days of water left, 9 times in 10"), plus a season-ahead water-security rating for lenders.
3. **How we know it works.** Every claim is tested on years and dams the model never saw. The test rules were written down and committed *before* any code ([PREREG.md](PREREG.md)). One whole region was downloaded but kept sealed (its file fingerprints are in [SEALED_HASHES.csv](SEALED_HASHES.csv)) and is opened once, on camera, on Saturday 17:30 AEST.
4. **How it works, in plain language:** [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) (one diagram, what each part adds, with validation numbers).
5. **Where the key logic lives** (see the next section).
6. **Reproduce the numbers:** run `scripts/01` to `scripts/12` in order (`.venv/Scripts/python.exe scripts/<name>.py`). `scripts/12_ladder_val.py` fits all four versions of the model (the pre-registered "ladder", L0 to L3) and writes the validation table that decides which one may be frozen ([artifacts/ladder_val.md](artifacts/ladder_val.md)) and the full validation scorecard of the best one that passes ([artifacts/val_tidemark_best.md](artifacts/val_tidemark_best.md)).

## Where the key logic lives

Read in this order. Each file starts with a plain-English explanation.

| file | what it does |
|---|---|
| [`damdays/models/tidemark.py`](damdays/models/tidemark.py) | The whole forecasting engine in one place: `fit_tidemark` learns only from answers known before a cutoff date, `predict_tidemark` makes every forecast (90-day chances, runway curve, "at least N days" floor, season band, lender rating). The same two calls run every version of the model on the pre-registered ladder (L0 = the benchmark, L1 = + per-dam correction, L2 = + neural nets, L3 = + water balance), and every version returns the same columns. |
| [`damdays/features/spec.py`](damdays/features/spec.py) | Every number a model is allowed to see, each with the reason it cannot see the future. [`tests/test_no_lookahead.py`](tests/test_no_lookahead.py) proves it: delete the future, rebuild, and every past input must be identical. |
| [`damdays/models/frailty.py`](damdays/models/frailty.py) | The per-dam correction ("this dam runs drier than similar dams"), learned from the dam's own past forecasts, but only once their answer was known. |
| [`damdays/models/hazard.py`](damdays/models/hazard.py) | The runway curve: the chance of falling below a third within 30, 60, 90 and 180 days, built so it can never go down as the days go up. |
| [`damdays/models/nets.py`](damdays/models/nets.py) | The two small neural nets (added at rung L2): one reads the dam's last 24 complete months of water and rain ([`damdays/features/sequences.py`](damdays/features/sequences.py)), the other its current facts. Each answers all three questions at once, is trained with 3 seeds, and learns only from answers known before the cutoff. |
| [`damdays/models/physics.py`](damdays/models/physics.py) | The water-balance outlook (added at rung L3): a simple bucket model of each dam (rain in, evaporation and stock use out), kept on track by the satellite looks, run over the rain of the 20 previous years. Gives two extra inputs to the learning model and the runway curve ("chance of falling below a third / running dry in 90 days under past rain years"). |
| [`damdays/models/season_rating.py`](damdays/models/season_rating.py) | The lender rating: will a farm's dams run dry this summer? It starts from each dam's own dry-season record and is tested against rainfall-only scores. |
| [`damdays/evaluation/scorecard.py`](damdays/evaluation/scorecard.py) | The one scorecard every model is judged by, with confidence ranges and a ledger that allows each model only one look at the test years ([docs/SCORECARD.md](docs/SCORECARD.md)). |
| [`scripts/12_ladder_val.py`](scripts/12_ladder_val.py) | The pre-registered fallback ladder: fits L0, L1, L2 and L3 through `fit_tidemark`, compares each with the value the pre-event research got for it, and reads the look-ahead test, so the version to freeze follows mechanically from the rule ([artifacts/ladder_val.md](artifacts/ladder_val.md)). |
| [`damdays/export/`](damdays/export/) | Turns forecasts into the app's data files: [`live_model.py`](damdays/export/live_model.py) refits Tidemark on every answer known by the last satellite look for today's forecasts (shown, never scored), and [`app_data.py`](damdays/export/app_data.py) writes the six JSON files the app reads, copying every score from the evaluation outputs. Run with [`scripts/11_export_app.py`](scripts/11_export_app.py). |

## Honesty notes
- Pre-event research and data download were allowed by the organisers and are disclosed in [DISCLOSURE.md](DISCLOSURE.md). All code in this repository was written during the event.
- [BUILD_LOG.md](BUILD_LOG.md) is a timestamped record of the build.

## Data
- DEA Waterbodies v3, Geoscience Australia (CC BY 4.0).
- SILO climate data, Queensland Government (CC BY 4.0).

## Licence
Copyright (c) 2026 Shaugato Paroi. All rights reserved. The source is public so the hackathon judges can review it; no licence to reuse it is granted.
