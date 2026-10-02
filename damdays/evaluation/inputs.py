"""Check and tidy a prediction table before anything is scored.

The scorecard trusts nothing. A duplicated row, a probability of 1.3, a label
of 0.5 or a missing baseline is an error, not something to fix quietly. All of
these checks run before any number is computed and, on TEST, before the
ledger is asked. A failed check therefore costs nothing.
"""
import numpy as np
import pandas as pd

KEY = ["uid", "issue_date"]   # one forecast = one dam (or cell) on one issue date


def tidy_keys(df):
    """A copy with uid and region as text and issue_date as a plain date-time.

    Dates are stored at nanosecond resolution so that tables built by
    different code paths still join and hash identically.
    """
    table = df.copy()
    if "uid" in table:
        table["uid"] = table["uid"].astype(str)
    if "region" in table:
        table["region"] = table["region"].astype(str)
    if "issue_date" in table:
        table["issue_date"] = pd.to_datetime(table["issue_date"]).astype("datetime64[ns]")
    return table


def require_columns(table, columns, hint=""):
    """Raise if any of `columns` is missing from the table."""
    missing = [c for c in columns if c not in table.columns]
    if missing:
        raise ValueError(f"Missing column(s) {missing}. {hint}".strip())


def check_unique_keys(table, what):
    """Raise if any (uid, issue_date) appears twice: each forecast must be one row."""
    duplicated = table.duplicated(KEY)
    if duplicated.any():
        example = table.loc[duplicated, KEY].iloc[0].tolist()
        raise ValueError(f"{int(duplicated.sum())} duplicated (uid, issue_date) rows in the {what}, e.g. {example}")


def same_values(a, b):
    """True where two columns agree (two blanks also count as agreeing)."""
    both_blank = a.isna() & b.isna()
    return (a.eq(b) | both_blank).to_numpy(dtype=bool)


def join_baselines(table, baselines):
    """Add columns such as p_B0 and p_B2 from a separate table, matched on uid + issue_date.

    Columns the prediction table already has are not replaced: the two copies
    must agree exactly, which catches a mis-join. Every prediction row must
    find its baseline row; extra baseline rows (other blocks, other dams) are ignored.
    """
    if baselines is None:
        return table
    extra = tidy_keys(baselines)
    require_columns(extra, KEY, "The baselines table needs uid and issue_date.")
    check_unique_keys(extra, "baselines table")
    merged = table.merge(extra, on=KEY, how="left", suffixes=("", "__baseline"), indicator=True)
    unmatched = int((merged["_merge"] == "left_only").sum())
    if unmatched:
        raise ValueError(f"{unmatched} prediction rows have no matching row in the baselines table.")
    for column in [c for c in extra.columns if c not in KEY and c in table.columns]:
        twin = column + "__baseline"
        disagree = ~same_values(merged[column], merged[twin])
        if disagree.any():
            raise ValueError(f"Column {column!r} differs between the predictions and the baselines "
                             f"table on {int(disagree.sum())} rows.")
        merged = merged.drop(columns=twin)
    return merged.drop(columns="_merge")


def check_probabilities(table, columns):
    """Raise unless every value in these columns is a finite number from 0 to 1."""
    for column in columns:
        values = pd.to_numeric(table[column], errors="coerce").to_numpy(dtype=float)
        bad = ~np.isfinite(values) | (values < 0) | (values > 1)
        if bad.any():
            raise ValueError(f"Column {column!r} must hold probabilities in [0, 1]; "
                             f"{int(bad.sum())} rows do not (blank, infinite, text or out of range).")
        table[column] = values


def check_labels(table, columns):
    """Raise unless every label is 1 (event), 0 (no event) or blank (answer not known)."""
    for column in columns:
        values = pd.to_numeric(table[column], errors="coerce").to_numpy(dtype=float)
        given = ~pd.isna(table[column]).to_numpy()
        bad = (given & np.isnan(values)) | (~np.isnan(values) & (values != 0) & (values != 1))
        if bad.any():
            raise ValueError(f"Column {column!r} must hold 1 (event), 0 (no event) or blank; "
                             f"{int(bad.sum())} rows do not.")
        table[column] = values


def prepare_table(df, *, required, probability_columns, label_columns, flag_columns=(), baselines=None):
    """A checked, tidied copy of a prediction table, sorted by uid and issue date.

    Sorting means the result never depends on the order rows were passed in.
    """
    table = tidy_keys(df)
    require_columns(table, KEY + ["region"], "Every table needs uid, issue_date and region.")
    check_unique_keys(table, "prediction table")
    table = join_baselines(table, baselines)
    require_columns(table, list(required) + list(probability_columns) + list(label_columns),
                    "Baselines (p_B0, p_B2 ...) can be columns or joined with baselines=; "
                    "a reference model 'X' needs a column p_X.")
    require_columns(table, list(flag_columns), "The requested subset needs these yes/no columns.")
    if table["region"].isna().any():
        raise ValueError("Column 'region' has blank values.")
    check_probabilities(table, probability_columns)
    check_labels(table, label_columns)
    return table.sort_values(KEY, kind="mergesort").reset_index(drop=True)


def check_expected_keys(scored, expected_keys):
    """Raise unless the scored rows are exactly the expected (uid, issue_date) rows.

    The official issue table says which rows a task must be scored on.
    Passing it here stops a model from being scored on a convenient part of
    them (missing rows), and catches subset flags that disagree (extra rows).
    """
    expected = tidy_keys(expected_keys)
    require_columns(expected, KEY, "expected_keys needs uid and issue_date.")
    check_unique_keys(expected, "expected_keys table")
    joined = scored[KEY].merge(expected[KEY], on=KEY, how="outer", indicator=True)
    missing = int((joined["_merge"] == "right_only").sum())
    extra = int((joined["_merge"] == "left_only").sum())
    if missing or extra:
        raise ValueError(f"Scored rows differ from expected_keys: {missing} expected rows have no "
                         f"prediction or label, {extra} scored rows were not expected.")
