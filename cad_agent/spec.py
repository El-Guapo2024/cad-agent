"""spec.toml: the brief as acceptance tests.

A spec says what a design must do, in terms the kernel can measure, and the
verifier checks every entry. Nothing in it is advice. An entry that cannot be
checked (a body that does not exist, a missing field, an unknown section) is
UNCHECKED, which fails the gate exactly as a FAIL does. A project with no
spec.toml is UNCHECKED too: nothing states what the design must do.

    [envelope]                  # the whole assembly's bounding box
    max_mm = [560, 520, 300]    # x, y, z; min_mm is optional

    [[clearance]]               # a gap two placed bodies must keep
    a = "x_carriage"
    b = "gantry_end_left"
    min_mm = 3.0

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

Bodies are the names assembly.py places; parts in [[mass]] are part modules.
"""
from __future__ import annotations

import math
import tomllib

from . import state as st
from .registry import Row

KINDS = ("envelope", "clearance", "keepout", "mass", "interface")
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
    for kind, fn in (("clearance", _clearance), ("keepout", _keepout),
                     ("interface", _interface)):
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
    over = [a for a, d, m in zip("xyz", dims, top) if d > m + 1e-6]
    under = [a for a, d, m in zip("xyz", dims, low) if d < m - 1e-6] if low else []
    state = "FAIL" if over or under else "PASS"
    why = (f", too big in {''.join(over)}" if over else "") + \
          (f", too small in {''.join(under)}" if under else "")
    limit = f"<= {top[0]:g} x {top[1]:g} x {top[2]:g} mm" + \
            (f", >= {low[0]:g} x {low[1]:g} x {low[2]:g}" if low else "")
    yield _row("assembly", "envelope", state,
               f"{dims[0]} x {dims[1]} x {dims[2]} mm{why}", limit)


def _clearance(entry: dict, parts: dict):
    from .geom import intersection_volume, min_distance
    a, b = _need(entry, "a", "[[clearance]]"), _need(entry, "b", "[[clearance]]")
    need = float(_need(entry, "min_mm", "[[clearance]]"))
    sa, sb = _body(parts, a), _body(parts, b)
    overlap = intersection_volume(sa, sb)
    if overlap > 1e-6:
        yield _row(f"{a}|{b}", "clearance", "FAIL",
                   f"they interfere, overlap {overlap:.3f} mm^3", f">= {need:g} mm")
        return
    gap = min_distance(sa, sb)
    yield _row(f"{a}|{b}", "clearance", "PASS" if gap >= need - 1e-6 else "FAIL",
               f"{gap:.3f} mm", f">= {need:g} mm")


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

def holes(solid) -> list[dict]:
    """Cylindrical holes: faces whose outward normal points toward their own axis.

    A boss has the same kind of face with the normal pointing away. OCCT often
    splits one cylinder into two faces at a seam, so holes sharing an axis and a
    radius are merged.
    """
    from build123d import Vector
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
        r, ax = cyl.Radius(), cyl.Axis()
        o = Vector(ax.Location().X(), ax.Location().Y(), ax.Location().Z())
        d = Vector(ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()).normalized()
        p = f.position_at(0.5, 0.5)                    # a point on the face itself
        foot = o + d * ((p - o).dot(d))
        if (foot - p).dot(f.normal_at(p)) <= 0:
            continue                                   # a boss, not a hole
        h = {"point": foot, "dir": d, "dia": 2 * r, "face": f}
        if not any(_same_axis(h, g) and abs(h["dia"] - g["dia"]) < 1e-3 for g in found):
            found.append(h)
    return found


def _axis_offset(h, g) -> float:
    """Distance between two parallel axes."""
    v = g["point"] - h["point"]
    return (v - h["dir"] * v.dot(h["dir"])).length


def _parallel(h, g, degrees: float = 1.0) -> bool:
    return abs(h["dir"].dot(g["dir"])) >= math.cos(math.radians(degrees))


