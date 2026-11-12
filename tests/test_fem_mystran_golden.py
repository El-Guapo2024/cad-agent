"""FreeCAD's Mystran solver (cad_agent/fcfem's femsolver/mystran, vendored unchanged) over the stand-ins does what it does
in FreeCAD 26.3 (tests/golden/fem_mystran: cases.py, make.py, freecad.json, meshes/).

With pyNastran (which FEM's Mystran writer writes with, as in FreeCAD) but without Gmsh or Mystran, each case's mesh is
FreeCAD's own (meshes/<case>.vtk), read back as GmshTools reads it, and the .bdf and pyNastran script the writer writes
from it must be FreeCAD's, byte for byte. With Gmsh and Mystran on the PATH (or FREECAD_BIN naming the folder that has
Gmsh), the whole analysis runs and Mystran's results must be those it gave FreeCAD's input; pyNastran's reading of the
.OP2 must agree with cad_agent/mystran_f06's reading of the .F06.
"""
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cad_agent.mystran_f06 import read_f06

pytest.importorskip("pyNastran", reason="FEM's Mystran writer writes with pyNastran, as in FreeCAD")

HERE = Path(__file__).parent / "golden" / "fem_mystran"
_spec = importlib.util.spec_from_file_location("fem_mystran_cases", HERE / "cases.py")
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


def _write(an, sol, wd):
    """make.py's lines: femsolver/mystran/tasks.py's Prepare without its [0] (which fails in FreeCAD 26.3)."""
    from femmesh import meshsetsgetter
    from femsolver.mystran import writer
    from femtools import membertools
    m = membertools.get_mesh_to_solve(an)
    g = meshsetsgetter.MeshSetsGetter(an, sol, m, membertools.AnalysisMember(an))
    g.get_mesh_sets()
    return writer.FemInputWriterMystran(an, sol, m, g.member, str(wd)).write_solver_input()


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_mystran_input_is_freecads(name, tmp_path):
    App, doc, an, mesh, sol = _setup(name)
    from femmesh.gmshtools import GmshTools
    g = GmshTools(mesh)
    g.get_gmsh_command = lambda: setattr(g, "gmsh_bin", "gmsh")     # Gmsh is not run here
    g.prepare()
    shutil.copy(HERE / "meshes" / f"{name}.vtk", g.temp_file_mesh)
    g.update_properties()                          # FreeCAD's mesh read back, its groups renamed
    assert mesh.FemMesh.NodeCount == FC[name]["nodes"]
    _write(an, sol, tmp_path)
    assert (tmp_path / "Mesh.bdf").read_text() == FC[name]["bdf"]
    assert (tmp_path / "Mesh.py").read_text().replace(str(tmp_path), "<dir>") == FC[name]["py"]
    App.closeDocument(doc.Name)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_freecads_mystran_run_fails_before_mystran_as_in_freecad(tmp_path):
    """FreeCAD 26.3's run_fem_solver with a SolverMystran stops in Prepare (`get_mesh_to_solve(...)[0]` of the mesh
    object): it does here too; feature_fem runs Mystran with make.py's lines instead."""
    App, doc, an, mesh, sol = _setup("cantilever")
    from femmesh.gmshtools import GmshTools
    g = GmshTools(mesh)
    g.get_gmsh_command = lambda: setattr(g, "gmsh_bin", "gmsh")
    g.prepare()
    shutil.copy(HERE / "meshes" / "cantilever.vtk", g.temp_file_mesh)
    g.update_properties()
    import femsolver.run
    machine = sol.Proxy.createMachine(sol, str(tmp_path), True)    # FreeCAD's femtest/app/test_solver_mystran.py
    machine.target = femsolver.run.PREPARE
    machine.start()
    machine.join()
    assert machine.failed and not (tmp_path / "Mesh.bdf").exists()
    App.closeDocument(doc.Name)


def _programs():
    path = os.pathsep.join(p for p in (os.environ.get("FREECAD_BIN"), os.environ.get("PATH")) if p)
    return [shutil.which(b, path=path) for b in ("gmsh", "mystran")], path


@pytest.mark.skipif(not all(_programs()[0]), reason="Gmsh and Mystran are not on the PATH")
@pytest.mark.parametrize("name", sorted(CASES))
def test_the_whole_mystran_analysis_is_freecads(name, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", _programs()[1])
    App, doc, an, mesh, sol = _setup(name)
    from femmesh.gmshtools import GmshTools
    assert not GmshTools(mesh).create_mesh()
    path = _write(an, sol, tmp_path)
    subprocess.run(["mystran", os.path.basename(path)], cwd=tmp_path, capture_output=True, check=True)
    assert sorted(os.listdir(tmp_path)) == FC[name]["outputs"]
    res = read_f06((tmp_path / "Mesh.F06").read_text(errors="replace"))
    rel = KNOWN.get(name, 1e-9)
    if name not in KNOWN:
        assert (tmp_path / "Mesh.bdf").read_text() == FC[name]["bdf"]
        assert (len(res["displacement"]), len(res["von_mises"])) == (FC[name]["grids"], FC[name]["elements"])
    for key, field in (("displacement", "displacement_length"), ("von_mises", "von_mises")):
        lo, hi = FC[name][key]
        assert min(res[field].values()) == pytest.approx(lo, rel=rel, abs=rel * hi), key
        assert max(res[field].values()) == pytest.approx(hi, rel=rel, abs=rel * hi), key

    from pyNastran.op2.op2 import read_op2
    op2 = read_op2(str(tmp_path / "Mesh.OP2"), debug=None)
    d = op2.displacements[1]
    for (grid, _), t in zip(d.node_gridtype.tolist(), d.data[0, :, :3].tolist()):
        assert res["displacement"][grid] == pytest.approx(t, rel=1e-6, abs=1e-6 * FC[name]["displacement"][1])
    s = op2.op2_results.stress.ctetra_stress[1]
    for (eid, nid), row in zip(s.element_node.tolist(), s.data[0].tolist()):
        if nid == 0:
            assert res["von_mises"][eid] == pytest.approx(row[9], rel=1e-6)
    App.closeDocument(doc.Name)
