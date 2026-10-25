"""Writes freecad.json: what FreeCAD 26.3 does for the Sketcher's commands on sketch objects, on sketches made by a fixed
seed, for tests/test_sketch_commands.py to hold cad_agent/sketch_commands.py to.

    python3 tests/golden/sketchobj/make.py <freecadcmd>          # writes freecad.json
    python3 tests/golden/sketchobj/make.py <freecadcmd> --check  # and compares with cad_agent/sketch_commands.py

<freecadcmd> may also come from $FREECADCMD (FreeCAD 26.3, weekly-2026.09.30 at 3160daf1e2b6). Each case is a sketch
(geometry and constraints as Sketcher.Constraint's argument lists, as tests/golden/sketchops writes them) and one of:

    mirror    Sketcher_MirrorSketch's steps, as CmdSketcherMirrorSketch::activated takes them through SketchObject's
              Python API (a temporary sketch holding a copy of the geometry and constraints, addSymmetric about the
              X axis, the Y axis or the origin, the new part shifted to the new sketch's numbering): the mirrored
              sketch's geometry and constraints as made, and its geometry after the recompute (the solve)
    merge     CmdSketcherMergeSketches' steps on two or three sketches (addGeometry, the constraints copied and
              renumbered): the merged sketch, made and solved
    validate  the Sketch Validation panel's analysis: detectMissingPointOnPointConstraints at several tolerances with
              and without construction geometry (MissingPointOnPointConstraints), OpenVertices, evaluateConstraints,
              detectDegeneratedGeometries, changeConstraintsLocking's counts, and the sketch after Fix
              (makeMissingPointOnPointCoincident, then the recompute) and after removeDegeneratedGeometries

Every case records the source sketch as FreeCAD solved it, which is what our side starts from. ui/scripts/
fcsketchobj_dump.py runs the commands themselves in FreeCAD's GUI (sketchobjcheck.mjs).
"""
from __future__ import annotations

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
TOL = 1e-9


def L(a, b, c=False):
    return {"type": "LineSegment", "start": [float(a[0]), float(a[1])], "end": [float(b[0]), float(b[1])],
            **({"construction": True} if c else {})}


def C(c, r, cons=False):
    return {"type": "Circle", "center": [float(c[0]), float(c[1])], "radius": float(r),
            **({"construction": True} if cons else {})}


def A(c, r, a1, a2):
    return {"type": "ArcOfCircle", "center": [float(c[0]), float(c[1])], "radius": float(r),
            "start_angle": float(a1), "end_angle": float(a2)}


def P(p, c=False):
    return {"type": "Point", "at": [float(p[0]), float(p[1])], **({"construction": True} if c else {})}


def E(c, a, b, ang=0.0):
    return {"type": "Ellipse", "center": [float(c[0]), float(c[1])], "major_radius": float(a),
            "minor_radius": float(b), "x_axis": [math.cos(ang), math.sin(ang)]}


def AE(c, a, b, ang, u1, u2):
    return {**E(c, a, b, ang), "type": "ArcOfEllipse", "start_angle": float(u1), "end_angle": float(u2)}


def AH(c, a, b, ang, u1, u2):
    return {"type": "ArcOfHyperbola", "center": [float(c[0]), float(c[1])], "major_radius": float(a),
            "minor_radius": float(b), "x_axis": [math.cos(ang), math.sin(ang)], "start_angle": float(u1),
            "end_angle": float(u2)}


def AP(v, f, ang, u1, u2):
    return {"type": "ArcOfParabola", "center": [float(v[0]), float(v[1])], "focal": float(f),
            "x_axis": [math.cos(ang), math.sin(ang)], "start_angle": float(u1), "end_angle": float(u2)}


def BS(poles):
    n = len(poles)
    return {"type": "BSplineCurve", "poles": [[float(x), float(y)] for x, y in poles],
            "mults": [4] + [1] * (n - 4) + [4], "knots": [float(i) for i in range(n - 2)], "degree": 3,
            "periodic": False}


