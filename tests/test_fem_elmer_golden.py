"""FreeCAD's Elmer solver (cad_agent/fcfem's femsolver/elmer, vendored unchanged) over the stand-ins does what it does in
FreeCAD 26.3 (tests/golden/fem_elmer: cases.py, make.py, freecad.json, meshes/).

Without Gmsh or Elmer, each case's mesh is FreeCAD's own (meshes/<case>.vtk), read back as GmshTools reads it, and
what FEM's Elmer writer writes from it (case.sif, ELMERSOLVER_STARTINFO) and the .unv FemMesh.write exports of it must be
FreeCAD's, byte for byte. With Gmsh, ElmerGrid and ElmerSolver on the PATH (or FREECAD_BIN naming the folder that has
Gmsh), the whole analysis runs and ElmerGrid's mesh files and ElmerSolver's results must be FreeCAD's.
"""
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

HERE = Path(__file__).parent / "golden" / "fem_elmer"
_spec = importlib.util.spec_from_file_location("fem_elmer_cases", HERE / "cases.py")
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


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_elmer_input_is_freecads(name, tmp_path):
    App, doc, an, mesh, sol = _setup(name)
    from femmesh.gmshtools import GmshTools
    from femsolver.elmer import writer
    g = GmshTools(mesh)
    g.get_gmsh_command = lambda: setattr(g, "gmsh_bin", "gmsh")     # Gmsh is not run here
    g.prepare()
    shutil.copy(HERE / "meshes" / f"{name}.vtk", g.temp_file_mesh)
    g.update_properties()                          # FreeCAD's mesh read back, its groups renamed
    assert mesh.FemMesh.NodeCount == FC[name]["nodes"]
    w = writer.Writer(sol, str(tmp_path))
    w.write_solver_input()
    assert (tmp_path / "case.sif").read_text() == FC[name]["sif"]
    assert (tmp_path / "ELMERSOLVER_STARTINFO").read_text() == FC[name]["startinfo"]
    w.getMesh().FemMesh.write(str(tmp_path / "mesh.unv"))
    assert _sha(tmp_path / "mesh.unv") == FC[name]["files"]["mesh.unv"]
    App.closeDocument(doc.Name)


def _programs():
    path = os.pathsep.join(p for p in (os.environ.get("FREECAD_BIN"), os.environ.get("PATH")) if p)
    return [shutil.which(b, path=path) for b in ("gmsh", "ElmerGrid", "ElmerSolver")], path


def _ranges(grid):
    pd = grid.GetPointData()
    out = {}
    for i in range(pd.GetNumberOfArrays()):
        a = pd.GetArray(i)
        n = a.GetNumberOfComponents()
        v = [a.GetComponent(j, 0) if n == 1 else sum(a.GetComponent(j, k) ** 2 for k in range(n)) ** 0.5
             for j in range(a.GetNumberOfTuples())]
        out[a.GetName()] = [min(v), max(v)]
    return out


@pytest.mark.skipif(not all(_programs()[0]), reason="Gmsh, ElmerGrid and ElmerSolver are not on the PATH")
@pytest.mark.parametrize("name", sorted(CASES))
def test_the_whole_elmer_analysis_is_freecads(name, tmp_path, monkeypatch):
    pytest.importorskip("vtkmodules", reason="VTK's Python (the vtk package) reads Elmer's results, as in FreeCAD")
    monkeypatch.setenv("PATH", _programs()[1])
    App, doc, an, mesh, sol = _setup(name)
    from femmesh.gmshtools import GmshTools
    from femsolver.run import run_fem_solver
    assert not GmshTools(mesh).create_mesh()
    run_fem_solver(sol, str(tmp_path), blocking=True)
    pipe = [r for r in sol.Results if r.isDerivedFrom("Fem::FemPostPipeline")][0]
    assert pipe.Data is not None
    rel = KNOWN.get(name, 1e-9)
    if name not in KNOWN:
        assert mesh.FemMesh.VolumeCount == FC[name]["volumes"]
        for f, sha in FC[name]["files"].items():
            assert _sha(tmp_path / f) == sha, f
        assert pipe.Data.GetNumberOfPoints() == FC[name]["points"]
    ours = _ranges(pipe.Data)
    assert sorted(ours) == sorted(FC[name]["arrays"])
    for k, (lo, hi) in FC[name]["arrays"].items():
        scale = max(abs(lo), abs(hi))
        assert ours[k][0] == pytest.approx(lo, rel=rel, abs=rel * scale), k
        assert ours[k][1] == pytest.approx(hi, rel=rel, abs=rel * scale), k
    App.closeDocument(doc.Name)
