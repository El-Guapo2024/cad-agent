"""Writes freecad.json: FreeCAD's Sketcher answers for a few hundred sketches, for tests/test_planegcs.py to
hold the port of the Sketcher's solver (ui/planegcs, cad_agent/planegcs.py) to.

    python3 tests/golden/sketcher/make.py <freecadcmd>          # writes freecad.json
    python3 tests/golden/sketcher/make.py <freecadcmd> --check  # and compares with the native build
    python3 tests/golden/sketcher/make.py <freecadcmd> --set=conics   # freecad_conics.json: conics and B-splines

<freecadcmd> may also come from $FREECADCMD (FreeCAD 26.3, weekly-2026.09.30 at 3160daf1e2b6, was
used: its AppImage extracted, squashfs-root/usr/bin/freecadcmd). Each case is made in a
Sketcher::SketchObject: addGeometry for each geometry, addConstraint with the list of constraints,
solve(), then each drag as moveGeometry(geo, pos, Vector, relative). Recorded: solve()'s status, DoF,
the conflicting, redundant, partially redundant and malformed constraints, the Geometry and every
constraint's Value after the solve and after each drag. The cases are generated from a fixed seed:
rectangles, polygons, slots and rounded corners (arcs tangent to lines), circles with radius,
diameter and distances, symmetric pairs, angles in each form, points on objects, blocks, reference
constraints, under-, fully and over-constrained, conflicting, redundant and malformed sketches, and
drags of points and edges.

freecadcmd runs on bump_malloc.c (a malloc that never reuses memory): PlaneGCS orders its unknowns by
address, so without it FreeCAD's answer for an under-constrained sketch depends on its heap and differs
from run to run; with it the parameters are ordered as they are made, as in the port. Each case is also
solved with its numbers moved by one ulp up and down; where that moves FreeCAD's answer beyond TOL the
case is marked rounding_sensitive (see tests/test_planegcs.py).
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
TOL = 1e-9          # relative, against max(1, |a|, |b|)


# ─── the cases ──────────────────────────────────────────────────────────────

def L(a, b, c=False):
    return {"type": "LineSegment", "start": [float(a[0]), float(a[1])], "end": [float(b[0]), float(b[1])],
            **({"construction": True} if c else {})}


def C(c, r, cons=False):
    return {"type": "Circle", "center": [float(c[0]), float(c[1])], "radius": float(r),
            **({"construction": True} if cons else {})}


def A(c, r, a1, a2):
    return {"type": "ArcOfCircle", "center": [float(c[0]), float(c[1])], "radius": float(r),
            "start_angle": float(a1), "end_angle": float(a2)}


def P(p):
    return {"type": "Point", "at": [float(p[0]), float(p[1])]}


class Gen:
    def __init__(self, seed=20261024):
        self.r = random.Random(seed)
        self.cases = []

    def j(self, s=1.0):
        return self.r.uniform(-s, s)

    def jp(self, p, s=1.0):
        return (p[0] + self.j(s), p[1] + self.j(s))

    def add(self, name, geometry, constraints, drags=()):
        self.cases.append({"name": f"{len(self.cases):03d} {name}", "geometry": geometry,
                           "constraints": constraints, "drags": list(drags)})

    def drags_for(self, geometry, n=2):
        """A few moves of points and edges."""
        out = []
        for _ in range(n):
            g = self.r.randrange(len(geometry))
            t = geometry[g]["type"]
            pos = self.r.choice({"Point": [1], "LineSegment": [0, 1, 2], "Circle": [0, 3],
                                 "ArcOfCircle": [0, 1, 2, 3]}[t])
            rel = self.r.random() < 0.3
            to = [self.j(3), self.j(3)] if rel else [self.j(30), self.j(30)]
            out.append({"geo": g, "pos": pos, "to": to, "relative": rel})
        return out


def rectangle(g, w, h, x0=0.0, y0=0.0, jit=1.0):
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    pts = [g.jp(p, jit) for p in pts]
    geo = [L(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    cons = [["Coincident", i, 2, (i + 1) % 4, 1] for i in range(4)]
    cons += [["Horizontal", 0], ["Horizontal", 2], ["Vertical", 1], ["Vertical", 3]]
    return geo, cons


def polygon(g, n, r, jit=0.5):
    pts = [(r * math.cos(2 * math.pi * k / n + 0.3), r * math.sin(2 * math.pi * k / n + 0.3)) for k in range(n)]
    pts = [g.jp(p, jit) for p in pts]
    geo = [L(pts[k], pts[(k + 1) % n]) for k in range(n)]
    cons = [["Coincident", k, 2, (k + 1) % n, 1] for k in range(n)]
    return geo, cons


def slot(g, length, rad, jit=0.3):
    # left cap, right cap, bottom line, top line, as FreeCAD's slot tool draws them
    c0, c1 = (0.0, 0.0), (length, 0.0)
    geo = [A(g.jp(c0, jit), rad + g.j(jit), math.pi / 2 + g.j(0.05), 3 * math.pi / 2 + g.j(0.05)),
           A(g.jp(c1, jit), rad + g.j(jit), -math.pi / 2 + g.j(0.05), math.pi / 2 + g.j(0.05)),
           L(g.jp((0, -rad), jit), g.jp((length, -rad), jit)),
           L(g.jp((length, rad), jit), g.jp((0, rad), jit))]
    cons = [["Tangent", 0, 2, 2, 1], ["Tangent", 2, 2, 1, 1], ["Tangent", 1, 2, 3, 1], ["Tangent", 3, 2, 0, 1],
            ["Equal", 0, 1], ["Horizontal", 2]]
    return geo, cons


def generate() -> list[dict]:
    g = Gen()

    # Rectangles
    for k in range(12):
        w, h = g.r.uniform(5, 60), g.r.uniform(5, 60)
        geo, cons = rectangle(g, w, h, g.j(10), g.j(10), jit=g.r.uniform(0.1, 3))
        g.add("rectangle, topology only", geo, cons, g.drags_for(geo, 3))
        full = cons + [["Coincident", 0, 1, -1, 1], ["DistanceX", 0, w], ["DistanceY", 1, h]]
        g.add("rectangle, fully constrained", geo, full)
        g.add("rectangle, lengths as Distance", geo,
              cons + [["DistanceX", 0, 1, -1, 1, g.j(5)], ["DistanceY", 0, 1, -1, 1, g.j(5)],
                      ["Distance", 0, w], ["Distance", 1, h]])
        g.add("rectangle, redundant horizontal", geo, full + [["Horizontal", 0]])
        g.add("rectangle, redundant equal-valued distance", geo, full + [["DistanceX", 2, -w]])
        g.add("rectangle, conflicting distance", geo, full + [["Distance", 2, w + 3.0]])
        g.add("rectangle, reference diagonal", geo,
              full + [{"type": "Distance", "args": [0, 1, 1, 2], "value": 1.0, "driving": False}])
        g.add("rectangle, centred on the origin", geo,
              cons + [["Symmetric", 0, 1, 1, 2, -1, 1], ["DistanceX", 0, w], ["DistanceY", 1, h]],
              g.drags_for(geo, 1))
        g.add("rectangle, symmetric about the V axis, drag", geo,
              cons + [["Symmetric", 0, 1, 0, 2, -2], ["Distance", 1, h]], g.drags_for(geo, 3))
        g.add("rectangle, inactive constraint", geo, full + [["Distance", 2, w + 3.0, False]])

    # Polygons, as the polygon tool makes them: construction circle, vertices on it, equal sides
    for k in range(18):
        n = 3 + k % 6
        rad = g.r.uniform(5, 40)
        geo, cons = polygon(g, n, rad, jit=g.r.uniform(0.05, 1.0))
        geo.append(C(g.jp((0, 0), 0.5), rad + g.j(), cons=True))
        cons += [["PointOnObject", i, 1, n] for i in range(n)]
        cons += [["Equal", 0, i] for i in range(1, n)]
        g.add(f"{n}-gon, free", geo, cons, g.drags_for(geo, 2))
        full = cons + [["Coincident", n, 3, -1, 1], ["Radius", n, rad], ["Horizontal", 0]]
        g.add(f"{n}-gon, fully constrained", geo, full)
        g.add(f"{n}-gon, diameter and angle", geo,
              cons + [["Coincident", n, 3, -1, 1], ["Diameter", n, 2 * rad], ["Angle", 0, g.r.uniform(-1, 1)]])
        g.add(f"{n}-gon, over-constrained", geo, full + [["Distance", 0, rad * 3.0]])
        g.add(f"{n}-gon, redundant equal", geo, full + [["Equal", 1, 2] if n > 2 else ["Equal", 0, 1]])

    # Slots: arcs tangent to lines at their ends
    for k in range(12):
        length, rad = g.r.uniform(10, 50), g.r.uniform(2, 10)
        geo, cons = slot(g, length, rad, jit=g.r.uniform(0.05, 0.6))
        g.add("slot, free", geo, cons, g.drags_for(geo, 3))
        full = cons + [["Coincident", 0, 3, -1, 1], ["Radius", 0, rad], ["Distance", 0, 3, 1, 3, length]]
        g.add("slot, fully constrained", geo, full)
        g.add("slot, redundant horizontal", geo, full + [["Horizontal", 3]])
        g.add("slot, diameter, distance x", geo,
              cons + [["Diameter", 1, 2 * rad], ["DistanceX", 0, 3, 1, 3, length], ["DistanceY", 0, 3, 0.0]])
        g.add("slot, reference arc length", geo,
              full + [{"type": "Distance", "args": [0], "value": 1.0, "driving": False},
                      {"type": "Angle", "args": [1], "value": 1.0, "driving": False}])

    # Rounded corners: two lines and an arc, tangent at both ends; endpoint-to-curve tangency
    for k in range(12):
        rad = g.r.uniform(1, 8)
        geo = [L(g.jp((0, 0), 0.3), g.jp((20, 0), 0.3)),
               A(g.jp((20, rad), 0.3), rad + g.j(0.3), -math.pi / 2 + g.j(0.1), 0 + g.j(0.1)),
               L(g.jp((20 + rad, rad), 0.3), g.jp((20 + rad, 25), 0.3))]
        cons = [["Tangent", 0, 2, 1, 1], ["Tangent", 1, 2, 2, 1]]
        g.add("fillet, free", geo, cons, g.drags_for(geo, 2))
        full = cons + [["Horizontal", 0], ["Vertical", 2], ["Coincident", 0, 1, -1, 1], ["Radius", 1, rad],
                       ["DistanceX", 0, 20.0], ["DistanceY", 2, 25.0 - rad]]
        g.add("fillet, fully constrained", geo, full)
        g.add("fillet, perpendicular lines too (redundant)", geo, full + [["Perpendicular", 0, 2]])
        geo2 = [L(g.jp((0, 0), 0.3), g.jp((20, 0), 0.3)), A(g.jp((25, 4), 1), 4 + g.j(0.5), 2.5, 4.5)]
        g.add("arc end on a line, tangent (endpoint to curve)", geo2,
              [["Tangent", 1, 1, 0], ["Horizontal", 0], ["Radius", 1, 4.0]], g.drags_for(geo2, 2))
        g.add("tangent via point", geo2,
              [["PointOnObject", 1, 1, 0], ["TangentViaPoint", 1, 0, 1, 1], ["Radius", 1, 3.0]])
        g.add("perpendicular endpoint to endpoint", [geo[0], L(g.jp((20, 0), 0.5), g.jp((22, 9), 0.5))],
              [["Perpendicular", 0, 2, 1, 1], ["Distance", 1, 9.0]])

    # Circles
    for k in range(15):
        c1, r1 = g.jp((0, 0), 10), g.r.uniform(2, 15)
        c2, r2 = g.jp((25, 5), 10), g.r.uniform(2, 15)
        geo = [C(c1, r1), C(c2, r2)]
        g.add("circles, radius and diameter", geo, [["Radius", 0, r1 + 1.0], ["Diameter", 1, 2 * r2 - 1.0]],
              g.drags_for(geo, 3))
        g.add("circles, concentric equal", geo, [["Coincident", 0, 3, 1, 3], ["Equal", 0, 1]], g.drags_for(geo, 2))
        g.add("circles, tangent", geo, [["Tangent", 0, 1], ["Coincident", 0, 3, -1, 1], ["Radius", 0, r1]])
        g.add("circles, distance", geo, [["Distance", 0, 1, g.r.uniform(1, 10)], ["Radius", 0, r1], ["Radius", 1, r2]])
        g.add("circle, point on it", geo + [P(g.jp((0, 0), 20))],
              [["PointOnObject", 2, 1, 0], ["Coincident", 0, 3, -1, 1], ["Radius", 0, r1],
               ["Distance", 2, 1, -1, g.j(5)]])
        line = L(g.jp((-30, -20), 3), g.jp((30, -18), 3))
        g.add("circle tangent to a line", [geo[0], line], [["Tangent", 1, 0], ["Radius", 0, r1]],
              g.drags_for([geo[0], line], 2))
        g.add("circle to line distance", [geo[0], line], [["Distance", 0, 1, g.r.uniform(1, 9)], ["Horizontal", 1]])
        g.add("point to circle distance", [geo[0], P(g.jp((30, 30), 3))],
              [["Distance", 1, 1, 0, g.r.uniform(1, 9)], ["Radius", 0, r1]])
        g.add("circle centre on line, perpendicular", [geo[0], line], [["Perpendicular", 1, 0]],
              g.drags_for([geo[0], line], 2))
        g.add("circles, conflicting radii", geo, [["Equal", 0, 1], ["Radius", 0, r1], ["Radius", 1, r1 + 2.0]])

    # Arcs
    for k in range(12):
        a1 = g.r.uniform(-4, 4)
        a2 = a1 + g.r.uniform(0.3, 6)
        geo = [A(g.jp((0, 0), 5), g.r.uniform(3, 20), a1, a2), A(g.jp((30, 0), 5), g.r.uniform(3, 20), 1.0, 2.5),
               C(g.jp((0, 30), 5), g.r.uniform(3, 9))]
        g.add("arcs, radius, angle, length", geo,
              [["Radius", 0, 8.0], ["Angle", 0, 1.2], ["Distance", 1, 15.0]], g.drags_for(geo, 3))
        g.add("arcs, tangent arc-arc and circle-arc", geo, [["Tangent", 0, 1], ["Tangent", 2, 0]], g.drags_for(geo, 2))
        g.add("arcs, end to end tangent", geo, [["Tangent", 0, 2, 1, 1], ["Equal", 0, 1]])
        g.add("arcs, equal circle and arc", geo, [["Equal", 2, 0], ["Coincident", 0, 3, 2, 3]])
        g.add("arc ends symmetric about a line through its centre", geo + [L(g.jp((0, -20)), g.jp((0, 20)))],
              [["Symmetric", 0, 1, 0, 2, 3], ["Coincident", 0, 3, -1, 1], ["Vertical", 3]])
        g.add("arc on circle, point on arc", geo + [P(g.jp((10, 10), 5))],
              [["PointOnObject", 3, 1, 0], ["PointOnObject", 0, 1, 2], ["Radius", 0, 6.0]])
        g.add("arc to circle distance", geo, [["Distance", 0, 2, 3.0], ["Distance", 1, 3, 0, 3, 20.0]])

    # Angles in each form, parallel, perpendicular
    for k in range(15):
        l0 = L(g.jp((0, 0), 2), g.jp((20, 3), 2))
        l1 = L(g.jp((0, 0), 2), g.jp((5, 18), 2))
        l2 = L(g.jp((30, 0), 2), g.jp((40, 15), 2))
        geo = [l0, l1, l2]
        a = g.r.uniform(-3, 3)
        g.add("angle of a line", geo, [["Angle", 0, a], ["Coincident", 0, 1, -1, 1], ["Distance", 0, 10.0]])
        g.add("angle between lines", geo, [["Angle", 0, 1, a], ["Coincident", 0, 1, 1, 1]], g.drags_for(geo, 2))
        g.add("angle between lines from given ends", geo, [["Angle", 0, 2, 1, 1, abs(a)], ["Coincident", 0, 2, 1, 1]])
        g.add("angle via point", geo, [["AngleViaPoint", 0, 1, 0, 1, a], ["Coincident", 0, 1, 1, 1]])
        g.add("parallel and perpendicular", geo, [["Parallel", 0, 2], ["Perpendicular", 0, 1], ["Coincident", 0, 1, 1, 1]],
              g.drags_for(geo, 2))
        g.add("perpendicular via point", geo, [["PerpendicularViaPoint", 0, 1, 0, 1], ["Coincident", 0, 1, 1, 1]])
        g.add("points perpendicular to a line", geo, [["Perpendicular", 0, 1, 2, 2, 1]])
        g.add("angle conflicts with perpendicular", geo,
              [["Perpendicular", 0, 1], ["Angle", 0, 1, 1.0], ["Coincident", 0, 1, 1, 1]])
        g.add("reference angle", geo, [["Horizontal", 0], {"type": "Angle", "args": [0, 1], "value": 0.5, "driving": False},
                                       ["Coincident", 0, 1, 1, 1]])
        g.add("tangent lines (collinear)", geo, [["Tangent", 0, 2]], g.drags_for(geo, 1))

    # Points, axes, horizontal/vertical point pairs, symmetric, distances
    for k in range(15):
        pts = [P(g.jp((g.j(20), g.j(20)), 1)) for _ in range(4)]
        line = L(g.jp((-10, -10), 3), g.jp((10, 12), 3))
        geo = pts + [line]
        g.add("points, horizontal and vertical pairs", geo,
              [["Horizontal", 0, 1, 1, 1], ["Vertical", 1, 1, 2, 1], ["Distance", 0, 1, 1, 1, 7.0]], g.drags_for(geo, 3))
        g.add("points symmetric about a line", geo, [["Symmetric", 0, 1, 1, 1, 4], ["Distance", 0, 1, 4, 3.0]],
              g.drags_for(geo, 2))
        g.add("points symmetric about a point", geo, [["Symmetric", 0, 1, 1, 1, 2, 1], ["Coincident", 2, 1, -1, 1]])
        g.add("points on the axes", geo, [["PointOnObject", 0, 1, -1], ["PointOnObject", 1, 1, -2],
                                         ["DistanceX", 0, 1, 4.0], ["DistanceY", 1, 1, -3.0]])
        g.add("point to line distance", geo, [["Distance", 0, 1, 4, 5.0], ["Distance", 1, 1, 4, 2.0], ["Horizontal", 4]],
              g.drags_for(geo, 2))
        g.add("point to the root, the V axis", geo, [["Distance", 0, 1, -1, 1, 10.0], ["Distance", 0, 1, -2, 4.0]])
        g.add("coincident points, over-constrained", geo,
              [["Coincident", 0, 1, 1, 1], ["Distance", 0, 1, 1, 1, 3.0]])
        g.add("block a point and a line", geo, [["Block", 0], ["Block", 4], ["PointOnObject", 1, 1, 4]],
              g.drags_for(geo, 2))
        g.add("block with other constraints on it", geo,
              [["Block", 4], ["Coincident", 4, 1, 0, 1], ["Distance", 4, 20.0]])
        g.add("block, conflicting", geo, [["Coincident", 0, 1, -1, 1], ["Block", 0], ["DistanceX", 0, 1, 3.0]])

    # Malformed and invalid constraints
    for k in range(5):
        geo = [L(g.jp((0, 0)), g.jp((10, 0))), C(g.jp((5, 10)), 3), A(g.jp((20, 0)), 4, 0.5, 2.0), P(g.jp((3, 3)))]
        g.add("malformed: parallel line circle", geo, [["Parallel", 0, 1], ["Horizontal", 0]])
        g.add("malformed: radius of a line", geo, [["Radius", 0, 5.0]])
        g.add("malformed: length of a circle", geo, [["Distance", 1, 5.0]])
        g.add("malformed: equal line and arc", geo, [["Equal", 0, 2], ["Radius", 1, 2.0]])
        g.add("malformed: horizontal circle", geo, [["Horizontal", 1]])
        g.add("malformed: tangent to a point", geo, [["Tangent", 3, 1, 1]])
        g.add("invalid: geometry index out of range", geo, [["Horizontal", 7]])

    # Random sketches: lines, circles and arcs with constraints drawn from a pool
    pool_types = ["Coincident", "Horizontal", "Vertical", "Parallel", "Perpendicular", "Equal", "Distance",
                  "DistanceX", "DistanceY", "Radius", "PointOnObject", "Tangent", "Angle"]
    for k in range(60):
        geo = []
        for _ in range(g.r.randint(2, 5)):
            t = g.r.random()
            if t < 0.55:
                geo.append(L(g.jp((0, 0), 30), g.jp((0, 0), 30)))
            elif t < 0.8:
                geo.append(C(g.jp((0, 0), 30), g.r.uniform(2, 10)))
            else:
                a1 = g.r.uniform(-3, 3)
                geo.append(A(g.jp((0, 0), 30), g.r.uniform(2, 10), a1, a1 + g.r.uniform(0.5, 5)))
        lines = [i for i, x in enumerate(geo) if x["type"] == "LineSegment"]
        curves = [i for i, x in enumerate(geo) if x["type"] != "LineSegment"]
        cons = []
        for _ in range(g.r.randint(1, 9)):
            t = g.r.choice(pool_types)
            i = g.r.randrange(len(geo))
            jx = g.r.randrange(len(geo))
            pos = lambda n: g.r.choice([1, 2] if geo[n]["type"] == "LineSegment" else
                                       [3] if geo[n]["type"] == "Circle" else [1, 2, 3])
            if t == "Coincident" and i != jx:
                cons.append(["Coincident", i, pos(i), jx, pos(jx)])
            elif t in ("Horizontal", "Vertical") and lines:
                cons.append([t, g.r.choice(lines)])
            elif t in ("Parallel", "Perpendicular") and len(lines) > 1:
                a, b = g.r.sample(lines, 2)
                cons.append([t, a, b])
            elif t == "Equal" and i != jx:
                cons.append(["Equal", i, jx])
            elif t == "Distance":
                if geo[i]["type"] != "Circle" and g.r.random() < 0.5:
                    cons.append(["Distance", i, g.r.uniform(2, 20)])
                elif i != jx:
                    cons.append(["Distance", i, pos(i), jx, pos(jx), g.r.uniform(2, 20)])
            elif t in ("DistanceX", "DistanceY"):
                cons.append([t, i, pos(i), -1, 1, g.r.uniform(-20, 20)])
            elif t == "Radius" and curves:
                cons.append(["Radius", g.r.choice(curves), g.r.uniform(2, 10)])
            elif t == "PointOnObject" and i != jx:
                cons.append(["PointOnObject", i, pos(i), jx])
            elif t == "Tangent" and i != jx:
                cons.append(["Tangent", i, jx])
            elif t == "Angle" and lines:
                cons.append(["Angle", g.r.choice(lines), g.r.uniform(-3, 3)])
        g.add("random", geo, cons, g.drags_for(geo, 2))
    return g.cases


# ─── conics and B-splines (freecad_conics.json) ─────────────────────────────
#
# Each case names the curves whose internal geometry FreeCAD's exposeInternalGeometry adds (the
# axes and foci of a conic, a B-spline's pole circles, first weight, equalities and knot points, as
# the Sketcher's tools add them). make.py asks freecadcmd for that geometry first and writes the
# case with it, so both sides start from FreeCAD's own numbers; the case's constraints come after.

def _ax(angle):
    return [math.cos(angle), math.sin(angle)]


def E(c, a, b, ang=0.0, cons=False):
    return {"type": "Ellipse", "center": [float(c[0]), float(c[1])], "major_radius": float(a),
            "minor_radius": float(b), "x_axis": _ax(ang), **({"construction": True} if cons else {})}


def AE(c, a, b, ang, u1, u2):
    return {**E(c, a, b, ang), "type": "ArcOfEllipse", "start_angle": float(u1), "end_angle": float(u2)}


def AH(c, a, b, ang, u1, u2):
    return {**E(c, a, b, ang), "type": "ArcOfHyperbola", "start_angle": float(u1), "end_angle": float(u2)}


def AP(v, f, ang, u1, u2):
    return {"type": "ArcOfParabola", "center": [float(v[0]), float(v[1])], "focal": float(f), "x_axis": _ax(ang),
            "start_angle": float(u1), "end_angle": float(u2)}


def BS(poles, degree=3, periodic=False, weights=None):
    """A B-spline as the Sketcher's B-spline tool makes one: uniform knots, clamped unless periodic."""
    n = len(poles)
    if periodic:
        knots, mults = [float(k) for k in range(n + 1)], [1] * (n + 1)
    else:
        spans = n - degree
        knots = [k / spans for k in range(spans + 1)]
        mults = [degree + 1] + [1] * (spans - 1) + [degree + 1]
    d = {"type": "BSplineCurve", "poles": [[float(p[0]), float(p[1])] for p in poles], "knots": knots,
         "mults": mults, "degree": degree, "periodic": periodic}
    if weights:
        d["weights"] = [float(w) for w in weights]
    return d


