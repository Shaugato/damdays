# Final-day checklist (Sun 4 Oct 2026): the unseen exam, publishing, the video and the submission

Our run sheet for the last day. (The file keeps its old name so that links to it still work.) The opening's full runbook, with what each check means and what to do if one refuses or the run crashes, is [SEALED_OPENING.md](SEALED_OPENING.md). The one change to the plan, the opening moving from Sat 3 Oct 17:30 AEST to today, is filed in [PREREG_ADDENDUM_2.md](../PREREG_ADDENDUM_2.md), which is committed and pushed **before** the opening.

**Clocks.** All times today are **AEDT** (UTC+11): the clocks went forward at 02:00 this morning. Friday and Saturday times are AEST (UTC+10). The event closes **Sun 4 Oct 21:00 AEDT**; we submit by **20:00 AEDT**.

All commands run in **PowerShell**, in the repo folder:

```powershell
cd "D:\Climate Hack-tion 2026\damdays"
```

## Done

- [x] Mentor sessions (Fri evening; Sat morning and midday), noted in [BUILD_LOG.md](../BUILD_LOG.md).
- [x] About-page wording fix for the sealed panel ("Not clearly ahead of" or "Behind" G2 when the result calls for it; commit 633b7d4).
- [x] Demo farms checked against aerial photos (Sat about 15:20 AEST): Farm E (near Mudgee) is the demo farm; the Dubbo farm is set aside.
- [x] Weekly texts, Proof data and each dam's record made again for Farm E (Sat about 19:05 AEST).
- [x] App redesign: four places on a phone (My farm, Proof, Questions, More), a story-style landing on a computer, every old feature kept (commit adada12, Sun 07:27 AEDT).
- [x] GitHub Pages switched on: the live app is https://shaugato.github.io/damdays/app/ (since about 07:40 AEDT).
- [x] `video/` (the draft video pipeline) is git-ignored, so it cannot make the opening's git check refuse.
- [x] Frozen model unchanged: nothing under `damdays/`, and not `scripts/20`, the model manifest or `SEALED_HASHES.csv`, has changed since the freeze (c95d5db, Fri 20:21 AEST). The config hash still comes out `7d466291008d` (recomputed in memory on Sunday morning), and the three model files on disk still have the SHA-256 values in the manifest.
- [x] `node app/tools/check_text_port.js` printed `same` on the redesign commit (9 of 9 farms identical).
- [x] [PREREG_ADDENDUM_2.md](../PREREG_ADDENDUM_2.md) written (the opening moves to today; nothing else changes), with the updated runbook, this checklist and [DISCLOSURE.md](../DISCLOSURE.md).

## 1. Before the opening: commit and push, Addendum 2 first

