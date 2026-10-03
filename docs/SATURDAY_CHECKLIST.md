# Saturday checklist: the build, the sealed opening, then the submission

The run sheet for Sat 3 Oct and Sun 4 Oct 2026. The opening's full runbook (what each check means, what to do if one refuses or the run crashes) is [SEALED_OPENING.md](SEALED_OPENING.md). This page is the order of the night.

**Changed on Saturday afternoon.** The sealed opening was pre-registered for 17:30 AEST. It moved to tonight, after the app build, because of the mentor calls and the design work ([BUILD_LOG.md](../BUILD_LOG.md)). Nothing else about it changes: the data stays sealed until the opening, and the opening checks every sealed file against its published fingerprint before it reads anything. The demo farm is now **Farm E (near Mudgee)**: the aerial-photo check found the Dubbo demo farm's waterbodies were treatment ponds, a racecourse pond, a town-edge pond and a stretch of river, so it was set aside.

**Clocks.** Saturday times are **AEST** (UTC+10). Clocks jump forward at **02:00 on Sunday** (to 03:00), so Sunday times are **AEDT** (UTC+11). The laptop and phone change by themselves; an alarm keeps its clock time. If the opening runs past 02:00, read the clock on the recording as it is. The event closes **Sun 4 Oct 21:00 AEDT**; we submit by **20:00 AEDT**.

All commands run in **PowerShell**, in the repo folder:

```powershell
cd "D:\Climate Hack-tion 2026\damdays"
```

## Done earlier on Saturday

- [x] Mentor calls, noted in [BUILD_LOG.md](../BUILD_LOG.md).
- [x] About-page wording fix for the sealed panel ("Not clearly ahead of" or "Behind" G2 when the result calls for it; commit 633b7d4).
- [x] Demo farms checked against aerial photos (about 15:20): Farm E is the demo farm; the Dubbo one is set aside.
- [x] Weekly texts, Proof data and each dam's record made again for Farm E (about 19:05; texts still dated Fri 2 Oct).

## 1. After the app build: review it

- [ ] **Phone size** (double-click `app/index.html`, then a hard reload; or a phone-sized window). Four tabs: My farm, Proof, Questions, More. No MOCK banner. No Farm D (near Dubbo) anywhere.
  - **My farm** opens on Farm E (near Mudgee). The text reads "Dam 1 ~80% full: at least 68 days before it drops below 1/3" and "Dam 3: no water seen". Tap Dam 1: ~80% full at the 13 Sep look, at least 68 days, 1 in 10 by 12 Dec, the DamDays day (9 Dec) marked on the six-month chart, and "held 380 of 428 times". Dam 5's card says "Runs wetter than similar dams". **Change** picks another demo farm, sets a homestead on the map and changes the circle size.
  - **Proof**: ten dots near the diagonal; ten bars above zero; the "Unseen exam" card not yet opened; **Rewind: the 2018-19 drought** on 1 Nov 2018, 1 Jan 2019 and 1 Mar 2019, with Reveal and the tally.
  - **More**: Runway (the region map, 272 of the 894 already below a third), the Area outlook (2018-19), About (the sealed panel not yet opened).
  - A 0% dam reads "no water seen", never "dry". Chances read "N in 10". "%" is only how full.
- [ ] **Computer size**: the story-style landing, with the real text in a phone frame, and every view one click away.
- [ ] `node app/tools/check_text_port.js` prints `same`.
- [ ] Old links still open the right place: `#runway`, `#rewind`, `#rating`, `#faq`, `#about`.
- [ ] Only changes outside `damdays/` tonight. The model code is frozen (code fingerprint `7d466291008d`).

## 2. Commit and push everything (before the opening)

The opening refuses to start until git is clean and pushed. **Untracked files count too**: its git check lists every modified, added, deleted or untracked file that is not git-ignored. The redesign adds many new files under `app/css/` and `app/js/`.

```powershell
git status --short                 # read every line
# Only if a test run rewrote them (the full test suite and scripts/14 do):
git checkout -- artifacts/config_hash.json artifacts/lookahead_test.json artifacts/leakage_hunt.json
git add app notify outbox scripts tests docs README.md DISCLOSURE.md BUILD_LOG.md artifacts/track_record.md
git status                         # anything still listed? decide on it before committing
git commit -m "App redesign, Farm E as the demo farm, docs"
git push
git status
```

- [ ] **Decide on `video/`** (the draft video pipeline: `assemble.py`, `render.py`, `shots.py`, `voice.py`, `common.py`, `beats.json`, `assets/`), if it is still untracked: it alone would make the opening refuse. Either commit it (`git add video`; its renders in `video/out/` are git-ignored and stay out) or move it out of the repo folder until after the opening. `video/beats.json` is draft 1 and out of date (it still uses the Dubbo farm).
- [ ] `git status` says `nothing to commit, working tree clean`. If it lists a file you changed on purpose, add it, commit and push again. If you did not mean to change it: `git checkout -- <file>`.

