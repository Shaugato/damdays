/* views/replay.js (WP-E)
 * Rewind: the 2018-19 drought, inside Proof (#proof/rewind; old #rewind and #proof/replay lead here).
 * UI_SPEC 3.4 (More), 5.19; founder: keep the name "Rewind".
 *
 * Go back to a date in 2018-19 and see the forecasts as they were made that day, from only what the
 * satellites had seen by then; then "Show what happened".
 *   - the demo farm (proof.json dam_by_dam.farm, Farm E near Mudgee) drawn from above, each dam tagged with
 *     that day's chance; the reveal rings the dams that fell below a third within 90 days ("fell 20 Dec")
 *     and marks the others "held"
 *   - the score: the chances added up (expected) against what happened, the dams without a forecast and why,
 *     and, after the reveal, proof.json's all-dates line
 *   - each dam that day, with a link to its whole season (#proof/dams/dam-N)
 *   - the region on the same date, in one line, and the hits-and-misses tables under "Show the numbers"
 *   - "See the whole region on the map": the old Rewind map (js/views/rewind.js, Leaflet), mounted on demand
 *     with DamDays.legacy.mount and driven by this sheet's own date and reveal; moved back to #legacy-store
 *     when the sheet closes (cleanup()).
 * Every number is read from forecasts.json's past issues, farms.json and proof.json; none is typed here.
 * Uses DamDays.proofKit (js/views/proof.js) for the dam glyph, the ten dots and the wording helpers.
 *
 *   DamDays.replay.render(sheetBody, data)   draw into the open sheet
 *   DamDays.replay.cleanup()                the sheet is closing or being replaced
 *   DamDays.replay.resize()                 redraw the sketch at the new width
 *   DamDays.replay.cardInfo(data)           { label, heading, sub, thumb } for the Proof page's card
 *   DamDays.replay.label(data)              "Rewind: the 2018-19 drought"
 */
window.DamDays = window.DamDays || {};

