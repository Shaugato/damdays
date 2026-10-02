"""Turn water and rain history into forecast issues, labels and causal features.

The one rule: a feature for a forecast issued on day D uses only information
that existed on day D. tests/test_no_lookahead.py proves it by rebuilding
everything with the future deleted. docs/FEATURES.md explains every feature.

Modules, in the order the build uses them:

- common        day numbers, seasons, per-dam row ranges
- checkpoints   what we knew about each dam on 1 Jan of each year (causal "full" etc.)
- neighbours    the semi-monthly grid, each dam's own climatology, neighbour summaries
- rain          rain sums and causal percentiles (window ends the month before the issue)
- dam_history   rolling features of one dam's own looks
- issues        P1 issues: at-risk flags, labels, the causal track record (B2, dam_rate)
- season        P2: the 1 Jul season rating, per dam and per 2 km cell
- spec          FEATURE_SPEC: the model input columns, and the columns that never are
- build         build_all: every table from the data layer, in one pure function
- store         save and load the tables in data_cache/features/
"""
