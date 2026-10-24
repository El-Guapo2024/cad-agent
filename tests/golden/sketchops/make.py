"""Writes freecad.json: what FreeCAD's SketchObject does for the Sketcher's editing operations (trim, split, extend,
fillet and chamfer) on a few hundred sketches, for tests/test_sketchops.py to hold ui/src/sketchops.ts to.

    python3 tests/golden/sketchops/make.py <freecadcmd>          # writes freecad.json
    python3 tests/golden/sketchops/make.py <freecadcmd> --check  # and compares with ui/src/sketchops.ts

<freecadcmd> may also come from $FREECADCMD (FreeCAD 26.3, weekly-2026.09.30 at 3160daf1e2b6). Each case is a sketch
(geometry and constraints, as tests/golden/sketcher's cases write them) and one operation, done as the Sketcher's tools
call them from Python: sketch.trim(GeoId, point, includeAxes), split(GeoId, point), extend(GeoId, increment, PosId),
fillet(GeoId1, GeoId2, refPnt1, refPnt2, radius, trim, createCorner, chamfer) and fillet(GeoId, PosId, radius, trim,
createCorner, chamfer). Recorded: the geometry (with the construction flags) and every constraint (type, elements,
alignment, value) after it. The cases come from a fixed seed: crossing lines, polylines, rectangles cut by lines,
circles, arcs and ellipses cut by lines and by each other, with the constraints the drawing tools leave on them.
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


def C(c, r):
    return {"type": "Circle", "center": [float(c[0]), float(c[1])], "radius": float(r)}


def A(c, r, a1, a2):
    return {"type": "ArcOfCircle", "center": [float(c[0]), float(c[1])], "radius": float(r),
            "start_angle": float(a1), "end_angle": float(a2)}


def E(c, a, b, ang=0.0):
    return {"type": "Ellipse", "center": [float(c[0]), float(c[1])], "major_radius": float(a),
            "minor_radius": float(b), "x_axis": [math.cos(ang), math.sin(ang)]}


def at_line(l, t):
    return [l["start"][0] + t * (l["end"][0] - l["start"][0]), l["start"][1] + t * (l["end"][1] - l["start"][1])]


def at_circle(c, a):
    return [c["center"][0] + c["radius"] * math.cos(a), c["center"][1] + c["radius"] * math.sin(a)]


def at_ellipse(e, u):
    x = e["x_axis"]
    y = [-x[1], x[0]]
    a, b = e["major_radius"] * math.cos(u), e["minor_radius"] * math.sin(u)
    return [e["center"][0] + a * x[0] + b * y[0], e["center"][1] + a * x[1] + b * y[1]]


class Gen:
    def __init__(self, seed=20261026):
        self.r = random.Random(seed)
        self.cases = []

    def j(self, s=1.0):
        return self.r.uniform(-s, s)

    def add(self, name, geometry, constraints, op):
        self.cases.append({"name": f"{len(self.cases):03d} {name}", "geometry": geometry, "constraints": constraints,
                           "op": op})


def rect(g, x0, y0, w, h):
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    geo = [L(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    cons = [["Coincident", i, 2, (i + 1) % 4, 1] for i in range(4)]
    cons += [["Horizontal", 0], ["Horizontal", 2], ["Vertical", 1], ["Vertical", 3]]
    return geo, cons


def generate() -> list[dict]:
    g = Gen()
    pi = math.pi

    # Trim: lines crossing lines
    for k in range(10):
        a = L(g.r.choice([(-20, 0), (-20, -5)]), (20 + g.j(3), 3 + g.j(3)))
        b = L((g.j(5), -15 + g.j(2)), (g.j(5), 15 + g.j(2)))
        c = L((10 + g.j(3), -15), (12 + g.j(3), 15))
        geo = [a, b, c]
        g.add("trim a line between two lines", geo, [], ["trim", [0, at_line(a, 0.62 + g.j(0.05)), False]])
        g.add("trim a line's end beyond a crossing", geo, [], ["trim", [0, at_line(a, 0.95), False]])
        g.add("trim a line's start before a crossing", geo, [["Horizontal", 0]], ["trim", [0, at_line(a, 0.1), False]])
        g.add("trim a line with constraints on it", geo,
              [["Distance", 0, 40.0], ["Coincident", 0, 1, -1, 1], ["PointOnObject", 1, 1, 0], ["Angle", 0, 1, 0.5]],
              ["trim", [0, at_line(a, 0.62), False]])
        g.add("trim a line crossing nothing (deleted)", [a, L((50, 50), (60, 55))], [["Coincident", 0, 2, 1, 1]],
              ["trim", [0, at_line(a, 0.5), False]])
        g.add("trim to the axes", [L((-10 + g.j(), -8 + g.j()), (12 + g.j(), 9 + g.j()))], [],
              ["trim", [0, [1.0 + g.j(0.5), 0.8 + g.j(0.5)], True]])
        g.add("trim with the axes off", [L((-10, -8), (12, 9)), L((-10, 5), (10, -5))], [],
              ["trim", [0, at_line(L((-10, -8), (12, 9)), 0.2), False]])

    # Trim: rectangles cut by a line, a polyline's corner
    for k in range(8):
        w, h = g.r.uniform(10, 40), g.r.uniform(10, 40)
        geo, cons = rect(g, g.j(5), g.j(5), w, h)
        cut = L((geo[0]["start"][0] + w * 0.4 + g.j(), geo[0]["start"][1] - 5), (geo[0]["start"][0] + w * 0.45 + g.j(), geo[0]["start"][1] + h + 5))
        geo2 = geo + [cut]
        g.add("trim a rectangle's side at a cutting line", geo2, cons, ["trim", [0, at_line(geo2[0], 0.2), False]])
        g.add("trim the cutting line inside the rectangle", geo2, cons, ["trim", [4, at_line(cut, 0.5), False]])
        g.add("trim the cutting line outside", geo2, cons + [["Vertical", 4]] if False else cons, ["trim", [4, at_line(cut, 0.03), False]])
        g.add("trim a rectangle's side with a dimension", geo2, cons + [["DistanceX", 0, w], ["DistanceY", 1, h]],
              ["trim", [2, at_line(geo2[2], 0.7), False]])

    # Trim: circles and arcs
    for k in range(10):
        r = g.r.uniform(5, 15)
        c = C((g.j(3), g.j(3)), r)
        l1 = L((-r - 5, g.j(r * 0.6)), (r + 5, g.j(r * 0.6)))
        l2 = L((g.j(r * 0.6), -r - 5), (g.j(r * 0.6), r + 5))
        g.add("trim a circle at a line", [c, l1], [], ["trim", [0, at_circle(c, pi / 2 + g.j(0.3)), False]])
        g.add("trim a circle at two lines", [c, l1, l2], [["Radius", 0, r]], ["trim", [0, at_circle(c, pi / 4 + g.j(0.2)), False]])
        g.add("trim a line inside a circle", [c, l1], [], ["trim", [1, at_line(l1, 0.5), False]])
        g.add("trim a line's end outside a circle", [c, l1], [], ["trim", [1, at_line(l1, 0.98), False]])
        a1 = g.r.uniform(-1, 0.5)
        arc = A((g.j(2), g.j(2)), r, a1, a1 + g.r.uniform(2, 4))
        g.add("trim an arc between two lines", [arc, l1, l2], [], ["trim", [0, at_circle(arc, (arc["start_angle"] + arc["end_angle"]) / 2), False]])
        g.add("trim an arc's end at a line", [arc, l2], [["Radius", 0, r]], ["trim", [0, at_circle(arc, arc["end_angle"] - 0.05), False]])
        g.add("trim an arc's start at a line", [arc, l2], [["Coincident", 0, 3, -1, 1]], ["trim", [0, at_circle(arc, arc["start_angle"] + 0.05), False]])
        c2 = C((r * 1.2 + g.j(), g.j()), r * g.r.uniform(0.6, 1.2))
        g.add("trim a circle at a circle", [c, c2], [["Equal", 0, 1]] if False else [], ["trim", [0, at_circle(c, 0.0), False]])
        g.add("trim a tangent line at a circle", [c, L((-r - 5, r), (r + 5, r))], [["Tangent", 1, 0]], ["trim", [1, [r + 4, r], False]])

    # Trim: ellipses, with and without their internal geometry
    for k in range(6):
        a = g.r.uniform(8, 15)
        b = a * g.r.uniform(0.4, 0.8)
        e = E((g.j(2), g.j(2)), a, b, g.r.uniform(-1, 1))
        line = L((-a - 5, g.j(b * 0.5)), (a + 5, g.j(b * 0.5)))
        g.add("trim an ellipse at a line", [e, line], [], ["trim", [0, at_ellipse(e, pi / 2), False]])
        g.add("trim a line inside an ellipse", [e, line], [], ["trim", [1, at_line(line, 0.5), False]])
        exposed = [e, line, L(at_ellipse(e, 0), at_ellipse(e, pi), True), L(at_ellipse(e, pi / 2), at_ellipse(e, -pi / 2), True)]
        g.add("trim an ellipse with its axes", exposed,
              [["InternalAlignment:EllipseMajorDiameter", 2, 0], ["InternalAlignment:EllipseMinorDiameter", 3, 0]],
              ["trim", [0, at_ellipse(e, pi / 2), False]])

    # Split
    for k in range(8):
        l = L((g.j(5), g.j(5)), (20 + g.j(5), 10 + g.j(5)))
        g.add("split a line", [l, L(l["end"], (30, 30))], [["Coincident", 0, 2, 1, 1], ["Horizontal", 1], ["Distance", 0, 20.0]],
              ["split", [0, at_line(l, g.r.uniform(0.2, 0.8))]])
        c = C((g.j(3), g.j(3)), g.r.uniform(4, 12))
        g.add("split a circle", [c], [["Radius", 0, c["radius"]], ["Coincident", 0, 3, -1, 1]], ["split", [0, at_circle(c, g.r.uniform(-3, 3))]])
        arc = A((g.j(3), g.j(3)), g.r.uniform(4, 12), 0.2, 2.8)
        g.add("split an arc", [arc, L(at_circle(arc, 2.8), (-20, 20))], [["Coincident", 0, 2, 1, 1], ["Radius", 0, arc["radius"]]],
              ["split", [0, at_circle(arc, g.r.uniform(0.5, 2.5))]])
        e = E((g.j(3), g.j(3)), 10, 6, g.r.uniform(-1, 1))
        g.add("split an ellipse", [e], [], ["split", [0, at_ellipse(e, g.r.uniform(-3, 3))]])

    # Extend
    for k in range(8):
        l = L((g.j(5), g.j(5)), (20 + g.j(5), 3 + g.j(5)))
        g.add("extend a line's end", [l], [], ["extend", [0, g.r.uniform(2, 10), 2]])
        g.add("extend a line's start", [l], [["Horizontal", 0]], ["extend", [0, g.r.uniform(2, 10), 1]])
        g.add("shorten a line", [l, L(l["start"], (-10, -10))], [["Coincident", 0, 1, 1, 1]], ["extend", [0, -g.r.uniform(1, 5), 2]])
        arc = A((g.j(3), g.j(3)), g.r.uniform(4, 12), 0.2 + g.j(0.1), 2.0 + g.j(0.1))
        g.add("extend an arc's end", [arc], [], ["extend", [1 - 1, g.r.uniform(0.2, 1.5), 2]])
        g.add("extend an arc's start", [arc], [["Radius", 0, arc["radius"]]], ["extend", [0, g.r.uniform(0.2, 1.5), 1]])

    # Fillet and chamfer between two lines
    for k in range(10):
        ang = g.r.uniform(0.6, 2.5)
        corner = (g.j(5), g.j(5))
        l1 = L(corner, (corner[0] + 20 + g.j(3), corner[1] + g.j(2)))
        l2 = L(corner, (corner[0] + 15 * math.cos(ang), corner[1] + 15 * math.sin(ang)))
        geo = [l1, l2]
        cons = [["Coincident", 0, 1, 1, 1]]
        r1, r2 = at_line(l1, 0.5), at_line(l2, 0.5)
        rad = g.r.uniform(1, 4)
        g.add("fillet two lines, keep the corner", geo, cons, ["fillet", [0, 1, r1, r2, rad, True, True, False]])
        g.add("fillet two lines", geo, cons + [["Horizontal", 0]], ["fillet", [0, 1, r1, r2, rad, True, False, False]])
        g.add("chamfer two lines, keep the corner", geo, cons, ["fillet", [0, 1, r1, r2, rad, True, True, True]])
        g.add("fillet two lines, no trim", geo, cons, ["fillet", [0, 1, r1, r2, rad, False, False, False]])
        g.add("fillet at the corner point", geo, cons + [["Distance", 0, 20.0]], ["fillet_point", [0, 1, rad, True, True, False]])
        rgeo, rcons = rect(g, g.j(5), g.j(5), g.r.uniform(15, 30), g.r.uniform(15, 30))
        g.add("fillet a rectangle's corner", rgeo, rcons, ["fillet_point", [1, 1, rad, True, True, False]])
        g.add("chamfer a rectangle's corner", rgeo, rcons, ["fillet_point", [2, 2, rad, True, False, True]])
        g.add("fillet two lines that do not touch (refused)", [l1, L((corner[0] + 40, corner[1] + 1), (corner[0] + 40, corner[1] + 20))], [],
              ["fillet", [0, 1, r1, [corner[0] + 40, corner[1] + 10], rad, True, True, False]])
    return g.cases


def run_freecad(freecadcmd: str, cases: list[dict]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        cin, cout = Path(tmp) / "cases.json", Path(tmp) / "answers.json"
        cin.write_text(json.dumps(cases))
        env = {**os.environ, "SKETCHOPS_CASES": str(cin), "SKETCHOPS_ANSWERS": str(cout)}
        subprocess.run([freecadcmd, str(HERE / "freecad_side.py")], env=env, check=True, stdout=subprocess.DEVNULL)
        return json.loads(cout.read_text())


def ours(cases: list[dict]) -> list[dict]:
    """What ui/src/sketchops.ts does for the cases (tests/golden/sketchops/ours.mjs, under node)."""
    with tempfile.TemporaryDirectory() as tmp:
        cin = Path(tmp) / "cases.json"
        cin.write_text(json.dumps(cases))
        r = subprocess.run(["node", str(HERE / "ours.mjs"), str(cin)], capture_output=True, text=True, check=True, cwd=ROOT)
        return json.loads(r.stdout)


def close(a, b, tol=TOL):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def _flat(v):
    if isinstance(v, list):
        return [x for item in v for x in _flat(item)]
    return [v]


def compare(case: dict, fc: dict, me: dict, tol: float = TOL) -> list[str]:
    if "error" in fc or "error" in me:
        return [] if ("error" in fc) == ("error" in me) else [f"error: {me.get('error')}, FreeCAD {fc.get('error')}"]
    out = []
    if (fc["ok"] is True) != (me["ok"] is True):
        out.append(f"ok: {me['ok']}, FreeCAD {fc['ok']}")
    if len(fc["geometry"]) != len(me["geometry"]):
        out.append(f"{len(me['geometry'])} geometries, FreeCAD {len(fc['geometry'])}")
    else:
        for i, (a, b) in enumerate(zip(fc["geometry"], me["geometry"])):
            if a["type"] != b["type"]:
                out.append(f"geo {i}: {b['type']}, FreeCAD {a['type']}")
                continue
            for key, va in a.items():
                if key == "type" or (key in ("start_point", "end_point") and key not in b):
                    continue
                pa, pb = _flat(va), _flat(b.get(key))
                if len(pa) != len(pb) or not all(close(x, y, tol) for x, y in zip(pa, pb)):
                    out.append(f"geo {i} {key}: {b.get(key)}, FreeCAD {va}")
    if fc["constructions"] != me["constructions"]:
        out.append(f"construction: {me['constructions']}, FreeCAD {fc['constructions']}")
    fmt = lambda c: f"{c['type']}{c['elements']}{c.get('alignment', '')}"
    if [fmt(c) for c in fc["constraints"]] != [fmt(c) for c in me["constraints"]]:
        out.append(f"constraints\n      ours     {[fmt(c) for c in me['constraints']]}\n      FreeCAD  {[fmt(c) for c in fc['constraints']]}")
    else:
        for i, (a, b) in enumerate(zip(fc["constraints"], me["constraints"])):
            if "value" in a and not close(a["value"], b.get("value", float("nan")), tol):
                out.append(f"constraint {i} value: {b.get('value')}, FreeCAD {a['value']}")
    return out


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