def _same_axis(h, g) -> bool:
    return _parallel(h, g, 0.01) and _axis_offset(h, g) < 1e-3


def _axis_hits_box(h, box, margin: float = 0.5) -> bool:
    """Does the hole's axis line pass through the box (slab test)?"""
    lo, hi = box
    t0, t1 = -math.inf, math.inf
    p = (h["point"].X, h["point"].Y, h["point"].Z)
    d = (h["dir"].X, h["dir"].Y, h["dir"].Z)
    for i in range(3):
        a, b = lo[i] - margin, hi[i] + margin
        if abs(d[i]) < 1e-12:
            if not a <= p[i] <= b:
                return False
            continue
        s0, s1 = (a - p[i]) / d[i], (b - p[i]) / d[i]
        t0, t1 = max(t0, min(s0, s1)), min(t1, max(s0, s1))
    return t0 <= t1


def _sizes(fastener: str) -> dict:
    from .parts import CLEARANCE_HOLE, HEATSET_BORE, TAP_DRILL
    if fastener not in CLEARANCE_HOLE:
        raise _Unusable(f"unknown fastener {fastener!r} (known: {', '.join(CLEARANCE_HOLE)})")
    return {"clearance": CLEARANCE_HOLE[fastener], "tap": TAP_DRILL.get(fastener),
            "insert": HEATSET_BORE.get(fastener)}


def _kind_of(dia: float, sizes: dict, tol: float = 0.15) -> str | None:
    for kind, size in sizes.items():
        if size is not None and abs(dia - float(size)) <= tol:
            return kind
    return None


def _interface(entry: dict, parts: dict):
    from build123d import Vertex
    from .geom import bbox
    a, b = _need(entry, "a", "[[interface]]"), _need(entry, "b", "[[interface]]")
    tol = float(entry.get("tol_mm", 0.1))
    near = float(entry.get("near_mm", 15.0))
    sa, sb = _body(parts, a), _body(parts, b)
    sizes = _sizes(entry["fastener"]) if "fastener" in entry else None
    box_b = bbox(sb)
    facing = [h for h in holes(sa)
              if _axis_hits_box(h, box_b) and Vertex(h["point"]).distance_to(sb) <= near]
    if not facing:
        raise _Unusable(f"no hole in {a} points into {b} within {near:g} mm")
    in_b = holes(sb)
    for h in facing:
        where = f"{a} hole dia {h['dia']:.2f} at ({h['point'].X:.1f}, {h['point'].Y:.1f}, {h['point'].Z:.1f})"
        mates = sorted((g for g in in_b if _parallel(h, g)), key=lambda g: _axis_offset(h, g))
        if not mates or _axis_offset(h, mates[0]) > tol + 2.0 * max(h["dia"], mates[0]["dia"]):
            yield _row(f"{a}|{b}", "interface", "FAIL", f"{where}: no hole in {b} under it",
                       f"a coaxial hole within {tol:g} mm")
            continue
        g, off = mates[0], _axis_offset(h, mates[0])
        state, note = ("PASS" if off <= tol else "FAIL"), ""
        if sizes and state == "PASS":
            ka, kb = _kind_of(h["dia"], sizes), _kind_of(g["dia"], sizes)
            if not ka or not kb or "clearance" not in (ka, kb):
                state = "FAIL"
                note = (f"; sizes {h['dia']:.2f}/{g['dia']:.2f} do not suit {entry['fastener']} "
                        f"(clearance {sizes['clearance']}, tap {sizes['tap']}, insert {sizes['insert']})")
            else:
                note = f"; {ka} over {kb}"
        yield _row(f"{a}|{b}", "interface", state,
                   f"{where}: offset {off:.3f} mm to {b} dia {g['dia']:.2f}{note}",
                   f"coaxial within {tol:g} mm" + (f", sized for {entry['fastener']}" if sizes else ""))
