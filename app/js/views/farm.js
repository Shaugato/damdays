/* views/farm.js
 * MY FARM: the farmer product. Farmers don't open apps or emails, so DamDays is
 * one text message a week (mentor feedback, Fri 2 Oct 2026). This view is where a
 * farm is set up and where the farmer looks deeper:
 *
 *   1. set the homestead: click the map (or drag the house), or pick a demo farm;
 *   2. set the radius: the farm's dams are every farm dam the satellites can see
 *      within it (we have no property boundaries), numbered by distance: Dam 1
 *      is the closest;
 *   3. see the weekly text on a phone, exactly as it would arrive, and the list of
 *      dams: how full each one is, its days of water and its chance;
 *   4. tap a dam for its full card (days, chance, runway curve, water history);
 *   5. judge our accuracy on their own dams: each dam's track record in the 2016-2026
 *      backtest (how often the cautious days-left promise held on it), and the farm's
 *      dams added up (track_record.json, scripts/18_track_record.py).
 *
 * The text is made in the browser by js/text.js, a line-for-line port of the
 * Python that writes the real texts (notify/message.py); app/tools/check_text_port.js
 * checks that both write the same text. Days are counted from the day of this
 * week's text (farms.json's date). "%" only ever means how full a dam is; a
 * chance is written "3 in 10".
 */
window.DamDays = window.DamDays || {};
DamDays.views = DamDays.views || {};

