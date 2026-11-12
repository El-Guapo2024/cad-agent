"""FreeCAD's Z88 solver (cad_agent/fcfem's femsolver/z88, vendored unchanged) over the stand-ins does what it does in
FreeCAD 26.3 (tests/golden/fem_z88: cases.py, make.py, freecad.json, meshes/).

Without Gmsh or Z88, each case's mesh is FreeCAD's own (meshes/<case>.vtk), read back as GmshTools reads it, and the
input files FEM's Z88 writer writes from it (Z88Tools.prepare) must be FreeCAD's, byte for byte. With Gmsh and z88r on
the PATH (or FREECAD_BIN naming the folder that has Gmsh), the whole analysis runs as the FEM workbench's Run runs it
(femsolver.run.run_fem_solver) and the result read back must be the one FreeCAD read.
"""
import importlib.util
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent / "golden" / "fem_z88"
_spec = importlib.util.spec_from_file_location("fem_z88_cases", HERE / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES
FC = json.loads((HERE / "freecad.json").read_text())
# The plate's hole: its mesh differs slightly from FreeCAD's (tests/test_fem_golden.py's KNOWN, ui/PARITY.md "FEM").
KNOWN = {"plate_hole": 1e-3}


def _setup(name):
    from cad_agent import fem_runtime
    fem_runtime.activate()
    import FreeCAD as App
    import ObjectsFem
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetInt("NumOfThreads", 1)
    doc = App.newDocument(name)
    an, mesh = CASES[name](doc, App, ObjectsFem)
    doc.recompute()
    sol = [o for o in an.Group if o.isDerivedFrom("Fem::FemSolverObjectPython")][0]
    return App, doc, an, mesh, sol


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_z88_input_is_freecads(name, tmp_path):
    App, doc, an, mesh, sol = _setup(name)
    from femmesh.gmshtools import GmshTools
    from femsolver.z88 import z88tools
    g = GmshTools(mesh)
    g.get_gmsh_command = lambda: setattr(g, "gmsh_bin", "gmsh")     # Gmsh is not run here
    g.prepare()
    shutil.copy(HERE / "meshes" / f"{name}.vtk", g.temp_file_mesh)
    g.update_properties()                          # FreeCAD's mesh read back, its groups renamed
    assert (mesh.FemMesh.NodeCount, mesh.FemMesh.VolumeCount) == (FC[name]["nodes"], FC[name]["volumes"])
    sol.WorkingDirectory = str(tmp_path)
    z88tools.Z88Tools(sol).prepare()               # run_fem_solver's first step
    for f, text in FC[name]["inputs"].items():
        assert (tmp_path / f).read_text() == text, f
    App.closeDocument(doc.Name)


def _programs():
    path = os.pathsep.join(p for p in (os.environ.get("FREECAD_BIN"), os.environ.get("PATH")) if p)
    return [shutil.which(b, path=path) for b in ("gmsh", "z88r")], path


def _lengths(grid, name):
    from vtkmodules.util import numpy_support as ns
    a = grid.GetPointData().GetArray(name)
    n = np.linalg.norm(ns.vtk_to_numpy(a).reshape(a.GetNumberOfTuples(), -1), axis=1)
    return float(n.min()), float(n.max())


@pytest.mark.skipif(not all(_programs()[0]), reason="Gmsh and z88r are not on the PATH")
@pytest.mark.parametrize("name", sorted(CASES))
def test_the_whole_z88_analysis_is_freecads(name, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", _programs()[1])
    App, doc, an, mesh, sol = _setup(name)
    from femmesh.gmshtools import GmshTools
    from femsolver.run import run_fem_solver
    assert not GmshTools(mesh).create_mesh()
    run_fem_solver(sol, str(tmp_path), blocking=True)
    assert sorted(os.listdir(tmp_path)) == FC[name]["outputs"]
    grid = [r for r in sol.Results if r.isDerivedFrom("Fem::FemPostPipeline")][0].Data
    pd = grid.GetPointData()
    assert [pd.GetArrayName(i) for i in range(pd.GetNumberOfArrays())] == FC[name]["arrays"]
    rel = KNOWN.get(name, 1e-9)
    if name not in KNOWN:
        assert (grid.GetNumberOfPoints(), grid.GetNumberOfCells()) == (FC[name]["points"], FC[name]["cells"])
        for f, text in FC[name]["inputs"].items():
            assert (tmp_path / f).read_text() == text, f
    for key, array in (("displacement", "Displacement"), ("nodal_force", "Nodal Force")):
        lo, hi = FC[name][key]
        got = _lengths(grid, array)
        assert got[0] == pytest.approx(lo, abs=max(rel, 1e-9) * hi), key
        assert got[1] == pytest.approx(hi, rel=rel), key
    App.closeDocument(doc.Name)
