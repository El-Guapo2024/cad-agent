"""Conics and B-splines in a feature list (cad_agent/feature_curves.py) build what FreeCAD's PartDesign builds.

tests/golden/feature_curves/cases.py holds the bodies: ellipses, arcs of ellipse, hyperbola and parabola closed
by lines, clamped, rational and periodic B-splines, holes, pockets, mixes, most with the internal geometry
FreeCAD exposes for them. make.py built each in FreeCAD 26.3 (3160daf1e2b6) through feature.to_freecad and wrote
freecad.json. Here the same lines go through feature.Body and must give the same solid (volume and area to 1e-6
relative, bounding box and centre of mass to 1e-6 of the box's size, the same solids, faces and edges, the same
faces); the stored geometry must satisfy its constraints as checked here and as FreeCAD's solver sees it (it
leaves the geometry where it was), so the build needs no solver; and the part file must carry the curves
through feature_edit without loss.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE

from cad_agent import feature, feature_curves
from cad_agent import feature_edit as E
from cad_agent.feature import (ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, Body, BSplineCurve, Circle, Constraint,
                               Ellipse, FeatureError, LineSegment, Pad, Point, Sketch)

GOLDEN = Path(__file__).parent / "golden" / "feature_curves"
# by a name of its own: tests/golden/feature/cases.py is `cases` to tests/test_feature.py
_spec = importlib.util.spec_from_file_location("feature_curves_cases", GOLDEN / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES, closed_by_line, exposed = _cases.CASES, _cases.closed_by_line, _cases.exposed
from test_workbench import demo  # noqa: E402,F401 (the project fixture)

FREECAD = json.loads((GOLDEN / "freecad.json").read_text())["cases"]

# Where FreeCAD's solve moves the stored geometry: a B-spline with exactly one weight of 1 (Sketch.cpp's OCC
# hack), so these sketches go through the solver here too, and come out where FreeCAD's do.
SOLVED = {"pad_bspline_one_weight_one", "pad_bspline_one_weight_one_bare"}


def _need_planegcs():
    from cad_agent import planegcs
    if not planegcs.available():
        pytest.skip("libplanegcs is not built (ui/planegcs/build.sh native)")


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
    faces = []
    for f in feature._faces(shape):
        fp = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, fp)
        fc = fp.CentreOfMass()
        faces.append([fp.Mass(), fc.X(), fc.Y(), fc.Z()])
    return {"volume": part.volume, "area": part.area, "bbox": [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()],
            "center_of_mass": [x / vol for x in com], "solids": len(part.solids()), "faces": len(faces),
            "edges": feature._count(shape, TopAbs_EDGE), "face_list": faces}


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/feature_curves/make.py in freecadcmd"
    assert len(CASES) >= 25
    assert not [n for n, g in FREECAD.items() if "error" in g or not g["valid"]]


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_solid_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    if name in SOLVED:
        _need_planegcs()
    got = _measure(Body(case["features"], case.get("params")))
    assert got["volume"] == pytest.approx(want["volume"], rel=1e-6)
    assert got["area"] == pytest.approx(want["area"], rel=1e-6)
    size = math.dist(want["bbox"][:3], want["bbox"][3:])
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size)
    assert got["center_of_mass"] == pytest.approx(want["center_of_mass"], abs=1e-6 * size)
    assert (got["solids"], got["faces"], got["edges"]) == (want["solids"], want["faces"], want["edges"])
    left = list(want["face_list"])                      # the same faces: each of ours is one of FreeCAD's
    for f in got["face_list"]:
        match = [w for w in left if all(abs(a - b) <= 1e-6 * max(1.0, abs(b)) + 1e-6 * size for a, b in zip(f, w))]
        assert match, f"face {f} is not one of FreeCAD's {left}"
        left.remove(match[0])


def _sketches(name):
    return [f for f in CASES[name]["features"] if isinstance(f, Sketch)]


def _same_geometry(ours, theirs, tol=1e-6):
    """Our geometry and FreeCAD's after its recompute: the same curve (an arc of ellipse's parameters may
    come back a turn apart)."""
    if ours["type"] != theirs["type"]:
        return False
    for k, v in theirs.items():
        if k == "type":
            continue
        o = ours[k]
        if k in ("start_angle", "end_angle") and ours["type"] == "ArcOfEllipse":
            d = (o - v + math.pi) % (2 * math.pi) - math.pi
            if abs(d) > tol:
                return False
        elif isinstance(v, list):
            flat = lambda x: [c for e in x for c in (e if isinstance(e, list) else [e])]   # noqa: E731
            if any(abs(a - b) > tol for a, b in zip(flat(o), flat(v))) or len(flat(o)) != len(flat(v)):
                return False
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            if abs(o - v) > tol:
                return False
        elif o != v:
            return False
    return True


@pytest.mark.parametrize("name", sorted(set(CASES) - SOLVED))
def test_stored_geometry_satisfies_its_constraints(name):
    """Every constraint checks here without the solver, and FreeCAD's solver leaves the geometry where it was."""
    for sk in _sketches(name):
        assert sk.unsatisfied(CASES[name].get("params")) == [], sk.name
        fc = FREECAD[name]["sketches"][sk.name]
        assert (fc["solve"], fc["malformed"], fc["conflicting"], fc["redundant"]) == (0, [], [], [])
        moved = [i for i, (g, h) in enumerate(zip(sk.geometry, fc["geometry"]))
                 if not _same_geometry(g.as_dict(), h)]
        assert moved == [] and len(sk.geometry) == len(fc["geometry"]), (sk.name, moved)


