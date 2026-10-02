"""The fitted TEST-setting models a region is forecast with: fitted before the opening, then frozen.

What they are (PREREG "Sealed region protocol": "Models are fitted on development-region issues
before 2016-07-01")
    tidemark  the frozen rung of Tidemark (L3 = full Tidemark): tidemark.fit_tidemark("2016-07-01", rung)
    g2        the PREREG benchmark G2: one LightGBM per kind (R30, D0, D0g) with G2's settings on
              the 29 G2 features, learned from the purged fit rows of all waterbodies
    physics   the water-balance parameters (one pooled set per yearly checkpoint), fitted on the
              same regions' look pairs. The scored region's dams are simulated with them; they are
              never refitted on that region.

Opening: these ARE the development TEST-setting models made by scripts/13_fit_test_setting.py
(the same fitted objects also forecast the development TEST block). `package_development_models`
only fingerprints them and writes the manifest; nothing is fitted.
Dry run: `fit_rehearsal_models` fits the same three things with the same calls, but on ONE
development region (nsw_cw), so the region it is judged on (wvic_sesa) is unseen. Its nets are
checkpointed in their own folder, so the development checkpoints are never overwritten.

Either way the manifest records each file's SHA-256, and `load_models` refuses to forecast with a
file whose SHA-256 differs. For the opening the manifest (artifacts/sealed_models_manifest.json)
is committed with the freeze addendum, before 17:30: anyone can then check that the models used at
the opening are the ones fitted, on development data only, before it.
"""
import hashlib
import json
import pickle
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from damdays import config
from damdays.features import store
from damdays.models import fusion, g2, physics, rows, tidemark

CUTOFF = config.TEST_START                                  # "2016-07-01"
DEVELOPMENT_MODEL_DIR = config.CACHE_DIR / "models" / "TEST"   # written by scripts/13_fit_test_setting.py
DEVELOPMENT_PHYSICS_FILE = store.FEATURES_DIR / "physics_params.pkl"   # written by scripts/10_physics_val.py
KINDS = rows.P1_KINDS                                        # R30, D0, D0g


# ===========================================================================
# Which rung is frozen
# ===========================================================================
def frozen_rung():
    """The rung frozen by the PREREG ladder: artifacts/config_hash.json (the freeze addendum's hash file) if it
    exists, else the highest rung passing both ladder conditions in artifacts/ladder_val.json."""
    hash_file = config.ARTIFACTS_DIR / "config_hash.json"
    if hash_file.exists():
        return json.loads(hash_file.read_text())["frozen_rung"]
    return json.loads((config.ARTIFACTS_DIR / "ladder_val.json").read_text())["highest_passing"]


# ===========================================================================
# G2: the benchmark trees
# ===========================================================================
def fit_g2_trees(table, say=print):
    """G2 for R30, D0 and D0g, fitted at the TEST cutoff. Returns {"models": {kind: tree}, "features": {kind: [...]}}.

    The G2 recipe (damdays.models.g2): G2's LightGBM settings (3 threads) on the 29 G2 features,
    learned from the purged fit rows of all waterbodies (rows.p1_fit_rows: answer final before
    2016-07-01). The same steps as scripts/13_fit_test_setting.py, so both files have one format.
    """
    models, features = {}, {}
    for kind in KINDS:
        started = time.time()
        features[kind] = g2.g2_features(kind)
        fit = np.flatnonzero(rows.p1_fit_rows(table, kind, "TEST", population="all"))
        y = table[rows.p1_label(kind)].to_numpy()[fit].astype(int)
        models[kind] = fusion.fit_tree(fusion.tree_inputs(table, fit, features[kind]), y, seed=0)
        say(f"G2 {kind}: {len(fit):,} fit rows ({int(y.sum()):,} events), {time.time() - started:.0f} s")
    return dict(models=models, features=features, cutoff=CUTOFF,
                about="G2 (PREREG benchmark) fitted at the TEST cutoff; predict with "
                      "fusion.predict_tree(models[kind], table, positions, features[kind])")


