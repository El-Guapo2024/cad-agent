"""cad_agent.feature_dressup builds the Fillet, Chamfer, Draft and Thickness FreeCAD's PartDesign builds.

tests/golden/dressup/dressup_cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote freecad.json. The same lines go through feature.Body here and must give the same
solid (volume, area, box, centre of mass, counts), the same faces and edges in the same order (FreeCAD's FaceN
and EdgeN), and every base feature numbered as FreeCAD numbers it, so a Base written ("Pad", ["Edge3"]) names
the edge FreeCAD's Edge3 is. FOLLOW: after an edit that renumbers the base, follow() rewrites the names as
FreeCAD's topological naming does.
"""
import json
import math
import sys
from pathlib import Path

import pytest
from build123d import Box, Pos
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE

from cad_agent import feature, feature_dressup as D
from cad_agent.feature import Body, FeatureError

GOLDEN = Path(__file__).parent / "golden" / "dressup"
sys.path.insert(0, str(GOLDEN))
from dressup_cases import CASES, FOLLOW  # noqa: E402

DATA = json.loads((GOLDEN / "freecad.json").read_text())
FREECAD, FC_FOLLOW = DATA["cases"], DATA["follow"]


def _base(case):
    if not case.get("base"):
        return None
    _, p, s = case["base"]
    return Pos(p[0] + s[0] / 2, p[1] + s[1] / 2, p[2] + s[2] / 2) * Box(*s)


def _props(s, linear):
    p = GProp_GProps()
    (BRepGProp.LinearProperties_s if linear else BRepGProp.SurfaceProperties_s)(s, p)
    c = p.CentreOfMass()
    return [p.Mass(), c.X(), c.Y(), c.Z()]


def _elements(shape):
    return ([_props(f, False) for f in feature._faces(shape)],
            [_props(e, True) for e in feature._subs(shape, TopAbs_EDGE)])


def _measure(part):
    shape = part.wrapped
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
    faces, edges = _elements(shape)
    return {"volume": part.volume, "area": part.area, "bbox": [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()],
            "center_of_mass": [x / vol for x in com], "solids": len(part.solids()), "faces": len(faces),
            "edges": len(edges), "face_list": faces, "edge_list": edges}


def _r(lst):
    return [[round(x, 4) + 0.0 for x in f] for f in lst]


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD)
    assert set(FOLLOW) == set(FC_FOLLOW)
    assert len(CASES) >= 45


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_solid_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    if "error" in want:
        with pytest.raises(FeatureError) as e:
            Body(case["features"], case.get("params"), base=_base(case))
        assert str(e.value) in want["error"], (str(e.value), want["error"])
        return
    got = _measure(Body(case["features"], case.get("params"), base=_base(case)))
    assert math.isclose(got["volume"], want["volume"], rel_tol=1e-6, abs_tol=1e-6)
    assert math.isclose(got["area"], want["area"], rel_tol=1e-6, abs_tol=1e-6)
    size = max(b - a for a, b in zip(want["bbox"][:3], want["bbox"][3:]))
    for g, w in zip(got["bbox"] + got["center_of_mass"], want["bbox"] + want["center_of_mass"]):
        assert abs(g - w) <= 1e-6 * size + 1e-7, (got["bbox"], want["bbox"])
    assert (got["solids"], got["faces"], got["edges"]) == (want["solids"], want["faces"], want["edges"])


# The same faces and edges, in another order (ui/PARITY.md, PartDesign). An outward Thickness with arc joins is
# numbered by BRepOffset's maps, which follow memory addresses: FreeCAD itself gives two orders for the same body
# built four times in one session, and Part.makeThickness on the same Pad too. (RectoVerso, two of them fused,
# gives FreeCAD's order since the fuse takes FreeCAD's tolerance.)
ORDER_DIFFERS = {"thickness_outwards"}


@pytest.mark.parametrize("name", sorted(n for n in CASES if "error" not in FREECAD[n] and n not in ORDER_DIFFERS))
def test_face_and_edge_names_are_freecads(name):
    case, want = CASES[name], FREECAD[name]
    got = _measure(Body(case["features"], case.get("params"), base=_base(case)))
    assert _r(got["face_list"]) == _r(want["face_list"])
    assert _r(got["edge_list"]) == _r(want["edge_list"])


@pytest.mark.parametrize("name", sorted(n for n in CASES if "error" not in FREECAD[n]))
def test_bases_are_numbered_as_freecad(name):
    """Every solid feature's own faces and edges, so the Base names in the cases are FreeCAD's."""
    case, want = CASES[name], FREECAD[name]
    shapes = feature.evaluate(case["features"], case.get("params"), getattr(_base(case), "wrapped", None))
    for fname, w in want["bases"].items():
        if fname not in shapes or (name in ORDER_DIFFERS and fname == "Thickness"):
            continue
        faces, edges = _elements(shapes[fname])
        assert _r(faces) == _r(w["face_list"]), fname
        assert _r(edges) == _r(w["edge_list"]), fname


@pytest.mark.parametrize("name", sorted(FOLLOW))
def test_follow_renames_as_freecad(name):
    case, want = FOLLOW[name], FC_FOLLOW[name]
    moved = D.follow(case["features"], case["after"], case.get("params"), case.get("params"))
    got = {}
    for f in case["after"]:
        if isinstance(f, D._DressUp):
            b = moved.get(f.name, f.base)
            got[f.name] = [b[0], list(b[1])]
    assert got == want["bases"]


def test_follow_leaves_unchanged_bases_alone():
    case = FOLLOW["reorder_fillet"]
    assert D.follow(case["features"], case["features"]) == {}


def test_follow_reroutes_a_moved_base():
    """A Pocket put between the Pad and the Fillet: the Fillet's Base becomes the Pocket, the edge found
    again on it (FreeCAD's onBaseFeatureRerouted / relinkToMatchingSubelements)."""
    from cad_agent.feature import Circle, Pocket, Sketch
    before = CASES["fillet_edge"]["features"]
    after = before[:2] + [Sketch("Hole", "XY", [Circle((20.0, 10.0), 3.0)]),
                          Pocket("Pocket", "Hole", type="ThroughAll", reversed=True)] + before[2:]
    moved = D.follow(before, after)
    assert moved["Fillet"][0] == "Pocket"
    old = feature.evaluate(before)["Pad"]
    new = feature.evaluate(after[:4])["Pocket"]
    sub = moved["Fillet"][1][0]
    assert _r([_props(D._sub_shape(new, sub, ""), True)]) == _r([_props(D._sub_shape(old, "Edge1", ""), True)])
    Body(after[:4] + [D.Fillet("Fillet", moved["Fillet"])])


def test_base_must_be_the_solid_before():
    f = CASES["fillet_edge"]["features"]
    with pytest.raises(FeatureError, match="Invalid edge link"):
        Body(f + [D.Fillet("Fillet001", ("Pad", ["Edge2"]))])


def test_bad_values_are_refused():
    with pytest.raises(FeatureError, match="chamfer_type"):
        D.Chamfer("C", ("Pad", ["Edge1"]), chamfer_type="Equal")
    with pytest.raises(FeatureError, match="mode"):
        D.Thickness("T", ("Pad", ["Face1"]), mode="Skinny")
    with pytest.raises(FeatureError, match="Base"):
        D.Fillet("F", ("Pad", ["Edge0"]))
    with pytest.raises(FeatureError, match="neutral_plane"):
        D.Draft("D", ("Pad", ["Face1"]), neutral_plane="XY")
