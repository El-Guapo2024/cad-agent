"""Writes freecad.json and meshes/<case>.vtk: each case of cases.py run in FreeCAD 26.3 (3160daf1e2b6) with its own
Gmsh (the AppImage's usr/bin) and Z88OS's z88r (on the PATH), as the FEM workbench's Run runs it
(femsolver.run.run_fem_solver: femsolver/z88/z88tools.py's Z88Tools): the mesh Gmsh made, the input files FEM's Z88
writer wrote, the files in the folder after the run, and the result it read back (the solver's FemPostPipeline: each
node's displacement and nodal force, by their lengths' ranges).

    PATH=$FREECAD:$PATH $FREECAD/freecadcmd tests/golden/fem_z88/make.py [CASE]      (from the repository's root)
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "fem_z88"
sys.path.insert(0, str(HERE))
import FreeCAD as App  # noqa: E402
import ObjectsFem  # noqa: E402
from femmesh.gmshtools import GmshTools  # noqa: E402
from femsolver.run import run_fem_solver  # noqa: E402
from vtkmodules.util import numpy_support as vtk_np  # noqa: E402

from cases import CASES  # noqa: E402

App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetInt("NumOfThreads", 1)
INPUTS = ["Material.txt", "z88.dyn", "z88elp.txt", "z88i1.txt", "z88i2.txt", "z88i5.txt", "z88int.txt", "z88man.txt",
          "z88mat.txt"]


def lengths(grid, name):
    a = grid.GetPointData().GetArray(name)
    v = vtk_np.vtk_to_numpy(a).reshape(a.GetNumberOfTuples(), -1)
    n = np.linalg.norm(v, axis=1)
    return [float(n.min()), float(n.max())]


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
    wd = tempfile.mkdtemp(prefix="z88_")
    run_fem_solver(sol, wd, blocking=True)
    grid = [r for r in sol.Results if r.isDerivedFrom("Fem::FemPostPipeline")][0].Data
    pd = grid.GetPointData()
    out = {"nodes": mesh.FemMesh.NodeCount, "volumes": mesh.FemMesh.VolumeCount,
           "inputs": {f: Path(wd, f).read_text() for f in INPUTS},
           "outputs": sorted(os.listdir(wd)),
           "points": grid.GetNumberOfPoints(), "cells": grid.GetNumberOfCells(),
           "arrays": [pd.GetArrayName(i) for i in range(pd.GetNumberOfArrays())],
           "displacement": lengths(grid, "Displacement"), "nodal_force": lengths(grid, "Nodal Force")}
    App.closeDocument(doc.Name)
    return out


path = HERE / "freecad.json"
data = json.loads(path.read_text()) if path.exists() else {}
for n in [a for a in sys.argv[1:] if not a.endswith(".py")] or list(CASES):
    data[n] = run(n)
    print(n, data[n]["nodes"], data[n]["displacement"], data[n]["nodal_force"])
path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
