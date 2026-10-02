"""Forecast models: the simple baselines, the G2 benchmark and Tidemark.

Every model here learns only from rows whose answer was known before the
block it is judged on (the purge), and every prediction is judged by the one
shared scorecard (damdays.evaluation.score).

Start with tidemark.py: fit_tidemark(cutoff, rung) and predict_tidemark(model)
build every DamDays forecast from the modules below.

Modules
    tidemark     the one entry point: 90-day probabilities, runway curve, floor, band and season rating;
                 the members registry (T now; the nets S and M later) and the fallback-ladder rungs
    rows         which rows a model may learn from, and which rows it predicts
    baselines    the pre-registered simple references: B0, B2, PERS (P1 and P2), RAIN and RAIN+ (P2)
    g2           G2, the pre-registered LightGBM benchmark, and its VAL diagnostics G2c and G2_rescue
    frailty      Tidemark's per-dam random intercept b = R / (V + 100) from the dam's matured past forecasts
    fusion       Tidemark's 90-day forecast: tree member T, equal-weight logit fusion, frailty, R30 max rule
    hazard       the runway curve H: discrete-time hazard LightGBM for 30/60/90/180 days, censored training
                 intervals, R30 curve >= D0 curve; plus the horizon baselines B0_h and B2_h
    uncertainty  the DamDays floor (LB90: 10% quantile of days to R30 + split conformal, shown as "180+"
                 from 180 days) and the season band (region-year logit offsets from inner backtests)
    season_rating  P2, the lender rating: LightGBM boosted from the dam's own past dry-season rate;
                 2 km cell p = product of its dam-like dams' p
    predictions  save and load predictions in data_cache/preds/<block>/<task>/<name>.pkl
"""