INTERNAL = {"Ellipse": 4, "ArcOfEllipse": 4, "ArcOfHyperbola": 3, "ArcOfParabola": 2}


def internal_count(g):
    if g["type"] == "BSplineCurve":
        return len(g["poles"]) + len(g["knots"])
    return INTERNAL[g["type"]]


def internal_start(geometry, expose):
    """{geoId: the index of its first internal element} once every curve of expose is exposed in turn."""
    at, out = len(geometry), {}
    for gid in expose:
        out[gid] = at
        at += internal_count(geometry[gid])
    return out


DRAG_POS = {"Point": [1], "LineSegment": [0, 1, 2], "Circle": [0, 3], "ArcOfCircle": [0, 1, 2, 3],
            "Ellipse": [0, 3], "ArcOfEllipse": [0, 1, 2, 3], "ArcOfHyperbola": [0, 1, 2, 3],
            "ArcOfParabola": [0, 1, 2, 3], "BSplineCurve": [0, 1, 2]}


class ConicGen(Gen):
    def __init__(self):
        super().__init__(seed=20261025)

    def add(self, name, geometry, constraints, drags=(), expose=(), drop_equal=(), weight=None):
        self.cases.append({"name": f"c{len(self.cases):03d} {name}", "geometry": geometry,
                           "expose": list(expose), "drop_equal": list(drop_equal), "weight": weight,
                           "constraints": constraints, "drags": list(drags)})

    def drag(self, geo_count, gid, pos, scale=30.0):
        rel = self.r.random() < 0.3
        to = [self.j(3), self.j(3)] if rel else [self.j(scale), self.j(scale)]
        return {"geo": gid, "pos": pos, "to": to, "relative": rel}

    def drags_of(self, geometry, ids, n=2):
        out = []
        for _ in range(n):
            gid = self.r.choice(ids)
            out.append(self.drag(len(geometry), gid, self.r.choice(DRAG_POS[geometry[gid]["type"]])))
        return out


