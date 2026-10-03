/* sketch.js (WP-C)
 * The drawings: the dam seen from above (5.11), the ten chance dots (5.12) and the
 * tile-free farm sketch with numbered tags (5.9). No map library, no tiles: the
 * sketch is drawn from the dams' real coordinates around the homestead point.
 *
 *   DamDays.sketch.glyph(dam, size, decorative)   -> svg string (dam: level_pct, status, name, issued_on)
 *   DamDays.sketch.dots(chance, r, label, tight)   -> svg string, ten dots, the first N filled ("N in 10")
 *   DamDays.sketch.chanceDot(chance, size)         -> svg string, one ringed dot in the chance's band colour
 *   DamDays.sketch.bandColor(chance)               -> "var(--c2)" etc. (grey var(--c-none) without a chance)
 *   DamDays.sketch.farm(el, opts)                  -> controller { redraw(opts), setOpen(n), hot(n, on), destroy() }
 *     opts.dams       [{ number, name, lat, lon, ... }]  every dam is drawn; only dams with a tag get one
 *     opts.home       { lat, lon }                       the homestead point (the centre)
 *     opts.radiusKm   the circle (3 km)
 *     opts.tag(d)     -> { text, low, quiet, ring, label } or null (no tag: the dam is still drawn)
 *                        low: dashed tag (below a third); quiet: muted tag (no forecast);
 *                        ring: a 3 px ink ring round the dam (the replay's "fell"); label: the link's name
 *     opts.href(d)    -> "#farm/dam-2" (the tag is a link); omit for plain tags
 *     opts.open       the number of the dam whose tag is drawn in ink (open in the sheet)
 *     opts.homeLabel  ["Homestead", "(demo point)"]
 *     opts.ratio      height / width: default 1.12 on phones, 0.92 from 960 px
 *     opts.glyphSize(d) -> px (default 18 for Dams 1-3, 24 for the rest: "drawn larger than life")
 *     opts.onDraw({ tags, untagged, width, height })   after every drawing (e.g. to say "N dams have no tag")
 *   Tags never overlap each other, the dams, the homestead or the labels: a scored search over
 *   candidate spots (distances 42 to 240 px, 17 angles), rejecting overlaps and leader lines through
 *   tags, preferring no crossing leaders, over several orders; a tag that cannot fit is left out
 *   (the dam stays drawn, and the list always reaches it). It re-runs on resize and after fonts load.
 *
 * Wording: "%" only means how full; a chance is "N in 10" (js/text.js inTen rounding).
 */
window.DamDays = window.DamDays || {};

