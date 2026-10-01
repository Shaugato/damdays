"""DamDays: calibrated drought-runway forecasts for farm dams.

The package is split into small, readable parts:

- damdays.config      every path, date and threshold in one place
- damdays.data        load satellite water history and rainfall, define events
- damdays.features    turn history into the numbers a model can learn from
- damdays.models      the forecasting engine (Tidemark) and its baselines
- damdays.evaluation  one shared scorecard so every model is judged the same way
"""
