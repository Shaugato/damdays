"""Step 17: the data behind the app's Proof view (app/data/real/proof.json): what accuracy looks like.

Run from the repo folder, after steps 13, 15, 11 and 16 (about a minute):
    .venv/Scripts/python.exe scripts/17_proof_data.py            # write proof.json and rebuild bundle.js
    .venv/Scripts/python.exe scripts/17_proof_data.py --check    # build and check everything; write nothing
    .venv/Scripts/python.exe scripts/17_proof_data.py --farm farm-a --rewind-day 2019-01-01 --check   # another farm/day

Why: many judges do not read "AUC" or "Brier skill". The Proof view (app/js/views/proof.js, #proof)
shows the same test in three pictures, each with one plain sentence:
  1. WHAT WE SAID vs WHAT HAPPENED. Every test forecast of the farmer question ("will this dam fall below
     a third within 90 days?") is put in a group by the chance it gave, rounded as the text and the app
     write it (notify.message.in_ten: "less than 1 in 10", "1 in 10", ... "9 in 10", "more than 9 in 10").
     For each group: how many forecasts, how many dams really fell below a third within 90 days.
  2. IT HELD UP YEAR AFTER YEAR. For each July-June year 2016-17 to 2025-26: how much less error the
     forecasts had than guessing the usual rate for that region and month (the Brier skill score against
     B0, the same number as the headline, on that year's forecasts), with a 95% range from re-drawing that
     year's dams; and how often the "at least N days" promise held that year (copied from the test results).
     Drier years are marked by a rule on the rainfall record (SILO), written below and in proof.json.
  3. DAM BY DAM. The hero farm of the weekly text (Farm E near Mudgee, outbox farm-e, 5 dams): each dam's
     forecasts from July 2018 to June 2019 against its satellite water level, the farm's forecasts on
     1 Nov 2018 (the first Rewind date), with what happened, and the tally over all three Rewind dates.

What it reads (and checks)
  data_cache/preds/TEST/tidemark/L3_p1.pkl            the frozen model's test forecasts (scripts/13)
  data_cache/preds/TEST/P1_R30/baselines_dam_like.pkl the usual-rate guess B0 for the same rows (scripts/13)
      Each must match the fingerprint step 13 recorded (artifacts/test_setting_fit_summary.json), as in
      scripts/15: these are exactly the forecasts that were scored.
  data_cache/features/p1_keys.pkl (via damdays.features.store)  the answers; same fingerprint as step 13 read
  artifacts/test_results.json                         step 15's one look: the overall numbers here must equal
                                                      it (rows, falls, dams, average chance, share that fell,
                                                      skill), and the promise-by-year numbers are copied from it
  data_cache/silo_rain.pkl                            monthly rainfall, for the "drier year" rule
  data_cache/panel.pkl, attributes.pkl, events.pkl    one farm's satellite looks and falls (part 3)
  app/data/real/farms.json, forecasts.json            the demo farm and the app's Rewind forecasts (part 3
                                                      must agree with Rewind on 1 Nov 2018)

It scores nothing on the TEST ledger. The test years were scored once by scripts/15; this step only
re-reads those saved forecasts and their answers to draw them, and refuses to write anything if its
totals differ from the test results. Nothing under damdays/ is changed.

Output: app/data/real/proof.json (format: app/DATA_CONTRACT.md, "proof.json"), then app/tools/build_bundle.py
packs it into bundle.js. Tests: tests/test_proof_data.py (the grouping and the year rule on made-up numbers;
the published proof.json against artifacts/test_results.json).
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from notify.message import chance_text, in_ten  # noqa: E402

FIT_SUMMARY = REPO / "artifacts" / "test_setting_fit_summary.json"
TEST_RESULTS = REPO / "artifacts" / "test_results.json"
APP_DIR = REPO / "app" / "data" / "real"
OUT = APP_DIR / "proof.json"
BUNDLE_TOOL = REPO / "app" / "tools" / "build_bundle.py"
FORECASTS_FILE = "data_cache/preds/TEST/tidemark/L3_p1.pkl"
BASELINES_FILE = "data_cache/preds/TEST/P1_R30/baselines_dam_like.pkl"
ANSWER_FILE = "data_cache/features/p1_keys.pkl"

PRIMARY_KEY = "P1_R30 | dam_like+octmar+at_risk | tidemark"   # the headline score in test_results.json
FIRST_YEAR, LAST_YEAR = 2016, 2025                            # July-June years of the test block
MIN_FORECASTS_TO_PLOT = 100        # a group with fewer forecasts is listed, not drawn as a dot
N_BOOT = 500                       # dam re-draws for the 95% ranges (as on the primary set in scripts/15)
SEED = 2026                        # config.RANDOM_SEED
RAIN_BASE_YEARS = (1960, 2015)     # "usual" rain: the July-June years July 1960 to June 2016 (before the test)
FARM_ID = "farm-e"                 # the hero farm of the weekly text (outbox/2026-10-02.json); --farm to change
REWIND_DAY = "2018-11-01"          # the first Rewind date, in the 2018-19 drought; --rewind-day to change
# Why a farm is the one shown (how_chosen). Farm E: every one of its waterbodies is a farm dam on aerial photos
# (Farm D, the first choice, was set aside by scripts/16 because its waterbodies are not farm dams).
CHOSEN_BECAUSE = {"farm-e": "We picked it because its dams are clearly farm dams on aerial photos, not for these results."}
STATUS_WORDS = {"already_low": "already below a third", "not_refilled": "not yet refilled to 60% full",
                "no_recent_look": "without a recent clear satellite look"}
SEASON_FROM, SEASON_TO = "2018-07-01", "2019-06-30"   # part 3: forecasts made in this July-June year
SHOW_TO = "2019-09-30"             # ... drawn to here, so the 90 days after the last forecast can be seen
REGION_WORDS = {"nsw_cw": "NSW Central West", "wvic_sesa": "western Victoria / SE South Australia"}
OPENS = "Sun 4 Oct 2026 (AEDT)"    # the sealed region's opening, moved from Sat 3 Oct 17:30 AEST (PREREG_ADDENDUM_2.md)


# ===========================================================================
# Plain words (pure functions: tested in tests/test_proof_data.py)
# ===========================================================================
def chance_bins(p):
    """Each chance's group, as a whole number of tenths, rounded exactly as the text and the app round it.

    notify.message.in_ten, vectorised: whole thousandths first (halves up), then tenths (halves up).
    0 = "less than 1 in 10" (under 0.05), 10 = "more than 9 in 10" (0.95 or more).
    """
    p = np.asarray(p, dtype=float)
    if np.isnan(p).any():
        raise ValueError("chance_bins: a forecast has no chance.")
    thousandths = np.floor(p * 1000 + 0.5).astype(np.int64)
    return (thousandths + 50) // 100


def fraction_words(skill):
    """A skill score as a share of the error, rounded DOWN, by the rule of docs/VIDEO_SCRIPT.md: 0.235 -> "nearly a
    quarter". The same table as scripts/21_publish_sealed.py (loaded from it, so the two can never differ)."""
    return load_step21().fraction_words(skill)