DamDays.sketch = (function () {
  "use strict";

  const esc = (t) => String(t === null || t === undefined ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const short = (iso) => (iso ? +String(iso).slice(8, 10) + " " + MONTHS[+String(iso).slice(5, 7) - 1] : "");
  // The weekly text's own rounding (js/text.js inTen), repeated so the drawings never need text.js.
  const inTen = (c) => (DamDays.text && DamDays.text.inTen ? DamDays.text.inTen(c)
    : Math.floor((Math.floor(c * 1000 + 0.5) + 50) / 100));
  const chanceWords = (c) => {
    if (c === null || c === undefined) return "no forecast";
    const t = inTen(c);
    return t === 0 ? "less than 1 in 10" : t === 10 ? "more than 9 in 10" : t + " in 10";
  };
  const fullWords = (p) => (DamDays.format && DamDays.format.fullness ? DamDays.format.fullness(p)
    : p === null || p === undefined ? "not seen lately" : p >= 100 ? "full" : p <= 0 ? "no water seen" : "~" + p + "% full");

  // ---------------------------------------------------------------------------
  // The dam seen from above: the usual full edge (dam bed), the wet patch scaled by AREA
  // about a point near the wall, and the earth wall along the low side. Never a glass or gauge.
  // ---------------------------------------------------------------------------
  const DAM_PATH = "M20 31C23 15 45 9 63 13C81 17 92 31 89 51C86 72 72 89 50 88C28 87 12 74 11 55C10 45 16 39 20 31Z";

  function isLow(d) {
    return Boolean(d && (d.low === true || d.status === "already_low" || d.kind === "low"));
  }

  function glyph(d, size, decorative) {
    d = d || {};
    size = size || 48;
    const lvl = d.level_pct === null || d.level_pct === undefined ? 0 : Math.max(0, Math.min(d.level_pct, 100));
    const p = lvl / 100;
    const s = Math.sqrt(p).toFixed(3);
    const low = isLow(d);
    const name = d.name || "The dam";
    const label = low
      ? name + " seen from above: below a third at its " + short(d.issued_on) + " satellite look (" + fullWords(d.level_pct) + ")"
      : name + " seen from above: " + fullWords(d.level_pct) + " of its usual water surface";
    const a11y = decorative ? 'aria-hidden="true" focusable="false"' : 'role="img" aria-label="' + esc(label) + '"';
    return '<svg class="dam-glyph" width="' + size + '" height="' + size + '" viewBox="0 0 100 100" ' + a11y + ">" +
      '<path d="' + DAM_PATH + '" fill="var(--dam-bed)" stroke="var(--dam-rim)" stroke-width="' + (low ? 5 : 4) + '"' +
      (low ? ' stroke-dasharray="10 8"' : "") + "/>" +
      (p > 0.004 ? '<path d="' + DAM_PATH + '" fill="var(--water)" transform="translate(64 70) scale(' + s + ') translate(-64 -70)"/>' : "") +
      '<path d="M34 86 Q52 95 74 84" fill="none" stroke="var(--earth)" stroke-width="6" stroke-linecap="round"/>' +
      "</svg>";
  }

  // ---------------------------------------------------------------------------
  // Chance: the band colour (the same bands as settings.chanceBands), ten dots, one dot
  // ---------------------------------------------------------------------------
  function bandColor(c) {
    if (c === null || c === undefined) return "var(--c-none)";
    const t = inTen(c);
    return t === 0 ? "var(--c0)" : t <= 2 ? "var(--c1)" : t <= 4 ? "var(--c2)" : t <= 6 ? "var(--c3)" : "var(--c4)";
  }

  function dots(c, r, label, tight) {
    r = r || 6;
    const t = c === null || c === undefined ? 0 : inTen(c);
    const gap = r * 2 + (tight ? 3 : 4);
    let s = "";
    for (let i = 0; i < 10; i++) {
      const on = i < t;
      s += '<circle cx="' + (r + 1.5 + i * gap) + '" cy="' + (r + 1.5) + '" r="' + r + '" fill="' + (on ? bandColor(c) : "none") +
        '" stroke="' + (on ? "var(--c-ring)" : "var(--line-strong)") + '" stroke-width="1.6"/>';
    }
    const w = 3 + r * 2 + 9 * gap, h = r * 2 + 3;
    return '<svg class="tendots" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="' +
      esc(label || chanceWords(c)) + '">' + s + "</svg>";
  }

  function chanceDot(c, size) {
    size = size || 14;
    const r = size * 0.4;
    return '<svg class="chance-dot" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + " " + size +
      '" aria-hidden="true" focusable="false"><circle cx="' + size / 2 + '" cy="' + size / 2 + '" r="' + r + '" fill="' +
      bandColor(c) + '" stroke="var(--c-ring)" stroke-width="1.6"/></svg>';
  }

  // ---------------------------------------------------------------------------
  // The farm sketch (5.9)
  // ---------------------------------------------------------------------------
  let measureCtx = null;
  function textWidth(t, px) {
    measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
    measureCtx.font = "800 " + px + 'px "Atkinson Hyperlegible Next", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    return measureCtx.measureText(t).width;
  }
  const svgEl = (tag, a, inner) => "<" + tag + " " + Object.keys(a).map((k) => k + '="' + a[k] + '"').join(" ") + ">" +
    (inner || "") + "</" + tag + ">";
  const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  // Do two segments cross (ignoring their very ends)?
  function segX(ax, ay, bx, by, cx, cy, dx, dy) {
    const den = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx);
    if (Math.abs(den) < 1e-9) return false;
    const t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / den;
    const u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / den;
    return t > 0.02 && t < 0.98 && u > 0.02 && u < 0.98;
  }
  // Does the segment pass through the box (its ends excluded, as the 4 px samples it replaces did)? An exact
  // clip of the segment against the box (Liang-Barsky): one step instead of one per 4 px, a long task less on a phone.
  function through(x1, y1, x2, y2, r) {
    const dx = x2 - x1, dy = y2 - y1;
    const n = Math.ceil(Math.hypot(dx, dy) / 4);
    if (n < 2) return false;
    let t0 = 1 / n, t1 = (n - 1) / n;
    const clip = (p, q) => {            // keep the t where p * t < q
      if (p === 0) return q > 0;
      const t = q / p;
      if (p < 0) { if (t > t0) t0 = t; } else if (t < t1) t1 = t;
      return t0 < t1;
    };
    return clip(-dx, x1 - r.x) && clip(dx, r.x + r.w - x1) && clip(-dy, y1 - r.y) && clip(dy, r.y + r.h - y1) && t0 < t1;
  }

  const DESK = "(min-width: 960px)";

  function farm(el, opts) {
    if (!el) return null;
    let o = Object.assign({}, opts || {});
    let lastW = -1;
    let ro = null;
    let onResize = null;

    function draw() {
      if (!el.isConnected || el.clientWidth < 10) return;     // hidden: drawn when it gets a width
      const desk = window.matchMedia && window.matchMedia(DESK).matches;
      const dams = (o.dams || []).filter((d) => d && isFinite(d.lat) && isFinite(d.lon));
      const home = o.home || { lat: 0, lon: 0 };
      const R = Math.max(0.1, Number(o.radiusKm) || 3);
      const W = Math.max(240, Math.floor(el.clientWidth));
      // narrow phones get extra height above and below the circle: room for the tags
      const ratio = o.ratio || (desk ? 0.92 : W < 340 ? 1.42 : W < 480 ? 1.24 : 1.12);
      const H = Math.round(Math.min(W * ratio, desk ? 620 : 640));
      lastW = el.clientWidth;
      const tagPx = W < 330 ? 14 : 15;
      const cos = Math.cos(home.lat * Math.PI / 180);
      const scale = (Math.min(W, H) / 2 - 26) / R;
      const cx = W / 2, cy = H / 2;
      const P = (d) => [cx + (d.lon - home.lon) * 111.32 * cos * scale, cy - (d.lat - home.lat) * 110.57 * scale];
      const gsize = (d) => (typeof o.glyphSize === "function" ? o.glyphSize(d) : (d.number <= 3 ? 18 : 24));
      const fixed = [];
      const box = (x, y, w, h) => fixed.push({ x, y, w, h });
      let s = "";

      // the circle, the inner 1 km ring, the scale words, north
      s += svgEl("circle", { cx, cy, r: (R * scale).toFixed(1), fill: "var(--surface-2)", stroke: "var(--line-strong)", "stroke-width": 1.5, "stroke-dasharray": "6 6" });
      if (R >= 1.5) {
        s += svgEl("circle", { cx, cy, r: scale.toFixed(1), fill: "none", stroke: "var(--line)", "stroke-width": 1.2 });
        s += svgEl("text", { x: (cx + scale + 5).toFixed(1), y: cy + 5, "font-size": 13, fill: "var(--ink-3)" }, "1 km");
        box(cx + scale + 2, cy - 10, 36, 19);
      }
      const rLabel = (Number.isInteger(R) ? R : R.toFixed(1)) + " km";
      const kx = Math.min(cx + R * scale * 0.72 + 8, W - 48), ky = Math.min(cy + R * scale * 0.72 + 16, H - 8);
      s += svgEl("text", { x: kx.toFixed(1), y: ky.toFixed(1), "font-size": 13, "font-weight": 700, fill: "var(--ink-2)" }, rLabel);
      box(kx - 4, ky - 15, 48, 20);
      s += '<g transform="translate(14 10)"><path d="M8 0l6 16-6-4-6 4z" fill="var(--ink)"/>' +
        svgEl("text", { x: 8, y: 31, "text-anchor": "middle", "font-size": 13, "font-weight": 800, fill: "var(--ink)" }, "N") + "</g>";
      box(6, 6, 32, 34);
      // the homestead and its two-line label
      const hl = o.homeLabel || ["Homestead", "(demo point)"];
      box(cx - 20, cy - 20, 40, 40);
      box(cx - 50, cy + 20, 100, 36);
      const homeLabelBox = { x: cx - 50, y: cy + 22, w: 100, h: 32 };      // a leader line should not cross the words
      dams.forEach((d) => { const p = P(d), g = gsize(d); box(p[0] - g / 2 - 2, p[1] - g / 2 - 2, g + 4, g + 4); });

      // candidate spots for each tag
      const items = [];
      dams.forEach((d) => {
        const t = typeof o.tag === "function" ? o.tag(d) : null;
        if (!t || !t.text) return;
        const p = P(d);
        const w = Math.ceil(textWidth(t.text, tagPx)) + (tagPx === 14 ? 48 : 52), h = 36;
        const out = (Math.abs(p[0] - cx) + Math.abs(p[1] - cy) < 1) ? -Math.PI / 2 : Math.atan2(p[1] - cy, p[0] - cx);
        const cands = [];
        [42, 58, 76, 98, 124, 150, 180, 210, 240, 275, 310].forEach((dist, di) => {
          for (let k = -8; k <= 8; k++) {
            const ang = out + (k * Math.PI) / 8;
            let tx = p[0] + Math.cos(ang) * (dist + Math.abs(Math.cos(ang)) * (w / 2 - 16));
            const ty = p[1] + Math.sin(ang) * dist;
            tx = Math.max(w / 2 + 4, Math.min(W - w / 2 - 4, tx));
            cands.push({ x: tx, y: ty, score: di + Math.abs(k) * 0.35 });
          }
        });
        cands.sort((a, b) => a.score - b.score);
        items.push({ d, p, t, w, h, cands });
      });

      const damBoxes = dams.map((d2) => {
        const p2 = P(d2), g = gsize(d2) / 2 + 1;
        return { d: d2, r: { x: p2[0] - g, y: p2[1] - g, w: 2 * g, h: 2 * g } };
      });

      function layout(order) {
        const placed = [];
        const taken = fixed.slice();
        let total = 0, fails = 0, missed = 0;
        order.forEach((it) => {
          let pick = null, loose = null;
          for (const c of it.cands) {
            // the tag's box, with room for its 46 px hit area (5 px above and below)
            const r = { x: c.x - it.w / 2 - 3, y: c.y - it.h / 2 - 5, w: it.w + 6, h: it.h + 10 };
            if (r.y < 1 || r.y + r.h > H - 1 || r.x < 0 || r.x + r.w > W) continue;
            if (taken.some((b) => hit(r, b))) continue;
            let penalty = 0;
            if (placed.some((q) => through(it.p[0], it.p[1], c.x, c.y, q.r) || through(q.it.p[0], q.it.p[1], q.x, q.y, r))) penalty += 90;  // leader under a tag
            if (damBoxes.some((b) => b.d !== it.d && through(it.p[0], it.p[1], c.x, c.y, b.r))) penalty += 40;   // leader over a dam
            if (through(it.p[0], it.p[1], c.x, c.y, homeLabelBox)) penalty += 40;                                  // leader over "Homestead"
            if (placed.some((q) => segX(it.p[0], it.p[1], c.x, c.y, q.it.p[0], q.it.p[1], q.x, q.y))) penalty += 60;  // crossing leaders
            if (penalty) {
              if (!loose || loose.score > c.score + penalty) loose = { it, x: c.x, y: c.y, r, score: c.score + penalty };
              continue;
            }
            pick = { it, x: c.x, y: c.y, r };
            total += c.score;
            break;
          }
          if (!pick && loose) { pick = loose; total += loose.score; }
          // no room: no tag (the list still has the dam). A prio-0 tag (below a third, or the fewest days) costs most to drop.
          if (!pick) { missed++; fails += (it.t.prio || 0) === 0 ? 10 : 1 + (2 - Math.min(2, it.t.prio)); return; }
          placed.push(pick);
          taken.push(pick.r);
        });
        return { placed, score: total + fails * 1000, fails: missed };
      }
      const dist = (a) => Math.hypot(a.p[0] - cx, a.p[1] - cy);
      const byDist = items.slice().sort((a, b) => dist(a) - dist(b));
      const orders = [byDist, byDist.slice().reverse(), items.slice().sort((a, b) => b.w - a.w),
        byDist.slice(3).reverse().concat(byDist.slice(0, 3)), byDist.slice(0, 3).reverse().concat(byDist.slice(3)),
        items.slice().sort((a, b) => a.p[1] - b.p[1]), items.slice().sort((a, b) => b.p[1] - a.p[1]),
        items.slice().sort((a, b) => a.p[0] - b.p[0]), items.slice().sort((a, b) => b.p[0] - a.p[0]),
        items.slice().sort((a, b) => (a.t.prio || 0) - (b.t.prio || 0) || dist(a) - dist(b))];
      let best = null;
      for (const ord of orders) {
        const l = layout(ord);
        if (!best || l.score < best.score) best = l;
        if (best.score === 0) break;          // every tag in its first-choice spot: no order can do better
      }
      best = best || { placed: [], fails: 0 };

      // leader lines, then the dams, then the homestead (all inside one decorative svg)
      best.placed.forEach((q) => {
        s += svgEl("line", { x1: q.it.p[0].toFixed(1), y1: q.it.p[1].toFixed(1), x2: q.x.toFixed(1), y2: q.y.toFixed(1), stroke: "var(--ink-3)", "stroke-width": 1.4 });
      });
      dams.forEach((d) => {
        const p = P(d), g = gsize(d);
        const t = typeof o.tag === "function" ? o.tag(d) : null;
        if (t && t.ring) {
          s += svgEl("circle", { cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: (g / 2 + 5).toFixed(1), fill: "none", stroke: "var(--ink)", "stroke-width": 3 });
        }
        s += '<g transform="translate(' + (p[0] - g / 2).toFixed(1) + " " + (p[1] - g / 2).toFixed(1) + ')">' + glyph(d, g, true) + "</g>";
      });
      s += '<g transform="translate(' + (cx - 12).toFixed(1) + " " + (cy - 12).toFixed(1) + ')" color="var(--ink)">' +
        '<rect x="-4" y="-4" width="32" height="32" rx="9" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.6"/>' +
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"><path d="M4 11l8-6 8 6v9H4z"/><path d="M10 20v-5h4v5"/></svg></g>';
      s += svgEl("text", { x: cx.toFixed(1), y: (cy + 34).toFixed(1), "text-anchor": "middle", "font-size": 13, "font-weight": 800, fill: "var(--ink-2)" }, esc(hl[0] || ""));
      if (hl[1]) s += svgEl("text", { x: cx.toFixed(1), y: (cy + 49).toFixed(1), "text-anchor": "middle", "font-size": 13, fill: "var(--ink-3)" }, esc(hl[1]));

      const openNo = o.open === null || o.open === undefined ? null : Number(o.open);
      // in dam-number order, so Tab steps Dam 1, 2, 3... (the tags never overlap, so paint order does not matter)
      const tagsHtml = best.placed.slice().sort((a, b) => Number(a.it.d.number) - Number(b.it.d.number)).map((q) => {
        const d = q.it.d, t = q.it.t;
        const cls = "tag2" + (t.low ? " is-low" : "") + (t.quiet ? " is-quiet" : "") + (t.ring ? " is-ring" : "") +
          (openNo !== null && openNo === Number(d.number) ? " is-on" : "") + (tagPx === 14 ? " is-small" : "");
        const label = t.label || ((d.name || "Dam " + d.number) + ": " + t.text);
        const isLink = typeof o.href === "function";
        const tagName = isLink ? "a" : "span";
        const attrs = isLink ? ' href="' + esc(o.href(d)) + '"' : ' role="img"';
        return "<" + tagName + ' class="' + cls + '" data-dam="' + esc(d.number) + '"' + attrs +
          ' style="left:' + q.x.toFixed(0) + "px;top:" + q.y.toFixed(0) + 'px" aria-label="' + esc(label) + '">' +
          '<span class="no" aria-hidden="true">' + esc(d.number) + '</span><span aria-hidden="true">' + esc(t.text) + "</span></" + tagName + ">";
      }).join("");
      el.classList.add("sketch");
      el.style.height = H + "px";
      el.innerHTML = '<svg class="sketch-art" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H +
        '" aria-hidden="true" focusable="false">' + s + "</svg>" + tagsHtml;
      el.dataset.tags = String(best.placed.length);
      el.dataset.untagged = String(best.fails || 0);
      if (typeof o.onDraw === "function") { try { o.onDraw({ tags: best.placed.length, untagged: best.fails || 0, width: W, height: H }); } catch (e) { /* ignore */ } }
    }

    function redraw(newOpts) {
      if (newOpts) o = Object.assign(o, newOpts);
      draw();
    }
    function setOpen(n) {
      o.open = n === undefined ? null : n;
      el.querySelectorAll(".tag2").forEach((t) => t.classList.toggle("is-on", n !== null && n !== undefined && Number(t.dataset.dam) === Number(n)));
    }
    function hot(n, on) {
      const t = el.querySelector('.tag2[data-dam="' + n + '"]');
      if (t) t.classList.toggle("is-hot", Boolean(on));
    }
    function destroy() {
      if (ro) ro.disconnect();
      ro = null;
      if (onResize) window.removeEventListener("resize", onResize);
    }

    if (typeof ResizeObserver === "function") {
      ro = new ResizeObserver(() => { if (Math.abs(el.clientWidth - lastW) > 0.5) draw(); });
      ro.observe(el);
    } else {
      onResize = () => { if (el.clientWidth !== lastW) draw(); };
      window.addEventListener("resize", onResize);
    }
    // redraw once the font is in only if it was still loading (tag widths are measured in it); a cold page whose
    // font is already in would otherwise draw twice for nothing
    if (document.fonts && document.fonts.ready && document.fonts.status !== "loaded") {
      document.fonts.ready.then(() => { if (el.isConnected) draw(); }).catch(() => {});
    }
    draw();
    return { redraw, setOpen, hot, destroy, el };
  }

  return { glyph, dots, chanceDot, bandColor, farm, isLow, DAM_PATH };
})();
