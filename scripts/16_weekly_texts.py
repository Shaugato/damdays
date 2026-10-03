"""Step 16: this week's DamDays texts for ten demo farms, from the live forecasts.

Run from the repo folder (seconds):
    .venv/Scripts/python.exe scripts/16_weekly_texts.py                  # texts dated today
    .venv/Scripts/python.exe scripts/16_weekly_texts.py --date 2026-10-02
    .venv/Scripts/python.exe scripts/16_weekly_texts.py --regions nsw_cw # without data_cache: the app's region only
    .venv/Scripts/python.exe scripts/16_weekly_texts.py --set-aside ""   # keep every demo farm (default: farm-d set aside)

What it does
  1. LIVE FORECASTS of each development region, the same numbers the app shows:
     - NSW Central West: the app's published file, app/data/real/forecasts.json.
     - western Victoria / SE South Australia (not in the app, which shows one region): rebuilt from
       the same saved production fit (data_cache/preds/LIVE/tidemark/L3_live.pkl) with the app
       exporter's own functions (damdays.export.app_data, used unchanged), exactly as
       scripts/11_export_app.py does. As a check, NSW is rebuilt the same way and must equal
       the published file row for row.
     Nothing is fitted or scored here, and nothing under damdays/ is changed.
  2. DEMO FARMS: 5 per region, each a homestead point in the middle of a real cluster of dams.
     For every dam, take the centre of the dams within 3 km of it; rank those points by how many
     dams lie within 3 km; keep the best five that are at least 25 km apart. They are named
     neutrally after the nearest town ("Farm A (near Orange)"). They are NOT real homesteads.
     A farm whose waterbodies turned out not to be farm dams on aerial photos is SET ASIDE (SET_ASIDE:
     Farm D, near Dubbo): it keeps its letter, so the others keep theirs, but it gets no text and is
     listed only under farms.json's "set_aside", with the reason.
  3. THE TEXTS (notify.message): one SMS per farm and its longer app/email version, written to
       outbox/<date>.json                    the week's texts, ready for notify/sms.py (dry run by default)
       app/data/real/farms.json              the demo farms, their dams and texts, for the app
                                             (then app/tools/build_bundle.py packs it into the app's bundle.js)
       notify/fixtures/demo_week.json        inputs and expected texts, to check the app's JavaScript port
       notify/fixtures/spec_examples.json    the same for the worked examples of notify/MESSAGE_SPEC.md
"""
import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from notify import examples, gsm7  # noqa: E402
from notify.farms import DEFAULT_RADIUS_KM, Farm, dams_for_farm, distance_km, live_issue, to_10_metres  # noqa: E402
from notify.message import days_left, kind, long_for_dams, sms_for_dams  # noqa: E402
from notify.outbox import message_record, write_outbox  # noqa: E402

APP_FORECASTS = REPO / "app" / "data" / "real" / "forecasts.json"
APP_META = REPO / "app" / "data" / "real" / "meta.json"
FARMS_JSON = REPO / "app" / "data" / "real" / "farms.json"
BUNDLE_TOOL = REPO / "app" / "tools" / "build_bundle.py"     # packs farms.json into the app's bundle.js
FIXTURES = REPO / "notify" / "fixtures"
REGION_NAMES = {"nsw_cw": "NSW Central West", "wvic_sesa": "western Victoria / SE South Australia"}
FARMS_PER_REGION = 5
FARM_SPACING_KM = 25            # demo farms at least this far apart
FIXTURE_MARGIN_KM = 1.0         # the fixture keeps dams up to 1 km beyond each radius (to test the cut-off)

# Demo farms set aside after a check of every demo farm against aerial photos (Sat 3 Oct 2026). The cluster
# search still finds them (so the other farms keep their letters); they get no text, and farms.json lists them
# under "set_aside" with the reason. `name` guards against the search ever picking a different place.
SET_ASIDE = {
    "farm-d": dict(
        name="Farm D (near Dubbo)",
        reason=("Set aside: on aerial photos its waterbodies are not farm dams. Three are cells of one "
                "treatment-pond complex at the edge of Dubbo; the others include a pond at a racecourse, a garden "
                "pond at the town edge and a stretch of the Macquarie River. They passed the filter that picks "
                "dam-sized waterbodies, which is why we checked the demo farms against aerial photos.")),
}

