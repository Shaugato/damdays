/* views/more.js (WP-F)
 * More (#more; #more/install opens the install sheet; #install is an alias). UI_SPEC 2.1, 3.9.
 * The places a farmer rarely needs and a judge may want: Runway (every dam we track in the region, for
 * advisers and agencies who look after many farms), About (with the methods and scores for specialists),
 * the Area outlook (set aside) and "Put DamDays on your home screen". Rewind lives inside Proof; a
 * quiet link here finds it too. Numbers come from the data.
 */
window.DamDays = window.DamDays || {};

(function () {
  "use strict";

  const D = window.DamDays;
  const esc = (t) => D.format.escapeHtml(t === null || t === undefined ? "" : t);
  const icon = (id, cls) => (D.icon ? D.icon(id, cls) : "");

  function row(href, ico, title, small, extra) {
    return '<a class="linkrow" href="' + href + '">' + icon(ico) + "<span>" + title + (extra ? " " + extra : "") + (small ? "<small>" + small + "</small>" : "") +
      '</span><span class="chev">' + icon("i-chev") + "</span></a>";
  }

  function pageHtml() {
    return '<div class="wrap page-narrow more-page">' +
      '<header class="page-head"><p class="eyebrow">More</p><h1 id="more-h1">Look closer</h1>' +
      "<p>The whole region, how DamDays works, and what else we built.</p></header>" +
      '<a class="more-feature surface" href="#runway" aria-labelledby="more-runway-t">' +
      '<span class="more-feature-art" id="more-thumb" aria-hidden="true"><span class="skel"></span></span>' +
      '<span class="more-feature-text"><span class="eyebrow">Runway · the region map</span>' +
      '<span class="more-feature-title" id="more-runway-t">Where water is running short</span>' +
      '<span class="more-feature-sub" id="more-runway-sub">Every dam we track in the region, for advisers and agencies who look after many farms.</span>' +
      '<span class="more-feature-go">Open Runway' + icon("i-chev", "sm") + "</span></span></a>" +
      '<h2 class="more-h">About DamDays</h2><div class="linkrows">' +
      row("#about", "i-info", "How it works", "Five steps, honest limits, the data and credits.") +
      row("#about/specialists", "i-chart", "Methods and scores, for specialists", "The test scores with their usual names, each in plain words.") +
      row("#proof/rewind", "i-rewind", "Rewind: the 2018-19 drought", "Inside Proof: what it said at the time, then what happened.") +
      "</div>" +
      '<h2 class="more-h">Also built</h2><div class="linkrows">' +
      row("#outlook", "i-hex", "Area outlook", "A season-ahead outlook for small areas, made for lenders. Set aside to focus on farmers; its result is still reported.",
        '<span class="tag">Set aside</span>') +
      "</div>" +
      '<h2 class="more-h">On your phone</h2><div class="linkrows">' +
      row("#more/install", "i-phone", "Put DamDays on your home screen", "Steps for iPhone and Android.") +
      "</div></div>";
  }

  /**
   * Fill the Runway card from the data: the counts from meta.coverage ("first" part), then a small preview
   * of the region sketch once every dam is in ("core"). Offline or without it, the card still reads and links.
   */
  function fill(root) {
    const thumb = root.querySelector("#more-thumb");
    const noThumb = () => { if (thumb) thumb.hidden = true; };
    const first = D.data.need ? D.data.need("first") : D.data.load();
    first.then((data) => {
      const sub = root.querySelector("#more-runway-sub");
      const cov = data.meta && data.meta.coverage;
      const lsc = cov && cov.live_status_counts;
      if (sub && cov && cov.dams && lsc && data.meta.region) {
        sub.textContent = "All " + D.format.thousands(cov.dams) + " dam-sized waterbodies we track in " + data.meta.region.name +
          ", mostly farm dams; " + D.format.thousands(lsc.already_low || 0) + " already below a third. For advisers and agencies who look after many farms.";
      }
    }, () => { /* the card still reads and links without the data */ });
    // The thumbnail needs every dam (the "core" part, ~90 KB): fetched when the phone is idle, and not at all
    // with Save-Data, on 2G or offline (the card reads and links without it).
    const c = navigator.connection;
    const skip = (c && (c.saveData || /(^|-)2g$/.test(c.effectiveType || ""))) || navigator.onLine === false ||
      (D.pwa && typeof D.pwa.isOffline === "function" && D.pwa.isOffline());
    if (skip) { noThumb(); return; }
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 300));
    idle(() => {
      const all = D.data.need ? D.data.need("core") : D.data.load();
      all.then((data) => {
        const svg = thumb && thumb.isConnected && D.region && typeof D.region.thumb === "function" ? D.region.thumb(data) : "";
        if (svg) thumb.innerHTML = svg; else noThumb();
      }, noThumb);
    }, { timeout: 3000 });
  }

  // ---- the install sheet (#more/install), UI_SPEC 3.9 ----
  function canInstall() {
    if (D.pwa && typeof D.pwa.canInstall === "function") { try { return Boolean(D.pwa.canInstall()); } catch (e) { return false; } }
    return Boolean(document.documentElement.dataset.canInstall && D.pwa && typeof D.pwa.install === "function");
  }

  function openInstall() {
    const ua = navigator.userAgent || "";
    const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
    const standalone = (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
    const iphone = "<li><h3>iPhone (Safari)</h3><ol><li>Tap Share.</li><li>Tap Add to Home Screen. On iOS 26: tap the ··· menu, then Share, " +
      "then Add to Home Screen, and keep Open as Web App on.</li></ol></li>";
    const android = "<li><h3>Android (Chrome)</h3><ol><li>Open the menu (the three dots).</li><li>Tap Install app, or Add to Home screen.</li></ol></li>";
    const body = '<div class="sheet-prose install-sheet"><p class="eyebrow">On your phone</p><h2>Put DamDays on your home screen</h2>' +
      (standalone ? "<p>DamDays is already on your home screen.</p>" :
        (canInstall() ? '<p><button class="btn btn-primary btn-block" type="button" data-install>' + icon("i-phone") + "Install DamDays</button></p>" : "") +
        '<ul class="install-steps">' + (ios ? iphone + android : android + iphone) + "</ul>") +
      saveHtml() +
      "<p class=\"meta\">It opens like an app, with nothing to sign up for. Your homestead point stays on this phone.</p></div>";
    const el = D.sheet.open({ title: "Install", short: true, body });
    wireSave(el);
  }

  // ---- "Save for offline" (UI_SPEC 9.4): every data part at once, so the region map, Rewind, the Area outlook and
  // every dam's water history open with no signal, not only the pages already opened. Needs the offline copy
  // (the service worker), so it is shown only when that is running. ----
  const swOn = () => Boolean(D.pwa && typeof D.pwa.status === "function" && D.pwa.status().sw === "on" &&
    typeof D.pwa.saveAll === "function");

  function saveHtml() {
    if (!swOn()) return "";
    return '<div class="install-save"><h3>Save for offline</h3>' +
      "<p>Keep every part on this phone now: the region map, Rewind, the Area outlook and every dam's water history, " +
      "for when the signal drops.</p>" +
      '<button class="btn btn-secondary btn-block" type="button" data-save-offline>' + icon("i-cloud-off") + "<span>Save for offline</span></button>" +
      '<p class="small install-save-status" data-save-status role="status" aria-live="polite"></p></div>';
  }

  function wireSave(el) {
    const btn = el && el.querySelector("[data-save-offline]");
    if (!btn) return;
    const status = el.querySelector("[data-save-status]");
    const label = btn.querySelector("span");
    const done = (text) => { label.textContent = "Saved on this phone"; btn.disabled = true; if (status) status.textContent = text; };
    // already saved? (the worker counts what it holds)
    if (typeof D.pwa.saved === "function") {
      D.pwa.saved().then((r) => {
        if (!btn.isConnected || !r || !r.ok || !r.total) return;
        if (r.savedCount >= r.total) done("Already saved: all " + r.total + " parts are on this phone.");
        else if (status) status.textContent = r.savedCount + " of " + r.total + " parts are on this phone so far.";
      }, () => {});
    }
    btn.addEventListener("click", () => {
      btn.disabled = true;
      label.textContent = "Saving…";
      if (status) status.textContent = "";
      const failed = () => {
        if (!btn.isConnected) return;
        btn.disabled = false; label.textContent = "Save for offline";
        if (status) status.textContent = "It could not save. Check your signal and try again.";
      };
      D.pwa.saveAll().then((r) => {
        if (!btn.isConnected) return;
        if (r && r.ok) done("Saved on this phone: all " + r.parts + " parts (" + r.added + " new).");
        else failed();
      }, failed);
    });
  }

  let root = null;
  D.router && typeof D.router.register === "function" && D.router.register("more", {
    render(rootEl) {
      root = rootEl;
      root.innerHTML = pageHtml();
      fill(root);
    },
    enter(route) {
      if (route.sub === "install") openInstall();
    },
  });
})();