def test_the_internal_geometry_cases_check_every_alignment():
    seen = {c.type for n in CASES for sk in _sketches(n) for c in sk.constraints}
    assert {"InternalAlignment:" + k for k in feature_curves.ALIGNMENTS} <= seen
    assert {"Weight", "Equal"} <= seen


def test_satisfied_sketches_build_without_the_solver(monkeypatch):
    def no(*a, **k):
        raise AssertionError("the solver was called")
    monkeypatch.setattr(feature, "_solve", no)
    for name in sorted(set(CASES) - SOLVED):
        Body(CASES[name]["features"], CASES[name].get("params"))


@pytest.mark.parametrize("name", sorted(SOLVED))
def test_one_weight_of_one_is_solved_as_freecad_solves_it(name):
    _need_planegcs()
    sk =_sketches(name)[0]
    assert sk.unsatisfied() and "exactly one weight is 1" in sk.unsatisfied()[-1]
    solved = sk.solved()
    fc = FREECAD[name]["sketches"][sk.name]["geometry"]
    assert _same_geometry(solved.geometry[0].as_dict(), fc[0], tol=1e-5)


# ── the residual checks: each alignment is caught when it does not hold ──────────────────────────────────

def _alignment_sketches():
    out = []
    for name in sorted(CASES):
        for sk in _sketches(name):
            if any(c.type.startswith("InternalAlignment:") or c.type == "Weight" for c in sk.constraints):
                out.append((name, sk))
    return out


def _moved(g, d=0.01):
    """g with its first point (or its centre) moved by d along x."""
    a = g.as_dict()
    for k in ("start", "at", "center"):
        if k in a:
            a[k] = [a[k][0] + d, a[k][1]]
            return feature.geometry_from_dict(a)
    raise AssertionError(a)


def test_each_internal_alignment_fails_when_its_geometry_moves():
    checked = set()
    for name, sk in _alignment_sketches():
        for i, c in enumerate(sk.constraints):
            if not (c.type.startswith("InternalAlignment:") or c.type == "Weight"):
                continue
            geo = list(sk.geometry)
            geo[c.args[0]] = _moved(geo[c.args[0]]) if c.type != "Weight" else \
                Circle(geo[c.args[0]].center, geo[c.args[0]].radius + 0.01, True)
            bad = Sketch(sk.name, sk.support, geo, sk.constraints).unsatisfied()
            assert any(b.startswith(f"constraint {i} ") for b in bad), (name, c)
            checked.add(c.type)
    assert len(checked) == len(feature_curves.ALIGNMENTS) + 1


