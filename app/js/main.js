/* main.js (WP-A)
 * The shell: the router (every level has its own address, Back steps one level),
 * the tab bar and top nav, DamDays.lazy() for scripts loaded on demand,
 * DamDays.legacy.mount() for the old map views, stub views for any view not yet
 * written, the mock-data banner and the load error.
 *
 * Contracts (UI_SPEC 13.0; research/ui/build/CONTRACTS.md has the full list):
 *   DamDays.router.register(name, { render(root, route), enter(route), leave() })
 *   DamDays.router.go(hash, { replace })
 *   route = { view, sub, deep, params, hash }
 *   DamDays.lazy(src) -> Promise; DamDays.lazy.leaflet() -> Promise<boolean>
 *   DamDays.data.need(part) -> Promise (a stub resolving to DamDays.data.load() until js/data.js has its own)
 *
 * Places: welcome (level 0 of My farm), farm, proof, questions, more, and under More:
 * runway (the region map), about, outlook (the Area outlook, once "Rating").
 * Old links keep working: #map -> #runway, #rewind -> #proof/rewind, #rating -> #outlook,
 * #faq -> #questions, #install -> #more/install. Unknown -> #welcome.
 *
 * Loaded with `defer` after js/data.js and before the views, so views can register at load
 * time; the first route runs once every deferred script has run (DOMContentLoaded).
 */
window.DamDays = window.DamDays || {};

