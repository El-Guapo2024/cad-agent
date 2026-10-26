"""FreeCAD's assembly solver, from Python: OndselSolver with AssemblyObject.cpp's mapping ported in front.

The solver is ui/ondsel: OndselSolver (FreeCAD's submodule at 4be80eef02a3, LGPL-2.1, unchanged, in
ui/ondsel/upstream) and assembly.cpp, a port of the solving half of FreeCAD 3160daf1e2b6's
src/Mod/Assembly/App/AssemblyObject.cpp (LGPL-2.1-or-later), built as a shared library and loaded with
ctypes. The browser runs the same code compiled to WebAssembly (ui/ondsel/dist, ui/src/ondsel.ts).

A document is a dict (ui/ondsel/api.cpp has the full format): the Assembly's components with their
Placement and whether they are grounded, and its JointGroup's joints with their properties, each
reference carrying the element type and radius AssemblyUtils reads off the shape:

    solve({"parts": [{"name": "Box", "placement": P, "grounded": True}, {"name": "Box001", ...}],
           "joints": [{"name": "Joint", "type": "Fixed",
                       "reference1": {"part": "Box", "subs": ["Face6", "Vertex8"], "geom": "Plane"},
                       "reference2": {...}, "placement1": P, "placement2": P}]})
    P = {"base": [x, y, z], "rotation": [x, y, z, w]}

The result is what AssemblyObject::solve() leaves: "status" (its return: 0, -1 failed, -6 nothing
grounded), "dof" and "redundant" (updateSolveStatus), "placements", the joints as the solve left them
("swapped": the ones whose references getDistanceType, Screw or RackPinion swapped), "warnings" (the
Console warnings) and "log" (the solver's own output). Drag keeps a document open for the drags the
view provider makes on every mouse move (preDrag, doDragStep, postDrag).

The library is looked for in $ONDSEL_LIB, next to this module and in ui/ondsel/build/; build it with
`ui/ondsel/build.sh native` (it needs only a C++ compiler).
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

_LIB = None
_NAME = "libondsel.dylib" if sys.platform == "darwin" else "libondsel.so"


class OndselNotBuilt(RuntimeError):
    pass


class OndselError(ValueError):
    pass


def library_paths() -> list[Path]:
    here = Path(__file__).resolve().parent
    paths = []
    if os.environ.get("ONDSEL_LIB"):
        paths.append(Path(os.environ["ONDSEL_LIB"]))
    paths += [here / _NAME, here.parent / "ui" / "ondsel" / "build" / _NAME]
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
        raise OndselNotBuilt(f"the assembly solver library is not built (looked for {tried}). Build it with "
                             "`ui/ondsel/build.sh native` (a C++ compiler is all it needs).")
    s, i = ctypes.c_char_p, ctypes.c_int
    for name, args, res in (
            ("ondsel_version", [], s), ("ondsel_solve", [s], s), ("ondsel_export", [s], s),
            ("ondsel_query", [s, s, s], s), ("ondsel_new", [s], i), ("ondsel_last_error", [], s),
            ("ondsel_free", [i], None), ("ondsel_handle_solve", [i], s), ("ondsel_pre_drag", [i, s], s),
            ("ondsel_drag_step", [i, s], s), ("ondsel_post_drag", [i], s)):
        f = getattr(lib, name)
        f.argtypes, f.restype = args, res
    _LIB = lib
    return lib


def available() -> bool:
    try:
        _lib()
        return True
    except OndselNotBuilt:
        return False


def version() -> str:
    return _lib().ondsel_version().decode()


def _out(raw: bytes) -> dict:
    out = json.loads(raw.decode())
    if "error" in out:
        raise OndselError(out["error"])
    return out


def _enc(v) -> bytes:
    return json.dumps(v, allow_nan=False).encode()


def solve(doc: dict, enable_redo: bool = False) -> dict:
    """AssemblyObject::solve() on the document; see the module docstring for the result."""
    return _out(_lib().ondsel_solve(_enc({**doc, "enable_redo": bool(enable_redo)})))


def export_asmt(doc: dict) -> dict:
    """AssemblyObject::exportAsASMT(): {"asmt": the file's text, "swapped", "warnings"}."""
    return _out(_lib().ondsel_export(_enc(doc)))


def query(doc: dict, op: str, *args: str):
    """isPartConnected(part), isPartGrounded(part), isJointConnectingPartToGround(joint, "Reference1"),
    getDownstreamParts(part, joint): the assembly's answers JointObject.py asks for."""
    return _out(_lib().ondsel_query(_enc(doc), op.encode(), _enc(list(args))))["value"]


class Drag:
    """A document kept open in the solver for a drag: pre_drag(parts), step({part: P}) per mouse move,
    post_drag(). Each returns the solve's result with the placements as they now are."""

    def __init__(self, doc: dict):
        lib = _lib()
        self._h = lib.ondsel_new(_enc(doc))
        if not self._h:
            raise OndselError(lib.ondsel_last_error().decode())

    def solve(self) -> dict:
        return _out(_lib().ondsel_handle_solve(self._h))

    def pre_drag(self, parts) -> dict:
        return _out(_lib().ondsel_pre_drag(self._h, _enc(list(parts))))

    def step(self, placements: dict) -> dict:
        return _out(_lib().ondsel_drag_step(self._h, _enc(placements)))

    def post_drag(self) -> dict:
        return _out(_lib().ondsel_post_drag(self._h))

    def close(self):
        if self._h:
            _lib().ondsel_free(self._h)
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