def g2_forecasts(g2_trees, table, kind):
    """G2's 90-day probability for every at-risk `kind` issue of the TEST block: (row positions, p)."""
    positions = np.flatnonzero(rows.p1_block_rows(table, kind, "TEST"))
    return positions, fusion.predict_tree(g2_trees["models"][kind], table, positions, g2_trees["features"][kind])


# ===========================================================================
# Fitting the dry run's models (one development region)
# ===========================================================================
def only_regions(frame, regions):
    """The rows of `frame` in the given regions, renumbered from 0 (the row order is kept)."""
    keep = frame["region"].astype(str).isin(list(regions)).to_numpy()
    return frame.loc[keep].reset_index(drop=True)


def rehearsal_physics(fit_regions, say):
    """The water balance fitted on the look pairs of `fit_regions` ONLY, and its columns for their P1 issues.

    The development physics table was fitted on both development regions, so for the dry run it
    is rebuilt: the region treated as unseen must not have shaped the balance either.
    """
    panel = pd.read_pickle(config.CACHE_DIR / "panel.pkl")
    attrs = pd.read_pickle(config.CACHE_DIR / "attributes.pkl")
    with open(config.CACHE_DIR / "silo_rain.pkl", "rb") as handle:
        rain_by_cell = pickle.load(handle)
    panel = panel[panel["region"].astype(str).isin(list(fit_regions))]
    attrs = attrs[attrs["region"].astype(str).isin(list(fit_regions))]
    say(f"physics: fitting the water balance on the look pairs of {list(fit_regions)} only")
    out = physics.build_physics(panel, attrs, rain_by_cell, verbose=True)
    return out["p1_physics"], out["physics_params"]


def rehearsal_inputs(run, say):
    """The development tables cut down to the dry run's fit regions, with that region's own physics columns."""
    columns, params = rehearsal_physics(run.fit_regions, say)
    inputs = tidemark.load_inputs()
    inputs = {name: only_regions(frame, run.fit_regions) for name, frame in inputs.items()}
    physics.check_aligned(columns, inputs["p1"])
    for column in physics.PHY_COLUMNS:
        inputs["p1"][column] = columns[column].to_numpy()
    inputs["net_checkpoint_dir"] = run.net_checkpoint_dir       # never the development checkpoint folder
    say(f"fit tables: {len(inputs['p1']):,} P1 rows, {len(inputs['p2_dam']):,} P2 dam-seasons, "
        f"regions {sorted(inputs['p1']['region'].astype(str).unique())}")
    return inputs, params


def save_pickle(obj, path, margin_bytes=2 ** 30):
    """Write a pickle atomically (temporary file, then rename) after checking there is disk room. Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path.parent).free < margin_bytes:
        raise OSError(f"Less than {margin_bytes / 2 ** 30:.0f} GB free on the disk of {path}: free some space first.")
    temporary = path.with_suffix(".tmp")
    with open(temporary, "wb") as handle:
        pickle.dump(obj, handle, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(path)
    return path


def fit_rehearsal_models(run, rung, say):
    """Fit the dry run's tidemark, G2 and physics on run.fit_regions at the TEST cutoff; save them; write the manifest."""
    started = time.time()
    inputs, params = rehearsal_inputs(run, say)
    say(f"tidemark: fit_tidemark('{CUTOFF}', '{rung}') on {list(run.fit_regions)}")
    model = tidemark.fit_tidemark(CUTOFF, rung, inputs=inputs, log=lambda m: say("  " + m))
    g2_trees = fit_g2_trees(inputs["p1"], say)
    folder = run.models_file.parent
    files = dict(tidemark=save_pickle(model, folder / f"tidemark_{rung}.pkl"),
                 g2=save_pickle(g2_trees, folder / "g2.pkl"),
                 physics=save_pickle({"params": params}, folder / "physics_params.pkl"))
    return write_manifest(run, rung, files, dict(fit_seconds=round(time.time() - started),
                                                 summary=tidemark.summary(model)))


