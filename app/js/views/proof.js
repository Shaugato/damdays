/* views/proof.js (WP-E)
 * Proof: "How do we know it works?" (UI_SPEC 3.4, 4.3, 5.15 to 5.18).
 *
 *   #proof              the page (glance): the cautious-days hero, the unseen exam card, four picture
 *                       cards, the caveat, the who-else slot (?whoelse=0 removes it)
 *   #proof/said         sheet 1: what we said vs what happened (the calibration picture)
 *   #proof/years        sheet 2: year after year (less error each year, and how often "at least N days" held)
 *   #proof/rewind       sheet 3: Rewind, the 2018-19 drought (drawn by js/views/replay.js)
 *   #proof/dams         sheet 4: dam by dam (the demo farm's dams through 2018-19); /dam-N picks a dam
 *   #proof/exam         the unseen exam in detail; /numbers opens "Every number, for specialists"
 *   .../numbers         opens that sheet's "Show the numbers"
 *
 * Every number comes from the data: proof.json (scripts/17), scoreboard.json (the sealed panel, filled by
 * scripts/21 after the opening), track_record.json (scripts/18). Sentences with numbers are proof.json's own;
 * the few built here only join numbers read from those files.
 * Charts are drawn at the width of their box (labels 13 px, no sideways scroll) and redrawn on resize.
 *
 * Wording: "%" only means how full a dam is; a chance is "N in 10"; how often something happened is
 * "N in 1,000". Scoring words (Brier, skill score, calibration slope, model names) appear only inside a
 * "For specialists" disclosure: proof.json's own brackets that carry them are moved there (plainSplit).
 *
 * DamDays.proofKit: small drawing and wording helpers shared with js/views/replay.js.
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.proofKit = (function () {
  "use strict";

  const D = window.DamDays;
  const esc = (t) => D.format.escapeHtml(t === null || t === undefined ? "" : t);
  const r1 = (v) => Math.round(v * 10) / 10;
  const count = (n) => Number(n).toLocaleString("en-AU");
  const inTen = (c) => D.text.inTen(c);
  const chance = (c) => (c === null || c === undefined ? "no forecast" : D.text.chanceText(c));
  const capital = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
  const numberWord = (n) => (n >= 0 && n < WORDS.length ? WORDS[n] : count(n));
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const dayNo = (iso) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 864e5;

  /** The fill of a chance's colour band (settings.chanceBands), as a token so dark mode follows. */
  function bandVar(c) {
    if (c === null || c === undefined) return "var(--c-none)";
    const t = inTen(c);
    return t === 0 ? "var(--c0)" : t <= 2 ? "var(--c1)" : t <= 4 ? "var(--c2)" : t <= 6 ? "var(--c3)" : "var(--c4)";
  }

  const sketchFn = (name) => (D.sketch && typeof D.sketch[name] === "function" ? D.sketch[name] : null);

  // A farm dam seen from above (UI_SPEC 5.11): its usual full edge, and the wet part scaled by AREA.
  // js/sketch.js draws the same glyph; it is used when there, this copy otherwise.
  const DAM_PATH = "M20 31C23 15 45 9 63 13C81 17 92 31 89 51C86 72 72 89 50 88C28 87 12 74 11 55C10 45 16 39 20 31Z";
  function glyph(d, size, decorative) {
    const own = sketchFn("glyph");
    if (own) { try { const s = own(d, size, decorative); if (s) return s; } catch (e) { /* use the copy below */ } }
    const p = d.level_pct === null || d.level_pct === undefined ? 0 : Math.min(d.level_pct, 100) / 100;
    const low = d.status === "already_low";
    const when = d.issued_on ? D.format.short(d.issued_on) : "";
    const label = low ? d.name + " seen from above: below a third at its " + when + " look"
                      : d.name + " seen from above: " + D.format.fullness(d.level_pct) + " of its usual water surface";
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 100 100" ' +
      (decorative ? 'aria-hidden="true" focusable="false"' : 'role="img" aria-label="' + esc(label) + '"') + ">" +
      '<path d="' + DAM_PATH + '" fill="var(--dam-bed)" stroke="var(--dam-rim)" stroke-width="' + (low ? 5 : 4) + '"' +
      (low ? ' stroke-dasharray="10 8"' : "") + "/>" +
      (p > 0.004 ? '<path d="' + DAM_PATH + '" fill="var(--water)" transform="translate(64 70) scale(' + Math.sqrt(p).toFixed(3) +
        ') translate(-64 -70)"/>' : "") +
      '<path d="M34 86 Q52 95 74 84" fill="none" stroke="var(--earth)" stroke-width="6" stroke-linecap="round"/></svg>';
  }

  /** Ten dots, the first N filled in the band colour (UI_SPEC 5.12); always with the "N in 10" words beside. */
  function dots(c, r, label, tight) {
    const own = sketchFn("dots");
    if (own) { try { const s = own(c, r, label, tight); if (s) return s; } catch (e) { /* use the copy below */ } }
    const t = c === null || c === undefined ? 0 : inTen(c);
    const gap = r * 2 + (tight ? 3 : 4);
    let s = "";
    for (let i = 0; i < 10; i++) {
      const on = i < t;
      s += '<circle cx="' + r1(r + 1.5 + i * gap) + '" cy="' + r1(r + 1.5) + '" r="' + r + '" fill="' + (on ? bandVar(c) : "none") +
        '" stroke="' + (on ? "var(--c-ring)" : "var(--line-strong)") + '" stroke-width="1.6"/>';
    }
    const w = r1(3 + r * 2 + 9 * gap), h = r1(r * 2 + 3);
    return '<svg class="dots" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="' +
      esc(label || chance(c)) + '">' + s + "</svg>";
  }

  /** "A. B (x). C" -> ["A.", "B (x).", "C"]: splits at a full stop followed by a capital (no look-behind). */
  function sentences(text) {
    return String(text || "").replace(/([.!?])\s+(?=[A-Z"(])/g, "$1\u0001").split("\u0001").map((s) => s.trim()).filter(Boolean);
  }

  // Scoring words that live only under "For specialists" (UI_SPEC 1; founder decision 5).
  const JARGON = /\b(calibration slope|brier|skill|auc|tidemark|g2|l3|bss|r30|b0|b2|prereg|config)\b/i;
  /** proof.json sentences, with any bracket that carries scoring words moved out: { plain, tech: [...] }. */
  function plainSplit(text) {
    const tech = [];
    const plain = String(text || "").replace(/\s*\(([^()]*)\)/g, (m, inner) => {
      if (JARGON.test(inner)) { tech.push(capital(inner.trim())); return ""; }
      return m;
    }).replace(/\s+([.,;:])/g, "$1");
    return { plain, tech };
  }

  /**
   * proof.json's sentences (scripts/17) say "at least N days" and "water level"; on screen a farmer reads "our
   * days-left number" and "how full" ("%" is the share of the surface that is wet, not depth). Words only:
   * every number in them stays as the data wrote it.
   */
  function plainWords(text) {
    return String(text || "")
      .replace(/The "at least N days" promise/g, "Our days-left number")
      .replace(/"at least N days"/g, "our days-left number")
      .replace(/for at least the N days promised/g, "for at least the days promised")
      .replace(/the dam's water level at each clear satellite look \(% of its usual full level\)/g,
        "how full the dam was at each clear satellite look (% of its usual full water surface, not depth)")
      .replace(/\bwater level\b/g, "fullness");
  }

  /** "Head: rest of it." -> ["Head.", "Rest of it."] (a takeaway as a card heading and its line). */
  function headAndRest(text) {
    const s = String(text || "");
    const i = s.indexOf(": ");
    if (i < 0) return [s, ""];
    return [s.slice(0, i) + ".", capital(s.slice(i + 2))];
  }

  /** Chances added up: 0.368 -> "less than 1 fall", 0.99 -> "about 1 fall", 1.57 -> "about 2 falls". */
  function sumWords(sum, noun) {
    const one = noun || "fall", many = noun ? noun + "s" : "falls";
    const v = Math.round(sum);
    if (v < 1) return "less than 1 " + one;
    return "about " + count(v) + " " + (v === 1 ? one : many);
  }

  // ---- SVG pieces (charts are drawn 1:1 with their box, so 13 in the SVG is 13 CSS px) ----
  function line(x1, y1, x2, y2, stroke, width, extra) {
    return '<line x1="' + r1(x1) + '" y1="' + r1(y1) + '" x2="' + r1(x2) + '" y2="' + r1(y2) + '" stroke="' + stroke +
      '" stroke-width="' + (width || 1) + '"' + (extra || "") + "/>";
  }
  function text(x, y, t, cls, anchor, extra) {
    return '<text x="' + r1(x) + '" y="' + r1(y) + '" class="' + cls + '"' + (anchor ? ' text-anchor="' + anchor + '"' : "") +
      (extra || "") + ">" + esc(t) + "</text>";
  }
  function rect(x, y, w, h, fill, extra) {
    return '<rect x="' + r1(x) + '" y="' + r1(y) + '" width="' + r1(Math.max(0, w)) + '" height="' + r1(Math.max(0, h)) +
      '" fill="' + fill + '"' + (extra || "") + "/>";
  }
  function svg(cls, W, H, summary, parts) {
    return '<svg class="pc ' + cls + '" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H +
      '" role="img" aria-label="' + esc(summary) + '">' + parts.join("") + "</svg>";
  }
  /** An invisible, larger hover target carrying a plain tooltip (desktop); the tables hold every value. */
  function hit(shape, attrs, tip) {
    return "<" + shape + " " + attrs + ' fill="transparent" class="pc-hit"><title>' + esc(tip) + "</title></" + shape + ">";
  }
  const textWidth = (t) => String(t).length * 7.3;   // 13 px Atkinson, roughly

  return { esc, r1, count, inTen, chance, capital, numberWord, MONTHS, dayNo, bandVar, glyph, dots, sentences, plainSplit,
           plainWords, headAndRest, sumWords, line, text, rect, svg, hit, textWidth, DAM_PATH };
})();

DamDays.views.proof = (function () {
  "use strict";

  const D = window.DamDays;
  const K = D.proofKit;
  const { esc, r1, count, inTen, chance, numberWord, line, text, rect, svg, hit, textWidth } = K;
  const icon = (id, cls, label) => (D.icon ? D.icon(id, cls, label) : "");
  const plus = () => icon("i-plus", "plus");
  const fmtDate = (iso) => D.format.date(iso);
  const short = (iso) => D.format.short(iso);
  const signed = (v, digits) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(digits);

  let data = null;
  let proof = null;
  let params = {};
  let openSub = null, openDeep = null, sheetToken = 0;
  let selectedDam = null;
  let wired = false;
  let resizeTimer = 0;

  /** The data for a part (WP-B's need(), if there), then the prepared object every view shares. */
  /** The parts a view needs (js/data.js need(): first = proof, scoreboard, farms, track records; rewind = the
   *  past dates), resolving to the one prepared object every view shares. load() only without need(). */
  function getData(parts) {
    const d = D.data;
    if (d && typeof d.need === "function") return Promise.resolve(d.need(parts)).then((x) => x || d.load());
    return d.load();
  }

  // =====================================================================
  // The unseen exam (4.3, 5.15): its state comes from scoreboard.json panels[key=sealed], never the clock
  // =====================================================================
  function sealedPanel() {
    const panels = (data && data.scoreboard && data.scoreboard.panels) || [];
    const key = (proof && proof.unseen_exam && proof.unseen_exam.panel_key) || "sealed";
    return panels.find((p) => p && p.key === key) || null;
  }
  const examState = (panel) => (!panel ? "missing" : panel.status === "scored" ? "scored" : "pending");

  /** "2026-10-02 20:36" -> "Fri 2 Oct, 20:36"; a stamp with a zone is shown in Sydney time. */
  function when(stamp, dayOnly) {
    const s = String(stamp || "");
    const m = /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?/.exec(s);
    if (!m) return "";
    let day = m[1], hm = m[2] || "";
    if (/(Z|[+-]\d{2}:?\d{2})$/.test(s) && hm) {
      try {
        const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Australia/Sydney", year: "numeric", month: "2-digit",
          day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(s));
        const get = (t) => (parts.find((p) => p.type === t) || {}).value;
        day = get("year") + "-" + get("month") + "-" + get("day");
        hm = get("hour") + ":" + get("minute");
      } catch (e) { /* keep the stamp's own day and time */ }
    }
    return D.format.dayShort(day) + (hm && !dayOnly ? ", " + hm : "");
  }

  /** proof.json's exam text, without "Everything below is the ten test years" (on this page the hero is too). */
  function examText() {
    const t = proof && proof.unseen_exam ? proof.unseen_exam.text : "";
    return K.sentences(t).filter((s) => !/^Everything below/i.test(s)).join(" ");
  }
  // No time is promised: the opening comes after tonight's build (founder, Sat 3 Oct).
  const PENDING_WHEN = "Not opened yet. We open it once this build of the app is finished, on camera, and this card then shows its score.";
  /** The pre-commitment line, its "(skill ...)" bracket moved to the specialists' view. */
  function expectSplit() {
    const e = proof && proof.unseen_exam && proof.unseen_exam.expect;
    return e ? K.plainSplit(e) : { plain: "", tech: [] };
  }

  function scoredHeading(panel) {
    const day = when(panel.scored_at, true);
    return "Unseen exam: opened " + (day ? day + ", " : "") + "scored once";
  }

  /** One or two sentences built from the scored panel (4.3): the result, then the pass marks. */
  function scoredLines(panel) {
    const r = panel.runway || {};
    let first = "On a region it never saw: " + D.format.examSkillWords(r.skill_vs_usual_rate);
    if (panel.floor && typeof panel.floor.held === "number") {
      first += "; the cautious days held " + count(D.format.inThousand(panel.floor.held)) + " times in 1,000";
    }
    first += ".";
    const marks = D.format.passMarks(panel);
    return [first, marks ? marks.sentence : ""].filter(Boolean);
  }

  /**
   * Each thing we said we expected, in plain words, against what came out (a scored panel's expectations and
   * fields), so a missed mark is said, not left to the specialists' panel. Then the cautious days' worst year.
   * -> [{ text, miss [, state, icon] }] (miss: it came out below what we expected, or not clearly ahead; the
   *    cautious days' line also carries format.floorCheck's state "met" | "miss" | "neutral" and its icon)
   */
  function expectedLines(panel) {
    const out = [];
    const fw = (v) => D.format.fractionWords(v) || "no";
    const field = (path) => path.split(".").reduce((o, k) => (o ? o[k] : null), panel);
    (panel.expectations || []).forEach((e) => {
      const got = field(e.field || "");
      if (!got || typeof got.value !== "number") return;
      const v = got.value, clear = typeof got.ci_low !== "number" || got.ci_low > 0;
      const inside = v >= e.low && v <= e.high;
      const where = inside ? "inside what we expected" : v < e.low ? "below what we expected" : "above what we expected";
      if (e.field === "runway.skill_vs_usual_rate" || e.field === "runway.skill_vs_own_record") {
        const what = e.field === "runway.skill_vs_usual_rate" ? "Less error than guessing the usual rate" : "Less error than each dam's own past rate";
        // the expected range itself is in the line under the card and, as numbers, for specialists
        out.push({ miss: v < e.low || !clear, text: what + ": " + (v <= 0 ? "none" : fw(v) + (clear ? "" : ", not a clear gain")) +
          ", " + where + "." });
      } else if (e.field === "runway.gain_vs_benchmark") {
        const lead = got.ci_low > 0 ? "ahead" : got.ci_high < 0 ? "behind" : "not clearly ahead";
        out.push({ miss: !(got.ci_low > 0), text: "Against the simpler model written down before the build began: " + lead + " (we expected it a little ahead)." });
      } else if (e.field === "rating.gain_vs_rain") {
        out.push({ miss: v < e.low, text: "The area outlook against rainfall alone: it ranked areas right " + Math.round(v * 100) +
          " more times in 100, " + where + " (" + Math.round(e.low * 100) + " to " + Math.round(e.high * 100) + " more)." });
      }
    });
    const fl = panel.floor;
    const fc = D.format.floorCheck(fl, proof);
    if (fc) {
      // one rule with the hero, the exam sheet, Questions and About (format.floorCheck): the panel's own on_target
      // flag when it has one (the sealed results'), else the test code's float rule. On target is met (a check);
      // below target is a miss (a cross); above the range is "more cautious than built for": neither (its own icon)
      const built = fc.target === null ? "" : " (built for " + count(fc.target) + (fc.range ? ", and " + fc.range + " counts as on target" : "") +
        (fc.edgeNote ? "; " + fc.edgeNote : "") + ")";
      out.push({ miss: fc.below, state: fc.state, icon: fc.icon, text: "The cautious days held " + count(fc.held) + " times in 1,000" +
        (fc.verdict ? ": " + fc.verdict : "") + built + (fl.worst_year && typeof fl.worst_year.coverage === "number"
          ? "; in the worst July-June year, " + fl.worst_year.year + "-" + String(fl.worst_year.year + 1).slice(2) + ", " +
            count(D.format.inThousand(fl.worst_year.coverage)) + " times in 1,000" : "") + "." });
    }
    return out;
  }
  // met: a check; miss: a cross; neutral (the cautious days above their range, or not judged): the line's own icon
  const LINE_STATE = { met: ["is-met", "i-check"], miss: ["is-miss", "i-x"], neutral: ["is-neutral", "i-minus"] };
  const expectedHtml = (panel, cls) => {
    const lines = expectedLines(panel);
    return lines.length ? '<ul class="exam-got' + (cls ? " " + cls : "") + '">' + lines.map((l) => {
      const [klass, mark] = LINE_STATE[l.state || (l.miss ? "miss" : "met")] || LINE_STATE.neutral;
      return '<li class="' + klass + '">' + icon(l.icon || mark, "sm") + "<span>" + esc(l.text) + "</span></li>";
    }).join("") + "</ul>" : "";
  };

  function timelineHtml(state, panel) {
    const items = [["Before the build", "the rules and the pass marks written down", false],
                   ["Then", "the model locked: no changes after this", false]];
    const years = proof && proof.by_year ? numberWord(proof.by_year.years.length) : "the";
    if (proof && proof.test && proof.test.scored_at) items.push([when(proof.test.scored_at), years + " test years scored once", false]);
    if (state === "scored") items.push([when(panel.scored_at) || "Opened", "the unseen exam opened, scored once", false]);
    else items.push(["Next", "the unseen exam, opened once on camera", true]);
    return '<ol class="timeline">' + items.map(([w, t, pending]) =>
      "<li" + (pending ? ' class="is-pending"' : "") + "><span><b>" + esc(w) + "</b> " + esc(t) + "</span></li>").join("") + "</ol>";
  }

  function examCardHtml(panel, state) {
    if (state === "missing") {
      // No sealed panel: hide the card, keep the timeline (5.15).
      return proof ? '<section class="exam-card is-missing" aria-labelledby="exam-title"><p class="eyebrow" id="exam-title">How the test was run</p>' +
        timelineHtml(state, panel) + "</section>" : "";
    }
    const scored = state === "scored";
    const ex = expectSplit();
    const body = scored
      ? (panel.label ? '<p class="exam-region">' + icon("i-pin", "sm") + "<span>" + esc(panel.label) + "</span></p>" : "") +
        scoredLines(panel).map((s, i) => '<p class="' + (i ? "exam-marks" : "exam-result") + '">' + esc(s) + "</p>").join("") +
        expectedHtml(panel)
      : "<p>" + esc(examText() || panel.label || "") + '</p><p class="exam-when">' + icon("i-lock", "sm") + "<span>" + esc(PENDING_WHEN) + "</span></p>";
    return '<section class="exam-card ' + (scored ? "is-scored" : "is-pending") + '" aria-labelledby="exam-title">' +
      '<div class="exam-top"><p class="eyebrow">The unseen exam</p><span class="tag' + (scored ? " tag-ink" : "") + '">' +
      (scored ? "Scored once" : "Not opened yet") + "</span></div>" +
      '<h2 id="exam-title">' + esc(scored ? scoredHeading(panel) : "Kept aside: a region we never opened or used") + "</h2>" + body +
      (ex.plain ? '<p class="exam-expect">' + esc(ex.plain) + "</p>" : "") + timelineHtml(state, panel) +
      '<a class="exam-more" href="#proof/exam"><span>' + (scored ? "The result in detail" : "The exam in detail") + "</span>" +
      icon("i-chev", "sm") + "</a></section>";
  }

  /** The exam sheet (#proof/exam): pending or scored; every number for specialists one tap down. */
  function examSheetHtml() {
    const panel = sealedPanel();
    const state = examState(panel);
    const ex = expectSplit();
    const region = panel && panel.label ? '<p class="ps-note"><b>The region:</b> ' + esc(panel.label) + ".</p>" : "";
    let main, spec;
    if (state === "scored") {
      main = '<h2 class="ps-h">' + esc(scoredHeading(panel)) + "</h2>" + region +
        scoredLines(panel).map((s) => '<p class="ps-lead">' + esc(s) + "</p>").join("") +
        (expectedLines(panel).length ? '<h3 class="ps-h3">What we said to expect, and what came out</h3>' + expectedHtml(panel, "is-sheet") : "");
      const about = D.views && D.views.about && typeof D.views.about.panelHtml === "function" ? D.views.about.panelHtml : null;
      spec = about ? '<div class="proof-specialists">' + about(panel) + "</div>" : "";
    } else {
      main = '<h2 class="ps-h">Unseen exam: not opened yet</h2><p class="ps-lead">' + esc(examText()) + "</p>" + region +
        '<p class="exam-when">' + icon("i-lock", "sm") + "<span>" + esc(PENDING_WHEN) + "</span></p>";
      const exp = (panel && panel.expectations) || [];
      spec = exp.length ? '<p>What we said we expected, before opening it. Each is a forecast, not a pass mark:</p><ul class="ps-list">' +
        exp.map((e) => "<li>" + esc(String(e.what || "").replace(/^Runway skill/, "90-day chance skill")) + ": " + signed(e.low, 2) + " to " + signed(e.high, 2) + "</li>").join("") + "</ul>" : "";
    }
    spec += ex.tech.length ? '<p class="small">The expectation in the card, as a score: ' + esc(ex.tech.join("; ")) + ".</p>" : "";
    return '<article class="ps">' +
      '<p class="eyebrow">The unseen exam</p>' + main +
      (ex.plain ? '<p class="ps-note exam-expect">' + esc(ex.plain) + "</p>" : "") +
      timelineHtml(state, panel) +
      '<details class="more ps-spec" data-numbers data-specialists><summary>' + icon("i-info") + "Every number, for specialists" + plus() +
      '</summary><div class="body">' + (spec || "<p>Nothing to show yet.</p>") + "</div></details>" +
      '<div class="linkrows"><a class="linkrow" href="#about/specialists">' + icon("i-chart") +
      "<span>Methods and scores, for specialists<small>Both test panels, the pass marks and the data facts, on About</small></span>" +
      '<span class="chev">' + icon("i-chev") + "</span></a></div></article>";
  }

  // =====================================================================
  // The page (glance)
  // =====================================================================
  function headHtml(state) {
    const years = proof && proof.by_year ? numberWord(proof.by_year.years.length) : null;
    // the two test regions, from proof.json's own intro ("in two farming regions (A; B)")
    const regions = proof && proof.test ? /in (two|three|\w+) farming regions \(([^)]+)\)/.exec(proof.test.intro || "") : null;
    let lead = "We wrote the pass marks down before the build began";
    if (years) lead += ", tested on " + years + " years the model never trained on" + (regions ? ", in " + regions[1] + " farming regions (" + regions[2] + ")" : "");
    lead += state === "scored" ? ", and opened a region it never saw, once, on camera."
      : state === "pending" ? ", and keep a third region aside, never opened or used, to open once, on camera." : ".";
    return '<header class="page-head"><p class="eyebrow">Proof</p><h1 id="proof-h1">How do we know it works?</h1>' +
      '<p class="lead">' + esc(lead) + "</p></header>";
  }

  function heroHtml() {
    if (!proof || !proof.by_year || !proof.by_year.all_years) return "";
    const by = proof.by_year, all = by.all_years;
    const n = D.format.inThousand(all.floor_held);
    const tenths = inTen(all.floor_held);
    // the one on-target rule (format.floorCheck), as on the exam card, Questions and About
    const fc = D.format.floorCheck({ held: all.floor_held, target: by.floor_target }, proof);
    const onTarget = !!(fc && fc.onTarget === true);
    let ten = "";
    for (let i = 0; i < 10; i++) ten += "<i" + (i < tenths ? "" : ' class="off"') + "></i>";
    const dist = data.trackRecord && data.trackRecord.summary && data.trackRecord.summary.distribution;
    const perDam = dist ? '<p class="proof-hero-dams">On each dam: the typical dam held <b>' + count(dist.median_in_1000) +
      " times in 1,000</b>; " + count(dist.dams_below_9_in_10) + " of the " + count(dist.dams_with_record) +
      " dams with a record held less than 9 times in 10 (" + count(dist.dams_below_8_in_10) + " less than 8 times in 10), " +
      "and their dam cards say to give the days extra margin.</p>" : "";
    const how = D.text && D.text.TRACK_RECORD_HOW ? D.text.TRACK_RECORD_HOW : "";
    return '<section class="proof-hero" aria-labelledby="proof-hero-label">' +
      '<p class="eyebrow" id="proof-hero-label">The cautious days held</p>' +
      '<p class="proof-big"><b>' + count(n) + "</b> <span>in 1,000</span></p>" +
      '<div class="proof-tendots" role="img" aria-label="' + tenths + ' in 10">' + ten + "</div>" +
      '<p class="proof-hero-line">times in ' + numberWord(by.years.length) + " test years (" + count(all.floor_judged) +
      " forecasts checked)" + (onTarget ? ", as designed." : ".") + "</p>" + perDam +
      '<details class="more proof-hero-how"><summary>' + icon("i-info") + "How was this checked?" + plus() + '</summary><div class="body">' +
      "<p>Each forecast says at least how many days a dam has before it drops below a third. It held if the dam stayed above a third at least that long.</p>" +
      (how ? "<p>" + esc(how) + "</p>" : "") + "</div></details></section>";
  }

  // ---- the mini pictures on the cards (decorative: the card's words say the same) ----
  function miniSaid() {
    const bins = proof.calibration.bins.filter((b) => b.plotted);
    let s = rect(0, 0, 64, 64, "var(--surface-2)", ' rx="12"') + line(8, 56, 56, 8, "var(--line-strong)", 1.5);
    bins.forEach((b) => { s += '<circle cx="' + r1(8 + 48 * b.in_ten / 10) + '" cy="' + r1(56 - 48 * b.share_fell) + '" r="3.4" fill="var(--c3)" stroke="var(--surface)" stroke-width="1"/>'; });
    return '<svg viewBox="0 0 64 64" width="64" height="64" aria-hidden="true" focusable="false">' + s + "</svg>";
  }
  function miniYears() {
    const ys = proof.by_year.years;
    const maxV = Math.max(0.3, ...ys.map((y) => y.skill));
    const bw = 48 / ys.length;
    let s = rect(0, 0, 64, 64, "var(--surface-2)", ' rx="12"');
    ys.forEach((y, i) => {
      if (y.drier) s += rect(8 + i * bw, 8, bw, 48, "var(--straw)");
    });
    ys.forEach((y, i) => { const h = 44 * Math.max(0, y.skill) / maxV; s += rect(8 + i * bw + bw * 0.2, 56 - h, bw * 0.6, h, "var(--ink)", ' rx="1"'); });
    return '<svg viewBox="0 0 64 64" width="64" height="64" aria-hidden="true" focusable="false">' + s + "</svg>";
  }
  function miniDams() {
    const part = proof.dam_by_dam;
    const dam = part.dams.find((d) => d.dam_id === part.default_dam) || part.dams[0];
    const pts = dam.looks.filter((l) => l[1] !== null);
    const d0 = K.dayNo(part.season.forecasts_from), d1 = K.dayNo(part.season.show_to);
    const x = (iso) => 6 + 52 * (K.dayNo(iso) - d0) / (d1 - d0), y = (p) => 56 - 46 * Math.min(p, 120) / 120;
    let s = rect(0, 0, 64, 64, "var(--surface-2)", ' rx="12"') + rect(6, y(part.threshold_pct), 52, 56 - y(part.threshold_pct), "var(--straw)");
    s += '<polyline points="' + pts.map((l) => r1(x(l[0])) + "," + r1(y(l[1]))).join(" ") + '" fill="none" stroke="var(--water)" stroke-width="2" stroke-linejoin="round"/>';
    return '<svg viewBox="0 0 64 64" width="64" height="64" aria-hidden="true" focusable="false">' + s + "</svg>";
  }

  function seasonLabel() {
    const part = proof && proof.dam_by_dam;
    if (!part || !part.season) return "";
    const y = +part.season.forecasts_from.slice(0, 4);
    return y + "-" + String(y + 1).slice(2);
  }
  function damsHeading() {
    const part = proof.dam_by_dam;
    return "Every " + seasonLabel() + " forecast for " + part.farm.name + ", dam by dam, against how full it was.";
  }

  function card(sub, n, eyebrow, heading, line2, mini, feature) {
    return '<a class="pcard' + (feature ? " is-feature" : "") + '" href="#proof/' + sub + '">' +
      '<span class="pcard-top"><span class="eyebrow">' + n + " · " + esc(eyebrow) + '</span><span class="pcard-mini" aria-hidden="true">' + mini + "</span></span>" +
      '<span class="pcard-h">' + esc(heading) + "</span>" + (line2 ? '<span class="pcard-sub">' + esc(line2) + "</span>" : "") +
      (feature ? '<span class="pcard-cta">' + icon("i-rewind", "sm") + "Open Rewind" + icon("i-chev", "sm") + "</span>"
               : '<span class="pcard-go">See the picture' + icon("i-chev", "sm") + "</span>") + "</a>";
  }

  function picturesHtml() {
    const list = [];
    if (proof && proof.calibration) list.push(["said", proof.calibration.title, proof.calibration.takeaway, "", miniSaid(), false]);
    if (proof && proof.by_year) {
      const [h, rest] = K.headAndRest(proof.by_year.takeaway);
      list.push(["years", proof.by_year.title, h, rest, miniYears(), false]);
    }
    const rw = D.replay && typeof D.replay.cardInfo === "function" ? D.replay.cardInfo(data) : null;
    if (rw) list.push(["rewind", rw.label, rw.heading, rw.sub, rw.thumb, true]);
    if (proof && proof.dam_by_dam) {
      list.push(["dams", proof.dam_by_dam.title, damsHeading(), "Pick a dam: when it fell below a third, and what each forecast said before.", miniDams(), false]);
    }
    if (!list.length) return "";
    const title = K.capital(numberWord(list.length)) + (list.length === 1 ? " picture" : " pictures");
    return '<h2 class="section-title proof-cards-title">' + esc(title) + ", set against what really happened</h2>" +
      '<div class="proof-cards">' + list.map((c, i) => card(c[0], i + 1, c[1], c[2], c[3], c[4], c[5])).join("") + "</div>";
  }

  function whoElseHtml() {
    if (params.whoelse === "0") return "";
    return '<section class="slot-who-else" data-optional="who-else" aria-label="An idea, not built">' + icon("i-leaf") +
      '<div><span class="tag">An idea, not built</span><p>Added up by district, never farm by farm, the same forecasts could show ' +
      "drought teams and fire agencies where water is running short soonest.</p></div></section>";
  }

  function pageHtml() {
    const panel = sealedPanel();
    const state = examState(panel);
    const missing = !proof ? '<div class="load-error" role="status"><p>The Proof pictures are made from the real test forecasts. ' +
      "This dataset does not have them.</p></div>" : "";
    return '<div class="wrap page-narrow proof-page">' + headHtml(state) + heroHtml() + examCardHtml(panel, state) + missing +
      picturesHtml() + (proof && proof.test ? '<p class="proof-caveat">' + icon("i-info", "sm") + "<span>" + esc(proof.test.caveat) + "</span></p>" : "") +
      whoElseHtml() + "</div>";
  }

  // =====================================================================
  // Charts (5.18): drawn at the box's width
  // =====================================================================
  function saidSvg(W) {
    const cal = proof.calibration;
    const bins = cal.bins.filter((b) => b.plotted);
    const narrow = W < 460;
    const left = narrow ? 60 : 70;
    const box = { left, right: W - 10, top: 30 };
    const plotW = box.right - box.left;
    // nearly square when the sheet is wide (the diagonal near 45 degrees), capped so the chart fits the screen
    const plotH = Math.round(narrow ? Math.min(plotW, 300) : Math.min(plotW / 1.11, 480));
    box.bottom = box.top + plotH;
    const showCounts = plotW / 11.1 >= 46;
    saidCounts = showCounts;
    const H = box.bottom + (showCounts ? 42 : 24) + 30;
    const x0 = -0.09, x1 = 1.02;
    const x = (v) => box.left + ((v - x0) / (x1 - x0)) * plotW;
    const y = (v) => box.bottom - v * plotH;
    const most = Math.max(...bins.map((b) => b.forecasts));
    const parts = [];
    [0, 0.2, 0.4, 0.6, 0.8, 1].forEach((v) => {
      parts.push(line(box.left, y(v), box.right, y(v), "var(--line)", 1));
      parts.push(text(box.left - 8, y(v) + 4, v === 0 ? "none" : Math.round(v * 10) + " in 10", "pc-axis", "end"));
    });
    parts.push(text(0, 14, "Up: how often it fell", "pc-title", "start"));
    parts.push(line(x(0), y(0), x(1), y(1), "var(--ink-3)", 1.5));
    if (!narrow) {
      const angle = Math.atan2(y(1) - y(0), x(1) - x(0)) * 180 / Math.PI;
      const at = 0.7;
      parts.push(text(x(at), y(at), "on this line, what happened = what we said", "pc-axis", "middle",
        ' dy="24" transform="rotate(' + r1(angle) + " " + r1(x(at)) + " " + r1(y(at)) + ')"'));
    }
    bins.forEach((b) => {
      const cx = x(b.in_ten / 10);
      if (b.share_fell_ci) parts.push(line(cx, y(b.share_fell_ci[0]), cx, y(b.share_fell_ci[1]), "var(--c3)", 2));
      const r = (narrow ? 4 : 5) + (narrow ? 8 : 10) * Math.sqrt(b.forecasts / most);
      parts.push('<circle cx="' + r1(cx) + '" cy="' + r1(y(b.share_fell)) + '" r="' + r1(r) + '" fill="var(--c3)" stroke="var(--surface)" stroke-width="2"/>');
      parts.push(hit("circle", 'cx="' + r1(cx) + '" cy="' + r1(y(b.share_fell)) + '" r="' + r1(Math.max(r + 4, 14)) + '"',
        "We said " + b.said + " (" + count(b.forecasts) + " forecasts): " + count(b.fell) + " fell below a third within 90 days, " +
        D.format.inThousandText(b.share_fell) + " (" + aboutChance(b.happened_in_ten / 10) + ")"));
      parts.push(text(cx, box.bottom + 19, b.in_ten === 0 ? (narrow ? "<1" : "under 1") : String(b.in_ten), "pc-axis-strong", "middle"));
      if (showCounts) parts.push(text(cx, box.bottom + 37, count(b.forecasts), "pc-axis", "middle"));
    });
    if (showCounts) parts.push(text(box.left - 8, box.bottom + 37, "forecasts", "pc-axis", "end"));
    parts.push(text((box.left + box.right) / 2, H - 6, "Across: what we said (the chance, in 10)", "pc-title", "middle"));
    const summary = "What we said against what happened, in " + bins.length + " groups: " +
      bins.map((b) => "said " + b.said + ", happened " + D.format.inThousandText(b.share_fell)).join("; ");
    return svg("pc-said", W, H, summary, parts);
  }

  function yearAxis(years, box, H, parts) {
    const band = (box.right - box.left) / years.length;
    const rotate = band < 60;
    years.forEach((yr, i) => {
      const cx = box.left + band * (i + 0.5);
      if (rotate) parts.push(text(cx + 4, box.bottom + 14, yr.label, "pc-axis", "end", ' transform="rotate(-40 ' + r1(cx + 4) + " " + r1(box.bottom + 14) + ')"'));
      else parts.push(text(cx, box.bottom + 18, yr.label, "pc-axis", "middle"));
    });
    return band;
  }
  const yearAxisRoom = (W, n) => ((W - 90) / n < 60 ? 56 : 26);

  function drierShading(by, box, band, labels, parts) {
    (by.drier_runs || []).forEach((run) => {
      const a = by.years.findIndex((y) => y.year === run.first), b = by.years.findIndex((y) => y.year === run.last);
      if (a < 0 || b < 0) return;
      const x0 = box.left + band * a + 1, x1 = box.left + band * (b + 1) - 1;
      parts.push(rect(x0, box.top, x1 - x0, box.bottom - box.top, "var(--straw)"));
      if (labels) {
        const long = "drier years " + run.label;
        parts.push(text((x0 + x1) / 2, box.top - 6, textWidth(long) < x1 - x0 + 30 ? long : "drier", "pc-axis-strong", "middle"));
      }
    });
  }

  function skillSvg(W) {
    const by = proof.by_year, years = by.years;
    const maxV = Math.max(0.35, ...years.map((y) => (y.skill_ci ? y.skill_ci[1] : y.skill) + 0.02));
    const box = { left: 70, right: W - 8, top: 50, bottom: 240 };
    const H = box.bottom + yearAxisRoom(W, years.length);
    const y = (v) => box.bottom - (Math.max(0, Math.min(v, maxV)) / maxV) * (box.bottom - box.top);
    const parts = [];
    const band = (box.right - box.left) / years.length;
    drierShading(by, box, band, true, parts);
    [[0, "none"], [0.1, "a tenth"], [0.2, "a fifth"], [0.3, "3 tenths"]].forEach(([v, words]) => {
      parts.push(line(box.left, y(v), box.right, y(v), "var(--line)", 1));
      parts.push(text(box.left - 8, y(v) + 4, words, "pc-axis", "end"));
    });
    const bw = Math.min(24, band * 0.5);
    years.forEach((yr, i) => {
      const cx = box.left + band * (i + 0.5);
      parts.push(rect(cx - bw / 2, y(yr.skill), bw, box.bottom - y(yr.skill), "var(--ink-2)", ' rx="3"'));
      if (yr.skill_ci) {
        // the range, both ends capped: light where it runs inside the bar, ink above it, so both ends show
        const lo = y(yr.skill_ci[0]), hi = y(yr.skill_ci[1]), top = y(yr.skill);
        const cap = Math.min(5, bw / 2 - 1.5);
        parts.push(line(cx, lo, cx, top, "var(--surface)", 1.8));
        parts.push(line(cx - cap, lo, cx + cap, lo, "var(--surface)", 1.8));
        parts.push(line(cx, top, cx, hi, "var(--ink)", 1.8));
        parts.push(line(cx - 5, hi, cx + 5, hi, "var(--ink)", 1.8));
      }
      parts.push(hit("rect", 'x="' + r1(cx - band / 2) + '" y="' + box.top + '" width="' + r1(band) + '" height="' + (box.bottom - box.top) + '"',
        yr.words + (yr.drier ? " (a drier year)" : "") + ": " + yr.skill_words + " less error than guessing the usual rate; " +
        count(yr.forecasts) + " forecasts, " + count(yr.fell) + " fell below a third"));
    });
    yearAxis(years, box, H, parts);
    const all = by.all_years;
    parts.push(line(box.left, y(all.skill), box.right, y(all.skill), "var(--ink-2)", 1.5, ' stroke-dasharray="6 4"'));
    parts.push(line(0, 14, 22, 14, "var(--ink-2)", 1.5, ' stroke-dasharray="6 4"'));
    parts.push(text(28, 18, "all " + years.length + " years: " + all.skill_words + " less", "pc-axis-strong", "start"));
    const summary = "Less error than guessing the usual rate, each July-June year: " +
      years.map((yr) => yr.label + " " + yr.skill_words + (yr.drier ? " (drier)" : "")).join("; ");
    return svg("pc-years", W, H, summary, parts);
  }

  function floorSvg(W) {
    const by = proof.by_year, years = by.years;
    const held = years.map((yr) => yr.floor.held_in_1000);
    const target = Math.round(by.floor_target * 1000), tol = Math.round(by.floor_tolerance * 1000);
    const lo = Math.min(850, Math.floor((Math.min(...held) - 10) / 10) * 10), hi = Math.max(950, Math.ceil((Math.max(...held) + 10) / 10) * 10);
    const box = { left: 46, right: W - 8, top: 46, bottom: 196 };
    const H = box.bottom + yearAxisRoom(W, years.length);
    const y = (v) => box.bottom - ((Math.max(lo, Math.min(v, hi)) - lo) / (hi - lo)) * (box.bottom - box.top);
    const parts = [];
    const band = (box.right - box.left) / years.length;
    drierShading(by, box, band, false, parts);
    // the on-target band in water blue, so it reads over the straw of the drier years
    parts.push(rect(box.left, y(target + tol), box.right - box.left, y(target - tol) - y(target + tol), "var(--water)", ' fill-opacity=".16"'));
    for (let v = Math.ceil(lo / 20) * 20; v <= hi; v += 20) {
      parts.push(line(box.left, y(v), box.right, y(v), "var(--line)", 1));
      parts.push(text(box.left - 8, y(v) + 4, String(v), "pc-axis", "end"));
    }
    parts.push(line(box.left, y(target), box.right, y(target), "var(--ink-2)", 1.5, ' stroke-dasharray="6 4"'));
    // key, above the plot
    parts.push(line(0, 12, 22, 12, "var(--ink-2)", 1.5, ' stroke-dasharray="6 4"'));
    parts.push(text(28, 16, "target " + target, "pc-axis-strong", "start"));
    const kx = 28 + textWidth("target " + target) + 18;
    parts.push(rect(kx, 4, 22, 14, "var(--water)", ' fill-opacity=".16"'));
    parts.push(text(kx + 28, 16, "on target: " + (target - tol) + " to " + (target + tol), "pc-axis", "start"));
    const lowest = Math.min(...held), highest = Math.max(...held);
    years.forEach((yr, i) => {
      const cx = box.left + band * (i + 0.5), v = yr.floor.held_in_1000, cy = y(v);
      parts.push('<circle cx="' + r1(cx) + '" cy="' + r1(cy) + '" r="5.5" fill="var(--ink)" stroke="var(--surface)" stroke-width="2"/>');
      // the lowest and highest year named as such; with no room for the words beside a narrow year, the number alone
      const wide = band >= 64;
      if (v === lowest) parts.push(text(cx, cy + 20, String(v) + (wide ? " (lowest)" : ""), "pc-axis-strong pc-halo", "middle"));
      else if (v === highest) parts.push(text(cx, cy - 11, String(v) + (wide ? " (highest)" : ""), "pc-axis-strong pc-halo", "middle"));
      parts.push(hit("rect", 'x="' + r1(cx - band / 2) + '" y="' + box.top + '" width="' + r1(band) + '" height="' + (box.bottom - box.top) + '"',
        yr.words + ": our days-left number held " + v + " times in 1,000 (" + count(yr.floor.judged) + " judged forecasts)"));
    });
    yearAxis(years, box, H, parts);
    const summary = "How often our days-left number held, in 1,000, each July-June year: " +
      years.map((yr) => yr.label + " " + yr.floor.held_in_1000).join("; ");
    return svg("pc-floor", W, H, summary, parts);
  }

  function quarterTicks(from, to) {
    const out = [];
    const s = new Date(from + "T00:00:00Z"), e = new Date(to + "T00:00:00Z");
    for (let d = new Date(Date.UTC(s.getUTCFullYear(), s.getUTCMonth(), 1)); d <= e; d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 3, 1))) {
      const iso = d.toISOString().slice(0, 10);
      if (iso >= from) out.push({ iso, month: K.MONTHS[d.getUTCMonth()], year: d.getUTCFullYear(), jan: d.getUTCMonth() === 0 });
    }
    return out;
  }
  function timeAxis(x, from, to, bottom, parts, labels) {
    quarterTicks(from, to).forEach((t, i) => {
      const px = x(t.iso);
      parts.push(line(px, bottom, px, bottom + 4, "var(--ink-3)", 1));
      if (!labels) return;
      parts.push(text(px, bottom + 18, t.month, "pc-axis", "middle"));
      if (t.jan || i === 0) parts.push(text(px, bottom + 34, String(t.year), "pc-axis", "middle"));
    });
  }

  function levelSvg(W, dam, part) {
    const from = part.season.forecasts_from, to = part.season.show_to;
    const d0 = K.dayNo(from), d1 = K.dayNo(to);
    const left = 62, right = W - 8;
    const x = (iso) => left + ((K.dayNo(iso) - d0) / (d1 - d0)) * (right - left);
    // the "fell 5 Jan" labels: own rows above the plot, each centred on its line, never overlapping
    const rows = [];
    const labels = dam.falls.map((day) => {
      const t = "fell " + short(day), w = textWidth(t) + 8;
      const cx = Math.max(left + w / 2, Math.min(right - w / 2, x(day)));
      let row = rows.findIndex((taken) => taken.every(([a, b]) => cx + w / 2 < a || cx - w / 2 > b));
      if (row < 0) { rows.push([]); row = rows.length - 1; }
      rows[row].push([cx - w / 2, cx + w / 2]);
      return { day, t, cx, row };
    });
    const box = { left, right, top: 14 + rows.length * 17, bottom: 160 + rows.length * 17 };
    const H = box.bottom + 42;
    const maxPct = 140;
    const y = (pct) => box.bottom - (Math.min(pct, maxPct) / maxPct) * (box.bottom - box.top);
    const parts = [];
    const seasonEnd = x(part.season.forecasts_to);
    parts.push(rect(box.left, y(part.threshold_pct), box.right - box.left, box.bottom - y(part.threshold_pct), "var(--straw)"));
    parts.push(rect(seasonEnd, box.top, box.right - seasonEnd, box.bottom - box.top, "var(--ink)", ' fill-opacity=".05"'));
    [[0, "0% full"], [part.threshold_pct, "a third"], [100, "full"]].forEach(([v, words]) => {
      const strong = v === part.threshold_pct;
      parts.push(line(box.left, y(v), box.right, y(v), strong ? "var(--ink-3)" : "var(--line)", strong ? 1.5 : 1));
      parts.push(text(box.left - 8, y(v) + 4, words, strong ? "pc-axis-strong" : "pc-axis", "end"));
    });
    const pts = dam.looks.filter((l) => l[1] !== null).map((l) => [x(l[0]), y(l[1]), l]);
    if (pts.length) {
      const area = [[pts[0][0], box.bottom]].concat(pts.map((p) => [p[0], p[1]]), [[pts[pts.length - 1][0], box.bottom]]);
      parts.push('<polygon points="' + area.map((p) => r1(p[0]) + "," + r1(p[1])).join(" ") + '" fill="var(--water)" fill-opacity=".12"/>');
      parts.push('<polyline points="' + pts.map((p) => r1(p[0]) + "," + r1(p[1])).join(" ") +
        '" fill="none" stroke="var(--water)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>');
      pts.forEach((p) => {
        parts.push('<circle cx="' + r1(p[0]) + '" cy="' + r1(p[1]) + '" r="2.4" fill="var(--water)"/>');
        parts.push(hit("circle", 'cx="' + r1(p[0]) + '" cy="' + r1(p[1]) + '" r="7"', fmtDate(p[2][0]) + ": " + D.format.fullness(p[2][1])));
      });
    }
    labels.forEach((l) => parts.push(line(x(l.day), 16 + l.row * 17, x(l.day), box.bottom, "var(--ink)", 1.5)));
    labels.forEach((l) => parts.push(text(l.cx, 12 + l.row * 17, l.t, "pc-axis-strong pc-halo", "middle")));   // over every line
    timeAxis(x, from, to, box.bottom, parts, true);
    const summary = "How full " + dam.name + " was, " + fmtDate(from) + " to " + fmtDate(to) + ". " +
      (dam.falls.length ? "Fell below a third on " + dam.falls.map(fmtDate).join(", ") + "." : "Did not fall below a third.");
    return svg("pc-level", W, H, summary, parts);
  }

  function forecastSvg(W, dam, part) {
    const box = { left: 62, right: W - 8, top: 10, bottom: 120 };
    const H = box.bottom + 42;
    const from = part.season.forecasts_from, to = part.season.show_to;
    const d0 = K.dayNo(from), d1 = K.dayNo(to);
    const x = (iso) => box.left + ((K.dayNo(iso) - d0) / (d1 - d0)) * (box.right - box.left);
    const y = (v) => box.bottom - v * (box.bottom - box.top);
    const parts = [];
    const seasonEnd = x(part.season.forecasts_to);
    parts.push(rect(seasonEnd, box.top, box.right - seasonEnd, box.bottom - box.top, "var(--ink)", ' fill-opacity=".05"'));
    [[0, "none"], [0.5, "5 in 10"], [1, "10 in 10"]].forEach(([v, words]) => {
      parts.push(line(box.left, y(v), box.right, y(v), "var(--line)", 1));
      parts.push(text(box.left - 8, y(v) + 4, words, "pc-axis", "end"));
    });
    dam.falls.forEach((day) => parts.push(line(x(day), box.top, x(day), box.bottom, "var(--ink)", 1.5)));
    dam.forecasts.forEach((f) => {
      const px = x(f.date), py = y(f.chance);
      parts.push(line(px, box.bottom, px, py, "var(--line-strong)", 1.2));
      const fill = f.fell === true ? "var(--c3)" : f.fell === false ? "var(--surface)" : "var(--c-none)";
      const stroke = f.fell === null ? "var(--c-none)" : "var(--c3)";
      parts.push('<circle cx="' + r1(px) + '" cy="' + r1(py) + '" r="4.5" fill="' + fill + '" stroke="' + stroke + '" stroke-width="2"/>');
      const what = f.fell === true ? "It fell below a third on " + fmtDate(f.fell_on) + "."
        : f.fell === false ? "It did not fall below a third within 90 days." : "The answer is not known.";
      parts.push(hit("rect", 'x="' + r1(px - 5) + '" y="' + box.top + '" width="10" height="' + (box.bottom - box.top) + '"',
        fmtDate(f.date) + ": " + chance(f.chance) + " that it falls below a third within 90 days. " + what));
    });
    timeAxis(x, from, to, box.bottom, parts, true);
    const summary = dam.name + ": " + dam.forecasts.length + " forecasts. " + dam.summary;
    return svg("pc-forecasts", W, H, summary, parts);
  }

  const CHARTS = {
    said: (W) => saidSvg(W),
    skill: (W) => skillSvg(W),
    floor: (W) => floorSvg(W),
    level: (W, el) => { const part = proof.dam_by_dam; const dam = part.dams.find((d) => d.dam_id === el.dataset.dam); return dam ? levelSvg(W, dam, part) : ""; },
    forecasts: (W, el) => { const part = proof.dam_by_dam; const dam = part.dams.find((d) => d.dam_id === el.dataset.dam); return dam ? forecastSvg(W, dam, part) : ""; },
  };

  function drawCharts(scope, onlyChanged) {
    (scope || document).querySelectorAll("[data-chart]").forEach((el) => {
      const W = Math.floor(el.clientWidth);
      if (!W || !CHARTS[el.dataset.chart]) return;
      if (onlyChanged && Math.abs(W - (+el.dataset.w || 0)) < 4) return;
      el.dataset.w = W;
      try { el.innerHTML = CHARTS[el.dataset.chart](W, el); } catch (e) { console.error(e); }
      if (el.dataset.chart === "said") countsClause(el.closest(".ps"));
    });
  }

  // =====================================================================
  // The picture sheets
  // =====================================================================
  const numbersDetails = (inner, label) => '<details class="more ps-numbers" data-numbers><summary>' + icon("i-chart") +
    esc(label || "Show the numbers") + plus() + '</summary><div class="body">' + inner + "</div></details>";
  const specialistsDetails = (inner) => (inner ? '<details class="more ps-spec" data-specialists><summary>' + icon("i-info") +
    "For specialists" + plus() + '</summary><div class="body">' + inner + "</div></details>" : "");
  const techList = (items) => (items.length ? '<ul class="ps-list">' + items.map((t) => "<li>" + esc(t) + "</li>").join("") + "</ul>" : "");
  /** A plain table; one with more than three columns stacks into one block per row on phones (proof.css). */
  const table = (head, rows) => {
    const wide = head.length > 3;
    return '<div class="table-scroll' + (wide ? " ps-stack" : "") + '"><table class="data" role="table"><thead role="rowgroup"><tr role="row">' +
      head.map((h) => '<th scope="col" role="columnheader">' + esc(h) + "</th>").join("") + '</tr></thead><tbody role="rowgroup">' +
      rows.map((r) => '<tr role="row">' + r.map((c, i) => (i ? '<td role="cell" data-label="' + esc(head[i]) + '">' + c + "</td>"
        : '<th scope="row" role="rowheader">' + c + "</th>")).join("") + "</tr>").join("") + "</tbody></table></div>";
  };

  /** "about 6 in 10", but "less than 1 in 10" / "more than 9 in 10" as they are (never "about less than"). */
  function aboutChance(v) {
    const words = chance(v);
    return /^(less|more) than/.test(words) ? words : "about " + words;
  }

  // On a narrow chart the counts under each group are left out (saidSvg): the caption then points to the table.
  const COUNTS_CLAUSE = /;\s*the number of forecasts is under each group/;
  let saidCounts = true;
  function countsClause(scope) {
    const el = (scope || document).querySelector("[data-counts-clause]");
    if (el) el.textContent = saidCounts ? "; the number of forecasts is under each group" : "; the number of forecasts in each group is in Show the numbers below";
  }

  /** Why this picture's count differs from the Proof hero's: these are October-to-March chances; the days were checked on every forecast. */
  function scopeHtml() {
    const all = proof.by_year && proof.by_year.all_years;
    if (!proof.test || typeof proof.test.forecasts !== "number") return "";
    // the question the test asked, as proof.json says it ("The question: will this farm dam fall below a third ...?")
    const question = K.sentences(proof.test.intro || "").find((s) => /^The question:/i.test(s));
    return (question ? '<p class="ps-note">' + esc(question) + "</p>" : "") +
      '<p class="ps-note">These are the ' + count(proof.test.forecasts) + " October-to-March forecasts, when dams run down" +
      (all && typeof all.floor_judged === "number" ? "; the days-left number on the Proof page was checked on every forecast, all months (" +
        count(all.floor_judged) + ")" : "") + ".</p>";
  }

  function saidHtml() {
    const cal = proof.calibration;
    const how = K.plainSplit(cal.how_to_read), lean = K.plainSplit(cal.lean);
    const nw = (t) => '<span class="nowrap">' + esc(t) + "</span>";     // "175 in 1,000" never splits across lines
    const rows = cal.bins.map((b) => [esc(b.said) + (b.plotted ? "" : " (not drawn)"), count(b.forecasts), count(b.fell),
      nw(D.format.inThousandText(b.share_fell)) + " " + nw("(" + aboutChance(b.happened_in_ten / 10) + ")"),
      nw(D.format.inThousandText(b.mean_chance)),
      b.share_fell_ci ? count(D.format.inThousand(b.share_fell_ci[0])) + " to " + count(D.format.inThousand(b.share_fell_ci[1])) : "-"]);
    return '<article class="ps">' +
      '<p class="eyebrow">1 · ' + esc(cal.title) + "</p>" +
      '<h2 class="ps-h">' + esc(cal.takeaway) + "</h2>" +
      '<p class="ps-lead">' + esc(cal.detail) + "</p>" + scopeHtml() +
      '<figure class="ps-fig"><figcaption class="ps-fig-h">Each dot: the forecasts that gave one chance, and how often those dams fell below a third within 90 days</figcaption>' +
      '<div class="ps-chart" data-chart="said"></div></figure>' +
      '<p class="ps-note">' + esc(how.plain).replace(COUNTS_CLAUSE, (m) => "<span data-counts-clause>" + m + "</span>") + "</p>" +
      '<p class="ps-note">' + esc(lean.plain) + "</p>" +
      (cal.not_plotted ? '<p class="ps-note">' + esc(cal.not_plotted) + "</p>" : "") +
      '<div class="ps-more">' + numbersDetails(table(["We said", "Forecasts", "Fell below a third within 90 days", "What happened",
        "Average chance given", "Range, re-drawing the dams (in 1,000)"], rows)) +
      specialistsDetails(techList(how.tech.concat(lean.tech))) + "</div></article>";
  }

  function yearsHtml() {
    const by = proof.by_year;
    const [h, rest] = K.headAndRest(by.takeaway);
    const note = K.plainSplit(by.skill_note);
    const region = (r) => ({ nsw_cw: "NSW", wvic_sesa: "Vic-SA" }[r] || r);
    const rows = by.years.map((yr) => ['<span class="nowrap">' + esc(yr.label) + "</span>" + (yr.drier ? " (drier)" : ""), count(yr.forecasts), count(yr.fell),
      esc(yr.skill_words) + " less", yr.rain_vs_usual_mean.toFixed(2) + " of usual (" +
        Object.keys(yr.rain_vs_usual).map((r) => region(r) + " " + yr.rain_vs_usual[r].toFixed(2)).join(", ") + ")",
      yr.floor.held_in_1000 + " in 1,000 (" + count(yr.floor.judged) + ")"]);
    const all = by.all_years;
    rows.push(["All " + by.years.length + " years", count(proof.test.forecasts), count(proof.test.fell), esc(all.skill_words) + " less", "-",
      D.format.inThousand(all.floor_held) + " in 1,000 (" + count(all.floor_judged) + ")"]);
    const specRows = by.years.map((yr) => [esc(yr.label), signed(yr.skill, 3) + (yr.skill_ci ? "; " + signed(yr.skill_ci[0], 3) + " to " + signed(yr.skill_ci[1], 3) : "")]);
    specRows.push(["All " + by.years.length + " years", signed(all.skill, 3) + (all.skill_ci ? "; " + signed(all.skill_ci[0], 3) + " to " + signed(all.skill_ci[1], 3) : "")]);
    return '<article class="ps">' +
      '<p class="eyebrow">2 · ' + esc(by.title) + "</p>" +
      '<h2 class="ps-h">' + esc(h) + "</h2>" + (rest ? '<p class="ps-lead">' + esc(rest) + "</p>" : "") +
      '<figure class="ps-fig"><figcaption class="ps-fig-h">Less error than guessing the usual rate, each July-June year</figcaption>' +
      '<div class="ps-chart" data-chart="skill"></div></figure>' +
      '<p class="ps-note">' + esc(note.plain) + "</p>" + '<p class="ps-note">' + esc(by.drier_rule) + "</p>" +
      '<h3 class="ps-h3">' + esc(K.plainWords(by.floor_takeaway)) + "</h3>" +
      '<p class="ps-lead">' + esc(K.plainWords(by.floor_detail)) + "</p>" +
      '<figure class="ps-fig"><figcaption class="ps-fig-h">How often our days-left number held, out of 1,000 forecasts, each July-June year</figcaption>' +
      '<div class="ps-chart" data-chart="floor"></div></figure>' +
      '<p class="ps-note">' + esc(K.plainWords(by.floor_note)) + "</p>" + '<p class="ps-note">' + esc(by.refit_note) + "</p>" +
      '<div class="ps-more">' + numbersDetails(table(["July-June year", "Forecasts (Oct-Mar)", "Fell below a third",
        "Less error than the usual guess", "Rain, both regions", "Days-left number held (judged)"], rows)) +
      specialistsDetails(techList(note.tech) + "<p>Skill against the usual rate for that region and month, with its range " +
        "(re-drawing that year's dams at random 500 times):</p>" + table(["July-June year", "Skill; range"], specRows)) +
      "</div></article>";
  }

  function damNumber(d) { const m = /(\d+)/.exec(d.name || ""); return m ? m[1] : d.dam_id; }

  function damDetailHtml() {
    const part = proof.dam_by_dam;
    const dam = part.dams.find((d) => d.dam_id === selectedDam) || part.dams[0];
    const anyUnknown = dam.forecasts.some((f) => f.fell === null);
    const key = (svgInner) => '<svg width="22" height="14" viewBox="0 0 22 14" aria-hidden="true" focusable="false">' + svgInner + "</svg>";
    const legend = '<ul class="ps-legend">' +
      "<li>" + key('<path d="M1 9 L8 4 L14 8 L21 3" fill="none" stroke="var(--water)" stroke-width="2"/>') + "how full at each clear look</li>" +
      "<li>" + key('<rect x="0" y="2" width="22" height="10" fill="var(--straw)"/>') + "below a third</li>" +
      "<li>" + key('<line x1="11" y1="0" x2="11" y2="14" stroke="var(--ink)" stroke-width="2"/>') + "fell below a third</li>" +
      "<li>" + key('<circle cx="11" cy="7" r="5" fill="var(--c3)" stroke="var(--c3)" stroke-width="2"/>') + "forecast followed by a fall within 90 days</li>" +
      "<li>" + key('<circle cx="11" cy="7" r="5" fill="var(--surface)" stroke="var(--c3)" stroke-width="2"/>') + "forecast that was not</li>" +
      (anyUnknown ? "<li>" + key('<circle cx="11" cy="7" r="5" fill="var(--c-none)"/>') + "answer not known</li>" : "") +
      "<li>" + key('<rect x="0" y="0" width="22" height="14" fill="var(--ink)" fill-opacity=".08"/>') + "after the season's last forecast</li></ul>";
    const rows = dam.forecasts.map((f) => [esc(fmtDate(f.date)), esc(chance(f.chance)),
      f.fell === true ? "fell below a third, " + esc(fmtDate(f.fell_on)) : f.fell === false ? "did not" : "not known"]);
    return '<p class="ps-dam-summary">' + esc(dam.summary) + " " + esc(String(dam.area_ha)) + " ha when full.</p>" + legend +
      '<figure class="ps-fig"><figcaption class="ps-fig-h">' + esc(dam.name) + ": how full at each clear satellite look</figcaption>" +
      '<div class="ps-chart" data-chart="level" data-dam="' + esc(dam.dam_id) + '"></div></figure>' +
      '<figure class="ps-fig"><figcaption class="ps-fig-h">Each forecast: the chance it falls below a third within 90 days</figcaption>' +
      '<div class="ps-chart" data-chart="forecasts" data-dam="' + esc(dam.dam_id) + '"></div></figure>' +
      '<div class="ps-more">' + numbersDetails(table(["Forecast made on", "Chance it falls below a third within 90 days", "Within those 90 days"], rows),
        "Show the numbers for " + dam.name) + "</div>";
  }

  function damsHtml() {
    const part = proof.dam_by_dam;
    const how = K.plainSplit(K.plainWords(part.how_to_read));
    // "Dam 1 ... is shown first; pick any of its dams" is an instruction the chooser already gives.
    const chosen = K.sentences(String(part.how_chosen || "").replace(/\((Farm [A-Z]) \(near ([^)]+)\): /, "($1, near $2: "))
      .filter((s) => !/\bfirst\b/i.test(s)).join(" ");
    // each dam as it stood on the Rewind date: its chance, and what happened within 90 days (proof.json dams[].rewind)
    const within = (rw) => {
      if (!rw) return "no look that day";
      // (the chance column already says "no forecast": here, why)
      if (rw.status === "already_low") return "already below a third";
      if (rw.status === "not_refilled") return "not refilled lately";
      if (rw.status !== "forecast") return "no recent clear look";
      return rw.outcome === true ? "fell below a third, " + fmtDate(rw.outcome_date)
        : rw.outcome === false ? "stayed above a third" : "not known";
    };
    const chooser = part.dams.map((d) => {
      const rw = d.rewind || null, fc = rw && rw.status === "forecast" && rw.chance !== null && rw.chance !== undefined;
      return '<button type="button" class="ps-pick-row' + (fc && rw.outcome === true ? " is-fell" : "") + '" data-ps-dam="' + esc(d.dam_id) +
        '" aria-pressed="' + (d.dam_id === selectedDam) + '">' +
        '<span class="pk-name">' + esc(d.name) + "</span>" +
        '<span class="pk-ch">' + (fc ? K.dots(rw.chance, 5, chance(rw.chance), true).replace(/role="img" aria-label="[^"]*"/, 'aria-hidden="true"') +
          "<b>" + esc(chance(rw.chance)) + "</b>" : '<span class="pk-none">no forecast</span>') + "</span>" +
        '<span class="pk-out">' + esc(within(rw)) + "</span></button>";
    }).join("");
    const pickCap = part.rewind_date ? esc(part.farm.name) + " on " + esc(fmtDate(part.rewind_date)) + ", as in Rewind. Pick a dam to see its whole season."
      : "Pick a dam to see its whole season.";
    return '<article class="ps">' +
      '<p class="eyebrow">4 · ' + esc(part.title) + "</p>" +
      '<h2 class="ps-h">' + esc(damsHeading()) + "</h2>" +
      '<p class="ps-lead">' + esc(String(part.takeaway || "").replace(/\bthe (\w+) dams on one farm, /, "the $1 dams with a forecast on one farm, ")) + "</p>" +
      '<div class="ps-picker" role="group" aria-labelledby="ps-pick-cap"><p class="ps-pick-cap" id="ps-pick-cap">' + pickCap + "</p>" +
      '<div class="ps-pick-head" aria-hidden="true"><span>Dam</span><span>Its chance that day</span><span>Within 90 days</span></div>' +
      chooser + "</div>" +
      '<div id="ps-dam" class="ps-dam" aria-live="polite">' + damDetailHtml() + "</div>" +
      '<p class="ps-note">' + esc(how.plain) + "</p>" + (chosen ? '<p class="ps-note">' + esc(chosen) + "</p>" : "") +
      specialistsDetails(techList(how.tech)) +
      '<div class="linkrows"><a class="linkrow" href="#proof/rewind" data-replace>' + icon("i-rewind") +
      "<span>" + esc(D.replay && D.replay.label ? D.replay.label(data) : "Rewind") +
      "<small>The same farm on " + numberWord((part.rewind_dates || []).length || 3) + " dates: what it said, then what happened</small></span>" +
      '<span class="chev">' + icon("i-chev") + "</span></a></div></article>";
  }

  function selectDam(id, scope) {
    const part = proof.dam_by_dam;
    if (!part.dams.some((d) => d.dam_id === id)) return;
    selectedDam = id;
    const body = scope || D.sheet.body();
    body.querySelectorAll("[data-ps-dam]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.psDam === id)));
    const box = body.querySelector("#ps-dam");
    if (box) { box.innerHTML = damDetailHtml(); drawCharts(box); }
  }

  // =====================================================================
  // Sheets: which ones, in what order, and what each holds
  // =====================================================================
  const SHEETS = {
    said: { ok: () => Boolean(proof && proof.calibration), title: () => proof.calibration.title, html: saidHtml },
    years: { ok: () => Boolean(proof && proof.by_year), title: () => proof.by_year.title, html: yearsHtml },
    rewind: { ok: () => Boolean(D.replay && D.replay.available && D.replay.available(data)), title: () => (D.replay.label ? D.replay.label(data) : "Rewind"), html: null },
    dams: { ok: () => Boolean(proof && proof.dam_by_dam), title: () => proof.dam_by_dam.title, html: damsHtml },
    exam: { ok: () => Boolean(sealedPanel() || proof), title: () => "The unseen exam", html: examSheetHtml },
  };
  const PICTURES = ["said", "years", "rewind", "dams"];

  function pagerHead(sub) {
    const list = PICTURES.filter((s) => SHEETS[s].ok());
    const i = list.indexOf(sub);
    if (i < 0 || list.length < 2) return undefined;
    const prev = list[(i - 1 + list.length) % list.length], next = list[(i + 1) % list.length];
    return { prev: { href: "#proof/" + prev, label: "Previous picture: " + SHEETS[prev].title() },
             next: { href: "#proof/" + next, label: "Next picture: " + SHEETS[next].title() } };
  }

  /** The third address part: numbers, specialists, dam-N. */
  function applyDeep(body, deep, sub) {
    if (!deep || !body) return;
    const m = /^dam-(\d+)$/.exec(deep);
    if (m && sub === "dams") {
      const d = proof.dam_by_dam.dams.find((x) => damNumber(x) === m[1]);
      if (d) selectDam(d.dam_id, body);
      return;
    }
    const target = deep === "numbers" ? body.querySelector("details[data-numbers]")
      : deep === "specialists" ? body.querySelector("details[data-specialists]") : null;
    if (!target) return;
    target.open = true;
    requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
  }

  function wireSheet() {
    if (wired) return;
    wired = true;
    D.sheet.body().addEventListener("click", (event) => {
      const b = event.target.closest("[data-ps-dam]");
      if (b && openSub === "dams") { event.preventDefault(); selectDam(b.dataset.psDam); }
    });
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (!openSub || !D.sheet.isOpen()) return;
        if (openSub === "rewind") { if (D.replay && D.replay.resize) D.replay.resize(); return; }
        drawCharts(D.sheet.body(), true);
      }, 150);
    });
  }

  function openSheet(r) {
    const sub = r.sub;
    const spec = SHEETS[sub];
    const tok = ++sheetToken;
    openSub = sub;
    openDeep = r.deep;
    if (sub === "dams") selectedDam = proof.dam_by_dam.default_dam;
    const isRewind = sub === "rewind";
    const body = D.sheet.open({
      title: spec.title(),
      head: pagerHead(sub),
      body: isRewind ? '<div class="view-skeleton" aria-hidden="true"><span class="skel skel-title"></span><span class="skel skel-card"></span></div>' : spec.html(),
      split: false,
      // desktop: the pictures' charts and tables get the room they need (880 px), as the old full-width page had
      wide: "wide",
      onClose() {
        if (isRewind && D.replay && D.replay.cleanup) D.replay.cleanup();
        if (tok === sheetToken) { openSub = null; openDeep = null; }
      },
    });
    wireSheet();
    if (isRewind) {
      return getData(["first", "rewind"]).then((d) => {
        if (tok !== sheetToken || !D.sheet.isOpen()) return;
        D.replay.render(body, d, r);
      }, () => {
        if (tok === sheetToken) body.innerHTML = loadErrorHtml();
      });
    }
    drawCharts(body);
    applyDeep(body, r.deep, sub);
    return null;
  }

  /** A part of the data did not load: offline, the "not saved on this phone yet" words (pwa.js); else "check your signal". */
  function loadErrorHtml() {
    const e = D.pwa && typeof D.pwa.loadErrorText === "function" ? D.pwa.loadErrorText() : null;
    const title = e && e.title ? e.title : "The forecast data could not be loaded.";
    const text = e && e.body ? e.body : "Check your signal and try again.";
    return '<div class="load-error" role="alert"><p><strong>' + esc(title) + "</strong> " + esc(text) + "</p>" +
      '<button class="btn btn-primary" type="button" data-retry>Try again</button></div>';
  }

  // =====================================================================
  // The router's view
  // =====================================================================
  function render(root, route) {
    params = (route && route.params) || {};
    return getData("first").then((loaded) => {
      data = loaded;
      proof = loaded.proof || null;
      if (proof && proof.dam_by_dam) selectedDam = proof.dam_by_dam.default_dam;
      root.innerHTML = pageHtml();
    });
  }

  function enter(r) {
    if (!r.sub) { openSub = null; openDeep = null; return null; }
    const spec = SHEETS[r.sub];
    if (!spec || !spec.ok()) { D.router.go("#proof", { replace: true }); return null; }
    if (openSub === r.sub && D.sheet.isOpen()) {
      // the same sheet, only the third part changed (numbers, a dam): no reopen, no jump to the top
      if (openDeep !== r.deep) { openDeep = r.deep; applyDeep(D.sheet.body(), r.deep, r.sub); }
      return null;
    }
    return openSheet(r);
  }

  function leave() { openSub = null; openDeep = null; }

  if (D.router && typeof D.router.register === "function") D.router.register("proof", { render, enter, leave });

  return { render, enter, leave, drawCharts };
})();
