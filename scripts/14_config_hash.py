"""Step 14: the EVENT BUILD CONFIG HASH, filed in the freeze addendum (PREREG_ADDENDUM_1.md).

Run from the repo folder:
    .venv/Scripts/python.exe scripts/14_config_hash.py

PREREG "Model": "The event build's own config hash is filed in a dated addendum before the
sealed region is opened." This script makes that hash. It reads no data and fits nothing.

What is hashed (SHA-256; the same files and constants always give the same hash)
  1. SOURCE: every damdays/**/*.py file (model, feature, data, evaluation and export code,
     config.py included; no tests). Line endings are read as LF, so a Windows (CRLF) checkout
     gives the same hash. The source hash is the SHA-256 of a sorted "<file hash>  <path>" list,
     the format of the standard sha256sum tool.
  2. CONSTANTS: the frozen settings, read from the modules that use them and written as JSON
     with sorted keys: the frozen rung (L3) and its members and seeds, every LightGBM setting and
     input list, the nets' settings and inputs, the frailty lambda, the floor and band settings,
     the season-rating settings and the physics constants (with the typed evaporation shapes).
     They are inside the source files too; listing them on their own makes the frozen values
     readable and checkable without reading the code.
  EVENT BUILD CONFIG HASH = SHA-256 of "source <hash 1>\\nconstants <hash 2>\\n". The addendum
  quotes its first 12 hex digits (like the pre-event research config fe0ab596d1fe) and the full value.

Also printed: the sealed region's typed evaporation constant and its own hash (PREREG "Sealed
region protocol": the evaporation shape is "typed in from public BoM climatology and hashed in
the addendum before opening"). The exact hashed text is printed, so any SHA-256 tool can check it:
    printf '%s' '<hashed text>' | sha256sum

Output: artifacts/config_hash.json (every file hash, the constants and the three hashes).
Any change to a hashed file or constant changes the hash, so run this again right before the
addendum is committed. It warns when git reports uncommitted changes under damdays/.
"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

# Let "import damdays" work when this file is run directly.
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from damdays import config  # noqa: E402
from damdays.features import sequences, spec  # noqa: E402
from damdays.models import frailty, fusion, g2, hazard, nets, physics, rows, tidemark  # noqa: E402
from damdays.models import season_rating as sr  # noqa: E402
from damdays.models import uncertainty as unc  # noqa: E402

FROZEN_RUNG = "L3"          # the PREREG ladder decision: highest rung passing both conditions (artifacts/ladder_val.md)
SEALED_REGION = next(iter(config.SEALED_REGION))   # "sealed_sdowns_newengland"
OUT_JSON = config.ARTIFACTS_DIR / "config_hash.json"


def sha256_text(text):
    """SHA-256 (hex) of a text, encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ===========================================================================
# 1. The source files
# ===========================================================================
def source_files():
    """Every damdays/**/*.py file except tests, as repo-relative POSIX paths in sorted order."""
    files = []
    for path in (REPO / "damdays").rglob("*.py"):
        relative = path.relative_to(REPO).as_posix()
        if "tests" in path.parts or path.name.startswith("test_") or "__pycache__" in path.parts:
            continue
        files.append(relative)
    return sorted(files)


