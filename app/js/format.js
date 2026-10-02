/* format.js
 * Small helpers that turn data values into plain words: dates, percentages,
 * day counts. Also escapeHtml, used whenever data text goes into the page.
 */
window.DamDays = window.DamDays || {};

DamDays.format = (function () {
  "use strict";

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  /** Read "2026-09-15" as a date. UTC avoids off-by-one-day time-zone shifts. */
  function parseDate(isoDate) {
    return new Date(isoDate + "T00:00:00Z");
  }

  /** "2026-09-15" -> "15 Sep 2026". */
  function date(isoDate) {
    if (!isoDate) return "unknown date";
    const d = parseDate(isoDate);
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()] + " " + d.getUTCFullYear();
  }

  /** "2026-10-01T23:50:00Z" -> "2 Oct 2026, 09:50" in the viewer's own time zone. */
  function dateTime(isoDateTime) {
    const d = new Date(isoDateTime);
    const pad = (n) => String(n).padStart(2, "0");
    return d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear() + ", " +
           pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  /** "2026-09-15" plus 90 days -> "2026-12-14". */
  function addDays(isoDate, days) {
    const d = parseDate(isoDate);
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }

  /** "2026-09" -> "Sep 2026". */
  function month(isoMonth) {
    const [year, monthNumber] = isoMonth.split("-");
    return MONTHS[Number(monthNumber) - 1] + " " + year;
  }

  /** 0.583 -> "58%". Very small or large chances say "under 1%" / "over 99%". */
  function percent(chance) {
    if (chance === null || chance === undefined) return "no forecast";
    if (chance < 0.005) return "under 1%";
    if (chance > 0.995) return "over 99%";
    return Math.round(chance * 100) + "%";
  }

  /** (0.41, 0.73) -> "41 to 73%". */
  function percentRange(low, high) {
    return Math.round(low * 100) + " to " + Math.round(high * 100) + "%";
  }

  /** The DamDays number: 60 -> "60", anything at or over the cap -> "180+". */
  function damdays(days) {
    const cap = DamDays.settings.damdaysCapDays;
    return days >= cap ? cap + "+" : String(days);
  }

  /** An AUC result {value, ci_low, ci_high} -> "0.81 (0.78 to 0.84)". */
  function auc(result) {
    return result.value.toFixed(2) + " (" + result.ci_low.toFixed(2) +
           " to " + result.ci_high.toFixed(2) + ")";
  }

  /** "12" or "1 dam" / "12 dams": a count with the right plural. */
  function count(n, singular, plural) {
    return n + " " + (n === 1 ? singular : (plural || singular + "s"));
  }

  /** Make text safe to put inside HTML (so data can never inject markup). */
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * A small "?" button that explains a term. Clicking (or tapping) it opens the
   * explanation just below; hovering shows it too, as a plain browser tooltip.
   * main.js does the opening and closing.
   */
  function tip(question, explanation) {
    return '<button type="button" class="tip" aria-expanded="false" title="' + escapeHtml(explanation) + '">' +
           '<span aria-hidden="true">?</span><span class="visually-hidden">' + escapeHtml(question) + "</span>" +
           '</button><span class="tip-text" hidden>' + escapeHtml(explanation) + "</span>";
  }

  return { parseDate, dateTime, addDays, date, month, percent, percentRange, damdays, auc, count, escapeHtml, tip };
})();
