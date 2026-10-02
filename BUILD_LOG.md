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
