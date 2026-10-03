# Build log

What we built during Climate Hack-tion 2026, and when, from the first commit to now. It is written for judges: it shows the build happened during the event, in order, with every honest note kept.

- **Times** are Sydney time: AEST (UTC+10) until the clocks went forward at 02:00 on Sun 4 Oct, AEDT (UTC+11) after. Commit times come from `git log --date=iso`. Every commit was pushed to the public GitHub repository within seconds of being made, except the first (committed 09:12, pushed 09:15 AEST).
- **Numbers** come from the results files linked beside them. Numbers in brackets are the exact scores, for anyone who wants them; [docs/SCORECARD.md](docs/SCORECARD.md) explains each one.
- **Words.** "%" only ever means how full a dam is: the share of its usual full water surface that the satellite saw wet, not its depth. The dams are farm dams big enough for the satellites to see (about 0.5 to 5 ha). **The unseen exam** is a third farming region whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check.

## Friday 2 October (AEST)

### 09:12-09:18 · Test rules first, then code
- **09:12** First commit, with no code in it: the pre-registration ([PREREG.md](PREREG.md): what we would build, how it would be tested, and the pass marks), [DISCLOSURE.md](DISCLOSURE.md), and the fingerprints of the unseen exam's 4,711 files ([SEALED_HASHES.csv](SEALED_HASHES.csv)). PREREG.md's header gives 09:00 AEST, the planned time; the commit itself is 09:12:19.
- **09:15** Pushed to GitHub (public).
- **09:16-09:18** Package skeleton; one shared config file holding every path, date and threshold from the pre-registration; README with a reading path for judges.

### 09:20-10:04 · Data, and an app skeleton beside it
- Data layer: each dam's satellite water record, dam details, drought events, rainfall, 2 km cells and the time blocks (training, validation, test). Every loader refuses the unseen exam's folder.
- All 7 check values from our pre-event research reproduce exactly, for example 5,227,589 clear satellite looks and 1,683 dam-sized waterbodies, mostly farm dams ([artifacts/data_checks.json](artifacts/data_checks.json)). An independent re-derivation of the drought events found 0 mismatches. 38 tests.
- App skeleton: a static site with no server, on a documented data contract ([app/DATA_CONTRACT.md](app/DATA_CONTRACT.md)), running on clearly labelled mock data.

### 10:04-12:22 · Inputs that cannot peek at the future
- Forecast inputs built only from what was known on each forecast date. The look-ahead test rebuilds them with the future deleted and compares about 1.4 million rows: 0 differences ([artifacts/lookahead_test.json](artifacts/lookahead_test.json)).
- **LEAK-1, found and fixed.** We then hunted for leaks on purpose and found one small one. A regional rate used as an input (how often dams fell below a third after past forecasts) counted some forecasts from Sep-Dec 2008 whose answers were only known in Jan-Apr 2009. It touched 22,156 validation forecasts from Jan-Apr 2009 and moved that input by at most 0.004. We fixed it and added a test that keeps it fixed; our pre-event research had the same flaw. Recorded in [docs/FEATURES.md](docs/FEATURES.md) and [PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md) (section 6, item 1).
- A scorecard with a one-look ledger: each model can be scored on the test years only once per task, and every look is recorded.
- The pre-registered reference model, G2, on the validation years (2009-2015): all three pass marks met (+0.170) ([artifacts/val_results.md](artifacts/val_results.md)).

