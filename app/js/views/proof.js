/* views/proof.js
 * Proof: what accuracy looks like, for judges who do not read "AUC" or "Brier skill".
 *
 * Three hand-drawn SVG charts (no chart library), all from proof.json, which
 * scripts/17_proof_data.py builds from the frozen model's test forecasts and their answers
 * (the test years were scored once by scripts/15; the totals in proof.json equal its results):
 *   1. What we said vs what happened: the test forecasts grouped by the chance they gave
 *      ("3 in 10"), against how often the dam really fell below a third within 90 days.
 *   2. It held up year after year: skill per July-June year 2016-17 to 2025-26 (drier years
 *      shaded), and how often "at least N days" held each year.
 *   3. Dam by dam: one farm's dams in 2018-19, water level and every forecast.
 * Every sentence with a number (the takeaways, the summaries) is written by scripts/17 from the
 * numbers, never typed here. Each chart has a "Show the numbers" table, so a tooltip never
 * gates a value.
 *
 * The unseen exam: the sealed-region panel of scoreboard.json. Until the opening it is a
 * placeholder ("Unseen exam: opens Sat 3 Oct 17:30 AEST"); once scripts/21_publish_sealed.py
 * fills the panel, this view shows it with the About page's own panelHtml (one wording).
 *
 * Wording: "%" only ever means how full a dam is; a chance is "N in 10"; how often something
 * happened is "N in 1,000".
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.views.proof = (function () {
  "use strict";

  const esc = (text) => DamDays.format.escapeHtml(text);
  const fmtDate = (iso) => DamDays.format.date(iso);
  const inTen = (chance) => DamDays.text.inTen(chance);
  const chanceWords = (chance) => DamDays.text.chanceText(chance);

  // One colour per job, the app's own: orange-brown = a chance (as on the maps), blue = how well
  // it did, water blue = the water level. Text stays in ink. Checked for colour-blind safety
  // (dataviz validator: orange-brown against blue, worst protan separation dE 23.9); every
  // difference that matters is also a shape (filled / open dot) or a label.
  const C = {
    chance: "#bb561a", skill: "#1c5cab", water: DamDays.settings.waterLine, ink: "#1d1c1a",
    inkSoft: "#4d4b47", muted: "#6b6963", grid: "#e1e0d9", stem: "#c9c6bd", unknown: "#b9b6ae",
    drier: "#efebe2", target: "#e3ebf6", after: "#f3f2ee", surface: "#ffffff",
  };

  const REGION_SHORT = { nsw_cw: "NSW", wvic_sesa: "Vic-SA" };
  let proof = null;
  let selectedDam = null;

  // ---- Small SVG helpers ------------------------------------------------------
  const r1 = (v) => Math.round(v * 10) / 10;
  function line(x1, y1, x2, y2, stroke, width) {
    return '<line x1="' + r1(x1) + '" y1="' + r1(y1) + '" x2="' + r1(x2) + '" y2="' + r1(y2) + '" stroke="' +
           stroke + '" stroke-width="' + (width || 1) + '"/>';
  }
  function label(x, y, text, cls, anchor, extra) {
    return '<text x="' + r1(x) + '" y="' + r1(y) + '" class="' + cls + '"' +
           (anchor ? ' text-anchor="' + anchor + '"' : "") + (extra || "") + ">" + esc(text) + "</text>";
  }
  function svg(cls, width, height, summary, parts) {
    return '<svg class="chart proof-chart ' + cls + '" viewBox="0 0 ' + width + " " + height +
           '" role="img" aria-label="' + esc(summary) + '">' + parts.join("") + "</svg>";
  }
  /** A bar with a 4 px rounded top, square at the baseline. */
  function bar(x, top, width, bottom, fill) {
    const r = Math.min(4, (bottom - top) / 2, width / 2);
    return '<path d="M' + r1(x) + "," + r1(bottom) + "V" + r1(top + r) + "Q" + r1(x) + "," + r1(top) + " " +
           r1(x + r) + "," + r1(top) + "H" + r1(x + width - r) + "Q" + r1(x + width) + "," + r1(top) + " " +
           r1(x + width) + "," + r1(top + r) + "V" + r1(bottom) + 'Z" fill="' + fill + '"/>';
  }
  /** An invisible, larger hover target carrying the tooltip. */
  function hitCircle(cx, cy, r, tip) {
    return '<circle cx="' + r1(cx) + '" cy="' + r1(cy) + '" r="' + r1(r) +
           '" fill="transparent" class="proof-hit"><title>' + esc(tip) + "</title></circle>";
  }
  function hitRect(x, y, w, h, tip) {
    return '<rect x="' + r1(x) + '" y="' + r1(y) + '" width="' + r1(w) + '" height="' + r1(h) +
           '" fill="transparent" class="proof-hit"><title>' + esc(tip) + "</title></rect>";
  }
  const thousand = (share) => Math.round(share * 1000);
  const count = (n) => n.toLocaleString("en-AU");
  const signed = (v, digits) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(digits);

  // ---- The unseen exam ----------------------------------------------------------
  function examHtml(data) {
    const exam = proof ? proof.unseen_exam : null;
    const panels = (data.scoreboard && data.scoreboard.panels) || [];
    const sealed = panels.find((p) => p.key === (exam ? exam.panel_key : "sealed")) || null;
    const scored = Boolean(sealed && sealed.status === "scored");
    const heading = exam ? (scored ? exam.heading_scored : exam.heading_pending)
                         : "Unseen exam: opens Sat 3 Oct 17:30 AEST";
    if (scored) {
      return '<section class="proof-exam-card proof-exam-done" aria-labelledby="proof-exam-title">' +
             '<p class="proof-kicker">The clean test</p><h2 id="proof-exam-title">' + esc(heading) + "</h2>" +
             DamDays.views.about.panelHtml(sealed) + "</section>";
    }
    const expected = exam && exam.expect ? '<p class="panel-small">' + esc(exam.expect) +
      ' Every expectation is listed on <a href="#about">About</a>.</p>' : "";
    return '<section class="proof-exam-card proof-exam-pending" aria-labelledby="proof-exam-title">' +
           '<p class="panel-status">Not opened yet</p><p class="proof-kicker">The clean test</p>' +
           '<h2 id="proof-exam-title">' + esc(heading) + "</h2>" +
           "<p>" + esc(exam ? exam.text : (sealed ? sealed.text : "")) + "</p>" +
           (sealed ? '<p class="panel-label">' + esc(sealed.label || "") + "</p>" : "") + expected + "</section>";
  }

  // ---- 1. What we said vs what happened ------------------------------------------
  function calibrationSvg(cal) {
    const W = 620, H = 470;
    const box = { left: 92, right: 600, top: 20, bottom: 372 };
    const x0 = -0.09, x1 = 1.02;   // a little room either side of "under 1" and "10 in 10"
    const x = (v) => box.left + ((v - x0) / (x1 - x0)) * (box.right - box.left);
    const y = (v) => box.bottom - v * (box.bottom - box.top);
    const bins = cal.bins.filter((b) => b.plotted);
    const most = Math.max(...bins.map((b) => b.forecasts));
    const parts = [];
    // Gridlines and "N in 10" labels up the side.
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach((v) => {
      parts.push(line(box.left, y(v), box.right, y(v), C.grid, 1));
      parts.push(label(box.left - 8, y(v) + 4, v === 0 ? "none" : Math.round(v * 10) + " in 10", "proof-axis", "end"));
    });
    // The diagonal: what happened = what we said. Its label runs along it, just below, in the empty
    // lower-right half (clear of the dots, which sit on the line).
    parts.push(line(x(0), y(0), x(1), y(1), C.muted, 1.5));
    const angle = Math.atan2(y(1) - y(0), x(1) - x(0)) * 180 / Math.PI;
    const at = 0.66;
    parts.push(label(x(at), y(at), "on this line, what happened = what we said", "proof-axis", "middle",
                     ' dy="27" transform="rotate(' + r1(angle) + " " + r1(x(at)) + " " + r1(y(at)) + ')"'));
    // Each group: a range line, then a dot sized by its number of forecasts.
    bins.forEach((b) => {
      const cx = x(b.in_ten / 10);
      if (b.share_fell_ci) parts.push(line(cx, y(b.share_fell_ci[0]), cx, y(b.share_fell_ci[1]), C.chance, 2));
      const r = 5 + 10 * Math.sqrt(b.forecasts / most);
      parts.push('<circle cx="' + r1(cx) + '" cy="' + r1(y(b.share_fell)) + '" r="' + r1(r) + '" fill="' + C.chance +
                 '" stroke="' + C.surface + '" stroke-width="2"/>');
      const tip = "We said " + b.said + " (" + count(b.forecasts) + " forecasts): " + count(b.fell) +
                  " fell below a third within 90 days, " + thousand(b.share_fell) + " in 1,000 (about " +
                  chanceWords(b.happened_in_ten / 10) + ")";
      parts.push(hitCircle(cx, y(b.share_fell), Math.max(r + 4, 14), tip));
      // Under the axis: the group's name, then how many forecasts it holds.
      parts.push(label(cx, box.bottom + 20, b.in_ten === 0 ? "under 1" : String(b.in_ten), "proof-axis-strong", "middle"));
      parts.push(label(cx, box.bottom + 37, count(b.forecasts), "proof-axis", "middle"));
    });
    parts.push(label(box.left - 8, box.bottom + 20, "said", "proof-axis", "end"));
    parts.push(label(box.left - 8, box.bottom + 37, "forecasts", "proof-axis", "end"));
    parts.push(label((box.left + box.right) / 2, box.bottom + 62, "What we said: the chance it falls below a third within 90 days (in 10)",
                     "proof-axis-title", "middle"));
    const midY = (box.top + box.bottom) / 2;
    parts.push(label(22, midY, "What happened: how often it fell (in 10)", "proof-axis-title", "middle",
                     ' transform="rotate(-90 22 ' + r1(midY) + ')"'));
    const summary = "What we said against what happened, in " + bins.length + " groups: " + bins.map((b) =>
      "said " + b.said + ", happened " + thousand(b.share_fell) + " in 1,000").join("; ");
    return svg("proof-calibration", W, H, summary, parts);
  }

  function calibrationTable(cal) {
    const rows = cal.bins.map((b) =>
      "<tr><th scope=\"row\">" + esc(b.said) + "</th><td>" + count(b.forecasts) + "</td><td>" + count(b.fell) +
      "</td><td>" + thousand(b.share_fell) + " in 1,000 (about " + esc(chanceWords(b.happened_in_ten / 10)) +
      ")</td><td>" + thousand(b.mean_chance) + " in 1,000</td><td>" +
      (b.share_fell_ci ? thousand(b.share_fell_ci[0]) + " to " + thousand(b.share_fell_ci[1]) : "-") +
      (b.plotted ? "" : " (not drawn)") + "</td></tr>");
    return '<details class="proof-numbers"><summary>Show the numbers</summary><div class="proof-table-scroll"><table>' +
           "<thead><tr><th scope=\"col\">We said</th><th scope=\"col\">Forecasts</th>" +
           "<th scope=\"col\">Fell below a third within 90 days</th><th scope=\"col\">What happened</th>" +
           "<th scope=\"col\">Average chance given</th><th scope=\"col\">Range, re-drawing the dams</th></tr></thead>" +
           "<tbody>" + rows.join("") + "</tbody></table></div></details>";
  }

  function calibrationFigure() {
    const cal = proof.calibration;
    return '<figure class="proof-figure" aria-labelledby="proof-1-title">' +
           '<p class="proof-kicker">1 · ' + esc(cal.title) + "</p>" +
           '<h2 id="proof-1-title" class="proof-takeaway">' + esc(cal.takeaway) + "</h2>" +
           '<p class="proof-detail">' + esc(cal.detail) + "</p>" +
           '<div class="proof-chart-wrap proof-chart-square">' + calibrationSvg(cal) + "</div>" +
           '<figcaption class="proof-note"><p>' + esc(cal.how_to_read) + "</p><p>" + esc(cal.lean) + "</p>" +
           (cal.not_plotted ? "<p>" + esc(cal.not_plotted) + "</p>" : "") + "</figcaption>" +
           calibrationTable(cal) + "</figure>";
  }

  // ---- 2. Year after year ------------------------------------------------------
  /** x positions shared by the two year charts, so the shaded drier years line up. */
  function yearScale(years, box) {
    const band = (box.right - box.left) / years.length;
    return { band: band, center: (i) => box.left + band * (i + 0.5) };
  }

  function drierShading(byYear, years, scale, top, bottom, withLabels) {
    const parts = [];
    byYear.drier_runs.forEach((run) => {
      const first = years.findIndex((y) => y.year === run.first);
      const last = years.findIndex((y) => y.year === run.last);
      if (first < 0 || last < 0) return;
      const x0 = scale.center(first) - scale.band / 2 + 1;
      const x1 = scale.center(last) + scale.band / 2 - 1;
      parts.push('<rect x="' + r1(x0) + '" y="' + r1(top) + '" width="' + r1(x1 - x0) + '" height="' +
                 r1(bottom - top) + '" fill="' + C.drier + '"/>');
      if (withLabels) parts.push(label((x0 + x1) / 2, top - 7, "drier years " + run.label, "proof-axis-strong", "middle"));
    });
    return parts;
  }

  function skillSvg(byYear) {
    const W = 700, H = 318;
    const box = { left: 96, right: 610, top: 50, bottom: 268 };
    const years = byYear.years;
    const scale = yearScale(years, box);
    const maxV = 0.35;
    const y = (v) => box.bottom - (Math.max(0, Math.min(v, maxV)) / maxV) * (box.bottom - box.top);
    const parts = drierShading(byYear, years, scale, box.top, box.bottom, true);
    [[0, "none"], [0.1, "a tenth"], [0.2, "a fifth"], [0.3, "three tenths"]].forEach(([v, words]) => {
      parts.push(line(box.left, y(v), box.right, y(v), C.grid, 1));
      parts.push(label(box.left - 8, y(v) + 4, words, "proof-axis", "end"));
    });
    const barWidth = Math.min(24, scale.band * 0.5);
    years.forEach((yr, i) => {
      const cx = scale.center(i);
      parts.push(bar(cx - barWidth / 2, y(yr.skill), barWidth, box.bottom, C.skill));
      if (yr.skill_ci) {
        parts.push(line(cx, y(yr.skill_ci[0]), cx, y(yr.skill_ci[1]), C.inkSoft, 1.5));
        parts.push(line(cx - 4, y(yr.skill_ci[1]), cx + 4, y(yr.skill_ci[1]), C.inkSoft, 1.5));
        parts.push(line(cx - 4, y(yr.skill_ci[0]), cx + 4, y(yr.skill_ci[0]), C.inkSoft, 1.5));
      }
      const tip = yr.words + (yr.drier ? " (a drier year)" : "") + ": " + yr.skill_words +
                  " less error than guessing the usual rate (skill " + signed(yr.skill, 3) +
                  (yr.skill_ci ? ", range " + signed(yr.skill_ci[0], 3) + " to " + signed(yr.skill_ci[1], 3) : "") +
                  "); " + count(yr.forecasts) + " forecasts, " + count(yr.fell) + " fell below a third";
      parts.push(hitRect(cx - scale.band / 2, box.top, scale.band, box.bottom - box.top, tip));
      parts.push(label(cx, box.bottom + 18, yr.label, "proof-axis", "middle"));
    });
    // All ten years together, as a reference line with its label in the right margin.
    const all = byYear.all_years;
    parts.push(line(box.left, y(all.skill), box.right, y(all.skill), C.ink, 1));
    parts.push(label(box.right + 8, y(all.skill) - 2, "all 10 years:", "proof-axis", "start"));
    parts.push(label(box.right + 8, y(all.skill) + 12, all.skill_words, "proof-axis-strong", "start"));
    parts.push(label(box.left, 16, "Less error than guessing the usual rate, each July-June year", "proof-axis-title", "start"));
    const summary = "Less error than guessing the usual rate, each July-June year: " + years.map((yr) =>
      yr.label + " " + yr.skill_words + (yr.drier ? " (drier)" : "")).join("; ");
    return svg("proof-years", W, H, summary, parts);
  }

  function floorSvg(byYear) {
    const W = 700, H = 230;
    const box = { left: 96, right: 610, top: 30, bottom: 180 };
    const years = byYear.years;
    const scale = yearScale(years, box);
    const lo = 850, hi = 950;
    const y = (v) => box.bottom - ((Math.max(lo, Math.min(v, hi)) - lo) / (hi - lo)) * (box.bottom - box.top);
    const target = byYear.floor_target * 1000;
    const tol = byYear.floor_tolerance * 1000;
    const parts = drierShading(byYear, years, scale, box.top, box.bottom, false);
    parts.push('<rect x="' + box.left + '" y="' + r1(y(target + tol)) + '" width="' + (box.right - box.left) +
               '" height="' + r1(y(target - tol) - y(target + tol)) + '" fill="' + C.target + '" fill-opacity="0.85"/>');
    [860, 880, 900, 920, 940].forEach((v) => {
      parts.push(line(box.left, y(v), box.right, y(v), C.grid, 1));
      parts.push(label(box.left - 8, y(v) + 4, String(v), "proof-axis", "end"));
    });
    parts.push(line(box.left, y(target), box.right, y(target), C.ink, 1));
    parts.push(label(box.right + 8, y(target) - 2, "target: 9 in 10", "proof-axis", "start"));
    parts.push(label(box.right + 8, y(target) + 12, "on target:", "proof-axis", "start"));
    parts.push(label(box.right + 8, y(target) + 26, (target - tol) + " to " + (target + tol), "proof-axis", "start"));
    const held = years.map((yr) => yr.floor.held_in_1000);
    const lowest = Math.min(...held), highest = Math.max(...held);
    years.forEach((yr, i) => {
      const cx = scale.center(i), v = yr.floor.held_in_1000, cy = y(v);
      parts.push('<circle cx="' + r1(cx) + '" cy="' + r1(cy) + '" r="5.5" fill="' + C.skill + '" stroke="' +
                 C.surface + '" stroke-width="2"/>');
      if (v === lowest) parts.push(label(cx, cy + 20, v + " (lowest)", "proof-axis-strong", "middle"));
      else if (v === highest) parts.push(label(cx, cy - 11, v + " (highest)", "proof-axis-strong", "middle"));
      const tip = yr.words + ": \"at least N days\" held " + v + " times in 1,000 (" + count(yr.floor.judged) +
                  " judged forecasts)";
      parts.push(hitRect(cx - scale.band / 2, box.top, scale.band, box.bottom - box.top, tip));
      parts.push(label(cx, box.bottom + 18, yr.label, "proof-axis", "middle"));
    });
    parts.push(label(box.left, 14, "How often \"at least N days\" held, in 1,000", "proof-axis-title", "start"));
    const summary = "How often the days-left promise held, in 1,000, each July-June year: " +
      years.map((yr) => yr.label + " " + yr.floor.held_in_1000).join("; ");
    return svg("proof-floor", W, H, summary, parts);
  }

  function yearsTable(byYear) {
    const rows = byYear.years.map((yr) =>
      "<tr><th scope=\"row\">" + esc(yr.label) + (yr.drier ? " (drier)" : "") + "</th><td>" + count(yr.forecasts) +
      "</td><td>" + count(yr.fell) + "</td><td>" + esc(yr.skill_words) + " (" + signed(yr.skill, 3) +
      (yr.skill_ci ? "; " + signed(yr.skill_ci[0], 3) + " to " + signed(yr.skill_ci[1], 3) : "") + ")</td><td>" +
      yr.rain_vs_usual_mean.toFixed(2) + " of usual (" + Object.keys(yr.rain_vs_usual).map((r) =>
        (REGION_SHORT[r] || r) + " " + yr.rain_vs_usual[r].toFixed(2)).join(", ") + ")</td><td>" + yr.floor.held_in_1000 + " in 1,000 (" +
      count(yr.floor.judged) + ")</td></tr>");
    const all = byYear.all_years;
    rows.push("<tr><th scope=\"row\">All ten years</th><td>" + count(proof.test.forecasts) + "</td><td>" +
              count(proof.test.fell) + "</td><td>" + esc(all.skill_words) + " (" + signed(all.skill, 3) + "; " +
              signed(all.skill_ci[0], 3) + " to " + signed(all.skill_ci[1], 3) + ")</td><td>-</td><td>" +
              thousand(all.floor_held) + " in 1,000 (" + count(all.floor_judged) + ")</td></tr>");
    return '<details class="proof-numbers"><summary>Show the numbers</summary><div class="proof-table-scroll"><table>' +
           "<thead><tr><th scope=\"col\">July-June year</th><th scope=\"col\">Forecasts (Oct-Mar)</th>" +
           "<th scope=\"col\">Fell below a third</th><th scope=\"col\">Less error than the usual rate (skill; range)</th>" +
           "<th scope=\"col\">Rain, both regions</th><th scope=\"col\">\"At least N days\" held (judged)</th></tr></thead>" +
           "<tbody>" + rows.join("") + "</tbody></table></div></details>";
  }

  function yearsFigure() {
    const byYear = proof.by_year;
    return '<figure class="proof-figure" aria-labelledby="proof-2-title">' +
           '<p class="proof-kicker">2 · ' + esc(byYear.title) + "</p>" +
           '<h2 id="proof-2-title" class="proof-takeaway">' + esc(byYear.takeaway) + "</h2>" +
           '<div class="proof-chart-wrap">' + skillSvg(byYear) + "</div>" +
           '<figcaption class="proof-note"><p>' + esc(byYear.skill_note) + "</p><p>" + esc(byYear.drier_rule) +
           "</p></figcaption>" +
           '<h3 class="proof-subtakeaway">' + esc(byYear.floor_takeaway) + "</h3>" +
           '<p class="proof-detail">' + esc(byYear.floor_detail) + "</p>" +
           '<div class="proof-chart-wrap">' + floorSvg(byYear) + "</div>" +
           '<figcaption class="proof-note"><p>' + esc(byYear.floor_note) + "</p><p>" + esc(byYear.refit_note) +
           "</p></figcaption>" + yearsTable(byYear) + "</figure>";
  }

  // ---- 3. Dam by dam -------------------------------------------------------------
  function dayNumber(iso) {
    return Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86400000;
  }

  function timeAxis(part, x, from, to, bottom, parts) {
    const start = new Date(from + "T00:00:00Z");
    const end = new Date(to + "T00:00:00Z");
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    for (let d = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1)); d <= end;
         d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 3, 1))) {
      const iso = d.toISOString().slice(0, 10);
      if (iso < from) continue;
      const px = x(iso);
      parts.push(line(px, bottom, px, bottom + 4, C.muted, 1));
      if (part === "labels") {
        const words = months[d.getUTCMonth()] + (d.getUTCMonth() === 0 || iso === from ? " " + d.getUTCFullYear() : "");
        parts.push(label(px, bottom + 18, words, "proof-axis", "middle"));
      }
    }
  }

  function levelSvg(dam, part) {
    const W = 700, H = 210;
    const box = { left: 72, right: 680, top: 26, bottom: 176 };
    const from = part.season.forecasts_from, to = part.season.show_to;
    const d0 = dayNumber(from), d1 = dayNumber(to);
    const x = (iso) => box.left + ((dayNumber(iso) - d0) / (d1 - d0)) * (box.right - box.left);
    const maxPct = 140;
    const y = (pct) => box.bottom - (Math.min(pct, maxPct) / maxPct) * (box.bottom - box.top);
    const parts = [];
    // The 90 days after the season's last forecast: shown so its answer can be seen.
    const seasonEnd = x(part.season.forecasts_to);
    parts.push('<rect x="' + r1(seasonEnd) + '" y="' + box.top + '" width="' + r1(box.right - seasonEnd) + '" height="' +
               (box.bottom - box.top) + '" fill="' + C.after + '"/>');
    parts.push(label((seasonEnd + box.right) / 2, box.top - 8, "after the last forecast", "proof-axis", "middle"));
    [[0, "dry"], [part.threshold_pct, "a third"], [100, "full"]].forEach(([v, words]) => {
      parts.push(line(box.left, y(v), box.right, y(v), v === part.threshold_pct ? C.inkSoft : C.grid,
                      v === part.threshold_pct ? 1.5 : 1));
      parts.push(label(box.left - 8, y(v) + 4, words, v === part.threshold_pct ? "proof-axis-strong" : "proof-axis", "end"));
    });
    // The water level at each clear look: a pale wash, the line, and a small dot per look.
    const pts = dam.looks.filter((l) => l[1] !== null).map((l) => [x(l[0]), y(l[1]), l]);
    if (pts.length) {
      const area = [[pts[0][0], box.bottom]].concat(pts.map((p) => [p[0], p[1]]), [[pts[pts.length - 1][0], box.bottom]]);
      parts.push('<polygon points="' + area.map((p) => r1(p[0]) + "," + r1(p[1])).join(" ") + '" fill="' + C.water +
                 '" fill-opacity="0.1"/>');
      parts.push('<polyline points="' + pts.map((p) => r1(p[0]) + "," + r1(p[1])).join(" ") + '" fill="none" stroke="' +
                 C.water + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>');
      pts.forEach((p) => {
        parts.push('<circle cx="' + r1(p[0]) + '" cy="' + r1(p[1]) + '" r="2.5" fill="' + C.water + '"/>');
        parts.push(hitCircle(p[0], p[1], 7, fmtDate(p[2][0]) + ": ~" + p[2][1] + "% full"));
      });
    }
    // The days it fell below a third.
    dam.falls.forEach((day, i) => {
      const px = x(day);
      parts.push(line(px, box.top, px, box.bottom, C.ink, 1.5));
      const right = px > (box.left + box.right) / 2;
      parts.push(label(px + (right ? -6 : 6), box.top + 14 + 16 * (i % 2), "fell below a third, " + fmtDate(day),
                       "proof-axis-strong", right ? "end" : "start"));
    });
    timeAxis("ticks", x, from, to, box.bottom, parts);
    parts.push(label(box.left, 12, "Water level at each clear satellite look (% of full)", "proof-axis-title", "start"));
    const summary = dam.name + " water level, " + fmtDate(from) + " to " + fmtDate(to) + ". " +
      (dam.falls.length ? "Fell below a third on " + dam.falls.map(fmtDate).join(" and ") + "."
                        : "Did not fall below a third.");
    return svg("proof-level", W, H, summary, parts);
  }

  function forecastSvg(dam, part) {
    const W = 700, H = 190;
    const box = { left: 72, right: 680, top: 26, bottom: 146 };
    const from = part.season.forecasts_from, to = part.season.show_to;
    const d0 = dayNumber(from), d1 = dayNumber(to);
    const x = (iso) => box.left + ((dayNumber(iso) - d0) / (d1 - d0)) * (box.right - box.left);
    const y = (v) => box.bottom - v * (box.bottom - box.top);
    const parts = [];
    const seasonEnd = x(part.season.forecasts_to);
    parts.push('<rect x="' + r1(seasonEnd) + '" y="' + box.top + '" width="' + r1(box.right - seasonEnd) + '" height="' +
               (box.bottom - box.top) + '" fill="' + C.after + '"/>');
    [[0, "none"], [0.5, "5 in 10"], [1, "10 in 10"]].forEach(([v, words]) => {
      parts.push(line(box.left, y(v), box.right, y(v), C.grid, 1));
      parts.push(label(box.left - 8, y(v) + 4, words, "proof-axis", "end"));
    });
    dam.falls.forEach((day) => parts.push(line(x(day), box.top, x(day), box.bottom, C.ink, 1.5)));
    dam.forecasts.forEach((f) => {
      const px = x(f.date), py = y(f.chance);
      parts.push(line(px, box.bottom, px, py, C.stem, 1.5));
      const fill = f.fell === true ? C.chance : (f.fell === false ? C.surface : C.unknown);
      const stroke = f.fell === null ? C.unknown : C.chance;
      parts.push('<circle cx="' + r1(px) + '" cy="' + r1(py) + '" r="4.5" fill="' + fill + '" stroke="' + stroke +
                 '" stroke-width="2"/>');
      const end = DamDays.format.addDays(f.date, 90);
      const what = f.fell === true ? "It fell below a third on " + fmtDate(f.fell_on) + "."
        : (f.fell === false ? "It did not fall below a third by then." : "The answer is not known.");
      parts.push(hitRect(px - 5, box.top, 10, box.bottom - box.top,
                         fmtDate(f.date) + ": chance " + chanceWords(f.chance) + " that it falls below a third by " +
                         fmtDate(end) + ". " + what));
    });
    timeAxis("labels", x, from, to, box.bottom, parts);
    parts.push(label(box.left, 12, "Each forecast: the chance it falls below a third within 90 days", "proof-axis-title", "start"));
    const summary = dam.name + ": " + dam.forecasts.length + " forecasts. " + dam.summary;
    return svg("proof-forecasts", W, H, summary, parts);
  }

  function damPicker(part) {
    const rows = part.dams.map((d) => {
      const rw = d.rewind;
      const said = rw.chance === null ? "no forecast (" + esc(rw.status.replace(/_/g, " ")) + ")" : esc(chanceWords(rw.chance));
      const next = rw.outcome === true ? "fell below a third, " + esc(fmtDate(rw.outcome_date))
        : (rw.outcome === false ? "stayed above a third" : "-");
      const selected = d.dam_id === selectedDam;
      return '<tr class="' + (selected ? "is-selected" : "") + '"><th scope="row"><button type="button" class="dam-link" ' +
             'data-proof-dam="' + esc(d.dam_id) + '" aria-pressed="' + selected + '">' + esc(d.name) + "</button></th>" +
             "<td>" + said + "</td><td>" + next + "</td></tr>";
    });
    return '<table class="farm-table proof-picker"><caption>' + esc(part.farm.name) + " on " +
           esc(fmtDate(part.rewind_date)) + " (as in Rewind). Pick a dam to see its whole season.</caption>" +
           "<thead><tr><th scope=\"col\">Dam</th><th scope=\"col\">Chance it falls below a third within 90 days</th>" +
           "<th scope=\"col\">What happened in those 90 days</th></tr></thead><tbody>" + rows.join("") + "</tbody></table>";
  }

  function damDetail(part) {
    const dam = part.dams.find((d) => d.dam_id === selectedDam) || part.dams[0];
    const anyUnknown = dam.forecasts.some((f) => f.fell === null);
    const legend = '<ul class="legend-items proof-legend">' +
      '<li><span class="proof-key proof-key-line" style="background:' + C.water + '" aria-hidden="true"></span>water level</li>' +
      '<li><span class="proof-key proof-key-rule" aria-hidden="true"></span>fell below a third</li>' +
      '<li><span class="swatch" style="background:' + C.chance + ";border-color:" + C.chance + '" aria-hidden="true"></span>' +
      "forecast that was followed by a fall within 90 days</li>" +
      '<li><span class="swatch" style="background:#ffffff;border:2px solid ' + C.chance + '" aria-hidden="true"></span>' +
      "forecast that was not</li>" +
      (anyUnknown ? '<li><span class="swatch" style="background:' + C.unknown + '" aria-hidden="true"></span>answer not known</li>' : "") +
      "</ul>";
    const rows = dam.forecasts.map((f) =>
      "<tr><th scope=\"row\">" + esc(fmtDate(f.date)) + "</th><td>" + esc(chanceWords(f.chance)) + "</td><td>" +
      (f.fell === true ? "fell below a third, " + esc(fmtDate(f.fell_on)) : (f.fell === false ? "did not" : "not known")) +
      "</td></tr>");
    return '<p class="proof-dam-summary">' + esc(dam.summary) + " Area " + dam.area_ha + " ha.</p>" + legend +
           '<div class="proof-chart-wrap">' + levelSvg(dam, part) + forecastSvg(dam, part) + "</div>" +
           '<details class="proof-numbers"><summary>Show the numbers (' + esc(dam.name) + ")</summary><div class=\"proof-table-scroll\"><table>" +
           "<thead><tr><th scope=\"col\">Forecast made on</th><th scope=\"col\">Chance it falls below a third within 90 days</th>" +
           "<th scope=\"col\">Within those 90 days</th></tr></thead><tbody>" + rows.join("") + "</tbody></table></div></details>";
  }

  function damFigure() {
    const part = proof.dam_by_dam;
    return '<figure class="proof-figure" aria-labelledby="proof-3-title">' +
           '<p class="proof-kicker">3 · ' + esc(part.title) + "</p>" +
           '<h2 id="proof-3-title" class="proof-takeaway">' + esc(part.takeaway) + "</h2>" +
           '<div id="proof-dam-picker">' + damPicker(part) + "</div>" +
           '<div id="proof-dam-detail" aria-live="polite">' + damDetail(part) + "</div>" +
           '<figcaption class="proof-note"><p>' + esc(part.how_to_read) + "</p><p>" + esc(part.how_chosen) +
           ' <a href="#rewind">Open Rewind</a>.</p></figcaption></figure>';
  }

  function selectDam(damId) {
    selectedDam = damId;
    const part = proof.dam_by_dam;
    document.getElementById("proof-dam-picker").innerHTML = damPicker(part);
    document.getElementById("proof-dam-detail").innerHTML = damDetail(part);
  }

  // ---- The view ----------------------------------------------------------------
  /** Runs once, the first time the view is shown. */
  function init(data) {
    proof = data.proof;
    document.getElementById("proof-exam").innerHTML = examHtml(data);
    const body = document.getElementById("proof-body");
    if (!proof) {
      body.innerHTML = '<p class="note">The Proof charts are made from the real test forecasts ' +
        "(<code>app/data/real/proof.json</code>, written by <code>scripts/17_proof_data.py</code>). " +
        "This dataset does not have them.</p>";
      return;
    }
    document.getElementById("proof-intro").textContent =
      "Can you trust the forecasts? Three pictures, set against what really happened. " + proof.test.intro;
    selectedDam = proof.dam_by_dam.default_dam;
    body.innerHTML = '<p class="proof-caveat">' + esc(proof.test.caveat) + "</p>" +
                     calibrationFigure() + yearsFigure() + damFigure();
    body.addEventListener("click", (event) => {
      const button = event.target.closest("[data-proof-dam]");
      if (button) selectDam(button.dataset.proofDam);
    });
  }

  /** Nothing to refresh: the data does not change while the page is open. */
  function show() {}

  return { init, show };
})();
