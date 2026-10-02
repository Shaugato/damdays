# DamDays

**How many days of water does this farm dam have left?** DamDays answers that for farm dams big enough for the satellites to see (about 0.5 ha and up), using 38 years of satellite water history, says how sure it is, and writes the answer for the farmer as one text a week.

Climate Hack-tion 2026 · Build for 2035 · COP31 track: **Awareness Across All Areas** (helping farmers and land managers adapt, and making climate information easy to use).

> Work in progress during the event (2-4 Oct 2026). This page is updated as the build progresses. Results below: Fri 2 Oct 2026, 21:07 AEST. <!-- SEALED:START status -->The sealed region opens Sat 3 Oct 17:30 AEST; its results are added below after that.<!-- SEALED:END -->

## What farmers get

**One text a week, per farm.** A mentor who grew up on farms told us farmers rarely open apps or emails, but a weekly text is what they would use. So the text is the product. This is the real text made on Fri 2 Oct 2026 for a demo farm near Dubbo (7 farm dams within 3 km of the homestead; the dams and forecasts are real, the homestead point is not):

```
Fri 2 Oct (satellite 13 Sep)
Dam 2 ~67% full: at least 29 days before it drops below 1/3
Dam 1 looks dry
Other 5 dams: at least 52 days
Reply MAP
```