**From now until the opening, do not run** anything that rewrites a committed file:
- the full test suite (it rewrites `artifacts/lookahead_test.json` and `artifacts/leakage_hunt.json`);
- `scripts/14_config_hash.py` (it rewrites the date in `artifacts/config_hash.json`; the opening computes the fingerprint itself);
- `scripts/11` or `scripts/16` (they rewrite the app data and the outbox);
- `scripts/20` in any mode other than the opening itself: `--dry-run` is another look at test years, and `--prepare` rewrites the model fingerprints.

## 3. Just before: clean git

- [ ] `git status` says `nothing to commit, working tree clean`.
- [ ] `git status -sb` starts with `## main...origin/main` and no `[ahead 1]`: the last commit is on GitHub.
- [ ] Free space on D: is at least 3 GB (`Get-PSDrive D`). The opening saves its tables and forecasts there (under 1 GB) and needs 2 GB free to save the forecasts.
- [ ] Optional: post the commit (`git log -1 --oneline`) on the hackathon Discord as an outside timestamp.

## 4. Set up

- [ ] Laptop on power. Close other programs. Notifications off. Windows Update paused for the night, so nothing restarts the laptop.
- [ ] The screen recorder saves to **C:** (plenty of space), not D:. The taskbar clock is on screen.
- [ ] Open a **new** PowerShell window, so no setting from earlier is left over. Do not set `DAMDAYS_RAW`: the default raw-data location is the right one.

## 5. Start the screen recording (about 15 minutes before the run)

- [ ] Record the whole screen from now until the results are pushed (about an hour). Keep the raw file: it is the evidence. The video uses a short sped-up cut.
- [ ] On camera: `cd` into the repo, then `git log -1 --oneline` and `git status`.
- [ ] On camera, say once why it is later than pre-registered: "We planned 17:30; mentor calls and the app build pushed it to tonight. The data is still sealed, and the script checks every file's fingerprint before it opens anything."

## 6. The opening

```powershell
git status                                   # must say "nothing to commit, working tree clean"
$env:DAMDAYS_OPEN_SEALED = "yes"             # the unlock switch (this window only)
.venv\Scripts\python.exe scripts\20_open_sealed_region.py --open
```

- [ ] The checks pass: unlock switch on; git clean and pushed; `SEALED_HASHES.csv` committed once (e0e9b0b, Fri 09:12); `100% match: 4,711 of 4,711 files`; the three model files match the manifest; the evaporation SHA-256 and the code fingerprint `7d466291008d` are quoted in `PREREG_ADDENDUM_1.md`.
- [ ] It runs for about 20 to 25 minutes (build, forecasts, scoring). Keep recording.
- [ ] At the end, **read the verdicts out as they are**: the pass marks for Tidemark and G2, the lender-rating mark and kill rule, each expectation.
- [ ] If it prints `REFUSED` or `CRASHED`: keep recording and follow [SEALED_OPENING.md](SEALED_OPENING.md), "If a check refuses" or "If it crashes".

## 7. Commit the raw results, unedited (straight after)

```powershell
Remove-Item Env:DAMDAYS_OPEN_SEALED          # switch off again
git add artifacts/sealed artifacts/test_ledger.csv
git commit -m "Sealed region opened: raw results, unedited"
git push
```

## 8. Publish the results everywhere (scripts/21, about 10 minutes later)

```powershell
.venv\Scripts\python.exe scripts\21_publish_sealed.py --check     # preview: changes nothing
.venv\Scripts\python.exe scripts\21_publish_sealed.py             # README, PITCH, VIDEO_SCRIPT and the app
git diff --stat
git add -A README.md docs/PITCH.md docs/VIDEO_SCRIPT.md app/data app/sw-version.js
git commit -m "Sealed results published (scripts/21_publish_sealed.py)"
git push
```

