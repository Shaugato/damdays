/* format.js
 * Small helpers that turn data values into plain words: dates, chances, day
 * counts. Also escapeHtml, used whenever data text goes into the page.
 *
 * The wording rule (mentor feedback; notify/MESSAGE_SPEC.md): farmers read "%"
 * as how full a dam is. So in the app "%" only ever means fullness, and a chance
 * is written "6 in 10", rounded exactly as the weekly text rounds it (js/text.js).
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

  /** A chance: 0.583 -> "6 in 10"; under 0.05 -> "less than 1 in 10"; none -> "no forecast". */
  function chance(value) {
    if (value === null || value === undefined) return "no forecast";
    return DamDays.text.chanceText(value);
  }

  /**
   * A range of chances: (0.41, 0.73) -> "4 to 7 in 10"; (0.02, 0.31) -> "up to 3 in 10";
   * (0.32, 0.36) -> "3 in 10 either way"; (0.01, 0.03) -> "less than 1 in 10 either way".
   */
  function chanceRange(low, high) {
    const lo = DamDays.text.inTen(low);
    const hi = DamDays.text.inTen(high);
    if (lo === hi) return chance(low) + " either way";
    if (lo >= 1 && hi <= 9) return lo + " to " + hi + " in 10";
    if (lo === 0 && hi <= 9) return "up to " + hi + " in 10";
    return chance(low) + " to " + chance(high);
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

  return { parseDate, dateTime, addDays, date, month, chance, chanceRange, damdays, auc, count, escapeHtml, tip };
})();

/* ---- Additions for the redesign (WP-A, UI_SPEC 13.0) ------------------------------------
 * Plain-word helpers shared by the new views. Same rules as above: "%" only for how full,
 * a chance is "N in 10", how often the promise held is a count ("held 198 of 222 times").
 */
