/* views/about.js
 * The About page is mostly plain text in index.html. This file fills in the
 * parts that depend on the loaded data: which dataset this is, when it was
 * made, and the headline test scores.
 * The test scores are for judges and lenders, so they keep their usual units
 * (skill as "23.5% less error", AUC as "81 in 100"), each in plain words.
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.views.about = (function () {
  "use strict";

  const fmt = DamDays.format;
  const esc = (text) => DamDays.format.escapeHtml(text);

  /** Runs once, the first time the view is shown. */
  function init(data) {
    const meta = data.meta;
    document.querySelectorAll('[data-fill="min-area"]').forEach((span) => {
      span.textContent = meta.min_dam_area_ha.toFixed(1);
    });
    document.getElementById("about-dataset").innerHTML = datasetFacts(data);
    document.getElementById("about-scores").innerHTML = scoresHtml(data.scoreboard);
    // Which years the shown scores come from (validation or test). The scoreboard says it,
    // so the sentence always matches the numbers below it.
    if (data.scoreboard.note) {
      document.getElementById("about-split").textContent = data.scoreboard.note;
    }
  }

  /** Nothing to refresh: the page is static once filled. */
  function show() {}

  /** A short list: region, data type, satellite looks up to, model, made on. */
  function datasetFacts(data) {
    const meta = data.meta;
    const facts = [
      ["Region", meta.region.name],
      ["Data", meta.is_mock ? "MOCK (made up, for testing the app)" : "Real forecasts"],
      ["Satellite looks up to", meta.data_through ? fmt.date(meta.data_through) : "not stated"],
      ["Model", meta.model ? meta.model.name + (meta.model.version ? ", " + meta.model.version : "") : "not stated"],
      ["Made on", meta.generated_at ? fmt.dateTime(meta.generated_at) : "not stated"],
    ];
    return facts.map(([term, value]) => "<dt>" + esc(term) + "</dt><dd>" + esc(value) + "</dd>").join("");
  }

  /** The headline test scores, in plain words, if the scoreboard has them. */
  function scoresHtml(board) {
    // A test-season export has one panel per test (development regions; sealed region).
    if (board.panels && board.panels.length) {
      return '<div class="score-panels">' + board.panels.map(panelHtml).join("") + "</div>";
    }
    const lines = [];
    const runway = board.runway;
    if (runway && runway.skill_vs_usual_rate) {
      const skill = runway.skill_vs_usual_rate;
      // A positive skill score means less error than the usual-rate guess; negative means more.
      const comparison = skill.value >= 0 ? "% less" : "% more";
      lines.push("<li><strong>Runway forecasts:</strong> " + Math.abs(Math.round(skill.value * 100)) +
                 comparison + " forecast error than always guessing the usual rate (Brier skill score " +
                 skill.value.toFixed(2) + ", 95% range " + skill.ci_low.toFixed(2) + " to " +
                 skill.ci_high.toFixed(2) + "). " + esc(runway.label || "") + ".</li>");
    }
    const all = board.rating && board.rating.all_seasons;
    if (all && all.rating_auc && all.rain_only_auc) {
      lines.push("<li><strong>Season rating:</strong> puts a cell that ran dry ahead of one that did not " +
                 Math.round(all.rating_auc.value * 100) + " times in 100, against " +
                 Math.round(all.rain_only_auc.value * 100) + " in 100 for rainfall alone (" +
                 esc(all.label || "all past seasons") + ").</li>");
    }
    if (!lines.length) return "";
    return '<p class="scores-source">' + esc(board.source_label || "") + "</p><ul>" + lines.join("") + "</ul>";
  }

  // ---- Test panels (scoreboard.panels) ----------------------------------------
  /** 0.0143 -> "+0.014" (signed, fixed decimals). */
  function signed(value, digits) {
    return (value >= 0 ? "+" : "−") + Math.abs(value).toFixed(digits);
  }

  /** A Range {value, ci_low, ci_high} -> "+0.235, 95% range +0.224 to +0.248". */
  function withRange(range, digits) {
    return signed(range.value, digits) + ", 95% range " + signed(range.ci_low, digits) + " to " +
           signed(range.ci_high, digits);
  }

  /** 0.23501 -> "23.5" (a share as a percentage with one decimal, as the README and docs write it).
   *  Only for the skill scores ("23.5% less error"), never for a chance. */
  function percentOne(value) {
    return (value * 100).toFixed(1);
  }

  /** How often something happened, out of 1,000: 0.90016 -> "900", 0.87199 -> "872". */
  function inThousand(share) {
    return String(Math.round(share * 1000));
  }

  /** A July-June year: 2023 -> "July 2023 to June 2024" (the pipeline names it by its first year). */
  function julyJuneYear(year) {
    return "July " + year + " to June " + (year + 1);
  }

  /** true / false / null -> "met" / "not met" / "not checked". */
  function verdict(passed, yes, no) {
    if (passed === true) return '<strong class="verdict-yes">' + yes + "</strong>";
    if (passed === false) return '<strong class="verdict-no">' + no + "</strong>";
    return "not checked";
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
      return "<li>" + esc(e.what) + ": " + signed(e.low, 2) + " to " + signed(e.high, 2) +
             (got ? "; <strong>got " + signed(got.value, 3) + "</strong>" : "") + "</li>";
    });
    return '<p class="panel-small">What we said we expected, before opening it (PREREG.md):</p><ul class="panel-list">' +
           items.join("") + "</ul>";
  }

  function pendingPanelHtml(panel) {
    return '<section class="score-panel score-panel-pending" aria-label="' + esc(panel.title) + '">' +
           '<p class="panel-status">Not opened yet</p>' +
           "<h3>" + esc(panel.title) + "</h3>" +
           '<p class="panel-label">' + esc(panel.label || "") + "</p>" +
           "<p>" + esc(panel.text || "") + "</p>" + expectationsHtml(panel) + "</section>";
  }

  function panelHtml(panel) {
    if (panel.status !== "scored") return pendingPanelHtml(panel);
    const r = panel.runway;
    const g = panel.rating;
    const items = [];
    // A skill score in words, either way round: 0.235 -> "23.5% less", -0.03 -> "3.0% more".
    const lessOrMore = (value) => percentOne(Math.abs(value)) + (value >= 0 ? "% less" : "% more");
    if (r && r.skill_vs_usual_rate) {
      items.push("<li><strong>Runway forecasts:</strong> " + lessOrMore(r.skill_vs_usual_rate.value) +
                 " forecast error than always guessing the usual rate (Brier skill score " +
                 withRange(r.skill_vs_usual_rate, 3) + ")" +
                 (r.skill_vs_own_record ? ", and " + lessOrMore(r.skill_vs_own_record.value) +
                  " than the dam's own track record" : "") + ".</li>");
      if (r.gain_vs_benchmark) {
        // "Ahead" only when the whole 95% range is above zero, so a sealed result that did not beat G2 says so.
        const gain = r.gain_vs_benchmark;
        const lead = gain.ci_low > 0 ? "Ahead of" : (gain.ci_high < 0 ? "Behind" : "Not clearly ahead of");
        items.push("<li>" + lead + " the pre-registered benchmark model G2, on the same forecasts (skill gain " +
                   withRange(gain, 3) + ").</li>");
      }
      items.push("<li>" + r.n_forecasts.toLocaleString("en-AU") + " forecasts made October to March for " +
                 r.n_dams.toLocaleString("en-AU") + " farm-like dams. Pre-registered pass bars: " +
                 verdict(r.pass_bars_met, "met", "not met") + ".</li>");
    }
    if (g && g.rating_auc && g.rain_only_auc) {
      items.push("<li><strong>Season rating:</strong> puts a cell that ran dry ahead of one that did not " +
                 Math.round(g.rating_auc.value * 100) + " times in 100, against " +
                 Math.round(g.rain_only_auc.value * 100) + " in 100 for rainfall alone (" +
                 g.n_cells.toLocaleString("en-AU") + " cell-seasons, " + g.n_ran_dry.toLocaleString("en-AU") +
                 " ran dry). Pre-registered bar (a gain of at least 0.05): " +
                 verdict(g.pass_bar_met, "met", "not met") + "; kill rule " +
                 verdict(g.kill_rule_triggered === null ? null : !g.kill_rule_triggered, "not triggered", "triggered") +
                 ".</li>");
    }
    if (panel.floor) {
      // How often the promise held is a chance, so it is written "N in 1,000", never as a percent
      // ("%" only ever means how full a dam is).
      const across = panel.floor.n_forecasts ? "across " + panel.floor.n_forecasts.toLocaleString("en-AU") + " forecasts, " : "";
      items.push("<li><strong>DamDays number:</strong> the \"at least N days, 9 times in 10\" promise held 9 times " +
                 "in 10, as designed: " + across + inThousand(panel.floor.held) + " in every 1,000 held (target " +
                 inThousand(panel.floor.target || 0.9) + "); in the worst year, " +
                 julyJuneYear(panel.floor.worst_year.year) + ", " + inThousand(panel.floor.worst_year.coverage) +
                 " in 1,000.</li>");
    }
    if (panel.band) {
      // On the development test years the band's design was partly chosen after seeing them
      // (PREREG.md, "Model"), so its coverage there is not an independent check. Say so.
      const notIndependent = panel.key === "dev_test"
        ? " Not an independent check: the range's design was partly chosen after seeing these years." : "";
      items.push("<li><strong>Likely range:</strong> covered " + panel.band.covered + " of " + panel.band.region_years +
                 " region-years." + notIndependent + "</li>");
    }
    return '<section class="score-panel" aria-label="' + esc(panel.title) + '">' +
           '<p class="panel-status panel-status-done">Scored once</p>' +
           "<h3>" + esc(panel.title) + "</h3>" +
           '<p class="panel-label">' + esc(panel.label || "") + "</p>" +
           '<ul class="panel-list">' + items.join("") + "</ul>" + expectationsHtml(panel) + "</section>";
  }

  return { init, show };
})();
