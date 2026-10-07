"""spec.toml: the brief as acceptance tests.

A spec says what a design must do, in terms the kernel can measure, and the
verifier checks every entry. Nothing in it is advice. An entry that cannot be
checked (a body that does not exist, a missing field, an unknown section) is
UNCHECKED, which fails the gate exactly as a FAIL does. A project with no
spec.toml is UNCHECKED too: nothing states what the design must do.

    [envelope]                  # the whole assembly's bounding box
    max_mm = [560, 520, 300]    # x, y, z; min_mm is optional

    [[size]]                    # one placed body's own bounding box, x, y, z
    body = "motor"              # min_mm and/or max_mm, at least one. Held to its real
    min_mm = [42.2, 42.2, 64]   # size, a given part can't be swapped for a smaller one
    max_mm = [42.4, 42.4, 65]

    [[position]]                # where a placed body's bounding-box center must be
    body = "motor"
    center_mm = [0, 0, 20]      # x, y, z
    tol_mm = 0.1                # distance allowed; default 0.1

    [[clearance]]               # a gap two placed bodies must keep
    a = "x_carriage"
    b = "gantry_end_left"
    min_mm = 3.0                # min_mm and/or max_mm, at least one; overlap always fails
    max_mm = 20.0               # a small max_mm is how "must grip" or "must touch" is written

    [[keepout]]                 # a tool's volume the listed bodies must stay out of
    tool = "laser_cone"         # drill, end_mill, collet_nose, laser_cone, needle
    params = { focal_length = 210, field = 150, lens_dia = 30 }
    at = [0, 0, 0]              # where the tool point sits
    clear = ["gantry_beam"]     # or "all"

    [[mass]]                    # a weight budget over part modules
    parts = { x_carriage = 1, syringe_clamp = 1 }
    max_g = 400

    [[interface]]               # bolt holes in `a` that point into `b` must line up
    a = "top_plate"             # with a hole in `b`
    b = "base_plate"
    fastener = "M3"             # optional: hole sizes must suit it
    tol_mm = 0.1                # axis offset allowed; default 0.1
    near_mm = 15                # only holes of `a` this close to `b`; default 15

An interface judges holes, not every round face. A hole is the cylinders on one axis that go
all the way round, and its size is its smallest bore, so a counterbore is part of its hole. A
slot is judged by its centre line: the other body's hole axis has to lie on it, and its width
is the size. Fillets and other partial arcs are not holes.

With a fastener, one hole of each pair must be a clearance hole and the other a clearance, tap
or heat-set size. Clearance is anything from ISO 273's fine to its coarse series (M3: 3.2 to
3.6 mm); a tap drill or insert bore is its table size to within 0.15 mm (`cad tables`).

Bodies are the names assembly.py places; parts in [[mass]] are part modules.
"""
from __future__ import annotations

import math
import tomllib

from . import state as st
from .registry import Row

KINDS = ("envelope", "size", "position", "clearance", "keepout", "mass", "interface")
TOOLS = ("drill", "end_mill", "collet_nose", "laser_cone", "needle")


def _row(subject, rule, state, measured, limit="n/a", source="spec.toml"):
    return Row(subject=subject, rule=f"spec/{rule}", state=state,
               measured=measured, limit=limit, source=source)


def check_spec(slug: str, parts: dict):
    """Every entry of the project's spec.toml, as rows."""
    path = st.project_dir(slug) / "spec.toml"
    if not path.exists():
        yield _row(slug, "present", "UNCHECKED",
                   "no spec.toml: nothing states what this design must do",
                   "a spec.toml with at least one requirement",
                   "write the brief as acceptance tests (see cad_agent/spec.py)")
        return
    try:
        spec = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        yield _row(slug, "present", "UNCHECKED", f"spec.toml does not parse: {e}")
        return
    unknown = sorted(set(spec) - set(KINDS))
    for key in unknown:
        yield _row(slug, key, "UNCHECKED", f"unknown section [{key}]",
                   f"one of {', '.join(KINDS)}")
    if not set(spec) & set(KINDS):
        yield _row(slug, "present", "UNCHECKED", "spec.toml states no requirement",
                   f"at least one of {', '.join(KINDS)}")
        return

    if "envelope" in spec:
        yield from _guard("envelope", "[envelope]", lambda: _envelope(spec["envelope"], parts))
    for kind, fn in (("size", _size), ("position", _position), ("clearance", _clearance),
                     ("keepout", _keepout), ("interface", _interface)):
        for i, entry in enumerate(_entries(spec, kind), 1):
            yield from _guard(kind, f"[[{kind}]] #{i}", lambda e=entry, f=fn: f(e, parts),
                              source=f"spec.toml [[{kind}]] #{i}")
    for i, entry in enumerate(_entries(spec, "mass"), 1):
        yield from _guard("mass", f"[[mass]] #{i}", lambda e=entry: _mass(e, slug),
                          source=f"spec.toml [[mass]] #{i}")


