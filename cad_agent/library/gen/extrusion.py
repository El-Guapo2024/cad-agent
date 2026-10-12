"""Aluminium T-slot extrusion: the real section (exact), and the box that stands for it (envelope).

Two ways to have a 2020, 2040 or 4040 in an assembly, and the library keeps them apart on purpose.

`envelope` is the blank cad_agent.parts.extrusion_blank draws: a box of the profile's outer size. A boolean against
it is cheap, which is why the eval givens use it, and it is the right solid to fit a part against. It is also
solid, so a stiffness rule reading it would take it for a beam six times stiffer than the real one: the catalog
marks it `geometry = "envelope"` and only `exact` may give stiffness.

`tslot6` and `tslot8` draw the cross-section the maker's own model has, extruded: the outer rectangle with its
corner radii, a T-slot cut into each face (neck, lip, undercut cavity with its 45 degree shoulders, floor), the
centre bore, and for the 20 x 40 and the 40 x 40 the hollow chambers between the slots. Everything is drawn from
the profile's own numbers, which the catalog lists one by one with the file they were measured on. What is left
out is what is under half a millimetre: the 0.2 and 0.5 mm fillets of the slot edges, which leave the section
a few tenths of a percent over the maker's area and second moments (0.6 percent at most, for the 20 x 40).
tests/test_library.py holds each section to the area and the second moments the maker's model has, to 1 percent, so
a number mistyped in the catalog is found by the test and not by a deflection that is wrong by a few percent.

The section is drawn in the xy plane, `width` across x and `height` along y (20 x 40 means the long side along y), then
extruded along z and turned to `axis`, with the same bounding box `envelope` has for the same arguments: the profile's
long side along y when the length runs along x or z, and along z when it runs along y. A section has two mirror planes,
so the turn that makes it a rotation and not a reflection changes nothing.
"""
from __future__ import annotations

import math

from build123d import Axis, Box, Cylinder, Edge, Face, Plane, Pos, Vector, Wire, extrude

AXES = ("x", "y", "z")


def _axis(axis: str) -> None:
    if axis not in AXES:
        raise ValueError(f"axis must be x, y or z, not {axis!r}")


def envelope(width, height, length, axis="x", bore_dia=None, bores=0):
    """The box of a `width` x `height` profile, `length` long along `axis`, centred on the origin.

    `bore_dia` and `bores` drill a bore of that diameter the whole length, one per `height` / `bores` of the
    profile's height, centred in each (two for a 2040: one in each 20 x 20 half).
    """
    _axis(axis)
    dims = {"x": (length, height, width), "y": (width, length, height), "z": (width, height, length)}[axis]
    body = Box(*dims)
    for k in range(bores):
        off = (k - (bores - 1) / 2.0) * (height / bores)
        bore = Cylinder(bore_dia / 2.0, length + 2.0)
        if axis == "x":
            body -= Pos(0, off, 0) * bore.rotate(Axis.Y, 90)
        elif axis == "y":
            body -= Pos(0, 0, off) * bore.rotate(Axis.X, 90)
        else:
            body -= Pos(0, off, 0) * bore
    return body


# ─── Drawing a section ───────────────────────────────────────────────────────

def _polygon(points) -> Face:
    return Face(Wire.make_polygon([Vector(x, y) for x, y in points], close=True))


def _rect(width, height, radius) -> Face:
    face = _polygon([(-width / 2.0, -height / 2.0), (width / 2.0, -height / 2.0), (width / 2.0, height / 2.0),
                     (-width / 2.0, height / 2.0)])
    return face.fillet_2d(radius, face.vertices()) if radius else face


def _slot_at(cutter: Face, side: str, at) -> Face:
    """A cutter drawn at the origin with its inward direction +y, moved to a slot on one side of the section."""
    turn = {"bottom": 0, "right": 90, "top": 180, "left": -90}[side]
    return cutter.rotate(Axis.Z, turn).moved(Pos(*at))


def _quadrants(quarter) -> list:
    """A polygon drawn in one quadrant, from the +y axis round to its end, mirrored into the other three."""
    q = [tuple(p) for p in quarter]
    out = q + [(x, -y) for x, y in reversed(q)] + [(-x, -y) for x, y in q] + [(-x, y) for x, y in reversed(q)]
    return [p for i, p in enumerate(out) if p != out[i - 1]]              # a point on an axis is not drawn twice


