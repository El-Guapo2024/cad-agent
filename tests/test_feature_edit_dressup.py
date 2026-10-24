"""Fillet, Chamfer, Draft and Thickness read and written in place by cad_agent.feature_edit, and `cad feature add`."""
import difflib
import importlib.util
from pathlib import Path

import pytest

from cad_agent import feature_edit as E

PART = '''"""plate: a test Body."""
from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                               Sketch)

PARAMS = {"r": 1.5}

FEATURES = [
    Sketch("Sketch", support="XY",
           geometry=[
               LineSegment((0.0, 0.0), (40.0, 0.0)),
               LineSegment((40.0, 0.0), (40.0, 20.0)),
               LineSegment((40.0, 20.0), (0.0, 20.0)),
               LineSegment((0.0, 20.0), (0.0, 0.0)),
           ],
           constraints=[]),
    Pad("Pad", "Sketch", length=5.0),   # the plate
]


def build(**p):
    return Body(FEATURES, p)
'''


@pytest.fixture
def part(tmp_path):
    p = tmp_path / "plate.py"
    p.write_text(PART)
    return p


def _build(path):
    spec = importlib.util.spec_from_file_location(f"part_{path.stem}_{id(path)}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(**mod.PARAMS)


def _diff(a, b):
    return [ln for ln in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
            if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]


FEATS = [
    {"name": "Fillet", "type": "PartDesign::Fillet", "base": ["Pad", ["Edge1", "Face6"]], "radius": "r"},
    {"name": "Chamfer", "type": "PartDesign::Chamfer", "base": ["Pad", ["Edge4"]],
     "chamfer_type": "Distance and Angle", "size": 2.0, "angle": 30.0, "flip_direction": True},
    {"name": "Draft", "type": "PartDesign::Draft", "base": ["Pad", ["Face1", "Face2"]], "angle": 3.0,
     "neutral_plane": "XY_Plane", "pull_direction": "Z_Axis", "reversed": True},
    {"name": "Draft", "type": "PartDesign::Draft", "base": ["Pad", ["Face3"]],
     "neutral_plane": ["Pad", "Face6"]},
    {"name": "Thickness", "type": "PartDesign::Thickness", "base": ["Pad", ["Face6"]], "value": 2.0,
     "mode": "RectoVerso", "join": "Intersection", "reversed": False, "refine": False},
]


@pytest.mark.parametrize("feat", FEATS, ids=lambda f: f["name"] + "_" + str(len(f)))
def test_add_round_trips(part, feat):
    before = part.read_text()
    d = E.apply(part, [{"op": "add", "feature": feat}])
    got = d["features"][-1]
    for k, v in feat.items():
        assert got[k] == v, k
    kind = feat["type"].split("::")[1]
    src = part.read_text()
    assert f"from cad_agent.feature import {kind}\n" in src        # the old import did not have it
    added = [ln for ln in _diff(before, src) if ln.startswith("+")]
    assert len(added) == 2, added                                   # the import and the entry, nothing else
    assert E.read(part)["features"][-1] == got
    assert _build(part).volume > 0


def test_defaults_are_left_out_and_read_back(part):
    E.apply(part, [{"op": "add", "feature": {"name": "Fillet", "type": "PartDesign::Fillet",
                                             "base": ["Pad", ["Edge1"]]}}])
    assert '    Fillet("Fillet", ("Pad", ["Edge1"])),\n' in part.read_text()
    f = E.read(part)["features"][-1]
    assert f == {"name": "Fillet", "type": "PartDesign::Fillet", "base": ["Pad", ["Edge1"]], "radius": 1.0,
                 "use_all_edges": False, "refine": True}


def test_set_rewrites_one_literal(part):
    E.apply(part, [{"op": "add", "feature": {"name": "Fillet", "type": "PartDesign::Fillet",
                                             "base": ["Pad", ["Edge1"]]}}])
    before = part.read_text()
    E.apply(part, [{"op": "set", "name": "Fillet", "props": {"base": ["Pad", ["Edge1", "Edge2"]], "radius": 2.0}}])
    assert _diff(before, part.read_text()) == ['-    Fillet("Fillet", ("Pad", ["Edge1"])),',
                                               '+    Fillet("Fillet", ("Pad", ["Edge1", "Edge2"]), radius=2.0),']
    with pytest.raises(E.FeatureEditError, match="not a property"):
        E.apply(part, [{"op": "set", "name": "Fillet", "props": {"size": 2.0}}])
    with pytest.raises(E.FeatureEditError, match="chamfer_type"):
        E.apply(part, [{"op": "add", "feature": {"name": "C", "type": "PartDesign::Chamfer",
                                                 "base": ["Pad", ["Edge1"]], "chamfer_type": "x"}}])


def test_rename_and_delete_follow_the_base(part):
    E.apply(part, [{"op": "add", "feature": FEATS[0]}])
    E.apply(part, [{"op": "rename", "name": "Pad", "to": "Plate"}])
    assert E.read(part)["features"][-1]["base"] == ["Plate", ["Edge1", "Face6"]]
    with pytest.raises(E.FeatureEditError, match="Fillet uses it"):
        E.apply(part, [{"op": "delete", "name": "Plate"}])
    E.apply(part, [{"op": "delete", "name": "Fillet"}])
    assert [f["name"] for f in E.read(part)["features"]] == ["Sketch", "Plate"]


def test_base_must_come_before(part):
    with pytest.raises(E.FeatureEditError, match="not before it"):
        E.apply(part, [{"op": "add", "feature": {"name": "Fillet", "type": "PartDesign::Fillet",
                                                 "base": ["Pad", ["Edge1"]]}, "after": "Sketch"}])


def test_a_sketch_edit_that_renumbers_is_followed(part):
    """The sketch's lines reordered in the Sketcher: the Pad's Edge7 (x = 40, top) is now its Edge4, and the
    Fillet's Base says so, as FreeCAD's does (tests/golden/dressup, FOLLOW reorder_fillet)."""
    E.apply(part, [{"op": "add", "feature": {"name": "Fillet", "type": "PartDesign::Fillet",
                                             "base": ["Pad", ["Edge7"]], "radius": 2.0}}])
    g = E.read(part)["features"][0]["geometry"]
    d = E.apply(part, [{"op": "set", "name": "Sketch", "props": {"geometry": g[1:] + g[:1]}}])
    assert d["features"][-1]["base"] == ["Pad", ["Edge4"]]


def test_a_feature_put_before_is_rerouted(part):
    """A Pocket inserted between the Pad and the Fillet: the Fillet's Base becomes the Pocket."""
    E.apply(part, [{"op": "add", "feature": {"name": "Fillet", "type": "PartDesign::Fillet",
                                             "base": ["Pad", ["Edge7"]], "radius": 2.0}}])
    d = E.apply(part, [
        {"op": "add", "after": "Pad", "feature": {"name": "Hole", "type": "Sketcher::SketchObject", "support": "XY",
                                                   "geometry": [{"type": "Circle", "center": [20.0, 10.0],
                                                                 "radius": 3.0, "construction": False}],
                                                   "constraints": []}},
        {"op": "add", "after": "Hole", "feature": {"name": "Pocket", "type": "PartDesign::Pocket", "profile": "Hole",
                                                    "type1": "ThroughAll", "reversed": True}}])
    assert d["features"][-1]["base"][0] == "Pocket"
    assert _build(part).volume > 0


def test_cad_feature_add_takes_them(tmp_path, monkeypatch):
    """`cad feature add` parses a dress-up's TYPE and its key=value props (base as JSON)."""
    from cad_agent import featurecmd as C
    assert C._type("Fillet") == "PartDesign::Fillet" and C._type("PartDesign::Thickness") == "PartDesign::Thickness"
    for k in ("Fillet", "Chamfer", "Draft", "Thickness"):
        assert C.ADD_NAMES[C.TYPES[k]] == f"Make {k}"


def test_links_shorthand():
    from cad_agent import featurecmd as C
    assert C._links({"base": "Pad:Edge1,Face6", "neutral_plane": "Pad:Face5", "radius": 2}) == \
        {"base": ["Pad", ["Edge1", "Face6"]], "neutral_plane": ["Pad", "Face5"], "radius": 2}
    assert C._links({"base": ["Pad", ["Edge1"]]}) == {"base": ["Pad", ["Edge1"]]}


def test_shape_after_ops_writes_nothing(part):
    """`cad feature shape`: the feature built after the panel's ops, with its base, by FreeCAD's names."""
    from cad_agent import feature_shape as S
    before = part.read_text()
    ops = [{"op": "add", "feature": {"name": "Fillet", "type": "PartDesign::Fillet", "base": ["Pad", ["Edge1"]]}},
           {"op": "tip", "name": "Fillet"}]
    doc, target, base_name, solid, base, error = S.shapes_after(part, ops, "Fillet")
    assert part.read_text() == before
    assert (target, base_name, error) == ("Fillet", "Pad", None)
    m, b = S.mesh(solid), S.mesh(base)
    assert [f["name"] for f in b["faces"]] == [f"Face{i}" for i in range(1, 7)]
    assert [e["name"] for e in b["edges"]] == [f"Edge{i}" for i in range(1, 13)]
    assert len(m["faces"]) == 7 and all(f["index"] and len(f["points"]) % 3 == 0 for f in m["faces"])
    # Edge1 is the vertical edge at the origin, as FreeCAD's Edge1 is (tests/golden/dressup)
    pts = b["edges"][0]["points"]
    assert (pts[0], pts[1]) == (0.0, 0.0) and {pts[2], pts[-1]} == {0.0, 5.0}
    # a feature that does not build says FreeCAD's words, and the base still comes back to pick from
    _, _, _, solid, base, error = S.shapes_after(part, [{"op": "add", "feature": {
        "name": "Fillet", "type": "PartDesign::Fillet", "base": ["Pad", []]}}, {"op": "tip", "name": "Fillet"}], "Fillet")
    assert error == "Fillet not possible on selected shapes" and base is not None
