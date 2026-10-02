"""Tests of the sealed-region runner (damdays.sealed), on small made-up files. Nothing sealed is read.

The full rehearsal (scripts/20_open_sealed_region.py --dry-run) runs the whole pipeline on a
development region; these check the pieces that must never go wrong at the opening: the hash
check, the guards, the separation of the dry run from the real ledger, and the verdicts.
"""
import dataclasses
import hashlib
import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from damdays import config
from damdays.data import guard, panel
from damdays.evaluation.ledger import LEDGER_PATH
from damdays.models import nets, physics
from damdays.sealed import checks, fitted_models, region, runs, scoring


# ---------------------------------------------------------------------------
# git is only ever read
# ---------------------------------------------------------------------------
def test_git_helper_refuses_every_command_that_could_write():
    for command in ("commit", "push", "fetch", "checkout", "reset", "add", "stash"):
        with pytest.raises(ValueError, match="read-only"):
            checks.git(command)


def test_only_the_runners_own_outputs_may_be_uncommitted(monkeypatch):
    changed = ["artifacts/sealed/run_log.txt", "artifacts/test_ledger.csv", "damdays/models/physics.py"]
    monkeypatch.setattr(checks, "changed_paths", lambda: changed)
    status = checks.git_status(runs.OPENING)
    assert not status["clean"] and status["changed"] == ["damdays/models/physics.py"]
    monkeypatch.setattr(checks, "changed_paths", lambda: changed[:2])
    assert checks.git_status(runs.OPENING)["clean"]
    # The models manifest is NOT a runner output: it must be committed before the opening.
    monkeypatch.setattr(checks, "changed_paths", lambda: ["artifacts/sealed_models_manifest.json"])
    assert not checks.git_status(runs.OPENING)["clean"]


def test_the_committed_hash_list_is_the_event_start_copy():
    table, provenance = checks.committed_hash_list()
    assert len(table) == checks.EXPECTED_SEALED_FILES == 4_711
    assert provenance["commit"].startswith("e0e9b0b")           # committed at 09:12 Fri, never changed since
    assert table["file"].is_unique and table["sha256"].str.len().eq(64).all()


# ---------------------------------------------------------------------------
# The file check: a 100% match or nothing
# ---------------------------------------------------------------------------
def write_files(folder, contents):
    """Write made-up time-series files; returns their hash list (file, sha256, bytes)."""
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, text in contents.items():
        (folder / name).write_bytes(text.encode())
        rows.append(dict(file=name, sha256=hashlib.sha256(text.encode()).hexdigest(), bytes=len(text.encode())))
    return pd.DataFrame(rows, columns=checks.HASH_LIST_COLUMNS)


FILES = {"r1aaaaaaa_v3.csv": "date,pc_wet,px_wet\n2000-01-01T00:00:00Z,50,10\n",
         "r1bbbbbbb_v3.csv": "date,pc_wet,px_wet\n2000-01-01T00:00:00Z,20,4\n"}


def test_verify_files_accepts_only_a_full_match(tmp_path):
    hash_list = write_files(tmp_path / "ts", FILES)
    report = checks.verify_files(hash_list, tmp_path / "ts")
    assert report["all_match"] and report["n_matched"] == 2
    checks.require_full_match(report, expected_files=2)
    with pytest.raises(checks.CheckFailed, match="2 files match, 3 expected"):
        checks.require_full_match(report, expected_files=3)


def test_one_changed_byte_an_extra_file_or_a_missing_file_stops_the_run(tmp_path):
    hash_list = write_files(tmp_path / "ts", FILES)
    (tmp_path / "ts" / "r1aaaaaaa_v3.csv").write_text(FILES["r1aaaaaaa_v3.csv"].replace("50", "51"))
    report = checks.verify_files(hash_list, tmp_path / "ts")
    assert list(report["mismatched"]) == ["r1aaaaaaa_v3.csv"]
    with pytest.raises(checks.CheckFailed, match="differ from their committed hash"):
        checks.require_full_match(report, 2)

    hash_list = write_files(tmp_path / "ts2", FILES)
    (tmp_path / "ts2" / "r1ccccccc_v3.csv").write_text("extra")
    with pytest.raises(checks.CheckFailed, match="unlisted files"):
        checks.require_full_match(checks.verify_files(hash_list, tmp_path / "ts2"), 2)
    # A development folder holds other regions' files too: they are ignored when asked.
    assert checks.verify_files(hash_list, tmp_path / "ts2", only_listed_files=False)["all_match"]

    (tmp_path / "ts2" / "r1bbbbbbb_v3.csv").unlink()
    with pytest.raises(checks.CheckFailed, match="missing"):
        checks.require_full_match(checks.verify_files(hash_list, tmp_path / "ts2", only_listed_files=False), 2)


