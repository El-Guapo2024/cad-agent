"""FreeCAD's FEM Python (cad_agent/fcfem, vendored unchanged) over the stand-ins does what it does in FreeCAD 26.3
(tests/golden/fem: cases.py, make.py, freecad.json, meshes/).

Without Gmsh or CalculiX, each case's mesh is FreeCAD's own (meshes/<case>.vtk, what its Gmsh wrote), read back as
GmshTools.update_properties reads it, and the CalculiX input FEM writes from it must be FreeCAD's, line for line. With
both programs on the PATH (or FREECAD_BIN naming the folder that has them), the whole analysis runs and the mesh and
the results must be FreeCAD's.
"""
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

HERE = Path(__file__).parent / "golden" / "fem"
_spec = importlib.util.spec_from_file_location("fem_cases", HERE / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES
FC = json.loads((HERE / "freecad.json").read_text())
# Known differences in the whole run (ui/PARITY.md, "FEM"): {case: relative tolerance}. The plate's hole is a boolean of
# the stand-ins' box and cylinder: the same faces, areas and .brep geometry as FreeCAD's, but OCCT's locations are nested
# differently in the file Gmsh reads, so its mesh differs slightly (its CalculiX input from FreeCAD's mesh is exact).
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
    return App, doc, an, mesh


def _inp(fea):
    fea.update_objects()
    fea.setup_working_dir()
    fea.purge_results()
    fea.write_inp_file()
    return "".join(line for line in open(fea.inp_file_name) if "written on" not in line)


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_calculix_input_is_freecads(name, tmp_path):
    App, doc, an, mesh = _setup(name)
    from femmesh.gmshtools import GmshTools
    from femtools import ccxtools
    g = GmshTools(mesh)
    g.get_gmsh_command = lambda: setattr(g, "gmsh_bin", "gmsh")     # Gmsh is not run here
    g.prepare()                                    # the geometry, the geo file and the group data, as before a run
    shutil.copy(HERE / "meshes" / f"{name}.vtk", g.temp_file_mesh)
    g.update_properties()                          # FreeCAD's mesh read back, its groups renamed
    assert mesh.FemMesh.NodeCount == FC[name]["nodes"]
    assert mesh.FemMesh.VolumeCount == FC[name]["volumes"]
    sol = [o for o in an.Group if o.isDerivedFrom("Fem::FemSolverObjectPython")][0]
    fea = ccxtools.FemToolsCcx(an, sol)
    ours = _inp(fea)
    want = FC[name]["inp"]
    assert ours.splitlines() == want.splitlines()
    App.closeDocument(doc.Name)


def _programs():
    path = os.pathsep.join(p for p in (os.environ.get("FREECAD_BIN"), os.environ.get("PATH")) if p)
    return shutil.which("gmsh", path=path), shutil.which("ccx", path=path), path


@pytest.mark.skipif(not all(_programs()[:2]), reason="Gmsh and CalculiX are not on the PATH (or FREECAD_BIN)")
@pytest.mark.parametrize("name", sorted(CASES))
def test_the_whole_analysis_is_freecads(name, monkeypatch):
    monkeypatch.setenv("PATH", _programs()[2])
    App, doc, an, mesh = _setup(name)
    from femmesh.gmshtools import GmshTools
    from femtools import ccxtools
    assert not GmshTools(mesh).create_mesh()
    assert mesh.FemMesh.NodeCount == FC[name]["nodes"]
    sol = [o for o in an.Group if o.isDerivedFrom("Fem::FemSolverObjectPython")][0]
    fea = ccxtools.FemToolsCcx(an, sol)
    fea.update_objects()
    fea.setup_working_dir()
    fea.setup_ccx()
    assert not fea.check_prerequisites()
    fea.purge_results()
    fea.write_inp_file()
    fea.ccx_run()
    fea.load_results()
    res = [o for o in doc.Objects if o.isDerivedFrom("Fem::FemResultObject")][0]
    rel = KNOWN.get(name, 1e-9)
    if name not in KNOWN:
        assert mesh.FemMesh.VolumeCount == FC[name]["volumes"]
    assert max(res.DisplacementLengths) == pytest.approx(FC[name]["max_displacement"], rel=rel)
    assert max(res.vonMises) == pytest.approx(FC[name]["max_von_mises"], rel=rel)
    if "frequencies" in FC[name]:                       # a frequency analysis: each mode's frequency and shape
        modes = [o for o in doc.Objects if o.isDerivedFrom("Fem::FemResultObject")]
        assert [o.EigenmodeFrequency for o in modes] == pytest.approx(FC[name]["frequencies"], rel=rel)
        assert [max(o.DisplacementLengths) for o in modes] == pytest.approx(FC[name]["mode_max_displacements"], rel=rel)
    if "max_temperature" in FC[name]:                   # a thermo-mechanical analysis: its temperature field too
        assert max(res.Temperature) == pytest.approx(FC[name]["max_temperature"], rel=rel)
        assert min(res.Temperature) == pytest.approx(FC[name]["min_temperature"], rel=rel)
    App.closeDocument(doc.Name)
