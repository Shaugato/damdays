# DISCLOSURE

## Before the event (confirmed by a hackathon mentor)
On 29 Sep 2026 we asked on the event Discord whether, before the start, we could download public datasets and do exploratory analysis on them (for example, checking which existing models suit the data), as long as all code in our submission was written during the event and all datasets were disclosed. A hackathon mentor replied that it "should be fine, as it falls under research" (screenshot, with names, handles and profile pictures hidden: [docs/img/organiser-permission.png](docs/img/organiser-permission.png)).

Before the event began (09:00 AEST, Fri 2 Oct 2026):
- **Choosing the problem.** We brainstormed ideas within the team, then used AI research agents (Claude) to check and sharpen them with web and desk research, which helped us choose the problem.
- **Checking the idea could work.** We ran exploratory model comparisons on two regions (DEA Waterbodies plus SILO rainfall) to see whether the idea could work, and wrote down a design and the test plan. In that research, AI research agents compared nine model families plus the forecasting model we went on to build (Tidemark, research config fe0ab596d1fe), chose it on the 2009-2015 validation years, and scored about ten configurations once each on the development test years (2016-2026). That is why those test years are not a clean test, and why the unseen exam exists. What was compared, and the results, are listed in [PREREG.md](PREREG.md) ("Pre-event research status").
- **Downloading the public data:**
  - DEA Waterbodies for the two development regions (NSW Central West; western Victoria / SE South Australia);
  - DEA Waterbodies for a third region (Southern Downs, Granite Belt, New England), fingerprinted and **never opened**, kept aside as the unseen exam (fingerprints: [SEALED_HASHES.csv](SEALED_HASHES.csv));
  - SILO monthly rainfall 1960-2026, cropped to the study regions.

**No code from that research is in this repository: all code and every model in this repository was written during the event.** The commit history is the evidence: the first commit (Fri 2 Oct 2026, 09:12 AEST) holds the test plan, the fingerprints and this disclosure, and no code. The research results are used only as check values that the event build had to reproduce ([PREREG_ADDENDUM_1.md](PREREG_ADDENDUM_1.md), section 1).

The unseen exam's opening moved from Sat 3 Oct to Sun 4 Oct. That change, filed before the opening, and one process note about an AI agent's text search are in [PREREG_ADDENDUM_2.md](PREREG_ADDENDUM_2.md).

## Datasets
- **DEA Waterbodies v3:** Geoscience Australia, CC BY 4.0.
- **SILO climate data:** Queensland Government, CC BY 4.0.

## Tools
- Python, pandas, numpy, scipy, scikit-learn, LightGBM, PyTorch (CPU), h5py, pyshp; in the app, Leaflet 1.9.4 (maps, BSD-2-Clause) with OpenStreetMap tiles (ODbL), and the Atkinson Hyperlegible Next font (Braille Institute, SIL Open Font License).
- **AI tools:**
  - Claude Code, for code generation and assistance during the event;
  - Claude research agents, for pre-event brainstorming support, research and benchmarking.
  - the video's voice-over is AI-generated (a Microsoft neural voice).
- Every commit in this repository is co-authored by Claude: each one carries a `Co-Authored-By` line naming Claude, visible in the commit history.

## Team
Skyrend Systems: Shaugato (team lead), Ishanee and Long. On the event platform, Shaugato is listed as "Nova Skyrend" and Long as "kono jome" (team list screenshot, with surnames and contact details hidden: [docs/img/team.png](docs/img/team.png)).
