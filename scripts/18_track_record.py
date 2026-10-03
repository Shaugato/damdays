"""Step 18: each dam's track record (app/data/real/track_record.json): a way for a farmer to judge our accuracy on
their own dam.

Run from the repo folder, after steps 13, 15, 11, 16 and 17 (seconds):
    .venv/Scripts/python.exe scripts/18_track_record.py            # write track_record.json, rebuild bundle.js
    .venv/Scripts/python.exe scripts/18_track_record.py --check    # build and check everything; write nothing

Why: a mentor (Sat 3 Oct) said the forecast is "the lifeline of farmers", so farmers need a way to judge
its accuracy themselves. An average over every dam does not show that. So for each dam the app shows, this step counts
how often our cautious days-left number held on THAT dam over the last 10 years (the founder's plain words):

    "Our record on this dam: held 198 of 222 times."

How (the "?" tip, notify.message.TRACK_RECORD_HOW): we re-ran our forecasts for July 2016 to June 2026 using only
data from before July 2016, then checked each one against what the dam really did. In the code's terms: the frozen
model learned only from data before July 2016, then made a forecast at every clear satellite look from July 2016 to
June 2026 (scripts/13), the backtest. Those years were scored once by scripts/15; this step only re-reads the saved
forecasts and their answers, to count them per dam. It scores nothing on the TEST ledger.

What is counted, for each forecast (one per clear satellite look, when the dam had refilled and was above a third):
  THE PROMISE   "at least N days before it drops below a third", N as the app and the text show it: whole days,
                rounded down, and "6 months+" (180+) judged at 180 days (floor_shown; test_results.json
                "floor.shown_all"). It HELD if the dam stayed above a third for at least N days. It is JUDGED only if the
                archive watched the dam for at least N days after the forecast (to 15 Aug 2026: the archive's end,
                14 Sep, less 30 days to confirm a fall), whatever happened: the rule of
                damdays.evaluation.coverage.floor_coverage.
                Forecasts with no known answer (label_ok false: too few looks) are left out, as in scripts/15.
  "LIKELY"      forecasts that gave a chance of 5 in 10 or more of falling below a third within 90 days (rounded
                as the text rounds it), with a known answer: how many were followed by a fall within those 90 days.
  SEASONS       the July-June years with at least one judged forecast.
A dam with fewer than 5 judged forecasts shows "not enough history" (notify.message.TRACK_RECORD_MIN).

Forecasts a week or two apart often share one dry spell, so a dam's misses tend to come in runs: a few misses can
be one bad season. The page says so, and lists the seasons the misses came in.

Which dams: the dams the app shows, all in the two development regions: every dam on the app's map
(app/data/real/forecasts.json, NSW Central West) and every dam of the demo farms in western Victoria / SE South
Australia (app/data/real/farms.json). Nothing from the sealed region is read.

What it reads (and checks)
  data_cache/preds/TEST/tidemark/L3_p1.pkl   the frozen model's test forecasts; must match step 13's fingerprint
  data_cache/features/p1_keys.pkl            the answers (R30 labels, days to the next fall); same fingerprint as
                                             step 13 read; dam_rate_prior.pkl for the archive's end date
  artifacts/test_results.json                over EVERY dam of both regions, the per-dam counts must add up to step
                                             15's "as shown in the app" floor result (forecasts judged, share held,
                                             by July-June year), or nothing is written
  app/data/real/proof.json                   the "likely" calls on the headline set must add up to the Proof view's
                                             "5 in 10" to "more than 9 in 10" groups (forecasts and falls)
  app/data/real/forecasts.json, farms.json   the app's dams and the demo farms

Output: app/data/real/track_record.json (format: app/DATA_CONTRACT.md, "track_record.json") and
artifacts/track_record.md (the same numbers as a page), then app/tools/build_bundle.py packs it into bundle.js.
Tests: tests/test_track_record.py. Nothing under damdays/ is changed.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from notify.message import (NAME_IF_IN_TEN, TRACK_RECORD_HOW, TRACK_RECORD_MIN, TRACK_RECORD_SPAN,  # noqa: E402
                            TRACK_RECORD_YEARS)

FIT_SUMMARY = REPO / "artifacts" / "test_setting_fit_summary.json"
TEST_RESULTS = REPO / "artifacts" / "test_results.json"
APP_DIR = REPO / "app" / "data" / "real"
OUT = APP_DIR / "track_record.json"
PAGE = REPO / "artifacts" / "track_record.md"
BUNDLE_TOOL = REPO / "app" / "tools" / "build_bundle.py"
FORECASTS_FILE = "data_cache/preds/TEST/tidemark/L3_p1.pkl"
ANSWER_FILE = "data_cache/features/p1_keys.pkl"

KIND = "R30"                       # "below a third" (the floor's event, uncertainty.FLOOR_KIND)
CAP_DAYS = 180                     # "6 months+" is judged at 180 days (uncertainty.FLOOR_DISPLAY_MAX_DAYS)
MIN_JUDGED = TRACK_RECORD_MIN      # fewer judged forecasts than this: "not enough history"
LIKELY_IN_TEN = NAME_IF_IN_TEN     # "likely": a chance shown as 5 in 10 or more (the text always names such a dam)
FIRST_YEAR, LAST_YEAR = 2016, 2025 # July-June years of the backtest
REGION_WORDS = {"nsw_cw": "NSW Central West", "wvic_sesa": "western Victoria / SE South Australia"}
# The app's "?" tip next to "Our record on this dam" (plain words: no "backtest", "frozen" or "never trained on").
TIP = (TRACK_RECORD_HOW + " Forecasts a week or two apart often share one dry spell, so misses tend to come in runs: "
       "a few misses can be one bad season.")


# ===========================================================================
# Counting (pure functions: tested in tests/test_track_record.py)
# ===========================================================================
def judge_floors(floor_days, days_to_event, followup_days, cap_days=CAP_DAYS):
    """Each forecast's promise: (judged, held), two boolean arrays.

    The rule of damdays.evaluation.coverage.floor_coverage, row by row:
      floor_days     N, "at least N days above a third" (above cap_days it is judged at cap_days)
      days_to_event  days from the forecast to the next fall below a third; NaN or inf if none was seen
      followup_days  days after the forecast in which a fall would show up in the archive
    JUDGED when the archive watched the dam for at least N days, whatever happened (decided by the follow-up
    alone, never by the outcome). HELD when judged and the dam did not fall below a third before day N.
    """
    floor = np.minimum(np.asarray(floor_days, dtype=float), cap_days)
    if np.isnan(floor).any():
        raise ValueError("judge_floors: a forecast has no promise (floor).")
    event = np.asarray(days_to_event, dtype=float)
    event = np.where(np.isnan(event), np.inf, event)
    judged = np.asarray(followup_days, dtype=float) >= floor
    held = judged & (event >= floor)
    return judged, held


def in_ten(p):
    """Chances as whole tenths, rounded exactly as the text rounds them (notify.message.in_ten, vectorised):
    whole thousandths first (halves up), then tenths (halves up). 0 = "less than 1 in 10", 10 = "more than 9 in 10"."""
    p = np.asarray(p, dtype=float)
    if np.isnan(p).any():
        raise ValueError("in_ten: a forecast has no chance.")
    return (np.floor(p * 1000 + 0.5).astype(np.int64) + 50) // 100


def season_label(year):
    """2016 -> "2016-17" (the July-June year that starts in July 2016)."""
    return f"{year}-{str(year + 1)[-2:]}"


def has_record(record, min_judged=MIN_JUDGED):
    """True when a dam has enough judged forecasts to show its record."""
    return record is not None and record["judged"] >= min_judged


def dam_records(frame, min_judged=MIN_JUDGED):
    """{uid: record} for every dam in `frame`.

    frame: one row per forecast with uid, year (July-June), floor (as shown), judged, held, likely (a chance of 5 in
    10 or more), known (the 90-day answer is known) and fell (it fell below a third within 90 days).
    A record: forecasts, judged, held, not_judged (too recent to judge), enough (judged >= min_judged), by_season
    {"2016": [held, judged], ...} (only the July-June years with a judged forecast: the seasons covered),
    median_days (the typical promise, whole days rounded down, judged forecasts only; 180 means "180+"),
    likely_said and likely_fell.
    """
    out = {}
    for uid, part in frame.groupby("uid", sort=True, observed=True):
        judged = part["judged"].to_numpy(dtype=bool)
        held = part["held"].to_numpy(dtype=bool)
        years = part["year"].to_numpy()
        by_season = {}
        for year in np.unique(years[judged]):
            mine = judged & (years == year)
            by_season[str(int(year))] = [int(held[mine].sum()), int(mine.sum())]
        likely = part["likely"].to_numpy(dtype=bool) & part["known"].to_numpy(dtype=bool)
        n_judged = int(judged.sum())
        out[str(uid)] = dict(
            forecasts=int(len(part)), judged=n_judged, held=int(held.sum()), not_judged=int(len(part) - n_judged),
            enough=n_judged >= min_judged, by_season=by_season,
            median_days=(int(np.floor(np.median(part["floor"].to_numpy(dtype=float)[judged]))) if n_judged else None),
            likely_said=int(likely.sum()), likely_fell=int((likely & part["fell"].to_numpy(dtype=bool)).sum()))
    return out


def farm_rollup(dams, records, min_judged=MIN_JUDGED):
    """One farm's record: its dams' judged and held forecasts added up, over the dams with enough history.

    dams: the farm's dams, closest first, as dicts with dam_id and name. records: {dam_id: record}.
    """
    with_record = [d for d in dams if has_record(records.get(d["dam_id"]), min_judged)]
    rate = {d["dam_id"]: records[d["dam_id"]]["held"] / records[d["dam_id"]]["judged"] for d in with_record}
    lowest = min(with_record, key=lambda d: rate[d["dam_id"]], default=None)    # ties: the closest dam
    seasons = sorted({int(y) for d in with_record for y in records[d["dam_id"]]["by_season"]})
    return dict(
        dams=len(dams), dams_with_record=len(with_record),
        held=sum(records[d["dam_id"]]["held"] for d in with_record),
        judged=sum(records[d["dam_id"]]["judged"] for d in with_record),
        not_enough_history=[d["name"] for d in dams if d not in with_record],
        lowest=(dict(name=lowest["name"], dam_id=lowest["dam_id"], held=records[lowest["dam_id"]]["held"],
                     judged=records[lowest["dam_id"]]["judged"]) if lowest else None),
        seasons=seasons)


def distribution(records, min_judged=MIN_JUDGED):
    """How the dams' records spread: share held per dam (dams with enough history), as numbers and in 1,000."""
    rates = np.array([r["held"] / r["judged"] for r in records.values() if has_record(r, min_judged)])
    if not len(rates):
        return dict(dams_with_record=0)
    q = np.quantile(rates, [0.10, 0.25, 0.5, 0.75, 0.90])
    in_1000 = lambda share: int(np.floor(share * 1000 + 0.5))        # noqa: E731
    return dict(
        dams_with_record=int(len(rates)),
        median_share_held=round(float(q[2]), 5), median_in_1000=in_1000(q[2]),
        quantiles_in_1000={k: in_1000(v) for k, v in zip(["p10", "p25", "p50", "p75", "p90"], q)},
        lowest_in_1000=in_1000(rates.min()), highest_in_1000=in_1000(rates.max()),
        dams_held_every_time=int((rates == 1).sum()),
        dams_at_or_above_9_in_10=int((rates >= 0.9).sum()),
        dams_below_9_in_10=int((rates < 0.9).sum()),
        dams_below_8_in_10=int((rates < 0.8).sum()),
        dams_below_7_in_10=int((rates < 0.7).sum()),
        dams_below_half=int((rates < 0.5).sum()))


