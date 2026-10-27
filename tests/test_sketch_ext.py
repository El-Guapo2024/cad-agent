"""External geometry beyond the projection of edges, vertices and flat faces, built as FreeCAD's Sketcher builds it.

tests/golden/sketchext/cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote freecad.json. Here the same lines go through feature.evaluate: every sketch must have
FreeCAD's ExternalTypes and external geometry (a face that is not flat through hidden-line removal, the
intersections with the sketch's plane, reversed arcs as FreeCAD keeps them) and FreeCAD's solved geometry. The part
file's form of a reference's type, feature_edit's round trip of it, and Validate's Swap Endpoints in Constraints
(SketchObject::port_reversedExternalArcs) are checked too.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest

from cad_agent import feature
from cad_agent.feature import Constraint, FeatureError, Sketch

GOLDEN = Path(__file__).parent / "golden" / "sketchext"
_spec = importlib.util.spec_from_file_location("sketchext_cases", GOLDEN / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES
FREECAD = json.loads((GOLDEN / "freecad.json").read_text())["cases"]
TYPES = {0: "Projection", 1: "Intersection", 2: "Both"}

_BUILT: dict = {}


def built(name):
    if name not in _BUILT:
        _BUILT[name] = feature.evaluate(CASES[name]["features"])
    return _BUILT[name]


def _points(g):
    """A geometry's defining points; an arc by the Sketcher's counter-clockwise start and end."""
    t = g["type"]
    if t == "LineSegment":
        return [g["start"], g["end"]]
    if t == "Circle":
        return [g["center"], [g["radius"], 0.0]]
    if t == "Point":
        return [g["at"]]
    if t == "BSplineCurve":
        return [*g["poles"], *[[k, m] for k, m in zip(g["knots"], g["mults"])], [g["degree"], float(g["periodic"])],
                *[[w, 0.0] for w in (g.get("weights") or [1.0] * len(g["poles"]))]]
    if t in ("Ellipse", "ArcOfEllipse"):
        x = g["x_axis"]
        out = [g["center"], [g["major_radius"], g["minor_radius"]], x]
        if t == "Ellipse":
            return out
        if "start" in g:
            s, e = (g["end"], g["start"]) if g.get("axis_z", 1.0) < 0 else (g["start"], g["end"])
            return out + [s, e]
        c, a, b, y = g["center"], g["major_radius"], g["minor_radius"], [-x[1], x[0]]
        at = lambda u: [c[0] + a * math.cos(u) * x[0] + b * math.sin(u) * y[0],  # noqa: E731
                        c[1] + a * math.cos(u) * x[1] + b * math.sin(u) * y[1]]
        return out + [at(g["start_angle"]), at(g["end_angle"])]
    if "start" in g:                                  # FreeCAD's record
        s, e = (g["end"], g["start"]) if g.get("axis_z", 1.0) < 0 else (g["start"], g["end"])
        return [g["center"], [g["radius"], 0.0], s, e]
    c, r = g["center"], g["radius"]
    return [c, [r, 0.0], [c[0] + r * math.cos(g["start_angle"]), c[1] + r * math.sin(g["start_angle"])],
            [c[0] + r * math.cos(g["end_angle"]), c[1] + r * math.sin(g["end_angle"])]]


def _close(a, b, tol):
    return len(a) == len(b) and all(abs(x - y) <= tol * max(1.0, abs(y)) for p, q in zip(a, b) for x, y in zip(p, q))


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/sketchext/make.py in freecadcmd"
    assert not [n for n, g in FREECAD.items() if g.get("error")]


@pytest.mark.parametrize("name", sorted(CASES))
def test_external_types_are_freecads(name):
    sk = next(f for f in CASES[name]["features"] if f.name == "Sketch001")
    assert sk.external_types == [TYPES[t] for t in FREECAD[name]["types"]]
    assert [list(r) for r in sk.external_geometry] == FREECAD[name]["refs"]


@pytest.mark.parametrize("name", sorted(CASES))
def test_external_geometry_is_freecads(name):
    got = built(name)["_sketches"]["Sketch001"]._external
    want = FREECAD[name]["external"]
    assert [g["type"] for g in got] == [g["type"] for g in want]
    for g, w in zip(got, want):
        assert _close(_points(g), _points(w), 1e-7), (g, w)
        if g["type"] == "ArcOfCircle":                # GeomArcOfConic::isReversed
            assert bool(g.get("reversed")) == (w["axis_z"] < 0), (g, w)


@pytest.mark.parametrize("name", sorted(CASES))
def test_solved_sketch_is_freecads(name):
    got = [g.as_dict() for g in built(name)["_sketches"]["Sketch001"].geometry]
    want = FREECAD[name]["geometry"]
    assert len(got) == len(want)
    for g, w in zip(got, want):
        assert _close(_points(g), _points(w), 1e-7), (g, w)


# ── the part file ────────────────────────────────────────────────────────────────────────────────────────

def test_reference_types_in_the_part_file():
    s = Sketch("S", "XY", external_geometry=[("Pad", "Edge3"), ("Pad", "Face1", "Intersection"), "Pad.Face2:Both"])
    assert s.external_geometry == [("Pad", "Edge3"), ("Pad", "Face1"), ("Pad", "Face2")]
    assert s.external_types == ["Projection", "Intersection", "Both"]
    with pytest.raises(FeatureError, match="'Intersection' or 'Both'"):
        Sketch("S", "XY", external_geometry=[("Pad", "Face1", "Section")])


SRC = '''from cad_agent.feature import Circle, Constraint, Pad, Sketch

FEATURES = [
    Sketch("Sketch", "XY", [Circle((0.0, 0.0), 5.0)], [Constraint("Coincident", 0, 3, -1, 1)]),
    Pad("Pad", "Sketch", length=8.0),
    Sketch("Sketch001", "XZ", [], [], external_geometry=[("Pad", "Face1", "Intersection")]),
]
'''


def test_feature_edit_round_trip(tmp_path):
    from cad_agent import feature_edit
    p = tmp_path / "p.py"
    p.write_text(SRC)
    doc = feature_edit.read(p)
    sk = next(f for f in doc["features"] if f["name"] == "Sketch001")
    assert sk["external_geometry"] == [["Pad", "Face1", "Intersection"]]
    feature_edit.apply(p, [{"op": "set", "name": "Sketch001",
                            "props": {"external_geometry": [["Pad", "Face1", "Both"], ["Pad", "Edge3"]]}}])
    text = p.read_text()
    assert 'external_geometry=[("Pad", "Face1", "Both"), ("Pad", "Edge3")]' in text
    sk = next(f for f in feature_edit.read(p)["features"] if f["name"] == "Sketch001")
    assert sk["external_geometry"] == [["Pad", "Face1", "Both"], ["Pad", "Edge3"]]


def test_project_query_takes_a_type(tmp_path):
    from cad_agent.feature_attach import project_query
    p = tmp_path / "p.py"
    p.write_text(SRC)
    out = project_query(p, "Sketch001", ["Pad.Face1:Intersection", "Pad.Face1"])
    assert [[g["type"] for g in gs] for gs in out["external"]] == [
        ["LineSegment", "LineSegment"], ["LineSegment", "BSplineCurve", "BSplineCurve", "LineSegment",
                                         "BSplineCurve", "BSplineCurve"]]


# ── Validate: reversed external arcs ──────────────────────────────────────────────────────────────────────

def test_swap_endpoints_in_constraints():
    from cad_agent.feature_attach_ext import swap_reversed
    from cad_agent.sketch_commands import reversed_external_arcs
    ext = built("reversed_arc_two")["_sketches"]["Sketch001"]._external
    assert [bool(g.get("reversed")) for g in ext] == [True, True]
    cons = [{"type": "Coincident", "first": 0, "first_pos": 1, "second": -4, "second_pos": 2, "third": -2000,
             "third_pos": 0},
            {"type": "Coincident", "first": 0, "first_pos": 2, "second": -3, "second_pos": 1, "third": -2000,
             "third_pos": 0},
            {"type": "Distance", "first": 0, "first_pos": 0, "second": -2000, "second_pos": 0, "third": -2000,
             "third_pos": 0}]
    pts, n = reversed_external_arcs(ext, cons)
    assert (len(pts), n) == (4, 2)
    out, n = swap_reversed(ext, cons)
    assert n == 2
    assert [(c["second"], c["second_pos"]) for c in out[:2]] == [(-4, 1), (-3, 2)]
    assert out[2] == cons[2]


REVERSED_SRC = '''import math
from cad_agent.feature import ArcOfCircle, Circle, Constraint, LineSegment, Pad, Sketch

FEATURES = [
    Sketch("Sketch", attachment_support=[("XY_Plane", "")], map_mode="FlatFace", map_reversed=True,
           geometry=[ArcOfCircle((0.0, 0.0), 5.0, 0.0, 3.141592654), LineSegment((-5.0, 0.0), (5.0, 0.0))],
           constraints=[Constraint("Coincident", 0, 1, 1, 2), Constraint("Coincident", 0, 2, 1, 1)]),
    Pad("Pad", "Sketch", length=4.0),
    Sketch("Sketch001", attachment_support=[("XY_Plane", "")], map_mode="FlatFace",
           attachment_offset=((0.0, 0.0, 6.0), (0.0, 0.0, 0.0)), external_geometry=[("Pad", "Edge3")],
           geometry=[LineSegment((5.0, 0.0), (25.0, 24.0))], constraints=[Constraint("Coincident", 0, 1, -3, 1)]),
]
'''


def test_validate_swaps_reversed_arcs(tmp_path):
    """Find: the reversed arc's two ends and the one constraint on them; Swap Endpoints in Constraints: the
    constraint on its other end, the line's start moved there, in "Sketch porting"."""
    from cad_agent.sketch_commands import validate
    p = tmp_path / "p.py"
    p.write_text(REVERSED_SRC)
    found = validate(p, "Sketch001", "reversed")
    assert len(found["points"]) == 2 and found["constraints"] == 1
    assert found["notification"]["kind"] == "warning"
    out = validate(p, "Sketch001", "reversed", fix=True)
    assert out["step"] == "Sketch porting"
    assert out["notification"]["text"] == "1 changes were made to constraints linking to endpoints of reversed arcs."
    props = out["ops"][0]["props"]
    assert props["constraints"][0]["args"] == [0, 1, -3, 2]
    start = props["geometry"][0]["start"]
    assert math.dist(start, (-5.0, 0.0)) < 1e-9         # from the start, (5, 0), to the arc's other end