def in_thousand(share):
    """0.87199 -> 872 (how often, out of 1,000; halves up)."""
    return int(np.floor(share * 1000 + 0.5))


def year_label(year):
    """2016 -> "2016-17" (the July-June year that starts in July 2016)."""
    return f"{year}-{str(year + 1)[-2:]}"


def year_words(year):
    """2023 -> "July 2023 to June 2024"."""
    return f"July {year} to June {year + 1}"


def runs(years):
    """Consecutive years grouped: [2017, 2018, 2019, 2023] -> [(2017, 2019), (2023, 2023)]."""
    out = []
    for year in sorted(years):
        if out and year == out[-1][1] + 1:
            out[-1] = (out[-1][0], year)
        else:
            out.append((year, year))
    return out


def run_label(first, last):
    """(2017, 2019) -> "2017-20": July 2017 to June 2020."""
    return f"{first}-{str(last + 1)[-2:]}"


def number_words(n):
    """3 -> "three" (up to ten; larger numbers as digits)."""
    words = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    return words[n] if 0 <= n <= 10 else f"{n:,}"


def day_words(day):
    """"2018-12-04" -> "4 Dec 2018"."""
    d = pd.Timestamp(day)
    return f"{d.day} {d:%b %Y}"


def list_words(items):
    """["Dam 1", "Dam 5"] -> "Dam 1 and Dam 5"; three or more with commas."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def brier_skill(y, p, p_ref, w=None):
    """1 - Brier(p) / Brier(p_ref): the share of the reference's squared error the forecast removes."""
    w = np.ones(len(y)) if w is None else np.asarray(w, dtype=float)
    top, bottom = np.sum(w * (p - y) ** 2), np.sum(w * (p_ref - y) ** 2)
    return float(1 - top / bottom) if bottom > 0 else float("nan")