@pytest.mark.parametrize("name,sk", _alignment_sketches(), ids=lambda x: x if isinstance(x, str) else x.name)
def test_planegcs_and_these_checks_agree(name, sk):
    """The internal geometry moved off, PlaneGCS puts it back, and what it makes passes these checks to 1e-6
    (Sketch.solved() raises when it does not)."""
    _need_planegcs()
    geo = [_moved(g, 0.3) if g.construction else g for g in sk.geometry]
    off = Sketch(sk.name, sk.support, geo, sk.constraints, attachment_offset=sk.attachment_offset)
    assert off.unsatisfied()
    solved = off.solved()
    assert solved.unsatisfied(tol=1e-6, unchecked=False) == []


def test_point_on_conics_and_bsplines():
    curves = [Ellipse((1.0, 2.0), 9.0, 4.0, (0.6, 0.8)), ArcOfEllipse((1.0, 2.0), 9.0, 4.0, 0.2, 2.0, (0.6, 0.8)),
              ArcOfHyperbola((1.0, 2.0), 4.0, 3.0, -1.0, 1.0, (0.6, 0.8)),
              ArcOfParabola((1.0, 2.0), 2.0, -5.0, 5.0, (0.6, 0.8)),
              BSplineCurve([(0.0, 0.0), (5.0, 8.0), (10.0, -2.0), (15.0, 3.0)], [4, 4], [0.0, 1.0],
                           weights=[1.0, 2.0, 0.5, 1.0])]
    for g in curves:
        if isinstance(g, BSplineCurve):
            p = g.value(0.37)
        else:
            p = g.at(0.7)
        for d, ok in ((0.0, True), (0.01, False)):
            sk = Sketch("S", "XY", [g, Point((p[0] + d, p[1]), construction=True)],
                        [Constraint("PointOnObject", 1, 1, 0)])
            assert (sk.unsatisfied() == []) is ok, (g.kind, d)


def test_tangent_at_a_conic_end():
    arc = ArcOfEllipse((0.0, 0.0), 10.0, 5.0, 0.0, math.pi / 2)        # ends at (0, 5), heading -x
    line = LineSegment((0.0, 5.0), (-8.0, 5.0))
    ok = Sketch("S", "XY", [arc, line], [Constraint("Tangent", 0, 2, 1, 1)])
    assert ok.unsatisfied() == []
    bent = Sketch("S", "XY", [arc, LineSegment((0.0, 5.0), (-8.0, 6.0))], [Constraint("Tangent", 0, 2, 1, 1)])
    assert bent.unsatisfied()


# ── the curves' points and edges are OCCT's ──────────────────────────────────────────────────────────────

ALL = [Ellipse((5.0, 3.0), 20.0, 10.0, (0.6, 0.8)), ArcOfEllipse((5.0, 3.0), 20.0, 10.0, -1.0, 2.5, (0.6, 0.8)),
       ArcOfEllipse((0.0, 0.0), 8.0, 3.0, 2.0, 1.0), ArcOfHyperbola((1.0, 2.0), 5.0, 3.0, -1.2, 0.9, (0.6, 0.8)),
       ArcOfParabola((1.0, 2.0), 3.0, -6.0, 8.0, (0.0, -1.0)),
       BSplineCurve([(0.0, 0.0), (10.0, 5.0), (20.0, -3.0), (30.0, 4.0), (40.0, 0.0)], [4, 1, 4], [0.0, 0.4, 1.0],
                    weights=[1.0, 2.0, 0.5, 1.5, 1.0]),
       BSplineCurve([(0.0, 0.0), (10.0, 15.0), (20.0, 3.0), (30.0, 14.0), (25.0, -5.0), (10.0, -8.0)], [1] * 7,
                    [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0], periodic=True),
       BSplineCurve([(0.0, 0.0), (10.0, 15.0), (20.0, 3.0), (30.0, 14.0), (25.0, -5.0), (10.0, -8.0)],
                    [2, 1, 1, 2, 2], [0.0, 1.0, 2.0, 3.0, 4.0], periodic=True, weights=[1.0, 2.0, 1.0, 3.0, 1.0, 1.0]),
       BSplineCurve([(0.0, 0.0), (8.0, 10.0), (16.0, -2.0), (24.0, 9.0), (25.0, 2.0), (32.0, 0.0)], [3, 1, 2, 3],
                    [0.0, 1.0, 1.5, 3.0], degree=2)]


