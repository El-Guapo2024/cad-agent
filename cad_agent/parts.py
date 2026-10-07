"""Shared geometry helpers. Standard hole sizes come from ISO 273 and the usual tap drills."""
from __future__ import annotations
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
    """
    if kind not in EXTRUSION:
        raise ValueError(f"unknown extrusion {kind!r}; choose from {sorted(EXTRUSION)}")
    if axis not in ("x", "y", "z"):
        raise ValueError(f"axis must be x, y or z, not {axis!r}")
    e = EXTRUSION[kind]
    w, h = e["w"], e["h"]
    dims = {"x": (length, h, w), "y": (w, length, h), "z": (w, h, length)}[axis]
    return Box(*dims)


def panel(width: float, height: float, thickness: float):
    return Box(width, height, thickness)
