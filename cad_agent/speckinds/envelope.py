"""[envelope]: the whole assembly's bounding box, against `max_mm` and optionally `min_mm`.

The format is in cad_agent/spec.py.
"""
from __future__ import annotations

from ..registry import spec_kind
from .kit import (Unusable as _Unusable, bounds as _bounds, require as _need, row as _row,
                  vec3 as _vec3)


@spec_kind("envelope", order=10, table=True)
def envelope(entry: dict, ctx):
    """The assembly's overall size against max_mm (and min_mm)."""
    parts = ctx.parts
    from ..geom import bbox
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
