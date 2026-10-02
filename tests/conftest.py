"""Make "import damdays" work when pytest is run from anywhere."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_report_header(config):
    """On a fresh clone, say at the top why the tests on the real data will skip."""
    from damdays import config as damdays_config
    if not (damdays_config.CACHE_DIR / "panel.pkl").exists():
        return ("DamDays: data_cache/ is not built (it is not in git), so the tests on the real data skip, "
                "each saying what it needs. Rebuild it from the raw data with scripts/01 and 02 "
                "(README, 'Reproduce'). Use -rs to list the skips.")
    return None