# ===========================================================================
# 1. What we said vs what happened
# ===========================================================================
def calibration_bins(y, p, uid=None, n_boot=0, seed=SEED):
    """One row per group of forecasts (by "N in 10"): forecasts, how many fell, the share that fell, the average
    chance given, and (with uid and n_boot) a 95% range for the share from re-drawing whole dams."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    if len(y) != len(p) or not np.isin(y, (0.0, 1.0)).all():
        raise ValueError("calibration_bins: y must be 0 or 1 for every forecast.")
    groups = chance_bins(p)
    present = np.unique(groups)
    ranges = {}
    if uid is not None and n_boot > 0:
        from damdays.evaluation.bootstrap import cluster_bootstrap

        def shares(w):
            total = np.bincount(groups, weights=w, minlength=11)
            fell = np.bincount(groups, weights=w * y, minlength=11)
            return {int(k): fell[k] / total[k] if total[k] > 0 else np.nan for k in present}
        ranges, _ = cluster_bootstrap(shares, np.asarray(uid), n_boot, seed)
    rows = []
    for k in present:
        mask = groups == k
        n, fell = int(mask.sum()), int(y[mask].sum())
        share = fell / n
        row = dict(in_ten=int(k), said=chance_text(k / 10), forecasts=n, fell=fell, share_fell=round(share, 5),
                   mean_chance=round(float(p[mask].mean()), 5), happened_in_ten=in_ten(share),
                   plotted=n >= MIN_FORECASTS_TO_PLOT)
        if int(k) in ranges:
            row["share_fell_ci"] = [round(v, 5) for v in ranges[int(k)]]
        rows.append(row)
    return rows


def calibration_words(bins, slope):
    """The takeaway (one sentence), its detail, the "which way it leans" note, and a line for any group too
    small to plot."""
    plotted = [b for b in bins if b["plotted"]]
    matched = [b for b in plotted if b["happened_in_ten"] == b["in_ten"]]
    example = next((b for b in plotted if b["in_ten"] == 3), plotted[len(plotted) // 2])
    happened = example["happened_in_ten"]
    times = ("less than once in 10" if happened == 0 else
             "more than 9 times in 10" if happened == 10 else f"about {happened} times in 10")
    lead = f"When we said {example['said']}, the dam fell below a third {times}"
    if len(matched) == len(plotted):
        takeaway = (f"{lead}, and in all {number_words(len(plotted))} groups what happened matched what we said, "
                    "to the nearest 1 in 10.")
    else:
        missed = [f"{b['said']} (happened {chance_text(b['happened_in_ten'] / 10)})" for b in plotted if b not in matched]
        takeaway = (f"{lead}; in {len(matched)} of {len(plotted)} groups what happened matched what we said, to the "
                    f"nearest 1 in 10, but not in {list_words(missed)}.")
    detail = (f"{example['said'][0].upper() + example['said'][1:]}: {example['fell']:,} of {example['forecasts']:,} "
              "forecasts were followed by a fall below a third within 90 days. Across all "
              f"{sum(b['forecasts'] for b in bins):,} forecasts, {sum(b['fell'] for b in bins):,} were.")
    # Which way it leans: groups where fewer fell than the average chance given, and groups where more fell.
    high = [b["in_ten"] for b in plotted if b["share_fell"] < b["mean_chance"]]
    low = [b["in_ten"] for b in plotted if b["share_fell"] > b["mean_chance"]]
    slope_words = (f"calibration slope {slope:.2f}, where 1.00 is perfect and the pass mark written before the build "
                   "began was 0.8 to 1.2")
    if high and low and max(high) < min(low):
        lean = (f"Below {min(low)} in 10, slightly fewer dams fell than we said; from {min(low)} in 10 up, slightly "
                f"more. So the chances could be a little bolder: low ones a little lower, high ones a little higher "
                f"({slope_words}).")
    else:
        lean = f"The small gaps go both ways ({slope_words})."
    small = [b for b in bins if not b["plotted"]]
    small_words = "; ".join(
        f"{b['forecasts']:,} forecast{'s' if b['forecasts'] != 1 else ''} said {b['said']} "
        f"({b['fell']:,} fell)" for b in small)
    not_plotted = (f"Not drawn, too few to read: {small_words}." if small else "")
    return takeaway, detail, lean, not_plotted


# ===========================================================================
# 2. Year after year
# ===========================================================================
def rain_by_year(rain, months, cells, regions, base_years=RAIN_BASE_YEARS):
    """{region: {year: July-June rain / the usual July-June rain}} from SILO monthly rain.

    A region's rain is the average over its SILO grid cells; "usual" is the average July-June total over
    base_years (both ends included). Only complete July-June years (12 months) count.
    """
    months = np.asarray(months)
    year, month = months // 100, months % 100
    july_june = np.where(month >= 7, year, year - 1)
    region_of = np.array([str(c).split(":")[0] for c in cells])
    out = {}
    for region in regions:
        monthly = np.asarray(rain)[region_of == region].mean(axis=0)
        totals = pd.Series(monthly).groupby(july_june).sum()
        complete = pd.Series(1, index=range(len(months))).groupby(july_june).sum() == 12
        totals = totals[complete]
        usual = totals.loc[base_years[0]:base_years[1]].mean()
        out[region] = {int(y): float(v / usual) for y, v in totals.items()}
    return out


def drier_years(ratios, years):
    """Years whose rain, averaged over the regions' ratios to their usual rain, was below the usual (< 1)."""
    return [y for y in years if np.mean([ratios[r][y] for r in ratios]) < 1]


def year_rows(frame, floor_by_year, ratios, n_boot=N_BOOT, seed=SEED):
    """One row per July-June year: forecasts, falls, skill against the usual rate (with a dam range), the
    promise held (copied), rain against the usual, and whether it was a drier year."""
    from damdays.evaluation.bootstrap import cluster_bootstrap
    years = list(range(FIRST_YEAR, LAST_YEAR + 1))
    drier = set(drier_years(ratios, years))
    out = []
    for year in years:
        part = frame[frame["year"] == year]
        y, p, p0 = (part[c].to_numpy(dtype=float) for c in ("y", "p", "p_B0"))
        skill = brier_skill(y, p, p0)
        ci = None
        if n_boot:
            ranges, _ = cluster_bootstrap(lambda w: dict(skill=brier_skill(y, p, p0, w)), part["uid"].to_numpy(),
                                          n_boot, seed)
            ci = [round(v, 5) for v in ranges["skill"]]
        held = floor_by_year[str(year)]
        out.append(dict(
            year=year, label=year_label(year), words=year_words(year), forecasts=int(len(part)), fell=int(y.sum()),
            dams=int(part["uid"].nunique()), share_fell=round(float(y.mean()), 5), mean_chance=round(float(p.mean()), 5),
            usual_rate=round(float(p0.mean()), 5), skill=round(skill, 5), skill_ci=ci, skill_words=fraction_words(skill),
            rain_vs_usual={r: round(ratios[r][year], 3) for r in ratios},
            rain_vs_usual_mean=round(float(np.mean([ratios[r][year] for r in ratios])), 3),
            drier=year in drier, floor=dict(held=held["coverage"], held_in_1000=in_thousand(held["coverage"]),
                                            judged=held["rows"])))
    return out


def one_region_words(rows):
    """" In 2023-24 and 2024-25 only western Victoria / SE South Australia was drier than usual; ..." for drier years
    that were drier in one region only (so the shading is not read as a drought everywhere)."""
    by_region = {}
    for r in rows:
        if not r["drier"]:
            continue
        below = [region for region, ratio in r["rain_vs_usual"].items() if ratio < 1]
        if len(below) == 1:
            by_region.setdefault(below[0], []).append(r["label"])
    parts = [f"in {list_words(labels)} only {REGION_WORDS.get(region, region)} was drier than usual"
             for region, labels in sorted(by_region.items(), key=lambda kv: kv[1][0])]
    if not parts:
        return ""
    text = "; ".join(parts)
    return " " + text[0].upper() + text[1:] + "."