def at_circle(c, a):
    return [c["center"][0] + c["radius"] * math.cos(a), c["center"][1] + c["radius"] * math.sin(a)]


def at_ellipse(e, u):
    x = e["x_axis"]
    y = [-x[1], x[0]]
    a, b = e["major_radius"] * math.cos(u), e["minor_radius"] * math.sin(u)
    return [e["center"][0] + a * x[0] + b * y[0], e["center"][1] + a * x[1] + b * y[1]]


class Gen:
    def __init__(self, seed=20261024):
        self.r = random.Random(seed)
        self.cases = []

    def j(self, s=1.0):
        return self.r.uniform(-s, s)

    def add(self, name, kind, **kw):
        self.cases.append({"name": f"{len(self.cases):03d} {name}", "kind": kind, **kw})


def rect(g, x0, y0, w, h, dims=True, construction=False):
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    geo = [L(pts[i], pts[(i + 1) % 4], construction) for i in range(4)]
    cons = [["Coincident", i, 2, (i + 1) % 4, 1] for i in range(4)]
    cons += [["Horizontal", 0], ["Horizontal", 2], ["Vertical", 1], ["Vertical", 3]]
    if dims:
        cons += [["DistanceX", 0, 1, 0, 2, w], ["DistanceY", 1, 1, 1, 2, h]]
    return geo, cons


def slot(g, cx, cy, half, r):
    """Two lines and two arcs, end to end with tangencies, as the Slot tool leaves them."""
    geo = [A((cx - half, cy), r, math.pi / 2, 3 * math.pi / 2), A((cx + half, cy), r, -math.pi / 2, math.pi / 2),
           L((cx - half, cy - r), (cx + half, cy - r)), L((cx + half, cy + r), (cx - half, cy + r))]
    cons = [["Tangent", 0, 2, 2, 1], ["Tangent", 2, 2, 1, 1], ["Tangent", 1, 2, 3, 1], ["Tangent", 3, 2, 0, 1],
            ["Horizontal", 2], ["Equal", 0, 1], ["Radius", 0, r]]
    return geo, cons