DamDays.replay = (function () {
  "use strict";

  const D = window.DamDays;
  const K = () => D.proofKit;
  const esc = (t) => D.format.escapeHtml(t === null || t === undefined ? "" : t);
  const icon = (id, cls, label) => (D.icon ? D.icon(id, cls, label) : "");
  const short = (iso) => D.format.short(iso);
  const fmtDate = (iso) => D.format.date(iso);
  const count = (n) => Number(n).toLocaleString("en-AU");

  let st = null;          // the open sheet's state
  let wiredBody = null;
  let measureCtx = null;

  // =====================================================================
  // The data: past issues, the demo farm and its dams
  // =====================================================================
  function issuesOf(data) {
    return (data.pastIssues || []).slice().sort((a, b) => (a.issue_date < b.issue_date ? -1 : a.issue_date > b.issue_date ? 1 : 0));
  }
  function rowOf(issue, damId) {
    if (!issue) return null;
    return (issue.rowsByDam ? issue.rowsByDam.get(damId) : issue.rows.find((r) => r.dam_id === damId)) || null;
  }

  /** "Rewind: the 2018-19 drought" (the season from meta.rewind), or "Rewind". */
  function label(data) {
    const season = data && data.meta && data.meta.rewind && data.meta.rewind.season;
    return season ? "Rewind: the " + season + " drought" : "Rewind";
  }

  function ctxFrom(data) {
    const issues = issuesOf(data);
    const part = (data.proof && data.proof.dam_by_dam) || null;
    const hidden = (D.settings && D.settings.hiddenFarmIds) || [];
    const wanted = part && part.farm ? part.farm.farm_id : D.settings && D.settings.defaultFarmId;
    const farms = (data.farms && data.farms.farms) || [];
    let farm = farms.find((f) => f.farm_id === wanted && !hidden.includes(f.farm_id)) || null;
    // the farm's dams must be in the past forecasts (the region the app shows)
    if (farm && !(issues.length && farm.dams.some((d) => rowOf(issues[0], d.dam_id)))) farm = null;
    const dams = farm ? farm.dams.slice().sort((a, b) => a.number - b.number) : [];
    const meta = data.meta || {};
    const ownPart = part && farm && part.farm && part.farm.farm_id === farm.farm_id ? part : null;
    let season = "";
    if (ownPart && ownPart.season) { const y = +ownPart.season.forecasts_from.slice(0, 4); season = y + "-" + String(y + 1).slice(2); }
    // which years these are: one of the test years, never trained on, scored once (proof.json test.scored_at)
    const rwSeason = (meta.rewind && meta.rewind.season) || season;
    const scored = data.proof && data.proof.test && data.proof.test.scored_at ? fmtDate(String(data.proof.test.scored_at).slice(0, 10)) : "";
    const testYears = rwSeason ? rwSeason + " is one of the years it never trained on" + (scored ? "; they were scored once, on " + scored : "") + "." : "";
    return {
      data, issues, farm, dams, part: ownPart, season,
      radius: (ownPart && ownPart.farm.radius_km) || (farm && farm.radius_km) || null,
      region: meta.region ? meta.region.name : "the region",
      horizon: meta.horizon_days || null,
      arm: meta.arm_level_pct || null,
      intro: (data.proof && data.proof.test ? K().sentences(data.proof.test.intro)[0] || "" : "") + (testYears ? " " + testYears : ""),
    };
  }
  const within = (c) => (c.horizon ? "within " + c.horizon + " days" : "in the months after");

  function defaultIndex(c) {
    const want = c.part && c.part.rewind_date;
    const i = want ? c.issues.findIndex((iss) => iss.issue_date === want) : -1;
    return i >= 0 ? i : 0;
  }

  const issue = () => st.c.issues[st.idx];
  const names = (list) => (list.length < 2 ? list.join("") : list.slice(0, -1).join(", ") + " and " + list[list.length - 1]);

  /** One region date: forecasts, those with a known answer, the chances added up, how many fell. */
  function regionTally(iss) {
    const fc = iss.rows.filter((r) => r.status === "forecast");
    const judged = fc.filter((r) => r.outcome === true || r.outcome === false);
    return { forecasts: fc.length, judged: judged.length, sum: judged.reduce((a, r) => a + r.chance, 0),
             fell: judged.filter((r) => r.outcome === true).length, rows: judged };
  }

  // =====================================================================
  // The Proof page's card: drawn from the "first" part alone (proof.json and farms.json), so the Proof page
  // never waits for the past forecasts; the sheet loads those ("rewind") when it opens.
  // =====================================================================
  /** Is there anything to rewind to (loaded already, or listed in meta / proof.json)? */
  function available(data) {
    if (!data) return false;
    if ((data.pastIssues || []).length) return true;
    if (data.meta && data.meta.rewind && (data.meta.rewind.dates || []).length) return true;
    return Boolean(data.proof && data.proof.dam_by_dam && (data.proof.dam_by_dam.rewind_dates || []).length);
  }

  /** The demo farm of proof.json dam_by_dam, from farms.json (never a hidden farm). */
  function proofFarm(data) {
    const part = data.proof && data.proof.dam_by_dam;
    const hidden = (D.settings && D.settings.hiddenFarmIds) || [];
    const farms = (data.farms && data.farms.farms) || [];
    const farm = part && part.farm ? farms.find((f) => f.farm_id === part.farm.farm_id && !hidden.includes(f.farm_id)) : null;
    return farm ? { farm, part, radius: part.farm.radius_km || farm.radius_km } : null;
  }

  /** A small drawing of the farm on the card: the dams as dots in that day's chance colour, dashed if no forecast. */
  function thumbSvg(pf) {
    let s = '<rect width="100" height="100" rx="18" fill="var(--surface-2)"/>' +
      '<circle cx="50" cy="50" r="40" fill="none" stroke="var(--line-strong)" stroke-width="1.5" stroke-dasharray="4 4"/>' +
      '<rect x="45" y="45" width="10" height="10" rx="3" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.5"/>';
    if (pf && pf.radius) {
      const farm = pf.farm, cos = Math.cos(farm.lat * Math.PI / 180), sc = 38 / pf.radius;
      farm.dams.forEach((d) => {
        const x = 50 + (d.lon - farm.lon) * 111.32 * cos * sc, y = 50 - (d.lat - farm.lat) * 110.57 * sc;
        const pd = pf.part.dams.find((x2) => x2.dam_id === d.dam_id);
        const rw = pd && pd.rewind, fc = rw && rw.status === "forecast" && rw.chance !== null;
        s += '<circle cx="' + K().r1(x) + '" cy="' + K().r1(y) + '" r="7" fill="' + (fc ? K().bandVar(rw.chance) : "var(--surface)") +
          '" stroke="var(--c-ring)" stroke-width="1.8"' + (fc ? "" : ' stroke-dasharray="3 2.5"') + "/>";
      });
    }
    return '<svg viewBox="0 0 100 100" width="96" height="96" aria-hidden="true" focusable="false">' + s + "</svg>";
  }

  function cardInfo(data) {
    if (!available(data)) return null;
    const pf = proofFarm(data);
    const dates = pf && (pf.part.rewind_dates || []).length ? pf.part.rewind_dates
      : (data.meta && data.meta.rewind && data.meta.rewind.dates) || issuesOf(data).map((i) => i.issue_date);
    const n = K().numberWord(dates.length);
    let heading;
    if (pf && (pf.part.rewind_dates || []).length) {
      // proof.json's own tally of the farm on each date (scripts/17), added up
      const sum = pf.part.rewind_dates.reduce((a, r) => a + (r.chance_sum || 0), 0);
      const fell = pf.part.rewind_dates.reduce((a, r) => a + (r.fell || []).length, 0);
      heading = "On " + pf.farm.name + ", over " + n + " dates, the chances added up to " + K().sumWords(sum) +
        " below a third, and " + fell + " happened.";
    } else if ((data.pastIssues || []).length) {
      let j = 0, sum = 0, fell = 0;
      issuesOf(data).forEach((iss) => { const t = regionTally(iss); j += t.judged; sum += t.sum; fell += t.fell; });
      heading = "Across " + (data.meta && data.meta.region ? data.meta.region.name : "the region") + " on " + n + " dates, " + count(j) +
        " forecasts expected " + K().sumWords(sum) + " below a third; " + count(fell) + " happened.";
    } else {
      heading = "Go back to " + n + " dates in the drought: what the forecasts said at the time, then what happened.";
    }
    return { label: label(data), heading, sub: "Pick a date, see what it said at the time, then show what happened.", thumb: thumbSvg(pf) };
  }

  // =====================================================================
  // The sheet
  // =====================================================================
  function datesHtml(c, where) {
    const label = "Forecast made on" + (where ? " (" + where + ")" : "");
    if (c.issues.length > 4) {
      return '<label class="rp-select"><span>' + esc(label) + "</span><select data-rp-select>" +
        c.issues.map((iss, i) => '<option value="' + i + '">' + esc(fmtDate(iss.issue_date)) + "</option>").join("") + "</select></label>";
    }
    return '<div class="rp-dates" role="group" aria-label="' + esc(label) + '">' + c.issues.map((iss, i) =>
      '<button type="button" class="rp-date" data-rp-date="' + i + '" aria-pressed="false">' + esc(fmtDate(iss.issue_date)) + "</button>").join("") + "</div>";
  }

  function shellHtml() {
    const c = st.c;
    const n = K().numberWord(c.issues.length);
    const who = c.farm ? c.farm.name : "Every dam-sized waterbody in " + c.region + " (mostly farm dams)";
    const lead = who + ": the forecasts as they were made on " + n + " dates, from only what the satellites had seen by then." +
      (c.intro ? " " + c.intro : "");
    const farmPart = c.farm
      ? '<figure class="rp-sketch-card"><div class="rp-sketch" data-rp-sketch></div>' +
        '<figcaption class="small">The farm from above. Each tag: that day\'s chance it falls below a third ' + within(c) +
        ". Tap a tag for that dam. Dams are drawn larger than life; the homestead point is made up.</figcaption></figure>"
      : "";
    const after = c.farm
      ? '<div class="rp-score" data-rp-score aria-live="polite"></div>' +
        '<h3 class="ps-h3">The dams that day</h3><ol class="rp-rows" data-rp-rows></ol>'
      : "";
    const dams = c.part
      ? '<div class="linkrows"><a class="linkrow" href="#proof/dams" data-replace>' + icon("i-chart") +
        "<span>Dam by dam<small>Every " + esc(c.season) + " forecast for each dam, against how full it was</small></span>" +
        '<span class="chev">' + icon("i-chev") + "</span></a></div>"
      : "";
    return '<article class="ps rp">' +
      '<p class="eyebrow">' + esc(label(c.data)) + "</p>" +
      '<h2 class="ps-h">What it said at the time, then what happened</h2>' +
      '<p class="ps-lead">' + esc(lead) + "</p>" + datesHtml(c) +
      (c.issues.length > 1 && defaultIndex(c) === 0 ? '<p class="small rp-start">We start on the earliest date, not the one that looks best.</p>' : "") +
      farmPart +
      '<button type="button" class="btn btn-primary btn-block rp-reveal" data-rp-reveal aria-pressed="false"></button>' +
      after +
      '<section class="rp-region" aria-labelledby="rp-region-h"><h3 class="ps-h3" id="rp-region-h">Across ' + esc(c.region) + "</h3>" +
      '<div data-rp-region aria-live="polite"></div><div data-rp-numbers></div>' +
      '<button type="button" class="btn btn-quiet rp-map-btn" data-rp-map aria-expanded="false" aria-controls="rp-region-host">' +
      icon("i-map") + "<span>See the whole region on the map</span></button>" +
      '<p class="small rp-map-note">Needs signal: the map tiles come from OpenStreetMap. Tap a dot for that dam.</p>' +
      // the same date and reveal controls, right above the map, so you can flip them while watching the dots
      '<div class="rp-mapbar" data-rp-mapbar hidden>' + datesHtml(c, "the map") +
      '<button type="button" class="btn btn-secondary rp-reveal-mini" data-rp-reveal aria-pressed="false"></button></div>' +
      '<div id="rp-region-host" class="rp-region-host" hidden></div></section>' + dams + "</article>";
  }

  // ---- the farm from above ----
  /** A tag's words: [first line, second line or ""]. The second line (what happened) comes with the reveal. */
  function tagLines(row, revealed) {
    if (!row) return ["no look", ""];
    if (row.status === "forecast") {
      const out = row.outcome === true ? "fell " + short(row.outcome_date) : row.outcome === false ? "held" : "not known";
      return [K().chance(row.chance), revealed ? out : ""];
    }
    if (row.status === "already_low") return ["below a third", ""];
    if (row.status === "not_refilled") return ["not refilled", ""];
    return ["no recent look", ""];
  }
  const tagInner = (lines) => '<span class="tx"><span class="l1">' + esc(lines[0]) + "</span>" +
    (lines[1] ? '<span class="l2">' + esc(lines[1]) + "</span>" : "") + "</span>";
  function outcomeWords(row) {
    if (row.outcome === true) return "It fell below a third on " + fmtDate(row.outcome_date) + ".";
    if (row.outcome === false) return "It stayed above a third to " + fmtDate(row.window_end) + ".";
    return "Not known: too few clear looks to tell.";
  }
  function statusWords(row) {
    if (!row) return "No satellite look that day.";
    if (row.status === "already_low") return "No forecast that day: already below a third.";
    if (row.status === "not_refilled") return "No forecast until it refills" + (st.c.arm ? " to " + st.c.arm + "% full" : "") + ".";
    return "No forecast: no recent clear satellite look.";
  }

  function textWidth(t) {
    try {
      measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
      measureCtx.font = '800 15px "Atkinson Hyperlegible Next", system-ui, sans-serif';
      return measureCtx.measureText(t).width;
    } catch (e) { return String(t).length * 8.4; }
  }
  /** The real size of a tag with these words (same CSS as the tags), so the layout never under-counts. */
  function tagSizes(node, list) {
    const probe = document.createElement("span");
    probe.className = "rp-tag rp-tag-probe";
    probe.setAttribute("aria-hidden", "true");
    node.appendChild(probe);
    const out = list.map((lines) => {
      probe.innerHTML = '<span class="no">0</span>' + tagInner(lines);
      const r = probe.getBoundingClientRect();
      return r.width > 0 ? [Math.ceil(r.width), Math.ceil(r.height)]
        : [Math.ceil(Math.max(textWidth(lines[0]), textWidth(lines[1]))) + 52, lines[1] ? 46 : 36];
    });
    probe.remove();
    return out;
  }
  const attr = (o) => Object.keys(o).map((k) => k + '="' + o[k] + '"').join(" ");

  function drawSketch() {
    if (!st || !st.c.farm || !st.c.radius) return;
    const node = st.body.querySelector("[data-rp-sketch]");
    if (!node) return;
    const W = Math.max(260, Math.floor(node.clientWidth));
    st.sketchW = W;
    // UI_SPEC 5.9: 1.12 x the width on phones (taller still on the narrowest), 0.92 x on wider boxes
    const H = Math.round(Math.min(W * (W < 300 ? 1.32 : W < 480 ? 1.12 : 0.92), 480));
    const c = st.c, farm = c.farm, iss = issue(), R = c.radius, r1 = K().r1;
    const cos = Math.cos(farm.lat * Math.PI / 180);
    const scale = (Math.min(W, H) / 2 - 26) / R, cx = W / 2, cy = H / 2;
    const P = (d) => [cx + (d.lon - farm.lon) * 111.32 * cos * scale, cy - (d.lat - farm.lat) * 110.57 * scale];
    const boxes = [];
    const box = (x, y, w, h) => boxes.push({ x, y, w, h });
    const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
    let s = "";
    s += "<circle " + attr({ cx, cy, r: r1(R * scale), fill: "var(--surface-2)", stroke: "var(--line-strong)", "stroke-width": 1.5, "stroke-dasharray": "6 6" }) + "/>";
    if (R > 1) {
      s += "<circle " + attr({ cx, cy, r: r1(scale), fill: "none", stroke: "var(--line)", "stroke-width": 1.2 }) + "/>";
      s += "<text " + attr({ x: r1(cx + scale + 5), y: cy + 5, class: "rp-svg-meta" }) + ">1 km</text>";
      box(cx + scale + 2, cy - 10, 34, 18);
    }
    const kx = r1(cx + R * scale * 0.72 + 8), ky = r1(cy + R * scale * 0.72 + 16);
    s += "<text " + attr({ x: kx, y: ky, class: "rp-svg-label" }) + ">" + esc(String(R)) + " km</text>";
    box(kx - 4, ky - 15, 44, 20);
    s += '<g transform="translate(14 10)"><path d="M8 0l6 16-6-4-6 4z" fill="var(--ink)"/><text x="8" y="31" text-anchor="middle" class="rp-svg-label">N</text></g>';
    box(6, 6, 32, 34);
    box(cx - 16, cy - 16, 32, 32);
    box(cx - 48, cy + 18, 96, 38);
    const homeLabelBox = { x: cx - 48, y: cy + 20, w: 96, h: 34 };   // a leader line should not cross "Homestead"
    // both states' texts, so the tags keep their places when "Show what happened" adds to them
    const both = c.dams.map((d) => { const row = rowOf(iss, d.dam_id); return [tagLines(row, false), tagLines(row, true)]; });
    const sizes = tagSizes(node, [].concat.apply([], both));
    const items = c.dams.map((d, i) => {
      const row = rowOf(iss, d.dam_id), p = P(d), g = d.number <= 3 ? 18 : 24;
      box(p[0] - g / 2 - 6, p[1] - g / 2 - 6, g + 12, g + 12);
      const now = tagLines(row, st.revealed);
      const w = Math.max(sizes[2 * i][0], sizes[2 * i + 1][0]) + 2, h = Math.max(36, sizes[2 * i][1], sizes[2 * i + 1][1]);
      const out = Math.atan2(p[1] - cy, p[0] - cx), cands = [];
      [42, 58, 76, 98, 124, 150, 180].forEach((dist, di) => {
        for (let k = -8; k <= 8; k++) {
          const ang = out + (k * Math.PI) / 8;
          let tx = p[0] + Math.cos(ang) * (dist + Math.abs(Math.cos(ang)) * (w / 2 - 16));
          const ty = p[1] + Math.sin(ang) * dist;
          tx = Math.max(w / 2 + 4, Math.min(W - w / 2 - 4, tx));
          cands.push({ x: tx, y: ty, score: di + Math.abs(k) * 0.35 });
        }
      });
      cands.sort((a, b) => a.score - b.score);
      return { d, row, p, g, now, w, h, cands, low: !row || row.status !== "forecast" };
    });
    const segX = (ax, ay, bx, by, px, py, qx, qy) => {
      const den = (bx - ax) * (qy - py) - (by - ay) * (qx - px);
      if (Math.abs(den) < 1e-9) return false;
      const t = ((px - ax) * (qy - py) - (py - ay) * (qx - px)) / den, u = ((px - ax) * (by - ay) - (py - ay) * (bx - ax)) / den;
      return t > 0.02 && t < 0.98 && u > 0.02 && u < 0.98;
    };
    const crosses = (x1, y1, x2, y2, r) => {
      const n = Math.ceil(Math.hypot(x2 - x1, y2 - y1) / 5);
      for (let i = 1; i < n; i++) {
        const x = x1 + (x2 - x1) * i / n, y = y1 + (y2 - y1) * i / n;
        if (x > r.x && x < r.x + r.w && y > r.y && y < r.y + r.h) return true;
      }
      return false;
    };
    function layout(order) {
      const placed = [], taken = boxes.slice();
      let total = 0, fails = 0;
      order.forEach((it) => {
        let pick = null, loose = null;
        for (const cand of it.cands) {
          const r = { x: cand.x - it.w / 2 - 3, y: cand.y - it.h / 2 - 3, w: it.w + 6, h: it.h + 6 };
          if (r.y < 2 || r.y + r.h > H - 2) continue;
          if (taken.some((b) => hit(r, b))) continue;
          if (placed.some((o) => crosses(it.p[0], it.p[1], cand.x, cand.y, o.r) || crosses(o.it.p[0], o.it.p[1], o.x, o.y, r))) continue;
          if (placed.some((o) => segX(it.p[0], it.p[1], cand.x, cand.y, o.it.p[0], o.it.p[1], o.x, o.y))) {
            if (!loose) loose = { it, x: cand.x, y: cand.y, r, score: cand.score + 60 };
            continue;
          }
          if (crosses(it.p[0], it.p[1], cand.x, cand.y, homeLabelBox)) {
            if (!loose || loose.score > cand.score + 40) loose = { it, x: cand.x, y: cand.y, r, score: cand.score + 40 };
            continue;
          }
          pick = { it, x: cand.x, y: cand.y, r };
          total += cand.score;
          break;
        }
        if (!pick && loose) { pick = loose; total += loose.score; }
        if (!pick) {
          // nothing free: take the spot that covers the least of what is already there
          fails += 1;
          let bestArea = Infinity;
          it.cands.forEach((cand) => {
            const r = { x: cand.x - it.w / 2 - 3, y: cand.y - it.h / 2 - 3, w: it.w + 6, h: it.h + 6 };
            if (r.y < 2 || r.y + r.h > H - 2) return;
            const area = taken.reduce((a, b) => a + Math.max(0, Math.min(r.x + r.w, b.x + b.w) - Math.max(r.x, b.x)) *
              Math.max(0, Math.min(r.y + r.h, b.y + b.h) - Math.max(r.y, b.y)), 0) + cand.score;
            if (area < bestArea) { bestArea = area; pick = { it, x: cand.x, y: cand.y, r }; }
          });
          if (!pick) pick = { it, x: Math.max(it.w / 2 + 4, Math.min(W - it.w / 2 - 4, it.p[0])), y: Math.min(H - 22, it.p[1] + 40), r: { x: 0, y: 0, w: 0, h: 0 } };
        }
        placed.push(pick);
        taken.push(pick.r);
      });
      return { placed, score: total + fails * 100 };
    }
    const byDist = items.slice().sort((a, b) => a.d.distance_km - b.d.distance_km);
    const orders = [byDist, byDist.slice().reverse(), items.slice().sort((a, b) => b.w - a.w),
      items.slice().sort((a, b) => a.p[1] - b.p[1]), items.slice().sort((a, b) => b.p[1] - a.p[1]),
      items.slice().sort((a, b) => a.p[0] - b.p[0]), items.slice().sort((a, b) => b.p[0] - a.p[0])];
    const best = orders.map(layout).sort((a, b) => a.score - b.score)[0];
    best.placed.forEach((o) => { s += "<line " + attr({ x1: r1(o.it.p[0]), y1: r1(o.it.p[1]), x2: r1(o.x), y2: r1(o.y), stroke: "var(--ink-3)", "stroke-width": 1.4 }) + "/>"; });
    items.forEach((it) => {
      const row = it.row;
      const state = { name: it.d.name, level_pct: row ? row.level_pct : null, status: row ? row.status : "no_recent_look", issued_on: row ? row.issued_on : null };
      s += '<g transform="translate(' + r1(it.p[0] - it.g / 2) + " " + r1(it.p[1] - it.g / 2) + ')">' + K().glyph(state, it.g, true) + "</g>";
      if (st.revealed && row && row.status === "forecast" && row.outcome === true) {
        s += "<circle " + attr({ class: "rp-ring", cx: r1(it.p[0]), cy: r1(it.p[1]), r: r1(it.g / 2 + 5), fill: "none", stroke: "var(--ink)", "stroke-width": 3 }) + "/>";
      }
    });
    s += '<g transform="translate(' + r1(cx - 10) + " " + r1(cy - 10) + ')" color="var(--ink)"><rect x="-3" y="-3" width="26" height="26" rx="8" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.6"/>' +
      '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><use href="#i-home"/></svg></g>';
    s += "<text " + attr({ x: cx, y: cy + 34, "text-anchor": "middle", class: "rp-svg-label" }) + ">Homestead</text>";
    s += "<text " + attr({ x: cx, y: cy + 49, "text-anchor": "middle", class: "rp-svg-meta" }) + ">(demo point)</text>";
    node.style.height = H + "px";
    node.innerHTML = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H + '" aria-hidden="true" focusable="false">' + s + "</svg>" +
      best.placed.slice().sort((a, b) => a.it.d.number - b.it.d.number).map((o) => {   // Tab steps Dam 1, 2, 3...
        const it = o.it, row = it.row, d = it.d;
        const fell = st.revealed && row && row.status === "forecast" && row.outcome === true;
        const aria = d.name + ": " + (row && row.status === "forecast" ? K().chance(row.chance) + " that it falls below a third by " + short(row.window_end) +
          (st.revealed ? ". " + outcomeWords(row) : "") : statusWords(row));
        return '<button type="button" class="rp-tag' + (it.low ? " is-low" : "") + (fell ? " is-fell" : "") + (st.hot === d.number ? " is-on" : "") +
          '" data-rp-dam="' + d.number + '" style="left:' + Math.round(o.x) + "px;top:" + Math.round(o.y) + 'px" aria-label="' + esc(aria) + '">' +
          '<span class="no" aria-hidden="true">' + d.number + '</span><span aria-hidden="true">' + tagInner(it.now) + "</span></button>";
      }).join("");
  }

  // ---- the score, the dams, the region ----
  function scoreHtml() {
    const c = st.c, iss = issue();
    const rows = c.dams.map((d) => ({ d, row: rowOf(iss, d.dam_id) }));
    const fc = rows.filter((x) => x.row && x.row.status === "forecast");
    const sum = fc.reduce((a, x) => a + x.row.chance, 0);
    const fell = fc.filter((x) => x.row.outcome === true);
    const unknown = fc.filter((x) => x.row.outcome !== true && x.row.outcome !== false);
    const v = Math.round(sum);
    const expected = v < 1 ? "less than 1" : "about " + v;
    const groups = { already_low: [], not_refilled: [], other: [] };
    rows.filter((x) => !x.row || x.row.status !== "forecast").forEach((x) => {
      groups[x.row && groups[x.row.status] ? x.row.status : "other"].push(x.d.name);
    });
    const why = [];
    if (groups.already_low.length) why.push(names(groups.already_low) + (groups.already_low.length > 1 ? " were" : " was") + " already below a third");
    if (groups.not_refilled.length) why.push(names(groups.not_refilled) + " had not refilled" + (c.arm ? " to " + c.arm + "% full" : ""));
    if (groups.other.length) why.push(names(groups.other) + " had no recent clear look");
    const whyLine = why.length ? why.join("; ") + ", so had no forecast." : "";
    const happenedSub = !st.revealed ? "Show what happened to see"
      : (fell.length ? "fell below a third " + within(c) + ": " + names(fell.map((x) => x.d.name + " (" + short(x.row.outcome_date) + ")"))
        : "of them fell below a third " + within(c)) + (unknown.length ? ". " + unknown.length + " cannot be checked" : "");
    const all = st.revealed && c.part && c.part.all_dates_takeaway ? '<p class="rp-all">' + esc(c.part.all_dates_takeaway) + "</p>" : "";
    return '<div class="rp-tiles">' +
      '<div class="rp-tile"><p class="eyebrow">Expected</p><p class="rp-big">' + esc(expected) + "</p>" +
      "<p>" + esc((v <= 1 ? "fall" : "falls") + " below a third: the " + fc.length + " chances that day, added up") + "</p></div>" +
      '<div class="rp-tile' + (st.revealed ? " is-shown" : " is-hidden") + '"><p class="eyebrow">Happened</p><p class="rp-big">' +
      (st.revealed ? esc(String(fell.length)) : '<span aria-hidden="true">?</span><span class="vh">Not shown yet</span>') + "</p>" +
      "<p>" + esc(happenedSub) + "</p></div></div>" +
      (whyLine ? '<p class="small rp-why">' + esc(whyLine) + "</p>" : "") + all;
  }

  function rowsHtml() {
    const c = st.c, iss = issue();
    return c.dams.map((d) => {
      const row = rowOf(iss, d.dam_id);
      const state = { name: d.name, level_pct: row ? row.level_pct : null, status: row ? row.status : "no_recent_look", issued_on: row ? row.issued_on : null };
      const look = row && row.issued_on ? D.format.fullness(row.level_pct) + " at its " + short(row.issued_on) + " look" : "no clear look";
      const meta = look + " · " + Number(d.distance_km).toFixed(1) + " km";
      let right, more;
      if (row && row.status === "forecast") {
        right = '<span class="rp-ch">' + esc(K().chance(row.chance)) + "</span>";
        more = '<p class="rp-dots">' + K().dots(row.chance, 6, K().chance(row.chance) + " by " + short(row.window_end), true) +
          "<span>chance it falls below a third by " + esc(short(row.window_end)) + "</span></p>";
        if (st.revealed) {
          more += '<p class="rp-out' + (row.outcome === true ? " is-fell" : "") + '">' +
            (row.outcome === true ? '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false"><circle cx="9" cy="9" r="6.5" fill="none" stroke="currentColor" stroke-width="3"/></svg>'
              : icon(row.outcome === false ? "i-check" : "i-info", "sm")) + "<span>" + esc(outcomeWords(row)) + "</span></p>";
        }
      } else {
        right = '<span class="rp-low">' + esc(row && row.status === "already_low" ? "Below a third" : row && row.status === "not_refilled" ? "Not refilled" : "No look") + "</span>";
        more = '<p class="small">' + esc(statusWords(row)) + "</p>";
      }
      const season = c.part && c.part.dams.some((x) => x.dam_id === d.dam_id)
        ? '<a class="rp-season" href="#proof/dams/dam-' + d.number + '" data-replace>' + esc(d.name + "'s whole " + c.season + " season") + icon("i-chev", "sm") + "</a>" : "";
      return '<li class="rp-row' + (st.hot === d.number ? " is-hot" : "") + '" id="rp-dam-' + d.number + '" tabindex="-1">' +
        '<div class="rp-row-top">' + K().glyph(state, 44, true) + '<span class="rp-name"><b>' + esc(d.name) + '</b><span class="meta">' + esc(meta) +
        "</span></span>" + right + "</div>" + more + season + "</li>";
    }).join("");
  }

  function regionHtml() {
    const c = st.c, iss = issue();
    const t = regionTally(iss);
    const date = fmtDate(iss.issue_date);
    if (!st.revealed) {
      return "<p>On " + esc(date) + ", " + count(t.forecasts) + " of the " + count(iss.rows.length) + " dam-sized waterbodies DamDays follows here, " +
        "mostly farm dams, had a forecast. Show what happened to compare.</p>";
    }
    let J = 0, S = 0, F = 0;
    c.issues.forEach((x) => { const y = regionTally(x); J += y.judged; S += y.sum; F += y.fell; });
    return "<p>On " + esc(date) + ": " + count(t.judged) + " forecasts we can check; their chances added up to " + esc(K().sumWords(t.sum)) +
      " below a third " + esc(within(c)) + ", and <b>" + count(t.fell) + " happened</b>.</p>" +
      (c.issues.length > 1 ? "<p>On all " + esc(K().numberWord(c.issues.length)) + " dates: " + count(J) + " forecasts expected " +
        esc(K().sumWords(S)) + "; <b>" + count(F) + " happened</b>.</p>" : "");
  }

  function numbersHtml() {
    if (!st.revealed) return "";
    const iss = issue(), t = regionTally(iss);
    if (!t.judged) return '<p class="small">No forecasts from this date can be checked yet.</p>';
    const likelyIn = D.settings.likelyInTen;
    const tally = { hits: 0, alarms: 0, misses: 0, clears: 0 };
    t.rows.forEach((r) => {
      const likely = D.colors.isLikely(r.chance);
      if (likely && r.outcome) tally.hits += 1; else if (likely) tally.alarms += 1; else if (r.outcome) tally.misses += 1; else tally.clears += 1;
    });
    const bands = D.settings.chanceBands.map((band) => {
      const inBand = t.rows.filter((r) => D.colors.bandFor(r.chance) === band);
      return { band, n: inBand.length, expected: inBand.reduce((a, r) => a + r.chance, 0), fell: inBand.filter((r) => r.outcome).length };
    }).filter((b) => b.n > 0);
    const unknown = t.forecasts - t.judged;
    const n = (v, one, many) => esc(D.format.count(v, one, many));       // "63 hits", "1 miss", "43 misses"
    return '<details class="more ps-numbers" data-numbers' + (st.numbersOpen ? " open" : "") + "><summary>" + icon("i-chart") +
      "Show the numbers for " + esc(fmtDate(iss.issue_date)) + icon("i-plus", "plus") + '</summary><div class="body">' +
      '<div class="table-scroll"><table class="data rp-tally"><caption>Hits and misses ("likely" is a chance of ' + likelyIn + " in 10 or more)</caption>" +
      '<thead><tr><th scope="col"><span class="vh">We said</span></th><th scope="col">Fell below a third</th><th scope="col">Stayed above</th></tr></thead><tbody>' +
      '<tr><th scope="row">We said likely</th><td>' + n(tally.hits, "hit") + "</td><td>" + n(tally.alarms, "false alarm") + "</td></tr>" +
      '<tr><th scope="row">We said unlikely</th><td>' + n(tally.misses, "miss", "misses") + "</td><td>" + n(tally.clears, "correct all-clear") + "</td></tr></tbody></table></div>" +
      '<div class="table-scroll"><table class="data"><caption>Did the chances come true?</caption><thead><tr><th scope="col">Chance we gave</th>' +
      '<th scope="col">Dams</th><th scope="col">Expected to fall</th><th scope="col">Did fall</th></tr></thead><tbody>' +
      bands.map((b) => '<tr><th scope="row"><span class="rp-swatch" style="background:' + esc(b.band.color) + '" aria-hidden="true"></span>' +
        esc(b.band.label) + "</th><td>" + count(b.n) + "</td><td>" + b.expected.toFixed(1) + "</td><td>" + count(b.fell) + "</td></tr>").join("") +
      "</tbody></table></div>" +
      '<p class="small">Expected to fall: the chances added up: ten dams at 3 in 10 each means about 3 should fall. Not counted: ' +
      n(unknown, "dam") + " with too few clear satellite looks to know.</p>" +
      "</div></details>";
  }

  // ---- the old region map (js/views/rewind.js), driven by this sheet ----
  function syncLegacy() {
    if (!st || !st.regionOpen) return;
    const sel = document.getElementById("rewind-issue"), btn = document.getElementById("rewind-reveal");
    if (!sel || !st.body.contains(sel)) return;
    const want = issue().issue_date;
    if (sel.value !== want && Array.from(sel.options).some((o) => o.value === want)) {
      sel.value = want;
      sel.dispatchEvent(new Event("change"));
    }
    if (btn && (btn.getAttribute("aria-pressed") === "true") !== st.revealed) btn.click();
  }

  /** Wide screens: the sheet widens while the region map is open, so a dam's card sits beside the map (proof.css). */
  function widenFor(open) {
    const sheet = D.sheet && D.sheet.el;
    if (!sheet) return;
    const wide = open && window.matchMedia && window.matchMedia("(min-width: 1024px)").matches;
    sheet.classList.toggle("is-wider", Boolean(wide));
    sheet.classList.toggle("is-wide", !wide);
    if (D.views && D.views.rewind && D.views.rewind.show) setTimeout(() => { try { D.views.rewind.show(); } catch (e) { /* not mounted */ } }, 260);
    setTimeout(resize, 260);
  }

  function toggleMap() {
    const host = st.body.querySelector("#rp-region-host"), btn = st.body.querySelector("[data-rp-map]");
    const bar = st.body.querySelector("[data-rp-mapbar]");
    st.regionOpen = !st.regionOpen;
    host.hidden = !st.regionOpen;
    if (bar) bar.hidden = !st.regionOpen;
    btn.setAttribute("aria-expanded", String(st.regionOpen));
    btn.querySelector("span").textContent = st.regionOpen ? "Hide the region map" : "See the whole region on the map";
    widenFor(st.regionOpen);
    if (!st.regionOpen) return;
    const mine = st;
    if (!host.querySelector("#view-rewind")) host.innerHTML = '<p class="small rp-map-wait">Loading the map.</p>';
    D.legacy.mount("rewind", host).then((ok) => {
      if (st !== mine) return;
      const wait = host.querySelector(".rp-map-wait");
      if (wait) wait.remove();
      if (!ok) { host.innerHTML = '<p class="small">The region map is not available in this copy of the app.</p>'; return; }
      syncLegacy();
    }, () => {
      if (st === mine) host.innerHTML = '<p class="small">The map could not load. Check your signal and try again.</p>';
    });
  }

  // ---- state changes ----
  function update() {
    const b = st.body;
    b.querySelectorAll("[data-rp-date]").forEach((btn) => btn.setAttribute("aria-pressed", String(+btn.dataset.rpDate === st.idx)));
    b.querySelectorAll("[data-rp-select]").forEach((sel) => { sel.value = String(st.idx); });
    // both copies: under the dates at the top, and the bar above the region map
    b.querySelectorAll("[data-rp-reveal]").forEach((rv) => {
      rv.setAttribute("aria-pressed", String(st.revealed));
      rv.innerHTML = icon(st.revealed ? "i-rewind" : "i-check") + "<span>" + (st.revealed ? "Hide what happened" : "Show what happened") + "</span>";
    });
    if (st.c.farm) {
      drawSketch();
      b.querySelector("[data-rp-score]").innerHTML = scoreHtml();
      b.querySelector("[data-rp-rows]").innerHTML = rowsHtml();
    }
    b.querySelector("[data-rp-region]").innerHTML = regionHtml();
    b.querySelector("[data-rp-numbers]").innerHTML = numbersHtml();
    syncLegacy();
  }

  function setIdx(i) {
    if (i === st.idx || !st.c.issues[i]) return;
    st.idx = i;
    st.revealed = false;
    st.hot = null;
    update();
  }

  function focusDam(n) {
    st.hot = n;
    st.body.querySelectorAll(".rp-tag").forEach((t) => t.classList.toggle("is-on", +t.dataset.rpDam === n));
    st.body.querySelectorAll(".rp-row").forEach((r) => r.classList.toggle("is-hot", r.id === "rp-dam-" + n));
    const row = st.body.querySelector("#rp-dam-" + n);
    if (row) {
      const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      row.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
      try { row.focus({ preventScroll: true }); } catch (e) { row.focus(); }
    }
  }

  function wire(body) {
    if (wiredBody === body) return;
    wiredBody = body;
    body.addEventListener("click", (event) => {
      if (!st || st.body !== body) return;
      const t = event.target;
      if (!(t instanceof Element)) return;
      const date = t.closest("[data-rp-date]");
      if (date) { setIdx(+date.dataset.rpDate); return; }
      if (t.closest("[data-rp-reveal]")) { st.revealed = !st.revealed; update(); return; }
      const tag = t.closest("[data-rp-dam]");
      if (tag) { focusDam(+tag.dataset.rpDam); return; }
      if (t.closest("[data-rp-map]")) toggleMap();
    });
    body.addEventListener("change", (event) => {
      if (st && st.body === body && event.target.matches && event.target.matches("[data-rp-select]")) setIdx(+event.target.value);
    });
    body.addEventListener("toggle", (event) => {
      if (st && st.body === body && event.target.matches && event.target.matches("[data-rp-numbers] details")) st.numbersOpen = event.target.open;
    }, true);
  }

  // =====================================================================
  // Public
  // =====================================================================
  function render(body, data) {
    cleanup();
    const c = ctxFrom(data);
    if (!c.issues.length) {
      body.innerHTML = '<p class="ps-lead">This dataset has no past forecasts to rewind to.</p>';
      return;
    }
    st = { c, body, idx: defaultIndex(c), revealed: false, hot: null, regionOpen: false, numbersOpen: false, sketchW: 0 };
    body.innerHTML = shellHtml();
    wire(body);
    update();
    const mine = st;
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (st === mine) drawSketch(); });
  }

  /** The sheet is closing or being replaced: put the old map back where DamDays.legacy.mount looks for it. */
  function cleanup() {
    const sec = document.getElementById("view-rewind"), store = document.getElementById("legacy-store");
    if (sec && store && sec.parentNode !== store) store.appendChild(sec);
    if (st && st.regionOpen && D.sheet && D.sheet.el) D.sheet.el.classList.remove("is-wider");
    st = null;
  }

  function resize() {
    if (!st || !st.c.farm) return;
    const node = st.body.querySelector("[data-rp-sketch]");
    if (node && Math.abs(Math.floor(node.clientWidth) - st.sketchW) > 4) drawSketch();
  }

  return { render, cleanup, resize, cardInfo, label, available };
})();