def generate_conics() -> list[dict]:
    g = ConicGen()
    pi = math.pi

    # Ellipses with their internal geometry: free, fully constrained, on and tangent to other curves
    for k in range(12):
        a = g.r.uniform(6, 30)
        b = a * g.r.uniform(0.2, 0.9)
        ang = g.r.uniform(-pi, pi)
        e = E(g.jp((0, 0), 10), a, b, ang)
        s = internal_start([e], [0])[0]  # major, minor, focus1, focus2
        g.add("ellipse, internal geometry, free", [e], [], expose=[0],
              drags=[g.drag(5, 0, 3), g.drag(5, s, 1), g.drag(5, s + 2, 1), g.drag(5, 0, 0)])
        g.add("ellipse, fully constrained", [e],
              [["Coincident", 0, 3, -1, 1], ["Horizontal", s], ["Distance", s, 2 * a + 1.0], ["Distance", s + 1, 2 * b]],
              expose=[0])
        g.add("ellipse, angle of the major axis, focus on the V axis", [e],
              [["Angle", s, g.r.uniform(-1.5, 1.5)], ["PointOnObject", s + 2, 1, -2], ["Distance", s + 1, b * 1.5]],
              expose=[0], drags=[g.drag(5, 0, 3)])
        p, line = P(g.jp((a, 0), 3)), L(g.jp((-40, -a - 5), 3), g.jp((40, -a - 3), 3))
        geo = [e, p, line]
        s = internal_start(geo, [0])[0]
        g.add("ellipse, point on it, tangent line", geo, [["PointOnObject", 1, 1, 0], ["Tangent", 2, 0]], expose=[0],
              drags=g.drags_of(geo, [0, 1, 2], 3))
        g.add("ellipse, line end tangent to it (endpoint to curve)", [e, line],
              [["Tangent", 1, 1, 0], ["Coincident", 0, 3, -1, 1]], expose=[0], drags=g.drags_of([e, line], [1], 2))
        g.add("ellipse without internal geometry", [e], [["PointOnObject", -1, 1, 0]], drags=g.drags_of([e], [0], 2))
        e2 = E(g.jp((40, 10), 8), a * g.r.uniform(0.6, 1.4), b * g.r.uniform(0.6, 1.0), g.r.uniform(-pi, pi))
        if e2["minor_radius"] > e2["major_radius"]:
            e2["minor_radius"] = e2["major_radius"] * 0.5
        g.add("equal ellipses", [e, e2], [["Equal", 0, 1]], expose=[0, 1], drags=g.drags_of([e, e2], [0, 1], 2))
        c = C(g.jp((a + 8, 0), 3), g.r.uniform(2, 8))
        g.add("malformed: circle tangent to ellipse", [e, c], [["Tangent", 1, 0]], expose=[0])
        geo = [e, c, P(g.jp((a, 0), 2))]
        g.add("circle tangent to ellipse via a point", geo,
              [["PointOnObject", 2, 1, 0], ["PointOnObject", 2, 1, 1], ["TangentViaPoint", 1, 0, 2, 1]],
              expose=[0], drags=g.drags_of(geo, [1, 2], 2))
        g.add("malformed: perpendicular line and ellipse, radius of ellipse", [e, line],
              [["Perpendicular", 1, 0], ["Radius", 0, 4.0]], expose=[0])

    # Arcs of ellipse
    for k in range(12):
        a = g.r.uniform(6, 30)
        b = a * g.r.uniform(0.2, 0.9)
        ang = g.r.uniform(-pi, pi)
        u1 = g.r.uniform(-3, 3)
        u2 = u1 + g.r.uniform(0.5, 5.5)
        ae = AE(g.jp((0, 0), 10), a, b, ang, u1, u2)
        s = internal_start([ae], [0])[0]
        g.add("arc of ellipse, internal geometry, free", [ae], [], expose=[0],
              drags=[g.drag(5, 0, 1), g.drag(5, 0, 2), g.drag(5, 0, 3), g.drag(5, s, 2)])
        g.add("arc of ellipse, fully constrained", [ae],
              [["Coincident", 0, 3, -1, 1], ["Horizontal", s], ["Distance", s, 2 * a], ["Distance", s + 1, 2 * b],
               ["Distance", 0, 1, 0, 2, a * 0.8], ["PointOnObject", 0, 1, -1]], expose=[0])
        geo = [ae, L(g.jp((0, 0), 30), g.jp((0, 0), 30))]
        g.add("arc of ellipse closed by a line", geo, [["Coincident", 0, 1, 1, 2], ["Coincident", 0, 2, 1, 1]],
              expose=[0], drags=g.drags_of(geo, [0, 1], 3))
        g.add("arc of ellipse tangent to a line at its end", geo,
              [["Tangent", 0, 2, 1, 1], ["Distance", 1, 12.0]], expose=[0], drags=g.drags_of(geo, [1], 2))
        ae2 = AE(g.jp((40, 0), 10), a * 0.7, b * 0.6, g.r.uniform(-pi, pi), 0.5, 2.5)
        g.add("equal arcs of ellipse, ellipse and arc", [ae, ae2, E(g.jp((0, 50), 5), a, b, 0.3)],
              [["Equal", 0, 1], ["Equal", 2, 0]], expose=[0, 1, 2])
        g.add("arc of ellipse ends symmetric about its major axis", [ae],
              [["Symmetric", 0, 1, 0, 2, s]], expose=[0], drags=[g.drag(5, 0, 3)])
        g.add("point on an arc of ellipse, block", [ae, P(g.jp((0, 0), 20))],
              [["PointOnObject", 1, 1, 0], ["Block", 0]], expose=[0], drags=[g.drag(6, 1, 1)])
        g.add("malformed: angle of an arc of ellipse", [ae], [["Angle", 0, 1.0]], expose=[0])

    # Arcs of hyperbola
    for k in range(10):
        a = g.r.uniform(3, 15)
        b = g.r.uniform(2, 15)
        ang = g.r.uniform(-pi, pi)
        u1 = g.r.uniform(-2, 0.5)
        u2 = u1 + g.r.uniform(0.4, 2.5)
        ah = AH(g.jp((0, 0), 10), a, b, ang, u1, u2)
        s = internal_start([ah], [0])[0]  # major, minor, focus
        g.add("arc of hyperbola, internal geometry, free", [ah], [], expose=[0],
              drags=[g.drag(4, 0, 1), g.drag(4, 0, 2), g.drag(4, 0, 3), g.drag(4, s + 2, 1)])
        g.add("arc of hyperbola, constrained", [ah],
              [["Coincident", 0, 3, -1, 1], ["Horizontal", s], ["Distance", s, a], ["Distance", s + 1, 2 * b],
               ["DistanceY", 0, 1, -1, 1, -b]], expose=[0])
        geo = [ah, L(g.jp((0, 0), 20), g.jp((0, 0), 20))]
        g.add("arc of hyperbola closed by a line, a point on it", geo + [P(g.jp((a, 0), 3))],
              [["Coincident", 0, 1, 1, 2], ["Coincident", 0, 2, 1, 1], ["PointOnObject", 2, 1, 0]],
              expose=[0], drags=g.drags_of(geo, [0, 1], 3))
        g.add("arc of hyperbola tangent to a line at its start", geo,
              [["Tangent", 0, 1, 1, 2]], expose=[0], drags=g.drags_of(geo, [0, 1], 2))
        g.add("equal arcs of hyperbola", [ah, AH(g.jp((40, 0), 5), a + 2, b * 0.8, 0.4, -1.0, 1.0)],
              [["Equal", 0, 1]], expose=[0, 1])

    # Arcs of parabola
    for k in range(10):
        f = g.r.uniform(1, 10)
        ang = g.r.uniform(-pi, pi)
        u1 = g.r.uniform(-12, 2)
        u2 = u1 + g.r.uniform(3, 15)
        ap = AP(g.jp((0, 0), 10), f, ang, u1, u2)
        s = internal_start([ap], [0])[0]  # focus point, focal axis line
        g.add("arc of parabola, internal geometry, free", [ap], [], expose=[0],
              drags=[g.drag(3, 0, 1), g.drag(3, 0, 2), g.drag(3, 0, 3), g.drag(3, s, 1)])
        g.add("arc of parabola, constrained", [ap],
              [["Coincident", 0, 3, -1, 1], ["Vertical", s + 1], ["Distance", s + 1, f + 1.0],
               ["Distance", 0, 1, 0, 2, 15.0], ["Horizontal", 0, 1, 0, 2]], expose=[0])
        geo = [ap, L(g.jp((0, 0), 20), g.jp((0, 0), 20))]
        g.add("arc of parabola closed by a line", geo, [["Coincident", 0, 1, 1, 2], ["Coincident", 0, 2, 1, 1]],
              expose=[0], drags=g.drags_of(geo, [0, 1], 3))
        g.add("point on an arc of parabola, tangent line", geo + [P(g.jp((0, 0), 10))],
              [["PointOnObject", 2, 1, 0], ["Tangent", 1, 2, 0]], expose=[0], drags=g.drags_of(geo, [1], 2))
        g.add("equal arcs of parabola", [ap, AP(g.jp((30, 0), 5), f * 1.5, 0.2, -5, 5)], [["Equal", 0, 1]],
              expose=[0, 1])

    # B-splines by control points, clamped, as the B-spline tool makes them (pole circles, the first
    # weight, equal weights, knot points)
    for k in range(14):
        degree = [2, 3, 3, 4][k % 4]
        n = degree + 1 + g.r.randint(0, 4)
        pts = [(10.0 * i + g.j(3), g.j(15)) for i in range(n)]
        bs = BS(pts, degree)
        s = internal_start([bs], [0])[0]  # n circles, then the knot points
        knots = len(bs["knots"])
        g.add(f"B-spline degree {degree}, {n} poles, free", [bs], [], expose=[0],
              drags=[g.drag(1, s, 3), g.drag(1, s + n - 1, 3), g.drag(1, 0, 0), g.drag(1, 0, 1)])
        cons = [["DistanceX", s + i, 3, -1, 1, pts[i][0]] for i in range(n)]
        cons += [["DistanceY", s + i, 3, -1, 1, pts[i][1] + 1.0] for i in range(n)]
        g.add(f"B-spline degree {degree}, poles placed", [bs], cons, expose=[0])
        g.add(f"B-spline degree {degree}, rational (weights set)", [bs],
              [["Weight", s + 1, 2.5], ["Weight", s + n - 2, 0.5]], expose=[0], drop_equal=[s + 1, s + n - 2],
              drags=[g.drag(1, s + 1, 3)])
        g.add(f"B-spline degree {degree}, first weight changed (all equal)", [bs], [], expose=[0], weight=2.0,
              drags=[g.drag(1, s, 0)])
        line = L(g.jp((pts[0][0] - 15, pts[0][1] - 5), 2), g.jp(pts[0], 2))
        geo = [bs, line]
        s = internal_start(geo, [0])[0]
        g.add(f"B-spline degree {degree}, line tangent at its start", geo,
              [["Coincident", 1, 2, 0, 1], ["Tangent", 1, 2, 0, 1]], expose=[0], drags=g.drags_of(geo, [1], 2))
        g.add(f"B-spline degree {degree}, closed by a line", geo,
              [["Coincident", 1, 2, 0, 1], ["Coincident", 1, 1, 0, 2]], expose=[0], drags=g.drags_of(geo, [0, 1], 2))
        geo = [bs, P(g.jp(pts[n // 2], 4))]
        g.add(f"B-spline degree {degree}, point on it", geo, [["PointOnObject", 1, 1, 0]], expose=[0],
              drags=[g.drag(2, 1, 1)])
        if knots > 2:
            kp = s + n + 1  # the second knot point (an interior knot of multiplicity 1)
            line = L(g.jp(pts[1], 6), g.jp(pts[2], 6))
            geo = [bs, line]
            s2 = internal_start(geo, [0])[0]
            g.add(f"B-spline degree {degree}, line tangent at a knot", geo,
                  [["Tangent", s2 + n + 1, 1, 1]], expose=[0], drags=g.drags_of(geo, [1], 2))
        geo = [bs, L(g.jp(pts[-1], 2), g.jp((pts[-1][0] + 10, pts[-1][1]), 2)), P(g.jp(pts[-1], 1))]
        g.add(f"B-spline degree {degree}, tangent via point", geo,
              [["PointOnObject", 2, 1, 0], ["PointOnObject", 2, 1, 1], ["TangentViaPoint", 1, 0, 2, 1]],
              expose=[0])
        bs2 = BS([(pts[-1][0] + 10.0 * i + g.j(2), g.j(10)) for i in range(degree + 1)], degree)
        g.add(f"two B-splines tangent end to end", [bs, bs2], [["Tangent", 0, 2, 1, 1]], expose=[0, 1],
              drags=g.drags_of([bs, bs2], [0, 1], 2))
        g.add(f"malformed: line tangent to a B-spline", [bs, line], [["Tangent", 1, 0]], expose=[0])

    # Periodic B-splines
    for k in range(8):
        degree = [2, 3][k % 2]
        n = degree + 2 + g.r.randint(0, 4)
        rad = g.r.uniform(8, 25)
        pts = [(rad * math.cos(2 * pi * i / n) + g.j(2), rad * math.sin(2 * pi * i / n) + g.j(2)) for i in range(n)]
        bs = BS(pts, degree, periodic=True)
        s = internal_start([bs], [0])[0]
        g.add(f"periodic B-spline degree {degree}, {n} poles, free", [bs], [], expose=[0],
              drags=[g.drag(1, s, 3), g.drag(1, 0, 0), g.drag(1, s + n, 1)])
        g.add(f"periodic B-spline degree {degree}, a point on it, a pole placed", [bs, P(g.jp((rad, 0), 3))],
              [["PointOnObject", 1, 1, 0], ["Coincident", s + 1, 3, -1, 1]], expose=[0], drags=[g.drag(2, 1, 1)])
        g.add(f"periodic B-spline degree {degree}, without internal geometry", [bs], [], drags=[g.drag(1, 0, 0)])

    # Random sketches mixing the new curves with lines and circles
    pool = ["Coincident", "PointOnObject", "Tangent", "Equal", "Distance", "Horizontal", "Vertical"]
    for k in range(30):
        geo = []
        for _ in range(g.r.randint(2, 4)):
            t = g.r.random()
            c0 = g.jp((0, 0), 30)
            if t < 0.3:
                geo.append(L(c0, g.jp((0, 0), 30)))
            elif t < 0.45:
                a = g.r.uniform(4, 15)
                geo.append(E(c0, a, a * g.r.uniform(0.3, 0.9), g.r.uniform(-pi, pi)))
            elif t < 0.6:
                a = g.r.uniform(4, 15)
                u1 = g.r.uniform(-3, 3)
                geo.append(AE(c0, a, a * g.r.uniform(0.3, 0.9), g.r.uniform(-pi, pi), u1, u1 + g.r.uniform(1, 4)))
            elif t < 0.7:
                geo.append(AH(c0, g.r.uniform(3, 10), g.r.uniform(3, 10), g.r.uniform(-pi, pi), -1.0, g.r.uniform(0, 1.5)))
            elif t < 0.8:
                geo.append(AP(c0, g.r.uniform(1, 6), g.r.uniform(-pi, pi), -g.r.uniform(2, 8), g.r.uniform(2, 8)))
            elif t < 0.9:
                geo.append(BS([g.jp((10.0 * i, 0), 5) for i in range(4)], 3))
            else:
                geo.append(C(c0, g.r.uniform(2, 10)))
        expose = [i for i, x in enumerate(geo) if x["type"] in INTERNAL or x["type"] == "BSplineCurve"
                  if g.r.random() < 0.6]
        ends = lambda n: [1, 2] if geo[n]["type"] in ("LineSegment", "ArcOfEllipse", "ArcOfHyperbola",
                                                       "ArcOfParabola", "BSplineCurve") else [3]
        cons = []
        for _ in range(g.r.randint(1, 5)):
            t = g.r.choice(pool)
            i, jx = g.r.randrange(len(geo)), g.r.randrange(len(geo))
            if i == jx:
                continue
            if t == "Coincident":
                cons.append(["Coincident", i, g.r.choice(ends(i)), jx, g.r.choice(ends(jx))])
            elif t == "PointOnObject":
                cons.append(["PointOnObject", i, g.r.choice(ends(i)), jx])
            elif t == "Tangent":
                if g.r.random() < 0.5:
                    cons.append(["Tangent", i, jx])
                else:
                    cons.append(["Tangent", i, g.r.choice(ends(i)), jx, g.r.choice(ends(jx))])
            elif t == "Equal":
                cons.append(["Equal", i, jx])
            elif t == "Distance":
                cons.append(["Distance", i, g.r.choice(ends(i)), jx, g.r.choice(ends(jx)), g.r.uniform(2, 20)])
            elif geo[i]["type"] == "LineSegment":
                cons.append([t, i])
        g.add("random conics", geo, cons, expose=expose, drags=g.drags_of(geo, list(range(len(geo))), 2))
    return g.cases


def expand(freecadcmd: str, cases: list[dict]) -> list[dict]:
    """The cases with the internal geometry FreeCAD exposes: geometry and constraints as FreeCAD made
    them, then the case's own constraints."""
    todo = [{"geometry": c["geometry"], "constraints": [], "expose": c["expose"]} for c in cases]
    built = run_freecad(freecadcmd, todo)
    out = []
    for c, b in zip(cases, built):
        if "error" in b:
            raise RuntimeError(f"{c['name']}: {b['error']}")
        geometry = []
        for x in b["geometry"]:
            x = {k: v for k, v in x.items() if k not in ("start_point", "end_point")}
            if not x.get("construction"):
                x.pop("construction", None)
            geometry.append(x)
        drop = set(c["drop_equal"])
        cons = [k for k in b["constraints"] if not (k[0] == "Equal" and k[1] in drop)]
        if c["weight"] is not None:
            cons = [[*k[:2], c["weight"]] if k[0] == "Weight" else k for k in cons]
        out.append({"name": c["name"], "geometry": geometry, "constraints": cons + c["constraints"],
                    "drags": c["drags"]})
    return out


# ─── running FreeCAD, and comparing ─────────────────────────────────────────

def run_freecad(freecadcmd: str, cases: list[dict], preload: bool = True) -> list[dict]:
    """FreeCAD's answers. With preload (the default), freecadcmd runs on bump_malloc.c, so that the
    solver's parameters are ordered as they are made, as in the port; see that file."""
    with tempfile.TemporaryDirectory() as tmp:
        cin, cout = Path(tmp) / "cases.json", Path(tmp) / "answers.json"
        cin.write_text(json.dumps(cases))
        env = {**os.environ, "SKETCHER_CASES": str(cin), "SKETCHER_ANSWERS": str(cout)}
        if preload:
            so = Path(tmp) / "bump_malloc.so"
            subprocess.run([os.environ.get("CC", "cc"), "-O2", "-shared", "-fPIC", "-o", str(so),
                            str(HERE / "bump_malloc.c")], check=True)
            env["LD_PRELOAD"] = str(so)
        subprocess.run([freecadcmd, str(HERE / "freecad_side.py")], env=env, check=True,
                       stdout=subprocess.DEVNULL)
        return json.loads(cout.read_text())


def close(a: float, b: float, tol: float = TOL) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def ours(case: dict) -> dict:
    """What the port answers for a case, in the shape freecad_side.py records."""
    from cad_agent import planegcs

    sketch = {"geometry": case["geometry"], "constraints": case["constraints"]}
    try:
        sk = planegcs.Sketch(sketch)
    except ValueError as e:
        return {"error": str(e)}

    def state(r):
        return {"geometry": r["stored_geometry"],
                "constructions": [g.get("construction", False) for g in r["stored_geometry"]],
                "values": [c["value"] for c in r["constraints"]]}

    with sk:
        r = sk.solve()
        out = {"status": r["status_code"], "dof": r["dof"],
               **{k: [i + 1 for i in r[k]] for k in ("conflicting", "redundant", "partially_redundant", "malformed")},
               **state(r), "drags": []}
        for d in case.get("drags", []):
            r = sk.move_geometry([(d["geo"], d["pos"])], d["to"], d.get("relative", False))
            out["drags"].append({"ok": r["status_code"] == 0, **state(r)})
    return out


def _flat(v) -> list:
    if isinstance(v, list):
        return [x for item in v for x in _flat(item)]
    return [v]


def diff_geometry(fc: list, me: list, where: str, tol: float) -> list[str]:
    if len(fc) != len(me):
        return [f"{where}: {len(me)} geometries, FreeCAD {len(fc)}"]
    out = []
    for i, (a, b) in enumerate(zip(fc, me)):
        if a["type"] != b["type"]:
            out.append(f"{where} geo {i}: {b['type']}, FreeCAD {a['type']}")
            continue
        for key, va in a.items():
            if key == "type" or (key in ("start_point", "end_point") and key not in b):
                continue
            vb = b[key]
            pa, pb = _flat(va), _flat(vb)
            if len(pa) != len(pb) or not all(close(x, y, tol) for x, y in zip(pa, pb)):
                out.append(f"{where} geo {i} {key}: {vb}, FreeCAD {va}")
    return out


def compare(case: dict, fc: dict, me: dict, tol: float = TOL) -> list[str]:
    """The differences between FreeCAD's answer and the port's, as readable lines (none: they agree)."""
    if "error" in fc or "error" in me:
        if ("error" in fc) != ("error" in me):
            return [f"error: {me.get('error')}, FreeCAD {fc.get('error')}"]
        return []
    out = []
    for k in ("status", "dof", "conflicting", "redundant", "partially_redundant", "malformed"):
        if fc[k] != me[k]:
            out.append(f"{k}: {me[k]}, FreeCAD {fc[k]}")
    out += diff_geometry(fc["geometry"], me["geometry"], "solve", tol)
    if fc["constructions"] != me["constructions"]:
        out.append(f"construction flags: {me['constructions']}, FreeCAD {fc['constructions']}")
    for i, (a, b) in enumerate(zip(fc["values"], me["values"])):
        if not close(a, b, tol):
            out.append(f"constraint {i} value: {b}, FreeCAD {a}")
    for n, (a, b) in enumerate(zip(fc["drags"], me["drags"])):
        if a["ok"] != b["ok"]:
            out.append(f"drag {n}: ok {b['ok']}, FreeCAD {a['ok']}")
        out += diff_geometry(a["geometry"], b["geometry"], f"drag {n}", tol)
    return out


def nudged(x, to=math.inf):
    """A case with every number in its geometry, constraint values and drags moved by one ulp."""
    if isinstance(x, float):
        return math.nextafter(x, to)
    if isinstance(x, list):
        return [nudged(v, to) for v in x]
    if isinstance(x, dict):
        return {k: (v if k in ("name", "type") else nudged(v, to)) for k, v in x.items()}
    return x


SETS = {"": "freecad.json", "conics": "freecad_conics.json"}


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    freecadcmd = args[0] if args else os.environ.get("FREECADCMD")
    if not freecadcmd:
        sys.exit("usage: make.py <freecadcmd> [--check] [--set=conics]   (or set FREECADCMD)")
    which = next((a.split("=", 1)[1] for a in argv if a.startswith("--set=")), "")
    if which not in SETS:
        sys.exit(f"--set must be one of {', '.join(k for k in SETS if k)}")
    cases = expand(freecadcmd, generate_conics()) if which == "conics" else generate()
    n = len(cases)
    answers = run_freecad(freecadcmd, cases + [nudged(c) for c in cases] + [nudged(c, -math.inf) for c in cases])
    # A case whose answer moves by more than TOL when its input moves by one ulp is sensitive to
    # rounding: an implementation whose arithmetic rounds differently in the last bit (another libm,
    # Eigen without SSE) may then land elsewhere, as FreeCAD itself does on another machine.
    golden = [{**c, "freecad": answers[i],
               "rounding_sensitive": bool(compare(c, answers[i], answers[n + i]) or compare(c, answers[i], answers[2 * n + i]))}
              for i, c in enumerate(cases)]
    (HERE / SETS[which]).write_text(
        "[\n" + ",\n".join(json.dumps(c, separators=(",", ":")) for c in golden) + "\n]\n")
    print(len(golden), "cases,", sum(c["rounding_sensitive"] for c in golden), "sensitive to rounding")
    if "--check" in argv:
        sys.path.insert(0, str(HERE.parents[2]))
        bad = 0
        for case in golden:
            d = compare(case, case["freecad"], ours(case))
            if d:
                bad += 1
                print(case["name"], *d, sep="\n    ")
        print(f"{len(golden) - bad} agree, {bad} differ")


if __name__ == "__main__":
    main(sys.argv[1:])
