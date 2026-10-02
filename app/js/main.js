/* main.js
 * Starts the app: loads the data, shows the MOCK banner if needed, and
 * switches between the five views when a tab is clicked.
 *
 * How the views work: each view file (js/views/*.js) has init(data), run once
 * the first time the view is opened, and show(), run every time it is opened.
 * The address bar keeps the view name (#farm, #runway, #rewind, #rating, #about),
 * so a link can open a view directly and the browser's back button works.
 * My farm (#farm) opens first: the weekly text is the farmer product.
 */
(function () {
  "use strict";

  const VIEW_NAMES = ["farm", "runway", "rewind", "rating", "about"];
  const started = new Set();   // views whose init() has already run
  let data = null;

  /** The view named in the address (#rating), or "farm" (My farm) by default. */
  function viewFromAddress() {
    const name = window.location.hash.replace("#", "");
    return VIEW_NAMES.includes(name) ? name : "farm";
  }

  /** Show one view, hide the others, and mark the active tab. */
  function showView(name) {
    VIEW_NAMES.forEach((other) => {
      document.getElementById("view-" + other).hidden = other !== name;
    });
    document.querySelectorAll(".tabs a").forEach((tab) => {
      if (tab.dataset.view === name) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    });
    const view = DamDays.views[name];
    if (!started.has(name)) {
      view.init(data);   // after un-hiding, so maps can measure their size
      started.add(name);
    }
    view.show();
  }

  /** The big MOCK banner, whenever the data says it is mock. */
  function showMockBanner(meta) {
    const banner = document.getElementById("mock-banner");
    banner.hidden = !meta.is_mock;
    document.body.classList.toggle("is-mock", Boolean(meta.is_mock));
  }

  /** If the data cannot load, say so plainly instead of showing an empty page. */
  function showLoadError(error) {
    const box = document.getElementById("load-error");
    box.hidden = false;
    box.textContent = "The forecast data could not be loaded. " + error.message +
      " If you are developing, run: python app/tools/make_mock_data.py";
  }

  /** A "?" tip opens or closes the explanation that sits right after it. */
  function setUpTips() {
    document.addEventListener("click", (event) => {
      const tip = event.target.closest(".tip");
      if (!tip) return;
      const isOpen = tip.getAttribute("aria-expanded") === "true";
      tip.setAttribute("aria-expanded", String(!isOpen));
      tip.nextElementSibling.hidden = isOpen;
    });
  }

  async function start() {
    setUpTips();
    try {
      data = await DamDays.data.load();
    } catch (error) {
      showLoadError(error);
      return;
    }
    showMockBanner(data.meta);
    window.addEventListener("hashchange", () => showView(viewFromAddress()));
    showView(viewFromAddress());
  }

  start();
})();
