"""Attachment, datums and external geometry in the part file: written, read back and edited in place.

Every body of tests/golden/attach/bodies.py is written into a part file through feature_edit's add ops (the
dicts read() gives), read back to the same dicts, and built to FreeCAD's volume (bodies.json). Then the edits
the app makes: a sketch moved from a face to a plane and back, a mode, an offset, Flip sides, its external
geometry, a datum's properties, renames that follow every reference, and the deletes and moves FreeCAD refuses.
And `cad feature add / list / attach` from the CLI.
"""
import json
import math
import sys
from pathlib import Path

import pytest

from cad_agent import cli
from cad_agent import feature as F
from cad_agent import feature_edit as E
from cad_agent import state as st
from cad_agent import undo as un
from cad_agent.feature_attach import DATUMS
from cad_agent.feature_edit_attach import DATUM_KINDS, SIZE_KEYS
from test_cli import run
from test_workbench import demo  # noqa: F401 (the fixture)

GOLDEN = Path(__file__).parent / "golden" / "attach"
sys.path.insert(0, str(GOLDEN))
from bodies import CASES  # noqa: E402

FREECAD = json.loads((GOLDEN / "bodies.json").read_text())["cases"]
SKETCH = "Sketcher::SketchObject"

EMPTY = '''"""A Body for the attachment tests."""
from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                               Sketch)

PARAMS = {}

FEATURES = [
]


def build(**p):
    return Body(FEATURES, p)
'''


def _j(v):
    return json.loads(json.dumps(v))


def as_dict(f) -> dict:
    """A feature object as read() gives it."""
    if isinstance(f, F.Sketch) or getattr(f, "is_datum", False):
        d = {"name": f.name, "type": SKETCH if isinstance(f, F.Sketch) else type(f).type_id,
             "attachment_support": [list(r) for r in f.attachment_support], "map_mode": f.map_mode,
             "attachment_offset": _j(f.attachment_offset), "map_reversed": f.map_reversed,
             "map_path_parameter": f.map_path_parameter, "placement": _j(f.own_placement)}
        if isinstance(f, F.Sketch):
            d.update({"support": f.support, "external_geometry": [list(r) for r in f.external_geometry],
                      "geometry": [g.as_dict() for g in f.geometry],
                      "constraints": [E._constraint_dict(c) for c in f.constraints]})
        else:
            for k in SIZE_KEYS[f.kind]:
                d[k] = getattr(f, k)
        return d
    if hasattr(f, "DEFAULTS"):                      # a feature_kw.KwFeature (an attached primitive)
        return _j(f.as_dict())
    d = {"name": f.name, "type": f"PartDesign::{f.kind}", "profile": f.profile}
    for key, attr in E.EXTRUDE_PROPS.items():
        v = getattr(f, attr)
        d[key] = _j(v) if isinstance(v, tuple) else v
    return d


def _norm(d):
    return _j({k: v for k, v in d.items()})


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_body_round_trips_and_builds_as_freecad(tmp_path, name):
    feats = CASES[name]["features"]
    path = tmp_path / "Body.py"
    path.write_text(EMPTY)
    doc = E.apply(path, [{"op": "add", "feature": as_dict(f)} for f in feats])
    want = [_norm(as_dict(f)) for f in feats]
    got = [_norm(f) for f in doc["features"]]
    for g, w in zip(got, want):
        assert g == {k: g.get(k) for k in w} == w
    from build123d import Solid
    from OCP.TopAbs import TopAbs_SOLID
    shapes = F.evaluate(st._load_module(path).FEATURES)
    vol = sum(Solid(s).volume for s in F._subs(shapes["Tip"], TopAbs_SOLID))
    assert vol == pytest.approx(FREECAD[name]["volume"], rel=1e-6)
    assert E.read(path) == doc
    head = path.read_text().split("PARAMS")[0]       # the import names each datum kind the body uses
    assert all(getattr(f, "kind", "") in head for f in feats if getattr(f, "is_datum", False))