# Approximate town centres (degrees, from public maps), used ONLY to give each demo farm a
# neutral name: "Farm A (near Orange)". Nothing else uses them.
TOWNS = {
    "nsw_cw": {
        "Dubbo": (-32.25, 148.60), "Orange": (-33.28, 149.10), "Bathurst": (-33.42, 149.58),
        "Mudgee": (-32.59, 149.59), "Wellington": (-32.56, 148.94), "Parkes": (-33.14, 148.18),
        "Forbes": (-33.38, 148.01), "Narromine": (-32.23, 148.24), "Gilgandra": (-31.71, 148.66),
        "Coonabarabran": (-31.27, 149.28), "Gulgong": (-32.36, 149.53), "Molong": (-33.09, 148.87),
        "Rylstone": (-32.80, 149.97), "Kandos": (-32.86, 149.97), "Warren": (-31.70, 147.84),
        "Trangie": (-32.03, 147.98), "Nyngan": (-31.56, 147.19), "Peak Hill": (-32.72, 148.19),
        "Coolah": (-31.83, 149.72), "Dunedoo": (-32.02, 149.40), "Coonamble": (-30.95, 148.39),
        "Condobolin": (-33.09, 147.15), "Tottenham": (-32.24, 147.36), "Trundle": (-32.92, 147.71),
        "Yeoval": (-32.75, 148.65), "Cumnock": (-32.93, 148.75), "Blayney": (-33.53, 149.25),
        "Canowindra": (-33.56, 148.67), "Eugowra": (-33.43, 148.37), "Cudal": (-33.29, 148.74),
        "Manildra": (-33.19, 148.69), "Baradine": (-30.94, 149.07), "Binnaway": (-31.55, 149.38),
        "Mendooran": (-31.82, 149.12), "Lithgow": (-33.48, 150.16), "Hill End": (-33.03, 149.42),
    },
    "wvic_sesa": {
        "Hamilton": (-37.74, 142.02), "Horsham": (-36.71, 142.20), "Ararat": (-37.28, 142.93),
        "Stawell": (-37.06, 142.78), "Naracoorte": (-36.96, 140.74), "Penola": (-37.38, 140.84),
        "Casterton": (-37.58, 141.40), "Coleraine": (-37.60, 141.69), "Edenhope": (-37.04, 141.30),
        "Harrow": (-37.16, 141.59), "Balmoral": (-37.25, 141.84), "Cavendish": (-37.53, 142.04),
        "Dunkeld": (-37.65, 142.34), "Glenthompson": (-37.64, 142.55), "Willaura": (-37.54, 142.74),
        "Halls Gap": (-37.14, 142.52), "Great Western": (-37.15, 142.86), "St Arnaud": (-36.62, 143.26),
        "Avoca": (-37.09, 143.47), "Skipton": (-37.69, 143.36), "Beaufort": (-37.43, 143.38),
        "Mortlake": (-38.08, 142.81), "Penshurst": (-37.87, 142.29), "Macarthur": (-38.03, 142.00),
        "Branxholme": (-37.86, 141.79), "Merino": (-37.72, 141.55), "Heywood": (-38.13, 141.63),
        "Mount Gambier": (-37.83, 140.78), "Millicent": (-37.59, 140.35), "Lucindale": (-36.97, 140.37),
        "Kaniva": (-36.38, 141.24), "Nhill": (-36.33, 141.65), "Natimuk": (-36.74, 141.94),
        "Goroke": (-36.72, 141.47), "Apsley": (-36.97, 141.08), "Bordertown": (-36.31, 140.77),
        "Lake Bolac": (-37.71, 142.84), "Camperdown": (-38.23, 143.15), "Lismore": (-37.95, 143.34),
    },
}


