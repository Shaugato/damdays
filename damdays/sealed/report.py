"""The results page of a sealed-region run (markdown for people, JSON for code).

Every number is copied from the scorecard results (damdays.evaluation.score), which are also
saved one JSON per score in the run's scorecard folder the moment they are computed. Nothing is
recomputed or rounded here except for display.
"""
import json
import math

from damdays.evaluation.report import clean_for_json
from damdays.models import rows, tidemark

PRIMARY = "dam_like+octmar+at_risk"
SUBSET_LABELS = {PRIMARY: "primary (dam-like, Oct-Mar, at risk)",
                 "persistent+octmar+at_risk": "persistent dams (Oct-Mar, at risk)",
                 "dam_like+at_risk": "dam-like, all months (at risk)"}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def num(value, digits=3, sign=True):
    """A number for a table cell ("-" when missing)."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "-"
    return f"{value:+.{digits}f}" if sign else f"{value:.{digits}f}"


def with_ci(result, metric, digits=3, sign=True):
    """value [dam 95% CI] from a score() result."""
    text = num(result["point"].get(metric), digits, sign)
    ci = result.get("ci_dam", {}).get(metric)
    return text + (f" [{num(ci[0], digits, sign)}, {num(ci[1], digits, sign)}]" if ci else "")


def pass_fail(flag):
    return "**PASS**" if flag else "**FAIL**"


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def verdict_lines(v, name):
    """The PREREG pass bars and the kill rule."""
    lines = ["## PREREG verdicts", ""]
    for who, bars in (("Tidemark", v["p1_pass_bars_tidemark"]), ("G2", v["p1_pass_bars_g2"])):
        lines.append(f"- **P1 pass bars, {who}** (R30, primary set): BSS vs B0 {num(bars['bss_B0']['value'])} "
                     f"(dam CI low {num(bars['bss_B0']['ci_low'])}; bar >= +0.10 with CI above 0) "
                     f"{pass_fail(bars['bss_B0']['passed'])}; BSS vs B2 {num(bars['bss_B2']['value'])} (bar >= +0.05) "
                     f"{pass_fail(bars['bss_B2']['passed'])}; calibration slope {num(bars['cal_slope']['value'], 2, False)} "
                     f"(bar 0.8-1.2) {pass_fail(bars['cal_slope']['passed'])}. "
                     f"All three: {pass_fail(bars['all_passed'])}.")
    for task in ("p2_cell", "p2_dam"):
        p2 = v[task]
        ci = p2["ci_dam"]
        lines.append(f"- **P2 pass bar, {task.replace('p2_', '')} rating**: AUC gain over RAIN {num(p2['d_auc_vs_RAIN'])}"
                     + (f" [{num(ci[0])}, {num(ci[1])}]" if ci else "") + f" (bar {p2['bar']}) {pass_fail(p2['passed'])}. "
                     f"Kill rule (RAIN within 0.02 AUC of the rating): "
                     f"{'**TRIGGERED**: drop the finance claim' if p2['kill_rule_triggered'] else 'not triggered'}.")
    return lines + [""]


def expectation_lines(v):
    lines = ["## Pre-declared expectations (PREREG; forecasts, not pass bars)", "",
             "| expectation | declared range | got [dam 95% CI] | verdict |", "|---|---|---|---|"]
    for e in v["expectations"]:
        declared = f"{num(e['low'], 2)} to {num(e['high'], 2)}" + (f" (central {num(e['central'], 2)})"
                                                                   if e["central"] is not None else "")
        ci = e["ci_dam"]
        got = num(e["got"], 3) + (f" [{num(ci[0])}, {num(ci[1])}]" if ci else "")
        lines.append(f"| {e['expectation']} | {declared} | {got} | {e['verdict']} |")
    return lines + [""]


def p1_lines(scores, name):
    lines = ["## P1, the farmer runway: Tidemark and G2 (BSS = Brier skill score)", "",
             "Brackets: 95% interval from resampling dams. 'Tidemark minus G2' is paired: same forecasts, same "
             "resamples, in BSS-vs-B0 units.", "",
             "| kind | subset | rows | events | G2 BSS vs B0 | Tidemark BSS vs B0 | Tidemark minus G2 | Tidemark BSS vs B2 "
             "| Tidemark AUC | slope | CITL |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for task in ([f"P1_{k}" for k in rows.P1_KINDS] + [f"P1_{k}_sens" for k in rows.P1_KINDS]):
        for subset, label in SUBSET_LABELS.items():
            tm, g2 = scores.get((task, subset, "tidemark")), scores.get((task, subset, "G2"))
            if tm is None:
                continue
            kind = task.replace("P1_", "").replace("_sens", " (sensitivity: no 3-look rule)")
            lines.append(f"| {kind} | {label} | {tm['rows']['scored']:,} | {tm['rows']['events']:,} "
                         f"| {with_ci(g2, 'bss_B0')} | {with_ci(tm, 'bss_B0')} | {with_ci(tm, 'd_bss_B0_vs_' + name('G2'))} "
                         f"| {with_ci(tm, 'bss_B2')} | {with_ci(tm, 'auc', sign=False)} "
                         f"| {num(tm['point']['cal_slope'], 2, False)} | {num(tm['point']['citl'], 2)} |")
    return lines + [""]


def curve_lines(curves):
    lines = ["## Runway curve (Tidemark), BSS against each horizon's own base rate B0_h", "",
             "| curve | subset | 30 days | 60 days | 90 days | 180 days | rows with a falling curve |",
             "|---|---|---|---|---|---|---|"]
    for (task, subset), result in curves.items():
        cells = " | ".join(num(result["bss_B0_by_horizon"].get(h)) for h in tidemark.HORIZONS)
        lines.append(f"| {task} | {SUBSET_LABELS.get(subset, subset)} | {cells} "
                     f"| {result['monotonicity']['share_rows_falling']:.4f} |")
    return lines + [""]


def p2_lines(scores, name):
    lines = ["## P2, the season rating (issued 1 July 2016 to 2025; dry-out in the following Oct-Mar)", "",
             "| rating | rows | dry | Tidemark AUC | gain over RAIN | gain over RAIN+ | gain over B2 | AUC within a season "
             "(Tidemark / RAIN) | RAIN AUC |", "|---|---|---|---|---|---|---|---|---|"]
    for task, subset in (("P2_cell", "all"), ("P2_dam", "dam_like"), ("P2_dam_g", "dam_like")):
        tm, rain = scores.get((task, subset, "tidemark")), scores.get((task, subset, "RAIN"))
        if tm is None:
            continue
        lines.append(f"| {task} | {tm['rows']['scored']:,} | {tm['rows']['events']:,} | {with_ci(tm, 'auc', sign=False)} "
                     f"| {with_ci(tm, 'd_auc_vs_' + name('RAIN'))} | {with_ci(tm, 'd_auc_vs_' + name('RAIN+'))} "
                     f"| {with_ci(tm, 'd_auc_vs_' + name('B2'))} "
                     f"| {num(tm['point'].get('auc_within_season'), 3, False)} / "
                     f"{num(rain['point'].get('auc_within_season'), 3, False)} | {num(rain['point']['auc'], 3, False)} |")
    return lines + [""]


def band_floor_lines(band, floor):
    lines = ["## Season band and DamDays floor", "",
             "Season band: a region-year (one July-June year) is covered when its offset (how far that year's forecasts "
             "were off, in log-odds) lies inside the band.", "",
             "| kind | pooled band (shipped) | covered | single-block band (2009-2016) | covered | drier than the band "
             "| wetter than the band |", "|---|---|---|---|---|---|---|"]
    for kind, b in band.items():
        pooled, single = b["pooled"], b["single_block_2009_2016"]
        lines.append(f"| {kind} | [{num(pooled['band'][0])}, {num(pooled['band'][1])}] "
                     f"| {pooled['covered']}/{pooled['region_years']} "
                     f"| [{num(single['band'][0])}, {num(single['band'][1])}] | {single['covered']}/{single['region_years']} "
                     f"| {', '.join(pooled['drier_than_band']) or '-'} | {', '.join(pooled['wetter_than_band']) or '-'} |")
    lines += ["", "DamDays floor (\"at least N days above a third, 9 times in 10\"): share of floors that held "
              "(target 0.90).", "", "| forecasts | judged | held | median floor (days) | worst July-June year |",
              "|---|---|---|---|---|"]
    for label, key in (("all, as issued", "issued_all"), ("primary set, as issued", "issued_primary"),
                       ("all, as shown (180+ cap)", "shown_all")):
        f = floor[key]
        worst = f.get("worst_year")
        worst_text = "{}: {:.3f}".format(worst["year"], worst["coverage"]) if worst else "-"
        lines.append(f"| {label} | {f['rows_judged']:,} | {num(f['coverage'], 3, False)} "
                     f"| {num(f['median_floor_days'], 0, False)} | {worst_text} |")
    return lines + [""]


def not_scored_lines(not_scored):
    """Subsets that could not be scored (no labelled rows, or not both events and non-events)."""
    if not not_scored:
        return []
    return (["## Subsets that could not be scored", "",
             "They need labelled forecasts with both events and non-events. Nothing was put on the ledger for them.", "",
             "| task | subset | model | labelled rows | events |", "|---|---|---|---|---|"]
            + [f"| {n['task']} | {n['subset']} | {n['model']} | {n['rows']:,} | {n['events']:,} |" for n in not_scored]
            + [""])


def code_line(checks, rehearsal):
    """The config hash of the code that ran, and which committed addendum quotes it (and the evaporation hash)."""
    code_hash = checks.get("config_hash_of_running_code")
    text = (f"- **Code**: event build config hash of the code that ran `{code_hash[:12]}` (recipe of "
            f"`scripts/14_config_hash.py`)" if code_hash else "- **Code**: config hash not computed")
    if rehearsal:
        return text + " (a dry run does not compare it with the freeze addendum)."
    quoted = checks.get("freeze_addendum", {})
    return (text + (f"; quoted in {', '.join(quoted['config_hash'])}" if quoted.get("config_hash")
                    else "; NOT quoted in any committed addendum (expected only after a logged crash fix)")
            + f". The sealed evaporation SHA-256 is quoted in {', '.join(quoted.get('evaporation', []))}.")


def run_lines(r):
    counts, checks, manifest = r["counts"], r["checks"], r["models_manifest"]
    files = checks["files"]
    verified = ("the dry run's own region files, against the list it made on its first run (the sealed folder is "
                "never touched by a dry run)" if r["run"]["rehearsal"] else "the sealed files")
    lines = ["## What was run", "",
             f"- **Checks before opening**: {checks['hash_list']['files']:,} files in the committed SEALED_HASHES.csv "
             f"(commit {checks['hash_list']['commit'][:12]}, {checks['hash_list']['committed_at']}, never changed). "
             f"Files verified ({verified}): {files['n_matched']:,} of {files['n_listed']:,} match their SHA-256 "
             f"(missing {len(files['missing'])}, extra {len(files['extra'])}, different {len(files['mismatched'])}). "
             f"git clean: {checks['git']['clean']}; HEAD {checks['git']['head'][:12]} pushed: {checks['git']['pushed']}"
             + (" (reported only in a dry run)." if r["run"]["rehearsal"] else "."),
             code_line(checks, r["run"]["rehearsal"]),
             f"- **Models** (fitted on {', '.join(manifest['fit_regions'])}, answers final before {manifest['cutoff']}): "
             f"Tidemark rung {manifest['rung']}, file SHA-256 {manifest['files']['tidemark']['sha256'][:16]}...; "
             f"G2 {manifest['files']['g2']['sha256'][:16]}...; water-balance parameters "
             f"{manifest['files']['physics']['sha256'][:16]}... (manifest `{r['manifest_path']}`).",
             f"- **Region** {counts['region']}: {counts['waterbodies_in_manifest']:,} waterbodies, "
             f"{counts['valid_looks']:,} valid looks ({counts['first_look']} to {counts['last_look']}); "
             f"{counts['has_hist']:,} with history, {counts['dam_like']:,} dam-like, {counts['persistent']:,} persistent "
             f"(flags from the region's own pre-2016 looks). TEST issues: {counts['p1_issues_by_block']['TEST']:,}; "
             f"R30 primary TEST rows {counts['r30_primary_test_rows']:,} ({counts['r30_primary_test_events']:,} events); "
             f"P2 dam-like TEST seasons {counts['p2_dam_like_test_seasons']:,}; 2 km cells {counts['p2_cells']:,}.",
             f"- **Evaporation shape** used by the water balance: {r['evaporation']['text']} "
             f"(SHA-256 {r['evaporation']['sha256'][:16]}...).",
             f"- **Ledger**: `{r['ledger_path']}` ({r['ledger_rows_written']} rows written by this run; "
             f"statuses: {r['ledger_statuses']})."]
    if r.get("store_comparison") is not None:
        c = r["store_comparison"]
        near_end = c.get("p1_data_end_rows")
        lines.append(f"- **Same-code check (dry run)**: the region rebuilt from raw files equals its rows in the "
                     f"development feature store: **{c['identical_apart_from_folds']}** (fold numbers aside; "
                     f"unexplained differences: {c['unexplained_differences']})."
                     + (f" {near_end['rows'][0]:,} P1 rows near the archive's end differ only in "
                        f"{sorted(near_end['differing'])}: {near_end['about']}." if near_end else ""))
    if r.get("reused"):
        lines.append(f"- **Resumed run**: {' and '.join(r['reused'])} were reloaded from an earlier run of the same "
                     "command (the crash-resume path), so exactly the same forecasts were scored; the stage times "
                     "below are this run's.")
    lines += ["", "| stage | minutes |", "|---|---|"]
    lines += [f"| {stage} | {seconds / 60:.1f} |" for stage, seconds in r["timing"].items()]
    return lines + [""]


def markdown(r):
    """The whole results page."""
    run = r["run"]
    title = "# DRY RUN (rehearsal) of the sealed-region opening" if run["rehearsal"] else "# Sealed-region results"
    lines = [title, ""]
    if run["rehearsal"]:
        lines += [f"> **This is a rehearsal, not a result.** The region scored here ({run['target_region']}) is a "
                  "DEVELOPMENT region treated as if it were unseen: the models learned from "
                  f"{', '.join(run['fit_regions'])} only. Its numbers are a transfer rehearsal (one development "
                  "region's models judged on the other region), **NOT the development TEST result** and not the sealed "
                  "result. They went on a separate dry-run ledger and are never used to choose or change anything.", ""]
    else:
        lines += ["> Opened once, as pre-registered (PREREG \"Sealed region protocol\"). Every number is published "
                  "whatever it shows. Nothing changes after opening except crash fixes that do not change "
                  "predictions, each logged with its time.", ""]
    lines += [f"Generated by `scripts/20_open_sealed_region.py` at {r['finished_at']}. {run['about']}", ""]
    name = r["name"]
    lines += verdict_lines(r["verdicts"], name) + expectation_lines(r["verdicts"])
    lines += p1_lines(r["scores"], name) + curve_lines(r["curves"]) + p2_lines(r["scores"], name)
    lines += band_floor_lines(r["band"], r["floor"]) + not_scored_lines(r.get("not_scored", [])) + run_lines(r)
    return "\n".join(lines) + "\n"


def write(r, run):
    """Write the results page and the JSON (scores keyed "task | subset | model")."""
    run.results_dir.mkdir(parents=True, exist_ok=True)
    run.results_md.write_text(markdown(r), encoding="utf-8")
    plain = dict(r, scores={" | ".join(k): v for k, v in r["scores"].items()},
                 curves={" | ".join(k): v for k, v in r["curves"].items()})
    plain.pop("name", None)
    run.results_json.write_text(json.dumps(clean_for_json(plain), indent=1, default=str), encoding="utf-8")