def year_words_all(rows, all_skill, floor, target, tolerance):
    """The takeaway for the skill bars and the one for the promise, from the year rows."""
    drier = [r for r in rows if r["drier"]]
    wetter = [r for r in rows if not r["drier"]]
    lowest, highest = min(rows, key=lambda r: r["skill"]), max(rows, key=lambda r: r["skill"])
    beat = [r for r in rows if r["skill"] > 0]
    spread = (f"from {fraction_words(lowest['skill'])} ({lowest['label']}) to {fraction_words(highest['skill'])} "
              f"({highest['label']})")
    groups = " and ".join(run_label(a, b) for a, b in runs([r["year"] for r in drier]))
    if len(beat) == len(rows):
        takeaway = (f"In every one of the {number_words(len(rows))} years, the forecasts had less error than "
                    f"guessing the usual rate: {spread} less, in the {number_words(len(drier))} drier years "
                    f"({groups}) as well as the {number_words(len(wetter))} wetter ones.")
    else:
        takeaway = (f"In {len(beat)} of the {len(rows)} years the forecasts had less error than guessing the usual "
                    f"rate ({spread}); in {list_words(r['label'] for r in rows if r['skill'] <= 0)} they did not.")
    held = [r["floor"]["held"] for r in rows]
    low_edge, high_edge = target - tolerance, target + tolerance
    short = [r for r in rows if r["floor"]["held"] < low_edge - 1e-12]
    cautious = [r for r in rows if r["floor"]["held"] > high_edge + 1e-12]
    span = f"from {in_thousand(min(held))} to {in_thousand(max(held))} times in 1,000"
    tenths = {in_ten(h) for h in held}
    floor_takeaway = (f"The \"at least N days\" promise held about {tenths.pop()} times in 10 in every year ({span})"
                      if len(tenths) == 1 else f"The \"at least N days\" promise held {span} a year")
    if short:
        floor_takeaway += (f"; it fell a little short of the {in_thousand(low_edge)} mark in "
                           + list_words(f"{r['words']} ({r['floor']['held_in_1000']})" for r in short))
    floor_takeaway += "."
    floor_detail = (f"Target {in_thousand(target)} in 1,000; on target means {in_thousand(low_edge)} to "
                    f"{in_thousand(high_edge)}.")
    if short:
        floor_detail += (" Short of target: " + "; ".join(f"{r['words']}, {r['floor']['held_in_1000']} in 1,000"
                                                          for r in short) + ".")
    if cautious:
        floor_detail += (" More cautious than needed: " + "; ".join(
            f"{r['words']}, {r['floor']['held_in_1000']} in 1,000" for r in cautious) + ".")
    return takeaway, floor_takeaway, floor_detail


# ===========================================================================
# 3. Dam by dam
# ===========================================================================
def dam_summary(name, forecasts, falls, closest=False):
    """One factual sentence about one dam's season: how many forecasts, the highest chance, the falls."""
    lead = f"{name}{' (the dam closest to the homestead)' if closest else ''}: "
    if not forecasts:
        return lead + "no forecast from July 2018 to June 2019 (it was below a third, or had not refilled, at every look)."
    top = max(forecasts, key=lambda f: f["chance"])
    followed = sum(1 for f in forecasts if f["fell"] is True)
    text = (f"{lead}{len(forecasts)} forecasts from July 2018 to June 2019; the highest chance was "
            f"{chance_text(top['chance'])} ({day_words(top['date'])}). ")
    if falls:
        text += f"It fell below a third on {list_words(day_words(d) for d in falls)}"
    else:
        text += f"It did not fall below a third between July 2018 and {pd.Timestamp(SHOW_TO):%B %Y}"
    return text + f"; {followed or 'none'} of the {len(forecasts)} forecasts were followed by a fall within 90 days."


def about_count(expected):
    """An expected number of falls in words: 1.57 -> "about 2"; under 0.5 -> "less than 1"."""
    rounded = int(np.floor(expected + 0.5))
    return "less than 1" if rounded == 0 else f"about {rounded}"


def farm_words(farm_name, rows, day=REWIND_DAY):
    """The takeaway for part 3: one farm, one day, each dam its own chance, and what happened.

    rows: one per dam, with name, chance (None if it had no forecast that day), outcome and, optionally, status
    (then the dams with no forecast are named, with the reason)."""
    with_chance = [r for r in rows if r["chance"] is not None]
    lowest, highest = min(r["chance"] for r in with_chance), max(r["chance"] for r in with_chance)
    expected = sum(r["chance"] for r in with_chance)
    fell = [r["name"] for r in with_chance if r["outcome"] is True]
    unknown = [r for r in with_chance if r["outcome"] is None]
    text = (f"On {day_words(day)}, the {number_words(len(with_chance))} dams on one farm, {farm_name}, "
            f"each got their own chance, from {chance_text(lowest)} to {chance_text(highest)}; the chances added up to "
            f"{about_count(expected)}, and {len(fell)} fell below a third within 90 days"
            f"{' (' + list_words(fell) + ')' if fell else ''}.")
    if unknown:
        text += f" For {len(unknown)} the answer is not known."
    no_forecast = [r for r in rows if r["chance"] is None and r.get("status")]
    groups = {}
    for r in no_forecast:
        groups.setdefault(STATUS_WORDS.get(r["status"], "without a forecast"), []).append(r["name"])
    if groups:
        text += " " + "; ".join(f"{list_words(names)} {'was' if len(names) == 1 else 'were'} {words}"
                                for words, names in groups.items()) + " that day, so had no forecast."
    return text


