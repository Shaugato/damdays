/* check_text_port.js
 * Checks that the app's JavaScript port of the weekly text (app/js/text.js) writes EXACTLY the
 * same texts as the Python original (notify/message.py).
 *
 * Run from the repo root (needs Node.js, nothing else):
 *     node app/tools/check_text_port.js
 *
 * With no arguments it checks:
 *   1. notify/fixtures/spec_examples.json  the 10 worked examples of notify/MESSAGE_SPEC.md
 *   2. notify/fixtures/demo_week.json      this week's 9 demo farms (both development regions)
 *   3. app/data/real/farms.json            the demo farms as the app's "My farm" view runs them:
 *                                          on the app's forecasts.json when the farm is in the app's
 *                                          region, otherwise on the farm's own dams in farms.json
 * The fixtures are written by scripts/16_weekly_texts.py with the Python code. For every farm the
 * dams (closest first), the SMS and the long text must be identical, character for character.
 *
 * Other fixture files can be given as arguments (tests/test_app_text_port.py passes random farms).
 * A fixture is { today, forecasts, cases: [{ farm, dam_ids, sms, long, region? }] }; `forecasts`
 * is one forecasts.json document, or one per region when cases name a `region`. A case (or the whole
 * fixture) may also give `track_record` ({dam_id: {held, judged}}): the long text is then made with
 * the optional track-record line, as notify/message.py's long_text(..., track_record) makes it.
 * Exit code 0 when everything matches, 1 otherwise.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const text = require("../js/text.js");

const REPO = path.resolve(__dirname, "..", "..");
const DEFAULT_FIXTURES = ["notify/fixtures/spec_examples.json", "notify/fixtures/demo_week.json"];
const FARMS_JSON = "app/data/real/farms.json";
const APP_FORECASTS = "app/data/real/forecasts.json";

function readJson(file) {
  return JSON.parse(fs.readFileSync(path.resolve(REPO, file), "utf8"));
}

/** The first place two strings differ, shown with a little context. */
function firstDifference(expected, got) {
  let i = 0;
  while (i < expected.length && i < got.length && expected[i] === got[i]) i++;
  const show = (s) => JSON.stringify(s.slice(Math.max(0, i - 30), i + 30));
  return "at character " + i + ": expected ..." + show(expected) + "... got ..." + show(got) + "...";
}

/** Compare one farm's dams and texts. Returns a list of problems (empty if it matches). */
function checkCase(label, farm, forecasts, today, expected, trackRecord = null) {
  const problems = [];
  let dams;
  let sms;
  let long;
  try {
    dams = text.damsForFarm(farm, forecasts);
    sms = text.smsForDams(dams, today, farm.radius_km);
    long = text.longForDams(dams, today, farm.name || "Your farm", farm.radius_km, trackRecord);
  } catch (error) {
    return [label + ": the port failed: " + error.message];
  }
  if (expected.dam_ids) {
    const ids = dams.map((d) => d.dam_id);
    if (JSON.stringify(ids) !== JSON.stringify(expected.dam_ids)) {
      problems.push(label + ": dams differ: expected " + expected.dam_ids.join(",") + " got " + ids.join(","));
    }
  }
  if (sms !== expected.sms) problems.push(label + ": SMS differs " + firstDifference(expected.sms, sms));
  if (long !== expected.long) problems.push(label + ": long text differs " + firstDifference(expected.long, long));
  if (!text.fitsOneSms(sms)) problems.push(label + ": the SMS does not fit one message (" + text.septets(sms) + " places)");
  return problems;
}

/** Every case of one fixture file. */
function checkFixture(file) {
  const fixture = readJson(file);
  const problems = [];
  fixture.cases.forEach((c, i) => {
    const forecasts = c.forecasts || (c.region ? fixture.forecasts[c.region] : fixture.forecasts);
    const label = path.basename(file) + " #" + (i + 1) + " (" + (c.key || c.farm.farm_id) + ")";
    const trackRecord = c.track_record !== undefined ? c.track_record
      : (fixture.track_record !== undefined ? fixture.track_record : null);
    problems.push(...checkCase(label, c.farm, forecasts, c.today || fixture.today, c, trackRecord));
  });
  return { name: file, cases: fixture.cases.length, problems: problems };
}

/** farms.json, run the way the app's "My farm" view runs it. */
function checkFarmsJson() {
  const farms = readJson(FARMS_JSON);
  const appForecasts = readJson(APP_FORECASTS);
  const problems = [];
  farms.farms.forEach((f) => {
    const farm = { farm_id: f.farm_id, name: f.name, lat: f.lat, lon: f.lon, radius_km: f.radius_km };
    const forecasts = f.dams_in_app ? appForecasts : text.docFromDams(f.dams);
    const label = "farms.json " + f.farm_id + (f.dams_in_app ? " (app forecasts)" : " (its own dams)");
    problems.push(...checkCase(label, farm, forecasts, farms.date,
                               { dam_ids: f.dams.map((d) => d.dam_id), sms: f.sms, long: f.long }));
    // The view also shows each dam's days left; they must equal the ones Python wrote.
    text.damsForFarm(farm, forecasts).forEach((dam, i) => {
      const what = text.kind(dam, farms.date);
      const days = what === "forecast" ? text.daysLeft(dam, farms.date) : null;
      if (what !== f.dams[i].text_kind || days !== f.dams[i].days_left) {
        problems.push(label + ": " + dam.name + " is " + what + " / " + days + " days, farms.json says " +
                      f.dams[i].text_kind + " / " + f.dams[i].days_left);
      }
    });
  });
  return { name: FARMS_JSON, cases: farms.farms.length, problems: problems };
}

function main() {
  const args = process.argv.slice(2);
  const results = (args.length ? args : DEFAULT_FIXTURES).map(checkFixture);
  if (!args.length && fs.existsSync(path.resolve(REPO, FARMS_JSON))) results.push(checkFarmsJson());

  let failed = 0;
  results.forEach((r) => {
    const ok = r.cases - new Set(r.problems.map((p) => p.split(":")[0])).size;
    console.log((r.problems.length ? "DIFFERS " : "same    ") + r.name + ": " + ok + " of " + r.cases + " farms identical");
    r.problems.slice(0, 20).forEach((p) => console.log("    " + p));
    failed += r.problems.length;
  });
  if (failed) {
    console.log("\nThe JavaScript port (app/js/text.js) does NOT match notify/message.py.");
    process.exit(1);
  }
  console.log("\nThe JavaScript port (app/js/text.js) writes exactly the same texts as notify/message.py.");
}

main();
