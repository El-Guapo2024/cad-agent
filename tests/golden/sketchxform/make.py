"""Writes freecad.json: what FreeCAD's SketchObject does for the Sketcher's transform operations (mirror, copy, clone,
move, rectangular array, remove axes alignment) on a few hundred sketches, for tests/test_sketchxform.py to hold
ui/src/sketchxform.ts to.

    python3 tests/golden/sketchxform/make.py <freecadcmd>          # writes freecad.json
    python3 tests/golden/sketchxform/make.py <freecadcmd> --check  # and compares with ui/src/sketchxform.ts

<freecadcmd> may also come from $FREECADCMD (FreeCAD 26.3, weekly-2026.09.30 at 3160daf1e2b6). Each case is a sketch
(geometry, constraints, the curves whose internal geometry is exposed, reference and named constraints) and one
operation, called as the Sketcher's tools call it from Python: sketch.addSymmetric(geoIds, refGeoId, refPosId),
addCopy(geoIds, vector, clone), addMove(geoIds, vector), addRectangularArray(geoIds, vector, clone, rows, cols,
constrainDisplacement, perpScale) and removeAxesAlignment(geoIds). FreeCAD solves the sketch as the constraints go in;
the sketch it then has (recorded as "input") is what the port starts from. Recorded after the operation: the geometry
(with the construction flags) and every constraint (type, elements, alignment, value, name, driving). The cases come
from a fixed seed: rectangles, polylines, circles, arcs, points, conics with and without their internal geometry and
B-splines, with the constraints the Sketcher's tools leave on them, about lines, the axes and points.
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


def _ax(a):
    return [math.cos(a), math.sin(a)]


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


def E(c, a, b, ang=0.0):
    return {"type": "Ellipse", "center": [float(c[0]), float(c[1])], "major_radius": float(a),
            "minor_radius": float(b), "x_axis": _ax(ang)}


def AE(c, a, b, ang, u1, u2):
    return {**E(c, a, b, ang), "type": "ArcOfEllipse", "start_angle": float(u1), "end_angle": float(u2)}


def AH(c, a, b, ang, u1, u2):
    return {**E(c, a, b, ang), "type": "ArcOfHyperbola", "start_angle": float(u1), "end_angle": float(u2)}


def AP(v, f, ang, u1, u2):
    return {"type": "ArcOfParabola", "center": [float(v[0]), float(v[1])], "focal": float(f), "x_axis": _ax(ang),
            "start_angle": float(u1), "end_angle": float(u2)}


def BS(poles, degree=3):
    n = len(poles)
    spans = n - degree
    return {"type": "BSplineCurve", "poles": [[float(p[0]), float(p[1])] for p in poles],
            "knots": [k / spans for k in range(spans + 1)], "mults": [degree + 1] + [1] * (spans - 1) + [degree + 1],
            "degree": degree, "periodic": False}


class Scene:
    """A sketch built from pieces: each piece's GeoIds counted from where it starts."""

    def __init__(self, r):
        self.r = r
        self.geo, self.cons, self.expose, self.reference, self.names = [], [], [], [], {}

    def j(self, s=1.0):
        return self.r.uniform(-s, s)

    def add(self, geos, cons):
        base = len(self.geo)
        self.geo += geos

        def shift(c):
            out = list(c)
            for k in GEO_ARGS(c[0], len(c) - 1 - (1 if c[0] in DIMENSIONAL else 0)):
                if out[k] >= 0:
                    out[k] += base
            return out
        self.cons += [shift(c) for c in cons]
        return list(range(base, base + len(geos)))

    # ── the pieces ──
    def rect(self, dims=True):
        x0, y0, w, h = self.j(8), self.j(8), self.r.uniform(6, 20), self.r.uniform(6, 20)
        pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
        cons = [["Coincident", i, 2, (i + 1) % 4, 1] for i in range(4)]
        cons += [["Horizontal", 0], ["Horizontal", 2], ["Vertical", 1], ["Vertical", 3]]
        if dims:
            cons += [["DistanceX", 0, 1, 0, 2, w], ["DistanceY", 1, 1, 1, 2, h]]
        return self.add([L(pts[i], pts[(i + 1) % 4]) for i in range(4)], cons)

    def polyline(self):
        p = [(self.j(10), self.j(10))]
        for _ in range(3):
            a = self.r.uniform(-math.pi, math.pi)
            q = p[-1]
            p.append((q[0] + 8 * math.cos(a), q[1] + 8 * math.sin(a)))
        geos = [L(p[i], p[i + 1]) for i in range(3)]
        cons = [["Coincident", 0, 2, 1, 1], ["Coincident", 1, 2, 2, 1],
                ["Distance", 0, 1, 0, 2, 8.0], ["Angle", 1, math.atan2(p[2][1] - p[1][1], p[2][0] - p[1][0])],
                ["Angle", 0, 2, self.r.uniform(0.3, 2.5)]]
        if self.r.random() < 0.5:
            cons.append(["Distance", 2, 8.0])
        return self.add(geos, cons)

    def circles(self):
        c1 = C((self.j(10), self.j(10)), self.r.uniform(2, 6))
        c2 = C((self.j(10), self.j(10)), self.r.uniform(2, 6))
        cons = [["Radius", 0, c1["radius"]], ["Diameter", 1, 2 * c2["radius"]]]
        if self.r.random() < 0.4:
            cons.append(["Block", 1])
        return self.add([c1, c2], cons)

    def slot_arc(self):
        c, r = (self.j(10), self.j(10)), self.r.uniform(3, 7)
        a1 = self.r.uniform(-1, 1)
        a2 = a1 + self.r.uniform(1, 3)
        arc = A(c, r, a1, a2)
        e = [c[0] + r * math.cos(a2), c[1] + r * math.sin(a2)]
        t = [-math.sin(a2), math.cos(a2)]
        line = L(e, (e[0] + 6 * t[0], e[1] + 6 * t[1]))
        cons = [["Radius", 0, r], ["Tangent", 0, 2, 1, 1], ["Distance", 1, 6.0]]
        if self.r.random() < 0.5:
            cons.append(["PointOnObject", 0, 3, -1])
        return self.add([arc, line], cons)

    def points(self):
        p1, p2 = P((self.j(10), self.j(10))), P((self.j(10), self.j(10)))
        cons = [["DistanceX", 0, 1, p1["at"][0]], ["DistanceY", 1, 1, p2["at"][1]],
                ["Distance", 0, 1, 1, 1, math.dist(p1["at"], p2["at"])]]
        return self.add([p1, p2], cons)

    def sym_pair(self):
        a = L((self.j(10), self.j(10)), (self.j(10), self.j(10)))
        axis = L((self.j(3), -10), (self.j(3), 10), True)
        p = P((self.j(10), self.j(10)))
        cons = [["Symmetric", 0, 1, 0, 2, 1], ["Vertical", 1], ["Symmetric", 0, 1, 2, 1, -1, 1],
                ["Symmetric", 0, 2, 2, 1, -1]]
        return self.add([a, axis, p], cons)

    def axes_line(self):
        a = L((self.j(10), 0), (self.j(10) + 10, 0))
        b = L((self.j(10), self.j(10)), (self.j(10), self.j(10)))
        c = L((self.j(10), self.j(10)), (self.j(10), self.j(10)))
        cons = [["PointOnObject", 0, 1, -1], ["Horizontal", 0], ["Symmetric", 1, 1, 1, 2, -2],
                ["Parallel", 1, 2], ["Perpendicular", 0, 2], ["Equal", 1, 2], ["DistanceX", 2, 4.0],
                ["DistanceY", 1, 1, 2, 2, 3.0], ["Horizontal", 1, 2, 2, 1]]
        return self.add([a, b, c], cons)

    def ellipse(self, expose):
        e = E((self.j(10), self.j(10)), self.r.uniform(5, 9), self.r.uniform(2, 4), self.r.uniform(-1, 1))
        ids = self.add([e], [])
        if expose:
            self.expose.append(ids[0])
        return ids

    def arc_ellipse(self, expose):
        u1 = self.r.uniform(-2, 0)
        e = AE((self.j(10), self.j(10)), self.r.uniform(5, 9), self.r.uniform(2, 4), self.r.uniform(-1, 1), u1, u1 + self.r.uniform(1, 3))
        ids = self.add([e], [])
        if expose:
            self.expose.append(ids[0])
        return ids

    def hyperbola(self, expose):
        u1 = self.r.uniform(-1.5, -0.2)
        h = AH((self.j(10), self.j(10)), self.r.uniform(2, 5), self.r.uniform(1, 4), self.r.uniform(-1, 1), u1, u1 + self.r.uniform(0.5, 2))
        ids = self.add([h], [])
        if expose:
            self.expose.append(ids[0])
        return ids

    def parabola(self, expose):
        u1 = self.r.uniform(-4, -0.5)
        p = AP((self.j(10), self.j(10)), self.r.uniform(1, 3), self.r.uniform(-1, 1), u1, u1 + self.r.uniform(1, 5))
        ids = self.add([p], [])
        if expose:
            self.expose.append(ids[0])
        return ids

    def bspline(self, expose):
        x0, y0 = self.j(10), self.j(10)
        b = BS([(x0, y0), (x0 + 3, y0 + 4 + self.j()), (x0 + 6, y0 - 2 + self.j()), (x0 + 9, y0 + 1)])
        ids = self.add([b], [])
        if expose:
            self.expose.append(ids[0])
        return ids


DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle", "Weight")


def GEO_ARGS(t, n):
    """Which arguments of Sketcher.Constraint(t, ...) (n of them, the value left out) are GeoIds."""
    if t in ("Coincident", "Symmetric") or n >= 4:
        return [1, 3, 5][: (n + 1) // 2]
    if t in ("Parallel", "Equal", "Perpendicular", "Tangent", "Angle") and n == 2:
        return [1, 2]
    if n == 3:
        return [1, 3]
    if n == 2:
        return [1]
    return [1]


PIECES = ["rect", "polyline", "circles", "slot_arc", "points", "sym_pair", "axes_line"]
CONICS = ["ellipse", "arc_ellipse", "hyperbola", "parabola", "bspline"]


def scene(r, conics=False):
    s = Scene(r)
    groups = []
    for name in r.sample(PIECES, r.randint(1, 3)):
        groups.append(getattr(s, name)())
    if conics:
        for name in r.sample(CONICS, r.randint(1, 2)):
            groups.append(getattr(s, name)(r.random() < 0.6))
    dims = [i for i, c in enumerate(s.cons) if c[0] in DIMENSIONAL]
    if dims and r.random() < 0.3:
        s.reference.append(r.choice(dims))
    if s.cons and r.random() < 0.3:
        s.names[r.randrange(len(s.cons))] = "Named"
    return s, groups


def pick(r, s, groups):
    """Some of the scene's geometry, in a random order (the selection order the tools pass on)."""
    ids = [g for grp in r.sample(groups, r.randint(1, len(groups))) for g in grp]
    if r.random() < 0.3:
        ids = r.sample(ids, max(1, len(ids) - 1))
    if r.random() < 0.3:
        r.shuffle(ids)
    return ids


def refs(r, s):
    """Something to mirror about: a line of the sketch, an axis, the root point, a point of the sketch."""
    lines = [i for i, g in enumerate(s.geo) if g["type"] == "LineSegment"]
    pts = [i for i, g in enumerate(s.geo) if g["type"] == "Point"]
    out = [(-1, 0), (-2, 0), (-1, 1)]
    if lines:
        out += [(r.choice(lines), 0), (r.choice(lines), r.choice([1, 2]))]
    if pts:
        out.append((r.choice(pts), 1))
    circ = [i for i, g in enumerate(s.geo) if g["type"] in ("Circle", "ArcOfCircle", "Ellipse")]
    if circ:
        out.append((r.choice(circ), 3))
    return out


def generate() -> list[dict]:
    r = random.Random(20261024)
    cases = []

    def add(name, s, op):
        cases.append({"name": f"{len(cases):03d} {name}", "geometry": s.geo, "constraints": s.cons, "expose": s.expose,
                      "reference": s.reference, "names": {str(k): v for k, v in s.names.items()}, "op": op})

    for k in range(70):
        s, groups = scene(r, conics=k % 3 == 0)
        ref = r.choice(refs(r, s))
        ids = pick(r, s, groups)
        if ref[1] == 0 and ref[0] in ids and r.random() < 0.7:
            ids = [i for i in ids if i != ref[0]] or ids
        add("mirror", s, ["symmetric", [ids, ref[0], ref[1]]])
    for k in range(60):
        s, groups = scene(r, conics=k % 3 == 1)
        v = [r.uniform(-20, 20), r.uniform(-20, 20)]
        add("copy" if k % 2 else "clone", s, ["copy", [pick(r, s, groups), v, k % 2 == 0]])
    for k in range(30):
        s, groups = scene(r, conics=k % 3 == 2)
        add("move", s, ["move", [pick(r, s, groups), [r.uniform(-20, 20), r.uniform(-20, 20)]]])
    for k in range(50):
        s, groups = scene(r, conics=k % 4 == 0)
        v = [r.uniform(-20, 20), r.uniform(-20, 20)]
        rows, cols = r.randint(1, 4), r.randint(1, 3)
        add("array", s, ["array", [pick(r, s, groups), v, r.random() < 0.5, rows, cols, r.random() < 0.5, r.choice([1.0, 0.5, 0.75])]])
    for k in range(40):
        s, groups = scene(r, conics=k % 4 == 0)
        add("remove axes alignment", s, ["removeAxes", [pick(r, s, groups)]])
    # the refusals: internal geometry first without the curve it defines
    for k in range(6):
        s = Scene(r)
        e = s.ellipse(True)
        s.rect()
        internal = len(s.geo)  # the first internal element, once exposed
        op = ["copy", [[internal, 1], [5.0, 3.0], False]] if k % 2 else ["array", [[internal, e[0]], [5.0, 3.0], True, 2, 2, False, 1.0]]
        add("internal geometry first (refused)" if k % 2 else "internal geometry first, with its ellipse", s, op)
    # no displacement: the construction line has no length (refused)
    for k in range(2):
        s, groups = scene(r)
        op = ["copy", [pick(r, s, groups), [0.0, 0.0], False]] if k == 0 else ["array", [pick(r, s, groups), [0.0, 0.0], False, 2, 2, False, 1.0]]
        add("no displacement (refused)", s, op)
    # everything (an empty list)
    for k in range(4):
        s, groups = scene(r)
        add("copy everything (an empty list)", s, ["copy", [[], [7.0, -2.0], k % 2 == 0]])
    return cases


def run_freecad(freecadcmd: str, cases: list[dict]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        cin, cout = Path(tmp) / "cases.json", Path(tmp) / "answers.json"
        cin.write_text(json.dumps(cases))
        env = {**os.environ, "SKETCHXFORM_CASES": str(cin), "SKETCHXFORM_ANSWERS": str(cout)}
        subprocess.run([freecadcmd, str(HERE / "freecad_side.py")], env=env, check=True, stdout=subprocess.DEVNULL)
        return json.loads(cout.read_text())


def ours(cases: list[dict]) -> list[dict]:
    """What ui/src/sketchxform.ts does for the cases (tests/golden/sketchxform/ours.mjs, under node)."""
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
    fmt = lambda c: f"{c['type']}{c['elements']}{c.get('alignment', '')}{'' if c['driving'] else ' ref'}{' ' + c['name'] if c['name'] else ''}"
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
