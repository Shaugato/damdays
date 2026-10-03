# Build log

A plain, timestamped record of what was built and when (AEST). Commit history has the detail.

| Time | What happened |
|---|---|
| Fri 09:12 | Repo created. PREREG, DISCLOSURE and sealed-region hashes committed before any code. |
| Fri 09:15 | Pushed to GitHub (public). |
| Fri 09:16 | Package skeleton and one shared config file (all paths, dates and thresholds in one place). |
| Fri 09:20 | Step 1 started: data layer (panel, dam attributes, events, rainfall, 2 km cells, time blocks) and app scaffold, built in parallel. |
| Fri 10:04 | Step 1 done: data layer (all 7 pre-event check values reproduce exactly; reviewer re-derived all 230,926 events, 0 mismatches) and app scaffold (mock data). |
| Fri 12:22 | Step 2 done: causal features (look-ahead test: ~1.4M rows bit-identical after deleting the future), scorecard with one-look test ledger, baselines and G2 on validation (R30 skill +0.170). Leak hunt found and fixed one tiny look-ahead (<=0.004). 182 tests. |
| Fri 12:30 | Step 3 started: Tidemark core (per-dam correction, season rating, runway curve, DamDays floor and band), each built and independently reviewed. |
| Fri 14:24 | Step 3 done: Tidemark L1 on validation years (below-a-third skill +0.171, passes PREREG bars; runway curve; DamDays floor holds 90%; lender rating AUC 0.787). Each part independently reviewed. 252 tests. |
| Fri 14:30 | Step 4 started: neural-net members (L2), physics water-balance features (L3), app data exporter (real forecasts). |
| Fri 18:10 | Step 4 done: neural nets (L2) and physics (L3); app shows real forecasts. Ladder table: all rungs reproduce pre-event validation within +-0.006; highest passing rung L3 (below-a-third +0.180, dry-out +0.194). 312 tests. |
| Fri 18:20 | Step 5a started: test-setting fits (no scoring), sealed-opening runner with a dry run on a dev region, freeze addendum draft. |
| Fri 20:25 | Step 5a done: test-setting fits (nothing scored; ledger empty), one-shot sealed-opening runner (dry run on a dev region treated as unseen: below-a-third +0.201, G2 +0.191), hostile review passed. |
| Fri 20:21 | **FREEZE**: PREREG_ADDENDUM_1.md committed. Frozen rung L3 by the pre-registered rule; event build config hash 7d466291008d. |
| Fri 20:21 | **FREEZE** committed (PREREG_ADDENDUM_1.md): rung L3, config hash 7d466291008d. |
| Fri 20:36-21:00 | Development test years (2016-2026) scored ONCE: below-a-third +0.235 (G2 +0.221), dry-out +0.240, DamDays floor held 90.0%, lender rating AUC 0.81 (+0.29 over rainfall-only). All pre-registered bars pass. |
| Fri 22:05 | App switched to the frozen model (live forecasts to 14 Sep 2026; Rewind 2018-19). Pitch and video script drafted. |
| Fri 20:34-20:46 | Mentor (hackathon lead, grew up on farms): "super useful" in a drought; farmers don't open apps or emails, a weekly text is what they'd use; "%" reads as how full a dam is. |
| Sat 00:15 | Step 6 done: weekly farmer text (notify/), "My farm" view with phone preview, chances written "N in 10" everywhere, story-led video script and pitch. 401 tests. Frozen model unchanged (7d466291008d). |
| Sat 00:52 | Step 7 done: one-command publishing of the sealed result (scripts/21, rehearsed on pass, partial and fail), fresh-clone judge check (322 pass, 79 skip cleanly without data), Saturday checklist. |
| Sat 08:30-10:00 | Mentor calls (climate strategist; two more mentors). Advice: show accuracy on unseen, recent data with pictures, not AUC; show how it keeps up as the climate shifts; pick one audience (farmers); describe the target farmer precisely; state the problem in one sentence; find what already exists; give farmers a way to judge the accuracy. |
| Sat 09:10-10:20 | Step 8 done: app **Proof** view (what we said vs what happened, year by year, dam by dam; same saved test forecasts, drawn not re-scored; totals must equal the test results); sourced target-farmer profile (docs/TARGET_FARMER.md); pitch and video script v2 (farmers only; the 2018-19 replay recounted as forecasts, not dams). Frozen model unchanged (7d466291008d). |
| Sat ~09:30 | **Process note.** A reviewing agent, searching for COP31 wording, ran a recursive text search over the pre-event research folder, which also holds the sealed region's files. It was stopped after about 2 minutes, printed no matches, and no sealed contents were shown to anyone. A search does not change files, so the fingerprints are unaffected (step 20 re-checks every one before opening). Logged for completeness. |