@pytest.mark.parametrize("g", ALL, ids=lambda g: g.kind)
def test_points_values_and_tangents_are_occts(g):
    ad = BRepAdaptor_Curve(feature._edge(g))
    a, b = ad.FirstParameter(), ad.LastParameter()
    pts = g.points()
    if isinstance(g, Ellipse):
        assert set(pts) == {3}
    else:
        p, q = ad.Value(a), ad.Value(b)
        assert math.dist(pts[1], (p.X(), p.Y())) < 1e-9 and math.dist(pts[2], (q.X(), q.Y())) < 1e-9
    if isinstance(g, BSplineCurve):
        assert set(pts) == {1, 2}
        for k in range(21):
            u = a + (b - a) * k / 20
            v = ad.Value(u)
            assert math.dist(g.value(u), (v.X(), v.Y())) < 1e-9
    for pos, u in ((1, a), (2, b)):
        if isinstance(g, Ellipse):
            continue
        from OCP.gp import gp_Pnt, gp_Vec
        P, V = gp_Pnt(), gp_Vec()
        ad.D1(u, P, V)
        t, n = feature_curves.tangent_at(g, pos), math.hypot(V.X(), V.Y())
        assert abs(t[0] - V.X() / n) < 1e-9 and abs(t[1] - V.Y() / n) < 1e-9


@pytest.mark.parametrize("g", ALL, ids=lambda g: g.kind)
def test_repr_and_dict_round_trip(g):
    assert eval(repr(g)) == g                                     # noqa: S307 - our own repr
    assert feature.geometry_from_dict(g.as_dict()) == g
    assert feature.geometry_from_dict({**g.as_dict(), "start_point": [0, 0], "end_point": [1, 1]}) == g


def test_bad_curves_are_refused_in_freecads_words():
    with pytest.raises(FeatureError, match="major radius"):
        Ellipse((0, 0), 3.0, 5.0)
    with pytest.raises(FeatureError, match="Poles and degree mismatch"):
        BSplineCurve([(0, 0), (1, 1), (2, 0)], [4, 4], [0.0, 1.0])
    with pytest.raises(FeatureError, match="not one of"):
        Constraint("InternalAlignment:Nothing", 1, 0)
    with pytest.raises(FeatureError, match="takes 2"):
        Constraint("InternalAlignment:EllipseMajorDiameter", 1, 1, 0)


# ── profiles ─────────────────────────────────────────────────────────────────────────────────────────────

def _pad(geometry):
    return Body([Sketch("Sketch", "XY", geometry), Pad("Pad", "Sketch")])


CROSSING = "^Could not create face from sketch.\nIntersecting sketch entities"


def test_an_ellipse_crossing_a_circle_is_refused():
    with pytest.raises(FeatureError, match=CROSSING):
        _pad([Ellipse((0.0, 0.0), 10.0, 5.0), Circle((10.0, 0.0), 3.0)])


def test_an_ellipse_inside_another_is_a_hole_and_touching_is_refused():
    assert _pad([Ellipse((0.0, 0.0), 10.0, 5.0), Ellipse((0.0, 0.0), 5.0, 2.0)]).volume == \
        pytest.approx(10 * math.pi * (50 - 10))
    with pytest.raises(FeatureError, match=CROSSING):
        _pad([Ellipse((0.0, 0.0), 10.0, 5.0), Ellipse((5.0, 0.0), 5.0, 2.0)])     # tangent inside at (10, 0)


def test_a_bspline_crossing_itself_or_a_line_is_refused():
    with pytest.raises(FeatureError, match=CROSSING):
        _pad([BSplineCurve([(0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0)], [1] * 5, [0.0, 1.0, 2.0, 3.0, 4.0],
                           periodic=True, degree=2)])
    spline = BSplineCurve([(0.0, 0.0), (10.0, 12.0), (20.0, -6.0), (30.0, 0.0)], [4, 4], [0.0, 1.0])
    with pytest.raises(FeatureError, match=CROSSING):
        _pad(closed_by_line(spline)[0])                     # the chord crosses the S-shaped spline


