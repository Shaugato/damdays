# DamDays

**How many days of water does this farm dam have left?** DamDays answers that for every visible farm dam, using 38 years of satellite water history, and says how sure it is.

Climate Hack-tion 2026 · Build for 2035 · COP31 track: **Awareness Across All Areas** (helping farmers and land managers adapt, and making climate information easy to use).

> Work in progress during the event (2-4 Oct 2026). This page is updated as the build progresses.

## Start here (2-minute tour for judges and mentors)

1. **The problem.** In a drought, graziers must decide when to cart water, move stock or sell, before the dam runs dry. Banks and valuers judging farm drought risk see rainfall, but not how much water a farm has stored.
2. **What we built.** A forecast for each dam ("58% chance this dam falls below a third by 1 February; at least 60 days of water left, 9 times in 10"), plus a season-ahead water-security rating for lenders.
3. **How we know it works.** Every claim is tested on years and dams the model never saw. The test rules were written down and committed *before* any code ([PREREG.md](PREREG.md)). One whole region was downloaded but kept sealed (its file fingerprints are in [SEALED_HASHES.csv](SEALED_HASHES.csv)) and is opened once, on camera, on Saturday 17:30 AEST.
4. **Where the key logic lives:** filled in as each part is built.
5. **Reproduce the numbers:** one command, documented here once the pipeline is complete.

## Honesty notes
- Pre-event research and data download were allowed by the organisers and are disclosed in [DISCLOSURE.md](DISCLOSURE.md). All code in this repository was written during the event.
- [BUILD_LOG.md](BUILD_LOG.md) is a timestamped record of the build.

## Data
- DEA Waterbodies v3, Geoscience Australia (CC BY 4.0).
- SILO climate data, Queensland Government (CC BY 4.0).

## Licence
Copyright (c) 2026 Shaugato Paroi. All rights reserved. The source is public so the hackathon judges can review it; no licence to reuse it is granted.
