"""PartDesign's last commands in a FEATURES list are what FreeCAD's PartDesign makes: the Involute Gear and the
Sprocket (cad_agent/feature_gear.py), ...

tests/golden/pdlast/cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote freecad.json. Here the same lines go through feature.evaluate and Body: the Body's solid,
and every object's shape, must be FreeCAD's. Each feature also goes through the part file (feature_edit), as every
feature_kw.KwFeature does.
"""
import importlib.util
import json
import math
from contextlib import contextmanager
from pathlib import Path

import pytest
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX

from cad_agent import feature
from cad_agent import feature_boolean as FB
from cad_agent import feature_edit as E
from cad_agent.feature import Body

GOLDEN = Path(__file__).parent / "golden" / "pdlast"
_spec = importlib.util.spec_from_file_location("pdlast_cases", GOLDEN / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES
FREECAD = json.loads((GOLDEN / "freecad.json").read_text())["cases"]


def _r(v):
    return round(v, 9) + 0.0


def _box(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    return [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()]


def _measure(shape) -> dict:
    out = {"solids": feature._count(shape, TopAbs_SOLID), "faces": feature._count(shape, TopAbs_FACE),
           "edges": feature._count(shape, TopAbs_EDGE), "vertices": feature._count(shape, TopAbs_VERTEX),
           "bbox": _box(shape)}
    if out["solids"]:
        v, a = GProp_GProps(), GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, v)
        BRepGProp.SurfaceProperties_s(shape, a)
        c = v.CentreOfMass()
        out.update(volume=v.Mass(), area=a.Mass(), center=[c.X(), c.Y(), c.Z()])
    elif out["faces"]:
        a = GProp_GProps()
        BRepGProp.SurfaceProperties_s(shape, a)
        out.update(area=a.Mass())
    else:
        g = GProp_GProps()
        BRepGProp.LinearProperties_s(shape, g)
        out.update(length=g.Mass())
    return out


def _same(got, want, what):
    size = max(math.dist(want["bbox"][:3], want["bbox"][3:]), 1.0)
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size), f"{what}: bbox"
    for k in ("volume", "area", "length"):
        if k in want:
            assert got[k] == pytest.approx(want[k], rel=1e-7, abs=1e-7), f"{what}: {k}"
    if "center" in want:
        assert got["center"] == pytest.approx(want["center"], abs=1e-6 * size), f"{what}: centre"


@contextmanager
def _others(case):
    """The case's other Bodies (a Boolean's tools, a Clone's source) as feature_boolean finds them: by name, each built
    from its own FEATURES (the part modules of a project, here)."""
    def body(oc):
        def shapes():
            ev = feature.evaluate(oc["features"], oc.get("params"))
            return ev["Tip"], {k: v for k, v in ev.items() if not k.startswith("_") and v is not None}
        return shapes
    token = FB.OTHERS.set({n: body(oc) for n, oc in (case.get("others") or {}).items()})
    try:
        yield
    finally:
        FB.OTHERS.reset(token)


def _evaluate(name):
    case = CASES[name]
    with _others(case):
        return feature.evaluate(case["features"], case.get("params"))


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/pdlast/make.py in freecadcmd"
    assert not [n for n, g in FREECAD.items() if "error" in g]


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_body_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    with _others(case):
        part = Body(case["features"], case.get("params"))
    got = _measure(part.wrapped)
    w = want["body"]
    _same(got, w, "body")
    assert (got["solids"], got["faces"], got["edges"], got["vertices"]) == \
        (w["solids"], w["faces"], w["edges"], w["vertices"])


@pytest.mark.parametrize("name", sorted(_cases.GEAR))
def test_gear_wire_as_freecad(name):
    """The gear's (or sprocket's) Shape: FreeCAD's wire, edge for edge, where its Placement puts it."""
    case, want = CASES[name], FREECAD[name]
    ev = _evaluate(name)
    ctx = ev["_attach"]
    for f in case["features"]:
        if not getattr(f, "is_part2d", False):
            continue
        w = want["objects"][f.name]
        assert w["type"] == "Part::Part2DObjectPython"
        assert ctx.kinds[f.name] == "sketch"
        got = _measure(ctx.sketch_shape(f.name))
        ws = w["shape"]
        assert ws["type"] == "Wire" and ws["closed"]
        assert (got["edges"], got["vertices"]) == (ws["edges"], ws["edges"] * 2)   # loose edges here, a wire there
        _same(got, ws, f"{f.name} wire")
        pl = ctx.placements[f.name]
        assert [_r(c) for c in (*pl.pos, *pl.rot.ypr())] == pytest.approx(w["placement"], abs=1e-9)


