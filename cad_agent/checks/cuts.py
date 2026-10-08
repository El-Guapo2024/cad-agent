"""What a process has to cut: its smallest round hole, and its narrowest slot or gap.

A laser cannot cut a hole much under a millimetre, nor a slot narrower than its own kerf, the width
of material the beam takes away. A mill has the same floor in its smallest drill and end mill. Both
are facts about the cutouts in the part, so they are read from the geometry, not declared:

  holes   spec.holes() reads the cylinders, so a round hole is its bore (a teardrop, a D and a slit
          bore count at their diameter) and a slot is its width
  gaps    two flat walls that face each other across air are a slot or a slit, whatever its shape: a
          window's short side, a notch cut into an edge, the space between two prongs. The distance
          between their planes is its width

A curved gap is not read here: a ring groove, or a flat wall facing a round boss. The round ends of
a slot are, because spec.holes() counts them in the slot.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM

PARALLEL = math.cos(math.radians(1.0))      # two walls face each other to within a degree
ALONG_EDGE = (0.0, 0.25, 0.5, 0.75, 1.0)    # where on each edge of a wall to read how far it reaches


def _where(x, y, z) -> tuple:
    """A point as rounded numbers; adding 0.0 turns the -0.0 that rounding noise leaves into 0.0."""
    return (round(x, 2) + 0.0, round(y, 2) + 0.0, round(z, 2) + 0.0)


def hole_report(solid) -> dict:
    """The round holes and slots of a solid as (size, where): a hole's diameter, a slot's width."""
    from ..spec import holes
    found = holes(solid)
    return {kind + "s": sorted((h["dia"], _where(h["point"].X, h["point"].Y, h["point"].Z))
                               for h in found if h["kind"] == kind)
            for kind in ("hole", "slot")}


def _walls(solid) -> list:
    """Every flat face of a solid as (outward normal, the points it reaches), in plain floats."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    walls = []
    for f in solid.faces():
        if BRepAdaptor_Surface(f.wrapped).GetType() != GeomAbs_Plane:
            continue
        reach = [e.position_at(t) for e in f.edges() for t in ALONG_EDGE]
        if reach:
            n = f.normal_at()
            walls.append(((n.X, n.Y, n.Z), [(p.X, p.Y, p.Z) for p in reach]))
    return walls


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _minus(a, b) -> tuple:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b) -> tuple:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a) -> tuple:
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def _extent(points, origin, u, v) -> tuple:
    """How far points reach from an origin along two directions: (u0, u1, v0, v1)."""
    us = [_dot(_minus(p, origin), u) for p in points]
    vs = [_dot(_minus(p, origin), v) for p in points]
    return min(us), max(us), min(vs), max(vs)


def gap_report(solid) -> list:
    """The air between flat walls that face each other, as (width, where), narrowest first.

    Two walls face when their outward normals point at each other, so what lies between them is
    air, not material, and when they overlap seen from one of them. The width is the distance
    between their planes. A plate's top and bottom face away from each other, so they never pair.
    """
    walls = _walls(solid)
    gaps = []
    for i, (na, reach_a) in enumerate(walls):
        pa = reach_a[0]
        u = _unit(_cross(na, (0.0, 0.0, 1.0) if abs(na[2]) < 0.9 else (1.0, 0.0, 0.0)))
        v = _cross(na, u)
        ua0, ua1, va0, va1 = _extent(reach_a, pa, u, v)
        for nb, reach_b in walls[i + 1:]:
            if _dot(na, nb) > -PARALLEL:
                continue
            pb = reach_b[0]
            across = _minus(pb, pa)
            width = _dot(across, na)                       # how far in front of A the other wall stands
            if width <= TOL_MM or -_dot(across, nb) <= TOL_MM:
                continue                                   # behind it, or level with it: not facing
            ub0, ub1, vb0, vb1 = _extent(reach_b, pa, u, v)
            lo_u, hi_u, lo_v, hi_v = max(ua0, ub0), min(ua1, ub1), max(va0, vb0), min(va1, vb1)
            if hi_u - lo_u <= TOL_MM or hi_v - lo_v <= TOL_MM:
                continue                                   # they pass each other without meeting
            mid = [pa[k] + u[k] * (lo_u + hi_u) / 2.0 + v[k] * (lo_v + hi_v) / 2.0
                   + na[k] * width / 2.0 for k in range(3)]
            gaps.append((width, _where(*mid)))
    return sorted(gaps)
