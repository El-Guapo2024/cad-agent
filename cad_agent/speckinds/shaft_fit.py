"""[[shaft_fit]]: a round shaft in the bores of another body, held to a clearance between their diameters.

A `[[clearance]]` `max_mm` is the closest approach, so "the bore grips the barrel" passed a loose bore with the
barrel resting on one side of it. A fit is the difference of the two diameters, which no placement changes:

    [[shaft_fit]]
    shaft = "shaft"             # the body with the round shaft
    bore = "bracket"            # the body whose bores it runs in
    min_mm = 0.2                # bore minus shaft, across the diameter: min_mm and/or max_mm, at least one
    max_mm = 1.0                # below 0 is an interference (press) fit
    fit = "H7/g6"               # or, instead of min_mm and max_mm: an ISO 286 fit, the limits from its tables
    nominal_mm = 10             # optional, with `fit`: the size it is looked up at; default from the model
    tol_mm = 0.1                # optional: how far the shaft's axis may be off a bore's; default 0.1
    pose = "park"               # optional, as on [[clearance]]

The clearance is diametral, as ISO 286 counts a fit: a 5.0 shaft in a 5.4 bore is 0.4, which is 0.2 a side
when it is centred and 0.4 on the open side when it rests on the other. A brief that says "0.1 to 0.5 mm a
side" is `min_mm = 0.2`, `max_mm = 1.0`.

`fit` is a hole class over a shaft class, hole basis or shaft basis or neither ("H7/g6", "G7/h6", "K7/h6").
It sets min_mm to the hole's lower deviation less the shaft's upper one, and max_mm to the hole's upper less
the shaft's lower, from the ISO 286-1 tables at the nominal size (cad_agent/iso286.py has them, and where
they come from): 25 H7/g6 is 0.007 to 0.041 mm, 25 H7/p6 -0.035 to -0.001. The nominal size is `nominal_mm`,
or else the mean of the bore's and the shaft's diameters to the nearest 0.1 mm, which is the size the two
were drawn about; it is in the row's limit, and near a range's end (10 is in 6 to 10, 10.1 in 10 to 18) it
is worth stating. The classes: holes F, G, H and JS 6 to 11, K and N 6 to 8, P 6 and 7; shafts c, d, e, f,
g, h and js 6 to 11, k, m, n, p and s 5 to 7; sizes over 0 up to 500 mm.

The model is one size, so a fit class judges the clearance that is modelled: right for a 3D print, where
the modelled gap is the gap the printer is asked for. A machined part drawn at its nominal size, bore and
shaft both 10.000 with H7/g6 on the drawing, fails by design (0 is below the class's least clearance): the
shop holds the class, so leave `fit` off it or model the bore and shaft inside their tolerance bands.

Both are read from the B-rep. A shaft is the convex cylinders of one radius on one axis that turn 270
degrees or more (so a D-shaft's flat leaves it a shaft); a bore is a hole as `[[interface]]` reads it
(speckinds/interface.py `holes()`), sized by its narrowest bore, except that bores on one axis with air
between them are a bore each (both cheeks of a fork are judged). A bore holds the shaft when their axes are
parallel within 1 degree, the shaft's axis is inside the bore, and the shaft runs along that narrowest bore.
Where a stepped shaft has more than one diameter in a bore, the largest is the one that fits.

One row per bore that holds the shaft: PASS when its clearance is within the limits and the axes are within
`tol_mm`, FAIL otherwise, and FAIL when the shaft is off the axis by more than half the clearance (it runs
into the wall). FAIL too when no bore of `bore` holds the shaft. UNCHECKED when the entry cannot be read: a
missing key, a body that is not there, `min_mm` above `max_mm`, or a `shaft` body with no round shaft; and
`fit` with `min_mm` or `max_mm` (which limit would hold is not clear), a fit or class it does not have,
`nominal_mm` without `fit`, or a nominal size outside 0 to 500 mm.

What it does not judge: how many bores (that is `[[holes]]`), the tolerance a shop would hold (the model is
one size; `fit` holds the modelled clearance to the class's limits), and how long the shaft is engaged.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, spec_kind
from .kit import (Unusable as _Unusable, get_body as _body, posed as _posed, require as _need, row as _row)

KEYS = ("shaft", "bore", "min_mm", "max_mm", "fit", "nominal_mm", "tol_mm", "pose")
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
    """A shaft in the bores of another body: bore minus shaft diameter against min_mm and/or max_mm, or a fit."""
    from .interface import _axis_offset, _parallel, _xyz, holes
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        raise _Unusable(f"[[shaft_fit]] does not take {', '.join(unknown)} (keys: {', '.join(KEYS)})")
    a, b = _need(entry, "shaft", "[[shaft_fit]]"), _need(entry, "bore", "[[shaft_fit]]")
    fit, nominal = _fit(entry)
    if fit is None and "min_mm" not in entry and "max_mm" not in entry:
        raise _Unusable("[[shaft_fit]] needs `min_mm` and/or `max_mm`, or `fit`")
    need = float(entry["min_mm"]) if "min_mm" in entry else None
    cap = float(entry["max_mm"]) if "max_mm" in entry else None
    if need is not None and cap is not None and need > cap:
        raise _Unusable(f"[[shaft_fit]] min_mm {need:g} is above max_mm {cap:g}")
    tol = float(entry.get("tol_mm", 0.1))
    if tol < 0:
        raise _Unusable("tol_mm must not be negative")

    def limits(size: float | None) -> tuple[float | None, float | None, str]:
        """(min_mm, max_mm, the limit's words): the entry's, or its fit's at a nominal size."""
        low, high, name = need, cap, ""
        if fit is not None:
            low, high = _fit_limits(fit, size)
            name = f"{fit} at {size:g} mm: "
        text = ", ".join(f"{sign} {v:g} mm" for sign, v in ((">=", low), ("<=", high)) if v is not None)
        return low, high, f"{name}bore minus shaft {text}, coaxial within {tol:g} mm"
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
        low, high, limit = limits(nominal if nominal is not None else round((h["dia"] + s["dia"]) / 2.0, 1))
        short = []
        if low is not None and gap < low - TOL_MM:
            short.append("too tight")
        if high is not None and gap > high + TOL_MM:
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
        limit = (limits(nominal)[2] if fit is None or nominal is not None
                 else f"{fit}: bore minus shaft in the fit's limits, coaxial within {tol:g} mm")
        yield _row(f"{a}|{b}", "shaft_fit", "FAIL",
                   f"no bore of {b} holds {a}: none is on its axis and along it{at_pose}", limit)


def _fit(entry: dict) -> tuple[str | None, float | None]:
    """(the entry's ISO 286 fit or None, its nominal_mm or None), each one checked."""
    if "fit" not in entry:
        if "nominal_mm" in entry:
            raise _Unusable("[[shaft_fit]] `nominal_mm` is the size a `fit` is looked up at, and there is no `fit`")
        return None, None
    if "min_mm" in entry or "max_mm" in entry:
        raise _Unusable("[[shaft_fit]] takes `fit` or `min_mm`/`max_mm`, not both: which limit holds is not clear")
    fit = entry["fit"]
    nominal = float(entry["nominal_mm"]) if "nominal_mm" in entry else None
    _fit_limits(fit, 10.0 if nominal is None else nominal)       # a class it does not have is UNCHECKED now
    return fit, nominal


def _fit_limits(fit: str, size: float) -> tuple[float, float]:
    """(min_mm, max_mm) of an ISO 286 fit at a nominal size, rounded to the micrometre the tables hold."""
    from ..iso286 import FitError, clearance
    try:
        low, high = clearance(fit, size)
    except FitError as e:
        raise _Unusable(f"[[shaft_fit]] `fit`: {e}") from None
    return round(low, 4), round(high, 4)
