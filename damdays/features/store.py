"""Save and load the feature tables (data_cache/features/, rebuildable, not committed).

The P1 table is large (about 2.5 million rows), so it is stored as column
groups with the same row order. Load only what you need:

    keys  ids, time block, populations, at-risk flags, labels, B2 counts
    dam   dam-history features (including dam_rate_*) and static shape
    nbr   neighbour features R_anom, R_chg3, R_zero
    rain  rain sums and causal percentiles

    p1 = load_p1(groups=("keys", "dam"))
"""
import pickle

import pandas as pd

from damdays import config
from damdays.features.spec import P1_KEY_COLUMNS, P1_NEIGHBOUR_COLUMNS, P1_RAIN_COLUMNS

FEATURES_DIR = config.CACHE_DIR / "features"
P1_GROUPS = ("keys", "dam", "nbr", "rain")


def p1_group_columns(p1_columns):
    """Which P1 column goes in which group."""
    rest = [c for c in p1_columns if c not in set(P1_KEY_COLUMNS + P1_NEIGHBOUR_COLUMNS + P1_RAIN_COLUMNS)]
    return {"keys": P1_KEY_COLUMNS, "dam": rest, "nbr": P1_NEIGHBOUR_COLUMNS, "rain": P1_RAIN_COLUMNS}


def save_tables(tables, folder=FEATURES_DIR):
    """Write every table of build_all's output to `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    p1 = tables["p1"]
    for group, columns in p1_group_columns(p1.columns).items():
        p1[columns].to_pickle(folder / f"p1_{group}.pkl")
    tables["p2_dam"].to_pickle(folder / "p2_dam.pkl")
    tables["p2_cell"].to_pickle(folder / "p2_cell.pkl")
    tables["checkpoints"].to_pickle(folder / "checkpoints.pkl")
    with open(folder / "neighbour_grid.pkl", "wb") as f:
        pickle.dump(tables["neighbour_grid"], f)
    with open(folder / "dam_rate_prior.pkl", "wb") as f:
        pickle.dump({"prior": tables["dam_rate_prior"], "data_end": tables["data_end"]}, f)


def load_p1(groups=P1_GROUPS, folder=FEATURES_DIR):
    """The P1 issue table, with the requested column groups side by side."""
    parts = [pd.read_pickle(folder / f"p1_{group}.pkl") for group in groups]
    return pd.concat(parts, axis=1) if len(parts) > 1 else parts[0]


def load_p2(level="dam", folder=FEATURES_DIR):
    """The P2 season-rating table: level "dam" or "cell"."""
    return pd.read_pickle(folder / f"p2_{level}.pkl")
