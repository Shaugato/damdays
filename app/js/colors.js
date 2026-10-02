/* colors.js
 * Turns a chance (0 to 1) into a colour band, and draws the colour key (legend).
 * The bands and colours themselves live in settings.js.
 */
window.DamDays = window.DamDays || {};

DamDays.colors = (function () {
  "use strict";

  /** The colour band a chance falls in, or null when there is no chance to show. */
  function bandFor(chance) {
    if (chance === null || chance === undefined) return null;
    const bands = DamDays.settings.chanceBands;
    return bands.find((band) => chance >= band.min && chance < band.max) || bands[bands.length - 1];
  }

  /** Fill colour for a chance; grey when there is no forecast. */
  function colorFor(chance) {
    const band = bandFor(chance);
    return band ? band.color : DamDays.settings.noForecastColor;
  }

  /**
   * Draw the colour key into a container.
   * options.title          the question the colours answer
   * options.showNoForecast add a grey "no forecast" entry
   * options.extraItems     more entries, e.g. [{ swatchClass: "swatch-ring", label: "Ran dry" }]
   */
  function renderLegend(container, options) {
    const esc = DamDays.format.escapeHtml;
    const items = DamDays.settings.chanceBands.map((band) =>
      '<li><span class="swatch" style="background:' + band.color + '" aria-hidden="true"></span>' +
      esc(band.label) + "</li>");
    if (options.showNoForecast) {
      items.push('<li><span class="swatch" style="background:' + DamDays.settings.noForecastColor +
                 '" aria-hidden="true"></span>No forecast (see the dam for why)</li>');
    }
    (options.extraItems || []).forEach((item) => {
      items.push('<li><span class="swatch ' + item.swatchClass + '" aria-hidden="true"></span>' +
                 esc(item.label) + "</li>");
    });
    container.innerHTML =
      '<p class="legend-title" id="' + container.id + '-title">' + esc(options.title) + "</p>" +
      '<ul class="legend-items" aria-labelledby="' + container.id + '-title">' + items.join("") + "</ul>";
  }

  return { bandFor, colorFor, renderLegend };
})();
