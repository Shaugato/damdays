/* views/region.js (WP-F)
 * Runway: the region map (#runway; #map and #region are aliases). UI_SPEC 3.6, founder decision 2.
 *
 *   Glance:  how many dams are already below a third, a stacked count bar whose groups filter the
 *            sketch, and a tile-free dot sketch of every dam-sized waterbody we track in the region,
 *            each dot coloured by its chance of dropping below a third in the next 90 days.
 *   More:    the dams with the highest chance (a list that opens each dam), every "likely" dam in a
 *            table, and the interactive street map (the old Leaflet Runway, needs signal).
 *   Most:    a dam's sheet: #runway/dam-<dam_id> (DamDays.damSheet.open when WP-D's sheet is there,
 *            otherwise a compact sheet drawn here).
 *
 * Every number comes from the data (forecasts.json live issue, meta.json, track_record.json, curves.json).
 * Town positions are approximate and only place labels ("towns approximate" under the sketch).
 * Also exports DamDays.region.thumb(data): a small preview of the sketch for the More page.
 */
window.DamDays = window.DamDays || {};

(function () {
  "use strict";

  const D = window.DamDays;
  const esc = (t) => D.format.escapeHtml(t === null || t === undefined ? "" : t);
  const icon = (id, cls) => (D.icon ? D.icon(id, cls) : "");
  const fmt = () => D.format;

  // Approximate town positions (lat, lon, label side), for labels and "near <town>" only. Not data.
  const TOWNS = [
    ["Coonabarabran", -31.273, 149.278, "r"], ["Gilgandra", -31.711, 148.663, "r"],
    ["Narromine", -32.232, 148.240, "l"], ["Dubbo", -32.257, 148.601, "r"],
    ["Wellington", -32.556, 148.945, "r"], ["Mudgee", -32.594, 149.588, "l"],
    ["Parkes", -33.137, 148.176, "r"], ["Orange", -33.283, 149.100, "r"], ["Bathurst", -33.419, 149.578, "r"],
  ];
  const H = 1000;          // sketch height in viewBox units (the width follows the region's shape)
  const PAD = 16;          // room round the region box so edge dots are not cut
  const DOT_R = 6.5;

  let model = null;        // built once from the data
  let root = null;
  let liveMounted = false;
  let onlyKey = null;      // the count-bar group shown alone, or null

  // =====================================================================
  // The model: every dam's place, group and words
  // =====================================================================
  function bands() { return (D.settings && D.settings.chanceBands) || []; }

  function bandIndex(chance) {
    const band = D.colors.bandFor(chance);
    return band ? bands().indexOf(band) : -1;
  }

  /** The projection for the region box: lat/lon -> viewBox x/y (north up, a km about the same both ways). */
  function projection(meta, dams) {
    let box = meta && meta.region && Array.isArray(meta.region.bbox) ? meta.region.bbox.slice() : null;
    if ((!box || box.length !== 4) && dams.length) {
      const la = dams.map((d) => d.lat), lo = dams.map((d) => d.lon);
      box = [Math.min.apply(null, la), Math.max.apply(null, la), Math.min.apply(null, lo), Math.max.apply(null, lo)];
    }
    if (!box) box = [-1, 0, 0, 1];
    const [lat0, lat1, lon0, lon1] = box;
    const cos = Math.cos(((lat0 + lat1) / 2) * Math.PI / 180);
    const k = H / (lat1 - lat0);
    const kx = k * cos;
    return {
      W: Math.round((lon1 - lon0) * kx) + 2 * PAD, H: H + 2 * PAD, box,
      kmAcross: Math.round((lon1 - lon0) * 111.32 * cos / 10) * 10,
      x: (lon) => PAD + (lon - lon0) * kx,
      y: (lat) => PAD + (lat1 - lat) * k,
      unitsPerKm: k / 111.32,
    };
  }

  function kmBetween(lat1, lon1, lat2, lon2) {
    if (D.text && D.text.distanceKm) return D.text.distanceKm(lat1, lon1, lat2, lon2);
    const r = Math.PI / 180;
    const a = Math.sin((lat2 - lat1) * r / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin((lon2 - lon1) * r / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(a));
  }

  function closestTown(lat, lon) {
    let best = TOWNS[0][0], bestKm = Infinity;
    TOWNS.forEach((t) => { const km = kmBetween(lat, lon, t[1], t[2]); if (km < bestKm) { bestKm = km; best = t[0]; } });
    return best;
  }

  /** Days of water counted from the text's date (the weekly text's rule), or null without a forecast. */
  function daysLeftOf(row, textDate) {
    if (row.status !== "forecast" || row.damdays_days === null || row.damdays_days === undefined || !row.issued_on) return null;
    if (!textDate) return row.damdays_days;
    const since = Math.max(0, D.text.dayNumber(textDate) - D.text.dayNumber(row.issued_on));
    return row.damdays_days - since;
  }

  /** The group a dam falls in: "low", "none", or "k0".."k4" (its chance band). */
  function keyOf(row) {
    if (row.status === "already_low") return "low";
    if (row.status !== "forecast" || row.chance === null || row.chance === undefined) return "none";
    const i = bandIndex(row.chance);
    return i < 0 ? "none" : "k" + i;
  }

  function build(data) {
    const issue = data.liveIssue;
    const meta = data.meta || {};
    const dams = data.dams || [];
    const proj = projection(meta, dams);
    const textDate = data.textDate || null;
    const items = [];
    (issue ? issue.rows : []).forEach((row) => {
      const dam = data.damsById.get(row.dam_id);
      if (!dam) return;
      items.push({ dam, row, key: keyOf(row), x: proj.x(dam.lon), y: proj.y(dam.lat), left: daysLeftOf(row, textDate) });
    });
    const counts = { low: 0, none: 0 };
    bands().forEach((b, i) => { counts["k" + i] = 0; });
    items.forEach((it) => { counts[it.key] = (counts[it.key] || 0) + 1; });
    // why "no forecast this week": waiting to refill, or no recent clear look (the rest of the "none" group)
    const noneWhy = { not_refilled: 0, no_recent_look: 0, other: 0 };
    items.filter((it) => it.key === "none").forEach((it) => {
      const s = it.row.status;
      noneWhy[s === "not_refilled" || s === "no_recent_look" ? s : "other"] += 1;
    });
    const forecast = items.filter((it) => it.row.status === "forecast" && it.row.chance !== null && it.row.chance !== undefined);
    const byName = (a, b) => a.dam.name.localeCompare(b.dam.name, "en", { numeric: true });
    const likely = forecast.filter((it) => D.colors.isLikely(it.row.chance)).sort((a, b) => b.row.chance - a.row.chance || byName(a, b));
    const top = forecast.slice().sort((a, b) => b.row.chance - a.row.chance || byName(a, b)).slice(0, (D.settings && D.settings.topDamsToList) || 8);
    const looks = items.map((it) => it.row.issued_on).filter(Boolean).sort();
    const areas = dams.map((d) => d.area_ha).filter((a) => typeof a === "number");
    const farms = data.farms && Array.isArray(data.farms.farms) ? data.farms.farms : [];
    const hidden = (D.settings && D.settings.hiddenFarmIds) || [];
    const featured = farms.find((f) => f.farm_id === (D.settings && D.settings.defaultFarmId) && !hidden.includes(f.farm_id) &&
      f.dams_in_app !== false) || null;
    return {
      data, issue, meta, proj, items, counts, noneWhy, forecast, likely, top, textDate, featured,
      byId: new Map(items.map((it) => [it.dam.dam_id, it])),
      lastLook: looks.length ? looks[looks.length - 1] : null,
      minHa: areas.length ? Math.min.apply(null, areas) : null,
      maxHa: areas.length ? Math.max.apply(null, areas) : null,
      regionName: (meta.region && meta.region.name) || "the region",
    };
  }

  // =====================================================================
  // Words
  // =====================================================================
  /** "about 0.5 to 5 ha", from the smallest and largest dam we track. */
  function sizeWords(m) {
    if (m.minHa === null) return "about half a hectare and up";
    return "about " + (Math.floor(m.minHa * 10) / 10) + " to " + Math.round(m.maxHa) + " ha";
  }

  function groupLabel(key) {
    if (key === "low") return "Already below a third";
    if (key === "none") return "No forecast this week";
    const band = bands()[Number(key.slice(1))];
    return band ? band.label : key;
  }

  /** A dam's days in a few words, from the text's date. Never "dry": a 0% dam is "no water seen". */
  function daysWords(it) {
    const row = it.row;
    if (row.status === "already_low") return row.level_pct === 0 ? "no water seen at its last look" : "already below a third";
    if (row.status === "not_refilled") return "no forecast until it refills";
    if (row.status !== "forecast" || it.left === null) return "no recent clear look";
    if (it.left <= 0) {
      return "its cautious days ran out on " + fmt().short(fmt().addDays(row.issued_on, row.damdays_days)) + ": it may be below a third now";
    }
    return D.text.floorText(it.left) + " before it drops below a third";
  }

  function lookWords(row) {
    if (!row.issued_on) return "no clear look lately";
    return fmt().fullness(row.level_pct) + " at its " + fmt().short(row.issued_on) + " look";
  }

  function chanceDot(chance, size) {
    const s = size || 14;
    return '<svg class="rg-dot" width="' + s + '" height="' + s + '" viewBox="0 0 14 14" aria-hidden="true" focusable="false">' +
      '<circle cx="7" cy="7" r="6" fill="' + D.colors.colorFor(chance) + '" stroke="var(--c-ring)" stroke-width="1.5"/></svg>';
  }

  /** Ten dots, the first N filled in the band colour (UI_SPEC 5.12), with a name for screen readers. */
  function tenDots(chance, r) {
    const n = D.text.inTen(chance), rr = r || 6, gap = 3, step = rr * 2 + gap;
    const fill = D.colors.colorFor(chance);
    let dots = "";
    for (let i = 0; i < 10; i++) {
      const on = i < n;
      dots += '<circle cx="' + (rr + 1 + i * step) + '" cy="' + (rr + 1) + '" r="' + rr + '" fill="' + (on ? fill : "none") +
        '" stroke="' + (on ? "var(--c-ring)" : "var(--line-strong)") + '" stroke-width="1.5"/>';
    }
    const w = 10 * step - gap + 2;
    return '<svg class="tendots" width="' + w + '" height="' + (rr * 2 + 2) + '" viewBox="0 0 ' + w + " " + (rr * 2 + 2) +
      '" role="img" aria-label="' + esc(fmt().chance(chance)) + '">' + dots + "</svg>";
  }

  // =====================================================================
  // The sketch (tile-free): one SVG of dots, HTML labels on top (they keep their size)
  // =====================================================================
  function drawOrder(it) { return it.key === "none" ? 0 : it.key === "low" ? 1 : 2 + it.row.chance; }
  function pct(v, of) { return (Math.max(0, Math.min(of, v)) / of * 100).toFixed(2) + "%"; }

  function sketchHtml(m, opts) {
    opts = opts || {};
    const p = m.proj;
    const dots = m.items.slice().sort((a, b) => drawOrder(a) - drawOrder(b)).map((it) =>
      '<circle class="rg-d ' + it.key + '" cx="' + it.x.toFixed(1) + '" cy="' + it.y.toFixed(1) + '" r="' + (opts.thumb ? 11 : DOT_R) + '"/>').join("");
    let farm = "", farmLabel = "", farmKey = "";
    if (m.featured && !opts.thumb) {
      const fx = p.x(m.featured.lon), fy = p.y(m.featured.lat);
      const fr = Math.max(24, (m.featured.radius_km || 3) * p.unitsPerKm * 2.2);
      // the featured farm: a solid ring with a light halo and a centre dot, so it stands out from the dam dots
      const at = 'cx="' + fx.toFixed(1) + '" cy="' + fy.toFixed(1) + '"';
      farm = '<circle class="rg-farm-halo" ' + at + ' r="' + fr.toFixed(1) + '"/><circle class="rg-farm" ' + at + ' r="' + fr.toFixed(1) + '"/>' +
        '<circle class="rg-farm-dot" ' + at + ' r="' + Math.max(9, fr * 0.28).toFixed(1) + '"/>';
      const short = String(m.featured.name || "").replace(/\s*\(.*\)\s*$/, "");
      const base = esc(short) + " <span>(demo)</span>";
      farmLabel = '<a class="rg-lab rg-farmlabel" href="#farm" data-ax="' + fx.toFixed(1) + '" data-ay="' + fy.toFixed(1) + '" data-ar="' + fr.toFixed(1) +
        '" data-base="' + esc(base) + '" data-town="' + esc(m.featured.near_town || "") + '" style="left:' + pct(fx, p.W) + ";top:" + pct(fy, p.H) + '">' + base + "</a>";
      // where no spot beside the ring is free of dam dots, the farm is named here instead, in the row above the
      // sketch, with the ring as its key (placeLabels shows one or the other)
      farmKey = '<a class="rg-farmkey" href="#farm" hidden><svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" focusable="false">' +
        '<circle class="rg-farm" cx="11" cy="11" r="8.5"/><circle class="rg-farm-dot" cx="11" cy="11" r="3.2"/></svg><span class="rg-farmkey-t">' + base + "</span></a>";
    }
    const inBox = TOWNS.filter((t) => t[1] >= p.box[0] && t[1] <= p.box[1] && t[2] >= p.box[2] && t[2] <= p.box[3]);
    const towns = opts.thumb ? "" : inBox.map((t) => '<i class="rg-town-dot" aria-hidden="true" data-town="' + esc(t[0]) + '" style="left:' + pct(p.x(t[2]), p.W) + ";top:" +
        pct(p.y(t[1]), p.H) + '"></i>').join("") +
      inBox.map((t) => '<span class="rg-lab rg-town" aria-hidden="true" data-town="' + esc(t[0]) + '" data-ax="' + p.x(t[2]).toFixed(1) + '" data-ay="' + p.y(t[1]).toFixed(1) +
        '" data-ar="5" data-side="' + t[3] + '"' + (m.featured && m.featured.near_town === t[0] ? ' data-near="1"' : "") + ' style="left:' + pct(p.x(t[2]), p.W) + ";top:" + pct(p.y(t[1]), p.H) + '">' + esc(t[0]) + "</span>").join("");
    const title = opts.thumb ? "" : "<title>" + esc(fmt().thousands(m.items.length) + " dam-sized waterbodies in " + m.regionName +
      ", each coloured by its chance of dropping below a third. The list beside the map names the dams with the highest chance.") + "</title>";
    // The north mark and Zoom sit in a slim row above the sketch, not on it: on the drawing they hid the dots of
    // its densest corner (they could not be seen, hovered or tapped there).
    const bar = opts.thumb ? "" : '<div class="rg-bar"><span class="rg-north" aria-hidden="true">' + icon("i-back", "sm") + "<b>N</b></span>" + farmKey +
      // the sketch does not zoom: this swaps it for the street map that does, in the same place
      '<button type="button" class="rg-zoom" data-live aria-label="Zoom in: open the interactive map here">' + icon("i-plus", "sm") + "<b>Zoom</b></button></div>";
    return bar + '<div class="rg-canvas" style="aspect-ratio:' + p.W + " / " + p.H + '">' +
      '<svg class="rg-svg" viewBox="0 0 ' + p.W + " " + p.H + '" preserveAspectRatio="xMidYMid meet" ' +
      (opts.thumb ? 'aria-hidden="true" focusable="false"' : 'role="img"') + ">" + title +
      '<rect class="rg-bg" x="0" y="0" width="' + p.W + '" height="' + p.H + '" rx="18"/>' +
      '<g class="rg-dots">' + dots + "</g>" + farm +
      (opts.thumb ? "" : '<circle class="rg-pick" r="17" cx="-50" cy="-50"/>') + "</svg>" +
      towns + farmLabel +
      (opts.thumb ? "" : '<div class="rg-tip" aria-hidden="true" hidden></div>') +
      "</div>";
  }

  /**
   * Place the town and farm labels so none leaves the sketch or covers another: for each label (the farm
   * first, then the towns nearest the farm), try right, left, above and below its point and keep the first
   * that fits; re-run on resize. The farm's ring and every town's dot are obstacles from the start, so no
   * label covers them; a town label with no free spot is left out rather than drawn over the farm. The farm's
   * label (a link) never covers a dam dot: with no such spot, the farm is named above the sketch instead.
   */
  function placeLabels(canvas, merged) {
    if (!canvas || !model) return;
    const box = canvas.getBoundingClientRect();
    if (!box.width) return;
    const scale = box.width / model.proj.W;
    const placed = [];
    const farmEl = canvas.querySelector(".rg-farmlabel");
    const nearEl = canvas.querySelector(".rg-town[data-near]");
    // A town whose name is left out loses its square too, so no unnamed square reads as the farm's town.
    // The farm's own town, if its name finds no room, goes into the farm's label ("Farm E (demo), near Mudgee").
    const dotOf = (el) => canvas.querySelector('.rg-town-dot[data-town="' + (window.CSS && CSS.escape ? CSS.escape(el.dataset.town || "") : el.dataset.town) + '"]');
    if (!merged) {
      if (farmEl && farmEl.dataset.base) farmEl.innerHTML = farmEl.dataset.base;
      if (nearEl) nearEl.dataset.skip = "";
    }
    const fx = farmEl ? Number(farmEl.dataset.ax) * scale : null, fy = farmEl ? Number(farmEl.dataset.ay) * scale : null;
    if (farmEl) {
      const fr = Number(farmEl.dataset.ar) * scale;
      placed.push({ x: fx - fr, y: fy - fr, w: 2 * fr, h: 2 * fr, protect: true });
    }
    canvas.querySelectorAll(".rg-town").forEach((t) => {
      const tx = Number(t.dataset.ax) * scale, ty = Number(t.dataset.ay) * scale;
      placed.push({ x: tx - 4, y: ty - 4, w: 8, h: 8 });
    });
    const far = (el) => (fx === null ? 0 : Math.hypot(Number(el.dataset.ax) * scale - fx, Number(el.dataset.ay) * scale - fy));
    const labels = Array.from(canvas.querySelectorAll(".rg-lab")).sort((a, b) =>
      ((b.classList.contains("rg-farmlabel") ? 1 : 0) - (a.classList.contains("rg-farmlabel") ? 1 : 0)) || far(a) - far(b));
    const hit = (r) => placed.some((q) => r.x < q.x + q.w + 3 && r.x + r.w + 3 > q.x && r.y < q.y + q.h + 3 && r.y + r.h + 3 > q.y);
    const inside = (r) => r.x >= 2 && r.y >= 2 && r.x + r.w <= box.width - 2 && r.y + r.h <= box.height - 2;
    // covering the farm's ring or its label costs far more than covering a town's dot or name
    const overlap = (r) => placed.reduce((sum, q) => sum + (q.protect ? 1000 : 1) * Math.max(0, Math.min(r.x + r.w, q.x + q.w) - Math.max(r.x, q.x)) *
      Math.max(0, Math.min(r.y + r.h, q.y + q.h) - Math.max(r.y, q.y)), 0);
    // dam dots whose centre a label (with its 4 px tap margin, more.css .rg-farmlabel::after) would cover
    const dotsPx = farmEl ? model.items.map((it) => [it.x * scale, it.y * scale]) : [];
    const dotsUnder = (r) => dotsPx.reduce((n, d) => n + (d[0] >= r.x - 6 && d[0] <= r.x + r.w + 6 && d[1] >= r.y - 6 && d[1] <= r.y + r.h + 6 ? 1 : 0), 0);
    // [a0, a1, ...] before [b0, b1, ...]: compared item by item, the first difference decides
    const before = (a, b) => { const j = a.findIndex((v, i) => v !== b[i]); return j >= 0 && a[j] < b[j]; };
    const keyEl = canvas.parentElement ? canvas.parentElement.querySelector(".rg-farmkey") : null;
    labels.forEach((el) => {
      el.style.transform = "none";
      if (el.dataset.skip === "1") { el.hidden = true; const dot = dotOf(el); if (dot) dot.hidden = true; return; }
      el.hidden = false;                      // measured as shown (a label left out last time measures 0 x 0)
      const w = el.offsetWidth, h = el.offsetHeight;
      const ax = Number(el.dataset.ax) * scale, ay = Number(el.dataset.ay) * scale, ar = Number(el.dataset.ar) * (el.classList.contains("rg-farmlabel") ? scale : 1) + 4;
      const order = (el.classList.contains("rg-farmlabel") ? ["t", "tr", "tl", "r", "l", "b"] : el.dataset.side === "l" ? ["l", "r", "b", "t"] : ["r", "l", "b", "t"])
        .concat(["tr", "tl", "br", "bl"]).filter((k, i, all) => all.indexOf(k) === i);
      const around = (rr) => ({ r: { x: ax + rr, y: ay - h / 2 }, l: { x: ax - rr - w, y: ay - h / 2 }, t: { x: ax - w / 2, y: ay - rr - h }, b: { x: ax - w / 2, y: ay + rr },
        tr: { x: ax + rr * 0.7, y: ay - rr * 0.7 - h }, tl: { x: ax - rr * 0.7 - w, y: ay - rr * 0.7 - h },
        br: { x: ax + rr * 0.7, y: ay + rr * 0.7 }, bl: { x: ax - rr * 0.7 - w, y: ay + rr * 0.7 } });
      const at = around(ar);
      let best = null, bestCost = Infinity, free = false;
      if (el.classList.contains("rg-farmlabel")) {
        // The farm's label is a link drawn over the dots: a dam dot under it could be neither hovered nor tapped. Of
        // the spots around its ring (up to 20 px further out) clear of the ring and the towns' dots, take one that
        // covers no dam dot, the nearest first. Where there is none (a crowded farm, a phone's small sketch), the
        // label is left off the drawing and the farm is named in the row above it instead (.rg-farmkey).
        let bestKey = null;
        [0, 6, 12, 20].forEach((extra) => {
          const spots = around(ar + extra);
          order.forEach((k, i) => {
            const r = { x: spots[k].x, y: spots[k].y, w, h };
            if (!inside(r)) return;
            const key = [hit(r) ? overlap(r) : 0, dotsUnder(r), extra, i];
            if (!bestKey || before(key, bestKey)) { bestKey = key; best = r; }
          });
        });
        if (keyEl && !(bestKey && bestKey[0] === 0 && bestKey[1] === 0)) {
          el.hidden = true;
          keyEl.querySelector(".rg-farmkey-t").innerHTML = el.innerHTML;
          keyEl.hidden = false;
          return;
        }
        if (keyEl) keyEl.hidden = true;
        free = Boolean(bestKey) && bestKey[0] === 0;
        bestCost = bestKey ? bestKey[0] : Infinity;
      } else {
        for (const k of order) {
          const r = { x: at[k].x, y: at[k].y, w, h };
          if (!inside(r)) continue;
          if (!hit(r)) { best = r; free = true; break; }
          const cost = overlap(r);
          if (cost < bestCost) { bestCost = cost; best = r; }
        }
      }
      const isTown = el.classList.contains("rg-town");
      el.hidden = false;
      const dot = isTown ? dotOf(el) : null;
      if (dot) dot.hidden = false;
      // no free spot: the farm's own town may touch another town's name or dot, never the farm; others are left out
      if (isTown && !free && !(el.dataset.near && best && bestCost < 1000)) { el.hidden = true; if (dot) dot.hidden = true; return; }
      if (!best) {
        const r = at[order[0]];
        best = { x: Math.max(2, Math.min(box.width - w - 2, r.x)), y: Math.max(2, Math.min(box.height - h - 2, r.y)), w, h };
      }
      placed.push(el.classList.contains("rg-farmlabel") ? Object.assign({ protect: true }, best) : best);
      el.style.left = best.x.toFixed(1) + "px";
      el.style.top = best.y.toFixed(1) + "px";
    });
    if (!merged && nearEl && nearEl.hidden && farmEl && farmEl.dataset.town) {
      farmEl.innerHTML = farmEl.dataset.base.replace(/<\/span>$/, ", near " + esc(farmEl.dataset.town) + "</span>");
      nearEl.dataset.skip = "1";
      placeLabels(canvas, true);
    }
  }

  /** A small preview of the sketch (the More page). */
  function thumb(data) {
    try { return sketchHtml(build(data), { thumb: true }); } catch (e) { return ""; }
  }

  // =====================================================================
  // The page
  // =====================================================================
  function countBarHtml(m) {
    const keys = ["low"].concat(bands().map((b, i) => "k" + i).reverse(), ["none"]).filter((k) => m.counts[k]);
    const segs = keys.map((k) => '<i class="cb-seg ' + k + '" style="flex-grow:' + m.counts[k] + '"></i>').join("");
    // the no-forecast group says why, with its two counts (the refill line from meta.arm_level_pct)
    const why = (k) => {
      if (k !== "none" || !m.noneWhy) return "";
      const arm = m.meta.arm_level_pct;
      const bits = [];
      if (m.noneWhy.not_refilled) bits.push(fmt().thousands(m.noneWhy.not_refilled) + " waiting to refill" + (arm ? " to " + arm + "% full" : ""));
      if (m.noneWhy.no_recent_look) bits.push(fmt().thousands(m.noneWhy.no_recent_look) + " with no clear look lately");
      if (m.noneWhy.other) bits.push(fmt().thousands(m.noneWhy.other) + " other");
      return bits.length ? '<small class="cb-why">' + esc(bits.join(" · ")) + "</small>" : "";
    };
    const keysHtml = keys.map((k) =>
      '<li><button type="button" class="cb-key" data-only="' + k + '" aria-pressed="false">' +
      '<span class="cb-sw ' + k + '" aria-hidden="true"></span><span class="cb-label">' + esc(groupLabel(k)) + why(k) + "</span>" +
      '<span class="cb-n">' + fmt().thousands(m.counts[k]) + "</span></button></li>").join("");
    return '<div class="countbar" role="img" aria-label="' + esc(keys.map((k) => groupLabel(k) + ": " + m.counts[k]).join(", ")) +
      '">' + segs + "</div>" +
      '<p class="cb-caption meta">Chance of dropping below a third in the next ' + esc(m.meta.horizon_days || 90) +
      " days. Tap a group to show only those dams on the map.</p>" +
      '<ul class="cb-keys" aria-label="Show one group on the map">' + keysHtml + "</ul>" +
      '<p class="cb-status small" aria-live="polite"></p>';
  }

  function rowHtml(it) {
    const row = it.row;
    return '<a class="rg-row" href="#runway/dam-' + esc(it.dam.dam_id) + '" data-dam="' + esc(it.dam.dam_id) + '">' +
      chanceDot(row.chance, 18) +
      '<span class="rg-row-main"><b>' + esc(it.dam.name) + "</b><small>near " + esc(closestTown(it.dam.lat, it.dam.lon)) +
      " · " + esc(lookWords(row)) + '</small><small class="rg-row-days">' + esc(daysWords(it)) + "</small></span>" +
      '<span class="rg-row-ch"><b>' + esc(fmt().chance(row.chance)) + "</b><small>by " + esc(fmt().short(row.window_end)) + "</small></span>" +
      "</a>";
  }

  function likelyTableHtml(m) {
    if (!m.likely.length) return "";
    const rows = m.likely.map((it) => '<tr><th scope="row"><a href="#runway/dam-' + esc(it.dam.dam_id) + '">' + esc(it.dam.name) +
      "</a></th><td>" + esc(closestTown(it.dam.lat, it.dam.lon)) + '</td><td class="num">' + esc(fmt().chance(it.row.chance)) +
      "</td><td>" + esc(fmt().fullness(it.row.level_pct)) + "</td></tr>").join("");
    const inTen = (D.settings && D.settings.likelyInTen) || 5;
    return '<details class="more rg-likely"><summary>' + icon("i-chart") + "<span>All " + fmt().thousands(m.likely.length) +
      " dams with a " + inTen + " in 10 chance or more</span>" + icon("i-plus", "plus") + '</summary><div class="body">' +
      '<div class="table-scroll"><table class="data"><thead><tr><th scope="col">Dam</th><th scope="col">Near</th>' +
      '<th scope="col" class="num">Chance, ' + esc(m.meta.horizon_days || 90) + ' days</th><th scope="col">How full at its last look</th></tr></thead><tbody>' +
      rows + "</tbody></table></div></div></details>";
  }

  function pageHtml(m) {
    const f = fmt();
    const low = m.counts.low || 0;
    const through = m.meta.data_through ? f.date(m.meta.data_through) : (m.lastLook ? f.date(m.lastLook) : "");
    const inTen = (D.settings && D.settings.likelyInTen) || 5;
    const days = esc(m.meta.horizon_days || 90);
    const lead = m.items.length
      ? "<strong>" + f.thousands(low) + " of the " + f.thousands(m.items.length) + "</strong> dam-sized waterbodies we track in " +
        esc(m.regionName) + ", mostly farm dams, were already below a third at the latest satellite looks" +
        (through ? " (to " + esc(through) + ")" : "") + "."
      : "This dataset has no current forecast.";
    return '<div class="wrap region">' +
      '<header class="page-head region-head"><p class="eyebrow">Runway · the region map</p>' +
      '<h1 id="runway-h1">Where water is running short</h1>' +
      '<p class="lead">' + lead + "</p>" +
      '<p class="region-who">For advisers and agencies who look after many farms: every dam we track, big enough for the satellites to see (' +
      esc(sizeWords(m)) + "), coloured by its chance of dropping below a third in the next " + days +
      " days. Tap a dot, or a dam in the list, to see its days.</p></header>" +
      '<div class="region-grid">' +
      '<figure class="region-map surface" id="region-map">' + sketchHtml(m) +
      // the interactive map opens here, in place of the sketch (Zoom on the sketch, or the button beside)
      '<div class="region-live-host" id="rg-live-host" aria-label="Interactive map of the region" role="region" hidden></div>' +
      '<figcaption class="small rg-cap-sketch">Each dot is one dam, drawn larger than life. Hollow rings: already below a third. ' +
      "Grey: no forecast this week (waiting to refill, or no recent clear look). " +
      "Towns approximate; the box is about " + esc(m.proj.kmAcross) + " km across. Dams are numbered across the region; on a farm, they are numbered from the homestead.</figcaption>" +
      '<figcaption class="small rg-cap-live" hidden><span>Zoom in, and tap any dot to open that dam. Street map &copy; OpenStreetMap contributors.</span>' +
      '<button type="button" class="btn btn-quiet rg-back" data-live-back>' + icon("i-back", "sm") + "Back to the sketch</button></figcaption></figure>" +
      '<div class="region-side">' +
      '<section class="region-counts surface" aria-labelledby="rg-counts-h"><h2 class="card-title" id="rg-counts-h">' +
      f.thousands(m.forecast.length) + " have a forecast this week; " + f.thousands(m.likely.length) + " of them a " + inTen + " in 10 chance or more</h2>" +
      countBarHtml(m) + "</section>" +
      (m.top.length ? '<section class="region-top" aria-labelledby="rg-top-h"><h2 class="section-title" id="rg-top-h">Highest chance in the next ' +
        days + " days</h2>" +
        '<p class="meta">Days counted from ' + esc(m.textDate ? f.dayShort(m.textDate) + ", the day of this week's text" : "the latest look") +
        ". A high chance often means the cautious days have already run out.</p>" +
        '<div class="rg-rows">' + m.top.map(rowHtml).join("") + "</div>" + likelyTableHtml(m) + "</section>" : "") +
      '<section class="region-live surface" aria-labelledby="rg-live-h">' +
      '<h2 class="card-title" id="rg-live-h">' + icon("i-map") + "<span>The interactive map</span></h2>" +
      '<p class="meta">The same dams on a street map you can zoom into, with the colour key. It opens in place of the sketch. Needs signal.</p>' +
      '<button class="btn btn-quiet" type="button" id="rg-live-btn" aria-expanded="false" aria-controls="rg-live-host">Open the interactive map</button>' +
      "</section>" +
      '<div class="linkrows region-links">' +
      '<a class="linkrow" href="#farm/setup">' + icon("i-home") + "<span>Your own farm<small>Set a homestead point and see the text it would get.</small></span>" +
      '<span class="chev">' + icon("i-chev") + "</span></a>" +
      '<a class="linkrow" href="#proof/rewind">' + icon("i-rewind") + "<span>Rewind: the 2018-19 drought<small>Inside Proof: what it said at the time, then what happened.</small></span>" +
      '<span class="chev">' + icon("i-chev") + "</span></a></div>" +
      "</div></div>" +
      "</div>";
  }

  // =====================================================================
  // Interaction: filter, hover, tap, the interactive map
  // =====================================================================
  function setOnly(key) {
    onlyKey = onlyKey === key ? null : key;
    const canvas = root.querySelector(".region-map .rg-canvas");
    if (canvas) { if (onlyKey) canvas.setAttribute("data-only", onlyKey); else canvas.removeAttribute("data-only"); }
    root.querySelectorAll(".cb-key").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.only === onlyKey)));
    const status = root.querySelector(".cb-status");
    if (status) {
      status.textContent = onlyKey ? "The map shows only: " + groupLabel(onlyKey).toLowerCase() + " (" + fmt().thousands(model.counts[onlyKey]) +
        " dams). Tap it again to show every dam." : "";
    }
  }

  function svgPoint(svg, event) {
    const r = svg.getBoundingClientRect();
    if (!r.width) return null;
    const scale = model.proj.W / r.width;
    return { x: (event.clientX - r.left) * scale, y: (event.clientY - r.top) * scale, scale };
  }

  function nearest(pt, maxCss) {
    let best = null, bestD = Infinity;
    model.items.forEach((it) => {
      if (onlyKey && it.key !== onlyKey) return;
      const d = Math.hypot(it.x - pt.x, it.y - pt.y);
      if (d < bestD) { bestD = d; best = it; }
    });
    return bestD <= maxCss * pt.scale ? best : null;
  }

  function markPick(damId) {
    if (!root || !model) return;
    const pick = root.querySelector(".rg-pick");
    const it = damId ? model.byId.get(damId) : null;
    if (pick) {
      pick.setAttribute("cx", it ? it.x.toFixed(1) : "-50");
      pick.setAttribute("cy", it ? it.y.toFixed(1) : "-50");
      pick.classList.toggle("is-on", Boolean(it));
    }
    root.querySelectorAll(".rg-row").forEach((a) => a.classList.toggle("is-hot", a.dataset.dam === damId));
  }

  function bindSketch() {
    const svg = root.querySelector(".region-map .rg-svg");
    const tip = root.querySelector(".region-map .rg-tip");
    if (!svg) return;
    svg.addEventListener("click", (event) => {
      const pt = svgPoint(svg, event);
      const it = pt && nearest(pt, 26);
      // with a dam's sheet open beside the sketch (desktop), the next dot swaps it: one level, never a stack
      if (it) D.router.go("#runway/dam-" + it.dam.dam_id, { replace: Boolean(D.sheet && D.sheet.isOpen()) });
    });
    if (!tip || !window.matchMedia || !window.matchMedia("(hover: hover)").matches) return;
    svg.addEventListener("pointermove", (event) => {
      const pt = svgPoint(svg, event);
      const it = pt && nearest(pt, 18);
      svg.style.cursor = it ? "pointer" : "";
      if (!it) { tip.hidden = true; return; }
      const width = svg.getBoundingClientRect().width;
      tip.innerHTML = "<b>" + esc(it.dam.name) + "</b> near " + esc(closestTown(it.dam.lat, it.dam.lon)) + "<br>" +
        // the chance says what it is a chance of, as the street map's tooltip and the list say it
        esc(it.row.status === "forecast" ? fmt().chance(it.row.chance) + " chance it drops below a third by " + fmt().short(it.row.window_end) +
          " · " + daysWords(it) : daysWords(it));
      tip.style.left = (it.x / pt.scale) + "px";
      tip.style.top = (it.y / pt.scale) + "px";
      tip.classList.toggle("is-left", it.x / pt.scale > width * 0.55);
      tip.hidden = false;
    });
    svg.addEventListener("pointerleave", () => { tip.hidden = true; svg.style.cursor = ""; });
  }

  function reduceMotion() { return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); }

  /**
   * The interactive street map (the old Leaflet Runway: zoom, pan, scale bar, tooltips, the colour key) opens in
   * place of the sketch, in the same card, so zooming happens where you are looking; "Back to the sketch" (or the
   * button beside) swaps back. open: true / false, or toggle when not given.
   */
  function openLiveMap(open) {
    const host = root.querySelector("#rg-live-host");
    const btn = root.querySelector("#rg-live-btn");
    const fig = root.querySelector(".region-map");
    if (!host || !fig) return;
    const isOpen = !host.hidden;
    const want = open === undefined ? !isOpen : Boolean(open);
    const canvas = fig.querySelector(".rg-canvas"), bar = fig.querySelector(".rg-bar");
    const capSketch = fig.querySelector(".rg-cap-sketch"), capLive = fig.querySelector(".rg-cap-live");
    host.hidden = !want;
    if (canvas) canvas.hidden = want;
    if (bar) bar.hidden = want;
    if (capSketch) capSketch.hidden = want;
    if (capLive) capLive.hidden = !want;
    fig.classList.toggle("is-live", want);
    if (btn) {
      btn.setAttribute("aria-expanded", String(want));
      btn.textContent = want ? "Back to the sketch" : "Open the interactive map";
    }
    if (!want) {
      const zoom = fig.querySelector(".rg-zoom");
      if (zoom && document.activeElement && host.contains(document.activeElement)) zoom.focus({ preventScroll: true });
      return;
    }
    if (liveMounted) {
      const v = D.views && D.views.runway;
      if (v && v.show) v.show();
      bringIntoView(fig);
      return;
    }
    liveMounted = true;
    host.innerHTML = '<div class="region-live-mount"><p class="meta region-live-wait">Loading the street map&hellip;</p></div>';
    bringIntoView(fig);
    const mount = host.querySelector(".region-live-mount");
    const failed = () => { mount.innerHTML = '<p class="meta region-live-off">The interactive map could not load. Check your signal; the sketch still works (Back to the sketch).</p>'; liveMounted = false; };
    D.legacy.mount("runway", mount).then((ok) => {
      const wait = mount.querySelector(".region-live-wait");
      if (wait) wait.remove();
      if (!ok) failed();
      // the street map is taller than its loading line: check again once it is laid out
      requestAnimationFrame(() => bringIntoView(fig));
    }, failed);
  }

  /**
   * Bring the map card's top into view when it is off screen or under the sticky top bar (phones: the button beside
   * is below it). Scrolled by hand: on desktop the card is sticky, and scrollIntoView() on a sticky card that the
   * end of its column has pushed up (the street map is taller than the screen's room) left its top under the bar.
   * Its scroll-margin-top (more.css) is the room kept above it.
   */
  function bringIntoView(fig) {
    if (!fig || !fig.isConnected) return;
    const r = fig.getBoundingClientRect();
    if (!r.height) return;
    const room = parseFloat(getComputedStyle(fig).scrollMarginTop) || 0;
    if (r.top < room - 1 || r.top > window.innerHeight * 0.6) {
      window.scrollTo({ top: Math.max(0, window.scrollY + r.top - room), behavior: reduceMotion() ? "auto" : "smooth" });
    }
  }

  // =====================================================================
  // A dam's sheet (#runway/dam-<id>)
  // =====================================================================
  /** The context My farm gives the dam sheet (REQUESTS.md, WP-C), built for a dam of the region. */
  function damContext(damId, route) {
    const it = model.byId.get(damId);
    if (!it) return null;
    const data = model.data;
    const records = data.trackRecord && data.trackRecord.dams ? data.trackRecord.dams : null;
    const toDam = (x) => {
      const d = {
        number: null, name: x.dam.name, dam_id: x.dam.dam_id, dea_uid: x.dam.dea_uid, distance_km: null,
        lat: x.dam.lat, lon: x.dam.lon, area_ha: x.dam.area_ha, status: x.row.status, issued_on: x.row.issued_on,
        window_end: x.row.window_end, level_pct: x.row.level_pct, chance: x.row.chance, damdays_days: x.row.damdays_days,
        days_left: x.left, row: x.row, in_app: true, near_town: closestTown(x.dam.lat, x.dam.lon),
        record: records ? records[x.dam.dam_id] || null : null,
      };
      try {
        d.kind = model.textDate ? D.text.kind(d, model.textDate)
          : ({ forecast: "forecast", already_low: "low", not_refilled: "not_refilled" })[d.status] || "no_look";
      } catch (e) { d.kind = "no_look"; }
      return d;
    };
    const inTop = model.top.findIndex((x) => x.dam.dam_id === damId);
    const dams = (inTop >= 0 ? model.top : [it]).map(toDam);
    const index = inTop >= 0 ? inTop : 0;
    return {
      dam: dams[index], dams, index, farm: null, context: "runway",
      region: { name: model.regionName, key: model.meta.region ? model.meta.region.key : null },
      textDate: model.textDate, deep: route.deep || null, data, route,
      hrefFor: (d) => "#runway/dam-" + d.dam_id,
      title: it.dam.name,
      // wide screens: no scrim, the sketch (or the street map) beside stays live, so the next dot is one click
      split: Boolean(window.matchMedia && window.matchMedia("(min-width: 1200px)").matches),
    };
  }

  function openDam(damId, route) {
    const ctx = damContext(damId, route);
    if (!ctx) { D.router.go("#runway", { replace: true }); return; }
    markPick(damId);
    const live = D.views && D.views.runway;
    if (live && typeof live.highlight === "function") live.highlight(damId);
    if (D.damSheet && typeof D.damSheet.open === "function") {
      try { D.damSheet.open(ctx); return; } catch (e) { console.error(e); }
    }
    openFallbackSheet(ctx);
  }

  function heroHtml(d, ctx) {
    const f = fmt(), row = d.row, t = D.text;
    const arm = (model.meta && model.meta.arm_level_pct) || 60;
    if (d.kind === "low") {
      const seen = row.level_pct === 0
        ? "No water seen at its " + f.short(row.issued_on) + " satellite look (one look can be wrong)."
        : f.fullness(row.level_pct) + " at its " + f.short(row.issued_on) + " satellite look.";
      return '<div class="rd-hero is-low"><p class="eyebrow">At the ' + esc(f.short(row.issued_on)) + " satellite look</p>" +
        '<p class="rd-state">Already below a third</p><p class="meta">' + esc(seen + " DamDays gives it days again once it refills to " + arm + "% full.") + "</p></div>";
    }
    if (d.kind === "not_refilled") {
      return '<div class="rd-hero is-low"><p class="eyebrow">At the ' + esc(f.short(row.issued_on)) + " satellite look</p>" +
        '<p class="rd-state">No forecast until it refills to ' + esc(arm) + '% full</p><p class="meta">It was ' +
        esc(f.fullness(row.level_pct)) + " then.</p></div>";
    }
    if (d.kind !== "forecast" || d.days_left === null) {
      return '<div class="rd-hero is-low"><p class="rd-state">No recent clear satellite look</p><p class="meta">' +
        esc(row.issued_on ? "Its last clear look was on " + f.date(row.issued_on) + ", so there is no forecast right now." : "So there is no forecast right now.") + "</p></div>";
    }
    const from = ctx.textDate ? "Counted from " + f.dayShort(ctx.textDate) : "Counted from its last clear look";
    if (d.days_left <= 0) {
      return '<div class="rd-hero"><p class="eyebrow">' + esc(from) + '</p><p class="rd-state">It may be below a third now</p>' +
        '<p class="meta">Its cautious days ran out on ' + esc(f.short(f.addDays(row.issued_on, row.damdays_days))) +
        ". The next clear look will tell.</p></div>";
    }
    const cap = d.days_left >= (t.CAP_DAYS || 180);
    const since = ctx.textDate ? t.dayNumber(ctx.textDate) - t.dayNumber(row.issued_on) : 0;
    return '<div class="rd-hero"><p class="eyebrow">' + esc(from) + "</p>" +
      (cap ? '<p class="rd-big"><b>6 months+</b></p>' : '<p class="rd-big"><span>at least</span> <b>' + esc(d.days_left) + "</b> <span>days</span></p>") +
      '<p class="rd-before">before it drops below a third</p>' +
      '<p class="meta"><strong>Cautious by design: built to hold 9 times in 10</strong>, so it will most likely last longer.</p>' +
      (since > 0 ? '<details class="more" data-deep="counted"><summary>How is this counted?' + icon("i-plus", "plus") + '</summary><div class="body"><p>' +
        esc(row.damdays_days + " days from its last clear satellite look (" + f.short(row.issued_on) + "), less the " + since + " days since. " +
        "Each week's text counts from the day it is sent.") + "</p></div></details>" : "") + "</div>";
  }

  function tilesHtml(d) {
    const f = fmt(), row = d.row;
    const full = '<div class="rd-tile"><p class="eyebrow">How full</p><p class="rd-tile-big">' + esc(f.fullness(row.level_pct)) +
      '</p><p class="meta">of its usual full water surface at the ' + esc(row.issued_on ? f.short(row.issued_on) : "last") + " satellite look. Not depth.</p></div>";
    if (row.status !== "forecast" || row.chance === null || row.chance === undefined) return '<div class="rd-tiles">' + full + "</div>";
    const hasBand = row.chance_low !== null && row.chance_low !== undefined && row.chance_high !== null && row.chance_high !== undefined;
    return '<div class="rd-tiles">' + full + '<div class="rd-tile"><p class="eyebrow">Chance by ' + esc(f.short(row.window_end)) +
      '</p><p class="rd-tile-big ch">' + esc(f.chance(row.chance)) + "</p>" + tenDots(row.chance, 5) +
      '<p class="meta">that it drops below a third by then.' + esc(hasBand ? " Wetter or drier season: " + f.chanceRange(row.chance_low, row.chance_high) + "." : "") +
      "</p></div></div>";
  }

  function recordHtml(d) {
    const rec = d.record, tr = model.data.trackRecord, f = fmt();
    if (!tr) return "";
    const min = tr.min_judged || 5;
    if (!rec || !rec.judged || rec.judged < min) {
      return '<section class="rd-card" data-deep="record"><p class="eyebrow">Our record on this dam</p><p>Not enough history: fewer than ' +
        esc(min) + " past forecasts could be checked.</p></section>";
    }
    const share = rec.held / rec.judged;
    const words = D.text.heldShareText(rec.held, rec.judged);
    const seasons = rec.by_season ? Object.keys(rec.by_season).sort().map((y) => {
      const v = rec.by_season[y];
      return '<tr><th scope="row">' + esc(y + "-" + String(Number(y) + 1).slice(2)) + '</th><td class="num">' + esc(v[0] + " of " + v[1]) + "</td></tr>";
    }).join("") : "";
    return '<section class="rd-card" data-deep="record"><p class="eyebrow">Our record on this dam</p>' +
      '<p class="rd-rec">' + esc(f.held(rec.held, rec.judged)) + "</p>" +
      '<div class="rd-tally" role="img" aria-label="' + esc(words) + '"><i style="width:' + (share * 100).toFixed(1) + '%"></i></div>' +
      '<p class="meta">That is ' + esc(rec.held === rec.judged ? words + "." : f.recordLead(rec.held, rec.judged) + f.recordAimWords(rec.held, rec.judged)) +
      " Over " + esc(tr.label || "the last 10 years") + ".</p>" +
      '<p class="small">' + esc(D.text.TRACK_RECORD_HOW || tr.tip || "") + "</p>" +
      (seasons ? '<details class="more"><summary>Season by season' + icon("i-plus", "plus") + '</summary><div class="body">' +
        '<table class="data"><thead><tr><th scope="col">July to June</th><th scope="col" class="num">Held, of checked</th></tr></thead><tbody>' +
        seasons + "</tbody></table>" + (rec.median_days ? "<p>Its typical promise was at least " + esc(rec.median_days) + " days.</p>" : "") +
        "</div></details>" : "") + "</section>";
  }

  /** Straight lines between the curve's points (0 at the look): the chance by day `day`. */
  function curveAt(curve, horizons, day) {
    const xs = [0].concat(horizons), ys = [0].concat(curve.chance);
    for (let i = 1; i < xs.length; i++) {
      if (day <= xs[i]) return ys[i - 1] + (ys[i] - ys[i - 1]) * (day - xs[i - 1]) / (xs[i] - xs[i - 1]);
    }
    return ys[ys.length - 1];
  }

  function sixMonthsHtml(d, ctx) {
    const row = d.row, f = fmt();
    if (row.status !== "forecast" || !model.issue || !model.data.curveFor) return "";
    const curve = model.data.curveFor(model.issue.issue_date, d.dam_id);
    const horizons = model.data.curveHorizons;
    if (!curve || !Array.isArray(horizons) || !Array.isArray(curve.chance)) return "";
    const lines = horizons.map((h, i) => ({ day: h, html: '<div class="rw"><span class="d">by ' + esc(f.short(f.addDays(row.issued_on, h))) +
      "</span>" + tenDots(curve.chance[i], 5) + '<span class="v">' + esc(f.chance(curve.chance[i])) + "</span></div>" }));
    const since = ctx.textDate ? D.text.dayNumber(ctx.textDate) - D.text.dayNumber(row.issued_on) : 0;
    if (since > 0) {
      lines.push({ day: since - 0.1, html: '<div class="rw mark"><span class="d">' + esc(f.dayShort(ctx.textDate)) +
        '</span><span class="line"></span><span class="v">the text</span></div>' });
    }
    const dd = row.damdays_days, last = horizons[horizons.length - 1];
    let sentence = "";
    if (dd !== null && dd !== undefined && dd < last) {
      const day = f.short(f.addDays(row.issued_on, dd));
      lines.push({ day: dd + 0.1, html: '<div class="rw mark dd"><span class="d">' + esc(day) +
        '</span><span class="line"></span><span class="v">DamDays day</span></div>' });
      const v = curveAt(curve, horizons, dd);
      const words = D.text.inTen(v) === 0 ? "less than 1 in 10" : "about " + D.text.chanceText(v);
      sentence = "On " + day + ", the DamDays day, this curve reads " + words + ". They come from two models: the curve is the chance for dams like " +
        "this one; the DamDays number is a cautious count that held 9 times in 10 across all dams in ten test years, less often for spring looks " +
        "and where this curve reads 2 in 10 or more.";
    } else if (dd !== null && dd !== undefined) {
      sentence = "DamDays day: after the end of this chart.";
    }
    lines.sort((a, b) => a.day - b.day);
    return '<section class="rd-card rd-six"><p class="eyebrow">The next six months</p><p class="meta">The chance it drops below a third by each date, counted from the ' +
      esc(f.short(row.issued_on)) + " satellite look:</p>" + lines.map((l) => l.html).join("") +
      (sentence ? '<p class="meta rd-two">' + esc(sentence) + "</p>" : "") + "</section>";
  }

  function historyHtml(d) {
    const data = model.data;
    const history = data.historyFor ? data.historyFor(d.dam_id) : null;
    if (!history || !D.charts || typeof D.charts.waterHistory !== "function" || !data.history) return "";
    let chart = "";
    try {
      chart = D.charts.waterHistory(history, { firstMonth: data.history.first_month, lastMonth: data.history.last_month,
        threshold: model.meta.threshold_pct, untilDate: null, markDate: null });
    } catch (e) { return ""; }
    return '<details class="more" data-deep="history"><summary>' + icon("i-drop") + "<span>How full since " +
      esc(String(data.history.first_month).slice(0, 4)) + "</span>" + icon("i-plus", "plus") + '</summary><div class="body rd-history">' + chart +
      '<p class="small">How full at each clear look, as a share of its usual full water surface. DamDays warns at the line for a third.</p></div></details>';
  }

  function aboutHtml(d) {
    const f = fmt();
    return '<details class="more" data-deep="about"><summary>' + icon("i-info") + "<span>About these numbers</span>" + icon("i-plus", "plus") +
      '</summary><div class="body"><p>' + esc(d.name + " is numbered across " + model.regionName + ". DEA Waterbodies id " + (d.dea_uid || "unknown") +
      (typeof d.area_ha === "number" ? ", " + d.area_ha.toFixed(1) + " ha when full" : "") + ". \"Below a third\" is our plain rounding of below " +
      (typeof model.meta.threshold_pct === "number" ? model.meta.threshold_pct : 30) + "% of its usual full water surface, " +
      "seen from space: satellites see the wet area, not depth.") + "</p>" +
      "<p>" + esc("Data: DEA Waterbodies (Geoscience Australia) and SILO rainfall (Queensland Government), both CC BY 4.0. Satellite looks up to " +
      (model.meta.data_through ? f.date(model.meta.data_through) : "the latest export") + ".") + "</p></div></details>";
  }

  function openFallbackSheet(ctx) {
    const d = ctx.dam;
    const notes = d.row && d.row.notes && d.row.notes.length
      ? '<div class="rd-note">' + icon("i-drop") + "<p>" + d.row.notes.map(esc).join(" ") + "</p></div>" : "";
    const body = '<article class="rd" aria-label="' + esc(d.name) + '">' +
      '<p class="eyebrow">Runway · ' + esc(model.regionName) + "</p>" +
      '<h2 class="rd-title">' + esc(d.name) + "</h2>" +
      '<p class="meta rd-meta">near ' + esc(d.near_town) + (typeof d.area_ha === "number" ? " · " + esc(d.area_ha.toFixed(1)) + " ha when full" : "") + "</p>" +
      heroHtml(d, ctx) + tilesHtml(d) + notes + recordHtml(d) + sixMonthsHtml(d, ctx) +
      '<div class="rd-more surface">' + historyHtml(d) + aboutHtml(d) + "</div>" +
      '<p class="small rd-foot">Not advice: use it alongside your own eyes on the dam.</p></article>';
    const n = ctx.dams.length, i = ctx.index;
    const prev = ctx.dams[(i - 1 + n) % n], next = ctx.dams[(i + 1) % n];
    const el = D.sheet.open({
      title: n > 1 ? d.name + " · " + (i + 1) + " of " + n : d.name,
      label: d.name + ", " + model.regionName,
      head: n > 1 ? { prev: { href: ctx.hrefFor(prev), label: "Previous dam: " + prev.name }, next: { href: ctx.hrefFor(next), label: "Next dam: " + next.name } } : undefined,
      body,
      onClose: () => { markPick(null); const v = D.views && D.views.runway; if (v && v.highlight) v.highlight(null); },
    });
    if (el && ctx.deep) {
      const target = el.querySelector('[data-deep="' + ctx.deep + '"]');
      if (target) {
        if (target.tagName === "DETAILS") target.open = true;
        setTimeout(() => target.scrollIntoView({ block: "start" }), 30);
      }
    }
  }

  // =====================================================================
  // Register
  // =====================================================================
  function render(rootEl) {
    root = rootEl;
    return (D.data.need ? D.data.need("core") : D.data.load()).then((data) => {
      model = build(data);
      root.innerHTML = pageHtml(model);
      bindSketch();
      const canvas = root.querySelector(".region-map .rg-canvas");
      const place = () => placeLabels(canvas);
      requestAnimationFrame(place);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(place);
      if (window.ResizeObserver && canvas) { let last = 0; new ResizeObserver(() => { const w = canvas.clientWidth; if (w && w !== last) { last = w; place(); } }).observe(canvas); }
      root.addEventListener("click", (event) => {
        const key = event.target.closest(".cb-key");
        if (key) { setOnly(key.dataset.only); return; }
        if (event.target.closest("#rg-live-btn")) { openLiveMap(); return; }
        if (event.target.closest("[data-live]")) { openLiveMap(true); return; }
        if (event.target.closest("[data-live-back]")) openLiveMap(false);
      });
    });
  }

  function enter(route) {
    if (!model) return;
    const sub = route.sub || "";
    if (sub.indexOf("dam-") === 0) { openDam(sub.slice(4), route); return; }
    markPick(null);
    const live = D.views && D.views.runway;
    if (live && typeof live.highlight === "function") live.highlight(null);
    if (liveMounted && live && live.show) live.show();
  }

  D.region = { thumb, closestTown, build };
  if (D.router && typeof D.router.register === "function") {
    D.router.register("runway", { render, enter, leave() { markPick(null); } });
  }
})();
