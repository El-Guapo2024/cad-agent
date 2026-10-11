"""[[clearance]]: a gap two placed bodies must keep (`min_mm`) or may not exceed (`max_mm`).

The format is in cad_agent/spec.py.
"""
from __future__ import annotations

from ..registry import TOL_MM, spec_kind
from .kit import Unusable as _Unusable
from .kit import get_body as _body, require as _need, row as _row


@spec_kind("clearance", order=40)
def clearance(entry: dict, ctx):
    """The gap between two bodies against min_mm and/or max_mm; any overlap fails."""
    parts = ctx.parts
    from ..geom import intersection_volume, min_distance
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
    close, far = need is not None and gap < need - TOL_MM, cap is not None and gap > cap + TOL_MM
    yield _row(f"{a}|{b}", "clearance", "FAIL" if close or far else "PASS",
               f"{gap:.3f} mm" + (", too close" if close else ", too far" if far else ""), limit)