def all_dates_words(farm_name, dates):
    """The tally over every Rewind date, so no one date is picked: how many forecasts the farm's dams got, what
    their chances added up to, and how many fell below a third within 90 days (with the date of each forecast)."""
    n = sum(d["forecasts"] for d in dates)
    expected = sum(d["chance_sum"] for d in dates)
    fell = [f"{name} after {day_words(d['date'])}" for d in dates for name in d["fell"]]
    unknown = sum(len(d["unknown"]) for d in dates)
    text = (f"Across all {number_words(len(dates))} Rewind dates ({list_words(day_words(d['date']) for d in dates)}), "
            f"the dams on {farm_name} got {n} forecasts; their chances added up to {about_count(expected)} falls below "
            f"a third within 90 days, and {len(fell)} happened{': ' + list_words(fell) if fell else ''}.")
    if unknown:
        text += f" For {unknown} the answer is not known."
    return text


# ===========================================================================
# Loading and checking the inputs
# ===========================================================================
def load_step21():
    """scripts/21_publish_sealed.py as a module (for its rounding words; it reads nothing when loaded)."""
    if "step21_publish_sealed" not in sys.modules:
        spec = importlib.util.spec_from_file_location("step21_publish_sealed", REPO / "scripts" / "21_publish_sealed.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules["step21_publish_sealed"] = module
    return sys.modules["step21_publish_sealed"]


def table_fingerprint(frame):
    """Step 13's fingerprint of a saved forecast table (the recipe of scripts/13, 15 and 11)."""
    row_hashes = pd.util.hash_pandas_object(frame, index=False).to_numpy()
    return hashlib.sha256("|".join(map(str, frame.columns)).encode() + row_hashes.tobytes()).hexdigest()[:16]


def file_sha256_16(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for piece in iter(lambda: handle.read(2 ** 24), b""):
            digest.update(piece)
    return digest.hexdigest()[:16]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def scored_table(summary, relative):
    """A table step 13 saved, refused unless it is byte for byte the one scripts/15 scored."""
    record = next((f for f in summary["files"] if f["path"] == relative), None)
    path = REPO / relative
    if record is None or not path.exists():
        raise SystemExit(f"{relative}: missing, or not among the files step 13 recorded. Run scripts/13 first.")
    frame = pd.read_pickle(path)
    if table_fingerprint(frame) != record["fingerprint"] or len(frame) != record["rows"]:
        raise SystemExit(f"{relative}: not the fingerprint step 13 recorded; not the scored test forecasts.")
    return frame


def primary_frame(summary):
    """The headline set, exactly as scripts/15 scored it: R30 within 90 days, farm-like dams, forecasts made
    October to March, at risk, with a known answer. Columns uid, issue_date, region, year, y, p, p_B0."""
    from damdays.data.splits import hydro_year
    from damdays.evaluation.inputs import join_baselines, tidy_keys
    from damdays.evaluation.rules import is_octmar
    from damdays.features import store
    from damdays.models import rows

    if file_sha256_16(REPO / ANSWER_FILE) != summary["inputs"]["files"][ANSWER_FILE]:
        raise SystemExit(f"{ANSWER_FILE} changed since step 13: not the answers the test was scored on.")
    table = store.load_p1(groups=("keys",))
    forecasts = scored_table(summary, FORECASTS_FILE)
    baselines = scored_table(summary, BASELINES_FILE)
    picked = rows.p1_block_rows(table, "R30", "TEST")
    chosen = table.loc[picked]
    part = forecasts.set_index("row").loc[np.flatnonzero(picked)]
    if not ((part["uid"].astype(str).to_numpy() == chosen["uid"].astype(str).to_numpy()).all()
            and (pd.to_datetime(part["issue_date"]).to_numpy() == pd.to_datetime(chosen["issue_date"]).to_numpy()).all()):
        raise SystemExit("The saved forecasts do not line up with the P1 table's rows.")
    frame = pd.DataFrame(dict(uid=chosen["uid"].astype(str).to_numpy(), issue_date=chosen["issue_date"].to_numpy(),
                              region=chosen["region"].astype(str).to_numpy(),
                              dam_like=chosen["dam_like"].to_numpy(dtype=bool),
                              y=rows.p1_scored_label(chosen, "R30"), p=part["p90_R30"].to_numpy(dtype=float)))
    keep = frame["y"].notna().to_numpy() & frame["dam_like"].to_numpy() & is_octmar(frame["issue_date"])
    frame = join_baselines(tidy_keys(frame.loc[keep].reset_index(drop=True)), baselines)
    frame["year"] = hydro_year(frame["issue_date"])
    return frame, table, forecasts


def check_against_test_results(frame, results):
    """The totals here must equal step 15's one look; returns the list of what was checked."""
    scored = results["scores"][PRIMARY_KEY]
    y, p, p0 = (frame[c].to_numpy(dtype=float) for c in ("y", "p", "p_B0"))
    pairs = [("forecasts scored", len(frame), scored["rows"]["scored"]),
             ("fell below a third", int(y.sum()), scored["rows"]["events"]),
             ("dams", int(frame["uid"].nunique()), scored["rows"]["dams"]),
             ("average chance given", round(float(p.mean()), 5), scored["point"]["mean_p"]),
             ("share that fell", round(float(y.mean()), 5), scored["point"]["base_rate"]),
             ("skill against the usual rate (BSS vs B0)", round(brier_skill(y, p, p0), 5), scored["point"]["bss_B0"])]
    wrong = [f"{what}: here {a}, test results {b}" for what, a, b in pairs if abs(a - b) > 1e-9]
    if wrong:
        raise SystemExit("Not the scored test set; nothing written. " + "; ".join(wrong))
    return [dict(what=what, value=a) for what, a, _ in pairs]


def silo_ratios():
    rain = pd.read_pickle(REPO / "data_cache" / "silo_rain.pkl")
    return rain_by_year(rain["rain"], rain["months"], rain["cells"], sorted(REGION_WORDS))


def farm_part(table, forecasts, farm_id=FARM_ID, rewind_day=REWIND_DAY):
    """Part 3: the demo farm's dams, their 2018-19 forecasts and water levels, checked against Rewind."""
    from damdays import config
    from damdays.export import app_data as ad

    farms = read_json(APP_DIR / "farms.json")
    published = read_json(APP_DIR / "forecasts.json")
    farm = next((f for f in farms["farms"] if f["farm_id"] == farm_id), None)
    if farm is None:
        raise SystemExit(f"{farm_id} is not among the demo farms of app/data/real/farms.json.")
    if not farm["dams_in_app"]:
        raise SystemExit(f"{farm_id} is outside the region the app shows: Rewind has no forecasts for its dams.")
    dam_ids = [d["dam_id"] for d in sorted(farm["dams"], key=lambda d: int(d["name"].split()[-1]))]
    names = {d["dam_id"]: d["name"] for d in farm["dams"]}
    app_dams_by_id = {d["dam_id"]: d for d in published["dams"]}
    past_issues = [i for i in published["issues"] if i["kind"] == "past"]
    rewind = next((i for i in past_issues if i["issue_date"] == rewind_day), None)
    if rewind is None:
        raise SystemExit(f"{rewind_day} is not a Rewind date: {[i['issue_date'] for i in past_issues]}")
    rewind_rows = {r["dam_id"]: r for r in rewind["rows"]}

    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    dams = ad.app_dams(attrs, [farm["region"]])
    dams = dams[dams["dam_id"].isin(dam_ids)].reset_index(drop=True)
    if sorted(dams["dam_id"]) != sorted(dam_ids):
        raise SystemExit("The demo farm's dams are not all among the app's dams.")
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    looks = ad.dam_looks(panel, dams)
    events = pd.read_pickle(config.CACHE_DIR / "events.pkl")
    r30 = events[events["kind"] == "R30"].assign(uid=lambda e: e["uid"].astype(str))
    start, end, show_to = pd.Timestamp(SEASON_FROM), pd.Timestamp(SEASON_TO), pd.Timestamp(SHOW_TO)

    out = []
    for dam_id in dam_ids:
        uid = dams.loc[dams["dam_id"] == dam_id, "uid"].iloc[0]
        if app_dams_by_id[dam_id]["dea_uid"] != uid:
            raise SystemExit(f"{dam_id}: the app's forecasts.json names another DEA waterbody.")
        mine = forecasts[(forecasts["uid"].astype(str) == uid) & forecasts["at_risk_R30"].to_numpy(dtype=bool)]
        mine = mine[(mine["issue_date"] >= start) & (mine["issue_date"] <= end)].sort_values("issue_date")
        keys = table.loc[mine["row"].to_numpy()]
        if not (keys["uid"].astype(str).to_numpy() == uid).all():
            raise SystemExit(f"{dam_id}: forecasts and answers do not line up.")
        rows_out = []
        for f, k in zip(mine.itertuples(), keys.itertuples()):
            known = bool(k.label_ok)
            fell = bool(k.y_R30) if known else None
            fell_on = (ad.day_text(f.issue_date + pd.Timedelta(days=float(k.lab_tte_R30))) if fell else None)
            rows_out.append(dict(date=ad.day_text(f.issue_date), chance=ad.chance(f.p90_R30), fell=fell, fell_on=fell_on))
        falls = sorted(ad.day_text(d) for d in r30.loc[(r30["uid"] == uid) & (r30["start_date"] >= start)
                                                       & (r30["start_date"] <= show_to), "start_date"])
        # Every "fell" must point at a fall in the event list (the same check as the app's Rewind outcomes).
        for row in rows_out:
            if row["fell"] and row["fell_on"] not in falls:
                raise SystemExit(f"{dam_id} {row['date']}: the answer says it fell on {row['fell_on']}, "
                                 "but no fall below a third starts that day.")
        # Every Rewind date shows this dam's forecast from its last look: each must be one of these, unchanged.
        for issue in past_issues:
            row = next(r for r in issue["rows"] if r["dam_id"] == dam_id)
            if row["status"] == "forecast":
                same = [r for r in rows_out if r["date"] == row["issued_on"]]
                if len(same) != 1 or same[0]["chance"] != row["chance"] or same[0]["fell"] != row["outcome"]:
                    raise SystemExit(f"{dam_id}: Rewind's {issue['issue_date']} forecast is not among these "
                                     "forecasts, unchanged.")
        rw = rewind_rows[dam_id]
        seen = looks[(looks["uid"] == uid) & (looks["date"] >= start) & (looks["date"] <= show_to)]
        out.append(dict(
            dam_id=dam_id, name=names[dam_id], area_ha=app_dams_by_id[dam_id]["area_ha"], dea_uid=uid,
            rewind=dict(status=rw["status"], issued_on=rw["issued_on"], level_pct=rw["level_pct"], chance=rw["chance"],
                        said=chance_text(rw["chance"]) if rw["chance"] is not None else None,
                        outcome=rw["outcome"], outcome_date=rw["outcome_date"]),
            looks=[[ad.day_text(d), ad.level_pct(v)] for d, v in zip(seen["date"], seen["rel"])],
            forecasts=rows_out, falls=falls,
            summary=dam_summary(names[dam_id], rows_out, falls, closest=names[dam_id] == "Dam 1")))
    picker = [dict(name=d["name"], chance=d["rewind"]["chance"], outcome=d["rewind"]["outcome"],
                   status=d["rewind"]["status"]) for d in out]
    default = next((d["dam_id"] for d in out if d["forecasts"]), out[0]["dam_id"])
    # The tally over EVERY Rewind date (so the one shown is not picked for its result), as Rewind shows them.
    dates = []
    for issue in past_issues:
        rows = [r for r in issue["rows"] if r["dam_id"] in names and r["status"] == "forecast"]
        dates.append(dict(date=issue["issue_date"], forecasts=len(rows),
                          chance_sum=round(sum(r["chance"] for r in rows), 3),
                          fell=[names[r["dam_id"]] for r in sorted(rows, key=lambda r: dam_ids.index(r["dam_id"]))
                                if r["outcome"] is True],
                          unknown=[names[r["dam_id"]] for r in rows if r["outcome"] is None]))
    return dict(
        title="Dam by dam",
        takeaway=farm_words(farm["name"], picker, rewind_day),
        farm=dict(farm_id=farm["farm_id"], name=farm["name"], radius_km=farm["radius_km"], region=farm["region"],
                  region_name=REGION_WORDS[farm["region"]]),
        rewind_date=rewind_day, season=dict(forecasts_from=SEASON_FROM, forecasts_to=SEASON_TO, show_to=SHOW_TO),
        rewind_dates=dates, all_dates_takeaway=all_dates_words(farm["name"], dates),
        threshold_pct=int(round(config.R30_LEVEL * 100)), default_dam=default,
        how_chosen=(f"The farm is the demo farm of this week's text ({farm['name']}: the farm dams big enough for the "
                    f"satellites to see, about half a hectare to 5 hectares, within {farm['radius_km']:g} km of the "
                    "homestead point). "
                    + CHOSEN_BECAUSE.get(farm["farm_id"], "It was picked for the text, not for these results.")
                    + " Dam 1, the dam closest to the homestead, is shown first; pick any of its dams."),
        how_to_read=("Top: the dam's water level at each clear satellite look (% of its usual full level), and the "
                     "days it fell below a third. A single odd look (cloud or shadow) is drawn as it is: a fall "
                     "counts only when a later look confirms it. Bottom: every forecast made for it from July 2018 to "
                     "June 2019 "
                     "(the chance it falls below a third within 90 days); a filled dot means it did fall within those "
                     "90 days, an open dot that it did not. These are test forecasts from a model that learned only "
                     "from data before July 2016, each made only from what had been seen by that look. The app's "
                     "Rewind view shows the same forecasts on "
                     "1 Nov 2018, 1 Jan 2019 and 1 Mar 2019 (it also hides a forecast until the dam has refilled to "
                     "60% full, so a few forecasts here are not in Rewind)."),
        dams=out)


def expect_words():
    """What we said to expect from the unseen exam, in plain words, from the app's sealed panel (scripts/11)."""
    board = read_json(APP_DIR / "scoreboard.json")
    sealed = next((p for p in board.get("panels", []) if p.get("key") == "sealed"), None)
    skill = next((e for e in (sealed or {}).get("expectations", []) if e["field"] == "runway.skill_vs_usual_rate"), None)
    if skill is None:
        return None
    return (f"What we said to expect, before opening it: from {fraction_words(skill['low'])} to "
            f"{fraction_words(skill['high'])} less error than guessing the usual rate (skill {skill['low']:+.2f} to "
            f"{skill['high']:+.2f}). A forecast, not a pass mark.")


# ===========================================================================
# Main
# ===========================================================================
def build(farm_id=FARM_ID, rewind_day=REWIND_DAY):
    from damdays.evaluation.coverage import FLOOR_TARGET, FLOOR_TOLERANCE

    summary, results = read_json(FIT_SUMMARY), read_json(TEST_RESULTS)
    frame, table, forecasts = primary_frame(summary)
    checked = check_against_test_results(frame, results)
    scored = results["scores"][PRIMARY_KEY]
    slope = scored["point"]["cal_slope"]
    y, p = frame["y"].to_numpy(dtype=float), frame["p"].to_numpy(dtype=float)

    bins = calibration_bins(y, p, frame["uid"].to_numpy(), N_BOOT)
    if sum(b["forecasts"] for b in bins) != len(frame) or sum(b["fell"] for b in bins) != int(y.sum()):
        raise SystemExit("The groups do not add up to the scored set.")
    takeaway, detail, lean, not_plotted = calibration_words(bins, slope)

    floor = results["floor"]["issued_all"]
    ratios = silo_ratios()
    years = year_rows(frame, floor["by_year"], ratios)
    all_skill = scored["point"]["bss_B0"]
    year_takeaway, floor_takeaway, floor_detail = year_words_all(years, all_skill, floor, FLOOR_TARGET,
                                                                 FLOOR_TOLERANCE)
    if sum(r["forecasts"] for r in years) != len(frame) or sum(r["floor"]["judged"] for r in years) != floor["rows_judged"]:
        raise SystemExit("The years do not add up to the scored set.")
    drier = [r["year"] for r in years if r["drier"]]
    scored_at = datetime.strptime(results["scored_at"][:16], "%Y-%m-%d %H:%M")

    return dict(
        schema_version="1.0",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        made_by="scripts/17_proof_data.py",
        test=dict(
            label="Ten test years, July 2016 to June 2026",
            scored_at=results["scored_at"],
            intro=(f"The model learned only from data before July 2016. These are its forecasts for the ten "
                   f"years after, in two farming regions ({REGION_WORDS['nsw_cw']}; "
                   f"{REGION_WORDS['wvic_sesa']}), scored once on {scored_at:%a} {scored_at.day} {scored_at:%b %Y}. "
                   "The question: will this farm dam fall below a third of full within 90 days? Forecasts made "
                   "October to March, when dams run down."),
            caveat=("These years were looked at before the event, so they may flatter the model slightly. "
                    "The unseen exam is the clean test."),
            forecasts=len(frame), fell=int(y.sum()), dams=int(frame["uid"].nunique()),
            skill_vs_usual_rate=dict(value=all_skill, ci_low=scored["ci_dam"]["bss_B0"][0],
                                     ci_high=scored["ci_dam"]["bss_B0"][1], words=fraction_words(all_skill)),
            calibration_slope=slope, model=f"Tidemark {results['frozen']['rung']}, frozen (config "
                                           f"{results['frozen']['config_hash']})"),
        unseen_exam=dict(
            panel_key="sealed", heading_pending=f"Unseen exam: opens {OPENS}", expect=expect_words(),
            heading_scored="Unseen exam: opened once, on camera, scored once",
            text=("Everything below is the ten test years. The clean test is the unseen exam: a third farming region "
                  "whose satellite data we downloaded and fingerprinted before the event and then never opened or used, "
                  "kept aside for one final check. It is opened once, on camera, and its score is published here "
                  "whatever it is.")),
        calibration=dict(
            title="What we said vs what happened", takeaway=takeaway, detail=detail, lean=lean,
            not_plotted=not_plotted,
            how_to_read=("Each dot is a group of forecasts that gave the same chance (rounded as the text and the app "
                         "write it). Across: the chance we gave. Up: how often the dam really fell below a third "
                         "within 90 days. On the diagonal line, what happened equals what we said. Bigger dots hold "
                         "more forecasts; the number of forecasts is under each group. Thin lines: the range if we "
                         "re-drew the dams at random 500 times."),
            min_forecasts_to_plot=MIN_FORECASTS_TO_PLOT, bins=bins),
        by_year=dict(
            title="It held up year after year", takeaway=year_takeaway, floor_takeaway=floor_takeaway,
            floor_detail=floor_detail,
            skill_note=("Bars: how much less error the forecasts had than guessing the usual rate for that region and "
                        "month (the Brier skill score against the usual rate: 0 = no better, 1 = perfect), on each "
                        "July-June year's forecasts. Thin lines: the range if we re-drew that year's dams at random "
                        f"500 times. All ten years together: {fraction_words(all_skill)} less "
                        f"(skill {all_skill:+.3f})."),
            drier_rule=(f"Shaded: drier years, when the July-June rain, averaged over the two regions, was below its "
                        f"{RAIN_BASE_YEARS[0]}-{RAIN_BASE_YEARS[1] + 1} average (SILO rainfall, Queensland "
                        "Government). By this rule the drier years are "
                        + " and ".join(f"{year_words(a).split(' to ')[0]} to {year_words(b).split(' to ')[1]}"
                                       for a, b in runs(drier)) + "." + one_region_words(years)),
            refit_note=("The model was not refitted during these ten years: it learned only from data before July 2016. "
                        "Only each dam's own track record kept updating, once each forecast's answer was known. In use it "
                        "would be refitted as new satellite looks arrive."),
            floor_note=(f"Dots: out of 1,000 forecasts that year, how often the dam stayed above a third for at least "
                        f"the N days promised (every judged forecast, all months: {floor['rows_judged']:,} over the ten "
                        f"years). Shaded band: on target ({in_thousand(FLOOR_TARGET - FLOOR_TOLERANCE)} to "
                        f"{in_thousand(FLOOR_TARGET + FLOOR_TOLERANCE)}). Copied from the test results."),
            drier_runs=[dict(first=a, last=b, label=run_label(a, b)) for a, b in runs(drier)],
            all_years=dict(skill=all_skill, skill_ci=scored["ci_dam"]["bss_B0"], skill_words=fraction_words(all_skill),
                           floor_held=floor["coverage"], floor_judged=floor["rows_judged"],
                           floor_worst=floor["worst_year"]),
            floor_target=FLOOR_TARGET, floor_tolerance=FLOOR_TOLERANCE, years=years),
        dam_by_dam=farm_part(table, forecasts, farm_id, rewind_day),
        sources=dict(
            forecasts=f"{FORECASTS_FILE} (scripts/13; fingerprint {next(f['fingerprint'] for f in summary['files'] if f['path'] == FORECASTS_FILE)}, as scored by scripts/15)",
            usual_rate=f"{BASELINES_FILE} (B0: the usual rate for the region and month, fitted before July 2016)",
            answers=f"{ANSWER_FILE} (the PREREG R30 labels)",
            test_results="artifacts/test_results.json (scripts/15): the totals here equal it; the promise by year is copied from it",
            rain="data_cache/silo_rain.pkl (SILO monthly rainfall, Queensland Government, CC BY 4.0)",
            farm="app/data/real/farms.json (scripts/16) and app/data/real/forecasts.json (Rewind, scripts/11)"),
        checks=dict(equal_to_test_results=checked, ledger="nothing scored on the TEST ledger"),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="build and check everything; write nothing")
    parser.add_argument("--farm", default=FARM_ID, help="the demo farm of the dam-by-dam panel (default %(default)s)")
    parser.add_argument("--rewind-day", default=REWIND_DAY,
                        help="the Rewind date of its takeaway (default %(default)s; 2019-01-01 and 2019-03-01 also)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    proof = build(args.farm, args.rewind_day)
    print("1. " + proof["calibration"]["takeaway"])
    print("   " + proof["calibration"]["detail"])
    print("   " + proof["calibration"]["lean"])
    print("2. " + proof["by_year"]["takeaway"])
    print("   " + proof["by_year"]["floor_takeaway"])
    print("   " + proof["by_year"]["floor_detail"])
    print("   " + str(proof["unseen_exam"]["expect"]))
    print("3. " + proof["dam_by_dam"]["takeaway"])
    print("   " + proof["dam_by_dam"]["all_dates_takeaway"])
    for dam in proof["dam_by_dam"]["dams"]:
        print("   " + dam["summary"])
    if args.check:
        print("CHECK ONLY: nothing written.")
        return 0
    OUT.write_text(json.dumps(proof, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO)} ({OUT.stat().st_size / 1024:.0f} KB)")
    subprocess.run([sys.executable, str(BUNDLE_TOOL), str(APP_DIR)], check=True, cwd=REPO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
