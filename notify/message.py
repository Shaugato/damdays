"""The weekly text: one SMS per farm, and a longer version for the app or an email.

    weekly_text(farm, forecasts, today)  ONE SMS: GSM-7 only, 160 places or fewer, no emoji
    long_text(farm, forecasts, today)    2 to 4 lines for the app or an email; with the optional
                                         track_record, one more line: our record on these dams
                                         over the last 10 years (how often our days-left number
                                         held; never in the SMS)

The words follow mentor feedback (Fri 2 Oct 2026):

* "%" only ever means HOW FULL a dam is: "~45% full", at its latest satellite look, against
  the dam's own full level (the share of its usual full water surface that is wet, not depth).
  Nothing else in a text is written as a percent.
* A chance is written "6 in 10" (rounded; "less than 1 in 10" under 0.05), and only in the
  long text. The SMS gives days and fullness, never a chance.
* The headline is DAYS: the cautious DamDays floor ("at least N days before it drops below
  1/3"; across all dams in the ten test years it held 9 times in 10, a little less often for
  spring looks). "6 months+" once it reaches 180 days.
* A dam at 0% is "no water seen": the satellite saw no water at its last clear look. Never
  "dry": a small pool, or muddy or green water, can be missed, and one look can be wrong.

Days are counted from TODAY. A forecast starts from the dam's latest clear satellite look,
often a week or more before the text is sent, so the text subtracts the days since that look:
a floor of 35 days from a look 19 days ago is "at least 16 days" today. That is the same
promise, measured from today. If the floor has run out since the look, the text says the dam
"may be below 1/3 now".

"Below a third" is the project's R30 event: below 30% of the dam's usual full level (PREREG.md).
Every rule here, with worked examples: notify/MESSAGE_SPEC.md.
"""
import math
from datetime import date

from notify import gsm7
from notify.farms import DEFAULT_RADIUS_KM, dams_for_farm

CAP_DAYS = 180            # a floor of 180 days or more is shown as "6 months+" (the app shows "180+")
OK_DAYS = 90              # every dam at least this many days: "All N dams look OK for 3 months+"
NAME_IF_IN_TEN = 5        # a dam with at least a 5 in 10 chance of falling below a third is always named
RECENT_LOOK_DAYS = 60     # a satellite look older than this (on the day the text is sent) is too old to use
CLOSE = "Reply MAP"       # replying MAP would send a link to the farm's map in the app
MAP_LINK = "[map link]"   # placeholder for the farm's link in the app (long text)
NO_WATER_SEEN = "no water seen"   # a dam at 0%: the satellite saw no water at its last clear look (never "dry")
# The day the farm's dams were last seen (the farm's latest clear satellite look). The SMS's first line says
# "Fri 2 Oct (dams seen 13 Sep)", not "(satellite 13 Sep)": a farmer reads "satellite" there as jargon.
# The long text says it in full: "dams seen from space on 13 Sep".
SEEN = "dams seen"
TRACK_RECORD_MIN = 5      # a dam's track record is shown only with at least this many judged past forecasts
TRACK_RECORD_YEARS = "2016-2026"   # the July-June years the track record counts (scripts/18_track_record.py)
TRACK_RECORD_SPAN = "the last 10 years"   # the same years, in the words the farmer reads
# How the track record was made, in plain words (the long text's record line, and the app's "?" tip).
TRACK_RECORD_HOW = ("We re-ran our forecasts for July 2016 to June 2026 using only data from before July 2016, "
                    "then checked each one against what the dam really did.")

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ===========================================================================
# 1. Small pieces of wording
# ===========================================================================
def as_date(value):
    """A datetime.date from a date or a "YYYY-MM-DD" string."""
    return value if isinstance(value, date) else date.fromisoformat(value)


def short_date(day):
    """2026-09-13 -> "13 Sep"."""
    day = as_date(day)
    return f"{day.day} {MONTHS[day.month - 1]}"


def date_text(day):
    """2026-10-02 -> "Fri 2 Oct" (fixed English names, whatever the computer's language)."""
    day = as_date(day)
    return f"{WEEKDAYS[day.weekday()]} {short_date(day)}"


def in_ten(chance):
    """A chance from 0 to 1 as a whole number of tenths, rounded halves up: 0.58 -> 6, 0.45 -> 5, 0.04 -> 0.

    Done in whole thousandths so Python and JavaScript always agree (chances have 3 decimals).
    """
    thousandths = math.floor(chance * 1000 + 0.5)
    return (thousandths + 50) // 100