def _then(section: Face, length, axis) -> object:
    """The section extruded `length` along z, centred, and turned so that the length runs along `axis`."""
    _axis(axis)
    part = extrude(section, amount=length / 2.0, both=True)
    if axis == "x":
        return part.rotate(Axis.Y, 90)
    if axis == "y":
        return part.rotate(Axis.X, -90)
    return part


# ─── The 20 mm module with the 6 mm slot: 2020 and 2040 ──────────────────────

def tslot6_section(width, height, corner, neck, lead, lead_t, lip, cavity, shoulder_t, floor, floor_s, notch_s,
                   notch_t, core_r, ear_root, ear_tip, chamber=None) -> Face:
    """The section of a profile made of 20 mm modules: `height` / `width` of them side by side along y.

    A slot is described by the air it cuts, in (s, t): s along the face from the slot's axis and t inward from the
    face. The opening is `neck` either side of the axis, widening to `lead` at the face over `lead_t`; the lip is
    `lip` thick; under it the cavity is `cavity` either side, down to `shoulder_t`, where a 45 degree wall runs to the
    `floor` (t) at `floor_s`; the floor has a V notch from `notch_s` to a point at `notch_t`. The centre bore of each
    module is a circle of `core_r` with four reliefs (`ear_root`, `ear_tip`: the corners of the one on the diagonal).
    A profile of more than one module has a hollow `chamber` between them, given as one quadrant of its polygon.
    """
    half = [(lead, -1.0), (lead, 0.0), (neck, lead_t), (neck, lip), (cavity, lip), (cavity, shoulder_t),
            (floor_s, floor), (notch_s, floor), (0.0, notch_t)]
    cutter = _polygon(half + [(-s, t) for s, t in reversed(half[:-1])])
    cells = round(height / width)
    section = _rect(width, height, corner)
    for side, at in (("bottom", (0, -height / 2.0)), ("top", (0, height / 2.0))):
        section = section - _slot_at(cutter, side, at)
    (a, b), (c, d) = ear_root, ear_tip
    bore = Face(Wire.make_circle(core_r, Plane.XY))
    for k in range(4):
        bore = bore + _polygon([(a, b), (c, d), (d, c), (b, a)]).rotate(Axis.Z, 90 * k)
    for k in range(cells):
        yc = (k - (cells - 1) / 2.0) * width
        section = section - _slot_at(cutter, "right", (width / 2.0, yc)) - _slot_at(cutter, "left", (-width / 2.0, yc))
        section = section - bore.moved(Pos(0, yc, 0))
    if chamber:
        section = section - _polygon(_quadrants(chamber))
    return section


def tslot6(width, height, length, corner, neck, lead, lead_t, lip, cavity, shoulder_t, floor, floor_s, notch_s, notch_t,
           core_r, ear_root, ear_tip, chamber=None, axis="x"):
    """A 2020 or a 2040: `tslot6_section` extruded `length` along `axis`."""
    return _then(tslot6_section(width, height, corner, neck, lead, lead_t, lip, cavity, shoulder_t, floor, floor_s,
                                notch_s, notch_t, core_r, ear_root, ear_tip, chamber), length, axis)


# ─── The 40 mm profile with the 8 mm slot: 4040 ──────────────────────────────

def _on(c, r, angle):
    return (c[0] + r * math.cos(math.radians(angle)), c[1] + r * math.sin(math.radians(angle)))


def _arc(c, r, start, end):
    """(the point halfway, the end point) of the arc about `c` of radius `r` from angle `start` to `end` (degrees, the short way)."""
    return _on(c, r, (start + end) / 2.0), _on(c, r, end)


def _round(c, r, start, end):
    """The vertex `_closed` takes for an arc about `c` of radius `r` from angle `start` to `end`: (its end, a point on it)."""
    mid, stop = _arc(c, r, start, end)
    return stop, mid