def sketches(g: Gen):
    """A few dozen sketches of every kind the cases use: (name, geometry, constraints)."""
    out = []
    pi = math.pi
    for k in range(4):
        w, h = g.r.uniform(10, 40), g.r.uniform(8, 30)
        geo, cons = rect(g, g.j(15), g.j(15), w, h)
        out.append(("rectangle", geo, cons + ([["Coincident", 0, 1, -1, 1]] if k == 0 else [])))
        geo, cons = slot(g, g.j(10), g.j(10), g.r.uniform(5, 15), g.r.uniform(2, 6))
        out.append(("slot", geo, cons + [["Distance", 2, 2 * g.r.uniform(5, 15)]] if k % 2 else cons))
        c = C((g.j(20), g.j(20)), g.r.uniform(2, 10))
        out.append(("circle", [c, C((c["center"][0] + 15, c["center"][1]), c["radius"] / 2)],
                    [["Radius", 0, c["radius"]], ["Diameter", 1, c["radius"]], ["DistanceX", 0, 3, c["center"][0]],
                     ["DistanceY", 0, 3, c["center"][1]], ["Horizontal", 0, 3, 1, 3]]))
        p0 = (g.j(10), g.j(10))
        p1 = (p0[0] + g.r.uniform(10, 20), p0[1] + g.j(3))
        p2 = (p0[0] + g.r.uniform(2, 8), p0[1] + g.r.uniform(8, 16))
        tri = [L(p0, p1), L(p1, p2), L(p2, p0)]
        a01 = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        a02 = math.atan2(p2[1] - p0[1], p2[0] - p0[0])
        out.append(("triangle", tri, [["Coincident", 0, 2, 1, 1], ["Coincident", 1, 2, 2, 1], ["Coincident", 2, 2, 0, 1],
                                       ["Angle", 0, a01], ["Distance", 0, math.dist(p0, p1)],
                                       ["Distance", 2, 1, 0, math.dist(p2, p0) * abs(math.sin(a02 - a01))]]))
        q0 = (g.j(10), g.j(10))
        l1 = L(q0, (q0[0] + 20, q0[1] + g.j(2)))
        l2 = L((q0[0] + 3, q0[1] + 5), (q0[0] + 17, q0[1] + 5 + g.j(2)))
        out.append(("parallel lines", [l1, l2], [["Parallel", 0, 1], ["Block", 0], ["DistanceX", 0, 1, 1, 1, 3.0]]))
        ang = g.r.uniform(0.4, 1.2)
        l3 = L((0, 0), (15 * math.cos(ang), 15 * math.sin(ang)))
        l4 = L((0, 0), (-10 * math.sin(ang), 10 * math.cos(ang)))
        out.append(("perpendicular at the origin", [l3, l4],
                    [["Coincident", 0, 1, -1, 1], ["Coincident", 1, 1, -1, 1], ["Perpendicular", 0, 1],
                     ["Angle", -1, 1, 0, 1, ang], ["Distance", 0, 15.0]]))
        s0 = (g.j(8), g.j(8))
        sym = [L((s0[0] - 10, s0[1]), (s0[0] + 10, s0[1] + 4), True), P((s0[0] - 2, s0[1] + 8)),
               P((s0[0] + 3.6, s0[1] - 6.2))]
        out.append(("points and a construction line", sym,
                    [["PointOnObject", 1, 1, -2], ["DistanceY", 2, 1, s0[1] - 6.2], ["Distance", 1, 1, 0, 3.0],
                     ["Distance", 1, 1, 2, 1, math.dist(sym[1]["at"], sym[2]["at"])]]))
        m = (g.j(5), g.j(5))
        pa, pb = (m[0] - 6, m[1] + 2), (m[0] + 6, m[1] - 2)
        out.append(("symmetric points about a point", [P(pa), P(pb), P(m)],
                    [["Symmetric", 0, 1, 1, 1, 2, 1]]))
        ln = L((m[0] - 8, m[1] - 8), (m[0] + 8, m[1] + 8), True)
        pc = (m[0] - 5, m[1] + 3)
        pd = (pc[1], pc[0])
        out.append(("symmetric points about a line", [ln, P(pc), P(pd)], [["Symmetric", 1, 1, 2, 1, 0]]))
        a1 = g.r.uniform(-1, 1)
        arc = A((g.j(10), g.j(10)), g.r.uniform(4, 10), a1, a1 + g.r.uniform(1, 4))
        tail = L(at_circle(arc, arc["end_angle"]), (arc["center"][0] - 20, arc["center"][1] + 20))
        out.append(("arc and line", [arc, tail], [["Coincident", 0, 2, 1, 1], ["Radius", 0, arc["radius"]],
                                                  ["PointOnObject", 0, 3, -1], ["Angle", 1, 2.4]]))
        e = E((g.j(10), g.j(10)), 10, 6, g.r.uniform(-1, 1))
        out.append(("ellipse with its axes", [e, L(at_ellipse(e, 0), at_ellipse(e, pi), True),
                                              L(at_ellipse(e, pi / 2), at_ellipse(e, -pi / 2), True)],
                    [["InternalAlignment:EllipseMajorDiameter", 1, 0], ["InternalAlignment:EllipseMinorDiameter", 2, 0]]))
        ae = AE((g.j(10), g.j(10)), 9, 5, g.r.uniform(-1, 1), g.r.uniform(-1, 0.5), g.r.uniform(1.5, 3.5))
        out.append(("arc of ellipse", [ae, L(at_ellipse(ae, ae["end_angle"]), (30, 30))], [["Coincident", 0, 2, 1, 1]]))
        out.append(("arc of hyperbola", [AH((g.j(5), g.j(5)), 6, 3, g.r.uniform(-1, 1), -0.8, 1.1)], []))
        out.append(("arc of parabola", [AP((g.j(5), g.j(5)), 2.5, g.r.uniform(-1, 1), -3.0, 4.0)], []))
        out.append(("b-spline", [BS([(0, 0), (5, 8 + g.j()), (12, -3), (18, 6), (25, g.j())])], []))
        geo, cons = rect(g, g.j(5), g.j(5), 30, 20, dims=False)
        geo += [L((5, 5), (25, 15), True), C((15, 10), 4)]
        cons += [["PointOnObject", 5, 3, 4], ["Radius", 5, 4.0, {"name": "hole"}],
                 ["DistanceX", 0, 1, 0, 2, 30.0, {"driving": False}], ["Equal", 0, 2]]
        out.append(("rectangle with construction and a hole", geo, cons))
    return out


