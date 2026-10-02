# Putting the app online (GitHub Pages)

The app is ready to go online as it is: no build step, nothing to install. Pages is **not switched on yet**.

## Switch it on: 3 steps

1. On https://github.com/Shaugato/damdays, open **Settings**, then **Pages** (left menu).
2. Under "Build and deployment", set **Source** to **Deploy from a branch**.
3. Set **Branch** to **`main`** and the folder to **`/ (root)`**, then click **Save**.

About 1 to 2 minutes later the app is live at:

**https://shaugato.github.io/damdays/app/**

Each view has its own link: [`#farm`](https://shaugato.github.io/damdays/app/#farm) (opens first), [`#runway`](https://shaugato.github.io/damdays/app/#runway), [`#rewind`](https://shaugato.github.io/damdays/app/#rewind), [`#rating`](https://shaugato.github.io/damdays/app/#rating), [`#about`](https://shaugato.github.io/damdays/app/#about).

- The Actions tab shows a run called "pages build and deployment"; when it is green, the site is up.
- Switching Pages on adds no file and no commit to the repo, so it does not affect the sealed-opening checks (clean git, HEAD pushed).
- After that, **every push to `main` updates the site** in 1 to 2 minutes. Browsers may keep the old copy for up to 10 minutes (GitHub's cache); Ctrl+F5 reloads it. For example, after the sealed region is opened, `scripts/11_export_app.py --panel-only ...` rewrites `app/data/real/bundle.js`: commit and push it, and the online About and Rating views show the sealed results.
- If a later build ever fails, the last good version stays online and the Actions tab says why.

## What was checked (Sat 3 Oct 2026, 00:15-00:30 AEST)

The committed `app/` files were served from a local web server under the same two-level path as the real site (`/damdays/app/`), and again with the server rooted at the repo (`/app/`).

| check | result |
|---|---|
| Paths | **All relative** (`css/`, `js/`, `data/`, next to `index.html`); none starts with `/`, so the app works under any folder. The only files from elsewhere are Leaflet (unpkg.com) and the map tiles (tile.openstreetmap.org), both over https. |
| The data, from a subfolder | **Loads.** The app reads one file, `data/real/bundle.js`, with a `<script>` tag (not `fetch()`). All five views opened with the real data, no MOCK banner, no console errors (Runway drew all 894 dams; Rating its 767 cells on both maps). |
| `farms.json` (My farm) | **Inside `bundle.js`.** Each of the 7 parts in `bundle.js` (the six files of [DATA_CONTRACT.md](DATA_CONTRACT.md) and `farms.json`) is identical to its JSON file. The app never downloads the JSON files themselves. |
| Double-click (`file://`) | **Works.** Chrome opened `index.html` from disk: real data, Farm D's weekly text on the phone, the map with its tiles. |
| `.nojekyll` | **Nothing to add.** With "Deploy from a branch", GitHub runs Jekyll over the repo, and only a `.nojekyll` at the repo root would turn that off (`app/.nojekyll` counts only when `app/` itself is the published folder). Jekyll is harmless here: it copies every file the app uses unchanged (none has a front-matter header, and none has a name starting with `_` or `.`, which Jekyll would leave out), and it could only fail on a Liquid template tag (two opening curly braces, or an opening curly brace followed by a percent sign) in a Markdown file; no tracked `.md` or `.html` file has one, and this page avoids writing them for that reason. |
| Size | `app/` is 10.2 MB in the repo (the whole repo 15.7 MB; the Pages limit is 1 GB). A first visit downloads about **0.9 MB**: the app's own files are 4.1 MB but GitHub sends them compressed (0.66 MB; `bundle.js` 3.9 MB becomes 0.6 MB), plus Leaflet (46 KB) and about a dozen map tiles. |
| First-load time | Local server: the page is ready in 0.4 s (`bundle.js` fetched and read in about 0.13 s). Online, from the sizes: about **1 s** on a 10 Mbit/s connection, about **3 to 4 s** on a slow mobile connection (2 Mbit/s). Later visits come from the browser's cache. |

## Optional: the root address

Without anything more, **https://shaugato.github.io/damdays/** shows the repo's README as a web page (GitHub's Jekyll does this), and its link to the app works. To send that address straight to the app instead, add this file as `index.html` **at the repo root** (not added: this check changed only `app/`):

```html
<!doctype html>
<meta charset="utf-8">
<title>DamDays</title>
<meta http-equiv="refresh" content="0; url=app/">
<p><a href="app/">Open the DamDays app</a></p>
```

Commit and push it like any other change, before the sealed-opening checks (git must be clean at 17:30).
