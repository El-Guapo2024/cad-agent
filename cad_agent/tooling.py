"""Tool envelopes: the space a cutting or dispensing tool needs to be left free.

A tool is not designed, it is bought, so this module never tries to be a
catalogue. What it generates is the **envelope** — the volume nothing else may
occupy — built from numbers you read off the tool or its datasheet, not from a
remembered table of part numbers.

That distinction is the whole design. A drill bit's usable length varies by
maker and by regrind; its diameter does not. A laser's beam cone follows from
the focal length and the scan field and nothing else. So every function here
takes the few dimensions that are either definitional or printed on the thing
in front of you, and refuses to invent the rest.

What each envelope is actually for:

    drill / end mill   does the chuck reach the work without the spindle
                       nose hitting the fixture, and does the tool clear
                       the clamps on the way in
    laser cone         the f-theta lens throws a cone, not a line. At the
                       field corners the beam is tilted, and that tilt is
                       what a fixture wall gets in the way of
    dispense needle    the tip plus the barrel above it, which is taller
                       than people expect and is what collides with tall
                       parts already placed on the board

Every envelope is generated, so none of them needs provenance: there is no
vendor claim being trusted. The numbers you pass in are your own measurement,
and where they came from belongs in the part or assembly that calls this.
"""
from __future__ import annotations

import math

from build123d import Cone, Cylinder, Pos, Rot


def drill(diameter: float, flute: float, shank: float | None = None,
          shank_dia: float | None = None):
    """A twist drill standing point-down at the origin, tip at z = 0.

    `flute` and `shank` are lengths you measure or read off the tool, because
    they are the dimensions that differ between makers and shrink with every
    regrind. Only the diameter is definitional.

    Straight-shank drills below about 13 mm have shank diameter equal to
    nominal, which is the default here; pass `shank_dia` for a reduced or
    tapered shank.
    """
    if diameter <= 0 or flute <= 0:
        raise ValueError("diameter and flute length must be positive")
    shank = flute * 1.6 if shank is None else shank
    shank_dia = diameter if shank_dia is None else shank_dia

    # The point is a cone. 118 degrees included is the general-purpose grind,
    # so the point is about 0.3 x diameter tall. A steeper grind is shorter,
    # which makes this the conservative envelope.
    point_h = diameter / 2.0 / math.tan(math.radians(118.0 / 2.0))
    tool = Pos(0, 0, point_h / 2.0) * Cone(0.0, diameter / 2.0, point_h)
    body = flute - point_h
    if body > 0:
        tool += Pos(0, 0, point_h + body / 2.0) * Cylinder(diameter / 2.0, body)
    tool += Pos(0, 0, flute + shank / 2.0) * Cylinder(shank_dia / 2.0, shank)
    return tool


def end_mill(diameter: float, flute: float, shank: float,
             shank_dia: float | None = None):
    """A flat end mill standing cutting-end down, tip at z = 0.

    Flat-bottomed rather than pointed, which is the difference that matters:
    an end mill can plunge but leaves a flat floor, so its envelope is a
    plain cylinder and the clearance it needs is the same all the way down.
    """
    if diameter <= 0 or flute <= 0 or shank <= 0:
        raise ValueError("diameter, flute and shank must be positive")
    shank_dia = diameter if shank_dia is None else shank_dia
    tool = Pos(0, 0, flute / 2.0) * Cylinder(diameter / 2.0, flute)
    tool += Pos(0, 0, flute + shank / 2.0) * Cylinder(shank_dia / 2.0, shank)
    return tool


def collet_nose(diameter: float, length: float, standoff: float = 0.0):
    """The spindle's collet nut, which is what actually hits a clamp.

    `standoff` lifts it above z = 0 by the amount of tool sticking out. The
    usual mistake is checking the cutter for clearance and forgetting that
    the fat part is 40 mm up and 30 mm across.
    """
    return Pos(0, 0, standoff + length / 2.0) * Cylinder(diameter / 2.0, length)


def laser_cone(focal_length: float, field: float, lens_dia: float,
               offset: float = 0.0):
    """The swept volume of a galvo laser's beam over its whole scan field.

    Not a cylinder and not a single cone. The galvos steer the beam across
    the field, so over a full job the beam sweeps out a frustum: wide at the
    f-theta lens, narrowing to the field at the work plane. The work plane
    is z = 0 and the lens sits `focal_length` above it.

    This is the envelope that decides how tall a fixture wall can be. A wall
    that clears the beam at the field centre can still shadow a corner,
    because at the corner the beam is tilted by roughly atan(field/2 / f).

    `field` is the square field edge; the frustum is taken on its diagonal,
    which is the conservative reading.

    The frustum is wide at the work plane and narrow at the lens, which reads
    backwards until you follow one beam: any single beam converges downward to
    a point, but the galvos put that point anywhere in the field, so the union
    over a whole job opens out toward the work. At a fraction t of the way up
    the radius is r_work x (1 - t) + r_lens x t, which is exactly a frustum.
    """
    if focal_length <= 0 or field <= 0:
        raise ValueError("focal length and field must be positive")
    if lens_dia <= 0:
        raise ValueError("lens diameter must be positive")
    r_work = field * math.sqrt(2.0) / 2.0          # field corner, not edge
    r_lens = lens_dia / 2.0
    h = focal_length - offset
    if h <= 0:
        raise ValueError("focal length must exceed the offset")
    if abs(r_work - r_lens) < 1e-6:
        return Pos(0, 0, offset + h / 2.0) * Cylinder(r_work, h)
    return Pos(0, 0, offset + h / 2.0) * Cone(r_work, r_lens, h)


def tilt_at_corner(focal_length: float, field: float) -> float:
    """Beam tilt in degrees at a field corner. What shadows a fixture wall."""
    r = field * math.sqrt(2.0) / 2.0
    return math.degrees(math.atan2(r, focal_length))


def needle(tip_dia: float, tip_length: float, barrel_dia: float,
           barrel_length: float, taper: float = 0.0):
    """A paste dispense needle and the barrel above it, tip at z = 0.

    The barrel is included on purpose. A 0.5 mm tip clears everything; the
    23 mm barrel 20 mm above it does not, and that is the collision that
    actually happens when dispensing beside a tall connector.
    """
    tool = Pos(0, 0, tip_length / 2.0) * Cylinder(tip_dia / 2.0, tip_length)
    if taper > 0:
        tool += (Pos(0, 0, tip_length + taper / 2.0)
                 * Cone(tip_dia / 2.0, barrel_dia / 2.0, taper))
    tool += (Pos(0, 0, tip_length + taper + barrel_length / 2.0)
             * Cylinder(barrel_dia / 2.0, barrel_length))
    return tool


def at(solid, x: float = 0.0, y: float = 0.0, z: float = 0.0,
       tilt_x: float = 0.0, tilt_y: float = 0.0):
    """Put a tool envelope where the machine actually holds it.

    Tools are generated tip-down at the origin because that is the one pose
    everyone agrees on; this is how you move one into machine coordinates
    without every caller rewriting the same transform.
    """
    return Pos(x, y, z) * Rot(tilt_x, tilt_y, 0) * solid
