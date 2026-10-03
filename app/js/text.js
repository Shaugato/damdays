/* text.js
 * The weekly text in JavaScript: a line-for-line port of notify/message.py (plus the parts of
 * notify/farms.py and notify/gsm7.py it needs), so the app's "My farm" view shows exactly the
 * text a farmer gets.
 *
 * The Python files are the original. This port must write exactly the same texts, and
 * app/tools/check_text_port.js checks that it does, on the fixtures scripts/16_weekly_texts.py
 * writes (notify/fixtures/*.json) and on app/data/real/farms.json:
 *     node app/tools/check_text_port.js
 *
 * The words (a mentor who grew up on farms, Fri 2 Oct 2026; notify/MESSAGE_SPEC.md):
 *   - "%" only ever means HOW FULL a dam is: "~45% full", at its latest satellite look.
 *   - A chance is written "6 in 10" (rounded; "less than 1 in 10" under 0.05), never a percent.
 *     The SMS gives no chances; the long text and the app do.
 *   - The headline is DAYS: the cautious DamDays floor, counted from the day the text is sent.
 *
 * Python name -> JavaScript name: weekly_text -> weeklyText, sms_for_dams -> smsForDams,
 * long_for_dams -> longForDams, dams_for_farm -> damsForFarm, days_left -> daysLeft,
 * track_record_line -> trackRecordLine, and so on.
 * Dates are "YYYY-MM-DD" strings (calendar days, no time zone), as in the data files.
 * The long text's optional track-record line (how often our days-left promise held on these dams in the
 * 2016-2026 backtest) takes the "dams" of app/data/real/track_record.json; the SMS never carries it.
 *
 * In the browser this file adds DamDays.text; in Node (the parity check) it is a module.
 */
