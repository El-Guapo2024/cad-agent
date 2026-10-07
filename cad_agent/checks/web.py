"""In-plane checks for flat parts: how much material is left between features.

This exists because two real faults got past every other gate on the first
car. A battery-bay cutout swallowed two of four caster holes, and a row of
slots sat 4.5 mm from a plate edge leaving under 3 mm of acrylic beside a
3.4 mm hole. Both are layout errors *inside one part*, so the fit gate never
looked at them, and ray-cast thickness cannot see them either: on a flat
plate every inward ray measures the 3 mm sheet, never the web between a hole
and the edge.

So this works in the plane instead. Section the solid, take the boundary
wires, and measure between them:

  web width   the closest approach between any two distinct boundaries, which
              is the narrowest strip of material in the part
  feature     the count of closed inner boundaries, which changes when one
  count       cutout eats another or a hole breaks out through an edge
  regions     the number of separate faces, which is above one only when the
              part has fallen into pieces

A swallowed hole shows up twice over: the count drops, and the merged opening
usually pulls the web width down as well.
"""
from __future__ import annotations

from itertools import combinations

from build123d import Plane, section

from ..geom import bbox, closest_points

# The plane to slice on, per thin axis. A flat part is flat *about* its
# thinnest bounding-box axis, and that axis is not always z.
#
# Hardcoding Plane.XY was a real bug rather than a limitation: a plate
# standing on edge got sliced along its thin direction, which returns a
# ragged strip instead of the part's outline. The rule then reported a split
# part and no cutouts — a confident wrong answer, which is worse than
# declining to judge. The axis is now derived from the part.
_PLANE = {0: Plane.YZ, 1: Plane.XZ, 2: Plane.XY}
_AXIS_NAME = {0: "x", 1: "y", 2: "z"}


def thin_axis(solid) -> int:
    """Index of the shortest bounding-box axis: the one a flat part is flat about."""
    lo, hi = bbox(solid)
    dims = [hi[i] - lo[i] for i in range(3)]
    return min(range(3), key=lambda i: dims[i])


def section_wires(solid, z: float | None = None, axis: int | None = None):
    """Boundary wires of a mid-slice through the part, and how many faces it made.

    `axis` is the index of the normal to slice on; by default the part's own
    thinnest axis, so the slice shows the outline a reader would draw.
    """
    if axis is None:
        axis = thin_axis(solid)
    if z is None:
        lo, hi = bbox(solid)
        z = (lo[axis] + hi[axis]) / 2.0
    sketch = section(solid, _PLANE[axis].offset(z))
    faces = sketch.faces()
    outers, inners = [], []
    for f in faces:
        outers.append(f.outer_wire())
        inners.extend(f.inner_wires())
    return outers, inners, len(faces)


def web_report(solid, z: float | None = None, max_pairs: int = 4000,
               axis: int | None = None) -> dict:
    """Narrowest web, feature count, and region count for a flat part.

    `state` is MEASURED, or says why there is no web number. TRIVIAL is a slice with one
    boundary, a plain plate: no cutout reaches it, so nothing sits between a cutout and the
    edge, and there is no web to find. EMPTY is a slice that cut no material, so the outline
    could not be read at all, and SKIPPED a part with more boundaries than max_pairs allows.
    """
    if axis is None:
        axis = thin_axis(solid)
    outers, inners, n_faces = section_wires(solid, z, axis)
    wires = outers + inners
    if not wires:
        return {"state": "EMPTY", "features": 0, "regions": 0,
                "note": "the slice cuts no material, so the outline could not be read"}
    if len(wires) < 2:
        return {"state": "TRIVIAL", "features": len(inners), "regions": n_faces,
                "note": "one boundary, so no cutout reaches the slice and there is no web to measure"}

    pairs = list(combinations(range(len(wires)), 2))
    if len(pairs) > max_pairs:
        return {"state": "SKIPPED", "features": len(inners), "regions": n_faces,
                "note": f"{len(pairs)} wire pairs exceeds the {max_pairs} cap; "
                        "raise max_pairs to gate this part"}

    best, where, at = float("inf"), None, None
    for i, j in pairs:
        d, p1, p2 = closest_points(wires[i], wires[j])
        if d < best:
            best, where, at = d, (i, j), (p1, p2)

    def label(k):
        if k < len(outers):
            return "outer edge"
        w = inners[k - len(outers)]
        c = w.center()
        u, v = [i for i in range(3) if i != axis]
        cc = (c.X, c.Y, c.Z)
        return f"cutout at ({cc[u]:.1f}, {cc[v]:.1f})"

    u, v = [i for i in range(3) if i != axis]
    mid = ((at[0][u] + at[1][u]) / 2.0, (at[0][v] + at[1][v]) / 2.0)
    return {
        "state": "MEASURED",
        "min_web_mm": round(best, 4),
        "between": f"{label(where[0])} and {label(where[1])}",
        "at_xy": [round(mid[0], 2), round(mid[1], 2)],
        "features": len(inners),
        "regions": n_faces,
        "pairs_checked": len(pairs),
        "plane": f"normal to {_AXIS_NAME[axis]}",
    }