PLATE = '''"""A plate with a sketch on its top face."""
from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                               Sketch)

PARAMS = {"thick": 5.0}

FEATURES = [
    Sketch("Sketch", support="XY",
           geometry=[
               LineSegment((0.0, 0.0), (40.0, 0.0)),
               LineSegment((40.0, 0.0), (40.0, 20.0)),
               LineSegment((40.0, 20.0), (0.0, 20.0)),
               LineSegment((0.0, 20.0), (0.0, 0.0)),
           ],
           constraints=[]),
    Pad("Pad", "Sketch", length="thick"),
    # the hole, on the top face
    Sketch("Sketch001", attachment_support=[("Pad", "Face6")], map_mode="FlatFace",
           external_geometry=[("Pad", "Edge4")],
           geometry=[Circle((10.0, 10.0), 3.0)],
           constraints=[]),       # keep this comment
    Pocket("Pocket", "Sketch001", type="ThroughAll"),
]


def build(**p):
    return Body(FEATURES, p)
'''


@pytest.fixture
def plate(tmp_path):
    p = tmp_path / "Plate.py"
    p.write_text(PLATE)
    return p


def _sketch(doc, name):
    return next(f for f in doc["features"] if f["name"] == name)


def test_a_face_sketch_reads_as_freecad_names_it(plate):
    s = _sketch(E.read(plate), "Sketch001")
    assert s["support"] is None and s["attachment_support"] == [["Pad", "Face6"]] and s["map_mode"] == "FlatFace"
    assert s["external_geometry"] == [["Pad", "Edge4"]]
    assert _sketch(E.read(plate), "Sketch")["support"] == "XY"
    assert _sketch(E.read(plate), "Sketch")["attachment_support"] == [["XY_Plane", ""]]


def test_set_attachment_rewrites_only_those_keywords(plate):
    E.apply(plate, [{"op": "set", "name": "Sketch001",
                     "props": {"attachment_offset": [[1, 2, 0], [0, 0, 0]], "map_reversed": True}}])
    text = plate.read_text()
    assert 'attachment_offset=((1, 2, 0), (0, 0, 0))' in text and "map_reversed=True" in text
    assert "# keep this comment" in text and "# the hole, on the top face" in text
    s = _sketch(E.read(plate), "Sketch001")
    assert s["attachment_offset"] == [[1, 2, 0], [0, 0, 0]] and s["map_reversed"] is True
    E.apply(plate, [{"op": "set", "name": "Sketch001", "props": {"map_reversed": False, "attachment_offset": None}}])
    assert "map_reversed" not in plate.read_text() and "attachment_offset" not in plate.read_text()


def test_a_sketch_moves_from_a_face_to_a_plane_and_back(plate):
    E.apply(plate, [{"op": "set", "name": "Sketch001", "props": {"support": "XZ"}}])
    text = plate.read_text()
    assert 'Sketch("Sketch001", support="XZ",' in text and "attachment_support" not in text.split("Sketch001")[1]
    assert _sketch(E.read(plate), "Sketch001")["attachment_support"] == [["XZ_Plane", ""]]
    E.apply(plate, [{"op": "set", "name": "Sketch001", "props": {"attachment_support": [["Pad", "Face2"]],
                                                                  "map_mode": "FlatFace"}}])
    s = _sketch(E.read(plate), "Sketch001")
    assert s["attachment_support"] == [["Pad", "Face2"]] and s["support"] is None
    assert 'support="XZ"' not in plate.read_text()
    E.apply(plate, [{"op": "set", "name": "Sketch001", "props": {"map_mode": "Deactivated",
                                                                  "attachment_support": [],
                                                                  "placement": [[0, 0, 30], [0, 0, 0]]}}])
    s = _sketch(E.read(plate), "Sketch001")
    assert s["map_mode"] == "Deactivated" and s["attachment_support"] == [] and s["placement"] == [[0, 0, 30], [0, 0, 0]]


def test_a_positional_support_gives_way(tmp_path):
    p = tmp_path / "P.py"
    p.write_text(EMPTY.replace("FEATURES = [\n]", 'FEATURES = [\n    Sketch("S", "XY", [Circle((0.0, 0.0), 2.0)], []),\n]'))
    E.apply(p, [{"op": "set", "name": "S", "props": {"attachment_support": [["XY_Plane", ""]], "map_mode": "ObjectXZ"}}])
    assert 'Sketch("S", None, [Circle((0.0, 0.0), 2.0)], [], attachment_support=[("XY_Plane", "")], ' \
           'map_mode="ObjectXZ")' in p.read_text()
    assert _sketch(E.read(p), "S")["map_mode"] == "ObjectXZ"


