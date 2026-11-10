"""Elmer analyses (FreeCAD's FEM Python, cad_agent/fcfem, over the stand-ins): the CalculiX cases' documents
(../fem/cases.py) with a SolverElmer and its equations in place of CalculiX, as the FEM workbench's Solver Elmer and
equation commands make them (ObjectsFem.makeSolverElmer, makeEquationElasticity and makeEquationHeat). The same lines
run in FreeCAD (make.py) and here (tests/test_fem_elmer_golden.py).
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fem_cases_ccx", Path(__file__).parent.parent / "fem" / "cases.py")
_ccx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ccx)


def _elmer(doc, an, ObjectsFem):
    """The analysis's CalculiX solver replaced by a SolverElmer."""
    for o in list(an.Group):
        if o.isDerivedFrom("Fem::FemSolverObjectPython"):
            an.removeObject(o)
            doc.removeObject(o.Name)
    sol = ObjectsFem.makeSolverElmer(doc, "SolverElmer")
    an.addObject(sol)
    return sol


def cantilever(doc, App, ObjectsFem):
    """The CalculiX cantilever (100 N down on a fixed steel bar), Elmer's elasticity with its stresses."""
    an, mesh = _ccx.cantilever(doc, App, ObjectsFem)
    eq = ObjectsFem.makeEquationElasticity(doc, _elmer(doc, an, ObjectsFem))
    eq.CalculateStresses = True
    return an, mesh


def pressure_plate(doc, App, ObjectsFem):
    """The plate fixed on both ends under 0.5 MPa, second order tetrahedra (the .unv's quadratic node order)."""
    an, mesh = _ccx.pressure_plate(doc, App, ObjectsFem)
    ObjectsFem.makeEquationElasticity(doc, _elmer(doc, an, ObjectsFem))
    return an, mesh


def plate_hole(doc, App, ObjectsFem):
    """The plate with a hole pulled at one end, Elmer's elasticity with its stresses."""
    an, mesh = _ccx.plate_hole(doc, App, ObjectsFem)
    eq = ObjectsFem.makeEquationElasticity(doc, _elmer(doc, an, ObjectsFem))
    eq.CalculateStresses = True
    return an, mesh


def heat(doc, App, ObjectsFem):
    """The thermo-mechanical bar's temperatures (373 K at x = 0, 293 K at the far end), Elmer's heat equation."""
    an, mesh = _ccx.thermomech(doc, App, ObjectsFem)
    for o in list(an.Group):
        if o.Name in ("Fixed", "InitialTemperature"):
            an.removeObject(o)
            doc.removeObject(o.Name)
    ObjectsFem.makeEquationHeat(doc, _elmer(doc, an, ObjectsFem))
    return an, mesh


CASES = {"cantilever": cantilever, "pressure_plate": pressure_plate, "plate_hole": plate_hole, "heat": heat}