def _closed(vertices) -> Wire:
    """A wire through (point, mid) vertices: mid is None for a line from the one before, else a point the arc passes through."""
    edges = []
    for (p0, _), (p1, mid) in zip(vertices, vertices[1:]):
        a, b = Vector(*p0), Vector(*p1)
        edges.append(Edge.make_three_point_arc(a, Vector(*mid), b) if mid else Edge.make_line(a, b))
    a, b = Vector(*vertices[-1][0]), Vector(*vertices[0][0])
    if (a - b).length > 1e-9:
        edges.append(Edge.make_line(a, b))
    return Wire(edges)


def tslot8_section(width, corner, neck, lead, hook_t, hook_r, hook_top, hook_out, wing_c, wing_r, wall, shoulder_r,
                   shoulder_t, floor, floor_half, chamber_lo, chamber_hi, chamber_r, bore_r) -> Face:
    """The section of the 40 x 40 profile: four slots, four hollow corners, the centre bore.

    A slot is the air it cuts, in (s, t) as above. Its lip edge is rounded with a radius of `lead` - `neck`, so the
    neck wall at `neck` starts that far in; a hook (rounded `hook_r` at its inner corner) reaches in to `hook_top`
    and out to `hook_out`; the cavity wings out round a circle of `wing_r` about `wing_c` to a wall at `wall`, and
    two shoulders of radius `shoulder_r` join it, by a 45 degree wall, to the floor at `floor`, `floor_half` either side.
    Each corner chamber is a square void from `chamber_lo` to `chamber_hi` with its outer corner rounded `chamber_r`.
    """
    lead_r = lead - neck
    dx = hook_out - wing_c[0]
    wing_start = math.degrees(math.atan2(-math.sqrt(wing_r ** 2 - dx ** 2), dx))   # where the hook's side meets the wing
    meet = (hook_out, wing_c[1] + wing_r * math.sin(math.radians(wing_start)))
    c1 = (wall - shoulder_r, shoulder_t)
    c2 = (floor_half, floor - shoulder_r)
    right = [((lead, -1.0), None), ((lead, 0.0), None), _round((lead, lead_r), lead_r, 270, 180),
             ((neck, hook_t), None), _round((neck + hook_r, hook_t), hook_r, 180, 90),
             ((hook_out, hook_top), None), (meet, None), _round(wing_c, wing_r, wing_start, 0),
             ((wall, shoulder_t), None), _round(c1, shoulder_r, 0, 45),
             (_on(c2, shoulder_r, 45), None), _round(c2, shoulder_r, 45, 90),
             ((0.0, floor), None)]
    left = []                                  # the left half: the right half walked back, every point and arc mirrored
    for i in range(len(right) - 1, 0, -1):
        prev, mid = right[i - 1][0], right[i][1]
        left.append(((-prev[0], prev[1]), (-mid[0], mid[1]) if mid else None))
    cutter = Face(_closed(right + left))
    section = _rect(width, width, corner)
    for side, at in (("bottom", (0, -width / 2.0)), ("right", (width / 2.0, 0)), ("top", (0, width / 2.0)),
                     ("left", (-width / 2.0, 0))):
        section = section - _slot_at(cutter, side, at)
    c = (chamber_hi - chamber_r, chamber_hi - chamber_r)
    mid, end = _arc(c, chamber_r, 45, 90)
    chamber = Face(_closed([((chamber_lo, chamber_lo), None), ((chamber_hi, chamber_lo), None), (_on(c, chamber_r, 0), None),
                            (end, mid), ((chamber_lo, chamber_hi), None)]))
    for k in range(4):
        section = section - chamber.rotate(Axis.Z, 90 * k)
    return section - Face(Wire.make_circle(bore_r, Plane.XY))


def tslot8(width, length, corner, neck, lead, hook_t, hook_r, hook_top, hook_out, wing_c, wing_r, wall, shoulder_r,
           shoulder_t, floor, floor_half, chamber_lo, chamber_hi, chamber_r, bore_r, axis="x"):
    """A 4040: `tslot8_section` extruded `length` along `axis`."""
    return _then(tslot8_section(width, corner, neck, lead, hook_t, hook_r, hook_top, hook_out, wing_c, wing_r, wall,
                                shoulder_r, shoulder_t, floor, floor_half, chamber_lo, chamber_hi, chamber_r, bore_r),
                 length, axis)
