"""Fit gate: interference and clearance between every pair of solids.

A pair either overlaps (interference volume > tolerance) or is separated by
some minimum distance. A required clearance turns that distance into a gate.
"""
from __future__ import annotations
from itertools import combinations
from ..geom import min_distance, intersection_volume
from ..registry import TOL_MM

# OCCT boolean noise on coincident faces. Below this an "overlap" is contact.
VOLUME_NOISE_MM3 = 1e-6


def check_fit(parts: dict, required_clearance: dict | None = None,
              default_clearance: float = 0.0, allow_contact: set | None = None):
    """parts: {name: solid}. required_clearance: {(a,b): mm} or {"a|b": mm}.

    Returns a list of row dicts, one per pair, each with an explicit state.
    """
    req = {}
    for k, v in (required_clearance or {}).items():
        key = tuple(sorted(k.split("|"))) if isinstance(k, str) else tuple(sorted(k))
        req[key] = float(v)
    contact_ok = {tuple(sorted(k.split("|"))) if isinstance(k, str) else tuple(sorted(k))
                  for k in (allow_contact or set())}

    rows = []
    for (na, a), (nb, b) in combinations(sorted(parts.items()), 2):
        key = tuple(sorted((na, nb)))
        need = req.get(key, default_clearance)
        overlap = intersection_volume(a, b)
        if overlap > VOLUME_NOISE_MM3:
            rows.append({
                "pair": f"{na} vs {nb}", "state": "FAIL",
                "check": "interference",
                "detail": f"overlap {overlap:.3f} mm^3",
                "measured_mm": 0.0, "required_mm": need,
            })
            continue
        dist = min_distance(a, b)
        touching = dist <= 1e-7
        if touching and key in contact_ok:
            state, detail = "PASS", "in contact (allowed)"
        elif touching:
            state = "PASS" if need <= 0.0 else "FAIL"
            detail = "in contact" + ("" if need <= 0.0 else f", needs {need:.2f} mm gap")
        else:
            state = "PASS" if dist >= need - TOL_MM else "FAIL"
            detail = f"gap {dist:.3f} mm" + ("" if state == "PASS" else f" < required {need:.2f} mm")
        rows.append({
            "pair": f"{na} vs {nb}", "state": state,
            "check": "clearance", "detail": detail,
            "measured_mm": round(dist, 4), "required_mm": need,
        })
    return rows