def test_a_malformed_hash_list_is_refused():
    good = "file,sha256,bytes\nr1aaaaaaa_v3.csv," + "a" * 64 + ",10\n"
    assert len(checks.parse_hash_list(good)) == 1
    for bad in (good.replace("a" * 64, "a" * 63), good.replace("r1aaaaaaa_v3.csv", "notes.txt"),
                good + "r1aaaaaaa_v3.csv," + "b" * 64 + ",10\n", good.replace("sha256", "hash")):
        with pytest.raises(checks.CheckFailed):
            checks.parse_hash_list(bad)


# ---------------------------------------------------------------------------
# Nothing sealed is touched while the switch is off; the dry run refuses the switch
# ---------------------------------------------------------------------------
def test_the_sealed_folder_and_manifest_are_refused_while_locked(monkeypatch):
    monkeypatch.delenv(config.SEALED_UNLOCK_ENV, raising=False)
    tiny = pd.DataFrame([dict(file="r1aaaaaaa_v3.csv", sha256="a" * 64, bytes=1)])
    with pytest.raises(PermissionError):
        checks.verify_files(tiny, config.SEALED_DIR / "ts")
    with pytest.raises(PermissionError):
        region.region_manifest(runs.SEALED_REGION_NAME)


def test_the_dry_run_refuses_to_start_with_the_unlock_switch_on(monkeypatch, tmp_path):
    monkeypatch.setenv(config.SEALED_UNLOCK_ENV, "yes")
    with pytest.raises(checks.CheckFailed, match="unset it for the dry run"):
        checks.rehearsal_preflight(runs.DRY_RUN, ([], tmp_path), tmp_path / "list.csv", say=lambda m: None)


def test_the_opening_refuses_without_the_unlock_switch(monkeypatch):
    monkeypatch.delenv(config.SEALED_UNLOCK_ENV, raising=False)
    with pytest.raises(checks.CheckFailed, match="unlock switch is off"):
        checks.opening_preflight(runs.OPENING, config.SEALED_DIR / "ts", say=lambda m: None)


# ---------------------------------------------------------------------------
# The dry run can never use up the real TEST look or overwrite development files
# ---------------------------------------------------------------------------
def test_the_dry_run_has_its_own_ledger_folders_and_names():
    dry, real = runs.DRY_RUN, runs.OPENING
    assert real.ledger_path == LEDGER_PATH and dry.ledger_path != LEDGER_PATH
    assert dry.target_region in config.DEV_REGIONS and dry.target_region not in dry.fit_regions
    assert real.target_region in config.SEALED_REGION and set(real.fit_regions) == set(config.DEV_REGIONS)
    assert dry.cache_dir != real.cache_dir and dry.results_dir != real.results_dir
    assert dry.model_name("tidemark") == "dryrun_tidemark" and real.model_name("tidemark") == "tidemark"
    # The dry run's nets are checkpointed in their own folder; the opening shares the development one.
    assert real.net_checkpoint_dir is None
    assert nets.checkpoint_path("S", "2009-01-01", 0, dry.net_checkpoint_dir).parent.parent == dry.net_checkpoint_dir
    assert nets.checkpoint_path("S", "2009-01-01", 0).parent.parent == nets.CHECKPOINT_DIR


def test_a_regions_raw_files_come_from_its_own_folder():
    assert region.raw_source("wvic_sesa") == (config.DEV_MANIFEST, config.DEV_TS_DIR)
    assert region.raw_source(runs.SEALED_REGION_NAME) == (config.SEALED_DIR / "manifest.csv", config.SEALED_DIR / "ts")
    with pytest.raises(ValueError):
        region.raw_source("nowhere")