### 12:30-14:24 · The DamDays model, first version (Tidemark L1)
- A correction for each dam; the runway curve (the chance of dropping below a third within 30, 60, 90 and 180 days); the DamDays number, "at least N days before it drops below a third", built to hold 9 times in 10; the season band; and a season rating for 2 km areas.
- On the validation years only: pass marks met (+0.171), and the DamDays number held 900 times in 1,000 ([artifacts/val_tidemark_L1.md](artifacts/val_tidemark_L1.md)). Each part was reviewed independently. 252 tests. Plain guide: [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

### 14:30-18:12 · Neural nets, a water balance, real forecasts in the app
- Neural nets (L2): one reads each dam's last 24 months; others read the table of inputs.
- Water balance (L3): each dam's water budget with Bureau of Meteorology evaporation, a Kalman filter, and 20 past years' rain as scenarios. The look-ahead test now covers both, and it caught the leaks we planted to test it.
- The app shows real forecasts (satellite looks up to 14 Sep 2026).
- **18:10** Ladder table: every model rung, L0 to L3, reproduces its pre-event validation score to within 0.006. The highest rung that passes both pre-registered rules is L3, the full model (+0.180) ([artifacts/ladder_val.md](artifacts/ladder_val.md)). 312 tests.

### 18:20-20:21 · Freeze
- Test-setting models fitted (finished 18:57), learning only from answers known before 1 July 2016. Nothing scored.
- The opening runner for the unseen exam (`scripts/20_open_sealed_region.py`) built and rehearsed 19:04-19:44 on one of our own regions treated as unseen (+0.201; G2 +0.191). The rehearsal used its own ledger, and Addendum 1 counts it as a look at that region's test years (section 6, item 16).
- **20:21 FREEZE** (commit `c95d5db`, pushed 20:21:54). [PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md) picks rung L3 by the pre-registered rule and records the model code's fingerprint, config hash `7d466291008d`. The model code (`damdays/`) and the opening runner have not changed since.

### ~20:30-20:50 · Mentor: hackathon lead (chat)
- **Feedback:** the drought pain is real; farmers read a weekly text, not apps or emails; "%" reads as how full a dam is; explain the testing plainly.
- **What we changed:** the weekly text became the product (Sat 00:12). "%" only ever means how full, the headline is days left, and chances are written "N in 10". Results are in plain words, and the sealed region became "the unseen exam".

### 20:36-22:05 · Ten years it never trained on, scored once
- **20:36** The frozen model was scored once on the test years, July 2016 to June 2026: ten years it never trained on (it learned only from data before July 2016) ([artifacts/test_results.md](artifacts/test_results.md)).
  - Will a dam drop below a third within 90 days? Its chances had nearly a quarter less error than guessing the usual rate for the region and month (+0.235, range +0.224 to +0.248). On exactly the same forecasts the reference model G2 scored +0.221; the gap, +0.014, stays above zero across its whole range.
  - The DamDays number held 900 times in 1,000 (of 729,749 checked; the typical N was about 60 days).
  - The season rating put a 2 km area that ran dry above one that did not about 8 times in 10, against about 5 in 10 for rainfall alone.
  - Every pre-registered pass mark was met. One ledger entry per model and task; an independent recompute matches.
  - **Honest caveat:** our pre-event research had looked at these years, so they may flatter the model a little (the pre-registration estimates by about 0.005 to 0.01). The clean check is the unseen exam.
- **22:05** The app runs on the frozen model: live forecasts (satellite looks to 14 Sep 2026), Rewind to the 2018-19 drought, and the test-year scoreboard. Results written in plain language; first drafts of the pitch and the video script.

## Saturday 3 October (AEST)

### 00:12-00:52 · The weekly text
- **00:12** `notify/`: one text per farm per week that fits in one SMS. Its headline is each dam's days left ("at least N days before it drops below a third"), and "%" only means how full. A spec with 10 worked examples ([notify/MESSAGE_SPEC.md](notify/MESSAGE_SPEC.md)); 55 tests. The app's "My farm" view shows the text on a phone, matching the Python version character for character.
- **00:13** `requirements.txt` with the exact package versions.
- **00:52** One command publishes the unseen exam's result (`scripts/21_publish_sealed.py`), rehearsed on made-up pass, partial and fail results; it refuses rehearsal data. A fresh-clone check for judges: 322 tests pass, and 79 skip cleanly without the data. Deployment guide and a checklist for Saturday.

### 08:30-09:15 · Mentor: climate strategy (call, then a follow-up message)
- **Feedback:** show accuracy on unseen, recent data, with pictures; show how it keeps up as the climate shifts; show it dam by dam; pick one audience (farmers) and describe the target farmer precisely.
- **What we changed:** the app's **Proof** view (10:21), which shows each of the ten test years on its own, dry and wet, and each dam; a sourced profile of the target farmer ([docs/TARGET_FARMER.md](docs/TARGET_FARMER.md)); pitch and video script v2 for farmers only.

### 09:10-11:20 · Proof, and a record farmers can judge
- **10:21** **Proof** view: what we said against what happened, year by year and dam by dam, drawn as pictures from the saved test forecasts. Nothing is re-scored: `scripts/17_proof_data.py` refuses to write if its totals differ from the test results.
- **11:20** Each dam's **track record** (`scripts/18_track_record.py`): how often our days-left number held on that dam over the ten years it never trained on. Nothing new is scored, and its totals must equal the test results. Over the 929 dams in the app with at least 5 checked forecasts, the typical dam held 912 times in 1,000, and 101 dams held less than 8 times in 10; poor records are shown as they are ([artifacts/track_record.md](artifacts/track_record.md)).
- **11:20** A one-page brief ([docs/ONE_PAGER.md](docs/ONE_PAGER.md)) and what already exists, checked live that morning ([docs/WHAT_EXISTS.md](docs/WHAT_EXISTS.md)).

### ~09:30 · Process note: an accidental text search
An AI agent (one of the AI tools listed in [DISCLOSURE.md](DISCLOSURE.md)), looking for COP31 wording, ran a recursive text search over our pre-event research folder, which also holds the unseen exam's files. It was stopped after about 2 minutes. It printed no matches, and no sealed contents were seen. A search changes no files, and the opening runner re-checks every file's fingerprint before it opens anything. Logged for completeness.

### ~10:00 and ~12:00 · Mentors: two startup mentors (two calls)
- **Feedback:** state the problem in one sentence; say which COP31 priority and which farms; show what already exists and what is new; give farmers a way to judge the accuracy; think about who else could use dam forecasts; explain how a satellite can tell the amount of water when dams differ in depth.
- **What we changed:** the one-pager states the problem in one sentence, the farms, the COP31 priority (Awareness Across All Areas: helping farmers adapt) and what is new; the what-exists page names the closest tools; the track record lets a farmer judge us on their own dams. On depth: the one-pager says plainly that the satellite sees how much of a dam is wet, not how deep it is, and the pitch and the app define "%" the same way; the size of dam the satellites can see is stated (14:30). Other users of dam forecasts get one "next" line in the pitch, so the story stays on farmers.

### 14:30 · Wording corrected
- "Ten years it never trained on" replaced "never saw": our pre-event research had looked at the test years, so "never saw" was too strong. Only the unseen exam is a region the model never saw. The size of dam the satellites can see (about 0.5 to 5 ha) is now stated wherever "every farm dam" could read as full coverage.

### ~15:20 · Demo farms checked against aerial photos
- The Dubbo demo farm (Farm D, the farm in the weekly text and the video script) was not a farm: none of its 7 waterbodies was clearly a farm dam. They included three cells of one treatment-pond complex, a pond at a racecourse, a pond at the town edge and a stretch of the Macquarie River. They had passed the filter that picks dam-sized waterbodies, which looks at size, shape and water history, not land use.
- The hero farm became **Farm E, near Mudgee**, whose 5 dams are all farm dams on the photos. Farm D was set aside. All 10 demo farms' 3 km circles were checked (dam by dam for 5 of them); the circles of Farms C, G, H, I and J also take in mine, wetland, town or treatment-works waterbodies, and the README's limits say so.
- Two more checks that afternoon. A dam reading 0% means the satellite saw no water at its last clear look, not that the dam is dry: at the latest looks, 148 of the 272 dam-sized waterbodies below a third in NSW Central West read 0%, and one look can be wrong. And the six-month chance and the days-left number come from two models, so the six-month chart now marks the DamDays day (done in the redesign).

### 17:30 · The pre-registered opening time passes; the opening moves
The unseen exam was pre-registered to open on Sat 3 Oct at 17:30 AEST. We did not open it then. On Saturday evening we decided to open it after the app build, because following up the mentor sessions, the aerial-photo check of the demo farms and the app redesign took the afternoon and evening. A pre-registration is never edited, so the move is recorded in a new dated addendum, [PREREG_ADDENDUM_2.md](PREREG_ADDENDUM_2.md), committed before the opening. The data stays unopened. Before it reads anything, the opening runner checks every one of the 4,711 files against its published fingerprint and the frozen models against theirs.

### ~19:05 · Weekly texts, Proof and records remade with Farm E
- Weekly texts, Proof data and track records made again with Farm E as the hero (scripts 16, 17 and 18; the texts are still dated Fri 2 Oct). A dam reading 0% now says "no water seen". The record is in plain words: "over the last 10 years, our days-left number held 1,640 of 1,767 times on these 5 dams". Farm D is out of the demo farms, the outbox and Proof's dam-by-dam panel.
- No dam's forecast or record changed, and the app still writes exactly the same texts as the Python.

### Evening to Sun 07:27 AEDT · App redesign
- Built from a mockup we agreed on. On a phone, a clean app with four places: **My farm, Proof, Questions, More**. On a computer, a short story of what DamDays is, with the real weekly text in a phone frame, the farm from above, why now, COP31 and what is new.
- Every feature of the old app is kept, restyled: the demo-farm picker, the homestead point and circle size, the farm map, the weekly text and its longer version, each dam's card (how full, days left, chance by date, six-month chart with the DamDays day marked, water since 1988, its correction note, our record on it season by season), the region map, Rewind to the 2018-19 drought (now inside Proof), Proof, the area outlook and About. A new Questions page. We checked old against new, feature by feature.
- The unseen exam's panel will also show how the DamDays number did there, using the opening's own on-target check (`scripts/11` and `scripts/21`; display only).
- The app can be installed on a phone, and its first screen loads only a small part of the data.

## Sunday 4 October (AEDT from 02:00)

### 07:27-07:40 · Redesign committed and live
- **07:27** Redesign committed (`adada12`) and pushed. 501 tests pass. Frozen model unchanged (`7d466291008d`).
- **~07:40** Live on GitHub Pages: <https://shaugato.github.io/damdays/app/>

### Morning · Docs and wording brought up to date for judges
- A final wording pass over the docs (this log included), the app, the weekly text and the wording of the Proof data and the publishing script. Display and wording only.
- The two screenshots DISCLOSURE.md links to were added with names, handles and profile pictures hidden.

## What changed after the freeze

`git diff --stat c95d5db HEAD -- damdays/ scripts/20_open_sealed_region.py` prints nothing: the model code (fingerprinted by config hash `7d466291008d`) and the opening runner are exactly as frozen on Fri 2 Oct at 20:21 AEST. After the freeze we added the one-time scoring of the test years (`scripts/15_score_test.py`, run Fri 20:36 AEST, as the pre-registration says) and code that shows or publishes results, never how they are computed or scored: the app's data export (`scripts/11`), the weekly text (`scripts/16` and the wording in `notify/`), the Proof data (`scripts/17`), the track record (`scripts/18`), the publishing step (`scripts/21`), the app and the docs.

## Sunday 4 October (AEDT): the unseen exam

| Time | What happened |
|---|---|
| 09:19:00 | Addendum 2 committed and pushed on its own (the opening moves to Sunday; nothing else changes), then the final docs. |
| 09:19:52 | **The unseen exam opened**, once, with `scripts/20_open_sealed_region.py --open`, on a screen recording. All 4,711 sealed files matched their published fingerprints; the frozen models matched their manifest. |
| 09:21-10:16 | Built the third region from raw files (2,008 dam-sized waterbodies), forecast it with the frozen models, scored it once on the shared ledger. |
| 10:16:04 | **Result: all 4 pre-registered pass marks met, and all 6 pre-declared expectations inside their ranges.** Below a third within 90 days: skill +0.183 (expected +0.15 to +0.23), ahead of the benchmark G2 (+0.172); fully dry +0.173 (G2 +0.149); the cautious days held 882 times in 1,000 (on target, 880 to 920); the area outlook picked the right 2 km area 8 times in 10, rainfall alone 5 in 10. |
| 10:20 | Raw results committed unedited (`artifacts/sealed/`, the ledger), then published into the README, pitch, video script and the app with `scripts/21_publish_sealed.py`. |

## Next

The video, then submission.
