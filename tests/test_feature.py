"""cad_agent.feature builds what FreeCAD's PartDesign builds, from the same FEATURES lines.

tests/golden/feature/cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote freecad.json. Here the same lines go through feature.Body and must give the same
solid: volume and area to 1e-6 relative, the bounding box and centre of mass to 1e-6 of the box's size, the same
number of solids and faces, and the same faces (area and centre).
"""
import json
import math
import sys
import types
from pathlib import Path

import pytest
from build123d import Box, Pos
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from cad_agent import feature
from cad_agent.feature import (Body, Circle, Constraint, FeatureError, LineSegment, Pad, Pocket, Sketch)

GOLDEN = Path(__file__).parent / "golden" / "feature"
sys.path.insert(0, str(GOLDEN))
from cases import CASES, rect, rect_constraints  # noqa: E402

FREECAD = json.loads((GOLDEN / "freecad.json").read_text())["cases"]


def _base(case):
    if not case.get("base"):
        return None
    _, p, s = case["base"]
    return Pos(p[0] + s[0] / 2, p[1] + s[1] / 2, p[2] + s[2] / 2) * Box(*s)


def _measure(part):
    shape = part.wrapped
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    com, vol = [0.0, 0.0, 0.0], 0.0                  # weighted over the solids, as make.py takes FreeCAD's
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
    return {"volume": part.volume, "area": part.area,
            "bbox": [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()],
            "center_of_mass": [x / vol for x in com], "solids": len(part.solids()), "faces": len(faces),
            "face_list": faces}


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/feature/make.py in freecadcmd"
    assert len(CASES) >= 40
    assert not [n for n, g in FREECAD.items() if "error" in g or not g["valid"]]


# Where the refine differs: FreeCAD refines with its own BRepBuilderAPI_RefineModel, this module with OCCT's
# UnifySameDomain. They make the same solid; here FreeCAD also merges the hole's two half cylinders (one the
# mirror of the other, as a symmetric pocket that is not a Length builds them) and UnifySameDomain does not.
REFINE_DIFFERS = {"pocket_symmetric_through_all": 8}


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_solid_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    got = _measure(Body(case["features"], case.get("params"), base=_base(case)))
    assert got["volume"] == pytest.approx(want["volume"], rel=1e-6)
    assert got["area"] == pytest.approx(want["area"], rel=1e-6)
    size = math.dist(want["bbox"][:3], want["bbox"][3:])
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size)
    assert got["center_of_mass"] == pytest.approx(want["center_of_mass"], abs=1e-6 * size)
    if name in REFINE_DIFFERS:
        assert (got["solids"], got["faces"]) == (want["solids"], REFINE_DIFFERS[name])
        return
    assert (got["solids"], got["faces"]) == (want["solids"], want["faces"])
    key = lambda f: tuple(round(x, 4) for x in f)       # noqa: E731
    assert sorted(map(key, got["face_list"])) == sorted(map(key, want["face_list"]))


# Mostly the faces come in FreeCAD's order too, so an UpToFace written ("Pad", "Face6") names the face
# FreeCAD's Face6 is. In these the faces are the same but their order is not: after a fuse with the refine
# merging faces, UnifySameDomain numbers them otherwise than FreeCAD's own refine does.
ORDER_DIFFERS = {"pad_up_to_last", "pad_up_to_last_step", "pad_up_to_first_wide", "pad_up_to_face",
                 "pad_up_to_face_larger", "pad_up_to_shape_face", "pad_symmetric_up_to_face",
                 "pad_two_sides_up_to", "pocket_symmetric_through_all", "pad_pad_refine", "base_box_pad"}
SAME_ORDER = sorted(set(CASES) - ORDER_DIFFERS)


def test_face_names_differ_only_where_known():
    assert len(SAME_ORDER) >= 45


@pytest.mark.parametrize("name", SAME_ORDER)
def test_face_names_are_freecads(name):
    case, want = CASES[name], FREECAD[name]
    got = _measure(Body(case["features"], case.get("params"), base=_base(case)))
    assert [[round(x, 4) for x in f] for f in got["face_list"]] == \
        [[round(x, 4) for x in f] for f in want["face_list"]]


# ── profiles FreeCAD refuses, or that are refused here ────────────────────────────────────────────

def _pad(geometry, **kw):
    return Body([Sketch("Sketch", "XY", geometry), Pad("Pad", "Sketch", **kw)])


