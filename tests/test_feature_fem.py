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


def test_panel_edits_keep_the_file_and_can_be_run_back(tmp_path):
    from cad_agent import fem_edit as FE
    src = PART.replace('Fem.ConstraintFixed("Fixed", [("Box", "Face1")]),',
                       'Fem.ConstraintFixed("Fixed", [("Box", "Face1")]),  # the wall')
    new = FE.apply_src(src, [
        {"op": "add", "kind": "ConstraintPressure", "name": "Load", "props": {"references": [["Box", "Face6"]], "pressure": "2 MPa"}},
        {"op": "set", "name": "Force", "props": {"force": "250 N"}},
    ])
    assert "# the wall" in new
    assert 'Fem.ConstraintPressure("Load", [("Box", "Face6")], pressure="2 MPa"),' in new
    objs = {o["name"]: o for o in FE.read_src(new)}
    assert objs["Force"]["force"] == "250 N" and objs["Force"]["direction"] == ("Box", "Edge5") and objs["Force"]["reversed"] is True
    gone = FE.apply_src(new, [{"op": "delete", "name": "Load"}, {"op": "set", "name": "Force", "props": {"force": "100 N"}}])
    assert gone == src
    p = tmp_path / "bar.py"
    p.write_text(new)
    assert len(Fem.load(p)[0]) == 6


def test_the_first_panel_makes_the_list_and_its_import():
    from cad_agent import fem_edit as FE
    src = PART.split("FEM = [")[0].replace("from cad_agent import feature_fem as Fem\n", "") + "def build(**p):\n    return Part.Document(OBJECTS, p)\n"
    new = FE.apply_src(src, [{"op": "add", "kind": "SolverCalculiX", "name": "Solver"}])
    assert "from cad_agent import feature_fem as Fem\n" in new and new.index("FEM = [") < new.index("def build")
    assert [o["name"] for o in FE.read_src(new)] == ["Solver"]


@pytest.mark.parametrize("op, why", [
    ({"op": "add", "kind": "Nope", "name": "X"}, "is not one of"),
    ({"op": "add", "kind": "ConstraintFixed", "name": "Box"}, "already has an object"),
    ({"op": "add", "kind": "ConstraintFixed", "name": "Fixed"}, "already has an object"),
    ({"op": "add", "kind": "ConstraintFixed", "name": "bad name"}, "is not a name"),
    ({"op": "set", "name": "Fixed", "props": {"forse": "1 N"}}, "not a property"),
    ({"op": "set", "name": "Fixed", "props": {"references": [["Box"]]}}, "pair"),
    ({"op": "delete", "name": "Ghost"}, "no object"),
    ({"op": "rename", "name": "Fixed"}, "not an edit"),
])
def test_a_bad_edit_is_refused(op, why):
    from cad_agent import fem_edit as FE
    with pytest.raises(Fem.FemError, match=why):
        FE.apply_src(PART, [op])


@pytest.mark.skipif(not (shutil.which("gmsh", path=_path()) and shutil.which("ccx", path=_path())),
                    reason="Gmsh and CalculiX are not on the PATH (or FREECAD_BIN)")
def test_the_results_file_holds_the_runs_values(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(PART)
    work = tmp_path / "work"
    r = Fem.run(p, workdir=work, threads=1)
    d = json.loads((work / Fem.RESULTS).read_text())
    assert d["range"]["displacement"][1] == pytest.approx(r["max_displacement_mm"], rel=1e-9)
    assert d["range"]["von_mises"][1] == pytest.approx(r["max_von_mises_mpa"], rel=1e-9)
    n = len(d["points"]) // 3
    assert n and len(d["triangles"]) % 3 == 0 and max(d["triangles"]) == n - 1
    assert all(len(v) == n for v in d["fields"].values())
    # the outside of a closed solid: every edge of the triangles is shared by exactly two
    from collections import Counter
    t = d["triangles"]
    edges = Counter(tuple(sorted(e)) for i in range(0, len(t), 3) for e in ((t[i], t[i + 1]), (t[i + 1], t[i + 2]), (t[i + 2], t[i])))
    assert set(edges.values()) == {2}
