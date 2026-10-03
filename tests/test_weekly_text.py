"""The weekly text (notify/): every rule of notify/MESSAGE_SPEC.md, checked.

* ONE SMS. Every text is GSM-7 only (no emoji), 160 characters or fewer AND 160 places or
  fewer ("~" takes two places).
* THE MENTOR'S WORDS. "%" appears only as "~N% full" (how full); a chance appears only as
  "N in 10", and only in the long text; the headline is days ("at least N days", "6 months+").
* THE RULES. The worked examples of the spec, word for word; days counted from today; the
  180-day cap; who gets named; lines left out to fit.
* THE DATA. Farms and their dams (numbered by distance, radius cut); the outbox; the
  optional sender (dry run, refusals; never touches the network); the fixtures for the
  JavaScript port; this week's demo texts against the app's published forecasts.
* A STRESS TEST. 3,000 random farms (0 to 40 dams of every kind) must all obey the rules.
* THE TRACK RECORD (optional, long text only): how often our days-left promise held on the farm's
  dams in the 2016-2026 backtest; the SMS never changes, and without it the long text never changes.
"""
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from notify import examples, gsm7, sms
from notify.farms import Farm, FarmDam, dams_for_farm, distance_km, to_10_metres
from notify.message import (CAP_DAYS, TRACK_RECORD_MIN, as_date, chance_text, count_text, date_text, days_left,
                            floor_text, fullness, has_track_record, long_for_dams, long_text, sms_for_dams,
                            track_record_line, weekly_text)
from notify.outbox import message_record, read_outbox, write_outbox

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "notify" / "MESSAGE_SPEC.md"
FIXTURES = REPO / "notify" / "fixtures"
APP_REAL = REPO / "app" / "data" / "real"


# ===========================================================================
# Helpers
# ===========================================================================
def dam(number=1, status="forecast", level=60, floor=40, chance=0.3, look="2026-09-28", km=None):
    """A FarmDam for tests (forecast fields only for forecast dams)."""
    is_forecast = status == "forecast"
    window = None if look is None else str(as_date(look) + timedelta(days=90))
    return FarmDam(number=number, dam_id=f"t-{number:03d}", dea_uid=None,
                   distance_km=km if km is not None else 0.1 * number, lat=-32.0, lon=148.0, area_ha=1.0,
                   status=status, issued_on=look, window_end=window, level_pct=level,
                   chance=chance if is_forecast else None, damdays_days=floor if is_forecast else None)


def check_sms_rules(text, today):
    """Every rule a farmer-facing SMS must keep."""
    assert gsm7.is_gsm7(text), text
    assert set(text) <= gsm7.SAFE, f"characters outside the safe set: {set(text) - gsm7.SAFE}"
    assert len(text) <= 160 and gsm7.septets(text) <= 160, (len(text), gsm7.septets(text), text)
    lines = text.split("\n")
    assert lines[0].startswith(date_text(today)), "the text must lead with the date"
    assert lines[-1].startswith("Reply MAP"), "the text must close with Reply MAP"
    check_percent_means_full(text)
    assert "chance" not in text.lower() and "in 10" not in text, "the SMS gives no chances"
    assert not re.search(r"\d\.\d", text), "no decimals in an SMS"


def check_percent_means_full(text):
    """"%" only ever means how full: always "N% full", never anything else."""
    assert not re.search(r"%(?! full)", text), f"'%' not followed by ' full': {text!r}"
    assert not re.search(r"(?<!\d)%", text), f"'%' without a number: {text!r}"


def check_long_rules(text):
    """The long text: 2 to 4 lines (5 with the optional track record); '%' means full; every chance is 'N in 10'."""
    lines = text.split("\n")
    with_record = sum(line.startswith("Our track record on ") for line in lines)
    assert with_record <= 1, lines
    assert 2 <= len(lines) - with_record <= 4, lines
    check_percent_means_full(text)
    for clause in re.split(r"[.;]", text):
        if "chance" in clause.lower():
            assert re.search(r"(less than 1|more than 9|\b[1-9]) in 10", clause), clause
    assert not re.search(r"\d\.\d+(?! km)", text), "the only decimals are distances (no chance as a decimal)"


