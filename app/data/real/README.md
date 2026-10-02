# Real data goes here

The pipeline's exporter writes the six JSON files described in `app/DATA_CONTRACT.md` into this folder. Then run, from the repo root:

    python app/tools/build_bundle.py app/data/real

That writes `bundle.js` here and lists "real" first in `app/data/datasets.js`, so the app shows the real data instead of the mock data.