def as_dict(c):
    """A Sketcher.Constraint argument list as a part file's constraint dict (feature_edit.read's form)."""
    from cad_agent.feature import DIMENSIONAL
    extra = c[-1] if isinstance(c[-1], dict) else {}
    t, args = c[0], list(c[1:len(c) - (1 if extra else 0)])
    d = {"type": t, "args": args[:-1] if t in DIMENSIONAL else args}
    if t in DIMENSIONAL:
        d["value"] = args[-1]
    d["driving"], d["name"] = extra.get("driving", True), extra.get("name", "")
    return d


def generate() -> list[dict]:
    g = Gen()
    base = sketches(g)
    for name, geo, cons in base:
        for ref in ("X", "Y", "origin"):
            g.add(f"mirror {name} about {ref}", "mirror", geometry=geo, constraints=cons, ref=ref)
    # merges: pairs and a triple
    for k in range(0, len(base) - 2, 3):
        group = base[k:k + 2 + (k % 2)]
        g.add("merge " + " + ".join(n for n, _, _ in group), "merge",
              sketches=[{"geometry": geo, "constraints": cons} for _, geo, cons in group])
    # validation: the sketches with some coincidences dropped, ends moved apart, degenerate lines
    for name, geo, cons in base:
        g.add(f"validate {name}", "validate", geometry=geo, constraints=cons)
    for k in range(12):
        w, h = g.r.uniform(10, 40), g.r.uniform(8, 30)
        geo, cons = rect(g, g.j(15), g.j(15), w, h, dims=False)
        drop = g.r.sample(range(4), g.r.randint(1, 4))
        cons = [c for i, c in enumerate(cons) if i not in drop]
        gap = [1e-9, 5e-8, 3e-6, 5e-5, 4e-4, 2e-3][k % 6]
        geo = [dict(x) for x in geo]
        for i in drop:                                   # the dropped corner opened by gap
            nxt = (i + 1) % 4
            geo[nxt] = {**geo[nxt], "start": [geo[nxt]["start"][0] + gap, geo[nxt]["start"][1] - gap * 0.5]}
        cons = [c for c in cons if c[0] != "Horizontal" and c[0] != "Vertical"] if k % 3 == 0 else \
            [c for c in cons if c[0] in ("Coincident",)]
        if k % 4 == 1:                                   # a construction line ending on a corner
            geo.append(L(geo[0]["start"], (geo[0]["start"][0] - 7, geo[0]["start"][1] - 9), True))
        if k % 4 == 2:                                   # a degenerate line and a degenerate arc
            geo.append(L((50, 50), (50 + 1e-9, 50)))
            geo.append(A((60, 60), 5.0, 1.0, 1.0 + 1e-10))
            cons.append(["Coincident", len(geo) - 2, 2, len(geo) - 1, 3])
        if k % 4 == 3:                                   # a point on a corner, three ends at one point
            geo.append(P(geo[2]["start"]))
            geo.append(L(geo[1]["start"], (geo[1]["start"][0] + 10, geo[1]["start"][1] - 10)))
        g.add(f"validate an open rectangle ({len(drop)} corners, gap {gap:g})", "validate", geometry=geo,
              constraints=cons)
    for k in range(6):                                   # fully constrained once Fix adds the missing one
        w, h = g.r.uniform(10, 40), g.r.uniform(8, 30)
        geo, cons = rect(g, 0.0, 0.0, w, h)
        cons.append(["Coincident", 0, 1, -1, 1])
        i = k % 4
        cons = [c for c in cons if c != ["Coincident", i, 2, (i + 1) % 4, 1]]
        nxt = (i + 1) % 4
        gap = [2e-5, 7e-5, 1e-6, 3e-5][i]
        geo[nxt] = {**geo[nxt], "start": [geo[nxt]["start"][0] - gap, geo[nxt]["start"][1] + gap]}
        g.add(f"validate a dimensioned rectangle with corner {i} open by {gap:g}", "validate", geometry=geo,
              constraints=cons)
    pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
    poly = [L(pts[i], pts[i + 1]) for i in range(3)] + [L((0, 10), (0, 1e-5)), L((0, 0), (0, -1e-5), True)]
    g.add("validate polyline with an almost closed end", "validate", geometry=poly,
          constraints=[["Coincident", 0, 2, 1, 1], ["Coincident", 1, 2, 2, 1], ["Coincident", 2, 2, 3, 1]])
    star = [L((0, 0), (10 * math.cos(a), 10 * math.sin(a))) for a in (0.0, 1.3, 2.5, 3.9, 5.1)]
    g.add("validate five lines from one point", "validate", geometry=star, constraints=[["Coincident", 0, 1, 1, 1],
                                                                                         ["Coincident", 2, 1, 3, 1]])
    many = []
    for i in range(30):                                  # past libstdc++'s 16-element insertion sort
        x0, y0 = g.r.uniform(-40, 40), g.r.uniform(-40, 40)
        many.append(L((round(x0), round(y0)), (round(x0 + g.j(10)), round(y0 + g.j(10)))))
    g.add("validate thirty lines on a grid", "validate", geometry=many, constraints=[])
    return g.cases