# ===========================================================================
# 1. The words
# ===========================================================================
@pytest.mark.parametrize("chance, words", [
    (0.0, "less than 1 in 10"), (0.049, "less than 1 in 10"), (0.05, "1 in 10"), (0.149, "1 in 10"),
    (0.15, "2 in 10"), (0.449, "4 in 10"), (0.45, "5 in 10"), (0.58, "6 in 10"), (0.62, "6 in 10"),
    (0.949, "9 in 10"), (0.95, "more than 9 in 10"), (1.0, "more than 9 in 10"),
])
def test_chance_is_n_in_10(chance, words):
    assert chance_text(chance) == words


def test_fullness_is_the_only_percent():
    assert fullness(45) == "~45% full"
    assert fullness(99) == "~99% full"
    assert fullness(100) == "full" and fullness(125) == "full"


def test_floor_words_and_the_cap():
    assert floor_text(1) == "at least 1 day"
    assert floor_text(35) == "at least 35 days"
    assert floor_text(CAP_DAYS - 1) == "at least 179 days"
    assert floor_text(CAP_DAYS) == "6 months+"
    assert floor_text(333) == "6 months+"


def test_dates_are_fixed_english():
    assert date_text("2026-10-02") == "Fri 2 Oct"
    assert date_text(date(2026, 10, 5)) == "Mon 5 Oct"


def test_gsm7_counts_places():
    assert gsm7.septets("Dam 1 ~45% full") == 16 and len("Dam 1 ~45% full") == 15
    assert gsm7.is_gsm7("Reply MAP\n1/3 (ok) 6 months+")
    assert not gsm7.is_gsm7("Dam 1 \U0001F4A7")                      # an emoji
    assert not gsm7.is_gsm7("Dam 1 – low")                      # a long dash
    assert gsm7.fits_one_sms("x" * 160) and not gsm7.fits_one_sms("x" * 161)
    assert not gsm7.fits_one_sms("~" * 81)                           # 162 places


# ===========================================================================
# 2. Days are counted from today; the cap; a floor that ran out
# ===========================================================================
def test_days_counted_from_today():
    d = dam(floor=35, look="2026-09-13")
    assert days_left(d, "2026-10-02") == 16
    assert "Dam 1 ~60% full: at least 16 days before it drops below 1/3" in sms_for_dams([d], "2026-10-02")


@pytest.mark.parametrize("floor, words", [
    (333, "6 months+"),            # far past the cap
    (199, "6 months+"),            # 199 - 19 = 180: exactly the cap
    (198, "at least 179 days"),    # one day under it
    (190, "at least 171 days"),
])
def test_floor_cap_after_the_days_since_the_look(floor, words):
    d = dam(floor=floor, chance=0.01, look="2026-09-13")
    text = sms_for_dams([d, dam(2, status="already_low", level=20, look="2026-09-13")], "2026-10-02")
    assert f"Dam 1 ~60% full: {words} before it drops below 1/3" in text
    assert "180" not in text


def test_floor_that_ran_out_is_not_promised():
    text = sms_for_dams([dam(floor=10, look="2026-09-13")], "2026-10-02")
    assert "Dam 1 ~60% full: may be below 1/3 now" in text
    assert "at least" not in text


def test_several_floors_that_ran_out_share_one_line_and_keep_the_headline():
    dams = [dam(n, level=55, floor=3, chance=0.9) for n in range(1, 4)] + [dam(4, floor=90, chance=0.2)]
    text = sms_for_dams(dams, "2026-10-05")
    assert "Dams 1, 2 and 3 may be below 1/3 now" in text
    assert "Dam 4 ~60% full: at least 83 days before it drops below 1/3" in text


def test_text_cannot_be_dated_before_the_look():
    with pytest.raises(ValueError):
        sms_for_dams([dam(look="2026-10-10")], "2026-10-05")


def test_a_look_older_than_60_days_is_not_reported():
    old = dam(floor=200, chance=0.01, look="2026-07-01")
    text = sms_for_dams([old], "2026-10-05")
    assert "Dam 1: no clear satellite look lately" in text
    assert "full" not in text


# ===========================================================================
# 3. Who is named
# ===========================================================================
def test_headline_is_the_shortest_floor_and_five_in_ten_is_named():
    dams = [dam(1, floor=75, chance=0.30), dam(2, level=55, floor=25, chance=0.71),
            dam(3, floor=95, chance=0.20), dam(4, floor=40, chance=0.45)]          # 0.45 rounds to 5 in 10
    lines = sms_for_dams(dams, "2026-10-05").split("\n")
    assert lines[1] == "Dam 2 ~55% full: at least 18 days before it drops below 1/3"
    assert lines[2] == "Dam 4 ~60% full: at least 33 days"
    assert lines[3] == "Other 2 dams: at least 68 days"


