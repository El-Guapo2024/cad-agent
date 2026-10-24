"""cad_agent.feature_edit reads a part's feature list and rewrites it in place, comments and layout kept."""
import difflib
import importlib.util
import math
import shutil
import sys
import types
from pathlib import Path

import pytest

from cad_agent import feature_edit as E

ROOT = Path(__file__).resolve().parent
PLATE = ROOT / "fixtures" / "feature_plate" / "parts" / "plate.py"
BRACKET = ROOT.parent / "projects" / "arduino_car" / "parts" / "motor_bracket.py"


@pytest.fixture
def plate(tmp_path):
    p = tmp_path / "plate.py"
    shutil.copy(PLATE, p)
    return p


def _build(path):
    spec = importlib.util.spec_from_file_location(f"part_{path.stem}_{id(path)}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(**mod.PARAMS)


def _diff(a, b):
    return [l for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and l[:3] not in ("+++", "---")]


def test_read_gives_the_tree():
    d = E.read(PLATE)
    assert d["part"] == "plate" and d["tip"] == "TiePocket" and d["base"] is False
    assert d["params"]["thick"] == 6.0
    names = [f["name"] for f in d["features"]]
    assert names == ["Sketch", "Pad", "Holes", "Holes001", "BossSketch", "Boss", "Bore", "BorePocket", "TieSlot",
                     "TiePocket"]
    sk = d["features"][0]
    assert sk["type"] == "Sketcher::SketchObject" and sk["support"] == "XY" and sk["attachment_offset"] is None
    assert sk["geometry"][0] == {"type": "LineSegment", "start": [-30.0, -20.0], "end": [30.0, -20.0],
                                 "construction": False}
    assert sk["geometry"][4] == {"type": "Point", "at": [0.0, 0.0], "construction": True}
    assert sk["constraints"][10] == {"type": "DistanceX", "args": [0, 1, 0, 2], "value": "width", "driving": True,
                                     "name": ""}
    pad = d["features"][1]
    assert pad["type"] == "PartDesign::Pad" and pad["profile"] == "Sketch" and pad["length"] == "thick"
    assert (pad["side_type"], pad["type1"], pad["length2"], pad["refine"]) == ("One side", "Length", 10.0, True)
    assert d["features"][3]["type1"] == "ThroughAll" and d["features"][3]["length"] == 5.0


def test_a_hand_written_part_has_no_features():
    d = E.read(BRACKET)
    assert d["features"] == [] and d["base"] is True and d["tip"] is None


def test_set_rewrites_one_literal(plate):
    before = plate.read_text()
    E.apply(plate, [{"op": "set", "name": "BorePocket", "props": {"length": 4.0}}])
    after = plate.read_text()
    assert _diff(before, after) == ['-    Pocket("BorePocket", "Bore", length=6.0),',
                                    '+    Pocket("BorePocket", "Bore", length=4.0),']
    E.apply(plate, [{"op": "set", "name": "Pad", "props": {"reversed": True, "side_type": "Symmetric"}}])
    assert 'Pad("Pad", "Sketch", length="thick", reversed=True, side_type="Symmetric"),' in plate.read_text()
    d = E.read(plate)["features"][1]
    assert d["reversed"] is True and d["side_type"] == "Symmetric"


def test_set_sketch_geometry_touches_only_what_changed(plate):
    d = E.read(plate)
    holes = d["features"][2]
    geo = [dict(g) for g in holes["geometry"]]
    geo[1] = dict(geo[1], center=[22.5, -14.0])
    geo.append({"type": "Circle", "center": [0.0, 15.0], "radius": 2.25})
    before = plate.read_text()
    E.apply(plate, [{"op": "set", "name": "Holes", "props": {"geometry": geo}}])
    diff = _diff(before, plate.read_text())
    assert diff == ["-               Circle((24.0, -14.0), 2.25),", "+               Circle((22.5, -14.0), 2.25),",
                    "+               Circle((0.0, 15.0), 2.25),"]
    assert "# M4 clearance, medium (ISO 273)" in plate.read_text()
    cons = holes["constraints"][:2]
    E.apply(plate, [{"op": "set", "name": "Holes", "props": {"constraints": cons}}])
    assert E.read(plate)["features"][2]["constraints"] == cons
    assert _build(plate).volume == pytest.approx(_expected_volume(holes=5, removed_extra=0), rel=1e-9)


def _expected_volume(holes=4, removed_extra=0.0):
    return (60 * 40 * 6 - holes * math.pi * 2.25 ** 2 * 6 + math.pi * 64 * 4 - math.pi * 16 * 6
            - (64 + math.pi * 16) * 2 - removed_extra)


def test_the_fixture_builds_what_it_says():
    assert _build(PLATE).volume == pytest.approx(_expected_volume(), rel=1e-9)


def test_add_delete_rename_move_tip(plate):
    sketch = {"name": "Notch", "type": "Sketcher::SketchObject", "support": "XY", "attachment_offset": [0, 0, 6],
              "geometry": [{"type": "LineSegment", "start": [-30, -5], "end": [-25, -5]},
                           {"type": "LineSegment", "start": [-25, -5], "end": [-25, 5]},
                           {"type": "LineSegment", "start": [-25, 5], "end": [-30, 5]},
                           {"type": "LineSegment", "start": [-30, 5], "end": [-30, -5]}],
              "constraints": [{"type": "DistanceY", "args": [1, 1, 1, 2], "value": 10.0}]}
    pocket = {"name": "NotchPocket", "type": "PartDesign::Pocket", "profile": "Notch", "type1": "ThroughAll"}
    d = E.apply(plate, [{"op": "add", "feature": sketch}, {"op": "add", "feature": pocket},
                        {"op": "tip", "name": "NotchPocket"}])
    assert [f["name"] for f in d["features"]][-2:] == ["Notch", "NotchPocket"] and d["tip"] == "NotchPocket"
    assert _build(plate).volume == pytest.approx(_expected_volume(removed_extra=50 * 6), rel=1e-9)
    src = plate.read_text()
    assert 'Pocket("NotchPocket", "Notch", type="ThroughAll"),' in src
    assert 'attachment_offset=(0, 0, 6)' in src

    d = E.apply(plate, [{"op": "rename", "name": "Notch", "to": "NotchSketch"}])
    assert d["features"][-1]["profile"] == "NotchSketch"
    with pytest.raises(E.FeatureEditError, match="NotchPocket uses it"):
        E.apply(plate, [{"op": "delete", "name": "NotchSketch"}])
    with pytest.raises(E.FeatureEditError, match="NotchPocket: its profile 'NotchSketch' is not a sketch before"):
        E.apply(plate, [{"op": "move", "name": "NotchPocket", "after": "Pad"}])
    d = E.apply(plate, [{"op": "move", "name": "NotchSketch", "after": "Pad"},
                        {"op": "move", "name": "NotchPocket", "after": "NotchSketch"}])
    assert [f["name"] for f in d["features"]][:4] == ["Sketch", "Pad", "NotchSketch", "NotchPocket"]
    assert _build(plate).volume == pytest.approx(60 * 40 * 6 - 50 * 6)     # the tip moved with it, as FreeCAD's
    E.apply(plate, [{"op": "tip", "name": "TiePocket"}])
    assert _build(plate).volume == pytest.approx(_expected_volume(removed_extra=50 * 6), rel=1e-9)
    d = E.apply(plate, [{"op": "delete", "name": "NotchPocket"}, {"op": "delete", "name": "NotchSketch"}])
    assert d["tip"] == "TiePocket"
    assert plate.read_text() == PLATE.read_text()                       # back to the byte


def test_move_refused_is_all_or_nothing(plate):
    before = plate.read_text()
    with pytest.raises(E.FeatureEditError, match="not a sketch before it"):
        E.apply(plate, [{"op": "set", "name": "Pad", "props": {"length": 9.0}},
                        {"op": "move", "name": "Pad", "after": None}])
    assert plate.read_text() == before


@pytest.mark.parametrize("ops,match", [
    ([{"op": "set", "name": "Pad", "props": {"type1": "ThroughAll"}}], "not one of Length, UpToLast"),
    ([{"op": "set", "name": "Pad", "props": {"colour": "red"}}], "not a property of a Pad"),
    ([{"op": "set", "name": "Nope", "props": {}}], "there is no feature 'Nope'"),
    ([{"op": "rename", "name": "Pad", "to": "Boss"}], "already a feature 'Boss'"),
    ([{"op": "rename", "name": "Pad", "to": "a b"}], "not a name FreeCAD takes"),
    ([{"op": "tip", "name": "Nope"}], "there is no feature"),
    ([{"op": "add", "feature": {"name": "X", "type": "PartDesign::Frobnicate"}}], "not a Sketch, Pad or Pocket"),
    ([{"op": "frobnicate"}], "is not an edit"),
    ([{"op": "set", "name": "Holes", "props": {"geometry": [{"type": "Spline"}]}}], "not LineSegment"),
])
def test_refused_edits_leave_the_file(plate, ops, match):
    before = plate.read_text()
    with pytest.raises(E.FeatureEditError, match=match):
        E.apply(plate, ops)
    assert plate.read_text() == before


def test_first_add_converts_a_hand_written_part(tmp_path):
    p = tmp_path / "motor_bracket.py"
    shutil.copy(BRACKET, p)
    hand = _build(p)
    sketch = {"name": "Lug", "type": "Sketcher::SketchObject", "support": "XY", "attachment_offset": None,
              "geometry": [{"type": "Circle", "center": [30.0, 0.0], "radius": 6.0}], "constraints": []}
    d = E.apply(p, [{"op": "add", "feature": sketch},
                    {"op": "add", "feature": {"name": "LugPad", "type": "PartDesign::Pad", "profile": "Lug",
                                              "length": 3.0}}])
    assert d["base"] is True and [f["name"] for f in d["features"]] == ["Lug", "LugPad"]
    src = p.read_text()
    assert "def build_base(base_l, base_w" in src and "base=build_base(**p)" in src
    assert "# Gusset so the upright does not hinge" in src            # the hand-written code is kept as it was
    part = _build(p)
    assert part.volume > hand.volume + 0.5 * math.pi * 36 * 3            # the lug, partly over the base


def test_solved_geometry_saves_back(plate, monkeypatch):
    """The UI's save after a solve: the geometry it got, written into the sketch."""
    d = E.read(plate)
    geo = d["features"][0]["geometry"]
    stretched = [dict(g, start=[g["start"][0] * 70 / 60, g["start"][1]], end=[g["end"][0] * 70 / 60, g["end"][1]])
                 if g["type"] == "LineSegment" else g for g in geo]
    E.apply(plate, [{"op": "set", "name": "Sketch", "props": {"geometry": stretched}}])
    src = plate.read_text()
    assert "LineSegment((-35.0, -20.0), (35.0, -20.0))," in src
    monkeypatch.setitem(sys.modules, "cad_agent.planegcs", types.SimpleNamespace(solve=None))
    spec = importlib.util.spec_from_file_location("plate_w70", plate)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    part = mod.build(**{**mod.PARAMS, "width": 70.0})               # satisfied: no solver is called
    assert part.bounding_box().size.X == pytest.approx(70)
