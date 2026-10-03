/* data.js (WP-B)
 * Loads the data the app shows, a part at a time, and builds quick lookups for the views.
 *
 * Where the data comes from:
 *   app/data/datasets.js lists the datasets that exist, preferred first ("real" before "mock"),
 *   and which are split into parts (window.DAMDAYS_SPLIT). Both are written by
 *   app/tools/build_bundle.py. Add ?data=mock to the address to force the mock data.
 *
 *   A split dataset has data/<name>/parts.js (the list) and content-hashed parts
 *   (app/DATA_CONTRACT.md, "Data parts"; UI_SPEC 8.2):
 *     first       meta, scoreboard, farms, proof and the demo farms' dams (entries, today's
 *                 rows and curves, track records). Welcome, My farm, the dam sheet's first
 *                 level, Proof, Questions and About draw from it alone.
 *     farms       the demo farms' dams' water history (fetched when the phone is idle)
 *     core        every other dam: entries, today's rows and curves, track records
 *     rewind      the past forecast dates and their curves
 *     rating      the 2 km cells (the Area outlook)
 *     history-NN  the other dams' water history, in map-area shards
 *   Any other dataset (e.g. mock) is one file, data/<name>/bundle.js.
 *
 * The API (every promise resolves to the SAME prepared object, filled in as parts arrive):
 *   DamDays.data.need("first")          a part (or a list of parts), merged; "first" draws the first screens
 *   DamDays.data.need(["core", "rewind"])
 *   DamDays.data.load()                 every part except the history shards: what the old map
 *                                       views (Runway, Rewind, Area outlook) need. Memoised.
 *   DamDays.data.history(damId)         Promise of { level_pct, events } or null (loads its part once)
 *   DamDays.data.historyPart(damId)     the part holding it ("farms", "history-03"), or null if not known yet
 *   DamDays.data.historyKnown(damId)    true when data.historyFor(damId) is final (loaded, or it has none)
 *   DamDays.data.has(part)              merged already? (sync)
 *   DamDays.data.info()                 { dataset, split, merged: [...], files: {...} } for checks
 *   DamDays.loaded                      the prepared object once "first" is in
 *
 * The prepared object has the same fields as before the split (name, meta, forecasts, dams,
 * damsById, liveIssue, pastIssues, farms, proof, trackRecord, textDate, curveHorizons,
 * history, cells, seasons, scoreboard, curveFor(), historyFor()). Arrays and maps are filled
 * in place when a part arrives, so a reference taken earlier stays good. After "first" alone:
 * every field is there, but dams, rows, curves and track records only for the demo farms'
 * dams, no past issues, no cells, and no water history.
 *
 * Why <script> and not fetch(): it also works when index.html is opened by double-clicking,
 * where browsers block fetch() of local files.
 */
window.DamDays = window.DamDays || {};

