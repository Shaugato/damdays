# PREREG Addendum 2: the unseen exam is opened on Sunday

**Dated Sun 4 Oct 2026 (AEDT, UTC+11). Filed before the sealed region is opened:** this file is committed and pushed first, and the opening runner refuses to start until git is clean and pushed.

PREREG.md and PREREG_ADDENDUM_1.md are not edited: a pre-registration is never edited after it is committed, and changes are made only as dated addenda filed before the sealed region is opened (PREREG.md, first lines). This addendum makes **one** change: when the sealed region is opened. Nothing else changes.

Clocks: daylight saving began at 02:00 on Sun 4 Oct (clocks went forward to 03:00). Saturday times below are AEST (UTC+10); Sunday times are AEDT (UTC+11).

## 1. The unseen exam, in plain words

We built and checked DamDays on two farming regions: NSW Central West, and western Victoria with south-east South Australia. The unseen exam is a third farming region whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check. It is Southern Downs, the Granite Belt and New England, either side of the Queensland-NSW border: 4,711 waterbodies of about 0.5 to 10 ha (5,400 to 100,000 m², PREREG.md), one fingerprinted file each. Which of them are dam-sized and behave like farm dams is decided at the opening, by the same pre-registered filter as in the other two regions. A fingerprint is a short code worked out from a file's contents: change one byte and the code changes. We published the fingerprints of all 4,711 files in this repository when the event began ([SEALED_HASHES.csv](SEALED_HASHES.csv), Fri 2 Oct 2026 09:12 AEST), so anyone can check that the files we open are the files we downloaded.