# ===========================================================================
# The opening's models: the development TEST-setting fits of step 13
# ===========================================================================
def package_development_models(run, rung, say):
    """Fingerprint step 13's TEST-setting models and write the opening's manifest (nothing is fitted)."""
    files = dict(tidemark=DEVELOPMENT_MODEL_DIR / f"tidemark_{rung}.pkl", g2=DEVELOPMENT_MODEL_DIR / "g2.pkl",
                 physics=DEVELOPMENT_PHYSICS_FILE)
    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing {missing}: run scripts/13_fit_test_setting.py first (it fits the "
                                "development TEST-setting models the opening forecasts with).")
    model = pd.read_pickle(files["tidemark"])
    if model.rung.name != rung or model.cutoff != CUTOFF:
        raise ValueError(f"{files['tidemark']} is rung {model.rung.name} at {model.cutoff}, not {rung} at {CUTOFF}.")
    summary_file = config.ARTIFACTS_DIR / "test_setting_fit_summary.json"
    say(f"packaging the development TEST-setting models of step 13 (rung {rung})")
    return write_manifest(run, rung, files, dict(summary=tidemark.summary(model),
                                                 step13_summary=summary_file.relative_to(config.REPO_DIR).as_posix()
                                                 if summary_file.exists() else None))


# ===========================================================================
# The manifest, and loading with the fingerprints checked
# ===========================================================================
def sha256_of(path):
    """SHA-256 (hex) of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(run, rung, files, extra):
    """Write run.models_manifest: each model file's path, size and SHA-256, plus a fit summary. Returns it."""
    manifest = dict(
        written_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        run=run.name, rung=rung, cutoff=CUTOFF, fit_regions=list(run.fit_regions),
        files={name: dict(path=Path(path).resolve().relative_to(config.REPO_DIR).as_posix(),
                          bytes=Path(path).stat().st_size, sha256=sha256_of(path)) for name, path in files.items()},
        physics_params=pd.read_pickle(files["physics"])["params"].to_dict(orient="records"),
        **extra)
    run.models_manifest.parent.mkdir(parents=True, exist_ok=True)
    run.models_manifest.write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return manifest


def load_models(run, say):
    """The run's fitted models, after checking every file's SHA-256 against the manifest.

    Returns dict(tidemark=TidemarkModel, g2={"models", "features"}, physics_params=DataFrame, manifest=dict).
    Raises if the manifest is missing, a file differs from it, or the models are not the TEST setting.
    """
    if not run.models_manifest.exists():
        raise FileNotFoundError(f"No {run.models_manifest}: run the runner with --prepare first.")
    manifest = json.loads(run.models_manifest.read_text())
    for name, entry in manifest["files"].items():
        path = config.REPO_DIR / entry["path"]
        got = sha256_of(path) if path.exists() else "missing"
        if got != entry["sha256"]:
            raise ValueError(f"Model file {entry['path']} ({name}) has SHA-256 {got[:16]}..., but the manifest "
                             f"says {entry['sha256'][:16]}...: these are not the frozen models.")
        say(f"  {name}: {entry['path']} SHA-256 {entry['sha256'][:16]}... matches the manifest")
    model = pd.read_pickle(config.REPO_DIR / manifest["files"]["tidemark"]["path"])
    g2_trees = pd.read_pickle(config.REPO_DIR / manifest["files"]["g2"]["path"])
    params = pd.read_pickle(config.REPO_DIR / manifest["files"]["physics"]["path"])["params"]
    if model.rung.name != manifest["rung"] or model.cutoff != CUTOFF or g2_trees["cutoff"] != CUTOFF:
        raise ValueError("The model files are not the TEST setting of the manifest's rung.")
    return dict(tidemark=model, g2=g2_trees, physics_params=params, manifest=manifest)
