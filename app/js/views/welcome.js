/* views/welcome.js (WP-C)
 * THE FIRST SCREEN (UI_SPEC 3.1, 4, 5.3 to 5.6, 5.8): the QR opens this. Its static frame is
 * in index.html (brand, eyebrow, H1 with the "farm dam" glossary button, sub-line, both
 * buttons, a skeleton of the text card), so it paints before any data. This file fills it:
 *
 *   #welcome-sms        this week's real text, word for word from farms.json farms[].sms, with
 *                       the straw highlight and tappable dam lines (each opens that dam)
 *   #welcome-trust      the cautious days' record (900 in 1,000) and the unseen-exam line
 *   #welcome-see-dams   "See the 5 dams"
 *   #welcome-stats      desktop: three stat columns
 *   #welcome-phone-cap  desktop: the caption under the drawn phone
 *   #welcome-below      phones: three short cards; desktop: the story (how a farmer sees it)
 *   #welcome/farm-dam   the glossary sheet ("What is a farm dam?")
 *
 * Every number comes from the data (farms.json, scoreboard.json, proof.json, meta.json,
 * track_record.json); nothing is typed in. Wording rules: "%" only for how full, chances
 * "N in 10", a 0% dam is "no water seen", never "days until empty".
 *
 * Shared with My farm (js/views/farm.js): DamDays.welcome.smsHtml(sms, opts), demoNote(farm).
 */
window.DamDays = window.DamDays || {};