The exam is sat once. The frozen model learned only from the other two regions, and only from data before July 2016 (the third region's own history before July 2016 sets only its local averages). It forecasts the third region's dams from July 2016 to June 2026, and those forecasts are compared with what the satellites then saw, with the same scorecard as all our other results and the pass marks we wrote down before the build began ([PREREG.md](PREREG.md)). Before it uses a single file, the opening program checks every file's fingerprint against the published list, and it stops if one differs. Whatever the result, we publish it.

## 2. The one change: the opening moves to Sunday

- **Pre-registered:** Sat 3 Oct 2026, 17:30 AEST, after the freeze addendum is committed and pushed (PREREG.md, "Data" and "Sealed region protocol"; PREREG_ADDENDUM_1.md, section 8).
- **Now:** Sun 4 Oct 2026 (AEDT), after this addendum is committed and pushed. Still once, on a screen recording, with the same command. The exact start and end times will be in [`artifacts/sealed/run_log.txt`](artifacts/sealed/run_log.txt), which the runner writes line by line as it goes (how to read it: section 7).
- **A deviation, recorded after the slot passed.** The 17:30 slot passed before this addendum was written. We did not open the sealed region then; on Saturday evening (AEST) we decided to open it after the app build. So this is a deviation from the pre-registered time, recorded after that time had passed, not a change made in advance. It is recorded before the opening, and nothing was opened in the meantime.
- **Why:** Saturday afternoon and night went on following up the mentor sessions, a check of the demo farms against aerial photos, and the app redesign. We chose to finish those first.
  - The mentor sessions ran on Saturday morning and around midday (after one on Friday evening); what they asked for, and what we changed, is in [BUILD_LOG.md](BUILD_LOG.md).
  - The aerial-photo check (about 15:20 AEST) showed that the demo farm near Dubbo was not farm dams (its waterbodies were treatment ponds, a racecourse pond, a town-edge pond and a stretch of river), so the demo moved to a farm near Mudgee, and the weekly texts, the Proof data and each dam's record were made again for it.
  - The app redesign was committed on Sun 4 Oct at 07:27 AEDT (commit adada12).
- **Why the test stays clean:** the delay changes when the files are opened, not what is done with them. The sealed files were not opened in the meantime, nothing that makes a forecast or a score has changed since the freeze (section 3), and the runner re-checks every file's fingerprint before it uses any of them.

## 3. What did not change

- **The frozen model.** Tidemark rung L3, event build config hash **`7d466291008d`** (full SHA-256 `7d466291008dccce8c06568a150b4f9a1196c5fd0ce92f98986d1676bd98ace3`; [PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md), section 2). No file under `damdays/` has changed since the freeze commit c95d5db (Fri 2 Oct 2026 20:21 AEST). Recomputed on the morning of Sun 4 Oct (AEDT), before this addendum was committed, with the recipe of `scripts/14_config_hash.py` (in memory; no file written), over the same 56 source files: the same hash.
- **The fitted models.** The three files fingerprinted in [`artifacts/sealed_models_manifest.json`](artifacts/sealed_models_manifest.json) (written Fri 2 Oct 19:08 AEST, committed with the freeze), fitted on the two development regions only, from answers final before 1 July 2016. The runner refuses to forecast with any file whose SHA-256 differs.

  | file | SHA-256 |
  |---|---|
  | `data_cache/models/TEST/tidemark_L3.pkl` (Tidemark rung L3) | `cc86a5753dde2e38e4bce8eb8e251fe6aa2ce9d452bfcdc43743f66f6344cc41` |
  | `data_cache/models/TEST/g2.pkl` (G2, the benchmark) | `e6a64fca6d0292fa0d1cd9a201b2bc20360c1009c297333fba41bec9c2598285` |
  | `data_cache/features/physics_params.pkl` (the water balance) | `62a5d21dec91c3e6132662ef561eb95e14586f040a26eb0f99780d5e09600263` |

- **The runner.** [`scripts/20_open_sealed_region.py`](scripts/20_open_sealed_region.py) and [`damdays/sealed/`](damdays/sealed/) are unchanged since c95d5db, and so are the two scripts they depend on: `scripts/13_fit_test_setting.py` (it fitted the models above) and `scripts/14_config_hash.py` (the runner uses its recipe to fingerprint the code it runs).
- **The rules.** The scoring rules and the shared scorecard, the pass marks, the kill rule and the pre-declared expectations (PREREG.md; PREREG_ADDENDUM_1.md, section 7), and the one-look ledger ([`artifacts/test_ledger.csv`](artifacts/test_ledger.csv)): each model is scored once per task; scoring it again is accepted only for byte-identical forecasts and is recorded as `same_predictions`, never as a second look.
- **The sealed files: never opened.** SEALED_HASHES.csv was committed once (commit e0e9b0b, Fri 2 Oct 09:12:19 AEST) and has not changed since. The sealed region's rainfall key is still not loaded (`damdays/data/rainfall.py` refuses it until the unlock switch is set at the opening). The test ledger has no sealed rows: its 44 rows all come from the development test years (marked `dev`, Fri 2 Oct 20:36 to 21:39 AEST). The runner re-checks every one of the 4,711 fingerprints before it uses any file.
- **The typed evaporation shape** of the sealed region and its SHA-256 ([PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md), section 3).

## 4. What changed after the freeze: display and publishing only

After the freeze, nothing that computes or scores the sealed results changed. The files that changed show or publish results, test that code, or were written by it; none of them changes how results are computed or scored. None of them is read by the opening runner (of this repository's code, it uses only `damdays/` and the recipe in `scripts/14_config_hash.py`, both unchanged), and none changes a forecast or a score.

- `scripts/11_export_app.py` (writes the app's data files): extended after the freeze to export the frozen model's test season (Rewind on 2018-19 and the Area outlook), the test-year scoreboard and today's forecasts from the live refit (commit ca6bdeb, Fri 2 Oct 22:05 AEST); later, its unseen-exam panel also carries the cautious-days block (how often "at least N days" held), with the opening's own on-target flag copied from its results, not recomputed, and the title of the scored panel takes the day from the results. Its test-season export re-read the frozen forecasts that scripts/15 scored and wrote 2 `same_predictions` rows to the ledger (Fri 2 Oct 21:39 AEST), never a new look.
- `scripts/21_publish_sealed.py` (new): after the opening, it copies the results, only rounded, into README.md, docs/PITCH.md, docs/VIDEO_SCRIPT.md and the app's data parts. Its README wording at the edge of the cautious-days target says so when the share rounds to an edge of the target range (88 to 92 in 100) but the frozen check puts it just outside; the verdict is still the frozen flag. Its wording was later aligned with the plain words used elsewhere (for example "before the build began", "no water seen"); what it copies did not change.
- `app/`: the app, changed in several commits from Fri 2 Oct 22:05 AEST to Sun 4 Oct 07:27 AEDT (ca6bdeb, 8cbdbf5, 633b7d4, fdded5c, aa755f2, 34b7e94, 5150989 and the redesign adada12), plus wording on Sunday morning.
- Docs: README.md, `docs/`, BUILD_LOG.md and DISCLOSURE.md.
- `notify/`, `scripts/16_weekly_texts.py` and `outbox/2026-10-02.json`: the weekly text, its wording and this week's texts.
- `scripts/17_proof_data.py`: the Proof data (it draws the saved test-year forecasts; nothing is re-scored).
- `scripts/18_track_record.py`: each dam's track record (it counts the saved test-year forecasts dam by dam; nothing is scored).
- `tests/`: new tests for the above; updated app-export tests (`test_app_export_real.py`) for scripts/11's new exports; clearer skip messages in two existing tests (`test_features.py`, `test_sealed_runner.py`); and a report header in `conftest.py`. Also `requirements.txt` (the exact package versions used in the build) and `.gitignore` (the local video folder).
- Output files these scripts write: `artifacts/test_results.md` and `.json`, `artifacts/test_ledger.csv` and `artifacts/scorecard/step15_test/` (scripts/15), `artifacts/track_record.md` (scripts/18), and the app's data files in `app/data/real/` (scripts/11, 16, 17, 18 and the bundle tool).

Some of these files were written before this change and still name the first planned slot, "Sat 3 Oct 17:30": `artifacts/test_results.md` (written Fri 2 Oct 21:07 AEST, a scored output that is never edited) and some titles and notes in the app's data files. The app writes its own wording instead of showing those, and the README, the app and the runbook give the Sunday opening.

One step that the freeze planned also ran after it: `scripts/15_score_test.py` scored the development test years once with the frozen model (Fri 2 Oct from 20:36 AEST; [`artifacts/test_results.md`](artifacts/test_results.md)). It is not part of the opening; its ledger rows are marked `dev`, and the opening's rows will be marked `sealed`.

## 5. Process note

On Sat 3 Oct at about 09:30 AEST, an AI agent reviewing our docs ran a recursive text search (looking for COP31 wording) over the pre-event research folder, which also holds the sealed region's files. It was stopped after about 2 minutes. It printed no matches, and no sealed contents were seen. A search like this reads files to look for words but cannot change them, so the fingerprints are unaffected, and the runner re-checks every file's fingerprint before opening. Logged for completeness (also in BUILD_LOG.md).

## 6. No other change

Everything else stays as in PREREG.md and PREREG_ADDENDUM_1.md: the data, populations, events, forecasts, splits, baselines, metrics, pass bars, expectations and the sealed region protocol. As before, nothing changes after the opening except crash fixes that do not change predictions, each logged with its time (`artifacts/sealed/CRASH_FIXES.md`).

## 7. Technical details: how to check

**Nothing that decides a forecast or a score changed since the freeze.** From the repo folder, this prints nothing:

```text
git diff --stat c95d5db HEAD -- damdays scripts/13_fit_test_setting.py scripts/14_config_hash.py scripts/20_open_sealed_region.py SEALED_HASHES.csv artifacts/sealed_models_manifest.json PREREG.md PREREG_ADDENDUM_1.md
```

and, when this addendum was written, `git diff --stat c95d5db HEAD -- scripts` listed only `scripts/11`, `15`, `16`, `17`, `18` and `21` (section 4).

**The start and end times of the opening.** `artifacts/sealed/run_log.txt` already holds the two `--prepare` runs of Fri 2 Oct 19:07 and 19:08 AEST. The opening appends to it. Its start is the line `scripts/20_open_sealed_region.py --open (run 'sealed')` of the run that goes through; its end is that run's last line, `time: total ... min`. Each line carries the laptop's clock time (AEDT on Sunday) and the minutes since the start, but no date; the date and time zone of the finish are in `finished_at` in `artifacts/sealed/sealed_results.json` and in the `time` column of each `sealed` row of `artifacts/test_ledger.csv`. A refused attempt, if any, is logged above it with `REFUSED`; a refusal stops before any water history is read or anything is scored. The commit of the raw results, straight after the run, is a second timestamp.

**What the runner prints about the addenda.** It requires a committed `PREREG_ADDENDUM*.md` that quotes the sealed evaporation SHA-256. This addendum does not repeat that hash, so that line still names `PREREG_ADDENDUM_1.md` alone. This addendum does quote the config hash, so the line for the code being run will read `quoted in ['PREREG_ADDENDUM_1.md', 'PREREG_ADDENDUM_2.md']` if the code is the frozen code.

**The runbook** for the opening, the commands and what to do if a check refuses or the run crashes: [docs/SEALED_OPENING.md](docs/SEALED_OPENING.md).
