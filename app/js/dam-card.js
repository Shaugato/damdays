/* dam-card.js
 * The card that opens when you pick a dam. Used by Runway (today's forecast)
 * and Rewind (a past forecast, and after the reveal, what happened).
 *
 * The card, top to bottom:
 *   1. the plain sentence ("Dam 3: 58% chance below a third by 1 Feb 2027")
 *   2. the DamDays number ("at least 60 days, 9 times in 10")
 *   3. the runway curve (chance by 30, 60, 90 and 180 days)
 *   4. the water history since 1988
 *   5. Rewind only: what actually happened
 *   6. notes and the coverage reminder
 */
window.DamDays = window.DamDays || {};

DamDays.damCard = (function () {
  "use strict";

  const fmt = DamDays.format;
  const esc = (text) => DamDays.format.escapeHtml(text);

  // ---- 1. The plain sentence ------------------------------------------------
  /** The headline sentence, which depends on whether the dam has a forecast. */
  function headline(dam, row, meta) {
    const name = "<strong>" + esc(dam.name) + "</strong>";
    if (row.status === "forecast") {
      return '<p class="card-headline">' + name + ": <strong>" + fmt.percent(row.chance) +
             " chance</strong> below a third by " + fmt.date(row.window_end) + ".</p>" +
             '<p class="card-band">Likely range in a wetter or drier season than usual: ' +
             fmt.percentRange(row.chance_low, row.chance_high) + ". " +
             fmt.tip("What is the likely range?",
                     "The forecast is for a typical season. The range shows how far the chance could move " +
                     "if the coming months turn out unusually wet or unusually dry.") + "</p>";
    }
    if (row.status === "already_low") {
      return '<p class="card-headline">' + name + " is already below a third (" + row.level_pct +
             "% of full at the last clear look). No runway forecast until it refills.</p>";
    }
    if (row.status === "not_refilled") {
      return '<p class="card-headline">' + name + " has not been at least " + meta.arm_level_pct +
             "% full in the last six months, so DamDays waits until it refills before forecasting it.</p>";
    }
    return '<p class="card-headline">' + name +
           ": no clear satellite look in the last 60 days, so no forecast right now.</p>";
  }

  /** Size, last clear look and level at that look. */
  function facts(dam, row) {
    const parts = [dam.area_ha.toFixed(1) + " ha", "last clear look " + fmt.date(row.issued_on)];
    if (row.level_pct !== null) parts.push(row.level_pct + "% of full then");
    return '<p class="card-facts">' + parts.join(" &middot; ") + "</p>";
  }

  // ---- 2. The DamDays number ------------------------------------------------
  function damdaysNumber(row) {
    if (row.status !== "forecast" || row.damdays_days === null) return "";
    const days = row.damdays_days;
    const shown = fmt.damdays(days);
    let sentence;
    if (days < 7) {
      sentence = "It could fall below a third within days.";
    } else if (days >= DamDays.settings.damdaysCapDays) {
      sentence = "At least " + shown + " days (six months or more) before it falls below a third, 9 times in 10.";
    } else {
      sentence = "At least " + shown + " days before it falls below a third, 9 times in 10.";
    }
    return '<div class="damdays-box">' +
           '<p class="damdays-value"><span class="damdays-big">' + shown + '</span> <span>days</span></p>' +
           '<p class="damdays-text"><strong>DamDays.</strong> ' + sentence + " " +
           fmt.tip("What is the DamDays number?",
                   "A cautious count of days of water. In 9 seasons out of 10 like this one, the dam " +
                   "would stay above a third for at least this many days.") + "</p></div>";
  }

  // ---- 3. The runway curve --------------------------------------------------
  function curveSection(row, curve, horizons) {
    if (!curve) return "";
    const shaped = { horizons: horizons, chance: curve.chance, low: curve.low, high: curve.high };
    const headlineMark = { days: 90, chance: row.chance,
                           label: fmt.percent(row.chance) + " by " + fmt.date(row.window_end) };
    const asText = horizons.map((d, i) => d + " days: " + fmt.percent(curve.chance[i])).join(" &middot; ");
    return '<section class="card-section"><h3>Chance of falling below a third, next six months</h3>' +
           DamDays.charts.runwayCurve(shaped, headlineMark) +
           '<p class="chart-note">' + asText + ". Shaded: likely range in a wetter or drier season.</p></section>";
  }

  // ---- 4. The water history -------------------------------------------------
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
    return '<section class="card-section"><h3>Water level since ' + range.first_month.slice(0, 4) +
           " (% of full)</h3>" + chart +
           '<p class="chart-note">Short orange ticks: it fell below a third. Tall black ticks: it ran dry.' +
           hidden + "</p></section>";
  }

  // ---- 5. What happened (Rewind, after the reveal) --------------------------
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

  // ---- 6. Notes and coverage ------------------------------------------------
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
   */
  function render(data, damId, issue, options) {
    const dam = data.damsById.get(damId);
    const row = issue.rowsByDam.get(damId);
    if (!dam || !row) return '<p class="card-empty">No forecast for this dam on this date.</p>';
    const meta = data.meta;
    const mockTag = meta.is_mock ? ' <span class="tag-mock">MOCK</span>' : "";
    const hideFuture = options.rewind && !options.revealed;

    return '<article class="card" aria-label="' + esc(dam.name) + '">' +
      '<p class="card-kicker">' + esc(issue.kind === "live" ? "Forecast" : "Forecast made on " + fmt.date(issue.issue_date)) +
      mockTag + "</p>" +
      headline(dam, row, meta) +
      facts(dam, row) +
      damdaysNumber(row) +
      curveSection(row, data.curveFor(issue.issue_date, damId), data.curveHorizons) +
      (options.revealed ? outcomeSection(row) : "") +
      historySection(data.historyFor(damId), data.history, {
        thresholdPct: meta.threshold_pct,
        untilDate: hideFuture ? row.issued_on : null,   // stop at the last look before the forecast
        markDate: options.rewind ? issue.issue_date : null,
      }) +
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

  return { render, bringIntoView };
})();
