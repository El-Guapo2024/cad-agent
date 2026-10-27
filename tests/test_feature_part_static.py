"""The static objects (cad_agent/feature_part_static.py): their goldens are in test_feature_part.py (cases_static.py); here
what no golden holds: FreeCAD's errors and messages, an empty section, and the objects through feature_edit and the tree."""
import types

import pytest

from cad_agent import feature as F
from cad_agent import feature_edit as E
from cad_agent import feature_edit_part as EP
from cad_agent import feature_part as Part
from cad_agent import feature_part_static as S

BOX = Part.Box("Box", length=10, width=20, height=5)


def _errors(*objs):
    return Part.evaluate([BOX, *objs], keep_going=True)["_errors"]


def test_a_section_that_misses_is_an_empty_compound():
    r = Part.evaluate([BOX, Part.CrossSections("Box_cs", "Box", plane="XY", positions=[50.0])])
    assert r["Box_cs"].ShapeType().name == "TopAbs_COMPOUND" and S._subs(r["Box_cs"], S.TopAbs_WIRE) == []


def test_the_builder_refuses_a_wrong_selection_with_its_message():
    for mode, elements, msg in (
            ("Edge from vertices", [("Box", "Vertex1")], "Select two vertices"),
            ("Face from vertices", [("Box", "Vertex1"), ("Box", "Vertex2")], "Select three or more vertices"),
            ("Shell from faces", [("Box", "Face1")], "Select at least 2 faces"),
            ("Solid from shell", [], "Select only 1 shape object")):
        err = _errors(Part.ShapeBuilder("B", mode, elements=elements))
        assert msg in err["B"], (mode, err)
    assert "Part object is not a shell" in _errors(Part.ShapeBuilder("B", "Solid from shell", elements=["Box"]))["B"]


def test_a_solid_is_not_converted():
    assert "neither a shell nor a compound" in _errors(Part.MakeSolid("S", "Box"))["S"]
    assert S.can_make_solid("Solid") == "{} is ignored because it is already a solid."
    assert S.can_make_solid("Face") == "{} is ignored because it is neither a shell nor a compound."
    assert S.can_make_solid("Shell") is None and S.can_make_solid("Compound") is None


def test_a_copy_follows_its_source_and_a_missing_one_fails():
    r = Part.evaluate([BOX, Part.Feature("Box001", "Box"), Part.Feature("Orphan")], keep_going=True)
    assert r["_errors"]["Orphan"].endswith("No part object linked.")
    assert S.Feature("Box001", ("Box", "Face3")).source == ("Box", "Face3")


def test_the_planes_the_dialog_gives():
    assert S.cross_section_planes(None, "XY", 5.0, sections=False) == [5.0]
    assert S.cross_section_planes(None, "XY", 5.0, count=3, distance=2.0) == [5.0, 7.0, 9.0]
    assert S.cross_section_planes(None, "XY", 5.0, count=3, distance=2.0, both=True) == [3.0, 5.0, 7.0]


def _run(path):
    mod = types.ModuleType("plate")
    exec(compile(path.read_text(), str(path), "exec"), mod.__dict__)
    return mod.build(**mod.PARAMS)


def test_static_objects_go_through_feature_edit(tmp_path):
    p = tmp_path / "plate.py"
    p.write_text(EP.new_document("plate", "petg", "fdm"))
    d = E.apply(p, [{"op": "add", "feature": {"name": n, "type": t, **kw}} for n, t, kw in (
        ("Box", "Part::Box", {"length": 10, "width": 20, "height": 5, "label": "Cube"}),
        ("Box001", "Part::Feature", {"source": "Box", "label": "Cube001"}),
        ("Box002", "Part::Feature", {"source": ["Box", "Face3"]}),
        ("Box_cs", "Part::CrossSections", {"base": "Box", "plane": "XZ", "positions": [2.0, 8.0]}),
        ("Face", "Part::ShapeBuilder", {"mode": "Face from vertices", "planar": True,
                                       "elements": [["Box", "Vertex1"], ["Box", "Vertex2"], ["Box", "Vertex4"]]}),
        ("Tolerance", "Part::ToleranceSet", {"objects": ["Box"], "min_tolerance": 1e-07}))])
    text = p.read_text()
    assert 'Part.Feature("Box001", "Box", label="Cube001"),' in text
    assert 'Part.Feature("Box002", ("Box", "Face3")),' in text
    assert 'Part.CrossSections("Box_cs", "Box", plane="XZ", positions=[2.0, 8.0]),' in text
    assert 'Part.ShapeBuilder("Face", "Face from vertices", elements=[("Box", "Vertex1")' in text
    assert 'Part.ToleranceSet("Tolerance", ["Box"], min_tolerance=1e-07),' in text
    t = d["object_tree"]
    assert t["children"]["Tolerance"] == ["Box"] and t["children"]["Box001"] == []
    assert "Box" in t["hidden"] and "Box001" in t["shown"]            # a ToleranceSet hides its object
    E.apply(p, [{"op": "set", "name": "Box_cs", "props": {"positions": [4.0]}},
                {"op": "rename", "name": "Box", "to": "Base"}])
    assert 'Part.Feature("Box001", "Base", label="Cube001")' in p.read_text()
    assert 'positions=[4.0]' in p.read_text()
    assert _run(p).volume > 0
    with pytest.raises(E.FeatureEditError, match="Box001|used"):
        E.apply(p, [{"op": "delete", "name": "Base"}])
    assert F is not None
