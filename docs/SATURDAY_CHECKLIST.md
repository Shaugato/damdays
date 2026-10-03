# Saturday checklist: the sealed opening, then the submission

The run sheet for Sat 3 Oct and Sun 4 Oct 2026. The opening's full runbook (what each check means, what to do if one refuses or the run crashes) is [SEALED_OPENING.md](SEALED_OPENING.md). This page is the order of the day.

**Clocks.** Saturday times are **AEST** (UTC+10). Clocks jump forward at **02:00 on Sunday** (to 03:00), so Sunday times are **AEDT** (UTC+11). The laptop and phone change by themselves; an alarm keeps its clock time. The event closes **Sun 4 Oct 21:00 AEDT**; we submit by **20:00 AEDT**.

All commands run in **PowerShell**, in the repo folder:

```powershell
cd "D:\Climate Hack-tion 2026\damdays"
```

## Morning (until 15:00)

- [ ] **Mentor chats.** Note anything to change in the app, pitch or video in [BUILD_LOG.md](../BUILD_LOG.md).
- [ ] **Review the app** (double-click `app/index.html`, then a hard reload): My farm opens on Farm D, then Runway, Rewind (1 Nov 2018, 1 Jan 2019, 1 Mar 2019), Proof (ten dots on the diagonal; ten bars above zero; the "Unseen exam" card not yet opened), Rating (2018-19) and About. No MOCK banner. The About page shows the sealed panel as not yet opened.
- [ ] **Decide on the About-page wording fix** (`app/js/views/about.js`, not part of the frozen code). Today the sealed panel always says "Ahead of the pre-registered benchmark model G2", and writes a negative skill as "-2.0% less". The fix (ready, 2 lines) makes it say "Not clearly ahead of" or "Behind", and "% more", when the result calls for it; a pass reads exactly as before. Apply it before 15:00, or read the About page after the opening and say any mismatch on camera.
- [ ] Only changes outside `damdays/` today. The model code is frozen (code fingerprint `7d466291008d`).

## 15:00 Final commit and push

This morning's work is not committed yet; the opening refuses to start until it is. **Untracked files count too**: the opening's git check lists every modified, added, deleted or untracked file that is not git-ignored. As of Sat 3 Oct, 10:30 AEST, `git status` lists these (the Proof view, the target-farmer profile, script and pitch v2, and the draft video pipeline):

```powershell
git add .gitignore README.md docs/PITCH.md docs/VIDEO_SCRIPT.md docs/SATURDAY_CHECKLIST.md docs/TARGET_FARMER.md
git add app/DATA_CONTRACT.md app/README.md app/css/style.css app/data/real/README.md app/data/real/bundle.js app/data/real/proof.json app/index.html app/js/data.js app/js/main.js app/js/views/about.js app/js/views/proof.js app/tools/build_bundle.py
git add scripts/17_proof_data.py scripts/21_publish_sealed.py tests/test_proof_data.py tests/test_publish_sealed.py
git add BUILD_LOG.md               # only if you added notes this morning
git status                         # anything still listed? decide on it before committing
git commit -m "Proof view, target-farmer profile, script and pitch v2 (farmers only)"
git push
git status
```

- [ ] **Decide on `video/`** (the draft video pipeline: `assemble.py`, `render.py`, `shots.py`, `voice.py`, `common.py`, `beats.json`, `assets/`). It is untracked, so it alone would make the opening refuse. Either commit it (`git add video`; its renders in `video/out/` are git-ignored and stay out) or move it out of the repo folder until after the opening. `video/beats.json` is draft 1 and out of date with script v2.

- [ ] `git status` says `nothing to commit, working tree clean`. If it lists a file you changed on purpose, add it, commit and push again. If you did not mean to change it: `git checkout -- <file>`.

**From now until the opening, do not run** anything that rewrites a committed file:
- the full test suite (it rewrites `artifacts/lookahead_test.json` and `artifacts/leakage_hunt.json`);
- `scripts/14_config_hash.py` (it rewrites the date in `artifacts/config_hash.json`; the opening computes the fingerprint itself);
- `scripts/11` or `scripts/16` (they rewrite the app data and the outbox);
- `scripts/20` in any mode: `--open` before 17:30 adds lines to the opening's log, `--dry-run` is another look at test years, and `--prepare` rewrites the model fingerprints.

