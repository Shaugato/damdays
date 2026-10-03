/* views/rewind.js
 * Go back to a past date. The map shows the forecasts as they would have been
 * made then. "Reveal what happened" rings the dams that really did fall below a
 * third, and the panel shows a tally of hits and misses, plus a check of
 * whether the chances came true ("we expected about 5; 6 happened").
 * Chances are written "3 in 10", as everywhere in the app.
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

    // Inside the Rewind sheet the map must not take keyboard focus on a click: focusing it scrolls the
    // window back but not the sheet, so the sheet jumped under the pointer and the tap on a dot was lost.
    const inSheet = Boolean(el.card && el.card.closest("#rp-region-host"));
    map = DamDays.map.create("rewind-map", inSheet ? { keyboard: false } : undefined);
    // half zoom steps: on a phone the region opens at the zoom Runway uses, not one step out
    if (map) { map.options.zoomSnap = 0.5; map.options.zoomDelta = 0.5; }
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
    el.note.textContent = plainNote(issue);
    el.card.innerHTML = "";
    if (map) drawMarkers();
    updateRevealState();
  }

  /**
   * The note under the date, in plain words. The data's own note names the model and its settings
   * (for specialists: About, "Methods and scores"); here it says what a farmer needs to know.
   */
  function plainNote(past) {
    const cutoff = data.meta && data.meta.rewind && data.meta.rewind.model_cutoff;
    const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    const learned = cutoff
      ? "from data before " + MONTHS[Number(cutoff.slice(5, 7)) - 1] + " " + cutoff.slice(0, 4)
      : "from earlier years only";
    return "Forecasts as they would have been made on " + fmt.date(past.issue_date) + ", using only what the satellites " +
           "had seen by then, from a model that learned only " + learned + ": these are years it never trained on.";
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
      low: row.status === "already_low",
      // thin grey rings: the dams already below a third (no forecast that day) stay quiet, so the thick black
      // "it did fall below a third" rings of the reveal stand out
      quietLow: true,
      selected: row.dam_id === selectedId,
      // Dams without a forecast are not judged, so they never get a reveal ring.
      revealed: revealed && row.status === "forecast",
      outcome: row.outcome,
    });
  }

  /** The hover text of one dot; it says what happened only after the reveal. */
  function tooltipFor(row) {
    const dam = data.damsById.get(row.dam_id);
    const none = row.status === "already_low" ? "already below a third" : row.status === "not_refilled" ? "waiting to refill" : "no forecast";
    let text = esc(dam.name) + ": " + (row.status === "forecast" ? fmt.chance(row.chance) + " chance" : none);
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
      showLow: true,
      lowQuiet: true,
      noForecastLabel: "No forecast that day (waiting to refill, or no recent look)",
      extraItems: revealed ? [
        { swatchClass: "swatch-ring", label: "Thick ring: it did fall below a third" },
        { swatchClass: "swatch-faded", label: "Faded: it stayed above (dashed: unknown)" },
      ] : [],
    });
    el.tally.innerHTML = revealed ? tallyHtml() : beforeRevealHtml();
    if (selectedId) renderCard(false);
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
    renderCard(true);
  }

  /** Close the card (the tally stays). */
  function unselect() {
    const previous = selectedId;
    selectedId = null;
    const marker = previous && markers.get(previous);
    if (marker) marker.setStyle(styleFor(issue.rowsByDam.get(previous)));
    el.card.innerHTML = "";
  }

  /** Show the dam's card (it sits above the tally): in the replay sheet, a short card in the new style. */
  function renderCard(bring) {
    const inReplay = Boolean(el.card.closest("#rp-region-host"));
    if (inReplay) {
      el.card.innerHTML = pastCardHtml(selectedId);
      wireFull(el.card.querySelector("[data-rw-full]"));
      // in the sheet, at every width: the card comes into view (beside the map on wide screens it already is)
      const scroller = el.card.closest(".sheet-body");
      const box = el.card.getBoundingClientRect(), view = scroller ? scroller.getBoundingClientRect() : { top: 0, bottom: window.innerHeight };
      if (bring && (box.top < view.top || box.top > view.bottom - 120)) {
        const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        el.card.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
      }
      return;
    }
    el.card.innerHTML =
      '<button type="button" class="button button-link" data-action="close">&times; Close this dam</button>' +
      DamDays.damCard.render(data, selectedId, issue, { rewind: true, revealed: revealed });
    if (bring) DamDays.damCard.bringIntoView(el.panel);
  }

  /**
   * One region dam on the past date, as the replay's rows say it: the chance by its date (ten dots), the
   * cautious days, how full it was, and after the reveal what happened; a link to the dam today on Runway.
   * Region dams are numbered across the region, so the name says so (not one of the farm's Dam 1 to 5).
   */
  function pastCardHtml(damId) {
    const dam = data.damsById.get(damId);
    const row = issue.rowsByDam.get(damId);
    if (!dam || !row) return "";
    const town = DamDays.region && DamDays.region.closestTown ? DamDays.region.closestTown(dam.lat, dam.lon) : null;
    const name = dam.name + " of the region" + (town ? ", near " + town : "");
    const look = row.issued_on ? fmt.fullness(row.level_pct) + " at its " + fmt.date(row.issued_on) + " look" : "no clear look lately";
    let main;
    if (row.status === "forecast" && row.chance !== null) {
      const dots = DamDays.charts && DamDays.charts.tenDots
        ? DamDays.charts.tenDots(row.chance, { r: 5.5, gap: 2.5, label: fmt.chance(row.chance) + " by " + fmt.date(row.window_end) }) : "";
      const days = row.damdays_days === null || row.damdays_days === undefined ? "" : daysHtml(row);
      main = '<p class="rw-chance"><b>' + esc(fmt.chance(row.chance)) + "</b> that it falls below a third by " + esc(fmt.date(row.window_end)) + "</p>" +
        (dots ? '<div class="rw-dots">' + dots + "</div>" : "") + days;
    } else {
      const why = row.status === "already_low" ? "Already below a third on that day, so no forecast."
        : row.status === "not_refilled" ? "No forecast: it had not refilled lately." : "No forecast: no recent clear look.";
      main = '<p class="rw-chance">' + esc(why) + "</p>";
    }
    let outcome = "";
    if (revealed && row.status === "forecast") {
      const text = row.outcome === true ? "It <b>fell below a third</b> on " + esc(fmt.date(row.outcome_date)) + "."
        : row.outcome === false ? "It <b>stayed above a third</b> until " + esc(fmt.date(row.window_end)) + "."
          : "Not enough clear satellite looks to know.";
      outcome = '<p class="rw-outcome"><span class="eyebrow">What happened</span><br>' + text + "</p>";
    }
    const full = '<details class="more rw-full" data-rw-full data-dam="' + esc(damId) + '"><summary>' +
      (DamDays.icon ? DamDays.icon("i-chart") : "") + "<span>See it in full<small>" +
      (row.status === "forecast" ? "The next six months as forecast that day, its water history to that day, and its note"
        : "Its water history to that day, and what the numbers mean") + "</small></span>" + (DamDays.icon ? DamDays.icon("i-plus", "plus") : "") +
      '</summary><div class="body" data-rw-full-body></div></details>';
    return '<article class="rw-card" aria-label="' + esc(name) + '">' +
      '<div class="rw-head"><p class="eyebrow">Forecast made on ' + esc(fmt.date(issue.issue_date)) + "</p>" +
      '<button type="button" class="iconbtn rw-close" data-action="close" aria-label="Close this dam">' +
      (DamDays.icon ? DamDays.icon("i-x") : "&times;") + "</button></div>" +
      '<h4 class="rw-name">' + esc(name) + "</h4>" +
      '<p class="rw-look">' + esc(look) + ".</p>" + main + outcome + full +
      '<a class="linkrow rw-link" href="#runway/dam-' + esc(damId) + '">' + (DamDays.icon ? DamDays.icon("i-map") : "") +
      "<span>This dam today, on Runway<small>This week's forecast and its water history since 1988</small></span>" +
      '<span class="chev">' + (DamDays.icon ? DamDays.icon("i-chev") : "") + "</span></a></article>";
  }

  /**
   * The cautious days as that day's text would have said them: counted from the date of the forecast (the days
   * from the dam's last clear look, less the days since that look), as the dam sheet under "See it in full" and
   * the weekly text count them, so the card and the sheet give one number.
   */
  function daysHtml(row) {
    const d = DamDays.damCard && DamDays.damCard.daysFrom ? DamDays.damCard.daysFrom(row, issue.issue_date)
      : { left: row.damdays_days, since: 0 };
    const from = fmt.date(issue.issue_date);
    const how = d.since > 0
      ? '<span class="rw-how">' + esc(row.damdays_days + " days from its " + fmt.date(row.issued_on) + " look, less the " +
        fmt.count(d.since, "day") + " since.") + "</span>" : "";
    const cautious = " Cautious: built to hold 9 times in 10 across all dams (a little less often for spring looks).";
    if (d.left <= 0) {
      return '<p class="rw-days"><span class="rw-big is-words">May already be below a third</span>' +
        esc("Its cautious days had run out by " + from + ".") + how + "</p>";
    }
    const cap = d.left >= DamDays.settings.damdaysCapDays;
    const big = cap ? '<span class="rw-big"><b>6 months+</b></span>'
      : '<span class="rw-big">at least <b>' + esc(d.left) + "</b> " + (d.left === 1 ? "day" : "days") + "</span>";
    const soon = !cap && d.left < 7 ? " <strong>It could drop below a third within days.</strong>" : "";
    return '<p class="rw-days">' + big + esc("before it drops below a third, counted from " + from + ".") + soon +
      esc(cautious) + how + "</p>";
  }

  /** "See it in full": the dam sheet's past-forecast view (js/dam-sheet.js), drawn inline the first time it opens. */
  function wireFull(det) {
    if (!det) return;
    const fill = () => {
      const body = det.querySelector("[data-rw-full-body]");
      if (!body || body.dataset.filled === "1") return;
      body.dataset.filled = "1";
      body.innerHTML = '<p class="small">Loading this dam&hellip;</p>';
      const files = ["js/charts.js", "js/dam-sheet.js"];
      const code = DamDays.damSheet ? Promise.resolve() : Promise.all(files.map((src) => DamDays.lazy(src)));
      code.then(() => {
        if (!det.isConnected) return;
        const opts = { dam: { dam_id: det.dataset.dam }, issueDate: issue.issue_date, revealed };
        body.innerHTML = DamDays.damSheet.html(data, opts);
        const root = body.querySelector(".ds");
        if (root) {
          root.removeAttribute("aria-labelledby");          // the card's own heading names the dam
          root.querySelectorAll("[id]").forEach((n) => n.removeAttribute("id"));
          DamDays.damSheet.wire(root, data, opts);
        }
      }, () => {
        body.dataset.filled = "";
        body.innerHTML = '<p class="small">This part needs signal the first time. Check your signal and try again.</p>';
      });
    };
    det.addEventListener("toggle", () => { if (det.open) fill(); });
  }

  // ---- The panel text -------------------------------------------------------
  function beforeRevealHtml() {
    const forecast = issue.rows.filter((r) => r.status === "forecast");
    return '<h2 class="panel-title">' + fmt.date(issue.issue_date) + "</h2>" +
           '<p class="panel-lead">' + fmt.count(forecast.length, "dam") + " had a forecast on this day.</p>" +
           '<p class="panel-small">Press <strong>Reveal what happened</strong> to compare these forecasts with ' +
           "what the satellites saw over the next " + data.meta.horizon_days + " days. Click a dam to see its card.</p>";
  }

  /** Count hits and misses: "likely" is a chance shown as 5 in 10 or more (settings.js). */
  function countTally(judged) {
    const tally = { hits: 0, falseAlarms: 0, misses: 0, allClears: 0 };
    judged.forEach((row) => {
      const saidLikely = DamDays.colors.isLikely(row.chance);
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
    const windowEnd = fmt.addDays(issue.issue_date, data.meta.horizon_days);

    const bandRows = bandCheck(judged).map((line) =>
      "<tr><th scope=\"row\"><span class=\"swatch\" style=\"background:" + line.band.color + "\" aria-hidden=\"true\"></span>" +
      esc(line.band.label) + "</th><td>" + line.dams + "</td><td>" + line.expected.toFixed(1) +
      "</td><td>" + line.happened + "</td></tr>").join("");

    return '<h2 class="panel-title">What happened</h2>' +
      '<p class="panel-lead"><strong>' + happened + " of " + judged.length + "</strong> dams fell below a third by about " +
      fmt.date(windowEnd) + ". The forecasts expected about <strong>" + Math.round(expected) + "</strong>.</p>" +
      '<table class="tally-table"><caption>Hits and misses (we said "likely" at ' + DamDays.settings.likelyInTen +
      " in 10 or more)</caption>" +
      '<thead><tr><th scope="col"></th><th scope="col">Fell below a third</th><th scope="col">Stayed above</th></tr></thead>' +
      '<tbody><tr><th scope="row">We said likely</th><td>' + fmt.count(t.hits, "hit") + "</td><td>" +
      fmt.count(t.falseAlarms, "false alarm") + "</td></tr>" +
      '<tr><th scope="row">We said unlikely</th><td>' + fmt.count(t.misses, "miss", "misses") + "</td><td>" +
      fmt.count(t.allClears, "correct all-clear") + "</td></tr></tbody></table>" +
      '<table class="band-table"><caption>Did the chances come true?</caption>' +
      '<thead><tr><th scope="col">Chance we gave</th><th scope="col">Dams</th><th scope="col">Expected to fall</th>' +
      '<th scope="col">Did fall</th></tr></thead><tbody>' + bandRows + "</tbody></table>" +
      '<p class="panel-small">Expected = the chances added up: ten dams at 3 in 10 each means about 3 should fall. ' +
      "Not counted: " + fmt.count(unknown, "dam") + " with too few clear satellite looks to know.</p>";
  }

  return { init, show };
})();
