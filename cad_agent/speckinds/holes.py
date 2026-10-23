"""[[holes]]: how many holes one placed body has, of a size and along an axis, through or blind.

"Four M3 clearance holes through the base" was in eval briefs and nothing counted them: `[[interface]]` judges
the holes of `a` that land on `b`, so a hole left out of the body that is not `a` was missed, and so was a spare.

    [[holes]]
    body = "bracket"
    count = 2                   # exactly this many; or min_count and/or max_count
    min_dia_mm = 5.2            # optional: only holes whose size is in this range
    max_dia_mm = 6.0
    axis = "y"                  # optional: only holes along this axis, "x", "y", "z" or [x, y, z], either sense
    kind = "hole"               # the default; "slot" counts slots, "any" both
    through = true              # optional: and every one of them open at both ends; false, every one blind
    depth_mm = 8                # optional: and every one blind, this deep (so through = false)
    depth_tol_mm = 0.1          # optional: how far the depth may be off; default 0.1

A hole is what `[[interface]]` reads (speckinds/interface.py `holes()`), from the body's B-rep: the concave
cylinders of one radius on one axis that turn 270 degrees or more. Its size is its narrowest bore, so a
counterbored hole is one hole of its through size, and a teardrop, a D-bore or a slit bore is a hole of its
circle. Bores on one axis with air between them are a hole each (the two cheeks of a fork: `[[interface]]`
reads them as one), each sized by its own narrowest bore. A slot's size is its width. Fillets and a notch open to an edge are not holes, nor is a boss.
`axis` holds a hole's axis to within 1 degree of that direction.

A hole goes through when it opens to air at both ends of its bores: a ring of points just past each end,
0.05 mm out along the axis and 0.02 mm outside the bore's wall, has one outside the solid. A flat bottom or
a drill point closes an end (the point's cone narrows inside the ring); a countersink, a chamfer, a sloped
face, a cross hole or a pocket the hole breaks into opens it. A blind hole opens at one end. Its depth is
along its axis, from where it opens to its bottom, which is where its round wall ends: a drill point's cone
is not counted. That is FreeCAD PartDesign Hole's Depth with DrillPoint Angled and "Take into account for
depth" off, the default (FeatureHole.cpp runs the wall to Depth and puts the tip past it), so a hole made
with that option on reads shallower by its cone. A countersink or a chamfer at the mouth is counted, so the
depth is from the face the hole opens on, and a counterbore is part of the hole, so a blind counterbored
hole is as deep as its narrow bore's bottom. On a sloped face the depth starts where the bore's wall goes
furthest, about the rim's high side (OCCT's bounds of the face, which can be a tenth of a mm long).

PASS when the number of holes that match is the count asked for and each ends as asked, FAIL otherwise,
with the holes found. `through` and `depth_mm` are not a filter: they hold every hole of the size and axis,
as a FreeCAD PartDesign Hole's Depth Type ("Through all" or a depth) holds every hole of the feature. So
"4 through" fails on four holes with one blind, and on four through holes and a fifth blind one (five,
and one blind); the row names the holes that do not end as asked. Holes of one size that must end two
ways are two entries told apart by size or axis, as FreeCAD's are two Hole features.
UNCHECKED when the entry cannot be read: no `body`, a body that is not there, no count, a count that is
not a whole number, a range that is upside down, an axis that is not a direction, a kind it does not know,
a `through` that is not true or false, `depth_mm` with `through = true`, a depth that is not above 0, a
negative `depth_tol_mm` or one without `depth_mm`, and `through` or `depth_mm` with a kind other than
"hole" (a slot's ends are not read).

What it does not judge: which face a hole opens on, and how long a through hole is; `axis`, the size and
`through` are the filter. Where the holes are is `[[interface]]`'s question.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, spec_kind
from .kit import (Unusable as _Unusable, get_body as _body, require as _need, row as _row)

KEYS = ("body", "count", "min_count", "max_count", "min_dia_mm", "max_dia_mm", "axis", "kind",
        "through", "depth_mm", "depth_tol_mm")
KINDS = ("hole", "slot", "any")
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
AXIS_DEG = 1.0          # how far a hole's axis may lean off `axis`
PAST_MM = 0.05          # how far past a bore's end the ring that reads it open or closed sits,
OUT_MM = 0.02           # how far outside the bore's wall,
RING = 12               # and how many points it has


@spec_kind("holes", order=82)
def holes_count(entry: dict, ctx):
    """How many holes a body has, of a size, along an axis and through or blind, against a count."""
    from build123d import Vector
    from .interface import _describe, _xyz, holes
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        raise _Unusable(f"[[holes]] does not take {', '.join(unknown)} (keys: {', '.join(KEYS)})")
    name = _need(entry, "body", "[[holes]]")
    low, high = _counts(entry)
    small = float(entry["min_dia_mm"]) if "min_dia_mm" in entry else None
    big = float(entry["max_dia_mm"]) if "max_dia_mm" in entry else None
    if small is not None and big is not None and small > big:
        raise _Unusable(f"[[holes]] min_dia_mm {small:g} is above max_dia_mm {big:g}")
    kind = entry.get("kind", "hole")
    if kind not in KINDS:
        raise _Unusable(f"[[holes]] `kind` must be one of {', '.join(KINDS)}, got {kind!r}")
    along = _axis(entry["axis"]) if "axis" in entry else None
    through, deep, slack = _ends_wanted(entry, kind)
    solid = _body(ctx.parts, name)

    def wanted(h) -> bool:
        if kind != "any" and h["kind"] != kind:
            return False
        if small is not None and h["dia"] < small - TOL_MM:
            return False
        if big is not None and h["dia"] > big + TOL_MM:
            return False
        return along is None or abs(h["dir"].dot(Vector(*along))) >= math.cos(math.radians(AXIS_DEG))

    found = [h for h in _each_bore(holes(solid)) if wanted(h)]
    wrong = []                                  # of the size and axis, but not open or deep as asked
    if through is not None:
        walls = _walls(solid)
        found = [h | _ends(solid, h, walls) for h in found]
        wrong = [h for h in found if not _ends_as_asked(h, through, deep, slack)]
    n = len(found)
    ok = (low is None or n >= low) and (high is None or n <= high) and not wrong
    what = {"hole": "holes", "slot": "slots", "any": "holes or slots"}[kind]
    size = (f" dia {small:g} to {big:g}" if small is not None and big is not None
            else f" dia >= {small:g}" if small is not None else f" dia <= {big:g}" if big is not None else "")
    way = "" if along is None else f" along {entry['axis']}"
    want = (f"exactly {low}" if low == high else f"{low} to {high}" if low is not None and high is not None
            else f"at least {low}" if low is not None else f"at most {high}")
    ends = ("" if through is None else ", through" if through
            else f", blind {deep:g} +-{slack:g} deep" if deep is not None else ", blind")

    def listed(some: list[dict]) -> str:
        text = "; ".join(f"{_describe(h)}{_ending(h)} at {_xyz(h['point'])}" for h in some[:6])
        return text + (f" and {len(some) - 6} more" if len(some) > 6 else "")
    shown = listed(found)
    if wrong:
        shown += f"; {len(wrong)} not {ends[2:]}: {listed(wrong)}"
    yield _row(name, "holes", "PASS" if ok else "FAIL", f"{n} {what}{size}{way}{ends}"
               + (f": {shown}" if shown else ""), f"{want} {what}{size}{way}{ends}")


def _ends_wanted(entry: dict, kind: str) -> tuple[bool | None, float | None, float]:
    """(True for through, False for blind, None for either; the depth asked for or None; how far it may be off)."""
    through = entry.get("through")
    if through is not None and not isinstance(through, bool):
        raise _Unusable(f"[[holes]] `through` must be true or false, got {through!r}")
    if "depth_tol_mm" in entry and "depth_mm" not in entry:
        raise _Unusable("[[holes]] `depth_tol_mm` needs `depth_mm`")
    deep = float(entry["depth_mm"]) if "depth_mm" in entry else None
    slack = float(entry.get("depth_tol_mm", 0.1))
    if deep is not None:
        if through:
            raise _Unusable("[[holes]] `depth_mm` is a blind hole's depth: it does not go with `through = true`")
        if deep <= 0:
            raise _Unusable(f"[[holes]] `depth_mm` must be above 0, got {deep:g}")
        if slack < 0:
            raise _Unusable("[[holes]] `depth_tol_mm` must not be negative")
        through = False
    if through is not None and kind != "hole":
        raise _Unusable(f"[[holes]] `through` and `depth_mm` judge holes, not kind = {kind!r}")
    return through, deep, slack


def _ends_as_asked(h: dict, through: bool, deep: float | None, slack: float) -> bool:
    if h["through"] != through:
        return False
    return deep is None or (h["depth"] is not None and abs(h["depth"] - deep) <= slack + TOL_MM)


def _ending(h: dict) -> str:
    """How a hole ends, for a row; nothing when the entry did not ask."""
    if "through" not in h:
        return ""
    if h["through"]:
        return ", through"
    return f", blind {h['depth']:.2f} deep" if h["depth"] is not None else ", closed at both ends"


def _walls(solid) -> list[dict]:
    """The concave cylinders and the cones of a solid, each with its axis and points to place it along that."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cone
    from .interface import _concave_cylinders, _vector
    found = [{"point": c["point"], "dir": c["dir"], "dia": c["dia"], "at": list(c["ends"])}
             for c in _concave_cylinders(solid)]       # where a bore runs, as interface._runs reads it
    for f in solid.faces():
        surf = BRepAdaptor_Surface(f.wrapped)
        if surf.GetType() == GeomAbs_Cone:              # a countersink, a chamfer, a drill point
            frame = surf.Cone().Position()
            found.append({"point": _vector(frame.Location()), "dir": _vector(frame.Direction()).normalized(),
                          "dia": None, "at": [v.center() for v in f.vertices()]
                          + [e.position_at(0.5) for e in f.edges()]})
    return found


