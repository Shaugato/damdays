/* pwa.js (WP-B)
 * What makes DamDays an installable web app, and nothing that gets in a first-time visitor's way
 * (UI_SPEC 9.4, 9.5; PWA_PLAN 1.5 to 1.7):
 *   - registers the service worker (sw.js) once the page has loaded (https; on localhost only
 *     with ?sw=1, remembered, so builders never get stale cached code; ?sw=0 removes it);
 *   - offline: a quiet chip at the top (#status-top) saying what you are looking at;
 *   - a new version deployed: "Updated forecasts are ready. Refresh" above the tab bar (#pwa-bar);
 *     nothing reloads until it is tapped;
 *   - install: Chrome's own mini-infobar is held back; never a prompt, banner or nag. The install
 *     sheet (More, #more/install) and, once, the setup sheet after a homestead is saved, offer it.
 * Nothing here runs from a double-clicked file (service workers need https or localhost).
 *
 * API for the views:
 *   DamDays.pwa.install()             Promise of "accepted" | "dismissed" | "unavailable"
 *   DamDays.pwa.canInstall()          the browser offers installing now (also html[data-can-install])
 *   DamDays.pwa.standalone()          opened from the home screen (also html[data-standalone])
 *   DamDays.pwa.isIOS(), isAndroid()  (also html[data-ios], html[data-android])
 *   DamDays.pwa.shouldOfferInstall()  true once: not installed, installable or iOS, not offered before
 *   DamDays.pwa.markInstallOffered()  after showing that one quiet offer
 *   DamDays.pwa.saveAll()             "Save for offline": Promise of { ok, parts, added } (every data part)
 *   DamDays.pwa.saved()               Promise of { ok, version, saved: { real: [...] }, total, savedCount }
 *   DamDays.pwa.isOffline()           the last signal check failed
 *   DamDays.pwa.loadErrorText()       { title, body } for a page whose data did not load (offline: "not saved yet")
 *   DamDays.pwa.status()              { sw: "off" | "on", controlled, offline, canInstall, standalone, updateReady }
 *   DamDays.pwa.onChange(fn)          fn(status) after any of the above changes (also a "damdays:pwa" event)
 * CSS hooks (pwa.css): .pwa-if-installable, .pwa-if-ios, .pwa-if-android, .pwa-if-standalone,
 * .pwa-if-browser (not installed), .pwa-if-offline.
 */
window.DamDays = window.DamDays || {};

