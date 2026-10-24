"""Writes freecad.json: what FreeCAD's Sketcher does with its curve tools on a few hundred sketches, for
tests/test_sketchcurves.py to hold ui/src/sketchbspline.ts and sketchops.ts (with the sketch kernel,
cad_agent/sketch_kernel.py) to.

    python3 tests/golden/sketchcurves/make.py <freecadcmd>          # writes freecad.json
    python3 tests/golden/sketchcurves/make.py <freecadcmd> --check  # and compares with ours

<freecadcmd> may also come from $FREECADCMD (FreeCAD 26.3, weekly-2026.09.30 at 3160daf1e2b6). Each case is a sketch
(geometry and constraints as tests/golden/sketchops writes them, and the curves whose internal geometry
exposeInternalGeometry shows first) and one tool, done as its command calls SketchObject from Python
(freecad_side.py): Geometry to B-spline (convertToNURBS then exposeInternalGeometry), Increase and Decrease B-spline
degree, Increase and Decrease knot multiplicity and Insert knot (then exposeInternalGeometry of the B-spline found by
its tag), Join curves, Trim and Split on B-splines, Fillet between curves other than two lines (radius 0, as the
tool passes it), and B-spline by knots (the interpolation tool's Python commands, without autoconstraints). Recorded:
the geometry, the construction flags and every constraint after it. The cases come from a fixed seed.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("sketchops_make", HERE.parent / "sketchops" / "make.py")
SO = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SO)
L, C, E = SO.L, SO.C, SO.E
compare = SO.compare


def _periodic(u1, u2):
    """ElCLib::AdjustPeriodic as Part.ArcOfCircle(circle, u1, u2) applies it: the arc FreeCAD holds starts in [0, 2pi)."""
    two = 2 * math.pi
    u1 -= math.floor(u1 / two) * two
    u2 -= math.floor((u2 - u1) / two) * two
    return u1, u2


def A(c, r, a1, a2):
    a1, a2 = _periodic(a1, a2)
    return SO.A(c, r, a1, a2)


def B(poles, degree=3, periodic=False, weights=None, construction=False):
    """A B-spline as the Sketcher's tool makes one: clamped uniform knots 0, 1, ... (or periodic, all 1)."""
    n = len(poles)
    if periodic:
        knots, mults = [float(i) for i in range(n + 1)], [1] * (n + 1)
    else:
        knots = [float(i) for i in range(n - degree + 1)]
        mults = [1] * len(knots)
        mults[0] = mults[-1] = degree + 1
    d = {"type": "BSplineCurve", "poles": [[float(x), float(y)] for x, y in poles], "mults": mults, "knots": knots,
         "degree": degree, "periodic": periodic}
    if weights:
        d["weights"] = [float(w) for w in weights]
    if construction:
        d["construction"] = True
    return d


def HYP(c, a, b, u1, u2, ang=0.0):
    return {"type": "ArcOfHyperbola", "center": [float(c[0]), float(c[1])], "major_radius": float(a),
            "minor_radius": float(b), "x_axis": [math.cos(ang), math.sin(ang)], "start_angle": float(u1),
            "end_angle": float(u2)}


def PAR(v, f, u1, u2, ang=0.0):
    return {"type": "ArcOfParabola", "center": [float(v[0]), float(v[1])], "focal": float(f),
            "x_axis": [math.cos(ang), math.sin(ang)], "start_angle": float(u1), "end_angle": float(u2)}


def AE(c, a, b, u1, u2, ang=0.0):
    u1, u2 = _periodic(u1, u2)
    return {**E(c, a, b, ang), "type": "ArcOfEllipse", "start_angle": float(u1), "end_angle": float(u2)}