def test_four_in_ten_is_not_named():
    dams = [dam(1, floor=25, chance=0.71), dam(2, floor=40, chance=0.449), dam(3, floor=95, chance=0.2)]
    text = sms_for_dams(dams, "2026-10-05")
    assert "Dam 2" not in text and "Other 2 dams: at least 33 days" in text


def test_all_fine():
    dams = [dam(1, level=100, floor=200, chance=0.02), dam(2, floor=140, chance=0.06)]
    assert sms_for_dams(dams, "2026-10-05").split("\n")[1] == "Both dams look OK for 3 months+"
    assert sms_for_dams(dams[:1], "2026-10-05").split("\n")[1] == "Your dam looks OK for 3 months+"
    # 97 days left is fine; 89 is not; a 5 in 10 chance is never "OK"
    assert "OK for 3 months+" in sms_for_dams([dam(floor=104, chance=0.1)], "2026-10-05")
    assert "OK for 3 months+" not in sms_for_dams([dam(floor=96, chance=0.1)], "2026-10-05")
    assert "OK for 3 months+" not in sms_for_dams([dam(floor=150, chance=0.5)], "2026-10-05")


def test_already_low_is_said_plainly():
    assert "Dam 2 already below 1/3" in sms_for_dams([dam(1), dam(2, status="already_low", level=20)], "2026-10-05")
    assert "Dam 2 looks dry" in sms_for_dams([dam(1), dam(2, status="already_low", level=0)], "2026-10-05")
    many = [dam(n, status="already_low", level=10) for n in range(1, 7)]
    assert "6 dams already below 1/3" in sms_for_dams(many, "2026-10-05")


def test_no_dams():
    farm = Farm("f", -20.0, 130.0)
    text = weekly_text(farm, {"dams": [], "issues": [{"kind": "live", "rows": []}]}, "2026-10-05")
    assert text == "Mon 5 Oct\nNo farm dams the satellites can see within 3 km\nReply MAP"


# ===========================================================================
# 4. The worked examples of MESSAGE_SPEC.md, word for word
# ===========================================================================
def spec_fixture():
    return json.loads((FIXTURES / "spec_examples.json").read_text(encoding="utf-8"))


def test_spec_has_8_to_10_worked_examples():
    assert 8 <= len(examples.EXAMPLES) <= 10


@pytest.mark.parametrize("index", range(len(examples.EXAMPLES)))
def test_worked_example(index):
    forecasts, farms = examples.build_examples()
    example, farm = farms[index]
    case = spec_fixture()["cases"][index]
    assert case["key"] == example["key"]
    sms_text = weekly_text(farm, forecasts, examples.TODAY)
    long = long_text(farm, forecasts, examples.TODAY)
    assert sms_text == case["sms"]
    assert long == case["long"]
    assert [d.dam_id for d in dams_for_farm(farm, forecasts)] == case["dam_ids"]
    check_sms_rules(sms_text, examples.TODAY)
    check_long_rules(long)
    assert "```\n" + sms_text + "\n```" in SPEC.read_text(encoding="utf-8"), \
        f"MESSAGE_SPEC.md must show example {index + 1}'s text exactly"


def test_spec_fixture_inputs_are_the_examples():
    forecasts, farms = examples.build_examples()
    fixture = spec_fixture()
    assert fixture["today"] == examples.TODAY
    assert fixture["forecasts"] == json.loads(json.dumps(forecasts))
    assert [c["farm"]["farm_id"] for c in fixture["cases"]] == [f.farm_id for _, f in farms]


def test_spec_long_text_example_is_exact():
    forecasts, farms = examples.build_examples()
    _, farm = farms[1]
    assert "```\n" + long_text(farm, forecasts, examples.TODAY) + "\n```" in SPEC.read_text(encoding="utf-8")


