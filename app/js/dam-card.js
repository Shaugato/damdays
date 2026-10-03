/* dam-card.js
 * The card that opens when you pick a dam. Used by My farm and Runway (today's
 * forecast) and Rewind (a past forecast, and after the reveal, what happened).
 *
 * The card, top to bottom, in the weekly text's words (mentor feedback):
 *   1. how full the dam was at its last clear look ("~67% full on 13 Sep 2026")
 *   2. the DamDays number, the headline: "at least 29 days" before it drops below
 *      a third, 9 times in 10, counted from the day of this week's text (or, in
 *      Rewind, from the day the forecast was made)
 *   3. the chance it drops below a third within 90 days, as "3 in 10"
 *   3b. today's forecast only (My farm, Runway): our track record on this dam, so a farmer
 *      can judge our accuracy on their own water: how often the cautious days-left promise
 *      held on it in the 2016-2026 backtest (track_record.json, scripts/18_track_record.py)
 *   4. the runway curve (chance by 30, 60, 90 and 180 days after the last look)
 *   5. the water history since 1988
 *   6. Rewind only: what actually happened
 *   7. notes and the coverage reminder
 * "%" only ever means how full a dam is. A chance is always "N in 10".
 */
window.DamDays = window.DamDays || {};

DamDays.damCard = (function () {
  "use strict";

  const fmt = DamDays.format;
  const esc = (text) => DamDays.format.escapeHtml(text);

  /** "2026-10-02" -> "Fri 2 Oct 2026". */
  function longDay(isoDate) {
    return DamDays.text.dateText(isoDate) + " " + isoDate.slice(0, 4);
  }

  /** "~67% full" or "full" (how full at the look), or "dry" when no water was seen. */
  function howFull(levelPct) {
    return levelPct === 0 ? "dry" : DamDays.text.fullness(levelPct);
  }

  /**
   * The DamDays floor counted from `asOf` (the text's date, or the forecast's date in Rewind):
   * { left, since }: the floor from the satellite look minus the days since the look.
   * Same rule as the weekly text (js/text.js, daysLeft).
   */
  function daysFrom(row, asOf) {
    const since = asOf && row.issued_on
      ? Math.max(0, DamDays.text.dayNumber(asOf) - DamDays.text.dayNumber(row.issued_on)) : 0;
    return { left: row.damdays_days - since, since: since };
  }

  /** A few words about a dam's days, for map tips: "at least 29 days", "may be below a third now". */
  function daysWords(row, asOf) {
    if (row.status === "already_low") return row.level_pct === 0 ? "looks dry" : "already below a third";
    if (row.status === "not_refilled") return "no forecast until it refills";
    if (row.status !== "forecast" || row.damdays_days === null) return "no recent clear look";
    const left = daysFrom(row, asOf).left;
    return left <= 0 ? "may be below a third now" : DamDays.text.floorText(left);
  }

  // ---- 1. How full, and why there is no forecast ------------------------------
  function headline(name, row, meta) {
    const who = "<strong>" + esc(name) + "</strong>";
    const when = fmt.date(row.issued_on);
    if (row.status === "forecast") {
      return '<p class="card-headline">' + who + ": " + howFull(row.level_pct) + " on " + when +
             ", its last clear satellite look.</p>";
    }
    if (row.status === "already_low") {
      const level = row.level_pct === 0 ? "it looked dry on " + when : "it was " + howFull(row.level_pct) + " on " + when;
      return '<p class="card-headline">' + who + " is already below a third: " + level +
             ", its last clear satellite look. No forecast until it refills.</p>";
    }
    if (row.status === "not_refilled") {
      const level = row.level_pct === null ? "" : " (" + howFull(row.level_pct) + " on " + when + ")";
      return '<p class="card-headline">' + who + level + " has not been back to " + meta.arm_level_pct +
             "% full in the last six months, so DamDays waits until it refills before forecasting it.</p>";
    }
    return '<p class="card-headline">' + who +
           ": no clear satellite look in the last 60 days, so no forecast right now.</p>";
  }

  // ---- 2. The DamDays number (the headline) -----------------------------------
  /** Where the days are counted from, in a sentence. */
  function countedFrom(row, asOf, since, isLive) {
    const look = fmt.date(row.issued_on);
    if (since === 0) return "Counted from its last clear look, " + look + ".";
    const day = isLive ? longDay(asOf) + ", the day of this week's text" : fmt.date(asOf) + ", the day of this forecast";
    return "Counted from " + day + ": " + row.damdays_days + " days from its last clear look (" + look +
           "), less the " + fmt.count(since, "day") + " since.";
  }

  function damdaysNumber(row, asOf, isLive) {
    if (row.status !== "forecast" || row.damdays_days === null) return "";
    const days = daysFrom(row, asOf);
    const tip = fmt.tip("What is the DamDays number?",
                        "A cautious count of days of water. In 9 seasons out of 10 like this one, the dam " +
                        "would stay above a third for at least this many days. In ten test years it held 9 times in 10.");
    const note = '<p class="damdays-from">' + esc(countedFrom(row, asOf, days.since, isLive)) + "</p>";
    if (days.left <= 0) {
      return '<div class="damdays-box"><p class="damdays-text"><strong>DamDays.</strong> Its cautious days ' +
             "have run out since that look, so it <strong>may be below a third now</strong>. The next clear " +
             "look will tell. " + tip + "</p>" + note + "</div>";
    }
    const shown = fmt.damdays(days.left);
    let sentence;
    if (days.left < 7) {
      sentence = "It could drop below a third within days.";
    } else if (days.left >= DamDays.settings.damdaysCapDays) {
      sentence = "At least " + shown + " days (six months or more) before it drops below a third, 9 times in 10.";
    } else {
      sentence = "At least " + shown + " days before it drops below a third, 9 times in 10.";
    }
    return '<div class="damdays-box">' +
           '<p class="damdays-value"><span class="damdays-big">' + shown + "</span> <span>" +
           (days.left === 1 ? "day" : "days") + "</span></p>" +
           '<p class="damdays-text"><strong>DamDays.</strong> ' + sentence + " " + tip + "</p>" + note + "</div>";
  }

  // ---- 3. The chance, as "N in 10" --------------------------------------------
  function chanceLines(row) {
    if (row.status !== "forecast" || row.chance === null) return "";
    let html = '<p class="card-chance">Chance it drops below a third by ' + fmt.date(row.window_end) +
               ": <strong>" + fmt.chance(row.chance) + "</strong>.</p>";
    if (row.chance_low !== null && row.chance_low !== undefined && row.chance_high !== null && row.chance_high !== undefined) {
      html += '<p class="card-band">In a wetter or drier season than usual: ' +
              fmt.chanceRange(row.chance_low, row.chance_high) + ". " +
              fmt.tip("What is the wetter or drier season range?",
                      "The forecast is for a typical season. The range shows how far the chance could move " +
                      "if the coming months turn out unusually wet or unusually dry.") + "</p>";
    }
    return html;
  }

  // ---- 3b. Our track record on this dam (2016-2026 backtest) -------------------
  /** "2016" -> "2016-17" (a July-June season). */
  function seasonLabel(year) {
    const y = Number(year);
    return y + "-" + String(y + 1).slice(-2);
  }

  /** A share as "about 8 times in 10", rounded as chances are ("N in 10"). */
  function timesInTen(share) {
    const tenths = DamDays.text.inTen(share);
    if (tenths === 0) return "less than once in 10";
    if (tenths === 1) return "about once in 10";
    if (tenths === 10) return "more than 9 times in 10";
    return "about " + tenths + " times in 10";
  }

  /** How the dam's record compares with the 9 in 10 the promise aims for, in one plain sentence. */
  function recordVerdict(record) {
    const tenths = DamDays.text.inTen(record.held / record.judged);
    let words;
    if (record.held === record.judged) words = "It held every time.";
    else if (tenths === 10) words = "That is " + timesInTen(record.held / record.judged) + ".";
    else if (tenths === 9) words = "That is " + timesInTen(record.held / record.judged) + ", as it aims for.";
    else {
      words = "That is " + timesInTen(record.held / record.judged) + ", less often than the 9 in 10 it aims " +
              "for: on this dam, give the days extra margin.";
    }
    if (record.judged < 20) words += " With so few past forecasts, this is only a rough guide.";
    return words;
  }

  /**
   * "Our track record on this dam (2016-2026 backtest): the cautious days-left promise held 18 of 20 times."
   * With fewer than 5 judged past forecasts: "not enough history". Every dam is shown as it is, good or poor.
   */
  function trackRecordSection(track, damId) {
    if (!track || !track.dams) return "";
    const record = track.dams[damId];
    const tip = fmt.tip("What is the backtest?", track.tip);
    const lead = '<strong>Our track record on this dam</strong> (<span class="record-label">' + esc(track.label) +
                 "</span>): ";
    if (!DamDays.text.hasTrackRecord(record)) {
      const n = record ? record.judged : 0;
      return '<section class="card-section card-record"><p class="record-main">' + lead +
             "<strong>not enough history</strong>. " + (n === 0 ? "No past forecast for this dam could be checked"
               : "Only " + fmt.count(n, "past forecast") + " could be checked") +
             "; we show a record once " + track.min_judged + " can be checked. " + tip + "</p></section>";
    }
    const count = DamDays.text.countText;
    const years = Object.keys(record.by_season).sort();
    const span = years.length === 1 ? "1 season (" + seasonLabel(years[0]) + ")"
      : years.length + " seasons, " + seasonLabel(years[0]) + " to " + seasonLabel(years[years.length - 1]);
    const typical = record.median_days === null || record.median_days < 1 ? ""
      : " Its typical promise was " + (record.median_days >= DamDays.settings.damdaysCapDays
        ? "6 months or more" : "at least " + fmt.count(record.median_days, "day")) + ".";
    const likely = record.likely_said > 0
      ? '<p class="record-more">When we said a fall below a third was likely (5 in 10 or more), it fell within ' +
        "90 days " + count(record.likely_fell) + " of " + count(record.likely_said) + " times.</p>" : "";
    const seasons = years.map((y) => seasonLabel(y) + ": " + count(record.by_season[y][0]) + " of " +
                                     count(record.by_season[y][1])).join(" &middot; ");
    // The last three seasons of the backtest, so a change on this dam is easy to see.
    const recentYears = [0, 1, 2].map((i) => String(track.last_season_year - i)).filter((y) => record.by_season[y]);
    const recentHeld = recentYears.reduce((sum, y) => sum + record.by_season[y][0], 0);
    const recentJudged = recentYears.reduce((sum, y) => sum + record.by_season[y][1], 0);
    const recent = recentJudged > 0 && years.length > recentYears.length
      ? " In the last three seasons (" + seasonLabel(track.last_season_year - 2) + " to " +
        seasonLabel(track.last_season_year) + ") it held " + count(recentHeld) + " of " + count(recentJudged) + " times."
      : "";
    return '<section class="card-section card-record">' +
      '<p class="record-main">' + lead + "the cautious days-left promise held <strong>" + count(record.held) +
      " of " + count(record.judged) + " times</strong>. " + tip + "</p>" +
      '<p class="record-more">' + esc(recordVerdict(record)) + recent + typical + "</p>" + likely +
      '<p class="chart-note">Over ' + span + ". Season by season (July to June), held of checked: " + seasons +
      ".</p></section>";
  }

  /** Size, and the dam's name on the Runway map when the card calls it something else. */
  function facts(dam, row, name) {
    const parts = ["Size " + dam.area_ha.toFixed(1) + " ha"];
    if (name !== dam.name && dam.name !== dam.dam_id) parts.push("on the Runway map: " + esc(dam.name));
    return '<p class="card-facts">' + parts.join(" &middot; ") + "</p>";
  }

  // ---- 4. The runway curve ------------------------------------------------------
  function curveSection(row, curve, horizons) {
    if (!curve) return "";
    const shaped = { horizons: horizons, chance: curve.chance, low: curve.low, high: curve.high };
    const headlineMark = { days: 90, chance: row.chance,
                           label: fmt.chance(row.chance) + " by " + fmt.date(row.window_end) };
    const asText = horizons.map((d, i) => d + " days: " + fmt.chance(curve.chance[i])).join(" &middot; ");
    return '<section class="card-section"><h3>Chance of dropping below a third, up to six months after the last look</h3>' +
           DamDays.charts.runwayCurve(shaped, headlineMark) +
           '<p class="chart-note">' + asText + ". Shaded: a wetter or drier season than usual.</p></section>";
  }

  // ---- 5. The water history -----------------------------------------------------
  function historySection(history, range, options) {
    if (!history) return "";
    const chart = DamDays.charts.waterHistory(history, {
      firstMonth: range.first_month,
      lastMonth: range.last_month,
      threshold: options.thresholdPct,
      untilDate: options.untilDate || null,
      markDate: options.markDate || null,
    });
    const hidden = options.untilDate ? " Later months stay hidden until you reveal what happened." : "";
    return '<section class="card-section"><h3>How full since ' + range.first_month.slice(0, 4) +
           " (% of full)</h3>" + chart +
           '<p class="chart-note">Short orange ticks: it fell below a third. Tall black ticks: it ran dry.' +
           hidden + "</p></section>";
  }

  // ---- 6. What happened (Rewind, after the reveal) ------------------------------
  function outcomeSection(row) {
    if (row.status !== "forecast") return "";
    let text;
    if (row.outcome === true) {
      text = "It <strong>fell below a third</strong> on " + fmt.date(row.outcome_date) + ".";
    } else if (row.outcome === false) {
      text = "It <strong>stayed above a third</strong> until " + fmt.date(row.window_end) + ".";
    } else {
      text = "Not enough clear satellite looks to know.";
    }
    return '<section class="card-section card-outcome"><h3>What happened</h3><p>' + text + "</p></section>";
  }

  // ---- 7. Notes and coverage ----------------------------------------------------
  function notesSection(row) {
    if (!row.notes || !row.notes.length) return "";
    return '<ul class="card-notes">' + row.notes.map((note) => "<li>" + esc(note) + "</li>").join("") + "</ul>";
  }

  function coverageNote(meta) {
    return '<p class="card-coverage">DamDays sees dams larger than about ' + meta.min_dam_area_ha.toFixed(1) +
           " ha. Bores and tanks are not visible.</p>";
  }

  /**
   * Build the whole card.
   * options.revealed   Rewind: show what happened (and the full history)
   * options.rewind     true in Rewind, so the history stops at the forecast date until the reveal
   * options.name       the name to show (My farm: "Dam 2", numbered from the homestead)
   * options.dam, options.row  the dam and its forecast row, when they are not in this dataset
   *                    (My farm's demo farms outside the region the map shows)
   * Days are counted from this week's text date for today's forecasts, and from the forecast's
   * date in Rewind.
   */
  function render(data, damId, issue, options) {
    const dam = options.dam || data.damsById.get(damId);
    const row = options.row || (issue && issue.rowsByDam.get(damId));
    if (!dam || !row) return '<p class="card-empty">No forecast for this dam on this date.</p>';
    const meta = data.meta;
    const isLive = !issue || issue.kind === "live";
    const asOf = isLive ? (data.textDate || (issue && issue.issue_date)) : issue.issue_date;
    const name = options.name || dam.name;
    const mockTag = meta.is_mock ? ' <span class="tag-mock">MOCK</span>' : "";
    const hideFuture = options.rewind && !options.revealed;
    const inData = issue && data.damsById.has(damId);

    return '<article class="card" aria-label="' + esc(name) + '">' +
      '<p class="card-kicker">' + esc(isLive ? "Forecast" : "Forecast made on " + fmt.date(issue.issue_date)) +
      mockTag + "</p>" +
      headline(name, row, meta) +
      damdaysNumber(row, asOf, isLive) +
      chanceLines(row) +
      (isLive ? trackRecordSection(data.trackRecord, dam.dam_id) : "") +
      facts(dam, row, name) +
      (inData ? curveSection(row, data.curveFor(issue.issue_date, damId), data.curveHorizons) : "") +
      (options.revealed ? outcomeSection(row) : "") +
      (inData ? historySection(data.historyFor(damId), data.history, {
        thresholdPct: meta.threshold_pct,
        untilDate: hideFuture ? row.issued_on : null,   // stop at the last look before the forecast
        markDate: options.rewind ? issue.issue_date : null,
      }) : "") +
      notesSection(row) +
      coverageNote(meta) +
      "</article>";
  }

  /**
   * After a dam is picked, make sure its card is in view: scroll the side panel
   * back to its top, and on narrow screens (where the panel sits below the
   * map) scroll the page down to it.
   */
  function bringIntoView(panel) {
    panel.scrollTop = 0;
    if (window.matchMedia("(max-width: 960px)").matches) {
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  return { render, bringIntoView, daysFrom, daysWords, howFull, seasonLabel, timesInTen };
})();
