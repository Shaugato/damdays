/* views/questions.js (WP-F)
 * Questions judges ask (#questions, #questions/<id>; #faq is an alias). UI_SPEC 3.5 and 5.20.
 *
 *   Glance:  the title, three things to know, a search box, group chips, and the questions as 56 px rows.
 *   More:    opening a question shows its answer: one sentence a judge could quote, then a little more.
 *   Most:    "Show the numbers" (two lines or a small table) and "Where to check" (repository files).
 *
 * Opening a question pushes #questions/<id> (so Back closes it); one is open at a time. The answers come
 * from research/questions/FAQ_DRAFT.md, rewritten for the featured demo farm (Farm E, near Mudgee) and
 * the app's wording rules. Every number is read from the data (meta, forecasts, farms, proof,
 * track_record, scoreboard, history); a question whose numbers are missing from this dataset is left out.
 * Who pays names our customers in order (CUSTOMERS below), always with the plain line that no price is set
 * and no customer has been approached yet.
 * The optional who-else slot (UI_SPEC 5.21) is last; ?whoelse=0 leaves it out.
 */
window.DamDays = window.DamDays || {};

(function () {
  "use strict";

  const D = window.DamDays;
  const esc = (t) => D.format.escapeHtml(t === null || t === undefined ? "" : t);
  const icon = (id, cls) => (D.icon ? D.icon(id, cls) : "");
  const repo = (path) => ((D.settings && D.settings.repoBlobUrl) || "https://github.com/Shaugato/damdays/blob/main/") + path;
  const COMMITS = "https://github.com/Shaugato/damdays/commits/main";

  // ---- small formatting helpers (all from js/format.js and js/text.js) ----
  const f = () => D.format;
  const T = (n) => f().thousands(n);
  const S = (iso) => f().short(iso);
  const L = (iso) => f().date(iso);
  const DS = (iso) => f().dayShort(iso);
  const CH = (x) => f().chance(x);
  const tenOf = (x) => D.text.inTen(x);
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const monthYear = (iso) => MONTHS[Number(String(iso).slice(5, 7)) - 1] + " " + String(iso).slice(0, 4);
  const shortName = (name) => String(name || "").replace(/\s*\(.*\)\s*$/, "");
  const seasonLabel = (year) => year + "-" + String(Number(year) + 1).slice(2);
  /**
   * A cautious-days count against its target, by the one on-target rule (format.floorCheck(...): a panel's own
   * on_target flag, else the test code's float rule):
   * ", below its target range of 880 to 920 (built for 900)" | ", inside ..." |
   * ", above its target range of 880 to 920 (built for 900), so more cautious than built for" |
   * ", just below its target range of 880 to 920 by the test's exact check (built for 900)" (a result at the edge) |
   * ", against its target of 900" | "".
   */
  function againstTarget(fc) {
    if (!fc || fc.target === null) return "";
    if (!fc.range) return ", against its target of " + T(fc.target);
    const where = fc.onTarget === true ? "inside" : fc.below ? "below" : fc.above ? "above" : "against";
    const exact = fc.edge && (fc.below || fc.above);
    return ", " + (exact ? "just " : "") + where + " its target range of " + fc.range + (exact ? " by the test's exact check" : "") +
      " (built for " + T(fc.target) + ")" + (fc.above ? ", so more cautious than built for" : "");
  }

  /** Throws when a number this answer needs is missing, so the question is left out (never shown half-empty). */
  function need(value) {
    if (value === null || value === undefined || (typeof value === "number" && Number.isNaN(value))) throw new Error("missing");
    return value;
  }

  /** The earliest end of a live forecast's 90 days, only when every dam's row is loaded (else null). */
  function firstWindowOf(data) {
    const rows = data && data.liveIssue ? data.liveIssue.rows || [] : [];
    const all = data && data.meta && data.meta.coverage ? data.meta.coverage.dams : null;
    if (!rows.length || (all && rows.length < all)) return null;
    const windows = rows.filter((r) => r.status === "forecast" && r.window_end).map((r) => r.window_end).sort();
    return windows.length ? windows[0] : null;
  }

  /** Fill the date of the first live answers when its question is opened (it needs every dam: the "core" part). */
  function fillFirstWindow(scope) {
    const el = scope && scope.querySelector("[data-first-window]");
    if (!el || el.dataset.filled) return;
    el.dataset.filled = "1";
    const need = D.data && typeof D.data.need === "function" ? D.data.need("core") : Promise.resolve(D.data.load());
    Promise.resolve(need).then((x) => {
      const first = firstWindowOf(x && x.liveIssue ? x : D.data.load());
      if (first && el.isConnected) el.textContent = "after " + f().date(first);
    }).catch(() => { el.dataset.filled = ""; });
  }

  // =====================================================================
  // The facts every answer reads, built once from the data
  // =====================================================================
  function buildFacts(data) {
    const meta = data.meta || {};
    const F = { data, meta };
    F.region = meta.region ? meta.region.name : null;
    F.through = meta.data_through || null;
    F.horizon = meta.horizon_days || null;
    F.thresholdPct = meta.threshold_pct || null;
    F.armPct = meta.arm_level_pct || null;
    F.likelyInTen = (D.settings && D.settings.likelyInTen) || 5;

    // Dam sizes: the smallest from meta, the largest from meta's coverage line ("0.54 to 4.95 ha"), else from the dams loaded.
    const areas = (data.dams || []).map((d) => d.area_ha).filter((a) => typeof a === "number");
    const minHa = typeof meta.min_dam_area_ha === "number" ? meta.min_dam_area_ha : (areas.length ? Math.min.apply(null, areas) : null);
    const cov = meta.coverage && meta.coverage.text ? /to\s+(\d+(?:\.\d+)?)\s*ha/.exec(meta.coverage.text) : null;
    const maxHa = cov ? Number(cov[1]) : (areas.length ? Math.max.apply(null, areas) : null);
    F.minHa = minHa !== null ? Math.floor(minHa * 10) / 10 : null;
    F.size = minHa !== null && maxHa !== null ? "about " + F.minHa + " to " + Math.round(maxHa) + " ha" : null;
    const hist = data.history || {};
    F.firstYear = hist.first_month ? Number(String(hist.first_month).slice(0, 4)) : null;
    F.years = hist.first_month && hist.last_month ? Number(String(hist.last_month).slice(0, 4)) - F.firstYear : null;

    // the region this week
    // The region this week: from meta.coverage (in the "first" part); counting rows needs every dam loaded.
    const rows = data.liveIssue ? data.liveIssue.rows : [];
    const lsc = meta.coverage && meta.coverage.live_status_counts;
    const count = (st) => rows.filter((r) => r.status === st).length;
    F.counts = lsc && meta.coverage.dams ? {
      dams: meta.coverage.dams, forecast: lsc.forecast || 0, low: lsc.already_low || 0, notRefilled: lsc.not_refilled || 0,
      noLook: lsc.no_recent_look || 0,
    } : (rows.length ? {
      dams: rows.length, forecast: count("forecast"), low: count("already_low"), notRefilled: count("not_refilled"),
      noLook: count("no_recent_look"),
    } : null);
    if (F.counts) F.counts.quiet = F.counts.dams - F.counts.forecast;
    F.firstWindow = firstWindowOf(data);

    // the demo farms and the featured farm
    const hidden = (D.settings && D.settings.hiddenFarmIds) || [];
    const farms = data.farms && Array.isArray(data.farms.farms) ? data.farms.farms.filter((x) => !hidden.includes(x.farm_id)) : [];
    F.farms = farms;
    F.textDate = data.farms ? data.farms.date : (data.textDate || null);
    F.radiusKm = data.farms && typeof data.farms.radius_km === "number" ? data.farms.radius_km : null;
    F.setAside = data.farms && Array.isArray(data.farms.set_aside) ? data.farms.set_aside : [];
    F.farm = farms.find((x) => x.farm_id === (D.settings && D.settings.defaultFarmId)) || farms[0] || null;
    if (F.farm) {
      F.farmName = F.farm.name;
      F.farmShort = shortName(F.farm.name);
      F.farmDams = Array.isArray(F.farm.dams) ? F.farm.dams.slice().sort((a, b) => a.number - b.number) : [];
      const forecast = F.farmDams.filter((d) => d.status === "forecast" && typeof d.days_left === "number");
      F.hero = forecast.slice().sort((a, b) => a.days_left - b.days_left)[0] || null;
      F.noWater = F.farmDams.find((d) => d.level_pct === 0) || null;
      F.weakest = null;
    }
    const live = data.liveIssue;
    const rowOf = (d) => (live && d ? live.rowsByDam.get(d.dam_id) || null : null);
    F.heroRow = rowOf(F.hero);
    if (F.hero && F.textDate) {
      F.since = D.text.dayNumber(F.textDate) - D.text.dayNumber(F.hero.issued_on);
      F.heroDay = f().addDays(F.hero.issued_on, F.hero.damdays_days);
    }
    F.noteDam = F.farmDams ? F.farmDams.find((d) => { const r = rowOf(d); return r && r.notes && r.notes.length; }) || null : null;
    F.noteText = F.noteDam ? rowOf(F.noteDam).notes[0] : null;
    if (farms.length) {
      const sizes = farms.map((x) => (Array.isArray(x.dams) ? x.dams.length : x.dams)).filter((n) => typeof n === "number");
      F.damRange = sizes.length ? [Math.min.apply(null, sizes), Math.max.apply(null, sizes)] : null;
      const regions = [];
      farms.forEach((x) => { if (x.region_name && !regions.includes(x.region_name)) regions.push(x.region_name); });
      F.regionNames = regions;
      // An example the farm's own text names as "full" (the short text first, then the longer version).
      let over = null;
      const named = (text, d) => new RegExp("(^|[\\n;:] ?)" + String(d.name).replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + " full\\b").test(String(text || ""));
      farms.forEach((x) => (x.dams || []).forEach((d) => {
        if (typeof d.level_pct !== "number" || d.level_pct <= 100) return;
        const where = named(x.sms, d) ? "its text says" : named(x.long, d) ? "its longer text says" : null;
        if (where && (!over || d.level_pct > over.dam.level_pct)) over = { farm: x, dam: d, where };
      }));
      F.over100 = over;
    }

    // the track record
    const tr = data.trackRecord;
    F.trLabel = tr ? tr.label : null;
    F.records = tr && tr.dams ? tr.dams : null;
    F.heroRec = F.records && F.hero ? F.records[F.hero.dam_id] || null : null;
    F.farmRec = tr && Array.isArray(tr.farms) && F.farm ? tr.farms.find((x) => x.farm_id === F.farm.farm_id) || null : null;
    F.dist = tr && tr.summary ? tr.summary.distribution : null;
    F.trFirstYear = tr ? tr.first_season_year : null;

    // the test years (proof.json)
    const proof = data.proof;
    F.proof = proof;
    F.test = proof ? proof.test : null;
    F.allYears = proof && proof.by_year ? proof.by_year.all_years : null;
    F.byYear = proof && proof.by_year ? proof.by_year.years || [] : [];
    F.floorTarget = proof && proof.by_year ? proof.by_year.floor_target : null;
    F.bins = proof && proof.calibration ? proof.calibration.bins || [] : [];
    F.exam = proof ? proof.unseen_exam : null;
    F.damByDam = proof ? proof.dam_by_dam : null;
    if (F.bins.length) {
      const likely = F.bins.filter((b) => b.in_ten >= F.likelyInTen);
      F.likely = { forecasts: likely.reduce((s, b) => s + b.forecasts, 0), fell: likely.reduce((s, b) => s + b.fell, 0) };
      F.lowBin = F.bins.find((b) => b.in_ten === 0) || null;
    }
    const cutoff = meta.rewind && meta.rewind.model_cutoff ? meta.rewind.model_cutoff : (F.trFirstYear ? F.trFirstYear + "-07-01" : null);
    F.cutoffWords = cutoff ? monthYear(cutoff) : null;
    F.rewindSeason = meta.rewind ? meta.rewind.season : null;

    // the score panels (scoreboard.json)
    const panels = data.scoreboard && Array.isArray(data.scoreboard.panels) ? data.scoreboard.panels : [];
    F.dev = panels.find((p) => p.key === "dev_test") || null;
    F.sealed = panels.find((p) => p.key === "sealed") || null;
    return F;
  }

  // =====================================================================
  // Building blocks for answers
  // =====================================================================
  function numbers(html) {
    return '<details class="more faq-sub"><summary>' + icon("i-chart") + "<span>Show the numbers</span>" + icon("i-plus", "plus") +
      '</summary><div class="body">' + html + "</div></details>";
  }

  function check(list) {
    if (!list || !list.length) return "";
    return '<details class="more faq-sub"><summary>' + icon("i-ext") + "<span>Where to check</span>" + icon("i-plus", "plus") +
      '</summary><div class="body"><ul class="checklinks">' + list.map((c) => {
        const href = /^https?:/.test(c[1]) ? c[1] : repo(c[1]);
        const host = /^https?:\/\/([^/]+)/.exec(c[1]);
        const small = host ? (/(^|\.)github\.com$/.test(host[1]) ? "on GitHub" : host[1].replace(/^www\./, "")) : (/PREREG/i.test(c[1]) ? "the test plan file" : c[1]);
        return '<li><a href="' + esc(href) + '" rel="noopener">' + esc(c[0]) + "</a> <small>" + esc(small) + "</small></li>";
      }).join("") + "</ul></div></details>";
  }

  function go(list) {
    return '<p class="faq-go">' + list.map((g) => '<a class="faq-link" href="' + esc(g[0]) + '">' + esc(g[1]) + icon("i-chev", "sm") + "</a>").join("") + "</p>";
  }

  function table(head, rows) {
    return '<div class="table-scroll"><table class="data"><thead><tr>' + head.map((h, i) => '<th scope="col"' + (i ? ' class="num"' : "") + ">" + esc(h) + "</th>").join("") +
      "</tr></thead><tbody>" + rows.map((r) => "<tr>" + r.map((c, i) => (i ? '<td class="num">' : '<th scope="row">') + esc(c) + (i ? "</td>" : "</th>")).join("") + "</tr>").join("") +
      "</tbody></table></div>";
  }

  const P = (text) => "<p>" + esc(text) + "</p>";

  // Our customers, in order (mentor advice: farmers first; the lender case set aside). No prices, and no customer
  // approached yet: HONEST goes with the list every time it is shown.
  const CUSTOMERS = [
    ["Farmers", "family sheep and cattle graziers whose stock drink from dams. They are the users, and they come first, as a mentor advised."],
    ["Drought support programmes and agencies", "for example, state drought teams and Local Land Services, Future Drought Fund programmes, regional drought resilience groups, and farm advisers who look after many farms. They could provide DamDays to the farmers in their region, and use the district view (Runway) to see where stock water runs short first."],
    ["Fire agencies", "to know before fire season which farm dams crews and aircraft can still refill from."],
    ["Farm software platforms and dam-sensor companies, as partners", "a sensor shows the level now; adding our forecast completes it."],
    ["Later, rural lenders and insurers", "set aside for now on mentor advice."],
  ];
  const HONEST = "We have not set prices or approached these customers yet; the next step is to talk to farmers and two drought programmes.";
  const customersHtml = () => '<ol class="faq-steps">' + CUSTOMERS.map((c) => "<li><b>" + esc(c[0]) + ":</b> " + esc(c[1]) + "</li>").join("") + "</ol>";

  /** The featured farm's SMS as a small text bubble, word for word from farms.json. */
  function smsHtml(F) {
    const lines = String(need(F.farm.sms)).split("\n");
    return '<figure class="faq-sms"><div class="faq-sms-head"><span>DamDays <span class="tag">Demo</span></span><span>' + esc(DS(F.textDate)) + "</span></div>" +
      '<div class="faq-sms-bubble">' + lines.map((l) => "<span>" + esc(l) + "</span>").join("") + "</div>" +
      "<figcaption class=\"small\">The real text our script wrote for " + esc(DS(F.textDate)) + " for " + esc(F.farmName) + ". Its " +
      esc(F.farmDams.length) + " dams and their forecasts are real; the homestead point is made up, and no farmer gets this text yet." +
      (D.text.fitsOneSms && D.text.fitsOneSms(F.farm.sms) ? " It fits in one text message." : "") + "</figcaption></figure>";
  }

  function installSteps() {
    return '<ol class="faq-steps"><li><b>iPhone (Safari):</b> tap Share, then Add to Home Screen. On iOS 26: the ··· menu, Share, Add to Home Screen, and keep Open as Web App on.</li>' +
      "<li><b>Android (Chrome):</b> open the menu (the three dots), then Install app or Add to Home screen.</li></ol>";
  }

  // =====================================================================
  // The questions (ids as UI_SPEC 3.5, plus the rest of FAQ_DRAFT.md)
  // Each: { id, q(F), a(F) -> the quotable sentence (text), more(F) -> html, nums(F) -> html, check, go(F) }
  // =====================================================================
  const GROUPS = [
    { id: "basics", title: "What it is", items: [
      { id: "problem", q: () => "What problem does it solve, in one sentence?",
        a: () => "Graziers whose stock drink from farm dams can't easily tell how many days of water each dam has left, so the costly moves a drought forces (move stock, cart water, buy feed, agist or sell) are often made late, when there are fewer choices.",
        more: () => P("Today they drive the water run and do the sums by hand: measure the dam, look up its volume, divide by what the stock drink. DamDays sends that number, dam by dam, once a week."),
        go: () => [["#welcome/farm-dam", "What is a farm dam?"]],
        check: [["The one-page summary", "docs/ONE_PAGER.md"], ["Who it is for", "docs/TARGET_FARMER.md"]] },

      { id: "what-farmers-get", q: () => "What does a farmer actually get?",
        a: () => "One text a week for each farm: for the dams that matter, how full each one was at its last clear satellite look, and at least how many days it has before it drops below a third.",
        more: (F) => smsHtml(F),
        go: (F) => [["#farm", "See " + need(F.farmShort) + "'s dams"], ["#farm/text", "This week's text, and the longer version"]],
        check: [["How the weekly text is written", "notify/MESSAGE_SPEC.md"], ["The project's front page", "README.md"]] },

      { id: "why-text", q: () => "Why a text, not an app?",
        a: () => "A plain text works on any mobile with nothing to install, and a mentor told us farmers rarely open apps or emails, but a weekly text suits them.",
        more: () => P("This rests on one mentor's view: we have not tested it with graziers yet, and we have not checked mobile coverage on farms. The app is where you look closer."),
        check: [["Who it is for", "docs/TARGET_FARMER.md"], ["How the weekly text is written", "notify/MESSAGE_SPEC.md"]] },

      { id: "percent-full", q: (F) => "What does \"" + f().fullness(need(F.hero).level_pct) + "\" mean?",
        a: (F) => "It is the share of " + F.hero.name + "'s usual full water surface that the satellite saw wet at its last clear look, on " + L(F.hero.issued_on) +
          ". Satellites can't see depth, so it is not depth or litres.",
        more: () => P("In DamDays \"%\" only ever means how full a dam is. At its usual full level or above, the text simply says \"full\"."),
        nums: (F) => P(need(F.farmName) + "'s dams at their last clear look:") + table(["Dam", "How full", "Look", "Size when full"],
          F.farmDams.map((d) => [d.name, f().fullness(d.level_pct), d.issued_on ? S(d.issued_on) : "none lately", d.area_ha.toFixed(1) + " ha"])),
        check: [["How the weekly text is written", "notify/MESSAGE_SPEC.md"], ["The data", "docs/DATA.md"]] },

      { id: "why-at-least", q: (F) => "Why \"at least " + need(F.hero).days_left + " days\" and not a date?",
        a: (F) => "Because it is cautious by design: the count is built to hold 9 times in 10 across all dams (a little less often for spring looks), so a dam will most likely last longer." +
          (F.heroDay ? " The app shows the date too (" + S(F.heroDay) + " for " + F.hero.name + ", its DamDays day); the text uses days because they read faster on a phone." : ""),
        more: () => P("It counts the days before the dam drops below a third of its usual full water surface, not until it is empty. A third is an early-warning line, so there is still time to act."),
        nums: (F) => P(F.hero.name + ": " + need(F.hero.damdays_days) + " days from its " + S(F.hero.issued_on) + " satellite look, less the " + need(F.since) +
          " days since, is at least " + F.hero.days_left + " days from " + DS(F.textDate) + ".") +
          P("Across all dams in the ten test years, the count held " + T(f().inThousand(need(F.allYears).floor_held)) + " times in 1,000 (" + T(F.allYears.floor_judged) +
          " forecasts checked), a little less often for spring looks."),
        check: [["The test results", "artifacts/test_results.md"], ["How the weekly text is written", "notify/MESSAGE_SPEC.md"]] },

      { id: "days-vs-chance", q: (F) => "The text says \"at least " + need(F.hero).days_left + " days\" and the app says \"" + CH(need(F.hero.chance)) + " by " + S(F.hero.window_end) + "\". Which do I act on?",
        a: (F) => "Plan on the days: they are the cautious figure. The chance is a second view: the chance this dam drops below a third by " + S(F.hero.window_end) + ", from a model that learned from dams like it.",
        more: () => P("They come from two models, so they don't always line up exactly. Neither number is advice: check the dam too."),
        nums: (F) => P(F.hero.name + ": at least " + F.hero.days_left + " days from " + DS(F.textDate) + ", which runs to " + S(need(F.heroDay)) + ". Chance it drops below a third by " +
          S(F.hero.window_end) + ": " + CH(F.hero.chance) + (F.heroRow && typeof F.heroRow.chance_low === "number"
            ? "; in a wetter or drier season than usual, " + f().chanceRange(F.heroRow.chance_low, F.heroRow.chance_high) : "") + "."),
        go: (F) => [["#farm/dam-" + F.hero.number, "Open " + F.hero.name]] },

      { id: "held-meaning", q: () => "Does \"built to hold 9 times in 10\" mean it is right 9 times in 10?",
        a: (F) => "Not quite: it is a floor, not our guess of the day. In the ten test years dams stayed above a third for at least the promised days " +
          T(f().inThousand(need(F.allYears).floor_held)) + " times in 1,000, and most lasted well past it; about 1 time in 10 a dam fell below a third sooner.",
        nums: (F) => P("Our record on " + need(F.hero).name + " over " + need(F.trLabel) + ": " + f().held(need(F.heroRec).held, F.heroRec.judged) + " (" +
          D.text.heldShareText(F.heroRec.held, F.heroRec.judged) + ").") +
          (F.farmRec ? P("On " + F.farmShort + "'s " + F.farmRec.dams + " dams: " + f().held(F.farmRec.held, F.farmRec.judged) + " (" + D.text.heldShareText(F.farmRec.held, F.farmRec.judged) + ").") : ""),
        go: (F) => [["#farm/dam-" + F.hero.number + "/record", F.hero.name + "'s record, season by season"]],
        check: [["Our record, dam by dam", "artifacts/track_record.md"], ["The test results", "artifacts/test_results.md"]] },

      { id: "farm-words", q: () => "What are a farm dam, a grazier, a paddock and the water run?",
        a: () => "A farm dam is the water itself: a pond dug in a paddock to catch run-off, held by an earth wall, that sheep and cattle drink from.",
        more: () => '<dl class="faq-words"><dt>Grazier</dt><dd>A farmer who raises sheep or cattle on pasture.</dd>' +
          "<dt>Paddock</dt><dd>A fenced field.</dd><dt>Water run</dt><dd>The drive around a farm's dams and troughs to check them.</dd>" +
          "<dt>Carting water</dt><dd>Trucking water in when a dam runs low.</dd><dt>Agistment</dt><dd>Paying to graze stock on someone else's land, often in a drought.</dd>" +
          "<dt>Homestead</dt><dd>The farmhouse.</dd><dt>Bore</dt><dd>A well that pumps groundwater.</dd></dl>",
        go: () => [["#welcome/farm-dam", "See the farm dam drawing"]] },

      { id: "live-service", q: () => "Is the weekly text a live service today?",
        a: (F) => "No: our script wrote this week's texts for " + need(F.farms.length || null) + " demo farms, but none has a phone number and nothing has been sent to a real farmer.",
        more: () => P("Replies such as MAP and STOP, opt-in and a sender name are not built, and Australia's spam law asks for a named sender and a working unsubscribe before any real send.") +
          P("Drought programmes and farm platforms, two of the customers we name under \"Who pays\", could offer the text to the farmers they work with; we have not approached any yet."),
        check: [["How the weekly text is written", "notify/MESSAGE_SPEC.md"], ["The one-page summary", "docs/ONE_PAGER.md"]] },

      { id: "who-for", q: () => "Which farms is it for?",
        a: (F) => "Family sheep and cattle farms, run by one or two people, whose stock drink from at least one farm dam big enough for the satellites to see (" + need(F.size) + "), in the farming regions where we tested it.",
        more: (F) => P("We tested it in " + (F.regionNames && F.regionNames.length ? F.regionNames.join(" and ") : need(F.region)) +
          ". Most farm dams are too small for the satellites, so a typical farm would see only one or a few of its dams in the text. Bore-fed stations, irrigators and hobby blocks are not the target.") +
          P("Anywhere else, such as Bourke, Cobar, the tropical north or WA, is untested, and each new area needs its own test before it gets texts."),
        check: [["Who it is for, described from public farm surveys", "docs/TARGET_FARMER.md"]] },

      { id: "australia-only", q: () => "Is it Australia only?",
        a: () => "For now, yes: it runs on Australian satellite and rainfall records, and we have tested it only in south-eastern Australia.",
        more: () => P("The satellites behind the record (Landsat) cover the whole world, and similar waterbody records exist elsewhere, such as Digital Earth Africa's. So other countries are a later path, not built: each would need its own waterbody record, its own rainfall record, its own test, and a way to reach its farmers.") +
          P("In Africa, USGS FEWS NET already forecasts livestock water points a month ahead; working with it would make more sense than competing."),
        check: [["What already exists", "docs/WHAT_EXISTS.md"]] },

      { id: "normal-year", q: () => "Not every year is a drought. Is it any use in a normal year?",
        a: (F) => {
          const y = need(F.byYear.slice().sort((a, b) => a.share_fell - b.share_fell)[0]);
          return "Yes: even in the test year with the fewest falls (" + y.label + "), " + T(y.fell) + " of " + T(y.forecasts) + " October-to-March forecasts were followed by a drop below a third within " +
            need(F.horizon) + " days.";
        },
        more: (F) => P("When every dam looks fine for at least " + need(D.text.OK_DAYS) + " days, the text says so in one line. The dams that matter in a normal year are the ones heading down: the text names them."),
        check: [["The numbers behind Proof", "app/data/real/proof.json"]] },
    ] },

    { id: "works", title: "Does it work", items: [
      { id: "how-tested", q: () => "How do you know it works?",
        a: (F) => "We wrote the tests and pass marks before the build began, made forecasts for ten years using only data from before " + need(F.cutoffWords) +
          ", and checked each one against what the dam really did: the cautious days held " + T(f().inThousand(need(F.allYears).floor_held)) + " times in 1,000.",
        more: () => P("Those are years it never trained on, but we had looked at them in research before the event, so they may flatter it slightly. The clean test is the unseen exam."),
        nums: (F) => P(T(need(F.test).forecasts) + " October-to-March forecasts on " + T(F.test.dams) + " dam-sized waterbodies, mostly farm dams: " +
          need(F.test.skill_vs_usual_rate.words) + " less error than guessing the usual rate for that region and month. " + T(F.test.fell) + " of them were followed by a fall below a third within " + need(F.horizon) + " days."),
        go: () => [["#proof", "Proof: what we said against what happened"], ["#proof/exam", "The unseen exam"]],
        check: [["The test results", "artifacts/test_results.md"], ["The scorecard", "docs/SCORECARD.md"]] },

      { id: "accuracy", q: () => "How accurate is it, and which number is the accuracy number?",
        a: (F) => "The accuracy number is \"" + need(F.test).skill_vs_usual_rate.words + " less error than the usual guess\", where the usual guess is the usual rate for that region and month, measured over ten years it never trained on.",
        more: (F) => P("Error here is how far each chance was from what happened (1 if the dam dropped below a third within 90 days, 0 if not). The pass mark, written down before the build began, was a tenth less error.") +
          (F.dev && F.dev.runway && F.dev.runway.auc ? P("Shown one dam that fell below a third and one that did not, it gave the higher chance to the right one about " +
          tenOf(F.dev.runway.auc.value) + " times in 10.") : ""),
        nums: (F) => P(T(F.test.forecasts) + " October-to-March forecasts, " + T(F.test.dams) + " dam-sized waterbodies, " + T(F.test.fell) + " falls below a third."),
        go: () => [["#about/specialists", "Every score with its range, for specialists"]],
        check: [["The test results", "artifacts/test_results.md"]] },

      { id: "said-vs-happened", q: () => "When it says \"3 in 10\", do about 3 in 10 dams really drop below a third?",
        a: (F) => "Yes, on the ten test years: " + need(F.proof.calibration.takeaway).replace(/^When/, "when"),
        more: () => P("There is a slight lean: low chances could be a touch lower, and high ones a touch higher."),
        nums: (F) => table(["We said", "Forecasts", "Fell below a third", "How often"],
          need(F.bins.filter((b) => b.plotted).length ? F.bins.filter((b) => b.plotted) : null).map((b) => [b.said, T(b.forecasts), T(b.fell), CH(b.fell / b.forecasts)])),
        go: () => [["#proof/said", "The picture: what we said vs what happened"]],
        check: [["The numbers behind Proof", "app/data/real/proof.json"]] },

      { id: "unseen-exam", q: () => "What is the unseen exam, and how did it go?",
        a: (F) => {
          const p = need(F.sealed);
          if (p.status === "scored" && p.runway && p.runway.skill_vs_usual_rate) {
            // the cautious days, on target or not by the one rule of Proof's exam card and About (format.floorCheck)
            const fc = f().floorCheck(p.floor, F.proof);
            const floor = fc ? "; the cautious days held " + T(f().inThousand(p.floor.held)) + " times in 1,000" + againstTarget(fc) : "";
            const marks = f().passMarks ? f().passMarks(p) : null;
            const met = marks ? " " + marks.sentence : "";
            // one rule with the first screen and Proof: a gain whose range reaches zero is "no clear gain"
            return "On the unseen exam, a third farming region kept aside for one final check (" + (p.label || "the locked region") + "): " + f().examSkillWords(p.runway.skill_vs_usual_rate) + floor + "." + met;
          }
          return "A third farming region (" + (p.label || "the locked region") + ") whose satellite data we downloaded and fingerprinted before the event and then never opened or used, kept aside for one final check; it is opened once, on camera, on Sun 4 Oct, and its score is published whatever it is.";
        },
        more: (F) => {
          const e = F.exam || {};
          const st = f().examStatus ? f().examStatus(F.sealed) : null;   // never a promised time
          const heading = st ? st.heading : null;
          return (heading ? '<p class="faq-status">' + icon("i-lock", "sm") + esc(heading) + "</p>" : "") +
            (e.expect ? P(String(e.expect).replace(/\s*\(skill[^)]*\)/i, "")) : "");
        },
        go: () => [["#proof/exam", "The exam card in Proof"], ["#about/specialists", "Every number, for specialists"]],
        check: [["How the unseen exam is opened", "docs/SEALED_OPENING.md"], ["The locked files' fingerprints", "SEALED_HASHES.csv"]] },

      { id: "really-unseen", q: () => "Were those ten test years really unseen?",
        a: (F) => "Not fully, so we call them \"years it never trained on\", never \"unseen\": the model learned only from data before " + need(F.cutoffWords) + ", but we looked at those years in research before the event.",
        more: (F) => P(need(F.test.caveat)),
        check: [["What we disclosed", "DISCLOSURE.md"], ["The test plan", "PREREG.md"]] },

      { id: "how-often-wrong", q: () => "How often is it wrong?",
        a: (F) => "When it gave " + F.likelyInTen + " in 10 or more (\"likely\"), the dam fell below a third within " + need(F.horizon) + " days " + T(need(F.likely).fell) + " times out of " +
          T(F.likely.forecasts) + ", about " + tenOf(F.likely.fell / F.likely.forecasts) + " in 10, so about " + (10 - tenOf(F.likely.fell / F.likely.forecasts)) + " in 10 \"likely\" calls did not fall.",
        more: (F) => P("Of the " + T(need(F.lowBin).forecasts) + " forecasts that said less than 1 in 10, only " + T(F.lowBin.fell) + " fell. That is how honest chances behave, which is why DamDays gives a cautious days number and a chance, not a yes or no."),
        check: [["Our record, dam by dam", "artifacts/track_record.md"], ["The numbers behind Proof", "app/data/real/proof.json"]] },

      { id: "own-dam", q: () => "How can a farmer judge the accuracy for themselves?",
        a: (F) => "On their own dam: each dam's card shows our record on that dam over " + need(F.trLabel) + ", how often its days-left number held, poor records included.",
        more: () => P((D.text.TRACK_RECORD_HOW || "") + " When a dam's record is under 9 in 10, its card says to give the days extra margin."),
        nums: (F) => P(need(F.hero).name + " on " + F.farmShort + ": " + f().held(need(F.heroRec).held, F.heroRec.judged) + ".") +
          P("The typical dam held " + T(need(F.dist).median_in_1000) + " times in 1,000; " + T(F.dist.dams_below_9_in_10) + " of the " + T(F.dist.dams_with_record) +
            " dams with a record held less than 9 times in 10, and " + T(F.dist.dams_below_8_in_10) + " less than 8 times in 10.") +
          (F.farmRec && F.farmRec.lowest ? P(F.farmShort + "'s lowest: " + F.farmRec.lowest.name + ", " + f().held(F.farmRec.lowest.held, F.farmRec.lowest.judged) + ".") : ""),
        go: (F) => [["#farm/dam-" + F.hero.number + "/record", F.hero.name + "'s record, season by season"]],
        check: [["Our record, dam by dam", "artifacts/track_record.md"]] },

      { id: "misses", q: () => "What happens when the cautious promise misses?",
        a: () => "A miss means the dam dropped below a third of its usual full surface sooner than the text said; it does not mean the dam was empty.",
        more: () => P("DamDays is not advice: use it alongside your own eyes on the dam. We have not measured how many days short the misses fall, or any harm to stock, and terms of use are not written yet.") },

      { id: "dry-years", q: () => "Does it under-warn in drier years, when farmers need it most?",
        a: (F) => {
          const under = need(F.byYear.filter((y) => y.drier && y.share_fell > y.mean_chance).sort((a, b) => (b.share_fell - b.mean_chance) - (a.share_fell - a.mean_chance))[0]);
          return "A little, and we publish it: in " + under.label + " it expected " + f().inThousand(under.mean_chance) + " of every 1,000 forecast dams to fall below a third, and " +
            f().inThousand(under.share_fell) + " did.";
        },
        more: (F) => {
          const w = F.allYears && F.allYears.floor_worst;
          // "only" and "below" by the one on-target rule (format.floorCheck), as on Proof and About
          const wc = w ? f().floorCheck({ held: w.coverage, target: need(F.floorTarget) }, F.proof) : null;
          return (w ? P("In one year (" + seasonLabel(w.year) + ") the days-left count held " + (wc.below ? "only " : "") + f().inThousand(w.coverage) +
            " times in 1,000" + againstTarget(wc) + ".") : "") +
            P("This week's forecasts come from a refit that learned from every year up to " + (F.through ? monthYear(F.through) : "the latest look") + ", including the recent drier ones. Dams with a weak record say so on their card, but the weekly text doesn't carry that warning yet.");
        },
        nums: (F) => table(["July to June", "Expected to fall, in 1,000", "Did fall, in 1,000"],
          F.byYear.map((y) => [y.label + (y.drier ? " (drier)" : ""), T(f().inThousand(y.mean_chance)), T(f().inThousand(y.share_fell))])),
        check: [["The test results", "artifacts/test_results.md"], ["The numbers behind Proof", "app/data/real/proof.json"]] },
    ] },

    { id: "satellites", title: "What the satellites see", items: [
      { id: "how-see", q: () => "Dams differ in size and depth. How can a satellite tell how much water is in one?",
        a: () => "It can't measure litres: each look shows how much of a dam's outline is wet, and \"% full\" compares that with the same dam's own usual full wet surface, so a big dam and a small one are each measured against themselves.",
        more: (F) => P("Depth stays unknown, but a dam's shape shows up in its record: how fast its wet surface shrinks in a dry summer, and how it refills after rain. The forecasts read that history, dam by dam" +
          (F.years ? " (" + F.years + " years of it)" : "") + ", so a dam that usually shrinks fast tends to get fewer days.") +
          P("What we can't do is turn the days into litres, or into a mob's drinking days, without the dam's depth. DamDays doesn't replace walking down to the dam; it tells the farmer which dam to check before the others."),
        check: [["The data", "docs/DATA.md"]] },

      { id: "over-100", q: () => "How can a dam be more than 100% full?",
        a: () => "\"Usual full\" is the wet area the dam reached or beat in 1 of every 10 clear looks before 2016, not the brim, so after a wet spell a dam can read above it; the text writes anything at 100% or more as \"full\".",
        nums: (F) => P("For example, " + need(F.over100).farm.name + "'s " + F.over100.dam.name + " was ~" + F.over100.dam.level_pct + "% full at its " + S(F.over100.dam.issued_on) +
          " look: " + F.over100.where + " \"" + F.over100.dam.name + " full\"."),
        check: [["How the weekly text is written", "notify/MESSAGE_SPEC.md"]] },

      { id: "third-line", q: () => "Is the line really a third? In litres, isn't that already late?",
        a: (F) => "Strictly, the line is below " + need(F.thresholdPct) + "% of the dam's usual full wet surface, confirmed by a second clear look; \"a third\" is our plain rounding.",
        more: () => P("In a bowl-shaped dam that much surface holds well under a third of the water, so treat the line as a warning light, not a safe level. The days can't be turned into litres, or a mob's drinking days, without the dam's depth, which we don't have."),
        check: [["How the weekly text is written", "notify/MESSAGE_SPEC.md"], ["The data", "docs/DATA.md"]] },

      { id: "old-look", q: (F) => "Why does a text dated " + S(need(F.textDate)) + " use a satellite look from " + S(need(F.hero).issued_on) + "?",
        a: (F) => "The satellite data in this build ends on " + L(need(F.through)) + ", so the " + DS(F.textDate) + " text starts from each dam's last clear look. The count is then shifted to start on the day of the text, so the last day it covers does not change.",
        nums: (F) => P(F.hero.name + ": " + F.hero.damdays_days + " days from " + S(F.hero.issued_on) + " is " + F.hero.days_left + " days from " + S(F.textDate) + "; both end on " + S(need(F.heroDay)) + "."),
        more: () => P("A dam with no recent clear look gets \"no clear satellite look lately\" and no forecast. Automatic weekly updates are not built yet; we refit by hand."),
        check: [["How the weekly text is written", "notify/MESSAGE_SPEC.md"], ["What we disclosed", "DISCLOSURE.md"]] },

      { id: "no-water-seen", q: (F) => "The text says \"" + need(F.noWater).name + ": no water seen\". What does that mean?",
        a: (F) => "The satellite saw no water in " + F.noWater.name + "'s outline at its last clear look, on " + L(need(F.noWater.issued_on)) + "; that is why the text says \"no water seen\" and nothing stronger.",
        more: () => P("A small pool, or muddy or green water, can be missed, and one look can be wrong: the next clear look will tell. Nobody has checked this dam on the ground for us."),
        go: (F) => [["#farm/dam-" + F.noWater.number, "Open " + F.noWater.name]] },

      { id: "small-dams", q: () => "Aren't you missing the small paddock dams?",
        a: (F) => "Yes: the satellites see only dams with about " + need(F.minHa) + " ha of water or more, and most farm dams are smaller than that.",
        more: (F) => P("The bigger dams aren't safe bets either: at the latest looks (to " + L(need(F.through)) + "), " + T(need(F.counts).low) + " of the " + T(F.counts.dams) +
          " dam-sized waterbodies we track in " + need(F.region) + ", mostly farm dams, were already below a third."),
        go: () => [["#runway", "Runway: the region map"]],
        check: [["Who it is for", "docs/TARGET_FARMER.md"]] },

      { id: "all-dams", q: (F) => "Are the " + T(need(F.counts).dams) + " dams all the farm dams in " + need(F.region) + "?",
        a: (F) => "No: they are the dam-sized waterbodies (" + need(F.size) + ") in our study area that are compact and usually hold water, mostly farm dams; the region has far more farm dams, most of them too small for the satellites.",
        more: () => P("The filter that picks them is not perfect: it also catches some town and industrial ponds. We checked the demo farms against aerial photos, and About's honest limits say what we found."),
        go: () => [["#about", "About: honest limits"]],
        check: [["The data", "docs/DATA.md"]] },

      { id: "circle", q: () => "Is a \"farm\" my property, or a circle that picks up my neighbour's dams?",
        a: (F) => "Today a farm is a homestead point plus every dam the satellites can see within " + need(F.radiusKm) + " km (" + T(Math.round(Math.PI * F.radiusKm * F.radiusKm * 100)) +
          " ha), because the data has no property boundaries, so the circle can take in a neighbour's dams.",
        more: (F) => P("In the app you can move the point and change the circle. The demo farms sit on dense clusters (" + need(F.damRange)[0] + " to " + F.damRange[1] + " dams in the circle), so they are the best case; a typical farm would see far fewer."),
        go: () => [["#farm/setup", "Change the homestead or the circle"]] },

      { id: "stock", q: () => "If I move my mob or double the stock on a dam, do the days change?",
        a: () => "Not straight away: DamDays doesn't know head count, pumping or carting, so a heavier draw shows up only once new clear looks see the dam dropping faster.",
        more: () => P("Each forecast reads how fast the level fell over the past few months. There is no way yet for a farmer to tell us stock numbers."),
        check: [["How it works", "docs/HOW_IT_WORKS.md"]] },

      { id: "no-days", q: (F) => "This week " + T(need(F.counts).quiet) + " of the " + T(F.counts.dams) + " dam-sized waterbodies we track get no days number. Doesn't it go quiet on the dams in trouble?",
        a: (F) => "No, the text names them: of the " + T(F.counts.quiet) + ", " + T(F.counts.low) + " are already below a third, " + T(F.counts.notRefilled) + " have not refilled to " + need(F.armPct) +
          "% full lately, and " + T(F.counts.noLook) + " have had no recent clear look.",
        more: () => P("The text says \"already below 1/3\", \"no water seen\", \"no forecast until it refills\" or \"no clear satellite look lately\". On a farm with many dams, some of these lines can be cut to fit one text (the dams with no forecast go first): the text then ends \"Reply MAP for N more dams\", and the app lists every dam. And we don't yet count days for a dam that is already low: a real gap."),
        go: () => [["#runway", "See them on Runway"]] },
    ] },

    { id: "climate", title: "Climate, and keeping up", items: [
      { id: "cop31", q: () => "Which COP31 priority does it serve?",
        a: () => "Awareness Across All Areas: it helps farmers adapt to a changing climate by showing, dam by dam, how many days each dam has before it drops below a third, while there are still choices.",
        more: (F) => P("The Global Goal on Adaptation's framework (the UAE Framework for Global Climate Resilience) includes targets on water scarcity and climate-resilient farming. " +
          "DamDays gives a farm-by-farm measure of water security for dams big enough for the satellites to see (" + need(F.size) + "), from free public data, with nothing to install."),
        go: () => [["#about", "About: why it matters for COP31"]] },

      { id: "climate-change", q: () => "Climate change makes the past a poorer guide. Why trust a tool built on past weather?",
        a: (F) => "We don't assume the past repeats: each forecast starts from the dam's latest look and how fast it is dropping, and a model that learned only from data before " + need(F.cutoffWords) +
          " still had less error than the usual guess in every one of the next ten years, dry and wet.",
        more: (F) => {
          const wet = F.byYear.filter((y) => !y.drier), dry = F.byYear.filter((y) => y.drier);
          const high = wet.filter((y) => y.mean_chance > y.share_fell).length, low = dry.filter((y) => y.mean_chance < y.share_fell).length;
          return (F.proof && F.proof.by_year && F.proof.by_year.takeaway ? P(F.proof.by_year.takeaway) : "") +
            (wet.length ? P("Where the weather pushed its chances off, we show it: too high in " + high + " of the " + wet.length + " wetter years, and a little low in " + low + " of the " + dry.length + " drier ones.") : "") +
            P("It is tested only in south-eastern Australia, and no test can show how it will behave in a climate unlike anything in the " + (F.years ? F.years + "-year " : "") + "record.");
        },
        go: () => [["#proof/years", "Year after year, in Proof"]],
        check: [["The numbers behind Proof", "app/data/real/proof.json"], ["How it works", "docs/HOW_IT_WORKS.md"]] },

      { id: "refit", q: () => "Is it self-learning? Who refits it?",
        a: (F) => "No: we refit it by hand, using every answer known by the latest satellite look (the last refit used looks up to " + L(need(F.through)) + ").",
        more: () => P("An automatic weekly refit, and a seasonal check of what it said against what happened, are planned but not built.") },

      { id: "this-week-tested", q: () => "Are this week's forecasts tested, or only the old ones?",
        a: (F) => "What we tested is the recipe: learn only from earlier data, then check once on the years after; this week's forecasts come from the same recipe, refit on everything known by the " + L(need(F.through)) + " look.",
        more: (F) => '<p>Their own answers start to arrive <span data-first-window' + (F.firstWindow ? ' data-filled="1">after ' + esc(L(F.firstWindow))
          : ">" + need(F.horizon) + " days after each forecast's satellite look") + "</span> (the " + need(F.horizon) +
          "-day chances); a log to score them as they arrive is not built yet.</p>",
        check: [["Our record, dam by dam", "artifacts/track_record.md"]] },
    ] },

    { id: "next", title: "What's new, and what's next", items: [
      { id: "whats-new", q: () => "What already exists, and what's new?",
        a: (F) => "Dam sensors, satellite maps of today's water, calculators and, in Africa, waterhole forecasts already exist; what's new is the combination: at least how many days each farm dam big enough for the satellites to see (" + need(F.size) + ") has before it drops below a third, with nothing to install or measure, tested against pass marks written before the build began, with each dam's own record, sent as one weekly text.",
        more: () => '<ul class="faq-list"><li>NSW reports the water in its waterbodies every month from the same satellite record, by parish, with no forecast.</li>' +
          "<li>Victorian tools give days of water, or a 12-month outlook for one dam, from the farmer's own measurements.</li><li>Dam sensors read today's level, one dam at a time.</li>" +
          "<li>In Africa, FEWS NET forecasts livestock water points a month ahead.</li></ul>" +
          P("Our search did not find the combination. It is built in two south-eastern regions so far."),
        check: [["What already exists", "docs/WHAT_EXISTS.md"]] },

      { id: "sensor", q: () => "Why not just fit a dam sensor?",
        a: () => "A sensor reads one dam's exact level right now, better than we can, but it has to be bought and fitted to each dam, often with a monthly fee; DamDays looks ahead, for every dam the satellites can see, with nothing to install.",
        more: (F) => P("DamDays sees only the wet surface, only on dams of " + need(F.size) + ", from a look that can be weeks old, but each dam comes with " + need(F.years) +
          " years of history from day one. A sensor reading could anchor the forecast; that is not built."),
        check: [["What already exists", "docs/WHAT_EXISTS.md"]] },

      { id: "data", q: () => "Where does the data come from, and what does it cost?",
        a: (F) => "Free public data: DEA Waterbodies from Geoscience Australia (the wet area of each waterbody, from Landsat since " + need(F.firstYear) + ") and SILO rainfall from the Queensland Government, both under CC BY 4.0.",
        more: () => P("The whole pipeline runs on a laptop. Street maps: OpenStreetMap contributors."),
        go: () => [["#about", "About: data and credits"]],
        check: [["The data", "docs/DATA.md"], ["DEA Waterbodies", "https://www.dea.ga.gov.au/"], ["SILO climate data", "https://www.longpaddock.qld.gov.au/silo/"]] },

      { id: "privacy", q: () => "Who sees my farm?",
        a: () => "Your homestead point stays on this phone and is never sent to us: no name, no sign-up.",
        more: () => P("A real service would hold only a homestead point, a circle size, an optional farm name and a phone number. The forecasts in this repository are listed by location, with no owner's name.") +
          P("Drought programmes and fire agencies would get what this repository already shows, dams by location, never a farmer's name, phone number or homestead point; the sharing rules are not written yet."),
        check: [["Who it is for", "docs/TARGET_FARMER.md"]] },

      { id: "difference", q: () => "What difference does it make, in numbers?",
        a: () => "None of it is measured yet: no real farmer has had a text, so fewer stock losses and less wasted feed are aims, not results.",
        more: () => P("We expect the value to come from timing the costly moves a failing dam forces, such as carting water or paying for grazing elsewhere. Trials with farmers, tracking how they act on the number, are how we would measure it. The first step is to talk to farmers and two drought programmes."),
        check: [["Who it is for", "docs/TARGET_FARMER.md"], ["The pitch", "docs/PITCH.md"]] },

      { id: "make-worse", q: () => "Could it make things worse, for example by encouraging a farmer to hang on?",
        a: () => "It could, and only a trial with farmers can show which way it goes; the design leans toward acting early.",
        more: (F) => '<ul class="faq-list"><li>The days are a cautious floor that warns at a third, not at empty.</li>' +
          "<li>A \"likely\" chance is followed by a fall about " + tenOf(need(F.likely).fell / F.likely.forecasts) + " times in 10, so about " + (10 - tenOf(F.likely.fell / F.likely.forecasts)) + " times in 10 it is not.</li>" +
          "<li>Every dam shows its own record.</li><li>It is not advice.</li></ul>" +
          P("We would read a high chance as a cue for cheaper moves that are easier to undo, not for selling breeding stock on one text.") },

      { id: "why-now", q: () => "Why now?",
        a: (F) => "The satellite data isn't new; what's missing is a tested look ahead, dam by dam, and the need is current: at the latest looks (to " + L(need(F.through)) + "), " + T(need(F.counts).low) +
          " of the " + T(F.counts.dams) + " dam-sized waterbodies we track in " + need(F.region) + ", mostly farm dams, were already below a third.",
        more: () => P("The whole thing runs on a laptop from free public data."),
        go: () => [["#runway", "Where water is running short"]] },

      { id: "feed", q: () => "Feed often runs out before water. Why focus on water?",
        a: () => "Water shouldn't drive the decision alone: DamDays sits beside the feed budget and the farmer's own eyes on the dam, and it warns at a third, not at empty.",
        more: () => P("It doesn't forecast feed (pasture tools do), and it can't see algae, salt or boggy edges, only how much of the surface is wet. We haven't tested with farmers which runs out sooner.") },

      { id: "left-out", q: () => "Who is left out?",
        a: (F) => "Farms with no dam of about " + need(F.minHa) + " ha of water or more, bore-fed farms, and anywhere outside the regions where we tested it.",
        more: () => P("Small and hobby blocks are probably hit hardest, though we have not measured it, and mobile coverage on farms hasn't been researched.") },

      { id: "next", q: () => "What's next?",
        a: () => "A real text service with opt-in and STOP, weekly refits, more regions, and trials with farmers.",
        more: () => P("Each new region needs its own test before it gets texts."),
        check: [["The pitch", "docs/PITCH.md"]] },
    ] },

    { id: "pays", title: "Who pays, and who it is for", items: [
      { id: "who-pays", q: () => "Who are your customers, and who pays?",
        a: () => "Farmers first, as the users; then drought support programmes and agencies, fire agencies, and farm software platforms and dam-sensor companies as partners, with rural lenders and insurers later.",
        more: () => customersHtml() + P(HONEST) +
          P("It needs no hardware and runs on a laptop from free public data; refits are run by hand today. Paying customers are what would keep it running into the next drought."),
        go: () => [["#runway", "Runway: the district view"]] },

      { id: "who-else", q: () => "Who else could use dam forecasts?",
        a: () => "Beyond farmers: drought support programmes and agencies, to see where stock water runs short first; fire agencies, to know before fire season which farm dams crews and aircraft can still refill from; and farm software platforms and dam-sensor companies, as partners.",
        more: (F) => P("Runway, the region map, is the start of the district view: every dam we track in " + (F.region || "the region") + ", coloured by its chance of dropping below a third within 90 days. A view added up by district, and a view for fire agencies, are not built yet.") +
          P("A season-ahead outlook for small areas, first built with lenders in mind, is built and tested, and set aside to keep the focus on farmers. " + HONEST),
        go: () => [["#questions/who-pays", "Who pays: our customers, in order"], ["#outlook", "The Area outlook (set aside)"]] },

      { id: "audience", q: () => "Who is the one audience?",
        a: () => "The family grazier whose stock drink from dams: they are the users, and we start with them, as a mentor advised; drought programmes, fire agencies and farm platforms come next, as customers and partners.",
        more: () => P("For drought programmes, the district view starts from Runway, the region map. The Area outlook for small areas is built but set aside to focus on farmers. " + HONEST),
        go: () => [["#questions/who-pays", "Who pays: our customers, in order"], ["#runway", "Runway"]] },

      { id: "also-built", q: () => "What else did you build?",
        a: (F) => "Runway, a map of every dam we track in the region; Rewind, a replay of the " + need(F.rewindSeason) + " drought; and the Area outlook, a season-ahead outlook for small areas, set aside to focus on farmers.",
        go: () => [["#runway", "Runway"], ["#proof/rewind", "Rewind"], ["#outlook", "Area outlook"]] },

      { id: "install", q: () => "Can I put it on my phone?",
        a: () => "Yes: add it to your home screen and it opens like an app.",
        more: () => installSteps(),
        go: () => [["#more/install", "Put DamDays on your home screen"]] },
    ] },

    { id: "technical", title: "For the technical reader", items: [
      { id: "why-nine", q: () => "Is \"at least N days\" useful, or just short? And why 9 in 10?",
        a: () => "It is a deliberately cautious floor, not a best guess, and the app shows the chance and the next six months beside it.",
        more: (F) => {
          const w = need(F.allYears).floor_worst;
          // on target or not by the one rule (format.floorCheck, proof.json's tolerance), as on Proof and About
          const all = f().floorCheck({ held: F.allYears.floor_held, target: need(F.floorTarget) }, F.proof);
          const wc = f().floorCheck({ held: w.coverage, target: F.floorTarget }, F.proof);
          return P("Across all forecasts it held " + f().inThousand(F.allYears.floor_held) + " times in 1,000" + (all.verdict ? ", " + all.verdict : "") +
            "; its worst year was " + seasonLabel(w.year) + " at " + f().inThousand(w.coverage) + againstTarget(wc) + ".") +
            P("The 9 in 10 is a statistical target written into the test plan before the build began; it was not set from what acting early or late costs a farmer. We have not yet measured how far past the floor dams usually last.") +
            (F.heroRec && F.heroRec.median_days ? P(F.hero.name + " on " + F.farmShort + ": its typical promise was at least " + F.heroRec.median_days + " days.") : "");
        },
        check: [["The test results", "artifacts/test_results.md"], ["The test plan", "PREREG.md"]] },

      { id: "baseline", q: () => "Is \"the usual guess\" a weak baseline?",
        a: (F) => {
          const own = need(F.dev && F.dev.runway && F.dev.runway.skill_vs_own_record);
          return "It is the easy yardstick, so we also report two harder ones: against each dam's own past rate it has " + f().fractionWords(own.value) +
            " less error, and against our own simpler benchmark model it is only a little better, but reliably so.";
        },
        go: () => [["#about/specialists", "The exact scores, for specialists"]],
        check: [["The test results", "artifacts/test_results.md"]] },

      { id: "rank-vs-time", q: () => "Can it tell whether my dam drops this year or next, or does it only rank dams?",
        a: () => "Our season-ahead test says it is much better at picking which dams run short soonest in a given summer than at timing one dam's drier years.",
        more: () => P("Within one dam's own history, the season outlook was barely better than a coin toss, and the 90-day forecast's within-dam score has not been computed. If its strength is ranking dams across a district, that suits the district view we plan for drought programmes, which starts from Runway, the region map."),
        go: () => [["#about/specialists", "The scores, for specialists"]],
        check: [["The season outlook check", "artifacts/season_rating_val.md"]] },

      { id: "independent", q: (F) => T(need(F.test).forecasts) + " forecasts sounds like a lot. How many independent droughts did you test on?",
        a: (F) => "Far fewer than the count suggests: forecasts a week or two apart on one dam share a dry spell, and a dry year hits every dam in a region at once, so the forecasts rest on " +
          need(F.dev && F.dev.band).region_years + " region-years and only a few dry spells.",
        more: (F) => {
          const rec = F.heroRec;
          let line = "";
          if (rec && rec.by_season) {
            const seasons = Object.keys(rec.by_season);
            const missed = seasons.filter((y) => rec.by_season[y][0] < rec.by_season[y][1]).length;
            line = " " + F.hero.name + " on " + F.farmShort + ": its " + T(rec.judged - rec.held) + " misses came in " + missed + " of its " + seasons.length + " seasons.";
          }
          return P("That is why our ranges re-draw whole region-years as well as whole dams, and why the unseen exam matters." + line);
        },
        check: [["The scorecard", "docs/SCORECARD.md"], ["Our record, dam by dam", "artifacts/track_record.md"]] },

      { id: "dropped-views", q: () => "Did you leave out the views that looked bad?",
        a: () => "No: the replay and the dam-by-dam view stay in the app, inside Proof, whatever they show.",
        more: (F) => P(need(F.damByDam).all_dates_takeaway || F.damByDam.takeaway) +
          P(((String(F.damByDam.how_chosen || "").match(/We picked[^.]*\./) || [""])[0])),
        go: () => [["#proof/rewind", "Rewind: the 2018-19 drought"], ["#proof/dams", "Dam by dam"]] },

      { id: "correction", q: () => "Does the per-dam correction help?",
        a: () => "Only a little: it nudges a dam's chance when the dam has run wetter or drier than similar dams, and it moves only the chance, not the days.",
        more: (F) => P("It counts a dam's whole history equally, so it is slow to notice a dam that has changed.") +
          (F.noteDam ? P("For example, " + F.noteDam.name + " on " + F.farmShort + ": \"" + F.noteText + "\"") : ""),
        check: [["The correction check", "artifacts/tree_frailty_val.md"]] },

      { id: "band", q: () => "What is the \"wetter or drier season\" range, and what if the climate moves outside it?",
        a: () => "It is a warning range shown beside each chance, built from earlier years; it never changes the forecast itself.",
        more: (F) => P("On the test years it covered " + need(F.dev && F.dev.band).covered + " of " + F.dev.band.region_years + " region-years, but we chose its final design after seeing some of those years, and we say so. Refreshing it each year is not built."),
        nums: (F) => P(need(F.hero).name + ": " + CH(F.hero.chance) + " by " + S(F.hero.window_end) + "; in a wetter or drier season, " +
          f().chanceRange(need(F.heroRow).chance_low, F.heroRow.chance_high) + "."),
        check: [["The test results", "artifacts/test_results.md"]] },

      { id: "as-received", q: () => "Did you test the number as a farmer would receive it?",
        a: () => "Partly: each test forecast uses only data dated before it, and we checked this by deleting everything after a cut-off date and rebuilding. But the dam outlines and rainfall we used are today's versions, which may have been tidied since.",
        more: () => P("Satellite looks also reach the public some days after the picture is taken. We have not recounted how often the promise held for texts as they would really have been sent, allowing for that."),
        check: [["The look-ahead check", "artifacts/lookahead_test.json"], ["The addendum to the test plan", "PREREG_ADDENDUM_1.md"]] },
    ] },

    { id: "fair", title: "A fair test", items: [
      { id: "who-built", q: () => "Who built it, and how much did AI write?",
        a: () => "We wrote the code in this repository during the event, with an AI coding assistant (Claude Code) generating code under our direction; every commit carries its co-author line.",
        more: () => P("We have not measured what share of the code it wrote. Before the event, as a hackathon mentor confirmed was allowed, we downloaded the public data, and AI research agents did the problem research and settled the design; none of that research code is in this repository."),
        check: [["What we disclosed", "DISCLOSURE.md"], ["The build log", "BUILD_LOG.md"]] },

      { id: "pass-marks-public", q: () => "Can I check on GitHub that the pass marks were public before the build began?",
        a: () => "Yes: the opening commit holds only the test plan with its pass marks, the locked region's fingerprints, the disclosure and a short README, and neither the plan nor the fingerprint list has been edited since.",
        more: () => P("Commit times come from our own computer, so GitHub's own record of each push is the outside check."),
        check: [["The commit history", COMMITS], ["The test plan", "PREREG.md"], ["The locked files' fingerprints", "SEALED_HASHES.csv"]] },

      { id: "believe-result", q: () => "You locked the unseen exam, opened it and marked it. Why should we believe the result?",
        a: () => "Everything that decides the mark was on GitHub before the opening: the locked files' fingerprints, the pass marks, the fingerprints of the models being marked, and their code.",
        more: () => P("The opening script refuses to run if the fingerprint list was edited, if any locked file or marked model differs, or if the repository is not clean and pushed. It scores once, on camera, and the raw results are pushed unedited. If a mark fails, we publish the fail and change nothing."),
        check: [["How the unseen exam is opened", "docs/SEALED_OPENING.md"]] },

      { id: "hard-to-fail", q: () => "Is the pass mark hard enough to fail?",
        a: () => "The main accuracy pass mark sits below what we predicted, and the honest-chances mark is a closer call; we also wrote down the ranges we expect, and missing one is published too.",
        more: (F) => (F.exam && F.exam.expect ? P(String(F.exam.expect).replace(/\s*\(skill[^)]*\)/i, "")) : ""),
        go: () => [["#about/specialists", "The pass marks and ranges, for specialists"]],
        check: [["The test plan", "PREREG.md"]] },

      { id: "peek", q: () => "Fingerprints prove the locked files didn't change, not that nobody looked. How do you know the locked region was never read?",
        a: () => "Fingerprints can't prove that; what protects the result is that the fingerprints of the models being marked were pushed on Friday evening (2 Oct), the opening refuses any other model, and no forecasting or scoring code has changed since.",
        more: () => P("Our build log records one slip: on Saturday morning an AI agent helping us ran a text search over our research folder, which also holds the locked files. It was stopped after about 2 minutes, printed no matches, and no locked contents were seen; the opening script re-checks every file's fingerprint before it opens anything. A text search does scan files, so we say so."),
        check: [["The build log", "BUILD_LOG.md"]] },

      { id: "reproduce", q: () => "Can I reproduce the results?",
        a: () => "Yes, with the public data: download it yourself (it is not in the repository) and the steps rebuild the numbers on a laptop, though refitted models may not match ours byte for byte.",
        more: () => P("Without the data, a fresh copy still runs the code checks, skipping the ones that need data."),
        check: [["How to reproduce it", "README.md"]] },

      { id: "feedback", q: () => "What did you change because of feedback?",
        a: () => "Mentors changed the product and the story, not the model: the weekly text became the product, \"%\" now means only how full a dam is, and chances read \"3 in 10\".",
        more: () => P("They asked us to explain the testing plainly, with pictures: so the app gained a Proof view and each dam's own record. They asked for one audience, described precisely: so the pitch is for family graziers. And they asked the questions on this page: the problem in one sentence, the COP31 priority, which farms, what already exists and what's new, who else could use it, how a satellite can tell how much water a dam holds, and how a farmer can judge the accuracy.") +
          P("So we now name our customers in order: farmers first, then drought programmes, fire agencies, and farm platforms and dam-sensor companies as partners.") +
          P("Through all of it, the forecasting code stayed locked: not one change."),
        check: [["The build log", "BUILD_LOG.md"]] },
    ] },
  ];

  // =====================================================================
  // The page
  // =====================================================================
  // Each answer's HTML, put into the page the first time it opens (or when the search needs its words): the
  // page then paints only the questions, a shorter first task on a slow phone. id -> HTML of .faq-a.
  const answers = new Map();

  function itemHtml(def, F) {
    try {
      const q = def.q(F);
      const a = def.a(F);
      const more = def.more ? def.more(F) : "";
      const nums = def.nums ? def.nums(F) : "";
      const goes = def.go ? def.go(F) : null;
      answers.set(def.id, '<p class="faq-quote">' + esc(a) + "</p>" + more +
        (goes && goes.length ? go(goes) : "") +
        (nums || def.check ? '<div class="faq-deeper">' + (nums ? numbers(nums) : "") + check(def.check) + "</div>" : ""));
      return '<details class="faq" id="q-' + def.id + '" data-q="' + def.id + '"><summary><span class="faq-q">' + esc(q) + "</span>" + icon("i-plus", "plus") +
        '</summary><div class="faq-a" data-empty="1"></div></details>';
    } catch (e) {
      return "";   // this dataset lacks a number the answer needs: leave the question out
    }
  }

  /** Put an answer's body in, once. */
  function fillAnswer(d) {
    const body = d && d.querySelector(".faq-a[data-empty]");
    if (!body) return;
    body.innerHTML = answers.get(d.dataset.q) || "";
    body.removeAttribute("data-empty");
  }

  function whoElseHtml() {
    return '<section class="slot-who-else" data-optional="who-else" aria-labelledby="q-who-else-h">' + icon("i-leaf", "who-icon") +
      '<div><span class="tag">Named, not yet approached</span><h2 class="card-title" id="q-who-else-h">Who will use it, and who pays?</h2>' +
      "<p>Farmers first. Then drought support programmes and agencies, fire agencies, and farm software platforms and dam-sensor companies as partners; rural lenders and insurers later. " + esc(HONEST) + " <a href=\"#questions/who-pays\">More</a></p></div></section>";
  }

  function pageHtml(F, route) {
    const groups = GROUPS.map((g) => {
      const items = g.items.map((def) => itemHtml(def, F)).filter(Boolean);
      return items.length ? { g, html: items.join(""), n: items.length } : null;
    }).filter(Boolean);
    const total = groups.reduce((s, x) => s + x.n, 0);
    const whoElse = !(route && route.params && route.params.whoelse === "0");
    return '<div class="wrap page-narrow faq-page">' +
      '<header class="page-head"><p class="eyebrow">Questions</p><h1 id="questions-h1">Questions people ask</h1>' +
      "<p>Short answers, each with the numbers and where to check them. Start here: " +
      [["problem", "What it is"], ["accuracy", "How accurate"], ["unseen-exam", "The unseen exam"], ["how-see", "How a satellite sees water"], ["who-for", "Which farms"]]
        .map((x) => '<a href="#questions/' + x[0] + '">' + x[1] + "</a>").join(" · ") + ".</p></header>" +
      '<aside class="faq-know" aria-labelledby="faq-know-h"><h2 class="card-title" id="faq-know-h">Three things to know</h2><ul>' +
      "<li><b>\"% full\"</b> is the share of a dam's usual full water surface that the satellite sees wet. Not depth or litres; \"%\" never means a chance.</li>" +
      "<li><b>Chances</b> are written \"3 in 10\".</li>" +
      "<li><b>\"Held\"</b> means the dam really stayed above a third for at least the days given. The days-left number is built to hold 9 times in 10: in 9 of every 10 past cases it did, and most dams lasted well beyond the number.</li></ul></aside>" +
      '<div class="faq-tools"><label class="faq-search"><span class="vh">Find a question</span>' + icon("i-q") +
      '<input type="search" id="faq-search" placeholder="Find a question" autocomplete="off" enterkeyhint="search"></label>' +
      '<p class="faq-count small" id="faq-count" aria-live="polite">' + total + " questions</p></div>" +
      '<nav class="faq-groups" aria-label="Question groups">' + groups.map((x) =>
        '<button type="button" class="chip faq-chip" data-group="faq-g-' + x.g.id + '">' + esc(x.g.title) + "</button>").join("") + "</nav>" +
      groups.map((x) => '<section class="faq-group" id="faq-g-' + x.g.id + '" aria-labelledby="faq-gh-' + x.g.id + '"><h2 class="faq-group-h" id="faq-gh-' + x.g.id + '">' +
        esc(x.g.title) + '</h2><div class="faq-list-items">' + x.html + "</div></section>").join("") +
      '<p class="faq-none" id="faq-none" hidden>No question matches. Try another word, or <button type="button" class="linkbtn" data-clear>show every question</button>.</p>' +
      (whoElse ? whoElseHtml() : "") +
      "</div>";
  }

  // ---- search ----
  function applySearch(text) {
    const words = String(text || "").toLowerCase().split(/\s+/).filter(Boolean);
    if (words.length) root.querySelectorAll("details.faq").forEach(fillAnswer);   // the search reads every answer's words
    let shown = 0;
    root.querySelectorAll(".faq-group").forEach((group) => {
      let inGroup = 0;
      group.querySelectorAll("details.faq").forEach((d) => {
        if (words.length && !d.dataset.text) d.dataset.text = d.textContent.toLowerCase();
        const ok = !words.length || words.every((w) => d.dataset.text.indexOf(w) >= 0);
        d.hidden = !ok;
        if (ok) inGroup += 1;
      });
      group.hidden = inGroup === 0;
      shown += inGroup;
    });
    const count = root.querySelector("#faq-count");
    const none = root.querySelector("#faq-none");
    const total = root.querySelectorAll("details.faq").length;
    if (count) count.textContent = words.length ? shown + " of " + total + " questions match" : total + " questions";
    if (none) none.hidden = shown > 0;
    root.querySelectorAll(".faq-chip").forEach((c) => {
      const g = root.querySelector("#" + c.dataset.group);
      c.hidden = Boolean(g && g.hidden);
    });
  }

  // =====================================================================
  // Router
  // =====================================================================
  let root = null;
  let ready = false;

  function openOnly(id) {
    let target = null;
    root.querySelectorAll("details.faq").forEach((d) => {
      const on = d.dataset.q === id;
      if (on) { target = d; fillAnswer(d); }
      if (d.open !== on) d.open = on;
    });
    if (target) fillFirstWindow(target);
    return target;
  }

  function onClick(event) {
    const t = event.target;
    const summary = t.closest("summary");
    if (summary && summary.parentElement && summary.parentElement.classList.contains("faq")) {
      event.preventDefault();
      const d = summary.parentElement;
      const id = d.dataset.q;
      const route = D.router.current();
      if (d.open) {
        if (route && route.sub === id) D.router.up(); else d.open = false;
      } else {
        D.router.go("#questions/" + id);
      }
      return;
    }
    const chip = t.closest(".faq-chip");
    if (chip) {
      const g = root.querySelector("#" + chip.dataset.group);
      if (g) {
        const h = g.querySelector("h2");
        if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
        g.scrollIntoView({ block: "start", behavior: reduceMotion() ? "auto" : "smooth" });
      }
      return;
    }
    if (t.closest("[data-clear]")) {
      const input = root.querySelector("#faq-search");
      if (input) { input.value = ""; applySearch(""); input.focus(); }
    }
  }

  function reduceMotion() { return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); }

  function render(rootEl, route) {
    root = rootEl;
    return (D.data.need ? D.data.need("first") : D.data.load()).then((data) => {
      const F = buildFacts(data);
      answers.clear();
      root.innerHTML = pageHtml(F, route);
      ready = true;
      root.addEventListener("click", onClick);
      // an answer opened any other way (the browser's find in page) gets its body too
      root.addEventListener("toggle", (event) => {
        const d = event.target;
        if (d && d.matches && d.matches("details.faq") && d.open) fillAnswer(d);
      }, true);
      const input = root.querySelector("#faq-search");
      if (input) input.addEventListener("input", () => applySearch(input.value));
    });
  }

  function enter(route) {
    if (!ready) return;
    const id = route.sub;
    if (!id) { openOnly(null); return; }
    let target = openOnly(id);
    if (!target) { D.router.go("#questions", { replace: true }); return; }
    if (target.hidden) {
      const input = root.querySelector("#faq-search");
      if (input) input.value = "";
      applySearch("");
      target = openOnly(id);
    }
    setTimeout(() => target.scrollIntoView({ block: "start", behavior: "auto" }), 40);
  }

  D.questions = { ids: () => GROUPS.reduce((all, g) => all.concat(g.items.map((i) => i.id)), []) };
  if (D.router && typeof D.router.register === "function") {
    D.router.register("questions", { render, enter });
  }
})();
