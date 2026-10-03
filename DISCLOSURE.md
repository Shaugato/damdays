# DISCLOSURE

## Before the event (allowed by the organisers)
The organisers confirmed on the event Discord that pre-event research, including downloading and processing data and exploratory model comparisons, is allowed. Screenshot: [add path or link].

Before 09:00 Fri 2 Oct 2026 we:
- **Explored the problem and the data.** AI research agents (Claude) helped with web and desk research and with choosing the problem.
- **Ran exploratory model comparisons** on two regions (DEA Waterbodies plus SILO rainfall), to check the idea could work, and wrote down a design and the test plan. What was compared, and the results, are listed in [PREREG.md](PREREG.md) ("Pre-event research status").
- **Downloaded the public data:** DEA Waterbodies for the two development regions; the sealed test region (fingerprinted, **not opened**; see SEALED_HASHES.csv); SILO monthly rainfall 1960-2026, cropped to the study regions.
- **No research code is in this repository.** All code here was written during the event, from the written design; the commit history is the evidence. Research results are used only as check values that the event build had to reproduce.

## Datasets
- **DEA Waterbodies v3:** Geoscience Australia, CC BY 4.0.
- **SILO climate data:** Queensland Government, CC BY 4.0.

## Tools
- Python, pandas, numpy, scipy, scikit-learn, LightGBM, PyTorch (CPU), h5py, pyshp; in the app, Leaflet 1.9.4 (maps, BSD-2-Clause) with OpenStreetMap tiles (ODbL), and the Atkinson Hyperlegible Next font (Braille Institute, SIL Open Font License).
- **AI tools:**
  - Claude Code, for code generation and assistance during the event;
  - Claude research agents, for pre-event research and benchmarking.

## Team
Built by the DamDays team for Climate Hack-tion 2026: Shaugato Paroi, [Teammate 1], [Teammate 2] and [Teammate 3] (names as registered on the Junction submission). The AI tools used are listed under "Tools" above.