DamDays.views.farm = (function () {
  "use strict";

  const fmt = DamDays.format;
  const txt = DamDays.text;
  const esc = (text) => DamDays.format.escapeHtml(text);

  const DEFAULT_FARM = "farm-d";          // Farm D (near Dubbo), the farm in the spec and the video
  const MAX_RADIUS_KM = 10;

  let data = null;
  let appForecasts = null;    // the app's live forecasts, as a forecasts.json document
  let textDate = null;        // the day of this week's text ("YYYY-MM-DD")
  let map = null;
  const layers = {};          // homestead, circle, farmDams (Leaflet layers)
  const el = {};              // page elements, looked up once
  const state = {
    demo: null,               // the demo farm picked (an entry of farms.json), or null
    lat: null,
    lon: null,
    radiusKm: txt.DEFAULT_RADIUS_KM,
    dams: [],                 // the farm's dams, numbered by distance (js/text.js damsForFarm)
    selectedId: null,         // the dam whose card is open, or null (the text is shown)
  };

  // ---- Start ----------------------------------------------------------------
  /** Runs once, the first time the view is shown. */
  function init(loadedData) {
    data = loadedData;
    textDate = data.textDate;
    appForecasts = data.liveIssue ? { dams: data.dams, issues: [data.liveIssue] } : null;
    ["pick", "radius", "note", "panel", "dams", "legend"].forEach((name) => {
      el[name] = document.getElementById("farm-" + name);
    });
    el.radiusOut = document.getElementById("farm-radius-out");

    fillPicker();
    el.pick.addEventListener("change", () => {
      if (el.pick.value !== "custom") pickDemo(el.pick.value);
    });
    el.radius.max = MAX_RADIUS_KM;
    el.radius.addEventListener("input", () => setRadius(Number(el.radius.value), false));
    el.radius.addEventListener("change", () => setRadius(Number(el.radius.value), true));
    el.panel.addEventListener("click", onClick);
    el.dams.addEventListener("click", onClick);

    DamDays.colors.renderLegend(el.legend, {
      title: "Dot colour: chance of falling below a third in the next " + data.meta.horizon_days + " days",
      showNoForecast: true,
      extraItems: [
        { swatchClass: "swatch-home", label: "Homestead: click the map or drag it" },
        { swatchClass: "swatch-radius", label: "How far your dams go" },
      ],
    });

    map = DamDays.map.create("farm-map");
    if (map) {
      drawRegionDams();
      map.on("click", (event) => setHomestead(event.latlng.lat, event.latlng.lng));
    }

    const farms = data.farms ? data.farms.farms : [];
    const first = farms.find((f) => f.farm_id === DEFAULT_FARM) || farms.find((f) => f.dams_in_app) || farms[0];
    if (first) {
      el.pick.value = first.farm_id;
      pickDemo(first.farm_id);
    } else {
      showEmpty();
    }
  }

  /** Runs every time the view is shown (maps need a nudge after being hidden). */
  function show() {
    if (map) map.invalidateSize();
  }

  /** The demo farms in the picker, grouped by region, and a "Your farm" line once the map is clicked. */
  function fillPicker() {
    const farms = data.farms ? data.farms.farms : [];
    const groups = new Map();
    farms.forEach((f) => {
      const label = f.region_name + (f.dams_in_app ? " (on this map)" : "");
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(f);
    });
    let html = "";
    groups.forEach((list, label) => {
      html += '<optgroup label="' + esc(label) + '">' + list.map((f) =>
        '<option value="' + esc(f.farm_id) + '">' + esc(f.name) + ", " + fmt.count(f.dams.length, "dam") +
        "</option>").join("") + "</optgroup>";
    });
    html += '<option value="custom" disabled>Your farm (click the map to set it)</option>';
    el.pick.innerHTML = html;
  }

  // ---- Setting the farm -----------------------------------------------------
  /** Pick one of farms.json's demo farms. */
  function pickDemo(farmId) {
    const farm = data.farms.farms.find((f) => f.farm_id === farmId);
    if (!farm) return;
    state.demo = farm;
    state.lat = farm.lat;
    state.lon = farm.lon;
    state.radiusKm = farm.radius_km;
    state.selectedId = null;
    // Outside the app's region only the farm's own dams (within its radius) are in the data.
    el.radius.max = farm.dams_in_app ? MAX_RADIUS_KM : farm.radius_km;
    el.radius.value = farm.radius_km;
    update(true);
  }

  /** Put the homestead where the map was clicked (or the house was dragged to). */
  function setHomestead(lat, lon) {
    if (!appForecasts) return;
    state.demo = null;
    state.lat = Math.round(lat * 1e5) / 1e5;
    state.lon = Math.round(lon * 1e5) / 1e5;
    state.selectedId = null;
    el.radius.max = MAX_RADIUS_KM;
    const custom = el.pick.querySelector('option[value="custom"]');
    custom.disabled = false;
    custom.textContent = "Your farm (set on the map)";
    el.pick.value = "custom";
    update(false);
  }

  function setRadius(km, settle) {
    state.radiusKm = km;
    update(settle);
  }

  /** The farm as js/text.js wants it. */
  function currentFarm() {
    return {
      farm_id: state.demo ? state.demo.farm_id : "my-farm",
      name: state.demo ? state.demo.name : "Your farm",
      lat: state.lat,
      lon: state.lon,
      radius_km: state.radiusKm,
    };
  }

  /** The forecasts the farm's dams come from: the app's, or a demo farm's own dams outside the app's region. */
  function sourceForecasts() {
    if (state.demo && !state.demo.dams_in_app) return txt.docFromDams(state.demo.dams);
    return appForecasts;
  }

  // ---- Redraw ---------------------------------------------------------------
  /** Find the farm's dams, make the text, and redraw the map, the list and the panel. */
  function update(fitMap) {
    const farm = currentFarm();
    el.radiusOut.textContent = farm.radius_km + " km";
    let sms;
    let long;
    try {
      state.dams = txt.damsForFarm(farm, sourceForecasts());
      sms = txt.smsForDams(state.dams, textDate, farm.radius_km);
      long = txt.longForDams(state.dams, textDate, farm.name, farm.radius_km, records());
      if (!state.dams.some((d) => d.dam_id === state.selectedId)) state.selectedId = null;   // it left the radius
    } catch (error) {
      el.panel.innerHTML = '<p class="load-error">The text could not be made: ' + esc(error.message) + "</p>";
      return;
    }
    el.note.innerHTML = noteHtml(farm);
    drawFarm(farm, fitMap);
    el.dams.innerHTML = damTableHtml();
    if (state.selectedId) showCard(state.selectedId);
    else el.panel.innerHTML = textPanelHtml(farm, sms, long);
  }

  /** One line under the controls: whose farm this is, and anything to know about it. */
  function noteHtml(farm) {
    const count = fmt.count(state.dams.length, "farm dam") + " within " + farm.radius_km + " km";
    if (state.demo) {
      let html = "<strong>" + esc(state.demo.name) + "</strong> is a demo farm: its point sits in the middle " +
                 "of a real cluster of farm dams near " + esc(state.demo.near_town) +
                 ", but it is not a real homestead. " + count + ".";
      if (!state.demo.dams_in_app) {
        html += " It is in " + esc(state.demo.region_name) + ". This app's map holds " + esc(data.meta.region.name) +
                ", so here you see only this farm's own dams (up to " + state.demo.radius_km + " km), from this " +
                "week's texts, and their cards have no curve or history.";
      }
      return html;
    }
    let html = "<strong>Your homestead</strong> (" + state.lat.toFixed(5) + ", " + state.lon.toFixed(5) + "): " +
               count + ". Click elsewhere or drag the house to move it.";
    const box = data.meta.region.bbox;
    const inRegion = box && state.lat >= box[0] && state.lat <= box[1] && state.lon >= box[2] && state.lon <= box[3];
    if (!inRegion) {
      html += " This app has forecasts for " + esc(data.meta.region.name) + " only, so dams outside it are not shown.";
    }
    return html;
  }

  // ---- The map --------------------------------------------------------------
  /** Every dam of the app's region, small, so you can see where the dams are before you click. */
  function drawRegionDams() {
    if (!data.liveIssue) return;
    const points = [];
    data.liveIssue.rows.forEach((row) => {
      const dam = data.damsById.get(row.dam_id);
      if (!dam) return;
      const style = DamDays.map.damStyle({ chance: row.chance });
      style.radius = 4;
      style.interactive = false;         // a click goes to the map: it sets the homestead
      L.circleMarker([dam.lat, dam.lon], style).addTo(map);
      points.push([dam.lat, dam.lon]);
    });
    DamDays.map.fitToPoints(map, points);
  }

  /** The house icon for the homestead. */
  function houseIcon() {
    return L.divIcon({
      className: "home-icon",
      html: '<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true"><path d="M3 11.5 12 4l9 7.5V21h-6v-6H9v6H3z" ' +
            'fill="#1d1c1a" stroke="#ffffff" stroke-width="1.6" stroke-linejoin="round"/></svg>',
      iconSize: [30, 30],
      iconAnchor: [15, 22],
    });
  }

  /** The homestead, its radius and the farm's numbered dams. */
  function drawFarm(farm, fitMap) {
    if (!map) return;
    const centre = [farm.lat, farm.lon];
    if (!layers.homestead) {
      layers.homestead = L.marker(centre, { icon: houseIcon(), draggable: true, keyboard: false,
                                            title: "Homestead (drag to move)" }).addTo(map);
      layers.homestead.on("dragend", () => {
        const at = layers.homestead.getLatLng();
        setHomestead(at.lat, at.lng);
      });
      layers.circle = L.circle(centre, { radius: farm.radius_km * 1000, interactive: false, className: "farm-radius",
                                         color: "#1c5cab", weight: 2, dashArray: "6 6", fillOpacity: 0.05 }).addTo(map);
      layers.farmDams = L.layerGroup().addTo(map);
    }
    layers.homestead.setLatLng(centre);
    layers.circle.setLatLng(centre);
    layers.circle.setRadius(farm.radius_km * 1000);
    layers.farmDams.clearLayers();
    // The open dam is drawn last, so its number sits on top where dams are close together.
    const order = state.dams.filter((d) => d.dam_id !== state.selectedId)
      .concat(state.dams.filter((d) => d.dam_id === state.selectedId));
    order.forEach((dam) => {
      const style = DamDays.map.damStyle({ chance: dam.status === "forecast" ? dam.chance : null,
                                           selected: dam.dam_id === state.selectedId });
      style.radius = Math.max(style.radius, 9);
      style.bubblingMouseEvents = false;    // a click on a dam opens it; it does not move the homestead
      const marker = L.circleMarker([dam.lat, dam.lon], style);
      marker.bindTooltip(String(dam.number), { permanent: true, direction: "right", offset: [8, 0], className: "dam-number" });
      marker.on("click", () => openDam(dam.dam_id));
      layers.farmDams.addLayer(marker);
    });
    // Zoom to the circle when a farm is picked, or when the circle has grown out of view.
    const bounds = circleBounds(farm);
    if (fitMap || !map.getBounds().contains(bounds)) map.fitBounds(bounds, { padding: [20, 20] });
  }

  /** The box around the radius circle (no need for the circle to be drawn first). */
  function circleBounds(farm) {
    const dLat = farm.radius_km / 111.2;
    const dLon = farm.radius_km / (111.2 * Math.cos(farm.lat * Math.PI / 180));
    return L.latLngBounds([farm.lat - dLat, farm.lon - dLon], [farm.lat + dLat, farm.lon + dLon]);
  }

  /** Each dam's track record ({dam_id: {held, judged, ...}}), or null without track_record.json. */
  function records() {
    return data.trackRecord ? data.trackRecord.dams : null;
  }

  // ---- The list of dams -----------------------------------------------------
  /** "~67% full on 13 Sep", "dry on 13 Sep", or "no clear look lately". */
  function fullCell(dam) {
    if (dam.level_pct === null || dam.level_pct === undefined || !dam.issued_on) return "no clear look lately";
    return DamDays.damCard.howFull(dam.level_pct) + " on " + txt.shortDate(dam.issued_on);
  }

  /** What the text says about the dam's days, counted from the text's date. */
  function daysCell(dam) {
    const what = txt.kind(dam, textDate);
    if (what === "forecast") {
      const left = txt.daysLeft(dam, textDate);
      return left <= 0 ? "may be below a third now" : "<strong>" + txt.floorText(left) + "</strong>";
    }
    if (what === "low") return dam.level_pct === 0 ? "looks dry" : "already below a third";
    if (what === "not_refilled") return "no forecast until it refills to 60% full";
    return "no clear satellite look in " + txt.RECENT_LOOK_DAYS + " days";
  }

  function chanceCell(dam) {
    if (txt.kind(dam, textDate) !== "forecast") return '<span class="muted">none</span>';
    return fmt.chance(dam.chance) + " by " + txt.shortDate(dam.window_end);
  }

  /** Our track record on the dam: "held 166 of 216 times", or "not enough history". */
  function recordCell(dam) {
    const record = records()[dam.dam_id];
    if (!txt.hasTrackRecord(record)) return '<span class="muted">not enough history</span>';
    return "held " + txt.countText(record.held) + " of " + txt.countText(record.judged) + " times";
  }

  /** The farm's dams added up, under the table, with the dam whose record is lowest. */
  function farmRecordHtml() {
    const all = records();
    const label = '<span class="record-label">' + esc(data.trackRecord.label) + "</span>";
    const withRecord = state.dams.filter((d) => txt.hasTrackRecord(all[d.dam_id]));
    if (!withRecord.length) {
      return '<p class="farm-record"><strong>Our track record on this farm</strong> (' + label + "): not enough " +
             "history on these dams.</p>";
    }
    const held = withRecord.reduce((sum, d) => sum + all[d.dam_id].held, 0);
    const judged = withRecord.reduce((sum, d) => sum + all[d.dam_id].judged, 0);
    const which = withRecord.length === state.dams.length
      ? (state.dams.length === 1 ? "on its one dam" : "across its " + state.dams.length + " dams")
      : "across the " + withRecord.length + " of its " + state.dams.length + " dams with enough history";
    let html = '<p class="farm-record"><strong>Our track record on this farm</strong> (' + label + "): " +
               which + ", the cautious days-left promise held <strong>" + txt.countText(held) + " of " +
               txt.countText(judged) + " times</strong>";
    if (withRecord.length > 1) {
      const share = (d) => all[d.dam_id].held / all[d.dam_id].judged;
      const lowest = withRecord.reduce((low, d) => (share(d) < share(low) ? d : low));
      html += "; lowest on " + esc(lowest.name) + ", " + txt.countText(all[lowest.dam_id].held) + " of " +
              txt.countText(all[lowest.dam_id].judged);
    }
    return html + ". Forecasts on nearby dams often share one dry spell, so these are not all separate checks.</p>";
  }

  function damTableHtml() {
    if (!state.dams.length) return "";
    const day = txt.dateText(textDate);
    const track = data.trackRecord;
    const rows = state.dams.map((dam) =>
      '<tr class="' + (dam.dam_id === state.selectedId ? "is-selected" : "") + '">' +
      '<th scope="row"><button type="button" class="dam-link" data-dam="' + esc(dam.dam_id) + '">' + esc(dam.name) +
      '</button><span class="score-range">' + txt.oneDecimal(dam.distance_km) + " km away</span></th>" +
      "<td>" + fullCell(dam) + "</td><td>" + daysCell(dam) + "</td><td>" + chanceCell(dam) + "</td>" +
      (track ? "<td>" + recordCell(dam) + "</td>" : "") + "</tr>").join("");
    const recordHead = track
      ? '<th scope="col">Our track record (<span class="record-label">' + esc(track.label) + "</span>) " +
        fmt.tip("What is the backtest?", track.tip) + "</th>" : "";
    return '<table class="farm-table"><caption>Your dams (Dam 1 is the closest to the homestead)</caption>' +
           '<thead><tr><th scope="col">Dam</th><th scope="col">How full at the last clear look</th>' +
           '<th scope="col">Days of water above a third, from ' + esc(day) + '</th>' +
           '<th scope="col">Chance it drops below a third</th>' + recordHead + "</tr></thead><tbody>" + rows +
           "</tbody></table>" + (track ? farmRecordHtml() : "") +
           '<p class="panel-small farm-footnote">"%" means how full a dam is: its wet area at the last clear ' +
           "satellite look, against its usual full area. Days are cautious: in ten test years a dam stayed above a " +
           "third at least that long 9 times in 10. A forecast starts from the dam's last clear look, so the days " +
           "since that look are taken off. Tap a dam for its full card.</p>";
  }

  // ---- The panel: the text on a phone, or a dam's card ----------------------
  function textPanelHtml(farm, sms, long) {
    const day = txt.dateText(textDate) + " " + textDate.slice(0, 4);
    const places = txt.septets(sms);
    return '<h2 class="panel-title">This week\'s text</h2>' +
      '<p class="panel-small">What <strong>' + esc(farm.name) + "</strong> gets on " + esc(day) +
      ": one text message, once a week.</p>" +
      phoneHtml(sms) +
      '<p class="phone-count">' + places + " of " + txt.SMS_MAX + " places: one text message." +
      " " + fmt.tip("What is a place?",
                    "One text message holds 160 places. Letters, digits and spaces take one place each; " +
                    "the \"~\" before a fullness takes two. The text drops its least important lines to fit.") +
      "</p>" + outboxCheck(sms) +
      '<details class="long-text"><summary>The longer version (for the app or an email)</summary>' +
      long.split("\n").map((line) => "<p>" + esc(line) + "</p>").join("") + "</details>" +
      '<p class="panel-hint">Tap a dam on the map or in the list for its full card.</p>';
  }

  /** The text, exactly as it arrives, on a drawn phone. */
  function phoneHtml(sms) {
    return '<figure class="phone" aria-label="The weekly text as it arrives on a phone">' +
      '<div class="phone-screen">' +
      '<div class="phone-top"><span class="phone-avatar" aria-hidden="true"></span>' +
      '<span class="phone-sender">DamDays</span><span class="phone-meta">Text message</span></div>' +
      '<div class="phone-thread"><p class="sms-when">' + esc(txt.dateText(textDate)) + ", 7:00 am</p>" +
      '<p class="sms-bubble">' + esc(sms) + "</p></div>" +
      '<div class="phone-reply" aria-hidden="true">Text message</div>' +
      "</div></figure>";
  }

  /** For an unchanged demo farm: is this the very text in this week's outbox (written by Python)? */
  function outboxCheck(sms) {
    if (!state.demo || state.radiusKm !== state.demo.radius_km || !data.farms) return "";
    const file = "outbox/" + data.farms.date + ".json";
    if (sms === state.demo.sms) {
      return '<p class="phone-check">The same text, character for character, as this week\'s outbox (<code>' +
             esc(file) + "</code>), written by the Python sender's code.</p>";
    }
    return '<p class="phone-check phone-check-bad">This differs from the text in <code>' + esc(file) +
           "</code>. Run <code>node app/tools/check_text_port.js</code>.</p>";
  }

  /** Open a dam's card in the panel. */
  function openDam(damId) {
    state.selectedId = damId;
    update(false);
    DamDays.damCard.bringIntoView(el.panel);
  }

  function showCard(damId) {
    const dam = state.dams.find((d) => d.dam_id === damId);
    if (!dam) return;
    const inApp = !state.demo || state.demo.dams_in_app;
    const options = { rewind: false, revealed: false, name: dam.name };
    if (!inApp) {
      // A demo farm outside the app's region: the card is made from farms.json's copy of the dam.
      options.dam = { dam_id: dam.dam_id, name: dam.dam_id, area_ha: dam.area_ha };
      options.row = { status: dam.status, issued_on: dam.issued_on, window_end: dam.window_end,
                      level_pct: dam.level_pct, chance: dam.chance, damdays_days: dam.damdays_days,
                      chance_low: null, chance_high: null, notes: [] };
    }
    el.panel.innerHTML =
      '<button type="button" class="button button-link" data-action="back">&larr; This week\'s text</button>' +
      '<p class="card-distance">' + esc(dam.name) + " is " + txt.oneDecimal(dam.distance_km) + " km from the homestead.</p>" +
      DamDays.damCard.render(data, damId, inApp ? data.liveIssue : null, options);
  }

  function showEmpty() {
    el.note.textContent = "";
    el.panel.innerHTML = '<h2 class="panel-title">This week\'s text</h2>' +
      '<p class="panel-lead">Click the map where your homestead is.</p>' +
      '<p class="panel-small">Your farm\'s dams are the farm dams the satellites can see within the radius you choose.</p>';
  }

  /** Clicks in the panel and the list: open a dam, or go back to the text. */
  function onClick(event) {
    const pick = event.target.closest("[data-dam]");
    if (pick) {
      openDam(pick.getAttribute("data-dam"));
      return;
    }
    if (event.target.closest('[data-action="back"]')) {
      state.selectedId = null;
      update(false);
    }
  }

  return { init, show };
})();
