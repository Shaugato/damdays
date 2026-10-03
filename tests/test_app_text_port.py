"""The app's JavaScript port of the weekly text (app/js/text.js) writes exactly what notify/message.py writes.

The app's "My farm" view shows the weekly text on a phone mock-up. It is made in the browser by
app/js/text.js, a line-for-line port of notify/message.py. These tests run the port with Node.js
(app/tools/check_text_port.js) and compare its texts with Python's, character for character:

* the fixtures scripts/16_weekly_texts.py writes (the spec's worked examples, this week's demo
  farms) and app/data/real/farms.json, run the way the app runs it;
* 600 random farms (0 to 40 dams of every kind, random radii, chances on the rounding edges,
  looks on the 60-day edge, dams at the same spot), made and written by Python here;
* 400 random farms whose long text carries the optional track record (some dams with no record,
  some with too few judged forecasts, counts with thousands commas), and the demo farms with the
  published app/data/real/track_record.json, run the way the app's My farm view runs them.

Skipped if Node.js is not installed.
"""
import json
import math
import random
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from notify.farms import Farm, dams_for_farm
from notify.message import long_text, weekly_text

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "app" / "tools" / "check_text_port.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")


def run_check(*fixtures):
    """Run the JavaScript check; returns (exit code, its printout)."""
    done = subprocess.run([NODE, str(CHECK), *map(str, fixtures)], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", timeout=300)
    return done.returncode, done.stdout + done.stderr


def test_port_matches_the_fixtures_and_farms_json():
    if not (REPO / "notify" / "fixtures" / "demo_week.json").exists():
        pytest.skip("run scripts/16_weekly_texts.py first")
    code, out = run_check()
    assert code == 0, out
    assert "writes exactly the same texts" in out


# ---------------------------------------------------------------------------
# Random farms: Python writes them and their texts, the JavaScript port must agree
# ---------------------------------------------------------------------------
CHANCE_EDGES = [0.0, 0.004, 0.045, 0.049, 0.05, 0.051, 0.149, 0.15, 0.449, 0.45, 0.5, 0.55, 0.949, 0.95, 0.951, 1.0]
FLOORS = [1, 2, 5, 18, 19, 20, 35, 89, 90, 91, 120, 179, 180, 181, 199, 333]
LOOK_DAYS_AGO = [0, 1, 7, 19, 35, 59, 60, 61, 90]
RADII = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5]


def random_farm(rng, index, today):
    """A homestead, its radius and a forecasts document with 0 to 40 dams around it."""
    lat, lon = round(rng.uniform(-38.5, -30.0), 5), round(rng.uniform(140.0, 150.5), 5)
    farm = Farm(farm_id=f"random-{index:03d}", lat=lat, lon=lon, radius_km=rng.choice(RADII),
                name=rng.choice([None, f"Random farm {index}"]))
    dams, rows = [], []
    statuses = ["forecast"] * 5 + ["already_low"] * 2 + ["not_refilled", "no_recent_look"]
    for j in range(rng.randint(0, 40)):
        km, bearing = rng.uniform(0, farm.radius_km + 1.5), rng.uniform(0, 2 * math.pi)
        if dams and rng.random() < 0.08:           # two dams at the same spot: numbered in dam_id order
            dlat, dlon = dams[-1]["lat"], dams[-1]["lon"]
        else:
            dlat = round(lat + km * math.cos(bearing) / 111.2, 5)
            dlon = round(lon + km * math.sin(bearing) / (111.2 * math.cos(math.radians(lat))), 5)
        dam_id = f"r{index:03d}-{rng.randint(0, 9999):04d}-{j:02d}"
        status = rng.choice(statuses)
        look = today - timedelta(days=rng.choice(LOOK_DAYS_AGO))
        issued_on = None if status == "no_recent_look" and rng.random() < 0.3 else str(look)
        level = rng.choice([0, 3, 12, 29]) if status == "already_low" else rng.randint(30, 150)
        forecast = status == "forecast"
        chance = (rng.choice(CHANCE_EDGES) if rng.random() < 0.4 else round(rng.random(), 3)) if forecast else None
        dams.append(dict(dam_id=dam_id, name=dam_id, lat=dlat, lon=dlon, area_ha=1.0, dea_uid=None))
        rows.append(dict(dam_id=dam_id, status=status, issued_on=issued_on,
                         window_end=None if issued_on is None else str(look + timedelta(days=90)),
                         level_pct=level, chance=chance, chance_low=None, chance_high=None,
                         damdays_days=rng.choice(FLOORS) if forecast else None,
                         notes=[], outcome=None, outcome_date=None))
    doc = dict(horizon_days=90, dams=dams, issues=[dict(issue_date=str(today), kind="live", label="random",
                                                        note=None, rows=rows)])
    return farm, doc