def chance_text(chance):
    """0.58 -> "6 in 10"; under 0.05 -> "less than 1 in 10"; 0.95 or more -> "more than 9 in 10"."""
    tenths = in_ten(chance)
    if tenths == 0:
        return "less than 1 in 10"
    if tenths == 10:
        return "more than 9 in 10"
    return f"{tenths} in 10"


def fullness(level_pct):
    """How full the dam was at its latest look: 45 -> "~45% full"; 100 or more -> "full"."""
    return "full" if level_pct >= 100 else f"~{level_pct}% full"


def floor_text(days):
    """The DamDays floor, counted from today: "at least 16 days", "at least 1 day", or "6 months+"."""
    if days >= CAP_DAYS:
        return "6 months+"
    return "at least 1 day" if days == 1 else f"at least {days} days"


def numbers_text(dams):
    """[Dam 3, Dam 5, Dam 6] -> "3, 5 and 6"."""
    numbers = [str(d.number) for d in dams]
    return numbers[0] if len(numbers) == 1 else ", ".join(numbers[:-1]) + " and " + numbers[-1]


def km_text(km):
    """3.0 -> "3", 2.5 -> "2.5" (a radius)."""
    return f"{km:g}"


def one_decimal(km):
    """0.42 -> "0.4" (a distance), rounded halves up so Python and JavaScript agree."""
    tenths = math.floor(km * 10 + 0.5)
    return f"{tenths // 10}.{tenths % 10}"


# ===========================================================================
# 2. Each dam on the day the text is sent
# ===========================================================================
def days_since_look(dam, today):
    """Whole days from the dam's satellite look to `today` (an error if the look is after today)."""
    days = (as_date(today) - as_date(dam.issued_on)).days
    if days < 0:
        raise ValueError(f"{dam.dam_id}: the satellite look {dam.issued_on} is after the text's date {today}")
    return days


def kind(dam, today):
    """What the text can say about a dam today: "forecast", "low", "not_refilled" or "no_look".

    "no_look" covers a dam with no clear satellite look in the 60 days before the text is sent,
    whatever its status was on the forecast's date: an old look is too stale to report.
    """
    if dam.issued_on is None or dam.status == "no_recent_look" or days_since_look(dam, today) > RECENT_LOOK_DAYS:
        return "no_look"
    return {"forecast": "forecast", "already_low": "low", "not_refilled": "not_refilled"}[dam.status]


def days_left(dam, today):
    """The DamDays floor counted from today: the floor from the look minus the days since the look."""
    return dam.damdays_days - days_since_look(dam, today)


def is_ok(dam, today):
    """A forecast dam that looks fine for 3 months: at least 90 days left and under a 5 in 10 chance."""
    return days_left(dam, today) >= OK_DAYS and in_ten(dam.chance) < NAME_IF_IN_TEN


def sorted_by_kind(dams, today):
    """The farm's dams split by kind; forecast dams most urgent first (fewest days left), others by number."""
    groups = {"forecast": [], "low": [], "not_refilled": [], "no_look": []}
    for dam in dams:
        groups[kind(dam, today)].append(dam)
    groups["forecast"].sort(key=lambda d: (days_left(d, today), d.number))
    return groups


def latest_look(dams, today):
    """The farm's latest satellite look (of dams seen in the last 60 days), or None.

    Dams can be seen on different days (cloud hides some on a pass); each dam's days are
    counted from its own look, and the long text gives the headline dam's own look date.
    """
    looks = [as_date(d.issued_on) for d in dams if kind(d, today) != "no_look"]
    return max(looks) if looks else None


# ===========================================================================
# 3. The SMS
# ===========================================================================
def dam_line(dam, today, explain):
    """One forecast dam: "Dam 1 ~45% full: at least 16 days before it drops below 1/3".

    explain  add "before it drops below 1/3" (only the first line that gives a number of days does)
    """
    days = days_left(dam, today)
    if days <= 0:
        return f"{dam.name} {fullness(dam.level_pct)}: may be below 1/3 now"
    line = f"{dam.name} {fullness(dam.level_pct)}: {floor_text(days)}"
    return line + " before it drops below 1/3" if explain else line


def ran_out_line(ran_out, today):
    """Dams whose floor has run out since their look: one dam gets its own line; several share one,
    "Dams 1 and 4 may be below 1/3 now" (so they can never push the headline out of the SMS)."""
    if len(ran_out) == 1:
        return dam_line(ran_out[0], today, explain=False)
    by_number = sorted(ran_out, key=lambda d: d.number)
    if len(ran_out) <= 4:
        return f"Dams {numbers_text(by_number)} may be below 1/3 now"
    return f"{len(ran_out)} dams may be below 1/3 now"


