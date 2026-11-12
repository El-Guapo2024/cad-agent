"""Mystran analyses (FreeCAD's FEM Python, cad_agent/fcfem, over the stand-ins): the CalculiX cases' documents
(../fem/cases.py) whose constraints Mystran's writer takes (Fixed and Force), with a SolverMystran in place of CalculiX,
as the FEM workbench's Solver Mystran command makes it (ObjectsFem.makeSolverMystran). The same lines run in FreeCAD
(make.py) and here (tests/test_fem_mystran_golden.py).
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fem_cases_ccx", Path(__file__).parent.parent / "fem" / "cases.py")
_ccx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ccx)


def _mystran(doc, an, ObjectsFem):
    """The analysis's CalculiX solver replaced by a SolverMystran."""
    for o in list(an.Group):
        if o.isDerivedFrom("Fem::FemSolverObjectPython"):
            an.removeObject(o)
            doc.removeObject(o.Name)
    sol = ObjectsFem.makeSolverMystran(doc, "SolverMystran")
    an.addObject(sol)
    return sol


def cantilever(doc, App, ObjectsFem):
    """The CalculiX cantilever: 100 N down on the free end of a fixed steel bar."""
    an, mesh = _ccx.cantilever(doc, App, ObjectsFem)
    _mystran(doc, an, ObjectsFem)
    return an, mesh


def plate_hole(doc, App, ObjectsFem):
    """The plate with a hole, fixed at one end and pulled at the other."""
    an, mesh = _ccx.plate_hole(doc, App, ObjectsFem)
    _mystran(doc, an, ObjectsFem)
    return an, mesh


CASES = {"cantilever": cantilever, "plate_hole": plate_hole}
