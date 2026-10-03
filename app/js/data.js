/* data.js
 * Loads the data the app shows, and builds quick lookups for the views.
 *
 * Where the data comes from:
 *   app/data/datasets.js lists the datasets that exist, preferred first
 *   (written by app/tools/build_bundle.py; "real" always comes before "mock").
 *   Each dataset is one file, app/data/<name>/bundle.js, holding the six JSON
 *   files described in app/DATA_CONTRACT.md, plus farms.json (the demo farms and
 *   their weekly texts), proof.json (the Proof view's charts) and track_record.json (each
 *   dam's 2016-2026 track record) when the dataset has them.
 *   Add ?data=mock to the address to force the mock data.
 *
 * Why <script> and not fetch(): it also works when index.html is opened by
 * double-clicking, where browsers block fetch() of local files.
 */
window.DamDays = window.DamDays || {};

DamDays.data = (function () {
  "use strict";

  const PARTS = ["meta", "forecasts", "curves", "history", "cells", "scoreboard"];

  /** Add a <script> tag to the page and wait until it has run. */
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error("Could not load " + src));
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

  /** Stop early with a clear message if a part of the bundle is missing. */
  function checkBundle(bundle, name) {
    if (!bundle) throw new Error("data/" + name + "/bundle.js did not set DAMDAYS_BUNDLE.");
    const missing = PARTS.filter((part) => !bundle[part]);
    if (missing.length) {
      throw new Error("data/" + name + "/bundle.js is missing: " + missing.join(", "));
    }
  }

  /** Turn the raw bundle into the lookups the views use. */
  function prepare(bundle, name) {
    const forecasts = bundle.forecasts;
    forecasts.issues.forEach((issue) => {
      issue.rowsByDam = new Map(issue.rows.map((row) => [row.dam_id, row]));
    });
    const curvesByIssue = new Map(bundle.curves.issues.map((c) => [c.issue_date, c.by_dam]));
    bundle.cells.seasons.forEach((season) => {
      season.rowsByCell = new Map(season.rows.map((row) => [row.cell_id, row]));
    });
    const liveIssue = forecasts.issues.find((issue) => issue.kind === "live") || null;
    const farms = bundle.farms || null;

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
      // Each dam's track record in the 2016-2026 backtest (track_record.json), or null:
      // how often the cautious days-left promise held on that dam (dam card, My farm).
      trackRecord: bundle.track_record || null,
      // The day this week's text is sent: days of water are counted from it (My farm, and the
      // live dam card). It is farms.json's date; without one, the latest satellite look.
      textDate: farms ? farms.date
        : (liveIssue ? liveIssue.rows.map((r) => r.issued_on).filter(Boolean).sort().pop() || null : null),
      curveHorizons: bundle.curves.horizons_days,
      history: bundle.history,
      cells: bundle.cells.cells,
      seasons: bundle.cells.seasons,
      scoreboard: bundle.scoreboard,

      /** The runway curve for a dam on an issue date, or null if there is none. */
      curveFor(issueDate, damId) {
        const byDam = curvesByIssue.get(issueDate);
        return byDam && byDam[damId] ? byDam[damId] : null;
      },

      /** The water history of a dam, or null. */
      historyFor(damId) {
        return bundle.history.by_dam[damId] || null;
      },
    };
  }

  /** Load the first dataset that works. Resolves to the prepared data. */
  async function load() {
    const errors = [];
    for (const name of datasetsToTry()) {
      try {
        window.DAMDAYS_BUNDLE = null;
        await loadScript("data/" + name + "/bundle.js");
        checkBundle(window.DAMDAYS_BUNDLE, name);
        return prepare(window.DAMDAYS_BUNDLE, name);
      } catch (error) {
        errors.push(error.message);
      }
    }
    throw new Error(errors.join(" "));
  }

  return { load };
})();