def low_line(low):
    """Dams already below a third: "Dam 3 already below 1/3" ("Dam 3: no water seen" if the satellite
    saw no water at its last clear look; never "dry"), "Dams 3 and 5 already below 1/3", "7 dams already below 1/3".

    How full each one is goes in the long text; the SMS keeps its places for the dams with days left.
    """
    if len(low) == 1:
        dam = low[0]
        return f"{dam.name}: {NO_WATER_SEEN}" if dam.level_pct == 0 else f"{dam.name} already below 1/3"
    if len(low) <= 4:
        return f"Dams {numbers_text(low)} already below 1/3"
    return f"{len(low)} dams already below 1/3"


def no_forecast_line(dams, today):
    """Dams with no forecast: not refilled since their last low, or no clear satellite look lately."""
    if len(dams) == 1:
        dam = dams[0]
        if kind(dam, today) == "not_refilled":
            return f"{dam.name} {fullness(dam.level_pct)}: no forecast until it refills"
        return f"{dam.name}: no clear satellite look lately"
    if len(dams) <= 4:
        return f"Dams {numbers_text(dams)}: no forecast this week"
    return f"{len(dams)} dams: no forecast this week"


def rest_line(rest, today, explain):
    """The forecast dams not named, by their shortest floor: "Other 3 dams: at least 45 days", or
    "Other 3 dams: 3 months+" when every one has at least 90 days (none of them has a 5 in 10 chance,
    or it would have been named)."""
    fewest = min(days_left(d, today) for d in rest)
    if fewest >= OK_DAYS:
        return f"Other {len(rest)} dams: 3 months+"
    line = f"Other {len(rest)} dams: {floor_text(fewest)}"
    return line + " before they drop below 1/3" if explain else line


def all_ok_line(n_dams):
    """Every dam fine for 3 months."""
    if n_dams == 1:
        return "Your dam looks OK for 3 months+"
    if n_dams == 2:
        return "Both dams look OK for 3 months+"
    return f"All {n_dams} dams look OK for 3 months+"


def sms_items(dams, today, radius_km=DEFAULT_RADIUS_KM):
    """The SMS's middle lines, most important first, each with how many dams it covers.

    Order: (1) the dams that matter most, fewest days left first: any dam whose floor has run
    out since its look (several share one line), the dam with the fewest days still left (the
    headline), and any dam with at least a 5 in 10 chance of falling below a third; (2) dams
    already below a third; (3) the rest, summed up by their shortest floor; (4) dams with no
    forecast. If every dam is fine: "All N dams look OK for 3 months+", then the headline dam.
    """
    if not dams:
        return [(f"No dams the satellites can see within {km_text(radius_km)} km", 0)]
    groups = sorted_by_kind(dams, today)
    forecast, low = groups["forecast"], groups["low"]
    no_forecast = sorted(groups["not_refilled"] + groups["no_look"], key=lambda d: d.number)

    if forecast and len(forecast) == len(dams) and all(is_ok(d, today) for d in forecast):
        return [(all_ok_line(len(dams)), 0), (dam_line(forecast[0], today, explain=True), 1)]

    items = []
    explained = False            # has a line said "before it drops below 1/3" yet?

    def add_dam(dam):
        nonlocal explained
        items.append((dam_line(dam, today, explain=not explained), 1))
        explained = explained or days_left(dam, today) > 0

    ran_out = [d for d in forecast if days_left(d, today) <= 0]
    with_days = [d for d in forecast if days_left(d, today) > 0]
    named = with_days[:1] + [d for d in with_days[1:] if in_ten(d.chance) >= NAME_IF_IN_TEN]
    rest = [d for d in with_days if d not in named]
    if ran_out:
        items.append((ran_out_line(ran_out, today), len(ran_out)))
    for dam in named:
        add_dam(dam)
    if low:
        items.append((low_line(low), len(low)))
    if len(rest) == 1:
        add_dam(rest[0])
    elif rest:
        items.append((rest_line(rest, today, explain=not explained), len(rest)))
    if no_forecast:
        items.append((no_forecast_line(no_forecast, today), len(no_forecast)))
    return items


def close_text(dams_left_out):
    """The last line: "Reply MAP", or "Reply MAP for 2 more dams" when some dams did not fit."""
    if dams_left_out == 0:
        return CLOSE
    return f"{CLOSE} for {dams_left_out} more dam{'' if dams_left_out == 1 else 's'}"


