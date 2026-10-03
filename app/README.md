# DamDays app

A static web page (no server, no build step) that is also an installable web app. On a phone it is a clean app with four tabs; on a desktop the first screen becomes a story page (what DamDays is, and the real text inside a drawn phone) for judges and visitors. Same app, same addresses.

- **Welcome** (the QR code opens this): this week's real text for the demo farm near Mudgee (Farm E), word for word from `farms.json`, with the headline phrase highlighted; each dam's line opens that dam. Under it, the trust line (the cautious days held 900 in 1,000 times in ten test years) and the unseen exam's status, and two buttons: **See the 5 dams** and **Can I trust it?**
- **My farm**: the farm's headline (the dam with the fewest days: "at least 68 days before it drops below a third"), the farm from above (a tile-free sketch, or the street map), and one row per dam: how full at its last clear satellite look, days, chance by a date, and **our record on it** ("held 380 of 428 times" on Farm E's Dam 1: how often our days-left number held on that dam over the last 10 years, re-running our forecasts for July 2016 to June 2026 with only data from before July 2016, so a farmer can judge our accuracy on their own water; "not enough history" under 5 checked forecasts). The farm's record adds them up. **Change** opens the setup sheet: pick one of the 9 demo farms, or tap the map to set your own homestead, and set the circle size; the text is remade in the browser by `js/text.js`, a line-for-line port of the Python that writes the real texts (`notify/message.py`). "This week's text" shows it as it arrives, and the longer version for the app or an email.
- **The dam sheet** (tap a dam): days first, then how full, the chance by a date with the wetter or drier season range, our record on this dam, the note when a dam runs wetter or drier than similar dams, the next six months as rows of ten dots (with the DamDays day marked), and, one more tap down, how the days are counted, season by season, how full since 1988, and about these numbers.
- **Proof** (for judges, without "AUC"): the cautious days' record, the **unseen exam** card ("not opened yet" until the sealed region is opened, then its scored panel), and four pictures of the ten test years, each a sheet with "Show the numbers": (1) what we said vs what happened; (2) it held up year after year; (3) **Rewind: the 2018-19 drought** (`#proof/rewind`, old link `#rewind`): Farm E on three dates, then "Show what happened", and the whole region on the map; (4) dam by dam: Farm E's five dams in the 2018-19 drought. Its data is `data/real/proof.json`, made by `scripts/17_proof_data.py`.
- **Questions**: questions judges ask, each answer one sentence with "Show the numbers" and "Where to check".
- **More**: **Runway: the region map** (`#runway`, also `#map`: every dam-sized waterbody we watch, coloured by its chance of dropping below a third in the next 90 days, the highest-chance list, and the interactive map), **About** (how it works, honest limits, the data and credits; "Methods and scores, for specialists" holds the test panels), the **Area outlook** (set aside; the old Rating, `#outlook`, old link `#rating`, its scoreboard under "For specialists"), and how to put DamDays on your home screen.

## Open it

- **Online** (once GitHub Pages is switched on; 3 steps in [DEPLOY.md](DEPLOY.md)): https://shaugato.github.io/damdays/app/
- **Double-click `index.html`.** Everything works from your disk. The street maps need internet.
- Or serve the folder: `python -m http.server 8000` inside `app/`, then open http://localhost:8000.
- Every level has its own address: `#farm`, `#farm/dam-1`, `#farm/dam-1/record`, `#farm/text`, `#farm/setup`, `#proof`, `#proof/said`, `#proof/rewind`, `#questions`, `#questions/<id>`, `#more`, `#runway`, `#about`, `#about/specialists`, `#outlook`. Old links keep working: `#rewind`, `#rating`, `#map`, `#faq`. Add `?data=mock` to force the mock data.

## Data

The app reads the files described in [DATA_CONTRACT.md](DATA_CONTRACT.md), split into content-hashed parts (`data/real/parts.js` lists them) so the first screen loads only what it shows. It prefers the real data; with `?data=mock` (or if no real data is there) it uses **mock data**, and a striped **MOCK DATA** banner sits at the top of every view.

