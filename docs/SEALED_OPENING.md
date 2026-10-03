# Opening the sealed region: the runbook

**When:** Saturday 3 October 2026, 17:30 AEST, once, on camera.
**What:** one command, `scripts/20_open_sealed_region.py --open`. It takes about **20 to 25 minutes** (the rehearsal on a region 0.7 times its size took 16).
**Why it matters:** the sealed region (Southern Downs, Granite Belt, New England: 4,711 waterbodies) is the only clean test of DamDays. Its files were downloaded and fingerprinted before the event and have never been opened ([PREREG.md](../PREREG.md), "Sealed region protocol"). Whatever the numbers show, they are published.

This page is written for the founder running the opening. Every command is exact; copy it.

## What the command does, in plain words

1. **Checks, before any sealed byte is read.** It stops (and says why) unless all of these hold:
   - the unlock switch `DAMDAYS_OPEN_SEALED` is set to `yes`;
   - git is clean (everything committed) and the last commit is pushed to GitHub;
   - `SEALED_HASHES.csv` is the copy committed at 09:12 on Friday and never changed since;
   - every one of the 4,711 sealed files is there, there is no extra file, and every file's fingerprint (SHA-256) equals the committed one. One difference stops the run.
2. **Loads the frozen models and checks the freeze addendum.** The models are the ones fitted on the two development regions' forecasts before 1 July 2016 (step 13). Their fingerprints must equal the manifest committed with the freeze addendum ([`artifacts/sealed_models_manifest.json`](../artifacts/sealed_models_manifest.json)). The committed addendum ([`PREREG_ADDENDUM_1.md`](../PREREG_ADDENDUM_1.md)) must quote the sealed evaporation hash, or it stops. It also prints the config hash of the code being run and whether the addendum quotes it.
3. **Builds the sealed region from its raw files** with exactly the same code as the development regions. First, the region's list of waterbodies (`manifest.csv`, not in the hash list) must name exactly the 4,711 verified files. Then: satellite history, dam shapes, the "dam-like" and "persistent" labels (from the region's own looks before 2016), dry-out events, rainfall from the sealed SILO key, the water balance (with the development regions' fitted parameters and the typed Glen Innes evaporation shape), and the nets' 24-month histories.
4. **Forecasts** every sealed satellite look from 1 July 2016 to 30 June 2026, and every 1 July season rating from 2016 to 2025. Each dam's own track record is used only as it stood on each forecast date.
5. **Scores once** with the same scorecard as everything else: G2 and Tidemark on the farmer runway (below a third, fully dry, gradual dry-out; three groups of dams; the sensitivity row), the runway curve, the lender rating against rainfall-only scores (RAIN, RAIN+) and the dam's own record (B2), the season band, the DamDays floor, the pre-registered pass bars, the kill rule and the pre-declared expectations. The simple rules it is compared with are fitted on the sealed region's own history before July 2016. Every score is written to [`artifacts/sealed/`](../artifacts/sealed/) the moment it is computed, and recorded on the TEST ledger ([`artifacts/test_ledger.csv`](../artifacts/test_ledger.csv)) as arena `sealed`.
6. **Writes the results page** `artifacts/sealed/SEALED_RESULTS.md` (and `sealed_results.json`).

Code: [`scripts/20_open_sealed_region.py`](../scripts/20_open_sealed_region.py) and [`damdays/sealed/`](../damdays/sealed/) (read `__init__.py` first).

## Timeline for Saturday

| time (AEST) | what | command |
|---|---|---|
| after step 13 finishes | Fingerprint the frozen TEST-setting models; this writes `artifacts/sealed_models_manifest.json`. Done once on Fri 2 Oct 19:08 for step 13's first run; **rerun it whenever step 13 is rerun** (new model files, new fingerprints). | `--prepare` (below) |
| before 16:45, only if needed | The rehearsal already ran (Fri 19:04-19:44). **Do not rerun it just to look again**: it scores western Victoria's test years, and every run is recorded on the dry-run ledger (disclosed in the addendum, 6.16). Rerun it only to test a change to the runner. | `--dry-run` (below) |
| last code change, then | Recompute the config hash and put the new values in section 2 of the freeze addendum. The hash covers every `damdays/**/*.py` file, so it must be the last step after any code change. | `.venv\Scripts\python.exe scripts\14_config_hash.py` |
| **by 16:45** | Commit and push the freeze addendum **and** `artifacts/sealed_models_manifest.json` (and everything else, including `artifacts/sealed_dryrun/`, `artifacts/config_hash.json` and the outputs of any development TEST scoring). Check `git status` is clean. Optional: post the commit SHA on Discord as a third-party timestamp. | `git status` |
| 17:15 | Start the screen recording. Open a terminal in the repo folder. | |
| **17:30** | Set the unlock switch and run the opening. | `--open` (below) |
| about 18:00 | Commit and push the raw results, unedited. | (below) |

## The exact commands

Open **PowerShell** in the repo folder:

```powershell
cd "D:\Climate Hack-tion 2026\damdays"
```

**Before the opening (no sealed file is read):**

```powershell
# 1. fingerprint the frozen models (after scripts/13_fit_test_setting.py has finished)
.venv\Scripts\python.exe scripts\20_open_sealed_region.py --prepare

# 2. the config hash, after the LAST code change: copy its values into section 2 of the addendum
.venv\Scripts\python.exe scripts\14_config_hash.py

# (only to test a change to the runner: the rehearsal; see "The dry run" below)
.venv\Scripts\python.exe scripts\20_open_sealed_region.py --dry-run
```

**At 17:30, the opening:**

```powershell
git status                                   # must say "nothing to commit, working tree clean"
$env:DAMDAYS_OPEN_SEALED = "yes"             # the unlock switch (this terminal only)
.venv\Scripts\python.exe scripts\20_open_sealed_region.py --open
```

**Right after it finishes:**

```powershell
Remove-Item Env:DAMDAYS_OPEN_SEALED          # switch off again
git add artifacts/sealed artifacts/test_ledger.csv
git commit -m "Sealed region opened: raw results, unedited"
git push
```

The same in **Git Bash**: `export DAMDAYS_OPEN_SEALED=yes`, then `.venv/Scripts/python.exe scripts/20_open_sealed_region.py --open`, and `unset DAMDAYS_OPEN_SEALED` afterwards.

**Then publish** with `scripts/21_publish_sealed.py` ([SATURDAY_CHECKLIST.md](SATURDAY_CHECKLIST.md), section 8, "Publish the results everywhere"). Commit with `git add -A README.md docs/PITCH.md docs/VIDEO_SCRIPT.md app/data app/sw-version.js` (the `git add` line scripts/21 prints): the app reads the split data parts, and the rebuild writes a new `app/data/real/first.<hash>.js`, deletes the old one, rewrites `parts.js` and restamps `app/sw-version.js`. Check that `git status` shows the new part added and the old one deleted, or the live app keeps saying "Unseen exam: not opened yet".

## What appears on screen

Every line starts with the clock time and the minutes since the start; the same lines go to `artifacts/sealed/run_log.txt`. The rehearsal printed these stages (the opening prints the same, with the sealed region's names and counts):

```text
[18:57:29 + 0.0 min] DRY RUN (REHEARSAL): wvic_sesa treated as an unseen region, models fitted on nsw_cw only, ...
[18:57:29 + 0.0 min] === 1. checks before touching the region ===
[18:57:30 + 0.0 min]   4,711 files listed; committed once, in e0e9b0b0a450 at 2026-10-02 09:12:19 +1000; unchanged since
[18:57:36 + 0.1 min]   100% match: 3,409 of 3,409 files (3.2 s)
[18:57:36 + 0.1 min] === 2. the frozen TEST-setting models and the freeze addendum ===
[18:57:36 + 0.1 min]   tidemark: data_cache/sealed_dryrun/models/tidemark_L3.pkl SHA-256 b708a44f91606259... matches the manifest
[18:57:36 + 0.1 min]   rung L3, fitted on ['nsw_cw'] at 2016-07-01; evaporation shape wvic_sesa:8.4,7.9,... (SHA-256 fd2a2b32f2bf3be1...)
[18:57:36 + 0.1 min] === 3. build wvic_sesa from raw files ===
[18:57:49 + 0.3 min]   panel: 2,090,473 valid looks, 1986-08-18 to 2026-09-11 (13 s)
[18:57:53 + 0.4 min]   attributes: 3,384 with history, 789 dam-like, 345 persistent (flags from the region's own pre-2016 looks)
[19:00:33 + 3.1 min]   features: 901,976 P1 issues, 128,592 P2 dam-seasons, 25,384 P2 cell-seasons (156 s)
[19:01:48 + 4.3 min]   physics: 799,898 issues simulated with the given balance and the wvic_sesa evaporation shape (232 s)
[19:02:03 + 4.6 min] === 4. forecasts with the frozen models ===
[19:04:41 + 7.2 min] === 5. score once (shared scorecard, ledger dryrun_ledger.csv) ===
[19:05:58 + 8.5 min]   P1_R30 primary: Tidemark BSS vs B0 ..., G2 ...
          (then D0 and D0g, the runway curve, the three P2 ratings, the season band and the floor)
[19:13:24 +15.9 min] P1 pass bars (R30 primary): Tidemark ..., G2 ...
[19:13:24 +15.9 min] P2 pass bar (cell): ...; kill rule ...
[19:13:24 +15.9 min] expectation R30 BSS vs B0: got ... (declared +0.15 to +0.23): ...
[19:13:24 +15.9 min] time: total 15.9 min
```

At the opening the check lines read instead:

```text
check 1: the unlock switch
  DAMDAYS_OPEN_SEALED=yes
check 2: git is clean and HEAD is pushed (read-only git)
  clean; HEAD <commit> is on the remote (live: git ls-remote origin main)
check 3: the hash list committed at the start of the event (SEALED_HASHES.csv, read from git)
  4,711 files listed; committed once, in e0e9b0b0a450 at 2026-10-02 09:12:19 +1000; unchanged since
check 4: SHA-256 of every sealed file in ...\dea_sealed\ts
  hashed 1,000 of 4,711 files ... hashed 4,000 of 4,711 files
  100% match: 4,711 of 4,711 files, none missing, none extra (... s)
```

Then the three model files (`data_cache/models/TEST/tidemark_L3.pkl`, `g2.pkl` and `data_cache/features/physics_params.pkl`) "match the manifest", and the evaporation shape `sealed_sdowns_newengland:5.4,4.8,4.1,3.0,2.0,1.5,1.7,2.5,3.6,4.5,5.1,5.4` with SHA-256 `f886f4190d19b044...`, followed by:

```text
  the evaporation SHA-256 is quoted in ['PREREG_ADDENDUM_1.md']
  config hash of the code being run: <12 characters>; quoted in ['PREREG_ADDENDUM_1.md']
```

If the second line says `WARNING: no addendum quotes it`, the code differs from the frozen code: the run goes on (a logged crash fix changes the code too), but say so on camera and write it in `artifacts/sealed/CRASH_FIXES.md`. Then the build starts with `manifest lists exactly the 4,711 verified time-series files`.

At the end it prints the verdicts: the P1 pass bars for Tidemark and G2, the P2 pass bar and kill rule, each pre-declared expectation (inside, below or above its range), and the time each stage took. **Read them out on camera as they are.**

## If a check refuses

A refusal prints `REFUSED: <reason>` and stops **before any water history is read or anything is scored**, so nothing is lost: fix the cause and run the same command again.

| message says | what to do |
|---|---|
| `The unlock switch is off` | Run `$env:DAMDAYS_OPEN_SEALED = "yes"` in the same terminal, then the command again. |
| `Uncommitted changes` | Commit and push them (or undo them), then run again. Only the runner's own outputs (`artifacts/sealed/`, `artifacts/test_ledger.csv`) may be uncommitted. |
| `HEAD ... is not on the remote` | `git push`, then run again. If the internet is down (or GitHub does not answer within 60 s), the check uses the last push from this computer and says `OFFLINE` on screen. |
| `No committed PREREG_ADDENDUM*.md quotes the sealed evaporation SHA-256` | The freeze addendum is missing or was edited. Do not open. Restore section 3 of `PREREG_ADDENDUM_1.md` (the hash `f886f419...`), commit and push, then run again. |
| `No ...sealed_models_manifest.json: run the runner with --prepare first` | The models were never fingerprinted. Run `--prepare`, commit and push the manifest (with a note in the addendum), then open. |
| `the models are rung X, but the frozen rung is Y` | The models do not match the freeze. Do not open. Rerun `--prepare` (with the right step 13 models), commit and push the new manifest with a note in the addendum, then open. |
| `Model file ... has SHA-256 ...` | A model file changed after the manifest was committed. Do not open. Find out why; do not refit. |
| `SEALED_HASHES.csv must have been committed once ...` or `differs from the committed one` | The fingerprint list was edited. **Stop.** Restore it with `git checkout -- SEALED_HASHES.csv` only if the edit was an accident on this computer; never commit a change to it. |
| `Sealed files do not match the committed hashes` (missing, extra or changed files) | **Do not open the region.** This is a protocol failure: publish the message and the file names it lists, exactly as printed. Do not re-download or "fix" files. |
| `The manifest lists ... waterbodies but ... files were verified` | Same as above: the sealed list of waterbodies does not match the fingerprinted files. **Do not go on.** Publish the message exactly as printed. |

## If it crashes

A crash prints `CRASHED` with the error. The PREREG allows **crash fixes that do not change predictions**, each logged with its time. Then:

1. Write down the time and the error in `artifacts/sealed/CRASH_FIXES.md` (create it): `HH:MM` what crashed, `HH:MM` what you changed and why it cannot change a forecast.
2. Fix only the crash: for example a typo in the report page, a missing folder, a full disk (free space: delete `data_cache/sealed_dryrun/`), or memory (close other programs). **Never** change a model, a feature, a setting or a baseline.
3. Commit the fix and `CRASH_FIXES.md`, push, and run **the same command** again.

What happens on the re-run:
- The checks run again (seconds).
- If the region's tables were already built, they are reloaded, not rebuilt (`reusing the region's tables saved by an earlier run`).
- If the forecasts were already made, they are reloaded (`reusing the forecasts saved by an earlier run`), so exactly the same forecasts are scored.
- The ledger accepts a model only with byte-identical forecasts. A re-scored model shows `same_predictions` on the ledger, never a second look. If a "fix" had changed the forecasts, the ledger would refuse with `LedgerError`: that is the protection working, not something to work around.

Where the time goes, so you know which stage you are in (the rehearsal's times on wvic_sesa, 3,409 waterbodies, and the expected times on the sealed region, 4,711 waterbodies, about 1.4 times as many):

| stage | rehearsal | sealed region (expected) |
|---|---|---|
| 1. checks (hashing every file) | 0.1 min | under 1 min |
| 2. loading the frozen models | under 0.1 min | under 0.1 min |
| 3. building the region from raw files | 4.2 min | about 6 min |
| 3b. same-code check (rehearsal only) | 0.2 min | - |
| 4. forecasts | 2.6 min | about 4 min |
| 5. scoring (with 95% ranges) | 8.7 min | about 12 min |
| total | 15.9 min | about 20 to 25 min |

## After the opening

- Commit and push `artifacts/sealed/` and `artifacts/test_ledger.csv` straight away, unedited (commands above).
- The headline numbers are in `artifacts/sealed/SEALED_RESULTS.md`: the PREREG verdicts first, then the expectations, then every table. Every single score has a JSON file in `artifacts/sealed/scorecard/sealed_TEST/`.
- Publish them whatever they show. If a bar fails, say so; never refit or retune (PREREG).

## The dry run (rehearsal)

`--dry-run` runs **the identical pipeline** on a development region treated as if it were unseen: **western Victoria / SE South Australia (`wvic_sesa`)**, with every model (Tidemark, G2 and the water-balance parameters) fitted on the other development region (`nsw_cw`) only, at the same cutoff (2016-07-01). It builds wvic from its raw files with the same code, forecasts its 2016-2026 issues, and scores them into a **separate dry-run ledger** (`artifacts/sealed_dryrun/dryrun_ledger.csv`), with every model name prefixed `dryrun_`.

- **It is a rehearsal, not a result.** Its numbers are a transfer test (one development region's models judged on the other), **not the development TEST result** and not the sealed result. They do not use up the real TEST look (the real ledger is never written), and they are never used to choose or change anything. They do use western Victoria's test-year answers, so the freeze addendum counts them as TEST looks (6.16), and a rerun is a further look: rerun only to test a change to the runner.
- It refuses to run with the unlock switch on, so it proves the pipeline never touches the sealed folder. It rehearses the hash check on wvic's own files (against a list it makes on its first run) and reads, but does not enforce, the git checks.
- It also checks the "same code" claim: wvic rebuilt from raw files equals its rows in the development feature store (apart from fold numbers, and a few hundred issues near the archive's end, because a region built alone ends at its own last look).
- First time only, fit the rehearsal's models (about 23 minutes): `.venv\Scripts\python.exe scripts\20_open_sealed_region.py --prepare --dry-run`.
- Results: [`artifacts/sealed_dryrun/DRY_RUN_RESULTS.md`](../artifacts/sealed_dryrun/DRY_RUN_RESULTS.md). Options (dry run only): `--quick` (no confidence ranges, faster), `--rebuild` (ignore saved tables and forecasts), `--fresh-ledger` (set the old dry-run ledger aside, kept).

### What the rehearsal showed (Fri 2 Oct, 18:34 to 19:45 AEST)

- **Models** for the rehearsal fitted on nsw_cw only in 22.9 minutes (`--prepare --dry-run`): Tidemark L3 (trees, 3 + 3 nets, runway curve, floor, band from two inner backtests, season rating), G2, and a water balance fitted on nsw_cw's look pairs only.
- **The whole pipeline ran end to end in 15.9 minutes** (stages in the table above) with no error, and wrote [`artifacts/sealed_dryrun/DRY_RUN_RESULTS.md`](../artifacts/sealed_dryrun/DRY_RUN_RESULTS.md).
- **Same code as the development build:** wvic_sesa rebuilt from its 3,409 raw files equals its rows in the development feature store, on every one of 86 P1, 82 P2-dam and 54 P2-cell columns (901,251, 128,592 and 25,384 rows), apart from the fold numbers. The other 725 P1 rows differ only in whether their label could be determined, because wvic's last look (11 Sep 2026) is three days before the development build's last look (14 Sep 2026). Run on its own with the development balance, the water balance also reproduced the stored development values exactly.
- **Resume after a crash:** two later runs reused the saved tables and forecasts (8.6 and 8.8 minutes, nearly all scoring) and the dry-run ledger recorded `same_predictions` for every one of their 84 scores: no second look. The results page says when a run was resumed.
- **Nothing real was touched:** the real TEST ledger still has no entries; the sealed folder and the sealed SILO key were never read (the run refuses to start with the unlock switch on).
- **The opening's own refusal was tested:** `--open` without the unlock switch stops at check 1 with `REFUSED` and exit code 2.

## Files

| file | what |
|---|---|
| `scripts/20_open_sealed_region.py` | the runner (`--prepare`, `--dry-run`, `--open`) |
| `damdays/sealed/runs.py` | the opening and the dry run: target region, fit regions, ledgers, folders |
| `damdays/sealed/checks.py` | the unlock switch, read-only git checks, the committed hash list, every file's SHA-256 |
| `damdays/sealed/fitted_models.py` | the frozen TEST-setting models and their manifest |
| `damdays/sealed/region.py` | builds a region from raw files with the development code |
| `damdays/sealed/scoring.py` | the single scoring pass, PREREG verdicts and expectations |
| `damdays/sealed/report.py` | the results page |
| `artifacts/sealed_models_manifest.json` | fingerprints of the frozen models (committed before 17:30) |
| `artifacts/sealed/` | the opening's results, scorecard JSONs and run log |
| `artifacts/sealed_dryrun/` | the rehearsal's results (not the dev TEST result) |
| `tests/test_sealed_runner.py` | tests of the checks, the guards and the dry run's separation |