def test_open_profile_is_freecads_error():
    with pytest.raises(FeatureError, match=r"^Wire is not closed\.$"):
        _pad(rect(0, 0, 10, 10)[:3])
    with pytest.raises(FeatureError, match=r"^Wire is not closed\.$"):        # a dangling line
        _pad(rect(0, 0, 10, 10) + [LineSegment((20, 0), (30, 0))])


@pytest.mark.parametrize("geometry", [
    rect(0, 0, 10, 10) + rect(5, 5, 15, 15),                                   # two squares overlap
    [LineSegment((0, 0), (10, 10)), LineSegment((10, 10), (10, 0)),           # a bow tie
     LineSegment((10, 0), (0, 10)), LineSegment((0, 10), (0, 0))],
    rect(0, 0, 10, 10) + [Circle((10, 5), 3)],                                # a circle across an edge
    rect(0, 0, 10, 10) + [Circle((5, 5), 5)],                                 # a circle touching four
])
def test_crossing_profile_is_an_error(geometry):
    with pytest.raises(FeatureError, match="Intersecting sketch entities or multiple faces"):
        _pad(geometry)


def test_construction_geometry_and_points_are_not_profile():
    geometry = rect(0, 0, 10, 10) + rect(-5, -5, 20, 20, construction=True) + [feature.Point((50, 50))]
    assert _pad(geometry, length=2).volume == pytest.approx(200)


def test_feature_errors_in_freecads_words():
    with pytest.raises(FeatureError, match="total length of zero"):
        _pad(rect(0, 0, 10, 10), length=0)
    with pytest.raises(FeatureError, match="No faces found in this direction"):
        _pad(rect(0, 0, 10, 10), type="UpToFirst")
    with pytest.raises(FeatureError, match="not one of Length, UpToLast"):
        Pad("Pad", "Sketch", type="ThroughAll")                # a Pocket's type, not a Pad's
    with pytest.raises(FeatureError, match="Pocket needs a solid"):
        Body([Sketch("Sketch", "XY", rect(0, 0, 10, 10)), Pocket("Pocket", "Sketch")])
    with pytest.raises(FeatureError, match="PARAMS has no 'thick'"):
        _pad(rect(0, 0, 10, 10), length="thick")
    with pytest.raises(FeatureError, match="no sketch 'Nope'"):
        Body([Pad("Pad", "Nope")])
    with pytest.raises(FeatureError, match="Must not be parallel"):
        Body([Sketch("S", "XY", rect(0, 0, 10, 10), attachment_offset=(0, 0, 5)),
              Pad("Pad", "S", type="UpToFace", up_to_face="XZ_Plane")])


def test_deprecated_forms_are_their_side_types():
    assert Pad("P", "S", midplane=True).side_type == "Symmetric"
    p = Pad("P", "S", type="TwoLengths", length=4, length2=1)
    assert (p.side_type, p.type) == ("Two sides", "Length")
    assert _pad(rect(0, 0, 10, 10), type="TwoLengths", length=4, length2=1).bounding_box().min.Z == \
        pytest.approx(-1)


def test_values_are_numbers_or_params():
    assert feature.value("w / 2 + 1", {"w": 10}) == 6.0
    assert feature.value(3, None) == 3.0
    with pytest.raises(FeatureError, match="can only use"):
        feature.value("__import__('os')", {})
    # an angle bound to PARAMS is in degrees, as a unitless FreeCAD expression is; a literal is radians
    assert Constraint("Angle", 0, 1, "a").resolved({"a": 90}) == pytest.approx(math.pi / 2)
    assert Constraint("Angle", 0, 1, 0.5).resolved({}) == 0.5


# ── solving: stored geometry needs no solver; a changed value goes through the one seam ────────────

def _plate(width):
    return [Sketch("Sketch", "XY", rect(0, 0, 40, 20), rect_constraints(0, "width", 20.0)),
            Pad("Pad", "Sketch", length=5.0)]


def test_satisfied_sketch_builds_without_a_solver(monkeypatch):
    def no(*a, **k):
        raise AssertionError("the solver was called")
    monkeypatch.setattr(feature, "_solve", no)
    assert Body(_plate(40), {"width": 40.0}).volume == pytest.approx(4000)


