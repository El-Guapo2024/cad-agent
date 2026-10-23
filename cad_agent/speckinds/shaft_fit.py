"""[[shaft_fit]]: a round shaft in the bores of another body, held to a clearance between their diameters.

A `[[clearance]]` `max_mm` is the closest approach, so "the bore grips the barrel" passed a loose bore with the
barrel resting on one side of it. A fit is the difference of the two diameters, which no placement changes:

    [[shaft_fit]]
    shaft = "shaft"             # the body with the round shaft
    bore = "bracket"            # the body whose bores it runs in
    min_mm = 0.2                # bore minus shaft, across the diameter: min_mm and/or max_mm, at least one
    max_mm = 1.0                # below 0 is an interference (press) fit
    tol_mm = 0.1                # optional: how far the shaft's axis may be off a bore's; default 0.1
    pose = "park"               # optional, as on [[clearance]]

The clearance is diametral, as ISO 286 counts a fit: a 5.0 shaft in a 5.4 bore is 0.4, which is 0.2 a side
when it is centred and 0.4 on the open side when it rests on the other. A brief that says "0.1 to 0.5 mm a
side" is `min_mm = 0.2`, `max_mm = 1.0`.

Both are read from the B-rep. A shaft is the convex cylinders of one radius on one axis that turn 270
degrees or more (so a D-shaft's flat leaves it a shaft); a bore is a hole as `[[interface]]` reads it
(speckinds/interface.py `holes()`), sized by its narrowest bore, except that bores on one axis with air
between them are a bore each (both cheeks of a fork are judged). A bore holds the shaft when their axes are
parallel within 1 degree, the shaft's axis is inside the bore, and the shaft runs along that narrowest bore.
Where a stepped shaft has more than one diameter in a bore, the largest is the one that fits.

One row per bore that holds the shaft: PASS when its clearance is within the limits and the axes are within
`tol_mm`, FAIL otherwise, and FAIL when the shaft is off the axis by more than half the clearance (it runs
into the wall). FAIL too when no bore of `bore` holds the shaft. UNCHECKED when the entry cannot be read: a
missing key, a body that is not there, `min_mm` above `max_mm`, or a `shaft` body with no round shaft.

What it does not judge: how many bores (that is `[[holes]]`), the tolerance a shop would hold (the model is
one size; a fit class such as H7/g6 is not read), and how long the shaft is engaged.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, spec_kind
from .kit import (Unusable as _Unusable, get_body as _body, posed as _posed, require as _need, row as _row)

KEYS = ("shaft", "bore", "min_mm", "max_mm", "tol_mm", "pose")
PARALLEL_DEG = 1.0


def shafts(solid) -> list[dict]:
    """The round shafts of a solid: convex cylinders of one radius on one axis that turn 270 degrees or more."""
    from .interface import ARC_TOL, BORE_TURN, _arc, _cover, _cylinders, _same_axis
    groups = []                                        # the cylinders of one axis and one diameter
    for c in _cylinders(solid, concave=False):
        for g in groups:
            if _same_axis(g[0], c) and abs(g[0]["dia"] - c["dia"]) < 1e-3:
                g.append(c)
                break
        else:
            groups.append([c])
    found = []
    for g in groups:
        d, x = g[0]["dir"], g[0]["x"]
        cover = _cover([_arc(c, d, x) for c in g])
        if max(end - start for start, end in cover) >= BORE_TURN - ARC_TOL:
            found.append({"point": g[0]["point"], "dir": d, "dia": g[0]["dia"],
                          "ends": [p for c in g for p in c["ends"]]})
    return found


@spec_kind("shaft_fit", order=83)
def shaft_fit(entry: dict, ctx):
    """A shaft in the bores of another body: bore minus shaft diameter against min_mm and/or max_mm."""
    from .interface import _axis_offset, _parallel, _xyz, holes
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        raise _Unusable(f"[[shaft_fit]] does not take {', '.join(unknown)} (keys: {', '.join(KEYS)})")
    a, b = _need(entry, "shaft", "[[shaft_fit]]"), _need(entry, "bore", "[[shaft_fit]]")
    if "min_mm" not in entry and "max_mm" not in entry:
        raise _Unusable("[[shaft_fit]] needs `min_mm` and/or `max_mm`")
    need = float(entry["min_mm"]) if "min_mm" in entry else None
    cap = float(entry["max_mm"]) if "max_mm" in entry else None
    if need is not None and cap is not None and need > cap:
        raise _Unusable(f"[[shaft_fit]] min_mm {need:g} is above max_mm {cap:g}")
    tol = float(entry.get("tol_mm", 0.1))
    if tol < 0:
        raise _Unusable("tol_mm must not be negative")
    limit = ", ".join(f"{sign} {v:g} mm" for sign, v in ((">=", need), ("<=", cap)) if v is not None)
    limit = f"bore minus shaft {limit}, coaxial within {tol:g} mm"
    parts, at_pose = _posed(ctx, entry, "[[shaft_fit]]")
    sa, sb = _body(parts, a), _body(parts, b)
    rods = shafts(sa)
    if not rods:
        raise _Unusable(f"{a} has no round shaft: no convex cylinder that turns 270 degrees or more")
    held = 0
    bores = [(h, run) for h in holes(sb) if h["kind"] == "hole" for run in h["runs"]]
    for h, (lo, hi, dia) in bores:
        h = h | {"dia": dia, "point": h["point"] + h["dir"] * ((lo + hi) / 2.0 - h["point"].dot(h["dir"]))}
        inside = []
        for s in rods:
            if not _parallel(h, s, PARALLEL_DEG) or _axis_offset(h, s) > h["dia"] / 2.0:
                continue
            z = [p.dot(h["dir"]) for p in s["ends"]]
            if min(hi, max(z)) - max(lo, min(z)) > TOL_MM:      # the shaft runs along the bore
                inside.append(s)
        if not inside:
            continue
        held += 1
        s = max(inside, key=lambda s: s["dia"])
        gap, off = h["dia"] - s["dia"], _axis_offset(h, s)
        short = []
        if need is not None and gap < need - TOL_MM:
            short.append("too tight")
        if cap is not None and gap > cap + TOL_MM:
            short.append("too loose")
        if off > tol + TOL_MM:
            short.append(f"axis {off:.3f} mm off")
        if gap >= 0 and off > gap / 2.0 + TOL_MM:
            short.append("into the wall")
        side = f"{gap / 2.0:.3f} a side centred" if gap >= 0 else "interference"
        yield _row(f"{a}|{b}", "shaft_fit", "FAIL" if short else "PASS",
                   f"bore {h['dia']:.3f} at {_xyz(h['point'])} over shaft {s['dia']:.3f}: {gap:.3f} mm "
                   f"({side}), axis offset {off:.3f} mm{at_pose}" + (f", {', '.join(short)}" if short else ""),
                   limit)
    if not held:
        yield _row(f"{a}|{b}", "shaft_fit", "FAIL",
                   f"no bore of {b} holds {a}: none is on its axis and along it{at_pose}", limit)
