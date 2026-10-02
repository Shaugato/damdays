/* views/about.js
 * The About page is mostly plain text in index.html. This file fills in the
 * parts that depend on the loaded data: which dataset this is, when it was
 * made, and the headline test scores.
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

  return { init, show };
})();