(function () {
  "use strict";

  // ===========================================================================
  // notify/gsm7.py: which characters one SMS can carry, and how many of its 160 places each takes
  // ===========================================================================
  // The GSM-7 basic alphabet (one place each) and its extension table (two places each).
  const GSM7_BASIC = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?" +
                     "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà";
  const GSM7_EXTENDED = "^{}\\[~]|€\f";
  const SMS_MAX = 160;

  /** True if every character is in the GSM-7 alphabet (basic or extension table). */
  function isGsm7(text) {
    for (const c of text) {
      if (!GSM7_BASIC.includes(c) && !GSM7_EXTENDED.includes(c)) return false;
    }
    return true;
  }

  /** How many of the SMS's 160 places the text takes ("~" takes two). */
  function septets(text) {
    let places = 0;
    for (const c of text) places += GSM7_EXTENDED.includes(c) ? 2 : 1;
    return places;
  }

  /** True if the text goes out as ONE GSM-7 SMS. */
  function fitsOneSms(text) {
    return isGsm7(text) && septets(text) <= SMS_MAX;
  }

  // ===========================================================================
  // notify/farms.py: a farm (homestead point + radius) and its dams, numbered by distance
  // ===========================================================================
  const DEFAULT_RADIUS_KM = 3.0;
  const EARTH_RADIUS_KM = 6371.0088;
  const DEG_TO_RAD = Math.PI / 180;     // the same constant as Python's math.radians

  /** Great-circle distance in km (haversine), written in the same order of operations as Python. */
  function distanceKm(lat1, lon1, lat2, lon2) {
    const p1 = lat1 * DEG_TO_RAD;
    const p2 = lat2 * DEG_TO_RAD;
    const dp = p2 - p1;
    const dl = (lon2 - lon1) * DEG_TO_RAD;
    const a = Math.sin(dp / 2);
    const b = Math.sin(dl / 2);
    const h = a * a + Math.cos(p1) * Math.cos(p2) * (b * b);
    return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
  }

  /** A distance rounded to 10 m (2 decimals of a km), halves up. */
  function toTenMetres(km) {
    return Math.floor(km * 100 + 0.5) / 100;
  }

  /** The one issue of a forecasts.json document with kind "live". */
  function liveIssue(forecasts) {
    const live = forecasts.issues.filter((issue) => issue.kind === "live");
    if (live.length !== 1) {
      throw new Error("forecasts.json must have exactly one live issue, found " + live.length);
    }
    return live[0];
  }

  function radiusOf(farm) {
    return farm.radius_km === undefined || farm.radius_km === null ? DEFAULT_RADIUS_KM : farm.radius_km;
  }

  /**
   * The farm's dams: every dam in `forecasts` within the farm's radius of the homestead.
   * farm       { farm_id, lat, lon, radius_km, name }
   * forecasts  a forecasts.json document (only its live issue is used)
   * Returns dams numbered by distance (Dam 1 = closest; equal distances in dam_id order), each
   * with its live row's fields (status, issued_on, window_end, level_pct, chance, damdays_days).
   */
  function damsForFarm(farm, forecasts) {
    const rows = new Map(liveIssue(forecasts).rows.map((row) => [row.dam_id, row]));
    const radius = radiusOf(farm);
    const found = [];
    forecasts.dams.forEach((dam) => {
      const row = rows.get(dam.dam_id);
      if (!row) return;          // the contract gives every dam a row; skip one that has none
      const km = toTenMetres(distanceKm(farm.lat, farm.lon, dam.lat, dam.lon));
      if (km <= radius) found.push({ km: km, dam: dam, row: row });
    });
    found.sort((x, y) => (x.km - y.km) || (x.dam.dam_id < y.dam.dam_id ? -1 : x.dam.dam_id > y.dam.dam_id ? 1 : 0));
    return found.map((item, i) => ({
      number: i + 1,
      name: "Dam " + (i + 1),
      dam_id: item.dam.dam_id,
      dea_uid: item.dam.dea_uid === undefined ? null : item.dam.dea_uid,
      distance_km: item.km,
      lat: item.dam.lat,
      lon: item.dam.lon,
      area_ha: item.dam.area_ha,
      status: item.row.status,
      issued_on: item.row.issued_on,
      window_end: item.row.window_end,
      level_pct: item.row.level_pct,
      chance: item.row.chance,
      damdays_days: item.row.damdays_days,
    }));
  }

  /**
   * A forecasts document holding only the given dams, from farms.json's copy of their live rows.
   * (The app uses it for demo farms outside the region its map shows.)
   */
  function docFromDams(dams) {
    return {
      dams: dams.map((d) => ({ dam_id: d.dam_id, name: d.dam_id, lat: d.lat, lon: d.lon,
                               area_ha: d.area_ha, dea_uid: d.dea_uid })),
      issues: [{ issue_date: null, kind: "live", rows: dams.map((d) => ({
        dam_id: d.dam_id, status: d.status, issued_on: d.issued_on, window_end: d.window_end,
        level_pct: d.level_pct, chance: d.chance, damdays_days: d.damdays_days })) }],
    };
  }

  // ===========================================================================
  // notify/message.py, part 1: small pieces of wording
  // ===========================================================================
  const CAP_DAYS = 180;           // a floor of 180 days or more is shown as "6 months+"
  const OK_DAYS = 90;             // every dam at least this many days: "All N dams look OK for 3 months+"
  const NAME_IF_IN_TEN = 5;       // a dam with at least a 5 in 10 chance of falling below a third is always named
  const RECENT_LOOK_DAYS = 60;    // a satellite look older than this is too old to use
  const CLOSE = "Reply MAP";      // replying MAP would send a link to the farm's map in the app
  const MAP_LINK = "[map link]";  // placeholder for the farm's link in the app (long text)
  const LONG_OTHERS_MAX = 6;      // the long text lists at most 6 other dams by name
  const TRACK_RECORD_MIN = 5;     // a dam's track record is shown only with at least this many judged past forecasts
  const TRACK_RECORD_YEARS = "2016-2026";   // the backtest the track record counts (scripts/18_track_record.py)

  const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /** "2026-10-02" -> its day number (days since 1 Jan 1970). Refuses anything but YYYY-MM-DD. */
  function dayNumber(isoDate) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
    if (!match) throw new Error("Not a YYYY-MM-DD date: " + isoDate);
    return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) / 86400000;
  }

  /** "2026-09-13" -> "13 Sep". */
  function shortDate(isoDate) {
    dayNumber(isoDate);
    return Number(isoDate.slice(8, 10)) + " " + MONTHS[Number(isoDate.slice(5, 7)) - 1];
  }

  /** "2026-10-02" -> "Fri 2 Oct" (1 Jan 1970 was a Thursday; Monday is 0, as in Python). */
  function dateText(isoDate) {
    const weekday = ((dayNumber(isoDate) + 3) % 7 + 7) % 7;
    return WEEKDAYS[weekday] + " " + shortDate(isoDate);
  }

  /** A chance (0 to 1) as whole tenths, halves up, in whole thousandths: 0.58 -> 6, 0.45 -> 5, 0.04 -> 0. */
  function inTen(chance) {
    const thousandths = Math.floor(chance * 1000 + 0.5);
    return Math.floor((thousandths + 50) / 100);
  }

  /** 0.58 -> "6 in 10"; under 0.05 -> "less than 1 in 10"; 0.95 or more -> "more than 9 in 10". */
  function chanceText(chance) {
    const tenths = inTen(chance);
    if (tenths === 0) return "less than 1 in 10";
    if (tenths === 10) return "more than 9 in 10";
    return tenths + " in 10";
  }

  /** How full at the latest look: 45 -> "~45% full"; 100 or more -> "full". */
  function fullness(levelPct) {
    return levelPct >= 100 ? "full" : "~" + levelPct + "% full";
  }

  /** The DamDays floor counted from today: "at least 16 days", "at least 1 day", or "6 months+". */
  function floorText(days) {
    if (days >= CAP_DAYS) return "6 months+";
    return days === 1 ? "at least 1 day" : "at least " + days + " days";
  }

  /** [Dam 3, Dam 5, Dam 6] -> "3, 5 and 6". */
  function numbersText(dams) {
    const numbers = dams.map((d) => String(d.number));
    return numbers.length === 1 ? numbers[0] : numbers.slice(0, -1).join(", ") + " and " + numbers[numbers.length - 1];
  }

  /** 3.0 -> "3", 2.5 -> "2.5" (a radius; Python's "{:g}" for ordinary radii). */
  function kmText(km) {
    return String(Number(km.toPrecision(6)));
  }

  /** 0.42 -> "0.4" (a distance), halves up. */
  function oneDecimal(km) {
    const tenths = Math.floor(km * 10 + 0.5);
    return Math.floor(tenths / 10) + "." + (tenths % 10);
  }

  // ===========================================================================
  // notify/message.py, part 2: each dam on the day the text is sent
  // ===========================================================================
  /** Whole days from the dam's satellite look to `today` (an error if the look is after today). */
  function daysSinceLook(dam, today) {
    const days = dayNumber(today) - dayNumber(dam.issued_on);
    if (days < 0) {
      throw new Error(dam.dam_id + ": the satellite look " + dam.issued_on + " is after the text's date " + today);
    }
    return days;
  }

  /** What the text can say about a dam today: "forecast", "low", "not_refilled" or "no_look". */
  function kind(dam, today) {
    if (dam.issued_on === null || dam.issued_on === undefined || dam.status === "no_recent_look" ||
        daysSinceLook(dam, today) > RECENT_LOOK_DAYS) {
      return "no_look";
    }
    const kinds = { forecast: "forecast", already_low: "low", not_refilled: "not_refilled" };
    if (!(dam.status in kinds)) throw new Error(dam.dam_id + ": unknown status " + dam.status);
    return kinds[dam.status];
  }

  /** The DamDays floor counted from today: the floor from the look minus the days since the look. */
  function daysLeft(dam, today) {
    return dam.damdays_days - daysSinceLook(dam, today);
  }

  /** A forecast dam that looks fine for 3 months: at least 90 days left and under a 5 in 10 chance. */
  function isOk(dam, today) {
    return daysLeft(dam, today) >= OK_DAYS && inTen(dam.chance) < NAME_IF_IN_TEN;
  }

  /** The farm's dams split by kind; forecast dams most urgent first (fewest days left), others by number. */
  function sortedByKind(dams, today) {
    const groups = { forecast: [], low: [], not_refilled: [], no_look: [] };
    dams.forEach((dam) => groups[kind(dam, today)].push(dam));
    groups.forecast.sort((a, b) => (daysLeft(a, today) - daysLeft(b, today)) || (a.number - b.number));
    return groups;
  }

  /** The farm's latest satellite look (of dams seen in the last 60 days), or null. */
  function latestLook(dams, today) {
    const looks = dams.filter((d) => kind(d, today) !== "no_look").map((d) => d.issued_on);
    return looks.length ? looks.reduce((a, b) => (b > a ? b : a)) : null;
  }

  // ===========================================================================
  // notify/message.py, part 3: the SMS
  // ===========================================================================
  /** One forecast dam: "Dam 1 ~45% full: at least 16 days before it drops below 1/3". */
  function damLine(dam, today, explain) {
    const days = daysLeft(dam, today);
    if (days <= 0) return dam.name + " " + fullness(dam.level_pct) + ": may be below 1/3 now";
    const line = dam.name + " " + fullness(dam.level_pct) + ": " + floorText(days);
    return explain ? line + " before it drops below 1/3" : line;
  }

  /** Dams whose floor has run out since their look: one line, however many there are. */
  function ranOutLine(ranOut, today) {
    if (ranOut.length === 1) return damLine(ranOut[0], today, false);
    const byNumber = ranOut.slice().sort((a, b) => a.number - b.number);
    if (ranOut.length <= 4) return "Dams " + numbersText(byNumber) + " may be below 1/3 now";
    return ranOut.length + " dams may be below 1/3 now";
  }

  /** Dams already below a third: "Dam 3 already below 1/3", "Dam 3 looks dry", "7 dams already below 1/3". */
  function lowLine(low) {
    if (low.length === 1) {
      const dam = low[0];
      return dam.level_pct === 0 ? dam.name + " looks dry" : dam.name + " already below 1/3";
    }
    if (low.length <= 4) return "Dams " + numbersText(low) + " already below 1/3";
    return low.length + " dams already below 1/3";
  }

  /** Dams with no forecast: not refilled since their last low, or no clear satellite look lately. */
  function noForecastLine(dams, today) {
    if (dams.length === 1) {
      const dam = dams[0];
      if (kind(dam, today) === "not_refilled") return dam.name + " " + fullness(dam.level_pct) + ": no forecast until it refills";
      return dam.name + ": no clear satellite look lately";
    }
    if (dams.length <= 4) return "Dams " + numbersText(dams) + ": no forecast this week";
    return dams.length + " dams: no forecast this week";
  }

  /** The forecast dams not named, by their shortest floor: "Other 3 dams: at least 45 days". */
  function restLine(rest, today, explain) {
    const fewest = Math.min.apply(null, rest.map((d) => daysLeft(d, today)));
    if (fewest >= OK_DAYS) return "Other " + rest.length + " dams OK for 3 months+";
    const line = "Other " + rest.length + " dams: " + floorText(fewest);
    return explain ? line + " before they drop below 1/3" : line;
  }

  /** Every dam fine for 3 months. */
  function allOkLine(nDams) {
    if (nDams === 1) return "Your dam looks OK for 3 months+";
    if (nDams === 2) return "Both dams look OK for 3 months+";
    return "All " + nDams + " dams look OK for 3 months+";
  }

  /** The SMS's middle lines, most important first, each as [line, how many dams it covers]. */
  function smsItems(dams, today, radiusKm) {
    if (!dams.length) return [["No farm dams the satellites can see within " + kmText(radiusKm) + " km", 0]];
    const groups = sortedByKind(dams, today);
    const forecast = groups.forecast;
    const low = groups.low;
    const noForecast = groups.not_refilled.concat(groups.no_look).sort((a, b) => a.number - b.number);

    if (forecast.length && forecast.length === dams.length && forecast.every((d) => isOk(d, today))) {
      return [[allOkLine(dams.length), 0], [damLine(forecast[0], today, true), 1]];
    }

    const items = [];
    let explained = false;       // has a line said "before it drops below 1/3" yet?
    function addDam(dam) {
      items.push([damLine(dam, today, !explained), 1]);
      explained = explained || daysLeft(dam, today) > 0;
    }

    const ranOut = forecast.filter((d) => daysLeft(d, today) <= 0);
    const withDays = forecast.filter((d) => daysLeft(d, today) > 0);
    const named = withDays.slice(0, 1).concat(withDays.slice(1).filter((d) => inTen(d.chance) >= NAME_IF_IN_TEN));
    const namedSet = new Set(named);
    const rest = withDays.filter((d) => !namedSet.has(d));
    if (ranOut.length) items.push([ranOutLine(ranOut, today), ranOut.length]);
    named.forEach(addDam);
    if (low.length) items.push([lowLine(low), low.length]);
    if (rest.length === 1) addDam(rest[0]);
    else if (rest.length) items.push([restLine(rest, today, !explained), rest.length]);
    if (noForecast.length) items.push([noForecastLine(noForecast, today), noForecast.length]);
    return items;
  }

  /** The last line: "Reply MAP", or "Reply MAP for 2 more dams" when some dams did not fit. */
  function closeText(damsLeftOut) {
    if (damsLeftOut === 0) return CLOSE;
    return CLOSE + " for " + damsLeftOut + " more dam" + (damsLeftOut === 1 ? "" : "s");
  }

  /**
   * The SMS for a farm's dams. Line 1 is the date, then the farm's latest satellite look. If the
   * whole text does not fit one SMS: first the satellite date is left out; then lines are left out
   * from the end, and the last line says how many dams were left out.
   */
  function smsForDams(dams, today, radiusKm = DEFAULT_RADIUS_KM) {
    const look = latestLook(dams, today);
    const headers = [dateText(today)];
    if (look !== null) headers.unshift(dateText(today) + " (satellite " + shortDate(look) + ")");
    const items = smsItems(dams, today, radiusKm);
    for (let keep = items.length; keep > 0; keep--) {
      const leftOut = items.slice(keep).reduce((sum, item) => sum + item[1], 0);
      for (const header of headers) {
        const text = [header].concat(items.slice(0, keep).map((item) => item[0]), [closeText(leftOut)]).join("\n");
        if (fitsOneSms(text)) return text;
      }
    }
    throw new Error("No SMS fits in " + SMS_MAX + " places, even with one line: " + items[0][0]);
  }

  /** THE WEEKLY TEXT: one SMS for `farm` from the live forecasts, as sent on `today` ("YYYY-MM-DD"). */
  function weeklyText(farm, forecasts, today) {
    return smsForDams(damsForFarm(farm, forecasts), today, radiusOf(farm));
  }

  // ===========================================================================
  // notify/message.py, part 4: the long text (app or email)
  // ===========================================================================
  /** The headline dam in full, with its look date, distance and chance. */
  function headlineSentence(dam, today) {
    const days = daysLeft(dam, today);
    const start = dam.name + " (" + oneDecimal(dam.distance_km) + " km from the homestead) was " +
                  fullness(dam.level_pct) + " on " + shortDate(dam.issued_on) + ": ";
    let middle;
    if (days <= 0) {
      middle = "its cautious number of days has run out since then, so it may be below a third now. ";
    } else {
      const floor = days >= CAP_DAYS ? "6 months or more" : floorText(days);
      middle = floor + " before it drops below a third, counted from today. ";
    }
    const chance = "Chance it drops below a third by " + shortDate(dam.window_end) + ": " + chanceText(dam.chance) + ".";
    return start + middle + chance;
  }

  /** One of the other dams, in a few words. */
  function otherClause(dam, today) {
    const what = kind(dam, today);
    if (what === "forecast") {
      const days = daysLeft(dam, today);
      const floor = days <= 0 ? "may be below a third now" : floorText(days);
      return dam.name + " " + fullness(dam.level_pct) + ", " + floor +
             " (chance by " + shortDate(dam.window_end) + ": " + chanceText(dam.chance) + ")";
    }
    if (what === "low") {
      return dam.level_pct === 0 ? dam.name + " looks dry"
                                 : dam.name + " already below a third (" + fullness(dam.level_pct) + ")";
    }
    if (what === "not_refilled") return dam.name + " " + fullness(dam.level_pct) + ", no forecast until it refills to 60% full";
    return dam.name + " has had no clear satellite look in the last " + RECENT_LOOK_DAYS + " days";
  }

  /** A count with thousands commas: 1234 -> "1,234" (Python's f"{n:,}"; no locale involved). */
  function countText(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  /** True when a dam's track record ({held, judged}) has enough judged forecasts to show. */
  function hasTrackRecord(record) {
    return record !== null && record !== undefined && record.judged >= TRACK_RECORD_MIN;
  }

  /**
   * The long text's optional track-record line: how often our cautious days-left promise held on these dams
   * in the 2016-2026 backtest. records: {dam_id: {held, judged, ...}}, the "dams" of track_record.json.
   */
  function trackRecordLine(dams, today, records) {
    const where = dams.length === 1 ? "this dam" : "these " + dams.length + " dams";
    const head = "Our track record on " + where + " (" + TRACK_RECORD_YEARS + " backtest, forecasts the model " +
                 "made for years it never trained on): ";
    const recorded = dams.filter((d) => hasTrackRecord(records[d.dam_id]));
    if (!recorded.length) return head + "too few past forecasts to judge.";
    const held = recorded.reduce((sum, d) => sum + records[d.dam_id].held, 0);
    const judged = recorded.reduce((sum, d) => sum + records[d.dam_id].judged, 0);
    let body = "the cautious days-left promise held " + countText(held) + " of " + countText(judged) + " times";
    if (recorded.length < dams.length) {
      body += " (" + recorded.length + " of the " + dams.length + (recorded.length === 1 ? " has" : " have") +
              " enough history to judge)";
    }
    const forecast = sortedByKind(dams, today).forecast;
    if (dams.length > 1 && forecast.length) {
      const dam = forecast[0];
      const record = records[dam.dam_id];
      if (hasTrackRecord(record)) {
        body += "; on " + dam.name + ", " + countText(record.held) + " of " + countText(record.judged);
      } else {
        body += "; " + dam.name + " has too few past forecasts to judge";
      }
    }
    return head + body + ".";
  }

  /**
   * The long text for a farm's dams: 2 to 4 lines, may give chances ("6 in 10"). With the optional
   * trackRecord ({dam_id: {held, judged}}), one more line before the last: the track record.
   */
  function longForDams(dams, today, farmLabel = "Your farm", radiusKm = DEFAULT_RADIUS_KM, trackRecord = null) {
    const opening = farmLabel + ", " + dateText(today) + " " + Number(today.slice(0, 4)) + ": ";
    if (!dams.length) {
      return [opening + "no farm dams the satellites can see within " + kmText(radiusKm) + " km of " +
              "the homestead. They see dams of about half a hectare and up.", "Map: " + MAP_LINK].join("\n");
    }
    const count = dams.length + " farm dam" + (dams.length === 1 ? "" : "s");
    const look = latestLook(dams, today);
    const seen = look ? "latest satellite look " + shortDate(look)
                      : "no clear satellite look in the last " + RECENT_LOOK_DAYS + " days";
    const lines = [opening + count + " within " + kmText(radiusKm) + " km of the homestead; " + seen + "."];

    const groups = sortedByKind(dams, today);
    const ordered = groups.forecast.concat(groups.low, groups.not_refilled, groups.no_look);
    let others;
    if (groups.forecast.length) {
      lines.push(headlineSentence(groups.forecast[0], today));
      others = ordered.slice(1);
    } else {
      lines.push("No dam has a forecast this week.");
      others = ordered;
    }
    if (others.length) {
      const clauses = others.slice(0, LONG_OTHERS_MAX).map((d) => otherClause(d, today));
      if (others.length > LONG_OTHERS_MAX) clauses.push("and " + (others.length - LONG_OTHERS_MAX) + " more on the map");
      lines.push((groups.forecast.length ? "Also: " : "") + clauses.join("; ") + ".");
    }
    if (trackRecord !== null && trackRecord !== undefined) lines.push(trackRecordLine(dams, today, trackRecord));
    if (groups.forecast.length) {
      lines.push("Days are counted from today and are cautious: in ten test years a dam stayed above a " +
                 "third at least that long 9 times in 10. Map: " + MAP_LINK);
    } else {
      lines.push("Map: " + MAP_LINK);
    }
    return lines.join("\n");
  }

  /** The weekly text's longer version for the app or an email (trackRecord optional, as in longForDams). */
  function longText(farm, forecasts, today, trackRecord = null) {
    return longForDams(damsForFarm(farm, forecasts), today, farm.name || "Your farm", radiusOf(farm), trackRecord);
  }

  const api = {
    // the texts
    weeklyText, longText, smsForDams, longForDams,
    // the farm and its dams
    damsForFarm, docFromDams, distanceKm, toTenMetres, liveIssue,
    // each dam on the text's date
    kind, daysLeft, daysSinceLook,
    // wording
    inTen, chanceText, fullness, floorText, shortDate, dateText, dayNumber, oneDecimal, countText,
    // the track record (long text only)
    trackRecordLine, hasTrackRecord,
    // one SMS
    septets, isGsm7, fitsOneSms,
    // settings
    SMS_MAX, CAP_DAYS, OK_DAYS, RECENT_LOOK_DAYS, DEFAULT_RADIUS_KM, NAME_IF_IN_TEN, TRACK_RECORD_MIN, TRACK_RECORD_YEARS,
  };

  if (typeof module === "object" && module.exports) module.exports = api;       // Node: the parity check
  if (typeof window !== "undefined") {                                          // the browser: DamDays.text
    window.DamDays = window.DamDays || {};
    window.DamDays.text = api;
  }
})();
