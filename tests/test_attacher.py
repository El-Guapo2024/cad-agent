"""cad_agent/attacher.py against FreeCAD's attachment engine.

tests/golden/attach/make.py ran FreeCAD 26.3 (3160daf1e2b6)'s Part.AttachEngine on elements of placed shapes (written
next to it as BREP) and a Body's origin features: suggestModes() for each reference set and engine, and
calculateAttachedPlacement() for every mode it suggests, plainly and with an offset, Flip sides and a path
parameter. Here the same references go through attacher.suggest() and attacher.attach().
"""
import json
import math
from pathlib import Path

import pytest

from cad_agent import attacher as A

GOLDEN = Path(__file__).parent / "golden" / "attach"
DATA = json.loads((GOLDEN / "engine.json").read_text())


def _placement(pq):
    pos, q = pq
    return A.Placement(pos, A.Rotation(q))


_SHAPES: dict = {}


def _shape(name):
    if name not in _SHAPES:
        from OCP.BRep import BRep_Builder
        from OCP.BRepTools import BRepTools
        from OCP.TopoDS import TopoDS_Shape
        s = TopoDS_Shape()
        BRepTools.Read_s(s, str(GOLDEN / "shapes" / f"{name}.brep"), BRep_Builder())
        _SHAPES[name] = s
    return _SHAPES[name]


def ref(obj, sub):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeVertex
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Dir, gp_Lin, gp_Pln, gp_Pnt
    from cad_agent.feature_attach import sub_shape
    if obj in DATA["origin"]:
        o = DATA["origin"][obj]
        pl = _placement(o["placement"])
        if o["type"] == "App::Plane":
            s = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))).Shape()
        elif o["type"] == "App::Line":
            s = BRepBuilderAPI_MakeEdge(gp_Lin(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))).Shape()
        else:
            s = BRepBuilderAPI_MakeVertex(gp_Pnt(0, 0, 0)).Shape()
        if o["type"] != "App::Point":
            s.Infinite(True)                    # PartFeature.cpp's _shape.Infinite(Standard_True)
        s = s.Moved(TopLoc_Location(pl.trsf()))
        return A.Ref(s, pl, whole=True, plane=o["type"] == "App::Plane")
    whole = _shape(obj)
    pl = _placement(DATA["shapes"][obj]["placement"])
    if not sub:
        return A.Ref(whole, pl, whole=True)
    return A.Ref(sub_shape(whole, sub), pl)


def _id(c):
    return f"{c['engine']}-{c['mode']}-{c['variant']}-" + "+".join(f"{o}.{s}" for o, s in c["refs"])


@pytest.mark.parametrize("s", DATA["suggestions"], ids=lambda s: f"{s['engine']}-" + "+".join(
    f"{o}.{x}" for o, x in s["refs"]))
def test_suggestions_are_freecads(s):
    refs = [ref(o, x) for o, x in s["refs"]]
    got = A.suggest(s["engine"], [r.type() for r in refs])
    assert got["types"] == s["types"]
    assert got["message"] == s["message"]
    assert got["best"] == s["best"]
    assert got["all"] == s["all"]
    assert got["reachable"] == s["reachable"]
    assert sorted(got["hints"]) == s["hints"]


def _same(a: A.Placement, b: A.Placement, tol=1e-9):
    scale = max(1.0, *(abs(c) for c in b.pos))
    if any(abs(x - y) > tol * scale for x, y in zip(a.pos, b.pos)):
        return False
    dq = sum(x * y for x, y in zip(a.rot.q, b.rot.q))
    return abs(abs(dq) - 1.0) < tol


@pytest.mark.parametrize("c", DATA["cases"], ids=_id)
def test_placements_are_freecads(c):
    refs = [ref(o, x) for o, x in c["refs"]]
    kw = {}
    if c["variant"] == "offset":
        kw = {"offset": _placement(DATA["offset"]), "reversed": True, "parameter": 0.3}
    orig = _placement(DATA["orig"])
    if "error" in c:
        with pytest.raises(A.AttachError):
            A.attach(c["engine"], c["mode"], refs, orig=orig, **kw)
        return
    got = A.attach(c["engine"], c["mode"], refs, orig=orig, **kw)
    if c["placement"] is None:
        assert got is None
        return
    want = _placement(c["placement"])
    # A circle's inertia has an axis of symmetry: its other two principal axes are undefined (FreeCAD warns so),
    # and the eigenvectors OCCT picks for them move with the last bits of the moments; the offset carries that
    # into the position. Those agree to 1e-7, the rest to 1e-9.
    tol = 1e-7 if c["refs"] == [["Cyl", "Edge1"]] and "nertia" in c["mode"] else 1e-9
    assert got is not None and _same(got, want, tol), f"ours {got}, FreeCAD's {want}"


def test_every_mode_is_tried():
    tried = {(c["engine"], c["mode"]) for c in DATA["cases"] if "placement" in c}
    for engine in A.ENGINES:
        missing = [m for m in A.modes(engine)[1:] if (engine, m) not in tried]
        # what the reference sets above cannot reach (no hyperbola asymptote fits a plane, ...)
        assert len(missing) <= {"3D": 0, "Plane": 0, "Line": 0, "Point": 0}[engine], (engine, missing)


def test_rotation_round_trips():
    r = A.Rotation.from_ypr(10, 20, 30)
    y, p, q = r.ypr()
    assert (round(y, 9), round(p, 9), round(q, 9)) == (10, 20, 30)
    m = r.matrix()
    assert all(abs(a - b) < 1e-15 for a, b in zip(A.Rotation.from_matrix(m).q, r.q))
    v = r.mult_vec((1, 2, 3))
    assert abs(math.dist(v, (0, 0, 0)) - math.sqrt(14)) < 1e-12


def test_deactivated_keeps_its_own_placement():
    assert A.attach("Plane", "Deactivated", [ref("Box", "Face1")]) is None
    assert A.attach("Plane", "FlatFace", []) is None


def test_wrong_mode_for_the_engine_is_refused():
    with pytest.raises(A.AttachError, match="not implemented"):
        A.attach("Point", "FlatFace", [ref("Box", "Face1")])
    with pytest.raises(A.AttachError, match="doesn't exist"):
        A.attach("Plane", "Flat", [ref("Box", "Face1")])
