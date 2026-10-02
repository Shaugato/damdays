"""Turning DamDays forecasts into the files the web app reads.

    live_model.py  the production fit: Tidemark fitted on every answer known by the
                   last satellite look, used only for today's ("live") forecasts
    app_data.py    builds the six JSON files of app/DATA_CONTRACT.md
    albers.py      converts the 2 km hexagons from Australian Albers metres to latitude/longitude

Run it with scripts/11_export_app.py.
"""