def test_an_arc_tangent_to_its_closing_line_is_not_a_crossing():
    # a half ellipse closed by a B-spline that leaves its ends along the same tangent
    arc = ArcOfEllipse((0.0, 0.0), 10.0, 5.0, 0.0, math.pi)
    spline = BSplineCurve([(-10.0, 0.0), (-10.0, -6.0), (10.0, -6.0), (10.0, 0.0)], [4, 4], [0.0, 1.0])
    assert _pad([arc, spline]).volume > 0


def test_an_open_arc_is_freecads_error():
    with pytest.raises(FeatureError, match=r"^Wire is not closed\.$"):
        _pad([ArcOfParabola((0.0, 0.0), 2.0, -5.0, 5.0)])


# ── the part file ────────────────────────────────────────────────────────────────────────────────────────

def _sketch_dicts(name):
    return [d for d in E.read_src(_part_src(name))["features"] if d["type"] == E.TYPE_IDS["Sketch"]]


def _part_src(name):
    src = '"""a part"""\nfrom cad_agent.feature import Body, Constraint, Pad, Pocket, Sketch, LineSegment\n\n' \
          'PARAMS = {}\n\nFEATURES = [\n]\n\n\ndef build(**p):\n    return Body(FEATURES, p)\n'
    ops = []
    for f in CASES[name]["features"]:
        if isinstance(f, Sketch):
            d = {"name": f.name, "type": E.TYPE_IDS["Sketch"], "support": f.support,
                 "attachment_offset": f.attachment_offset, **f.as_dict(), }
            d["constraints"] = [{"type": c.type, "args": list(c.args), **({"value": c.value} if c.dimensional else {}),
                                 "driving": c.driving, "name": c.name or ""} for c in f.constraints]
        else:
            d = {"name": f.name, "type": f"PartDesign::{f.kind}", "profile": f.profile, "type1": f.type,
                 "length": f.length, "reversed": f.reversed, "side_type": f.side_type}
        ops.append({"op": "add", "feature": d})
    return E.apply_src(src, ops)


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_case_written_by_feature_edit_reads_back_the_same(name, tmp_path):
    src = _part_src(name)
    for want, got in zip(_sketches(name), _sketch_dicts(name)):
        geo = [feature.geometry_from_dict(g) for g in got["geometry"]]
        assert len(geo) == len(want.geometry)
        for a, b in zip(want.geometry, geo):
            assert a.kind == b.kind and _same_geometry(a.as_dict(), b.as_dict(), tol=1e-9), (a, b)
        assert [(c["type"], c["args"]) for c in got["constraints"]] == \
            [(c.type, list(c.args)) for c in want.constraints]
    if name in SOLVED:
        _need_planegcs()
    path = tmp_path / f"{name}.py"
    path.write_text(src)
    ns = {}
    exec(compile(src, str(path), "exec"), ns)                 # noqa: S102 - the file we just wrote
    want = FREECAD[name]
    assert ns["build"]().volume == pytest.approx(want["volume"], rel=1e-6)


def test_set_rewrites_only_the_curve_that_changed():
    src = _part_src("pad_arc_of_hyperbola")
    sk = E.read_src(src)["features"][0]
    geo = [dict(g) for g in sk["geometry"]]
    lines = src.splitlines()
    geo[2] = dict(geo[2], end=[geo[2]["end"][0] + 1.0, geo[2]["end"][1]])      # a construction line moves
    out = E.apply_src(src, [{"op": "set", "name": "Sketch", "props": {"geometry": geo}}])
    changed = [(a, b) for a, b in zip(lines, out.splitlines()) if a != b]
    assert len(changed) == 1 and "LineSegment" in changed[0][0]
    assert E.apply_src(src, [{"op": "set", "name": "Sketch", "props": {"geometry": sk["geometry"]}}]) == src


def test_an_old_import_gains_the_curves_it_needs():
    src = _part_src("pad_ellipse")
    assert "from cad_agent.feature import (Body, Constraint, Ellipse, LineSegment, Pad, Pocket, Sketch)" in src
    assert "Ellipse((5.0, 3.0), 20.0, 10.0, x_axis=(0.877582562, 0.479425539))" in src


