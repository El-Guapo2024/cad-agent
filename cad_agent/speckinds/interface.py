"""[[interface]]: bolt holes in `a` that point into `b` must line up with a hole in `b`.

The format is in cad_agent/spec.py. This module also holds the hole finder, `holes()`, which reads
the cylinders of a solid: `cad_agent.spec.holes` re-exports it, and checks/cuts.py and the eval
reference designs import it from there.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, spec_kind
from .kit import (Unusable as _Unusable, get_body as _body, require as _need, row as _row)

# ─── Interfaces: holes that must line up ─────────────────────────────────────

FULL_TURN = 2.0 * math.pi
BORE_TURN = 1.5 * math.pi       # 270 degrees: the least a bore turns, since a teardrop's point takes 90
ARC_TOL = 1e-3          # radians: how far two arcs may miss meeting, or a half turn be off
ALIGNED = math.cos(math.radians(2.0))     # how well a slot's two ends must face each other


def holes(solid) -> list[dict]:
    """The holes and slots of a solid: the places a fastener can go.

    A hole is the concave cylinders of one radius on one axis that together turn 270 degrees
    or more without a break. Most go all the way round. A printed hole lying on its side has a
    teardrop's point, a shaft bore a D's flat, a clamp a slit: each takes part of the circle and
    leaves the bore what it was, so none of them changes `dia`. A counterbore shares the axis of
    the hole it widens, so it is part of that hole: `dia` is the narrowest bore, which is what a
    screw passes, and `bores` lists every diameter. OCCT often splits one cylinder in two at a
    seam, so the angles are added up per axis and radius, not taken from one face.

    A slot is two half-turn cylinders of one radius on parallel axes, each bulging away from
    the other. Its `ends` are those axes at mid-depth, `point` is halfway between them and
    `dia` is its width. A hole is the same with both ends on one axis, so `ends` serves both.

    Nothing else is a hole. An inside-corner fillet covers a quarter turn, and a notch open
    at one end half of one. A boss has the same kind of face with the normal pointing away.
    """
    axes = []                                          # the cylinders on each axis
    for c in _concave_cylinders(solid):
        for group in axes:
            if _same_axis(group[0], c):
                group.append(c)
                break
        else:
            axes.append([c])
    found, halves = [], []
    for group in axes:
        d, x = group[0]["dir"], group[0]["x"]
        radii = []                                     # the cylinders of one diameter each
        for c in group:
            for same in radii:
                if abs(same[0]["dia"] - c["dia"]) < 1e-3:
                    same.append(c)
                    break
            else:
                radii.append([c])
        bores, arcs = [], []
        for same in radii:
            cover = _cover([_arc(c, d, x) for c in same])
            turn = max(end - start for start, end in cover)        # the longest unbroken arc
            if turn >= BORE_TURN - ARC_TOL:
                bores.append(same)
            elif len(cover) == 1 and abs(turn - math.pi) <= ARC_TOL:
                arcs.append((same, sum(cover[0]) / 2.0))
        if bores:
            found.append(_hole(group[0]["point"], d, bores))
        else:                                          # on an axis with a hole, a half turn is its step
            halves += [_half(same, d, x, mid) for same, mid in arcs]
    return found + _slots(halves)


def _concave_cylinders(solid) -> list[dict]:
    """Every cylinder face whose outward normal points toward its own axis."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    found = []
    for f in solid.faces():
        # Read the cylinder from OCCT itself: build123d's Face.radius can be None
        # for a located face, and Face.center() is not always on the surface.
        surf = BRepAdaptor_Surface(f.wrapped)
        if surf.GetType() != GeomAbs_Cylinder:
            continue
        cyl = surf.Cylinder()
        frame = cyl.Position()
        o, d = _vector(frame.Location()), _vector(frame.Direction()).normalized()
        p = f.position_at(0.5, 0.5)                    # a point on the face itself
        foot = o + d * ((p - o).dot(d))
        if (foot - p).dot(f.normal_at(p)) <= 0:
            continue                                   # a boss, not a hole
        v0, v1 = surf.FirstVParameter(), surf.LastVParameter()
        found.append({"point": o, "dir": d, "dia": 2 * cyl.Radius(), "face": f,
                      "x": _vector(frame.XDirection()), "y": _vector(frame.YDirection()),
                      "u": (surf.FirstUParameter(), surf.LastUParameter()),
                      "ends": (o + d * v0, o + d * v1)})   # the axis where the face starts and stops
    return found


