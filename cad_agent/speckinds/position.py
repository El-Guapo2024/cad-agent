"""[[position]]: where a placed body's bounding-box centre must be, within `tol_mm`.

The format is in cad_agent/spec.py.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, spec_kind
from .kit import (Unusable as _Unusable, get_body as _body, require as _need, row as _row,
                  vec3 as _vec3)


@spec_kind("position", order=30)
def position(entry: dict, ctx):
    """Where one body's bounding-box centre is, against center_mm within tol_mm."""
    parts = ctx.parts
    from ..geom import bbox
    name = _need(entry, "body", "[[position]]")
    want = _vec3(_need(entry, "center_mm", "[[position]]"), "center_mm")
    tol = float(entry.get("tol_mm", 0.1))
    if tol < 0:
        raise _Unusable("tol_mm must not be negative")
    lo, hi = bbox(_body(parts, name))
    got = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    delta = [g - w for g, w in zip(got, want)]
    off = math.sqrt(sum(d * d for d in delta))
    ok = off <= tol + TOL_MM
    yield _row(name, "position", "PASS" if ok else "FAIL",
               f"center ({got[0]:.2f}, {got[1]:.2f}, {got[2]:.2f}) mm, offset {off:.3f} mm"
               + ("" if ok else f" (dx {delta[0]:+.2f}, dy {delta[1]:+.2f}, dz {delta[2]:+.2f})"),
               f"center ({want[0]:g}, {want[1]:g}, {want[2]:g}) mm within {tol:g} mm")
