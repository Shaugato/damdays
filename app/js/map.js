/* map.js
 * Shared map helpers (Leaflet): make a map with the background tiles, style a
 * dam dot, and zoom to fit. Every view's map is made here so they all match.
 */
window.DamDays = window.DamDays || {};

DamDays.map = (function () {
  "use strict";

  /** True when the Leaflet library loaded from the internet. */
  function leafletReady() {
    return typeof window.L !== "undefined";
  }

  /**
   * Make a map inside the element with this id, with OpenStreetMap tiles.
   * Returns null (and shows a friendly note) if Leaflet could not load, so the
   * rest of the page keeps working offline.
   */
  function create(elementId) {
    const element = document.getElementById(elementId);
    if (!leafletReady()) {
      element.innerHTML = '<p class="map-missing">The map could not load. Check your internet ' +
                          "connection; the rest of the page still works.</p>";
      return null;
    }
    const map = L.map(element);
    const tiles = DamDays.settings.mapTiles;
    L.tileLayer(tiles.url, { attribution: tiles.attribution, maxZoom: tiles.maxZoom }).addTo(map);
    L.control.scale({ imperial: false }).addTo(map);
    allMaps[elementId] = map;
    return map;
  }

  // Every map made so far, by element id. Handy for checking things in the
  // browser console, e.g. DamDays.map.allMaps["runway-map"].getZoom().
  const allMaps = {};

  /**
   * How a dam dot looks.
   * state.chance    the forecast chance (null = no forecast, drawn grey)
   * state.selected  the dam the user clicked
   * state.revealed  Rewind only: show what happened
   * state.outcome   Rewind only: true (fell below a third), false, or null (unknown)
   */
  function damStyle(state) {
    const s = DamDays.settings;
    const style = {
      radius: 7,
      fillColor: DamDays.colors.colorFor(state.chance),
      fillOpacity: 0.95,
      color: s.markOutline,
      opacity: 0.9,
      weight: 1,
      dashArray: null,
    };
    if (state.revealed) {
      if (state.outcome === true) {
        // It happened: a thick black ring, so it stands out without relying on colour.
        style.radius = 8;
        style.color = s.revealOutline;
        style.weight = 3.5;
        style.opacity = 1;
      } else {
        // It did not happen (or we cannot tell): fade the dot back.
        style.fillOpacity = 0.3;
        style.opacity = 0.5;
        if (state.outcome === null) style.dashArray = "2 3";
      }
    }
    if (state.selected) {
      style.radius = 11;
      style.color = s.selectedOutline;
      style.weight = 3;
      style.opacity = 1;
    }
    return style;
  }

  /** Zoom the map so every point is in view. */
  function fitToPoints(map, latLngs) {
    if (!latLngs.length) return;
    const bounds = L.latLngBounds(latLngs);
    const fit = () => map.fitBounds(bounds, { padding: [24, 24] });
    const size = map.getSize();
    if (size.x > 0 && size.y > 0) {
      fit();
      return;
    }
    // The map has no size yet (its window is hidden or still opening).
    // Show the right area for now, and fit properly once it gets a size.
    map.setView(bounds.getCenter(), 8);
    map.once("resize", fit);
  }

  return { create, damStyle, fitToPoints, allMaps };
})();
