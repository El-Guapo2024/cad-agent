"""[[axis]]: an axis the design must declare in AXES, and what it must do.

The sweep, reach and centre-of-mass rules judge the axes a design declares, so a design that declares none is
judged at home only and passes the rest by having nothing to judge. This is how a spec asks for one:

    [[axis]]
    name = "x"                                          # a key of AXES; a sub-assembly's axis is "gantry/x"
    moves = ["block", "carriage_plate", "tool"]         # optional: it moves at least these bodies
    only = true                                         # optional, default false: and no other body
    direction = [1, 0, 0]                               # optional: it runs along this line (either way)
    tol_deg = 1.0                                       # optional: how far off the line it may be; default 1
    travel_min_mm = 80                                  # optional: its travel, max minus min, is at least this
    travel_max_mm = 120                                 # optional: and at most this
    work_min_mm = 80                                    # optional: it declares a work span at least this long
    tool = "tool"                                       # optional: the body that carries its tool point

Only `name` is required: alone, it asks that the axis exists. Whether the work span lies inside the travel is
the `reach` rule's, and whether the travel is clear of everything is `sweep`'s; this asks that the declaration is
there and says what was asked for, so a design cannot skip it.

FAIL when the design does not do what was asked: no such axis (the row lists the ones declared, or says AXES is
empty), a body it should move that it does not, one more than `only` allows, a direction off the line, a travel
or a work span too short or too long, no work span at all, another tool body. PASS otherwise, with what the axis
does. UNCHECKED when the entry cannot be read: a key this section does not have, a body it names that the
assembly does not return, a direction of zero length, a bad number, or no assembly loaded to read AXES from.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, spec_kind
from .kit import Unusable as _Unusable, get_body as _body, require as _need, row as _row, vec3 as _vec3

KEYS = ("name", "moves", "only", "direction", "tol_deg", "travel_min_mm", "travel_max_mm", "work_min_mm", "tool")


@spec_kind("axis", order=85)
def axis(entry: dict, ctx):
    """Whether AXES declares the named axis, moving what was asked, along the direction asked, far enough."""
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        raise _Unusable(f"[[axis]] does not take {', '.join(unknown)} (keys: {', '.join(KEYS)})")
    name = _need(entry, "name", "[[axis]]")
    if not isinstance(name, str) or not name:
        raise _Unusable("[[axis]] `name` must be the name of an axis in AXES")
    moves = _bodies(entry, "moves")
    only = entry.get("only", False)
    if not isinstance(only, bool):
        raise _Unusable(f"[[axis]] `only` must be true or false, got {only!r}")
    if only and moves is None:
        raise _Unusable("[[axis]] `only` says no other body moves, and there is no `moves` to say which")
    tool = entry.get("tool")
    if tool is not None and not isinstance(tool, str):
        raise _Unusable("[[axis]] `tool` must name a body")
    line = _unit(_vec3(entry["direction"], "direction")) if "direction" in entry else None
    tol_deg = _number(entry, "tol_deg", 1.0, least=0.0)
    travel_min, travel_max = _number(entry, "travel_min_mm"), _number(entry, "travel_max_mm")
    work_min = _number(entry, "work_min_mm")
    if travel_min is not None and travel_max is not None and travel_min > travel_max:
        raise _Unusable(f"[[axis]] travel_min_mm {travel_min:g} is above travel_max_mm {travel_max:g}")
    if getattr(ctx, "machine", None) is None:
        raise _Unusable("[[axis]] reads AXES from assembly.py, and no assembly was loaded")
    for body in [*(moves or []), *([tool] if tool else [])]:
        _body(ctx.parts, body)

    asked = _asked(moves, only, line, tol_deg, travel_min, travel_max, work_min, tool)
    axes = ctx.machine.axes
    if name not in axes:
        have = ", ".join(sorted(axes)) if axes else "none: assembly.py declares no AXES"
        yield _row(f"axis {name}", "axis", "FAIL", f"no axis {name!r} in AXES (axes: {have})", asked)
        return
    ax = axes[name]
    short, facts = [], [f"moves {', '.join(ax.moves) or 'nothing'}"]
    if moves is not None:
        lacking = [b for b in moves if b not in ax.moves]
        if lacking:
            short.append(f"does not move {', '.join(lacking)}")
        extra = [b for b in ax.moves if b not in moves]
        if only and extra:
            short.append(f"also moves {', '.join(extra)}")
    if line is not None:
        try:
            u = ax.unit
        except ValueError:
            short.append("has a zero direction")
        else:
            angle = math.degrees(math.acos(min(1.0, abs(sum(a * b for a, b in zip(u, line))))))
            facts.append(f"along ({u[0]:.3f}, {u[1]:.3f}, {u[2]:.3f})")
            if angle > tol_deg + 1e-9:
                short.append(f"runs {angle:.1f} deg off the line asked for")
    span = ax.span
    facts.append(f"travel {ax.travel[0]:g} to {ax.travel[1]:g} mm ({span:g} mm)")
    if travel_min is not None and span < travel_min - TOL_MM:
        short.append(f"travels {span:g} mm, short of {travel_min:g}")
    if travel_max is not None and span > travel_max + TOL_MM:
        short.append(f"travels {span:g} mm, past {travel_max:g}")
    if work_min is not None:
        if ax.work is None:
            short.append("declares no work span")
        else:
            length = ax.work[1] - ax.work[0]
            facts.append(f"work {ax.work[0]:g} to {ax.work[1]:g} mm")
            if length < work_min - TOL_MM:
                short.append(f"promises {length:g} mm of work, short of {work_min:g}")
    if tool is not None and ax.tool != tool:
        short.append(f"carries its tool on {ax.tool!r}, not {tool!r}")
    yield _row(f"axis {name}", "axis", "FAIL" if short else "PASS",
               ("; ".join(short) + " (" + "; ".join(facts) + ")") if short else "; ".join(facts), asked)


def _bodies(entry: dict, key: str):
    value = entry.get(key)
    if value is None:
        return None
    if not (isinstance(value, list) and value and all(isinstance(b, str) and b for b in value)):
        raise _Unusable(f"[[axis]] `{key}` must be a list of body names")
    if len(set(value)) != len(value):
        raise _Unusable(f"[[axis]] `{key}` lists a body twice")
    return value


def _number(entry: dict, key: str, default: float | None = None, least: float | None = None):
    if key not in entry:
        return default
    v = entry[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise _Unusable(f"[[axis]] `{key}` must be a number, got {v!r}")
    if least is not None and v < least:
        raise _Unusable(f"[[axis]] `{key}` must be at least {least:g}, got {v:g}")
    return float(v)


def _unit(v: list) -> list:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0.0:
        raise _Unusable("[[axis]] `direction` has zero length")
    return [x / n for x in v]


def _asked(moves, only, line, tol_deg, travel_min, travel_max, work_min, tool) -> str:
    parts = ["declared in AXES"]
    if moves is not None:
        parts.append(("moves exactly " if only else "moves ") + ", ".join(moves))
    if line is not None:
        parts.append(f"along ({line[0]:.3f}, {line[1]:.3f}, {line[2]:.3f}) within {tol_deg:g} deg")
    if travel_min is not None:
        parts.append(f"travel >= {travel_min:g} mm")
    if travel_max is not None:
        parts.append(f"travel <= {travel_max:g} mm")
    if work_min is not None:
        parts.append(f"work span >= {work_min:g} mm")
    if tool is not None:
        parts.append(f"tool on {tool}")
    return "; ".join(parts)
