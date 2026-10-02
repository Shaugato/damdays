"""Forecast models: the simple baselines, the G2 benchmark and (later) Tidemark.

Every model here learns only from rows whose answer was known before the
block it is judged on (the purge), and every prediction is judged by the one
shared scorecard (damdays.evaluation.score).

Modules
    rows         which rows a model may learn from, and which rows it predicts
    baselines    the pre-registered simple references: B0, B2, PERS (P1 and P2), RAIN and RAIN+ (P2)
    g2           G2, the pre-registered LightGBM benchmark, and its VAL diagnostics G2c and G2_rescue
    predictions  save and load predictions in data_cache/preds/<block>/<task>/<name>.pkl
"""