@pytest.mark.parametrize("name", sorted(_cases.DEFEATURING))
def test_defeaturing_as_freecad(name):
    """The Defeaturing's own Shape is the Body's (it is the Tip), with FreeCAD's faces in FreeCAD's order."""
    case, want = CASES[name], FREECAD[name]
    ev = _evaluate(name)
    w = want["objects"]["Defeaturing"]
    assert w["type"] == "PartDesign::Defeaturing" and w["valid"]
    got = _measure(ev["Defeaturing"])
    _same(got, w["shape"], "Defeaturing")
    assert (got["faces"], got["edges"]) == (w["shape"]["faces"], w["shape"]["edges"])


TYPES = {"COMPOUND": "Compound", "SOLID": "Solid", "SHELL": "Shell", "FACE": "Face", "WIRE": "Wire", "EDGE": "Edge",
         "VERTEX": "Vertex", "COMPSOLID": "CompSolid"}


@pytest.mark.parametrize("name", sorted(_cases.SUBBINDER))
def test_subshapebinder_as_freecad(name):
    """The binder's Shape (its type, counts, size, where its Placement puts it) and Support are FreeCAD's."""
    case, want = CASES[name], FREECAD[name]
    ev = _evaluate(name)
    ctx = ev["_attach"]
    for f in case["features"]:
        if type(f).__name__ != "SubShapeBinder":
            continue
        w = want["objects"][f.name]
        assert w["type"] == "PartDesign::SubShapeBinder" and w["valid"]
        assert ctx.kinds[f.name] == "binder"
        shape = ctx.shapes[f.name]
        ws = w["shape"]
        if ws.get("null"):
            assert shape is None or shape.IsNull()
            continue
        got = _measure(shape)
        assert TYPES[shape.ShapeType().name.replace("TopAbs_", "")] == ws["type"]
        assert (got["solids"], got["faces"], got["edges"], got["vertices"]) == \
            (ws["solids"], ws["faces"], ws["edges"], ws["vertices"])
        _same(got, ws, f"{f.name}")
        pl = ctx.placements[f.name]
        assert [_r(c) for c in (*pl.pos, *pl.rot.ypr())] == pytest.approx(w["placement"], abs=1e-9)
        assert [_r(c) for c in (*pl.pos, *pl.rot.ypr())] == pytest.approx(ws["placement"], abs=1e-9)


@pytest.mark.parametrize("name", sorted(CASES))
def test_tip_as_freecad(name):
    """The Tip our part file reads for these FEATURES (no TIP =): a gear is not a solid feature, as a sketch is not."""
    case, want = CASES[name], FREECAD[name]
    src = "FEATURES = [\n" + "".join(
        f"    {type(f).__name__}({f.name!r}" + (f", {f.profile!r}" if hasattr(f, "profile") else "") + "),\n"
        for f in case["features"]) + "]\n"
    assert E.read_src(src)["tip"] == want["tip"]


NEW_BODY = """from cad_agent.feature import Body

PARAMS = {"teeth": 13.0}

FEATURES = [
]
TIP = None


def build(**p):
    return Body(FEATURES, p, tip=TIP)
"""


def _build(src, tmp_path, name="part"):
    path = tmp_path / f"{name}.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location(f"pdlast_{name}_{id(path)}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(**mod.PARAMS)


def test_gear_part_file_round_trip(tmp_path):
    src = E.apply_src(NEW_BODY, [
        {"op": "add", "feature": {"name": "InvoluteGear", "type": "Part::InvoluteGear"}},
        {"op": "add", "feature": {"name": "Pad", "type": "PartDesign::Pad", "profile": "InvoluteGear", "length": 4.0}},
        {"op": "set", "name": "InvoluteGear", "props": {"number_of_teeth": "teeth", "modules": 1.5}},
        {"op": "add", "feature": {"name": "Sprocket", "type": "Part::Sprocket", "sprocket_reference": "ANSI 40",
                                  "pitch": 12.7, "attachment_support": [["XY_Plane", ""]], "map_mode": "FlatFace",
                                  "attachment_offset": [[0.0, 0.0, 4.0], [0.0, 0.0, 0.0]]}},
    ])
    assert 'InvoluteGear("InvoluteGear", number_of_teeth="teeth", modules=1.5)' in src
    d = E.read_src(src)
    gear = next(f for f in d["features"] if f["name"] == "InvoluteGear")
    assert gear["type"] == "Part::InvoluteGear" and gear["pressure_angle"] == 20.0 and gear["high_precision"] is True
    assert d["tip"] == "Pad"                         # neither the gear nor the sprocket is a solid feature
    part = _build(src, tmp_path)
    want = Body([feature.InvoluteGear("InvoluteGear", number_of_teeth=13, modules=1.5),
                 feature.Pad("Pad", "InvoluteGear", length=4.0)])
    assert part.volume == pytest.approx(want.volume, rel=1e-12)
    # a gear something uses is not deleted; a Pad's profile must be a sketch or a gear before it
    with pytest.raises(E.FeatureEditError, match="Pad"):
        E.apply_src(src, [{"op": "delete", "name": "InvoluteGear"}])
    with pytest.raises(E.FeatureEditError, match="not one of"):
        E.apply_src(src, [{"op": "set", "name": "Sprocket", "props": {"sprocket_reference": "ANSI 99"}}])


