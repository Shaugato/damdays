/* views/runway.js (legacy wrapper, WP-F)
 * The interactive region map (Leaflet, needs signal). The Runway page (views/region.js) mounts it
 * with DamDays.legacy.mount("runway", ...) under "Open the interactive map". Every dam in the region,
 * coloured by the chance it falls below a third in the next 90 days ("3 in 10"). Tapping a dot opens
 * that dam's sheet (#runway/dam-<dam_id>); without the router it opens the old card in the side panel.
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
      title: "Chance of dropping below a third in the next " + data.meta.horizon_days + " days",
      showNoForecast: true,
      showLow: true,
    });
    map = DamDays.map.create("runway-map");
    // half zoom steps: the region fills the card it opens in (in place of the Runway sketch), not one step out
    if (map) { map.options.zoomSnap = 0.5; map.options.zoomDelta = 0.5; addMarkers(); }
    showSummary();
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
      const marker = L.circleMarker([dam.lat, dam.lon], DamDays.map.damStyle({ chance: row.chance, low: row.status === "already_low" }));
      // "auto": the tooltip opens on the side with room, so it is never cut off at the map's edge on a phone
      marker.bindTooltip(tooltipFor(dam, row), { direction: "auto", className: "dam-tip" });
      marker.on("click", () => select(row.dam_id));
      marker.addTo(map);
      markers.set(row.dam_id, marker);
      points.push([dam.lat, dam.lon]);
    });
    DamDays.map.fitToPoints(map, points);
  }

  /** A dam's days in a few words, counted from the text's date. A 0% dam is "no water seen", never "dry". */
  function daysWords(row) {
    if (row.status === "already_low") return row.level_pct === 0 ? "no water seen at its last look" : "already below a third";
    if (row.status === "not_refilled") return "no forecast until it refills";
    if (row.status !== "forecast" || row.damdays_days === null) return "no recent clear look";
    const since = data.textDate && row.issued_on
      ? Math.max(0, DamDays.text.dayNumber(data.textDate) - DamDays.text.dayNumber(row.issued_on)) : 0;
    const left = row.damdays_days - since;
    return left <= 0 ? "may be below a third now" : DamDays.text.floorText(left);
  }

  /** The hover text of a dot: "Dam 408: at least 29 days; 3 in 10 chance it drops below a third by 12 Dec 2026". */
  function tooltipFor(dam, row) {
    let text = esc(dam.name) + ": " + esc(daysWords(row));
    if (row.status === "forecast") text += "; " + fmt.chance(row.chance) + " chance it drops below a third by " + fmt.date(row.window_end);
    return text;
  }

  /** Redraw one dot (for example after it is selected or unselected). */
  function restyle(damId) {
    const marker = markers.get(damId);
    if (!marker) return;
    const row = issue.rowsByDam.get(damId);
    marker.setStyle(DamDays.map.damStyle({ chance: row.chance, low: row.status === "already_low", selected: damId === selectedId }));
    if (damId === selectedId) marker.bringToFront();
  }

  /** Ring a dam on the map (the Runway page calls this when a dam's sheet opens or closes). */
  function highlight(damId) {
    const previous = selectedId;
    selectedId = damId || null;
    if (previous && previous !== selectedId) restyle(previous);
    if (selectedId) restyle(selectedId);
    // a dam picked elsewhere (the list, the sketch) and out of this map's view: pan to it, so its ring shows
    const dam = selectedId && data ? data.damsById.get(selectedId) : null;
    if (map && dam && map.getSize().x > 0 && !map.getBounds().pad(-0.08).contains([dam.lat, dam.lon])) map.panTo([dam.lat, dam.lon]);
  }

  /** A dot or a list button was picked: open its sheet (the new app), or the old card in the panel. */
  function select(damId) {
    const host = document.getElementById("v-runway");
    if (DamDays.router && host && panel && host.contains(panel)) {
      highlight(damId);
      // a dam's sheet already open beside the map (desktop): swap it, one level, never a stack
      DamDays.router.go("#runway/dam-" + damId, { replace: Boolean(DamDays.sheet && DamDays.sheet.isOpen()) });
      return;
    }
    highlight(damId);
    panel.innerHTML =
      '<button type="button" class="button button-link" data-action="back">&larr; All dams</button>' +
      DamDays.damCard.render(data, damId, issue, { rewind: false, revealed: false });
    const dam = data.damsById.get(damId);
    if (map && dam) map.panTo([dam.lat, dam.lon]);
    DamDays.damCard.bringIntoView(panel);
  }

  /** Close the card and go back to the area summary. */
  function unselect() {
    highlight(null);
    showSummary();
  }

  /** The area summary: how many dams, how many likely to drop below a third, and the most likely few. */
  function showSummary() {
    const rows = issue.rows;
    const forecast = rows.filter((r) => r.status === "forecast");
    const likely = forecast.filter((r) => DamDays.colors.isLikely(r.chance));
    const countOf = (status) => rows.filter((r) => r.status === status).length;
    const top = forecast.slice().sort((a, b) => b.chance - a.chance).slice(0, DamDays.settings.topDamsToList);
    const lastLook = rows.map((r) => r.issued_on).filter(Boolean).sort().pop();

    const topItems = top.map((row) => {
      const dam = data.damsById.get(row.dam_id);
      return '<li><button type="button" class="dam-pick" data-dam="' + esc(row.dam_id) + '">' +
             '<span class="swatch" style="background:' + DamDays.colors.colorFor(row.chance) + '" aria-hidden="true"></span>' +
             '<span class="dam-pick-name">' + esc(dam.name) + ' <span class="dam-pick-days">' + esc(daysWords(row)) +
             "</span></span><strong>" + fmt.chance(row.chance) + "</strong></button></li>";
    }).join("");

    panel.innerHTML =
      '<h2 class="panel-title">' + esc(data.meta.region.name) + "</h2>" +
      '<p class="panel-lead"><strong>' + fmt.count(likely.length, "dam") + "</strong> of " + forecast.length +
      (likely.length === 1 ? " has a " : " have a ") + DamDays.settings.likelyInTen +
      " in 10 chance or more of dropping below a third in the next " + data.meta.horizon_days + " days.</p>" +
      '<p class="panel-small">Based on satellite looks up to ' + fmt.date(lastLook) + "." +
      (data.textDate ? " Days of water are counted from " + DamDays.text.dateText(data.textDate) + " " +
       data.textDate.slice(0, 4) + ", the day of this week's text." : "") + "</p>" +
      '<h3 class="panel-subtitle">Highest chance of dropping below a third</h3>' +
      '<ul class="dam-list">' + topItems + "</ul>" +
      '<p class="panel-small">No forecast for ' + countOf("already_low") + " dams already below a third, " +
      countOf("not_refilled") + " not refilled lately, and " + countOf("no_recent_look") +
      " with no recent clear look.</p>" +
      '<p class="panel-hint">Tap any dot on the map to open that dam.</p>' +
      '<p class="panel-small">Farmers get this as one text a week: <a href="#farm/setup">set up My farm</a>.</p>';
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

  return { init, show, highlight };
})();
