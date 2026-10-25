"""A PartDesign ShapeBinder in a FEATURES list (cad_agent/feature_binder.py) is what FreeCAD's PartDesign makes.

tests/golden/binder/cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote freecad.json. Here the same lines go through feature.evaluate and Body: every binder
must have FreeCAD's shape, shape placement and Support, and the Body must be the same solid as without it. The
part file carries a binder through feature_edit as every feature_kw.KwFeature, and a binder is never a Body's Tip.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import (TopAbs_COMPSOLID, TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHAPE, TopAbs_SHELL,
                        TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE)

from cad_agent import attacher as A
from cad_agent import feature
from cad_agent import feature_edit as E
from cad_agent.feature import Body, ShapeBinder

GOLDEN = Path(__file__).parent / "golden" / "binder"
_spec = importlib.util.spec_from_file_location("binder_cases", GOLDEN / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES
from test_workbench import demo  # noqa: E402,F401 (the project fixture)

FREECAD = json.loads((GOLDEN / "freecad.json").read_text())["cases"]

TYPES = {TopAbs_COMPOUND: "Compound", TopAbs_COMPSOLID: "CompSolid", TopAbs_SOLID: "Solid", TopAbs_SHELL: "Shell",
         TopAbs_FACE: "Face", TopAbs_WIRE: "Wire", TopAbs_EDGE: "Edge", TopAbs_VERTEX: "Vertex",
         TopAbs_SHAPE: "Shape"}


def _r(v):
    return round(v, 9) + 0.0                     # make.py rounds -0.0 to 0.0 too


def _ypr(shape):
    return A.Placement.from_trsf(shape.Location().Transformation())


def _measure(shape) -> dict:
    """A TopoDS shape as make.py measures FreeCAD's: kind, counts, bbox, area and volume (not for an infinite
    one), and its placement."""
    if shape is None or shape.IsNull():
        return {"null": True}
    pl = _ypr(shape)
    out = {"type": TYPES[shape.ShapeType()], "solids": feature._count(shape, TopAbs_SOLID),
           "faces": feature._count(shape, TopAbs_FACE), "edges": feature._count(shape, TopAbs_EDGE),
           "vertices": feature._count(shape, TopAbs_VERTEX),
           "placement": [_r(c) for c in (*pl.pos, *pl.rot.ypr())]}
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return out
    lo, hi = box.CornerMin(), box.CornerMax()
    corn = [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()]
    if any(abs(c) > 1e99 for c in corn):
        out["infinite"] = True
        return out
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    vol = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vol)
    out.update({"bbox": [_r(c) for c in corn], "area": _r(props.Mass()), "volume": _r(vol.Mass())})
    return out


def _measure_part(part) -> dict:
    shape = part.wrapped
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    return {"volume": _r(part.volume), "area": _r(part.area),
            "bbox": [_r(c) for c in (lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z())],
            "faces": feature._count(shape, TopAbs_FACE), "edges": feature._count(shape, TopAbs_EDGE),
            "solids": len(part.solids())}


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/binder/make.py in freecadcmd"
    assert len(CASES) >= 14
    assert not [n for n, g in FREECAD.items() if "error" in g]


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_binder_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    ev = feature.evaluate(case["features"], case.get("params"))
    ctx = ev["_attach"]
    assert set(want["binders"]) == {f.name for f in case["features"] if isinstance(f, ShapeBinder)}
    for binder in sorted(want["binders"]):
        w = want["binders"][binder]
        got = _measure(ctx.shapes.get(binder))
        assert ctx.kinds[binder] == "binder"
        if w.get("null"):
            assert got == {"null": True}
            continue
        assert (got["type"], got["solids"], got["faces"], got["edges"], got["vertices"]) == \
            (w["type"], w["solids"], w["faces"], w["edges"], w["vertices"])
        assert got["placement"] == pytest.approx(w["placement"], abs=1e-7)
        # the object's Placement is its shape's (ShapeBinder::execute sets it so)
        pl = ctx.placements[binder]
        assert [_r(c) for c in (*pl.pos, *pl.rot.ypr())] == pytest.approx(w["placement"], abs=1e-7)
        if w.get("infinite"):
            assert got.get("infinite")
        else:
            assert got["bbox"] == pytest.approx(w["bbox"], abs=1e-6)
            assert got["area"] == pytest.approx(w["area"], rel=1e-6, abs=1e-9)
            assert got["volume"] == pytest.approx(w["volume"], rel=1e-6, abs=1e-9)


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_body_and_tip_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    # the binder is not a solid feature: the Body's solid and Tip are what they were before it
    ev = feature.evaluate(case["features"], case.get("params"))
    assert ev["Tip"] is not None
    got = _measure_part(Body(case["features"], case.get("params")))
    w = want["body"]
    assert got["volume"] == pytest.approx(w["volume"], rel=1e-6)
    assert got["area"] == pytest.approx(w["area"], rel=1e-6)
    size = math.dist(w["bbox"][:3], w["bbox"][3:])
    assert got["bbox"] == pytest.approx(w["bbox"], abs=1e-6 * size)
    assert (got["faces"], got["edges"], got["solids"]) == (w["faces"], w["edges"], w["solids"])
    solid = next((f.name for f in reversed(case["features"])
                  if not isinstance(f, ShapeBinder)), None)
    assert want["tip"] == solid


def _plate(tmp_path, name="plate.py"):
    import shutil
    p = tmp_path / name
    shutil.copy(Path(__file__).parent / "fixtures" / "feature_plate" / "parts" / "plate.py", p)
    return p


def test_part_file_round_trip(tmp_path):
    p = _plate(tmp_path)
    src = E.apply_src(p.read_text(), [{
        "op": "add", "after": "Pad",
        "feature": {"name": "Binder", "type": "PartDesign::ShapeBinder", "support": [["Pad", "Face6"]],
                    "trace_support": True}}])
    d = E.read_src(src)
    b = next(f for f in d["features"] if f["name"] == "Binder")
    assert b["type"] == "PartDesign::ShapeBinder"
    assert b["support"] == [["Pad", "Face6"]] and b["trace_support"] is True
    assert d["tip"] == "TiePocket"                    # a binder is never the Tip, even as the last feature
    # the part still builds, and with the binder in it it builds the same solid as without
    import importlib.util

    def build(path):
        spec = importlib.util.spec_from_file_location(f"binder_plate_{path.stem}_{id(path)}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.build(**mod.PARAMS)

    before = build(Path(__file__).parent / "fixtures" / "feature_plate" / "parts" / "plate.py")
    p.write_text(src)
    after = build(p)
    assert (after.volume, after.area) == pytest.approx((before.volume, before.area), rel=1e-12)


def test_part_file_refuses_a_binder_of_a_later_feature(tmp_path):
    p = _plate(tmp_path)
    with pytest.raises(E.FeatureEditError, match="Boss"):
        E.apply_src(p.read_text(), [{
            "op": "add", "after": "Pad",
            "feature": {"name": "Binder", "type": "PartDesign::ShapeBinder", "support": [["Boss", "Face1"]]}}])


def test_binder_support_is_a_reference_list(tmp_path):
    """The binder's support is FreeCAD's PropertyLinkSubList: several elements of one object, and its references()
    names that object once, for feature_edit's order check."""
    b = ShapeBinder("Binder", support=[("Pad", "Face1"), ("Pad", ["Face6", "Edge3"])])
    assert b.support == (("Pad", "Face1"), ("Pad", "Face6"), ("Pad", "Edge3"))
    # one name per Support entry, as Sketch.references() lists attachment_support: the order check reads a set
    assert b.references() == ["Pad", "Pad", "Pad"]
    assert ShapeBinder("B", support=("Pad", "")).support == (("Pad", ""),)
    assert ShapeBinder("B").support == ()
