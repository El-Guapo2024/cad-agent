"""com: whether the centre of mass is over the footprint the assembly stands on.

`stance` (rules.py) measures the footprint and says in its own docstring what it does not prove: that the
weight is over it. A machine with a motor out on a boom has a footprint with area and still falls over.
This rule closes that, with the masses that step 6 added (bodies.py): a made body weighs volume x density,
a bought body weighs what it declares (`mass_g` with a `mass_source`, bought.py), a stock body weighs
nothing anyone said.

What it judges. The assembly is one rigid body standing on its lowest plane, as `stance` takes it, and the
footprint is the support polygon there: the convex hull of the contact patches, which is every part of a
body within 0.05 mm of that plane (a flat foot gives its outline, a wheel on its side a strip, a ball a
dot). Not the bounding box of the bodies that touch, which is wrong for a frame on two feet or a body
with a leg at each corner. The centre of mass is the mass-weighted mean of the bodies' centroids, so a
bought body counts at the centroid of its solid, which for a box standing in for a part is the box's
centre. It must lie inside the polygon, and the row says by how much (or how far outside). Then, for each
axis in AXES, the same at both ends of its travel, one axis at a time from home like the `sweep` rule:
the centre of mass moves by (mass moved / total mass) x the travel, along the axis, and the polygon stays,
so a gantry that is stable at home and tips with its carriage at the end is a FAIL at that end. An axis
that moves a body standing on the ground changes the footprint as it goes, which this does not model, so
that axis is UNCHECKED.

When it applies. The rule is N/A for a design in which no bought part declares a mass. All 13 designs
that existed before step 6 are like that, each with a body of unknown mass (a motor, a rail, a bench), so
a rule that went UNCHECKED on every unknown mass would have put every one of them on hold for a claim
none of them ever made. Declaring a mass on a bought part is how a design starts to claim a balance, and
from then on the rule is strict: UNCHECKED while any body's mass is unknown, naming each and why. That is
the only place it can be loosened: `_judged` below.

What it does not judge: dynamics, anything flexing, a pose other than home and the ends of each axis, two
axes off home together (step 8), or whether the thing is meant to stand at all. A bracket that is screwed
to a frame has a lowest plane too, and once its bought parts declare masses it is held to this.
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, Row, register

GROUND_MM = 0.05            # stance's number: a body this near the lowest plane rests on it
CHORD_MM = 0.05             # how finely the outline of a contact patch is cut into points
RULE = "centre of mass"
SOURCE = ("mass-weighted centroids of the bodies (made: volume x density; bought: declared mass_g); footprint: "
          f"the convex hull of what is within {GROUND_MM:g} mm of the lowest plane; static, one axis at a time")


@register(scope="assembly", name="com", order=35)
def com(ctx):
    """Whether the centre of mass is over the footprint the assembly stands on, once a bought part declares a mass."""
    if not ctx.parts:
        yield Row(subject="assembly", rule=RULE, state="N/A", measured="no assembly", limit="n/a",
                  source="nothing positioned to stand up")
        return
    infos = _infos(ctx)
    if not _judged(infos):
        none = sorted(n for n in ctx.parts if infos.get(n) is None or infos[n].mass_g is None)
        yield Row(subject="assembly", rule=RULE, state="N/A",
                  measured=("no bought part declares a mass_g with a mass_source, so nothing says what the assembly "
                            f"weighs ({len(none)} of {len(ctx.parts)} bodies have no mass)"),
                  limit="n/a",
                  source="judged once a bought part declares a mass (bought.py has the contract); `stance` "
                         "says the footprint has area, not that the weight is over it")
        return
    unknown = sorted(n for n in ctx.parts if infos.get(n) is None or infos[n].mass_g is None)
    if unknown:
        why = "; ".join(f"{n} ({_why_no_mass(infos.get(n))})" for n in unknown)
        yield Row(subject="assembly", rule=RULE, state="UNCHECKED",
                  measured=f"no mass for {len(unknown)} of {len(ctx.parts)} bodies: {why}",
                  limit="every body's mass known",
                  source="made: volume x density of its MATERIAL; bought: declared mass_g with a mass_source; "
                         "a stock body has none")
        return

    try:
        bodies = {n: _body(ctx.parts[n], infos[n].mass_g, n) for n in sorted(ctx.parts)}
    except _Unmeasurable as e:
        yield Row(subject="assembly", rule=RULE, state="UNCHECKED", measured=str(e), limit="every body has a volume",
                  source=SOURCE)
        return
    total = sum(b.mass for b in bodies.values())
    centre = tuple(sum(b.mass * b.at[i] for b in bodies.values()) / total for i in range(3))

    from ..geom import bbox
    ground = min(bbox(s)[0][2] for s in ctx.parts.values())
    resting = sorted(n for n, s in ctx.parts.items() if bbox(s)[0][2] - ground <= GROUND_MM + TOL_MM)
    try:
        hull = _hull([p for n in resting for p in _patch(ctx.parts[n], ground, n)])
    except _Unmeasurable as e:
        yield Row(subject="assembly", rule=RULE, state="UNCHECKED", measured=str(e),
                  limit="a contact patch for every body on the ground", source=SOURCE)
        return

    on = ", ".join(resting[:4]) + (f" and {len(resting) - 4} more" if len(resting) > 4 else "")
    margin = _margin(hull, centre[:2])
    where = f"({_mm(centre[0])}, {_mm(centre[1])}) mm, {_mm(centre[2] - ground)} mm above the ground"
    if margin is None:
        yield Row(subject="assembly", rule=RULE, state="FAIL",
                  measured=f"the footprint of {on} is a line or a point, so there is nothing for the centre of mass "
                           f"{where} to be over",
                  limit="inside a footprint with area", source=SOURCE)
        return
    yield Row(subject="assembly", rule=RULE, state="PASS" if margin >= -TOL_MM else "FAIL",
              measured=(f"centre of mass {where}, {_mm(max(margin, 0.0))} mm inside the footprint of {on}; "
                        f"{total:.1f} g in all" if margin >= -TOL_MM else
                        f"centre of mass {where}, {_mm(-margin)} mm outside the footprint of {on}; "
                        f"{total:.1f} g in all"),
              limit="inside the footprint", source=SOURCE)

    for name, axis in sorted(ctx.axes.items()):
        yield _axis_row(name, axis, bodies, resting, hull, centre, total, ctx.parts)


def _axis_row(name: str, axis, bodies: dict, resting: list, hull: list, centre: tuple, total: float, parts: dict) -> Row:
    """The centre of mass with the axis at each end of its travel, against the footprint at home."""
    rule = f"{RULE}/{name}"
    missing = [m for m in axis.moves if m not in parts]
    if missing:
        return Row(subject=f"axis {name}", rule=rule, state="UNCHECKED",
                   measured=f"axis {name} moves {', '.join(missing)}, which the assembly does not return",
                   limit="every moved body is in the assembly", source=SOURCE)
    stands = sorted(set(axis.moves) & set(resting))
    if stands:
        return Row(subject=f"axis {name}", rule=rule, state="UNCHECKED",
                   measured=(f"axis {name} moves {', '.join(stands)}, which stands on the ground, so the footprint "
                             "changes along its travel"),
                   limit="a footprint that does not move", source=SOURCE)
    share = sum(bodies[m].mass for m in set(axis.moves)) / total
    try:
        u = axis.unit
    except ValueError as e:     # motion.Axis says so for a zero direction
        return Row(subject=f"axis {name}", rule=rule, state="UNCHECKED", measured=str(e),
                   limit="an axis with a direction", source=SOURCE)
    ends = []
    for t in axis.travel:
        at = (centre[0] + share * u[0] * t, centre[1] + share * u[1] * t)
        ends.append((_margin(hull, at), t, at))
    worst = min(ends, key=lambda e: e[0])
    if worst[0] >= -TOL_MM:
        return Row(subject=f"axis {name}", rule=rule, state="PASS",
                   measured=(f"over {name} = {axis.travel[0]:+.1f} to {axis.travel[1]:+.1f} mm the centre of mass stays "
                             f"inside the footprint, closest {_mm(max(worst[0], 0.0))} mm from its edge at {name} = "
                             f"{worst[1]:+.1f} mm ({share * 100:.0f}% of the mass moves)"),
                   limit="inside the footprint at both ends of travel", source=SOURCE)
    return Row(subject=f"axis {name}", rule=rule, state="FAIL",
               measured=(f"at {name} = {worst[1]:+.1f} mm the centre of mass ({_mm(worst[2][0])}, {_mm(worst[2][1])}) mm "
                         f"is {_mm(-worst[0])} mm outside the footprint ({share * 100:.0f}% of the mass moves)"),
               limit="inside the footprint at both ends of travel", source=SOURCE)


def _mm(v: float) -> str:
    """A length to a tenth of a millimetre, without the sign of a zero that is only rounding."""
    return f"{round(v, 1) + 0.0:.1f}"


# ─── What the rule applies to ────────────────────────────────────────────────

def _judged(infos: dict) -> bool:
    """Whether the design has started to declare masses: any bought part with a mass it gives a source for."""
    return any(i.kind == "bought" and i.mass_g is not None for i in infos.values())


def _infos(ctx) -> dict:
    """The BodyInfo of every body: the machine's, or described from the project's files for a bare context."""
    machine = ctx.machine
    if machine is not None and getattr(machine, "bodies", None):
        return machine.bodies
    from ..bodies import describe
    return describe(ctx.slug, ctx.parts)


def _why_no_mass(info) -> str:
    if info is not None and info.notes:
        return "; ".join(info.notes)
    if info is not None and info.kind == "bought":
        return f"bought part {info.part!r} declares no mass_g with a mass_source"
    return "stock: assembly.py builds it itself; make it a part module with a MATERIAL or a bought part with a mass"


# ─── Geometry ────────────────────────────────────────────────────────────────

class _Unmeasurable(Exception):
    """A body whose centroid or contact patch could not be measured."""


class _Body:
    __slots__ = ("mass", "at")

    def __init__(self, mass: float, at: tuple):
        self.mass, self.at = mass, at


def _body(solid, mass_g: float, name: str) -> _Body:
    """A body's mass and the centroid of its solid, from the kernel's volume properties."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid.wrapped if hasattr(solid, "wrapped") else solid, props)
    if abs(props.Mass()) < 1e-9:
        raise _Unmeasurable(f"{name} has no volume, so its mass has no centroid to sit at")
    c = props.CentreOfMass()
    return _Body(mass_g, (c.X(), c.Y(), c.Z()))