def log(text):
    print(text, flush=True)


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ===========================================================================
# 1. Live forecasts of each region
# ===========================================================================
def rebuilt_live_forecasts(regions):
    """forecasts.json-shaped documents (live issue only) rebuilt from the saved production fit.

    The same calls as scripts/11_export_app.py (live_forecasts and live_issue), without a refit.
    """
    import pandas as pd                                         # only this step needs pandas
    from damdays import config
    from damdays.export import app_data as ad
    from damdays.export import live_model
    from damdays.models.predictions import load_predictions, prediction_path

    rung = json.loads(APP_META.read_text(encoding="utf-8"))["model"]["version"]
    name = f"{rung}_live"
    path = prediction_path(live_model.PRED_BLOCK, live_model.PRED_TASK, name)
    summary_path = path.with_name(f"{name}_summary.json")
    for needed in (path, summary_path, config.CACHE_DIR / "panel.pkl"):
        if not Path(needed).exists():
            raise SystemExit(f"Missing {needed}: the live forecasts of regions outside the app need data_cache "
                             "(scripts 01-11). Run with --regions nsw_cw to use the app's published file only.")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    events = pd.read_pickle(config.CACHE_DIR / "events.pkl")
    last_day = live_model.last_look_date()
    summary = json.loads(summary_path.read_text())
    if summary["cutoff"] != str(live_model.live_cutoff(last_day).date()):
        raise SystemExit(f"The saved live fit ({summary['cutoff']}) is older than the data: run scripts/11 first.")
    preds = load_predictions(live_model.PRED_BLOCK, live_model.PRED_TASK, name)
    band = tuple(summary["band_exact"]["R30"])
    docs = {}
    for region in regions:
        dams = ad.app_dams(attrs, [region])
        table, _ = ad.issue_tables(dams, ad.dam_looks(panel, dams), events, last_day, preds, band)
        note = (f"Tidemark {rung} fitted on every answer known by {ad.day_text(last_day)} (production fit). "
                "Each dam's forecast starts from its latest clear satellite look.")
        docs[region] = dict(horizon_days=config.HORIZON_DAYS, dams=ad.dams_json(dams),
                            issues=[ad.issue_json(table, last_day, "live", "Latest forecast", note)])
    return docs, f"data_cache/preds/LIVE/tidemark/{name}.pkl"


def live_forecasts(regions):
    """{region: forecasts document} and a sentence saying where each came from."""
    app_region = json.loads(APP_META.read_text(encoding="utf-8"))["region"]["key"]
    app_doc = json.loads(APP_FORECASTS.read_text(encoding="utf-8"))
    others = [r for r in regions if r != app_region]
    docs, sources = {}, []
    if app_region in regions:
        docs[app_region] = app_doc
        sources.append(f"{REGION_NAMES[app_region]}: app/data/real/forecasts.json (the app's published file)")
    if others:
        rebuilt, fit_file = rebuilt_live_forecasts([app_region, *others])
        # The check: the app's region, rebuilt the same way, equals the published file row for row.
        published_live = live_issue(app_doc)
        if (rebuilt[app_region]["dams"] != app_doc["dams"]
                or live_issue(rebuilt[app_region])["rows"] != published_live["rows"]):
            raise SystemExit("The rebuilt live forecasts differ from app/data/real/forecasts.json: "
                             "re-export the app (scripts/11) before making texts.")
        log(f"check passed: {app_region} rebuilt from {fit_file} equals the app's published file, row for row")
        for region in others:
            docs[region] = rebuilt[region]
            sources.append(f"{REGION_NAMES[region]}: the same production fit ({fit_file}), rebuilt with "
                           "damdays.export.app_data as scripts/11 does")
    return docs, app_region, "Live DamDays forecasts. " + "; ".join(sources) + "."


# ===========================================================================
# 2. Demo farms at real dam clusters
# ===========================================================================
def dams_near(doc, lat, lon, radius_km):
    return [d for d in doc["dams"] if to_10_metres(distance_km(lat, lon, d["lat"], d["lon"])) <= radius_km]


def cluster_points(doc, radius_km):
    """Candidate homesteads: for each dam, the centre of the dams within radius_km of it,
    with how many dams lie within radius_km of that centre. Densest first."""
    points = {}
    for dam in doc["dams"]:
        near = dams_near(doc, dam["lat"], dam["lon"], radius_km)
        lat = round(sum(d["lat"] for d in near) / len(near), 3)
        lon = round(sum(d["lon"] for d in near) / len(near), 3)
        points[(lat, lon)] = len(dams_near(doc, lat, lon, radius_km))
    return sorted(points.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))


def nearest_town(region, lat, lon):
    name, (town_lat, town_lon) = min(TOWNS[region].items(),
                                     key=lambda item: distance_km(lat, lon, *item[1]))
    return name, round(distance_km(lat, lon, town_lat, town_lon), 1)


