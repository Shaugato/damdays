"""The published app data (app/data/real/) checked against the raw data: truncation, hand checks, copies.

* TRUNCATION. For every Rewind date D in forecasts.json, rebuild each dam's row
  from only the satellite looks up to D and the events confirmed by D. Status,
  last look, level and chance must equal the published row. Positive control:
  a planted leak (each dam's NEXT look moved to D) must change some statuses.
* HAND CHECKS. On the first Rewind date, one dam that fell below a third and one
  that stayed above are re-read straight from the satellite looks: the last look,
  its level, the chance (the forecast for that look by the model that never saw the
  season: VAL-setting for a validation season, the frozen TEST-setting model for a
  test season), and the event: two looks below 30% of full at most 30 days apart,
  after a refill to 60%.
* THE LIVE RUNWAY CURVE IS THE VALIDATED ONE. The production code path for the
  curve (live_model.fit_live_hazard + live_curves), run at the VAL cutoff
  1 Jan 2009, must give the saved VAL curves bit for bit. So the live curve is the
  validated recipe with only the cutoff moved.
* THE LIVE FIT'S TIME RULES. The fit sizes saved with the live forecasts must equal
  an independent count of the rows whose answer was final before the cutoff.
* COPIES. The scoreboard numbers equal the evaluation outputs they are copied from
  (validation results, or for a test season artifacts/test_results.json and the
  scorecard's one-season result files).

Needs the published files (scripts/11_export_app.py) and data_cache (scripts/01-08, and
scripts/13 for a test season); skipped otherwise. About 2 minutes (two LightGBM fits).
"""
import json

import numpy as np
import pandas as pd
import pytest

from damdays import config
from damdays.export import app_data as ad
from damdays.export import live_model
from damdays.features import store
from damdays.models import physics, tidemark
from damdays.models.predictions import load_predictions, prediction_path

REAL = config.REPO_DIR / "app" / "data" / "real"