- [ ] Commit the two screenshots that DISCLOSURE.md links to: `docs/img/organiser-permission.png` (a hackathon mentor's reply on Discord) and `docs/img/team.png` (the team list). Both have names, handles, a surname and profile pictures hidden; the unredacted originals are kept outside the repository and must never be committed.
- [ ] If today's wording changes touched the weekly text: `node app/tools/check_text_port.js` prints `same`.
- [ ] Commit and push, Addendum 2 in a commit of its own so its time is clear:

```powershell
git status --short                 # read every line
# Only if a test run rewrote them (the full test suite and scripts/14 do):
git checkout -- artifacts/config_hash.json artifacts/lookahead_test.json artifacts/leakage_hunt.json
git add PREREG_ADDENDUM_2.md
git commit -m "PREREG Addendum 2: the unseen exam opens Sun 4 Oct (filed before the opening)"
git push
git add -A DISCLOSURE.md README.md BUILD_LOG.md docs app notify outbox scripts tests artifacts/track_record.md
git status                         # anything still listed? decide on it before committing
git commit -m "Final-day docs: disclosure, runbook, checklist"
git push
git status                         # must say: nothing to commit, working tree clean
```

- [ ] Never stage a change to `PREREG.md`, `PREREG_ADDENDUM_1.md`, `SEALED_HASHES.csv`, `damdays/` or `scripts/20_open_sealed_region.py`. If `git status` lists one of them, undo it with `git checkout -- <file>`.

**From now until the opening, do not run** anything that rewrites a committed file:
- the full test suite (it rewrites `artifacts/lookahead_test.json` and `artifacts/leakage_hunt.json`);
- `scripts/14_config_hash.py` (it rewrites the date in `artifacts/config_hash.json`; the opening computes the hash itself);
- `scripts/11`, `16`, `17` or `18` (they rewrite the app data, the outbox, the Proof data or the track record);
- `scripts/20` in any mode other than the opening itself: `--dry-run` is another look at test years, and `--prepare` rewrites the model fingerprints.

## 2. Just before: clean git

- [ ] `git status` says `nothing to commit, working tree clean`.
- [ ] `git status -sb` starts with `## main...origin/main` and no `[ahead 1]`: the last commit is on GitHub.
- [ ] Free space on D: is at least 3 GB (`Get-PSDrive D`). The opening saves its tables and forecasts there (under 1 GB) and needs 2 GB free to save the forecasts.
- [ ] Optional: post the commit (`git log -1 --oneline`) on the event Discord as an outside timestamp.

## 3. Set up

- [ ] Laptop on power. Close other programs. Notifications off. Windows Update paused, so nothing restarts the laptop.
- [ ] The screen recorder saves to **C:** (plenty of space), not D:. The taskbar clock is on screen.
- [ ] Open a **new** PowerShell window, so no setting from earlier is left over. Do not set `DAMDAYS_RAW`: the default raw-data location is the right one.

## 4. Start the screen recording (about 15 minutes before the run)

- [ ] Record the whole screen from now until the published results show in the app (about an hour). Keep the raw file: it is the evidence. The video uses a short sped-up cut.
- [ ] On camera: `cd` into the repo, then `git log -1 --oneline` and `git status`.
- [ ] On camera, say once why it is later than pre-registered: "We pre-registered Saturday at 17:30. We moved it to today and filed that change before opening, in Addendum 2. The data is still sealed, and the script checks every file's fingerprint before it opens anything."

## 5. The opening

```powershell
git status                                   # must say "nothing to commit, working tree clean"
$env:DAMDAYS_OPEN_SEALED = "yes"             # the unlock switch (this window only)
.venv\Scripts\python.exe scripts\20_open_sealed_region.py --open
```

- [ ] The checks pass: unlock switch on; git clean and pushed; `SEALED_HASHES.csv` committed once (e0e9b0b, Fri 09:12 AEST); `100% match: 4,711 of 4,711 files`; the three model files match the manifest; the evaporation SHA-256 quoted in `PREREG_ADDENDUM_1.md`; the code fingerprint `7d466291008d` quoted in `PREREG_ADDENDUM_1.md` and `PREREG_ADDENDUM_2.md`.
- [ ] It runs for about 20 to 25 minutes (build, forecasts, scoring). Keep recording.
- [ ] At the end, **read the verdicts out as they are**: the pass marks for Tidemark and G2, the lender-rating mark and kill rule, each expectation.
- [ ] If it prints `REFUSED` or `CRASHED`: keep recording and follow [SEALED_OPENING.md](SEALED_OPENING.md), "If a check refuses" or "If it crashes".

## 6. Commit the raw results, unedited (straight after)

```powershell
Remove-Item Env:DAMDAYS_OPEN_SEALED          # switch off again
git add artifacts/sealed artifacts/test_ledger.csv
git commit -m "Sealed region opened: raw results, unedited"
git push
```

- [ ] Note the start and end times from `artifacts/sealed/run_log.txt` (the opening's lines come after the two `--prepare` runs of Friday): they go in the README, the video's beat 8 and the BUILD_LOG.

## 7. Publish the results everywhere (scripts/21, about 10 minutes later)

```powershell
.venv\Scripts\python.exe scripts\21_publish_sealed.py --check     # preview: changes nothing
.venv\Scripts\python.exe scripts\21_publish_sealed.py             # README, PITCH, VIDEO_SCRIPT and the app
git diff --stat
git add -A README.md docs/PITCH.md docs/VIDEO_SCRIPT.md app/data app/sw-version.js
git status                                   # expect the new app/data/real/first.<hash>.js added, the old one deleted
git commit -m "Sealed results published (scripts/21_publish_sealed.py)"
git push
```

- [ ] Read the block `WHAT TO SAY ON CAMERA` out loud. It is written the same way whether the result is a pass, a partial pass or a fail.
- [ ] The `git add` line above is the one scripts/21 prints. It stages the whole `app/data` folder and `app/sw-version.js`: the rebuild writes a new `first.<hash>.js`, deletes the old one, rewrites `parts.js` and restamps `sw-version.js`, and the app reads the parts, not `bundle.js`.
- [ ] If it prints `CHECK THE APP'S WORDING` about "% less forecast error" on a negative skill: that warning is expected and harmless, because the redesigned About already says "more error" (it looks for the old "% more" words). Don't mention it on camera. Any other `CHECK THE APP'S WORDING`: say so on camera and fix the About page wording afterwards.
- [ ] If it prints `REFUSED`, nothing was changed: read the reason. If it prints `APP NOT UPDATED`, the docs are done; fill the app with the command it prints.
- [ ] The README's sealed section heading is "The unseen exam: the result"; the "Details below" link scripts/21 writes still lands there, through the anchor kept above it.
- [ ] Never hand-edit the text between the `SEALED:START` and `SEALED:END` markers: scripts/21 fills it.

## 8. GitHub Pages and a quick look at the live app

- [ ] Pages updates itself from the push: the repository's Actions tab shows "pages build and deployment"; when it is green (a few minutes), the site is up.
- [ ] Hard-reload https://shaugato.github.io/damdays/app/ : Proof's "Unseen exam" card and About's sealed panel show the scores. Then stop the recording.
- [ ] **Phone size** (a phone, or a phone-sized window): four tabs (My farm, Proof, Questions, More); My farm opens on Farm E (near Mudgee) with the same text as `outbox/2026-10-02.json`; a dam with no water at its last look reads "no water seen", never "dry"; chances read "N in 10"; "%" is only how full; no MOCK banner; no Farm D (near Dubbo) anywhere.
- [ ] **Computer size**: the story-style landing, with the real text in a phone frame, and every view one click away. Old links still land in the right place: `#runway`, `#rewind`, `#rating`, `#faq`, `#about`.

## 9. The video ([VIDEO_SCRIPT.md](VIDEO_SCRIPT.md): 2:00 at most)

Script v4: farmers only, ten beats, 240 words, Farm E in the text. The shots follow its shot list. Not used: Rewind, the Area outlook, the About page and the `test_results.md` pass-mark table.

- [ ] Cut shot S8 from the opening recording: about 15 seconds, sped up, the clock visible, ending on Proof's "Unseen exam" card.
- [ ] Record the app shots, now that the app shows the result: S3 (Runway, whole region), S5 (My farm on Farm E, the whole 3 km circle, Dam 1's card; keep the circle at 3 km so Dam 5 stays in), S6 and S7 (Proof, parts 1 and 2).
- [ ] Make the two cards: S2 ("Who it's for") and S9 (COP31).
- [ ] Phone shots S1, S4 and S10; record the voice-over (240 words, calm pace; about 1:56 with pauses).
- [ ] Check the beat-8 line and captions that scripts/21 wrote into VIDEO_SCRIPT.md against `artifacts/sealed/SEALED_RESULTS.md` (scripts/21 still calls it "beat 5"; burn in only the first two caption lines). Fill beat 8's "[the opening's date and time, from the recording]".
- [ ] If the `video/` pipeline is used: rebuild `video/beats.json` from script v4 first (it is still draft 1, with the Dubbo farm).
- [ ] First full cut with captions, 2:00 or less. Tick "Before recording" and "Recording checklist" in VIDEO_SCRIPT.md.
- [ ] **By 16:00:** export a 1080p MP4 and upload it with a link that opens without signing in.

## 10. Last docs pass, then commit and push

- [ ] DISCLOSURE.md, "Tools": add the video, screen-recording and voice tools (and any music). The two screenshots in `docs/img/`, if not added yet.
- [ ] README final pass (outside the `SEALED` markers): the lines that still say the opening comes "after the app build" or was "pre-registered for Sat 3 Oct" get the opening's date and time (from the run log) and a link to Addendum 2; drop the note beside "Latest status" about the first planned time; link the opening's screen recording in "Opened once". docs/ONE_PAGER.md has no markers: add the headline result there by hand, in one sentence.
- [ ] A last BUILD_LOG entry: Addendum 2, the opening's start and end times, the publish, the video.
- [ ] Commit and push; Pages updates itself.

## 11. Junction submission (by 20:00 AEDT)

- [ ] Project name, one-line summary and the written pitch ([PITCH.md](PITCH.md), now with the result).
- [ ] Repository: https://github.com/Shaugato/damdays
- [ ] Live app: https://shaugato.github.io/damdays/app/
- [ ] Tools, datasets and AI used: from [DISCLOSURE.md](../DISCLOSURE.md).
- [ ] **By 18:00:** the video link in the draft. Open every link (video, repository, app) in a private browser window.
- [ ] **By 20:00 AEDT: final submit** (the event closes at 21:00 AEDT).

## Checked before the opening

First on Sat 3 Oct (about 00:45 AEST), and again on Sunday morning (AEDT) for the first three points. Everything the opening checks, except the unlock switch and the sealed files themselves, which were not touched:

- The config hash of the code is `7d466291008d`, the fingerprint frozen in [PREREG_ADDENDUM_1.md](../PREREG_ADDENDUM_1.md). No file under `damdays/`, and not `scripts/20`, Addendum 1 or the model manifest, has changed since the freeze commit (c95d5db, Fri 20:21 AEST).
- The three frozen model files on disk have the SHA-256 values in [artifacts/sealed_models_manifest.json](../artifacts/sealed_models_manifest.json) and in Addendum 1 (rung L3, fitted on both development regions, cutoff 2016-07-01), so `--prepare` does not need to run again.
- `SEALED_HASHES.csv` was committed once (e0e9b0b, Fri 2 Oct 09:12:19 AEST) and never changed: 4,711 files listed.
- Addendum 1 quotes the sealed evaporation SHA-256 (`f886f419...`) and the code fingerprint.
- The opening writes only to `artifacts/sealed/`, `artifacts/test_ledger.csv` and `data_cache/`. The first two are not git-ignored, so the commit straight after it picks them up; `data_cache/` is git-ignored, so it never makes git unclean.
- `scripts/21_publish_sealed.py` on a made-up results file (never the real one): its tests pass, including the refusals (no results yet, a dry run, scores that disagree with the app's files). A full run on a copy of the docs and the real app data wrote a pass, a partial pass and a fail correctly, and left the real files unchanged.
