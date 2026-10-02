"""User preferences that the CLI acts on, shared by the agent and the UI — the
part of FreeCAD's `User parameter:BaseApp/Preferences` that changes what a
`cad` command does rather than how the page looks (those stay in the page).

Store: `~/.cad-agent/preferences.json`, or `CAD_PREFS` when set (tests set
it). Read fresh on every call, never cached: a command may run in a warm
worker started long before the setting changed (see undo.record).

Keys, with FreeCAD's names and defaults:
- MaxUndoSize (Preferences > General > Document, "Maximum undo/redo steps",
  DlgSettingsDocument.ui prefUndoRedoSize, default 20): how many entries
  each end of the undo journal keeps.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS: dict[str, int] = {"MaxUndoSize": 20}
# QSpinBox's own range (DlgSettingsDocument.ui sets none): 0..99.
RANGES: dict[str, tuple[int, int]] = {"MaxUndoSize": (0, 99)}


def path() -> Path:
    raw = os.environ.get("CAD_PREFS")
    return Path(raw).expanduser() if raw else Path.home() / ".cad-agent" / "preferences.json"


def load() -> dict:
    """Every key, the stored value or its default."""
    try:
        stored = json.loads(path().read_text())
    except (OSError, ValueError):
        stored = {}
    return {k: stored.get(k, v) if isinstance(stored.get(k, v), type(v)) else v for k, v in DEFAULTS.items()}


def get(key: str) -> int:
    if key not in DEFAULTS:
        raise KeyError(key)
    return load()[key]


def set_value(key: str, value: str | int) -> int:
    """Store one key (clamped to its range, as the spin box does); returns it."""
    if key not in DEFAULTS:
        raise KeyError(key)
    v = int(value)
    lo, hi = RANGES[key]
    v = max(lo, min(hi, v))
    p = path()
    try:
        stored = json.loads(p.read_text())
    except (OSError, ValueError):
        stored = {}
    stored[key] = v
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(stored, indent=2) + "\n")
    tmp.replace(p)
    return v


def reset(key: str) -> int:
    """Back to FreeCAD's default (Reset Page)."""
    return set_value(key, DEFAULTS[key])