## 16:45 Clean git

- [ ] `git status` says `nothing to commit, working tree clean`.
- [ ] `git status -sb` starts with `## main...origin/main` and no `[ahead 1]`: the last commit is on GitHub.
- [ ] Free space on D: is at least 3 GB (`Get-PSDrive D`; 7 GB on Friday night). The opening saves its tables and forecasts there (under 1 GB) and needs 2 GB free to save the forecasts.
- [ ] Optional: post the commit (`git log -1 --oneline`) on the hackathon Discord as an outside timestamp.

## 17:00 Set up

- [ ] Laptop on power. Close other programs. Notifications off. Windows Update paused for the evening, so nothing restarts the laptop.
- [ ] The screen recorder saves to **C:** (plenty of space), not D:. The taskbar clock is on screen.
- [ ] Open a **new** PowerShell window, so no setting from earlier is left over. Do not set `DAMDAYS_RAW`: the default raw-data location is the right one.

## 17:15 Start the screen recording

- [ ] Record the whole screen from now until the results are pushed (about 18:30). Keep the raw file: it is the evidence. The video uses a short sped-up cut.
- [ ] On camera: `cd` into the repo, then `git log -1 --oneline` and `git status`.

## 17:30 The opening

```powershell
git status                                   # must say "nothing to commit, working tree clean"
$env:DAMDAYS_OPEN_SEALED = "yes"             # the unlock switch (this window only)
.venv\Scripts\python.exe scripts\20_open_sealed_region.py --open
```

- [ ] The checks pass: unlock switch on; git clean and pushed; `SEALED_HASHES.csv` committed once (e0e9b0b, Fri 09:12); `100% match: 4,711 of 4,711 files`; the three model files match the manifest; the evaporation SHA-256 and the code fingerprint `7d466291008d` are quoted in `PREREG_ADDENDUM_1.md`.
- [ ] It runs for about 20 to 25 minutes (build, forecasts, scoring). Keep recording.
- [ ] At the end, **read the verdicts out as they are**: the pass marks for Tidemark and G2, the lender-rating mark and kill rule, each expectation.
- [ ] If it prints `REFUSED` or `CRASHED`: keep recording and follow [SEALED_OPENING.md](SEALED_OPENING.md), "If a check refuses" or "If it crashes".

## About 17:55 Commit the raw results, unedited

```powershell
Remove-Item Env:DAMDAYS_OPEN_SEALED          # switch off again
git add artifacts/sealed artifacts/test_ledger.csv
git commit -m "Sealed region opened: raw results, unedited"
git push
```

## About 18:05 Publish the results everywhere (scripts/21)

```powershell
.venv\Scripts\python.exe scripts\21_publish_sealed.py --check     # preview: changes nothing
.venv\Scripts\python.exe scripts\21_publish_sealed.py             # README, PITCH, VIDEO_SCRIPT and the app
git diff --stat
git add README.md docs/PITCH.md docs/VIDEO_SCRIPT.md app/data/real/scoreboard.json app/data/real/bundle.js app/data/datasets.js
git commit -m "Sealed results published (scripts/21_publish_sealed.py)"
git push
```

- [ ] Read the block `WHAT TO SAY ON CAMERA` out loud. It is written the same way whether the result is a pass, a partial pass or a fail.
- [ ] If it prints `CHECK THE APP'S WORDING`, say so on camera and fix the About page wording afterwards.
- [ ] If it prints `REFUSED`, nothing was changed: read the reason. If it prints `APP NOT UPDATED`, the docs are done; fill the app with the command it prints.
- [ ] Open the app's About page: the sealed panel shows the scores. Then stop the recording.

## 21:00 Junction submissions open: start the draft

