"""The two runs of the sealed-region runner: the real opening, and its dry-run rehearsal.

Both runs go through exactly the same code (scripts/20_open_sealed_region.py).
Only the settings below differ.

    OPENING  the sealed region (Southern Downs / Granite Belt / New England), opened ONCE,
             Sat 3 Oct 2026 17:30 AEST (PREREG "Sealed region protocol").
             Models learn from both development regions (issues before 2016-07-01).
             Scores go on the real TEST ledger, arena "sealed".

    DRY_RUN  a REHEARSAL on a development region treated as if it were unseen (wvic_sesa).
             Models learn from the other development region only (nsw_cw), so wvic's
             answers never reach them. Scores go on a SEPARATE dry-run ledger, so the
             rehearsal never uses up a real TEST look. Its numbers are a transfer
             rehearsal (one region's models judged on another region), NOT the
             development TEST result, and they are never used to choose anything.

Where things go
    cache_dir        data_cache/... (big, rebuildable, git-ignored): the fitted models, the region's
                     tables, the forecasts
    results_dir      artifacts/... (small, committed): the scorecard JSONs, the results page, the run log
    models_manifest  the fitted models' SHA-256 and fit summary. For the opening it is committed with
                     the freeze addendum BEFORE the opening, so anyone can check that the models used at
                     17:30 are the ones fitted (on development data only) before it.
"""
from dataclasses import dataclass
from pathlib import Path

from damdays import config
from damdays.evaluation.ledger import LEDGER_PATH

SEALED_REGION_NAME = next(iter(config.SEALED_REGION))      # "sealed_sdowns_newengland"


@dataclass(frozen=True)
class Run:
    """Everything that differs between the opening and the dry run."""
    name: str                 # "sealed" or "dryrun"
    about: str                # one line, printed at the start and on the results page
    target_region: str        # the region whose forecasts are scored
    fit_regions: tuple        # the regions the models learn from (issues before 2016-07-01)
    cache_dir: Path           # big files (git-ignored)
    results_dir: Path         # small results (committed)
    ledger_path: Path         # the TEST ledger this run writes to
    models_manifest: Path     # SHA-256 + summary of the fitted models
    model_prefix: str         # prefix of every model name on the scorecard and ledger
    rehearsal: bool           # True for the dry run

    # Paths derived from the two folders, in the order the runner uses them.
    @property
    def models_file(self):
        """The fitted TEST-setting models (one pickle: G2 and the frozen Tidemark rung)."""
        return self.cache_dir / "models" / "test_setting_models.pkl"

    @property
    def net_checkpoint_dir(self):
        """Where nets fitted for this run are checkpointed. None = the development folder data_cache/nets
        (the opening's models ARE the development TEST-setting models, so they share it)."""
        return None if set(self.fit_regions) == set(config.DEV_REGIONS) else self.cache_dir / "nets"

    @property
    def region_dir(self):
        """The target region's tables, built from its raw files (kept so a crash can resume without rebuilding)."""
        return self.cache_dir / "region"

    @property
    def forecasts_dir(self):
        """The forecasts for the target region (kept so a resumed run scores exactly the same forecasts)."""
        return self.cache_dir / "forecasts"

    @property
    def scorecard_dir(self):
        """Where the shared scorecard writes one JSON per score and its markdown tables."""
        return self.results_dir / "scorecard"

    @property
    def results_md(self):
        return self.results_dir / ("SEALED_RESULTS.md" if not self.rehearsal else "DRY_RUN_RESULTS.md")

    @property
    def results_json(self):
        return self.results_dir / ("sealed_results.json" if not self.rehearsal else "dry_run_results.json")

    @property
    def log_file(self):
        """Every line the runner prints, with times (appended on each run, so a resumed run is visible)."""
        return self.results_dir / "run_log.txt"

    def model_name(self, name):
        """The scorecard / ledger name of a model, e.g. "tidemark" or "dryrun_tidemark"."""
        return f"{self.model_prefix}{name}"


OPENING = Run(
    name="sealed",
    about="THE SEALED-REGION OPENING (PREREG 'Sealed region protocol'): scored once, on the real TEST ledger",
    target_region=SEALED_REGION_NAME,
    fit_regions=tuple(config.DEV_REGIONS),
    cache_dir=config.CACHE_DIR / "sealed",
    results_dir=config.ARTIFACTS_DIR / "sealed",
    ledger_path=LEDGER_PATH,
    models_manifest=config.ARTIFACTS_DIR / "sealed_models_manifest.json",
    model_prefix="",
    rehearsal=False,
)

DRY_RUN = Run(
    name="dryrun",
    about=("DRY RUN (REHEARSAL): wvic_sesa treated as an unseen region, models fitted on nsw_cw only, "
           "scored on a separate dry-run ledger. NOT the development TEST result."),
    target_region="wvic_sesa",
    fit_regions=("nsw_cw",),
    cache_dir=config.CACHE_DIR / "sealed_dryrun",
    results_dir=config.ARTIFACTS_DIR / "sealed_dryrun",
    ledger_path=config.ARTIFACTS_DIR / "sealed_dryrun" / "dryrun_ledger.csv",
    models_manifest=config.ARTIFACTS_DIR / "sealed_dryrun" / "models_manifest.json",
    model_prefix="dryrun_",
    rehearsal=True,
)

RUNS = {"open": OPENING, "dry-run": DRY_RUN}