def test_external_geometry_is_set_in_place(plate):
    E.apply(plate, [{"op": "set", "name": "Sketch001",
                     "props": {"external_geometry": [["Pad", "Edge4"], ["Pad", "Vertex6"]]}}])
    assert 'external_geometry=[("Pad", "Edge4"), ("Pad", "Vertex6")]' in plate.read_text()
    E.apply(plate, [{"op": "set", "name": "Sketch001", "props": {"external_geometry": []}}])
    assert "external_geometry" not in plate.read_text()


def test_rename_follows_attachments_and_external_geometry(plate):
    E.apply(plate, [{"op": "rename", "name": "Pad", "to": "Plate"}])
    text = plate.read_text()
    assert '("Plate", "Face6")' in text and '("Plate", "Edge4")' in text and 'Pocket("Pocket", "Sketch001"' in text


def test_what_a_sketch_is_attached_to_cannot_go(plate):
    with pytest.raises(E.FeatureEditError, match="Sketch001 uses it"):
        E.apply(plate, [{"op": "delete", "name": "Pad"}])
    with pytest.raises(E.FeatureEditError, match="attached to or projects 'Pad', which is not before it"):
        E.apply(plate, [{"op": "move", "name": "Sketch001", "after": None}])
    assert plate.read_text() == PLATE


def test_a_datum_is_added_with_its_import(plate):
    doc = E.apply(plate, [{"op": "add", "feature": {"name": "DatumPlane", "type": "Part::DatumPlane",
                                                    "attachment_support": [["Pad", "Face6"]], "map_mode": "FlatFace",
                                                    "attachment_offset": [[0, 0, 10], [0, 0, 0]]}, "after": "Pad"}])
    text = plate.read_text()
    assert "DatumPlane," in text.split("PARAMS")[0]
    assert 'DatumPlane("DatumPlane", attachment_support=[("Pad", "Face6")], map_mode="FlatFace", ' \
           'attachment_offset=((0, 0, 10), (0, 0, 0))),' in text
    d = _sketch(doc, "DatumPlane")
    assert d["type"] == "Part::DatumPlane" and "length" not in d
    E.apply(plate, [{"op": "set", "name": "DatumPlane", "props": {"map_mode": "Translate",
                                                                   "attachment_support": [["Pad", "Vertex6"]]}}])
    d = _sketch(E.read(plate), "DatumPlane")
    assert d["map_mode"] == "Translate" and d["attachment_support"] == [["Pad", "Vertex6"]]
    with pytest.raises(E.FeatureEditError, match="length is not a property of a DatumPlane"):
        E.apply(plate, [{"op": "set", "name": "DatumPlane", "props": {"length": 50.0}}])
    E.apply(plate, [{"op": "add", "feature": {"name": "DatumPlane001", "type": "PartDesign::Plane",
                                              "attachment_support": [["Pad", "Face2"]], "map_mode": "FlatFace"}}])
    E.apply(plate, [{"op": "set", "name": "DatumPlane001", "props": {"length": 50.0, "resize_mode": "Manual"}}])
    d = _sketch(E.read(plate), "DatumPlane001")
    assert (d["type"], d["length"], d["resize_mode"], d["width"]) == ("PartDesign::Plane", 50.0, "Manual", 20.0)
    assert 'PartDesignPlane("DatumPlane001", attachment_support=[("Pad", "Face2")], map_mode="FlatFace", ' \
           'length=50.0, resize_mode="Manual")' in plate.read_text()
    with pytest.raises(E.FeatureEditError, match="map_mode 'Vertex' is not one of"):
        E.apply(plate, [{"op": "set", "name": "DatumPlane", "props": {"map_mode": "Vertex"}}])
    mod = st._load_module(plate)
    assert F.evaluate(mod.FEATURES, mod.PARAMS)["_attach"].placements["DatumPlane"].pos == (40.0, 20.0, 15.0)   # Translate keeps the offset


@pytest.mark.parametrize("kind", DATUM_KINDS)
def test_every_datum_kind_round_trips(tmp_path, kind):
    p = tmp_path / "B.py"
    p.write_text(EMPTY)
    f = {"name": kind + "1", "type": DATUMS[kind].type_id, "placement": [[1, 2, 3], [10, 20, 30]]}
    doc = E.apply(p, [{"op": "add", "feature": f}])
    d = doc["features"][0]
    assert d["map_mode"] == "Deactivated" and d["placement"] == [[1, 2, 3], [10, 20, 30]]
    pl = F.evaluate(st._load_module(p).FEATURES)["_attach"].placements[kind + "1"]
    assert pl.pos == (1.0, 2.0, 3.0) and all(abs(a - b) < 1e-9 for a, b in zip(pl.rot.ypr(), (10, 20, 30)))


