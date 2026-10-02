/* views/rating.js
 * The lender view: two maps side by side, moving together.
 *   Left:  a rainfall-only score for each 2 km cell (what most drought tools use).
 *   Right: the DamDays Rating for the same cells.
 * "Reveal which ran dry" rings the cells whose dams really did run dry that
 * season, and shows a small scoreboard (AUC of each score, with its range).
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.views.rating = (function () {
  "use strict";

  const fmt = DamDays.format;
  const esc = (text) => DamDays.format.escapeHtml(text);

  // Which number each map colours by.
  const SCORE_FIELD = { rain: "rain_only_chance", damdays: "rating_chance" };

  // A 2 km hexagon is only a speck when zoomed out. Until you zoom in this
  // far, each cell is shown as a dot (like the dams in Runway) instead.
  // Both shapes are always on the map; a CSS class on the map hides one of them.
  const HEX_MIN_ZOOM = 11;

  let data = null;
  let season = null;
  let revealed = false;
  const maps = { rain: null, damdays: null };
  const shapes = { rain: new Map(), damdays: new Map() };   // cell_id -> { hex, dot }
  const el = {};

  /** Runs once, the first time the view is shown. */
  function init(loadedData) {
    data = loadedData;
    el.select = document.getElementById("rating-season");
    el.reveal = document.getElementById("rating-reveal");
    el.note = document.getElementById("rating-note");
    el.legend = document.getElementById("rating-legend");
    el.scoreboard = document.getElementById("rating-scoreboard");

    if (!data.seasons.length) {
      el.note.textContent = "This dataset has no season ratings.";
      el.reveal.disabled = true;
      return;
    }
    data.seasons.forEach((s) => {
      const option = document.createElement("option");
      option.value = s.season;
      option.textContent = s.season + (s.kind === "live" ? " (coming season)" : "");
      el.select.appendChild(option);
    });
    el.select.value = mostTellingSeason().season;
    el.select.addEventListener("change", () => setSeason(el.select.value));
    el.reveal.addEventListener("click", toggleReveal);

    maps.rain = DamDays.map.create("rating-map-rain");
    maps.damdays = DamDays.map.create("rating-map-damdays");
    if (maps.rain && maps.damdays) {
      drawCells("rain");
      drawCells("damdays");
      keepMapsTogether(maps.rain, maps.damdays);
      DamDays.map.fitToPoints(maps.damdays, data.cells.map((c) => [c.lat, c.lon]));
    }
    setSeason(el.select.value);
  }

  /** Runs every time the view is shown. */
  function show() {
    if (maps.rain) maps.rain.invalidateSize();
    if (maps.damdays) maps.damdays.invalidateSize();
  }

  /** Start on the past season where the most cells ran dry (the most telling one). */
  function mostTellingSeason() {
    const dryCount = (s) => s.rows.filter((r) => r.ran_dry === true).length;
    const past = data.seasons.filter((s) => s.kind === "past");
    if (!past.length) return data.seasons[0];
    return past.reduce((best, s) => (dryCount(s) > dryCount(best) ? s : best));
  }

  // ---- Maps -----------------------------------------------------------------
  /** When one map is moved or zoomed, move the other to match. */
  function keepMapsTogether(a, b) {
    let busy = false;   // stops the two maps from endlessly moving each other
    function follow(source, target) {
      source.on("move", () => {
        if (busy) return;
        busy = true;
        target.setView(source.getCenter(), source.getZoom(), { animate: false });
        busy = false;
      });
    }
    follow(a, b);
    follow(b, a);
  }

  /** Make a hexagon and a dot for every cell on one map ("rain" or "damdays"). */
  function drawCells(which) {
    const map = maps[which];
    data.cells.forEach((cell) => {
      const hex = L.polygon(cell.corners, { className: "cell-hex" }).addTo(map);
      const dot = L.circleMarker([cell.lat, cell.lon], { className: "cell-dot" }).addTo(map);
      shapes[which].set(cell.cell_id, { hex: hex, dot: dot });
    });
    map.on("zoomend", () => showHexesOrDots(which));
  }

  /** Show hexagons when zoomed in, dots when zoomed out (see style.css: .zoomed-in). */
  function showHexesOrDots(which) {
    const map = maps[which];
    map.getContainer().classList.toggle("zoomed-in", map.getZoom() >= HEX_MIN_ZOOM);
  }

  /** The look of one hexagon: same colours and reveal rules as the dots. */
  function hexStyle(chance, ranDry) {
    const s = DamDays.settings;
    const style = { fillColor: DamDays.colors.colorFor(chance), fillOpacity: 0.9,
                    color: s.markOutline, weight: 1, opacity: 0.8 };
    if (revealed) {
      if (ranDry === true) {
        style.color = s.revealOutline;   // its dams ran dry: thick black edge
        style.weight = 3.5;
        style.opacity = 1;
      } else {
        style.fillOpacity = 0.25;        // they did not (or unknown): fade back
        style.opacity = 0.3;
      }
    }
    return style;
  }

  // ---- Season and reveal ----------------------------------------------------
  /** Switch season: recolour both maps, reset the reveal. */
  function setSeason(seasonName) {
    season = data.seasons.find((s) => s.season === seasonName);
    revealed = false;
    const isLive = season.kind === "live";
    el.reveal.disabled = isLive;
    el.note.textContent = isLive
      ? "This season has not happened yet, so there is nothing to reveal. Pick a past season to check the scores."
      : "Rated on " + fmt.date(season.issue_date) + ", before the season. Judged on October to March.";
    redraw();
  }

  function toggleReveal() {
    revealed = !revealed;
    redraw();
  }

  /** Recolour every cell, update tooltips, legend, button and scoreboard. */
  function redraw() {
    ["rain", "damdays"].forEach((which) => {
      shapes[which].forEach((shape, cellId) => {
        const row = season.rowsByCell.get(cellId);
        if (!row) {
          // This cell was not rated this season: hide it.
          shape.hex.setStyle({ fillOpacity: 0, opacity: 0 });
          shape.dot.setStyle({ fillOpacity: 0, opacity: 0 });
          return;
        }
        const chance = row[SCORE_FIELD[which]];
        shape.hex.setStyle(hexStyle(chance, row.ran_dry));
        shape.dot.setStyle(DamDays.map.damStyle({ chance: chance, revealed: revealed, outcome: row.ran_dry }));
        [shape.hex, shape.dot].forEach((layer) => {
          layer.unbindTooltip();
          layer.bindTooltip(cellTooltip(row));
        });
      });
    });
    el.reveal.textContent = revealed ? "Hide which ran dry" : "Reveal which ran dry";
    el.reveal.setAttribute("aria-pressed", String(revealed));
    DamDays.colors.renderLegend(el.legend, {
      title: "Chance that every dam in the cell runs completely dry, October to March",
      showNoForecast: false,
      extraItems: revealed ? [
        { swatchClass: "swatch-ring", label: "Black ring: its dams did run dry" },
        { swatchClass: "swatch-faded", label: "Faded: they did not" },
      ] : [],
    });
    el.scoreboard.innerHTML = revealed ? scoreboardHtml() : "";
  }

  function cellTooltip(row) {
    let text = "Chance every dam runs dry, October to March<br>Rainfall-only: " + fmt.chance(row.rain_only_chance) +
               "<br>DamDays Rating: " + fmt.chance(row.rating_chance);
    if (revealed) {
      text += "<br>" + (row.ran_dry === true ? "Ran dry" : row.ran_dry === false ? "Did not run dry" : "Unknown");
    }
    return text;
  }

  // ---- Scoreboard -----------------------------------------------------------
  /** One AUC in plain words: "81 in 100", with the AUC and its range underneath. */
  function aucCell(result) {
    if (!result) return "<td>not enough data</td>";
    return '<td><span class="score-big">' + Math.round(result.value * 100) + "</span> in 100" +
           '<span class="score-range">AUC ' + fmt.auc(result) + "</span></td>";
  }

  function scoreRow(label, line) {
    if (!line || line.n_ran_dry < DamDays.settings.minDryCellsForScore) {
      const dry = line ? line.n_ran_dry : 0;
      return '<tr><th scope="row">' + esc(label) + '<span class="score-range">' + fmt.count(dry, "cell") +
             ' ran dry</span></th><td colspan="2">Too few dry cells to score fairly.</td></tr>';
    }
    return '<tr><th scope="row">' + esc(label) + '<span class="score-range">' + line.n_ran_dry.toLocaleString("en-AU") + " of " +
           line.n_cells.toLocaleString("en-AU") + " cells ran dry</span></th>" +
           aucCell(line.rain_only_auc) + aucCell(line.rating_auc) + "</tr>";
  }

  function scoreboardHtml() {
    const board = data.scoreboard;
    const thisSeason = board.rating.by_season.find((line) => line.season === season.season);
    const all = board.rating.all_seasons;
    const aucTip = fmt.tip("What is AUC?",
      "Take one cell that ran dry and one that did not. AUC is how often the score rates the dry one " +
      "as riskier. 0.5 is a coin toss; 1.0 is always right. The range in brackets is the 95% confidence range.");
    return '<h2 class="scoreboard-title">Scoreboard <span class="scoreboard-source">' + esc(board.source_label || "") +
           "</span></h2>" +
           '<p class="panel-small">How often each score puts a cell that ran dry ahead of one that did not ' +
           "(50 in 100 is a coin toss). " + aucTip + "</p>" +
           '<table class="score-table"><thead><tr><th scope="col"></th><th scope="col">Rainfall-only</th>' +
           '<th scope="col">DamDays Rating</th></tr></thead><tbody>' +
           scoreRow("This season (" + season.season + ")", thisSeason) +
           scoreRow(all.label || "All past seasons", all) +
           sealedRow(board) +
           "</tbody></table>";
  }

  /** The sealed region's line: its scores once opened, a placeholder before. Empty if the data has no such panel. */
  function sealedRow(board) {
    const panel = (board.panels || []).find((p) => p.key === "sealed");
    if (!panel) return "";
    if (panel.status === "scored" && panel.rating) {
      return scoreRow("Sealed region, all test seasons (scored once)", panel.rating);
    }
    return '<tr class="row-pending"><th scope="row">' + esc(panel.title) + '<span class="score-range">' +
           esc(panel.label || "") + '</span></th><td colspan="2">Not opened yet. Its scores appear here after ' +
           "the opening, scored once with the frozen model.</td></tr>";
  }

  return { init, show };
})();
