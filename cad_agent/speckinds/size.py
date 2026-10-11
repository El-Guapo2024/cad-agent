"""[[size]]: one placed body's own bounding box, against `min_mm` and/or `max_mm`.

The format is in cad_agent/spec.py.
"""
from __future__ import annotations

from ..registry import spec_kind
from .kit import (Unusable as _Unusable, bounds as _bounds, get_body as _body, require as _need,
                  row as _row, vec3 as _vec3)


@spec_kind("size", order=20)
def size(entry: dict, ctx):
    """One body's size against min_mm and/or max_mm."""
    parts = ctx.parts
    from ..geom import bbox
    name = _need(entry, "body", "[[size]]")
    top = _vec3(entry["max_mm"], "max_mm") if "max_mm" in entry else None
    low = _vec3(entry["min_mm"], "min_mm") if "min_mm" in entry else None
    if top is None and low is None:
        raise _Unusable("[[size]] needs `min_mm` and/or `max_mm`")
    lo, hi = bbox(_body(parts, name))
    dims = [round(hi[i] - lo[i], 2) for i in range(3)]
    state, why, limit = _bounds(dims, top, low)
    yield _row(name, "size", state, f"{dims[0]} x {dims[1]} x {dims[2]} mm{why}", limit)