def _vector(g):
    """A build123d Vector from an OCCT point or direction."""
    from build123d import Vector
    return Vector(g.X(), g.Y(), g.Z())


def _arc(c, d, x):
    """The angles a cylinder face covers around the axis d, as (start, span) counterclockwise from x."""
    u0, u1 = c["u"]
    span = min(u1 - u0, FULL_TURN)
    start = c["x"] * math.cos(u0) + c["y"] * math.sin(u0)
    start = math.atan2(start.dot(d.cross(x)), start.dot(x))
    if c["x"].cross(c["y"]).dot(d) < 0:                # a left-handed OCCT frame: u runs clockwise
        start -= span
    return start % FULL_TURN, span


def _cover(arcs) -> list[list[float]]:
    """Arcs (start, span) of one circle merged into disjoint [start, end] intervals."""
    merged = []
    for start, span in sorted(arcs):
        if merged and start <= merged[-1][1] + ARC_TOL:
            merged[-1][1] = max(merged[-1][1], start + span)
        else:
            merged.append([start, start + span])
    while len(merged) > 1 and merged[-1][1] >= merged[0][0] + FULL_TURN - ARC_TOL:
        first = merged.pop(0)                          # the last arc runs on past 2 pi into the first
        merged[-1][1] = max(merged[-1][1], first[1] + FULL_TURN)
    return merged


def _hole(base, d, bores) -> dict:
    """One hole from the bores on an axis, its middle halfway along all of them."""
    z = [p.dot(d) for same in bores for c in same for p in c["ends"]]
    point = base + d * ((min(z) + max(z)) / 2.0 - base.dot(d))
    narrowest = min(bores, key=lambda same: same[0]["dia"])
    return {"kind": "hole", "point": point, "ends": (point, point), "dir": d,
            "dia": narrowest[0]["dia"], "bores": sorted(same[0]["dia"] for same in bores),
            "face": narrowest[0]["face"]}


def _half(same, d, x, mid) -> dict:
    """A half-turn cylinder, maybe a slot's end; `wall` points from its axis to the middle of the arc."""
    return {"point": same[0]["point"], "dir": d, "dia": same[0]["dia"], "face": same[0]["face"],
            "wall": x * math.cos(mid) + d.cross(x) * math.sin(mid),
            "ends": [p for c in same for p in c["ends"]]}


def _slots(halves) -> list[dict]:
    """Pair half-turn cylinders into slots, nearest first, each one used once.

    Two make a slot when they have one radius, parallel axes, and each wall bulges away from the
    other end, so the arcs sit at the ends of the line between the axes.
    """
    pairs = []
    for i, a in enumerate(halves):
        for j in range(i + 1, len(halves)):
            b = halves[j]
            if abs(a["dia"] - b["dia"]) >= 1e-3 or not _parallel(a, b, 2.0):
                continue
            across = b["point"] - a["point"]
            across = across - a["dir"] * across.dot(a["dir"])
            if across.length < 1e-3:
                continue
            u = across.normalized()
            if a["wall"].dot(u) <= -ALIGNED and b["wall"].dot(u) >= ALIGNED:   # both bulge outward
                pairs.append((across.length, i, j))
    slots, used = [], set()
    for _, i, j in sorted(pairs):
        if i in used or j in used:
            continue
        used.update((i, j))
        a, b = halves[i], halves[j]
        z = [p.dot(a["dir"]) for p in a["ends"] + b["ends"]]
        mid = (min(z) + max(z)) / 2.0
        p, q = _at(a, mid, a["dir"]), _at(b, mid, a["dir"])
        slots.append({"kind": "slot", "point": (p + q) * 0.5, "ends": (p, q), "dir": a["dir"],
                      "dia": a["dia"], "bores": [a["dia"]], "face": a["face"]})
    return slots


def _at(axis, z, along):
    """The point on an axis whose coordinate along the direction `along` is z."""
    p, d = axis["point"], axis["dir"]
    return p + d * ((z - p.dot(along)) / d.dot(along))


def _axis_offset(h, g) -> float:
    """Distance between two parallel axes."""
    v = g["point"] - h["point"]
    return (v - h["dir"] * v.dot(h["dir"])).length


