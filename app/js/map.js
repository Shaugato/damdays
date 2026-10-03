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
   * options: passed to L.map (e.g. { keyboard: false } for a map inside a scrolling sheet).
   * Dots and cells are taken out of the Tab order (their tooltips still show on hover and tap): keyboard
   * users get the same dams from the lists beside each map, without hundreds of unnamed Tab stops.
   */
  function create(elementId, options) {
    const element = document.getElementById(elementId);
    if (!leafletReady()) {
      element.innerHTML = '<p class="map-missing">The map could not load. Check your internet ' +
                          "connection; the rest of the page still works.</p>";
      return null;
    }
    const map = L.map(element, options || {});
    // A hover or tap tooltip that would run past the map's edge (a wide one, on a dot near the middle of a phone's
    // map) is slid back inside; the permanent dam numbers stay on their dots.
    map.on("tooltipopen", (event) => {
      const tip = event.tooltip;
      const el = tip && typeof tip.getElement === "function" ? tip.getElement() : null;
      if (!el || (tip.options && tip.options.permanent)) return;
      el.style.marginLeft = "";
      const box = map.getContainer().getBoundingClientRect(), r = el.getBoundingClientRect();
      let dx = 0;
      if (r.left < box.left + 6) dx = box.left + 6 - r.left;
      else if (r.right > box.right - 6) dx = box.right - 6 - r.right;
      if (dx) el.style.marginLeft = ((parseFloat(getComputedStyle(el).marginLeft) || 0) + dx) + "px";
    });
    map.on("layeradd", (event) => {
      const el = event.layer && typeof event.layer.getElement === "function" ? event.layer.getElement() : null;
      if (el && typeof SVGElement !== "undefined" && el instanceof SVGElement) {
        el.setAttribute("tabindex", "-1");
        el.setAttribute("focusable", "false");
      }
    });
    const tiles = DamDays.settings.mapTiles;
    // crossOrigin: tiles come back as CORS responses the service worker may keep for offline (only
    // tiles actually viewed; OpenStreetMap sends Access-Control-Allow-Origin: *).
    L.tileLayer(tiles.url, { attribution: tiles.attribution, maxZoom: tiles.maxZoom, crossOrigin: "" }).addTo(map);
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
   * state.low       already below a third: a hollow ink ring, as the sketches draw it (no chance fill)
   * state.quietLow  with state.low: a thin grey ring instead (Rewind, under the reveal's black rings)
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
    if (state.low) {
      style.fillColor = s.lowFill || "#ffffff";
      style.fillOpacity = 1;
      style.color = s.lowRing || "#14222B";
      style.weight = 2.5;
      style.opacity = 1;
      if (state.quietLow) {
        // Rewind: thin grey rings, so the thick black "it did fall below a third" rings of the reveal stand out
        style.color = s.quietLowRing || "#8E979D";
        style.weight = 1.2;
        style.opacity = 0.75;
        style.fillOpacity = 0.6;
      }
    }
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
