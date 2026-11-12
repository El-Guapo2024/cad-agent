"""Writes freecad.json and meshes/<case>.vtk: each case of cases.py run in FreeCAD 26.3 (3160daf1e2b6) with its own
Gmsh (the AppImage's usr/bin), pyNastran 1.4.1 and Mystran (on the PATH): the mesh Gmsh made, what FEM's Mystran writer
wrote (the .bdf and the pyNastran script, its folder written <dir>) and Mystran's results (cad_agent/mystran_f06.py reading its
.F06: each node's displacement and each element's von Mises stress, by their ranges).

FreeCAD's own numpy (2.5) no longer has numpy.in1d, which pyNastran 1.4.1 calls: it is numpy.isin here, as numpy's
deprecation of it says.

    PYNASTRAN_PATH=<pyNastran's folder> PATH=$FREECAD:$PATH $FREECAD/freecadcmd tests/golden/fem_mystran/make.py [CASE]
                                                                                     (from the repository's root)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy

sys.path[:0] = [p for p in os.environ.get("PYNASTRAN_PATH", "").split(os.pathsep) if p]
if not hasattr(numpy, "in1d"):
    numpy.in1d = numpy.isin

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "fem_mystran"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "cad_agent"))
import FreeCAD as App  # noqa: E402
import ObjectsFem  # noqa: E402
from femmesh.gmshtools import GmshTools  # noqa: E402
from femmesh import meshsetsgetter  # noqa: E402
from femsolver.mystran import writer  # noqa: E402
from femtools import membertools  # noqa: E402

from cases import CASES  # noqa: E402
from mystran_f06 import read_f06  # noqa: E402

App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetInt("NumOfThreads", 1)


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
    wd = tempfile.mkdtemp(prefix="mystran_")
    # femsolver/mystran/tasks.py's Prepare and Solve; its `get_mesh_to_solve(...)[0]` fails in 26.3 (the function
    # returns the mesh itself now), so FreeCAD's run_fem_solver never gets to Mystran: the same lines, without the [0].
    m = membertools.get_mesh_to_solve(an)
    g2 = meshsetsgetter.MeshSetsGetter(an, sol, m, membertools.AnalysisMember(an))
    g2.get_mesh_sets()
    path = writer.FemInputWriterMystran(an, sol, m, g2.member, wd).write_solver_input()
    subprocess.run(["mystran", os.path.basename(path)], cwd=wd, capture_output=True, check=True)
    base = mesh.Name
    res = read_f06(Path(wd, base + ".F06").read_text(errors="replace"))
    out = {"nodes": mesh.FemMesh.NodeCount, "volumes": mesh.FemMesh.VolumeCount,
           "bdf": Path(wd, base + ".bdf").read_text(), "py": Path(wd, base + ".py").read_text().replace(wd, "<dir>"),
           "outputs": sorted(os.listdir(wd)),
           "grids": len(res["displacement"]), "elements": len(res["von_mises"]),
           "displacement": [min(res["displacement_length"].values()), max(res["displacement_length"].values())],
           "von_mises": [min(res["von_mises"].values()), max(res["von_mises"].values())]}
    App.closeDocument(doc.Name)
    return out


path = HERE / "freecad.json"
data = json.loads(path.read_text()) if path.exists() else {}
for n in [a for a in sys.argv[1:] if not a.endswith(".py")] or list(CASES):
    data[n] = run(n)
    print(n, data[n]["nodes"], data[n]["displacement"], data[n]["von_mises"])
path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
