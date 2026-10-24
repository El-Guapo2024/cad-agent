"""FreeCAD's sketch solver, from Python: PlaneGCS with FreeCAD's Sketch.cpp ported in front of it.

The solver is ui/planegcs (FreeCAD's planegcs, unchanged, and sketch.cpp, a port of the Sketcher's
Sketch.cpp at 3160daf1e2b6, LGPL-2.1-or-later), built as a shared library and loaded with ctypes.
The browser runs the same code compiled to WebAssembly (ui/planegcs/dist, ui/src/planegcs.ts).

A sketch is a dict, the same one ui/src/planegcs.ts takes (ui/planegcs/api.cpp has the full format):

    solve({
        "geometry": [
            {"type": "LineSegment", "start": [0, 0], "end": [10, 0]},
            {"type": "Circle", "center": [5, 5], "radius": 2},
            {"type": "ArcOfCircle", "center": [0, 0], "radius": 3, "start_angle": 0.0, "end_angle": 1.5},
            {"type": "Point", "at": [1, 1], "construction": True},
        ],
        "constraints": [
            # Sketcher.Constraint's argument list after the type; the value, if any, apart
            {"type": "Horizontal", "args": [0]},
            {"type": "Coincident", "args": [0, 1, -1, 1]},
            {"type": "Distance", "args": [0], "value": 10.0, "driving": False},  # reference
            ["Radius", 1, 2.0],    # or the whole Python argument list
        ],
    })

The result says what FreeCAD's SketchObject.solve() would: "status" ("solved", "failed",
"conflicting", "redundant" or "malformed"; "status_code" is FreeCAD's number), "dof",
"conflicting", "redundant", "partially_redundant", "malformed" (constraint indices from 0),
"geometry" (the solution, as the Sketcher draws it; "stored_geometry" is what FreeCAD keeps in
the sketch, which it updates only on success), "constraints" (values after solving: reference
constraints measure, tangency is locked), "dependent" and "dependency_groups" (what is not
fixed yet). Point positions: 1 start, 2 end, 3 centre, 0 the edge; geoId -1 is the H axis (its
start the origin), -2 the V axis.

drag() moves a point or edge after solving, as SketchObject.moveGeometry does; Sketch keeps a
sketch open for the interactive drags the Sketcher makes on every mouse move.

The library is looked for in $PLANEGCS_LIB, next to this module and in ui/planegcs/build/; build it
with `ui/planegcs/build.sh native` (it needs Eigen 3.4 and Boost headers, see that script).
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

_LIB = None
_NAME = "libplanegcs.dylib" if sys.platform == "darwin" else "libplanegcs.so"

START, END, MID, EDGE = 1, 2, 3, 0      # FreeCAD's PointPos
H_AXIS, V_AXIS, ROOT = -1, -2, -1       # geoIds: the axes; the root point is (ROOT, START)


class PlaneGCSNotBuilt(RuntimeError):
    pass


def library_paths() -> list[Path]:
    here = Path(__file__).resolve().parent
    paths = []
    if os.environ.get("PLANEGCS_LIB"):
        paths.append(Path(os.environ["PLANEGCS_LIB"]))
    paths += [here / _NAME, here.parent / "ui" / "planegcs" / "build" / _NAME]
    return paths


def _lib():
    global _LIB
    if _LIB is not None:
        return _LIB
    for path in library_paths():
        if path.is_file():
            lib = ctypes.CDLL(str(path))
            break
    else:
        tried = ", ".join(str(p) for p in library_paths())
        raise PlaneGCSNotBuilt(
            f"the sketch solver library is not built (looked for {tried}). Build it with "
            "`ui/planegcs/build.sh native`, with EIGEN_DIR and BOOST_DIR set (or the system's "
            "libeigen3-dev and libboost-dev installed), or point PLANEGCS_LIB at a built library.")
    s, i, d = ctypes.c_char_p, ctypes.c_int, ctypes.c_double
    for name, res, args in [
        ("pgcs_version", s, []), ("pgcs_solve", s, [s]), ("pgcs_new", i, [s]),
        ("pgcs_last_error", s, []), ("pgcs_free", None, [i]), ("pgcs_handle_solve", s, [i]),
        ("pgcs_result", s, [i]), ("pgcs_move_geometry", s, [i, s, d, d, i]),
        ("pgcs_init_move", s, [i, s]), ("pgcs_move", s, [i, d, d, i]), ("pgcs_end_move", None, [i]),
    ]:
        fn = getattr(lib, name)
        fn.restype = res
        fn.argtypes = args
    _LIB = lib
    return lib


def available() -> bool:
    try:
        _lib()
        return True
    except PlaneGCSNotBuilt:
        return False


def version() -> str:
    return _lib().pgcs_version().decode()


def _out(raw: bytes) -> dict:
    out = json.loads(raw.decode())
    if "error" in out:
        raise ValueError(out["error"])
    return out


def solve(sketch: dict) -> dict:
    """Solve a sketch as FreeCAD's SketchObject.solve() does (see the module docstring)."""
    return _out(_lib().pgcs_solve(json.dumps(sketch).encode()))


def drag(sketch: dict, geo_id: int, pos: int, to, relative: bool = False) -> dict:
    """Solve, then move point `pos` of geometry `geo_id` (pos 0: the whole edge) to `to`, as
    SketchObject.moveGeometry(geo, pos, Vector(*to), relative) does. `to` may be a list of points:
    each is one moveGeometry call, in order."""
    points = [to] if isinstance(to[0], (int, float)) else list(to)
    drags = [{"geo": geo_id, "pos": pos, "to": list(p)[:2], "relative": relative} for p in points]
    return solve({**sketch, "drags": drags})


class Sketch:
    """A sketch kept open in the solver, for interactive editing.

    with Sketch(sketch) as sk:
        sk.solve()
        sk.begin_drag([(0, START)])      # the view provider's initTemporaryMove
        sk.drag_to(3, 4)                 # every mouse move: moveGeometriesTemporary
        sk.end_drag()
        sk.move_geometry([(0, START)], (3, 4))   # the committed move (SketchObject.moveGeometries)
    """

    def __init__(self, sketch: dict):
        lib = _lib()
        self._h = lib.pgcs_new(json.dumps(sketch).encode())
        if not self._h:
            raise ValueError(lib.pgcs_last_error().decode())

    def solve(self) -> dict:
        return _out(_lib().pgcs_handle_solve(self._h))

    def result(self) -> dict:
        return _out(_lib().pgcs_result(self._h))

    def move_geometry(self, elements, to, relative: bool = False) -> dict:
        els = json.dumps([list(e) for e in elements]).encode()
        return _out(_lib().pgcs_move_geometry(self._h, els, float(to[0]), float(to[1]), int(relative)))

    def begin_drag(self, elements) -> dict:
        return _out(_lib().pgcs_init_move(self._h, json.dumps([list(e) for e in elements]).encode()))

    def drag_to(self, x: float, y: float, relative: bool = False) -> dict:
        return _out(_lib().pgcs_move(self._h, float(x), float(y), int(relative)))

    def end_drag(self) -> None:
        _lib().pgcs_end_move(self._h)

    def close(self) -> None:
        if self._h:
            _lib().pgcs_free(self._h)
            self._h = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
