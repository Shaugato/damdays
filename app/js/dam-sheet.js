/* dam-sheet.js (WP-D)
 * The dam sheet: one dam, one sheet (UI_SPEC 3.3, 5.11 to 5.14). It is the redesign of the old
 * dam card (js/dam-card.js), with every part of that card kept and each one at its level:
 *
 *   the sheet (one tap)     the dam's name, how far and how big; the HERO: at least N days before
 *                           it drops below a third, counted from the day of the text (cautious,
 *                           built to hold 9 times in 10); TILES: how full (the dam drawn from
 *                           above), the chance by the 90-day date (ten dots) and our record on
 *                           this dam ("held 380 of 428 times"); the per-dam note ("Runs wetter than
 *                           similar dams"); THE NEXT SIX MONTHS as ten-dot rows by date, with the
 *                           day of the text and the DamDays day marked, and the two-models sentence
 *   expanders (one more)    How is this counted? (in the hero) / See it as a chart (the six-month
 *                           chart with the DamDays day) / Season by season / How full since 1988 /
 *                           In this week's text / About these numbers
 *   states                  forecast, 6 months+, under a week, may be below a third now, already
 *                           below a third, no water seen (0%: "one look can be wrong"), not
 *                           refilled, no recent clear look, not enough history, a demo farm
 *                           outside the region the app holds, a past forecast (Rewind) before and
 *                           after the reveal
 *
 * Deep links (the router's route.deep): #farm/dam-2/counted, /curve, /record, /history, /text,
 * /about open that expander and scroll to it.
 *
 * API (research/ui/build/REQUESTS.md shows the farm view's and Runway's calls):
 *   DamDays.damSheet.open(opts) -> the sheet body element
 *     opts.dam       the dam: a farm dam from DamDays.text.damsForFarm / farms.json (number, name,
 *                    dam_id, distance_km, ...) or a region dam ({ dam_id })
 *     opts.dams      the list the pager steps through (wraps round); title "Dam 2 of 5"
 *     opts.hrefFor(d) the address of a dam of that list (default "#farm/dam-" + d.number; opts.href too)
 *     opts.deep      the expander to open ("counted" | "curve" | "record" | "history" | "text" | "about")
 *     opts.data      the prepared data (DamDays.data.load()); without it the sheet opens with a
 *                    skeleton and fills in when the data arrives
 *     opts.farm      the farm ({ name, sms, long, region_name, dams_in_app }) for "In this week's text"
 *     opts.inApp     false for a demo farm outside the region the app holds (no curve or history)
 *     opts.issueDate a past forecast's date ("2018-11-01", Rewind); opts.revealed shows what happened
 *     opts.title, opts.split, opts.onClose, opts.label   passed to DamDays.sheet.open
 *   DamDays.damSheet.fromRoute(route, ctx) -> true if it opened "dam-N" of ctx.dams
 *     ctx = { dams, data, farm, inApp, href }: what the farm view's enter(route) calls
 *   DamDays.damSheet.openRegion(damId, opts) -> a region dam by its id (Runway's map and list)
 *   DamDays.damSheet.html(data, opts) -> the sheet's content as HTML, for any other container;
 *   DamDays.damSheet.wire(el, data, opts) then draws its charts and opens opts.deep inside `el`
 *   DamDays.damSheet.managed = true      switches off the fallback below (set by the farm view's
 *                                        first open() on a #farm address)
 * Fallback: if a #farm/dam-N address shows no sheet (no farm view opened one), the sheet opens
 * Dam N of the default demo farm (?farm= or settings.defaultFarmId), so deep links always work.
 *
 * Wording (UI_SPEC section 1, founder decisions): "%" only means how full; a chance is "N in 10";
 * the headline is "at least N days before it drops below a third"; a 0% look is "no water seen";
 * the record is "held 198 of 222 times" over the last 10 years. Every number comes from the data.
 */
window.DamDays = window.DamDays || {};