def sms_for_dams(dams, today, radius_km=DEFAULT_RADIUS_KM):
    """The SMS for a farm's dams (see weekly_text).

    Line 1 is the date, then the day the farm's dams were last seen (its latest clear satellite look):
    "Fri 2 Oct (dams seen 13 Sep)". If the whole text does not fit one SMS: first the "dams seen" date
    is left out; then lines are left out from the end (the least important first, never the first
    line) and the last line says how many dams were left out: "Reply MAP for 2 more dams".
    """
    today = as_date(today)
    look = latest_look(dams, today)
    headers = [date_text(today)]
    if look is not None:
        headers.insert(0, f"{date_text(today)} ({SEEN} {short_date(look)})")
    items = sms_items(dams, today, radius_km)
    for keep in range(len(items), 0, -1):
        left_out = sum(n for _, n in items[keep:])
        for header in headers:
            text = "\n".join([header, *(line for line, _ in items[:keep]), close_text(left_out)])
            if gsm7.fits_one_sms(text):
                return text
    raise ValueError(f"No SMS fits in {gsm7.SMS_MAX} places, even with one line: {items[0][0]!r}")


def weekly_text(farm, forecasts, today):
    """THE WEEKLY TEXT: one SMS for `farm` from the live forecasts, as sent on `today`.

    farm       a notify.farms.Farm
    forecasts  a forecasts.json document (app/DATA_CONTRACT.md)
    today      the day the text is sent (date or "YYYY-MM-DD")
    Returns one string: GSM-7 characters only, 160 places or fewer, lines separated by "\\n".
    """
    return sms_for_dams(dams_for_farm(farm, forecasts), today, farm.radius_km)


# ===========================================================================
# 4. The long text (app or email)
# ===========================================================================
def headline_sentence(dam, today):
    """The headline dam in full, with its look date, distance and chance."""
    days = days_left(dam, today)
    start = (f"{dam.name} ({one_decimal(dam.distance_km)} km from the homestead) was "
             f"{fullness(dam.level_pct)} on {short_date(dam.issued_on)}: ")
    if days <= 0:
        middle = "its cautious number of days has run out since then, so it may be below a third now. "
    else:
        floor = "6 months or more" if days >= CAP_DAYS else floor_text(days)
        middle = f"{floor} before it drops below a third, counted from today. "
    chance = f"Chance it drops below a third by {short_date(dam.window_end)}: {chance_text(dam.chance)}."
    return start + middle + chance


def other_clause(dam, today):
    """One of the other dams, in a few words."""
    what = kind(dam, today)
    if what == "forecast":
        days = days_left(dam, today)
        floor = "may be below a third now" if days <= 0 else floor_text(days)
        return (f"{dam.name} {fullness(dam.level_pct)}, {floor} "
                f"(chance by {short_date(dam.window_end)}: {chance_text(dam.chance)})")
    if what == "low":
        if dam.level_pct == 0:
            return f"{dam.name}: {NO_WATER_SEEN} at its {short_date(dam.issued_on)} satellite look (one look can be wrong)"
        return f"{dam.name} already below a third ({fullness(dam.level_pct)})"
    if what == "not_refilled":
        return f"{dam.name} {fullness(dam.level_pct)}, no forecast until it refills to 60% full"
    return f"{dam.name} has had no clear satellite look in the last {RECENT_LOOK_DAYS} days"


LONG_OTHERS_MAX = 6        # the long text lists at most 6 other dams by name; the map shows them all


def count_text(n):
    """A count with thousands commas: 1234 -> "1,234" (the same in Python and JavaScript)."""
    return f"{n:,}"


def has_track_record(record):
    """True when a dam's track record (a dict with "held" and "judged") has enough judged forecasts to show."""
    return record is not None and record["judged"] >= TRACK_RECORD_MIN


def held_share_text(held, judged):
    """How often a record held, in tenths, rounded as chances are: 1640 of 1767 -> "about 9 in 10";
    "more than 9 in 10" from 0.95, "less than 1 in 10" under 0.05, "every time" when it always held."""
    if held == judged:
        return "every time"
    tenths = in_ten(held / judged)
    if tenths == 0:
        return "less than 1 in 10"
    if tenths == 10:
        return "more than 9 in 10"
    return f"about {tenths} in 10"