def _parallel(h, g, degrees: float = 1.0) -> bool:
    return abs(h["dir"].dot(g["dir"])) >= math.cos(math.radians(degrees))


def _same_axis(h, g) -> bool:
    return _parallel(h, g, 0.01) and _axis_offset(h, g) < 1e-3


def _gap(h, g) -> float:
    """How far apart two parallel holes or slots are, measured across their axes.

    Two holes: axis to axis. A hole and a slot: the axis to the slot's centre line, the segment
    between its two axes, so zero anywhere along it. Two slots: how close their lines come.
    """
    n = h["dir"]
    flat = [p - n * p.dot(n) for p in (*h["ends"], *g["ends"])]
    return _segment_gap(*flat)


def _segment_gap(p1, q1, p2, q2) -> float:
    """Shortest distance between the segments p1-q1 and p2-q2; a point is a segment of no length."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1.dot(d1), d2.dot(d2), d2.dot(r)
    clamp = lambda t: min(1.0, max(0.0, t))            # noqa: E731
    if a < 1e-12 and e < 1e-12:
        return r.length
    if a < 1e-12:
        s, t = 0.0, clamp(f / e)
    else:
        c = d1.dot(r)
        if e < 1e-12:
            s, t = clamp(-c / a), 0.0
        else:
            b = d1.dot(d2)
            denom = a * e - b * b                      # zero for parallel segments: any s will do
            s = clamp((b * f - c * e) / denom) if denom > 1e-12 * a * e else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                s, t = clamp(-c / a), 0.0
            elif t > 1.0:
                s, t = clamp((b - c) / a), 1.0
    return ((p1 + d1 * s) - (p2 + d2 * t)).length


def _axis_span(point, direction, box, margin: float = 1.0):
    """Where the line through a point along a direction crosses the box, grown by `margin`.

    Returns (t0, t1), distances along the direction, or None when the line misses it (slab test).
    """
    lo, hi = box
    t0, t1 = -math.inf, math.inf
    p = (point.X, point.Y, point.Z)
    d = (direction.X, direction.Y, direction.Z)
    for i in range(3):
        a, b = lo[i] - margin, hi[i] + margin
        if abs(d[i]) < 1e-12:
            if not a <= p[i] <= b:
                return None
            continue
        s0, s1 = (a - p[i]) / d[i], (b - p[i]) / d[i]
        t0, t1 = max(t0, min(s0, s1)), min(t1, max(s0, s1))
    return (t0, t1) if t0 <= t1 else None


def _on_hole(point, direction, in_body) -> bool:
    """Is the line through a point along a direction inside one of the body's holes or slots?"""
    probe = {"dir": direction, "ends": (point, point)}
    return any(_parallel(probe, g) and _gap(probe, g) <= g["dia"] / 2.0 + TOL_MM for g in in_body)


def _on_material(point, direction, body, box) -> bool:
    """Does the line through a point along a direction hit the body's solid, not just its box?"""
    from build123d import Edge
    from ..geom import min_distance
    span = _axis_span(point, direction, box)
    if span is None:
        return False
    line = Edge.make_line(point + direction * span[0], point + direction * span[1])
    return min_distance(line, body) <= TOL_MM


def _points_into(h, body, box, in_body, near=None) -> bool:
    """Does the hole's axis land on the body: on its material, or in one of its holes?

    A mounting hole has something under it: material that wants a hole, or a hole to line up
    with. A cutout over a window has nothing, so it points into nothing and needs no mate. A
    slot is looked at in the middle and at both ends: it points into the body if any of them
    does. With `near`, the hole also has to be that close to the body.
    """
    from build123d import Vertex
    spots = [h["point"]] if h["kind"] == "hole" else [h["point"], *h["ends"]]
    return any((_on_hole(p, h["dir"], in_body) or _on_material(p, h["dir"], body, box))
               and (near is None or Vertex(p).distance_to(body) <= near)
               for p in spots)


def _describe(h) -> str:
    if h["kind"] == "slot":
        length = (h["ends"][1] - h["ends"][0]).length
        return f"slot {h['dia']:.2f} wide, axes {length:.1f} apart"
    steps = f" (stepped, widest {h['bores'][-1]:.2f})" if len(h["bores"]) > 1 else ""
    return f"hole dia {h['dia']:.2f}{steps}"