- Make the mock data again: `python app/tools/make_mock_data.py` (from the repo root).
- Publish real data: write the six JSON files to `app/data/real/`, then run `python app/tools/build_bundle.py app/data/real`. The app then prefers the real data automatically. The real files are written by `scripts/11_export_app.py`; see [data/real/README.md](data/real/README.md) for where every number comes from.
- **My farm's demo farms and this week's date** come from `app/data/real/farms.json`, written by `scripts/16_weekly_texts.py` ([notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md)). `build_bundle.py` packs it into `bundle.js` when it is there; run the bundle again after step 16.
- **Proof's charts** come from `app/data/real/proof.json`, written by `.venv/Scripts/python.exe scripts/17_proof_data.py` (about a minute, after steps 13, 15, 11 and 16; it rebuilds `bundle.js` itself). It reads the saved test forecasts and their answers, scores nothing, and refuses to write if its totals differ from `artifacts/test_results.json`. Format: [DATA_CONTRACT.md](DATA_CONTRACT.md#proofjson-optional-what-accuracy-looks-like-for-the-proof-view); tests: `tests/test_proof_data.py`.
- **The track record** (My farm's table and the dam card) comes from `app/data/real/track_record.json`, written by `.venv/Scripts/python.exe scripts/18_track_record.py` (seconds, after steps 13, 15, 11, 16 and 17; it rebuilds `bundle.js` itself). It counts the saved 2016-2026 test forecasts dam by dam for every dam the app shows, scores nothing, and refuses to write unless its counts over every dam add up to `artifacts/test_results.json` and `proof.json`. Format: [DATA_CONTRACT.md](DATA_CONTRACT.md#track_recordjson-optional-each-dams-track-record-so-a-farmer-can-judge-our-accuracy); tests: `tests/test_track_record.py`; the same numbers as a page: [`artifacts/track_record.md`](../artifacts/track_record.md).
- After the sealed region is opened: `.venv/Scripts/python.exe scripts/11_export_app.py --panel-only --sealed-scores artifacts/sealed/scorecard/sealed_TEST` fills the sealed panel (seconds; nothing else changes).

## How the code is laid out

Plain HTML, CSS and JavaScript, no framework and no modules (so a double-clicked `index.html` works). Each script adds one part to a global `DamDays` object. `index.html` loads the shell, the Welcome, My farm and the dam sheet with the page; the other views load when their address opens (`js/main.js` `LAZY`), and the service worker keeps them all for offline use.

| file | what it does |
|---|---|
| `index.html` | the page: the static first screen (paints before any data), the tab bar, the sheet, and the old map views' markup (Runway's interactive map, Rewind's region map, the Area outlook) |
| `css/tokens.css`, `base.css`, `shell.css` | design tokens (colour, type, space, motion, light and dark), shared components, the shell |
| `css/welcome.css`, `farm.css`, `dam.css`, `proof.css`, `more.css`, `legacy.css`, `pwa.css` | one file per area; `legacy.css` styles the old map views inside the new pages |
| `fonts/` | Atkinson Hyperlegible Next, self-hosted (SIL Open Font License, `fonts/OFL.txt`) |
| `js/settings.js` | colour bands, thresholds, map tiles, the default demo farm |
| `js/text.js` | **the weekly text**: a line-for-line port of `notify/message.py` (and the parts of `notify/farms.py` and `notify/gsm7.py` it needs) |
| `js/format.js` | dates, chances ("3 in 10"), "held N of M times", fraction words, the unseen exam's status, the "?" tips |
| `js/colors.js` | chance to colour, and the colour key |
| `js/charts.js` | ten-dot rows, the six-month chart, the water history since 1988 (hand-drawn SVG) |
| `js/sketch.js` | the dam drawn from above, the farm sketch with placed tags |
| `js/sheet.js` | the one sheet every second level opens in (bottom sheet on phones, side panel on desktop) |
| `js/dam-sheet.js`, `js/dam-card.js` | the dam sheet; the old dam card (still used by the old region maps) |
| `js/data.js` | loads the data parts (`data/real/parts.js` and the hashed parts it lists), builds quick lookups |
| `js/main.js` | the router (every level has an address; Back steps one level), lazy loading, the old map views' mount |
| `js/pwa.js`, `sw.js`, `sw-version.js`, `manifest.webmanifest`, `icons/` | the installable app and offline copy |
| `js/views/welcome.js`, `farm.js` | the Welcome and My farm (with the setup and text sheets) |
| `js/views/proof.js`, `replay.js` | Proof and its picture sheets; Rewind: the 2018-19 drought |
| `js/views/questions.js`, `more.js`, `region.js`, `about.js` | Questions, More, Runway (the region map), About (keeps `panelHtml(panel)`, which `scripts/21_publish_sealed.py` reads) |
| `js/views/runway.js`, `rewind.js`, `rating.js` | the old Leaflet views, mounted inside Runway, Rewind and the Area outlook |
| `tools/build_bundle.py` | packs a dataset's JSON files into `bundle.js` and the hashed parts, and stamps `sw-version.js` |
| `tools/check_text_port.js` | checks that `js/text.js` writes exactly the texts `notify/message.py` writes (below) |
| `tools/make_mock_data.py` | makes the mock dataset |

Why the data is loaded as scripts and not with `fetch()`: browsers block `fetch()` of local files when a page is opened by double-clicking, but they do run local scripts.

## The weekly text in the browser: one text, two languages

The real texts are written in Python (`notify/message.py`, rules in [notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md)); the app's phone shows the same text, made by `js/text.js`. To check that the two agree, character for character:

```
node app/tools/check_text_port.js
```

It runs the port on the fixtures `scripts/16_weekly_texts.py` writes (the spec's 10 worked examples and this week's 9 demo farms) and on `app/data/real/farms.json` (run the way My farm runs it), and prints `same` or `DIFFERS` for each. `tests/test_app_text_port.py` runs it from pytest, plus 600 random farms (every kind of dam, chances on the rounding edges, looks on the 60-day edge) written by Python; it is skipped if Node.js is not installed. The app itself shows farmers only the text (and "Fits in one text message."); these character-for-character checks stay in the tests.

## Design choices

- **The mentor's words** (mentor feedback, Fri 2 Oct): farmers read "%" as how full a dam is. So in the app **"%" only ever means fullness** ("~80% full"), a chance is written **"3 in 10"** (rounded as the text rounds it; "less than 1 in 10" under 0.05), and the headline is **days of water** before the dam drops below a third. The test scores in About's "Methods and scores, for specialists" and the Area outlook's scoreboard (for specialists) keep their usual names (skill as "23.5% less error", AUC as "81 in 100"), each with a plain-words line or "?" tip; how often the DamDays number held is a chance, so About writes it "900 in every 1,000", not as a percent.
- **Days are counted from the day of this week's text** (`farms.json`'s date, Fri 2 Oct 2026) for today's forecasts, and from the forecast's date in Rewind: the DamDays number from the dam's last clear satellite look, less the days since that look. The card says so under the number.
- One colour family (light sand to dark brown) for chance, in bands of whole tenths ("3 or 4 in 10"), so a dam's colour always matches the "N in 10" it shows: darker always means more risk, which still reads in greyscale and for colour-blind viewers. Every dot has a thin dark ring so the palest ones still show on the map, and "what happened" is shown with a thick black ring, not a colour. "Likely" (Runway summary, Rewind hits and misses) means a chance shown as 5 in 10 or more, the same line at which the weekly text always names a dam.
- **Proof is for judges who do not read "AUC".** Each chart says its point in one sentence first, written by `scripts/17_proof_data.py` from the numbers. Skill is said in fractions ("a fifth less error than guessing the usual rate", rounded down, as the video script does), how often the promise held as "N in 1,000", and a group of forecasts by the words the text uses ("3 in 10"). One colour per job (orange-brown = a chance, as on the maps; blue = how well it did; water blue = the water level), every difference that matters also a shape (filled or open dot) or a label, and the colour pair checked for colour-blind separation. Each chart has a table of every number, so a tooltip never hides one.
- **Trust, dam by dam** (a mentor, Sat 3 Oct: the forecast is the farmer's "lifeline", so give farmers a way to judge its accuracy). Each dam's card and My farm's table say how often our cautious days-left promise held **on that dam** over the last 10 years, as a count ("held 380 of 428 times", never a percent), with a "?" tip: "We re-ran our forecasts for July 2016 to June 2026 using only data from before July 2016, then checked each one against what the dam really did." Every dam is shown as it is, poor records too: under about 9 in 10 the card says so and suggests extra margin, and it lists the seasons (and the last three) so a run of misses in one drought is easy to see. Fewer than 5 checked forecasts: "not enough history". Rewind leaves it out, so it never gives away what happened.
- Plain words: "chance", "below a third", "no water seen" (a 0% reading: the satellite saw no water at its last clear look, and one look can be wrong; never "dry"). The few technical terms (AUC, the wetter or drier season range, the DamDays number) have a "?" tip.
- Large type (Atkinson Hyperlegible Next) and 48 px touch targets (56 px for main actions), so it reads on a projector and works on a phone in the sun.

## Publishing on GitHub Pages

All paths are relative and there is no build step, so the app can be served as it is. Settings, Pages, "Deploy from a branch", branch `main`, folder `/ (root)`: the app is then at https://shaugato.github.io/damdays/app/. The steps and what was checked (paths, data from a subfolder, size, first-load time) are in [DEPLOY.md](DEPLOY.md). (`.nojekyll` matters only if `app/` itself is ever the published folder; with the setup above it is not needed.)

## Credits

Map library: [Leaflet](https://leafletjs.com) (BSD-2-Clause), loaded from unpkg only where a street map opens. Map tiles: © OpenStreetMap contributors. Type: Atkinson Hyperlegible Next, Braille Institute (SIL Open Font License). Data: DEA Waterbodies (Geoscience Australia) and SILO (Queensland Government), both CC BY 4.0.
