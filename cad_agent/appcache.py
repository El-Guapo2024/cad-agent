"""The user cache: FreeCAD's ApplicationCache (Gui/PreferencePages/
DlgSettingsCacheDirectory.cpp at 3160daf1e2b6) for this tool's cache directory,
the warm worker's `~/.cache/cad-agent` (`CAD_WARM_DIR`): its size, the check
against Preferences' size limit, and clearing it.

Clearing keeps what is in use, as ApplicationCache::clearDirectory keeps the
lock files and open documents' transient directories: only a stopped
worker's files (warm-<id>.*, no live socket) go. Anything else in the
directory, such as the workbench's saved project folders (workbench.json),
is settings, not cache, and stays.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import userprefs

# ApplicationCache::Period, in DlgSettingsCacheDirectory.ui's combo order.
PERIODS = ("Always", "Daily", "Weekly", "Monthly", "Yearly", "Never")
_DAYS = {0: -1, 1: 1, 2: 7, 3: 31, 4: 365, 5: None}
STAMP = ".last-cache-check"  # QSettings' LastCacheCheck


def directory() -> Path:
    return Path(os.environ.get("CAD_WARM_DIR") or Path.home() / ".cache" / "cad-agent")


def size() -> int:
    """ApplicationCache::size: every file under the directory, in bytes."""
    d = directory()
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) if d.is_dir() else 0


def to_string(n: float) -> str:
    """ApplicationCache::toString: Bytes, KB, MB or GB with two decimals."""
    units = ("Bytes", "KB", "MB", "GB")
    i = 0
    while i < len(units) - 1 and n >= 1024:
        n /= 1024
        i += 1
    return f"{n:.2f} {units[i]}"


def limit_bytes() -> int:
    return userprefs.get("CacheLimit") * 1024 * 1024  # ApplicationCache::toBytes(MB)


def _clearable(p: Path) -> bool:
    # A worker's files share its stem (warm-<id>.lock/.sock/.log): a stopped worker's go, but
    # never a lock file or a live worker's (its socket still there).
    if not p.name.startswith("warm-") or p.suffix == ".lock" or p.is_socket():
        return False
    sock = p.with_suffix(".sock")
    return not (sock.exists() and sock.is_socket())


def clear() -> int:
    """ApplicationCache::clearDirectory, keeping what's in use; returns the bytes freed."""
    freed = 0
    d = directory()
    if not d.is_dir():
        return 0
    for p in d.iterdir():
        if p.is_file() and _clearable(p):
            freed += p.stat().st_size
            p.unlink()
    return freed


def periodic_check_due() -> bool:
    """ApplicationCache::periodicCheckOfSize: whether CachePeriod has passed since the last
    check (and if so, record this one)."""
    days = _DAYS[userprefs.get("CachePeriod")]
    if days is None:
        return False
    stamp = directory() / STAMP
    last = stamp.stat().st_mtime if stamp.exists() else None
    if last is not None and (time.time() - last) / 86400 < days:
        return False
    stamp.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp.touch()
    return True
