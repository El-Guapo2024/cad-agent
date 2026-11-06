"""Draft's objects in a part file (cad_agent/feature_draft.py). Their shapes are held to FreeCAD's by
tests/test_feature_part.py (tests/golden/part/cases_draft.py, freecad_draft.json); here each class's DEFAULTS are the
fresh object its draftmake maker makes in FreeCAD 26.3 (make.py draft), and the editor adds a Draft object to a part
file with its import, and the part builds.
"""
import json
from pathlib import Path

import pytest

from cad_agent import feature_draft as Draft
from cad_agent import feature_edit as E
from cad_agent import feature_edit_part as EP

FC = json.loads((Path(__file__).parent / "golden" / "part" / "freecad_draft.json").read_text())["draft_defaults"]
CLASSES = sorted(Draft.OBJECTS.items())


@pytest.mark.parametrize("kind,cls", CLASSES, ids=[k for k, _ in CLASSES])
def test_defaults_are_freecads(kind, cls):
    fc = FC[cls.TYPE_ID]
    assert fc["_TypeId"] == cls.FC_TYPE
    for key, d in cls.DEFAULTS.items():
        if key in ("label", "visibility", "placement") or key in cls.ATTACH:
            continue
        prop = cls.prop_name(key)
        assert prop in fc, f"{prop} is not a property of FreeCAD's {kind}"
        v = fc[prop]
        if key in cls.REFS:
            assert v in (None, [], "None") or isinstance(v, str), (prop, v)
            continue
        ours = json.loads(json.dumps(d))
        if isinstance(v, (int, float, list)) and not isinstance(v, bool):
            assert ours == pytest.approx(v), (prop, ours, v)
        else:
            assert ours == v, (prop, ours, v)
    # every property a user sets is a keyword; only read-only results, links not ported, and Draft's internals are not
    left = set(fc) - {cls.prop_name(k) for k in cls.DEFAULTS} - {"_TypeId", "Placement", "Label", "Area", "Length",
                                                                   "Count", "PlacementList", "_ElementMapVersion"}
    left -= {"AttacherEngine", "AttacherType", "AttachmentOffset", "AttachmentSupport", "MapMode",
             "MapPathParameter", "MapReversed"}
    assert left <= {"Base", "Tool", "Start", "End", "AxisReference", "PathSubelements", "ExtraPlacement",
                    "AlwaysSyncPlacement", "ExpandArray", "LinkTransform", "ColoredElements", "LinkCopyOnChange",
                    "ElementList", "Scale", "ScaleVector", "ScaleList", "VisibilityList", "_ChildCache",
                    "_LinkOwner", "_LinkTouched", "Continuity"}, left


def test_the_editor_adds_draft_objects_and_the_part_builds(tmp_path):
    import types
    p = tmp_path / "plate.py"
    p.write_text(EP.new_document("plate", "petg", "fdm"))
    d = E.apply(p, [{"op": "add", "feature": {"name": "Rectangle", "type": "Draft::Rectangle", "length": 4,
                                              "height": 2}},
                    {"op": "add", "feature": {"name": "Array", "type": "Draft::Array", "base": "Rectangle",
                                              "number_x": 3, "interval_x": [6, 0, 0]}}])
    assert [o["name"] for o in d["objects"]] == ["Rectangle", "Array"]
    text = p.read_text()
    assert "from cad_agent import feature_draft as Draft\n" in text
    assert 'Draft.Rectangle("Rectangle", length=4, height=2),' in text
    assert 'Draft.Array("Array", "Rectangle", number_x=3, interval_x=[6.0, 0.0, 0.0]),' in text
    mod = types.ModuleType("plate")
    exec(compile(text, str(p), "exec"), mod.__dict__)
    shape = mod.build(**mod.PARAMS)
    assert shape.area == pytest.approx(3 * 2 * 8)          # the array: 6 rectangles 4 x 2 (the base is hidden)


def test_attachment_is_refused():
    with pytest.raises(Exception, match="attachment is not supported"):
        Draft.Rectangle("R", map_mode="FlatFace", attachment_support=[("Box", "Face1")]).validate()
