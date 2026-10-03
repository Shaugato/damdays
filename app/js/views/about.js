/* views/about.js (WP-F)
 * About (#about, from More), UI_SPEC 3.8. Glance: how it works in five steps, a note on words, how we
 * checked it, honest limits, COP31, data and credits, the team. More: "Methods and scores, for
 * specialists" (#about/specialists), the only place in the app where the test scores keep their usual
 * names (skill, AUC, calibration slope, the benchmark G2, the model and its config hash), each with
 * plain words. Skill is worded as a fraction ("nearly a quarter less error"), never as a percent.
 *
 * panelHtml(panel) draws one test panel (the development regions, or the sealed region) and is also
 * used by Proof's exam card, so the sealed result reads the same in both places.
 * scripts/21_publish_sealed.py reads this file: keep it at this path, keep panelHtml, and keep the
 * words "Not clearly ahead of" (written when the sealed gain over the benchmark is not clearly above 0).
 *
 * Every number comes from the data (meta, scoreboard, proof, track_record, farms).
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.views.about = (function () {
  "use strict";

  const fmt = DamDays.format;
  const esc = (text) => DamDays.format.escapeHtml(text === null || text === undefined ? "" : text);

  // =====================================================================
  // Legacy hooks (the old About markup in index.html): still work if anything mounts it
  // =====================================================================
  /** Runs once, the first time the old view is shown. */
  function init(data) {
    const meta = data.meta;
    document.querySelectorAll('[data-fill="min-area"]').forEach((span) => {
      span.textContent = meta.min_dam_area_ha.toFixed(1);
    });
    const facts = document.getElementById("about-dataset");
    if (facts) facts.innerHTML = datasetFacts(data);
    const scores = document.getElementById("about-scores");
    if (scores) scores.innerHTML = scoresHtml(data.scoreboard);
  }

  /** Nothing to refresh: the page is static once filled. */
  function show() {}

  /** A short list: region, data, satellite looks up to, model, made on. */
  function datasetFacts(data) {
    const meta = data.meta;
    const facts = [
      ["Region", meta.region ? meta.region.name : "not stated"],
      ["Data", meta.is_mock ? "MOCK (made up, for testing the app)" : "Real forecasts"],
      ["Satellite looks up to", meta.data_through ? fmt.date(meta.data_through) : "not stated"],
      ["Model", meta.model ? meta.model.name + (meta.model.version ? " " + meta.model.version : "") +
        (meta.model.config_hash ? " (config " + meta.model.config_hash + ")" : "") : "not stated"],
      ["Made on", meta.generated_at ? fmt.dateTime(meta.generated_at) : "not stated"],
    ];
    if (meta.coverage && meta.coverage.dams) facts.splice(1, 0, ["Dams tracked", fmt.thousands(meta.coverage.dams) + " dam-sized waterbodies, mostly farm dams"]);
    return facts.map(([term, value]) => "<dt>" + esc(term) + "</dt><dd>" + esc(value) + "</dd>").join("");
  }

  /** The headline test scores: one panel per test, or (older exports) the summary lines. */
  function scoresHtml(board) {
    if (!board) return "";
    if (board.panels && board.panels.length) {
      return '<div class="score-panels">' + board.panels.map(panelHtml).join("") + "</div>";
    }
    const lines = [];
    const runway = board.runway;
    if (runway && runway.skill_vs_usual_rate) {
      lines.push("<li><strong>The 90-day chance:</strong> " + esc(lessOrMore(runway.skill_vs_usual_rate.value)) +
                 " than always guessing the usual rate (Brier skill score " + withRange(runway.skill_vs_usual_rate, 3) + "). " +
                 esc(runway.label || "") + ".</li>");
    }
    const all = board.rating && board.rating.all_seasons;
    if (all && all.rating_auc && all.rain_only_auc) {
      lines.push("<li><strong>Area outlook:</strong> puts an area where every dam fell to ~0% full ahead of one that kept water " +
                 Math.round(all.rating_auc.value * 100) + " times in 100, against " + Math.round(all.rain_only_auc.value * 100) +
                 " in 100 for rainfall alone (" + esc(all.label || "all past seasons") + ").</li>");
    }
    if (!lines.length) return "";
    return '<p class="scores-source">' + esc(board.source_label || "") + "</p><ul class=\"panel-list\">" + lines.join("") + "</ul>";
  }

  // =====================================================================
  // Test panels (scoreboard.panels): for specialists
  // =====================================================================
  /** 0.0143 -> "+0.014" (signed, fixed decimals). */
  function signed(value, digits) {
    return (value >= 0 ? "+" : "−") + Math.abs(value).toFixed(digits);
  }

  /** A Range {value, ci_low, ci_high} -> "+0.235, range +0.224 to +0.248". */
  function withRange(range, digits) {
    return signed(range.value, digits) + ", range " + signed(range.ci_low, digits) + " to " + signed(range.ci_high, digits);
  }

  /** A skill score in words, either way round: 0.235 -> "nearly a quarter less error"; -0.03 -> "more error". Never a percent. */
  function lessOrMore(value) {
    if (value > 0) return (fmt.fractionWords(value) || "a little") + " less error";
    if (value === 0) return "no less error";
    const words = fmt.fractionWords(-value);
    return (words ? words + " " : "") + "more error";
  }

  /** How often something happened, out of 1,000: 0.90016 -> "900". */
  function inThousand(share) {
    return fmt.thousands(fmt.inThousand(share));
  }

  /** A July-June year: 2023 -> "July 2023 to June 2024" (the pipeline names it by its first year). */
  function julyJuneYear(year) {
    return "July " + year + " to June " + (year + 1);
  }

  /** true / false / null -> "met" / "not met" / "not checked". */
  function verdict(passed, yes, no) {
    // a tick in a quiet outlined pill, a cross in a filled ink pill: a fail stands out by shape and weight, not colour
    const mark = (id) => (DamDays.icon ? DamDays.icon(id, "sm") : "");
    if (passed === true) return '<strong class="verdict-yes">' + mark("i-check") + yes + "</strong>";
    if (passed === false) return '<strong class="verdict-no">' + mark("i-x") + no + "</strong>";
    return "not checked";
  }

  /**
   * The cautious days' verdict (format.floorCheck) in the same pills: on target a tick, below target a cross, and
   * "more cautious than built for" (above the range) neither: a dashed pill with an up arrow.
   */
  function floorVerdict(fc) {
    if (fc.state === "met") return verdict(true, fc.verdict, "");
    if (fc.state === "miss") return verdict(false, "", fc.verdict);
    const mark = DamDays.icon ? DamDays.icon(fc.icon, "sm") : "";
    return '<strong class="verdict-neutral">' + mark + esc(fc.verdict) + "</strong>";
  }

  /** Read "runway.skill_vs_usual_rate" from a panel. */
  function field(panel, path) {
    return path.split(".").reduce((part, key) => (part ? part[key] : null), panel);
  }

  /** "What we said before opening" list; with the result next to each line once scored. */
  function expectationsHtml(panel) {
    if (!panel.expectations || !panel.expectations.length) return "";
    const items = panel.expectations.map((e) => {
      const got = panel.status === "scored" ? field(panel, e.field) : null;
      return "<li>" + esc(String(e.what || "").replace(/^Runway skill/, "90-day chance skill")) + ": " + signed(e.low, 2) + " to " + signed(e.high, 2) +
             (got && typeof got.value === "number" ? "; <strong>got " + signed(got.value, 3) + "</strong>" : "") + "</li>";
    });
    return '<p class="panel-small">What we said we expected, before opening it (written in the test plan, PREREG.md):</p>' +
           '<ul class="panel-list">' + items.join("") + "</ul>";
  }

  // The panel's own title and text still name the old 17:30 slot; the opening now comes after this
  // build of the app, so the pending panel promises no time (scripts/21 replaces it with the scores).
  function pendingPanelHtml(panel) {
    const title = "Sealed region: not opened yet";
    const first = String(panel.text || "").split(/(?<=\.)\s+/)[0] || "";
    return '<section class="score-panel score-panel-pending" aria-label="' + esc(title) + '">' +
           '<p class="panel-status">Not opened yet</p>' +
           "<h3>" + esc(title) + "</h3>" +
           '<p class="panel-label">' + esc(panel.label || "") + "</p>" +
           "<p>" + esc(first) + (first ? " " : "") + "It is opened once, on camera, after this build of the app, forecast with the locked model and scored once. Its results will appear here.</p>" +
           expectationsHtml(panel) + "</section>";
  }

  function panelHtml(panel) {
    if (!panel) return "";
    if (panel.status !== "scored") return pendingPanelHtml(panel);
    const r = panel.runway;
    const g = panel.rating;
    const items = [];
    if (r && r.skill_vs_usual_rate) {
      items.push("<li><strong>The 90-day chance (R30):</strong> " + esc(lessOrMore(r.skill_vs_usual_rate.value)) +
                 " than always guessing the usual rate for the region and month (Brier skill score against B0, " +
                 withRange(r.skill_vs_usual_rate, 3) + ")" +
                 (r.skill_vs_own_record ? "; " + esc(lessOrMore(r.skill_vs_own_record.value)) +
                  " than each dam's own past rate (against B2, " + withRange(r.skill_vs_own_record, 3) + ")" : "") + ".</li>");
      if (r.gain_vs_benchmark) {
        // "Ahead" only when the whole range is above zero, so a result that did not beat G2 says so.
        const gain = r.gain_vs_benchmark;
        const lead = gain.ci_low > 0 ? "Ahead of" : (gain.ci_high < 0 ? "Behind" : "Not clearly ahead of");
        items.push("<li>" + lead + " the benchmark model written down before the code (G2, the decision-tree model alone), on the same " +
                   "forecasts (skill gain " + withRange(gain, 3) + ").</li>");
      }
      if (r.auc) {
        items.push("<li><strong>Ranking:</strong> shown one dam that fell below a third and one that did not, it gave the higher chance to " +
                   "the right one " + Math.round(r.auc.value * 100) + " times in 100 (AUC " + fmt.auc(r.auc) + ").</li>");
      }
      if (r.calibration_slope) {
        items.push("<li><strong>Honest chances:</strong> calibration slope " + r.calibration_slope.value.toFixed(2) + " (range " +
                   r.calibration_slope.ci_low.toFixed(2) + " to " + r.calibration_slope.ci_high.toFixed(2) + "); 1.00 means what " +
                   "happened matched what was said, above 1 means the chances could be a little bolder.</li>");
      }
      if (typeof r.n_forecasts === "number") {
        items.push("<li>" + fmt.thousands(r.n_forecasts) + " forecasts made October to March" +
                   (typeof r.n_dams === "number" ? " for " + fmt.thousands(r.n_dams) + " dam-sized waterbodies" : "") +
                   (typeof r.n_fell_below_third === "number" ? "; " + fmt.thousands(r.n_fell_below_third) + " were followed by a fall below a third" : "") +
                   ". Pass marks written before the code: " + verdict(r.pass_bars_met, "met", "not met") + ".</li>");
      }
    }
    if (g && g.rating_auc && g.rain_only_auc) {
      items.push("<li><strong>Area outlook (season ahead, 2 km areas):</strong> puts an area where every dam fell to ~0% full ahead of one " +
                 "that kept water " + Math.round(g.rating_auc.value * 100) + " times in 100, against " +
                 Math.round(g.rain_only_auc.value * 100) + " in 100 for rainfall alone (AUC " + fmt.auc(g.rating_auc) + " against " +
                 fmt.auc(g.rain_only_auc) + "; " + fmt.thousands(g.n_cells) + " area-seasons, " + fmt.thousands(g.n_ran_dry) +
                 " fell to ~0% full). Pass mark: " + verdict(g.pass_bar_met, "met", "not met") +
                 "; kill rule (drop it if rainfall alone did as well): " +
                 verdict(g.kill_rule_triggered === null || g.kill_rule_triggered === undefined ? null : !g.kill_rule_triggered, "not triggered", "triggered") +
                 ".</li>");
    }
    if (panel.floor && typeof panel.floor.held === "number") {
      // How often the promise held is written "N in 1,000", never as a percent ("%" only means how full).
      const across = panel.floor.n_forecasts ? " across " + fmt.thousands(panel.floor.n_forecasts) + " forecasts" : "";
      const worst = panel.floor.worst_year
        ? "; in the worst year, " + julyJuneYear(panel.floor.worst_year.year) + ", " + inThousand(panel.floor.worst_year.coverage) + " in 1,000" : "";
      const ci = typeof panel.floor.ci_low === "number" && typeof panel.floor.ci_high === "number"
        ? " (range " + inThousand(panel.floor.ci_low) + " to " + inThousand(panel.floor.ci_high) + ")" : "";
      // on target or not: the one rule of Proof's exam card and Questions (format.floorCheck: the panel's own
      // on_target flag when it has one, else the test code's float rule with proof.json's tolerance)
      const fc = fmt.floorCheck(panel.floor);
      const target = fc.target === null ? "" : " (target " + fmt.thousands(fc.target) + (fc.range ? "; " + fc.range + " counts as on target" : "") +
        (fc.edgeNote ? "; " + fc.edgeNote : "") + ")";
      items.push("<li><strong>The DamDays number</strong> (\"at least N days\", built to hold 9 times in 10): held " +
                 inThousand(panel.floor.held) + " in every 1,000" + across + ci + (fc.verdict ? ", " + floorVerdict(fc) : "") + target + worst + ".</li>");
    }
    if (panel.band) {
      // On the development test years the band's design was partly chosen after seeing them, so its
      // coverage there is not an independent check. Say so.
      const notIndependent = panel.key === "dev_test"
        ? " Not an independent check: the range's design was partly chosen after seeing these years." : "";
      items.push("<li><strong>Wetter or drier season range (R30 band):</strong> covered " + panel.band.covered + " of " +
                 panel.band.region_years + " region-years." + notIndependent + "</li>");
    }
    // The exporter titles the sealed panel with the slot it was first planned for ("opened Sat 3 Oct
    // 17:30"); the opening came after the app build, so name the day from the panel's own scored_at.
    const day = panel.key === "sealed" && panel.scored_at && fmt.stampDay ? fmt.stampDay(panel.scored_at) : "";
    const title = day ? "Sealed region: opened " + day + ", scored once" : panel.title;
    return '<section class="score-panel" aria-label="' + esc(title) + '">' +
           '<p class="panel-status panel-status-done">Scored once</p>' +
           "<h3>" + esc(title) + "</h3>" +
           '<p class="panel-label">' + esc(panel.label || "") + "</p>" +
           '<ul class="panel-list">' + items.join("") + "</ul>" + expectationsHtml(panel) + "</section>";
  }

  // =====================================================================
  // The new About page (#about, #about/specialists)
  // =====================================================================
  const icon = (id, cls) => (DamDays.icon ? DamDays.icon(id, cls) : "");
  const repo = (path) => ((DamDays.settings && DamDays.settings.repoBlobUrl) || "https://github.com/Shaugato/damdays/blob/main/") + path;

  function featuredFarm(data) {
    const farms = data.farms && Array.isArray(data.farms.farms) ? data.farms.farms : [];
    const hidden = (DamDays.settings && DamDays.settings.hiddenFarmIds) || [];
    return farms.find((f) => f.farm_id === (DamDays.settings && DamDays.settings.defaultFarmId) && !hidden.includes(f.farm_id)) ||
      farms.find((f) => !hidden.includes(f.farm_id)) || null;
  }

  /** The numbers the page quotes, each from the data (null when this dataset lacks it). */
  function facts(data) {
    const meta = data.meta || {};
    const proof = data.proof || null;
    const areas = (data.dams || []).map((d) => d.area_ha).filter((a) => typeof a === "number");
    const minHa = typeof meta.min_dam_area_ha === "number" ? meta.min_dam_area_ha : (areas.length ? Math.min.apply(null, areas) : null);
    const cov = meta.coverage && meta.coverage.text ? /to\s+(\d+(?:\.\d+)?)\s*ha/.exec(meta.coverage.text) : null;
    const maxHa = cov ? Number(cov[1]) : (areas.length ? Math.max.apply(null, areas) : null);
    const hist = data.history || {};
    const firstYear = hist.first_month ? Number(String(hist.first_month).slice(0, 4)) : null;
    const lastYear = hist.last_month ? Number(String(hist.last_month).slice(0, 4)) : null;
    const allYears = proof && proof.by_year ? proof.by_year.all_years : null;
    const farm = featuredFarm(data);
    const records = data.trackRecord && data.trackRecord.dams ? data.trackRecord.dams : null;
    let heroDam = null, heroRecord = null;
    if (farm && Array.isArray(farm.dams)) {
      heroDam = farm.dams.filter((d) => d.status === "forecast" && typeof d.days_left === "number").sort((a, b) => a.days_left - b.days_left)[0] || farm.dams[0];
      heroRecord = heroDam && records ? records[heroDam.dam_id] : null;
    }
    const sealed = data.scoreboard && data.scoreboard.panels ? data.scoreboard.panels.find((p) => p.key === "sealed") : null;
    return {
      meta, farm, heroDam, heroRecord, sealed,
      size: minHa !== null && maxHa !== null ? "about " + (Math.floor(minHa * 10) / 10) + " to " + Math.round(maxHa) + " ha" : null,
      minHa: typeof meta.min_dam_area_ha === "number" ? (Math.floor(meta.min_dam_area_ha * 10) / 10) : null,
      years: firstYear && lastYear ? lastYear - firstYear : null,
      horizon: meta.horizon_days || null,
      arm: meta.arm_level_pct || null,
      floorHeld: allYears && typeof allYears.floor_held === "number" ? allYears.floor_held : null,
      floorTarget: proof && proof.by_year && typeof proof.by_year.floor_target === "number" ? proof.by_year.floor_target : null,
      skillWords: proof && proof.test && proof.test.skill_vs_usual_rate ? proof.test.skill_vs_usual_rate.words || fmt.fractionWords(proof.test.skill_vs_usual_rate.value) : null,
      setAside: data.farms && Array.isArray(data.farms.set_aside) ? data.farms.set_aside : [],
      examWhen: sealed && fmt.examStatus ? fmt.examStatus(sealed).when : null,   // from the panel, never a promised time
    };
  }

  /** A worked example of the DamDays number, from the featured farm's dam with the fewest days this week. */
  function exampleText(F) {
    const d = F.heroDam;
    if (!d || d.status !== "forecast" || typeof d.days_left !== "number" || d.days_left <= 0 || !d.issued_on ||
        typeof d.damdays_days !== "number" || !fmt.addDays) return "";
    const farm = F.farm ? String(F.farm.name).replace(/\s*\(.*\)\s*$/, "") : "A demo farm";
    const cap = (DamDays.text && DamDays.text.CAP_DAYS) || 180;
    if (d.days_left >= cap) return "";
    return " For example, " + farm + "'s " + d.name + " says at least " + d.days_left + " days this week: it should stay above a third " +
      "until at least " + fmt.short(fmt.addDays(d.issued_on, d.damdays_days)) + ".";
  }

  function stepsHtml(F) {
    const steps = [
      ["i-sat", "Satellites watch the dams.", "Landsat has photographed Australia every couple of weeks for decades. Geoscience Australia turns those photos into the wet area of each waterbody" +
        (F.years ? ": " + F.years + " years of water history for each dam." : ".")],
      ["i-chart", "We learn how each dam behaves.", "How fast it drops in summer, how it fills after rain, and whether it runs wetter or drier than similar dams."],
      ["i-calendar", "We forecast the chance of running low.", "For each dam: the chance it drops below a third of its usual full water surface" +
        (F.horizon ? " in the next " + F.horizon + " days" : "") + ", written \"3 in 10\", and by each date over the next six months."],
      ["i-drop", "The DamDays number.", "At least how many days before it drops below a third. Cautious by design: across all dams in ten test years it held 9 times in 10, a little less often for spring looks. It is the headline." +
        exampleText(F)],
      ["i-sms", "One text a week.", "Each farm gets one text a week for the dams that matter: how full each one is, at least how many days it has, and which are already low."],
    ];
    return '<ol class="about-steps">' + steps.map((s, i) => '<li class="about-step"><span class="about-step-n" aria-hidden="true">' + (i + 1) +
      "</span>" + icon(s[0], "about-step-i") + "<div><h3>" + esc(s[1]) + "</h3><p>" + esc(s[2]) + "</p></div></li>").join("") + "</ol>" +
      '<p class="about-cta"><a class="btn btn-secondary" href="#farm">' + (F.farm ? "See " + esc(String(F.farm.name).replace(/\s*\(.*\)\s*$/, "")) + "'s text and dams" : "See a farm's text and dams") + "</a></p>";
  }

  function wordsHtml(F) {
    const rec = F.heroRecord && F.heroRecord.judged ? fmt.held(F.heroRecord.held, F.heroRecord.judged) : null;
    return '<aside class="about-words" aria-labelledby="about-words-h"><h2 class="card-title" id="about-words-h">' + icon("i-info") +
      "<span>A note on words</span></h2><ul>" +
      "<li><b>\"%\"</b> always means how full a dam is: its wet water surface against its usual full surface, not its depth.</li>" +
      "<li>A <b>chance</b> is written \"3 in 10\".</li>" +
      (rec ? "<li>How often our days held is a count: \"" + esc(rec) + "\".</li>"
        : "<li>How often our days held is a count: the times it held, of the times we could check.</li>") +
      "<li>A dam at 0% is <b>\"no water seen\"</b>: the satellite saw no water at its last clear look.</li></ul></aside>";
  }

  function checkedHtml(F) {
    const held = F.floorHeld !== null ? fmt.inThousandText(F.floorHeld) : null;
    const how = (DamDays.text && DamDays.text.TRACK_RECORD_HOW) || "";
    return '<section class="about-sec" aria-labelledby="about-checked-h"><h2 class="section-title" id="about-checked-h">How we checked it</h2>' +
      "<p>We wrote down the tests and the pass marks before writing any code, in the public repository. " + esc(how) +
      (held ? " The cautious days held <b>" + esc(held) + "</b> times" + (F.skillWords ? ", and the chances had " + esc(F.skillWords) + " less error than guessing the usual rate" : "") + "." : "") +
      "</p><p>Those are years it never trained on, but we had looked at them in research before the event, so they may flatter it slightly. " +
      "The clean test is a third farming region, a region it never saw, locked away before the event and opened once, on camera" +
      (F.examWhen ? " (" + esc(F.examWhen) + ")" : "") + ".</p>" +
      '<div class="linkrows about-links">' +
      '<a class="linkrow" href="#proof">' + icon("i-proof") + "<span>Proof<small>What we said against what happened, year by year and dam by dam.</small></span><span class=\"chev\">" + icon("i-chev") + "</span></a>" +
      '<a class="linkrow" href="#proof/exam">' + icon("i-lock") + "<span>The unseen exam<small>The region it never saw, opened once.</small></span><span class=\"chev\">" + icon("i-chev") + "</span></a>" +
      "</div></section>";
  }

  function limitsHtml(F) {
    const farmD = F.setAside[0];
    // The data's reason, without its "Set aside:" lead and its closing "which is why we checked" sentence (said just before it here).
    const reason = farmD && farmD.reason ? String(farmD.reason).replace(/^Set aside:\s*/i, "").replace(/\s*They passed the filter[^.]*\.\s*$/, "") : "";
    const nearTown = farmD && farmD.name ? (/\(near ([^)]+)\)/.exec(farmD.name) || [])[1] : null;
    const featured = F.farm ? String(F.farm.name).replace(/\s*\(.*\)\s*$/, "") : null;
    // how many satellite pixels a dam needs, from meta.json's own limits ("about 0.54 ha (6 Landsat pixels)")
    const px = /\((\d+) Landsat pixels\)/.exec([].concat(F.meta.limits || [], F.meta.notes || []).join(" "));
    const limits = [
      ["Only dams of " + (F.minHa !== null ? "about " + F.minHa + " ha" : "about half a hectare") + " and up.",
        "A dam needs " + (px ? "at least " + px[1] + " Landsat pixels" : "several satellite pixels") + " of water to be seen" +
        (F.size ? ": DamDays follows dams of " + F.size + " of water" : "") + ". Bores, tanks and small dams are not visible."],
      ["Water area, not depth.", "Satellites see how much of the dam is wet, not how deep it is. \"Below a third\" is our plain rounding of the line the forecasts use: " +
        (typeof F.meta.threshold_pct === "number" ? F.meta.threshold_pct : 30) + "% of the dam's usual full wet area."],
      ["Clouds and gaps.", "Some weeks have no clear look, and looks can be weeks old. Each forecast shows the date of its last clear look."],
      ["\"No water seen\" is not \"dry\".", "0% means no satellite pixel was classed as water at the last clear look. A small pool, or muddy or green water, can be missed, and one look can be wrong; the next look will tell."],
      ["Not every waterbody is a farm dam.", "Our demo farms sit on the densest clusters of dam-sized waterbodies, and the filter that picks them catches some town or industrial ponds, " +
        "so we checked the demo farms against aerial photos." +
        (farmD ? " We took out " + (nearTown ? "the farm near " + nearTown : farmD.name) + (reason ? ": " + reason.charAt(0).toLowerCase() + reason.slice(1) : ".") : "") +
        (F.setAside.length > 1 ? " We set " + F.setAside.length + " demo farms aside in all." :
          " From quick looks at the whole circle, several other demo farms' circles also take in mine ponds, wetland basins or town lagoons, so not every dam in their texts is a farm dam.") +
        (featured ? " " + featured + ", the farm we feature, has " + (F.farm.dams && F.farm.dams.length ? F.farm.dams.length + " " : "") + "clear farm dams." : "")],
      ["A chance is a chance.", "A chance of 3 in 10 means that about 3 of every 10 dams like this one drop below a third. Some will, most won't."],
      ["The days are cautious, not certain.", "Our days-left number held 9 times in 10 across all dams in the ten test years (a little less often for spring looks), so about 1 time in 10 a dam drops below a third sooner. On some dams it held less often: each dam shows its own record. Each forecast starts from the dam's last clear look; the days since that look are taken off."],
      ["A farm is a circle.", "We have no property boundaries, so a farm's dams are the dams within the circle you choose. On a small block the circle can take in a neighbour's dams; on a big station it can miss some."],
      ["The Area outlook ranks areas, not drought years.", "Set aside, with its result still reported: it is good at saying which areas are more exposed in a season. " +
        "Whether a whole season will be dry is a different job, best left to the Bureau of Meteorology's climate outlooks."],
      ["Not advice.", "Use it alongside your own eyes on the dam and local knowledge."],
    ];
    return '<section class="about-sec" aria-labelledby="about-limits-h"><h2 class="section-title" id="about-limits-h">Honest limits</h2>' +
      '<ul class="about-limits">' + limits.map((l) => "<li" + (l[1].length > 260 ? ' class="is-wide"' : "") + "><h3>" + esc(l[0]) + "</h3><p>" + esc(l[1]) + "</p></li>").join("") + "</ul></section>";
  }

  function copHtml(F) {
    return '<section class="about-sec" aria-labelledby="about-cop-h"><h2 class="section-title" id="about-cop-h">Why it matters for COP31</h2>' +
      '<ul class="about-bullets">' +
      "<li><b>Awareness track: helping farmers adapt.</b> Farmers would get a forecast for each dam big enough for the satellites to see" +
      (F && F.size ? " (" + esc(F.size) + ")" : "") + ", counted in days before it drops below a third, " +
      "to help them decide while there are still choices: move or sell stock, book water carting, or fix a leaking dam.</li>" +
      "<li><b>Global Goal on Adaptation.</b> Its framework (the UAE Framework for Global Climate Resilience) includes targets on water scarcity and " +
      "climate-resilient farming. DamDays gives a farm-by-farm measure of water security that can be refreshed with each clear satellite look " +
      "(today we run it by hand; automatic weekly updates are not built yet).</li></ul></section>";
  }

  function creditsHtml() {
    return '<section class="about-sec" aria-labelledby="about-data-h"><h2 class="section-title" id="about-data-h">Data and credits</h2>' +
      '<ul class="about-credits">' +
      '<li><b>DEA Waterbodies</b> (version 3), Geoscience Australia. CC BY 4.0. <a href="https://www.dea.ga.gov.au/" rel="noopener">dea.ga.gov.au</a></li>' +
      '<li><b>SILO climate data</b> (monthly rainfall), Queensland Government. CC BY 4.0. <a href="https://www.longpaddock.qld.gov.au/silo/" rel="noopener">longpaddock.qld.gov.au/silo</a></li>' +
      "<li><b>Street maps</b> &copy; OpenStreetMap contributors (ODbL), drawn with Leaflet.</li>" +
      "<li><b>Type:</b> Atkinson Hyperlegible Next, Braille Institute (SIL Open Font License).</li></ul>" +
      '<p class="about-team">Built by the DamDays team for Climate Hack-tion 2026. An AI coding assistant (Claude Code) generated code under our direction; ' +
      '<a href="' + esc(repo("DISCLOSURE.md")) + '" rel="noopener">the disclosure</a> says what was done before the event.</p></section>';
  }

  /**
   * The exporter's note names the slot first planned for the opening ("opened once on Sat 3 Oct"); scripts/21
   * does not rewrite it. Scored: the day comes from the panel's own scored_at (as the panel title does);
   * pending: no day is promised.
   */
  function noteText(board) {
    const sealed = (board.panels || []).find((p) => p.key === "sealed");
    const note = String(board.note || "");
    if (sealed && sealed.status === "scored") {
      const day = sealed.scored_at && fmt.stampDay ? fmt.stampDay(sealed.scored_at) : "";
      return note.replace(/opened once on [^,.]*/i, day ? "opened once on " + day : "opened once");
    }
    return note.replace(/the sealed region, opened once on [^,.]*, is the clean test/i,
      "the sealed region, to be opened once on camera after this build of the app, is the clean test");
  }

  function specialistsHtml(data) {
    const board = data.scoreboard || {};
    const meta = data.meta || {};
    const checks = [
      ["The test results", "artifacts/test_results.md"], ["The test plan, written before the code", "PREREG.md"],
      ["The scorecard", "docs/SCORECARD.md"], ["How the unseen exam is opened", "docs/SEALED_OPENING.md"],
      ["Our record, dam by dam", "artifacts/track_record.md"], ["What we disclosed", "DISCLOSURE.md"],
    ];
    return '<details class="more about-specialists" id="about-specialists"><summary>' + icon("i-chart") +
      "<span>Methods and scores, for specialists<small>The test scores with their usual names, each in plain words</small></span>" + icon("i-plus", "plus") +
      '</summary><div class="body">' +
      (board.note ? '<p class="spec-note">' + esc(noteText(board)) + "</p>" : "") +
      '<p class="panel-small">Each range is where the score would likely fall if the dams and region-years were re-drawn (95 in 100 times).</p>' +
      scoresHtml(board) +
      (meta.live && meta.live.about ? '<p class="panel-small">Today\'s forecasts: ' + esc(meta.model ? meta.model.name + " " + (meta.model.version || "") : "the same model") +
        ", " + esc(meta.live.about) + (meta.live.cutoff ? " (answers known before " + esc(fmt.date(meta.live.cutoff)) + ")" : "") + ".</p>" : "") +
      '<h3 class="spec-h">This page\'s data</h3><dl class="facts">' + datasetFacts(data) + "</dl>" +
      '<h3 class="spec-h">Where to check</h3><ul class="checklinks">' + checks.map((c) =>
        '<li><a href="' + esc(repo(c[1])) + '" rel="noopener">' + esc(c[0]) + "</a> <small>" + esc(c[1]) + "</small></li>").join("") + "</ul>" +
      "</div></details>";
  }

  function pageHtml(data) {
    const F = facts(data);
    return '<div class="wrap page-narrow about-page">' +
      '<header class="page-head"><p class="eyebrow">About DamDays</p><h1 id="about-h1">How DamDays works</h1>' +
      '<p class="lead">One text a week for each farm dam big enough for the satellites to see' + (F.size ? " (" + esc(F.size) + ")" : "") +
      ": how full it was at its last clear look, and at least how many days it has before it drops below a third.</p></header>" +
      '<section class="about-sec" aria-labelledby="about-how-h"><h2 class="section-title" id="about-how-h">How it works</h2>' + stepsHtml(F) + "</section>" +
      wordsHtml(F) + checkedHtml(F) + limitsHtml(F) + copHtml(F) + creditsHtml() +
      '<section class="about-sec" aria-label="For specialists">' + specialistsHtml(data) + "</section>" +
      "</div>";
  }

  // ---- router ------------------------------------------------------------------------
  let root = null;
  let ready = false;

  function render(rootEl) {
    root = rootEl;
    return (DamDays.data.need ? DamDays.data.need("first") : DamDays.data.load()).then((data) => {
      root.innerHTML = pageHtml(data);
      ready = true;
      const det = root.querySelector("#about-specialists");
      if (det) {
        det.querySelector("summary").addEventListener("click", (event) => {
          event.preventDefault();
          const route = DamDays.router.current();
          if (det.open) {
            if (route && route.sub === "specialists") DamDays.router.up(); else det.open = false;
          } else {
            DamDays.router.go("#about/specialists");
          }
        });
      }
    });
  }

  function enter(route) {
    if (!ready) return;
    const det = root.querySelector("#about-specialists");
    if (!det) return;
    if (route.sub === "specialists") {
      det.open = true;
      setTimeout(() => det.scrollIntoView({ block: "start", behavior: "auto" }), 30);
    } else {
      det.open = false;
    }
  }

  if (DamDays.router && typeof DamDays.router.register === "function") {
    DamDays.router.register("about", { render, enter });
  }

  return { init, show, panelHtml, lessOrMore, scoresHtml };
})();
