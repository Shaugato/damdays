/* charts.js
 * Two small hand-drawn SVG charts, so the app needs no chart library:
 *   runwayCurve: chance of falling below a third by 30, 60, 90 and 180 days;
 *   waterHistory: the dam's monthly water level since 1988 (a sparkline).
 * Each function returns an SVG string to put in the page.
 */
window.DamDays = window.DamDays || {};

DamDays.charts = (function () {
  "use strict";

  const esc = (text) => DamDays.format.escapeHtml(text);
  const LINE_COLOR = "#bb561a";     // dark orange, the same family as the map colours
  const GRID_COLOR = "#e1e0d9";
  const AXIS_TEXT = "#6b6963";

  /** Round to 1 decimal so the SVG text stays short and readable. */
  function r1(value) {
    return Math.round(value * 10) / 10;
  }

  /** "x1,y1 x2,y2 ..." for an SVG polyline or polygon. */
  function pointList(points) {
    return points.map((p) => r1(p[0]) + "," + r1(p[1])).join(" ");
  }

  // -------------------------------------------------------------------------
  // Runway curve
  // -------------------------------------------------------------------------
  /**
   * curve: { horizons: [30,60,90,180], chance: [...], low: [...], high: [...] }
   * headline: { days: 90, chance: 0.58, label: "6 in 10 by 11 Dec 2026" }
   * Days are counted from the forecast's satellite look ("last look").
   */
  function runwayCurve(curve, headline) {
    const box = { left: 54, right: 328, top: 16, bottom: 158 };
    const maxDays = curve.horizons[curve.horizons.length - 1];
    const x = (days) => box.left + (days / maxDays) * (box.right - box.left);
    const y = (chance) => box.bottom - chance * (box.bottom - box.top);

    // Every curve starts at no chance at the last look.
    const days = [0].concat(curve.horizons);
    const mid = [0].concat(curve.chance);
    const low = [0].concat(curve.low);
    const high = [0].concat(curve.high);

    const parts = [];

    // Horizontal gridlines labelled "N in 10" (a chance is never written as a percent).
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach((level) => {
      parts.push('<line x1="' + box.left + '" x2="' + box.right + '" y1="' + r1(y(level)) +
                 '" y2="' + r1(y(level)) + '" stroke="' + GRID_COLOR + '" stroke-width="1"/>');
      parts.push('<text x="' + (box.left - 6) + '" y="' + r1(y(level) + 4) +
                 '" text-anchor="end" class="chart-axis">' + Math.round(level * 10) + " in 10</text>");
    });

    // Day labels along the bottom.
    days.forEach((d) => {
      const text = d === 0 ? "last look" : d === maxDays ? d + " days" : String(d);
      const anchor = d === 0 ? "start" : d === maxDays ? "end" : "middle";
      parts.push('<text x="' + r1(x(d)) + '" y="' + (box.bottom + 18) + '" text-anchor="' + anchor +
                 '" class="chart-axis">' + text + "</text>");
    });

    // Shaded band: the likely range for a wetter or drier season.
    const bandPoints = days.map((d, i) => [x(d), y(high[i])])
      .concat(days.slice().reverse().map((d, i) => [x(d), y(low[low.length - 1 - i])]));
    parts.push('<polygon points="' + pointList(bandPoints) + '" fill="' + LINE_COLOR +
               '" fill-opacity="0.16" stroke="none"/>');

    // The central curve.
    const linePoints = days.map((d, i) => [x(d), y(mid[i])]);
    parts.push('<polyline points="' + pointList(linePoints) + '" fill="none" stroke="' + LINE_COLOR +
               '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>');

    // A dot at each horizon, with a hover tooltip.
    curve.horizons.forEach((d, i) => {
      const tip = d + " days: " + DamDays.format.chance(curve.chance[i]) +
                  " (wetter or drier season: " + DamDays.format.chanceRange(curve.low[i], curve.high[i]) + ")";
      parts.push('<circle cx="' + r1(x(d)) + '" cy="' + r1(y(curve.chance[i])) + '" r="4" fill="' +
                 LINE_COLOR + '" stroke="#ffffff" stroke-width="2"><title>' + esc(tip) + "</title></circle>");
    });

    // The headline (the 90-day chance from the main forecast), marked and labelled.
    if (headline) {
      const hx = x(headline.days);
      const hy = y(headline.chance);
      const labelY = hy - 12 < box.top + 4 ? hy + 22 : hy - 12;
      parts.push('<circle cx="' + r1(hx) + '" cy="' + r1(hy) + '" r="6.5" fill="none" stroke="#1d1c1a" stroke-width="2"/>');
      parts.push('<text x="' + r1(hx - 10) + '" y="' + r1(labelY) + '" text-anchor="end" class="chart-label">' +
                 esc(headline.label) + "</text>");
    }

    const summary = "Chance of falling below a third, counted from the last look: " + curve.horizons.map((d, i) =>
      d + " days " + DamDays.format.chance(curve.chance[i])).join(", ");
    return '<svg class="chart chart-runway" viewBox="0 0 340 186" role="img" aria-label="' +
           esc(summary) + '">' + parts.join("") + "</svg>";
  }

  // -------------------------------------------------------------------------
  // Water history sparkline
  // -------------------------------------------------------------------------
  /** Months between the first month of the history ("1988-01") and a date. */
  function monthsBetween(firstMonth, isoDate) {
    const [y0, m0] = firstMonth.split("-").map(Number);
    const [y1, m1] = isoDate.split("-").map(Number);
    return (y1 - y0) * 12 + (m1 - m0);
  }

  /**
   * history: { level_pct: [...], events: [{date, kind}] }
   * options.firstMonth  "1988-01", the month of level_pct[0]
   * options.lastMonth   "2026-09", the month of the last value
   * options.threshold   30 (% of full that counts as "below a third")
   * options.untilDate   hide everything after this date (Rewind before the reveal)
   * options.markDate    draw a vertical "forecast made" line at this date
   */
  function waterHistory(history, options) {
    const box = { left: 4, right: 296, top: 10, bottom: 72 };
    const values = history.level_pct;
    const lastIndex = options.untilDate
      ? Math.min(values.length - 1, monthsBetween(options.firstMonth, options.untilDate))
      : values.length - 1;
    const x = (i) => box.left + (i / (values.length - 1)) * (box.right - box.left);
    const y = (pct) => box.bottom - (Math.min(pct, 110) / 110) * (box.bottom - box.top);

    const parts = [];

    // Reference lines: full, and a third.
    [[100, "full"], [options.threshold, "a third"]].forEach(([level, label]) => {
      parts.push('<line x1="' + box.left + '" x2="' + box.right + '" y1="' + r1(y(level)) + '" y2="' +
                 r1(y(level)) + '" stroke="' + GRID_COLOR + '" stroke-width="1"/>');
      parts.push('<text x="' + (box.right + 4) + '" y="' + r1(y(level) + 4) + '" class="chart-axis">' +
                 label + "</text>");
    });

    // Build the line in pieces: a month with no clear look (null) breaks the line.
    const segments = [];
    let current = [];
    for (let i = 0; i <= lastIndex; i++) {
      if (values[i] === null) {
        if (current.length) segments.push(current);
        current = [];
      } else {
        current.push([x(i), y(values[i])]);
      }
    }
    if (current.length) segments.push(current);

    segments.forEach((points) => {
      // A pale water-coloured area under the line, then the line itself.
      const area = [[points[0][0], box.bottom]].concat(points, [[points[points.length - 1][0], box.bottom]]);
      parts.push('<polygon points="' + pointList(area) + '" fill="' + DamDays.settings.waterLine +
                 '" fill-opacity="0.12" stroke="none"/>');
      if (points.length > 1) {
        parts.push('<polyline points="' + pointList(points) + '" fill="none" stroke="' +
                   DamDays.settings.waterLine + '" stroke-width="1.5" stroke-linejoin="round"/>');
      }
    });

    // Past events as ticks under the chart: short orange = below a third, tall black = ran dry.
    (history.events || []).forEach((event) => {
      const index = monthsBetween(options.firstMonth, event.date);
      if (index > lastIndex) return;
      const isDry = event.kind === "dry";
      const height = isDry ? 9 : 5;
      const color = isDry ? "#111111" : LINE_COLOR;
      const label = (isDry ? "Ran dry, " : "Fell below a third, ") + DamDays.format.date(event.date);
      parts.push('<line x1="' + r1(x(index)) + '" x2="' + r1(x(index)) + '" y1="' + (box.bottom + 2) +
                 '" y2="' + (box.bottom + 2 + height) + '" stroke="' + color + '" stroke-width="2"><title>' +
                 esc(label) + "</title></line>");
    });

    // Rewind: mark the day the forecast was made.
    if (options.markDate) {
      const index = monthsBetween(options.firstMonth, options.markDate);
      parts.push('<line x1="' + r1(x(index)) + '" x2="' + r1(x(index)) + '" y1="' + box.top + '" y2="' +
                 box.bottom + '" stroke="#1d1c1a" stroke-width="1.5"/>');
    }

    // First and last year under the chart.
    const firstYear = options.firstMonth.slice(0, 4);
    const lastYear = options.lastMonth.slice(0, 4);
    parts.push('<text x="' + box.left + '" y="' + (box.bottom + 24) + '" class="chart-axis">' + firstYear + "</text>");
    parts.push('<text x="' + box.right + '" y="' + (box.bottom + 24) + '" text-anchor="end" class="chart-axis">' +
               lastYear + "</text>");

    const known = values.slice(0, lastIndex + 1).filter((v) => v !== null);
    const summary = known.length === 0
      ? "No clear satellite looks of this dam yet."
      : "Water level history since " + firstYear + ". Lowest " + Math.min(...known) +
        "% of full, latest " + known[known.length - 1] + "% of full.";
    return '<svg class="chart chart-history" viewBox="0 0 340 100" role="img" aria-label="' +
           esc(summary) + '">' + parts.join("") + "</svg>";
  }

  return { runwayCurve, waterHistory };
})();