DamDays.damSheet = (function () {
  "use strict";

  const D = window.DamDays;
  const DEEP = ["counted", "curve", "record", "history", "text", "about"];
  const DAM_PATH = "M20 31C23 15 45 9 63 13C81 17 92 31 89 51C86 72 72 89 50 88C28 87 12 74 11 55C10 45 16 39 20 31Z";

  const esc = (t) => (D.format && D.format.escapeHtml ? D.format.escapeHtml(t === null || t === undefined ? "" : t)
    : String(t === null || t === undefined ? "" : t).replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";"));
  const icon = (id, cls) => (D.icon ? D.icon(id, cls)
    : '<svg class="i' + (cls ? " " + cls : "") + '" aria-hidden="true" focusable="false"><use href="#' + id + '"/></svg>');
  const plus = () => icon("i-plus", "plus");
  const fmt = () => D.format;
  const txt = () => D.text;

  let current = null;      // { key, auto, hash, opts, model, body }
  let resizeTimer = 0;
  let lastWidth = 0;

  // ===========================================================================
  // Small wording helpers (same rules as js/text.js and js/format.js)
  // ===========================================================================
  const isNum = (v) => typeof v === "number" && !Number.isNaN(v);
  const short = (iso) => fmt().short(iso);                       // "13 Sep"
  const day = (iso) => fmt().dayShort(iso);                      // "Fri 2 Oct"
  const count = (n) => fmt().thousands(n);                       // "1,640"
  const chance = (c) => fmt().chance(c);                         // "3 in 10"
  /** The same words, kept together when they wrap: "less than" / "1 in 10" (HTML, escaped). */
  const chanceHtml = (c) => esc(chance(c)).replace(/(\d+) in 10$/, "$1&nbsp;in&nbsp;10");
  const fullness = (p) => fmt().fullness(p);                     // "~67% full", "full", "no water seen"
  const cap1 = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);
  function dayNo(iso) { return Math.round(Date.parse(String(iso).slice(0, 10) + "T00:00:00Z") / 86400000); }
  function capDays(m) { return (m.track && m.track.cap_days) || (txt() && txt().CAP_DAYS) || 180; }
  /** "13 Sep", or "26 Mar 2022" when the look is from another year than the text. */
  function lookDate(m) {
    if (!m.issuedOn) return "";
    return m.asOf && String(m.asOf).slice(0, 4) === String(m.issuedOn).slice(0, 4) ? short(m.issuedOn) : fmt().date(m.issuedOn);
  }
  function seasonLabel(year) { const y = Number(year); return y + "-" + String(y + 1).slice(-2); }
  function timesInTen(share) {
    if (D.damCard && D.damCard.timesInTen) return D.damCard.timesInTen(share);
    const t = txt().inTen(share);
    return t === 0 ? "less than once in 10" : t === 1 ? "about once in 10" : t === 10 ? "more than 9 times in 10" : "about " + t + " times in 10";
  }

  // ===========================================================================
  // The model: everything the sheet says about one dam, from the data
  // ===========================================================================
  function issueOf(data, issueDate) {
    if (!issueDate) return data.liveIssue || null;
    const issues = (data.forecasts && data.forecasts.issues) || [];
    return issues.find((i) => i.issue_date === issueDate) || null;
  }

  function build(data, opts) {
    const input = opts.dam || {};
    const id = input.dam_id;
    const issue = issueOf(data, opts.issueDate);
    const isLive = !opts.issueDate;
    const regionDam = data.damsById ? data.damsById.get(id) || null : null;
    const inApp = opts.inApp !== false && input.in_app !== false && Boolean(regionDam);
    const row = inApp && issue && issue.rowsByDam ? issue.rowsByDam.get(id) || null : null;
    // The farm dam's own copy (farms.json) is used only when the region rows do not hold the dam.
    const src = row || (isLive ? input : {});
    const farm = opts.farm || null;
    const m = {
      id,
      name: opts.name || input.name || (regionDam && regionDam.name) || id,
      number: input.number || null,
      mapName: regionDam ? regionDam.name : null,
      distanceKm: isNum(input.distance_km) ? input.distance_km : null,
      areaHa: isNum(input.area_ha) ? input.area_ha : regionDam ? regionDam.area_ha : null,
      deaUid: input.dea_uid || (regionDam && regionDam.dea_uid) || null,
      lat: isNum(input.lat) ? input.lat : regionDam ? regionDam.lat : null,
      lon: isNum(input.lon) ? input.lon : regionDam ? regionDam.lon : null,
      status: src.status || null,
      levelPct: isNum(src.level_pct) ? src.level_pct : null,
      issuedOn: src.issued_on || null,
      windowEnd: src.window_end || null,
      chance: isNum(src.chance) ? src.chance : null,
      low: row && isNum(row.chance_low) ? row.chance_low : isNum(input.chance_low) ? input.chance_low : null,
      high: row && isNum(row.chance_high) ? row.chance_high : isNum(input.chance_high) ? input.chance_high : null,
      notes: (row ? row.notes : input.notes) || [],
      damdaysDays: isNum(src.damdays_days) ? src.damdays_days : null,
      outcome: row ? row.outcome : null,
      outcomeDate: row ? row.outcome_date : null,
      isLive,
      issueDate: issue ? issue.issue_date : opts.issueDate || null,
      asOf: isLive ? (opts.textDate || data.textDate || (issue && issue.issue_date) || null) : opts.issueDate,
      inApp,
      outsideRegion: opts.inApp === false || (!regionDam && Boolean(farm && farm.dams_in_app === false)),
      farm,
      texts: farmTexts(opts, data, isLive ? (opts.textDate || data.textDate || null) : null),
      regionName: data.meta && data.meta.region ? data.meta.region.name : "",
      meta: data.meta || {},
      horizons: data.curveHorizons || [30, 60, 90, 180],
      curve: inApp && issue && typeof data.curveFor === "function" ? data.curveFor(issue.issue_date, id) : null,
      track: data.trackRecord || null,
      record: data.trackRecord && data.trackRecord.dams ? data.trackRecord.dams[id] || null : null,
      historyRange: data.history && data.history.first_month ? data.history : null,
      revealed: Boolean(opts.revealed),
      isMock: Boolean(data.meta && data.meta.is_mock),
      data,
    };
    m.kind = kindOf(m);
    m.since = m.asOf && m.issuedOn ? Math.max(0, dayNo(m.asOf) - dayNo(m.issuedOn)) : 0;
    m.daysLeft = m.kind === "forecast" ? m.damdaysDays - m.since : null;
    return m;
  }

  /** What the text can say about the dam on the day: forecast, low, not_refilled or no_look (js/text.js kind). */
  function kindOf(m) {
    if (!m.status) return "none";
    let k;
    try {
      k = txt().kind({ dam_id: m.id, issued_on: m.issuedOn, status: m.status }, m.asOf);
    } catch (e) {
      k = { forecast: "forecast", already_low: "low", not_refilled: "not_refilled" }[m.status] || "no_look";
    }
    if (k === "forecast" && !isNum(m.damdaysDays)) k = "no_look";
    return k;
  }

  // ===========================================================================
  // The dam seen from above (WP-C's DamDays.sketch.glyph when it is there)
  // ===========================================================================
  function glyph(m, size, decorative) {
    const dam = { name: m.name, number: m.number, level_pct: m.levelPct, issued_on: m.issuedOn,
                  status: m.kind === "low" ? "already_low" : m.status, kind: m.kind };
    if (D.sketch && typeof D.sketch.glyph === "function") {
      try { return D.sketch.glyph(dam, size, decorative); } catch (e) { /* draw our own */ }
    }
    const p = m.levelPct === null ? 0 : Math.min(m.levelPct, 100) / 100;
    const low = m.kind === "low";
    const label = m.name + " seen from above: " + fullness(m.levelPct) + (m.levelPct > 0 ? " of its usual water surface" : "");
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 100 100" ' +
      (decorative ? 'aria-hidden="true"' : 'role="img" aria-label="' + esc(label) + '"') + ' focusable="false">' +
      '<path d="' + DAM_PATH + '" fill="var(--dam-bed)" stroke="var(--dam-rim)" stroke-width="' + (low ? 5 : 4) + '"' +
      (low ? ' stroke-dasharray="10 8"' : "") + "/>" +
      (p > 0.004 ? '<path d="' + DAM_PATH + '" fill="var(--water)" transform="translate(64 70) scale(' +
        Math.sqrt(p).toFixed(3) + ') translate(-64 -70)"/>' : "") +
      '<path d="M34 86 Q52 95 74 84" fill="none" stroke="var(--earth)" stroke-width="6" stroke-linecap="round"/></svg>';
  }

  // ===========================================================================
  // The parts of the sheet
  // ===========================================================================
  function details(deep, ico, summary, body) {
    return '<details class="more ds-x" data-deep="' + deep + '"><summary>' + (ico ? icon(ico) : "") +
      "<span>" + summary + "</span>" + plus() + '</summary><div class="body">' + body + "</div></details>";
  }

  function headHtml(m) {
    const bits = [];
    if (m.distanceKm !== null) bits.push(txt().oneDecimal(m.distanceKm) + " km from the homestead");
    if (m.areaHa !== null) bits.push(m.areaHa.toFixed(1) + " ha when full");
    if (m.distanceKm === null && m.regionName && m.inApp) bits.push(m.regionName);
    const kicker = !m.isLive ? '<p class="eyebrow ds-kicker">Forecast made on ' + esc(fmt().date(m.issueDate)) + "</p>" : "";
    const mock = m.isMock ? ' <span class="tag ds-mock">Mock data</span>' : "";
    return '<header class="ds-head">' + kicker + '<h2 class="ds-title" id="ds-title">' + esc(m.name) + mock + "</h2>" +
      (bits.length ? '<p class="ds-meta">' + bits.map(esc).join(" &middot; ") + "</p>" : "") + "</header>";
  }

  /** The sentence about how full it was at that look, for the states without days. */
  function levelSentence(m) {
    if (m.levelPct === null) return "";
    if (m.levelPct <= 0) return "No water was seen at that look.";
    return cap1(fullness(m.levelPct)) + " at that look.";
  }

  function countedBody(m) {
    const look = lookDate(m);
    let first;
    if (m.since === 0) {
      first = "Counted from its last clear satellite look (" + look + ").";
    } else {
      const from = m.isLive ? day(m.asOf) : fmt().date(m.asOf) + ", the day of this forecast";
      const left = m.daysLeft >= capDays(m)
        ? fmt().count(m.daysLeft, "day") + ", shown as 6 months+ (the count stops at six months)"
        : m.daysLeft <= 0 ? "none left" : "at least " + fmt().count(m.daysLeft, "day");
      first = m.damdaysDays + " days from its last clear satellite look (" + look + "), less the " +
        fmt().count(m.since, "day") + " since: " + left + ", counted from " + from + ".";
    }
    const each = m.isLive ? " Each week's text counts from the day it is sent." : "";
    return "<p>" + esc(first + each) + "</p>" +
      "<p>A cautious count of days of water: the dam should stay above a third for at least this many days. " +
      "Across all dams in ten test years it held 9 times in 10, a little less often for spring looks.</p>";
  }

  function heroHtml(m) {
    const at = '<p class="eyebrow">At the ' + esc(lookDate(m)) + " satellite look</p>";
    const arm = isNum(m.meta.arm_level_pct) ? m.meta.arm_level_pct : 60;
    if (m.kind === "forecast") {
      const counted = details("counted", "i-info", "How is this counted?", countedBody(m));
      const fromWhen = '<p class="eyebrow">Counted from ' + esc(m.isLive ? day(m.asOf) : fmt().date(m.asOf)) + "</p>";
      if (m.daysLeft <= 0) {
        return '<section class="ds-hero is-low" aria-label="Days of water">' + fromWhen +
          '<h3 class="ds-state">May be below a third now</h3>' +
          '<p class="ds-caution">Its cautious days have run out since its last clear satellite look (' + esc(lookDate(m)) +
          "). The next clear look will tell.</p>" + counted + "</section>";
      }
      const big = m.daysLeft >= capDays(m)
        ? '<p class="ds-big is-cap"><span class="n">6 months+</span></p>'
        : '<p class="ds-big"><span class="pre">at least</span><span class="n">' + m.daysLeft + '</span><span class="post">' +
          (m.daysLeft === 1 ? "day" : "days") + "</span></p>";
      const soon = m.daysLeft < 7 ? '<p class="ds-soon">It could drop below a third within days.</p>' : "";
      return '<section class="ds-hero" aria-label="Days of water">' + fromWhen + big +
        '<p class="ds-before">before it drops below a third</p>' + soon +
        '<p class="ds-caution"><b>Cautious by design: built to hold 9 times in 10</b> across all dams, a little less ' +
        "often for spring looks, so it will most likely last longer.</p>" + counted + "</section>";
    }
    if (m.kind === "low") {
      if (m.levelPct !== null && m.levelPct <= 0) {
        return '<section class="ds-hero is-low" aria-label="At the last look">' + at + '<h3 class="ds-state">No water seen</h3>' +
          '<p class="ds-caution">Already below a third: the satellite saw no water at its last clear look. A satellite ' +
          "can miss a small pool, or muddy or green water, and one look can be wrong; the next look will tell.</p>" +
          '<p class="ds-caution">DamDays gives it days again once it refills to ' + arm + "% full.</p></section>";
      }
      return '<section class="ds-hero is-low" aria-label="At the last look">' + at + '<h3 class="ds-state">Already below a third</h3>' +
        '<p class="ds-caution">' + esc(levelSentence(m)) + " DamDays gives it days again once it refills to " + arm +
        "% full.</p></section>";
    }
    if (m.kind === "not_refilled") {
      return '<section class="ds-hero is-wait" aria-label="At the last look">' + at +
        '<h3 class="ds-state">No forecast until it refills</h3>' +
        '<p class="ds-caution">' + esc(levelSentence(m)) + " It has not been back to " + arm + "% full in the last six " +
        "months, so DamDays waits until it refills to " + arm + "% full before it counts days again.</p></section>";
    }
    const since = m.issuedOn ? "No clear satellite look since " + esc(lookDate(m)) + ", so no forecast right now."
      : "No clear satellite look lately, so no forecast right now.";
    return '<section class="ds-hero is-wait" aria-label="Satellite looks"><p class="eyebrow">Satellite looks</p>' +
      '<h3 class="ds-state">No recent clear look</h3><p class="ds-caution">' + since +
      " Clouds and gaps in the satellite record can hide a dam for weeks.</p></section>";
  }

  function fullTile(m, wide) {
    if (m.levelPct === null) return "";
    const look = m.issuedOn ? "at the " + esc(lookDate(m)) + " satellite look" : "at its last clear look";
    let big;
    let text;
    if (m.levelPct <= 0) {
      big = "No water seen";
      text = cap1(look) + ". The dashed edge is its usual full water surface; one look can be wrong.";
    } else if (m.levelPct >= 100) {
      big = fullness(m.levelPct);
      text = "At or above its usual full water surface " + look + ". Not depth.";
    } else {
      big = fullness(m.levelPct);
      text = "of its usual full water surface " + look + ". Not depth." +
        (m.kind === "low" ? " The dashed edge: below a third." : "");
    }
    if (wide) {
      return '<div class="ds-tile wide ds-full-wide"><div class="ds-glyph">' + glyph(m, 64, true) + "</div><div>" +
        '<p class="eyebrow">How full</p><p class="ds-tbig">' + esc(cap1(big)) + "</p><p>" + text + "</p></div></div>";
    }
    return '<div class="ds-tile"><p class="eyebrow">How full</p><div class="ds-glyph">' + glyph(m, 56, true) + "</div>" +
      '<p class="ds-tbig ds-nowrap">' + esc(big) + "</p><p>" + text + "</p></div>";
  }

  function chanceTile(m) {
    if (m.chance === null || !m.windowEnd) return "";
    const range = m.low !== null && m.high !== null
      ? " Wetter or drier season: " + esc(fmt().chanceRange(m.low, m.high)) + ". " +
        fmt().tip("What is the wetter or drier season range?", "The chance is for a typical season. The range shows " +
          "how far it could move if the coming months turn out unusually wet or unusually dry.")
      : "";
    return '<div class="ds-tile"><p class="eyebrow">Chance by ' + esc(short(m.windowEnd)) + "</p>" +
      '<p class="ds-tbig ds-ch">' + chanceHtml(m.chance) + '</p><div class="ds-glyph">' +
      D.charts.tenDots(m.chance, { r: 5.5, gap: 2.5, label: chance(m.chance) + " by " + short(m.windowEnd) }) + "</div>" +
      "<p>that it drops below a third by then." + range + "</p></div>";
  }

  function recordTile(m) {
    if (!m.track || !m.isLive) return "";
    const r = m.record;
    const how = fmt().tip("How was this checked?", m.track.tip || txt().TRACK_RECORD_HOW || "");
    const span = esc(m.track.label || txt().TRACK_RECORD_SPAN || "the last 10 years");
    const min = m.track.min_judged || txt().TRACK_RECORD_MIN || 5;
    if (!txt().hasTrackRecord(r)) {
      const n = r ? r.judged : 0;
      return '<div class="ds-tile wide ds-rec"><p class="eyebrow">Our record on this dam</p>' +
        '<p class="ds-tbig">Not enough history</p><p>' + (n === 0 ? "No past forecast for this dam could be checked"
          : "Only " + esc(fmt().count(n, "past forecast")) + " could be checked") + "; we show a record once " + min +
        " can be checked. " + how + "</p></div>";
    }
    const share = r.held / r.judged;
    // One rule everywhere (format.recordLevel): under the aim means held / judged below 0.9.
    const level = fmt().recordLevel(r.held, r.judged);
    let verdict;
    if (level === "every") verdict = "It held every time over " + span + ".";
    else if (level === "near") verdict = cap1(fmt().recordLead(r.held, r.judged)) + " over " + span + ", short of the 9 in 10 it aims for: " +
      "<b>give the days some extra margin.</b>";
    else if (level === "below") verdict = cap1(timesInTen(share)) + " over " + span + ", less often than the 9 in 10 it aims for: " +
      "<b>on this dam, give the days extra margin.</b>";
    else verdict = cap1(timesInTen(share)) + " over " + span + esc(fmt().recordAimWords(r.held, r.judged));
    if (r.judged < 20) verdict += " With so few past forecasts, this is only a rough guide.";
    const pct = Math.max(0, Math.min(100, Math.round(share * 1000) / 10));
    return '<div class="ds-tile wide ds-rec"><p class="eyebrow">Our record on this dam</p>' +
      '<p class="ds-tbig">' + esc(fmt().held(r.held, r.judged)) + "</p>" +
      '<div class="ds-tally" role="img" aria-label="' + esc(fmt().held(r.held, r.judged)) + '"><i style="width:' + pct + '%"></i></div>' +
      "<p>" + verdict + " " + how + "</p></div>";
  }

  function tilesHtml(m) {
    if (m.kind === "forecast") return '<div class="ds-tiles">' + fullTile(m, false) + chanceTile(m) + recordTile(m) + "</div>";
    return '<div class="ds-tiles">' + fullTile(m, true) + recordTile(m) + "</div>";
  }

  function notesHtml(m) {
    let html = (m.notes || []).map((n) => '<p class="ds-note">' + icon("i-drop") + "<span>" + esc(n) + "</span></p>").join("");
    if (m.outsideRegion) {
      const where = m.farm && m.farm.region_name ? "in " + m.farm.region_name : "outside the region this app holds";
      html += '<p class="ds-note is-plain">' + icon("i-info") + "<span>This farm is " + esc(where) + ". The app's maps hold " +
        esc(m.regionName || "one region") + ", so this dam's sheet has no six-month chances or water history; " +
        "its days, fullness and chance come from this week's texts.</span></p>";
    }
    return html;
  }

  function outcomeHtml(m) {
    if (m.isLive || !m.revealed || m.kind !== "forecast") return "";
    let text;
    if (m.outcome === true) text = "It <b>fell below a third</b> on " + esc(fmt().date(m.outcomeDate)) + ".";
    else if (m.outcome === false) text = "It <b>stayed above a third</b> until " + esc(fmt().date(m.windowEnd)) + ".";
    else text = "Not enough clear satellite looks to know.";
    return '<section class="ds-outcome" aria-label="What happened"><p class="eyebrow">What happened</p><p>' + text + "</p></section>";
  }

  // ---- The next six months: ten-dot rows by date, the text's day and the DamDays day marked ----
  function sixHtml(m) {
    if (m.kind !== "forecast" || !m.curve || !m.issuedOn) return "";
    const h = m.horizons;
    const maxDays = h[h.length - 1];
    const items = h.map((d, i) => ({ iso: fmt().addDays(m.issuedOn, d), order: 1, kind: "h", c: m.curve.chance[i] }));
    if (m.asOf) items.push({ iso: m.asOf, order: 0, kind: "text" });
    const dd = m.damdaysDays;
    const ddIso = isNum(dd) ? fmt().addDays(m.issuedOn, dd) : null;
    if (ddIso && dd < maxDays) items.push({ iso: ddIso, order: 0, kind: "dd" });
    items.sort((a, b) => (a.iso < b.iso ? -1 : a.iso > b.iso ? 1 : a.order - b.order));
    const rows = items.map((it) => {
      if (it.kind === "text") {
        return '<li class="ds-rw is-mark"><span class="d">' + esc(m.isLive ? day(it.iso) : short(it.iso)) +
          '</span><span class="line" aria-hidden="true"></span><span class="v">' + (m.isLive ? "the text" : "the forecast") + "</span></li>";
      }
      if (it.kind === "dd") {
        return '<li class="ds-rw is-mark is-dd"><span class="d">' + esc(short(it.iso)) +
          '</span><span class="line" aria-hidden="true"></span><span class="v">DamDays day</span></li>';
      }
      const words = chance(it.c);
      return '<li class="ds-rw"><span class="d">by ' + esc(short(it.iso)) + "</span>" +
        '<span class="dots">' + D.charts.tenDots(it.c, { r: 6, gap: 3, label: words + " by " + short(it.iso) }) + "</span>" +
        '<span class="v">' + chanceHtml(it.c) + "</span></li>";
    }).join("");
    const band = m.low !== null && m.high !== null && m.windowEnd
      ? '<p class="ds-lead">In a wetter or drier season than usual, by ' + esc(short(m.windowEnd)) + ": " +
        esc(fmt().chanceRange(m.low, m.high)) + ".</p>" : "";
    let two = "";
    if (isNum(dd)) {
      if (dd >= maxDays) {
        two = '<p class="ds-two">DamDays day: after the end of this chart.</p>';
      } else {
        const v = D.charts.lineAt(m.curve.chance, h, dd);
        const t = txt().inTen(v);
        const words = t === 0 ? "less than 1 in 10" : t >= 10 ? "more than 9 in 10" : "about " + chance(v);
        two = '<p class="ds-two">On ' + esc(short(ddIso)) + ", the DamDays day, this curve reads " + esc(words) +
          ". They come from two models: the curve is the chance for dams like this one; the DamDays number is a " +
          "cautious count that held 9 times in 10 across all dams in ten test years, less often for spring looks and " +
          "where this curve reads 2 in 10 or more.</p>";
      }
    }
    const chartNote = "The line is the chance it drops below a third, counted from the " + esc(short(m.issuedOn)) +
      " satellite look; shaded, a wetter or drier season than usual." +
      (m.chance !== null && m.windowEnd ? " Ringed: " + esc(chance(m.chance)) + " by " + esc(short(m.windowEnd)) + ", the chance on this card." : "") +
      (isNum(dd) && dd < maxDays ? " Dashed: the DamDays day (" + esc(short(ddIso)) + ")." : "") +
      (m.since > 0 ? " Dotted: " + esc(m.isLive ? day(m.asOf) + ", the day of this week's text." : short(m.asOf) +
        ", the day of this forecast.") : "");
    return '<section class="ds-six" aria-labelledby="ds-six-h"><h3 class="eyebrow ds-sec" id="ds-six-h">The next six months</h3>' +
      '<div class="ds-card"><p class="ds-lead">The chance it drops below a third by each date, counted from the ' +
      esc(short(m.issuedOn)) + ' satellite look:</p><ol class="ds-rows">' + rows + "</ol>" + band + two +
      details("curve", "i-chart", "See it as a chart", '<div class="ds-chart" data-chart="curve"></div><p class="ds-small">' +
        chartNote + "</p>") + "</div></section>";
  }

  // ---- Season by season (the record, one more level) ----
  function seasonsHtml(m) {
    const r = m.record;
    const min = (m.track && m.track.min_judged) || 5;
    if (!txt().hasTrackRecord(r)) {
      return "<p>Not enough history: fewer than " + min + " past forecasts on this dam could be checked.</p>";
    }
    const years = Object.keys(r.by_season || {}).sort();
    const rows = years.map((y) => {
      const pair = r.by_season[y];
      const pct = pair[1] ? Math.round((pair[0] / pair[1]) * 1000) / 10 : 0;
      const weak = pair[1] && fmt().recordBelowAim(pair[0], pair[1]);
      return '<tr' + (weak ? ' class="is-weak"' : "") + '><th scope="row">' + seasonLabel(y) + '</th><td class="ds-bar-cell"><span class="ds-mini' + (weak ? " is-weak" : "") +
        '" aria-hidden="true"><i style="width:' + pct + '%"></i></span></td><td class="num">' + count(pair[0]) + " of " +
        count(pair[1]) + (weak ? '<span class="vh"> (under 9 in 10)</span>' : "") + "</td></tr>";
    }).join("");
    const anyWeak = years.some((y) => r.by_season[y][1] && fmt().recordBelowAim(r.by_season[y][0], r.by_season[y][1]));
    const last = m.track && m.track.last_season_year ? Number(m.track.last_season_year) : Number(years[years.length - 1]);
    const recent = [0, 1, 2].map((i) => String(last - i)).filter((y) => r.by_season[y]);
    const rh = recent.reduce((s, y) => s + r.by_season[y][0], 0);
    const rj = recent.reduce((s, y) => s + r.by_season[y][1], 0);
    const bits = [];
    if (rj > 0 && years.length > recent.length) {
      bits.push("In the last three seasons (" + seasonLabel(last - 2) + " to " + seasonLabel(last) + ") it held " + count(rh) +
        " of " + count(rj) + " times.");
    }
    if (isNum(r.median_days) && r.median_days >= 1) {
      bits.push("Its typical promise was " + (r.median_days >= capDays(m) ? "6 months or more" : "at least " +
        fmt().count(r.median_days, "day")) + ".");
    }
    if (r.likely_said > 0) {
      bits.push("When we said a fall below a third was likely (5 in 10 or more), it fell within 90 days " +
        count(r.likely_fell) + " of " + count(r.likely_said) + " times.");
    }
    if (r.not_judged > 0) {
      bits.push(cap1(fmt().count(r.not_judged, "more forecast")) + " " + (r.not_judged === 1 ? "is" : "are") +
        " too recent to judge.");
    }
    return '<p class="ds-small">Each season runs July to June: how often our days-left number held, of the forecasts we could check.</p>' +
      '<p class="ds-season-key"><span class="k"><span class="ds-mini" aria-hidden="true"><i style="width:100%"></i></span>the share that held</span>' +
      (anyWeak ? '<span class="k"><span class="ds-mini is-weak" aria-hidden="true"><i style="width:100%"></i></span>a season it held less than 9 times in 10</span>' : "") + "</p>" +
      '<div class="table-scroll" tabindex="0" role="region" aria-label="Season by season">' +
      '<table class="ds-seasons"><caption class="vh">Our record on ' + esc(m.name) + ", season by season</caption>" +
      '<thead><tr><th scope="col">Season</th><th scope="col">Share that held</th>' +
      '<th scope="col" class="num">Held, of checked</th></tr></thead><tbody>' + rows + "</tbody></table></div>" +
      (bits.length ? "<p>" + esc(bits.join(" ")) + "</p>" : "") +
      (m.track && m.track.tip ? '<p class="ds-small">' + esc(m.track.tip) + "</p>" : "");
  }

  // ---- In this week's text: the line of the SMS and the clause of the longer version ----
  /**
   * The farm's weekly text and its longer version: the farm's own (farms.json sms and long) when given,
   * else made by js/text.js from the farm's dams, exactly as the farm view makes them.
   */
  function farmTexts(opts, data, asOf) {
    const farm = opts.farm;
    if (!farm || !asOf) return null;
    if (farm.sms || farm.long) return { sms: farm.sms || "", long: farm.long || "" };
    const dams = opts.dams;
    if (!dams || !dams.length || !txt() || typeof txt().smsForDams !== "function") return null;
    try {
      const radius = isNum(farm.radius_km) ? farm.radius_km : txt().DEFAULT_RADIUS_KM;
      return { sms: txt().smsForDams(dams, asOf, radius), long: txt().longForDams(dams, asOf, farm.name || "Your farm", radius, null) };
    } catch (e) {
      return null;
    }
  }

  function textSays(m) {
    const farm = m.texts;
    if (!m.isLive || !farm || (!farm.sms && !farm.long)) return null;
    const n = m.number;
    const nameRe = new RegExp("^" + String(m.name).replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?=[ :~(,]|$)");
    const lines = String(farm.sms || "").split("\n");
    let line = lines.find((l) => nameRe.test(l)) || null;
    let how = "says";
    if (!line && n) {
      line = lines.find((l) => {
        const g = /^Dams ([\d, and]+?)(?= already| may|:)/.exec(l);
        return Boolean(g) && g[1].split(/, | and /).map(Number).includes(n);
      }) || null;
    }
    if (!line) {
      const group = { forecast: /^(Other \d+ dams|All \d+ dams|Both dams|Your dam)\b/, low: /^\d+ dams already below/,
                      not_refilled: /^\d+ dams: no forecast/, no_look: /^\d+ dams: no forecast/ }[m.kind];
      if (m.kind === "forecast" && m.daysLeft <= 0) line = lines.find((l) => /^\d+ dams may be below/.test(l)) || null;
      else if (group) line = lines.find((l) => group.test(l)) || null;
      if (line) how = "counts it in";
    }
    if (!line) {
      line = lines.find((l) => /^Reply MAP for \d+ more dams?$/.test(l)) || null;
      if (line) how = "leaves it out to fit one message";
    }
    let clause = null;
    String(farm.long || "").split("\n").some((l) => l.replace(/^Also: /, "").split("; ").some((part) => {
      if (nameRe.test(part)) { clause = part; return true; }
      return false;
    }));
    if (!line && !clause) return null;
    return { line, how, clause };
  }

  function textHtml(m) {
    const says = textSays(m);
    if (!says) return "";
    let body = "";
    if (says.line) {
      body += "<p>The text message of " + esc(day(m.asOf)) + " " + esc(says.how) + ":</p>" +
        '<p class="ds-quote">' + esc(says.line) + "</p>";
    }
    if (says.clause) {
      const dated = m.asOf ? says.clause.replace(/counted from today\b/, "counted from today (" + day(m.asOf) + ")") : says.clause;
      body += '<p>The longer version, for the app or an email:</p><p class="ds-quote is-long">' + esc(dated) + "</p>";
    }
    return details("text", "i-sms", "In this week's text", body);
  }

  // ---- About these numbers ----
  /** What each number on this sheet is counted from: only the numbers the sheet shows (no chance, no such sentence). */
  function countedFromHtml(m) {
    const parts = [];
    if (m.kind === "forecast") parts.push(m.isLive ? "Days are counted from the day of each week's text" : "Days are counted from the day of this forecast");
    const fromLook = [];
    if (m.kind === "forecast" && m.chance !== null && m.windowEnd) fromLook.push("the chance by " + esc(short(m.windowEnd)));
    if (m.kind === "forecast" && m.curve && m.issuedOn) fromLook.push("the six-month chances");
    if (fromLook.length) parts.push(fromLook.join(" and ") + (fromLook.length > 1 ? " are" : " is") + " counted from the satellite look");
    if (!parts.length) return "";
    const text = parts.join("; ");
    return "<p>" + text.charAt(0).toUpperCase() + text.slice(1) + ".</p>";
  }

  function aboutHtml(m) {
    const rows = [];
    if (m.deaUid) rows.push(["Waterbody", "DEA Waterbodies " + m.deaUid + " (Geoscience Australia)"]);
    if (m.areaHa !== null) rows.push(["Size when full", m.areaHa.toFixed(2) + " ha of water surface"]);
    if (m.lat !== null && m.lon !== null) {
      rows.push(["Where", Math.abs(m.lat).toFixed(4) + "° " + (m.lat < 0 ? "S" : "N") + ", " + Math.abs(m.lon).toFixed(4) +
        "° " + (m.lon < 0 ? "W" : "E") + (m.distanceKm !== null ? "; " + txt().oneDecimal(m.distanceKm) +
        " km from the homestead (a demo point)" : "")]);
    }
    if (m.mapName && m.mapName !== m.name) rows.push(["On the Runway map", m.mapName]);
    if (m.issuedOn) rows.push(["Last clear look", fmt().date(m.issuedOn)]);
    const minHa = isNum(m.meta.min_dam_area_ha) ? m.meta.min_dam_area_ha.toFixed(1) : null;
    const third = isNum(m.meta.threshold_pct) ? m.meta.threshold_pct : 30;
    return '<dl class="ds-facts">' + rows.map((r) => "<dt>" + esc(r[0]) + "</dt><dd>" + esc(r[1]) + "</dd>").join("") + "</dl>" +
      "<p>“How full” is the share of its usual full water surface that is wet at a satellite look, not its depth. " +
      "“Below a third” means less than " + third + "% of that surface is wet (we round it to “a third”).</p>" +
      countedFromHtml(m) +
      (minHa ? "<p>DamDays sees dams of about " + minHa + " ha and up, from above. Smaller dams, tanks and bores are not visible.</p>" : "") +
      "<p>Water surface: DEA Waterbodies (Geoscience Australia). Rainfall: SILO climate data (Queensland Government). " +
      'Both CC BY 4.0. How it all works: <a href="#about">About DamDays</a>.</p>';
  }

  function moreHtml(m) {
    const parts = [];
    if (m.isLive && m.track) parts.push(details("record", "i-tally", "Season by season", seasonsHtml(m)));
    if (m.inApp && m.historyRange) {
      parts.push(details("history", "i-drop", "How full since " + esc(m.historyRange.first_month.slice(0, 4)),
        '<div class="ds-chart" data-chart="history"></div><div class="ds-hist-note"></div>'));
    }
    parts.push(textHtml(m));
    parts.push(details("about", "i-info", "About these numbers", aboutHtml(m)));
    return '<div class="ds-more">' + parts.join("") + "</div>";
  }

  /** The whole sheet content for one dam. */
  function contentHtml(m) {
    return '<article class="ds" data-dam-id="' + esc(m.id) + '" data-kind="' + esc(m.kind) + '" aria-labelledby="ds-title">' +
      headHtml(m) + heroHtml(m) + outcomeHtml(m) + tilesHtml(m) + notesHtml(m) + sixHtml(m) + moreHtml(m) + "</article>";
  }

  function skeletonHtml(name) {
    return '<div class="ds ds-loading" aria-busy="true"><header class="ds-head"><h2 class="ds-title">' + esc(name || "Dam") +
      '</h2><span class="skel skel-line ds-skel-meta"></span></header>' +
      '<div class="skel ds-skel-hero"></div><div class="ds-tiles"><div class="skel ds-skel-tile"></div>' +
      '<div class="skel ds-skel-tile"></div></div></div>';
  }

  // ===========================================================================
  // Charts inside expanders: drawn at the width they have, when they open
  // ===========================================================================
  function chartWidth(holder) {
    return Math.floor(holder.clientWidth || holder.getBoundingClientRect().width || 320);
  }

  function drawCurve(holder, m) {
    if (!m.curve) return;
    const main = isNum(m.meta.horizon_days) ? m.meta.horizon_days : 90;
    holder.innerHTML = D.charts.sixMonths(m.curve, {
      width: chartWidth(holder), horizons: m.horizons, issuedOn: m.issuedOn,
      damdaysDays: m.damdaysDays, sinceDays: m.since,
      sinceLabel: m.isLive ? day(m.asOf) : short(m.asOf),
      // the card's own chance, ringed on the chart: "1 in 10 by 12 Dec"
      headline: m.chance !== null && m.windowEnd ? { days: main, label: chance(m.chance) + " by " + short(m.windowEnd), short: chance(m.chance) } : null,
    });
  }

  /** True when the dam's water history is in the data (with split data parts it may come later). */
  function historyReady(m) {
    return !(typeof m.data.hasHistory === "function" && !m.data.hasHistory(m.id));
  }

  /** Load the dam's water history part once; resolves true when it arrived. */
  function loadHistory(m) {
    if (!m.historyPromise) {
      m.historyPromise = typeof m.data.ensureHistory === "function"
        ? Promise.resolve(m.data.ensureHistory(m.id)).then(() => true, () => false) : Promise.resolve(false);
    }
    return m.historyPromise;
  }

  function drawHistory(holder, m) {
    const note = holder.parentNode.querySelector(".ds-hist-note");
    const from = m.historyRange.first_month.slice(0, 4);
    if (!historyReady(m)) {
      holder.innerHTML = '<span class="skel ds-skel-chart"></span>';
      if (note) note.innerHTML = '<p class="ds-small">Loading how full it has been since ' + esc(from) + "&hellip;</p>";
      loadHistory(m).then((ok) => {
        if (!holder.isConnected) return;
        if (ok && historyReady(m)) { drawHistory(holder, m); return; }
        holder.innerHTML = "";
        if (note) note.innerHTML = "<p>The water history needs an internet connection the first time.</p>";
      });
      return;
    }
    const history = typeof m.data.historyFor === "function" ? m.data.historyFor(m.id) : null;
    if (!history || !history.level_pct || !history.level_pct.length) {
      holder.innerHTML = "";
      if (note) note.innerHTML = "<p>No water history for this dam in this app.</p>";
      return;
    }
    const range = m.historyRange;
    const hide = !m.isLive && !m.revealed;
    const opts = {
      width: chartWidth(holder), firstMonth: range.first_month, lastMonth: range.last_month,
      threshold: isNum(m.meta.threshold_pct) ? m.meta.threshold_pct : 30, name: m.name,
      untilDate: hide ? m.issuedOn : null, markDate: m.isLive ? null : m.issueDate,
      latestPct: m.levelPct, latestDate: m.levelPct === null ? null : m.issuedOn,
    };
    holder.innerHTML = D.charts.history(history, opts);
    const f = D.charts.historyFacts(history, opts);
    const step = opts.width < 480 ? "each point the middle reading of three months, the pale band its lowest and highest month"
      : "each point the middle reading of one month";
    // history.json holds each month's middle reading (DATA_CONTRACT), which can differ from one look: quote the
    // dam's own look here, the same one as the "How full" tile.
    const overFull = history.level_pct.some((v) => typeof v === "number" && v > 100);
    const latest = m.levelPct === null || !m.issuedOn ? ""
      : (m.isLive ? " Latest clear look: " : " At the look of this forecast: ") + fullness(m.levelPct) + " (" + lookDate(m) + ").";
    if (note) {
      note.innerHTML = '<p class="ds-hist-key"><span><span class="k k-below" aria-hidden="true"></span>fell below a third: ' +
        f.below + (f.below === 1 ? " time" : " times") + '</span><span><span class="k k-none" aria-hidden="true"></span>' +
        "no water seen at a look: " + f.noWater + (f.noWater === 1 ? " time" : " times") + "</span></p>" +
        '<p class="ds-small">How full it has been since ' + esc(from) + " (% of its usual full water surface), " + step +
        "; months with no clear look leave gaps. The shaded band is below a third." + esc(latest) +
        (hide ? " Later months stay hidden until you reveal what happened." : "") + "</p>" +
        (overFull ? '<p class="ds-small">Above 100: fuller than its usual full mark (after a wet spell the water spreads wider). ' +
          '<a href="#questions/over-100">How can a dam be more than 100% full?</a></p>' : "");
    }
  }

  function drawOpen(root, m) {
    root.querySelectorAll("details[open] [data-chart]").forEach((holder) => {
      if (holder.dataset.chart === "curve") drawCurve(holder, m);
      else if (holder.dataset.chart === "history") drawHistory(holder, m);
    });
  }

  /** Open the expander named by a deep link, draw its chart and bring it into view inside the sheet. */
  function applyDeep(root, deep, m) {
    if (!deep || !root) return;
    const key = String(deep).split("/")[0].toLowerCase();
    if (!DEEP.includes(key)) return;
    const el = root.querySelector('details[data-deep="' + key + '"]');
    if (!el) return;
    el.open = true;
    drawOpen(root, m);
    const scroller = root.closest(".sheet-body");
    const bring = () => {
      if (scroller) scroller.scrollTop += el.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 8;
      else el.scrollIntoView({ block: "start" });
    };
    requestAnimationFrame(() => requestAnimationFrame(bring));
  }

  /** Charts on open, the deep link, and the water history fetched early (it is small). */
  function wire(root, data, opts) {
    opts = opts || {};
    const m = root.__dsModel || build(data, opts);
    root.__dsModel = m;
    root.querySelectorAll("details.ds-x").forEach((el) => {
      el.addEventListener("toggle", () => { if (el.open) drawOpen(el, m); });
    });
    if (opts.deep) applyDeep(root, opts.deep, m);
    if (m.inApp && m.historyRange && !historyReady(m)) loadHistory(m);
    return m;
  }

  // ===========================================================================
  // Opening the sheet
  // ===========================================================================
  /** The prepared data with the first screens' part (js/data.js need("first"); the whole bundle without parts). */
  function getData() {
    if (D.loaded && D.loaded.damsById) return Promise.resolve(D.loaded);
    const need = D.data && typeof D.data.need === "function"
      ? Promise.resolve(D.data.need("first")).catch(() => null) : Promise.resolve(null);
    return need.then((x) => (x && x.damsById ? x : D.data.load()));
  }

  /**
   * The data parts this sheet still needs (js/data.js splits the data): "core" for a dam that is not one
   * of the demo farms' dams (the region's dams), "rewind" for a past forecast date. [] when all is there.
   */
  function partsFor(data, opts) {
    if (!data || typeof data.need !== "function" || typeof data.has !== "function") return [];
    const dam = opts.dam || {};
    const outside = opts.inApp === false || dam.in_app === false || Boolean(opts.farm && opts.farm.dams_in_app === false);
    const parts = [];
    if (!outside && dam.dam_id && !(data.damsById && data.damsById.has(dam.dam_id)) && !data.has("core")) parts.push("core");
    if (opts.issueDate && !issueOf(data, opts.issueDate) && !data.has("rewind")) parts.push("rewind");
    return parts;
  }

  /** The data with every part this sheet needs merged in. */
  function dataFor(opts) {
    const start = opts.data && opts.data.damsById ? Promise.resolve(opts.data) : getData();
    return start.then((d) => {
      const more = partsFor(d, opts);
      return more.length ? Promise.resolve(d.need(more)).then((x) => (x && x.damsById ? x : d)) : d;
    });
  }

  function keyOf(opts) {
    const d = opts.dam || {};
    return [d.dam_id, opts.issueDate || "live", opts.revealed ? 1 : 0, (opts.dams || []).map((x) => x.dam_id).join(","),
            opts.farm ? [opts.farm.name, opts.farm.radius_km, opts.farm.lat, opts.farm.lon].join("/") : "",
            opts.textDate || "", opts.title || ""].join("|");
  }

  /** The dam's name: the one given, else its name in the region's data (a dam opened by id alone). */
  function nameOf(d, data) {
    if (d.name) return d.name;
    const known = data && data.damsById ? data.damsById.get(d.dam_id) : null;
    return known ? known.name : "Dam";
  }

  function pager(opts, data) {
    const list = opts.dams || [];
    const d = Object.assign({}, opts.dam || {});
    d.name = nameOf(d, data);
    const i = list.findIndex((x) => x.dam_id === d.dam_id);
    if (i < 0 || list.length < 2) return { title: opts.title || d.name, head: {} };
    const href = typeof opts.hrefFor === "function" ? opts.hrefFor
      : typeof opts.href === "function" ? opts.href : (x) => "#farm/dam-" + x.number;
    const prev = list[(i - 1 + list.length) % list.length];
    const next = list[(i + 1) % list.length];
    return {
      title: opts.title || (d.name || "Dam") + " of " + list.length,
      head: {
        prev: { href: href(prev), label: "Previous dam: " + prev.name },
        next: { href: href(next), label: "Next dam: " + next.name },
      },
    };
  }

  /** Open (or keep) the sheet for one dam. Returns the sheet body element. */
  function open(opts) {
    opts = opts || {};
    const route = D.router && D.router.current ? D.router.current() : null;
    if (!opts.auto && route && route.view === "farm") api.managed = true;
    const key = keyOf(opts);
    // The same dam again (the farm view's enter() runs on every visit): keep it, just open the deep link.
    if (current && current.key === key && D.sheet.isOpen() && current.body && current.body.isConnected &&
        current.body.querySelector(".ds[data-dam-id]")) {
      current.hash = route ? route.hash : null;
      current.auto = Boolean(opts.auto);
      if (opts.deep) applyDeep(current.body.querySelector(".ds"), opts.deep, current.model);
      return current.body;
    }
    const given = opts.data || (D.loaded && D.loaded.damsById ? D.loaded : null);
    const data = given && !partsFor(given, opts).length ? given : null;     // null: a part is still to load
    const p = pager(opts, given);
    const state = { key, auto: Boolean(opts.auto), hash: route ? route.hash : null, opts, model: null, body: null };
    const userClose = opts.onClose;
    const body = D.sheet.open({
      title: p.title, head: p.head, split: opts.split, label: opts.label,
      body: data ? "" : skeletonHtml(p.title.replace(/ of \d+$/, "")),
      onClose(why) {
        if (current === state) current = null;
        if (typeof userClose === "function") userClose(why);
      },
    });
    state.body = body;
    current = state;
    const fill = (d) => {
      if (current !== state || !body.isConnected) return;
      const m = build(d, opts);
      state.model = m;
      if (p.title === "Dam") {                         // opened before the data: name it now
        const title = document.getElementById("sheet-title");
        if (title) title.textContent = pager(opts, d).title;
      }
      body.innerHTML = contentHtml(m);
      const root = body.querySelector(".ds");
      root.__dsModel = m;
      wire(root, d, opts);
    };
    if (data) fill(data);
    else {
      dataFor(opts).then(fill, (error) => {
        if (D.logLoad) D.logLoad(error); else console.error(error);
        if (current === state) {
          const e = D.pwa && typeof D.pwa.loadErrorText === "function" ? D.pwa.loadErrorText() : null;
          body.innerHTML = '<div class="load-error" role="alert"><p><strong>' + esc(e && e.title ? e.title : "The forecast data could not be loaded.") +
            "</strong> " + esc(e && e.body ? e.body : "Check your signal and try again.") +
            '</p><button class="btn btn-primary" type="button" data-retry>Try again</button></div>';
        }
      });
    }
    return body;
  }

  /** The farm view's enter(route): "#farm/dam-3" (and its deep link) opens Dam 3 of ctx.dams. */
  function fromRoute(route, ctx) {
    ctx = ctx || {};
    const match = /^dam-(\d+)$/.exec((route && route.sub) || "");
    if (!match) return false;
    const n = Number(match[1]);
    const list = (ctx.dams || []).slice().sort((a, b) => (a.number || 0) - (b.number || 0));
    const dam = list.find((d) => d.number === n);
    if (!dam) return false;
    open({ dam, dams: list, data: ctx.data, farm: ctx.farm, inApp: ctx.inApp, hrefFor: ctx.hrefFor || ctx.href, deep: route.deep,
           auto: Boolean(ctx.auto), split: ctx.split, onClose: ctx.onClose, title: ctx.title, textDate: ctx.textDate });
    return true;
  }

  /** A dam of the region by its id (Runway's map and list): no homestead, so no distance. */
  function openRegion(damId, opts) {
    opts = Object.assign({}, opts || {});
    opts.dam = Object.assign({ dam_id: damId }, opts.dam || {});
    return open(opts);
  }

  /** The sheet's content as HTML, for a container other than the sheet (call wire() after inserting it). */
  function html(data, opts) {
    return contentHtml(build(data, opts || {}));
  }

  // ===========================================================================
  // Fallback: a #farm/dam-N address with no sheet opens Dam N of the default demo farm
  // ===========================================================================
  function defaultFarm(data) {
    const farms = data && data.farms ? data.farms.farms || [] : [];
    const s = D.settings || {};
    const hidden = s.hiddenFarmIds || [];
    const wanted = new URLSearchParams(location.search).get("farm");
    return farms.find((f) => f.farm_id === wanted && !hidden.includes(f.farm_id)) ||
      farms.find((f) => f.farm_id === s.defaultFarmId) || farms.find((f) => !hidden.includes(f.farm_id)) || null;
  }

  function autoRoute(r) {
    if (api.managed || !r || r.view !== "farm" || !/^dam-\d+$/.test(r.sub || "")) return;
    setTimeout(() => {
      const now = D.router.current();
      if (api.managed || !now || now.hash !== r.hash) return;
      if (D.sheet.isOpen() && !(current && current.auto)) return;              // someone else's sheet
      if (D.sheet.isOpen() && current && current.auto && current.hash === r.hash) return;
      getData().then((data) => {
        const again = D.router.current();
        if (api.managed || !again || again.hash !== r.hash) return;
        const farm = defaultFarm(data);
        if (!farm) return;
        const ok = fromRoute(r, { dams: farm.dams, data, farm, inApp: farm.dams_in_app !== false, auto: true });
        if (!ok) D.router.go("#farm", { replace: true });
      }, () => null);
    }, 0);
  }

  function onResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (!current || !current.body || !current.model || !D.sheet.isOpen()) return;
      const w = current.body.clientWidth;
      if (w === lastWidth) return;
      lastWidth = w;
      const root = current.body.querySelector(".ds");
      if (root) drawOpen(root, current.model);
    }, 150);
  }

  const api = {
    open, fromRoute, openRegion, html, wire,
    current: () => (current && current.model ? current.model.id : null),
    managed: false,
  };

  if (D.router && typeof D.router.onChange === "function") D.router.onChange(autoRoute);
  window.addEventListener("resize", onResize);

  return api;
})();
