"""The undo/redo journal: one FreeCAD-style transaction per model-changing
command, shared by the person in the UI and the agent in the terminal —
the same contract as a FreeCAD document's own Undo/Redo (App/Document.cpp
transactions; Preferences > General > Document "Maximum Undo/Redo steps",
default 20; a new change clears the redo stack).

`cad set`, `cad place` and the bought-part add commands each call `record`
after they write their files, with the whole text of every file they touched
(before and after; `None` when a file did not exist at that end). A macro is
not a transaction of its own: `macro run` replays `cad` commands one at a
time (see macro.py), so each line that changes something records its own
entry exactly as if it had been typed by hand — this module has no notion of
"macro" at all.

Store: `<project>/.cad/undo.json`, `{"undo": [...], "redo": [...]}`, oldest
first in each list (the last element is the most recent). Both ends are
capped at max_steps() entries (Preferences' MaxUndoSize, userprefs.py;
MAX_STEPS by default), dropping the oldest. `.cad/` is outside what
`cad verify` hashes (verify.DESIGN lists parts/assembly/spec/placements/
bought/baseline only) and outside what counts toward git's dirty check
(verify.git_info skips any path under `/.cad/`), so the journal itself is
never part of a verdict.

`undo`/`redo` (see `perform`) refuse to touch a file that no longer matches
what the entry recorded — someone edited it by hand since the entry was
made — rather than clobbering that edit.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

FILE = "undo.json"
MAX_STEPS = 20


def max_steps() -> int:
    """MaxUndoSize from the user preferences (App::Document::setUndoMode/
    setMaxUndoStackSize take it from Preferences > Document; 0 keeps nothing)."""
    from . import userprefs
    return userprefs.get("MaxUndoSize")


class UndoError(ValueError):
    """An entry's files no longer match what it recorded; undo/redo refused."""


def actor() -> str:
    """The fallback when `record()` isn't given an explicit `by`: 'ui' when
    CAD_ACTOR=ui is set in *this* process's own environment, else 'agent'.
    cli.py's `--actor` argv flag is the real mechanism the workbench server
    uses (see `record`'s docstring for why); this is just a convenience for
    someone testing by hand with `CAD_ACTOR=ui cad set ...` in a shell that
    talks directly to a cold process, not through the warm worker."""
    return "ui" if os.environ.get("CAD_ACTOR") == "ui" else "agent"


def _path(pdir: Path) -> Path:
    return Path(pdir) / ".cad" / FILE


def load(pdir: Path) -> dict:
    """{"undo": [...], "redo": [...]}; empty lists when nothing has been
    journaled yet, or the file does not parse (never raises)."""
    try:
        data = json.loads(_path(pdir).read_text())
    except (OSError, ValueError):
        return {"undo": [], "redo": []}
    if not isinstance(data, dict):
        return {"undo": [], "redo": []}
    undo = data.get("undo", [])
    redo = data.get("redo", [])
    return {"undo": list(undo) if isinstance(undo, list) else [],
            "redo": list(redo) if isinstance(redo, list) else []}


def _save(pdir: Path, data: dict) -> Path:
    path = _path(pdir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)
    return path


def record(pdir: Path, name: str, cmd: str, files: list[dict], by: str | None = None) -> dict | None:
    """Journal one transaction: `files` is `[{"path", "before", "after"}, ...]`,
    each path relative to `pdir`, "before"/"after" the file's whole text
    (`None` when it did not exist at that end). A no-op (every file's before
    equals its after) is not journaled — an empty transaction, the way
    FreeCAD discards one — and this returns `None` in that case.

    `by`, when given, wins over `actor()` — the CLI passes the `--actor`
    argv flag through explicitly, since an env var set in the workbench
    server's own process does not reach a command run in a warm-worker fork
    (the fork inherits the *daemon's* environment, not a client's).

    Recording a new entry clears the redo stack, same as a fresh edit in any
    undo/redo system: the entries being redone described a future that this
    new change has just replaced.
    """
    if all(f.get("before") == f.get("after") for f in files):
        return None
    entry = {"id": uuid.uuid4().hex, "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "by": by or actor(), "name": name, "cmd": cmd, "files": files}
    data = load(pdir)
    n = max_steps()
    data["undo"] = (data["undo"] + [entry])[-n:] if n else []
    data["redo"] = []
    _save(pdir, data)
    return entry


def _check(pdir: Path, entry: dict, field: str, direction: str) -> None:
    """Raise UndoError, naming the file, if any file the entry touched no
    longer holds what was recorded for `field` ("after" to undo, "before"
    to redo) — it was edited by hand since this entry was made."""
    for f in entry["files"]:
        path = Path(pdir) / f["path"]
        want = f[field]
        have = path.read_text() if path.exists() else None
        if have != want:
            when = "left it as" if direction == "undo" else "found it before"
            raise UndoError(
                f"{f['path']} no longer matches what \"{entry['name']}\" {when}; "
                f"it looks like it was edited by hand since. {direction} refused.")


def _write(pdir: Path, files: list[dict], field: str) -> None:
    for f in files:
        path = Path(pdir) / f["path"]
        value = f[field]
        if value is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)


def perform(pdir: Path, direction: str, steps: int = 1) -> dict:
    """Undo or redo up to `steps` entries, one transaction at a time.

    Stops early, with no error, once the stack runs dry — that is just
    "nothing more to undo", not a refusal. Stops early *with* `blocked` set
    when an entry's files no longer match what it recorded; entries already
    applied earlier in this same call are left applied (they were each
    checked and written on their own terms, same as a loop of single steps).

    Returns `{"applied": [entry, ...], "blocked": {"entry", "reason"} | None}`,
    `applied` oldest-first (the order they were walked off the stack).
    """
    if direction not in ("undo", "redo"):
        raise ValueError(direction)
    src, check_field = ("undo", "after") if direction == "undo" else ("redo", "before")
    dst, write_field = ("redo", "before") if direction == "undo" else ("undo", "after")
    applied: list[dict] = []
    blocked = None
    for _ in range(max(0, steps)):
        data = load(pdir)
        stack = data[src]
        if not stack:
            break
        entry = stack[-1]
        try:
            _check(pdir, entry, check_field, direction)
        except UndoError as e:
            blocked = {"entry": entry, "reason": str(e)}
            break
        _write(pdir, entry["files"], write_field)
        data[src] = stack[:-1]
        n = max_steps()
        data[dst] = (data[dst] + [entry])[-n:] if n else []
        _save(pdir, data)
        applied.append(entry)
    return {"applied": applied, "blocked": blocked}
