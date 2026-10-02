/* settings.js
 * Every setting the app's look and wording depend on, in one place.
 * Change a colour or a threshold here and every view follows.
 */
window.DamDays = window.DamDays || {};

DamDays.settings = {
  // Colour bands for "chance of falling below a third" (and the season rating).
  // One hue (orange-brown), light to dark, so the order reads without colour
  // vision: darker always means more risk. Checked for colour-blind safety.
  chanceBands: [
    { min: 0.00, max: 0.10, label: "Under 10%", color: "#fbe0bf" },
    { min: 0.10, max: 0.25, label: "10 to 25%", color: "#f4b073" },
    { min: 0.25, max: 0.50, label: "25 to 50%", color: "#e3803c" },
    { min: 0.50, max: 0.75, label: "50 to 75%", color: "#bb561a" },
    { min: 0.75, max: 1.01, label: "75% or more", color: "#7a320b" },
  ],
  noForecastColor: "#b9b6ae",   // grey: dams without a forecast
  markOutline: "#4a463f",       // thin dark ring so pale dots still show on the map
  selectedOutline: "#1c5cab",   // blue ring around the dam you clicked
  revealOutline: "#111111",     // thick black ring: "this one did run low / dry"
  waterLine: "#256abf",         // the water-history line

  // In Rewind, a forecast of this chance or more counts as "we said likely".
  likelyThreshold: 0.5,

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