def _ends(solid, h: dict, walls: list[dict]) -> dict:
    """{"through": does the hole open at both ends, "depth": a blind hole's depth}, as the module docstring says."""
    from build123d import Vector
    from .interface import _same_axis
    d, base = h["dir"], h["point"]
    lo, hi, _ = h["runs"][0]
    mine = [w | {"z": (min(z), max(z))} for w in walls if _same_axis(h, w)
            for z in [[p.dot(d) for p in w["at"]]]]
    bores = [w for w in mine if w["dia"] is not None and w["z"][0] >= lo - 1e-3 and w["z"][1] <= hi + 1e-3]
    u = d.cross(Vector(1, 0, 0) if abs(d.X) < 0.9 else Vector(0, 1, 0)).normalized()
    v = d.cross(u)

    def opens(z: float, out: int) -> bool:
        """Is there air in a ring just past the end at z, outside the bore that ends there?"""
        r = min(bores, key=lambda w: abs(w["z"][out > 0] - z))["dia"] / 2.0 + OUT_MM if bores \
            else h["dia"] / 2.0 + OUT_MM
        centre = base + d * (z + out * PAST_MM - base.dot(d))
        return any(not solid.is_inside(centre + (u * math.cos(t) + v * math.sin(t)) * r)
                   for t in (2.0 * math.pi * i / RING for i in range(RING)))

    def mouth(z: float, out: int) -> float:
        """Where the hole opens: past the end of its bores, on over the cones (a countersink, a chamfer) there."""
        moved = True
        while moved:
            moved = False
            for w in mine:
                near, far = w["z"] if out > 0 else w["z"][::-1]
                if abs(near - z) < 1e-3 and (far - z) * out > 1e-3:
                    z, moved = far, True
        return z

    low, high = opens(lo, -1), opens(hi, 1)
    if low == high:
        return {"through": low, "depth": None}
    return {"through": False, "depth": hi - mouth(lo, -1) if low else mouth(hi, 1) - lo}


