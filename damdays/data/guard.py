"""Keep the sealed test region sealed.

The sealed region is our one clean test (see PREREG.md). Its files must not be
read until the scheduled opening on Sat 3 Oct 17:30 AEST. Every loader in
damdays.data passes its paths through `check_path` before opening anything, so
an accidental read fails loudly instead of silently leaking test data.

At the opening, set the environment variable named in
config.SEALED_UNLOCK_ENV to "yes" to allow access.
"""
import os
from pathlib import Path

from damdays import config


def sealed_unlocked():
    """True only when the sealed region has been deliberately opened."""
    return os.environ.get(config.SEALED_UNLOCK_ENV, "") == "yes"


def _normalised(path):
    """Absolute path text with ".." removed and case folded on Windows.

    Pure text work: it never touches the file system, so checking a sealed
    path does not open or list anything inside the sealed folder. The flip
    side: it does not follow shortcuts (symlinks, junctions) or Windows short
    names like "DEA_SE~1". The guard stops accidents, not deliberate tricks.
    """
    return os.path.normcase(os.path.abspath(path))


def check_path(path):
    """Return `path` unchanged, or raise if it points inside the sealed folder.

    Paths are normalised first, so tricks like "dea_dev/../dea_sealed" are caught too.
    """
    if sealed_unlocked():
        return Path(path)

    sealed = _normalised(config.SEALED_DIR)
    target = _normalised(path)
    if target == sealed or target.startswith(sealed + os.sep):
        raise PermissionError(
            f"Refusing to read the sealed region: {path}. "
            f"It opens once, at the scheduled time, by setting {config.SEALED_UNLOCK_ENV}=yes."
        )
    return Path(path)