DamDays.data = (function () {
  "use strict";

  const REQUIRED = ["meta", "forecasts", "curves", "history", "cells", "scoreboard"];
  const PART_NAMES = ["first", "farms", "core", "rewind", "rating"];
  const LOAD_ALL = ["first", "farms", "core", "rewind", "rating"];
  // Friendly names a view may ask for (each means the part that holds it).
  const ALIASES = {
    meta: "first", scoreboard: "first", proof: "first", track_record: "first", trackRecord: "first",
    sms: "first", text: "first", "history-farms": "farms", forecasts: "core", dams: "core",
    region: "core", map: "core", runway: "core", past: "rewind", cells: "rating", outlook: "rating",
  };

  /** Add a <script> tag to the page and wait until it has run. */
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => { script.remove(); reject(new Error("Could not load " + src)); };
      document.head.appendChild(script);
    });
  }

  /** The datasets to try, in order. ?data=<name> in the address moves that one first. */
  function datasetsToTry() {
    const available = window.DAMDAYS_DATASETS || ["mock"];
    const requested = new URLSearchParams(window.location.search).get("data");
    if (available.includes(requested)) {
      return [requested].concat(available.filter((name) => name !== requested));
    }
    return available;
  }

  const isSplit = (name) => (window.DAMDAYS_SPLIT || []).includes(name);
  const lists = () => window.DAMDAYS_PART_LISTS || {};
  const store = () => (window.DAMDAYS_PART_DATA = window.DAMDAYS_PART_DATA || {});

  /** Turn a bundle (or the "first" part, which has the same shape) into the lookups the views use. */
  function prepare(bundle, name) {
    for (const part of REQUIRED) {
      if (!bundle[part]) throw new Error("data/" + name + " is missing: " + part);
    }
    const forecasts = bundle.forecasts;
    forecasts.issues.forEach((issue) => {
      issue.rowsByDam = new Map(issue.rows.map((row) => [row.dam_id, row]));
    });
    const curvesByIssue = new Map(bundle.curves.issues.map((c) => [c.issue_date, c.by_dam]));
    const cells = bundle.cells || { cells: [], seasons: [] };
    cells.seasons.forEach((season) => {
      season.rowsByCell = new Map(season.rows.map((row) => [row.cell_id, row]));
    });
    const liveIssue = forecasts.issues.find((issue) => issue.kind === "live") || null;
    const farms = bundle.farms || null;
    const history = bundle.history;

    return {
      name: name,
      meta: bundle.meta,
      forecasts: forecasts,
      dams: forecasts.dams,
      damsById: new Map(forecasts.dams.map((dam) => [dam.dam_id, dam])),
      liveIssue: liveIssue,
      pastIssues: forecasts.issues.filter((issue) => issue.kind === "past"),
      // My farm: the demo farms and their weekly texts (farms.json), or null.
      farms: farms,
      // Proof: what accuracy looks like on the test years (proof.json), or null.
      proof: bundle.proof || null,
      // Each dam's record over the last 10 years (track_record.json), or null: how often the
      // cautious days-left number held on that dam (dam sheet, My farm).
      trackRecord: bundle.track_record || null,
      // The day this week's text is sent: days of water are counted from it (My farm, and the
      // live dam card). It is farms.json's date; without one, the latest satellite look.
      textDate: farms ? farms.date : latestLook(liveIssue),
      curveHorizons: bundle.curves.horizons_days,
      history: history,
      cells: cells.cells,
      seasons: cells.seasons,
      scoreboard: bundle.scoreboard,

      /** The six-month curve for a dam on an issue date, or null if there is none. */
      curveFor(issueDate, damId) {
        const byDam = curvesByIssue.get(issueDate);
        return byDam && byDam[damId] ? byDam[damId] : null;
      },

      /** The water history of a dam, or null (none, or its part not loaded yet: see DamDays.data.history). */
      historyFor(damId) {
        return history.by_dam[damId] || null;
      },

      _curvesByIssue: curvesByIssue,
    };
  }

  function latestLook(issue) {
    return issue ? issue.rows.map((r) => r.issued_on).filter(Boolean).sort().pop() || null : null;
  }

  // =========================================================================================
  // The chosen dataset: { name, split, data, listing, merged, historyIndex, inFarms }
  // =========================================================================================
  let chosen = null;          // Promise of the state
  let state = null;           // the state, once chosen
  const inFlight = new Map(); // "real/core" -> Promise of the part's content

  function fetchPart(st, part) {
    const key = st.name + "/" + part;
    if (store()[key]) return Promise.resolve(store()[key]);
    if (inFlight.has(key)) return inFlight.get(key);
    const src = "data/" + st.name + "/" + st.listing.files[part];
    const got = () => {
      const content = store()[key];
      if (!content) throw new Error(src + " did not add its data.");
      return content;
    };
    // parts.js may already have started "first" (when index.html loads it early): wait for that one.
    const early = window.DAMDAYS_PART_LOADS && window.DAMDAYS_PART_LOADS[key];
    let p = early ? early.then(got, () => loadScript(src).then(got)) : loadScript(src).then(got);
    p = p.catch((error) => {
      inFlight.delete(key);                     // can be tried again (back online)
      try { window.dispatchEvent(new CustomEvent("damdays:part-failed", { detail: { part: key } })); } catch (e) { /* old browser */ }
      throw error;
    });
    inFlight.set(key, p);
    return p;
  }

  async function startSplit(name) {
    if (!lists()[name]) await loadScript("data/" + name + "/parts.js");
    const listing = lists()[name];
    if (!listing || !listing.files || !listing.files.first) throw new Error("data/" + name + "/parts.js lists no parts.");
    const st = { name, split: true, listing, merged: new Set(), historyIndex: {}, inFarms: new Set(), data: null };
    const first = await fetchPart(st, "first");
    st.data = prepare(first, name);
    (first.history_in_farms || []).forEach((id) => st.inFarms.add(id));
    st.merged.add("first");
    return st;
  }

  async function startWhole(name) {
    window.DAMDAYS_BUNDLE = null;
    await loadScript("data/" + name + "/bundle.js");
    const bundle = window.DAMDAYS_BUNDLE;
    if (!bundle) throw new Error("data/" + name + "/bundle.js did not set DAMDAYS_BUNDLE.");
    const st = { name, split: false, listing: null, merged: new Set(LOAD_ALL), historyIndex: {}, inFarms: new Set(), data: null };
    st.data = prepare(bundle, name);
    return st;
  }

  async function choose() {
    const errors = [];
    for (const name of datasetsToTry()) {
      if (isSplit(name)) {
        try { return await startSplit(name); } catch (error) { errors.push(error.message); }
      }
      try { return await startWhole(name); } catch (error) { errors.push(error.message); }
    }
    throw new Error(errors.join(" "));
  }

  function base() {
    if (!chosen) {
      chosen = choose().then((st) => {
        state = st;
        DamDays.loaded = st.data;
        decorate(st);
        wrapDamCard();
        if (st.split) warmUp();
        return st;
      }, (error) => { chosen = null; throw error; });
    }
    return chosen;
  }

  // =========================================================================================
  // Merging a part into the prepared object (in place, so earlier references stay good)
  // =========================================================================================
  function merge(st, part, content) {
    if (st.merged.has(part)) return;
    const d = st.data;
    if (part === "farms" || part.indexOf("history-") === 0) {
      Object.assign(d.history.by_dam, content.history || {});
    } else if (part === "core") {
      (content.forecasts_dams || []).forEach((dam) => {
        if (!d.damsById.has(dam.dam_id)) { d.dams.push(dam); d.damsById.set(dam.dam_id, dam); }
      });
      Object.keys(content.live_rows || {}).forEach((date) => {
        const issue = d.forecasts.issues.find((i) => i.kind === "live" && i.issue_date === date);
        if (!issue) return;
        content.live_rows[date].forEach((row) => {
          if (!issue.rowsByDam.has(row.dam_id)) { issue.rows.push(row); issue.rowsByDam.set(row.dam_id, row); }
        });
      });
      Object.keys(content.live_curves || {}).forEach((date) => {
        if (!d._curvesByIssue.has(date)) d._curvesByIssue.set(date, {});
        Object.assign(d._curvesByIssue.get(date), content.live_curves[date]);
      });
      if (d.trackRecord && d.trackRecord.dams) Object.assign(d.trackRecord.dams, content.track_record_dams || {});
      Object.assign(st.historyIndex, content.history_index || {});
      if (!d.farms) d.textDate = latestLook(d.liveIssue);
    } else if (part === "rewind") {
      (content.issues || []).forEach((issue) => {
        issue.rowsByDam = new Map(issue.rows.map((row) => [row.dam_id, row]));
        d.forecasts.issues.push(issue);
        if (issue.kind === "past") d.pastIssues.push(issue);
      });
      (content.curves || []).forEach((c) => d._curvesByIssue.set(c.issue_date, c.by_dam));
    } else if (part === "rating") {
      (content.seasons || []).forEach((season) => {
        season.rowsByCell = new Map(season.rows.map((row) => [row.cell_id, row]));
      });
      Array.prototype.push.apply(d.cells, content.cells || []);
      Array.prototype.push.apply(d.seasons, content.seasons || []);
    }
    st.merged.add(part);
  }

  /** "proof" -> "first", "history-03" -> itself; throws on a name no dataset has. */
  function partName(st, asked) {
    const name = Object.prototype.hasOwnProperty.call(ALIASES, asked) ? ALIASES[asked] : asked;
    const known = st.split ? Object.prototype.hasOwnProperty.call(st.listing.files, name)
      : PART_NAMES.includes(name) || /^history-\d\d$/.test(name);
    if (!known) {
      throw new Error("No data part called '" + asked + "' (parts: " +
        (st.split ? Object.keys(st.listing.files).join(", ") : PART_NAMES.join(", ") + ", history-NN") + ").");
    }
    return name;
  }

  /** Load parts (once each) and merge them in. Resolves to the prepared object. */
  function need(parts) {
    const asked = Array.isArray(parts) ? parts : [parts === undefined || parts === null ? "first" : parts];
    return base().then((st) => {
      const names = asked.map((p) => partName(st, String(p)));
      if (!st.split) return st.data;
      const todo = names.filter((n) => !st.merged.has(n));
      if (!todo.length) return st.data;
      return Promise.all(todo.map((n) => fetchPart(st, n))).then((contents) => {
        todo.forEach((n, i) => merge(st, n, contents[i]));
        return st.data;
      });
    });
  }

  let all = null;
  /** Every part except the history shards (the old map views read all of it). Memoised. */
  function load() {
    if (!all) {
      all = base().then((st) => need(st.split ? (st.listing.load || LOAD_ALL) : "first"))
        .catch((error) => { all = null; throw error; });
    }
    return all;
  }

  /** The part that holds a dam's water history, or null (unknown dam, or "core" not loaded yet). */
  function historyPart(damId) {
    if (!state) return null;
    if (!state.split) return state.data.history.by_dam[damId] ? "first" : null;
    if (state.inFarms.has(damId)) return "farms";
    return state.historyIndex[damId] || null;
  }

  /** True when historyFor(damId) is final: loaded, or this dam has none. */
  function historyKnown(damId) {
    if (!state) return false;
    if (!state.split || state.data.history.by_dam[damId]) return true;
    if (state.inFarms.has(damId) || state.historyIndex[damId]) return false;
    return state.merged.has("core");   // after core, a dam missing from the index has no history
  }

  /** Promise of a dam's water history ({ level_pct, events }) or null; loads its part once. */
  function history(damId) {
    return base().then((st) => {
      const d = st.data;
      if (d.history.by_dam[damId] || !st.split) return d.historyFor(damId);
      if (st.inFarms.has(damId)) return need("farms").then(() => d.historyFor(damId));
      return need("core").then(() => {
        const part = st.historyIndex[damId];
        return part ? need(part).then(() => d.historyFor(damId)) : null;
      });
    });
  }

  /** Give the prepared object the same helpers (older code reads them off the data). */
  function decorate(st) {
    const d = st.data;
    d.parts = st.listing;
    d.need = need;
    d.has = (part) => st.merged.has(part);
    d.historyPart = historyPart;
    d.historyKnown = historyKnown;
    d.hasHistory = historyKnown;
    d.ensureHistory = (damId) => history(damId).then(() => undefined);
  }

  /** After the first screen: fetch the demo farms' history when the phone is idle (not on Save-Data or 2G). */
  function warmUp() {
    const conn = navigator.connection || {};
    if (conn.saveData || /(^|-)2g$/.test(conn.effectiveType || "")) return;
    const later = window.requestIdleCallback
      ? (fn) => window.requestIdleCallback(fn, { timeout: 5000 })
      : (fn) => setTimeout(fn, 1500);
    const go = () => later(() => need("farms").catch(() => { /* offline: the dam sheet says so when it opens */ }));
    if (document.readyState === "complete") go();
    else window.addEventListener("load", go, { once: true });
  }

  /**
   * The old dam card (js/dam-card.js, used by the Runway, Rewind and legacy farm maps) reads the
   * history synchronously. When it is not loaded yet, draw the card at once with a loading line,
   * then draw it again in place when the history arrives.
   */
  function wrapDamCard() {
    const card = DamDays.damCard;
    if (!card || typeof card.render !== "function" || card.render._lazyHistory) return;
    const render = card.render;
    let count = 0;
    const lazy = function (data, damId, issue, options) {
      const html = render.apply(card, arguments);
      if (!data || typeof data.historyKnown !== "function" || data.historyKnown(damId) || !issue ||
          !data.damsById.has(damId) || html.indexOf('<article class="card"') !== 0) return html;
      const token = "dd-card-" + (++count);
      history(damId).then(() => {
        const el = document.querySelector('[data-card-token="' + token + '"]');
        if (el) el.outerHTML = render.call(card, data, damId, issue, options);
      }, () => {
        const note = document.querySelector('[data-card-token="' + token + '"] .card-loading');
        if (note) note.textContent = "The water history needs an internet connection the first time.";
      });
      return html
        .replace('<article class="card"', '<article class="card" data-card-token="' + token + '"')
        .replace(/<\/article>$/, '<p class="chart-note card-loading">Loading how full it has been since 1988&hellip;</p></article>');
    };
    lazy._lazyHistory = true;
    card.render = lazy;
  }
  wrapDamCard();

  function info() {
    if (!state) return { dataset: null, split: null, merged: [], files: null };
    return { dataset: state.name, split: state.split, merged: Array.from(state.merged),
             files: state.listing ? state.listing.files : null };
  }

  return {
    load, need, history, historyPart, historyKnown, info,
    has: (part) => Boolean(state && state.merged.has(part)),
    // js/dam-card.js may load after this file (on demand): it calls this to get the lazy history wrap
    wrapDamCard,
  };
})();
