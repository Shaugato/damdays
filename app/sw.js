/* sw.js (WP-B): the DamDays service worker. Scope: the app folder (/damdays/app/ on GitHub Pages).
 * Other projects on shaugato.github.io share the origin, so every cache is named "damdays-..."
 * and only those are ever touched.
 *
 * What is kept, and how (UI_SPEC 9.4, PWA_PLAN 1.5):
 *   app shell     index.html, CSS, JS, fonts, the manifest, small icons, datasets.js and parts.js
 *                 (the list in sw-version.js, written by app/tools/build_bundle.py). Saved on install
 *                 as one version, then served cache-first. A new deploy changes sw-version.js; the
 *                 browser installs the new version beside the old one and the page offers "Refresh"
 *                 (pwa.js). Nothing reloads by surprise.
 *   data parts    data/<dataset>/<part>.<hash>.js. A content-hashed name never changes: cache-first,
 *                 kept across app versions, pruned when parts.js stops listing them. "first" and
 *                 "farms" are saved on install; the others the first time they are used, or all at
 *                 once from "Save for offline" (message SAVE_ALL).
 *   Leaflet       (unpkg, a versioned URL) and Google Fonts files: cache-first, CORS responses only.
 *   map tiles     (tile.openstreetmap.org) network-first; a copy of each tile actually viewed is kept
 *                 for when the signal drops: at most 300, at most 7 days old. Never prefetched
 *                 (OpenStreetMap's tile policy).
 *   navigations   any page in the scope (#farm, ?data=mock ...) is the saved index.html.
 *   everything else goes to the network untouched (sw-version.js too: pwa.js uses it to test the signal).
 *
 * Emergency: if a broken worker ever ships, copy research/ui/pwa/sw-killswitch.js over this file and push.
 */
importScripts("sw-version.js");
importScripts.apply(self, self.DAMDAYS_SHELL.parts || []);

const SHELL_CACHE = "damdays-shell-" + self.DAMDAYS_SHELL.version;
const DATA_CACHE = "damdays-data";
const RUNTIME_CACHE = "damdays-runtime";
const TILE_CACHE = "damdays-tiles";
const MAX_TILES = 300;
const TILE_MAX_AGE_MS = 7 * 24 * 3600 * 1000;
const SAVED_AT = "x-damdays-saved-at";

const SCOPE = self.registration.scope;
const LISTS = self.DAMDAYS_PART_LISTS || {};
const SHELL_URLS = self.DAMDAYS_SHELL.files.map((f) => new URL(f, SCOPE).href);
const SHELL_SET = new Set(SHELL_URLS);
const INDEX_URLS = [new URL("./", SCOPE).href, new URL("index.html", SCOPE).href];
const PART_URL = /\/data\/[a-z0-9_-]+\/[a-z0-9-]+\.[0-9a-f]{10}\.js$/;
const PING = new URL("sw-version.js", SCOPE).href;

/** Every data part's URL, by dataset: { real: { first: url, ... } }. */
function partUrls() {
  const out = {};
  Object.keys(LISTS).forEach((dataset) => {
    const list = LISTS[dataset];
    out[dataset] = {};
    Object.keys(list.files || {}).forEach((part) => {
      out[dataset][part] = new URL("data/" + dataset + "/" + list.files[part], SCOPE).href;
    });
  });
  return out;
}
const PARTS = partUrls();
const allPartUrls = () => [].concat(...Object.values(PARTS).map((byPart) => Object.values(byPart)));
const precacheUrls = () => [].concat(...Object.keys(LISTS).map((dataset) =>
  (LISTS[dataset].precache || []).map((part) => PARTS[dataset][part]).filter(Boolean)));

/** Save the URLs this cache does not have yet (a content-hashed part never needs saving twice). */
async function addMissing(cacheName, urls) {
  const cache = await caches.open(cacheName);
  const have = new Set((await cache.keys()).map((r) => r.url));
  const todo = urls.filter((u) => !have.has(u));
  await Promise.all(todo.map((u) => cache.add(u)));
  return todo.length;
}

/**
 * Save the app shell as one version. "no-cache": ask the server whether each file changed (ETag), so
 * an unchanged file costs a 304, not a second download, and a stale HTTP-cache copy never slips in.
 * Only the page itself is required: a file missing on the server (say, never committed) is left to
 * the network instead of failing the whole install (which would mean no offline copy at all).
 */
async function saveShell() {
  const cache = await caches.open(SHELL_CACHE);
  const results = await Promise.all(SHELL_URLS.map(async (u) => {
    try {
      const response = await fetch(new Request(u, { cache: "no-cache" }));
      if (!response.ok) return u;
      await cache.put(u, response);
      return null;
    } catch (error) {
      return u;
    }
  }));
  const missing = results.filter(Boolean);
  if (INDEX_URLS.every((u) => missing.includes(u) || !SHELL_SET.has(u))) {
    await caches.delete(SHELL_CACHE);
    throw new Error("DamDays: the page itself could not be saved; no offline copy this time.");
  }
  if (missing.length) console.warn("DamDays: not saved for offline (missing on the server):", missing);
}

