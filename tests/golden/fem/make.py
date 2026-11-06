"""Writes freecad.json and meshes/<case>.vtk: each case of cases.py run in FreeCAD 26.3 (3160daf1e2b6) with its own
Gmsh and CalculiX (on the PATH; the AppImage's usr/bin has both): the mesh Gmsh made, the CalculiX input FEM wrote (its
"written on" line left out), and the results (node count, the largest displacement and von Mises stress).

    PATH=$FREECAD:$PATH $FREECAD/freecadcmd tests/golden/fem/make.py [CASE]      (from the repository's root)
"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "fem"
sys.path.insert(0, str(HERE))
import FreeCAD as App  # noqa: E402
import ObjectsFem  # noqa: E402
from femmesh.gmshtools import GmshTools  # noqa: E402
from femtools import ccxtools  # noqa: E402

from cases import CASES  # noqa: E402

App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetInt("NumOfThreads", 1)


def inp_text(path):
    return "".join(line for line in open(path) if "written on" not in line)


def run(name):
    doc = App.newDocument(name)
    an, mesh = CASES[name](doc, App, ObjectsFem)
    doc.recompute()
    g = GmshTools(mesh)
    err = g.create_mesh()
    if err:
        raise RuntimeError(err)
    shutil.copy(g.temp_file_mesh, HERE / "meshes" / f"{name}.vtk")
    sol = [o for o in an.Group if o.isDerivedFrom("Fem::FemSolverObjectPython")][0]
    fea = ccxtools.FemToolsCcx(an, sol)
    fea.update_objects()
    fea.setup_working_dir()
    fea.setup_ccx()
    msg = fea.check_prerequisites()
    if msg:
        raise RuntimeError(msg)
    fea.purge_results()
    fea.write_inp_file()
    inp = inp_text(fea.inp_file_name)
    fea.ccx_run()
    fea.load_results()
    res = [o for o in doc.Objects if o.isDerivedFrom("Fem::FemResultObject")][0]
    out = {"nodes": mesh.FemMesh.NodeCount, "volumes": mesh.FemMesh.VolumeCount, "inp": inp,
           "max_displacement": max(res.DisplacementLengths), "max_von_mises": max(res.vonMises)}
    App.closeDocument(doc.Name)
    return out


path = HERE / "freecad.json"
data = json.loads(path.read_text()) if path.exists() else {}
for n in [a for a in sys.argv[1:] if not a.endswith(".py")] or list(CASES):
    data[n] = run(n)
    print(n, data[n]["nodes"], data[n]["max_displacement"], data[n]["max_von_mises"])
path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
