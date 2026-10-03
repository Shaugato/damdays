/* charts.js
 * Small hand-drawn SVG charts, so the app needs no chart library. Each function returns an
 * SVG string to put in the page.
 *
 * For the dam sheet (WP-D, UI_SPEC 3.3 and 5.14), drawn at the container's width so the
 * labels stay 13 px, with colours from the design tokens (so dark mode follows):
 *   tenDots(chance, opts)       ten circles, the first N filled in the chance's colour ("N in 10")
 *   sixMonths(curve, opts)      the chance it drops below a third over six months, its points
 *                               written as dates, the day of the text and the DamDays day marked
 *   history(history, opts)      how full since 1988: three-month medians on phones, monthly when
 *                               wide; the band below a third shaded; ticks for falls below a third
 *                               and for looks that saw no water
 *   historyFacts(history, opts) the counts and the latest value, for the sentence under it
 *   lineAt(chance, horizons, days)  the curve's straight line at a day (0 at the look)
 *   bandVar(chance)             "var(--c2)" etc.: the chance's colour token
 *
 * For the old map views' dam card (js/dam-card.js), kept with the same names:
 *   runwayCurve(curve, headline, marks)   the six-month chance, with the DamDays day and the
 *                                         day of the text marked when `marks` is given
 *   waterHistory(history, options)        the water level since 1988 (a sparkline)
 *
 * Wording: "%" only ever means how full a dam is; a chance is "N in 10" (js/text.js rounding);
 * a look that saw no water is "no water seen", never "dry".
 */
window.DamDays = window.DamDays || {};