def run_freecad(freecadcmd: str, cases: list[dict]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        cin, cout = Path(tmp) / "cases.json", Path(tmp) / "answers.json"
        cin.write_text(json.dumps(cases))
        env = {**os.environ, "SKETCHOBJ_CASES": str(cin), "SKETCHOBJ_ANSWERS": str(cout)}
        subprocess.run([freecadcmd, str(HERE / "freecad_side.py")], env=env, check=True, stdout=subprocess.DEVNULL)
        return json.loads(cout.read_text())


def main(argv):
    fc = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else os.environ.get("FREECADCMD")
    if not fc:
        sys.exit("usage: make.py <freecadcmd> [--check]")
    sys.path.insert(0, str(ROOT))
    cases = generate()
    for c in cases:                                      # the part file's constraint form
        if "constraints" in c:
            c["constraints"] = [as_dict(x) for x in c["constraints"]]
        for s in c.get("sketches", []):
            s["constraints"] = [as_dict(x) for x in s["constraints"]]
    answers = run_freecad(fc, cases)
    out = {"about": "FreeCAD 26.3 (3160daf1e2b6) on the Sketcher's commands on sketch objects, written by "
                    "tests/golden/sketchobj/make.py; tests/test_sketch_commands.py compares.",
           "cases": [{**c, "freecad": a} for c, a in zip(cases, answers)]}
    (HERE / "freecad.json").write_text(json.dumps(out, indent=0) + "\n")
    errors = [c["name"] for c, a in zip(cases, answers) if "error" in a]
    print(f"wrote {HERE / 'freecad.json'}: {len(cases)} cases, {len(errors)} FreeCAD errors")
    for e in errors[:10]:
        print("  error:", e)
    if "--check" in argv:
        sys.path.insert(0, str(ROOT / "tests"))
        from test_sketch_commands import compare_all
        bad = compare_all(out["cases"])
        for name, why in bad[:40]:
            print(f"DIFF {name}: {why}")
        print(f"{len(out['cases']) - len(bad)} of {len(out['cases'])} cases equal")


if __name__ == "__main__":
    main(sys.argv)