def _entries(spec: dict, kind: str) -> list:
    value = spec.get(kind, [])
    return value if isinstance(value, list) else [value]


def _guard(kind, where, fn, source="spec.toml"):
    """One broken entry becomes an UNCHECKED row, never a crash that hides the rest."""
    try:
        rows = list(fn())
    except _Unusable as e:
        rows = [_row(where, kind, "UNCHECKED", str(e))]
    except Exception as e:  # noqa: BLE001 - a rule must not take the run down
        rows = [_row(where, kind, "UNCHECKED", f"{type(e).__name__}: {e}")]
    for r in rows:
        if r.source == "spec.toml":
            r.source = source
        yield r


class _Unusable(Exception):
    """An entry that names something missing, or lacks a field."""


def _need(entry: dict, key: str, where: str):
    if key not in entry:
        raise _Unusable(f"{where} is missing `{key}`")
    return entry[key]


def _body(parts: dict, name: str):
    if name not in parts:
        raise _Unusable(f"no body {name!r} in the assembly (bodies: {', '.join(sorted(parts))})")
    return parts[name]


def _vec3(value, what: str) -> list[float]:
    if not (isinstance(value, list) and len(value) == 3):
        raise _Unusable(f"{what} must be [x, y, z]")
    return [float(v) for v in value]


# ─── Requirements ────────────────────────────────────────────────────────────

def _bounds(dims, top, low):
    """The state, the reason and the limit text for a box held to x, y, z bounds."""
    over = [a for a, d, m in zip("xyz", dims, top) if d > m + 1e-6] if top else []
    under = [a for a, d, m in zip("xyz", dims, low) if d < m - 1e-6] if low else []
    why = (f", too big in {''.join(over)}" if over else "") + \
          (f", too small in {''.join(under)}" if under else "")
    limit = ", ".join(f"{sign} {b[0]:g} x {b[1]:g} x {b[2]:g} mm"
                      for sign, b in (("<=", top), (">=", low)) if b)
    return ("FAIL" if over or under else "PASS"), why, limit


def _envelope(entry: dict, parts: dict):
    from .geom import bbox
    if not parts:
        raise _Unusable("no assembly.py, so there is no assembly to measure")
    top = _vec3(_need(entry, "max_mm", "[envelope]"), "max_mm")
    low = _vec3(entry["min_mm"], "min_mm") if "min_mm" in entry else None
    boxes = [bbox(s) for s in parts.values()]
    lo = [min(b[0][i] for b in boxes) for i in range(3)]
    hi = [max(b[1][i] for b in boxes) for i in range(3)]
    dims = [round(hi[i] - lo[i], 2) for i in range(3)]
    state, why, limit = _bounds(dims, top, low)
    yield _row("assembly", "envelope", state,
               f"{dims[0]} x {dims[1]} x {dims[2]} mm{why}", limit)


def _size(entry: dict, parts: dict):
    from .geom import bbox
    name = _need(entry, "body", "[[size]]")
    top = _vec3(entry["max_mm"], "max_mm") if "max_mm" in entry else None
    low = _vec3(entry["min_mm"], "min_mm") if "min_mm" in entry else None
    if top is None and low is None:
        raise _Unusable("[[size]] needs `min_mm` and/or `max_mm`")
    lo, hi = bbox(_body(parts, name))
    dims = [round(hi[i] - lo[i], 2) for i in range(3)]
    state, why, limit = _bounds(dims, top, low)
    yield _row(name, "size", state, f"{dims[0]} x {dims[1]} x {dims[2]} mm{why}", limit)