def file_hash(relative_path):
    """SHA-256 of one file with its line endings read as LF (so CRLF and LF checkouts agree)."""
    content = (REPO / relative_path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def source_hash():
    """(hash of the manifest, manifest lines). Manifest: "<file hash>  <path>" per file, sorted by path."""
    lines = [f"{file_hash(path)}  {path}" for path in source_files()]
    return sha256_text("\n".join(lines) + "\n"), lines


# ===========================================================================
# 2. The frozen constants
# ===========================================================================
def frozen_constants():
    """The frozen settings of the event build, by component (exactly the values the code uses)."""
    rung = tidemark.RUNGS[FROZEN_RUNG]
    kinds = rows.P1_KINDS
    return {
        "frozen_rung": dict(name=rung.name, about=rung.about, members=rung.members, frailty=rung.frailty,
                            max_rule=rung.max_rule, extra_features=rung.extra_features),
        "member_seeds": {name: member.seeds for name, member in tidemark.MEMBERS.items()},
        "settings_by_cutoff": tidemark.SETTINGS,
        "tree_T": dict(params=g2.G2_PARAMS, threads=fusion.TREE_N_JOBS, probability_clip=[fusion.P_MIN, fusion.P_MAX],
                       features={k: fusion.tree_features(k, rung.extra_features) for k in kinds}),
        "frailty": dict(lam=frailty.FRAILTY_LAMBDA, answer_final_days=frailty.ANSWER_FINAL_DAYS),
        "nets_S_M": dict(settings=nets.NET_SETTINGS, seeds=nets.SEEDS, threads=nets.TORCH_THREADS,
                         tabular_inputs=nets.TABULAR_INPUTS, log_scaled=nets.LOG_SCALED,
                         sequence_months=sequences.SEQUENCE_MONTHS, sequence_channels=sequences.CHANNELS,
                         rain_climatology_years=sequences.RAIN_CLIMATOLOGY_YEARS,
                         months_since_cap=sequences.MONTHS_SINCE_CAP, log_rain_scale=sequences.LOG_RAIN_SCALE),
        "runway_curve_H": dict(params=hazard.HAZARD_PARAMS, interval_edges=hazard.INTERVAL_EDGES,
                               confirm_days=hazard.CONFIRM_DAYS,
                               features={k: hazard.hazard_features(k, rung.extra_features) for k in hazard.CURVE_KINDS}),
        "floor": dict(params=unc.FLOOR_PARAMS, kind=unc.FLOOR_KIND, cap_days=unc.FLOOR_CAP_DAYS,
                      miss_rate=unc.FLOOR_MISS_RATE, display_max_days=unc.FLOOR_DISPLAY_MAX_DAYS,
                      features=unc.floor_features()),
        "season_band": dict(inner_blocks=unc.BAND_INNER_BLOCKS),
        "season_rating_P2": dict(params=sr.P2_PARAMS, seeds=sr.SEEDS, k_shrink=sr.K_SHRINK,
                                 variant=sr.VARIANTS["main"], features=sr.season_features(True),
                                 area_index=sr.AREA_INDEX, area_min=[sr.AREA_MIN_LAST, sr.AREA_MIN_LONG]),
        "physics": dict(columns=physics.PHY_COLUMNS, evaporation_mm_per_day=physics.EVAPORATION_MM_PER_DAY,
                        draw_weight=physics.DRAW_WEIGHT, volume_exponent=physics.VOLUME_EXPONENT,
                        rain_thresholds_mm=physics.RAIN_THRESHOLDS_MM, first_year=physics.FIRST_PHYSICS_YEAR,
                        fit_regions=physics.FIT_REGIONS, pair_gap_days=physics.PAIR_GAP_DAYS,
                        pair_rel_range=physics.PAIR_REL_RANGE, huber_k=physics.HUBER_K,
                        huber_iterations=physics.HUBER_ITERATIONS, ridge=physics.RIDGE,
                        obs_variance=physics.OBS_VARIANCE, process_variance_per_day=physics.PROCESS_VARIANCE_PER_DAY,
                        filter_restart_gap_days=physics.FILTER_RESTART_GAP_DAYS, members=physics.N_MEMBERS,
                        step_days=physics.STEP_DAYS, steps=physics.N_STEPS, half_pixel=physics.HALF_PIXEL,
                        d0_level_range=physics.D0_LEVEL_RANGE, seed=physics.PHYSICS_SEED),
        "p1_feature_lists": dict(g2c={k: spec.p1_tree_features(k) for k in kinds}, physics=spec.PHYSICS_FEATURE_SPEC),
    }


def sorted_set(value):
    """JSON has no sets: write a set as a sorted list. Any other unknown type is an error, never a guess."""
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"Cannot hash a constant of type {type(value).__name__}: {value!r}")


def canonical_json(value):
    """JSON with sorted keys and no spaces: the same value always gives the same text."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=sorted_set)


# ===========================================================================
# 3. The sealed region's typed evaporation constant
# ===========================================================================
def sealed_evaporation():
    """(hashed text, its SHA-256, the 12 typed values, the shape the model uses = values / their mean)."""
    values = physics.EVAPORATION_MM_PER_DAY[SEALED_REGION]
    text = f"{SEALED_REGION}:" + ",".join(str(v) for v in values)
    shape = [round(float(v), 4) for v in physics.evaporation_shape(SEALED_REGION)]
    return text, sha256_text(text), list(values), shape


# ===========================================================================
# Run
# ===========================================================================
def uncommitted_changes():
    """Lines of `git status --porcelain damdays` (empty when the hashed files equal the last commit)."""
    try:
        result = subprocess.run(["git", "status", "--porcelain", "--", "damdays"], cwd=REPO,
                                capture_output=True, text=True, check=True)
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.CalledProcessError) as error:
        return [f"(git status failed: {error})"]


def config_hash():
    """(event build config hash, source hash, constants hash, file manifest lines, constants JSON text).

    Also called by scripts/20_open_sealed_region.py, which records the hash of the code it runs.
    """
    source, manifest = source_hash()
    constants_text = canonical_json(frozen_constants())
    constants_hash = sha256_text(constants_text)
    build_hash = sha256_text(f"source {source}\nconstants {constants_hash}\n")
    return build_hash, source, constants_hash, manifest, constants_text


def main():
    build_hash, source, constants_hash, manifest, constants_text = config_hash()
    evap_text, evap_hash, evap_values, evap_shape = sealed_evaporation()
    changes = uncommitted_changes()

    out = dict(computed_at=time.strftime("%Y-%m-%d %H:%M:%S"), frozen_rung=FROZEN_RUNG,
               event_build_config_hash=build_hash, event_build_config_hash_short=build_hash[:12],
               source_hash=source, constants_hash=constants_hash, source_files=manifest,
               constants=json.loads(constants_text),
               sealed_evaporation=dict(region=SEALED_REGION, mm_per_day=evap_values, shape=evap_shape,
                                       hashed_text=evap_text, sha256=evap_hash),
               uncommitted_changes_under_damdays=changes)
    OUT_JSON.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")

    print(f"source files hashed: {len(manifest)} (damdays/**/*.py, no tests)")
    print(f"source hash:         {source}")
    print(f"constants hash:      {constants_hash}")
    print(f"EVENT BUILD CONFIG HASH: {build_hash[:12]}  (full {build_hash})")
    print(f"sealed evaporation constant ({SEALED_REGION}, mm/day Jan-Dec): {evap_values}")
    print(f"  shape used by the model (values / mean): {evap_shape}")
    print(f"  hashed text: {evap_text}")
    print(f"  SHA-256:     {evap_hash}")
    if changes:
        print("WARNING: uncommitted changes under damdays/ (the hash describes the files on disk):")
        for line in changes:
            print(f"  {line}")
    print(f"wrote {OUT_JSON.relative_to(REPO).as_posix()}")


if __name__ == "__main__":
    main()
