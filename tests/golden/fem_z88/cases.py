"""Z88 analyses (FreeCAD's FEM Python, cad_agent/fcfem, over the stand-ins): the CalculiX cases' documents
(../fem/cases.py) whose constraints Z88's writer takes (Fixed, Force, Pressure, Displacement), with a SolverZ88 in place
of CalculiX, as the FEM workbench's Solver Z88 command makes it (ObjectsFem.makeSolverZ88). The same lines run in
FreeCAD (make.py) and here (tests/test_fem_z88_golden.py).
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fem_cases_ccx", Path(__file__).parent.parent / "fem" / "cases.py")
_ccx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ccx)


def _z88(doc, an, ObjectsFem):
    """The analysis's CalculiX solver replaced by a SolverZ88."""
    for o in list(an.Group):
        if o.isDerivedFrom("Fem::FemSolverObjectPython"):
            an.removeObject(o)
            doc.removeObject(o.Name)
    sol = ObjectsFem.makeSolverZ88(doc, "SolverZ88")
    an.addObject(sol)
    return sol


def _case(ccx):
    def make(doc, App, ObjectsFem):
        an, mesh = ccx(doc, App, ObjectsFem)
        _z88(doc, an, ObjectsFem)
        return an, mesh
    make.__name__ = ccx.__name__
    make.__doc__ = ccx.__doc__
    return make


cantilever = _case(_ccx.cantilever)               # 100 N down on the free end of a fixed steel bar
pressure_plate = _case(_ccx.pressure_plate)       # 0.5 MPa on a plate fixed on both ends, second order tetrahedra
plate_hole = _case(_ccx.plate_hole)               # the plate with a hole, fixed at one end and pulled at the other
displacement_bar = _case(_ccx.displacement_bar)   # the bar's far end moved 0.5 mm down

CASES = {"cantilever": cantilever, "pressure_plate": pressure_plate, "plate_hole": plate_hole,
         "displacement_bar": displacement_bar}