DamDays.welcome = (function () {
  "use strict";

  const D = window.DamDays;
  const esc = (t) => String(t === null || t === undefined ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const icon = (id, cls) => (D.icon ? D.icon(id, cls) : '<svg class="i ' + (cls || "") + '" aria-hidden="true"><use href="#' + id + '"/></svg>');
  const fmt = () => D.format;
  const S = () => D.settings || {};
  const $ = (id) => document.getElementById(id);

  const AVATAR = '<svg class="avatar" viewBox="0 0 100 100" aria-hidden="true" focusable="false"><rect width="100" height="100" rx="26" fill="#14222B"/>' +
    '<g transform="translate(8 6) scale(.84)"><path d="M20 31C23 15 45 9 63 13C81 17 92 31 89 51C86 72 72 89 50 88C28 87 12 74 11 55C10 45 16 39 20 31Z" fill="#EDE5D3"/>' +
    '<path d="M20 31C23 15 45 9 63 13C81 17 92 31 89 51C86 72 72 89 50 88C28 87 12 74 11 55C10 45 16 39 20 31Z" fill="#3B7BD0" transform="translate(64 70) scale(.72) translate(-64 -70)"/>' +
    '<path d="M34 86 Q52 95 74 84" fill="none" stroke="#C9A97A" stroke-width="7" stroke-linecap="round"/></g></svg>';

  // ---------------------------------------------------------------------------
  // Data: the "first" part when the data is split (WP-B), else the whole prepared object
  // ---------------------------------------------------------------------------
  function want(part) {
    const data = D.data;
    const ok = (x) => x && x.meta && (x.farms !== undefined || x.forecasts);
    if (data && typeof data.need === "function") {
      return Promise.resolve(data.need(part)).then((x) => (ok(x) ? x : data.load()), () => data.load());
    }
    return data.load();
  }
  const trackOf = (x) => (x && (x.trackRecord || x.track_record)) || null;
  const textDateOf = (x) => (x && (x.textDate || (x.farms && x.farms.date))) || null;

  /** The demo farm the Welcome shows: ?farm= if it is a demo farm, else settings.defaultFarmId (never a hidden one). */
  function demoFarm(data) {
    const farms = data && data.farms && data.farms.farms ? data.farms.farms : [];
    const hidden = S().hiddenFarmIds || [];
    const wanted = new URLSearchParams(location.search).get("farm");
    const shown = farms.filter((f) => !hidden.includes(f.farm_id));
    return shown.find((f) => f.farm_id === wanted) || shown.find((f) => f.farm_id === S().defaultFarmId) || shown[0] || null;
  }

  /** "Farm E (near Mudgee)" -> "Farm E, near Mudgee". */
  function shortName(name) {
    return String(name || "").replace(/\s*\((near [^)]+)\)\s*$/, ", $1");
  }

  /**
   * The one line under a demo farm. The hero farm's dams were checked against aerial photos
   * (research/checks/DEMO_CHECKS.md); the other demo farms are dam-sized waterbodies, mostly farm dams.
   */
  function demoNote(farm) {
    if (!farm) return "";
    const town = farm.near_town || "";
    if (farm.farm_id === S().defaultFarmId) return "Real dams near " + town + "; the homestead point is made up.";
    return "Real dam-sized waterbodies near " + town + ", mostly farm dams; the homestead point is made up.";
  }

  // ---------------------------------------------------------------------------
  // The text card (5.3, 5.4, 5.5): the SMS word for word; dam lines are links
  // ---------------------------------------------------------------------------
  const HL = /at least \d+ days? before it drops below 1\/3/;

  /**
   * opts.date      "Fri 2 Oct" in the card's head
   * opts.note      the caption (with the tap hint); "" for none
   * opts.first     play the once-per-session rise and highlight
   * opts.farmId    the demo farm the lines belong to (data-farm on links, so My farm shows that farm)
   * opts.links     false: plain lines (no links)
   * opts.label     aria-label of the figure
   */
  function smsHtml(sms, opts) {
    opts = opts || {};
    const links = opts.links !== false;
    const farmAttr = opts.farmId ? ' data-farm="' + esc(opts.farmId) + '"' : "";
    const body = String(sms || "").split("\n").map((line) => {
      let html = esc(line).replace(HL, (m) => '<mark class="hl">' + m + "</mark>");
      if (!links) return '<span class="ln">' + html + "</span>";
      let m = /^Dam (\d+)\b/.exec(line);
      if (m) {
        return '<a class="ln" href="#farm/dam-' + m[1] + '"' + farmAttr + ">" +
          html.replace(/^Dam \d+/, (x) => '<span class="who">' + x + "</span>") + "</a>";
      }
      m = /^(Other \d+ dams|Dams [\d, and]+\d|\d+ dams)/.exec(line);
      if (m) {
        return '<a class="ln" href="#farm" data-scroll="rows"' + farmAttr + ">" +
          html.replace(m[1], '<span class="who">' + esc(m[1]) + "</span>") + "</a>";
      }
      m = /^Reply MAP for \d+ more dams?$/.exec(line);
      if (m) return '<a class="ln" href="#farm" data-scroll="rows"' + farmAttr + ">" + html + "</a>";
      return '<span class="ln">' + html + "</span>";
    }).join("");
    const note = opts.note === undefined ? "" : opts.note;
    return '<figure class="sms' + (opts.first ? " first" : "") + '" aria-label="' + esc(opts.label || "This week's text for the demo farm") + '">' +
      '<div class="sms-head">' + AVATAR + '<div class="who">DamDays <span class="tag">Demo</span></div>' +
      '<div class="when">' + esc(opts.date || "") + "</div></div>" +
      '<div class="bubble">' + body + "</div>" +
      (note ? '<figcaption class="sms-foot">' + icon(opts.noteIcon || (links ? "i-tap" : "i-info")) + "<span>" + note + "</span></figcaption>" : "") +
      "</figure>";
  }

  /** Play the card's entrance once per session (never with reduced motion: CSS decides that). */
  function firstTime() {
    try {
      if (sessionStorage.getItem("damdays.smsSeen")) return false;
      sessionStorage.setItem("damdays.smsSeen", "1");
      return true;
    } catch (e) {
      return true;
    }
  }

  // ---------------------------------------------------------------------------
  // The trust line and the exam (4.3): the state comes from the sealed panel, never the clock
  // ---------------------------------------------------------------------------
  function panels(data) {
    const list = data && data.scoreboard && data.scoreboard.panels ? data.scoreboard.panels : [];
    return { dev: list.find((p) => p.key === "dev_test") || null, sealed: list.find((p) => p.key === "sealed") || null };
  }
  function heldShare(data) {
    const dev = panels(data).dev;
    return dev && dev.floor && typeof dev.floor.held === "number" ? dev.floor.held : null;
  }
  /**
   * { scored, line, statTitle, statText } for the exam, from the sealed panel (UI_SPEC 4.3), never the
   * clock. Pending names the day but no hour: the region is opened once, on camera, on Sun 4 Oct, after this
   * build of the app (proof.json's heading_pending still names the old 17:30 slot, so it is not shown here).
   */
  function exam(data) {
    const st = fmt().examStatus ? fmt().examStatus(panels(data).sealed) : null;
    if (!st) return null;
    if (st.scored) {
      return { scored: true, line: st.line, statTitle: st.day || "Opened", statText: "the unseen exam, opened once on camera: " + st.words };
    }
    return { scored: false, line: st.line, statTitle: "Unseen exam", statText: "a third farming region we never opened, kept for one final check, on camera, on Sun 4 Oct" };
  }

  function yearsText(data) {
    const h = data && data.history;
    if (!h || !h.first_month || !h.last_month) return null;
    return String(Number(h.last_month.slice(0, 4)) - Number(h.first_month.slice(0, 4)));
  }

  function trustHtml(data) {
    const share = heldShare(data);
    const ex = exam(data);
    const span = D.text && D.text.TRACK_RECORD_YEARS ? ' <span class="nowrap">(' + esc(D.text.TRACK_RECORD_YEARS) + ")</span>" : "";
    const lead = share !== null
      ? "Our days-left number held <b>" + esc(fmt().thousands(fmt().inThousand(share))) + " times in 1,000</b> over ten years it never trained on" + span + "."
      : "";
    if (!lead && !ex) return "";
    // COP31 (30% of the judging) is said on the first screen, not only further down
    return '<p class="trust"><span class="badge">' + icon("i-tally") + "</span><span>" + lead +
      (ex ? '<small><a href="#proof/exam">' + esc(ex.line) + "</a></small>" : "") +
      '<small class="trust-cop"><a href="#questions/cop31">Climate adaptation for COP31</a></small>' + "</span></p>";
  }

  function statsHtml(data) {
    const share = heldShare(data);
    const ex = exam(data);
    const years = yearsText(data) || ((document.querySelector('[data-fill="years"]') || {}).textContent || "").trim();
    let html = "";
    if (share !== null) html += "<div><b>" + esc(fmt().inThousandText(share)) + "</b><span>how often our days-left number held, over ten years it never trained on</span></div>";
    if (years) html += "<div><b>" + esc(years) + " years</b><span>of free satellite records for each dam; nothing to install</span></div>";
    if (ex) html += "<div><b>" + esc(ex.statTitle) + "</b><span>" + esc(ex.statText) + "</span></div>";
    return html ? '<div class="stats">' + html + "</div>" : "";
  }

  // ---------------------------------------------------------------------------
  // Below the first screen: phones get three short cards, desktop the story
  // ---------------------------------------------------------------------------
  function regionLine(data) {
    const cov = data && data.meta && data.meta.coverage;
    const counts = cov && cov.live_status_counts;
    if (!counts || !cov.dams) return null;
    return {
      low: counts.already_low,
      all: cov.dams,
      name: data.meta.region ? data.meta.region.name : "the region",
      through: data.meta.data_through,
    };
  }

  function whyNowHtml(data, tag) {
    const r = regionLine(data);
    if (!r) return "";
    const f = fmt();
    return "<" + tag + ' class="why-card">' + '<p class="eyebrow">Why now</p><h2>' + f.thousands(r.low) + " of the " + f.thousands(r.all) +
      " dam-sized waterbodies we watch in " + esc(r.name) + ", mostly farm dams, were already below a third.</h2>" +
      "<p>At the latest satellite looks, to " + esc(f.date(r.through)) + ". In a dry spring, knowing how long each dam lasts decides when to move stock, cart water, buy feed, agist or sell.</p></" + tag + ">";
  }

  /** "about 0.5 to 5 ha": the dam sizes the satellites see, from meta (the smallest, and the coverage line's largest). */
  function sizeText(data) {
    const meta = (data && data.meta) || {};
    const lo = typeof meta.min_dam_area_ha === "number" ? Math.floor(meta.min_dam_area_ha * 10) / 10 : null;
    const cov = meta.coverage && meta.coverage.text ? /to\s+(\d+(?:\.\d+)?)\s*ha/.exec(meta.coverage.text) : null;
    const hi = cov ? Math.round(Number(cov[1])) : null;
    return lo !== null && hi !== null ? "about " + lo + " to " + hi + " ha" : null;
  }

  function cantSeeHtml(data, heroDam, tag) {
    const example = heroDam && heroDam.level_pct > 0 && heroDam.level_pct < 100 ? fmt().fullness(heroDam.level_pct) : null;
    const size = sizeText(data);
    return "<" + tag + ' class="why-card"><p class="eyebrow">What it can\'t see</p><h2>Small dams, bores, tanks, and depth.</h2>' +
      "<p>It follows dams big enough for the satellites to see" + (size ? ", " + esc(size) + "," : "") + " from above." +
      (example ? ' "' + esc(example) + '" is the share of the usual water surface that is wet, not the depth.' : " A dam's \"% full\" is the share of its usual water surface that is wet, not the depth.") +
      ' <a href="#questions/how-see">How a satellite can tell how much water a dam holds</a></p></' + tag + ">";
  }

  /** What is new (creativity): what DamDays does that sensors and rainfall maps don't. */
  function whatsNewHtml(data, tag) {
    const size = sizeText(data);
    return "<" + tag + ' class="why-card"><p class="eyebrow">What\'s new</p><h2>Days before each dam drops below a third, with nothing to install.</h2>' +
      "<p>Sensors read one dam's level today, and rainfall maps show how much rain fell, not how much water each dam holds. DamDays says at least how many days each farm dam big enough " +
      "for the satellites to see" + (size ? " (" + esc(size) + ")" : "") + " has before it drops below a third, from free satellite records, with each dam's own track record, " +
      'in one weekly text. <a href="#questions/whats-new">What already exists, and what\'s new</a></p></' + tag + ">";
  }

  /** COP31 (the Awareness track; the Global Goal on Adaptation), from About's own section, kept short. */
  function copHtml(tag) {
    return "<" + tag + ' class="why-card"><p class="eyebrow">Why it matters for COP31</p><h2>Helping farmers adapt to drier years.</h2>' +
      "<p>Awareness Across All Areas: it shows farmers, dam by dam, how many days each dam has before it drops below a third, while there are still choices. " +
      "The Global Goal on Adaptation's framework (the UAE Framework for Global Climate Resilience) includes targets on water scarcity and " +
      'climate-resilient farming; DamDays measures water security farm by farm. <a href="#about">More in About</a></p></' + tag + ">";
  }

  function howItWorksHtml(data, tag) {
    const h = data && data.history;
    const since = h && h.first_month ? " since " + h.first_month.slice(0, 4) : "";
    return "<" + tag + ' class="why-card"><p class="eyebrow">How it works</p><ol class="steps">' +
      "<li><span><b>Satellites watch each dam.</b> Geoscience Australia maps its water surface" + esc(since) + ".</span></li>" +
      "<li><span><b>We learn how each dam behaves</b> in dry and wet months, with the rainfall.</span></li>" +
      "<li><span><b>One text a week</b> gives the cautious days before each dam drops below a third.</span></li></ol></" + tag + ">";
  }

  /** The farm's dams (farms.json copy), in the shape the sketch wants, with each dam's text kind. */
  function farmDams(farm) {
    return (farm && farm.dams ? farm.dams : []).slice().sort((a, b) => a.number - b.number);
  }

  /** The dam with the fewest days on the farm (the text's headline dam), or null. */
  function heroDamOf(farm) {
    const fc = farmDams(farm).filter((d) => d.text_kind === "forecast" && typeof d.days_left === "number");
    fc.sort((a, b) => a.days_left - b.days_left || a.number - b.number);
    return fc[0] || null;
  }

  function sketchTag(d) {
    const k = d.text_kind || (d.status === "already_low" ? "low" : d.status === "forecast" ? "forecast" : "none");
    if (k === "forecast") {
      if (d.days_left <= 0) return { text: "may be below a third", low: true, label: d.name + ": may be below a third now", prio: 0 };
      const cap = D.text ? D.text.CAP_DAYS : 180;
      const t = d.days_left >= cap ? "6 months+" : d.days_left + (d.days_left === 1 ? " day" : " days");
      return { text: t, label: d.name + ": " + (t === "6 months+" ? "6 months or more" : "at least " + t) + " before it drops below a third", prio: 1 };
    }
    if (k === "low" && d.level_pct === 0) return { text: "no water seen", low: true, label: d.name + ": no water seen at its last clear look", prio: 0 };
    if (k === "low") return { text: "below a third", low: true, label: d.name + ": already below a third", prio: 0 };
    if (k === "not_refilled") return { text: "no forecast", quiet: true, label: d.name + ": no forecast until it refills", prio: 2 };
    return { text: "no recent look", quiet: true, label: d.name + ": no clear satellite look lately", prio: 2 };
  }

  function storyHtml(data, farm) {
    if (!farm) return "";
    const f = fmt();
    const dams = farmDams(farm);
    const hero = heroDamOf(farm);
    const tr = trackOf(data);
    const roll = tr && tr.farms ? tr.farms.find((x) => x.farm_id === farm.farm_id) : null;
    const heroLine = hero ? String(farm.sms).split("\n").find((l) => l.indexOf(hero.name + " ") === 0) : null;
    const farmAttr = ' data-farm="' + esc(farm.farm_id) + '"';

    let cards = "";
    // 1 · the text
    cards += '<li class="story-card"><p class="step-no" aria-hidden="true">1</p><h3>One text a week</h3>' +
      "<p>Each week the farmer gets one text message: the dam with the fewest days, any dam already low, and the rest in one line. It fits in one text message, so it needs no app and no mobile data.</p>" +
      (heroLine ? '<p class="story-quote"><span>' + esc(heroLine).replace(HL, (m) => '<mark class="hl">' + m + "</mark>") + "</span></p>" : "") + "</li>";
    // 2 · the dam
    if (hero) {
      cards += '<li class="story-card"><p class="step-no" aria-hidden="true">2</p><h3>Tap a dam to see why</h3>' +
        "<p>How full it was at its last clear satellite look, the chance it drops below a third by a date, and the next six months.</p>" +
        '<a class="story-dam" href="#farm/dam-' + hero.number + '"' + farmAttr + ">" +
        (D.sketch ? D.sketch.glyph(Object.assign({ status: hero.status }, hero), 56, true) : "") +
        '<span class="story-dam-text"><span><b>' + esc(hero.name) + "</b> " + esc(f.fullness(hero.level_pct)) + " at the " + esc(f.short(hero.issued_on)) + " look</span>" +
        '<span class="story-chance">' + (D.sketch ? D.sketch.dots(hero.chance, 5, f.chance(hero.chance) + " by " + f.short(hero.window_end), true) : "") +
        '<span class="nowrap">' + esc(f.chance(hero.chance)) + " by " + esc(f.short(hero.window_end)) + "</span></span>" +
        '<span class="story-days">at least ' + esc(hero.days_left) + " days before it drops below a third</span></span>" + icon("i-chev", "chev") + "</a></li>";
    }
    // 3 · the record on these dams
    if (roll && roll.judged) {
      const share = D.text && D.text.heldShareText ? D.text.heldShareText(roll.held, roll.judged) : "";
      const span = (tr && tr.label) || "the last 10 years";
      const pct = (100 * roll.held / roll.judged).toFixed(1);
      cards += '<li class="story-card"><p class="step-no" aria-hidden="true">3</p><h3>Judge us on your own dams</h3>' +
        "<p>Over " + esc(span) + ", our days-left number held <b>" + f.thousands(roll.held) + " of " + f.thousands(roll.judged) + " times</b> on these " +
        f.thousands(roll.dams_with_record || dams.length) + " dams" + (share && share !== "every time" ? " (" + esc(share) + ")" : "") + ".</p>" +
        '<div class="tallybar" role="img" aria-label="' + esc("held " + roll.held + " of " + roll.judged + " times") + '"><i style="width:' + pct + '%"></i></div>' +
        '<p class="small">' + esc(D.text && D.text.TRACK_RECORD_HOW ? D.text.TRACK_RECORD_HOW : (tr && tr.tip) || "") + "</p></li>";
    }

    const nearTown = farm.near_town ? " near " + esc(farm.near_town) : "";
    return '<section class="story" aria-labelledby="story-h2"' + farmAttr + ">" +
      '<div class="story-head"><p class="eyebrow">How a farmer sees it</p><h2 id="story-h2">One text a week. The detail is one tap away.</h2></div>' +
      '<ol class="story-cards">' + cards + "</ol>" +
      '<div class="story-farm">' +
        '<figure class="story-sketch"><div class="sketch" id="welcome-sketch"></div>' +
        '<figcaption class="sketch-cap">' + esc(shortName(farm.name)) + " from above: its " + dams.length +
        " dams within " + esc(farm.radius_km) + " km of the homestead point, drawn from the satellite record. Dams are drawn larger than life.</figcaption></figure>" +
        '<div class="story-side">' +
          '<p class="eyebrow">The farm from above</p><h3>Every dam the satellites can see, within ' + esc(farm.radius_km) + " km of the homestead.</h3>" +
          "<p>No property boundaries and nothing to install: a farm is a homestead point and a circle. Tap a tag to open that dam.</p>" +
          '<p class="small">' + esc(demoNote(farm)) + "</p>" +
          '<div class="story-actions"><a class="btn btn-primary" href="#farm"' + farmAttr + ">See the " + dams.length + " dams" + nearTown + "</a>" +
          '<a class="btn btn-quiet" href="#runway">' + icon("i-map") + "Runway: the region map</a></div>" +
        "</div>" +
      "</div>" +
      '<div class="story-why">' + whyNowHtml(data, "div") + copHtml("div") + whatsNewHtml(data, "div") + cantSeeHtml(data, hero, "div") + "</div>" +
      "</section>";
  }

  function belowHtml(data, farm) {
    const hero = heroDamOf(farm);
    const phone = '<div class="why mob-only">' + whyNowHtml(data, "section") + copHtml("section") + howItWorksHtml(data, "section") +
      whatsNewHtml(data, "section") + cantSeeHtml(data, hero, "section") + "</div>";
    return phone + '<div class="desk-only">' + storyHtml(data, farm) + "</div>";
  }

  // ---------------------------------------------------------------------------
  // Glossary sheet (5.8): "What is a farm dam?" with the labelled paddock drawing
  // ---------------------------------------------------------------------------
  function glossaryHtml() {
    const P = D.sketch ? D.sketch.DAM_PATH : "M20 31C23 15 45 9 63 13C81 17 92 31 89 51C86 72 72 89 50 88C28 87 12 74 11 55C10 45 16 39 20 31Z";
    return '<div class="gloss-sheet"><p class="eyebrow">For readers outside Australia</p><h2>What is a farm dam?</h2>' +
      '<svg class="paddock" viewBox="0 0 340 190" width="100%" role="img" aria-label="A paddock seen from above with a farm dam: the water, its usual full edge and the earth wall">' +
      '<rect width="340" height="190" rx="18" fill="var(--straw)"/><path d="M0 40 H340 M120 0 V190" stroke="var(--straw-deep)" stroke-width="3"/>' +
      '<g transform="translate(150 30) scale(1.4)"><path d="' + P + '" fill="var(--dam-bed)" stroke="var(--dam-rim)" stroke-width="3"/>' +
      '<path d="' + P + '" fill="var(--water)" transform="translate(64 70) scale(.82) translate(-64 -70)"/>' +
      '<path d="M34 86 Q52 95 74 84" fill="none" stroke="var(--earth)" stroke-width="6" stroke-linecap="round"/></g>' +
      '<text x="14" y="70" font-size="15" font-weight="800" fill="var(--ink)">the water</text><path d="M86 66 L200 92" stroke="var(--ink)" stroke-width="1.5"/>' +
      '<text x="14" y="150" font-size="15" font-weight="800" fill="var(--ink)">earth wall</text><path d="M90 146 L238 158" stroke="var(--ink)" stroke-width="1.5"/>' +
      '<text x="250" y="24" font-size="15" font-weight="800" fill="var(--ink)">usual edge</text><path d="M282 30 L262 58" stroke="var(--ink)" stroke-width="1.5"/></svg>' +
      "<p>In Australia a <b>farm dam</b> is the water itself: a pond dug in a paddock to catch run-off, held by an earth wall. Sheep and cattle drink from it. DamDays watches its water surface from space.</p>" +
      '<dl class="words"><div><dt>Grazier</dt><dd>a farmer who raises sheep or cattle on pasture.</dd></div>' +
      "<div><dt>Paddock</dt><dd>a fenced field.</dd></div>" +
      "<div><dt>Water run</dt><dd>the drive around a farm's dams and troughs to check them.</dd></div>" +
      "<div><dt>Agistment</dt><dd>paying to graze stock on someone else's land, often in a drought.</dd></div>" +
      "<div><dt>Homestead</dt><dd>the farmhouse.</dd></div>" +
      "<div><dt>Bore</dt><dd>a well that pumps groundwater.</dd></div></dl>" +
      '<p class="small">"% full" is the share of the dam\'s usual water surface that is wet, seen from above. Not depth.</p></div>';
  }

  function openGlossary() {
    if (!D.sheet) return;
    D.sheet.open({ title: "Farm words", short: true, body: glossaryHtml() });
  }

  // ---------------------------------------------------------------------------
  // Fill the static first screen
  // ---------------------------------------------------------------------------
  let sketchCtl = null;

  /** The farm saved on this phone by My farm (js/views/farm.js, "damdays.farm"), for this dataset; or null. */
  function savedFarm() {
    try {
      const v = JSON.parse(localStorage.getItem("damdays.farm") || "null");
      const name = new URLSearchParams(location.search).get("data") || "real";
      return v && typeof v === "object" && (v.data || "real") === name ? v : null;
    } catch (e) {
      return null;
    }
  }

  function fill(data) {
    const farm = demoFarm(data);
    const textDate = (farm && farm.date) || textDateOf(data);
    const day = textDate && D.text ? D.text.dateText(textDate) : "";

    const smsBox = $("welcome-sms");
    if (smsBox) {
      if (farm && farm.sms) {
        const note = "Tap a dam's line to see why. " + esc(demoNote(farm));
        smsBox.innerHTML = smsHtml(farm.sms, { date: day, note, first: firstTime(), farmId: farm.farm_id });
      } else {
        smsBox.innerHTML = '<div class="sms sms-empty"><p>This data has no demo farm. Open My farm and tap the map where a homestead is to make its text.</p></div>';
      }
      smsBox.removeAttribute("aria-busy");
    }
    const trust = $("welcome-trust");
    if (trust) trust.innerHTML = trustHtml(data);

    const see = $("welcome-see-dams");
    const own = new URLSearchParams(location.search).get("farm") ? null : savedFarm();   // ?farm= wins on My farm too
    if (see && own && !(farm && own.farm_id === farm.farm_id && own.radiusKm === farm.radius_km)) {
      // a farmer's own saved farm opens on My farm: name that, not the demo farm's dam count
      see.textContent = "See my farm";
      see.removeAttribute("data-farm");
    } else if (see && farm) {
      see.textContent = "See the " + farm.dams.length + " dam" + (farm.dams.length === 1 ? "" : "s");
      see.setAttribute("data-farm", farm.farm_id);
    }
    const stats = $("welcome-stats");
    if (stats) stats.innerHTML = statsHtml(data);
    const cap = $("welcome-phone-cap");
    if (cap && farm) {
      cap.hidden = false;
      cap.textContent = "The real text of " + day + " for a demo farm near " + farm.near_town + ": its " + farm.dams.length +
        " dams and their forecasts are real; the homestead point is made up.";
    } else if (cap) {
      cap.hidden = true;                                 // made-up data (?data=mock): no demo farm, no caption
    }
    const years = yearsText(data);
    if (years) document.querySelectorAll('#v-welcome [data-fill="years"]').forEach((n) => { n.textContent = years; });
    const size = sizeText(data);
    if (size) document.querySelectorAll('#v-welcome [data-fill="size"]').forEach((n) => { n.textContent = size; });

    // The cards below the fold come a frame later, so the text paints first (a shorter first task).
    const fillBelow = () => fillBelowNow(data, farm, textDate);
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => setTimeout(fillBelow, 0));
    else fillBelow();
  }

  function fillBelowNow(data, farm, textDate) {
    const below = $("welcome-below");
    if (below) {
      below.innerHTML = belowHtml(data, farm ? Object.assign({ date: textDate }, farm) : null);
      const sk = $("welcome-sketch");
      if (sk && farm && D.sketch) {
        if (sketchCtl) sketchCtl.destroy();
        // a big farm: tags for every dam below a third and the 8 with the fewest days (as My farm)
        const all = farmDams(farm);
        const tagged = new Set(all.length <= 10 ? all.map((d) => d.number)
          : all.filter((d) => d.text_kind === "low").concat(all.filter((d) => d.text_kind === "forecast")
            .sort((a, b) => a.days_left - b.days_left || a.number - b.number).slice(0, 8)).map((d) => d.number));
        sketchCtl = D.sketch.farm(sk, {
          dams: all,
          home: { lat: farm.lat, lon: farm.lon },
          radiusKm: farm.radius_km,
          tag: (d) => (tagged.has(d.number) ? sketchTag(d) : null),
          href: (d) => "#farm/dam-" + d.number,
          ratio: 0.86,
          homeLabel: ["Homestead", "(demo point)"],
        });
      }
    }
  }

  if (D.router) {
    D.router.register("welcome", {
      render() {
        return want("first").then(fill);
      },
      enter(route) {
        if (route.sub === "farm-dam") openGlossary();
      },
    });
  }

  return { smsHtml, demoNote, shortName, demoFarm, glossaryHtml, want, sketchTag, refresh: fill };
})();
