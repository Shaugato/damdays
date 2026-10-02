"""Write scorecard results: one JSON file per result plus one markdown table row per call.

JSON, full detail, one file per (model, task, subset), overwritten on re-score:
    artifacts/scorecard/<arena>_<block>/<task>/<model>__<subset>.json
Markdown, one row per call, newest at the bottom:
    artifacts/scorecard/scorecard_<arena>_<block>.md   (score)
    artifacts/scorecard/curves_<arena>_<block>.md      (score_curve)

Numbers in the markdown are rounded for reading; the JSON keeps 5 decimals.
"""
import json
import math
from pathlib import Path

import numpy as np

from damdays import config

OUT_DIR = config.ARTIFACTS_DIR / "scorecard"


def out_dir_or_default(out_dir):
    """The folder results go to: `out_dir` if given, else artifacts/scorecard."""
    return Path(out_dir) if out_dir is not None else Path(OUT_DIR)


def clean_for_json(value):
    """Round floats to 5 decimals and turn NaN / infinity into null, recursively."""
    if isinstance(value, dict):
        return {str(k): clean_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_for_json(v) for v in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return round(float(value), 5) if math.isfinite(value) else None
    return value


def write_json(result, out_dir, kind="score"):
    """Save the full result as JSON; returns the file path."""
    folder = out_dir_or_default(out_dir) / f"{result['arena']}_{result['block']}" / result["task"]
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{result['model']}__{result['subset']}" + ("__curve" if kind == "curve" else "")
    path = folder / f"{stem}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(clean_for_json(result), handle, indent=1)
    return path


def append_markdown(result, out_dir, header, row, prefix):
    """Add one row to the markdown table for this arena and block (writing the header first if new)."""
    folder = out_dir_or_default(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{prefix}_{result['arena']}_{result['block']}.md"
    with open(path, "a", encoding="utf-8") as handle:
        if path.stat().st_size == 0:
            handle.write(header)
        handle.write(row)
    return path


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def number(value, digits=3, sign=True):
    """A number for a table cell: fixed decimals, "+" on positives, "-" for missing."""
    if value is None or not math.isfinite(value):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def interval(ci, digits=3, sign=True):
    """A [low, high] interval for a table cell, or "" when there is none."""
    if not ci:
        return ""
    return f"[{number(ci[0], digits, sign)}, {number(ci[1], digits, sign)}]"


def with_intervals(result, name, digits=3, sign=True):
    """Point value followed by its dam interval and its region-year interval (marked ry)."""
    text = number(result["point"].get(name), digits, sign)
    dam = interval(result["ci_dam"].get(name), digits, sign)
    ry = interval(result["ci_region_year"].get(name), digits, sign)
    if dam:
        text += f" {dam}"
    if ry:
        text += f" ry {ry}"
    return text


SCORE_HEADER = (
    "| time | model | task | subset | rows | events | base rate | mean p | BSS vs B0 | BSS vs B2 | AUC "
    "| cal. slope | CITL | prec. at 50% recall | paired vs reference (BSS-vs-B0 units; AUC) | ledger |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def score_row(result):
    """One markdown row for a score() result. Brackets: dam 95% interval, then region-year (ry)."""
    paired = "; ".join(
        f"{ref}: {with_intervals(result, 'd_bss_B0_vs_' + ref)}, dAUC {with_intervals(result, 'd_auc_vs_' + ref)}"
        for ref in result["refs"]) or "-"
    cells = [
        result["time"], result["model"], result["task"], result["subset"],
        str(result["rows"]["scored"]), str(result["rows"]["events"]),
        number(result["point"]["base_rate"], 3, False), number(result["point"]["mean_p"], 3, False),
        with_intervals(result, "bss_B0"), with_intervals(result, "bss_B2"),
        with_intervals(result, "auc", sign=False), with_intervals(result, "cal_slope", 2, sign=False),
        with_intervals(result, "citl", 2), number(result["point"]["prec_at_50_recall"], 3, False),
        paired, result["test_ledger"] or "not TEST",
    ]
    return "| " + " | ".join(cells) + " |\n"


CURVE_HEADER = (
    "| time | model | task | subset | horizon (days) | rows | events | BSS vs B0_h | BSS vs B2_h | AUC "
    "| cal. slope | CITL | rows with a falling curve | ledger |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")


def curve_rows(result):
    """Markdown rows for a score_curve() result, one per horizon."""
    lines = []
    for h in result["horizons"]:
        cells = [
            result["time"], result["model"], result["task"], result["subset"], str(h["horizon"]),
            str(h["rows"]), str(h["events"]),
            with_intervals(h, "bss_B0"), with_intervals(h, "bss_B2"),
            with_intervals(h, "auc", sign=False), with_intervals(h, "cal_slope", 2, sign=False),
            with_intervals(h, "citl", 2),
            number(result["monotonicity"]["share_rows_falling"], 4, False),
            result["test_ledger"] or "not TEST",
        ]
        lines.append("| " + " | ".join(cells) + " |\n")
    return "".join(lines)