- [ ] Read the block `WHAT TO SAY ON CAMERA` out loud. It is written the same way whether the result is a pass, a partial pass or a fail.
- [ ] The `git add` line above stages the whole `app/data` folder and `app/sw-version.js`: the rebuild writes a new `first.<hash>.js`, deletes the old one, rewrites `parts.js` and restamps `sw-version.js`, and the app on Pages reads the parts, not `bundle.js`. (scripts/21 prints this same line.)
- [ ] If it prints `CHECK THE APP'S WORDING` about "% less forecast error" on a negative skill: that warning is expected and harmless, because the redesigned About already says "more error" (it looks for the old "% more" words). Don't mention it on camera. Any other `CHECK THE APP'S WORDING`: say so on camera and fix the About page wording afterwards.
- [ ] If it prints `REFUSED`, nothing was changed: read the reason. If it prints `APP NOT UPDATED`, the docs are done; fill the app with the command it prints. (If the redesign split the app's data into parts, check that Proof's "Unseen exam" card and About's panel both show the scores after a hard reload.)
- [ ] Open the app: Proof's "Unseen exam" card and About's sealed panel show the scores. Then stop the recording.
- [ ] The README's sealed section heading is now "Sealed region: the unseen exam"; the "Details below" link scripts/21 writes still lands there, through the anchor kept above it.

## 9. Junction submission (open since Sat 21:00)

- [ ] Project name, one-line summary and the written pitch ([PITCH.md](PITCH.md), now with the sealed result).
- [ ] Repository: https://github.com/Shaugato/damdays
- [ ] Tools, datasets and AI used: from [DISCLOSURE.md](../DISCLOSURE.md).
- [ ] Leave the video link for Sunday. Save as a draft.
- [ ] GitHub Pages, so judges can open the app online: 3 steps in [app/DEPLOY.md](../app/DEPLOY.md).

## The video ([VIDEO_SCRIPT.md](VIDEO_SCRIPT.md): 2:00 at most)

Script v3 (Sat 3 Oct evening): farmers only, ten beats, 239 words, Farm E in the text. The shots below follow its shot list. Not used: Rewind, the Area outlook, the About page and the `test_results.md` pass-mark table.

**After the opening (Saturday night)**
- [ ] Cut shot S8 from the opening recording: about 15 seconds, sped up, the clock visible, ending on Proof's "Unseen exam" card.
- [ ] Record the app shots, now that the app shows the sealed result: S3 (Runway, whole region), S5 (My farm on Farm E, the whole 3 km circle, Dam 1's card; keep the circle at 3 km so Dam 5 stays in), S6 and S7 (Proof, parts 1 and 2).
- [ ] Make the two cards: S2 ("Who it's for") and S9 (COP31).
- [ ] Check the beat-8 line and captions that scripts/21 wrote into VIDEO_SCRIPT.md against `artifacts/sealed/SEALED_RESULTS.md` (scripts/21 still calls it "beat 5"; burn in only the first two caption lines). Fill beat 8's "[the opening's date and time, from the recording]".
- [ ] Rebuild `video/beats.json` from script v3 once the video platform is chosen (it is still draft 1).

**02:00 Sunday: clocks jump forward to 03:00. From here, times are AEDT.**

**Sunday (AEDT)**
- [ ] Morning: phone shots S1, S4 and S10; record the voice-over (239 words, calm pace; about 1:56 with pauses).
- [ ] By 13:00: first full cut with captions, 2:00 or less. Tick "Before recording" and "Recording checklist" in VIDEO_SCRIPT.md.
- [ ] By 16:00: export 1080p MP4; upload it with a link that opens without signing in. Add the video and screen-recording tools to DISCLOSURE.md. Final README pass (the results are in; the "Work in progress" line and the "now planned for Saturday night" lines). A last BUILD_LOG entry. Commit and push.
- [ ] By 18:00: add the video link to the Junction draft. Open every link (video, repository, app) in a private browser window.
- [ ] **By 20:00 AEDT: final submit** (the event closes at 21:00 AEDT).

## Checked the night before (Sat 3 Oct, about 00:45 AEST)

Everything the opening checks, except the unlock switch and the sealed files themselves, which were not touched:

- `scripts/14_config_hash.py` prints `7d466291008d`, the fingerprint frozen in [PREREG_ADDENDUM_1.md](../PREREG_ADDENDUM_1.md). No file under `damdays/`, and not `scripts/20`, the addendum or the model manifest, has changed since the freeze commit (c95d5db, Fri 20:21).
- The three frozen model files on disk have the SHA-256 values in [artifacts/sealed_models_manifest.json](../artifacts/sealed_models_manifest.json) and in the addendum (rung L3, fitted on both development regions, cutoff 2016-07-01), so `--prepare` does not need to run again.
- `SEALED_HASHES.csv` was committed once (e0e9b0b, Fri 2 Oct 09:12:19) and never changed: 4,711 files listed.
- The addendum quotes the sealed evaporation SHA-256 (`f886f419...`) and the code fingerprint.
- The opening writes only to `artifacts/sealed/`, `artifacts/test_ledger.csv` and `data_cache/`. The first two are not git-ignored, so the commit straight after it picks them up; `data_cache/` is git-ignored, so it never makes git unclean.
- `scripts/21_publish_sealed.py` on a made-up results file (never the real one): its tests pass, including the refusals (no results yet, a dry run, scores that disagree with the app's files). A full run on a copy of the docs and the real app data wrote a pass, a partial pass and a fail correctly, and left the real files unchanged.