PLATE = Path(__file__).parent / "fixtures" / "feature_plate" / "parts" / "plate.py"


def test_defeaturing_and_subshapebinder_part_file_round_trip(tmp_path):
    """Both go through the part file as every dress-up and binder does: written with only what is not FreeCAD's
    default, read back with every property, refused where FreeCAD's Body would not build them, renamed with what they
    link."""
    src = E.apply_src(PLATE.read_text(), [
        {"op": "add", "feature": {"name": "Defeaturing", "type": "PartDesign::Defeaturing",
                                  "base": ["TiePocket", ["Face1"]]}},
        {"op": "add", "feature": {"name": "Binder", "type": "PartDesign::SubShapeBinder",
                                  "support": [["Defeaturing", "Face6"], ["Pad", "Face1"]], "offset": 1.0}},
        {"op": "tip", "name": "Defeaturing"},
    ])
    assert 'Defeaturing("Defeaturing", ("TiePocket", ["Face1"]))' in src
    assert 'SubShapeBinder("Binder", support=[("Defeaturing", "Face6"), ("Pad", "Face1")], offset=1.0)' in src
    d = E.read_src(src)
    assert d["tip"] == "Defeaturing"
    b = next(f for f in d["features"] if f["name"] == "Binder")
    assert b["make_face"] is True and b["bind_mode"] == "Synchronized" and b["refine"] is True
    _build(src, tmp_path)                            # it builds
    with pytest.raises(E.FeatureEditError, match="Binder"):
        E.apply_src(src, [{"op": "delete", "name": "Defeaturing"}])     # the binder uses it
    with pytest.raises(E.FeatureEditError, match="Synchronized"):
        E.apply_src(src, [{"op": "set", "name": "Binder", "props": {"bind_mode": "Frozen"}}])
    src = E.apply_src(src, [{"op": "rename", "name": "Pad", "to": "Plate"}])
    assert '("Plate", "Face1")' in src


@pytest.mark.parametrize("name", sorted(_cases.BOOLEAN))
def test_boolean_and_clone_objects_as_freecad(name):
    """The Boolean's or Clone's own Shape is FreeCAD's (the Body's, as it is the Tip there and here)."""
    case, want = CASES[name], FREECAD[name]
    ev = _evaluate(name)
    for f in case["features"]:
        if type(f).__name__ not in ("Boolean", "Clone"):
            continue
        w = want["objects"][f.name]
        assert w["type"] == f.TYPE_ID and w["valid"]
        got = _measure(ev[f.name])
        _same(got, w["shape"], f.name)
        assert (got["faces"], got["edges"]) == (w["shape"]["faces"], w["shape"]["edges"])


PLATE_SRC = '''from cad_agent.feature import Body, Circle, LineSegment, Pad, Sketch, Boolean, Clone

PARAMS = {"w": 40.0}

FEATURES = [
    Sketch("Sketch", support="XY", geometry=[LineSegment((0.0, 0.0), (40.0, 0.0)), LineSegment((40.0, 0.0), (40.0, 20.0)),
                                             LineSegment((40.0, 20.0), (0.0, 20.0)), LineSegment((0.0, 20.0), (0.0, 0.0))]),
    Pad("Pad", "Sketch", length=5.0),
%s]


def build(**p):
    return Body(FEATURES, p)
'''
ROD_SRC = '''from cad_agent.feature import Body, Boolean, Circle, Pad, Sketch, Clone

PARAMS = {}

FEATURES = [
    Sketch("Sketch", support="XY", geometry=[Circle((20.0, 10.0), 4.0)], attachment_offset=(0, 0, -3)),
    Pad("Pad", "Sketch", length=12.0),
%s]


def build(**p):
    return Body(FEATURES, p)
'''


def _project(tmp_path, body_extra="", rod_extra=""):
    parts = tmp_path / "proj" / "parts"
    parts.mkdir(parents=True)
    (parts / "Body.py").write_text(PLATE_SRC % body_extra)
    (parts / "Body001.py").write_text(ROD_SRC % rod_extra)
    return parts