def test_the_panel_reads_a_given_folder(tmp_path):
    write_files(tmp_path / "ts", FILES)
    manifest = pd.DataFrame(dict(uid=["r1aaaaaaa_v3", "r1bbbbbbb_v3"], region="x", area_m2=9000.0, lat=-30.0, lon=150.0))
    assert panel.check_downloads(manifest, tmp_path / "ts")["missing"] == []
    built, qc = panel.build_panel(manifest, tmp_path / "ts")
    assert len(built) == 2 and list(qc["n_kept"]) == [1, 1]


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------
def test_expectations_are_read_as_inside_below_or_above():
    values = {"R30 BSS vs B0": (0.19, [0.17, 0.21]), "R30 BSS vs B2": (0.05, None),
              "R30 calibration slope": (1.4, None), "R30 CITL": (-0.3, None)}
    got = {e["expectation"]: e["verdict"] for e in scoring.expectation_rows(values)}
    assert got["R30 BSS vs B0"] == "inside" and got["R30 BSS vs B2"] == "below"
    assert got["R30 calibration slope"] == "above" and got["R30 CITL"] == "inside"
    assert got["P2 cell AUC gain over RAIN"] == "not computed"


def test_p2_pass_bar_and_kill_rule():
    def result(gain, ci):
        return dict(point={"d_auc_vs_RAIN": gain}, ci_dam={"d_auc_vs_RAIN": ci}, ci_region_year={})
    passed = scoring.p2_rules(result(0.25, [0.20, 0.30]), "RAIN")
    assert passed["passed"] and not passed["kill_rule_triggered"]
    weak = scoring.p2_rules(result(0.06, [-0.01, 0.12]), "RAIN")       # gain above 0.05 but CI not above 0
    assert not weak["passed"] and not weak["kill_rule_triggered"]
    killed = scoring.p2_rules(result(0.015, [0.0, 0.03]), "RAIN")
    assert not killed["passed"] and killed["kill_rule_triggered"]
    assert np.isclose(scoring.P2_PASS_DAUC, 0.05) and np.isclose(scoring.P2_KILL_DAUC, 0.02)


# ---------------------------------------------------------------------------
# The frozen models: a file that differs from its committed fingerprint is refused
# ---------------------------------------------------------------------------
def test_a_model_file_that_differs_from_the_manifest_is_refused(tmp_path):
    run = dataclasses.replace(runs.DRY_RUN, models_manifest=tmp_path / "manifest.json")
    model_file = tmp_path / "tidemark.pkl"
    model_file.write_bytes(b"the frozen model")
    run.models_manifest.write_text(json.dumps(dict(rung="L3", files={"tidemark": dict(
        path=str(model_file), sha256=hashlib.sha256(b"the frozen model").hexdigest())})))
    model_file.write_bytes(b"a refitted model")
    with pytest.raises(ValueError, match="not the frozen models"):
        fitted_models.load_models(run, say=lambda m: None)
    with pytest.raises(FileNotFoundError, match="--prepare"):
        fitted_models.load_models(dataclasses.replace(run, models_manifest=tmp_path / "none.json"), say=lambda m: None)


# ---------------------------------------------------------------------------
# The whole opening pre-flight on copies of REAL development files (never sealed ones)
# ---------------------------------------------------------------------------
def opening_preflight_on(folder, hash_list, monkeypatch):
    """Run checks.opening_preflight on `folder`, with git and the committed list replaced by test values."""
    monkeypatch.setattr(guard, "sealed_unlocked", lambda: True)          # the switch, without the environment
    monkeypatch.setattr(checks, "git_status", lambda run: dict(clean=True, changed=[], runner_outputs_changed=[]))
    monkeypatch.setattr(checks, "head_is_pushed", lambda: dict(pushed=True, head="0" * 40, remote_sha="0" * 40,
                                                               how="test"))
    monkeypatch.setattr(checks, "committed_hash_list",
                        lambda: (hash_list, dict(files=len(hash_list), commit="0" * 40, committed_at="test")))
    monkeypatch.setattr(checks, "EXPECTED_SEALED_FILES", len(hash_list))
    return checks.opening_preflight(runs.OPENING, folder, say=lambda m: None)


