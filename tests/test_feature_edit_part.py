"""feature_edit reads and edits a part file's OBJECTS, the Part workbench's objects (cad_agent/feature_edit_part.py), as it
does a Body's FEATURES: in place, only what is not FreeCAD's default, all or nothing, and the result still builds."""
import ast
import importlib.util
from pathlib import Path

import pytest

from cad_agent import feature_edit as E
from cad_agent import feature_edit_part as EP
from cad_agent import feature_part as Part

GOLDEN = Path(__file__).parent / "golden" / "part"


def _cases():
    out = {}
    for p in sorted(GOLDEN.glob("cases*.py")):
        spec = importlib.util.spec_from_file_location(f"edit_{p.stem}", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        out.update(m.CASES)
    return out


CASES = _cases()
OBJS = sorted({(c, o.name): o for c, case in CASES.items() for o in case["objects"]
               if isinstance(o, Part.PartObject)}.items())


@pytest.mark.parametrize("key,obj", OBJS, ids=[f"{c}-{n}" for (c, n), _ in OBJS])
def test_every_golden_object_round_trips(key, obj):
    """dict -> part file source -> dict gives the same properties, and the source leaves FreeCAD's defaults out."""
    d = obj.as_dict()
    src = E.feature_src(d, 0)
    call = ast.parse(src, mode="eval").body
    assert E._feature_dict(call, src) == d
    written = {k.arg for k in call.keywords}
    for k in obj.DEFAULTS:
        if obj.is_default(k) and k not in obj.POS:
            assert k not in written, f"{k} is FreeCAD's default and is written: {src}"


def _doc(tmp_path, text=None):
    p = tmp_path / "plate.py"
    p.write_text(text if text is not None else EP.new_document("plate", "petg", "fdm"))
    return p


def _run(path):
    import types
    mod = types.ModuleType("plate")
    exec(compile(path.read_text(), str(path), "exec"), mod.__dict__)
    return mod.build(**mod.PARAMS)


def test_a_document_takes_objects_and_builds(tmp_path):
    p = _doc(tmp_path)
    d = E.apply(p, [{"op": "add", "feature": {"name": "Box", "type": "Part::Box", "length": 40, "width": 20,
                                              "height": 5, "label": "Cube"}},
                    {"op": "add", "feature": {"name": "Cylinder", "type": "Part::Cylinder", "radius": 3,
                                              "placement": [[8, 10, 0], [0, 0, 0]]}},
                    {"op": "add", "feature": {"name": "Cut", "type": "Part::Cut", "base": "Box", "tool": "Cylinder"}}])
    assert [o["name"] for o in d["objects"]] == ["Box", "Cylinder", "Cut"]
    assert d["body"] is False and d["features"] == [] and d["base"] is False
    text = p.read_text()
    assert 'Part.Box("Box", length=40, width=20, height=5, label="Cube"),' in text
    assert 'Part.Cut("Cut", "Box", "Cylinder"),' in text
    assert "radius=3, placement=((8.0, 10.0, 0.0), (0.0, 0.0, 0.0))" in text
    assert _run(p).volume == pytest.approx(40 * 20 * 5 - 3.141592653589793 * 9 * 5)


def test_set_rename_delete_move(tmp_path):
    p = _doc(tmp_path)
    E.apply(p, [{"op": "add", "feature": {"name": n, "type": t, **kw}} for n, t, kw in (
        ("Box", "Part::Box", {}), ("Sphere", "Part::Sphere", {"radius": 7}),
        ("Cut", "Part::Cut", {"base": "Box", "tool": "Sphere"}))])
    E.apply(p, [{"op": "set", "name": "Sphere", "props": {"radius": 6, "angle3": 180}}])
    assert 'Part.Sphere("Sphere", radius=6, angle3=180),' in p.read_text()
    E.apply(p, [{"op": "set", "name": "Sphere", "props": {"angle3": 360}}])      # back to the default: left out
    assert 'Part.Sphere("Sphere", radius=6),' in p.read_text()
    d = E.apply(p, [{"op": "rename", "name": "Sphere", "to": "Ball"}])
    assert d["objects"][2]["tool"] == "Ball"
    with pytest.raises(E.FeatureEditError, match="Cut uses it"):
        E.apply(p, [{"op": "delete", "name": "Ball"}])
    with pytest.raises(E.FeatureEditError, match="not before it"):
        E.apply(p, [{"op": "move", "name": "Cut", "after": None}])
    d = E.apply(p, [{"op": "move", "name": "Ball", "after": None}])
    assert [o["name"] for o in d["objects"]] == ["Ball", "Box", "Cut"]
    d = E.apply(p, [{"op": "delete", "name": "Cut"}, {"op": "delete", "name": "Ball"}])
    assert [o["name"] for o in d["objects"]] == ["Box"]
    with pytest.raises(E.FeatureEditError, match="already"):
        E.apply(p, [{"op": "add", "feature": {"name": "Box", "type": "Part::Cone"}}])


def test_an_attachment_follows_a_rename_and_holds_a_delete(tmp_path):
    """AttachExtension's support is a reference like any other (a Part object's REFS): a rename follows it, a delete
    is refused while it is used, and a move before the object it is attached to is refused."""
    p = _doc(tmp_path)
    E.apply(p, [{"op": "add", "feature": {"name": "Base", "type": "Part::Box"}},
                {"op": "add", "feature": {"name": "Box", "type": "Part::Box",
                                          "attachment_support": [["Base", "Face6"]], "map_mode": "FlatFace"}}])
    assert 'Part.Box("Box", attachment_support=[("Base", "Face6")], map_mode="FlatFace")' in p.read_text()
    d = E.apply(p, [{"op": "rename", "name": "Base", "to": "Ground"}])
    assert d["objects"][1]["attachment_support"] == [["Ground", "Face6"]]
    with pytest.raises(E.FeatureEditError, match="Box uses it"):
        E.apply(p, [{"op": "delete", "name": "Ground"}])
    with pytest.raises(E.FeatureEditError, match="not before it"):
        E.apply(p, [{"op": "move", "name": "Box", "after": None}])


def test_bad_values_are_refused_and_nothing_written(tmp_path):
    p = _doc(tmp_path)
    E.apply(p, [{"op": "add", "feature": {"name": "Box", "type": "Part::Box"}}])
    before = p.read_text()
    for ops in ([{"op": "set", "name": "Box", "props": {"lenght": 3}}],
                [{"op": "add", "feature": {"name": "Cut", "type": "Part::Cut", "base": "Box", "tool": "Nope"}}],
                [{"op": "add", "feature": {"name": "Helix", "type": "Part::Helix", "local_coord": "Sideways"}}]):
        with pytest.raises(E.FeatureEditError):
            E.apply(p, ops)
        assert p.read_text() == before


BODY_FILE = '''"""plate"""
from cad_agent.feature import (Body, LineSegment, Pad, Sketch)

PARAMS = {"t": 5.0}

FEATURES = [
    Sketch("Sketch", support="XY",
           geometry=[LineSegment((0.0, 0.0), (30.0, 0.0)), LineSegment((30.0, 0.0), (30.0, 20.0)),
                     LineSegment((30.0, 20.0), (0.0, 20.0)), LineSegment((0.0, 20.0), (0.0, 0.0))],
           constraints=[]),
    Pad("Pad", "Sketch", length="t"),
]
TIP = "Pad"


def build(**p):
    return Body(FEATURES, p, tip=TIP)
'''


def test_a_body_file_becomes_a_document(tmp_path):
    p = _doc(tmp_path, BODY_FILE)
    d = E.apply(p, [{"op": "add", "feature": {"name": "Cylinder", "type": "Part::Cylinder", "radius": 4, "height": 20,
                                              "placement": [[15, 10, -5], [0, 0, 0]]}},
                    {"op": "add", "feature": {"name": "Cut", "type": "Part::Cut", "base": "Body", "tool": "Cylinder"}}])
    text = p.read_text()
    assert "return Part.Document(OBJECTS, p, FEATURES, tip=TIP)" in text
    assert "from cad_agent import feature_part as Part" in text
    assert d["body"] is True and d["tip"] == "Pad" and [f["name"] for f in d["features"]] == ["Sketch", "Pad"]
    assert _run(p).volume == pytest.approx(30 * 20 * 5 - 3.141592653589793 * 16 * 5)
    # a Part object may use the Body's sketch; the sketch then cannot be deleted
    E.apply(p, [{"op": "add", "feature": {"name": "Extrude", "type": "Part::Extrusion", "base": "Sketch",
                                          "length_fwd": 2, "solid": True, "reversed": True}}])
    with pytest.raises(E.FeatureEditError, match="Extrude"):
        E.apply(p, [{"op": "delete", "name": "Sketch"}])
    with pytest.raises(E.FeatureEditError, match="already"):
        E.apply(p, [{"op": "add", "feature": {"name": "Body", "type": "Part::Box"}}])


HAND = '''"""a hand-written part"""
from build123d import Box, Cylinder

PARAMS = {"w": 10.0}


def build(**p):
    return Box(p["w"], p["w"], p["w"]) - Cylinder(2, 20)
'''


def test_a_hand_written_part_keeps_its_solid_as_the_body(tmp_path):
    p = _doc(tmp_path, HAND)
    E.apply(p, [{"op": "add", "feature": {"name": "Box", "type": "Part::Box", "placement": [[20, 0, 0], [0, 0, 0]]}}])
    text = p.read_text()
    assert "def build_base(**p):" in text and "return Part.Document(OBJECTS, p, FEATURES, base=build_base(**p)" in text
    shape = _run(p)
    assert shape.volume == pytest.approx(1000 - 3.141592653589793 * 4 * 10 + 1000, rel=1e-6)


def test_a_document_gets_a_body_for_partdesign(tmp_path):
    p = _doc(tmp_path)
    E.apply(p, [{"op": "add", "feature": {"name": "Box", "type": "Part::Box"}}])
    d = E.apply(p, [{"op": "add", "feature": {"name": "Sketch", "type": "Sketcher::SketchObject", "support": "XY",
                                              "geometry": [{"type": "Circle", "center": [5, 5], "radius": 2,
                                                            "construction": False}], "constraints": []}},
                    {"op": "add", "feature": {"name": "Pad", "type": "PartDesign::Pad", "profile": "Sketch",
                                              "length": 3}}])
    assert d["body"] is True and [f["name"] for f in d["features"]] == ["Sketch", "Pad"]
    assert "return Part.Document(OBJECTS, p, FEATURES, tip=TIP)" in p.read_text()
    assert _run(p).volume == pytest.approx(1000 + 3.141592653589793 * 4 * 3)


def test_a_sketch_outside_the_body_and_its_extrusion(tmp_path):
    p = _doc(tmp_path)
    sketch = {"name": "Sketch", "type": "Sketcher::SketchObject", "support": "XZ",
              "geometry": [{"type": "Circle", "center": [0, 0], "radius": 3, "construction": False}],
              "constraints": [{"type": "Radius", "args": [0], "value": 3.0, "driving": True, "name": ""}]}
    d = E.apply(p, [{"op": "add", "feature": sketch, "list": "OBJECTS"},
                    {"op": "add", "feature": {"name": "Extrude", "type": "Part::Extrusion", "base": "Sketch",
                                              "dir_mode": "Normal", "length_fwd": 10, "solid": True}}])
    assert [o["name"] for o in d["objects"]] == ["Sketch", "Extrude"] and d["features"] == []
    assert _run(p).volume == pytest.approx(3.141592653589793 * 9 * 10)
    g = dict(sketch["geometry"][0], radius=4)
    E.apply(p, [{"op": "set", "name": "Sketch", "props": {"geometry": [g], "constraints": [
        {"type": "Radius", "args": [0], "value": 4.0, "driving": True, "name": ""}]}}])
    assert _run(p).volume == pytest.approx(3.141592653589793 * 16 * 10)


def test_the_tree_shows_and_hides_as_freecads(tmp_path):
    """read()'s object_tree, as the real FreeCAD's tree has it after its commands (ui/scripts/fcpart.json's tree): a Cut
    claims and hides its Base and Tool, an Extrude its sketch, a Mirror claims its source and leaves it shown, a Refine
    claims nothing and hides its source, and Space's visibility= overrides."""
    p = _doc(tmp_path)
    sk = {"name": "Sketch", "type": "Sketcher::SketchObject", "support": "XY", "constraints": [],
          "geometry": [{"type": "Circle", "center": [0, 0], "radius": 3, "construction": False}]}
    d = E.apply(p, [{"op": "add", "feature": {"name": n, "type": t, **kw}} for n, t, kw in (
        ("BoxA", "Part::Box", {}), ("CylA", "Part::Cylinder", {}), ("Cut", "Part::Cut", {"base": "BoxA", "tool": "CylA"}),
        ("BoxM", "Part::Box", {}), ("Part__Mirroring", "Part::Mirroring", {"source": "BoxM", "label": "BoxM (Mirror #1)"}),
        ("BoxB", "Part::Box", {}), ("CylB", "Part::Cylinder", {}), ("Fusion", "Part::MultiFuse", {"shapes": ["BoxB", "CylB"]}),
        ("Fusion001", "Part::Refine", {"source": "Fusion"}))] +
        [{"op": "add", "feature": sk, "list": "OBJECTS"},
         {"op": "add", "feature": {"name": "Extrude", "type": "Part::Extrusion", "base": "Sketch", "solid": True}}])
    t = d["object_tree"]
    assert t["children"]["Cut"] == ["BoxA", "CylA"] and t["children"]["Part__Mirroring"] == ["BoxM"]
    assert t["children"]["Fusion001"] == [] and t["children"]["Extrude"] == ["Sketch"]
    assert t["top"] == ["Cut", "Part__Mirroring", "Fusion", "Fusion001", "Extrude"]
    assert set(t["hidden"]) == {"BoxA", "CylA", "BoxB", "CylB", "Fusion"} and "BoxM" in t["shown"]
    assert t["sketches_shown"] == []
    t = E.apply(p, [{"op": "set", "name": "BoxA", "props": {"visibility": True}},
                    {"op": "set", "name": "BoxM", "props": {"visibility": False}}])["object_tree"]
    assert "BoxA" in t["shown"] and "BoxM" in t["hidden"]
    assert "visibility=True" in p.read_text()


def test_the_cli_takes_part_types(tmp_path):
    from cad_agent import featurecmd as FC
    assert FC._type("Part.Box") == "Part::Box" and FC._type("Part::MultiFuse") == "Part::MultiFuse"


def test_a_file_that_binds_part_is_refused(tmp_path):
    p = _doc(tmp_path, HAND.replace("from build123d import Box, Cylinder", "from build123d import Box, Cylinder, Part"))
    with pytest.raises(E.FeatureEditError, match="binds the name Part"):
        E.apply(p, [{"op": "add", "feature": {"name": "Box", "type": "Part::Box"}}])
    assert "build_base" not in p.read_text()