# ===========================================================================
# 5. Farms and their dams
# ===========================================================================
def tiny_forecasts():
    """Three dams due east of (-32, 148) at about 0.5, 1.5 and 3.5 km, plus one with no row."""
    def at(km):
        return round(148 + km / (6371.0088 * 0.848048) * 57.29578, 5)    # cos(32 deg) = 0.848048
    dams = [dict(dam_id="d-far", lat=-32.0, lon=at(1.5), area_ha=1.0, dea_uid="u2"),
            dict(dam_id="d-near", lat=-32.0, lon=at(0.5), area_ha=0.8, dea_uid="u1"),
            dict(dam_id="d-out", lat=-32.0, lon=at(3.5), area_ha=2.0, dea_uid="u3"),
            dict(dam_id="d-norow", lat=-32.0, lon=at(0.2), area_ha=1.0, dea_uid="u4")]
    rows = [dict(dam_id=d, status="forecast", issued_on="2026-09-28", window_end="2026-12-27", level_pct=70,
                 chance=0.2, damdays_days=100) for d in ("d-far", "d-near", "d-out")]
    return dict(dams=dams, issues=[dict(kind="past", rows=[]), dict(kind="live", rows=rows)])


def test_dams_numbered_by_distance_within_the_radius():
    found = dams_for_farm(Farm("f", -32.0, 148.0), tiny_forecasts())
    assert [(d.name, d.dam_id) for d in found] == [("Dam 1", "d-near"), ("Dam 2", "d-far")]
    assert found[0].dea_uid == "u1" and 0.45 <= found[0].distance_km <= 0.55
    wider = dams_for_farm(Farm("f", -32.0, 148.0, radius_km=4.0), tiny_forecasts())
    assert [d.dam_id for d in wider] == ["d-near", "d-far", "d-out"]


def test_equal_distances_go_in_id_order():
    forecasts = tiny_forecasts()
    forecasts["dams"][0]["lon"] = forecasts["dams"][1]["lon"]          # d-far moved onto d-near
    found = dams_for_farm(Farm("f", -32.0, 148.0), forecasts)
    assert [d.dam_id for d in found] == ["d-far", "d-near"]


def test_distance_and_rounding():
    assert abs(distance_km(-32.0, 148.0, -33.0, 148.0) - 111.195) < 0.01
    assert to_10_metres(0.125) == 0.13 and to_10_metres(2.994) == 2.99


# ===========================================================================
# 6. The outbox and the optional sender (never touches the network)
# ===========================================================================
def test_outbox_round_trip(tmp_path):
    forecasts, farms = examples.build_examples()
    _, farm = farms[1]
    found = dams_for_farm(farm, forecasts)
    record = message_record(farm, found, sms_for_dams(found, examples.TODAY), long_for_dams(found, examples.TODAY))
    path = write_outbox("2026-10-05", [record], "test", folder=tmp_path)
    assert path.name == "2026-10-05.json"
    back = read_outbox(path)
    assert back["messages"][0]["sms"] == record["sms"] and back["messages"][0]["to"] is None
    assert back["messages"][0]["sms_septets"] == gsm7.septets(record["sms"])


def test_outbox_refuses_a_text_that_is_not_one_sms():
    with pytest.raises(ValueError):
        message_record(Farm("f", 0, 0), [], "x" * 161, "long")


def an_outbox():
    return dict(date="2026-10-05", messages=[
        dict(farm_id="farm-a", farm_name="Farm A", to=None, sms="Mon 5 Oct\nReply MAP", sms_septets=19),
        dict(farm_id="farm-b", farm_name="Farm B", to="+61491570156", sms="Mon 5 Oct\nReply MAP", sms_septets=19)])


def test_sender_dry_run_by_default_never_posts():
    def post(*args, **kwargs):
        raise AssertionError("a dry run must never post")
    results = sms.send_outbox(an_outbox(), env={}, post=post)
    assert [r["status"] for r in results] == ["skipped: no valid phone number", "dry run"]
    assert results[1]["request"]["url"].endswith("/Accounts/<TWILIO_SID>/Messages.json")
    assert results[1]["request"]["data"] == {"From": "<TWILIO_FROM>", "To": "+61491570156",
                                             "Body": "Mon 5 Oct\nReply MAP"}


def test_sender_refuses_to_send_without_the_account():
    with pytest.raises(SystemExit):
        sms.send_outbox(an_outbox(), send=True, env={"TWILIO_SID": "ACxxxx"}, post=lambda *a, **k: None)


def test_sender_send_path_with_a_fake_post():
    calls = []

    class Response:
        status_code = 201

    def post(url, data, auth, timeout):
        calls.append((url, data, auth))
        return Response()
    env = {"TWILIO_SID": "ACfake", "TWILIO_TOKEN": "fake-token", "TWILIO_FROM": "+61400000000"}
    results = sms.send_outbox(an_outbox(), send=True, farm="farm-a", to="+61491570156", env=env, post=post)
    assert [r["status"] for r in results] == ["sent"]
    assert calls == [("https://api.twilio.com/2010-04-01/Accounts/ACfake/Messages.json",
                      {"From": "+61400000000", "To": "+61491570156", "Body": "Mon 5 Oct\nReply MAP"},
                      ("ACfake", "fake-token"))]