def _position(entry: dict, parts: dict):
    from .geom import bbox
    name = _need(entry, "body", "[[position]]")
    want = _vec3(_need(entry, "center_mm", "[[position]]"), "center_mm")
    tol = float(entry.get("tol_mm", 0.1))
    if tol < 0:
        raise _Unusable("tol_mm must not be negative")
    lo, hi = bbox(_body(parts, name))
    got = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    delta = [g - w for g, w in zip(got, want)]
    off = math.sqrt(sum(d * d for d in delta))
    ok = off <= tol + 1e-9
    yield _row(name, "position", "PASS" if ok else "FAIL",
               f"center ({got[0]:.2f}, {got[1]:.2f}, {got[2]:.2f}) mm, offset {off:.3f} mm"
               + ("" if ok else f" (dx {delta[0]:+.2f}, dy {delta[1]:+.2f}, dz {delta[2]:+.2f})"),
               f"center ({want[0]:g}, {want[1]:g}, {want[2]:g}) mm within {tol:g} mm")


def _clearance(entry: dict, parts: dict):
    from .geom import intersection_volume, min_distance
    a, b = _need(entry, "a", "[[clearance]]"), _need(entry, "b", "[[clearance]]")
    if "min_mm" not in entry and "max_mm" not in entry:
        raise _Unusable("[[clearance]] needs `min_mm` and/or `max_mm`")
    need = float(entry["min_mm"]) if "min_mm" in entry else None
    cap = float(entry["max_mm"]) if "max_mm" in entry else None
    if need is not None and cap is not None and need > cap:
        raise _Unusable(f"[[clearance]] min_mm {need:g} is above max_mm {cap:g}")
    limit = ", ".join(f"{sign} {v:g} mm" for sign, v in ((">=", need), ("<=", cap))
                      if v is not None)
    sa, sb = _body(parts, a), _body(parts, b)
    overlap = intersection_volume(sa, sb)
    if overlap > 1e-6:
        yield _row(f"{a}|{b}", "clearance", "FAIL",
                   f"they interfere, overlap {overlap:.3f} mm^3", limit)
        return
    gap = min_distance(sa, sb)
    close, far = need is not None and gap < need - 1e-6, cap is not None and gap > cap + 1e-6
    yield _row(f"{a}|{b}", "clearance", "FAIL" if close or far else "PASS",
               f"{gap:.3f} mm" + (", too close" if close else ", too far" if far else ""), limit)


def _keepout(entry: dict, parts: dict):
    from . import tooling
    from .geom import intersection_volume, min_distance
    kind = _need(entry, "tool", "[[keepout]]")
    if kind not in TOOLS:
        raise _Unusable(f"unknown tool {kind!r} (tools: {', '.join(TOOLS)})")
    params = dict(entry.get("params", {}))
    try:
        envelope = getattr(tooling, kind)(**params)
    except TypeError as e:
        raise _Unusable(f"{kind} params: {e}") from None
    x, y, z = _vec3(entry.get("at", [0, 0, 0]), "at")
    envelope = tooling.at(envelope, x=x, y=y, z=z)
    clear = _need(entry, "clear", "[[keepout]]")
    names = sorted(parts) if clear == "all" else list(clear)
    if not names:
        raise _Unusable("`clear` names no body")
    for name in names:
        body = _body(parts, name)
        overlap = intersection_volume(envelope, body)
        if overlap > 1e-6:
            yield _row(f"{kind}|{name}", "keepout", "FAIL",
                       f"{name} is inside the {kind} envelope, overlap {overlap:.3f} mm^3",
                       "outside the envelope")
        else:
            yield _row(f"{kind}|{name}", "keepout", "PASS",
                       f"clear by {min_distance(envelope, body):.3f} mm", "outside the envelope")


def _mass(entry: dict, slug: str):
    from .geom import mass_g
    counts = _need(entry, "parts", "[[mass]]")
    limit = float(_need(entry, "max_g", "[[mass]]"))
    if not isinstance(counts, dict) or not counts:
        raise _Unusable("`parts` must map part names to counts, e.g. { x_carriage = 1 }")
    total, lines = 0.0, []
    for name, n in counts.items():
        if name not in st.part_names(slug):
            raise _Unusable(f"no part module {name!r} (parts: {', '.join(st.part_names(slug))})")
        solid, meta = st.build_part(slug, name)
        if not meta["material"]:
            raise _Unusable(f"{name} declares no MATERIAL, so its mass is unknown")
        g = mass_g(solid, meta["material"]) * float(n)
        total += g
        lines.append(f"{name} x{n} {g:.1f} g")
    yield _row(", ".join(counts), "mass", "PASS" if total <= limit + 1e-9 else "FAIL",
               f"{total:.1f} g ({'; '.join(lines)})", f"<= {limit:g} g")