@pytest.mark.skipif(not config.DEV_TS_DIR.exists(), reason="needs the development downloads")
def test_the_hash_check_cannot_pass_on_a_tampered_copy_of_real_development_files(tmp_path, monkeypatch):
    names = [f"{uid}.csv" for uid in panel.load_manifest()["uid"].head(3)]
    folder = tmp_path / "ts"
    folder.mkdir()
    for name in names:
        shutil.copyfile(config.DEV_TS_DIR / name, folder / name)
    # The list is made without checks.py: hashlib straight on the ORIGINAL files.
    hash_list = pd.DataFrame([dict(file=n, sha256=hashlib.sha256((config.DEV_TS_DIR / n).read_bytes()).hexdigest(),
                                   bytes=(config.DEV_TS_DIR / n).stat().st_size) for n in names])
    checked, verified = opening_preflight_on(folder, hash_list, monkeypatch)
    assert checked["files"]["all_match"] and checked["files"]["n_matched"] == 3 and verified == sorted(names)

    original = (folder / names[1]).read_bytes()
    middle = len(original) // 2
    tampered = {
        "one bit flipped, same size": original[:middle] + bytes([original[middle] ^ 1]) + original[middle + 1:],
        "line endings changed, as an editor might save it": original.replace(b"\n", b"\r\n"),
        "another dam's history under this name": (folder / names[0]).read_bytes(),
        "last line cut": original[:original.rstrip(b"\r\n").rfind(b"\n") + 1],
    }
    for what, content in tampered.items():
        assert content != original, what
        (folder / names[1]).write_bytes(content)
        with pytest.raises(checks.CheckFailed, match="differ from their committed hash"):
            opening_preflight_on(folder, hash_list, monkeypatch)
    (folder / names[1]).write_bytes(original)
    opening_preflight_on(folder, hash_list, monkeypatch)                  # restored: passes again

    (folder / "r9zzzzzzz_v3.csv").write_bytes(original)                  # an extra file
    with pytest.raises(checks.CheckFailed, match="unlisted files"):
        opening_preflight_on(folder, hash_list, monkeypatch)
    (folder / "r9zzzzzzz_v3.csv").unlink()
    (folder / names[2]).unlink()                                          # a missing file
    with pytest.raises(checks.CheckFailed, match="missing"):
        opening_preflight_on(folder, hash_list, monkeypatch)


def test_the_manifest_must_list_exactly_the_verified_files():
    manifest = pd.DataFrame(dict(uid=["r1aaaaaaa_v3", "r1bbbbbbb_v3"]))
    region.require_manifest_matches_files(manifest, ["r1bbbbbbb_v3.csv", "r1aaaaaaa_v3.csv"])
    with pytest.raises(checks.CheckFailed, match="verified but not listed"):
        region.require_manifest_matches_files(manifest.iloc[:1], ["r1aaaaaaa_v3.csv", "r1bbbbbbb_v3.csv"])
    with pytest.raises(checks.CheckFailed, match="listed but not verified"):
        region.require_manifest_matches_files(manifest, ["r1aaaaaaa_v3.csv"])


# ---------------------------------------------------------------------------
# git that never answers is a failure (or the offline fallback), never a hang or a crash
# ---------------------------------------------------------------------------
def test_git_that_does_not_answer_is_a_failure_not_a_hang(monkeypatch):
    def never_answers(command, *args, **kwargs):
        raise subprocess.TimeoutExpired(command, checks.GIT_TIMEOUT_SECONDS)
    monkeypatch.setattr(checks.subprocess, "run", never_answers)
    assert checks.git("ls-remote", "origin", allow_fail=True)[0] != 0
    with pytest.raises(checks.CheckFailed, match="no answer"):
        checks.git("status")