self.addEventListener("install", (event) => {
  event.waitUntil(Promise.all([saveShell(), addMissing(DATA_CACHE, precacheUrls())]));
  // A new version takes over as soon as it is saved: forecasts and results change between visits, and
  // nobody should be shown last week's numbers. The page reloads once when it does (js/pwa.js).
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith("damdays-shell-") && name !== SHELL_CACHE) await caches.delete(name);
    }
    const keep = new Set(allPartUrls());
    const data = await caches.open(DATA_CACHE);
    for (const req of await data.keys()) if (!keep.has(req.url)) await data.delete(req);
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  const msg = event.data || {};
  const reply = (body) => { if (event.ports && event.ports[0]) event.ports[0].postMessage(body); };
  if (msg.type === "SKIP_WAITING") {
    self.skipWaiting();
  } else if (msg.type === "SAVE_ALL") {
    // "Save for offline": every data part of every dataset listed (the history shards, Rewind, the outlook).
    const all = allPartUrls();
    event.waitUntil(addMissing(DATA_CACHE, all).then(
      (added) => reply({ ok: true, parts: all.length, added: added }),
      (error) => reply({ ok: false, error: String(error) })));
  } else if (msg.type === "STATUS") {
    event.waitUntil((async () => {
      const data = await caches.open(DATA_CACHE);
      const have = new Set((await data.keys()).map((r) => r.url));
      const saved = {};
      Object.keys(PARTS).forEach((dataset) => {
        saved[dataset] = Object.keys(PARTS[dataset]).filter((part) => have.has(PARTS[dataset][part]));
      });
      reply({ ok: true, version: self.DAMDAYS_SHELL.version, saved: saved,
              total: allPartUrls().length, savedCount: allPartUrls().filter((u) => have.has(u)).length });
    })());
  }
});

async function cacheFirst(cacheName, request, keep) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok && keep(response)) await cache.put(request, response.clone());
  return response;
}

/** Oldest first: drop tiles past the count. */
async function trimTiles() {
  const cache = await caches.open(TILE_CACHE);
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - MAX_TILES; i++) await cache.delete(keys[i]);
}

/** Map tiles: the network first; when it fails, the copy of that tile kept within the last 7 days. */
async function tile(request) {
  const cache = await caches.open(TILE_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok && response.type === "cors") {
      // Keep a copy stamped with the time it was saved (OSM's own Date header is not readable here).
      const body = await response.clone().blob();
      const headers = new Headers(response.headers);
      headers.set(SAVED_AT, String(Date.now()));
      cache.put(request, new Response(body, { status: response.status, statusText: response.statusText, headers }))
        .then(trimTiles).catch(() => {});
    }
    return response;
  } catch (error) {
    const hit = await cache.match(request);
    if (hit && Date.now() - Number(hit.headers.get(SAVED_AT) || 0) <= TILE_MAX_AGE_MS) return hit;
    if (hit) cache.delete(request);
    throw error;
  }
}

/** Any page in the app is the one index.html: the saved copy, else the network. */
async function navigate(request) {
  const cache = await caches.open(SHELL_CACHE);
  for (const url of INDEX_URLS) {
    const hit = await cache.match(url);
    if (hit) return hit;
  }
  return fetch(request);
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.origin === self.location.origin) {
    if (!url.href.startsWith(SCOPE)) return;                       // another project on this origin
    if (request.mode === "navigate") { event.respondWith(navigate(request)); return; }
    if (url.href.startsWith(PING) && url.searchParams.has("ping")) {
      // pwa.js testing the signal: always the network. No signal is an answer, not a page error
      // (a 204 with a flag: browsers log any 4xx or 5xx as a console error).
      event.respondWith(fetch(request).catch(() => new Response(null, {
        status: 204, headers: { "x-damdays-offline": "1" } })));
      return;
    }
    if (PART_URL.test(url.pathname)) {
      event.respondWith(cacheFirst(DATA_CACHE, request, () => true));
      return;
    }
    const plain = url.origin + url.pathname;                       // the shell ignores ?query
    if (SHELL_SET.has(plain)) {
      event.respondWith(caches.open(SHELL_CACHE).then((c) => c.match(plain)).then((hit) => hit || fetch(request)));
    }
    return;                                                        // e.g. sw-version.js, bundle.js: network
  }
  if (url.hostname === "unpkg.com" && /@\d+\.\d+\.\d+\//.test(url.pathname)) {
    event.respondWith(cacheFirst(RUNTIME_CACHE, request, (r) => r.type === "cors"));
    return;
  }
  if (url.hostname === "fonts.gstatic.com") {
    event.respondWith(cacheFirst(RUNTIME_CACHE, request, (r) => r.type === "cors"));
    return;
  }
  if (url.hostname === "tile.openstreetmap.org" || /^[abc]\.tile\.openstreetmap\.org$/.test(url.hostname)) {
    event.respondWith(tile(request));
  }
});
