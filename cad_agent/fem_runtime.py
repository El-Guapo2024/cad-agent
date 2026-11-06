"""The FEM workbench's runtime: FreeCAD's own FEM Python (cad_agent/fcfem/Mod/Fem: femtools, femsolver, femmesh,
femobjects, femresult, feminout, ObjectsFem.py, vendored unchanged) importable over the stand-ins for FreeCAD's C++
(cad_agent/fcshim/top), as draft_runtime does for Draft. Gmsh and CalculiX are separate programs, found on the PATH or
in the FEM preferences as FreeCAD finds them (femtools.ccxtools, femmesh.gmshtools)."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FEM = HERE / "fcfem" / "Mod" / "Fem"
_active = False


def activate():
    global _active
    if _active:
        return
    from . import draft_runtime
    draft_runtime.activate()
    if str(FEM) in sys.path:
        sys.path.remove(str(FEM))
    sys.path.insert(0, str(FEM))
    _active = True
