"""Writes freecad.json and meshes/<case>.vtk: each case of cases.py run in FreeCAD 26.3 (3160daf1e2b6) with its own
Gmsh (the AppImage's usr/bin) and Elmer (ElmerGrid and ElmerSolver on the PATH): the mesh Gmsh made, what FEM's Elmer
writer wrote (case.sif, ELMERSOLVER_STARTINFO, the mesh.unv FemMesh.write exports and the mesh files ElmerGrid makes of
it, these by their SHA-256) and the results (each .vtu point array's range).

    PATH=$FREECAD:$PATH $FREECAD/freecadcmd tests/golden/fem_elmer/make.py [CASE]      (from the repository's root)
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "fem_elmer"
sys.path.insert(0, str(HERE))
import FreeCAD as App  # noqa: E402
import ObjectsFem  # noqa: E402
from femmesh.gmshtools import GmshTools  # noqa: E402
from femsolver.run import run_fem_solver  # noqa: E402

from cases import CASES  # noqa: E402

App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetInt("NumOfThreads", 1)
FILES = ["mesh.unv", "mesh.header", "mesh.nodes", "mesh.elements", "mesh.boundary", "mesh.names"]


def arrays(grid):
    """{point array: [its smallest, its largest]}, of a vector array its length."""
    pd = grid.GetPointData()
    out = {}
    for i in range(pd.GetNumberOfArrays()):
        a = pd.GetArray(i)
        n = a.GetNumberOfComponents()
        v = [a.GetComponent(j, 0) if n == 1 else sum(a.GetComponent(j, k) ** 2 for k in range(n)) ** 0.5
             for j in range(a.GetNumberOfTuples())]
        out[a.GetName()] = [min(v), max(v)]
    return out


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
    wd = tempfile.mkdtemp(prefix="elmer_")
    run_fem_solver(sol, wd, blocking=True)
    pipe = [r for r in sol.Results if r.isDerivedFrom("Fem::FemPostPipeline")][0]
    out = {"nodes": mesh.FemMesh.NodeCount, "volumes": mesh.FemMesh.VolumeCount,
           "sif": Path(wd, "case.sif").read_text(), "startinfo": Path(wd, "ELMERSOLVER_STARTINFO").read_text(),
           "files": {f: hashlib.sha256(Path(wd, f).read_bytes()).hexdigest() for f in FILES},
           "points": pipe.Data.GetNumberOfPoints(), "arrays": arrays(pipe.Data)}
    App.closeDocument(doc.Name)
    return out


path = HERE / "freecad.json"
data = json.loads(path.read_text()) if path.exists() else {}
for n in [a for a in sys.argv[1:] if not a.endswith(".py")] or list(CASES):
    data[n] = run(n)
    print(n, data[n]["nodes"], data[n]["arrays"])
path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