- [ ] Project name, one-line summary and the written pitch ([PITCH.md](PITCH.md), now with the sealed result).
- [ ] Repository: https://github.com/Shaugato/damdays
- [ ] Tools, datasets and AI used: from [DISCLOSURE.md](../DISCLOSURE.md).
- [ ] Leave the video link for Sunday. Save as a draft.
- [ ] Optional, your decision: switch on GitHub Pages so judges can open the app online (3 steps in [app/DEPLOY.md](../app/DEPLOY.md)).

## The video ([VIDEO_SCRIPT.md](VIDEO_SCRIPT.md): 2:00 at most)

Script v2 (Sat 3 Oct): farmers only, ten beats, 237 words. The shots below follow its shot list. Not used any more: Rewind, Rating, the About page and the `test_results.md` pass-mark table.

**Saturday evening (AEST)**
- [ ] Cut shot S8 from the opening recording: about 15 seconds, sped up, the clock visible, ending on Proof's "Unseen exam" card.
- [ ] Record the app shots, now that the app shows the sealed result: S3 (Runway, whole region), S5 (My farm, cropped tight on Farm D's seven dams, Dam 2's card), S6 and S7 (Proof, parts 1 and 2).
- [ ] Make the two cards: S2 ("Who it's for") and S9 (COP31).
- [ ] Check the beat-8 line and captions that scripts/21 wrote into VIDEO_SCRIPT.md against `artifacts/sealed/SEALED_RESULTS.md` (scripts/21 still calls it "beat 5"; burn in only the first two caption lines).
- [ ] Rebuild `video/beats.json` from script v2 once the video platform is chosen (it is still draft 1).

**02:00 Sunday: clocks jump forward to 03:00. From here, times are AEDT.**

**Sunday (AEDT)**
- [ ] Morning: phone shots S1, S4 and S10; record the voice-over (237 words, calm pace; about 1:55 with pauses).
- [ ] By 13:00: first full cut with captions, 2:00 or less. Tick "Before recording" and "Recording checklist" in VIDEO_SCRIPT.md.
- [ ] By 16:00: export 1080p MP4; upload it with a link that opens without signing in. Add the video and screen-recording tools to DISCLOSURE.md. Final README pass (the results are in; the "Work in progress" line). A last BUILD_LOG entry. Commit and push.
- [ ] By 18:00: add the video link to the Junction draft. Open every link (video, repository, app) in a private browser window.
- [ ] **By 20:00 AEDT: final submit** (the event closes at 21:00 AEDT).

## Checked the night before (Sat 3 Oct, about 00:45 AEST)

Everything the opening checks, except the unlock switch and the sealed files themselves, which were not touched:

- `scripts/14_config_hash.py` prints `7d466291008d`, the fingerprint frozen in [PREREG_ADDENDUM_1.md](../PREREG_ADDENDUM_1.md). No file under `damdays/`, and not `scripts/20`, the addendum or the model manifest, has changed since the freeze commit (c95d5db, Fri 20:21).
- The three frozen model files on disk have the SHA-256 values in [artifacts/sealed_models_manifest.json](../artifacts/sealed_models_manifest.json) and in the addendum (rung L3, fitted on both development regions, cutoff 2016-07-01), so `--prepare` does not need to run again.
- `SEALED_HASHES.csv` was committed once (e0e9b0b, Fri 2 Oct 09:12:19) and never changed: 4,711 files listed.
- The addendum quotes the sealed evaporation SHA-256 (`f886f419...`) and the code fingerprint.
- The last commit (a087c76) is on GitHub. Git is not clean yet: 12 prep files (the list under 15:00) are uncommitted. That is the only check that would refuse today.
- The opening writes only to `artifacts/sealed/`, `artifacts/test_ledger.csv` and `data_cache/`. The first two are not git-ignored, so the 17:55 commit picks them up; `data_cache/` is git-ignored, so it never makes git unclean.
- `scripts/21_publish_sealed.py` on a made-up results file (never the real one): its 18 tests pass, including the refusals (no results yet, a dry run, scores that disagree with the app's files). A full run on a copy of the docs and the real app data wrote a pass, a partial pass and a fail correctly, and left the real files unchanged.
