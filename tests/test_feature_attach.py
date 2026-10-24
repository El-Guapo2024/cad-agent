"""Sketches on faces and datums, datum features and external geometry, built as FreeCAD builds them.

tests/golden/attach/bodies.py holds the bodies; make_bodies.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote bodies.json. Here the same lines go through feature.evaluate and must give the same
solid (as tests/test_feature.py measures it), every sketch and datum the Placement FreeCAD's attachment gave it,
every sketch the external geometry FreeCAD projected and the geometry FreeCAD's solver left.
"""
import json
import math
import sys
from pathlib import Path

import pytest
from build123d import Compound, Part, Solid
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_SOLID

from cad_agent import attacher as A
from cad_agent import feature
from cad_agent.feature import (Circle, Constraint, DatumLine, DatumPlane, DatumPoint, FeatureError, Pad,
                               Sketch)

GOLDEN = Path(__file__).parent / "golden" / "attach"
sys.path.insert(0, str(GOLDEN))
from bodies import CASES  # noqa: E402
from cases import base_pad, rect  # noqa: E402  (tests/golden/feature/cases.py, on bodies.py's path)

FREECAD = json.loads((GOLDEN / "bodies.json").read_text())["cases"]


def _measure(shape):
    part = Part(Compound([Solid(s) for s in feature._subs(shape, TopAbs_SOLID)]).wrapped)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    com, vol = [0.0, 0.0, 0.0], 0.0
    for s in part.solids():
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(s.wrapped, props)
        c = props.CentreOfMass()
        vol += props.Mass()
        com = [com[0] + c.X() * props.Mass(), com[1] + c.Y() * props.Mass(), com[2] + c.Z() * props.Mass()]
    faces = []
    for f in feature._faces(shape):
        fp = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, fp)
        fc = fp.CentreOfMass()
        faces.append([fp.Mass(), fc.X(), fc.Y(), fc.Z()])
    return {"volume": part.volume, "area": part.area, "bbox": [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()],
            "center_of_mass": [x / vol for x in com], "solids": len(part.solids()), "faces": len(faces),
            "face_list": faces}


_BUILT: dict = {}


def built(name):
    if name not in _BUILT:
        case = CASES[name]
        _BUILT[name] = feature.evaluate(case["features"], case.get("params"))
    return _BUILT[name]


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/attach/make_bodies.py in freecadcmd"
    assert not [n for n, g in FREECAD.items() if "error" in g or not g["valid"]]


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_solid_as_freecad(name):
    want = FREECAD[name]
    got = _measure(built(name)["Tip"])
    assert got["volume"] == pytest.approx(want["volume"], rel=1e-6)
    assert got["area"] == pytest.approx(want["area"], rel=1e-6)
    size = math.dist(want["bbox"][:3], want["bbox"][3:])
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size)
    assert got["center_of_mass"] == pytest.approx(want["center_of_mass"], abs=1e-6 * size)
    assert (got["solids"], got["faces"]) == (want["solids"], want["faces"])
    key = lambda f: tuple(round(x, 4) for x in f)       # noqa: E731
    assert sorted(map(key, got["face_list"])) == sorted(map(key, want["face_list"]))


def _objects():
    for name in sorted(CASES):
        for obj, rec in FREECAD[name]["objects"].items():
            yield name, obj, rec


def _same(a: A.Placement, pq, tol=1e-9):
    pos, q = pq
    if any(abs(x - y) > tol * max(1.0, abs(y)) for x, y in zip(a.pos, pos)):
        return False
    return abs(abs(sum(x * y for x, y in zip(a.rot.q, q))) - 1.0) < tol


@pytest.mark.parametrize("name,obj,rec", list(_objects()), ids=lambda v: v if isinstance(v, str) else "")
def test_placements_are_freecads(name, obj, rec):
    ctx = built(name)["_attach"]
    assert obj in ctx.placements, f"{obj} was not built"
    got = ctx.placements[obj]
    assert _same(got, rec["placement"]), f"ours {got}, FreeCAD's {A.Placement(rec['placement'][0], A.Rotation(rec['placement'][1]))}"
    if obj in ctx.modes:
        assert ctx.modes[obj] == rec["map_mode"]


def _sketches():
    for name, obj, rec in _objects():
        if rec["type"] == "Sketcher::SketchObject":
            yield name, obj, rec