def generate() -> list[dict]:
    g = SO.Gen(seed=20261027)
    pi = math.pi
    j = g.j

    def wavy(n, x0=-20.0, w=40.0, h=8.0):
        return [(x0 + w * i / (n - 1) + j(1.5), h * math.sin(i * 1.3 + j(0.4)) + j(2)) for i in range(n)]

    def ring(n, r=12.0):
        return [(r * math.cos(2 * pi * i / n) + j(1.5), r * math.sin(2 * pi * i / n) + j(1.5)) for i in range(n)]

    # Geometry to B-spline
    for k in range(6):
        ln = L((j(5), j(5)), (20 + j(5), 8 + j(5)))
        nxt = L(ln["end"], (30 + j(3), -5 + j(3)))
        g.add("convert a line", [ln, nxt], [["Coincident", 0, 2, 1, 1], ["Horizontal", 1], ["Distance", 0, 20.0]],
              ["convert", [[0]]])
        c = C((j(4), j(4)), g.r.uniform(4, 12))
        g.add("convert a circle", [c, L(c["center"], (30, 30))], [["Radius", 0, c["radius"]], ["Coincident", 0, 3, 1, 1]],
              ["convert", [[0]]])
        a1 = g.r.uniform(-1, 1)
        arc = A((j(3), j(3)), g.r.uniform(4, 12), a1, a1 + g.r.uniform(1, 4))
        g.add("convert an arc", [arc, L(SO.at_circle(arc, arc["end_angle"]), (30, 10))],
              [["Coincident", 0, 2, 1, 1], ["Coincident", 0, 3, -1, 1]], ["convert", [[0]]])
        e = E((j(3), j(3)), 12, g.r.uniform(4, 9), g.r.uniform(-1, 1))
        g.add("convert an ellipse", [e], [], ["convert", [[0]]])
        ae = AE((j(3), j(3)), 12, g.r.uniform(4, 9), g.r.uniform(-1, 0), g.r.uniform(1, 3), g.r.uniform(-1, 1))
        g.cases.append({"name": f"{len(g.cases):03d} convert an arc of ellipse (exposed)", "geometry": [ae], "constraints": [],
                        "expose": [0], "op": ["convert", [[0]]]})
        g.add("convert an arc of hyperbola", [HYP((j(2), j(2)), 4, 3, -1 + j(0.3), 1 + j(0.3), j(1))], [], ["convert", [[0]]])
        g.add("convert an arc of parabola", [PAR((j(2), j(2)), 2 + j(1), -3 + j(1), 3 + j(1), j(1))], [], ["convert", [[0]]])
        g.add("convert two lines", [ln, nxt], [["Coincident", 0, 2, 1, 1]], ["convert", [[0, 1]]])
        g.add("convert construction line", [L((0, 0), (10, 4), True)], [], ["convert", [[0]]])
        g.add("convert a B-spline", [B(wavy(5))], [], ["convert", [[0]]])

    # Degree
    for k in range(6):
        for deg in (1, 2, 3):
            n = deg + 2 + g.r.randrange(3)
            b = B(wavy(n), deg)
            g.cases.append({"name": f"{len(g.cases):03d} increase degree {deg}", "geometry": [b], "constraints": [],
                            "expose": [0], "op": ["degree_up", [0]]})
            g.cases.append({"name": f"{len(g.cases):03d} decrease degree {deg}", "geometry": [b], "constraints": [],
                            "expose": [0], "op": ["degree_down", [0]]})
        bp = B(ring(6), 3, periodic=True)
        g.cases.append({"name": f"{len(g.cases):03d} increase degree periodic", "geometry": [bp], "constraints": [],
                        "expose": [0], "op": ["degree_up", [0]]})
        g.cases.append({"name": f"{len(g.cases):03d} decrease degree periodic", "geometry": [bp], "constraints": [],
                        "expose": [0], "op": ["degree_down", [0]]})
        br = B(wavy(5), 2, weights=[1, 2 + j(0.5), 1, 0.5 + j(0.2) + 0.3, 1])
        g.cases.append({"name": f"{len(g.cases):03d} increase degree rational", "geometry": [br, L((40, 0), (50, 5))],
                        "constraints": [], "expose": [0], "op": ["degree_up", [0]]})
        g.add("increase degree, not exposed", [B(wavy(4))], [], ["degree_up", [0]])
        g.add("increase degree of a line (refused)", [L((0, 0), (5, 5))], [], ["degree_up", [0]])

    # Knots
    for k in range(6):
        n = 6 + g.r.randrange(3)
        b = B(wavy(n), 3)
        nk = len(b["knots"])
        ki = 2 + g.r.randrange(nk - 2)
        g.cases.append({"name": f"{len(g.cases):03d} increase knot multiplicity", "geometry": [b], "constraints": [],
                        "expose": [0], "op": ["knot_mult", [0, ki, 1]]})
        g.cases.append({"name": f"{len(g.cases):03d} decrease knot multiplicity (remove)", "geometry": [b], "constraints": [],
                        "expose": [0], "op": ["knot_mult", [0, ki, -1]]})
        g.cases.append({"name": f"{len(g.cases):03d} increase end knot (refused)", "geometry": [b], "constraints": [],
                        "expose": [0], "op": ["knot_mult", [0, 1, 1]]})
        b2 = {**b, "mults": [4] + [2 if i == ki - 1 else 1 for i in range(1, nk - 1)] + [4]}
        b2["poles"] = b["poles"] + [[b["poles"][-1][0] + 4, b["poles"][-1][1] + j(3)]]
        g.cases.append({"name": f"{len(g.cases):03d} decrease knot multiplicity 2 to 1", "geometry": [b2], "constraints": [],
                        "expose": [0], "op": ["knot_mult", [0, ki, -1]]})
        u = round(g.r.uniform(0.1, nk - 1.1), 6)
        g.cases.append({"name": f"{len(g.cases):03d} insert knot", "geometry": [b], "constraints": [],
                        "expose": [0], "op": ["insert_knot", [0, u, 1]]})
        g.cases.append({"name": f"{len(g.cases):03d} insert knot at a knot", "geometry": [b], "constraints": [],
                        "expose": [0], "op": ["insert_knot", [0, float(ki - 1), 1]]})
        bp = B(ring(6), 3, periodic=True)
        g.cases.append({"name": f"{len(g.cases):03d} insert knot periodic", "geometry": [bp], "constraints": [],
                        "expose": [0], "op": ["insert_knot", [0, round(g.r.uniform(0.2, 5.8), 6), 1]]})
        g.cases.append({"name": f"{len(g.cases):03d} insert knot outside (refused)", "geometry": [b], "constraints": [],
                        "expose": [0], "op": ["insert_knot", [0, nk + 3.0, 1]]})

    # Join
    for k in range(6):
        b1 = B(wavy(5, -40, 30))
        b2 = B([(b1["poles"][-1][0], b1["poles"][-1][1])] + [(p[0] + 30, p[1]) for p in wavy(4, -10, 20)][1:])
        g.add("join two B-splines", [b1, b2], [["Coincident", 0, 2, 1, 1]], ["join", [0, 2, 1, 1, 0]])
        g.add("join two B-splines, tangent", [b1, b2], [["Coincident", 0, 2, 1, 1]], ["join", [0, 2, 1, 1, 1]])
        ln = L(b1["poles"][-1], (b1["poles"][-1][0] + 10, b1["poles"][-1][1] + j(5)))
        g.add("join a B-spline and a line", [b1, ln, L((50, 50), (60, 60))],
              [["Coincident", 0, 2, 1, 1], ["Coincident", 0, 1, 2, 1], ["Horizontal", 2]], ["join", [0, 2, 1, 1, 0]])
        g.add("join a line and a B-spline, reversed", [ln, b1], [["Coincident", 1, 2, 0, 1]], ["join", [0, 1, 1, 2, 0]])
        r = g.r.uniform(4, 9)
        arc = A((0, 0), r, 0.3, 2.0)
        l2 = L(SO.at_circle(arc, 2.0), (-15, 15))
        g.add("join an arc and a line", [arc, l2], [["Coincident", 0, 2, 1, 1]], ["join", [0, 2, 1, 1, 0]])
        g.cases.append({"name": f"{len(g.cases):03d} join exposed B-splines", "geometry": [b1, b2],
                        "constraints": [["Coincident", 0, 2, 1, 1]], "expose": [0, 1], "op": ["join", [0, 2, 1, 1, 0]]})
        g.add("join construction and normal (refused)", [b1, {**b2, "construction": True}], [], ["join", [0, 2, 1, 1, 0]])

    # Trim and split on B-splines
    for k in range(8):
        b = B(wavy(6))
        cut1 = L((-8 + j(2), -15), (-6 + j(2), 15))
        cut2 = L((7 + j(2), -15), (9 + j(2), 15))
        geo = [b, cut1, cut2]
        g.add("trim a B-spline between two lines", geo, [], ["trim", [0, [0.0 + j(1), 0.0], False]])
        g.add("trim a B-spline's end", geo, [], ["trim", [0, b["poles"][-1], False]])
        g.add("trim a line crossing a B-spline", geo, [], ["trim", [1, SO.at_line(cut1, 0.9), False]])
        g.cases.append({"name": f"{len(g.cases):03d} trim an exposed B-spline", "geometry": geo, "constraints": [],
                        "expose": [0], "op": ["trim", [0, [0.0 + j(1), 0.0], False]]})
        bp = B(ring(6), 3, periodic=True)
        g.add("trim a periodic B-spline", [bp, L((-20, j(3)), (20, j(3)))], [], ["trim", [0, [0, 12], False]])
        g.add("split a B-spline", [b, L(b["poles"][-1], (30, 20))], [["Coincident", 0, 2, 1, 1]],
              ["split", [0, [j(5), 0]]])
        g.cases.append({"name": f"{len(g.cases):03d} split an exposed B-spline", "geometry": [b], "constraints": [],
                        "expose": [0], "op": ["split", [0, [j(5), 0]]]})
        g.add("split a periodic B-spline", [bp], [], ["split", [0, [12, 0]]])

    # Fillet between curves other than two lines
    for k in range(8):
        # a line ending at the origin and an arc leaving it at an angle (centre up and to the right)
        r = g.r.uniform(6, 12)
        phi = g.r.uniform(0.3, 1.2)
        span = g.r.uniform(1.0, 2.0)
        cen = (r * math.cos(phi), r * math.sin(phi))
        arc = A(cen, r, phi + pi, phi + pi + span)
        ln = L((-20, j(4)), (0, 0))
        on_arc = SO.at_circle(arc, phi + pi + span / 2)
        g.add("fillet a line and an arc", [ln, arc], [["Coincident", 0, 2, 1, 1]],
              ["fillet", [0, 1, SO.at_line(ln, 0.5), on_arc, 0.0, True, False, False]])
        g.add("fillet a line and an arc, keep corner", [ln, arc], [["Coincident", 0, 2, 1, 1], ["Radius", 1, r]],
              ["fillet", [0, 1, SO.at_line(ln, 0.5), on_arc, 0.0, True, True, False]])
        g.add("fillet with a radius", [ln, arc], [["Coincident", 0, 2, 1, 1]],
              ["fillet", [0, 1, SO.at_line(ln, 0.5), on_arc, round(g.r.uniform(0.5, 2), 6), True, False, False]])
        g.add("chamfer a line and an arc", [ln, arc], [["Coincident", 0, 2, 1, 1]],
              ["fillet", [0, 1, SO.at_line(ln, 0.5), on_arc, 0.0, True, False, True]])
        g.add("fillet a line and an arc, no trim", [ln, arc], [["Coincident", 0, 2, 1, 1]],
              ["fillet", [0, 1, SO.at_line(ln, 0.5), on_arc, 0.0, False, False, False]])
        # an arc ending at the origin (its end) and a line leaving it
        ang = g.r.uniform(0.2, 1.0)
        ln2 = L((0, 0), (15 * math.cos(ang), 15 * math.sin(ang)))
        psi = g.r.uniform(-0.3, 0.6)
        c2 = (-r * math.cos(psi), -r * math.sin(psi))
        arc2 = A(c2, r, psi - 1.2, psi)
        g.add("fillet an arc's end and a line, keep corner", [arc2, ln2], [["Coincident", 0, 2, 1, 1]],
              ["fillet", [0, 1, SO.at_circle(arc2, psi - 0.6), SO.at_line(ln2, 0.5), 0.0, True, True, False]])
        # a line and a B-spline starting at the origin
        b = B([(0, 0), (6, 6 + j(2)), (12, -2 + j(2)), (20, 4 + j(2))])
        lb = L((-15, -5 + j(3)), (0, 0))
        g.add("fillet a line and a B-spline", [lb, b], [["Coincident", 0, 2, 1, 1]],
              ["fillet", [0, 1, SO.at_line(lb, 0.5), [6, 3], 0.0, True, False, False]])
        # an arc of ellipse starting at the origin
        ea, eb, u0, eang = 10.0, g.r.uniform(4, 7), g.r.uniform(2.6, 3.4), g.r.uniform(-0.4, 0.4)
        ex = (math.cos(eang), math.sin(eang))
        ey = (-ex[1], ex[0])
        ec = (-(ea * math.cos(u0) * ex[0] + eb * math.sin(u0) * ey[0]), -(ea * math.cos(u0) * ex[1] + eb * math.sin(u0) * ey[1]))
        e = AE(ec, ea, eb, u0, u0 + 1.2, eang)
        g.add("fillet a line and an arc of ellipse", [ln, e], [["Coincident", 0, 2, 1, 1]],
              ["fillet", [0, 1, SO.at_line(ln, 0.5), SO.at_ellipse(e, u0 + 0.6), 0.0, True, False, False]])
        # two arcs meeting end to start
        s1, s2 = g.r.uniform(5, 8), g.r.uniform(5, 8)
        a3 = A((-s1, 0), s1, -0.9, 0.0)
        a4 = A((s2 * math.cos(2.2), s2 * math.sin(2.2)), s2, 2.2 + pi, 2.2 + pi + 1.0)
        g.add("fillet two arcs", [a3, a4], [["Coincident", 0, 2, 1, 1]],
              ["fillet", [0, 1, SO.at_circle(a3, -0.45), SO.at_circle(a4, 2.2 + pi + 0.5), 0.0, True, False, False]])
        # two arcs that cross without touching ends (the basis circles' intersection)
        a5 = A((-5, 0), 7, -0.5, 0.9)
        a6 = A((5, 0), 7, pi - 0.9, pi + 0.5)
        g.add("fillet two crossing arcs", [a5, a6], [],
              ["fillet", [0, 1, SO.at_circle(a5, 0.2), SO.at_circle(a6, pi - 0.2), 0.0, True, False, False]])

    # Carbon copy: another sketch (placed as given) copied into this one, mirrored when its axes run the other way
    s45 = math.sqrt(0.5)
    placements = [("parallel above", [0, 0, 10], [0, 0, 0, 1]), ("turned over X (yinv)", [0, 0, 10], [1, 0, 0, 0]),
                  ("turned over Y (xinv)", [0, 0, -5], [0, 1, 0, 0]), ("turned about Z (xinv, yinv)", [0, 0, 7], [0, 0, 1, 0]),
                  ("same place", [0, 0, 0], [0, 0, 0, 1]), ("not parallel (refused)", [0, 0, 10], [s45, 0, 0, s45]),
                  ("origin aside (refused)", [5, 0, 10], [0, 0, 0, 1]), ("axes turned 90 (refused)", [0, 0, 10], [0, 0, s45, s45])]
    for k in range(2):
        src_geo = [L((2 + j(1), 3 + j(1)), (20 + j(2), 5 + j(2))), L((20, 5), (24 + j(1), 18 + j(1))),
                   A((10 + j(1), 15 + j(1)), 4 + j(0.5), 0.3, 2.4), C((30 + j(1), 20 + j(1)), 3 + j(0.5)),
                   {"type": "Point", "at": [6.0, 22.0]}, B([(30, 0), (35, 6), (40, 2), (45, 8)])]
        src_geo[1]["start"] = list(src_geo[0]["end"])
        src_cons = [["Coincident", 0, 2, 1, 1], ["DistanceX", 0, 1, 0, 2, 18.0], ["DistanceY", 1, 1, 1, 2, 12.0],
                    ["DistanceX", 0, 1, 1, 2, 22.0], ["Angle", 0, 0.1], ["Angle", 0, 1, 1.2], ["Radius", 2, 4.0],
                    ["PointOnObject", 4, 1, -2], ["Diameter", 3, 6.0]]
        target = [L((-10, -10), (-2, -12))]
        for name, base, q in placements:
            for constr in (False, True) if name == "parallel above" else (False,):
                g.add(f"carbon copy, {name}{' (construction)' if constr else ''}", target, [["Horizontal", 0]] if k else [],
                      ["carbon_copy", [src_geo, src_cons, {"base": [0, 0, 0], "rotation": [0, 0, 0, 1]},
                                       {"base": base, "rotation": q}, constr]])
    # a target sketch placed elsewhere (on XZ, its own axes), the source on a parallel plane
    for name, base, q in (("on XZ", [0, 8, 0], [s45, 0, 0, s45]), ("on XZ, turned over", [0, -8, 0], [0, s45, s45, 0])):
        g.add(f"carbon copy onto a sketch {name}", [L((0, 0), (5, 5))], [],
              ["carbon_copy", [[L((1, 1), (9, 3)), A((5, 5), 3, 0.5, 2.0)], [["DistanceX", 0, 1, 0, 2, 8.0]],
                               {"base": [0, 0, 0], "rotation": [s45, 0, 0, s45]}, {"base": base, "rotation": q}, False]])

    # B-spline by knots
    for k in range(8):
        n = 3 + g.r.randrange(5)
        pts = [[round(x, 3), round(y, 3)] for x, y in wavy(n)]
        g.add("B-spline by knots", [], [], ["bspline_by_knots", [pts, [1] * n, False, False]])
        g.add("periodic B-spline by knots", [], [], ["bspline_by_knots", [[[round(x, 3), round(y, 3)] for x, y in ring(n + 1)], [1] * (n + 1), True, False]])
        if n >= 4:
            m = [1] * n
            m[n // 2] = 2
            g.add("B-spline by knots, a double knot", [], [], ["bspline_by_knots", [pts, m, False, False]])
        g.add("B-spline by two knots", [], [], ["bspline_by_knots", [pts[:2], [1, 1], False, True]])
    return [c for c in g.cases if c]


def run_freecad(freecadcmd: str, cases: list[dict]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        cin, cout = Path(tmp) / "cases.json", Path(tmp) / "answers.json"
        cin.write_text(json.dumps(cases))
        env = {**os.environ, "SKETCHCURVES_CASES": str(cin), "SKETCHCURVES_ANSWERS": str(cout)}
        subprocess.run([freecadcmd, str(HERE / "freecad_side.py")], env=env, check=True, stdout=subprocess.DEVNULL)
        return json.loads(cout.read_text())


def ours(cases: list[dict], node: str = "node") -> list[dict]:
    """What ui/src does for the cases (tests/golden/sketchcurves/ours.mjs under node), the sketch kernel's answers
    (cad_agent/sketch_kernel.py) fed in: node lists the requests it has no answer for, they are answered here, and
    node runs again until none are left."""
    from cad_agent import sketch_kernel
    answers: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        cin, kin = Path(tmp) / "cases.json", Path(tmp) / "kernel.json"
        cin.write_text(json.dumps(cases))
        for _ in range(40):
            kin.write_text(json.dumps(answers))
            r = subprocess.run([node, str(HERE / "ours.mjs"), str(cin), str(kin)], capture_output=True, text=True,
                               check=True, cwd=ROOT)
            out = json.loads(r.stdout)
            if not out["needs"]:
                return out["results"]
            for key in out["needs"]:
                answers[key] = sketch_kernel.run(json.loads(key))
    raise RuntimeError("the sketch kernel was asked too many times")


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    freecadcmd = args[0] if args else os.environ.get("FREECADCMD")
    if not freecadcmd:
        sys.exit("usage: make.py <freecadcmd> [--check]   (or set FREECADCMD)")
    cases = generate()
    answers = run_freecad(freecadcmd, cases)
    golden = [{**c, "freecad": a} for c, a in zip(cases, answers)]
    (HERE / "freecad.json").write_text("[\n" + ",\n".join(json.dumps(c, separators=(",", ":")) for c in golden) + "\n]\n")
    print(len(golden), "cases")
    if "--check" in argv:
        mine = ours(golden)
        bad = 0
        for case, me in zip(golden, mine):
            d = compare(case, case["freecad"], me)
            if d:
                bad += 1
                print(case["name"], *d, sep="\n    ")
        print(f"{len(golden) - bad} agree, {bad} differ")


if __name__ == "__main__":
    main(sys.argv[1:])
