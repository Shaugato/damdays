# DamDays app

A static web page (no server, no build step) with six views:

- **My farm** (opens first; the farmer product): farmers don't open apps or emails, so DamDays is **one text message a week**. Click the map to set a homestead (or pick one of the 10 demo farms), set the radius, and see this week's text on a drawn phone, exactly as it arrives, plus the farm's dams (Dam 1 = closest): how full each one is, its days of water and its chance. Tap a dam for its card. The text is made in the browser by `js/text.js`, a line-for-line port of the Python that writes the real texts (`notify/message.py`).
- **Runway** (the regional map): every farm dam in the region, coloured by the chance it falls below a third full in the next 90 days. Pick a dam for its card: how full it is, the DamDays number (days of water, the headline), the chance, the runway curve and the water history since 1988.
- **Rewind**: pick a past date, see the forecasts as they were made then, and press "Reveal what happened". A tally shows hits and misses, and whether the chances came true.
- **Proof** (for judges: what accuracy looks like, without "AUC"): three pictures of the ten test years (July 2016 to June 2026, scored once), each with a one-sentence takeaway and a "Show the numbers" table. (1) *What we said vs what happened*: the test forecasts grouped by the chance they gave ("3 in 10"), against how often the dam really fell below a third within 90 days, as dots near a diagonal. (2) *It held up year after year*: how much less error than guessing the usual rate, for each July-June year, with the drier years shaded, and how often "at least N days" held each year (worst: July 2023 to June 2024, 872 in 1,000). (3) *Dam by dam*: the seven dams of the demo farm near Dubbo in the 2018-19 drought, each dam's water level against every forecast made for it. At the top, the **unseen exam** card: "Unseen exam: opens Sat 3 Oct 17:30 AEST" until the sealed region is opened, then its scored panel (the same one About shows). Its data is `data/real/proof.json`, made by `scripts/17_proof_data.py`.
- **Rating** (for lenders): two maps side by side, a rainfall-only score against the DamDays Rating, for each 2 km cell. "Reveal which ran dry" shows the cells whose dams really ran dry, and a scoreboard (this season, all test seasons, and the sealed region's line once it is opened).
- **About**: how it works, how it was checked (one panel per one-time test: the development regions 2016-2026, scored once, and the sealed region, a placeholder until it is opened on Sat 3 Oct 17:30), honest limits, data credits and the COP31 link.

## Open it

- **Online** (once GitHub Pages is switched on; 3 steps in [DEPLOY.md](DEPLOY.md)): https://shaugato.github.io/damdays/app/
- **Double-click `index.html`.** Everything works from your disk. The background map needs internet.
- Or serve the folder: `python -m http.server 8000` inside `app/`, then open http://localhost:8000.
- Add `#runway`, `#rewind`, `#proof`, `#rating` or `#about` to the address to open a view directly (no address: My farm). Add `?data=mock` to force the mock data.

## Data

The app reads the files described in [DATA_CONTRACT.md](DATA_CONTRACT.md). Until the real forecasts exist, it uses **mock data**, and a striped **MOCK DATA** banner sits at the top of every view.

- Make the mock data again: `python app/tools/make_mock_data.py` (from the repo root).
- Publish real data: write the six JSON files to `app/data/real/`, then run `python app/tools/build_bundle.py app/data/real`. The app then prefers the real data automatically. The real files are written by `scripts/11_export_app.py`; see [data/real/README.md](data/real/README.md) for where every number comes from.
- **My farm's demo farms and this week's date** come from `app/data/real/farms.json`, written by `scripts/16_weekly_texts.py` ([notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md)). `build_bundle.py` packs it into `bundle.js` when it is there; run the bundle again after step 16.
- **Proof's charts** come from `app/data/real/proof.json`, written by `.venv/Scripts/python.exe scripts/17_proof_data.py` (about a minute, after steps 13, 15, 11 and 16; it rebuilds `bundle.js` itself). It reads the saved test forecasts and their answers, scores nothing, and refuses to write if its totals differ from `artifacts/test_results.json`. Format: [DATA_CONTRACT.md](DATA_CONTRACT.md#proofjson-optional-what-accuracy-looks-like-for-the-proof-view); tests: `tests/test_proof_data.py`.
- After the sealed region is opened: `.venv/Scripts/python.exe scripts/11_export_app.py --panel-only --sealed-scores artifacts/sealed/scorecard/sealed_TEST` fills the sealed panel (seconds; nothing else changes).

## How the code is laid out

Plain HTML, CSS and JavaScript. Each script adds one part to a global `DamDays` object, and `index.html` loads them in order.

| file | what it does |
|---|---|
| `index.html` | the page: header, the six views, the About text |
| `css/style.css` | all styling; colours named once at the top |
| `js/settings.js` | colour bands, thresholds and map tiles, in one place |
| `js/text.js` | **the weekly text**: a line-for-line port of `notify/message.py` (and the parts of `notify/farms.py` and `notify/gsm7.py` it needs) |
| `js/format.js` | dates, chances ("3 in 10"), the "?" tips |
| `js/colors.js` | chance to colour, and the colour key (legend) |
| `js/charts.js` | the runway curve and the water-history sparkline (hand-drawn SVG) |
| `js/map.js` | shared Leaflet map set-up and dot styles |
| `js/dam-card.js` | the dam card used by My farm, Runway and Rewind |
| `js/data.js` | loads the data and builds quick lookups |
| `js/views/farm.js`, `runway.js`, `rewind.js`, `proof.js`, `rating.js`, `about.js` | one file per view (`proof.js` draws its three charts as hand-made SVG, like `charts.js`) |
| `js/main.js` | starts the app and switches views |
| `tools/build_bundle.py` | packs a dataset's JSON files (and `farms.json` and `proof.json`, if there) into `bundle.js` |
| `tools/check_text_port.js` | checks that `js/text.js` writes exactly the texts `notify/message.py` writes (below) |
| `tools/make_mock_data.py` | makes the mock dataset |

Why the data is loaded as a script (`bundle.js`) and not with `fetch()`: browsers block `fetch()` of local files when a page is opened by double-clicking, but they do run local scripts.

## The weekly text in the browser: one text, two languages

The real texts are written in Python (`notify/message.py`, rules in [notify/MESSAGE_SPEC.md](../notify/MESSAGE_SPEC.md)); the app's phone shows the same text, made by `js/text.js`. To check that the two agree, character for character:

```
node app/tools/check_text_port.js
```

It runs the port on the fixtures `scripts/16_weekly_texts.py` writes (the spec's 10 worked examples and this week's 10 demo farms) and on `app/data/real/farms.json` (run the way My farm runs it), and prints `same` or `DIFFERS` for each. `tests/test_app_text_port.py` runs it from pytest, plus 600 random farms (every kind of dam, chances on the rounding edges, looks on the 60-day edge) written by Python; it is skipped if Node.js is not installed. On a demo farm whose point and radius are unchanged, My farm also says whether its text is the very text in this week's outbox (`outbox/<date>.json`).

## Design choices

- **The mentor's words** (a mentor who grew up on farms): farmers read "%" as how full a dam is. So in the app **"%" only ever means fullness** ("~67% full"), a chance is written **"3 in 10"** (rounded as the text rounds it; "less than 1 in 10" under 0.05), and the headline is **days of water** before the dam drops below a third. The test scores on the About page and the Rating scoreboard are for judges and lenders and keep their usual units (skill as "23.5% less error", AUC as "81 in 100"), each with a plain-words line or "?" tip; how often the DamDays number held is a chance, so About writes it "900 in every 1,000", not as a percent.
- **Days are counted from the day of this week's text** (`farms.json`'s date, Fri 2 Oct 2026) for today's forecasts, and from the forecast's date in Rewind: the DamDays number from the dam's last clear satellite look, less the days since that look. The card says so under the number.
- One colour family (light sand to dark brown) for chance, in bands of whole tenths ("3 or 4 in 10"), so a dam's colour always matches the "N in 10" it shows: darker always means more risk, which still reads in greyscale and for colour-blind viewers. Every dot has a thin dark ring so the palest ones still show on the map, and "what happened" is shown with a thick black ring, not a colour. "Likely" (Runway summary, Rewind hits and misses) means a chance shown as 5 in 10 or more, the same line at which the weekly text always names a dam.
- **Proof is for judges who do not read "AUC".** Each chart says its point in one sentence first, written by `scripts/17_proof_data.py` from the numbers. Skill is said in fractions ("a fifth less error than guessing the usual rate", rounded down, as the video script does), how often the promise held as "N in 1,000", and a group of forecasts by the words the text uses ("3 in 10"). One colour per job (orange-brown = a chance, as on the maps; blue = how well it did; water blue = the water level), every difference that matters also a shape (filled or open dot) or a label, and the colour pair checked for colour-blind separation. Each chart has a table of every number, so a tooltip never hides one.
- Plain words: "chance", "below a third", "ran dry". The few technical terms (AUC, the wetter or drier season range, the DamDays number) have a "?" tip.
- Large type and 44 px touch targets, so it reads on a projector and works on a phone.

## Publishing on GitHub Pages

All paths are relative and there is no build step, so the app can be served as it is. Settings, Pages, "Deploy from a branch", branch `main`, folder `/ (root)`: the app is then at https://shaugato.github.io/damdays/app/. The steps and what was checked (paths, data from a subfolder, size, first-load time) are in [DEPLOY.md](DEPLOY.md). (`.nojekyll` matters only if `app/` itself is ever the published folder; with the setup above it is not needed.)

## Credits

Map library: [Leaflet](https://leafletjs.com) (BSD-2-Clause), loaded from unpkg. Map tiles: © OpenStreetMap contributors. Data: DEA Waterbodies (Geoscience Australia) and SILO (Queensland Government), both CC BY 4.0.
