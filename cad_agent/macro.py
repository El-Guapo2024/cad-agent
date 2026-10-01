"""Macros: FreeCAD's macro recorder, for this CLI.

A macro is a text file of `cad` commands — what a person did in the UI,
recorded as the commands an agent would type — so a workflow can be shown and
replayed, and an agent in a terminal can read and write one like any other
file. One macro is one file, `<macro dir>/<Name>.cad`:

    # cad macro: <Name>
    # recorded <iso8601>
    cad build demo plate
    # cad gui select demo plate        (commented out: recorded without GUI commands,
                                         the way FreeCAD comments out Gui.* lines)
    cad check demo

A `#` line is a comment (including the two header lines above) and a blank
line is ignored; everything else is one `cad <subcommand> <args…>` command,
project slug written out explicitly, the same line a person would type. This
module only reads, writes and replays that text — recording it (building the
text line by line as someone works) is the UI's job, the way FreeCAD's own
macro recorder lives in the GUI, not in this file.

Replay (`run_lines`) is shared by the CLI (`cad macro run`) and the workbench
(`POST /api/macro/run`): skip blanks/comments, run each line in order, stop at
the first line whose exit code is usage/crash (>= 3) the way a script raises,
but let FAIL/UNCHECKED lines (1/2) carry on. Each side supplies its own
`exec_line(argv) -> {"exit", "text"}` — the CLI's just re-enters `cli.main`,
so a `cad gui ...` line falls through to the same `gui_client` call typing it
by hand would make; the workbench's dispatches `gui` lines straight to its own
`GuiBoard` (the `/api/gui/do` path) instead of spawning a subprocess for them,
since that state only exists in the server's own memory.
"""
from __future__ import annotations

import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path

EXT = ".cad"
NAME_RE = re.compile(r"[A-Za-z0-9_ -]+")


def macro_dir() -> Path:
    """`~/.cad-agent/macros`, or `CAD_MACRO_DIR` when set. Tests must set the
    env var to a temp dir; this never touches the real one otherwise."""
    raw = os.environ.get("CAD_MACRO_DIR")
    return Path(raw).expanduser() if raw else Path.home() / ".cad-agent" / "macros"


def validate_name(name) -> str:
    """Letters, digits, space, `-` and `_` only: no path parts, no dot, so a
    name can never climb out of the macro dir or collide with its .cad suffix."""
    name = str(name)
    if not name or name != name.strip() or not NAME_RE.fullmatch(name):
        raise ValueError(f"macro name {name!r}: letters, digits, space, - and _ only")
    return name


def macro_path(name: str) -> Path:
    return macro_dir() / f"{validate_name(name)}{EXT}"


def _names() -> list[str]:
    d = macro_dir()
    return sorted(p.stem for p in d.glob(f"*{EXT}")) if d.is_dir() else []


def _missing(name: str) -> FileNotFoundError:
    have = ", ".join(_names()) or "none"
    return FileNotFoundError(f"no macro {name!r} (macros: {have})")


def list_macros() -> list[dict]:
    """Every saved macro: name, line count, last-modified, sorted by name."""
    d = macro_dir()
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob(f"*{EXT}")):
        try:
            text = p.read_text()
            mtime = p.stat().st_mtime
        except OSError:
            continue
        out.append({"name": p.stem, "lines": len(text.splitlines()),
                    "modified": datetime.fromtimestamp(mtime, tz=timezone.utc)
                    .isoformat(timespec="seconds")})
    return sorted(out, key=lambda r: r["name"])


def read_macro(name: str) -> str:
    p = macro_path(name)
    if not p.is_file():
        raise _missing(name)
    return p.read_text()


def save_macro(name: str, text: str) -> Path:
    """Create or overwrite a macro with exactly this text."""
    p = macro_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(p)
    return p


def delete_macro(name: str) -> Path:
    p = macro_path(name)
    if not p.is_file():
        raise _missing(name)
    p.unlink()
    return p


def rename_macro(name: str, to: str) -> Path:
    src = macro_path(name)
    if not src.is_file():
        raise _missing(name)
    dest = macro_path(to)
    if dest == src:
        return src
    if dest.exists():
        raise FileExistsError(f"macro {to!r} already exists")
    src.rename(dest)
    return dest


def duplicate_macro(name: str, to: str) -> Path:
    src = macro_path(name)
    if not src.is_file():
        raise _missing(name)
    dest = macro_path(to)
    if dest == src or dest.exists():
        raise FileExistsError(f"macro {to!r} already exists")
    dest.write_text(src.read_text())
    return dest


# ─── replay ──────────────────────────────────────────────────────────────────

def tokens(line: str) -> list[str] | None:
    """One line's argv, or None for a blank line or a comment. A leading
    literal `cad` token is dropped, so a line reads the way it would be typed."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    parts = shlex.split(s)
    if parts and parts[0] == "cad":
        parts = parts[1:]
    return parts or None


def run_lines(lines, exec_line) -> dict:
    """Run a macro's lines in order through `exec_line(argv) -> {"exit", "text"}`.

    Blanks and comments are skipped. A line whose exit is >= 3 (usage/crash)
    stops the replay right there, like a script raising; FAIL (1) and
    UNCHECKED (2) are recorded and the replay continues. Returns
    `{"exit": worst, "ran": [{"line", "exit", "text"}, ...]}`, where `worst`
    is that stopping line's own exit if it stopped early, else FAIL if any
    line failed, else UNCHECKED if any was unchecked, else OK.
    """
    ran = []
    for raw in lines:
        try:
            argv = tokens(raw)
        except ValueError as e:
            ran.append({"line": raw.strip(), "exit": 3, "text": f"bad macro line: {e}"})
            break
        if argv is None:
            continue
        r = exec_line(argv)
        ran.append({"line": raw.strip(), "exit": r["exit"], "text": r.get("text", "")})
        if r["exit"] >= 3:
            break
    exits = [r["exit"] for r in ran]
    if exits and exits[-1] >= 3:
        worst = exits[-1]
    elif 1 in exits:
        worst = 1
    elif 2 in exits:
        worst = 2
    else:
        worst = 0
    return {"exit": worst, "ran": ran}
