/* views/rating.js (legacy wrapper, WP-F)
 * The Area outlook (#outlook; #rating is an alias): set aside to focus on farmers, its result still
 * reported (UI_SPEC 3.7). Two maps side by side, moving together:
 *   Left:  a rainfall-only score for each 2 km area (what most drought tools use).
 *   Right: the DamDays outlook for the same areas.
 * "Reveal what happened" rings the areas where every dam fell to ~0% full (no water seen at a clear
 * look) between October and March. The scoreboard (ranking scores, AUC) sits inside a "For specialists"
 * disclosure, each line with its plain words. Never "ran dry": a 0% reading is "no water seen".
 * Also registers the "outlook" view with the router (it mounts this legacy view).
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
  let specialistsOpen = false;   // "For specialists" stays as the reader left it across Hide / Reveal
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

  /** Show hexagons when zoomed in, dots when zoomed out (see css/legacy.css: .zoomed-in). */
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
      : "Rated on " + fmt.date(season.issue_date) + ", before the season. Judged on what happened from October to March.";
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
    el.reveal.textContent = revealed ? "Hide what happened" : "Reveal what happened";
    el.reveal.setAttribute("aria-pressed", String(revealed));
    DamDays.colors.renderLegend(el.legend, {
      title: "Chance that every dam in the area falls to ~0% full (no water seen at a clear look), October to March",
      showNoForecast: false,
      extraItems: revealed ? [
        // "thick", not "black": in dark mode the ring is drawn light (legacy.css), so the words hold in both themes
        { swatchClass: "swatch-ring", label: "Thick ring: every dam in it fell to ~0% full" },
        { swatchClass: "swatch-faded", label: "Faded: some water was still seen" },
      ] : [],
    });
    // the specialists' disclosure keeps its open state when the reveal redraws it
    const was = el.scoreboard.querySelector(".outlook-specialists");
    if (was) specialistsOpen = was.open;
    el.scoreboard.innerHTML = revealed ? revealSummaryHtml() + scoreboardHtml() : "";
    const now = el.scoreboard.querySelector(".outlook-specialists");
    if (now) {
      now.open = specialistsOpen;
      now.addEventListener("toggle", () => { specialistsOpen = now.open; });
    }
  }

  function cellTooltip(row) {
    let text = "Chance every dam falls to ~0% full, October to March<br>Rainfall-only: " + fmt.chance(row.rain_only_chance) +
               "<br>DamDays outlook: " + fmt.chance(row.rating_chance);
    if (revealed) {
      text += "<br>" + (row.ran_dry === true ? "Every dam fell to ~0% full" : row.ran_dry === false ? "Some water still seen" : "Unknown");
    }
    return text;
  }

  /** After the reveal, in plain words: how many areas saw every dam fall to ~0% full this season, then which score did better. */
  function revealSummaryHtml() {
    const judged = season.rows.filter((r) => r.ran_dry === true || r.ran_dry === false);
    const fell = judged.filter((r) => r.ran_dry === true).length;
    if (!judged.length) return "";
    return '<p class="outlook-summary">In the ' + esc(season.season) + " season, <strong>" + fell.toLocaleString("en-AU") + " of " +
           judged.length.toLocaleString("en-AU") + "</strong> areas saw every dam in them fall to ~0% full between October and March " +
           "(no water seen at a clear look). The thick rings show which.</p>" + resultHtml();
  }

  /**
   * The result, outside the specialists' disclosure: how often each score put an area where every dam fell to ~0%
   * full ahead of one that kept water, this season and across all test seasons, and the pass mark written before
   * the code. Only scoreboard.json numbers (rating.by_season, rating.all_seasons, the dev_test panel's pass_bar_met).
   */
  function resultHtml() {
    const board = data.scoreboard;
    if (!board || !board.rating) return "";
    const line = (board.rating.by_season || []).find((x) => x.season === season.season);
    const all = board.rating.all_seasons;
    const inHundred = (r) => (r && typeof r.value === "number" ? Math.round(r.value * 100) : null);
    const enough = (x) => x && x.n_ran_dry >= DamDays.settings.minDryCellsForScore;
    const devPanel = (board.panels || []).find((p) => p.key === "dev_test");
    const mark = devPanel && devPanel.rating && typeof devPanel.rating.pass_bar_met === "boolean" ? devPanel.rating.pass_bar_met : null;
    const parts = [];
    if (enough(line) && inHundred(line.rating_auc) !== null && inHundred(line.rain_only_auc) !== null) {
      const dd = inHundred(line.rating_auc), rain = inHundred(line.rain_only_auc);
      parts.push('<div class="outlook-vs" role="group" aria-label="This season, how often each score ranked an area that fell to ~0% full ahead of one that kept water">' +
        '<div><span class="ov-n"><span class="score-big">' + rain + '</span> in 100</span><span class="ov-who">Rainfall-only</span></div>' +
        '<div class="is-ours"><span class="ov-n"><span class="score-big">' + dd + '</span> in 100</span><span class="ov-who">DamDays outlook</span></div></div>');
      parts.push("<p>Ranked by risk this season, the DamDays outlook put an area where every dam fell to ~0% full ahead of one that kept water " +
        "<strong>" + dd + " times in 100</strong>; rainfall alone, " + rain + " in 100 (a coin toss is 50).</p>");
    } else if (line) {
      parts.push("<p>This season had too few areas where every dam fell to ~0% full to score fairly.</p>");
    }
    if (enough(all) && inHundred(all.rating_auc) !== null && inHundred(all.rain_only_auc) !== null) {
      const span = /(\d{4}-\d{2}) to (\d{4}-\d{2})/.exec(all.label || "");
      parts.push("<p>Across all test seasons" + (span ? " " + esc(span[1] + " to " + span[2]) : "") + ", years it never trained on: <strong>" +
        inHundred(all.rating_auc) + "</strong> against " + inHundred(all.rain_only_auc) + "." +
        (mark !== null ? " Its pass mark, written before the build began: <strong>" + (mark ? "met" : "not met") + "</strong>." : "") + "</p>");
    }
    return parts.length ? '<div class="outlook-result">' + parts.join("") + "</div>" : "";
  }

  // ---- Scoreboard (for specialists) -------------------------------------------
  /** One AUC in plain words: "81 in 100", with the AUC and its range underneath. */
  function aucCell(result, label) {
    const at = label ? ' data-label="' + esc(label) + '"' : "";
    if (!result) return "<td" + at + ">not enough data</td>";
    return "<td" + at + '><span class="score-big">' + Math.round(result.value * 100) + "</span> in 100" +
           '<span class="score-range">AUC ' + fmt.auc(result) + "</span></td>";
  }

  function scoreRow(label, line) {
    if (!line || line.n_ran_dry < DamDays.settings.minDryCellsForScore) {
      const fell = line ? line.n_ran_dry : 0;
      return '<tr><th scope="row">' + esc(label) + '<span class="score-range">' + fmt.count(fell, "area") +
             ' fell to ~0% full</span></th><td colspan="2">Too few such areas to score fairly.</td></tr>';
    }
    return '<tr><th scope="row">' + esc(label) + '<span class="score-range">' + line.n_ran_dry.toLocaleString("en-AU") + " of " +
           line.n_cells.toLocaleString("en-AU") + " areas fell to ~0% full</span></th>" +
           aucCell(line.rain_only_auc, "Rainfall-only") + aucCell(line.rating_auc, "DamDays outlook") + "</tr>";
  }

  function scoreboardHtml() {
    const board = data.scoreboard;
    if (!board || !board.rating) return "";
    const thisSeason = (board.rating.by_season || []).find((line) => line.season === season.season);
    const all = board.rating.all_seasons;
    return '<details class="more outlook-specialists"><summary><span>For specialists: how the two scores compare</span>' +
           (DamDays.icon ? DamDays.icon("i-plus", "plus") : "") + '</summary><div class="body">' +
           '<p class="panel-small">Each number says how often a score puts an area where every dam fell to ~0% full ahead of one ' +
           "that kept water: 50 in 100 is a coin toss, 100 in 100 always right. Underneath: the same as a ranking score " +
           "(AUC, 0.5 to 1.0) with the range it would likely fall in if the areas were re-drawn (95 in 100 times). " +
           esc(board.source_label || "") + ".</p>" +
           '<div class="table-scroll"><table class="score-table"><thead><tr><th scope="col"></th><th scope="col">Rainfall-only</th>' +
           '<th scope="col">DamDays outlook</th></tr></thead><tbody>' +
           scoreRow("This season (" + season.season + ")", thisSeason) +
           (all ? scoreRow(all.label || "All past seasons", all) : "") +
           sealedRow(board) +
           "</tbody></table></div></div></details>";
  }

  /** The sealed region's line: its scores once opened, a placeholder before. Empty if the data has no such panel. */
  function sealedRow(board) {
    const panel = (board.panels || []).find((p) => p.key === "sealed");
    if (!panel) return "";
    if (panel.status === "scored" && panel.rating) {
      return scoreRow("Sealed region, all test seasons (scored once)", panel.rating);
    }
    // The panel's own title names the old 17:30 slot; until it is scored, say only that it is not opened yet (as About does).
    return '<tr class="row-pending"><th scope="row">Sealed region (the unseen exam)<span class="score-range">' +
           esc(panel.label || "") + '</span></th><td colspan="2">Not opened yet. Its scores appear here after ' +
           "the opening, scored once.</td></tr>";
  }

  return { init, show };
})();

/* The Area outlook page (#outlook): the legacy view above, mounted into its section. Its intro (the
 * "Set aside" tag, the heading and the plain paragraph) is in index.html's legacy markup. */
(function () {
  "use strict";
  const D = window.DamDays;
  if (!D.router || typeof D.router.register !== "function") return;
  let mounted = false;
  D.router.register("outlook", {
    render(root) {
      root.innerHTML = '<div class="wrap outlook-page"></div>';
      return D.legacy.mount("rating", root.firstChild).then((ok) => {
        mounted = ok;
        if (!ok) {
          root.firstChild.innerHTML = '<header class="page-head"><p class="eyebrow">Set aside</p><h1 id="outlook-h1">Area outlook</h1>' +
            "<p>This part could not be loaded. Check your signal and try again.</p></header>";
        }
      });
    },
    enter() {
      const v = D.views && D.views.rating;
      if (mounted && v && v.show) v.show();
    },
  });
})();