def test_bspline_source_is_parts_argument_order():
    g = BSplineCurve([(0.0, 0.0), (1.0, 2.0), (3.0, 0.0)], [3, 3], [0.0, 1.0], degree=2, weights=[1.0, 2.0, 1.0])
    assert E.geometry_src(g.as_dict()) == \
        "BSplineCurve([(0.0, 0.0), (1.0, 2.0), (3.0, 0.0)], [3, 3], [0.0, 1.0], degree=2, weights=[1.0, 2.0, 1.0])"
    assert E.geometry_src(BSplineCurve([(0.0, 0.0), (1.0, 2.0), (3.0, 0.0), (1.0, -1.0)], [1] * 5,
                                       [0.0, 1.0, 2.0, 3.0, 4.0], periodic=True, degree=2).as_dict()) == \
        "BSplineCurve([(0.0, 0.0), (1.0, 2.0), (3.0, 0.0), (1.0, -1.0)], [1, 1, 1, 1, 1], [0.0, 1.0, 2.0, 3.0, 4.0], " \
        "periodic=True, degree=2)"
    with pytest.raises(E.FeatureEditError, match="mismatch"):
        E.geometry_src({**g.as_dict(), "mults": [2, 2]})


def test_internal_alignment_constraints_are_written_as_python_writes_them():
    c = {"type": "InternalAlignment:BSplineControlPoint", "args": [5, 3, 0, 2], "driving": True, "name": ""}
    assert E.constraint_src(c) == 'Constraint("InternalAlignment:BSplineControlPoint", 5, 3, 0, 2)'
    assert E.constraint_src({"type": "Weight", "args": [5], "value": 1.0}) == 'Constraint("Weight", 5, 1.0)'


def test_exposed_matches_freecads_internal_geometry_count():
    geo, cons = exposed(*closed_by_line(ArcOfHyperbola((0.0, 0.0), 3.0, 2.0, -1.0, 1.0)), [0])
    assert len(geo) == 2 + 3 and len(cons) == 2 + 3


# ── `cad feature`, through the real part-file layer ──────────────────────────────────────────────────────

def test_cad_feature_takes_a_sketch_of_curves(demo, capsys):
    from cad_agent import cli
    from test_cli import run
    assert run(capsys, "feature", "new", "demo", "Body")[0] == cli.OK
    src = (demo / "parts" / "Body.py").read_text()
    assert "Ellipse" in src and "BSplineCurve" in src                 # the template imports the curves
    sk = _sketches("pad_rect_two_holes")[0]
    d = _sketch_dicts("pad_rect_two_holes")[0]
    ops = [{"op": "add", "feature": {k: d[k] for k in ("name", "type", "support", "geometry", "constraints")}},
           {"op": "add", "feature": {"name": "Pad", "type": "PartDesign::Pad", "profile": sk.name, "length": 8.0}}]
    code, data = run(capsys, "feature", "apply", "demo", "Body", "--ops", json.dumps(ops))
    assert data.get("built") is True, data
    assert [g["type"] for g in data["doc"]["features"][0]["geometry"][4:6]] == ["Ellipse", "BSplineCurve"]
    geo = data["doc"]["features"][0]["geometry"]
    geo[4] = dict(geo[4], minor_radius=5.0)                           # the ellipse thinner, its foci with it
    f1, f2 = Ellipse(geo[4]["center"], geo[4]["major_radius"], 5.0, geo[4]["x_axis"]).foci()
    geo[8], geo[9] = dict(geo[8], at=list(f1)), dict(geo[9], at=list(f2))
    geo[7] = dict(geo[7], start=[15.0, 20.0], end=[25.0, 20.0])
    code, data = run(capsys, "feature", "apply", "demo", "Body", "--ops",
                     json.dumps([{"op": "set", "name": "Sketch", "props": {"geometry": geo}}]))
    assert data.get("built") is True, data
    text = (demo / "parts" / "Body.py").read_text()
    assert "Ellipse((20.0, 20.0), 12.0, 5.0, x_axis=(0.0, 1.0))" in text