def test_port_matches_python_on_random_farms(tmp_path):
    rng = random.Random(20261003)
    today = date(2026, 10, 2)
    cases = []
    for i in range(600):
        farm, doc = random_farm(rng, i, today)
        cases.append(dict(farm=dict(farm_id=farm.farm_id, name=farm.name, lat=farm.lat, lon=farm.lon,
                                    radius_km=farm.radius_km),
                          forecasts=doc, dam_ids=[d.dam_id for d in dams_for_farm(farm, doc)],
                          sms=weekly_text(farm, doc, today), long=long_text(farm, doc, today)))
    fixture = tmp_path / "random_farms.json"
    fixture.write_text(json.dumps(dict(today=str(today), cases=cases)), encoding="utf-8")
    code, out = run_check(fixture)
    assert code == 0, out
    assert "600 of 600 farms identical" in out


# ---------------------------------------------------------------------------
# The optional track-record line of the long text (app/data/real/track_record.json)
# ---------------------------------------------------------------------------
def random_records(rng, doc):
    """A track record for most of the dams: none, too few judged forecasts, or counts up to the thousands."""
    out = {}
    for dam in doc["dams"]:
        roll = rng.random()
        if roll < 0.15:
            continue                                          # no record at all
        judged = rng.randint(0, 6) if roll < 0.35 else rng.randint(5, 3000)
        out[dam["dam_id"]] = dict(held=rng.randint(0, judged), judged=judged)
    return out


def test_port_matches_python_with_the_track_record(tmp_path):
    rng = random.Random(20261004)
    today = date(2026, 10, 2)
    cases = []
    for i in range(400):
        farm, doc = random_farm(rng, i, today)
        records = random_records(rng, doc)
        cases.append(dict(farm=dict(farm_id=farm.farm_id, name=farm.name, lat=farm.lat, lon=farm.lon,
                                    radius_km=farm.radius_km),
                          forecasts=doc, dam_ids=[d.dam_id for d in dams_for_farm(farm, doc)], track_record=records,
                          sms=weekly_text(farm, doc, today), long=long_text(farm, doc, today, track_record=records)))
    fixture = tmp_path / "random_farms_with_track_record.json"
    fixture.write_text(json.dumps(dict(today=str(today), cases=cases)), encoding="utf-8")
    code, out = run_check(fixture)
    assert code == 0, out
    assert "400 of 400 farms identical" in out


def test_port_matches_python_on_the_demo_farms_with_the_published_track_record(tmp_path):
    real = REPO / "app" / "data" / "real"
    if not (real / "track_record.json").exists() or not (real / "farms.json").exists():
        pytest.skip("run scripts/16_weekly_texts.py and scripts/18_track_record.py first")
    farms = json.loads((real / "farms.json").read_text(encoding="utf-8"))
    app_forecasts = json.loads((real / "forecasts.json").read_text(encoding="utf-8"))
    records = json.loads((real / "track_record.json").read_text(encoding="utf-8"))["dams"]
    cases = []
    for f in farms["farms"]:
        farm = Farm(farm_id=f["farm_id"], lat=f["lat"], lon=f["lon"], radius_km=f["radius_km"], name=f["name"])
        # As My farm runs it: the app's forecasts in its region, otherwise the farm's own dams (text.docFromDams).
        doc = app_forecasts if f["dams_in_app"] else dict(
            dams=[dict(dam_id=d["dam_id"], name=d["dam_id"], lat=d["lat"], lon=d["lon"], area_ha=d["area_ha"],
                       dea_uid=d["dea_uid"]) for d in f["dams"]],
            issues=[dict(issue_date=None, kind="live", rows=[
                {k: d[k] for k in ("dam_id", "status", "issued_on", "window_end", "level_pct", "chance",
                                   "damdays_days")} for d in f["dams"]])])
        long = long_text(farm, doc, farms["date"], track_record=records)
        assert "Our track record on these" in long and long.count("\n") == f["long"].count("\n") + 1
        cases.append(dict(farm=dict(farm_id=farm.farm_id, name=farm.name, lat=farm.lat, lon=farm.lon,
                                    radius_km=farm.radius_km), forecasts=doc,
                          dam_ids=[d["dam_id"] for d in f["dams"]], sms=f["sms"], long=long))
    fixture = tmp_path / "demo_farms_with_track_record.json"
    fixture.write_text(json.dumps(dict(today=farms["date"], track_record=records, cases=cases)), encoding="utf-8")
    code, out = run_check(fixture)
    assert code == 0, out
    assert f"{len(cases)} of {len(cases)} farms identical" in out