def test_a_slow_remote_falls_back_to_the_last_push_from_this_clone(monkeypatch):
    if checks.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", allow_fail=True)[0] != 0:
        pytest.skip("this clone has no upstream branch")
    real_run = subprocess.run

    def slow_remote(command, *args, **kwargs):
        if command[:2] == ["git", "ls-remote"]:
            raise subprocess.TimeoutExpired(command, checks.GIT_TIMEOUT_SECONDS)
        return real_run(command, *args, **kwargs)
    monkeypatch.setattr(checks.subprocess, "run", slow_remote)
    assert "OFFLINE" in checks.head_is_pushed()["how"]


# ---------------------------------------------------------------------------
# The freeze addendum and the typed evaporation shape
# ---------------------------------------------------------------------------
def test_the_opening_refuses_unless_a_committed_addendum_quotes_the_evaporation_hash(tmp_path):
    evaporation, code = "f" * 64, "c" * 64
    with pytest.raises(checks.CheckFailed, match="freeze addendum"):
        checks.freeze_addendum_quotes(evaporation, code, folder=tmp_path)
    (tmp_path / "PREREG_ADDENDUM_1.md").write_text(f"evaporation {evaporation}", encoding="utf-8")
    assert checks.freeze_addendum_quotes(evaporation, code, folder=tmp_path) == dict(
        evaporation=["PREREG_ADDENDUM_1.md"], config_hash=[])           # a config hash not quoted: reported only
    (tmp_path / "PREREG_ADDENDUM_1.md").write_text(f"evaporation {evaporation}, code {code[:12]}", encoding="utf-8")
    assert checks.freeze_addendum_quotes(evaporation, code, folder=tmp_path)["config_hash"] == ["PREREG_ADDENDUM_1.md"]


def test_the_typed_sealed_evaporation_shape_is_the_one_hashed_in_the_freeze_addendum():
    values = physics.EVAPORATION_MM_PER_DAY[runs.SEALED_REGION_NAME]
    text = f"{runs.SEALED_REGION_NAME}:" + ",".join(str(v) for v in values)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digest == "f886f4190d19b044fadb8b08aa0fbe854efa1342abba191316dd10e65096af36"
    addendum = config.REPO_DIR / "PREREG_ADDENDUM_1.md"
    if addendum.exists():
        assert digest in addendum.read_text(encoding="utf-8") and text in addendum.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A subset of a new region without events is listed, not a crash of the one-shot run
# ---------------------------------------------------------------------------
def test_a_subset_without_events_is_listed_instead_of_stopping_the_run():
    messages = []
    scorer = scoring.RegionScoring.__new__(scoring.RegionScoring)      # only what score() needs
    scorer.run, scorer.say, scorer.results, scorer.not_scored = runs.DRY_RUN, messages.append, {}, []
    frame = pd.DataFrame(dict(uid=["a", "b", "c"], issue_date=pd.to_datetime(["2017-01-01"] * 3),
                              y=[0.0, 0.0, np.nan]))
    keys = frame.loc[frame["y"].notna(), ["uid", "issue_date"]]
    assert scorer.score(frame, "P1_D0g", "persistent+octmar+at_risk", "G2", [], "side", keys) is None
    assert scorer.not_scored == [dict(task="P1_D0g", subset="persistent+octmar+at_risk", model="dryrun_G2",
                                      rows=2, events=0)]
    assert "NOT SCORABLE" in messages[0] and scorer.results == {}


# ---------------------------------------------------------------------------
# The opening's models are the ones fingerprinted in the committed manifest
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not runs.OPENING.models_manifest.exists(), reason="no opening manifest yet (--prepare)")
def test_the_opening_models_match_their_manifest():
    manifest = json.loads(runs.OPENING.models_manifest.read_text())
    if not all((config.REPO_DIR / entry["path"]).exists() for entry in manifest["files"].values()):
        pytest.skip("the model files are not on this machine (data_cache is not in git)")
    models = fitted_models.load_models(runs.OPENING, say=lambda m: None)
    assert manifest["rung"] == fitted_models.frozen_rung() == models["tidemark"].rung.name
    assert set(manifest["fit_regions"]) == set(config.DEV_REGIONS) and manifest["cutoff"] == config.TEST_START
    assert models["physics_params"]["year"].max() <= config.LAST_CHECKPOINT_YEAR   # pairs before 2016 only