# ─── Interfaces: holes that must line up ─────────────────────────────────────

FULL_TURN = 2.0 * math.pi
ARC_TOL = 1e-3          # radians: how far two arcs may miss meeting, or a half turn be off
ALIGNED = math.cos(math.radians(2.0))     # how well a slot's two ends must face each other


def holes(solid) -> list[dict]:
    """The holes and slots of a solid: the places a fastener can go.

    A hole is the concave cylinders on one axis that together go all the way round. A
    counterbore shares the axis of the hole it widens, so it is part of that hole: `dia`
    is the smallest bore, which is what a screw passes, and `bores` lists every diameter.
    OCCT often splits one cylinder in two at a seam, so the angles are added up per axis and
    radius, not taken from one face.

    A slot is two half-turn cylinders of one radius on parallel axes, each bulging away from
    the other. Its `ends` are those axes at mid-depth, `point` is halfway between them and
    `dia` is its width; a hole is the same thing with both ends on one axis.

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
            if len(cover) == 1 and cover[0][1] - cover[0][0] >= FULL_TURN - ARC_TOL:
                bores.append(same)
            elif len(cover) == 1 and abs(cover[0][1] - cover[0][0] - math.pi) <= ARC_TOL:
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


def _axis_hits_box(point, direction, box, margin: float = 0.5) -> bool:
    """Does the line through a point along a direction pass through the box (slab test)?"""
    lo, hi = box
    t0, t1 = -math.inf, math.inf
    p = (point.X, point.Y, point.Z)
    d = (direction.X, direction.Y, direction.Z)
    for i in range(3):
        a, b = lo[i] - margin, hi[i] + margin
        if abs(d[i]) < 1e-12:
            if not a <= p[i] <= b:
                return False
            continue
        s0, s1 = (a - p[i]) / d[i], (b - p[i]) / d[i]
        t0, t1 = max(t0, min(s0, s1)), min(t1, max(s0, s1))
    return t0 <= t1


def _points_into(h, box, body, near: float) -> bool:
    """Does the hole's axis meet the box with the hole within `near` of the body?

    A slot is looked at in the middle and at both ends: it points into the body if any of them does.
    """
    from build123d import Vertex
    spots = [h["point"]] if h["kind"] == "hole" else [h["point"], *h["ends"]]
    return any(_axis_hits_box(p, h["dir"], box) and Vertex(p).distance_to(body) <= near
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
    from .parts import HEATSET_BORE, ISO_273, TAP_DRILL
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
        if lo - 1e-6 <= dia <= hi + 1e-6:
            return kind
    return None


def _sizes_text(fastener: str, sizes: dict) -> str:
    """The sizes that suit a fastener, for the limit of a row."""
    low, high = sizes["clearance"]
    text = [f"clearance {low:g} to {high:g}"]
    text += [f"{kind} {sizes[kind]:g} +-{SIZE_TOL:g}" for kind in ("tap", "insert") if sizes[kind] is not None]
    return f"{fastener}: {', '.join(text)} mm"


def _interface(entry: dict, parts: dict):
    from .geom import bbox
    a, b = _need(entry, "a", "[[interface]]"), _need(entry, "b", "[[interface]]")
    tol = float(entry.get("tol_mm", 0.1))
    near = float(entry.get("near_mm", 15.0))
    sa, sb = _body(parts, a), _body(parts, b)
    sizes = _sizes(entry["fastener"]) if "fastener" in entry else None
    box_b = bbox(sb)
    facing = [h for h in holes(sa) if _points_into(h, box_b, sb, near)]
    if not facing:
        raise _Unusable(f"no hole in {a} points into {b} within {near:g} mm")
    in_b = holes(sb)
    for h in facing:
        where = f"{a} {_describe(h)} at {_xyz(h['point'])}"
        mates = sorted((g for g in in_b if _parallel(h, g)), key=lambda g: _gap(h, g))
        if not mates or _gap(h, mates[0]) > tol + 2.0 * max(h["dia"], mates[0]["dia"]):
            yield _row(f"{a}|{b}", "interface", "FAIL", f"{where}: no hole in {b} under it",
                       f"a coaxial hole within {tol:g} mm")
            continue
        g, off = mates[0], _gap(h, mates[0])
        state, note = ("PASS" if off <= tol else "FAIL"), ""
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