def demo_farms(region, doc, first_letter, radius_km):
    """The region's demo farms: the densest dam clusters, at least FARM_SPACING_KM apart."""
    picked = []
    for (lat, lon), n_dams in cluster_points(doc, radius_km):
        if all(distance_km(lat, lon, p[0], p[1]) >= FARM_SPACING_KM for p in picked):
            picked.append((lat, lon, n_dams))
        if len(picked) == FARMS_PER_REGION:
            break
    farms = []
    for i, (lat, lon, n_dams) in enumerate(picked):
        letter = chr(ord(first_letter) + i)
        town, town_km = nearest_town(region, lat, lon)
        farm = Farm(farm_id=f"farm-{letter.lower()}", lat=lat, lon=lon, radius_km=radius_km,
                    name=f"Farm {letter} (near {town})")
        farms.append(dict(farm=farm, region=region, town=town, town_km=town_km))
    return farms


# ===========================================================================
# 3. Texts, outbox, farms.json and fixtures
# ===========================================================================
def farm_json(farm):
    return dict(farm_id=farm.farm_id, name=farm.name, lat=farm.lat, lon=farm.lon, radius_km=farm.radius_km)


def app_dam(dam, today):
    """One dam in farms.json: its forecast row, what the text says about it, and its days left today."""
    what = kind(dam, today)
    return dict(dam.as_json(), text_kind=what, days_left=days_left(dam, today) if what == "forecast" else None)


def fixture_doc(doc, farms):
    """A forecasts document cut down to the dams near the given farms (radius + 1 km)."""
    keep = {d["dam_id"] for f in farms
            for d in dams_near(doc, f.lat, f.lon, f.radius_km + FIXTURE_MARGIN_KM)}
    live = live_issue(doc)
    return dict(horizon_days=doc["horizon_days"], dams=[d for d in doc["dams"] if d["dam_id"] in keep],
                issues=[dict(live, rows=[r for r in live["rows"] if r["dam_id"] in keep])])


