"""The TEST ledger: each model gets one look at the TEST years.

Why it exists. If ten versions of a model are scored on the test years and the
best one is reported, the test score is no longer an honest test: it has been
used to choose. The ledger makes that hard to do, even by accident.

The rules
- Every TEST scoring call is written to artifacts/test_ledger.csv: the time, the
  model, the task, the arena (dev or sealed), a fingerprint (hash) of the
  predictions and what happened. Refused calls and dry runs are written too.
- The first call for a (model, task, arena) is "new", and its predictions are kept.
- A later call goes ahead only if the predictions are byte-for-byte the same
  ("same_predictions"), e.g. to score the same forecasts on another subset.
  A table holding only some of the first call's rows is also accepted, if
  every one of those rows is identical.
- Anything else raises LedgerError before a single TEST number is computed.
- There is no override switch. If a model really must be re-scored (say a bug
  fix changed its predictions), it gets a new name. Both rows stay on the
  ledger and both must be reported.
- A reference model used for paired differences must already be on the ledger
  with exactly the predictions passed in, so a weakened copy of the benchmark
  cannot be slipped in.
- Use one name per model family ("tidemark", "g2"), not one per configuration.

The CSV is the source of truth. The saved first-call predictions (in
test_ledger_preds/, git-ignored because of their size) only allow a table
with fewer rows to be matched row by row. Without them, only an exact hash
match is accepted, which errs on the strict side.
"""
import csv
import hashlib
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from damdays import config
from damdays.evaluation.inputs import KEY

LEDGER_PATH = config.ARTIFACTS_DIR / "test_ledger.csv"
COLUMNS = ["time", "model", "task", "arena", "block", "status", "pred_hash", "baseline_hash",
           "n_rows", "subset", "refs", "note"]
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.+-]*$")


class LedgerError(RuntimeError):
    """Raised when a TEST scoring call would break the one-look rule."""


def model_key(name):
    """The ledger name of a model: trimmed and lower-case, so "G2" and "g2 " are the same model."""
    key = str(name).strip().lower()
    if not NAME_PATTERN.match(key):
        raise ValueError(f"Model name {name!r} must be letters, digits and _ . + - only.")
    return key


def prediction_hash(table, columns=("p",)):
    """A 16-character fingerprint of the predictions in `columns`.

    Rows are put in a fixed order first (uid, then issue date), so the order
    they arrive in does not matter. The uid, the issue date and the exact 8
    bytes of every probability are hashed, so any change at all, even in the
    16th decimal place or to which row a value belongs, gives a new fingerprint.
    Column names are not hashed: the same values under another name match.
    """
    rows = table.sort_values(KEY, kind="mergesort")
    digest = hashlib.sha256()
    digest.update("\n".join(rows["uid"].astype(str)).encode("utf-8"))
    dates = rows["issue_date"].to_numpy().astype("datetime64[ns]").view("int64")
    digest.update(dates.astype("<i8").tobytes())
    for column in columns:
        digest.update(b"|")
        digest.update(rows[column].to_numpy(dtype="<f8").tobytes())
    return digest.hexdigest()[:16]


def identical_floats(a, b):
    """True if two float arrays hold exactly the same bytes (not just "close")."""
    a = np.ascontiguousarray(a, dtype="<f8")
    b = np.ascontiguousarray(b, dtype="<f8")
    return a.shape == b.shape and bool(np.array_equal(a.view("<i8"), b.view("<i8")))