def _points(g):
    """A geometry's defining points, arcs by their geometric start and end as FreeCAD's StartPoint/EndPoint."""
    t = g["type"]
    if t == "LineSegment":
        return [g["start"], g["end"]]
    if t == "Circle":
        return [g["center"], [g["radius"], 0.0]]
    if t == "Point":
        return [g["at"]]
    if "start" in g:                                  # FreeCAD's record
        s, e = g["start"], g["end"]
        if g.get("axis_z", 1.0) < 0:                  # GeomArcOfCircle runs clockwise: the Sketcher's CCW start
            s, e = e, s
        return [g["center"], [g["radius"], 0.0], s, e]
    c, r = g["center"], g["radius"]
    return [c, [r, 0.0], [c[0] + r * math.cos(g["start_angle"]), c[1] + r * math.sin(g["start_angle"])],
            [c[0] + r * math.cos(g["end_angle"]), c[1] + r * math.sin(g["end_angle"])]]


def _close(a, b, tol):
    return len(a) == len(b) and all(abs(x - y) <= tol for p, q in zip(a, b) for x, y in zip(p, q))


@pytest.mark.parametrize("name,obj,rec", list(_sketches()), ids=lambda v: v if isinstance(v, str) else "")
def test_external_geometry_is_freecads(name, obj, rec):
    sk = built(name)["_sketches"][obj]
    got = list(sk._external)
    assert [g["type"] for g in got] == [g["type"] for g in rec["external"]]
    for g, w in zip(got, rec["external"]):
        assert _close(_points(g), _points(w), 1e-9), (g, w)


@pytest.mark.parametrize("name,obj,rec", list(_sketches()), ids=lambda v: v if isinstance(v, str) else "")
def test_solved_sketch_is_freecads(name, obj, rec):
    sk = built(name)["_sketches"][obj]
    got = [g.as_dict() for g in sk.geometry]
    for g, w in zip(got, rec["geometry"]):
        assert _close(_points(g), _points(w), 1e-9), (g, w)


# ── the vocabulary ──────────────────────────────────────────────────────────────────────────────────────

def test_support_forms_are_the_same_sketch():
    a = Sketch("S", "XZ")
    b = Sketch("S", attachment_support=[("XZ_Plane", "")])
    c = Sketch("S", attachment_support="XZ", map_mode="FlatFace")
    assert a.attachment_support == b.attachment_support == c.attachment_support == [("XZ_Plane", "")]
    assert a.support == b.support == c.support == "XZ"
    d = Sketch("S", attachment_support=[("Pad", ["Face6", "Face2"])], map_mode="MidPlane")
    assert d.attachment_support == [("Pad", "Face6"), ("Pad", "Face2")] and d.support is None
    e = Sketch("S", map_mode="Deactivated", placement=((1, 2, 3), (0, 0, 0)))
    assert e.attachment_support == [] and e.placement()[0] == (1.0, 2.0, 3.0)


def test_attachment_errors_in_freecads_words():
    with pytest.raises(FeatureError, match="map_mode 'Vertex' is not one of"):
        Sketch("S", attachment_support=[("Pad", "Face6")], map_mode="Vertex")
    with pytest.raises(FeatureError, match="no 'Pad' before it"):
        feature.evaluate([Sketch("S", attachment_support=[("Pad", "Face6")]), Pad("Pad", "S")])
    with pytest.raises(FeatureError, match="there is no Face9"):
        feature.evaluate(base_pad() + [Sketch("S2", attachment_support=[("Pad", "Face9")], geometry=rect(1, 1, 2, 2))])
    with pytest.raises(FeatureError, match="No planar face"):
        feature.evaluate([Sketch("S", "XY", [Circle((0.0, 0.0), 5.0)]), Pad("Pad", "S", length=8.0),
                          Sketch("S2", attachment_support=[("Pad", "Face1")])])
    with pytest.raises(FeatureError, match="is the name of the Body's origin"):
        feature.evaluate([DatumPlane("XY_Plane")])


def test_a_datum_keeps_its_placement_unattached():
    shapes = feature.evaluate([DatumLine("L", placement=((1, 2, 3), (90, 0, 0)))])
    pl = shapes["_attach"].placements["L"]
    assert pl.pos == (1.0, 2.0, 3.0) and abs(pl.rot.ypr()[0] - 90) < 1e-9


def test_external_geometry_needs_the_body():
    sk = Sketch("S", "XY", [Circle((1.0, 1.0), 2.0)], [Constraint("Coincident", 0, 3, -3, 1)],
                external_geometry=[("Pad", "Vertex1")])
    with pytest.raises(FeatureError, match="external geometry -3"):
        sk.unsatisfied()
