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


# tests/golden/fem's displacement_bar, self_weight and thermomech written as part files: FreeCAD's input and results
_BAR = '''"""bar: a steel bar."""
from cad_agent import feature_fem as Fem
from cad_agent import feature_part as Part

PARAMS = {}
OBJECTS = [Part.Box("Box", length=100, width=10, height=10)]

FEM = [
%s
]


def build(**p):
    return Part.Document(OBJECTS, p)
'''
_STEEL = '    Fem.MaterialSolid("Material", youngs_modulus="210000 MPa", poisson_ratio=0.30, density="7900 kg/m^3"%s),'
_MESH = '    Fem.MeshGmsh("Mesh", "Box", characteristic_length_max="5 mm"),'
_FIX = '    Fem.ConstraintFixed("Fixed", [("Box", "Face1")]),'
MORE = {
    "displacement_bar": "\n".join(['    Fem.SolverCalculiX("CalculiXccxTools"),', _STEEL % "", _FIX,
                                   '    Fem.ConstraintDisplacement("Displacement", [("Box", "Face2")], z_free=False, z_displacement="-0.5 mm"),',
                                   _MESH]),
    "self_weight": "\n".join(['    Fem.SolverCalculiX("CalculiXccxTools"),', _STEEL % "", _FIX,
                              '    Fem.ConstraintSelfWeight("SelfWeight"),', _MESH]),
    "thermomech": "\n".join(['    Fem.SolverCalculiX("CalculiXccxTools", analysis_type="thermomech"),',
                             _STEEL % ', thermal_conductivity="50 W/m/K", thermal_expansion_coefficient="12 um/m/K", specific_heat="500 J/kg/K"',
                             _FIX, '    Fem.ConstraintTemperature("Hot", [("Box", "Face1")], temperature="373 K"),',
                             '    Fem.ConstraintTemperature("Cold", [("Box", "Face2")], temperature="293 K"),',
                             '    Fem.ConstraintInitialTemperature("InitialTemperature", initial_temperature="293 K"),', _MESH]),
}


@pytest.mark.skipif(not (shutil.which("gmsh", path=_path()) and shutil.which("ccx", path=_path())),
                    reason="Gmsh and CalculiX are not on the PATH (or FREECAD_BIN)")
