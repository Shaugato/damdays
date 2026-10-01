# DISCLOSURE

## Pre-event research (allowed by the organisers)
The organisers confirmed on the event Discord that pre-event research, including data download, data processing and exploratory model analysis, is allowed. Screenshot: `[add path or link]`.

Before 09:00 Fri 2 Oct 2026 we did the following:
- **Problem research.** AI research agents (Claude) carried out web and desk research, fact audits and problem selection.
- **Pre-event benchmark** on the two development regions (DEA Waterbodies plus SILO rainfall):
  - data processing;
  - nine model families compared under one evaluation harness, with selection on the 2009-2015 validation block and the 2016-2026 development test block scored once per family;
  - a hybrid design (Tidemark v1);
  - a leakage audit.

  Results and the frozen design are summarised in PREREG.md.
- **Data downloaded before the event:**
  - DEA Waterbodies time series for the development regions;
  - the sealed test region (hashed, **not opened**, see SEALED_HASHES.csv);
  - SILO monthly rainfall 1960-2026, cropped to the study regions.
- **Code.** All research code lives outside this repository. It was not copied in. **All code in this repository was written during the event**, re-implementing a written specification; the commit history is the evidence. Research outputs are used only as check values: counts and validation scores that the event build must reproduce.

## Datasets
- **DEA Waterbodies v3:** Geoscience Australia, CC BY 4.0.
- **SILO climate data:** Queensland Government, CC BY 4.0.

## Tools
- Python, pandas, numpy, scipy, scikit-learn, LightGBM, PyTorch (CPU), h5py, pyshp and [front-end libraries].
- **AI tools:**
  - Claude Code, for code generation and assistance during the event;
  - Claude research agents, for pre-event research and benchmarking.

## Team
- Shaugato Paroi: builder (end to end).
- [Teammate 1]: fact-checking of the pitch figures.
- [Teammate 2]: buyer interview questions and outreach list.
- [Teammate 3]: video and pitch review.
