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
6. **Reproduce the numbers:** one command, documented here once the pipeline is complete. Today: `scripts/01` to `scripts/08`, in order; `scripts/08_tidemark_val.py` gives the whole validation scorecard ([artifacts/val_tidemark_L1.md](artifacts/val_tidemark_L1.md)).

## Where the key logic lives

Read in this order. Each file starts with a plain-English explanation.

| file | what it does |
|---|---|
| [`damdays/models/tidemark.py`](damdays/models/tidemark.py) | The whole forecasting engine in one place: `fit_tidemark` learns only from answers known before a cutoff date, `predict_tidemark` makes every forecast (90-day chances, runway curve, "at least N days" floor, season band, lender rating). |
| [`damdays/features/spec.py`](damdays/features/spec.py) | Every number a model is allowed to see, each with the reason it cannot see the future. [`tests/test_no_lookahead.py`](tests/test_no_lookahead.py) proves it: delete the future, rebuild, and every past input must be identical. |
| [`damdays/models/frailty.py`](damdays/models/frailty.py) | The per-dam correction ("this dam runs drier than similar dams"), learned from the dam's own past forecasts, but only once their answer was known. |
| [`damdays/models/hazard.py`](damdays/models/hazard.py) | The runway curve: the chance of falling below a third within 30, 60, 90 and 180 days, built so it can never go down as the days go up. |
| [`damdays/models/season_rating.py`](damdays/models/season_rating.py) | The lender rating: will a farm's dams run dry this summer? It starts from each dam's own dry-season record and is tested against rainfall-only scores. |
| [`damdays/evaluation/scorecard.py`](damdays/evaluation/scorecard.py) | The one scorecard every model is judged by, with confidence ranges and a ledger that allows each model only one look at the test years ([docs/SCORECARD.md](docs/SCORECARD.md)). |

## Honesty notes
- Pre-event research and data download were allowed by the organisers and are disclosed in [DISCLOSURE.md](DISCLOSURE.md). All code in this repository was written during the event.
- [BUILD_LOG.md](BUILD_LOG.md) is a timestamped record of the build.

## Data
- DEA Waterbodies v3, Geoscience Australia (CC BY 4.0).
- SILO climate data, Queensland Government (CC BY 4.0).

## Licence
Copyright (c) 2026 Shaugato Paroi. All rights reserved. The source is public so the hackathon judges can review it; no licence to reuse it is granted.