def _xyz(p) -> str:
    """A point as text; adding 0.0 turns the -0.0 that rounding noise leaves into 0.0."""
    return "(" + ", ".join(f"{round(v, 1) + 0.0:.1f}" for v in (p.X, p.Y, p.Z)) + ")"


SIZE_TOL = 0.15         # mm: how far a tap drill or heat-set bore may be off its size


def _sizes(fastener: str) -> dict:
    """What a hole may measure for a fastener: a clearance range, a tap drill, a heat-set bore.

    Clearance is any of ISO 273's fine, medium and coarse sizes and between them, so a close 3.2 mm
    M3 hole is as good as the 3.4 mm medium one. A tap drill and a bore are tight and stay a size.
    """
    from ..parts import HEATSET_BORE, ISO_273, TAP_DRILL
    if fastener not in ISO_273:
        raise _Unusable(f"unknown fastener {fastener!r} (known: {', '.join(ISO_273)})")
    fine, _, coarse = ISO_273[fastener]
    return {"clearance": (fine, coarse), "tap": TAP_DRILL.get(fastener),
            "insert": HEATSET_BORE.get(fastener)}


def _kind_of(dia: float, sizes: dict) -> str | None:
    for kind, size in sizes.items():
        if size is None:
            continue
        lo, hi = size if isinstance(size, tuple) else (size - SIZE_TOL, size + SIZE_TOL)
        if lo - TOL_MM <= dia <= hi + TOL_MM:          # float noise, so 3.6 is 3.6
            return kind
    return None


def _sizes_text(fastener: str, sizes: dict) -> str:
    """The sizes that suit a fastener, for the limit of a row."""
    low, high = sizes["clearance"]
    text = [f"clearance {low:g} to {high:g}"]
    for kind in ("tap", "insert"):
        if sizes[kind] is not None:
            text.append(f"{kind} {sizes[kind]:g} +-{SIZE_TOL:g}")
    return f"{fastener}: {', '.join(text)} mm"


@spec_kind("interface", order=60)
def interface(entry: dict, ctx):
    """Whether the holes of `a` that point into `b` line up with a hole in `b` (sized for a fastener, if given)."""
    parts = ctx.parts
    from ..geom import bbox
    a, b = _need(entry, "a", "[[interface]]"), _need(entry, "b", "[[interface]]")
    tol = float(entry.get("tol_mm", 0.1))
    near = float(entry["near_mm"]) if "near_mm" in entry else None
    sa, sb = _body(parts, a), _body(parts, b)
    sizes = _sizes(entry["fastener"]) if "fastener" in entry else None
    box_b, in_b = bbox(sb), holes(sb)
    facing = [h for h in holes(sa) if _points_into(h, sb, box_b, in_b, near)]
    if not facing:
        raise _Unusable(f"no hole in {a} points into {b}: none has its axis on {b}'s material "
                        f"or in a hole of {b}" + (f", within {near:g} mm" if near is not None else ""))
    for h in facing:
        where = f"{a} {_describe(h)} at {_xyz(h['point'])}"
        mates = sorted((g for g in in_b if _parallel(h, g)), key=lambda g: _gap(h, g))
        if not mates or _gap(h, mates[0]) > tol + 2.0 * max(h["dia"], mates[0]["dia"]):
            yield _row(f"{a}|{b}", "interface", "FAIL", f"{where}: no hole in {b} under it",
                       f"a coaxial hole within {tol:g} mm")
            continue
        g, off = mates[0], _gap(h, mates[0])
        state, note = ("PASS" if off <= tol + TOL_MM else "FAIL"), ""
        if sizes and state == "PASS":
            ka, kb = _kind_of(h["dia"], sizes), _kind_of(g["dia"], sizes)
            if not ka or not kb or "clearance" not in (ka, kb):
                state = "FAIL"
                note = f"; sizes {h['dia']:.2f}/{g['dia']:.2f} do not suit {entry['fastener']}"
            else:
                note = f"; {ka} over {kb}"
        mate = f"dia {g['dia']:.2f}" if g["kind"] == "hole" else f"slot {g['dia']:.2f} wide"
        yield _row(f"{a}|{b}", "interface", state, f"{where}: offset {off:.3f} mm to {b} {mate}{note}",
                   f"coaxial within {tol:g} mm"
                   + (f", sized for {_sizes_text(entry['fastener'], sizes)}" if sizes else ""))
