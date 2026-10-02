# DamDays app

A static web page (no server, no build step) with four views:

- **Runway** (for farmers): a map of dams coloured by the chance each falls below a third full in the next 90 days. Pick a dam for its card: the plain sentence, the DamDays number, the runway curve and the water history since 1988.
- **Rewind**: pick a past date, see the forecasts as they were made then, and press "Reveal what happened". A tally shows hits and misses, and whether the chances came true.
- **Rating** (for lenders): two maps side by side, a rainfall-only score against the DamDays Rating, for each 2 km cell. "Reveal which ran dry" shows the cells whose dams really ran dry, and a scoreboard.
- **About**: how it works, how it was checked, honest limits, data credits and the COP31 link.

## Open it

- **Double-click `index.html`.** Everything works from your disk. The background map needs internet.
- Or serve the folder: `python -m http.server 8000` inside `app/`, then open http://localhost:8000.
- Add `#rewind`, `#rating` or `#about` to the address to open a view directly. Add `?data=mock` to force the mock data.

## Data

The app reads the files described in [DATA_CONTRACT.md](DATA_CONTRACT.md). Until the real forecasts exist, it uses **mock data**, and a striped **MOCK DATA** banner sits at the top of every view.

- Make the mock data again: `python app/tools/make_mock_data.py` (from the repo root).
- Publish real data: write the six JSON files to `app/data/real/`, then run `python app/tools/build_bundle.py app/data/real`. The app then prefers the real data automatically.

## How the code is laid out

Plain HTML, CSS and JavaScript. Each script adds one part to a global `DamDays` object, and `index.html` loads them in order.

| file | what it does |
|---|---|
| `index.html` | the page: header, the four views, the About text |
| `css/style.css` | all styling; colours named once at the top |
| `js/settings.js` | colour bands, thresholds and map tiles, in one place |
| `js/format.js` | dates, percentages, the "?" tips |
| `js/colors.js` | chance to colour, and the colour key (legend) |
| `js/charts.js` | the runway curve and the water-history sparkline (hand-drawn SVG) |
| `js/map.js` | shared Leaflet map set-up and dot styles |
| `js/dam-card.js` | the dam card used by Runway and Rewind |
| `js/data.js` | loads the data and builds quick lookups |
| `js/views/runway.js`, `rewind.js`, `rating.js`, `about.js` | one file per view |
| `js/main.js` | starts the app and switches views |
| `tools/build_bundle.py` | packs a dataset's JSON files into `bundle.js` |
| `tools/make_mock_data.py` | makes the mock dataset |

Why the data is loaded as a script (`bundle.js`) and not with `fetch()`: browsers block `fetch()` of local files when a page is opened by double-clicking, but they do run local scripts.

## Design choices

- One colour family (light sand to dark brown) for chance: darker always means more risk, which still reads in greyscale and for colour-blind viewers. Every dot has a thin dark ring so the palest ones still show on the map, and "what happened" is shown with a thick black ring, not a colour.
- Plain words: "chance", "below a third", "ran dry". The few technical terms (AUC, the likely range, the DamDays number) have a "?" tip.
- Large type and 44 px touch targets, so it reads on a projector and works on a phone.

## Publishing on GitHub Pages

All paths are relative and there is no build step, so the `app/` folder can be served as it is. In the repository settings, under Pages, choose "GitHub Actions" and use the standard static-site workflow with its upload path set to `app`. (`.nojekyll` stops GitHub from processing the files.)

## Credits

Map library: [Leaflet](https://leafletjs.com) (BSD-2-Clause), loaded from unpkg. Map tiles: © OpenStreetMap contributors. Data: DEA Waterbodies (Geoscience Australia) and SILO (Queensland Government), both CC BY 4.0.
