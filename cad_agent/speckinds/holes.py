"""[[holes]]: how many holes one placed body has, of a size and along an axis.

"Four M3 clearance holes through the base" was in eval briefs and nothing counted them: `[[interface]]` judges
the holes of `a` that land on `b`, so a hole left out of the body that is not `a` was missed, and so was a spare.

    [[holes]]
    body = "bracket"
    count = 2                   # exactly this many; or min_count and/or max_count
    min_dia_mm = 5.2            # optional: only holes whose size is in this range
    max_dia_mm = 6.0
    axis = "y"                  # optional: only holes along this axis, "x", "y", "z" or [x, y, z], either sense
    kind = "hole"               # the default; "slot" counts slots, "any" both

A hole is what `[[interface]]` reads (speckinds/interface.py `holes()`), from the body's B-rep: the concave
cylinders of one radius on one axis that turn 270 degrees or more. Its size is its narrowest bore, so a
counterbored hole is one hole of its through size, and a teardrop, a D-bore or a slit bore is a hole of its
circle. Bores on one axis with air between them are a hole each (the two cheeks of a fork: `[[interface]]`
reads them as one), each sized by its own narrowest bore. A slot's size is its width. Fillets and a notch open to an edge are not holes, nor is a boss.
`axis` holds a hole's axis to within 1 degree of that direction.

PASS when the number of holes that match is the count asked for, FAIL otherwise, with the holes found.
UNCHECKED when the entry cannot be read: no `body`, a body that is not there, no count, a count that is
not a whole number, a range that is upside down, an axis that is not a direction, a kind it does not know.

What it does not judge: whether a hole goes through (a blind hole of the size counts) and which face it
opens on; `axis` and the size are the filter. Where the holes are is `[[interface]]`'s question.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, spec_kind
from .kit import (Unusable as _Unusable, get_body as _body, require as _need, row as _row)

KEYS = ("body", "count", "min_count", "max_count", "min_dia_mm", "max_dia_mm", "axis", "kind")
KINDS = ("hole", "slot", "any")
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
AXIS_DEG = 1.0          # how far a hole's axis may lean off `axis`


@spec_kind("holes", order=82)
def holes_count(entry: dict, ctx):
    """How many holes a body has, of a size and along an axis, against a count."""
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
    n = len(found)
    ok = (low is None or n >= low) and (high is None or n <= high)
    what = {"hole": "holes", "slot": "slots", "any": "holes or slots"}[kind]
    size = (f" dia {small:g} to {big:g}" if small is not None and big is not None
            else f" dia >= {small:g}" if small is not None else f" dia <= {big:g}" if big is not None else "")
    way = "" if along is None else f" along {entry['axis']}"
    want = (f"exactly {low}" if low == high else f"{low} to {high}" if low is not None and high is not None
            else f"at least {low}" if low is not None else f"at most {high}")
    shown = "; ".join(f"{_describe(h)} at {_xyz(h['point'])}" for h in found[:6])
    shown += f" and {n - 6} more" if n > 6 else ""
    yield _row(name, "holes", "PASS" if ok else "FAIL",
               f"{n} {what}{size}{way}" + (f": {shown}" if shown else ""), f"{want} {what}{size}{way}")


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
