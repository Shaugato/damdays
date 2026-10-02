/* settings.js
 * Every setting the app's look and wording depend on, in one place.
 * Change a colour or a threshold here and every view follows.
 */
window.DamDays = window.DamDays || {};

DamDays.settings = {
  // Colour bands for "chance of falling below a third" (and the season rating).
  // One hue (orange-brown), light to dark, so the order reads without colour
  // vision: darker always means more risk. Checked for colour-blind safety.
  // Bands are in whole tenths, rounded as the app writes a chance ("3 in 10"), so a
  // dam that says "3 in 10" is always in the "3 or 4 in 10" band. No "%": in DamDays
  // "%" only means how full a dam is.
  chanceBands: [
    { minTenths: 0, maxTenths: 0, label: "Less than 1 in 10", color: "#fbe0bf" },
    { minTenths: 1, maxTenths: 2, label: "1 or 2 in 10", color: "#f4b073" },
    { minTenths: 3, maxTenths: 4, label: "3 or 4 in 10", color: "#e3803c" },
    { minTenths: 5, maxTenths: 6, label: "5 or 6 in 10", color: "#bb561a" },
    { minTenths: 7, maxTenths: 10, label: "7 in 10 or more", color: "#7a320b" },
  ],
  noForecastColor: "#b9b6ae",   // grey: dams without a forecast
  markOutline: "#4a463f",       // thin dark ring so pale dots still show on the map
  selectedOutline: "#1c5cab",   // blue ring around the dam you clicked
  revealOutline: "#111111",     // thick black ring: "this one did run low / dry"
  waterLine: "#256abf",         // the water-history line

  // A chance shown as this many in 10 or more counts as "likely" (the Runway summary,
  // and Rewind's hits and misses). The weekly text uses the same line: a dam with a
  // 5 in 10 chance or more is always named.
  likelyInTen: 5,

  // Show "180+" when the DamDays number is this long or longer.
  damdaysCapDays: 180,

  // Below this many dry cells in a season, an AUC is too shaky to show.
  minDryCellsForScore: 5,

  // How many dams to list under "Highest chance" in the Runway panel.
  topDamsToList: 8,

  // Background map. OpenStreetMap's standard tiles (attribution is required).
  mapTiles: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 17,
  },
};
