/* views/farm.js (WP-C)
 * MY FARM (UI_SPEC 3.2, 5.9 to 5.12, 5.24). Farmers don't open apps or emails, so DamDays is
 * one text message a week; this page is where a farm is set up and where the farmer looks closer.
 *
 *   #farm             the farm: headline (the dam with the fewest days), the farm from above
 *                     (tile-free sketch, or the real map), the dams as rows (fewest days or water
 *                     run), the farm's record over the last 10 years, all dams as a table
 *   #farm/dam-N[/x]   the dam sheet (js/dam-sheet.js, WP-D) for Dam N; x = counted|record|history|about
 *   #farm/setup       sheet: pick a demo farm, tap the map to set your homestead, the circle size
 *   #farm/text        sheet: this week's text as it arrives, and the longer version (app or email)
 *
 * A farm is a homestead point and a circle: its dams are every dam the satellites can see within
 * it, numbered by distance (Dam 1 is the closest), made by js/text.js (a line-for-line port of
 * notify/message.py, checked by app/tools/check_text_port.js). A demo farm at its own radius shows
 * farms.json's text word for word. Days are counted from the day of this week's text.
 * Wording: "%" only means how full; chances "N in 10"; a 0% dam is "no water seen".
 *
 * Public: DamDays.farm.current(), DamDays.farm.damContext(n, deep), DamDays.farm.useDemo(id).
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.farm = (function () {
  "use strict";

  const D = window.DamDays;
  const esc = (t) => String(t === null || t === undefined ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const icon = (id, cls, label) => D.icon(id, cls, label);
  const txt = () => D.text;
  const fmt = () => D.format;
  const S = () => D.settings || {};
  const MAX_RADIUS_KM = 10;
  const MIN_RADIUS_KM = 0.5;
  const ROW_LIMIT = 8;            // a farm with many dams shows the 8 with the fewest days (plus every dam below a third)
  const MANY = 10;                // ... when it has more than this many dams

  let root = null;
  let data = null;                // the prepared data object (grows as parts arrive)
  let sketchCtl = null;
  let leafletFarm = null;         // { map, layers } for the "Map" view of the farm
  let setupMap = null;            // the setup sheet's map
  let firstRows = true;
  const state = {
    demo: null,                   // the demo farm (a farms.json farm), or null for your own point
    lat: null, lon: null, radiusKm: 3,
    dams: [],                     // the farm's dams, numbered by distance, with kind, days_left, row, record
    textDate: null,
    order: "fewest",              // "fewest" | "run"
    showAll: false,
    view: "sketch",               // "sketch" | "map"
    openNo: null,
    pending: false,               // dams still loading (a part of the data)
  };

  // ===========================================================================
  // Data
  // ===========================================================================
  function want(part) {
    const dd = D.data;
    if (dd && typeof dd.need === "function") {
      return Promise.resolve(dd.need(part)).then((x) => (x && x.meta ? x : dd.load()), () => dd.load());
    }
    return dd.load();
  }
  const farmsOf = (x) => (x && x.farms && x.farms.farms ? x.farms.farms : []);
  const trackOf = (x) => (x && (x.trackRecord || x.track_record)) || null;
  const recordsOf = (x) => { const t = trackOf(x); return t && t.dams ? t.dams : null; };
  // Every dam of the region is loaded (the "core" part, or the whole bundle): needed for your own point.
  const hasCore = (x) => Boolean(x && x.liveIssue && Array.isArray(x.dams) && x.dams.length && x.meta &&
    x.dams.length >= ((x.meta.coverage && x.meta.coverage.dams) || 0));
  const appDoc = (x) => (x && x.liveIssue && x.dams ? { dams: x.dams, issues: [x.liveIssue] } : null);
  const textDateOf = (x) => (x && (x.textDate || (x.farms && x.farms.date))) || null;
  const visibleFarms = () => farmsOf(data).filter((f) => !(S().hiddenFarmIds || []).includes(f.farm_id));
  const armPct = () => (data && data.meta && data.meta.arm_level_pct) || null;
  const regionName = () => (data && data.meta && data.meta.region ? data.meta.region.name : "the region");
  const inRegion = (lat, lon) => {
    const box = data && data.meta && data.meta.region ? data.meta.region.bbox : null;
    return !box || (lat >= box[0] && lat <= box[1] && lon >= box[2] && lon <= box[3]);
  };

  // ===========================================================================
  // The farm and its dams
  // ===========================================================================
  /** The farm as js/text.js wants it, with what the views need. */
  function farmObj(st) {
    st = st || state;
    const demo = st.demo;
    return {
      farm_id: demo ? demo.farm_id : "my-farm",
      name: demo ? demo.name : "Your farm",
      short_name: demo ? (D.welcome && D.welcome.shortName ? D.welcome.shortName(demo.name) : String(demo.name).replace(/\s*\(.*\)\s*$/, "")) : "Your farm",
      near_town: demo ? demo.near_town : null,
      lat: st.lat, lon: st.lon, radius_km: st.radiusKm,
      demo: Boolean(demo),
      dams_in_app: demo ? Boolean(demo.dams_in_app) : true,
      region_name: demo ? demo.region_name : regionName(),
    };
  }

  /** Is this the demo farm exactly as farms.json made it (same point, same radius)? Then its text is farms.sms. */
  const asPublished = (st) => Boolean(st.demo && st.radiusKm === st.demo.radius_km);

  /** Which forecasts the farm's dams come from; null when a part of the data must load first. */
  function sourceFor(st) {
    if (asPublished(st)) return { dams: st.demo.dams };
    if (st.demo && !st.demo.dams_in_app) return { doc: txt().docFromDams(st.demo.dams) };
    return hasCore(data) ? { doc: appDoc(data) } : null;
  }

  function enrich(list, textDate) {
    const records = recordsOf(data);
    const rows = data && data.liveIssue && data.liveIssue.rowsByDam ? data.liveIssue.rowsByDam : null;
    return list.map((d) => {
      let kind = "no_look", days = null;
      try {
        kind = txt().kind(d, textDate);
        days = kind === "forecast" ? txt().daysLeft(d, textDate) : null;
      } catch (e) { /* a look after the text's date: treat as no forecast */ }
      const row = rows ? rows.get(d.dam_id) || null : null;
      return Object.assign({}, d, {
        kind, days_left: days, row,
        record: records ? (records[d.dam_id] || null) : undefined,
        in_app: Boolean(row) && (!state.demo || state.demo.dams_in_app !== false),
      });
    });
  }

  /** The dams for a farm state, or null while the data they need is loading. */
  function damsFor(st) {
    const src = sourceFor(st);
    if (!src) return null;
    const td = state.textDate;
    if (src.dams) return enrich(src.dams.slice().sort((a, b) => a.number - b.number), td);
    return enrich(txt().damsForFarm(farmObj(st), src.doc), td);
  }

  function smsFor(st, dams) {
    if (asPublished(st) && st.demo.sms) return st.demo.sms;
    return txt().smsForDams(dams, state.textDate, st.radiusKm);
  }
  function longFor(st, dams) {
    return txt().longForDams(dams, state.textDate, farmObj(st).name, st.radiusKm, recordsOf(data));
  }

  // ===========================================================================
  // Small wording helpers
  // ===========================================================================
  // The text card and the demo note come from js/views/welcome.js (loaded with the page; render() loads it
  // again if a weak signal dropped it). Plain fallbacks keep My farm working without it.
  const demoNote = (demo) => (D.welcome && D.welcome.demoNote ? D.welcome.demoNote(demo) : "Its dams are real; the homestead point is made up.");
  const smsCard = (sms, opts) => (D.welcome && D.welcome.smsHtml ? D.welcome.smsHtml(sms, opts)
    : '<figure class="sms"><div class="bubble">' + String(sms).split("\n").map((l) => '<span class="ln">' + esc(l) + "</span>").join("") + "</div></figure>");
  const short = (iso) => (iso ? txt().shortDate(iso) : "");
  const km = (x) => txt().oneDecimal(x);
  const capDays = () => txt().CAP_DAYS;

  function latestLook(dams) {
    const looks = dams.filter((d) => d.kind !== "no_look" && d.issued_on).map((d) => d.issued_on);
    return looks.length ? looks.reduce((a, b) => (b > a ? b : a)) : null;
  }
  function fewest(dams) {
    const fc = dams.filter((d) => d.kind === "forecast");
    fc.sort((a, b) => a.days_left - b.days_left || a.number - b.number);
    return fc;
  }
  function weakRecord(r) {
    return Boolean(r && txt().hasTrackRecord(r) && fmt().recordBelowAim(r.held, r.judged));
  }
  function daysTag(d, rank, n) {
    if (d.kind === "forecast") {
      if (d.days_left <= 0) return { text: "may be below a third", low: true, label: d.name + ": may be below a third now", prio: 0 };
      const t = d.days_left >= capDays() ? "6 months+" : d.days_left + (d.days_left === 1 ? " day" : " days");
      // prio (sketch.js): 0 is never dropped first; from 1 to 2, the longer a dam lasts the sooner its tag gives way
      const prio = rank === 0 ? 0 : (typeof rank === "number" && n ? 1 + rank / n : 1);
      return { text: t, label: d.name + ": " + (t === "6 months+" ? "6 months or more" : "at least " + t) + " before it drops below a third", prio };
    }
    if (d.kind === "low") return { text: "below a third", low: true, label: d.name + ": already below a third", prio: 0 };
    if (d.kind === "not_refilled") return { text: "no forecast", quiet: true, label: d.name + ": no forecast until it refills", prio: 2 };
    return { text: "no recent look", quiet: true, label: d.name + ": no clear satellite look lately", prio: 2 };
  }
  function countsOf(dams) {
    const c = { forecast: 0, low: 0, not_refilled: 0, no_look: 0 };
    dams.forEach((d) => { c[d.kind] = (c[d.kind] || 0) + 1; });
    return c;
  }
  function refillWords() {
    const p = armPct();
    return p ? "No forecast until it refills to " + p + "% full" : "No forecast until it refills";
  }

  // ===========================================================================
  // Rendering the page
  // ===========================================================================
  function headHtml() {
    const f = farmObj();
    const n = state.dams.length;
    const count = n === 0 ? "No dams the satellites can see within " + esc(f.radius_km) + " km of the homestead"
      : n + " dam" + (n === 1 ? "" : "s") + " the satellites can see within " + esc(f.radius_km) + " km of the homestead";
    let note = "";
    if (f.demo) {
      note = esc(demoNote(state.demo));
      if (!state.demo.dams_in_app) {
        note += " It is in " + esc(state.demo.region_name) + ", outside the region the app's maps hold (" + esc(regionName()) +
          "), so you see only this farm's own dams.";
      }
    } else {
      note = "Your homestead point (" + state.lat.toFixed(4) + ", " + state.lon.toFixed(4) + ") stays on this phone.";
      if (!inRegion(state.lat, state.lon)) note += " DamDays has forecasts for " + esc(regionName()) + " only, so dams outside it are not shown.";
    }
    return '<header class="farm-head">' +
      '<div class="farm-head-top"><p class="eyebrow">My farm · ' + (f.demo ? "demo homestead" : "your homestead") + "</p>" +
      '<a class="btn btn-quiet farm-change" href="#farm/setup">' + icon("i-pin", "sm") + "Change</a></div>" +
      '<h1 id="farm-h1">' + esc(f.short_name) + "</h1>" +
      '<p class="meta farm-count">' + count + "</p>" +
      '<p class="farm-note">' + note + "</p></header>";
  }

  function headlineHtml() {
    const dams = state.dams;
    const look = latestLook(dams);
    const day = txt().dateText(state.textDate);
    const chip = look ? '<span class="chip">' + icon("i-sat") + "Dams seen " + esc(short(look)) + " · text of " + esc(day) + "</span>" : "";
    if (!dams.length) {
      return '<div class="headline is-empty"><p class="eyebrow">No dams in the circle</p>' +
        '<p class="who">No dams the satellites can see within ' + esc(state.radiusKm) + " km of this point.</p>" +
        '<p class="caution">DamDays follows dams of about half a hectare to 5 hectares. Try a bigger circle, or move the homestead.</p>' +
        '<a class="btn btn-primary" href="#farm/setup">Change the homestead or the circle</a></div>';
    }
    const fc = fewest(dams);
    if (!fc.length) {
      const c = countsOf(dams);
      const why = [];
      if (c.low) why.push("<b>" + c.low + "</b> already below a third");
      if (c.not_refilled) why.push("<b>" + c.not_refilled + "</b> waiting to refill");
      if (c.no_look) why.push("<b>" + c.no_look + "</b> with no clear satellite look lately");
      return '<div class="headline is-none"><p class="eyebrow">This week</p>' +
        '<p class="who">No dam on this farm has a forecast this week</p>' +
        '<p class="caution">' + why.join(" · ") + "</p>" + chip + "</div>";
    }
    const d = fc[0];
    let big, before, extra = "";
    if (d.days_left <= 0) {
      big = '<p class="bigdays is-words"><span class="n-words">may be below a third now</span></p>';
      before = "";
      extra = '<p class="caution">Its cautious number of days has run out since its ' + esc(short(d.issued_on)) + " satellite look.</p>";
    } else if (d.days_left >= capDays()) {
      big = '<p class="bigdays"><span class="n n-cap">6 months+</span></p>';
      before = '<p class="before">before it drops below a third</p>';
    } else {
      big = '<p class="bigdays"><span class="pre">at least</span><span class="n">' + d.days_left + '</span><span class="post">day' + (d.days_left === 1 ? "" : "s") + "</span></p>";
      before = '<p class="before">before it drops below a third</p>';
      if (d.days_left < 7) extra = '<p class="caution soon"><b>It could drop below a third within days.</b></p>';
    }
    const label = "Fewest days on this farm: " + d.name + ", " +
      (d.days_left <= 0 ? "may be below a third now" : d.days_left >= capDays() ? "6 months or more" : "at least " + d.days_left + " days") +
      " before it drops below a third. Open " + d.name;
    const cautious = d.days_left <= 0 ? ""
      : '<p class="caution">Cautious: built to hold 9 times in 10 across all dams (a little less often for spring looks), so it will most likely last longer.</p>';
    // this dam's own record under the 9 in 10 aim: say so here, where the decision is made, not only in its row
    const weak = weakRecord(d.record)
      ? '<p class="caution weak-rec">' + icon("i-tally", "sm") + "<span>On " + esc(d.name) + " our record is lower: held " + txt().countText(d.record.held) +
        " of " + txt().countText(d.record.judged) + " times, so give the days some extra margin.</span></p>" : "";
    const fullLabel = label + (weak ? ". Our record on " + d.name + " is lower: give the days some extra margin" : "");
    return '<a class="headline" href="#farm/dam-' + d.number + '" data-dam="' + d.number + '" aria-label="' + esc(fullLabel) + '">' +
      '<span class="chev">' + icon("i-chev") + "</span>" +
      '<p class="eyebrow">Fewest days on this farm</p><p class="who">' + esc(d.name) + "</p>" + big + before + extra + cautious + weak + chip + "</a>";
  }

  function countsHtml() {
    const c = countsOf(state.dams);
    if (!state.dams.length) return "";
    const parts = [];
    parts.push("<span><b>" + c.forecast + "</b> with a forecast</span>");
    if (c.low) parts.push("<span><b>" + c.low + "</b> already below a third</span>");
    if (c.not_refilled) parts.push("<span><b>" + c.not_refilled + "</b> waiting to refill</span>");
    if (c.no_look) parts.push("<span><b>" + c.no_look + "</b> with no recent look</span>");
    return '<p class="counts">' + parts.join("") + "</p>";
  }

  function rowHtml(d, i, look) {
    const f = fmt();
    const r = d.record;
    let rec = "";
    if (r !== undefined) {
      rec = !txt().hasTrackRecord(r)
        ? '<span class="rec">' + icon("i-tally", "sm") + "Our record: not enough history</span>"
        : '<span class="rec">' + icon("i-tally", "sm") + "Our record: held " + txt().countText(r.held) + " of " + txt().countText(r.judged) + " times" +
          (weakRecord(r) ? ' · <span class="weak">give extra margin</span>' : "") + "</span>";
    }
    let right, facts;
    if (d.kind === "forecast") {
      if (d.days_left <= 0) right = '<span class="days"><span class="low">May be below<br>a third now</span></span>';
      else if (d.days_left >= capDays()) right = '<span class="days"><b class="cap">6 months+</b></span>';
      else right = '<span class="days"><small>at least</small><b>' + d.days_left + "</b><span>day" + (d.days_left === 1 ? "" : "s") + "</span></span>";
      facts = '<span class="ch">' + D.sketch.chanceDot(d.chance) + esc(f.chance(d.chance)) + " by " + esc(short(d.window_end)) + "</span>" + rec;
    } else if (d.kind === "low") {
      right = '<span class="days"><span class="low">Below<br>a third</span></span>';
      facts = "<span>" + (d.level_pct === 0 ? "No water seen at its last clear look (one look can be wrong). " : "") + esc(refillWords()) + ".</span>" + rec;
    } else if (d.kind === "not_refilled") {
      right = '<span class="days"><span class="low quiet">No<br>forecast</span></span>';
      facts = "<span>" + esc(refillWords()) + ".</span>" + rec;
    } else {
      right = '<span class="days"><span class="low quiet">No recent<br>look</span></span>';
      facts = "<span>No clear satellite look in the last " + txt().RECENT_LOOK_DAYS + " days, so no forecast right now.</span>" + rec;
    }
    const lookNote = d.issued_on && look && d.issued_on !== look ? " · " + short(d.issued_on) + " look" : "";
    const meta = esc(f.fullness(d.level_pct)) + " · " + km(d.distance_km) + " km" + esc(lookNote);
    return '<li><a class="row' + (state.openNo === d.number ? " is-hot" : "") + '" href="#farm/dam-' + d.number + '" data-dam="' + d.number + '" style="--i:' + i + '">' +
      D.sketch.glyph(d, 48, true) +
      '<span class="row-main"><span class="name">' + esc(d.name) + '</span><span class="meta">' + meta + "</span></span>" + right +
      '<span class="facts">' + facts + "</span></a></li>";
  }

  /** Which dams get a row (and a tag): every one, or on a big farm the 8 with the fewest days and every dam below a third. */
  function shownSet() {
    const dams = state.dams;
    if (dams.length <= MANY || state.showAll) return new Set(dams.map((d) => d.number));
    const set = new Set();
    dams.filter((d) => d.kind === "low").forEach((d) => set.add(d.number));
    fewest(dams).slice(0, ROW_LIMIT).forEach((d) => set.add(d.number));
    return set;
  }
  function tagSet() {
    const dams = state.dams;
    if (dams.length <= MANY) return new Set(dams.map((d) => d.number));
    const set = new Set();
    dams.filter((d) => d.kind === "low").forEach((d) => set.add(d.number));
    fewest(dams).slice(0, ROW_LIMIT).forEach((d) => set.add(d.number));
    return set;
  }

  function rowsHtml() {
    const dams = state.dams;
    if (!dams.length) return "";
    const look = latestLook(dams);
    const shown = shownSet();
    const anim = firstRows ? " first" : "";
    let i = 0;
    const list = (arr) => '<ol class="rows' + anim + '">' + arr.map((d) => rowHtml(d, i++, look)).join("") + "</ol>";
    let html = "";
    if (state.order === "fewest") {
      const low = dams.filter((d) => d.kind === "low" && shown.has(d.number));
      const fc = fewest(dams).filter((d) => shown.has(d.number));
      const none = dams.filter((d) => (d.kind === "not_refilled" || d.kind === "no_look") && shown.has(d.number));
      if (low.length) html += '<p class="eyebrow group-label">Already below a third</p>' + list(low);
      if (fc.length) html += '<p class="eyebrow group-label">Fewest days first</p>' + list(fc);
      if (none.length) html += '<p class="eyebrow group-label">No forecast this week</p>' + list(none);
    } else {
      const arr = dams.slice().sort((a, b) => a.number - b.number);
      const cut = dams.length > MANY && !state.showAll ? arr.slice(0, ROW_LIMIT) : arr;
      html += '<p class="eyebrow group-label">Water run: closest to the homestead first</p>' + list(cut);
    }
    const hiddenCount = state.order === "fewest" ? dams.length - shown.size : (dams.length > MANY && !state.showAll ? dams.length - ROW_LIMIT : 0);
    if (hiddenCount > 0) {
      html += '<button class="btn btn-quiet btn-block show-all" type="button" data-show-all>Show all ' + dams.length + " dams</button>";
    }
    return html;
  }

  function recordHtml() {
    const recs = recordsOf(data);
    const dams = state.dams;
    if (!dams.length || !recs) return "";
    const t = txt(), f = fmt();
    const track = trackOf(data);
    const span = (track && track.label) || t.TRACK_RECORD_SPAN;
    const withRec = dams.filter((d) => t.hasTrackRecord(recs[d.dam_id]));
    const tipText = (track && track.tip) || t.TRACK_RECORD_HOW;
    const tip = '<button type="button" class="tip" aria-expanded="false" aria-label="How we checked our record">?</button>' +
      '<span class="tip-text" hidden>' + esc(tipText) + "</span>";
    if (!withRec.length) {
      return '<section class="farm-record"><h2 class="eyebrow">Our record on this farm ' + tip + "</h2><p>Too few past forecasts on these dams to judge.</p></section>";
    }
    const held = withRec.reduce((s, d) => s + recs[d.dam_id].held, 0);
    const judged = withRec.reduce((s, d) => s + recs[d.dam_id].judged, 0);
    const where = withRec.length === dams.length
      ? (dams.length === 1 ? "on this dam" : "on these " + dams.length + " dams")
      : "on the " + withRec.length + " of its " + dams.length + " dams with enough history to judge";
    const share = t.heldShareText(held, judged);
    const years = (track && track.years) || t.TRACK_RECORD_YEARS;
    let html = "<p>Over " + esc(span) + (years ? ' <span class="nowrap">(' + esc(years) + ")</span>" : "") + ", years it never trained on, " +
      "our days-left number held <b>" + t.countText(held) + " of " + t.countText(judged) + " times</b> " +
      where + (share === "every time" ? ", every time" : " (" + esc(share) + ")") + ".";
    if (withRec.length > 1) {
      const sh = (d) => recs[d.dam_id].held / recs[d.dam_id].judged;
      const lowest = withRec.reduce((lo, d) => (sh(d) < sh(lo) ? d : lo));
      html += " The lowest: " + esc(lowest.name) + ", held " + t.countText(recs[lowest.dam_id].held) + " of " + t.countText(recs[lowest.dam_id].judged) + " times.";
    }
    html += "</p>";
    const pct = (100 * held / judged).toFixed(1);
    return '<section class="farm-record" aria-labelledby="farm-record-h">' +
      '<h2 class="eyebrow" id="farm-record-h">' + icon("i-tally", "sm") + "Our record on this farm " + tip + "</h2>" + html +
      '<div class="tallybar" role="img" aria-label="' + esc("held " + held + " of " + judged + " times") + '"><i style="width:' + pct + '%"></i></div>' +
      '<p class="small">' + (withRec.length > 1 ? "Forecasts on nearby dams often share one dry spell, so these are not all separate checks. " : "") +
      'Poor records are shown as they are: a dam marked "give extra margin" held less often than 9 times in 10.</p>' +
      "</section>";
  }

  function tableHtml() {
    const dams = state.dams;
    if (!dams.length) return "";
    const t = txt(), f = fmt();
    const recs = recordsOf(data);
    const day = t.dateText(state.textDate);
    const heads = ["How full at the last clear look", "Days above a third, from " + day, "Chance it drops below a third", "Our record on this dam"];
    const rows = dams.slice().sort((a, b) => a.number - b.number).map((d) => {
      const full = d.level_pct === null || d.level_pct === undefined || !d.issued_on ? "not seen lately"
        : f.fullness(d.level_pct) + " on " + short(d.issued_on);
      let days;
      if (d.kind === "forecast") days = d.days_left <= 0 ? "may be below a third now" : t.floorText(d.days_left);
      else if (d.kind === "low") days = d.level_pct === 0 ? "no water seen; below a third" : "already below a third";
      else if (d.kind === "not_refilled") days = "no forecast until it refills";
      else days = "no clear look in " + t.RECENT_LOOK_DAYS + " days";
      const ch = d.kind === "forecast" ? f.chance(d.chance) + " by " + short(d.window_end) : "no forecast";
      const r = recs ? recs[d.dam_id] : undefined;
      const rec = r === undefined && !recs ? "" : t.hasTrackRecord(r) ? "held " + t.countText(r.held) + " of " + t.countText(r.judged) + " times" : "not enough history";
      const cell = (label, value) => '<td data-label="' + esc(label) + '">' + esc(value) + "</td>";
      return '<tr><th scope="row"><a href="#farm/dam-' + d.number + '">' + esc(d.name) + "</a> <small>" + km(d.distance_km) + " km</small></th>" +
        cell(heads[0], full) + cell(heads[1], days) + cell(heads[2], ch) + (recs ? cell(heads[3], rec) : "") + "</tr>";
    }).join("");
    return '<details class="more farm-table-more" id="farm-table"><summary>' + icon("i-chart") + "All dams as a table" + icon("i-plus", "plus") + "</summary>" +
      '<div class="body"><div class="table-scroll farm-stack"><table class="data farm-table"><caption class="vh">Your dams (Dam 1 is the closest to the homestead)</caption>' +
      '<thead><tr><th scope="col">Dam</th><th scope="col">' + esc(heads[0]) + '</th><th scope="col">' + esc(heads[1]) + "</th>" +
      '<th scope="col">' + esc(heads[2]) + "</th>" + (recs ? '<th scope="col">' + esc(heads[3]) + "</th>" : "") + "</tr></thead>" +
      "<tbody>" + rows + "</tbody></table></div>" +
      '<p class="small">"%" means how full a dam is: its wet water surface at the last clear satellite look, against its usual full surface, not its depth. ' +
      "Days are cautious: across all dams in ten test years, a dam stayed above a third at least that long 9 times in 10, a little less often for spring looks. " +
      "A forecast starts from the dam's last clear look, so the days since that look are taken off.</p></div></details>";
  }

  /** This week's text, on the first screen (under the headline card): what the farm gets, one tap away. */
  function textLinkHtml() {
    if (!state.dams.length) return "";
    const f = farmObj();
    const day = txt().dateText(state.textDate);
    const who = f.demo ? f.short_name.split(",")[0] : "your farm";
    return '<a class="linkrow farm-textlink" href="#farm/text">' + icon("i-sms") + "<span>This week's text<small>What " + esc(who) +
      " gets on " + esc(day) + ", word for word, and the longer version</small></span>" +
      '<span class="chev">' + icon("i-chev") + "</span></a>";
  }

  function linksHtml() {
    let html = '<div class="linkrows farm-links">' +
      '<a class="linkrow" href="#farm/setup">' + icon("i-pin") + "<span>Change the homestead or the circle<small>Pick a demo farm or tap the map. Your homestead point stays on this phone.</small></span>" +
      '<span class="chev">' + icon("i-chev") + "</span></a>";
    if (!state.demo || state.demo.dams_in_app) {
      html += '<a class="linkrow" href="#runway">' + icon("i-map") + "<span>Runway: the region map<small>Every dam-sized waterbody we watch in " + esc(regionName()) +
        ", by its chance of dropping below a third</small></span>" + '<span class="chev">' + icon("i-chev") + "</span></a>";
    }
    html += '<a class="linkrow" href="#proof/rewind">' + icon("i-rewind") + "<span>Rewind: the 2018-19 drought<small>What it said at the time, then what happened</small></span>" +
      '<span class="chev">' + icon("i-chev") + "</span></a></div>";
    return html;
  }

  function sketchCardHtml() {
    return '<figure class="sketch-card" aria-labelledby="farm-sketch-cap">' +
      '<div class="sketch-top"><p class="eyebrow">From above</p>' +
      '<div class="seg seg-sm" role="group" aria-label="Show the farm as"><button type="button" data-fview="sketch" aria-pressed="' + (state.view === "sketch") + '">Sketch</button>' +
      '<button type="button" data-fview="map" aria-pressed="' + (state.view === "map") + '">Map</button></div></div>' +
      '<div class="sketch-wrap"' + (state.view === "map" ? " hidden" : "") + '><div class="sketch" id="farm-sketch"></div></div>' +
      '<div class="farm-mapbox"' + (state.view === "map" ? "" : " hidden") + '><div class="farm-map" id="farm-leaflet" role="region" aria-label="Map of the farm\'s dams"></div>' +
      '<div class="map-key" id="farm-leaflet-key"></div></div>' +
      '<figcaption class="sketch-cap" id="farm-sketch-cap">' + (state.view === "map"
        ? "The farm on a map: each dam's dot is coloured by its chance of dropping below a third in the next " + esc((data.meta && data.meta.horizon_days) || 90) + " days. Tap a dot to open that dam."
        : "The farm from above, from the satellite record. Tap a tag to open that dam. Dams are drawn larger than life." +
          '<span id="farm-sketch-untagged"></span>') +
      "</figcaption></figure>";
  }

  function render() {
    if (!root) return;
    const keepScroll = window.scrollY;
    root.innerHTML = '<div class="wrap farm">' + headHtml() +
      '<div class="farm-grid">' +
        '<div class="farm-top">' + headlineHtml() + countsHtml() + textLinkHtml() + "</div>" +
        '<div class="farm-left">' + sketchCardHtml() + "</div>" +
        '<div class="farm-right">' +
          (state.dams.length ? '<div class="list-head" id="rows"><h2>Your dams</h2>' +
            '<div class="seg" role="group" aria-label="Order of the dams"><button type="button" data-order="fewest" aria-pressed="' + (state.order === "fewest") + '">Fewest days</button>' +
            '<button type="button" data-order="run" aria-pressed="' + (state.order === "run") + '">Water run</button></div></div>' : '<div id="rows"></div>') +
          '<div id="farm-rowlist">' + rowsHtml() + "</div>" +
          recordHtml() + tableHtml() + linksHtml() +
        "</div>" +
      "</div></div>";
    firstRows = false;
    // The sketch is drawn just after the next frame: the page's first layout then happens in the browser's own
    // rendering step, not inside this task (a long task on a slow phone). farm.css keeps its room, so nothing moves.
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => setTimeout(drawSketch, 0));
    else drawSketch();
    if (state.view === "map") drawFarmMap();
    window.scrollTo(0, keepScroll);
  }

  function rerenderRows() {
    const box = document.getElementById("farm-rowlist");
    if (box) box.innerHTML = rowsHtml();
    root.querySelectorAll("[data-order]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.order === state.order)));
  }

  function drawSketch() {
    const el = document.getElementById("farm-sketch");
    if (!el || !D.sketch) return;
    if (sketchCtl) sketchCtl.destroy();
    const tags = tagSet();
    const ranked = fewest(state.dams);
    const rankOf = new Map(ranked.map((d, i) => [d.number, i]));
    sketchCtl = D.sketch.farm(el, {
      dams: state.dams,
      home: { lat: state.lat, lon: state.lon },
      radiusKm: state.radiusKm,
      tag: (d) => (tags.has(d.number) ? daysTag(d, rankOf.get(d.number), ranked.length) : null),
      href: (d) => "#farm/dam-" + d.number,
      open: state.openNo,
      homeLabel: ["Homestead", state.demo ? "(demo point)" : "(your point)"],
      onDraw: (info) => {
        const note = document.getElementById("farm-sketch-untagged");
        if (!note) return;
        const missing = state.dams.length - info.tags;
        note.textContent = missing > 0 ? " " + missing + " dam" + (missing === 1 ? " has" : "s have") + " no tag here: the list below has every dam." : "";
      },
    });
  }

  // ---------------------------------------------------------------------------
  // The farm on a real map (Leaflet, loaded on demand): numbered dots coloured by chance
  // ---------------------------------------------------------------------------
  function houseIcon() {
    return L.divIcon({
      className: "home-icon",
      html: '<svg viewBox="0 0 24 24" width="32" height="32" aria-hidden="true"><path d="M3 11.5 12 4l9 7.5V21h-6v-6H9v6H3z" fill="#14222B" stroke="#ffffff" stroke-width="1.6" stroke-linejoin="round"/></svg>',
      iconSize: [32, 32], iconAnchor: [16, 24],
    });
  }
  /**
   * A pane above the dam dots (overlayPane 400, markers 600) and under the dam numbers (tooltips 650): a dam
   * close to the homestead no longer hides the house. It takes no taps, so every dam dot under it still opens.
   */
  function homePane(map) {
    if (!map.getPane("dd-home")) {
      const pane = map.createPane("dd-home");
      pane.style.zIndex = 620;
      pane.style.pointerEvents = "none";
    }
    return "dd-home";
  }
  function circleBounds(lat, lon, radiusKm) {
    const dLat = radiusKm / 111.2, dLon = radiusKm / (111.2 * Math.cos(lat * Math.PI / 180));
    return L.latLngBounds([lat - dLat, lon - dLon], [lat + dLat, lon + dLon]);
  }
  /** Draw a farm's dams, homestead and circle on a Leaflet map. onDam(d) when a dot is tapped. */
  function drawDamsOn(map, layers, st, dams, opts) {
    opts = opts || {};
    if (!layers.group) layers.group = L.layerGroup().addTo(map);
    layers.group.clearLayers();
    const centre = [st.lat, st.lon];
    L.circle(centre, { radius: st.radiusKm * 1000, interactive: false, color: "#1c5cab", weight: 2, dashArray: "6 6", fillOpacity: 0.05 }).addTo(layers.group);
    if (!opts.homeMarker) L.marker(centre, { icon: houseIcon(), keyboard: false, interactive: false, pane: homePane(map) }).addTo(layers.group);
    const order = dams.filter((d) => d.number !== state.openNo).concat(dams.filter((d) => d.number === state.openNo));
    order.forEach((d) => {
      const style = D.map.damStyle({ chance: d.kind === "forecast" ? d.chance : null, low: d.kind === "low", selected: d.number === state.openNo });
      style.radius = Math.max(style.radius, 10);
      style.bubblingMouseEvents = false;
      const m = L.circleMarker([d.lat, d.lon], style);
      m.bindTooltip(String(d.number), { permanent: true, direction: "right", offset: [9, 0], className: "dam-number" });
      if (opts.onDam) m.on("click", () => opts.onDam(d));
      m.addTo(layers.group);
    });
  }
  /** The house drawn on the maps (houseIcon), as a key swatch. */
  const HOUSE_SWATCH = '<svg class="swatch-house" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">' +
    '<path d="M3 11.5 12 4l9 7.5V21h-6v-6H9v6H3z" fill="#14222B" stroke="#ffffff" stroke-width="1.6" stroke-linejoin="round"/></svg>';

  /**
   * The key under a map: the dot colours, then what the house, the dashed circle and the small dots are.
   * opts.setup: the setup map (the house can be moved there); opts.radiusKm: the circle's size;
   * opts.region: the small dots of the region's other dams are drawn.
   */
  function legendHtml(opts) {
    opts = opts || {};
    const bands = S().chanceBands || [];
    const km = opts.radiusKm !== undefined ? opts.radiusKm : state.radiusKm;
    return '<p class="map-key-title">Dot colour: chance it drops below a third in the next ' + esc((data.meta && data.meta.horizon_days) || 90) + " days</p>" +
      '<ul class="map-key-items">' + bands.map((b) => '<li><span class="swatch" style="background:' + b.color + '"></span>' + esc(b.label) + "</li>").join("") +
      '<li><span class="swatch" style="background:' + (S().lowFill || "#ffffff") + ";border:2.5px solid " + (S().lowRing || "#14222B") + '"></span>Already below a third</li>' +
      '<li><span class="swatch" style="background:' + (S().noForecastColor || "#b9b6ae") + '"></span>No forecast this week (see the dam for why)</li>' +
      "<li>" + HOUSE_SWATCH + (opts.setup ? "Homestead: tap the map or drag it" : "Homestead") + "</li>" +
      '<li><span class="swatch swatch-ring-dash" aria-hidden="true"></span><span>How far your dams go: <span data-key-km>' + esc(km) + "</span> km</span></li>" +
      (opts.region ? '<li><span class="swatch swatch-small" aria-hidden="true"></span>Small dots: the other dams we watch nearby</li>' : "") + "</ul>";
  }
  /** Keep the key's circle size in step with the radius (the setup sheet's slider). */
  function legendKm(el, km) {
    const n = el && el.querySelector("[data-key-km]");
    if (n) n.textContent = km;
  }
  /** Is this farm in the region the app's maps hold (so the region's other dams can be drawn round it)? */
  const farmInRegion = (st) => Boolean((!st.demo || st.demo.dams_in_app) && inRegion(st.lat, st.lon));

  function drawFarmMap() {
    const el = document.getElementById("farm-leaflet");
    if (!el) return;
    const key = document.getElementById("farm-leaflet-key");
    if (key) key.innerHTML = legendHtml({ region: farmInRegion(state) });
    D.lazy.leaflet().then((ok) => {
      if (!ok || !document.getElementById("farm-leaflet")) {
        el.innerHTML = '<p class="map-missing">The map needs signal. The sketch shows the same dams.</p>';
        return;
      }
      if (leafletFarm && leafletFarm.el !== el) { try { leafletFarm.map.remove(); } catch (e) { /* gone */ } leafletFarm = null; }
      if (!leafletFarm) {
        const map = D.map.create("farm-leaflet");
        if (!map) return;
        leafletFarm = { map, layers: {}, el };
        // the neighbourhood: every dam of the region, small and faint, behind the farm's own dots
        if (farmInRegion(state)) drawRegionDots(leafletFarm);
      }
      drawDamsOn(leafletFarm.map, leafletFarm.layers, state, state.dams, { onDam: (d) => D.router.go("#farm/dam-" + d.number) });
      leafletFarm.map.invalidateSize();
      leafletFarm.map.fitBounds(circleBounds(state.lat, state.lon, state.radiusKm), { padding: [16, 16] });
    });
  }

  // ===========================================================================
  // Opening a dam (the sheet is WP-D's js/dam-sheet.js)
  // ===========================================================================
  function damContext(n, deep, route) {
    const dams = state.dams.slice().sort((a, b) => a.number - b.number);
    const index = dams.findIndex((d) => d.number === Number(n));
    if (index < 0) return null;
    const farm = farmObj();
    try { farm.sms = smsFor(state, state.dams); farm.long = longFor(state, state.dams); } catch (e) { /* the sheet does without */ }
    const href = (d) => "#farm/dam-" + d.number;
    return {
      dam: dams[index], dams, index, farm, textDate: state.textDate, deep: deep || null,
      data, href, hrefFor: href, inApp: farm.dams_in_app, route: route || (D.router ? D.router.current() : null),
    };
  }

  function markOpen(n) {
    state.openNo = n === null || n === undefined ? null : Number(n);
    if (sketchCtl) sketchCtl.setOpen(state.openNo);
    if (root) root.querySelectorAll(".row").forEach((r) => r.classList.toggle("is-hot", Number(r.dataset.dam) === state.openNo));
    if (state.view === "map" && leafletFarm) drawDamsOn(leafletFarm.map, leafletFarm.layers, state, state.dams, { onDam: (d) => D.router.go("#farm/dam-" + d.number) });
  }

  function openDam(n, deep, route) {
    const ctx = damContext(n, deep, route);
    if (!ctx) { D.router.go("#farm", { replace: true }); return; }
    markOpen(ctx.dam.number);
    if (D.damSheet && typeof D.damSheet.open === "function") {
      D.damSheet.open(ctx);
    } else {
      fallbackDamSheet(ctx);
    }
  }

  /** Only if js/dam-sheet.js is missing: a plain sheet with the dam's main numbers. */
  function fallbackDamSheet(ctx) {
    const d = ctx.dam, dams = ctx.dams, i = ctx.index, f = fmt(), t = txt();
    const prev = dams[(i - 1 + dams.length) % dams.length], next = dams[(i + 1) % dams.length];
    let hero;
    if (d.kind === "forecast") {
      hero = d.days_left <= 0 ? "May be below a third now" : (d.days_left >= capDays() ? "6 months+" : "at least " + d.days_left + " days") + " before it drops below a third";
    } else if (d.kind === "low") hero = "Already below a third";
    else if (d.kind === "not_refilled") hero = refillWords();
    else hero = "No clear satellite look lately, so no forecast right now";
    const r = d.record;
    D.sheet.open({
      title: d.name + " of " + dams.length,
      head: dams.length > 1 ? { prev: { href: "#farm/dam-" + prev.number, label: "Previous dam: " + prev.name }, next: { href: "#farm/dam-" + next.number, label: "Next dam: " + next.name } } : undefined,
      body: '<div class="sheet-prose"><h2>' + esc(d.name) + "</h2><p>" + km(d.distance_km) + " km from the homestead" + (d.area_ha ? " · " + esc(d.area_ha.toFixed(1)) + " ha when full" : "") + "</p>" +
        "<p><b>" + esc(hero) + "</b></p><p>" + esc(f.fullness(d.level_pct)) + (d.issued_on ? " at the " + esc(short(d.issued_on)) + " satellite look" : "") + ".</p>" +
        (d.kind === "forecast" ? "<p>Chance it drops below a third by " + esc(short(d.window_end)) + ": " + esc(f.chance(d.chance)) + ".</p>" : "") +
        (r && t.hasTrackRecord(r) ? "<p>Our record on this dam: held " + t.countText(r.held) + " of " + t.countText(r.judged) + " times.</p>" : "") + "</div>",
    });
  }

  // ===========================================================================
  // The text sheet (#farm/text): this week's text, and the longer version
  // ===========================================================================
  function openText() {
    const f = farmObj();
    const sms = smsFor(state, state.dams);
    const long = longFor(state, state.dams);
    const day = txt().dateText(state.textDate);
    const fits = txt().fitsOneSms(sms);
    const longHtml = long.split("\n").map((line) => "<p>" + esc(line).replace("[map link]", '<a href="#farm">open the farm map</a>') + "</p>").join("");
    D.sheet.open({
      title: "This week's text",
      body: '<div class="text-sheet">' +
        '<p class="eyebrow">' + esc(f.short_name) + "</p>" +
        "<h2>What " + (f.demo ? esc(f.short_name.split(",")[0]) : "your farm") + " gets on " + esc(day) + " " + esc(state.textDate.slice(0, 4)) + "</h2>" +
        '<p class="lead">One text message, once a week. Tap a dam\'s line to open that dam.</p>' +
        // on desktop the card sits in the drawn phone, as on the Welcome (shell.css .phone-frame); phones show the card
        '<div class="text-phone"><div class="phone-frame"><div class="phone-screen">' +
        '<div class="phone-status" aria-hidden="true"><span>' + esc(day.split(" ")[0]) + '</span><span class="island"></span><span>4G</span></div>' +
        '<div class="welcome-sms">' +
        smsCard(sms, { date: day, note: fits ? "Fits in one text message." : "", noteIcon: "i-check", label: "This week's text for " + f.short_name }) +
        '</div><div class="phone-input" aria-hidden="true">Text message</div></div></div></div>' +
        '<section class="long-text" aria-labelledby="long-h"><h3 id="long-h">The longer version, for the app or an email</h3>' +
        '<div class="long-body">' + longHtml + "</div></section>" +
        '<p class="small">Days are counted from the day the text is sent. ' + (f.demo ? esc(demoNote(state.demo)) : "Your homestead point stays on this phone.") + "</p>" +
        "</div>",
    });
  }

  // ===========================================================================
  // The setup sheet (#farm/setup): demo farm, homestead on the map, circle size, Save (5.24)
  // ===========================================================================
  let draft = null;

  function draftFromState() {
    return { demo: state.demo, lat: state.lat, lon: state.lon, radiusKm: state.radiusKm };
  }

  function pickerHtml(d) {
    const groups = new Map();
    visibleFarms().forEach((f) => {
      const label = f.region_name + (f.dams_in_app ? " (on the region map)" : "");
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(f);
    });
    let html = "";
    groups.forEach((list, label) => {
      html += '<optgroup label="' + esc(label) + '">' + list.map((f) =>
        '<option value="' + esc(f.farm_id) + '"' + (d.demo && d.demo.farm_id === f.farm_id ? " selected" : "") + ">" +
        esc(f.name) + ", " + f.dams.length + " dam" + (f.dams.length === 1 ? "" : "s") + "</option>").join("") + "</optgroup>";
    });
    html += '<option value="custom"' + (d.demo ? " disabled" : " selected") + ">" + (d.demo ? "Your point (tap the map)" : "Your point (set on the map)") + "</option>";
    return html;
  }

  function maxRadius(d) {
    return d.demo && !d.demo.dams_in_app ? d.demo.radius_km : MAX_RADIUS_KM;
  }

  /** The line under the setup map: what its dots are, for the farm being set up. */
  function mapHint(d) {
    const how = "Tap the map or drag the house; with a keyboard, move the map with the arrow keys and use the button above. ";
    if (d.demo && !d.demo.dams_in_app) {
      return how + "The numbered dots are this farm's dams; the app's region map covers " + regionName() + " only.";
    }
    return how + "The small dots are the dams we watch in " + regionName() + ", coloured by chance.";
  }

  /**
   * The setup sheet. Phones and the narrow desktop panel: one column. A wide screen (setupWide()): the sheet
   * widens, the map takes the left of it at full size and the picker, the circle and the text it would get sit
   * beside it, so a tap on the map changes the count and the text in view (farm.css). The Save button is in
   * the sheet's foot (sheet.js opts.foot), so it never covers the map or the button under it.
   */
  function setupHtml() {
    const d = draft;
    const mx = maxRadius(d);
    return '<div class="setup">' +
      '<div class="setup-head"><h2 class="setup-title">Your farm</h2>' +
      '<p class="lead">A farm is a homestead point and a circle. Its dams are every dam the satellites can see within the circle: we have no property boundaries.</p></div>' +
      '<div class="setup-field setup-pickfield"><label for="setup-pick" class="setup-label">Demo farm</label>' +
      '<select id="setup-pick" class="select">' + pickerHtml(d) + "</select>" +
      '<p class="small">Each demo homestead point is made up, in the middle of a real cluster of dams.</p></div>' +
      '<div class="setup-field setup-mapfield"><p class="setup-label" id="setup-map-label">Or tap your homestead on the map</p>' +
      '<div class="setup-map" id="setup-map" role="region" aria-labelledby="setup-map-label"></div>' +
      '<button type="button" class="btn btn-quiet setup-centre" data-centre>' + icon("i-pin", "sm") + "Put the homestead at the centre of the map</button>" +
      '<p class="small" id="setup-map-hint">' + esc(mapHint(d)) + "</p>" +
      '<div class="map-key" id="setup-map-key"></div></div>' +
      '<div class="setup-field setup-radiusfield"><label for="setup-radius" class="setup-label">How far your dams go: <output id="setup-radius-out" for="setup-radius">' + esc(d.radiusKm) + " km</output></label>" +
      '<div class="radius-row"><button type="button" class="iconbtn" data-radius="-1" aria-label="Smaller circle">' + icon("i-minus") + "</button>" +
      '<input id="setup-radius" type="range" min="' + MIN_RADIUS_KM + '" max="' + mx + '" step="0.5" value="' + d.radiusKm + '" aria-valuetext="' + esc(d.radiusKm) + ' km">' +
      '<button type="button" class="iconbtn" data-radius="1" aria-label="Bigger circle">' + icon("i-plus") + "</button></div></div>" +
      '<div class="setup-preview" id="setup-preview" aria-live="polite"></div>' +
      '<p class="privacy">' + icon("i-lock", "sm") + "Your homestead point stays on this phone and is never sent to us. No name, no sign-up.</p>" +
      "</div>";
  }
  const SETUP_FOOT = '<div class="setup-actions"><button type="button" class="btn btn-primary btn-block" data-save>Save</button></div>';
  /** A screen wide enough for the map beside the controls: every desktop width (the sheet widens to 1,160 px;
   *  at 960-1023 px the controls' column narrows to 340 px, farm.css), so the desktop never gets the side panel
   *  with the saved farm's sketch beside a map showing the new point. */
  const setupWide = () => Boolean(window.matchMedia && window.matchMedia("(min-width: 960px)").matches);

  function previewHtml(d) {
    const dams = damsFor(d);
    if (!dams) return '<p class="small">Loading the dams around this point…</p>';
    const n = dams.length;
    let sms;
    try { sms = d.demo && d.radiusKm === d.demo.radius_km ? d.demo.sms : txt().smsForDams(dams, state.textDate, d.radiusKm); }
    catch (e) { return '<p class="load-error">The text could not be made: ' + esc(e.message) + "</p>"; }
    return '<p class="setup-count"><b>' + n + " dam" + (n === 1 ? "" : "s") + "</b> the satellites can see within " + esc(d.radiusKm) + " km. The text would read:</p>" +
      smsCard(sms, { date: txt().dateText(state.textDate), links: false, label: "The text for this farm" });
  }

  function updatePreview() {
    const box = document.getElementById("setup-preview");
    if (box) box.innerHTML = previewHtml(draft);
    const out = document.getElementById("setup-radius-out");
    if (out) out.textContent = draft.radiusKm + " km";
    const range = document.getElementById("setup-radius");
    if (range) { range.max = maxRadius(draft); range.value = draft.radiusKm; range.setAttribute("aria-valuetext", draft.radiusKm + " km"); }
    const hint = document.getElementById("setup-map-hint");
    if (hint) hint.textContent = mapHint(draft);
    if (!damsFor(draft)) {
      want("core").then((x) => { if (x) data = x; updatePreview(); drawSetupMap(false); });
    }
  }

  function drawSetupMap(fit) {
    const el = document.getElementById("setup-map");
    if (!el) return;
    const key = document.getElementById("setup-map-key");
    if (key && !key.innerHTML) key.innerHTML = legendHtml({ setup: true, radiusKm: draft.radiusKm, region: !(draft.demo && !draft.demo.dams_in_app) });
    else legendKm(key, draft.radiusKm);
    D.lazy.leaflet().then((ok) => {
      if (!document.getElementById("setup-map")) return;
      if (!ok) { el.innerHTML = '<p class="map-missing">The map needs signal. You can still pick a demo farm and the circle size.</p>'; return; }
      if (setupMap && setupMap.el !== el) { try { setupMap.map.remove(); } catch (e) { /* gone */ } setupMap = null; }
      if (!setupMap) {
        const map = D.map.create("setup-map");
        if (!map) return;
        setupMap = { map, layers: {}, el };
        map.on("click", (ev) => setHome(ev.latlng.lat, ev.latlng.lng));
        drawRegionDots(setupMap);
        fit = true;
      }
      const dams = damsFor(draft) || [];
      drawDamsOn(setupMap.map, setupMap.layers, draft, dams, { homeMarker: true });
      const centre = [draft.lat, draft.lon];
      if (!setupMap.home) {
        setupMap.home = L.marker(centre, { icon: houseIcon(), draggable: true, keyboard: false, title: "Homestead (drag to move)" }).addTo(setupMap.map);
        setupMap.home.on("dragend", () => { const at = setupMap.home.getLatLng(); setHome(at.lat, at.lng); });
      }
      setupMap.home.setLatLng(centre);
      setupMap.map.invalidateSize();
      const b = circleBounds(draft.lat, draft.lon, draft.radiusKm);
      if (fit || !setupMap.map.getBounds().contains(b)) setupMap.map.fitBounds(b, { padding: [16, 16] });
    });
  }

  /**
   * Every dam of the region, small and faint, on a map ({ map } of the setup sheet or the farm's Map view): the
   * neighbourhood, dams just outside the circle included. Drawn in their own pane under the farm's dots (the
   * overlay pane is 400), so they never sit on top of a farm dot, whichever finishes loading first.
   */
  function drawRegionDots(target) {
    if (!target) return;
    const go = () => {
      // the map is still on screen (not removed while "core" was loading)
      if ((target !== setupMap && target !== leafletFarm) || !data || !data.liveIssue || !data.damsById) return;
      if (!target.map.getPane("dd-region")) {
        const pane = target.map.createPane("dd-region");
        pane.style.zIndex = 390;
        pane.style.pointerEvents = "none";
      }
      if (target.region) target.region.remove();
      target.region = L.layerGroup().addTo(target.map);
      data.liveIssue.rows.forEach((row) => {
        const dam = data.damsById.get(row.dam_id);
        if (!dam) return;
        const style = D.map.damStyle({ chance: row.status === "forecast" ? row.chance : null, low: row.status === "already_low" });
        style.radius = 4; style.interactive = false; style.weight = 0.8; style.pane = "dd-region";
        style.opacity = 0.75; style.fillOpacity = Math.min(style.fillOpacity, 0.8);
        L.circleMarker([dam.lat, dam.lon], style).addTo(target.region);
      });
    };
    if (hasCore(data)) go();
    else want("core").then((x) => { if (x) data = x; go(); if (target === setupMap) updatePreview(); });
  }

  function setHome(lat, lon) {
    draft.demo = null;
    draft.lat = Math.round(lat * 1e5) / 1e5;
    draft.lon = Math.round(lon * 1e5) / 1e5;
    if (draft.radiusKm > MAX_RADIUS_KM) draft.radiusKm = MAX_RADIUS_KM;
    const pick = document.getElementById("setup-pick");
    if (pick) pick.innerHTML = pickerHtml(draft);
    updatePreview();
    drawSetupMap(false);
  }

  function pickDemo(id) {
    const f = visibleFarms().find((x) => x.farm_id === id);
    if (!f) return;
    draft.demo = f; draft.lat = f.lat; draft.lon = f.lon; draft.radiusKm = f.radius_km;
    updatePreview();
    drawSetupMap(true);
  }

  function setRadius(km) {
    const mx = maxRadius(draft);
    draft.radiusKm = Math.max(MIN_RADIUS_KM, Math.min(mx, Math.round(km * 2) / 2));
    updatePreview();
    drawSetupMap(false);
  }

  function openSetup() {
    draft = draft && D.sheet.isOpen() ? draft : draftFromState();
    const wide = setupWide();
    const body = D.sheet.open({
      title: "Change the farm",
      body: setupHtml(),
      foot: SETUP_FOOT,
      // wide: the map fills the sheet's left side, so the saved farm's sketch behind is dimmed, not shown beside it
      wide: wide ? "wider" : undefined,
      split: wide ? false : undefined,
      onClose() {
        if (setupMap) { try { setupMap.map.remove(); } catch (e) { /* gone */ } setupMap = null; }
        draft = null;
      },
    });
    wireSheet(body);
    updatePreview();
    setTimeout(() => drawSetupMap(true), 320);       // after the sheet has slid in, so the map can measure
  }

  /** The sheet body is shared by every sheet: listen once, and act only inside the setup content. */
  let sheetWired = false;
  function wireSheet(body) {
    if (sheetWired) return;
    sheetWired = true;
    const inSetup = (e) => e.target instanceof Element && e.target.closest(".setup");
    // Save sits in the sheet's foot, outside the body
    D.sheet.foot().addEventListener("click", (e) => {
      if (draft && e.target instanceof Element && e.target.closest("[data-save]")) save();
    });
    body.addEventListener("change", (e) => {
      if (!inSetup(e) || !draft) return;
      if (e.target.id === "setup-pick" && e.target.value !== "custom") pickDemo(e.target.value);
      if (e.target.id === "setup-radius") setRadius(Number(e.target.value));
    });
    body.addEventListener("input", (e) => {
      if (inSetup(e) && draft && e.target.id === "setup-radius") setRadius(Number(e.target.value));
    });
    body.addEventListener("click", (e) => {
      if (!inSetup(e)) return;
      const b = e.target.closest("[data-radius]");
      if (b && draft) { setRadius(draft.radiusKm + 0.5 * Number(b.dataset.radius)); return; }
      if (e.target.closest("[data-centre]") && draft) {
        // keyboard users: the arrow keys and +/- move a focused map; this sets the homestead where it is centred
        if (setupMap) { const c = setupMap.map.getCenter(); setHome(c.lat, c.lng); }
        return;
      }
      if (e.target.closest("[data-save]")) { save(); return; }
      if (e.target.closest("[data-dismiss-install]")) {
        try { localStorage.setItem("damdays.installOffered", "1"); } catch (err) { /* private mode */ }
        const card = e.target.closest(".install-card");
        if (card) card.remove();
      }
    });
  }

  function installOfferHtml() {
    let offered = false;
    try { offered = Boolean(localStorage.getItem("damdays.installOffered")); localStorage.setItem("damdays.installOffered", "1"); } catch (e) { offered = true; }
    const standalone = window.matchMedia && window.matchMedia("(display-mode: standalone)").matches;
    if (offered || standalone) return "";
    return '<div class="install-card">' + icon("i-phone") + '<div><p><b>Put DamDays on your home screen</b></p>' +
      '<p class="small">It opens like an app and keeps this week\'s forecasts for when the signal drops.</p>' +
      '<div class="install-actions"><a class="btn btn-quiet" href="#more/install">How</a><button type="button" class="linkbtn" data-dismiss-install>No thanks</button></div></div></div>';
  }

  function save() {
    if (!draft) return;
    const dams = damsFor(draft);
    if (!dams) return;
    state.demo = draft.demo; state.lat = draft.lat; state.lon = draft.lon; state.radiusKm = draft.radiusKm;
    state.dams = dams; state.showAll = false; state.openNo = null;
    storeFarm();
    render();
    const n = dams.length;
    if (setupMap) { try { setupMap.map.remove(); } catch (e) { /* gone */ } setupMap = null; }
    draft = null;
    const day = txt().dateText(state.textDate);
    // The same sheet, swapped to the confirmation at the usual width (the wide map is done with). The text link
    // replaces this address, so Back from the text goes to My farm, not into the setup again.
    const body = D.sheet.open({
      title: "Change the farm",
      body: '<div class="setup saved"><p class="eyebrow">Saved</p><h2 class="setup-title">' + esc(farmObj().short_name) + "</h2>" +
        "<p>My farm now shows the " + n + " dam" + (n === 1 ? "" : "s") + " the satellites can see within " + esc(state.radiusKm) + " km of " +
        (state.demo ? "the demo homestead" : "your homestead") + ".</p>" + installOfferHtml() +
        '<div class="setup-done"><button type="button" class="btn btn-primary btn-block" data-close>See the dams</button>' +
        '<a class="btn btn-secondary btn-block" href="#farm/text" data-replace>' + icon("i-sms") + "See this week's text</a>" +
        '<p class="small">What ' + esc(state.demo ? farmObj().short_name.split(",")[0] : "your farm") + " gets on " + esc(day) + ", and the longer version.</p></div></div>",
    });
    const h = body.querySelector("h2");
    if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
  }

  // The address is left as it is: changing ?farm= with replaceState would make Back cross a search
  // change, which fires no hashchange (the router would not see it). ?farm= still picks the farm on load.

  // ===========================================================================
  // The saved farm: kept only in this browser (localStorage), never sent anywhere
  // ===========================================================================
  const SAVE_KEY = "damdays.farm";
  const datasetName = () => new URLSearchParams(location.search).get("data") || "real";
  function storeFarm() {
    const v = state.demo ? { farm_id: state.demo.farm_id, radiusKm: state.radiusKm }
      : { lat: state.lat, lon: state.lon, radiusKm: state.radiusKm };
    v.data = datasetName();
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(v)); } catch (e) { /* private mode: kept for this visit only */ }
  }
  function storedFarm() {
    try {
      const v = JSON.parse(localStorage.getItem(SAVE_KEY) || "null");
      return v && typeof v === "object" && (v.data || "real") === datasetName() ? v : null;
    } catch (e) { return null; }
  }
  const clampKm = (km, mx) => Math.max(MIN_RADIUS_KM, Math.min(mx, Math.round(Number(km) * 2) / 2));

  // ===========================================================================
  // Choosing the farm on start, and from the Welcome's links (data-farm)
  // ===========================================================================
  function startFarm() {
    const farms = visibleFarms();
    const wanted = new URLSearchParams(location.search).get("farm");
    const asked = farms.find((x) => x.farm_id === wanted) || null;
    const saved = asked ? null : storedFarm();
    if (saved && saved.farm_id) {
      const f = farms.find((x) => x.farm_id === saved.farm_id);     // a farm set aside since is not restored
      if (f) {
        state.demo = f; state.lat = f.lat; state.lon = f.lon;
        state.radiusKm = isFinite(saved.radiusKm) ? clampKm(saved.radiusKm, maxRadius({ demo: f })) : f.radius_km;
        return;
      }
    } else if (saved && isFinite(saved.lat) && isFinite(saved.lon) && Math.abs(saved.lat) <= 90 && Math.abs(saved.lon) <= 180) {
      state.demo = null; state.lat = Number(saved.lat); state.lon = Number(saved.lon);
      state.radiusKm = isFinite(saved.radiusKm) ? clampKm(saved.radiusKm, MAX_RADIUS_KM) : txt().DEFAULT_RADIUS_KM;
      return;
    }
    const f = asked || farms.find((x) => x.farm_id === S().defaultFarmId) || farms[0] || null;
    if (f) {
      state.demo = f; state.lat = f.lat; state.lon = f.lon; state.radiusKm = f.radius_km;
      return;
    }
    // No demo farms in this data (e.g. ?data=mock): a test homestead at the dam with the most dams around it.
    state.demo = null;
    state.radiusKm = txt().DEFAULT_RADIUS_KM;
    const all = (data.dams || []).slice(0, 400);
    let best = all[0] || null, most = -1;
    all.forEach((a) => {
      const n = all.reduce((c, b) => c + (txt().distanceKm(a.lat, a.lon, b.lat, b.lon) <= state.radiusKm ? 1 : 0), 0);
      if (n > most) { most = n; best = a; }
    });
    state.lat = best ? best.lat : 0; state.lon = best ? best.lon : 0;
  }

  function refreshDams() {
    const dams = damsFor(state);
    if (dams) { state.dams = dams; state.pending = false; return Promise.resolve(); }
    state.pending = true;
    return want("core").then((x) => { if (x) data = x; state.dams = damsFor(state) || []; state.pending = false; });
  }

  function useDemo(id) {
    const f = visibleFarms().find((x) => x.farm_id === id);
    if (!f || (state.demo && state.demo.farm_id === id && asPublished(state))) return;
    state.demo = f; state.lat = f.lat; state.lon = f.lon; state.radiusKm = f.radius_km;
    state.showAll = false;
    if (data) { state.dams = damsFor(state) || []; if (root && root.childElementCount) render(); }
  }

  // Links from the Welcome's demo text say which demo farm they mean (data-farm): show that farm.
  document.addEventListener("click", (e) => {
    const t = e.target instanceof Element ? e.target : null;
    const a = t && t.closest("a[href^='#farm']");
    const host = a && a.closest("[data-farm]");
    if (host && data) useDemo(host.getAttribute("data-farm"));
  }, true);

  // ===========================================================================
  // Page events: order, show all, sketch or map, hover between rows and tags
  // ===========================================================================
  function wire() {
    root.addEventListener("click", (e) => {
      const ord = e.target.closest("[data-order]");
      if (ord) { state.order = ord.dataset.order; rerenderRows(); return; }
      if (e.target.closest("[data-show-all]")) {
        state.showAll = true; rerenderRows();
        const first = root.querySelector("#farm-rowlist .row");
        if (first) first.focus({ preventScroll: true });
        return;
      }
      const fv = e.target.closest("[data-fview]");
      if (fv && fv.dataset.fview !== state.view) {
        state.view = fv.dataset.fview;
        const card = root.querySelector(".sketch-card");
        if (card) {
          card.outerHTML = sketchCardHtml();
          if (state.view === "map") drawFarmMap(); else { if (leafletFarm) { try { leafletFarm.map.remove(); } catch (err) { /* gone */ } leafletFarm = null; } drawSketch(); }
          const btn = root.querySelector('[data-fview="' + state.view + '"]');
          if (btn) btn.focus({ preventScroll: true });
        }
      }
    });
    const hover = (e, on) => {
      const row = e.target.closest && e.target.closest(".row");
      if (row && sketchCtl) sketchCtl.hot(row.dataset.dam, on);
      const tag = e.target.closest && e.target.closest(".tag2");
      if (tag) {
        const r = root.querySelector('.row[data-dam="' + tag.dataset.dam + '"]');
        if (r) r.classList.toggle("is-near", on);
      }
    };
    root.addEventListener("mouseover", (e) => hover(e, true));
    root.addEventListener("mouseout", (e) => hover(e, false));
    root.addEventListener("focusin", (e) => hover(e, true));
    root.addEventListener("focusout", (e) => hover(e, false));
  }

  // ===========================================================================
  // The router
  // ===========================================================================
  const view = {
    render(r) {
      root = r;
      const welcome = D.welcome || !D.lazy ? null : D.lazy("js/views/welcome.js").catch(() => null);
      return Promise.all([want("first"), welcome]).then(([x]) => {
        data = x;
        state.textDate = textDateOf(data);
        startFarm();
        return refreshDams();
      }).then(() => {
        root.innerHTML = "";
        wire();
        render();
        // Records for dams outside the first part arrive with the farms or core part.
        if (state.dams.length && state.dams.some((d) => d.record === undefined)) {
          const more = typeof D.data.need === "function" ? D.data.need("core") : D.data.load();
          more.then((x) => { data = x; state.dams = damsFor(state) || state.dams; render(); }).catch(() => {});
        }
      });
    },
    enter(route) {
      const sub = route.sub || "";
      const m = /^dam-(\d+)$/.exec(sub);
      if (m) { openDam(Number(m[1]), route.deep, route); return; }
      markOpen(null);
      if (sub === "setup") { openSetup(); return; }
      if (sub === "text") { openText(); return; }
      if (sub) D.router.go("#farm", { replace: true });
    },
    leave() {
      markOpen(null);
    },
  };
  if (D.router) {
    D.router.register("farm", view);
    D.router.onChange((r) => { if (r.view === "farm" && !r.sub) markOpen(null); });
  }

  return {
    current: () => ({ farm: farmObj(), dams: state.dams.slice(), textDate: state.textDate, data }),
    damContext,
    useDemo,
    view,
  };
})();
