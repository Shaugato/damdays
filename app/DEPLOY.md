# Putting the app online (GitHub Pages)

The app goes online as it is: no build step on the server, nothing to install. It is a plain folder of HTML, CSS, JavaScript and data scripts, and since the redesign it is also an **installable web app** that keeps working offline (a manifest, icons and a service worker). Pages is switched on by the orchestrator, not by this guide's author.

## Switch it on: 3 steps

1. On https://github.com/Shaugato/damdays, open **Settings**, then **Pages** (left menu).
2. Under "Build and deployment", set **Source** to **Deploy from a branch**.
3. Set **Branch** to **`main`** and the folder to **`/ (root)`**, then click **Save**.

About 1 to 2 minutes later the app is live at:

**https://shaugato.github.io/damdays/app/**

It opens on the Welcome (this week's text for the demo farm near Mudgee). Each place has its own link, and the old links still work:

| link | opens |
|---|---|
| [`#farm`](https://shaugato.github.io/damdays/app/#farm) | My farm: Farm E (near Mudgee), its dams; `#farm/dam-1` opens Dam 1 |
| [`#proof`](https://shaugato.github.io/damdays/app/#proof) | Proof; [`#proof/rewind`](https://shaugato.github.io/damdays/app/#proof/rewind) is Rewind: the 2018-19 drought (old link `#rewind`) |
| [`#questions`](https://shaugato.github.io/damdays/app/#questions) | Questions judges ask (old link `#faq`) |
| [`#runway`](https://shaugato.github.io/damdays/app/#runway) | Runway: the region map (also `#map`) |
| [`#about`](https://shaugato.github.io/damdays/app/#about) | About: how it works, the data, honest limits |
| [`#outlook`](https://shaugato.github.io/damdays/app/#outlook) | the Area outlook, set aside (old link `#rating`) |
| `?data=mock` | the made-up data, with a MOCK DATA banner |

- The Actions tab shows a run called "pages build and deployment"; when it is green, the site is up.
- Switching Pages on adds no file and no commit to the repo.
- After that, **every push to `main` updates the site** in 1 to 2 minutes. Keep the repo public through judging: on the free plan a private repo takes the site down, and the QR code in the video with it.

## Before every push: stamp the app shell

```
.venv/Scripts/python.exe app/tools/build_bundle.py --stamp
.venv/Scripts/python.exe app/tools/build_bundle.py --check-stamp     # says "up to date", or exits 1
```

`--stamp` rewrites `app/sw-version.js`: the list of the app's own files (HTML, CSS, JS, the font, small icons, the data lists) and one fingerprint over all of them. Phones that opened or installed DamDays keep those files and serve them from the phone (that is what makes the second visit instant and offline). A changed fingerprint is how they learn there is a new version: they fetch it in the background and show **"Updated forecasts are ready. Refresh"**. **Without the stamp, a code-only change never reaches them.** Every data export stamps it too (scripts 11, 16, 17, 18 and 21 all run `build_bundle.py`), so commit `app/sw-version.js` together with `app/data/real/`.

## How the data is split (and why it is fast on a slow phone)

`build_bundle.py` writes the data twice, from the same JSON files ([DATA_CONTRACT.md](DATA_CONTRACT.md)): the old one-file `data/real/bundle.js` (kept for the tests, `?data=mock` and anyone reading the contract) and the same data in parts (`data/real/parts.js` lists them). Sizes as GitHub sends them (gzip), Sat 3 Oct 2026:

| part | gzip | when the app loads it |
|---|---:|---|
| `first` | 28 KB | at once: the Welcome, My farm, the dam sheet, Proof, Questions and About need nothing else |
| `farms` | 23 KB | when the phone is idle after the first screen (not on Save-Data or 2G): the demo farms' water history |
| `core` | 89 KB | the region map, a custom homestead, a dam outside the demo farms |
| `rewind`, `rating` | 49 KB each | the region replay map; the Area outlook |
| `history-00` to `-11` | 32 to 41 KB each | when a dam outside the demo farms shows its water history |

The whole `bundle.js` is 0.65 MB gzipped; the app never loads it when the parts are there. Each part's file name carries a hash of its content (`first.21f2c59052.js`): a new export writes new names and deletes the old files, so the repo does not grow, and phones never mix old and new data.

## The installable app and offline

- `manifest.webmanifest`: name, colours, icons (`icons/`, drawn from the logo by `research/ui/build/make_app_icons.py`), and four shortcuts (My farm, Proof, Questions, Runway: long-press the home-screen icon on Android).
- `sw.js`, the service worker (scope `/damdays/app/`; every cache it makes is named `damdays-...`, so other projects on `shaugato.github.io` are never touched). On the first visit, once the page has loaded, it saves the app's files and the `first` and `farms` parts. Other parts are saved the first time they are used, or all at once with **Save for offline** (`DamDays.pwa.saveAll()`, on the install sheet). Map tiles: only tiles you looked at, at most 300, at most 7 days old, never downloaded ahead (OpenStreetMap's rule).
- Offline after one visit: the Welcome, My farm, the demo farms' dam sheets and Proof open, with a chip at the top: "Offline. Showing the forecasts saved for the week of 2 Oct 2026. New map areas need internet." A page never saved says "This page has not been saved on this phone yet. Connect to the internet once and it will be."
- No install prompt, banner or nag on a first visit (Chrome's own mini-infobar is held back). The install sheet (More, `#more/install`) has the steps and, where the browser offers it, an Install button. Chrome's menu ("Install app") and Safari's Share, "Add to Home Screen" always work.
- The service worker needs https (or localhost). A double-clicked `index.html` (file://) still works exactly as before, without it.
- **Local testing:** on `localhost` the worker registers only after you open the app once with `?sw=1` (remembered in this browser); `?sw=0` removes it and its caches. This keeps builders from seeing stale cached code.

## Check it once it is online

```
curl -sI --compressed https://shaugato.github.io/damdays/app/ | grep -i -E "HTTP/|content-encoding|cache-control"
curl -sI https://shaugato.github.io/damdays/app/manifest.webmanifest | grep -i content-type
curl -sI --compressed https://shaugato.github.io/damdays/app/data/real/parts.js | grep -i content-encoding
```

Expect `200`, `content-encoding: gzip` and `cache-control: max-age=600` (GitHub's fixed setting; the worker asks for `sw.js` and `sw-version.js` past that cache). Then on a phone: open the address, wait for the page to settle, switch to flight mode and reopen it: the Welcome, `#farm`, `#farm/dam-1` and `#proof` should open with the offline chip. In desktop Chrome, DevTools, Application: Manifest shows no errors, Service workers shows "activated and is running".

## If a broken service worker ever ships

Copy `research/ui/pwa/sw-killswitch.js` over `app/sw.js`, then commit and push. On the next visit it deletes every `damdays-` cache, unregisters itself and reloads from the network (tested in the PWA prototype). Put the real `sw.js` back once the fix is out.

## Jekyll

With "Deploy from a branch", GitHub runs Jekyll over the repo. It copies every file the app uses unchanged, but it leaves out any file or folder whose name starts with `_` or `.`, and it would fail on a Liquid template tag (two opening curly braces, or an opening curly brace followed by a percent sign) in a Markdown or HTML file. None of the app's files does either; `stamp_shell` also skips any such name, so the worker never asks for a file Pages does not serve.

## Optional: the root address

Without anything more, **https://shaugato.github.io/damdays/** shows the repo's README as a web page, and its link to the app works. To send that address straight to the app instead, add this file as `index.html` **at the repo root**:

```html
<!doctype html>
<meta charset="utf-8">
<title>DamDays</title>
<meta http-equiv="refresh" content="0; url=app/">
<p><a href="app/">Open the DamDays app</a></p>
```
