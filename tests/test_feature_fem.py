"""A part file's FEM analysis (cad_agent/feature_fem.py, `cad fem run`) gives what FreeCAD's FEM workbench gives for
the same analysis: tests/golden/fem's cantilever, written as a part's OBJECTS and FEM. It needs Gmsh and CalculiX on the
PATH (or FREECAD_BIN), as FreeCAD does; without them the run says which program is missing."""
import json
import os
import shutil
from pathlib import Path

import pytest

from cad_agent import feature_fem as Fem

FC = json.loads((Path(__file__).parent / "golden" / "fem" / "freecad.json").read_text())
PART = '''"""bar: a steel cantilever."""
from cad_agent import feature_fem as Fem
from cad_agent import feature_part as Part

PARAMS = {}
OBJECTS = [Part.Box("Box", length=100, width=10, height=10)]

FEM = [
    Fem.SolverCalculiX("CalculiXccxTools"),
    Fem.MaterialSolid("Material", youngs_modulus="210000 MPa", poisson_ratio=0.30, density="7900 kg/m^3"),
    Fem.ConstraintFixed("Fixed", [("Box", "Face1")]),
    Fem.ConstraintForce("Force", [("Box", "Face2")], force="100 N", direction=("Box", "Edge5"), reversed=True),
    Fem.MeshGmsh("Mesh", "Box", characteristic_length_max="5 mm"),
]


def build(**p):
    return Part.Document(OBJECTS, p)
'''


def _path():
    return os.pathsep.join(p for p in (os.environ.get("FREECAD_BIN"), os.environ.get("PATH")) if p)


def test_a_part_without_fem_says_so(tmp_path):
    p = tmp_path / "plain.py"
    p.write_text(PART.split("FEM = [")[0] + "\n\ndef build(**p):\n    return Part.Document(OBJECTS, p)\n")
    with pytest.raises(Fem.FemError, match="no FEM analysis"):
        Fem.load(p)


def test_unknown_properties_are_refused():
    with pytest.raises(Fem.FemError, match="not a property"):
        Fem.ConstraintForce("F", [("Box", "Face2")], forse="1 N")


@pytest.mark.skipif(not (shutil.which("gmsh", path=_path()) and shutil.which("ccx", path=_path())),
                    reason="Gmsh and CalculiX are not on the PATH (or FREECAD_BIN)")
def test_the_cantilever_part_gives_freecads_results(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(PART)
    r = Fem.run(p, workdir=tmp_path / "work", threads=1)
    want = FC["cantilever"]
    assert (r["nodes"], r["volumes"]) == (want["nodes"], want["volumes"])
    assert r["max_displacement_mm"] == pytest.approx(want["max_displacement"], rel=1e-9)
    assert r["max_von_mises_mpa"] == pytest.approx(want["max_von_mises"], rel=1e-9)
    inp = "".join(line for line in open(r["inp"]) if "written on" not in line)
    assert inp.splitlines() == want["inp"].splitlines()