def test_sender_needs_a_farm_for_to():
    with pytest.raises(SystemExit):
        sms.send_outbox(an_outbox(), to="+61491570156", env={})


# ===========================================================================
# 7. This week's demo texts and the JavaScript fixtures
# ===========================================================================
def demo_fixture():
    path = FIXTURES / "demo_week.json"
    if not path.exists():
        pytest.skip("run scripts/16_weekly_texts.py first")
    return json.loads(path.read_text(encoding="utf-8"))


def test_demo_fixture_reproduces():
    fixture = demo_fixture()
    assert len(fixture["cases"]) >= 5
    for case in fixture["cases"]:
        f = case["farm"]
        farm = Farm(f["farm_id"], f["lat"], f["lon"], f["radius_km"], f["name"])
        forecasts = fixture["forecasts"][case["region"]]
        assert [d.dam_id for d in dams_for_farm(farm, forecasts)] == case["dam_ids"]
        assert weekly_text(farm, forecasts, fixture["today"]) == case["sms"]
        assert long_text(farm, forecasts, fixture["today"]) == case["long"]
        check_sms_rules(case["sms"], fixture["today"])
        check_long_rules(case["long"])


def test_demo_farms_match_the_apps_published_forecasts():
    """farms.json's texts for the app's region, remade from app/data/real/forecasts.json."""
    farms_path, forecasts_path = APP_REAL / "farms.json", APP_REAL / "forecasts.json"
    if not farms_path.exists() or not forecasts_path.exists():
        pytest.skip("run scripts/16_weekly_texts.py first")
    published = json.loads(farms_path.read_text(encoding="utf-8"))
    forecasts = json.loads(forecasts_path.read_text(encoding="utf-8"))
    in_app = [f for f in published["farms"] if f["dams_in_app"]]
    assert in_app, "at least the app's region has demo farms"
    for f in published["farms"]:
        check_sms_rules(f["sms"], published["date"])
        check_long_rules(f["long"])
        assert f["dams"], f"{f['name']}: a demo farm sits on a real dam cluster"
        assert [d["number"] for d in f["dams"]] == list(range(1, len(f["dams"]) + 1))
        assert [d["distance_km"] for d in f["dams"]] == sorted(d["distance_km"] for d in f["dams"])
    for f in in_app:
        farm = Farm(f["farm_id"], f["lat"], f["lon"], f["radius_km"], f["name"])
        assert weekly_text(farm, forecasts, published["date"]) == f["sms"]
        assert long_text(farm, forecasts, published["date"]) == f["long"]


# ===========================================================================
# 8. Stress test: random farms of every kind keep every rule
# ===========================================================================
def random_farm(rng, today):
    statuses = ["forecast"] * 5 + ["already_low"] * 2 + ["not_refilled", "no_recent_look"]
    dams = []
    for n in range(1, rng.randint(0, 40) + 1):
        status = rng.choice(statuses)
        look = today - timedelta(days=rng.choice([0, 3, 7, 19, 35, 59, 61, 90]))
        level = rng.choice([0, 3, 12, 29]) if status == "already_low" else rng.randint(30, 150)
        dams.append(dam(n, status=status, level=level, floor=rng.choice([1, 5, 19, 20, 35, 89, 90, 120, 179,
                                                                          180, 199, 333]),
                        chance=round(rng.random(), 3), look=str(look)))
    return dams


def test_random_farms_keep_every_rule():
    rng = random.Random(20261002)
    today = date(2026, 10, 2)
    for _ in range(3000):
        dams = random_farm(rng, today)
        text = sms_for_dams(dams, today)
        check_sms_rules(text, today)
        check_long_rules(long_for_dams(dams, today))
        # The headline (the fewest days still left) is always in the SMS, with its days.
        with_days = [d for d in dams if d.status == "forecast" and (today - as_date(d.issued_on)).days <= 60
                     and days_left(d, today) > 0]
        if with_days:
            first = min(with_days, key=lambda d: (days_left(d, today), d.number))
            assert re.search(rf"(^|\n){first.name} (full|~\d+% full): ", text), (first, text)