DamDays.charts = (function () {
  "use strict";

  const esc = (text) => DamDays.format.escapeHtml(text);
  const LINE_COLOR = "#bb561a";     // dark orange, the same family as the map colours
  const GRID_COLOR = "#e1e0d9";
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /** Round to 1 decimal so the SVG text stays short and readable. */
  function r1(value) {
    return Math.round(value * 10) / 10;
  }

  /** "x1,y1 x2,y2 ..." for an SVG polyline or polygon. */
  function pointList(points) {
    return points.map((p) => r1(p[0]) + "," + r1(p[1])).join(" ");
  }

  /** "2026-09-13" -> "13 Sep". */
  function shortDate(isoDate) {
    if (!isoDate) return "";
    return Number(String(isoDate).slice(8, 10)) + " " + MONTHS[Number(String(isoDate).slice(5, 7)) - 1];
  }

  /** "2026-09-13" plus 87 days -> "2026-12-09". */
  function addDays(isoDate, days) {
    return DamDays.format.addDays(isoDate, days);
  }

  /** Whole tenths as the weekly text rounds them (js/text.js inTen). */
  function inTen(chance) {
    return DamDays.text && DamDays.text.inTen ? DamDays.text.inTen(chance)
      : Math.floor((Math.floor(chance * 1000 + 0.5) + 50) / 100);
  }

  /** A chance's colour token: the same bands as js/settings.js chanceBands. */
  function bandVar(chance) {
    if (chance === null || chance === undefined) return "var(--c-none)";
    const t = inTen(chance);
    return t === 0 ? "var(--c0)" : t <= 2 ? "var(--c1)" : t <= 4 ? "var(--c2)" : t <= 6 ? "var(--c3)" : "var(--c4)";
  }

  /** About how wide a 13 px label is (Atkinson Hyperlegible Next), for keeping labels apart. */
  function labelWidth(text, px) {
    return String(text).length * (px || 13) * 0.56;
  }

  /**
   * Keep only the axis labels that do not overlap, most important first.
   * items: [{ x, text, anchor, rank }] (rank 0 = keep first). Returns the kept items.
   */
  function spreadLabels(items, gap) {
    const kept = [];
    items.slice().sort((a, b) => a.rank - b.rank).forEach((item) => {
      const w = labelWidth(item.text);
      const left = item.anchor === "start" ? item.x : item.anchor === "end" ? item.x - w : item.x - w / 2;
      const box = [left - (gap || 6), left + w + (gap || 6)];
      if (kept.some((k) => box[0] < k.box[1] && k.box[0] < box[1])) return;
      kept.push(Object.assign({ box }, item));
    });
    return kept;
  }

  /** The curve's straight line at `days` after the look (it starts at no chance on the look day). */
  function lineAt(chance, horizons, days) {
    const xs = [0].concat(horizons);
    const ys = [0].concat(chance);
    if (days <= 0) return 0;
    for (let i = 1; i < xs.length; i++) {
      if (days <= xs[i]) {
        const t = (days - xs[i - 1]) / (xs[i] - xs[i - 1]);
        return ys[i - 1] + t * (ys[i] - ys[i - 1]);
      }
    }
    return ys[ys.length - 1];
  }

  // -------------------------------------------------------------------------
  // Ten dots: "3 in 10" drawn as ten circles, the first three filled
  // -------------------------------------------------------------------------
  /**
   * opts.r      dot radius (6 = the 12 px dots of the six-month rows)
   * opts.gap    space between dots (3)
   * opts.label  the accessible name ("1 in 10 by 12 Dec"); default the chance in words
   */
  function tenDots(chance, opts) {
    opts = opts || {};
    const r = opts.r || 6;
    const gap = opts.gap === undefined ? 3 : opts.gap;
    const filled = chance === null || chance === undefined ? 0 : Math.min(10, inTen(chance));
    const step = r * 2 + gap;
    const pad = 1.5;
    let dots = "";
    for (let i = 0; i < 10; i++) {
      const on = i < filled;
      dots += '<circle cx="' + r1(pad + r + i * step) + '" cy="' + r1(pad + r) + '" r="' + r + '" fill="' +
              (on ? bandVar(chance) : "none") + '" stroke="' + (on ? "var(--c-ring)" : "var(--line-strong)") +
              '" stroke-width="1.6"/>';
    }
    const w = r1(pad * 2 + r * 2 + 9 * step);
    const h = r1(pad * 2 + r * 2);
    const label = opts.label || (chance === null || chance === undefined ? "no forecast" : DamDays.format.chance(chance));
    return '<svg class="tendots" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h +
           '" role="img" aria-label="' + esc(label) + '" focusable="false">' + dots + "</svg>";
  }

  // -------------------------------------------------------------------------
  // The next six months, drawn at the container's width (dam sheet)
  // -------------------------------------------------------------------------
  /**
   * curve: { chance: [...], low: [...], high: [...] } for opts.horizons (days after the look)
   * opts.width        the container's width in px (the SVG is drawn 1:1, so labels stay 13 px)
   * opts.horizons     [30, 60, 90, 180]
   * opts.issuedOn     the satellite look the days count from ("2026-09-13")
   * opts.damdaysDays  the DamDays number from that look (87): a dashed line "DamDays: 9 Dec",
   *                   none when it is at or past the end of the chart
   * opts.sinceDays    days from the look to the text's date (19): a dotted line
   * opts.sinceLabel   that line's label ("Fri 2 Oct")
   * opts.headline     { days: 90, label: "1 in 10 by 12 Dec" }: the main forecast point, ringed and labelled
   * Every date (each point's and the look's) is written: one with no room on the date row goes on a row under it.
   */
  function sixMonths(curve, opts) {
    opts = opts || {};
    const W = Math.max(260, Math.round(opts.width || 320));
    let H = Math.round(Math.max(190, Math.min(240, W * 0.6)));
    // left: room for the widest axis label ("10 in 10", about 52 px at 13 px) right of the SVG's edge
    const box = { left: 64, right: W - 14, top: 40, bottom: H - 30 };
    const horizons = opts.horizons || [30, 60, 90, 180];
    const maxDays = horizons[horizons.length - 1];
    const x = (d) => box.left + (Math.max(0, Math.min(d, maxDays)) / maxDays) * (box.right - box.left);
    const y = (c) => box.bottom - Math.max(0, Math.min(c, 1)) * (box.bottom - box.top);
    const days = [0].concat(horizons);
    const mid = [0].concat(curve.chance);
    const low = [0].concat(curve.low || curve.chance);
    const high = [0].concat(curve.high || curve.chance);
    const parts = [];

    // The text's day and the DamDays day close together (a look under a week old): each label goes on the far side
    // of its own line, so neither line runs through the other's label; with no room for that, the text's label goes
    // up a row and the chart grows by that row.
    const dd = opts.damdaysDays;
    const hasSince = opts.sinceDays !== undefined && opts.sinceDays !== null && opts.sinceDays > 0 && opts.sinceDays < maxDays;
    const hasDd = Boolean(dd !== undefined && dd !== null && dd > 0 && dd < maxDays && opts.issuedOn);
    const ddText = hasDd ? "DamDays: " + shortDate(addDays(opts.issuedOn, dd)) : "";
    const sinceText = opts.sinceLabel || "";
    let markLayout = null;          // null (apart) | { sSide, dSide } (side by side) | "stack"
    if (hasSince && hasDd && Math.abs(x(opts.sinceDays) - x(dd)) < 24) {
      const sxx = x(opts.sinceDays), dxx = x(dd);
      const sinceLeft = sxx <= dxx;
      const room = (xx, text, side) => (side === "end" ? xx - 5 - labelWidth(text) >= 2 : xx + 5 + labelWidth(text) <= W - 2);
      const sSide = sinceLeft ? "end" : "start", dSide = sinceLeft ? "start" : "end";
      markLayout = room(sxx, sinceText, sSide) && room(dxx, ddText, dSide) ? { sSide, dSide } : "stack";
      if (markLayout === "stack") { box.top += 14; H += 14; box.bottom = H - 30; }
    }

    // Gridlines, labelled "N in 10" (a chance is never a percent).
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach((level) => {
      const yy = r1(y(level));
      parts.push('<line class="ch-grid" x1="' + box.left + '" x2="' + box.right + '" y1="' + yy + '" y2="' + yy + '"/>');
      parts.push('<text class="ch-ax" x="' + (box.left - 8) + '" y="' + r1(yy + 4.5) + '" text-anchor="end">' +
                 (level === 0 ? "0" : Math.round(level * 10) + " in 10") + "</text>");
    });

    // Dates along the bottom: each point's date, and the look's. A date that would sit under the DamDays line
    // moves to the side of it (its tick stays on the point), so one vertical line never carries two dates.
    // Kept first: the last point, the main (90-day) point, then the others; the look's date last. A date with
    // no room on the row (the look's too) is written on a second row under it, never dropped.
    const ddDays = opts.damdaysDays;
    const ddX = ddDays !== undefined && ddDays !== null && ddDays > 0 && ddDays < maxDays && opts.issuedOn ? x(ddDays) : null;
    const mainDays = opts.headline && opts.headline.days ? opts.headline.days : 90;
    // A moved date never reads as another point's (over that point's tick, or nearer it than its own): it tries
    // the other side of the DamDays line, else it stays centred on its own tick (the DamDays line stops at the
    // axis, so it never crosses a date; a date with no room goes down a row, still under its own tick).
    const readsAsOther = (i, text, at, anchor) => {
      const w = labelWidth(text);
      const l = anchor === "start" ? at : anchor === "end" ? at - w : at - w / 2;
      const mid = l + w / 2, own = Math.abs(mid - x(days[i]));
      // over another point's tick (or the look's, at the curve's start), or nearer to one than to its own
      return days.some((h, j) => j !== i && ((x(h) > l - 2 && x(h) < l + w + 2) || Math.abs(mid - x(h)) < own));
    };
    const ticks = days.map((d, i) => {
      const text = opts.issuedOn ? shortDate(addDays(opts.issuedOn, d)) : (d === 0 ? "look" : d + " days");
      let tx = x(d);
      // the look's date is centred on the curve's start (half of it under the "0" column), so it never runs
      // under the first point's tick; the last point's date always ends at its own tick, the chart's right edge
      let anchor = i === days.length - 1 ? "end" : "middle";
      if (ddX !== null && i > 0 && i < days.length - 1 && Math.abs(tx - ddX) < 28) {
        const own = x(d);
        const sides = [["start", Math.max(own - 4, ddX + 6)], ["end", Math.min(own + 4, ddX - 6)]];
        if (own < ddX) sides.reverse();
        const fits = sides.find(([a, at]) => !readsAsOther(i, text, at, a));
        if (fits) { anchor = fits[0]; tx = fits[1]; }
      }
      const rank = i === 0 ? 9 : i === days.length - 1 ? 0 : d === mainDays ? 1 : 1 + (days.length - 1 - i);
      return { x: tx, text, anchor, rank, point: i > 0, idx: i };
    });
    days.forEach((d, i) => {
      if (i === 0) return;
      const tx = r1(x(d));
      parts.push('<line class="ch-tick" x1="' + tx + '" x2="' + tx + '" y1="' + box.bottom + '" y2="' + (box.bottom + 5) + '"/>');
    });
    // every date the first row had no room for goes on the next free row, the look's too (points first in each row)
    const rows = [spreadLabels(ticks, 6)];
    let left = ticks.filter((t) => !rows[0].some((k) => k.idx === t.idx));
    while (left.length && rows.length < 4) {
      const row = spreadLabels(left, 6);
      rows.push(row);
      left = left.filter((t) => !row.some((k) => k.idx === t.idx));
    }
    H += 16 * (rows.length - 1);
    rows.forEach((row, n) => row.forEach((t) => {
      parts.push('<text class="ch-ax" x="' + r1(t.x) + '" y="' + (box.bottom + 20 + 16 * n) + '" text-anchor="' + t.anchor + '">' +
                 esc(t.text) + "</text>");
    }));

    // The wetter or drier season band, then the curve, then a dot on each date.
    const band = days.map((d, i) => [x(d), y(high[i])])
      .concat(days.slice().reverse().map((d, i) => [x(d), y(low[low.length - 1 - i])]));
    parts.push('<polygon class="ch-band" points="' + pointList(band) + '"/>');
    parts.push('<polyline class="ch-line" points="' + pointList(days.map((d, i) => [x(d), y(mid[i])])) + '"/>');
    // the dots on each date come last (below), so the DamDays marker never hides one
    const dotParts = horizons.map((d, i) => {
      const when = opts.issuedOn ? "by " + shortDate(addDays(opts.issuedOn, d)) : d + " days";
      const tip = when + ": " + DamDays.format.chance(curve.chance[i]) + " (wetter or drier season: " +
                  DamDays.format.chanceRange(low[i + 1], high[i + 1]) + ")";
      return '<circle class="ch-dot" cx="' + r1(x(d)) + '" cy="' + r1(y(curve.chance[i])) + '" r="4.5"><title>' +
             esc(tip) + "</title></circle>";
    });

    // A label on top, kept inside the chart.
    const topLabel = (xx, yy, text, cls) => {
      const w = labelWidth(text);
      const anchor = xx - w / 2 < 4 ? "start" : xx + w / 2 > W - 4 ? "end" : "middle";
      const at = anchor === "start" ? Math.max(4, xx - 6) : anchor === "end" ? Math.min(W - 4, xx + 6) : xx;
      return '<text class="' + cls + '" x="' + r1(at) + '" y="' + yy + '" text-anchor="' + anchor + '">' + esc(text) + "</text>";
    };

    // A label beside a line, on the side away from it: "end" ends 5 px left of x, "start" starts 5 px right.
    const sideLabel = (xx, yy, text, cls, side) => '<text class="' + cls + '" x="' + r1(side === "end" ? xx - 5 : xx + 5) + '" y="' + yy +
      '" text-anchor="' + side + '">' + esc(text) + "</text>";
    const sx = hasSince ? r1(x(opts.sinceDays)) : null;
    const dx = hasDd ? r1(x(dd)) : null;
    // The day of this week's text (or of the forecast): a dotted line.
    if (hasSince) {
      parts.push('<line class="ch-today" x1="' + sx + '" x2="' + sx + '" y1="' + (box.top - 8) + '" y2="' + box.bottom + '"/>');
      parts.push(markLayout && markLayout.sSide ? sideLabel(sx, box.top - 13, sinceText, "ch-mark-t", markLayout.sSide)
        : topLabel(sx, box.top - (markLayout === "stack" ? 41 : 13), sinceText, "ch-mark-t"));
    }
    // The DamDays day: a dashed line where the cautious count runs out, and the curve there. On a point (closer than
    // 10 px to one), a hollow ring round that point instead of a dot that would half hide it.
    let ddRing = "", ddOn = null;
    if (hasDd) {
      const v = lineAt(curve.chance, horizons, dd);
      parts.push('<line class="ch-dd" x1="' + dx + '" x2="' + dx + '" y1="' + (box.top - 22) + '" y2="' + box.bottom + '"/>');
      const onPoint = horizons.find((h) => Math.abs(x(h) - x(dd)) < 10);
      if (onPoint === undefined) parts.push('<circle class="ch-dd-dot" cx="' + dx + '" cy="' + r1(y(v)) + '" r="4"/>');
      else {
        ddOn = onPoint;
        ddRing = '<circle class="ch-dd-ring" cx="' + r1(x(onPoint)) + '" cy="' + r1(y(curve.chance[horizons.indexOf(onPoint)])) + '" r="8"/>';
      }
      parts.push(markLayout && markLayout.dSide ? sideLabel(dx, box.top - 27, ddText, "ch-mark-dd", markLayout.dSide)
        : topLabel(dx, box.top - 27, ddText, "ch-mark-dd"));
    }
    Array.prototype.push.apply(parts, dotParts);
    if (ddRing) parts.push(ddRing);
    // The main forecast (the chance by its date, as the card says it): its point ringed and labelled.
    const hl = opts.headline;
    const hi = hl ? horizons.indexOf(hl.days) : -1;
    if (hi >= 0 && hl.label) {
      const hx = x(hl.days), hy = y(curve.chance[hi]);
      parts.push('<circle class="ch-hl" cx="' + r1(hx) + '" cy="' + r1(hy) + '" r="' + (ddOn === hl.days ? 11.5 : 7.5) + '"/>');
      // Above the point (below it near the top), left of it (the curve rises to the right), else right, else centred;
      // never across the DamDays or the text's line. With no such room, the chance alone (its date is on the axis).
      const ly = hy - 14 < box.top + 6 ? hy + 25 : hy - 14;
      const lines = [dx, sx].filter((v) => v !== null);
      // does the curve run through the label (sampled along it)?
      const toDays = (xx) => ((xx - box.left) / (box.right - box.left)) * maxDays;
      const crossesCurve = (a, b) => [0, 0.25, 0.5, 0.75, 1].some((f) => {
        const cy = y(lineAt(curve.chance, horizons, toDays(a + (b - a) * f)));
        return cy > ly - 14 && cy < ly + 5;
      });
      const place = (text) => {
        const w = labelWidth(text);
        const cands = [[hx - 12 - w, "end", hx - 12], [hx + 12, "start", hx + 12], [hx - w / 2, "middle", hx]];
        return cands.map((c) => ({ left: c[0], right: c[0] + w, anchor: c[1], at: c[2], text }))
          .find((c) => c.left >= box.left - 6 && c.right <= W - 2 && !lines.some((lx) => lx > c.left - 3 && lx < c.right + 3) &&
            !crossesCurve(Math.max(c.left, box.left), Math.min(c.right, box.right))) || null;
      };
      const spot = place(hl.label) || (hl.short ? place(hl.short) : null) ||
        { at: hx, anchor: "middle", text: hl.short || hl.label };
      parts.push('<text class="ch-hl-t ch-halo" x="' + r1(spot.at) + '" y="' + r1(ly) + '" text-anchor="' + spot.anchor + '">' + esc(spot.text) + "</text>");
    }

    const from = opts.issuedOn ? "counted from the " + shortDate(opts.issuedOn) + " satellite look" : "counted from the last look";
    const summary = "The chance it drops below a third, " + from + ": " + horizons.map((d, i) =>
      (opts.issuedOn ? "by " + shortDate(addDays(opts.issuedOn, d)) : d + " days") + " " +
      DamDays.format.chance(curve.chance[i])).join(", ") +
      (dd && dd < maxDays && opts.issuedOn ? ". DamDays day: " + shortDate(addDays(opts.issuedOn, dd)) : "") + ".";
    return '<svg class="ch ch-six" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H +
           '" role="img" aria-label="' + esc(summary) + '" focusable="false">' + parts.join("") + "</svg>";
  }

  // -------------------------------------------------------------------------
  // How full since 1988, drawn at the container's width (dam sheet)
  // -------------------------------------------------------------------------
  /** Months between the first month of the history ("1988-01") and a date. */
  function monthsBetween(firstMonth, isoDate) {
    const [y0, m0] = firstMonth.split("-").map(Number);
    const [y1, m1] = isoDate.split("-").map(Number);
    return (y1 - y0) * 12 + (m1 - m0);
  }

  /** The middle value of a list of numbers (lower middle for an even count, as the mockup did). */
  function median(values) {
    const s = values.slice().sort((a, b) => a - b);
    return s[Math.floor(s.length / 2)];
  }

  /**
   * history: { level_pct: [...monthly, null = no clear look], events: [{date, kind}] }
   * opts.width       the container's width in px
   * opts.firstMonth  "1988-01"; opts.lastMonth "2026-09"
   * opts.threshold   30 ("below a third")
   * opts.step        months per point: 3 (three-month medians) or 1; default 3 under 480 px, else 1
   * opts.untilDate   hide everything after this date (a past forecast, before the reveal)
   * opts.markDate    a vertical line on this date (the day a past forecast was made)
   * opts.name        the dam's name, for the accessible summary
   */
  function historyChart(history, opts) {
    opts = opts || {};
    const W = Math.max(260, Math.round(opts.width || 320));
    const H = Math.round(Math.max(170, Math.min(230, W * 0.46)));
    const box = { left: 36, right: W - 8, top: 10, bottom: H - 42 };
    const values = history.level_pct || [];
    const n = values.length;
    const threshold = opts.threshold || 30;
    const lastIndex = opts.untilDate ? Math.min(n - 1, monthsBetween(opts.firstMonth, opts.untilDate)) : n - 1;
    const step = opts.step || (W < 480 ? 3 : 1);
    const TOP = 120;    // fuller than usual (above 100) is drawn up to 120, then clipped
    const x = (i) => box.left + (n > 1 ? i / (n - 1) : 0) * (box.right - box.left);
    const y = (p) => box.bottom - (Math.max(0, Math.min(p, TOP)) / TOP) * (box.bottom - box.top);
    const parts = [];

    // Below a third: the dry-ground band.
    parts.push('<rect class="hi-band" x="' + box.left + '" y="' + r1(y(threshold)) + '" width="' + r1(box.right - box.left) +
               '" height="' + r1(y(0) - y(threshold)) + '"/>');
    // Above 100: fuller than its usual full mark (after a wet spell the water spreads wider); labelled so it
    // does not read as a broken chart.
    parts.push('<rect class="hi-over" x="' + box.left + '" y="' + r1(y(TOP)) + '" width="' + r1(box.right - box.left) +
               '" height="' + r1(y(100) - y(TOP)) + '"/>');
    // Its label sits at the right; when a past forecast's day line (opts.markDate) would run through it, at the
    // left, so that line never cuts the words (and should neither side be free, it is drawn over the line).
    const OVER = "fuller than usual";
    const markX = opts.markDate ? x(monthsBetween(opts.firstMonth, opts.markDate)) : null;
    const overW = labelWidth(OVER);
    const under = (l) => markX !== null && markX > l - 4 && markX < l + overW + 4;
    const overAtLeft = under(box.right - 4 - overW) && !under(box.left + 4);
    const overCrossed = under(overAtLeft ? box.left + 4 : box.right - 4 - overW);
    const overLabel = '<text class="ch-ax ch-halo" x="' + r1(overAtLeft ? box.left + 4 : box.right - 4) + '" y="' + r1(y(TOP) + 12) +
      '" text-anchor="' + (overAtLeft ? "start" : "end") + '">' + OVER + "</text>";
    if (!overCrossed) parts.push(overLabel);
    [[0, "0"], [threshold, String(threshold)], [60, "60"], [100, "100"]].forEach(([p, label]) => {
      const yy = r1(y(p));
      parts.push('<line class="ch-grid" x1="' + box.left + '" x2="' + box.right + '" y1="' + yy + '" y2="' + yy + '"/>');
      parts.push('<text class="ch-ax" x="' + (box.left - 6) + '" y="' + r1(yy + 4.5) + '" text-anchor="end">' + label + "</text>");
    });

    // The line, from medians of `step` months; a stretch with no clear look breaks it. With more than one month
    // per point (phones), a pale band behind it runs from each stretch's lowest month to its highest, so a fall
    // below a third inside three months still shows as a dip, as the monthly line shows it on wider screens.
    let path = "";
    let pen = false;
    const runs = [];          // the band, in pieces broken at the gaps: [[x, lo, hi], ...]
    let run = null;
    for (let i = 0; i <= lastIndex; i += step) {
      const chunk = values.slice(i, Math.min(i + step, lastIndex + 1)).filter((v) => v !== null && v !== undefined);
      if (!chunk.length) { pen = false; run = null; continue; }
      const at = i + (Math.min(step, lastIndex + 1 - i) - 1) / 2;
      path += (pen ? "L" : "M") + r1(x(at)) + " " + r1(y(median(chunk)));
      pen = true;
      if (step > 1) {
        if (!run) { run = []; runs.push(run); }
        run.push([x(at), Math.min.apply(null, chunk), Math.max.apply(null, chunk)]);
      }
    }
    runs.forEach((r) => {
      const pts = r.length === 1 ? [[r[0][0] - 1.5, r[0][1], r[0][2]], [r[0][0] + 1.5, r[0][1], r[0][2]]] : r;
      const poly = pts.map((p) => [p[0], y(p[2])]).concat(pts.slice().reverse().map((p) => [p[0], y(p[1])]));
      parts.push('<polygon class="hi-range" points="' + pointList(poly) + '"/>');
    });
    if (path) parts.push('<path class="hi-line" d="' + path + '"/>');

    // Ticks under the chart: short = it fell below a third; tall = no water seen at a look.
    (history.events || []).forEach((event) => {
      const index = monthsBetween(opts.firstMonth, event.date);
      if (index < 0 || index > lastIndex) return;
      const none = event.kind === "dry";
      const label = (none ? "No water seen at a look, " : "Fell below a third, ") + DamDays.format.date(event.date);
      const xx = r1(x(index));
      parts.push('<line class="' + (none ? "hi-tick-none" : "hi-tick") + '" x1="' + xx + '" x2="' + xx + '" y1="' +
                 (box.bottom + 3) + '" y2="' + (box.bottom + (none ? 13 : 8)) + '"><title>' + esc(label) + "</title></line>");
    });

    // A past forecast: the day it was made.
    if (markX !== null) {
      const xx = r1(markX);
      parts.push('<line class="hi-mark" x1="' + xx + '" x2="' + xx + '" y1="' + box.top + '" y2="' + box.bottom + '"/>');
    }
    if (overCrossed) parts.push(overLabel);

    // Years along the bottom, every 10 years.
    const y0 = Number(opts.firstMonth.slice(0, 4));
    const y1 = Number((opts.lastMonth || opts.firstMonth).slice(0, 4));
    for (let yr = Math.ceil(y0 / 10) * 10; yr <= y1; yr += 10) {
      const i = (yr - y0) * 12 - (Number(opts.firstMonth.slice(5, 7)) - 1);
      if (i < 0 || i > n - 1) continue;
      parts.push('<text class="ch-ax" x="' + r1(x(i)) + '" y="' + (H - 6) + '" text-anchor="middle">' + yr + "</text>");
    }

    const facts = historyFacts(history, opts);
    // The latest value: the dam's own last clear look when given (as the caption and the card say it), else
    // the last month's middle reading, named as such.
    const latest = typeof opts.latestPct === "number" && opts.latestDate
      ? ", latest clear look " + DamDays.format.fullness(opts.latestPct) + " (" + DamDays.format.date(opts.latestDate) + ")"
      : facts.latest === null ? "" : ", middle reading for " + DamDays.format.month(facts.latestMonth) + ": " + DamDays.format.fullness(facts.latest);
    const summary = "How full " + (opts.name || "this dam") + " has been since " + y0 + latest +
      ". It fell below a third " + facts.below + (facts.below === 1 ? " time" : " times") + "; no water was seen at " +
      facts.noWater + (facts.noWater === 1 ? " look" : " looks") + ".";
    return '<svg class="ch ch-hist" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H +
           '" role="img" aria-label="' + esc(summary) + '" focusable="false">' + parts.join("") + "</svg>";
  }

  /**
   * The numbers for the sentence under the history chart, up to opts.untilDate:
   * { below, noWater, latest, latestMonth, firstYear } (counts of events; the last clear month's value).
   */
  function historyFacts(history, opts) {
    opts = opts || {};
    const values = history.level_pct || [];
    const lastIndex = opts.untilDate ? Math.min(values.length - 1, monthsBetween(opts.firstMonth, opts.untilDate)) : values.length - 1;
    let latest = null;
    let latestIndex = -1;
    for (let i = lastIndex; i >= 0; i--) {
      if (values[i] !== null && values[i] !== undefined) { latest = values[i]; latestIndex = i; break; }
    }
    const shown = (history.events || []).filter((e) => {
      const i = monthsBetween(opts.firstMonth, e.date);
      return i >= 0 && i <= lastIndex;
    });
    let latestMonth = null;
    if (latestIndex >= 0) {
      const y0 = Number(opts.firstMonth.slice(0, 4));
      const m0 = Number(opts.firstMonth.slice(5, 7)) - 1 + latestIndex;
      latestMonth = (y0 + Math.floor(m0 / 12)) + "-" + String((m0 % 12) + 1).padStart(2, "0");
    }
    return {
      below: shown.filter((e) => e.kind !== "dry").length,
      noWater: shown.filter((e) => e.kind === "dry").length,
      latest, latestMonth,
      firstYear: Number(opts.firstMonth.slice(0, 4)),
    };
  }

  // -------------------------------------------------------------------------
  // Runway curve (the old map views' dam card)
  // -------------------------------------------------------------------------
  /**
   * curve: { horizons: [30,60,90,180], chance: [...], low: [...], high: [...] }
   * headline: { days: 90, chance: 0.58, label: "6 in 10 by 11 Dec 2026" }
   * marks (optional, research/checks/DEMO_CHECKS.md item 8):
   *   { issuedOn: "2026-09-13", damdaysDays: 87, sinceDays: 19, sinceLabel: "Fri 2 Oct" }
   *   writes the dates under the chart, a dashed line "DamDays: 9 Dec" (none when it is at or past
   *   the end of the chart) and a short tick on the day of the text.
   * Days are counted from the forecast's satellite look ("last look").
   */
  function runwayCurve(curve, headline, marks) {
    marks = marks || {};
    const box = { left: 62, right: 328, top: 34, bottom: 176 };     // left: room for "10 in 10"
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

    // Labels along the bottom: dates when the look is known, else days (kept apart).
    const ticks = days.map((d, i) => ({
      x: x(d),
      text: marks.issuedOn ? shortDate(addDays(marks.issuedOn, d)) : d === 0 ? "last look" : d === maxDays ? d + " days" : String(d),
      anchor: i === 0 ? "start" : i === days.length - 1 ? "end" : "middle",
      rank: i === 0 ? 0 : i === days.length - 1 ? 1 : 10 - i,
    }));
    spreadLabels(ticks, 4).forEach((t) => {
      parts.push('<text x="' + r1(t.x) + '" y="' + (box.bottom + 18) + '" text-anchor="' + t.anchor +
                 '" class="chart-axis">' + esc(t.text) + "</text>");
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
      const when = marks.issuedOn ? "by " + shortDate(addDays(marks.issuedOn, d)) : d + " days";
      const tip = when + ": " + DamDays.format.chance(curve.chance[i]) +
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

    // The day of the text: a short tick on the axis, labelled.
    if (marks.sinceDays !== undefined && marks.sinceDays !== null && marks.sinceDays > 0 && marks.sinceDays < maxDays) {
      const sx = r1(x(marks.sinceDays));
      parts.push('<line x1="' + sx + '" x2="' + sx + '" y1="' + (box.bottom - 8) + '" y2="' + (box.bottom + 4) +
                 '" stroke="#1d1c1a" stroke-width="2"/>');
      parts.push('<text x="' + sx + '" y="' + (box.top - 6) + '" text-anchor="' + (sx < 90 ? "start" : "middle") +
                 '" class="chart-axis">' + esc(marks.sinceLabel || "today") + "</text>");
      parts.push('<line x1="' + sx + '" x2="' + sx + '" y1="' + (box.top - 2) + '" y2="' + (box.bottom - 8) +
                 '" stroke="#6b6963" stroke-width="1" stroke-dasharray="2 3"/>');
    }
    // The DamDays day: a dashed line where the cautious count runs out.
    const dd = marks.damdaysDays;
    if (marks.issuedOn && dd !== undefined && dd !== null && dd > 0 && dd < maxDays) {
      const dx = r1(x(dd));
      parts.push('<line x1="' + dx + '" x2="' + dx + '" y1="' + (box.top - 16) + '" y2="' + box.bottom +
                 '" stroke="#1d1c1a" stroke-width="1.5" stroke-dasharray="5 4"/>');
      parts.push('<text x="' + dx + '" y="' + (box.top - 20) + '" text-anchor="' + (dx > 260 ? "end" : "middle") +
                 '" class="chart-label">' + esc("DamDays: " + shortDate(addDays(marks.issuedOn, dd))) + "</text>");
    }

    const summary = "Chance of falling below a third, counted from the last look: " + curve.horizons.map((d, i) =>
      (marks.issuedOn ? "by " + shortDate(addDays(marks.issuedOn, d)) : d + " days") + " " +
      DamDays.format.chance(curve.chance[i])).join(", ");
    return '<svg class="chart chart-runway" viewBox="0 0 340 204" role="img" aria-label="' +
           esc(summary) + '">' + parts.join("") + "</svg>";
  }

  // -------------------------------------------------------------------------
  // Water history sparkline (the old map views' dam card)
  // -------------------------------------------------------------------------
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

    // Past events as ticks under the chart: short orange = below a third, tall black = no water seen.
    (history.events || []).forEach((event) => {
      const index = monthsBetween(options.firstMonth, event.date);
      if (index > lastIndex) return;
      const none = event.kind === "dry";
      const height = none ? 9 : 5;
      const color = none ? "#111111" : LINE_COLOR;
      const label = (none ? "No water seen at a look, " : "Fell below a third, ") + DamDays.format.date(event.date);
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
      : "How full since " + firstYear + ". Lowest " + DamDays.format.fullness(Math.min(...known)) +
        ", latest " + DamDays.format.fullness(known[known.length - 1]) + ".";
    return '<svg class="chart chart-history" viewBox="0 0 340 100" role="img" aria-label="' +
           esc(summary) + '">' + parts.join("") + "</svg>";
  }

  return { runwayCurve, waterHistory, tenDots, sixMonths, history: historyChart, historyFacts, lineAt, bandVar };
})();