def _each_bore(found: list[dict]) -> list[dict]:
    """The holes with a hole's runs (interface._runs) made a hole each, at its own middle and of its own size."""
    out = []
    for h in found:
        runs = h.get("runs", ())
        if len(runs) < 2:
            out.append(h)
            continue
        d, base = h["dir"], h["point"]
        for lo, hi, dia in runs:
            point = base + d * ((lo + hi) / 2.0 - base.dot(d))
            out.append(h | {"point": point, "ends": (point, point), "dia": dia,
                            "bores": [b for b in h["bores"] if b >= dia - 1e-3], "runs": [(lo, hi, dia)]})
    return out


def _counts(entry: dict) -> tuple[int | None, int | None]:
    """(the fewest, the most) holes the entry allows, from `count` or `min_count` and `max_count`."""
    def whole(key):
        v = entry[key]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise _Unusable(f"[[holes]] `{key}` must be a whole number, got {v!r}")
        return v
    if "count" in entry:
        if "min_count" in entry or "max_count" in entry:
            raise _Unusable("[[holes]] takes `count` or `min_count`/`max_count`, not both")
        n = whole("count")
        return n, n
    low = whole("min_count") if "min_count" in entry else None
    high = whole("max_count") if "max_count" in entry else None
    if low is None and high is None:
        raise _Unusable("[[holes]] needs `count`, or `min_count` and/or `max_count`")
    if low is not None and high is not None and low > high:
        raise _Unusable(f"[[holes]] min_count {low} is above max_count {high}")
    return low, high


def _axis(value) -> tuple[float, float, float]:
    """A direction from "x", "y", "z" (a sign in front is allowed and changes nothing) or [x, y, z]."""
    if isinstance(value, str) and value.lstrip("+-") in AXES:
        return AXES[value.lstrip("+-")]
    if isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value):
        length = math.sqrt(sum(float(v) ** 2 for v in value))
        if length > 1e-9:
            return tuple(float(v) / length for v in value)
    raise _Unusable(f"[[holes]] `axis` must be x, y, z or [x, y, z], got {value!r}")