- **"%" means only how full a dam is**, at its latest clear satellite look. The text gives no chances; its longer app/email version writes a chance as "3 in 10", never as a percent.
- **The headline is days**: the cautious DamDays number, counted from the day of the text (Dam 2 had at least 48 days from its 13 Sep look, so 29 from 2 Oct). On the ten test years it held 9 times in 10. From 180 days on, the text says "6 months+".
- **Dam 1 is the dam closest to the homestead.** A farm is a homestead point plus every farm dam the satellites can see within 3 km (there are no property boundaries in the data).
- **Every text fits one SMS** (160 places). This week's texts for 10 demo farms in both regions: [outbox/2026-10-02.json](outbox/2026-10-02.json). The rules, line by line, with 10 worked examples: [notify/MESSAGE_SPEC.md](notify/MESSAGE_SPEC.md). Nothing is sent unless you run the sender with your own SMS account's keys.
- **In the app** ([app/index.html](app/index.html)), the **My farm** view opens first and shows the same farm: the homestead, its dams on the map, this week's text on a drawn phone, and each dam's card. Click the map to set your own homestead and the text is made again in the browser, by a JavaScript copy of the Python that is checked to write the same texts character for character ([app/README.md](app/README.md#the-weekly-text-in-the-browser-one-text-two-languages)). Its data, the demo farms with their dams and texts, is [app/data/real/farms.json](app/data/real/farms.json) ([format](app/DATA_CONTRACT.md#farmsjson-optional-demo-farms-and-their-weekly-texts)).

## Results

The model was frozen on Fri 2 Oct 2026 at 20:21 AEST: version L3 (full Tidemark), code fingerprint `7d466291008d` ([PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md)). The test rules and pass marks had been committed before any code ([PREREG.md](PREREG.md)). Then the model sat three exams, each on years or places it never learned from:

| exam | what it is | result |
|---|---|---|
| **Validation**, 2009-2015 | The practice exam. Every design choice was made on these years. | All pass marks met. |
| **Test**, July 2016 to June 2026 | Ten years the frozen model never trained on, scored **once** ([artifacts/test_results.md](artifacts/test_results.md)). | **All pass marks met.** |
| **Sealed region** | A third region (Southern Downs, Granite Belt, New England), downloaded before the event, locked away with public fingerprints ([SEALED_HASHES.csv](SEALED_HASHES.csv)) and opened once, on camera. | <!-- SEALED:START cell -->**Opens Sat 3 Oct 17:30 AEST.** Numbers go here.<!-- SEALED:END --> |

Brackets below are 95% ranges, found by re-drawing the dams at random 500 times and scoring again. A range above zero means the result is unlikely to be luck.

### For the farmer: will this dam fall below a third of full in the next 90 days?

Forecasts made from October to March (when dams run down), for waterbodies that look and behave like farm dams. Test: 142,938 forecasts, 29,415 of which fell below a third.

| what we measured | validation 2009-15 | test 2016-26 | what it means (test) |
|---|---|---|---|
| Error compared with guessing the usual rate for that region and month (Brier skill score) | +0.180 [+0.165, +0.197] | **+0.235** [+0.224, +0.248] | 23.5% less error than guessing the usual rate |
| Error compared with the dam's own track record ("this dam fell below a third after 3 in 10 of its past forecasts") | +0.110 | +0.155 | 15.5% less error than the dam's own record, a much tougher rule to beat |
| Ranking (AUC): a dam that fell below a third is given a higher chance than one that did not | 0.79 | 0.82 | the right way round 8 times in 10 (a coin toss is 5 in 10) |
| Gain over our own strong benchmark G2 (the decision-tree model alone, without the nets, the per-dam correction or the water balance), on exactly the same forecasts | +0.010 [+0.007, +0.014] | +0.014 [+0.011, +0.018] | small, but reliably above zero |
| Calibration slope (1.0 is ideal; pass mark 0.8 to 1.2) | 1.06 | 1.09 | the chances are about right, if a little cautious |
| **"At least N days of water above a third, 9 times in 10"** (the DamDays number) | held for 90.0% of 304,611 [89.7%, 90.3%] | held for **90.0%** of 729,749 [89.8%, 90.2%] | the cautious promise held 9 times in 10, as designed; the typical N was 60 days |

The **runway curve** (the chance of falling below a third within 30, 60, 90 and 180 days) beats each horizon's own usual rate on the test years by +0.105, +0.178, +0.223 and +0.253. No curve ever went down as the days went up (0 of 147,196 checked).

### For the lender: will every farm dam in this 2 km patch run dry this summer?

Rated each 1 July, before the season. "Ran dry" means every farm dam in the patch ran completely dry between October and March. Test: 14,331 ratings over 10 seasons (2016-17 to 2025-26), 2,316 of which ran dry.

| what we measured | validation (7 seasons) | test (10 seasons) | what it means (test) |
|---|---|---|---|
| Ranking (AUC), DamDays Rating | 0.79 [0.77, 0.80] | **0.81** [0.80, 0.82] | shown a patch that ran dry and one that did not, it picks the right one 8 times in 10 |
| Ranking (AUC), rainfall-only score (the kind most drought tools use today) | 0.54 | 0.53 | close to a coin toss |
| Ranking within a single season: DamDays against rainfall-only | 0.79 against 0.47 | 0.81 against 0.49 | in a given summer, rainfall alone cannot tell which farms will run dry |
| Gain over rainfall-only (pass mark +0.05; the "kill rule" drops the lender claim if the gain is under 0.02) | +0.25 [+0.23, +0.27] | **+0.29** [+0.27, +0.30] | passed by a wide margin; kill rule not triggered |
| Gain over the dam's own dry-season record alone | +0.014 | +0.029 | most of the rating's power comes from that record; the model adds a little |

### What these numbers do and do not show

- **Every pre-registered pass mark was met**, on validation and on test. On test, the benchmark G2 met them too ([artifacts/test_results.md](artifacts/test_results.md), "PREREG pass bars").
- **The test years are not a perfectly clean test.** Some design choices were informed by earlier scores on these years, so they may flatter the model slightly (the pre-registration estimates by about 0.005 to 0.01 of skill). The reasons are listed at the top of the results page and in [DISCLOSURE.md](DISCLOSURE.md). **The clean test is the sealed region.**
- **Worst year for the DamDays number:** July 2023 to June 2024, when it held for 87.2%, a little below the 88% to 92% target range. In the other nine years it held within that range or above it.
- **Season band** (how far a very wet or very dry year can move a forecast): it covered all 20 test region-years, but its design was partly chosen after seeing these years, so this is not an independent check. The earlier single-block band covered 17 of 20; every miss was a year drier than it allowed.

### Sealed region (opened Sat 3 Oct 2026, 17:30 AEST)

<!-- SEALED:START -->
> **The sealed region opens Sat 3 Oct 17:30 AEST.** After the opening, `scripts/21_publish_sealed.py` writes its results here, copied from `artifacts/sealed/sealed_results.json` (the full page, unedited: `artifacts/sealed/SEALED_RESULTS.md`).
>
> What we said to expect, before opening it ([PREREG.md](PREREG.md)): skill against the usual rate of about +0.15 to +0.23 (central +0.19); gain over G2 of +0.01 to +0.03; lender-rating gain over rainfall-only of +0.15 to +0.30. These are forecasts, not pass marks. Every number is published, whatever it shows.

<!-- SEALED:END -->

## Start here (2-minute tour for judges and mentors)

1. **The problem.** In a drought, graziers must decide when to cart water, move stock or sell, before the dam runs dry. Banks and valuers judging farm drought risk see rainfall, but not how much water a farm has stored.
2. **What we built.** A weekly text for each farm with each dam's days of water left ([above](#what-farmers-get)); an app to look closer, where each dam's card adds the chance it drops below a third (Dam 2 above: 3 in 10 by 12 Dec) and a six-month runway; and a season-ahead water-security rating for lenders.
3. **How we know it works.** Every claim is tested on years and dams the model never saw. The test rules were written down and committed *before* any code ([PREREG.md](PREREG.md)). One whole region was downloaded but kept sealed (its file fingerprints are in [SEALED_HASHES.csv](SEALED_HASHES.csv)) and is opened once, on camera, on Saturday 17:30 AEST. The results so far are [above](#results).
4. **How it works, in plain language:** [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) (one diagram, what each part adds, and the final numbers).
5. **Where the key logic lives** (see the next section).
6. **Reproduce the numbers:** see [Reproduce](#reproduce) below.

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
| [`scripts/13_fit_test_setting.py`](scripts/13_fit_test_setting.py) | Fits the frozen models on answers known before 1 July 2016 and saves their forecasts for the test years. It scores nothing. |
| [`scripts/15_score_test.py`](scripts/15_score_test.py) | The test years' one look: reads step 13's saved forecasts (fingerprints checked) and scores them once through the ledger. Writes [artifacts/test_results.md](artifacts/test_results.md). |
| [`scripts/20_open_sealed_region.py`](scripts/20_open_sealed_region.py) | The sealed-region opening, run once on Sat 3 Oct 17:30 AEST ([docs/SEALED_OPENING.md](docs/SEALED_OPENING.md) is the runbook). It refuses to start unless the unlock switch is on, git is clean and pushed, every sealed file's SHA-256 matches the committed [SEALED_HASHES.csv](SEALED_HASHES.csv), the models match their committed fingerprints and the freeze addendum ([PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md)) is committed; then it builds the region from raw files with the development code ([`damdays/sealed/`](damdays/sealed/)), forecasts it with the frozen TEST-setting models and scores it once. `--dry-run` rehearses the whole pipeline on a development region treated as unseen, on a separate ledger (not the development TEST result). |
| [`damdays/export/`](damdays/export/) | Turns forecasts into the app's data files: [`live_model.py`](damdays/export/live_model.py) refits Tidemark on every answer known by the last satellite look for today's forecasts (shown, never scored), and [`app_data.py`](damdays/export/app_data.py) writes the six JSON files the app reads, copying every score from the evaluation outputs. Run with [`scripts/11_export_app.py`](scripts/11_export_app.py). |
| [`notify/`](notify/) | The weekly text ([notify/MESSAGE_SPEC.md](notify/MESSAGE_SPEC.md)): finds a farm's dams (every dam within 3 km of a homestead point, Dam 1 the closest), writes the SMS and its longer app/email version from the live forecasts, and keeps each text to one SMS. It only reads the forecasts; it does not import or change the frozen model. Run with [`scripts/16_weekly_texts.py`](scripts/16_weekly_texts.py); checked by [`tests/test_weekly_text.py`](tests/test_weekly_text.py). |

## Reproduce

Everything runs on a laptop CPU (built on Windows 11 with Python 3.12, 8 cores and 32 GB RAM). Steps 01 to 16 rebuild every number on this page from the raw public data, in about 5 to 7 hours, most of it model fitting.

**1. Set up** (once, from the repo folder; Python 3.12):

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

On macOS or Linux, use `.venv/bin/python` wherever this page says `.venv/Scripts/python.exe`. If pip finds no `torch==2.14.1+cpu` for your computer (macOS has no `+cpu` build), change that line of [requirements.txt](requirements.txt) to `torch==2.14.1`.

**Quick check from a fresh clone** (about 5 minutes, no data download). The raw data and `data_cache/` (everything steps 01-13 compute) are not in git, but these run on the committed files alone:

```
.venv/Scripts/python.exe -m pytest tests -rs
.venv/Scripts/python.exe scripts/14_config_hash.py
node app/tools/check_text_port.js
python -m http.server 8000 --directory app
```

- **The tests** take about 4 minutes. The tests on the real data skip, each saying what it needs: the git-ignored `data_cache/` (rebuilt from the raw data by steps 01-02 below) or the raw data itself. Everything else runs (3 Oct 2026: 322 passed, 79 skipped). Without Node.js, the text-port tests skip too.
- **The code fingerprint** printed must be `7d466291008d`, the one frozen in [PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md). (It rewrites the date in `artifacts/config_hash.json`; `git checkout artifacts/config_hash.json` undoes that.)
- **The weekly text** in the app is written by JavaScript; `check_text_port.js` (Node.js) prints `same` for every text the Python wrote.
- **The app**: open http://localhost:8000 (or double-click `app/index.html`). It reads only the committed `app/data/real/bundle.js`; the background map needs internet.

**2. Raw data** (public, CC BY 4.0; not in the repo because of its size). Point the environment variable `DAMDAYS_RAW` at a folder holding `dea_dev/ts/` (one DEA Waterbodies CSV per waterbody), `dea_dev/manifest.csv`, `dea_polygons/wb.zip` (the DEA Waterbodies v3 outlines) and `silo/` (SILO monthly rainfall, one file per year). The sources and every cleaning step are in [docs/DATA.md](docs/DATA.md); the default location is set in [`damdays/config.py`](damdays/config.py). The sealed folder `dea_sealed/` is only ever read by step 20.

**3. Run the steps in order** (each script's first lines say what it does; `--quick` skips the confidence ranges where a script offers it):

| step | command | what it does | time |
|---|---|---|---|
| 01 | `.venv/Scripts/python.exe scripts/01_build_data.py` | clean satellite history, dam shapes, dry-out events, rainfall | about 1 min |
| 02 | `.venv/Scripts/python.exe scripts/02_build_features.py` | the facts each forecast may use (only what was known that day) | 5-8 min |
| 03 | `.venv/Scripts/python.exe scripts/03_baselines_and_g2.py` | the simple rules and the benchmark G2, on validation | about 25 min |
| 04 | `.venv/Scripts/python.exe scripts/04_tidemark_l1.py` | the decision trees and the per-dam correction | about 30 min |
| 05 | `.venv/Scripts/python.exe scripts/05_season_rating.py` | the lender rating, on validation | about 2 min |
| 06 | `.venv/Scripts/python.exe scripts/06_hazard_curve.py` | the runway curve | about 35 min |
| 07 | `.venv/Scripts/python.exe scripts/07_uncertainty.py` | the DamDays number ("at least N days") and the season band | about 5 min |
| 08 | `.venv/Scripts/python.exe scripts/08_tidemark_val.py` | version L1 end to end, on validation | about 15 min |
| 09 | `.venv/Scripts/python.exe scripts/09_nets_val.py` | the two neural nets (version L2) | 30-40 min |
| 10 | `.venv/Scripts/python.exe scripts/10_physics_val.py` | the water-balance outlook (version L3) | 30-50 min |
| 11 | `.venv/Scripts/python.exe scripts/11_export_app.py --rung L3 --season 2018 --refit-live` | the app's data files, as shipped (frozen L3; Rewind and Rating on 2018-19). **Run it after step 15**: a test season is shown only after the one-time scoring. With no options it makes a validation-season export at rung L1 instead (options in its first lines) | about 25 min |
| 12 | `.venv/Scripts/python.exe scripts/12_ladder_val.py` | all four versions side by side: decides which may be frozen | 60-75 min |
| 13 | `.venv/Scripts/python.exe scripts/13_fit_test_setting.py` | fits the frozen models on answers known before 1 July 2016 and saves the test forecasts; scores nothing | 45-75 min |
| 14 | `.venv/Scripts/python.exe scripts/14_config_hash.py` | the code fingerprint; for the frozen code it prints `7d466291008d` | seconds |
| 15 | `.venv/Scripts/python.exe scripts/15_score_test.py --check`, then `.venv/Scripts/python.exe scripts/15_score_test.py` | `--check` builds and checks every table and scores nothing; the second command is the test years' one look | 15-30 min |
| 16 | `.venv/Scripts/python.exe scripts/16_weekly_texts.py --date 2026-10-02` | the weekly texts for 10 demo farms, as shown on this page ([What farmers get](#what-farmers-get)). Without `--date` they are dated today, so the days change. Needs step 11's live fit; `--regions nsw_cw` needs only the app's published file | seconds |

Then the tests: `.venv/Scripts/python.exe -m pytest tests` (with `data_cache/` built, the tests on the real data run instead of skipping).

**Step 20 is not part of the rebuild.** `scripts/20_open_sealed_region.py --open` opens the sealed region once (Sat 3 Oct 17:30 AEST, on camera; runbook: [docs/SEALED_OPENING.md](docs/SEALED_OPENING.md)). It refuses to start without the unlock switch, a clean and pushed git, and matching fingerprints for every sealed file and every frozen model.

Two things to know when re-running:
- **The test ledger** ([artifacts/test_ledger.csv](artifacts/test_ledger.csv)) records this build's one look at the test years. Re-running step 15 on the same saved forecasts only adds "same predictions" rows; forecasts that differ in any digit are refused, by design. To score a fresh rebuild, start from an empty ledger.
- **Re-running step 13** writes new model files. Their fingerprints can differ from the ones committed with the freeze ([artifacts/sealed_models_manifest.json](artifacts/sealed_models_manifest.json)), and step 20 refuses models whose fingerprints differ.

## Limits

- **Only dams of about 0.5 ha or more.** The satellite (Landsat, 30 m pixels) needs a dam outline of at least 6 pixels (5,400 m², about 0.54 ha) to see it reliably. Many smaller farm dams are not covered.
- **No bores, tanks or rivers.** DamDays sees surface water in dams. Groundwater bores and tanks are invisible to it.
- **Two development regions.** It was built and tested in NSW Central West and in western Victoria / south-east South Australia, with the sealed region (Southern Downs, Granite Belt, New England) as the test in a new place. Other climates, such as the tropical north or Western Australia, are untested.
- **The satellite floor.** A satellite sees how much of a dam is wet, not how deep it is: "a third" means a third of the dam's usual full wet area. Clear looks come every week or two when there is no cloud, so a forecast starts from the last clear look, which can be weeks old. The DEA outlines and SILO rainfall are final, revised products, not exactly what was known at the time.
- **It ranks farms better than it times droughts.** It is good at "which dams run dry this summer" and weak at "will this dam run dry this year or next" (close to a coin toss within a single dam's history, on validation).
- **Very wet and very dry years.** In the wet 2010-12 years the forecasts were too high on average. The season band shows how far such a year can move a forecast.
- **Not advice.** Use it alongside your own eyes on the dam and local knowledge.

## Honesty notes
- Pre-event research and data download were allowed by the organisers and are disclosed in [DISCLOSURE.md](DISCLOSURE.md). All code in this repository was written during the event.
- [BUILD_LOG.md](BUILD_LOG.md) is a timestamped record of the build.

## Data
- DEA Waterbodies v3, Geoscience Australia (CC BY 4.0).
- SILO climate data, Queensland Government (CC BY 4.0).

## Licence
Copyright (c) 2026 Shaugato Paroi. All rights reserved. The source is public so the hackathon judges can review it; no licence to reuse it is granted.