(function () {
  "use strict";

  const D = window.DamDays;
  const esc = (t) => String(t === null || t === undefined ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  // =====================================================================
  // Icons: one inline sprite in index.html (2 px line icons)
  // =====================================================================
  /** DamDays.icon("i-chev") -> '<svg class="i" ...><use href="#i-chev"/></svg>' (decorative unless a label is given). */
  D.icon = function (id, cls, label) {
    const a11y = label ? 'role="img" aria-label="' + esc(label) + '"' : 'aria-hidden="true"';
    return '<svg class="i' + (cls ? " " + cls : "") + '" ' + a11y + ' focusable="false"><use href="#' + id + '"/></svg>';
  };

  // =====================================================================
  // DamDays.lazy(src): load a script (or a .css file) once; resolves when loaded
  // =====================================================================
  /** A failed load: a warning when the phone is offline (the page's own box already says what to do), else an error. */
  D.logLoad = function (error) {
    if (typeof navigator !== "undefined" && navigator.onLine === false) console.warn("DamDays (offline):", error && error.message ? error.message : error);
    else console.error(error);
  };
  const lazyCache = new Map();
  // The app's own stylesheets in cascade order: one loaded on demand goes in its place, before any
  // later one already on the page, so the cascade is the same whichever page opened first.
  const CSS_ORDER = ["fonts/fonts.css", "css/tokens.css", "css/base.css", "css/shell.css", "css/welcome.css", "css/farm.css",
                     "css/dam.css", "css/proof.css", "css/more.css", "css/legacy.css", "css/pwa.css"];
  function placeCss(node, src) {
    const at = CSS_ORDER.indexOf(src);
    if (at >= 0) {
      const later = Array.from(document.head.querySelectorAll('link[rel="stylesheet"]'))
        .find((l) => CSS_ORDER.indexOf(l.getAttribute("href")) > at);
      if (later) { document.head.insertBefore(node, later); return; }
    }
    document.head.appendChild(node);
  }
  D.lazy = function (src, opts) {
    opts = opts || {};
    if (lazyCache.has(src)) return lazyCache.get(src);
    const isCss = opts.css || /\.css(\?|$)/.test(src);
    const p = new Promise((resolve, reject) => {
      const node = document.createElement(isCss ? "link" : "script");
      if (isCss) { node.rel = "stylesheet"; node.href = src; } else { node.src = src; node.async = false; }
      if (opts.integrity) { node.integrity = opts.integrity; node.crossOrigin = ""; }
      else if (opts.crossOrigin !== undefined) node.crossOrigin = opts.crossOrigin;
      node.onload = () => resolve(node);
      node.onerror = () => { lazyCache.delete(src); node.remove(); reject(new Error("Could not load " + src)); };
      if (isCss) placeCss(node, src); else document.head.appendChild(node);
    });
    lazyCache.set(src, p);
    return p;
  };
  /** js/map.js (DamDays.map, the Leaflet helpers): loaded on demand with Leaflet, or by a legacy map view. */
  D.lazy.mapHelpers = function () {
    return D.map ? Promise.resolve(true) : D.lazy("js/map.js").then(() => true, () => false);
  };
  /** Leaflet (CSS and JS) and js/map.js for the farm map, the setup map and the legacy maps.
   *  Resolves true, or false offline (never rejects). */
  D.lazy.leaflet = function () {
    const helpers = D.lazy.mapHelpers();
    if (window.L) return helpers.then(() => true);
    const L = (D.settings && D.settings.leaflet) || {};
    return Promise.all([
      D.lazy(L.css, { css: true, integrity: L.cssIntegrity }).catch(() => null),
      D.lazy(L.js, { integrity: L.jsIntegrity }),
      helpers,
    ]).then(() => Boolean(window.L)).catch(() => false);
  };

  // =====================================================================
  // Data: the prepared object is loaded once and shared
  // =====================================================================
  const hasParts = Boolean(D.data && typeof D.data.need === "function");
  if (D.data && typeof D.data.load === "function" && !hasParts) {
    // Today's data.js loads the whole bundle on every call: keep one promise for everyone.
    const rawLoad = D.data.load;
    let loading = null;
    D.data.load = function () {
      if (!loading) {
        loading = rawLoad.apply(D.data, arguments).then((data) => { D.loaded = data; return data; },
          (error) => { loading = null; throw error; });
      }
      return loading;
    };
    // Stub until WP-B's data.js: every part is in the one bundle.
    D.data.need = function () { return D.data.load(); };
  }

  // =====================================================================
  // ROUTER
  // =====================================================================
  const VIEWS = ["welcome", "farm", "proof", "questions", "more", "runway", "about", "outlook"];
  const TAB_OF = { welcome: "farm", farm: "farm", proof: "proof", questions: "questions",
                   more: "more", runway: "more", about: "more", outlook: "more" };
  const TITLES = { welcome: "DamDays", farm: "My farm", proof: "Proof", questions: "Questions", more: "More",
                   runway: "Runway: the region map", about: "About", outlook: "Area outlook" };
  // first segment -> where it lives now (the rest of the address is kept)
  const ALIASES = { "": "welcome", home: "welcome", map: "runway", region: "runway", rewind: "proof/rewind",
                    rating: "outlook", faq: "questions", install: "more/install" };
  const SUB_ALIASES = { proof: { replay: "rewind" } };

  const registry = {};          // name -> view object (registered by a package)
  const rendered = new Map();   // name -> Promise of render()
  const stubbed = new Set();    // names rendered by a stub
  const listeners = [];
  const savedScroll = {};
  let current = null;           // the route on screen
  let lastHash = null;          // its canonical hash
  let token = 0;                // drops stale async work when the route moves on
  let started = false;
  let pendingScroll = null;     // [data-scroll] target to bring into view after the next route

  const sectionOf = (view) => document.getElementById("v-" + view);

  // Views loaded on demand (UI_SPEC 8.3, first-screen budget 8.1): only the shell and the Welcome load
  // with the page; My farm and the dam sheet are fetched when the phone is idle after the first screen
  // (warmUp below) or when their address opens, whichever comes first. Each file still calls
  // DamDays.router.register() when it runs. The service worker saves every js/*.js with the app
  // shell, so these open offline too.
  // Stylesheets first (each page waits for them, so nothing flashes unstyled), then the code.
  const CARD = ["js/charts.js", "js/dam-card.js", "js/dam-sheet.js"];   // the dam sheet and what it draws with
  const LAZY = {
    farm: CARD.concat(["js/views/farm.js"]),
    // Proof's scored exam sheet shows About's panelHtml (every number, for specialists; styled in more.css)
    proof: ["css/proof.css", "css/more.css", "js/views/proof.js", "js/views/replay.js", "js/views/about.js"],
    questions: ["css/proof.css", "css/more.css", "js/views/questions.js"],   // proof.css: the who-else slot
    more: ["css/more.css", "js/charts.js", "js/views/region.js", "js/views/more.js"],
    runway: ["css/more.css"].concat(CARD, ["js/views/region.js"]),
    about: ["css/more.css", "js/views/about.js"],
    outlook: ["css/more.css", "css/legacy.css", "js/views/rating.js"],
  };
  /** Load a view's files once, in order. Resolves even if one fails: the stub or the error box takes over. */
  function loadView(view) {
    const list = LAZY[view];
    if (!list) return Promise.resolve();
    // every file of the list, even when the view registered already (another page loaded its script):
    // DamDays.lazy() loads each file once, so files already in resolve at once
    // in parallel: scripts added by DamDays.lazy() have async = false, so they still run in list order
    return Promise.all(list.map((src) => D.lazy(src).catch((e) => { D.logLoad(e); })));
  }
  D.lazy.view = loadView;
  const parentHash = (r) => "#" + r.view;
  const paramsObject = () => {
    const out = {};
    new URLSearchParams(location.search).forEach((value, key) => { if (!(key in out)) out[key] = value; });
    return out;
  };

  /** Read an address: "#rewind" -> { view: "proof", sub: "rewind", deep: null, hash: "#proof/rewind" }. */
  function parse(hash) {
    let h = String(hash || "").replace(/^#\/?/, "").replace(/\/+$/, "");
    try { h = decodeURIComponent(h); } catch (e) { /* keep as is */ }
    let parts = h ? h.split("/") : [];
    const first = (parts[0] || "").toLowerCase();
    if (Object.prototype.hasOwnProperty.call(ALIASES, first)) parts = ALIASES[first].split("/").concat(parts.slice(1));
    else if (parts.length) parts[0] = first;
    const view = parts[0];
    if (!VIEWS.includes(view)) return { known: false, anchor: h, view: null };
    let sub = parts[1] || null;
    if (sub && SUB_ALIASES[view] && SUB_ALIASES[view][sub]) sub = SUB_ALIASES[view][sub];
    const deep = parts.slice(2).join("/") || null;
    const canon = "#" + [view, sub, deep].filter(Boolean).join("/");
    return { known: true, view, sub, deep, params: paramsObject(), hash: canon };
  }
  const same = (a, b) => { const x = parse(a), y = parse(b); return x.known && y.known && x.hash === y.hash; };

  /** Register a view: render(root, route) once (may return a Promise), enter(route) on every visit and sub-address, leave(). */
  function register(name, view) {
    let key = String(name || "").toLowerCase();
    if (!VIEWS.includes(key) && Object.prototype.hasOwnProperty.call(ALIASES, key)) key = ALIASES[key].split("/")[0];
    if (!VIEWS.includes(key)) { console.warn("DamDays.router.register: unknown view '" + name + "'"); return; }
    registry[key] = view || {};
    if (stubbed.has(key)) {                         // a stub drew it first: let the real view take over
      stubbed.delete(key);
      rendered.delete(key);
      const root = sectionOf(key);
      if (root && key !== "welcome") root.innerHTML = "";
      if (started && current && current.view === key) apply(current, { viewChanged: true, quiet: true });
    }
  }

  /** Go to an address. { replace: true } replaces the history entry (aliases, the dam pager). */
  function go(hash, opts) {
    hash = String(hash || "");
    if (hash.charAt(0) !== "#") hash = "#" + hash;
    if (opts && opts.replace) {
      const st = history.state;
      history.replaceState({ dd: true, prev: st && st.dd ? st.prev : lastHash }, "", hash);
      route();
    } else if (same(hash, location.hash) || hash === location.hash) {
      route();
    } else {
      location.hash = hash;                         // pushes an entry; hashchange runs route()
    }
  }

  /** One level up: from a sheet back to its page. Uses Back when we came from there, so Back never bounces. */
  function up() {
    if (!current) return;
    const parent = parentHash(current);
    if (current.hash === parent) { if (D.sheet) D.sheet.hide("close"); return; }
    const st = history.state;
    if (st && st.dd && st.prev && same(st.prev, parent)) history.back();
    else go(parent, { replace: true });
  }

  function setTabs(view) {
    const tab = TAB_OF[view];
    document.querySelectorAll("[data-tab]").forEach((a) => {
      if (a.dataset.tab === tab) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }

  function showSection(view) {
    VIEWS.forEach((name) => {
      const s = sectionOf(name);
      if (!s) return;
      const on = name === view;
      s.classList.toggle("is-active", on);
      if (!on) s.classList.remove("is-entering");
    });
    document.documentElement.removeAttribute("data-boot");
    document.body.dataset.view = view;
    document.title = view === "welcome" ? "DamDays: one text a week for each farm dam the satellites can see" : TITLES[view] + " · DamDays";
    setTabs(view);
    if (view === "welcome" && skyWatch) setSky();
  }

  /** The words for a load error: offline (or the offline copy serving the page) says the page is not saved yet. */
  function loadErrorText() {
    return D.pwa && D.pwa.loadErrorText ? D.pwa.loadErrorText()
      : { title: "The forecast data could not be loaded.", body: "Check your signal and try again." };
  }
  function viewErrorHtml() {
    const t = loadErrorText();
    return '<div class="wrap"><div class="load-error" role="alert"><p><strong>' + esc(t.title) + "</strong> " +
      esc(t.body) + "</p>" +
      '<button class="btn btn-primary" type="button" data-retry>Try again</button></div></div>';
  }

  function focusHeading(root) {
    const h = root && root.querySelector("h1");
    if (!h) return;
    if (!h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1");
    try { h.focus({ preventScroll: true }); } catch (e) { h.focus(); }
  }

  /** Render a view once; returns the Promise every later enter() waits for. */
  function ensureRendered(view, r) {
    if (rendered.has(view)) return rendered.get(view);
    const root = sectionOf(view);
    const p = loadView(view)
      .then(() => {
        let impl = registry[view];
        // its code could not load (offline and never saved, or a failed request): show the error box with Try again
        if (!impl && LAZY[view] && !STUBS[view]) throw new Error("Could not load the code of " + view);
        if (!impl) { impl = STUBS[view] || {}; stubbed.add(view); }
        return typeof impl.render === "function" ? impl.render(root, r) : null;
      })
      .then(() => { root.querySelectorAll(":scope > .view-skeleton").forEach((n) => n.remove()); })
      .catch((error) => {
        D.logLoad(error);
        rendered.delete(view);
        if (view !== "welcome") {
          root.innerHTML = viewErrorHtml();
          // the page shows its own box: no second one above it (the shell's, from the first data part)
          const box = document.getElementById("load-error");
          if (box) box.hidden = true;
        }
        throw error;
      });
    rendered.set(view, p);
    return p;
  }

  function implOf(view) { return registry[view] || (stubbed.has(view) ? STUBS[view] : null) || {}; }

  /** Show a route: switch the view if needed, render it once, then enter(route). */
  function apply(r, how) {
    how = how || {};
    const prevView = current ? current.view : null;
    const viewChanged = how.viewChanged || prevView !== r.view;
    const live = started;          // false on the first route: no animation, no focus move
    current = r;
    lastHash = r.hash;
    const my = ++token;

    if (viewChanged) {
      if (prevView && prevView !== r.view) {
        savedScroll[prevView] = window.scrollY;
        const old = implOf(prevView);
        if (typeof old.leave === "function") { try { old.leave(); } catch (e) { console.error(e); } }
      }
      if (D.sheet && D.sheet.isOpen()) D.sheet.hide("route");
      showSection(r.view);
      const section = sectionOf(r.view);
      if (live && !how.quiet && section) {
        section.classList.remove("is-entering");
        void section.offsetWidth;
        section.classList.add("is-entering");
        setTimeout(() => section.classList.remove("is-entering"), 400);
      }
      if (!how.back) window.scrollTo(0, 0);
    }

    const root = sectionOf(r.view);
    return ensureRendered(r.view, r)
      .then(() => {
        if (my !== token) return null;
        const impl = implOf(r.view);
        return typeof impl.enter === "function" ? impl.enter(r) : null;
      })
      .then(() => {
        if (my !== token) return;
        if (!r.sub && D.sheet && D.sheet.isOpen()) D.sheet.hide("route");
        if (r.sub && D.sheet && !D.sheet.isOpen() && FALLBACK_SHEETS[r.view + "/" + r.sub]) FALLBACK_SHEETS[r.view + "/" + r.sub](r);
        if (viewChanged && how.back && savedScroll[r.view] !== undefined) window.scrollTo(0, savedScroll[r.view]);
        if (viewChanged && live && !how.quiet && !(D.sheet && D.sheet.isOpen())) focusHeading(root);
        if (pendingScroll) {
          const target = document.getElementById(pendingScroll);
          pendingScroll = null;
          if (target) setTimeout(() => target.scrollIntoView({ block: "start" }), 30);
        }
        listeners.forEach((fn) => { try { fn(r); } catch (e) { console.error(e); } });
      })
      .catch(() => { /* the view shows its own error box */ });
  }

  /** Read the address bar and show it. Aliases and unknown addresses are replaced, so Back does not bounce. */
  function route() {
    const raw = location.hash;
    const r = parse(raw);
    if (!r.known) {
      const target = r.anchor && document.getElementById(r.anchor);
      if (target && current) {
        // an in-page anchor (the skip link, a stray #id): show it, keep the address we were on
        history.replaceState(history.state, "", lastHash || location.pathname + location.search);
        if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
        target.scrollIntoView({ block: "start" });
        return;
      }
      go("#welcome", { replace: true });
      return;
    }
    const st = history.state;
    const isNew = !(st && st.dd);
    if (raw && raw !== r.hash) {
      history.replaceState({ dd: true, prev: isNew ? lastHash : st.prev }, "", r.hash);   // an alias
    } else if (isNew) {
      history.replaceState({ dd: true, prev: lastHash }, "");
    }
    if (!started && r.sub && isNew) {
      // A deep link opened cold (a QR, a pasted link): put its page underneath, so Back steps one level.
      history.replaceState({ dd: true, prev: null }, "", parentHash(r));
      history.pushState({ dd: true, prev: parentHash(r) }, "", r.hash);
    }
    apply(r, { back: !isNew });
  }

  D.router = {
    register,
    go,
    up,
    parse,
    current: () => current,
    onChange: (fn) => { if (typeof fn === "function") listeners.push(fn); },
    views: VIEWS.slice(),
  };

  // =====================================================================
  // LEGACY VIEWS: the old views (js/views/*.js with init/show) mounted into a new page
  // =====================================================================
  // The old Leaflet views (markup in index.html #legacy-store, code loaded on demand). Each asks only
  // for the data parts it reads (js/data.js need()), not the whole bundle.
  const LEGACY = {
    runway: { section: "view-runway", map: true, parts: ["core"], script: "js/views/runway.js" },
    // region.js: its closestTown() names a region dam "near <town>" on the past-date card
    rewind: { section: "view-rewind", map: true, parts: ["core", "rewind"], script: "js/views/rewind.js", extra: ["js/views/region.js"] },
    rating: { section: "view-rating", map: true, parts: ["rating"], script: "js/views/rating.js" },
  };
  const legacyStarted = new Set();

  /**
   * Move a legacy view's markup (kept in index.html, #legacy-store) into a container and start it:
   * loads Leaflet for map views, waits for the data, runs DamDays.views[name].init(data) once and
   * show() every time. Resolves true when shown, false when that legacy view is not there.
   */
  function mountLegacy(name, container) {
    const spec = LEGACY[name];
    const section = spec && document.getElementById(spec.section);
    if (!section || !container) return Promise.resolve(false);
    // the old views draw the old dam card (js/dam-card.js, with js/charts.js)
    const files = ["css/legacy.css", "js/charts.js", "js/dam-card.js"].concat(spec.extra || [], [spec.script]);
    const code = D.views && D.views[name] ? Promise.resolve()
      : Promise.all(files.map((src) => D.lazy(src).catch((e) => { D.logLoad(e); })));
    return Promise.all([code, D.lazy.mapHelpers()]).then(() => {
      const view = D.views && D.views[name];
      if (!view || typeof view.init !== "function") return false;
      if (section.parentNode !== container) container.appendChild(section);
      section.hidden = false;
      section.classList.add("legacy");
      const data = hasParts && spec.parts ? D.data.need(spec.parts) : D.data.load();
      return Promise.all([spec.map ? D.lazy.leaflet() : true, data]).then(([, loaded]) => {
        if (!legacyStarted.has(name)) { view.init(loaded); legacyStarted.add(name); }
        if (typeof view.show === "function") view.show();
        return true;
      });
    });
  }
  D.legacy = { mount: mountLegacy, has: (name) => Boolean(LEGACY[name]) };

  // =====================================================================
  // STUBS: used only for a view no package has registered yet
  // =====================================================================
  const S = () => D.settings || {};
  const pageHead = (eyebrow, title, id, lead) => '<header class="page-head"><p class="eyebrow">' + esc(eyebrow) + "</p>" +
    '<h1 id="' + id + '">' + esc(title) + "</h1>" + (lead ? "<p>" + esc(lead) + "</p>" : "") + "</header>";
  const linkRow = (href, ico, title, small) => '<a class="linkrow" href="' + href + '">' + D.icon(ico) +
    "<span>" + esc(title) + (small ? "<small>" + esc(small) + "</small>" : "") + '</span><span class="chev">' + D.icon("i-chev") + "</span></a>";

  function legacyStub(name, wrapClass) {
    return {
      render(root) {
        root.innerHTML = '<div class="wrap ' + (wrapClass || "") + '" data-legacy-host="' + name + '"></div>';
        return mountLegacy(name, root.firstChild).then((ok) => {
          if (!ok) root.firstChild.innerHTML = pageHead("DamDays", TITLES[name] || name, name + "-h1", "This part is being rebuilt.");
        });
      },
      enter() { const v = D.views && D.views[name]; if (v && legacyStarted.has(name) && v.show) v.show(); },
    };
  }

  /** The demo farm the first screen shows (settings.defaultFarmId, never a hidden farm). */
  function defaultFarm(data) {
    const farms = data && data.farms ? data.farms.farms : [];
    const hidden = S().hiddenFarmIds || [];
    const wanted = new URLSearchParams(location.search).get("farm");
    return farms.find((f) => f.farm_id === wanted && !hidden.includes(f.farm_id)) ||
      farms.find((f) => f.farm_id === S().defaultFarmId) ||
      farms.find((f) => !hidden.includes(f.farm_id)) || null;
  }

  const STUBS = {
    // The first screen is static in index.html; until welcome.js lands, show the farm's real text plainly.
    welcome: {
      render() {
        return (hasParts ? D.data.need("first") : D.data.load()).then((data) => {
          const farm = defaultFarm(data);
          const sms = document.getElementById("welcome-sms");
          const trust = document.getElementById("welcome-trust");
          if (trust) trust.innerHTML = "";
          if (!farm || !sms) return;
          const when = D.text && D.text.dateText && data.farms.date ? D.text.dateText(data.farms.date) : "";
          sms.innerHTML = '<figure class="stub-sms" aria-label="This week\'s text for the demo farm">' +
            '<div class="stub-head"><span>DamDays <span class="tag">Demo</span></span><span>' + esc(when) + "</span></div>" +
            '<div class="stub-bubble">' + farm.sms.split("\n").map((line) => "<span>" + esc(line) + "</span>").join("") + "</div>" +
            '<figcaption class="stub-foot">Real dams near ' + esc(farm.near_town) + "; the homestead point is made up.</figcaption></figure>";
          const cta = document.getElementById("welcome-see-dams");
          if (cta) cta.textContent = "See the " + farm.dams.length + " dams";
        });
      },
    },
    runway: legacyStub("runway"),
    outlook: legacyStub("rating"),
    questions: {
      render(root) {
        root.innerHTML = '<div class="wrap page-narrow stub-page">' +
          pageHead("Questions", "Questions judges ask", "questions-h1", "Short answers, with where to check.") +
          '<div class="linkrows">' + linkRow("#proof", "i-proof", "How do we know it works?", "Proof: what we said against what happened") +
          linkRow("#about", "i-info", "How does it work, and what can't it see?", "About: how it works, the data, honest limits") + "</div></div>";
      },
    },
    more: {
      render(root) {
        root.innerHTML = '<div class="wrap page-narrow stub-page">' + pageHead("More", "Look closer", "more-h1") +
          '<div class="linkrows">' +
          linkRow("#runway", "i-map", "Runway: the region map", "Every dam-sized waterbody we watch, by its chance of dropping below a third") +
          linkRow("#proof/rewind", "i-rewind", "Rewind: the 2018-19 drought", "What it said at the time, then what happened") +
          linkRow("#about", "i-info", "About DamDays", "How it works, the data, honest limits") +
          linkRow("#outlook", "i-hex", "Area outlook", "Also built, set aside: a season-ahead outlook for small areas") +
          linkRow("#more/install", "i-phone", "Put DamDays on your home screen", "Steps for iPhone and Android") +
          "</div></div>";
      },
    },
  };

  // Sheets the shell opens when the page under them does not (so every address shows something).
  const FALLBACK_SHEETS = {
    "welcome/farm-dam": function () {
      D.sheet.open({
        title: "Farm words", short: true,
        body: '<div class="sheet-prose"><p class="eyebrow">For readers outside Australia</p><h2>What is a farm dam?</h2>' +
          "<p>In Australia a <b>farm dam</b> is the water itself: a pond dug in a paddock to catch run-off, held by an earth wall. " +
          "Sheep and cattle drink from it. DamDays watches its water surface from space.</p>" +
          "<p><b>Grazier:</b> a farmer who raises sheep or cattle on pasture. <b>Paddock:</b> a fenced field. " +
          "<b>Water run:</b> the drive around a farm's dams and troughs to check them. <b>Agistment:</b> paying to graze stock on someone else's land, often in a drought. " +
          "<b>Homestead:</b> the farmhouse. <b>Bore:</b> a well that pumps groundwater.</p></div>",
      });
    },
  };

  // =====================================================================
  // STARTUP: banner, clicks, keys, the first route
  // =====================================================================
  let mockWatch = null;
  function showMock(data) {
    const isMock = Boolean(data && data.meta && data.meta.is_mock);
    const banner = document.getElementById("mock-banner");
    if (banner) banner.hidden = !isMock;
    document.body.classList.toggle("is-mock", isMock);
    // The banner is pinned on wide screens: the sticky top bar and the side sheet sit under it, at its real
    // height (it wraps to two lines on narrower windows and with large text).
    const root = document.documentElement;
    if (!isMock || !banner) { root.style.removeProperty("--mock-h"); return; }
    const set = () => { if (banner.offsetHeight) root.style.setProperty("--mock-h", banner.offsetHeight + "px"); };
    set();
    if (!mockWatch && typeof ResizeObserver === "function") { mockWatch = new ResizeObserver(set); mockWatch.observe(banner); }
  }
  D.shell = { mockBanner: (on) => showMock({ meta: { is_mock: Boolean(on) } }), focusHeading };

  /** Fill small static spots from the data (data-fill="horizon-days" etc.), so no number is typed in. */
  function fillStatic(data) {
    if (!data || !data.meta) return;
    const meta = data.meta;
    const lo = typeof meta.min_dam_area_ha === "number" ? Math.floor(meta.min_dam_area_ha * 10) / 10 : null;
    const cov = meta.coverage && meta.coverage.text ? /to\s+(\d+(?:\.\d+)?)\s*ha/.exec(meta.coverage.text) : null;
    const values = {
      "horizon-days": meta.horizon_days,
      "region-name": meta.region && meta.region.name,
      "since": data.history && data.history.first_month ? String(data.history.first_month).slice(0, 4) : null,
      "size": lo !== null && cov ? "about " + lo + " to " + Math.round(Number(cov[1])) + " ha" : null,
    };
    document.querySelectorAll("[data-fill]").forEach((node) => {
      const v = values[node.dataset.fill];
      if (v !== undefined && v !== null) node.textContent = v;
    });
  }

  // The Welcome's static loading blocks, as index.html has them, to put back when Try again runs.
  const welcomeStart = {};
  function keepWelcomeStart() {
    ["welcome-sms", "welcome-trust"].forEach((id) => {
      const n = document.getElementById(id);
      if (n && welcomeStart[id] === undefined) welcomeStart[id] = n.innerHTML;
    });
  }

  /** The Welcome's text and trust line could not load: say so, and stop their skeletons pulsing. */
  function stopWelcomeSkeletons() {
    const sms = document.getElementById("welcome-sms");
    if (!sms || !sms.hasAttribute("aria-busy")) return;           // already filled
    document.querySelectorAll("#v-welcome .skel").forEach((n) => { n.style.animation = "none"; });
    const bubble = sms.querySelector(".sk-bubble");
    if (bubble) {
      const p = document.createElement("p");
      p.className = "small sk-failed";
      p.textContent = "This week's text could not be loaded.";
      bubble.replaceWith(p);
    }
    sms.removeAttribute("aria-busy");
    const trust = document.getElementById("welcome-trust");
    if (trust) trust.innerHTML = "";
  }

  function showLoadError() {
    const box = document.getElementById("load-error");
    if (!box) return;
    if (!current || current.view === "welcome") stopWelcomeSkeletons();
    // the page on screen already shows its own box (a deep link whose data failed): one box, not two
    const v = current && current.view !== "welcome" && sectionOf(current.view);
    if (v && v.querySelector(".load-error")) { box.hidden = true; return; }
    box.hidden = false;
    const t = loadErrorText();
    box.innerHTML = "<p><strong>" + esc(t.title) + "</strong> " + esc(t.body) + "</p>" +
      '<button class="btn btn-primary" type="button" data-retry>Try again</button>';
  }

  /**
   * Try again: load the page's data and code once more, in place. Never location.reload(): with no signal and
   * no offline copy controlling the page (a first visit, localhost) a reload swaps the app for the browser's
   * own offline page. Failed scripts and data parts are forgotten (DamDays.lazy, js/data.js), so they are
   * asked for again.
   */
  function retry(button) {
    if (!current) { location.reload(); return; }
    const box = document.getElementById("load-error");
    if (box) { box.hidden = true; box.innerHTML = ""; }
    const inSheet = Boolean(button && D.sheet && D.sheet.el && D.sheet.el.contains(button));
    if (inSheet) {
      // only the sheet's part failed: close it and open the same address again
      D.sheet.hide("route");
      apply(current, { quiet: true });
      return;
    }
    const view = current.view;
    rendered.delete(view);
    const root = sectionOf(view);
    if (view === "welcome") {
      Object.keys(welcomeStart).forEach((id) => {
        const n = document.getElementById(id);
        if (n) { n.innerHTML = welcomeStart[id]; if (id === "welcome-sms") n.setAttribute("aria-busy", "true"); }
      });
    } else if (root) {
      root.innerHTML = '<div class="wrap view-skeleton" aria-hidden="true"><span class="skel skel-title"></span><span class="skel skel-card"></span></div>';
    }
    apply(current, { viewChanged: true, quiet: true });
    const first = hasParts ? D.data.need("first") : D.data.load();
    Promise.resolve(first).then((data) => { showMock(data); fillStatic(data); }, (error) => {
      D.logLoad(error);
      showLoadError();
    });
  }

  function onClick(event) {
    const t = event.target;
    if (!(t instanceof Element)) return;
    // the old "?" tips (format.tip): open or close the explanation right after them
    const tip = t.closest(".tip");
    if (tip && tip.nextElementSibling) {
      const isOpen = tip.getAttribute("aria-expanded") === "true";
      tip.setAttribute("aria-expanded", String(!isOpen));
      tip.nextElementSibling.hidden = isOpen;
      return;
    }
    const again = t.closest("[data-retry]");
    if (again) { retry(again); return; }
    const installBtn = t.closest("[data-install]");
    if (installBtn && D.pwa && D.pwa.install) { D.pwa.install(); return; }
    const skip = t.closest("a.skip");
    if (skip) {
      event.preventDefault();
      const main = document.getElementById("main");
      main.focus({ preventScroll: true });
      main.scrollIntoView({ block: "start" });
      return;
    }
    const closer = t.closest("[data-close]");
    if (closer && !(D.sheet && D.sheet.el && D.sheet.el.contains(closer))) { event.preventDefault(); D.sheet.close(); return; }
    const opener = t.closest("[data-open]");
    if (opener) { event.preventDefault(); go(opener.getAttribute("data-open")); return; }
    const a = t.closest("a[href^='#']");
    if (!a || event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (a.closest(".sheet-head") && a.hasAttribute("data-pager")) return;     // sheet.js steps the pager
    const href = a.getAttribute("href");
    if (a.dataset.scroll) pendingScroll = a.dataset.scroll;
    if (a.hasAttribute("data-replace")) { event.preventDefault(); go(href, { replace: true }); return; }
    // Same address as now (a tab tapped again): back to the top of that page.
    if (current && same(href, location.hash || "#welcome") && !(D.sheet && D.sheet.isOpen())) {
      event.preventDefault();
      if (pendingScroll) { const n = document.getElementById(pendingScroll); pendingScroll = null; if (n) n.scrollIntoView({ block: "start" }); }
      else window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
  }

  function start() {
    if (started) return;
    keepWelcomeStart();
    document.addEventListener("click", onClick);
    window.addEventListener("hashchange", route);
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    route();
    started = true;
    watchTabbar();
    watchTopbar();
    watchSky();
    warmUp();
    const first = hasParts ? D.data.need("first") : D.data.load();
    Promise.resolve(first).then((data) => { showMock(data); fillStatic(data); }, (error) => {
      D.logLoad(error);
      showLoadError();
    });
  }

  /** The phone tab bar grows with large text: keep the page's bottom space (--tabbar-real) at its real height,
   *  so content and focus never sit under it. On desktop the bar is hidden (height 0): the variable is removed. */
  function watchTabbar() {
    const bar = document.querySelector(".tabbar");
    if (!bar || typeof ResizeObserver !== "function") return;
    const set = () => {
      const h = bar.offsetHeight;
      if (h > 0) document.documentElement.style.setProperty("--tabbar-real", h + "px");
      else document.documentElement.style.removeProperty("--tabbar-real");
    };
    // observe() reports the bar's size once laid out, so no read here (it would force a layout on a cold page)
    new ResizeObserver(set).observe(bar);
  }

  /** The desktop top bar (sticky, 960 px and up) grows with large text (shell.css): keep --topbar-h, which places
   *  the side sheet, the sticky panels and the scroll padding under it, at its real height. At 100% text the bar
   *  is 64 px and tokens.css's value stands; below 960 px the variable is left to tokens.css. */
  function watchTopbar() {
    const wrap = document.querySelector("#topbar .wrap");
    if (!wrap || typeof ResizeObserver !== "function" || !window.matchMedia) return;
    const wide = window.matchMedia("(min-width: 960px)");
    const root = document.documentElement.style;
    const set = () => {
      const h = Math.ceil(wrap.getBoundingClientRect().height);
      if (wide.matches && h > 64) root.setProperty("--topbar-h", h + "px");
      else root.removeProperty("--topbar-h");
    };
    new ResizeObserver(set).observe(wrap);
    if (typeof wide.addEventListener === "function") wide.addEventListener("change", set);
  }

  /**
   * The Welcome's sky band (shell.css: body[data-view="welcome"], 100% var(--sky-h)) reaches exactly down to the
   * hero's top, whatever sits above it: the mock banner, the offline chip, a load error, larger text. A fixed
   * band left a paper strip across the sky when those stacked lower than it, and a taller one would show sky
   * under a short hero (a landscape phone). Measured only while the Welcome is shown; showSection re-measures.
   */
  let skyWatch = null;
  function setSky() {
    if (document.body.dataset.view !== "welcome") return;
    const hero = document.querySelector("#v-welcome .welcome-hero");
    if (!hero || !hero.offsetHeight) return;
    const top = hero.getBoundingClientRect().top + window.scrollY;
    document.documentElement.style.setProperty("--sky-h", Math.max(0, Math.ceil(top) + 1) + "px");
  }
  function watchSky() {
    if (skyWatch || typeof ResizeObserver !== "function") return;
    skyWatch = new ResizeObserver(setSky);
    ["mock-banner", "topbar", "status-top", "load-error"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) skyWatch.observe(el);
    });
  }

  /** After the first screen, when the phone is idle: fetch My farm and the dam sheet, the next tap
   *  from the Welcome (skipped with Save-Data or on 2G; they then load when their address opens). */
  function warmUp() {
    const c = navigator.connection;
    if (c && (c.saveData || /(^|-)2g$/.test(c.effectiveType || ""))) return;
    const go = () => {
      const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 200));
      idle(() => { loadView("farm"); }, { timeout: 4000 });
    };
    if (document.readyState === "complete") setTimeout(go, 600);
    else window.addEventListener("load", () => setTimeout(go, 600), { once: true });
  }

  if (document.readyState === "complete") setTimeout(start, 0);
  else {
    document.addEventListener("DOMContentLoaded", start, { once: true });
    window.addEventListener("load", start, { once: true });
  }
})();
