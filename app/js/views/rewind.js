/* views/rewind.js
 * Go back to a past date. The map shows the forecasts as they would have been
 * made then. "Reveal what happened" rings the dams that really did fall below a
 * third, and the panel shows a tally of hits and misses, plus a check of
 * whether the chances came true ("we expected about 5; 6 happened").
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.views.rewind = (function () {
  "use strict";

  const fmt = DamDays.format;
  const esc = (text) => DamDays.format.escapeHtml(text);

  let data = null;
  let issue = null;            // the past issue being shown
  let revealed = false;
  let selectedId = null;
  let map = null;
  const markers = new Map();   // dam_id -> Leaflet circle marker
  const el = {};               // page elements, looked up once

  /** Runs once, the first time the view is shown. */
  function init(loadedData) {
    data = loadedData;
    el.select = document.getElementById("rewind-issue");
    el.reveal = document.getElementById("rewind-reveal");
    el.note = document.getElementById("rewind-note");
    el.tally = document.getElementById("rewind-tally");
    el.card = document.getElementById("rewind-card");
    el.legend = document.getElementById("rewind-legend");
    el.panel = document.getElementById("rewind-panel");

    if (!data.pastIssues.length) {
      el.tally.innerHTML = '<p class="card-empty">This dataset has no past forecasts to rewind to.</p>';
      el.reveal.disabled = true;
      return;
    }
    data.pastIssues.forEach((past) => {
      const option = document.createElement("option");
      option.value = past.issue_date;
      option.textContent = fmt.date(past.issue_date);
      el.select.appendChild(option);
    });
    el.select.value = mostTellingIssue().issue_date;
    el.select.addEventListener("change", () => setIssue(el.select.value));
    el.reveal.addEventListener("click", toggleReveal);
    el.card.addEventListener("click", (event) => {
      if (event.target.closest('[data-action="close"]')) unselect();
    });

    map = DamDays.map.create("rewind-map");
    setIssue(el.select.value);
  }

  /** Runs every time the view is shown. */
  function show() {
    if (map) map.invalidateSize();
  }

  /** Start on the past date where the most dams fell below a third (the most telling one). */
  function mostTellingIssue() {
    const happened = (past) => past.rows.filter((r) => r.status === "forecast" && r.outcome === true).length;
    return data.pastIssues.reduce((best, past) => (happened(past) > happened(best) ? past : best));
  }

  /** Switch to another past date. Everything resets to "before the reveal". */
  function setIssue(issueDate) {
    issue = data.pastIssues.find((past) => past.issue_date === issueDate);
    revealed = false;
    selectedId = null;
    el.note.textContent = issue.note || "";
    el.card.innerHTML = "";
    if (map) drawMarkers();
    updateRevealState();
  }

  /** Remove old dots and draw this date's dams. */
  function drawMarkers() {
    markers.forEach((marker) => marker.remove());
    markers.clear();
    const points = [];
    issue.rows.forEach((row) => {
      const dam = data.damsById.get(row.dam_id);
      if (!dam) return;
      const marker = L.circleMarker([dam.lat, dam.lon], styleFor(row));
      marker.on("click", () => select(row.dam_id));
      marker.addTo(map);
      markers.set(row.dam_id, marker);
      points.push([dam.lat, dam.lon]);
    });
    DamDays.map.fitToPoints(map, points);
  }

  /** The look of one dot, given the reveal state and selection. */
  function styleFor(row) {
    return DamDays.map.damStyle({
      chance: row.chance,
      selected: row.dam_id === selectedId,
      // Dams without a forecast are not judged, so they never get a reveal ring.
      revealed: revealed && row.status === "forecast",
      outcome: row.outcome,
    });
  }

  /** The hover text of one dot; it says what happened only after the reveal. */
  function tooltipFor(row) {
    const dam = data.damsById.get(row.dam_id);
    let text = esc(dam.name) + ": " + (row.status === "forecast" ? fmt.percent(row.chance) : "no forecast");
    if (revealed && row.status === "forecast") {
      text += row.outcome === true ? " (fell below a third)" :
              row.outcome === false ? " (stayed above)" : " (unknown)";
    }
    return text;
  }

  /** Redraw every dot, legend, tally, card and button after a change. */
  function updateRevealState() {
    issue.rows.forEach((row) => {
      const marker = markers.get(row.dam_id);
      if (!marker) return;
      marker.setStyle(styleFor(row));
      marker.unbindTooltip();
      marker.bindTooltip(tooltipFor(row));
    });
    el.reveal.textContent = revealed ? "Hide what happened" : "Reveal what happened";
    el.reveal.setAttribute("aria-pressed", String(revealed));
    DamDays.colors.renderLegend(el.legend, {
      title: "Chance of falling below a third in the " + data.meta.horizon_days + " days after " + fmt.date(issue.issue_date),
      showNoForecast: true,
      extraItems: revealed ? [
        { swatchClass: "swatch-ring", label: "Black ring: it did fall below a third" },
        { swatchClass: "swatch-faded", label: "Faded: it stayed above (dashed: unknown)" },
      ] : [],
    });
    el.tally.innerHTML = revealed ? tallyHtml() : beforeRevealHtml();
    if (selectedId) renderCard();
  }

  function toggleReveal() {
    revealed = !revealed;
    updateRevealState();
  }

  /** Open a dam's card. */
  function select(damId) {
    const previous = selectedId;
    selectedId = damId;
    [previous, damId].forEach((id) => {
      const marker = id && markers.get(id);
      if (marker) marker.setStyle(styleFor(issue.rowsByDam.get(id)));
    });
    markers.get(damId).bringToFront();
    renderCard();
  }

  /** Close the card (the tally stays). */
  function unselect() {
    const previous = selectedId;
    selectedId = null;
    const marker = previous && markers.get(previous);
    if (marker) marker.setStyle(styleFor(issue.rowsByDam.get(previous)));
    el.card.innerHTML = "";
  }

  /** Show the card (it sits above the tally in the side panel). */
  function renderCard() {
    el.card.innerHTML =
      '<button type="button" class="button button-link" data-action="close">&times; Close this dam</button>' +
      DamDays.damCard.render(data, selectedId, issue, { rewind: true, revealed: revealed });
    DamDays.damCard.bringIntoView(el.panel);
  }

  // ---- The panel text -------------------------------------------------------
  function beforeRevealHtml() {
    const forecast = issue.rows.filter((r) => r.status === "forecast");
    return '<h2 class="panel-title">' + fmt.date(issue.issue_date) + "</h2>" +
           '<p class="panel-lead">' + fmt.count(forecast.length, "dam") + " had a forecast on this day.</p>" +
           '<p class="panel-small">Press <strong>Reveal what happened</strong> to compare these forecasts with ' +
           "what the satellites saw over the next " + data.meta.horizon_days + " days. Click a dam to see its card.</p>";
  }

  /** Count hits and misses, using the "likely" line from settings.js. */
  function countTally(judged) {
    const likely = DamDays.settings.likelyThreshold;
    const tally = { hits: 0, falseAlarms: 0, misses: 0, allClears: 0 };
    judged.forEach((row) => {
      const saidLikely = row.chance >= likely;
      if (saidLikely && row.outcome) tally.hits += 1;
      else if (saidLikely) tally.falseAlarms += 1;
      else if (row.outcome) tally.misses += 1;
      else tally.allClears += 1;
    });
    return tally;
  }

  /** For each colour band: how many dams, how many we expected to fall, how many did. */
  function bandCheck(judged) {
    return DamDays.settings.chanceBands.map((band) => {
      const inBand = judged.filter((row) => DamDays.colors.bandFor(row.chance) === band);
      return {
        band: band,
        dams: inBand.length,
        expected: inBand.reduce((sum, row) => sum + row.chance, 0),
        happened: inBand.filter((row) => row.outcome).length,
      };
    }).filter((line) => line.dams > 0);
  }

  function tallyHtml() {
    const forecast = issue.rows.filter((r) => r.status === "forecast");
    const judged = forecast.filter((r) => r.outcome !== null);
    const unknown = forecast.length - judged.length;
    if (!judged.length) {
      return '<p class="card-empty">No forecasts from this date can be checked yet.</p>';
    }
    const happened = judged.filter((r) => r.outcome).length;
    const expected = judged.reduce((sum, r) => sum + r.chance, 0);
    const t = countTally(judged);
    const likelyPct = Math.round(DamDays.settings.likelyThreshold * 100);
    const windowEnd = fmt.addDays(issue.issue_date, data.meta.horizon_days);

    const bandRows = bandCheck(judged).map((line) =>
      "<tr><th scope=\"row\"><span class=\"swatch\" style=\"background:" + line.band.color + "\" aria-hidden=\"true\"></span>" +
      esc(line.band.label) + "</th><td>" + line.dams + "</td><td>" + line.expected.toFixed(1) +
      "</td><td>" + line.happened + "</td></tr>").join("");

    return '<h2 class="panel-title">What happened</h2>' +
      '<p class="panel-lead"><strong>' + happened + " of " + judged.length + "</strong> dams fell below a third by about " +
      fmt.date(windowEnd) + ". The forecasts expected about <strong>" + Math.round(expected) + "</strong>.</p>" +
      '<table class="tally-table"><caption>Hits and misses (we said "likely" at ' + likelyPct + "% or more)</caption>" +
      '<thead><tr><th scope="col"></th><th scope="col">Fell below a third</th><th scope="col">Stayed above</th></tr></thead>' +
      '<tbody><tr><th scope="row">We said likely</th><td>' + fmt.count(t.hits, "hit") + "</td><td>" +
      fmt.count(t.falseAlarms, "false alarm") + "</td></tr>" +
      '<tr><th scope="row">We said unlikely</th><td>' + fmt.count(t.misses, "miss", "misses") + "</td><td>" +
      fmt.count(t.allClears, "correct all-clear") + "</td></tr></tbody></table>" +
      '<table class="band-table"><caption>Did the chances come true?</caption>' +
      '<thead><tr><th scope="col">Chance we gave</th><th scope="col">Dams</th><th scope="col">Expected to fall</th>' +
      '<th scope="col">Did fall</th></tr></thead><tbody>' + bandRows + "</tbody></table>" +
      '<p class="panel-small">Expected = the chances added up: ten dams at 30% each means about 3 should fall. ' +
      "Not counted: " + fmt.count(unknown, "dam") + " with too few clear satellite looks to know.</p>";
  }

  return { init, show };
})();