def spec_examples_fixture():
    """notify/fixtures/spec_examples.json: the worked examples' inputs and expected texts."""
    forecasts, farms = examples.build_examples()
    cases = []
    for example, farm in farms:
        dams = dams_for_farm(farm, forecasts)
        cases.append(dict(key=example["key"], title=example["title"], farm=farm_json(farm),
                          dam_ids=[d.dam_id for d in dams],
                          sms=sms_for_dams(dams, examples.TODAY, farm.radius_km),
                          long=long_for_dams(dams, examples.TODAY, farm.name, farm.radius_km)))
    return dict(about=("Worked examples of notify/MESSAGE_SPEC.md (made-up numbers). For each case: run the "
                       "farm against `forecasts` on `today`; the dams (closest first) must be `dam_ids`, and "
                       "the texts must equal `sms` and `long` exactly. Made by scripts/16_weekly_texts.py "
                       "from notify/examples.py."),
                today=examples.TODAY, forecasts=forecasts, cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", default=str(date.today()), help="the day the texts are for (default: today)")
    parser.add_argument("--regions", default="nsw_cw,wvic_sesa",
                        help="development regions, comma-separated (default both; nsw_cw alone needs no data_cache)")
    parser.add_argument("--radius", type=float, default=DEFAULT_RADIUS_KM, help="farm radius in km (default 3)")
    parser.add_argument("--set-aside", default=",".join(SET_ASIDE),
                        help="demo farms to set aside, comma-separated (default: %(default)s; \"\" keeps every farm); "
                             "each needs a reason in SET_ASIDE")
    args = parser.parse_args()
    today = date.fromisoformat(args.date)
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    unknown = [r for r in regions if r not in REGION_NAMES]
    if unknown:
        parser.error(f"unknown region(s) {unknown}; choose from {list(REGION_NAMES)}")
    set_aside_ids = [f.strip() for f in args.set_aside.split(",") if f.strip()]
    no_reason = [f for f in set_aside_ids if f not in SET_ASIDE]
    if no_reason:
        parser.error(f"no reason recorded in SET_ASIDE for {no_reason}")

    docs, app_region, source = live_forecasts(regions)
    farms = []
    for i, region in enumerate(regions):
        farms += demo_farms(region, docs[region], chr(ord("A") + FARMS_PER_REGION * i), args.radius)

    # Set aside the farms whose waterbodies are not farm dams (they keep their letters; see SET_ASIDE).
    set_aside = []
    for item in [f for f in farms if f["farm"].farm_id in set_aside_ids]:
        farm = item["farm"]
        if farm.name != SET_ASIDE[farm.farm_id]["name"]:
            raise SystemExit(f"{farm.farm_id} is now {farm.name!r}, not {SET_ASIDE[farm.farm_id]['name']!r}: the "
                             "cluster search picked another place; check SET_ASIDE before setting it aside.")
        set_aside.append(dict(farm_id=farm.farm_id, name=farm.name, region=item["region"],
                              reason=SET_ASIDE[farm.farm_id]["reason"]))
        log(f"set aside: {farm.name} ({SET_ASIDE[farm.farm_id]['reason']})")
    farms = [f for f in farms if f["farm"].farm_id not in set_aside_ids]

    messages, app_farms, cases = [], [], []
    for item in farms:
        farm, region = item["farm"], item["region"]
        doc = docs[region]
        dams = dams_for_farm(farm, doc)
        sms = sms_for_dams(dams, today, farm.radius_km)
        long = long_for_dams(dams, today, farm.name, farm.radius_km)
        record = message_record(farm, dams, sms, long)
        messages.append(dict(record, region=region))
        app_farms.append(dict(farm_json(farm), region=region, region_name=REGION_NAMES[region],
                              near_town=item["town"], town_km=item["town_km"],
                              dams_in_app=region == app_region, data_through=live_issue(doc)["issue_date"],
                              dams=[app_dam(dam, today) for dam in dams],
                              sms=sms, sms_septets=record["sms_septets"], long=long))
        cases.append(dict(farm=farm_json(farm), region=region, dam_ids=[d.dam_id for d in dams],
                          sms=sms, long=long))
        log(f"\n{farm.name}, {REGION_NAMES[region]} ({farm.lat}, {farm.lon}): {len(dams)} dams within "
            f"{farm.radius_km:g} km; SMS {record['sms_septets']} of {gsm7.SMS_MAX} places")
        log("  " + sms.replace("\n", "\n  "))

    made_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    outbox = write_outbox(today, messages, source)
    write_json(FARMS_JSON, dict(
        schema_version="1.0", generated_at=made_at, date=str(today), radius_km=args.radius,
        about=("Demo farms for the weekly text. Each homestead point is placed in the middle of a real cluster "
               "of dam-sized waterbodies, mostly farm dams (the densest clusters, at least 25 km apart), and named "
               "after the nearest town; they are not real homesteads. A farm's dams are the dams within its "
               "radius: we have no property boundaries. Texts made by notify.message from the live forecasts "
               "(scripts/16_weekly_texts.py). `dams_in_app` is false for farms outside the region the app shows. "
               "`set_aside`: farms found the same way but left out, with the reason."),
        source=source, farms=app_farms, set_aside=set_aside))
    write_json(FIXTURES / "demo_week.json", dict(
        about=("The demo farms' texts for one week, to check the app's JavaScript port. For each case: run "
               "the farm against forecasts[region] on `today`; the dams (closest first) must be `dam_ids`, "
               "and the texts must equal `sms` and `long`. `forecasts` keeps only the dams within each "
               "farm's radius plus 1 km. Made by scripts/16_weekly_texts.py."),
        today=str(today), forecasts={r: fixture_doc(docs[r], [f["farm"] for f in farms if f["region"] == r])
                                     for r in regions},
        cases=cases))
    write_json(FIXTURES / "spec_examples.json", spec_examples_fixture())
    # The app reads farms.json from its bundle (My farm view): pack it in, as scripts/11 does.
    subprocess.run([sys.executable, str(BUNDLE_TOOL), str(FARMS_JSON.parent)], check=True, cwd=REPO)

    log(f"\nwrote {outbox.relative_to(REPO).as_posix()} ({len(messages)} texts), "
        f"{FARMS_JSON.relative_to(REPO).as_posix()}, notify/fixtures/demo_week.json, "
        "notify/fixtures/spec_examples.json")
    log("Nothing was sent. To see what a send would do (a dry run): "
        f".venv/Scripts/python.exe -m notify.sms {outbox.relative_to(REPO).as_posix()}")


if __name__ == "__main__":
    main()