def test_changed_value_is_solved_through_planegcs(monkeypatch):
    calls = []

    def solve(sk):                     # a stand-in for cad_agent.planegcs: stretch the rectangle in x
        calls.append(sk)
        w = next(c["value"] for c in sk["constraints"] if c["type"] == "DistanceX")
        geo = []
        for g in sk["geometry"]:
            g = dict(g)
            for k in ("start", "end"):
                if g[k][0] > 0:
                    g[k] = [w, g[k][1]]
            geo.append(g)
        return {"status": "solved", "geometry": geo, "dof": 0}

    monkeypatch.setitem(sys.modules, "cad_agent.planegcs", types.SimpleNamespace(solve=solve))
    part = Body(_plate(40), {"width": 55.0})
    assert part.volume == pytest.approx(55 * 20 * 5)
    assert len(calls) == 1
    assert calls[0]["constraints"][8] == {"type": "DistanceX", "args": [0, 1, 0, 2], "value": 55.0,
                                          "driving": True, "name": ""}
    assert calls[0]["geometry"][0] == {"type": "LineSegment", "start": [0.0, 0.0], "end": [40.0, 0.0],
                                       "construction": False}


def test_a_solver_that_misses_is_reported(monkeypatch):
    monkeypatch.setitem(sys.modules, "cad_agent.planegcs",
                        types.SimpleNamespace(solve=lambda sk: {"status": "solved", "geometry": sk["geometry"]}))
    with pytest.raises(FeatureError, match="the solver's result still misses constraint 8"):
        Body(_plate(40), {"width": 55.0})
    monkeypatch.setitem(sys.modules, "cad_agent.planegcs", types.SimpleNamespace(
        solve=lambda sk: {"status": "conflicting", "geometry": sk["geometry"], "conflicting": [4, 8]}))
    with pytest.raises(FeatureError, match=r"Sketch with conflicting constraints \(constraints 4, 8\)"):
        Body(_plate(40), {"width": 55.0})


def test_missing_solver_says_why(monkeypatch):
    monkeypatch.setitem(sys.modules, "cad_agent.planegcs", None)     # import fails
    with pytest.raises(FeatureError, match=r"constraint 8 \(DistanceX\): is 40 mm, wants 55.*not installed"):
        Body(_plate(40), {"width": 55.0})


def test_residuals_of_the_constraints():
    sk = Sketch("S", "XY", [LineSegment((0, 0), (10, 0)), LineSegment((10, 0), (10, 5)),
                            Circle((3, 3), 2), feature.ArcOfCircle((0, 0), 5, 0, math.pi / 2),
                            feature.Point((5, 0))])
    ok = [Constraint("Coincident", 0, 2, 1, 1), Constraint("Horizontal", 0), Constraint("Vertical", 1),
          Constraint("Perpendicular", 0, 1), Constraint("Distance", 0, 10.0), Constraint("DistanceX", 0, 2, 10),
          Constraint("DistanceY", 1, 1, 1, 2, 5), Constraint("Radius", 2, 2), Constraint("Diameter", 3, 10),
          Constraint("Angle", 1, math.pi / 2), Constraint("Angle", 0, 1, math.pi / 2),
          Constraint("PointOnObject", 0, 1, -1), Constraint("PointOnObject", 3, 1, -1),
          Constraint("Distance", 2, 3, 0, 3.0), Constraint("Coincident", 3, 3, -1, 1),
          Constraint("Symmetric", 0, 1, 0, 2, 4, 1), Constraint("Angle", 3, math.pi / 2)]
    bad = [Constraint("Parallel", 0, 1), Constraint("Equal", 0, 1), Constraint("DistanceX", 0, 1, 0, 2, 11),
           Constraint("Tangent", 0, 2), Constraint("Symmetric", 0, 1, 0, 2, -2)]
    sk.constraints = ok + bad
    got = sk.unsatisfied()
    assert [g.split(":")[0] for g in got] == [f"constraint {i} ({c.type})" for i, c in enumerate(ok + bad)
                                             if c in bad]
    assert Sketch("S", "XY", sk.geometry, [Constraint("InternalAlignment", 0, 1, 2)]).unsatisfied() == \
        ["constraint 0 (InternalAlignment): cannot be checked without the solver"]


def test_planes_are_freecads():
    # FreeCAD's XZ sketch: x along X, y along Z, normal -Y; YZ: x along Y, y along Z, normal +X
    assert Sketch("S", "XZ").placement()[1] == ((1, 0, 0), (0, 0, -1), (0, 1, 0))
    assert Sketch("S", "YZ").normal() == (1, 0, 0)
    bb = Body([Sketch("S", "XZ", rect(0, 0, 4, 2)), Pad("P", "S", length=1)]).bounding_box()
    assert (bb.min.Y, bb.max.Y, bb.max.Z) == pytest.approx((-1, 0, 2))