# ===========================================================================
# 9. The optional track record (long text only)
# ===========================================================================
def records_for(*pairs):
    """{dam_id: {"held", "judged"}} for dams t-001, t-002, ... (None: no record for that dam)."""
    return {f"t-{n:03d}": dict(held=pair[0], judged=pair[1]) for n, pair in enumerate(pairs, start=1) if pair}


def test_count_text_and_enough_history():
    assert [count_text(n) for n in (0, 7, 999, 1000, 1362, 1524, 12345, 1234567)] == \
        ["0", "7", "999", "1,000", "1,362", "1,524", "12,345", "1,234,567"]
    assert TRACK_RECORD_MIN == 5
    assert has_track_record(dict(held=0, judged=5)) and not has_track_record(dict(held=4, judged=4))
    assert not has_track_record(None)


def test_track_record_line_for_a_farm():
    today = "2026-10-05"
    dams = [dam(1, status="already_low", level=0), dam(2, floor=40, chance=0.3), dam(3, floor=100, chance=0.1)]
    line = track_record_line(dams, today, records_for((166, 216), (198, 222), (998, 1086)))
    assert line == ("Our track record on these 3 dams (2016-2026 backtest, forecasts the model made for years it "
                    "never trained on): the cautious days-left promise held 1,362 of 1,524 times; on Dam 2, 198 of 222.")


def test_track_record_line_with_too_little_history():
    today = "2026-10-05"
    dams = [dam(1, floor=40), dam(2, floor=100), dam(3, status="not_refilled", level=45)]
    # Dam 1 (the headline: fewest days) has only 4 judged forecasts; Dam 3 has none.
    line = track_record_line(dams, today, records_for((4, 4), (90, 100)))
    assert line.endswith("the cautious days-left promise held 90 of 100 times (1 of the 3 has enough history to "
                         "judge); Dam 1 has too few past forecasts to judge.")
    assert track_record_line(dams, today, {}).endswith("): too few past forecasts to judge.")


def test_spec_track_record_example_is_exact():
    forecasts, farms = examples.build_examples()
    _, farm = farms[1]
    long = long_text(farm, forecasts, examples.TODAY, track_record=examples.TRACK_RECORD_EXAMPLE)
    assert "```\n" + long + "\n```" in SPEC.read_text(encoding="utf-8")
    check_long_rules(long)


def test_track_record_line_for_one_dam():
    line = track_record_line([dam(1, floor=40)], "2026-10-05", records_for((18, 20)))
    assert line == ("Our track record on this dam (2016-2026 backtest, forecasts the model made for years it never "
                    "trained on): the cautious days-left promise held 18 of 20 times.")


def test_track_record_is_in_the_long_text_only():
    forecasts, farms = examples.build_examples()
    for _, farm in farms:
        dams = dams_for_farm(farm, forecasts)
        records = {d.dam_id: dict(held=17 + d.number, judged=20 + d.number) for d in dams}
        plain = long_text(farm, forecasts, examples.TODAY)
        with_record = long_text(farm, forecasts, examples.TODAY, track_record=records)
        check_long_rules(with_record)
        if not dams:
            assert with_record == plain             # no dams: nothing to report
            continue
        lines, plain_lines = with_record.split("\n"), plain.split("\n")
        assert lines[:-2] + lines[-1:] == plain_lines                       # one line added, before the last
        assert lines[-2] == track_record_line(dams, examples.TODAY, records)
        assert "backtest" not in weekly_text(farm, forecasts, examples.TODAY)   # never in the SMS


def test_track_record_on_random_farms_keeps_every_rule():
    rng = random.Random(20261003)
    today = date(2026, 10, 2)
    for _ in range(1000):
        dams = random_farm(rng, today)
        records = {}
        for d in dams:
            if rng.random() < 0.85:
                held = rng.randint(0, 2000)
                records[d.dam_id] = dict(held=held, judged=held + rng.randint(0, 30))
        text = long_for_dams(dams, today, track_record=records)
        check_long_rules(text)
        if not dams:
            continue
        line = next(x for x in text.split("\n") if x.startswith("Our track record on "))
        shown = [records[d.dam_id] for d in dams if d.dam_id in records and records[d.dam_id]["judged"] >= 5]
        if shown:
            held, judged = sum(r["held"] for r in shown), sum(r["judged"] for r in shown)
            assert f"held {count_text(held)} of {count_text(judged)} times" in line
        else:
            assert line.endswith("too few past forecasts to judge.")