def _patch(solid, ground: float, name: str) -> list:
    """The XY points of the part of `solid` within GROUND_MM of the ground plane."""
    from build123d import Box, Pos
    from ..geom import bbox
    lo, hi = bbox(solid)
    height = 1.0 + GROUND_MM
    slab = Pos((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, ground - 1.0 + height / 2) * Box(
        hi[0] - lo[0] + 2, hi[1] - lo[1] + 2, height)
    try:
        vertices, _ = (solid & slab).tessellate(CHORD_MM)
    except Exception as e:      # a boolean the kernel cannot do is a body we cannot measure, not a crash
        raise _Unmeasurable(f"where {name} touches the ground could not be measured: {type(e).__name__}: {e}") from e
    if not vertices:
        raise _Unmeasurable(f"{name} reaches the ground by its bounding box but no material of it is within "
                            f"{GROUND_MM:g} mm of it")
    return [(v.X, v.Y) for v in vertices]


def _hull(points: list) -> list:
    """The convex hull of points, counter-clockwise (Andrew's monotone chain); fewer than 3 if it has no area."""
    pts = sorted({(round(x, 6), round(y, 6)) for x, y in points})
    if len(pts) < 3:
        return pts

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _margin(hull: list, q: tuple) -> float | None:
    """How far inside the hull `q` is (mm, negative: how far outside), or None if the hull has no area."""
    if len(hull) < 3:
        return None
    inside, outside = math.inf, math.inf
    for (ax, ay), (bx, by) in zip(hull, hull[1:] + hull[:1]):
        ex, ey = bx - ax, by - ay
        length = math.hypot(ex, ey)
        inside = min(inside, (ex * (q[1] - ay) - ey * (q[0] - ax)) / length)     # signed: positive on the inner side
        t = max(0.0, min(1.0, ((q[0] - ax) * ex + (q[1] - ay) * ey) / (length * length)))
        outside = min(outside, math.hypot(q[0] - (ax + t * ex), q[1] - (ay + t * ey)))
    return inside if inside >= 0 else -outside