def _build_file(path):
    from cad_agent import state
    mod = state._load_module(path)
    return mod.build(**mod.PARAMS)


def test_a_boolean_takes_another_part_of_the_project(tmp_path):
    """In a part file the tool is another part module of the project, by its name, built from its own source."""
    parts = _project(tmp_path, '    Boolean("Boolean", ["Body001"], type="Cut"),\n')
    assert _build_file(parts / "Body.py").volume == pytest.approx(FREECAD["bool_cut"]["body"]["volume"], rel=1e-9)
    # the tool's own edit is what the next build takes
    (parts / "Body001.py").write_text(ROD_SRC.replace("4.0)]", "2.0)]") % "")
    assert _build_file(parts / "Body.py").volume == pytest.approx(4000 - math.pi * 4 * 5, rel=1e-9)


def test_a_clone_is_a_new_part_whose_base_is_another(tmp_path):
    parts = _project(tmp_path)
    (parts / "Body002.py").write_text(ROD_SRC.replace(
        '    Sketch("Sketch", support="XY", geometry=[Circle((20.0, 10.0), 4.0)], attachment_offset=(0, 0, -3)),\n'
        '    Pad("Pad", "Sketch", length=12.0),\n', "") % '    Clone("Clone", "Body"),\n')
    assert _build_file(parts / "Body002.py").volume == pytest.approx(4000.0, rel=1e-12)
    d = E.read(parts / "Body002.py")
    assert d["tip"] == "Clone" and d["features"][0]["type"] == "PartDesign::FeatureBase"
    assert d["features"][0]["base_feature"] == "Body"


def test_a_link_cycle_and_a_missing_body_are_refused(tmp_path):
    parts = _project(tmp_path, '    Boolean("Boolean", ["Body001"]),\n', '    Boolean("Boolean", ["Body"]),\n')
    with pytest.raises(feature.FeatureError, match="Link cycle: Body001 -> Body -> Body001|Link cycle"):
        _build_file(parts / "Body.py")
    (parts / "Body.py").write_text(PLATE_SRC % '    Boolean("Boolean", ["Body009"]),\n')
    with pytest.raises(feature.FeatureError, match="no Body 'Body009'"):
        _build_file(parts / "Body.py")


def test_boolean_part_file_round_trip(tmp_path):
    parts = _project(tmp_path)
    src = E.apply_src((parts / "Body.py").read_text(), [
        {"op": "add", "feature": {"name": "Boolean", "type": "PartDesign::Boolean", "group": ["Body001"], "type1": "Cut"}}])
    assert 'Boolean("Boolean", ["Body001"], type="Cut")' in src
    d = E.read_src(src)
    b = next(f for f in d["features"] if f["name"] == "Boolean")
    assert b["type"] == "PartDesign::Boolean" and b["type1"] == "Cut" and b["group"] == ["Body001"] and b["refine"] is True
    assert d["tip"] == "Boolean"
    src = E.apply_src(src, [{"op": "set", "name": "Boolean", "props": {"type1": "Common"}}])
    assert 'Boolean("Boolean", ["Body001"], type="Common")' in src
    with pytest.raises(E.FeatureEditError, match="not one of"):
        E.apply_src(src, [{"op": "set", "name": "Boolean", "props": {"type1": "Section"}}])


from test_cli import run  # noqa: E402
from test_workbench import demo  # noqa: E402,F401 (the project fixture)


def test_cad_feature_clone(demo, capsys):
    """`cad feature clone demo plate`: a new Body (Body, then Body001, ...) whose Clone copies plate; one undo step,
    "Create Clone", which undo takes back."""
    from cad_agent import cli
    from cad_agent import undo as un
    code, data = run(capsys, "feature", "clone", "demo", "plate")
    assert code == cli.OK and data["part"] == "Body"
    path = demo / "parts" / "Body.py"
    assert 'Clone("Clone", "plate"),' in path.read_text() and 'TIP = "Clone"' in path.read_text()
    assert data["doc"]["tip"] == "Clone"
    assert un.load(demo)["undo"][-1]["name"] == "Create Clone"
    un.perform(demo, "undo")
    assert not path.exists()
    un.perform(demo, "redo")
    assert _build_file(path).volume == pytest.approx(_build_file(demo / "parts" / "plate.py").volume, rel=1e-12)
    assert run(capsys, "feature", "clone", "demo", "plate")[1]["part"] == "Body001"
    assert run(capsys, "feature", "clone", "demo", "nothing")[0] == cli.USAGE