def track_record_line(dams, today, records):
    """The long text's optional track-record line: how often our days-left number held on these dams.

    records  {dam_id: {"held": int, "judged": int, ...}}: the "dams" of app/data/real/track_record.json
             (scripts/18_track_record.py), counted on forecasts re-run for July 2016 to June 2026 using only
             data from before July 2016. A dam with fewer than TRACK_RECORD_MIN judged forecasts, or none,
             has "too few past forecasts to judge".
    The farm's dams with a record are added up; with two or more dams, the headline dam's own record follows;
    then how the record was made (TRACK_RECORD_HOW), in plain words:
    "Our record on these 5 dams over the last 10 years: our days-left number held 1,640 of 1,767 times (about
    9 in 10); on Dam 1, 380 of 428. We re-ran our forecasts for July 2016 to June 2026 using only data from
    before July 2016, then checked each one against what the dam really did."
    """
    where = "this dam" if len(dams) == 1 else f"these {len(dams)} dams"
    head = f"Our record on {where} over {TRACK_RECORD_SPAN}: "
    recorded = [d for d in dams if has_track_record(records.get(d.dam_id))]
    if not recorded:
        return head + "too few past forecasts to judge."
    held = sum(records[d.dam_id]["held"] for d in recorded)
    judged = sum(records[d.dam_id]["judged"] for d in recorded)
    body = f"our days-left number held {count_text(held)} of {count_text(judged)} times"
    if held != judged:
        body += f" ({held_share_text(held, judged)})"
    if len(recorded) < len(dams):
        body += f" on the {len(recorded)} dam{'' if len(recorded) == 1 else 's'} with enough history to judge"
    forecast = sorted_by_kind(dams, today)["forecast"]
    if len(dams) > 1 and forecast:
        dam = forecast[0]
        record = records.get(dam.dam_id)
        if has_track_record(record):
            body += f"; on {dam.name}, {count_text(record['held'])} of {count_text(record['judged'])}"
        else:
            body += f"; {dam.name} has too few past forecasts to judge"
    return head + body + ". " + TRACK_RECORD_HOW


def long_for_dams(dams, today, farm_label="Your farm", radius_km=DEFAULT_RADIUS_KM, track_record=None):
    """The long text for a farm's dams (see long_text)."""
    today = as_date(today)
    opening = f"{farm_label}, {date_text(today)} {today.year}: "
    if not dams:
        return "\n".join([opening + f"no dams the satellites can see within {km_text(radius_km)} km of "
                          "the homestead. DamDays follows dams of about half a hectare to 5 hectares.",
                          f"Map: {MAP_LINK}"])

    count = f"{len(dams)} dam{'' if len(dams) == 1 else 's'} the satellites can see"
    look = latest_look(dams, today)
    seen = f"{SEEN} from space on {short_date(look)}" if look else \
        f"no clear satellite look in the last {RECENT_LOOK_DAYS} days"
    lines = [opening + f"{count} within {km_text(radius_km)} km of the homestead; {seen}."]

    groups = sorted_by_kind(dams, today)
    ordered = groups["forecast"] + groups["low"] + groups["not_refilled"] + groups["no_look"]
    if groups["forecast"]:
        lines.append(headline_sentence(groups["forecast"][0], today))
        others = ordered[1:]
    else:
        lines.append("No dam has a forecast this week.")
        others = ordered
    if others:
        clauses = [other_clause(d, today) for d in others[:LONG_OTHERS_MAX]]
        if len(others) > LONG_OTHERS_MAX:
            clauses.append(f"and {len(others) - LONG_OTHERS_MAX} more on the map")
        lines.append(("Also: " if groups["forecast"] else "") + "; ".join(clauses) + ".")
    if track_record is not None:
        lines.append(track_record_line(dams, today, track_record))
    if groups["forecast"]:
        lines.append("Days are counted from today and are cautious: across all dams in ten test years, a dam "
                     "stayed above a third at least that long 9 times in 10, a little less often for spring "
                     f"looks. Map: {MAP_LINK}")
    else:
        lines.append(f"Map: {MAP_LINK}")
    return "\n".join(lines)


def long_text(farm, forecasts, today, track_record=None):
    """The weekly text's longer version for the app or an email: 2 to 4 lines, may give chances ("6 in 10").

    track_record  optional {dam_id: {"held": int, "judged": int, ...}}, the "dams" of
                  app/data/real/track_record.json: adds one line before the last, our record on these dams
                  over the last 10 years (track_record_line).
                  Without it (the default) the text is unchanged. The SMS never carries it.
    """
    return long_for_dams(dams_for_farm(farm, forecasts), today, farm.name or "Your farm", farm.radius_km,
                         track_record)
