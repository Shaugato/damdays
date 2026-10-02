"""Save and load model predictions (data_cache/preds/, rebuildable, not committed).

One file per block, task and name:
    data_cache/preds/<block>/<task>/<name>.pkl
for example data_cache/preds/VAL/P1_R30/models.pkl. Probabilities are stored
as float64 so the scorecard's prediction fingerprints never change on reload.
"""
import pandas as pd

from damdays import config

PREDS_DIR = config.CACHE_DIR / "preds"


def prediction_path(block, task, name, folder=PREDS_DIR):
    """Where one prediction table lives."""
    return folder / block / task / f"{name}.pkl"


def save_predictions(table, block, task, name, folder=PREDS_DIR):
    """Write a prediction table; probability columns (p, p_*) are stored as float64. Returns the path."""
    out = table.copy()
    for column in out.columns:
        if column == "p" or column.startswith("p_"):
            out[column] = out[column].astype("float64")
    path = prediction_path(block, task, name, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_pickle(path)
    return path


def load_predictions(block, task, name, folder=PREDS_DIR):
    """Read a prediction table written by save_predictions."""
    return pd.read_pickle(prediction_path(block, task, name, folder))