Object.assign(DamDays.format, (function () {
  "use strict";

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // A skill score as a share of the error, rounded DOWN. Port of FRACTIONS in
  // scripts/21_publish_sealed.py (lines 303-305), so the app says what the README says.
  const FRACTIONS = [[1 / 3, "a third"], [0.30, "nearly a third"], [0.25, "a quarter"], [0.225, "nearly a quarter"],
                     [0.20, "a fifth"], [0.18, "nearly a fifth"], [1 / 6, "a sixth"], [1 / 7, "about a seventh"],
                     [0.125, "an eighth"], [0.10, "a tenth"], [0.05, "a twentieth"], [0.0, "a little"]];

  /** 0.235 -> "nearly a quarter"; 0.02 -> "a little"; below 0 (or none) -> null. */
  function fractionWords(skill) {
    if (skill === null || skill === undefined || Number.isNaN(Number(skill))) return null;
    for (const [low, words] of FRACTIONS) {
      if (skill >= low) return words;
    }
    return null;
  }

  /** 0.235 -> "nearly a quarter less error than guessing the usual rate"; 0 or below -> "no less error than ...". */
  function skillWords(skill) {
    if (skill === null || skill === undefined) return "no skill score";
    if (skill <= 0) return "no less error than guessing the usual rate";
    return fractionWords(skill) + " less error than guessing the usual rate";
  }

  /** A share as a whole number in 1,000, rounded as scripts/21 rounds it: 0.8996 -> 900. */
  function inThousand(share) {
    if (share === null || share === undefined) return null;
    return Math.floor(share * 1000 + 0.5);
  }

  /** 0.8996 -> "900 in 1,000". */
  function inThousandText(share) {
    const n = inThousand(share);
    return n === null ? "" : thousands(n) + " in 1,000";
  }

  /** "2026-09-13" -> "13 Sep" (no year: dates on screen sit next to the year they belong to). */
  function short(isoDate) {
    if (!isoDate) return "";
    const d = new Date(String(isoDate).slice(0, 10) + "T00:00:00Z");
    return d.getUTCDate() + " " + MONTHS[d.getUTCMonth()];
  }

  /** "2026-10-02" -> "Fri 2 Oct" (the weekly text's own date style, js/text.js dateText). */
  function dayShort(isoDate) {
    if (!isoDate) return "";
    return DamDays.text && DamDays.text.dateText ? DamDays.text.dateText(String(isoDate).slice(0, 10)) : short(isoDate);
  }

  /**
   * 1640 -> "1,640"; 1234.5 -> "1,234.5". Plain string work, not Intl: the first Intl.NumberFormat loads the
   * locale data, a long task on a slow phone's first screen.
   */
  function thousands(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return String(n);
    const [i, d] = String(Math.abs(x)).split(".");
    return (x < 0 ? "-" : "") + i.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (d ? "." + d : "");
  }

  /**
   * How a dam's record compares with the 9 in 10 the cautious days aim for. One rule everywhere, the same as
   * track_record.json's "dams_below_9_in_10": a record is under the aim when it held less than 9 times in 10
   * (held / judged < 0.9). -> null (no record) | "every" | "aim" (0.9 or more) | "near" (under 0.9, but it
   * still rounds to "about 9 in 10") | "below".
   */
  function recordLevel(heldCount, judged) {
    if (!judged) return null;
    if (heldCount >= judged) return "every";
    const share = heldCount / judged;
    if (share >= 0.9) return "aim";
    return DamDays.text.inTen(share) >= 9 ? "near" : "below";
  }

  /** True when a record held less than 9 times in 10: its card and row say "give extra margin". */
  function recordBelowAim(heldCount, judged) {
    const level = recordLevel(heldCount, judged);
    return level === "near" || level === "below";
  }

  /** A share as "about 8 times in 10", rounded as chances are ("N in 10"). */
  function timesInTen(share) {
    const tenths = DamDays.text.inTen(share);
    if (tenths === 0) return "less than once in 10";
    if (tenths === 1) return "about once in 10";
    if (tenths === 10) return "more than 9 times in 10";
    return "about " + tenths + " times in 10";
  }

  /**
   * The start of a record sentence: "about 9 times in 10", or for a record just under the aim (it would round
   * to "about 9 in 10") "a little under 9 times in 10", so a sentence never says "about 9 ... less than 9".
   */
  function recordLead(heldCount, judged) {
    if (!judged) return "";
    if (heldCount >= judged) return "every time";
    return recordLevel(heldCount, judged) === "near" ? "a little under 9 times in 10" : timesInTen(heldCount / judged);
  }

  /**
   * The end of a record sentence (recordLead + " over the last 10 years" + this), as plain HTML-free words:
   * ", as it aims for." | ": give the days some extra margin." (just under) | ", less often than ... extra margin." | "."
   */
  function recordAimWords(heldCount, judged) {
    const level = recordLevel(heldCount, judged);
    if (level === "aim") return DamDays.text.inTen(heldCount / judged) >= 10 ? "." : ", as it aims for.";
    if (level === "near") return ": give the days some extra margin.";
    if (level === "below") return ", less often than the 9 in 10 it aims for: on this dam, give the days extra margin.";
    return ".";
  }

  /** How full a dam is, in words: 67 -> "~67% full", 100+ -> "full", 0 -> "no water seen" (never "dry"). */
  function fullness(levelPct) {
    if (levelPct === null || levelPct === undefined) return "not seen lately";
    if (levelPct >= 100) return "full";
    if (levelPct <= 0) return "no water seen";
    return "~" + Math.round(levelPct) + "% full";
  }

  /** (198, 222) -> "held 198 of 222 times". */
  function held(heldCount, judged) {
    return "held " + thousands(heldCount) + " of " + thousands(judged) + " times";
  }

  /** "2026-10-03 17:41:02" -> "Sat 3 Oct" (a stamp with a zone is read in Sydney time). */
  function stampDay(stamp) {
    const s = String(stamp || "");
    const m = /^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?/.exec(s);
    if (!m) return "";
    let day = m[1];
    if (/(Z|[+-]\d{2}:?\d{2})$/.test(s) && m[2]) {
      try {
        const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Australia/Sydney", year: "numeric", month: "2-digit", day: "2-digit" })
          .formatToParts(new Date(s));
        const get = (t) => (parts.find((p) => p.type === t) || {}).value;
        day = get("year") + "-" + get("month") + "-" + get("day");
      } catch (e) { /* keep the stamp's own day */ }
    }
    return dayShort(day);
  }

  /**
   * The pass marks written before the build began, from a scored panel, by group (never "N of 2": scripts/21 counts
   * the four marks one by one, and the panel only says whether each group met all of its marks).
   * -> null | { all, sentence: "Pass marks written before the build began: not all met (the forecasts' three marks:
   *    not all met; the area outlook's one mark, set aside: met)." }
   */
  function passMarks(panel) {
    if (!panel || panel.status !== "scored") return null;
    const r = panel.runway || {}, g = panel.rating || {};
    const groups = [];
    if (typeof r.pass_bars_met === "boolean") groups.push(["the forecasts' three marks", r.pass_bars_met, "all met", "not all met"]);
    if (typeof g.pass_bar_met === "boolean") {
      // The drop rule written before the build began: if rainfall alone did as well, the area outlook's claim is dropped.
      const dropped = g.kill_rule_triggered === true ? ", and its drop rule was triggered because rainfall alone did as well, so that claim is dropped" : "";
      groups.push(["the area outlook's one mark, set aside", g.pass_bar_met, "met" + dropped, "not met" + dropped]);
    }
    if (!groups.length) return null;
    const all = groups.every((x) => x[1]);
    const none = groups.every((x) => !x[1]);
    const lead = all ? "all met" : none ? "not met" : "not all met";
    const each = groups.map((x) => x[0] + ": " + (x[1] ? x[2] : x[3])).join("; ");
    return { all, none, lead, sentence: "Pass marks written before the build began: " + lead + " (" + each + ")." };
  }

  /**
   * Whether the cautious days ("at least N days", built to hold 9 times in 10) held as built: one rule
   * everywhere (Proof's hero and exam card, the exam sheet, Questions, About).
   * The rule is the frozen test code's (damdays/evaluation/coverage.py, the one scripts/21's README text reads):
   * on target when |held - target| <= tolerance, in floats. A panel that carries its own on_target flag (the sealed
   * panel: the opening computed it on the unrounded share, scripts/11 copies it) is followed as it is, never judged
   * again. Otherwise the same float test runs here on held, target and the tolerance (the panel's own, else
   * proof.json by_year.floor_tolerance, scripts/17), never typed here. So 0.88 exactly is off target, as in the test
   * code (|0.88 - 0.9| is 0.020000000000000018 in floats); when such an edge result shows as 880 or 920 in 1,000,
   * `edge` is true and the words say the exact check put it just outside. With no tolerance known, it is only
   * "below target" when under the target, and otherwise unjudged.
   * floor: a scoreboard panel's floor { held, target [, tolerance] [, on_target] }, or { held } (proof's target is used).
   * -> null | { held, target, low, high (in 1,000; low/high null without a tolerance), onTarget (null: not known),
   *    below, above, edge, range: "880 to 920" | "", verdict: "on target" | "below target" | "just below target" |
   *    "more cautious than built for" | "more cautious than built for, just above target" | "",
   *    edgeNote: "by the test's exact check, this result is just outside that range" | "",
   *    state: "met" (on target) | "miss" (below) | "neutral" (above the range, or not judged),
   *    icon: "i-check" | "i-x" | "i-up" (more cautious: neither a miss nor a check) | "i-minus" (not judged) }
   */
  function floorCheck(floor, proof) {
    if (!floor || typeof floor.held !== "number") return null;
    const pr = proof || (DamDays.loaded && DamDays.loaded.proof) || null;
    const by = pr && pr.by_year ? pr.by_year : null;
    const target = typeof floor.target === "number" ? floor.target : by && typeof by.floor_target === "number" ? by.floor_target : null;
    const tol = typeof floor.tolerance === "number" ? floor.tolerance
      : by && typeof by.floor_tolerance === "number" ? by.floor_tolerance : null;
    const out = { held: inThousand(floor.held), target: inThousand(target), low: null, high: null, onTarget: null,
                  below: false, above: false, edge: false, range: "", verdict: "", edgeNote: "", state: "neutral", icon: "i-minus" };
    if (target === null) return out;
    if (tol !== null) {
      out.low = inThousand(target - tol);
      out.high = inThousand(target + tol);
      out.range = thousands(out.low) + " to " + thousands(out.high);
    }
    if (typeof floor.on_target === "boolean") out.onTarget = floor.on_target;     // the opening's own flag
    else if (tol !== null) out.onTarget = Math.abs(floor.held - target) <= tol;  // coverage.py's rule, in floats
    if (out.onTarget === true) {
      out.verdict = "on target";
      out.state = "met";
      out.icon = "i-check";
      return out;
    }
    out.below = out.onTarget === false ? floor.held < target : out.held < out.target;
    out.above = out.onTarget === false && !out.below;
    // off target by the exact check, though the count in 1,000 shown beside it rounds to the range's edge
    out.edge = out.onTarget === false && out.low !== null && out.held >= out.low && out.held <= out.high;
    if (out.edge) out.edgeNote = "by the test's exact check, this result is just outside that range";
    if (out.below) {
      out.verdict = out.edge ? "just below target" : "below target";
      out.state = "miss";
      out.icon = "i-x";
    } else if (out.above) {
      out.verdict = "more cautious than built for" + (out.edge ? ", just above target" : "");
      out.icon = "i-up";
    }
    return out;
  }

  /**
   * The unseen exam's result in words, one rule everywhere (the first screen, Proof's exam card, Questions):
   * a gain whose 95% range reaches zero is "no clear gain". sk = panel.runway.skill_vs_usual_rate.
   * shortForm: "the usual guess" (the first screen) instead of "guessing the usual rate".
   */
  function examSkillWords(sk, shortForm) {
    const usual = shortForm ? "the usual guess" : "guessing the usual rate";
    if (!sk || typeof sk.value !== "number") return "no skill score";
    if (sk.value <= 0) return "no less error than " + usual;
    if (typeof sk.ci_low === "number" && sk.ci_low <= 0) return "no clear gain over " + usual + (shortForm ? "" : " (its range reaches zero)");
    return fractionWords(sk.value) + " less error than " + usual;
  }

  /**
   * The unseen exam's status in plain words, from scoreboard.json panels[key=sealed] (never the clock).
   * Pending: no time is promised (the opening comes after this build of the app, on camera).
   * -> null (no panel) | { scored: false, line: "Unseen exam: not opened yet" }
   *    | { scored: true, day: "Sat 3 Oct", line: "Unseen exam, opened Sat 3 Oct: ...", heading: "Unseen exam: opened Sat 3 Oct, scored once" }
   */
  function examStatus(panel) {
    if (!panel) return null;
    if (panel.status !== "scored") {
      return { scored: false, line: "Unseen exam: not opened yet", heading: "Unseen exam: not opened yet",
               when: "not opened yet; we open it once, on camera, after this build of the app" };
    }
    const day = stampDay(panel.scored_at);
    const sk = panel.runway && panel.runway.skill_vs_usual_rate ? panel.runway.skill_vs_usual_rate : null;
    let words = sk ? examSkillWords(sk, true) : "no less error than the usual guess";
    const marks = passMarks(panel);
    if (marks && !marks.all) words += "; pass marks " + marks.lead;
    return { scored: true, day, words,
             line: "Unseen exam, opened" + (day ? " " + day : "") + ": " + words,
             heading: "Unseen exam: opened " + (day ? day + ", " : "") + "scored once",
             when: "opened" + (day ? " " + day : "") + ", scored once" };
  }

  return { fractionWords, skillWords, inThousand, inThousandText, short, dayShort, thousands, fullness, held, stampDay, examStatus,
           recordLevel, recordBelowAim, recordAimWords, recordLead, timesInTen, passMarks, examSkillWords, floorCheck };
})());