# ===========================================================================
# Loading and checking the inputs
# ===========================================================================
def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def table_fingerprint(frame):
    """Step 13's fingerprint of a saved forecast table (the recipe of scripts/13, 15 and 17)."""
    row_hashes = pd.util.hash_pandas_object(frame, index=False).to_numpy()
    return hashlib.sha256("|".join(map(str, frame.columns)).encode() + row_hashes.tobytes()).hexdigest()[:16]


def file_sha256_16(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for piece in iter(lambda: handle.read(2 ** 24), b""):
            digest.update(piece)
    return digest.hexdigest()[:16]


def scored_forecasts(summary):
    """The saved test forecasts, refused unless they are byte for byte the ones scripts/15 scored."""
    record = next((f for f in summary["files"] if f["path"] == FORECASTS_FILE), None)
    path = REPO / FORECASTS_FILE
    if record is None or not path.exists():
        raise SystemExit(f"{FORECASTS_FILE}: missing, or not among the files step 13 recorded. Run scripts/13 first.")
    frame = pd.read_pickle(path)
    if table_fingerprint(frame) != record["fingerprint"] or len(frame) != record["rows"]:
        raise SystemExit(f"{FORECASTS_FILE}: not the fingerprint step 13 recorded; not the scored test forecasts.")
    return frame, record["fingerprint"]


def forecast_frame(summary):
    """Every at-risk R30 forecast of the test years with a known answer (scripts/15's floor rows), one row each:
    uid, region, issue_date, year, dam_like, octmar, floor (as shown), judged, held, p, likely, known, fell."""
    from damdays.data.splits import hydro_year
    from damdays.evaluation.rules import is_octmar
    from damdays.features import store
    from damdays.models import rows
    from damdays.models import uncertainty as unc

    if unc.FLOOR_KIND != KIND or unc.FLOOR_DISPLAY_MAX_DAYS != CAP_DAYS:
        raise SystemExit("The floor's event or its display cap changed; update scripts/18.")
    if file_sha256_16(REPO / ANSWER_FILE) != summary["inputs"]["files"][ANSWER_FILE]:
        raise SystemExit(f"{ANSWER_FILE} changed since step 13: not the answers the test was scored on.")
    table = store.load_p1(groups=("keys",))
    data_end = pd.Timestamp(pd.read_pickle(store.FEATURES_DIR / "dam_rate_prior.pkl")["data_end"])
    forecasts, fingerprint = scored_forecasts(summary)

    picked = rows.p1_block_rows(table, KIND, "TEST")         # every at-risk TEST forecast (scripts/15)
    chosen = table.loc[picked]
    part = forecasts.set_index("row").loc[np.flatnonzero(picked)]
    if not ((part["uid"].astype(str).to_numpy() == chosen["uid"].astype(str).to_numpy()).all()
            and (pd.to_datetime(part["issue_date"]).to_numpy() == pd.to_datetime(chosen["issue_date"]).to_numpy()).all()):
        raise SystemExit("The saved forecasts do not line up with the P1 table's rows.")
    labelled = chosen["label_ok"].to_numpy(dtype=bool)        # as scripts/15: forecasts with a known answer
    chosen, part = chosen.loc[labelled], part.loc[labelled]
    floor = np.minimum(part["floor_shown"].to_numpy(dtype=float), CAP_DAYS)
    p = part["p90_R30"].to_numpy(dtype=float)
    if not (np.isfinite(floor).all() and np.isfinite(p).all()):
        raise SystemExit("Some test forecasts have no promise or no chance.")
    judged, held = judge_floors(floor, chosen[f"lab_tte_{KIND}"].to_numpy(dtype=float),
                                unc.followup_days(chosen["issue_date"], data_end))
    y = rows.p1_scored_label(chosen, KIND)                     # the 90-day answer (blank if unknown)
    frame = pd.DataFrame(dict(
        uid=chosen["uid"].astype(str).to_numpy(), region=chosen["region"].astype(str).to_numpy(),
        issue_date=chosen["issue_date"].to_numpy(), year=hydro_year(chosen["issue_date"]),
        dam_like=chosen["dam_like"].to_numpy(dtype=bool), octmar=is_octmar(chosen["issue_date"]),
        floor=floor, judged=judged, held=held, p=p, likely=in_ten(p) >= LIKELY_IN_TEN,
        known=~np.isnan(y), fell=np.nan_to_num(y, nan=0.0) == 1.0))
    found = set(frame["region"])
    if not found <= set(REGION_WORDS):
        raise SystemExit(f"Unexpected regions in the test forecasts: {sorted(found)}")
    return frame, dict(data_end=str(data_end.date()), fingerprint=fingerprint,
                       watched_to=str((data_end - pd.Timedelta(days=30)).date()))


def check_against_test_results(frame, results):
    """Every dam of both regions added up must equal step 15's floor result as shown in the app (shown_all)."""
    shown = results["floor"]["shown_all"]
    judged, held = frame["judged"].to_numpy(), frame["held"].to_numpy()
    pairs = [("forecasts with a known answer", len(frame), shown["rows"]),
             ("forecasts judged", int(judged.sum()), shown["rows_judged"]),
             ("share that held", round(float(held.sum() / judged.sum()), 5), shown["coverage"])]
    by_year = frame[frame["judged"]].groupby("year")["held"].agg(["mean", "size"])
    for year, row in by_year.iterrows():
        published = shown["by_year"][str(int(year))]
        pairs.append((f"{season_label(int(year))}: judged", int(row["size"]), published["rows"]))
        pairs.append((f"{season_label(int(year))}: share held", round(float(row["mean"]), 5),
                      round(published["coverage"], 5)))
    wrong = [f"{what}: here {a}, test results {b}" for what, a, b in pairs if abs(a - b) > 1e-9]
    if wrong:
        raise SystemExit("The per-dam counts do not add up to the scored test result; nothing written. " + "; ".join(wrong))
    return [dict(what=what, value=a, test_results=b) for what, a, b in pairs]


def check_against_proof(frame):
    """The "likely" calls on the headline set (farm-like dams, October-March) must equal proof.json's groups."""
    proof = read_json(APP_DIR / "proof.json")
    bins = [b for b in proof["calibration"]["bins"] if b["in_ten"] >= LIKELY_IN_TEN]
    head = frame[frame["dam_like"] & frame["octmar"] & frame["known"]]
    likely = head[head["likely"]]
    pairs = [("headline set: forecasts", len(head), proof["test"]["forecasts"]),
             ("headline set: likely calls (5 in 10 or more)", len(likely), sum(b["forecasts"] for b in bins)),
             ("headline set: likely calls followed by a fall", int(likely["fell"].sum()), sum(b["fell"] for b in bins))]
    wrong = [f"{what}: here {a}, proof.json {b}" for what, a, b in pairs if a != b]
    if wrong:
        raise SystemExit("The 'likely' counts differ from the Proof view; nothing written. " + "; ".join(wrong))
    return [dict(what=what, value=a, proof_json=b) for what, a, b in pairs]


def app_dams():
    """The dams the app shows: [(dam_id, dea_uid, region)], map dams first, then the demo farms' other dams."""
    forecasts = read_json(APP_DIR / "forecasts.json")
    farms = read_json(APP_DIR / "farms.json")
    region = read_json(APP_DIR / "meta.json")["region"]["key"]
    out = {d["dam_id"]: (d["dam_id"], d["dea_uid"], region) for d in forecasts["dams"]}
    for farm in farms["farms"]:
        for d in farm["dams"]:
            if d["dam_id"] in out:
                if out[d["dam_id"]][1] != d["dea_uid"]:
                    raise SystemExit(f"{d['dam_id']}: farms.json and forecasts.json name different DEA waterbodies.")
                continue
            if farm["dams_in_app"]:
                raise SystemExit(f"{farm['farm_id']}: {d['dam_id']} is not on the app's map.")
            out[d["dam_id"]] = (d["dam_id"], d["dea_uid"], farm["region"])
    if not {r for _, _, r in out.values()} <= set(REGION_WORDS):
        raise SystemExit("The app shows a dam outside the two development regions.")
    return list(out.values()), farms


# ===========================================================================
# Words
# ===========================================================================
def held_words(record):
    """"held 18 of 20 times", or "not enough history" (fewer than 5 judged forecasts)."""
    if not has_record(record):
        return "not enough history"
    return f"held {record['held']:,} of {record['judged']:,} times"


def page(doc):
    """artifacts/track_record.md: the same numbers, for people reading the repository."""
    s, d = doc["summary"], doc["summary"]["distribution"]
    q = d["quantiles_in_1000"]
    lines = [
        "# Track record: how often the days-left number held, dam by dam (July 2016 to June 2026)",
        "",
        f"Generated by `scripts/18_track_record.py` on {doc['generated_at'][:16].replace('T', ' ')}. Data: "
        "`app/data/real/track_record.json` (format: `app/DATA_CONTRACT.md`).",
        "",
        "> **What this is.** " + doc["about"],
        "",
        "> **Not a new test.** " + doc["caveat"],
        "",
        "## The dams the app shows",
        "",
        f"- **{s['dams_in_app']:,} dams** in the app ({s['dams_by_region']['nsw_cw']:,} on the NSW Central West map, "
        f"{s['dams_by_region'].get('wvic_sesa', 0):,} on the demo farms in western Victoria / SE South Australia). "
        f"**{d['dams_with_record']:,}** have at least {doc['min_judged']} judged past forecasts; "
        f"{s['dams_in_app'] - d['dams_with_record']:,} show \"not enough history\".",
        f"- **Typical dam:** the promise held **{q['p50']} times in 1,000** (the median dam). Half the dams sit between "
        f"{q['p25']} and {q['p75']} in 1,000; one dam in ten is below {q['p10']}, one in ten above {q['p90']}.",
        f"- **Spread:** {d['dams_at_or_above_9_in_10']:,} dams held 9 times in 10 or more "
        f"({d['dams_held_every_time']:,} every time); {d['dams_below_9_in_10']:,} held less often than 9 in 10, "
        f"{d['dams_below_8_in_10']:,} less than 8 in 10, {d['dams_below_7_in_10']:,} less than 7 in 10 and "
        f"{d['dams_below_half']:,} less than half the time. Lowest {d['lowest_in_1000']:,} in 1,000, highest "
        f"{d['highest_in_1000']:,}.",
        f"- **All these dams together:** held {s['held']:,} of {s['judged']:,} judged forecasts "
        f"({s['held_in_1000']} in 1,000); a typical dam has {s['median_judged']} judged forecasts over "
        f"{s['median_seasons']} seasons.",
        f"- **\"Likely\" calls** (a chance of 5 in 10 or more): {s['likely_fell']:,} of {s['likely_said']:,} were "
        "followed by a fall below a third within 90 days.",
        "",
        "## Demo farms",
        "",
        "| farm | dams | with a record | promise held | lowest dam |",
        "|---|---|---|---|---|",
    ]
    for f in doc["farms"]:
        low = f["lowest"]
        lines.append(f"| {f['name']} | {f['dams']} | {f['dams_with_record']} | "
                     f"{f['held']:,} of {f['judged']:,} | "
                     + (f"{low['name']}: {low['held']:,} of {low['judged']:,}" if low else "-") + " |")
    lines += ["", "## Checks", ""]
    for c in doc["checks"]["equal_to_test_results"]:
        lines.append(f"- {c['what']}: {c['value']} (test results: {c['test_results']})")
    for c in doc["checks"]["equal_to_proof"]:
        lines.append(f"- {c['what']}: {c['value']} (proof.json: {c['proof_json']})")
    lines += ["", "## How it is counted", ""] + [f"- {h}" for h in doc["how"]] + [""]
    return "\n".join(lines)


# ===========================================================================
# Main
# ===========================================================================
def build():
    summary, results = read_json(FIT_SUMMARY), read_json(TEST_RESULTS)
    frame, inputs = forecast_frame(summary)
    checked = check_against_test_results(frame, results)
    checked_proof = check_against_proof(frame)

    dams, farms = app_dams()
    by_uid = dam_records(frame[frame["uid"].isin({uid for _, uid, _ in dams})])
    records = {}
    for dam_id, uid, region in dams:
        record = by_uid.get(uid, dict(forecasts=0, judged=0, held=0, not_judged=0, enough=False, by_season={},
                                      median_days=None, likely_said=0, likely_fell=0))
        records[dam_id] = dict(dea_uid=uid, region=region, **record)

    farm_rows = []
    for farm in farms["farms"]:
        roll = farm_rollup([dict(dam_id=d["dam_id"], name=d["name"]) for d in farm["dams"]], records)
        farm_rows.append(dict(farm_id=farm["farm_id"], name=farm["name"], region=farm["region"],
                              radius_km=farm["radius_km"], **roll))

    shown = [r for r in records.values() if has_record(r)]
    judged_total, held_total = sum(r["judged"] for r in shown), sum(r["held"] for r in shown)
    summary_block = dict(
        dams_in_app=len(records),
        dams_by_region={k: sum(1 for r in records.values() if r["region"] == k) for k in REGION_WORDS},
        distribution=distribution(records),
        judged=judged_total, held=held_total,
        held_in_1000=int(np.floor(held_total / judged_total * 1000 + 0.5)) if judged_total else None,
        median_judged=int(np.median([r["judged"] for r in shown])) if shown else None,
        median_seasons=int(np.median([len(r["by_season"]) for r in shown])) if shown else None,
        likely_said=sum(r["likely_said"] for r in shown), likely_fell=sum(r["likely_fell"] for r in shown))

    return dict(
        schema_version="1.0",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        made_by="scripts/18_track_record.py",
        years=TRACK_RECORD_YEARS, label=TRACK_RECORD_SPAN,
        first_season=season_label(FIRST_YEAR), last_season=season_label(LAST_YEAR),
        first_season_year=FIRST_YEAR, last_season_year=LAST_YEAR,
        min_judged=MIN_JUDGED, cap_days=CAP_DAYS, likely_in_ten=LIKELY_IN_TEN,
        tip=TIP,
        about=("For each dam the app shows: how often our cautious days-left number (\"at least N days before it "
               "drops below a third\") held on that dam over the last 10 years. We re-ran our forecasts for July 2016 "
               "to June 2026 using only data from before July 2016: one forecast per clear satellite look while the "
               "dam was above a third and had refilled, each checked against what the dam really did."),
        caveat=("These are the same ten test years that were scored once on Fri 2 Oct 2026 (artifacts/test_results.md), "
                "counted dam by dam; nothing new was scored. Those years were looked at before the event, so they may "
                "flatter the model slightly. The forecasts a farmer gets today come from the same recipe refitted on "
                "all data to September 2026, not from these re-run forecasts."),
        how=[
            "Promise: \"at least N days above a third\", N as the app and the text show it (whole days, rounded down; "
            "\"6 months+\" is judged at 180 days). It held if the dam stayed above a third for at least N days.",
            f"A forecast is judged only if the satellite archive watched the dam for at least N days after it (to "
            f"{inputs['watched_to']}: the archive ends {inputs['data_end']}, less 30 days to confirm a fall), whatever "
            "happened. Forecasts with too few clear looks to know the answer are left out (as in the test).",
            f"A dam with fewer than {MIN_JUDGED} judged forecasts shows \"not enough history\".",
            "Likely calls: forecasts that gave a chance of 5 in 10 or more of falling below a third within 90 days "
            "(rounded as the text rounds it), with a known answer; fell = it fell below a third within those 90 days.",
            "Seasons (by_season): the July-June years with at least one judged forecast, each with [held, judged]; "
            "\"2016\" is July 2016 to June 2017.",
            "Farm roll-up: the farm's dams with a record, added up (forecasts on nearby dams often share one dry "
            "spell, so this is not many independent checks).",
        ],
        dams=records,
        farms=farm_rows,
        summary=summary_block,
        checks=dict(equal_to_test_results=checked, equal_to_proof=checked_proof,
                    ledger="nothing scored on the TEST ledger"),
        sources=dict(
            forecasts=f"{FORECASTS_FILE} (scripts/13; fingerprint {inputs['fingerprint']}, as scored by scripts/15)",
            answers=f"{ANSWER_FILE} (the PREREG R30 labels and days to the next fall below a third)",
            test_results="artifacts/test_results.json floor.shown_all (scripts/15): every dam of both regions adds up to it",
            proof="app/data/real/proof.json (scripts/17): the likely calls on the headline set add up to its groups",
            dams="app/data/real/forecasts.json (scripts/11) and app/data/real/farms.json (scripts/16)"),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="build and check everything; write nothing")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    doc = build()
    s, d = doc["summary"], doc["summary"]["distribution"]
    print(f"Dams in the app: {s['dams_in_app']:,}; with a record (>= {MIN_JUDGED} judged): {d['dams_with_record']:,}")
    print(f"Median dam: held {d['median_in_1000']} in 1,000; quartiles {d['quantiles_in_1000']}")
    print(f"Below 9 in 10: {d['dams_below_9_in_10']:,}; below 8 in 10: {d['dams_below_8_in_10']:,}; "
          f"below half: {d['dams_below_half']:,}; every time: {d['dams_held_every_time']:,}")
    for f in doc["farms"]:
        print(f"  {f['name']}: {f['held']:,} of {f['judged']:,} on {f['dams_with_record']} of {f['dams']} dams")
    if args.check:
        print("CHECK ONLY: nothing written.")
        return 0
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    PAGE.write_text(page(doc), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO)} ({OUT.stat().st_size / 1024:.0f} KB) and {PAGE.relative_to(REPO)}")
    subprocess.run([sys.executable, str(BUNDLE_TOOL), str(APP_DIR)], check=True, cwd=REPO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