@pytest.fixture(scope="module")
def data():
    """The published documents, the app's dams, their looks, the events and the forecasts (skip if missing).

    val_p1   the rung's VAL-setting forecasts (for the live-curve check)
    past_p1  the forecasts Rewind shows: those of the block of the Rewind season (VAL or TEST)
    """
    needed = [REAL / "forecasts.json", config.CACHE_DIR / "panel.pkl", config.CACHE_DIR / "events.pkl"]
    missing = [path.relative_to(config.REPO_DIR).as_posix() for path in needed if not path.exists()]
    if missing:
        pytest.skip(f"needs {', '.join(missing)} (data_cache/ is not in git: scripts/01 rebuilds it from the "
                    "raw data; app/data/real/ is written by scripts/11)")
    docs = {name: json.loads((REAL / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("meta", "forecasts", "scoreboard")}
    rung = docs["meta"]["model"]["version"]
    block = docs["meta"]["rewind"]["block"]
    for needed_block in {"VAL", block}:
        if not prediction_path(needed_block, "tidemark", f"{rung}_p1").exists():
            pytest.skip(f"needs the {needed_block} forecasts of rung {rung} (scripts/08 or scripts/13)")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    dams = ad.app_dams(attrs, ad.app_regions(docs["meta"]["region"]["key"]))
    looks = ad.dam_looks(pd.read_pickle(config.CACHE_DIR / "panel.pkl"), dams)
    val_p1 = load_predictions("VAL", "tidemark", f"{rung}_p1")
    return dict(docs=docs, rung=rung, block=block, dams=dams, looks=looks,
                events=pd.read_pickle(config.CACHE_DIR / "events.pkl"), val_p1=val_p1,
                past_p1=val_p1 if block == "VAL" else load_predictions(block, "tidemark", f"{rung}_p1"),
                band=tuple(docs["meta"]["rewind"]["band_R30"]))


def past_issues(data):
    return [issue for issue in data["docs"]["forecasts"]["issues"] if issue["kind"] == "past"]


def published_rows(issue):
    return pd.DataFrame(issue["rows"]).set_index("dam_id")


def status_table(looks, events, dams, day):
    """Each dam's last look and status on `day`, with the exporter's own functions."""
    last = ad.last_looks(looks, dams, day)
    last["status"] = ad.issue_status(last, ad.armed_at(looks, events, last), day)
    last["dam_id"] = dams["dam_id"].to_numpy()
    return last.set_index("dam_id")


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------
def test_rewind_rows_use_only_what_was_known_on_the_day(data):
    for issue in past_issues(data):
        day = pd.Timestamp(issue["issue_date"])
        looks = data["looks"][data["looks"]["date"] <= day]
        events = data["events"][data["events"]["confirm_date"] <= day]          # confirmed by the day
        table, _ = ad.issue_tables(data["dams"], looks, events, day, data["past_p1"], data["band"])
        rebuilt = pd.DataFrame(ad.rows_json(table)).set_index("dam_id")
        published = published_rows(issue)
        for column in ("status", "issued_on", "level_pct", "chance", "chance_low", "chance_high", "damdays_days"):
            assert rebuilt[column].equals(published[column]), (issue["issue_date"], column)


def test_truncation_check_catches_a_planted_leak(data):
    """Positive control: let every dam peek at its next look (moved to the issue date); statuses must change."""
    issue = past_issues(data)[0]
    day = pd.Timestamp(issue["issue_date"])
    looks = data["looks"]
    next_look = looks[looks["date"] > day].groupby("uid", sort=False).head(1).assign(date=day)
    leaky = pd.concat([looks[looks["date"] <= day], next_look]).sort_values(["uid", "date"]).reset_index(drop=True)
    status = status_table(leaky, data["events"], data["dams"], day)["status"]
    changed = (status != published_rows(issue)["status"]).sum()
    assert changed > 10


# ---------------------------------------------------------------------------
# Hand checks on single dams, straight from the satellite looks
# ---------------------------------------------------------------------------
def looks_of(data, dam_id):
    """One dam's looks (date, rel = pc_wet / static full), oldest first."""
    uid = data["dams"].set_index("dam_id").loc[dam_id, "uid"]
    return uid, data["looks"][data["looks"]["uid"] == uid][["date", "rel"]].reset_index(drop=True)


def check_forecast_basics(data, issue, row):
    """The last look, its level and the chance of one published forecast."""
    day = pd.Timestamp(issue["issue_date"])
    uid, looks = looks_of(data, row["dam_id"])
    last = looks[looks["date"] <= day].iloc[-1]
    assert row["issued_on"] == last["date"].strftime("%Y-%m-%d")
    assert row["level_pct"] == min(round(last["rel"] * 100), 150)
    past = data["past_p1"]
    p = past.loc[(past["uid"].astype(str) == uid) & (pd.to_datetime(past["issue_date"]) == last["date"]), "p90_R30"]
    assert len(p) == 1 and row["chance"] == round(float(p.iloc[0]), 3)
    return looks, last["date"]


def test_hand_check_a_dam_that_fell_below_a_third(data):
    issue = past_issues(data)[0]
    row = next(r for r in issue["rows"] if r["status"] == "forecast" and r["outcome"] is True)
    looks, issued = check_forecast_basics(data, issue, row)
    start = pd.Timestamp(row["outcome_date"])
    assert issued < start <= issued + pd.Timedelta(days=config.HORIZON_DAYS)
    at = looks.index[looks["date"] == start][0]
    first, second = looks.loc[at], looks.loc[at + 1]
    # The PREREG event: two looks below 30% of full at most 30 days apart ...
    assert first["rel"] < config.R30_LEVEL and second["rel"] < config.R30_LEVEL
    assert (second["date"] - first["date"]).days <= config.CONFIRM_GAP_DAYS
    # ... after a refill to 60% of full in the 180 days before ...
    before = looks[(looks["date"] < start) & (looks["date"] >= start - pd.Timedelta(days=config.ARM_WINDOW_DAYS))]
    assert (before["rel"] >= config.ARM_LEVEL).any()
    # ... and the first such pair after the forecast (no earlier pair inside the window).
    window = looks[(looks["date"] > issued) & (looks["date"] < start)]
    low = (window["rel"] < config.R30_LEVEL).to_numpy()
    assert not (low[:-1] & low[1:]).any()


def test_hand_check_a_dam_that_stayed_above_a_third(data):
    issue = past_issues(data)[0]
    for row in (r for r in issue["rows"] if r["status"] == "forecast" and r["outcome"] is False):
        looks, issued = check_forecast_basics(data, issue, row)
        window = looks[(looks["date"] > issued) & (looks["date"] <= issued + pd.Timedelta(days=config.HORIZON_DAYS))]
        if len(window) >= config.MIN_LABEL_OBS and (window["rel"] >= config.R30_LEVEL).all():
            return          # every look in its 90 days was at least a third full: it did stay above
    pytest.fail("No 'stayed above' forecast whose every look stayed above a third.")


# ---------------------------------------------------------------------------
# The live runway curve is the validated recipe
# ---------------------------------------------------------------------------
def test_live_curve_code_reproduces_the_validated_curves(data):
    extra = tidemark.RUNGS[data["rung"]].extra_features          # rung L3: the two water-balance columns
    table = store.load_p1(groups=("keys", "dam", "nbr"))
    if extra:
        table = physics.with_physics_columns(table)
    models = {kind: live_model.fit_live_hazard(table, kind, config.VAL_START, extra)[0] for kind in ("R30", "D0")}
    val = data["val_p1"]
    sample = val[val["at_risk_R30"].astype(bool)].sample(5000, random_state=0).sort_values("row")
    got = live_model.live_curves(models, table, sample["row"].to_numpy(), extra)
    saved = sample[[f"curve_R30_{h}" for h in ad.HORIZONS]].to_numpy()
    # Bit for bit at the stored precision (the ladder's saved forecasts, e.g. rung L3's, are float32).
    assert np.array_equal(got.astype(saved.dtype), saved)


# ---------------------------------------------------------------------------
# The live fit's time rules, by an independent count
# ---------------------------------------------------------------------------
def test_live_fit_sizes_match_an_independent_count(data):
    path = prediction_path(live_model.PRED_BLOCK, live_model.PRED_TASK, f"{data['rung']}_live")
    summary_path = path.with_name(f"{data['rung']}_live_summary.json")
    if not summary_path.exists():
        pytest.skip("needs the saved live fit (scripts/11)")
    summary = json.loads(summary_path.read_text())
    cutoff = pd.Timestamp(summary["cutoff"])
    keys = store.load_p1(groups=("keys",))
    issued = pd.to_datetime(keys["issue_date"])
    labelled = keys["label_ok"].astype(bool)
    for kind in ("R30", "D0", "D0g"):
        at_risk = keys["at_risk_R30" if kind == "R30" else "at_risk_D0"].astype(bool)
        # TIME: issue + 90 days + 30 days to confirm < cutoff
        final = issued + pd.Timedelta(days=config.ANSWER_FINAL_DAYS) < cutoff
        assert summary["members"][kind]["fit_rows"] == int((at_risk & labelled & keys[f"y_{kind}"].notna()
                                                            & final).sum())
    # The floor: answers (365 days + 30) final before 1 Jul 2016 to fit, before the cutoff to calibrate.
    at_risk = keys["at_risk_R30"].astype(bool) & labelled
    floor_final = pd.Timedelta(days=395)
    assert summary["floor"]["fit_rows"] == int((at_risk & (issued + floor_final < pd.Timestamp(config.TEST_START)))
                                               .sum())
    assert summary["floor"]["calibration_rows"] == int((at_risk & (issued >= pd.Timestamp(config.TEST_START))
                                                        & (issued + floor_final < cutoff)).sum())
    # The curve: the first 30-day interval of its last issue was final (+ 30 days to confirm) before the cutoff.
    for kind in ("R30", "D0"):
        last_issue = pd.Timestamp(summary["curves"][kind]["last_issue_used"])
        assert last_issue + pd.Timedelta(days=30 + 30) < cutoff


# ---------------------------------------------------------------------------
# Copies
# ---------------------------------------------------------------------------
def test_scoreboard_is_copied_from_the_evaluation_outputs(data):
    board, rung = data["docs"]["scoreboard"], data["rung"]
    if board["source"] == "dev_test":
        check_test_scoreboard(board)
        return
    results = json.loads((config.ARTIFACTS_DIR / f"val_tidemark_{rung}.json").read_text())
    rain = json.loads((config.ARTIFACTS_DIR / "scorecard" / "step03_val" / "dev_VAL" / "P2_cell" / "rain__all.json")
                      .read_text())
    assert board["source"] == "dev_val" and board["is_validation"] is True
    p2, p1 = results["p2"][f"P2_cell|all|{rung}"], results["p1"][f"P1_R30|primary|{rung}"]
    all_seasons = board["rating"]["all_seasons"]
    assert all_seasons["rating_auc"] == dict(value=p2["point"]["auc"], ci_low=p2["ci_dam"]["auc"][0],
                                             ci_high=p2["ci_dam"]["auc"][1])
    assert all_seasons["rain_only_auc"] == dict(value=rain["point"]["auc"], ci_low=rain["ci_dam"]["auc"][0],
                                                ci_high=rain["ci_dam"]["auc"][1])
    assert (all_seasons["n_cells"], all_seasons["n_ran_dry"]) == (p2["rows"]["scored"], p2["rows"]["events"])
    assert board["runway"]["skill_vs_usual_rate"]["value"] == p1["point"]["bss_B0"]
    assert board["runway"]["n_forecasts"] == p1["rows"]["scored"]


def check_test_scoreboard(board):
    """A test-season scoreboard: copied from artifacts/test_results.json and the scorecard's one-season files."""
    results = json.loads((config.ARTIFACTS_DIR / "test_results.json").read_text())
    scores = results["scores"]
    p1 = scores["P1_R30 | dam_like+octmar+at_risk | tidemark"]
    p2, rain = scores["P2_cell | all | tidemark"], scores["P2_cell | all | RAIN"]

    def as_range(result, metric):
        return dict(value=result["point"][metric], ci_low=result["ci_dam"][metric][0],
                    ci_high=result["ci_dam"][metric][1])

    assert board["is_validation"] is False and board["block"] == "TEST"
    all_seasons = board["rating"]["all_seasons"]
    assert all_seasons["rating_auc"] == as_range(p2, "auc")
    assert all_seasons["rain_only_auc"] == as_range(rain, "auc")
    assert (all_seasons["n_cells"], all_seasons["n_ran_dry"]) == (p2["rows"]["scored"], p2["rows"]["events"])
    assert board["runway"]["skill_vs_usual_rate"] == as_range(p1, "bss_B0")
    assert board["runway"]["n_forecasts"] == p1["rows"]["scored"]
    dev = next(panel for panel in board["panels"] if panel["key"] == "dev_test")
    assert dev["runway"]["gain_vs_benchmark"] == as_range(p1, "d_bss_B0_vs_G2")
    assert dev["rating"]["gain_vs_rain"] == as_range(p2, "d_auc_vs_RAIN")
    assert dev["rating"]["pass_bar_met"] == results["verdicts"]["p2_cell"]["passed"]
    assert dev["runway"]["pass_bars_met"] == results["verdicts"]["p1_pass_bars_tidemark"]["all_passed"]
    # The one-season line: the scorecard's own result files, on the frozen forecasts (TEST ledger: same_predictions).
    folder = config.ARTIFACTS_DIR / "scorecard" / "step11_app" / "dev_TEST" / "P2_cell"
    season_rating = json.loads((folder / "tidemark__all.json").read_text())
    season_rain = json.loads((folder / "rain__all.json").read_text())
    line = board["rating"]["by_season"][0]
    assert line["rating_auc"] == as_range(season_rating, "auc")
    assert line["rain_only_auc"] == as_range(season_rain, "auc")
    assert season_rating["test_ledger"] == "same_predictions" and season_rain["test_ledger"] == "same_predictions"
