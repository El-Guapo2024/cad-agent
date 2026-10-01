"""placements.toml: parts moved by hand, on top of what assembly.py places.

The workbench (`cad serve`) writes this file when you drag a part, and so does
`cad place`. Each entry is one rigid move in world millimetres and degrees:

    p' = R · (p - about) + about + move,    R = Rx(turn.x) · Ry(turn.y) · Rz(turn.z)

`about` is the pivot, fixed when the entry is first written, so the entry
means the same thing after the part's geometry changes. The rotation order is
three.js's Euler "XYZ", which is what the workbench's handle produces.

Every consumer of an assembly (check, verify, render, measure --posed) sees
the moved parts, because `state.load_assembly` applies this file. It is a
design input: `cad verify` hashes it, and git shows exactly what moved. Once
a move settles, fold it into assembly.py and delete the entry.

It fails closed: an unparseable file, an unknown key, or a vector that is not
three numbers raises, so a typo cannot quietly leave a part where it was.
"""
from __future__ import annotations

import math
import tomllib
from pathlib import Path

FILE = "placements.toml"
KEYS = ("move", "turn", "about")
HEADER = """\
# Parts moved by hand in the workbench (cad serve) or with `cad place`.
# Each entry is a rigid move on top of assembly.py, in world mm and degrees:
#   p' = R(turn) . (p - about) + about + move,   R = Rx . Ry . Rz
# `cad place <slug> <body> --reset` removes one. Fold settled moves into
# assembly.py and delete them here.
"""


class PlacementError(ValueError):
    """placements.toml exists but does not say something we can apply."""


def _vec(name: str, key: str, value) -> tuple[float, float, float]:
    if (not isinstance(value, list) or len(value) != 3
            or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value)):
        raise PlacementError(f"{FILE}: [{name}] {key} must be three numbers, got {value!r}")
    out = tuple(float(x) for x in value)
    if not all(math.isfinite(x) for x in out):
        raise PlacementError(f"{FILE}: [{name}] {key} must be finite, got {value!r}")
    return out


def load(pdir: Path) -> dict[str, dict]:
    """{body: {"move", "turn", "about"}}, or {} when the project has no file."""
    path = Path(pdir) / FILE
    if not path.exists():
        return {}
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise PlacementError(f"{FILE} does not parse: {e}") from e
    out = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise PlacementError(f"{FILE}: {name!r} must be a [table], got {type(entry).__name__}")
        unknown = sorted(set(entry) - set(KEYS))
        if unknown:
            raise PlacementError(f"{FILE}: [{name}] has unknown key {', '.join(unknown)} "
                                 f"(keys: {', '.join(KEYS)})")
        out[name] = {"move": _vec(name, "move", entry.get("move", [0, 0, 0])),
                     "turn": _vec(name, "turn", entry.get("turn", [0, 0, 0])),
                     "about": _vec(name, "about", entry.get("about", [0, 0, 0]))}
    return out


def matrix(p: dict) -> list[list[float]]:
    """The 3x4 matrix [R | t] of one placement, so that p' = R p + t."""
    ax, ay, az = (math.radians(a) for a in p["turn"])
    cx, sx, cy, sy, cz, sz = (math.cos(ax), math.sin(ax), math.cos(ay),
                              math.sin(ay), math.cos(az), math.sin(az))
    # Rx · Ry · Rz, written out
    r = [[cy * cz, -cy * sz, sy],
         [cx * sz + sx * sy * cz, cx * cz - sx * sy * sz, -sx * cy],
         [sx * sz - cx * sy * cz, sx * cz + cx * sy * sz, cx * cy]]
    about, move = p["about"], p["move"]
    t = [about[i] + move[i] - sum(r[i][j] * about[j] for j in range(3)) for i in range(3)]
    return [r[i] + [t[i]] for i in range(3)]


def location(p: dict):
    """A build123d Location for one placement."""
    from build123d import Location
    from OCP.gp import gp_Trsf
    m = matrix(p)
    trsf = gp_Trsf()
    trsf.SetValues(*m[0], *m[1], *m[2])
    return Location(trsf)


def apply(parts: dict, placed: dict) -> dict:
    """Parts with every placement applied. Names the assembly lacks are left
    for the `placements` rule to report, rather than failing every command."""
    if not placed:
        return parts
    return {n: (s.moved(location(placed[n])) if n in placed else s) for n, s in parts.items()}


def is_identity(p: dict) -> bool:
    return all(abs(x) < 1e-9 for x in (*p["move"], *p["turn"]))


def _fmt(v) -> str:
    return "[" + ", ".join(repr(round(float(x), 6) + 0.0) for x in v) + "]"


def save(pdir: Path, placed: dict) -> Path:
    """Write every placement, sorted, in a stable format so diffs stay small.
    An empty mapping removes the file."""
    path = Path(pdir) / FILE
    if not placed:
        path.unlink(missing_ok=True)
        return path
    lines = [HEADER]
    for name in sorted(placed):
        p = placed[name]
        lines += [f"[{name}]", f"move = {_fmt(p['move'])}", f"turn = {_fmt(p['turn'])}",
                  f"about = {_fmt(p['about'])}", ""]
    path.write_text("\n".join(lines))
    return path
