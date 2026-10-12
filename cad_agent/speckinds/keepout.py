"""[[keepout]]: a tool's volume (a drill, a laser cone, ...) the listed bodies must stay out of.

The format is in cad_agent/spec.py. `pose = "park"` judges it with the machine at that pose of POSES instead of
at home (kit.posed); the tool stays where `at` puts it, so it is the bodies that move.
"""
from __future__ import annotations

from ..registry import spec_kind
from .kit import (Unusable as _Unusable, get_body as _body, posed as _posed, require as _need, row as _row,
                  vec3 as _vec3)

TOOLS = ("drill", "end_mill", "collet_nose", "laser_cone", "needle")


@spec_kind("keepout", order=50)
def keepout(entry: dict, ctx):
    """Whether the listed bodies stay out of a tool's envelope."""
    from .. import tooling
    from ..geom import intersection_volume, min_distance
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
    parts, at_pose = _posed(ctx, entry, "[[keepout]]")
    names = sorted(parts) if clear == "all" else list(clear)
    if not names:
        raise _Unusable("`clear` names no body")
    for name in names:
        body = _body(parts, name)
        overlap = intersection_volume(envelope, body)
        if overlap > 1e-6:
            yield _row(f"{kind}|{name}", "keepout", "FAIL",
                       f"{name} is inside the {kind} envelope, overlap {overlap:.3f} mm^3{at_pose}",
                       "outside the envelope")
        else:
            yield _row(f"{kind}|{name}", "keepout", "PASS",
                       f"clear by {min_distance(envelope, body):.3f} mm{at_pose}", "outside the envelope")
