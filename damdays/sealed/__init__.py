"""The sealed-region opening: run once, Sat 3 Oct 2026 17:30 AEST, by scripts/20_open_sealed_region.py.

PREREG "Sealed region protocol": a third region (Southern Downs / Granite Belt / New England) was
downloaded and hashed before the event and never opened. It is opened once, after the model is
frozen; every file's SHA-256 is checked first; the frozen models (fitted on the development regions'
issues before 2016-07-01) forecast its issues from 2016-07-01 to 2026-06-30; G2 and Tidemark are
scored once; every number is published whatever it shows. docs/SEALED_OPENING.md is the runbook.

Read in this order:
    runs.py           the two runs through the same code: the OPENING, and the DRY_RUN rehearsal on a
                      development region treated as unseen (separate ledger; not the dev TEST result)
    checks.py         before anything sealed is parsed: the unlock switch, git clean and pushed, the
                      committed hash list, and every sealed file's SHA-256 (a 100% match on 4,711 files)
    fitted_models.py  the frozen TEST-setting models (Tidemark, G2, the water-balance parameters),
                      fingerprinted in a manifest committed before the opening
    region.py         the region's tables, built from its raw files by the same functions as the
                      development build (data layer, features, physics, the nets' months)
    scoring.py        one scoring pass with the shared scorecard; the PREREG pass bars, the kill rule
                      and the pre-declared expectations
    report.py         the results page (markdown) and its JSON
"""
