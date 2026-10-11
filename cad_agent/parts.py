"""Shared geometry helpers. Standard hole sizes come from ISO 273 and the usual tap drills."""
from __future__ import annotations
from typing import NamedTuple

from build123d import (
    BuildPart, BuildSketch, Plane, Pos, Rot, Box, Cylinder, Rectangle, Circle,
    extrude, Mode, Axis, Locations, fillet, chamfer,
)

# ISO 273 clearance holes for coarse-thread screws, as (fine, medium, coarse). Parts drill the
# medium size; `[[interface]]` in a spec accepts anything from fine to coarse, since a close
# 3.2 mm or a loose 3.6 mm hole for an M3 is no mistake.
ISO_273 = {"M2": (2.2, 2.4, 2.6), "M2.5": (2.7, 2.9, 3.1), "M3": (3.2, 3.4, 3.6),
           "M4": (4.3, 4.5, 4.8), "M5": (5.3, 5.5, 5.8), "M6": (6.4, 6.6, 7.0),
           "M8": (8.4, 9.0, 10.0)}
CLEARANCE_HOLE = {screw: sizes[1] for screw, sizes in ISO_273.items()}
# Tapping drill diameters for coarse thread.
TAP_DRILL = {"M2": 1.6, "M2.5": 2.05, "M3": 2.5, "M4": 3.3, "M5": 4.2, "M6": 5.0, "M8": 6.8}
# Heat-set insert bores, typical for brass knurled inserts in FDM parts.
HEATSET_BORE = {"M3": 4.0, "M4": 5.6, "M5": 6.4}

# Aluminium extrusion: profile width, slot width, centre bore for a self-tapping screw.
EXTRUSION = {
    "2020": {"w": 20.0, "h": 20.0, "slot": 6.0, "bore": 4.2},
    "2040": {"w": 20.0, "h": 40.0, "slot": 6.0, "bore": 4.2},
    "4040": {"w": 40.0, "h": 40.0, "slot": 8.0, "bore": 6.8},
}


def extrusion_blank(kind: str, length: float, axis: str = "x"):
    """Simplified extrusion: outer envelope only, no slot profile.

    The envelope is what fit checks need. The slot profile matters only for
    renders, so it is deliberately omitted to keep boolean cost down.

    `axis` is the direction the length runs in, which defaults to x because a
    rail is nearly always horizontal. Getting this wrong puts a rail through
    whatever it was meant to support, so it is explicit rather than implied.

    It is a solid box, which has about twice the stiffness of the profile it stands for, so a rule that
    wants a section must not take one from it: `blank_of` recognises one, however it has been cut since.
    """
    if kind not in EXTRUSION:
        raise ValueError(f"unknown extrusion {kind!r}; choose from {sorted(EXTRUSION)}")
    if axis not in ("x", "y", "z"):
        raise ValueError(f"axis must be x, y or z, not {axis!r}")
    e = EXTRUSION[kind]
    w, h = e["w"], e["h"]
    dims = {"x": (length, h, w), "y": (w, length, h), "z": (w, h, length)}[axis]
    return Box(*dims)


BLANK_FILL = 0.9           # a solid box of an extrusion's size with less than this of it cut away is still its blank
BLANK_SLENDER = 2.0        # and at least this many times as long as it is wide: a rail, not a stub or a cube
BLANK_TOL_MM = 0.1         # how far its two sides across may be from the profile's


class Blank(NamedTuple):
    kind: str                 # the EXTRUSION it stands for, "2040"
    footprint_mm: tuple       # its two sides across, smaller first
    length_mm: float
    fill: float               # its volume as a fraction of footprint x length


def blank_of(footprint_mm, length_mm: float, volume_mm3: float) -> Blank | None:
    """The extrusion a body stands in for, or None, from the size of its usual section (the two sides of its
    bounding box, `beam.Profile.footprint`), its length along the beam and its volume.

    A body is "made" and its geometry "exact" to bodies.describe when it is a part module's, and a part module
    that returns `extrusion_blank`, or drills it for a bracket, is as exact as any other. But a section read from
    a solid box is a solid rectangle, and a 2040's real stiffness is about half that, so a rule that takes a
    second moment of area from it (`[[deflection]]`) can pass what the real rail would fail. A tag on the solid
    would not do: a boolean (a hole, a cut) builds a new solid and drops it. So a body is a blank by what it is:
    its two sides across are a profile's width and height (EXTRUSION, to BLANK_TOL_MM), it is at least
    BLANK_SLENDER times as long as the longer of them, and its volume is BLANK_FILL or more of that footprint
    times its length. The footprint is read from the sections, which a placement or a turn of a degree or two
    does not change, and holes, bores, notches and mitres leave a blank well over the fill. A real profile
    fills 30 to 55 % of its box, and a body machined down for another purpose (a bracket) falls under the fill
    as well, so neither is caught. A solid bar that really has such a size says `solid = true` where it asks.
    """
    a, b = sorted(footprint_mm)
    if a <= 0 or length_mm < BLANK_SLENDER * b:
        return None
    fill = volume_mm3 / (a * b * length_mm)
    if fill < BLANK_FILL:
        return None
    for kind, e in EXTRUSION.items():
        w, h = sorted((e["w"], e["h"]))
        if abs(a - w) <= BLANK_TOL_MM and abs(b - h) <= BLANK_TOL_MM:
            return Blank(kind, (a, b), length_mm, fill)
    return None


def panel(width: float, height: float, thickness: float):
    return Box(width, height, thickness)