# ── the CLI ────────────────────────────────────────────────────────────────────────────────────────

def _plate_body(capsys):
    assert run(capsys, "feature", "new", "demo", "Body")[0] == cli.OK
    rect = [{"type": "LineSegment", "start": a, "end": b, "construction": False}
            for a, b in [([0, 0], [40, 0]), ([40, 0], [40, 20]), ([40, 20], [0, 20]), ([0, 20], [0, 0])]]
    ops = [{"op": "add", "feature": {"name": "Sketch", "type": SKETCH, "support": "XY", "geometry": rect,
                                     "constraints": []}},
           {"op": "add", "feature": {"name": "Pad", "type": "PartDesign::Pad", "profile": "Sketch", "length": 5.0}}]
    code, data = run(capsys, "feature", "apply", "demo", "Body", "--ops", json.dumps(ops))
    assert data.get("built") is True, data


def test_cad_feature_attach_answers_as_the_panel(demo, capsys):
    _plate_body(capsys)
    code, data = run(capsys, "feature", "attach", "demo", "Body", "--support", "Pad.Face6")
    assert code == cli.OK and data["types"] == ["Plane"] and data["mode"] == "FlatFace"
    assert data["suggestion"]["best"] == "FlatFace" and "ObjectXY" not in data["suggestion"]["all"]
    assert data["placement"]["position"] == [0.0, 0.0, 5.0]
    code, data = run(capsys, "feature", "attach", "demo", "Body", "--support", "Pad.Vertex1", "--support",
                     "Pad.Vertex4", "--engine", "Line")
    assert data["mode"] == "TwoPointLine" and "TwoPointLine" in data["suggestion"]["all"]
    code, data = run(capsys, "feature", "attach", "demo", "Body", "--support", "Pad.Face9")
    assert data["message"] == "LinkBroken" and "Face9" in data["error"]


def test_cad_feature_attach_and_list_a_part_object(demo, capsys):
    """A Part workbench object's AttachExtension (engine 3D): the panel's query resolves the objects before it and the
    Body's features, and `cad feature list` places every object (feature_attach.body_info's Part objects)."""
    _plate_body(capsys)
    ops = [{"op": "add", "feature": {"name": "Base", "type": "Part::Box", "length": 20, "width": 20, "height": 10,
                                     "placement": [[0, 0, 30], [0, 0, 0]]}},
           {"op": "add", "feature": {"name": "Box", "type": "Part::Box", "length": 4, "width": 6, "height": 2,
                                     "attachment_support": [["Base", "Face6"]], "map_mode": "FlatFace",
                                     "attachment_offset": [[1, 2, 3], [0, 0, 0]]}},
           {"op": "add", "feature": {"name": "Chip", "type": "Part::Box", "length": 2, "width": 2, "height": 2,
                                     "attachment_support": [["Pad", "Face6"]], "map_mode": "FlatFace"}}]
    code, data = run(capsys, "feature", "apply", "demo", "Body", "--ops", json.dumps(ops))
    assert data.get("built") is True, data              # the gates may leave rows unchecked
    code, data = run(capsys, "feature", "attach", "demo", "Body", "--support", "Base.Face6", "--mode", "FlatFace",
                     "--offset", "[[1,2,3],[0,0,0]]", "--before", "Box")
    assert code == cli.OK and data["engine"] == "3D"                    # Attacher::AttachEngine3D, not the CLI's Plane
    assert data["suggestion"]["types"] == ["Plane"] and data["mode"] == "FlatFace"
    assert data["placement"]["position"] == pytest.approx([1.0, 2.0, 43.0])       # Base sits at z 30, its top at 40
    code, data = run(capsys, "feature", "attach", "demo", "Body", "--support", "Pad.Face6", "--before", "Chip")
    assert data["engine"] == "3D" and data["placement"]["position"] == pytest.approx([0.0, 0.0, 5.0])
    code, data = run(capsys, "feature", "attach", "demo", "Body", "--support", "Box.Face6", "--before", "Base")
    assert data["message"] == "LinkBroken" and "'Box' before it" in data["error"]  # a part file is in order
    code, data = run(capsys, "feature", "list", "demo", "Body")
    objs = data["attached"]["objects"]
    assert objs["Box"]["placement"]["position"] == pytest.approx([1.0, 2.0, 43.0])
    assert objs["Box"]["map_mode"] == "FlatFace" and objs["Chip"]["map_mode"] == "FlatFace"
    assert objs["Chip"]["placement"]["position"] == pytest.approx([0.0, 0.0, 5.0])
    assert objs["Base"]["placement"]["position"] == pytest.approx([0.0, 0.0, 30.0])
    assert data["attached"]["error"] is None


