/* views/runway.js
 * The regional map. Every farm dam in the region, coloured by the chance it
 * falls below a third in the next 90 days ("3 in 10"). Pick a dam (on the map
 * or in the list) to open its card, which leads with its days of water. With no
 * dam picked, the side panel shows a summary of the area.
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.views.runway = (function () {
  "use strict";

  const fmt = DamDays.format;
  const esc = (text) => DamDays.format.escapeHtml(text);

  let data = null;
  let issue = null;            // today's ("live") forecasts
  let map = null;
  const markers = new Map();   // dam_id -> Leaflet circle marker
  let selectedId = null;
  let panel = null;

  /** Runs once, the first time the view is shown. */
  function init(loadedData) {
    data = loadedData;
    issue = data.liveIssue;
    panel = document.getElementById("runway-panel");
    if (!issue) {
      panel.innerHTML = '<p class="card-empty">This dataset has no current forecast.</p>';
      return;
    }
    DamDays.colors.renderLegend(document.getElementById("runway-legend"), {
      title: "Chance of falling below a third in the next " + data.meta.horizon_days + " days",
      showNoForecast: true,
    });
    map = DamDays.map.create("runway-map");
    if (map) addMarkers();
    showSummary();
    // Clicks on "Highest chance" buttons and the "back" button inside the panel.
    panel.addEventListener("click", onPanelClick);
  }

  /** Runs every time the view is shown (maps need a nudge after being hidden). */
  function show() {
    if (map) map.invalidateSize();
  }

  /** One dot per dam, coloured by its chance. */
  function addMarkers() {
    const points = [];
    issue.rows.forEach((row) => {
      const dam = data.damsById.get(row.dam_id);
      if (!dam) return;
      const marker = L.circleMarker([dam.lat, dam.lon], DamDays.map.damStyle({ chance: row.chance }));
      marker.bindTooltip(tooltipFor(dam, row));
      marker.on("click", () => select(row.dam_id));
      marker.addTo(map);
      markers.set(row.dam_id, marker);
      points.push([dam.lat, dam.lon]);
    });
    DamDays.map.fitToPoints(map, points);
  }

  /** The hover text of a dot: "Dam 408: at least 29 days; 3 in 10 chance below a third by 12 Dec 2026". */
  function tooltipFor(dam, row) {
    let text = esc(dam.name) + ": " + DamDays.damCard.daysWords(row, data.textDate);
    if (row.status === "forecast") {
      text += "; " + fmt.chance(row.chance) + " chance below a third by " + fmt.date(row.window_end);
    }
    return text;
  }

  /** Redraw one dot (for example after it is selected or unselected). */
  function restyle(damId) {
    const marker = markers.get(damId);
    if (!marker) return;
    const row = issue.rowsByDam.get(damId);
    marker.setStyle(DamDays.map.damStyle({ chance: row.chance, selected: damId === selectedId }));
    if (damId === selectedId) marker.bringToFront();
  }

  /** Open a dam's card and highlight it on the map. */
  function select(damId) {
    const previous = selectedId;
    selectedId = damId;
    if (previous) restyle(previous);
    restyle(damId);
    panel.innerHTML =
      '<button type="button" class="button button-link" data-action="back">&larr; All dams</button>' +
      DamDays.damCard.render(data, damId, issue, { rewind: false, revealed: false });
    const dam = data.damsById.get(damId);
    if (map && dam) map.panTo([dam.lat, dam.lon]);
    DamDays.damCard.bringIntoView(panel);
  }

  /** Close the card and go back to the area summary. */
  function unselect() {
    const previous = selectedId;
    selectedId = null;
    if (previous) restyle(previous);
    showSummary();
  }

  /** The area summary: how many dams, how many at high risk, and the riskiest few. */
  function showSummary() {
    const rows = issue.rows;
    const forecast = rows.filter((r) => r.status === "forecast");
    const likely = forecast.filter((r) => DamDays.colors.isLikely(r.chance));
    const countOf = (status) => rows.filter((r) => r.status === status).length;
    const top = forecast.slice().sort((a, b) => b.chance - a.chance).slice(0, DamDays.settings.topDamsToList);
    const lastLook = rows.map((r) => r.issued_on).sort().pop();

    const topItems = top.map((row) => {
      const dam = data.damsById.get(row.dam_id);
      return '<li><button type="button" class="dam-pick" data-dam="' + esc(row.dam_id) + '">' +
             '<span class="swatch" style="background:' + DamDays.colors.colorFor(row.chance) + '" aria-hidden="true"></span>' +
             "<span>" + esc(dam.name) + '<span class="dam-pick-days">' + DamDays.damCard.daysWords(row, data.textDate) +
             "</span></span><strong>" + fmt.chance(row.chance) + "</strong></button></li>";
    }).join("");

    panel.innerHTML =
      '<h2 class="panel-title">' + esc(data.meta.region.name) + "</h2>" +
      '<p class="panel-lead"><strong>' + fmt.count(likely.length, "dam") + "</strong> of " + forecast.length +
      (likely.length === 1 ? " has a " : " have a ") + DamDays.settings.likelyInTen +
      " in 10 chance or more of falling below a third in the next " + data.meta.horizon_days + " days.</p>" +
      '<p class="panel-small">Based on satellite looks up to ' + fmt.date(lastLook) + "." +
      (data.textDate ? " Days of water are counted from " + DamDays.text.dateText(data.textDate) + " " +
       data.textDate.slice(0, 4) + ", the day of this week's text." : "") + "</p>" +
      '<h3 class="panel-subtitle">Highest chance of falling below a third</h3>' +
      '<ul class="dam-list">' + topItems + "</ul>" +
      '<p class="panel-small">No forecast for ' + countOf("already_low") + " dams already below a third, " +
      countOf("not_refilled") + " not refilled lately, and " + countOf("no_recent_look") +
      " with no recent clear look.</p>" +
      '<p class="panel-hint">Tip: click any dot on the map to open that dam.</p>' +
      '<p class="panel-small">Farmers get this as one text a week: <a href="#farm">set up My farm</a>.</p>';
  }

  /** Handle clicks inside the side panel. */
  function onPanelClick(event) {
    const pick = event.target.closest("[data-dam]");
    if (pick) {
      select(pick.getAttribute("data-dam"));
      return;
    }
    if (event.target.closest('[data-action="back"]')) unselect();
  }

  return { init, show };
})();
