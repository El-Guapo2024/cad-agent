"""Std_Delete answered Yes (cad_agent/feature_delete.py): the feature goes and its links break as FreeCAD 26.3 breaks them,
in the four cases ui/scripts/fcpick.json's "delete" recorded from the real FreeCAD's GUI on the same Body (a 40 x 20 x 5
Pad, a datum plane at z 12 a sketch is attached to, a Pad of that sketch, a Fillet on that Pad's Edge1):

  DatumPlane  the sketch keeps its place (FreeCAD: AttachmentSupport empty, Placement (0, 0, 12)); the Body builds
  Sketch001   FreeCAD leaves Pad001 with no profile ("No object linked"): refused here, the Body must build
  Pad001      the Fillet's Base is rerouted to the Pad (FreeCAD: ("Pad", ["Edge1"]), valid)
  Pad         nothing links the Pad but Pad001's BaseFeature (the Body's order): it goes
"""
import json
from pathlib import Path

import pytest

from cad_agent import feature as F
from cad_agent import feature_edit as E

GOLDEN = Path(__file__).parents[1] / "ui" / "scripts" / "fcpick.json"
SRC = '''from cad_agent.feature import Body, Circle, DatumPlane, Fillet, LineSegment, Pad, Sketch

PARAMS = {}

FEATURES = [
    Sketch("Sketch", "XY", geometry=[LineSegment((0, 0), (40, 0)), LineSegment((40, 0), (40, 20)),
                                     LineSegment((40, 20), (0, 20)), LineSegment((0, 20), (0, 0))], constraints=[]),
    Pad("Pad", "Sketch", length=5),
    DatumPlane("DatumPlane", placement=((0, 0, 12), (0, 0, 0))),
    Sketch("Sketch001", attachment_support=[("DatumPlane", "")], map_mode="FlatFace", geometry=[Circle((10, 10), 3)],
           constraints=[]),
    Pad("Pad001", "Sketch001", length=2),
    Fillet("Fillet", ("Pad001", ["Edge1"]), radius=0.5),
]


def build(**p):
    return Body(FEATURES, p)
'''


def _build(src):
    feats, params, base = E._run(src, Path("_part.py"))
    return F.evaluate(feats, params, base)


def _fc(victim):
    return json.loads(GOLDEN.read_text())["delete"][victim]


def test_a_sketchs_datum_plane_goes_and_the_sketch_stays_where_it_was():
    src = E.apply_src(SRC, [{"op": "delete", "name": "DatumPlane", "break": True}])
    doc = E.read_src(src)
    sk = next(f for f in doc["features"] if f["name"] == "Sketch001")
    assert not sk.get("attachment_support") and sk["map_mode"] == "Deactivated"
    shapes = _build(src)
    pl = shapes["_attach"].placements["Sketch001"]
    assert pl.pos == pytest.approx((0, 0, 12))
    want = _fc("DatumPlane")
    assert want["objects"]["Sketch001"]["AttachmentSupport"] == [] and "Pos=(0,0,12)" in want["sketch_placement"]
    assert "DatumPlane" not in [f["name"] for f in doc["features"]]


def test_a_pads_profile_cannot_go():
    with pytest.raises(E.FeatureEditError, match="Pad001 uses it"):
        E.apply_src(SRC, [{"op": "delete", "name": "Sketch001", "break": True}])
    assert _fc("Sketch001")["objects"]["Pad001"]["status"] == "No object linked"


def test_a_dressups_base_goes_and_it_follows_to_the_solid_before():
    src = E.apply_src(SRC, [{"op": "delete", "name": "Pad001", "break": True}])
    fil = next(f for f in E.read_src(src)["features"] if f["name"] == "Fillet")
    assert fil["base"][0] == "Pad"
    assert _fc("Pad001")["objects"]["Fillet"]["Base"] == ["Pad", ["Edge1"]]
    _build(src)                                                  # it builds, as FreeCAD's is valid


def test_without_break_it_is_refused():
    with pytest.raises(E.FeatureEditError, match="DatumPlane cannot be deleted: Sketch001 uses it"):
        E.apply_src(SRC, [{"op": "delete", "name": "DatumPlane"}])


def test_the_first_solid_goes():
    src = E.apply_src(SRC, [{"op": "delete", "name": "Pad", "break": True}])
    assert [f["name"] for f in E.read_src(src)["features"]][:2] == ["Sketch", "DatumPlane"]