class Ledger:
    """The ledger file plus the saved first-call predictions."""

    def __init__(self, path=None):
        """Use the ledger at `path` (default artifacts/test_ledger.csv)."""
        self.path = Path(path) if path is not None else Path(LEDGER_PATH)
        self.store_dir = self.path.parent / (self.path.stem + "_preds")

    # -- reading and writing ---------------------------------------------------
    def entries(self):
        """Every ledger row, as text (an empty table if nothing has been scored yet)."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return pd.DataFrame(columns=COLUMNS)
        return pd.read_csv(self.path, dtype=str, keep_default_na=False)

    def first_look(self, model, task, arena):
        """The ledger row of the first ("new") TEST scoring of this model and task, or None."""
        rows = self.entries()
        hit = rows[(rows["model"] == model) & (rows["task"] == task) & (rows["arena"] == arena)
                   & (rows["status"] == "new")]
        return None if hit.empty else hit.iloc[0]

    def write(self, **fields):
        """Append one row, stamped with the current local time, to the ledger file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        row = {column: fields.get(column, "") for column in COLUMNS}
        row["time"] = datetime.now().astimezone().isoformat(timespec="seconds")
        with open(self.path, "a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)

    def saved_path(self, model, task, arena):
        """Where the first call's predictions for this model and task are kept."""
        return self.store_dir / f"{model}__{task}__{arena}.pkl"

    # -- the checks --------------------------------------------------------------
    def matches_first_look(self, first, preds):
        """(True, how) if `preds` are the predictions on the ledger, else (False, why not).

        `preds` has uid, issue_date and the probability column(s), named as
        when they were first saved.
        """
        columns = [c for c in preds.columns if c not in KEY]
        if prediction_hash(preds, columns) == first["pred_hash"]:
            return True, "identical to the first call"
        path = self.saved_path(first["model"], first["task"], first["arena"])
        if not path.exists():
            return False, "the prediction hash differs from the first call"
        saved = pd.read_pickle(path)
        joined = preds.merge(saved, on=KEY, how="left", suffixes=("", "__saved"), indicator=True)
        new_rows = int((joined["_merge"] == "left_only").sum())
        if new_rows:
            return False, f"{new_rows} rows were not in the first call"
        for column in columns:
            if not identical_floats(joined[column], joined[column + "__saved"]):
                return False, f"column {column!r} differs from the first call"
        return True, "row subset of the first call, identical values"

    def check_reference(self, ref, task, arena, ref_preds):
        """Raise LedgerError unless reference model `ref` is on the ledger with exactly these predictions."""
        first = self.first_look(ref, task, arena)
        if first is None:
            raise LedgerError(f"Reference model {ref!r} has no TEST score for {task} ({arena}). "
                              f"Score it on its own first, then use it as a reference.")
        same, why = self.matches_first_look(first, ref_preds)
        if not same:
            raise LedgerError(f"Reference model {ref!r}: {why}. Pass exactly its ledgered predictions.")

    def admit(self, *, model, task, arena, preds, refs=None, subset="", baseline_hash="", note="",
              dry_run=False):
        """Decide whether a TEST scoring call may go ahead, and write it on the ledger.

        preds: uid, issue_date and the probability column(s) of the model.
        refs:  {reference model name: its predictions, in the same shape}.
        Returns "new", "same_predictions", or "dry_run". Otherwise writes the
        refused attempt to the ledger and raises LedgerError. This is always
        called before any TEST number is computed.
        """
        refs = refs or {}
        columns = [c for c in preds.columns if c not in KEY]
        entry = dict(model=model, task=task, arena=arena, block="TEST",
                     pred_hash=prediction_hash(preds, columns), baseline_hash=baseline_hash,
                     n_rows=len(preds), subset=subset, refs=";".join(refs), note=note)
        try:
            for ref, ref_preds in refs.items():
                self.check_reference(ref, task, arena, ref_preds)
            first = self.first_look(model, task, arena)
            status, how = "new", "first TEST look"
            if first is not None:
                same, how = self.matches_first_look(first, preds)
                if not same:
                    raise LedgerError(
                        f"{model!r} was already scored on TEST for {task} ({arena}) at {first['time']} "
                        f"with different predictions ({how}). TEST is scored once per model; "
                        f"make choices on VAL. A changed model needs a new name, and both rows get reported.")
                status = "same_predictions"
        except LedgerError as err:
            self.write(**{**entry, "status": "refused_dry_run" if dry_run else "refused",
                          "note": str(err)[:300]})
            raise
        entry["note"] = f"{how}; {note}" if note else how
        if dry_run:
            self.write(**{**entry, "status": "dry_run", "note": f"would be {status}; {entry['note']}"})
            return "dry_run"
        if status == "new":
            self.store_dir.mkdir(parents=True, exist_ok=True)
            preds.to_pickle(self.saved_path(model, task, arena))
        self.write(**{**entry, "status": status})
        return status