DamDays.pwa = (function () {
  "use strict";

  const D = window.DamDays;
  const root = document.documentElement;
  const store = {
    get(key) { try { return localStorage.getItem("damdays." + key); } catch (e) { return null; } },
    set(key, value) { try { localStorage.setItem("damdays." + key, value); } catch (e) { /* private mode */ } },
    del(key) { try { localStorage.removeItem("damdays." + key); } catch (e) { /* private mode */ } },
  };
  const esc = (t) => String(t === null || t === undefined ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const icon = (id) => (D.icon ? D.icon(id) : "");

  const listeners = [];
  let installEvent = null;
  let offline = false;
  let updateReady = false;
  let registration = null;
  let userAskedRefresh = false;

  const hasSW = "serviceWorker" in navigator;
  const isLocal = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  const standalone = () => (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
    navigator.standalone === true;
  const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isAndroid = () => /android/i.test(navigator.userAgent);
  const controlled = () => Boolean(hasSW && navigator.serviceWorker.controller);

  function status() {
    return {
      sw: registration ? "on" : "off",
      controlled: controlled(),
      offline: offline,
      canInstall: Boolean(installEvent),
      standalone: standalone(),
      updateReady: updateReady,
    };
  }

  function changed() {
    flags();
    const s = status();
    listeners.forEach((fn) => { try { fn(s); } catch (e) { console.error(e); } });
    try { window.dispatchEvent(new CustomEvent("damdays:pwa", { detail: s })); } catch (e) { /* old browser */ }
  }

  function flag(name, on) {
    if (on) root.setAttribute(name, ""); else root.removeAttribute(name);
  }
  /** html[data-ios] etc., so CSS can show the right install steps without waiting for a script. */
  function flags() {
    flag("data-ios", isIOS());
    flag("data-android", isAndroid());
    flag("data-standalone", standalone());
    flag("data-offline", offline);
    if (installEvent) root.dataset.canInstall = "1"; else delete root.dataset.canInstall;
    root.dataset.sw = controlled() ? "on" : "off";
  }

  // ==========================================================================================
  // Chips: offline (top) and update (above the tab bar)
  // ==========================================================================================
  function drop(id) { const el = document.getElementById(id); if (el) el.remove(); }

  function offlineText() {
    const data = D.loaded;
    const when = data && data.textDate && D.format && D.format.date ? D.format.date(data.textDate) : null;
    if (controlled() && when) {
      return "<strong>Offline.</strong> Showing the forecasts saved for the week of " + esc(when) +
        ". New map areas need internet.";
    }
    if (controlled()) return "<strong>Offline.</strong> Showing the forecasts saved on this phone. New map areas need internet.";
    return "<strong>Offline.</strong> Pages you have not opened yet need internet.";
  }

  function showOffline() {
    const slot = document.getElementById("status-top");
    if (!slot) return;
    let el = document.getElementById("pwa-offline");
    if (!el) {
      el = document.createElement("p");
      el.id = "pwa-offline";
      el.className = "pwa-status";
      slot.appendChild(el);
    }
    el.innerHTML = icon("i-cloud-off") + "<span>" + offlineText() + "</span>";
  }

  function offerUpdate(reg) {
    updateReady = true;
    changed();
    const bar = document.getElementById("pwa-bar");
    if (!bar || document.getElementById("pwa-update")) return;
    const el = document.createElement("div");
    el.id = "pwa-update";
    el.className = "pwa-chip";
    el.innerHTML = icon("i-refresh") + "<span>Updated forecasts are ready.</span>" +
      '<button type="button" class="pwa-action" data-pwa="refresh">Refresh</button>' +
      '<button type="button" class="pwa-close" data-pwa="later" aria-label="Not now">' + icon("i-x") + "</button>";
    el.addEventListener("click", (event) => {
      const b = event.target.closest("[data-pwa]");
      if (!b) return;
      if (b.dataset.pwa === "later") { el.remove(); return; }
      const waiting = reg.waiting;
      if (!waiting) { location.reload(); return; }
      userAskedRefresh = true;
      b.disabled = true;
      waiting.postMessage({ type: "SKIP_WAITING" });
    });
    bar.appendChild(el);
  }

  // ==========================================================================================
  // Offline: test the signal for real (navigator.onLine says "online" on one bar with no data)
  // ==========================================================================================
  async function reachable() {
    if (navigator.onLine === false) return false;
    if (!/^https?:$/.test(location.protocol)) return true;
    const ctl = window.AbortController ? new AbortController() : null;
    const timer = ctl ? setTimeout(() => ctl.abort(), 5000) : null;
    try {
      // sw-version.js is never served from the service worker's caches: this goes to the network.
      // With no signal the worker answers 204 + x-damdays-offline (so the page logs no error).
      const r = await fetch("sw-version.js?ping=" + Date.now(), { cache: "no-store", signal: ctl ? ctl.signal : undefined });
      return !r.headers.get("x-damdays-offline");
    } catch (error) {
      return false;
    } finally {
      if (timer) clearTimeout(timer);
    }
  }

  let checking = null;
  function checkOnline() {
    if (!checking) {
      checking = reachable().then((ok) => {
        checking = null;
        const was = offline;
        offline = !ok;
        if (offline) {
          showOffline();
          // the week's date arrives with the data: fill it in then
          if (D.data && D.data.need && !(D.loaded && D.loaded.textDate)) D.data.need("first").then(showOffline, () => {});
        } else {
          drop("pwa-offline");
        }
        if (was !== offline) changed();
        return !offline;
      });
    }
    return checking;
  }

  // ==========================================================================================
  // The service worker
  // ==========================================================================================
  /** Register on https; on localhost only when asked (?sw=1, remembered; ?sw=0 forgets it). */
  function wanted() {
    const asked = new URLSearchParams(location.search).get("sw");
    if (asked === "1" && isLocal) store.set("sw", "1");
    if (asked === "0") { store.del("sw"); return false; }
    if (location.protocol === "https:") return true;
    return isLocal && store.get("sw") === "1";
  }

  /** Take this app's worker and caches away (?sw=0, or localhost without ?sw=1). */
  async function removeWorker() {
    if (!hasSW) return;
    const here = new URL("./", location.href).href;
    const regs = await navigator.serviceWorker.getRegistrations();
    let removed = false;
    for (const reg of regs) {
      if (reg.scope === here) { await reg.unregister(); removed = true; }
    }
    if (removed && window.caches) {
      for (const name of await caches.keys()) if (name.indexOf("damdays-") === 0) await caches.delete(name);
    }
  }

  async function register() {
    // updateViaCache "none": GitHub Pages sends max-age=600; without it a new sw-version.js or
    // parts.js could go unseen by the update check for up to 10 minutes.
    const reg = await navigator.serviceWorker.register("sw.js", { scope: "./", updateViaCache: "none" });
    registration = reg;
    const hadController = controlled();
    if (reg.waiting && hadController) offerUpdate(reg);
    reg.addEventListener("updatefound", () => {
      const worker = reg.installing;
      if (!worker) return;
      worker.addEventListener("statechange", () => {
        if (worker.state === "installed" && controlled()) offerUpdate(reg);
        if (worker.state === "activated") changed();
      });
    });
    // Reload only when a NEW version takes over (not when the first one starts controlling the page).
    let reloading = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (!reloading && (hadController || userAskedRefresh)) { reloading = true; location.reload(); return; }
      changed();
    });
    // Phones keep a home-screen app alive for days: look for a new version when it comes back to the front.
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) reg.update().catch(() => { /* offline */ });
    });
    changed();
    return reg;
  }

  /** Ask the worker something; resolves with its answer (needs an active worker). */
  function ask(message) {
    if (!hasSW || !registration) return Promise.reject(new Error("Saving for offline needs the app to be opened online, over https."));
    return navigator.serviceWorker.ready.then((reg) => new Promise((resolve) => {
      const channel = new MessageChannel();
      channel.port1.onmessage = (event) => resolve(event.data);
      reg.active.postMessage(message, [channel.port2]);
    }));
  }

  /** "Save for offline": every data part (the region map, Rewind, the outlook, every dam's history). */
  function saveAll() { return ask({ type: "SAVE_ALL" }); }
  /** Which parts this phone has saved. */
  function saved() { return ask({ type: "STATUS" }); }

  // ==========================================================================================
  // Install (never a prompt, banner or nag of our own)
  // ==========================================================================================
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();          // no mini-infobar: a first look is for reading
    installEvent = event;
    changed();
  });
  window.addEventListener("appinstalled", () => {
    installEvent = null;
    store.set("installed", "1");
    changed();
  });

  async function install() {
    if (!installEvent) return "unavailable";
    const event = installEvent;
    installEvent = null;
    event.prompt();
    let outcome = "dismissed";
    try { outcome = (await event.userChoice).outcome; } catch (e) { /* closed */ }
    changed();
    return outcome;
  }

  function shouldOfferInstall() {
    if (standalone() || store.get("installed") || store.get("install-offered")) return false;
    return Boolean(installEvent) || isIOS();
  }

  // ==========================================================================================
  // Start
  // ==========================================================================================
  flags();
  window.addEventListener("load", () => {
    if (hasSW && /^https?:$/.test(location.protocol)) {
      if (wanted()) register().catch((error) => console.warn("DamDays: the offline copy could not start.", error));
      else removeWorker().catch(() => {});
    }
    checkOnline();
  });
  window.addEventListener("online", checkOnline);
  window.addEventListener("offline", checkOnline);
  window.addEventListener("damdays:part-failed", () => { checkOnline(); });   // js/data.js: a part did not load
  document.addEventListener("visibilitychange", () => { if (!document.hidden && offline) checkOnline(); });
  if (window.matchMedia) {
    const mq = window.matchMedia("(display-mode: standalone)");
    if (mq.addEventListener) mq.addEventListener("change", changed);
  }

  /**
   * The words for a page whose data did not load (UI_SPEC 5.23): with no signal, or when the
   * offline copy serves the page (then a failed part was never saved), "not saved yet";
   * otherwise "could not be loaded". Returns { title, body } as plain text.
   */
  function loadErrorText() {
    if (offline || navigator.onLine === false || controlled()) {
      return { title: "This page has not been saved on this phone yet.", body: "Connect to the internet once and it will be." };
    }
    return { title: "The forecast data could not be loaded.", body: "Check your signal and try again." };
  }

  return {
    install,
    loadErrorText,
    canInstall: () => Boolean(installEvent),
    standalone, isIOS, isAndroid,
    shouldOfferInstall,
    markInstallOffered: () => store.set("install-offered", "1"),
    saveAll, saved,
    isOffline: () => offline,
    checkOnline,
    status,
    onChange: (fn) => { if (typeof fn === "function") listeners.push(fn); },
  };
})();