def test_cad_feature_add_a_sketch_on_a_face_and_a_datum(demo, capsys):
    _plate_body(capsys)
    circle = json.dumps([{"type": "Circle", "center": [10, 10], "radius": 3, "construction": False}])
    code, data = run(capsys, "feature", "add", "demo", "Body", "Sketch", "Sketch001",
                     'attachment_support=[["Pad", "Face6"]]', "map_mode=FlatFace", f"geometry={circle}")
    assert code in (cli.OK, cli.UNCHECKED), data          # the gates may leave rows unchecked
    assert un.load(demo)["undo"][-1]["name"] == "New Sketch"
    code, data = run(capsys, "feature", "add", "demo", "Body", "Pad", "Pad001", "profile=Sketch001", "length=4")
    assert data.get("built") is True, data
    code, data = run(capsys, "feature", "add", "demo", "Body", "DatumPlane", "DatumPlane",
                     "attachment_support=XY_Plane", "map_mode=FlatFace", "attachment_offset=[[0, 0, 12], [0, 0, 0]]")
    assert code in (cli.OK, cli.UNCHECKED), data
    assert un.load(demo)["undo"][-1]["name"] == "Add datum plane"           # Part/Gui/Command.cpp's
    code, data = run(capsys, "feature", "list", "demo", "Body")
    objs = data["attached"]["objects"]
    assert objs["Sketch001"]["placement"]["position"] == [0.0, 0.0, 5.0] and objs["Sketch001"]["map_mode"] == "FlatFace"
    assert objs["DatumPlane"]["placement"]["position"] == [0.0, 0.0, 12.0]
    assert objs["Pad001"]["placement"]["position"] == [0.0, 0.0, 0.0] and data["attached"]["error"] is None
    code, data = run(capsys, "feature", "set", "demo", "Body", "Sketch001", 'external_geometry=["Pad.Edge4"]')
    assert code in (cli.OK, cli.UNCHECKED), data
    code, data = run(capsys, "feature", "list", "demo", "Body")
    ext = data["attached"]["objects"]["Sketch001"]["external"]
    assert ext == [{"type": "LineSegment", "start": [0.0, 0.0], "end": [40.0, 0.0], "construction": True}]
    assert run(capsys, "undo", "demo")[0] == cli.OK
    assert "external_geometry" not in (demo / "parts" / "Body.py").read_text()


def test_a_primitive_is_attached_edited_and_followed(plate):
    """A PartDesign primitive's AttachExtension (engine 3D): added on a face, its mode and offset set in place, the
    Pad renamed under it, and the face it is attached to kept from being deleted."""
    E.apply(plate, [{"op": "add", "feature": {"name": "Box", "type": "PartDesign::AdditiveBox", "length": 6.0,
                                              "attachment_support": [["Pad", "Face2"]], "map_mode": "FlatFace"},
                     "after": "Pad"}])
    box = _sketch(E.read(plate), "Box")
    assert box["attachment_support"] == [["Pad", "Face2"]] and box["map_mode"] == "FlatFace"
    E.apply(plate, [{"op": "set", "name": "Box", "props": {"attachment_offset": [[2.0, 1.0, 0.0], [15.0, 0.0, 0.0]],
                                                            "map_reversed": True}}])
    box = _sketch(E.read(plate), "Box")
    assert box["attachment_offset"] == [[2.0, 1.0, 0.0], [15.0, 0.0, 0.0]] and box["map_reversed"] is True
    mod = st._load_module(plate)
    pl = F.evaluate(mod.FEATURES, mod.PARAMS)["_attach"].placements["Box"]
    (pos, q) = FREECAD["primitive_on_side_face"]["objects"]["Box"]["placement"]    # the same attachment, unflipped
    assert pl.pos[0] == pytest.approx(pos[0]) and pl.pos != pytest.approx(pos)     # on Face2; Flip sides moved it
    E.apply(plate, [{"op": "rename", "name": "Pad", "to": "Plate"}])
    assert '("Plate", "Face2")' in plate.read_text()
    with pytest.raises(E.FeatureEditError, match="Box"):
        E.apply(plate, [{"op": "delete", "name": "Plate"}])