@pytest.mark.parametrize("name", sorted(MORE))
def test_more_analyses_as_part_files_give_freecads(name, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(_BAR % MORE[name])
    work = tmp_path / "work"
    r = Fem.run(p, workdir=work, threads=1)
    want = FC[name]
    assert (r["nodes"], r["volumes"]) == (want["nodes"], want["volumes"])
    assert r["max_displacement_mm"] == pytest.approx(want["max_displacement"], rel=1e-9)
    assert r["max_von_mises_mpa"] == pytest.approx(want["max_von_mises"], rel=1e-9)
    inp = "".join(line for line in open(r["inp"]) if "written on" not in line)
    assert inp.splitlines() == want["inp"].splitlines()
    if "max_temperature" in want:
        assert (r["min_temperature_k"], r["max_temperature_k"]) == pytest.approx((want["min_temperature"], want["max_temperature"]))
        d = json.loads((work / Fem.RESULTS).read_text())
        assert d["range"]["temperature"] == pytest.approx([want["min_temperature"], want["max_temperature"]])


def test_the_new_objects_round_trip_through_the_panels_edits():
    from cad_agent import fem_edit as FE
    src = _BAR % MORE["thermomech"]
    new = FE.apply_src(src, [
        {"op": "add", "kind": "ConstraintHeatflux", "name": "Air", "props": {"references": [["Box", "Face3"]], "film_coef": "10 W/m^2/K", "ambient_temp": "293 K"}},
        {"op": "add", "kind": "ConstraintDisplacement", "name": "Hold", "props": {"references": [["Box", "Face5"]], "y_free": False}},
        {"op": "add", "kind": "ConstraintSelfWeight", "name": "Gravity", "props": {"gravity_direction": [0, -1, 0]}},
    ])
    objs = {o["name"]: o for o in FE.read_src(new)}
    assert objs["Air"]["film_coef"] == "10 W/m^2/K" and objs["Hold"]["y_free"] is False
    assert objs["Gravity"]["gravity_direction"] == (0.0, -1.0, 0.0)
    assert FE.apply_src(new, [{"op": "delete", "name": n} for n in ("Air", "Hold", "Gravity")]) == src


@pytest.mark.skipif(not (shutil.which("gmsh", path=_path()) and shutil.which("ccx", path=_path())),
                    reason="Gmsh and CalculiX are not on the PATH (or FREECAD_BIN)")
def test_a_frequency_analysis_as_a_part_file_gives_freecads_modes(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(_BAR % "\n".join(['    Fem.SolverCalculiX("CalculiXccxTools", analysis_type="frequency", eigenmodes_count=6),',
                                   _STEEL % "", _FIX, _MESH]))
    work = tmp_path / "work"
    r = Fem.run(p, workdir=work, threads=1)
    want = FC["frequency"]
    assert r["frequencies_hz"] == pytest.approx(want["frequencies"], rel=1e-9)
    inp = "".join(line for line in open(r["inp"]) if "written on" not in line)
    assert inp.splitlines() == want["inp"].splitlines()
    d = json.loads((work / Fem.RESULTS).read_text())
    assert [m["frequency"] for m in d["modes"]] == pytest.approx(want["frequencies"], rel=1e-9)
    assert [m["range"]["displacement"][1] for m in d["modes"]] == pytest.approx(want["mode_max_displacements"], rel=1e-9)


# tests/golden/fem_elmer's cantilever and heat written as part files, with Elmer as their solver
FC_ELMER = json.loads((Path(__file__).parent / "golden" / "fem_elmer" / "freecad.json").read_text())
ELMER = {
    "cantilever": "\n".join(['    Fem.SolverElmer("SolverElmer"),',
                             '    Fem.EquationElasticity("Elasticity", "SolverElmer", calculate_stresses=True),',
                             _STEEL % "", _FIX,
                             '    Fem.ConstraintForce("Force", [("Box", "Face2")], force="100 N", direction=("Box", "Edge5"), reversed=True),',
                             _MESH]),
    "heat": "\n".join(['    Fem.SolverElmer("SolverElmer"),', '    Fem.EquationHeat("Heat", "SolverElmer"),',
                       _STEEL % ', thermal_conductivity="50 W/m/K", thermal_expansion_coefficient="12 um/m/K", specific_heat="500 J/kg/K"',
                       '    Fem.ConstraintTemperature("Hot", [("Box", "Face1")], temperature="373 K"),',
                       '    Fem.ConstraintTemperature("Cold", [("Box", "Face2")], temperature="293 K"),', _MESH]),
}


def _elmer():
    return all(shutil.which(b, path=_path()) for b in ("gmsh", "ElmerGrid", "ElmerSolver"))


@pytest.mark.skipif(not _elmer(), reason="Gmsh, ElmerGrid and ElmerSolver are not on the PATH")
@pytest.mark.parametrize("name", sorted(ELMER))
def test_an_elmer_analysis_as_a_part_file_gives_freecads(name, tmp_path, monkeypatch):
    pytest.importorskip("vtkmodules")
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(_BAR % ELMER[name])
    work = tmp_path / "work"
    r = Fem.run(p, workdir=work, threads=1)
    want = FC_ELMER[name]
    assert (r["nodes"], r["volumes"], r["solver"]) == (want["nodes"], want["volumes"], "Elmer")
    assert Path(r["sif"]).read_text() == want["sif"]
    d = json.loads((work / Fem.RESULTS).read_text())
    if "displacement" in want["arrays"]:          # Elmer's SI: metres and pascals; FreeCAD's mm and MPa
        assert r["max_displacement_mm"] == pytest.approx(want["arrays"]["displacement"][1] * 1e3, rel=1e-9)
        assert d["range"]["displacement"][1] == pytest.approx(r["max_displacement_mm"], rel=1e-9)
    if "vonmises" in want["arrays"]:
        assert r["max_von_mises_mpa"] == pytest.approx(want["arrays"]["vonmises"][1] * 1e-6, rel=1e-9)
    if "temperature" in want["arrays"]:
        assert (r["min_temperature_k"], r["max_temperature_k"]) == pytest.approx(tuple(want["arrays"]["temperature"]))
        assert d["range"]["temperature"] == pytest.approx(want["arrays"]["temperature"])


def test_an_equation_needs_its_elmer_solver_first(tmp_path):
    p = tmp_path / "bar.py"
    p.write_text(_BAR % "\n".join(['    Fem.EquationHeat("Heat", "SolverElmer"),', _STEEL % "", _MESH]))
    with pytest.raises(Fem.FemError, match="no SolverElmer"):
        Fem.run(p, workdir=tmp_path / "work")


# tests/golden/fem_mystran's cantilever written as a part file, with Mystran as its solver
FC_MYSTRAN = json.loads((Path(__file__).parent / "golden" / "fem_mystran" / "freecad.json").read_text())
MYSTRAN = "\n".join(['    Fem.SolverMystran("SolverMystran"),', _STEEL % "", _FIX,
                     '    Fem.ConstraintForce("Force", [("Box", "Face2")], force="100 N", direction=("Box", "Edge5"), reversed=True),',
                     _MESH])


@pytest.mark.skipif(not all(shutil.which(b, path=_path()) for b in ("gmsh", "mystran")),
                    reason="Gmsh and Mystran are not on the PATH")
def test_a_mystran_analysis_as_a_part_file_gives_freecads(tmp_path, monkeypatch):
    pytest.importorskip("pyNastran")
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(_BAR % MYSTRAN)
    work = tmp_path / "work"
    r = Fem.run(p, workdir=work, threads=1)
    want = FC_MYSTRAN["cantilever"]
    assert (r["nodes"], r["volumes"], r["solver"]) == (want["nodes"], want["volumes"], "Mystran")
    assert Path(r["bdf"]).read_text() == want["bdf"]
    assert r["max_displacement_mm"] == pytest.approx(want["displacement"][1], rel=1e-9)
    assert r["max_von_mises_mpa"] == pytest.approx(want["von_mises"][1], rel=1e-9)
    d = json.loads((work / Fem.RESULTS).read_text())
    assert d["range"]["displacement"][1] == pytest.approx(r["max_displacement_mm"], rel=1e-9)
    assert 0 < d["range"]["von_mises"][1] <= r["max_von_mises_mpa"]       # each node's mean of its solids'


def test_mystran_takes_only_fixed_and_force(tmp_path, monkeypatch):
    pytest.importorskip("pyNastran")
    if not all(shutil.which(b, path=_path()) for b in ("gmsh", "mystran")):
        pytest.skip("Gmsh and Mystran are not on the PATH")
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(_BAR % "\n".join(['    Fem.SolverMystran("SolverMystran"),', _STEEL % "", _FIX,
                                   '    Fem.ConstraintPressure("Pressure", [("Box", "Face2")], pressure="1 MPa"),',
                                   _MESH]))
    with pytest.raises(Fem.FemError, match="Fixed and Force constraints only"):
        Fem.run(p, workdir=tmp_path / "work", threads=1)


# tests/golden/fem_z88's cantilever written as a part file, with Z88 as its solver
FC_Z88 = json.loads((Path(__file__).parent / "golden" / "fem_z88" / "freecad.json").read_text())
Z88 = "\n".join(['    Fem.SolverZ88("SolverZ88"),', _STEEL % "", _FIX,
                 '    Fem.ConstraintForce("Force", [("Box", "Face2")], force="100 N", direction=("Box", "Edge5"), reversed=True),',
                 _MESH])


@pytest.mark.skipif(not all(shutil.which(b, path=_path()) for b in ("gmsh", "z88r")),
                    reason="Gmsh and z88r are not on the PATH")
def test_a_z88_analysis_as_a_part_file_gives_freecads(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(_BAR % Z88)
    work = tmp_path / "work"
    r = Fem.run(p, workdir=work, threads=1)
    want = FC_Z88["cantilever"]
    assert (r["nodes"], r["volumes"], r["solver"]) == (want["nodes"], want["volumes"], "Z88")
    assert Path(r["z88i1"]).read_text() == want["inputs"]["z88i1.txt"]
    assert r["max_displacement_mm"] == pytest.approx(want["displacement"][1], rel=1e-9)
    assert r["max_nodal_force_n"] == pytest.approx(want["nodal_force"][1], rel=1e-9)
    assert r["max_von_mises_mpa"] is None
    d = json.loads((work / Fem.RESULTS).read_text())
    assert d["range"]["displacement"][1] == pytest.approx(r["max_displacement_mm"], rel=1e-9)
    assert "von_mises" not in d["fields"]


def test_z88_refuses_what_its_writer_does_not_take(tmp_path, monkeypatch):
    if not all(shutil.which(b, path=_path()) for b in ("gmsh", "z88r")):
        pytest.skip("Gmsh and z88r are not on the PATH")
    monkeypatch.setenv("PATH", _path())
    p = tmp_path / "bar.py"
    p.write_text(_BAR % "\n".join(['    Fem.SolverZ88("SolverZ88"),', _STEEL % "", _FIX,
                                   '    Fem.ConstraintSelfWeight("SelfWeight"),', _MESH]))
    with pytest.raises(Fem.FemError, match="Fixed, Displacement, Force and Pressure constraints only"):
        Fem.run(p, workdir=tmp_path / "work", threads=1)
