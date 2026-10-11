"""Beam deflection: Euler-Bernoulli bending, and the sections of a solid that it needs (step 6, piece C2).

`[[deflection]]` (speckinds/deflection.py) asks whether a body, held as a simple, fixed or cantilever beam
and loaded by a force, a mass or its own weight, sags more than a limit. This module is the engineering under
it, with no spec in sight: the closed forms, and the cross-sections of a solid that they need. The rule is the
judge. The method is the plan's: formulas now, and a finite-element cross-check (CalculiX with Gmsh) only later,
as an optional second opinion that never decides alone. Nothing here is a solver.

The formulas
------------
A prismatic beam of stiffness E I over a span L, under a point load P and a distributed load of total W (w L),
deflects by the sum of the two, each a case of Roark's Formulas for Stress and Strain (Young, Budynas and
Sadegh, 8th edition, McGraw-Hill 2012), Table 8.1. A case there is a number for the loading (1 a concentrated
load, 2 a distributed load over part of the span, here all of it) and a letter for the ends (a left end free and
right end fixed, d both ends fixed, e both ends simply supported):

    support     P at       P term                 W term                    where
    simple      midspan    P L^3 / (48 E I)  1e   5 W L^3 / (384 E I)  2e    midspan
    fixed       midspan    P L^3 / (192 E I) 1d     W L^3 / (384 E I)  2d    midspan
    cantilever  free end   P L^3 / (3 E I)   1a     W L^3 / (8 E I)    2a    the free end
    cantilever  midspan    5 P L^3 / (48 E I) 1a

Both terms peak at the same place, so their sum is the largest deflection anywhere, and that place is also the
worst one for the load: a load that moves along a simple or fixed beam does most harm at midspan, and along a
cantilever at its free end (`at = "worst"`). The forms are checked against an independent finite-element beam
in tests/test_deflection.py, which does not use these coefficients.

The sections
------------
E I needs the second moment of area of the beam's section, which is read from the solid and not from its
bounding box: a 20 x 40 T-slot extrusion has less than half the stiffness of the solid bar around it. The solid
is cut by a plane across the beam (BRepAlgoAPI_Common with a planar face, which leaves the face of the cut, holes
and separate regions included), BRepGProp.SurfaceProperties gives its area and centroid and GProp_GProps
.MatrixOfInertia its second moments about that centroid. That is what FreeCAD's Face.MatrixOfInertia returns for
a face (src/Mod/Part/App/TopoShapeFacePyImp.cpp, TopoShapeFacePy::getMatrixOfInertia at 3160daf1e2b6). With the
beam along a, a load along d and p the third axis, a flat section has M[p][p] = the integral of d^2 dA, which is
the second moment of area for that load: the one about the axis normal to the load. A section that is not
symmetric about the load has a product of inertia as well, and bends sideways; the stiffness against the load is
then I - Ipd^2 / Ipp, so that is what is used (the same, to the last digit, for a section symmetric about it).

Where along the body the sections are taken matters as much as how: a notch 2 mm wide is invisible to 21
sections spread over 400 mm. The stations are STATIONS equal cells' middles, the two ends (a small way in),
and the middle of every cut across the beam: OCCT gives where each edge of the solid starts and ends along the
axis, a section changes in kind only between those, and the middle of a hole's extent is its diameter plane, the
weakest section it makes. A body with more than MAX_STATIONS of them is not one this samples (NotABeam). None is
within SKIRT of the section's size from an end except the end stations, just beyond it. A body a degree or two off
its axis ends in a slanted cut, which is no cross-section, and the chamfers and fillets of an end are as short:
a zone that short at the clamped end of a cantilever, with half the stiffness, moves the tip by 3 w / L, which is
3 % for the 10 % of a beam ten times as long as it is deep, and less anywhere else.

The weakest section stands for the whole beam in the answer, and so does the stiffest: with every section at
least I_min the deflection cannot exceed the one computed with I_min everywhere (for a simple or cantilever beam
the deflection is a sum of positive terms, one for each section; for a fixed beam it follows from Castigliano for
a point load, and for its own weight it is the usual bound), and with every section at most I_max it cannot fall
below the one computed with I_max. tests/test_deflection.py holds both on finite-element beams whose stiffness
changes from element to element at random, for every support and load. `Profile.second_moment` gives I_min and
I_max; the rule passes on the first, fails on the second, and is UNCHECKED between them, since the answer then
depends on a section it cannot choose.

What a body must be to be a beam, and what is left out
-------------------------------------------------------
`profile` refuses (NotABeam, which the rule reports as UNCHECKED) a body that is not one solid, one that is as
wide as it is long, one with a long edge (a quarter of its length) that strays more than TILT_DEG from its axis
(a tilted, bent or tapered body: a plane across it is not its cross-section) or none at all, one with too many
cuts, and one whose section is in pieces over more than SPLIT_RUN of its size. A hole cuts the section at its
diameter in two, and the plate is still one beam, since the material round the hole ties the strips together;
the rails of a ladder, or the prongs of a fork, are tied only far away, so each bends alone or the load goes to
one of them.

Left out, and said in the rows: shear (the rule needs span/depth of SLENDER or more: for a solid rectangle the
shear term is (E / kG)(h / L)^2 of the bending term for a simple beam with a central load, a quarter of that for
a cantilever and four times it for fixed ends, which is 3 %, 0.8 % and 12 % at span/depth 10, so a fixed beam
gets 20; a thin-walled section carries its shear in its webs and does worse), torsion (the load is taken through
the section's centre: an open section such as a channel twists), buckling, the local give of a load or a support,
creep, and the anisotropy of a printed part. Supports are ideal: a bolted end is somewhere between simple and fixed,
and nothing here knows where.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

# The CAD kernel is imported where a solid is read (profile and what it calls), not here: cad_agent.spec
# imports every spec kind, and `cad ls` and `cad lib` answer without loading the kernel.

GRAVITY = 9.80665             # m/s^2, standard gravity: a mass of m grams weighs m * GRAVITY / 1000 newtons
STATIONS = 21                 # equal cells along the body, a section in the middle of each (the plan's number)
MAX_STATIONS = 120            # all stations together: about 60 ms each for a body with 60 holes, so 7 s at most
TILT_DEG = 2.0                # a long edge of the body may stray this far from its axis: 0.1 % off the section's I
LONG_EDGE = 0.25              # an edge is long enough to say which way the body runs at this fraction of its length
SPLIT_RUN = 0.5               # a section may be in pieces for this fraction of its size along the body (a hole)
SLENDER = {"simple": 10.0, "cantilever": 10.0, "fixed": 20.0}     # span/depth below which shear matters
MERGE_MM = 1e-3               # stations closer than this are one
NUDGE_MM = 1e-2               # how far a station on a face across the beam is moved off it
SKIRT = 0.1                   # a body a degree or two off its axis is cut slantwise at its ends, and an end has its
                              # chamfers: no station is nearer an end than this fraction of the body's size across,
                              # and the end stations sit just beyond
END_FRACTION = 1e-3           # the end stations are at least this fraction of the length inside the ends
GAP = 0.05                    # the second longest side is this much shorter than the longest, or the way is unclear
AXES = "xyz"
SUPPORTS = ("simple", "fixed", "cantilever")
PLACES = ("center", "end", "worst")


class NotABeam(Exception):
    """The body cannot be read as a beam, and why: the rule reports it as UNCHECKED."""


# ─── The closed forms ────────────────────────────────────────────────────────

# (the coefficient c of c F L^3 / (E I), the Roark Table 8.1 case) for each support and kind of load
_CASES = {
    "simple": {"center": (1 / 48, "1e"), "udl": (5 / 384, "2e")},
    "fixed": {"center": (1 / 192, "1d"), "udl": (1 / 384, "2d")},
    "cantilever": {"center": (5 / 48, "1a (a = L/2)"), "end": (1 / 3, "1a (a = 0)"), "udl": (1 / 8, "2a")},
}


class Deflection(NamedTuple):
    mm: float                 # the largest deflection: the sum of the two, where they both peak
    point_mm: float
    udl_mm: float
    where: str                # "midspan" or "the free end"
    cases: tuple              # the Roark cases that gave the terms, the point load's first


def place_of(support: str, at: str) -> str:
    """Where the point load acts, "center" or "end": `worst` is the free end of a cantilever, else midspan."""
    if support not in SUPPORTS:
        raise ValueError(f"support must be one of {', '.join(SUPPORTS)}, not {support!r}")
    if at not in PLACES:
        raise ValueError(f"at must be one of {', '.join(PLACES)}, not {at!r}")
    if at == "worst":
        return "end" if support == "cantilever" else "center"
    if at == "end" and support != "cantilever":
        raise ValueError("`end` is a cantilever's free end; a simple or fixed beam is loaded at `center`")
    return at


def deflection(support: str, span_mm: float, e_mpa: float, i_mm4: float, point_n: float = 0.0,
               udl_n: float = 0.0, at: str = "worst") -> Deflection:
    """The deflection of a beam, by Roark's Table 8.1 (see the module docstring): millimetres, from newtons,
    MPa and mm^4. `udl_n` is the whole of a load spread over the span."""
    place = place_of(support, at)
    for name, v in (("span_mm", span_mm), ("e_mpa", e_mpa), ("i_mm4", i_mm4)):
        if not (math.isfinite(v) and v > 0):
            raise ValueError(f"{name} must be a positive number, not {v!r}")
    if point_n < 0 or udl_n < 0:
        raise ValueError("loads are magnitudes: give them as positive numbers")
    k, point_case = _CASES[support][place]
    c, udl_case = _CASES[support]["udl"]
    scale = span_mm ** 3 / (e_mpa * i_mm4)
    point, udl = k * point_n * scale, c * udl_n * scale
    return Deflection(point + udl, point, udl, "the free end" if support == "cantilever" else "midspan",
                      (point_case, udl_case))


def weight_n(grams: float) -> float:
    """What a mass weighs, in newtons."""
    return grams * GRAVITY / 1000.0


# ─── The sections ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Section:
    """One cut across the beam. u and v are the two axes across it, in x, y, z order (Profile.across)."""
    x: float                  # where along the beam, mm
    area: float               # mm^2
    iu: float                 # the integral of u^2 dA: the second moment for a load along u, mm^4
    iv: float                 # the integral of v^2 dA
    iuv: float                # the integral of u v dA, the product of inertia
    extent: tuple             # the section's size along u and along v, mm
    pieces: int               # separate regions of it


@dataclass(frozen=True)
class Profile:
    """The sections along a body, in order, and the axis the beam runs along."""
    axis: int
    lo: float
    hi: float
    sections: tuple

    @property
    def length(self) -> float:
        return self.hi - self.lo

    @property
    def across(self) -> tuple:
        return tuple(i for i in range(3) if i != self.axis)

    def second_moment(self, load_axis: int) -> tuple[float, float]:
        """(the smallest, the largest) of the stiffness I the sections give against a load along `load_axis`."""
        u, v = self.across
        if load_axis not in (u, v):
            raise ValueError(f"a load along {AXES[load_axis]} does not bend a beam along {AXES[self.axis]}")
        both = [s.iu - s.iuv ** 2 / s.iv if load_axis == u else s.iv - s.iuv ** 2 / s.iu for s in self.sections]
        return min(both), max(both)

    def depth(self, load_axis: int) -> float:
        """The deepest the section gets along `load_axis`, mm."""
        u, v = self.across
        return max(s.extent[0 if load_axis == u else 1] for s in self.sections)


def profile(solid, axis: int | None = None) -> Profile:
    """The sections of `solid` along its axis (the longest way, or `axis` when it is given, as 0, 1 or 2).

    Raises NotABeam when it is not one: see the module docstring.
    """
    from .geom import box
    shape = solid.wrapped if hasattr(solid, "wrapped") else solid
    solids = _count(shape, "solid")
    if solids != 1:
        raise NotABeam(f"the body is {solids} solids, and a beam is one")
    g = box(shape).Get()
    lo3, hi3 = g[:3], g[3:]
    size = [h - low for low, h in zip(lo3, hi3)]
    if axis is None:
        a, b = sorted(range(3), key=lambda i: -size[i])[:2]
        if size[b] > (1.0 - GAP) * size[a]:
            raise NotABeam(f"the body is {size[a]:.1f} mm long in {AXES[a]} and {size[b]:.1f} mm in {AXES[b]}, "
                           f"so which way it runs as a beam is not clear: say `axis = \"{AXES[a]}\"` or "
                           f"`axis = \"{AXES[b]}\"`")
        axis = a
    lo, hi = lo3[axis], hi3[axis]
    if hi - lo <= 0:
        raise NotABeam("the body has no length along its axis")
    edges = _edges(shape, axis)
    _straight(edges, axis, lo, hi)
    u, v = (i for i in range(3) if i != axis)
    centre, half = [(low + h) / 2.0 for low, h in zip(lo3, hi3)], max(size) + 1.0
    marks = _marks(edges, lo, hi)
    stations = _stations(edges, marks, lo, hi, SKIRT * max(size[u], size[v]))
    sections = tuple(_section(shape, axis, x, centre, half, u, v) for x in stations)
    _joined(sections, marks, axis)
    return Profile(axis, lo, hi, sections)


def _count(shape, kind: str) -> int:
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    ex = TopExp_Explorer(shape, {"solid": TopAbs_SOLID, "face": TopAbs_FACE}[kind])
    n = 0
    while ex.More():
        n += 1
        ex.Next()
    return n


def _edges(shape, axis: int) -> list[tuple]:
    """(where it starts along the beam, where it ends, how far it strays across) for every edge of the shape."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape
    u, v = (i for i in range(3) if i != axis)
    edges = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
    found = set()
    for i in range(1, edges.Extent() + 1):
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(edges.FindKey(i), box, False, False)
        if box.IsVoid():                                  # a degenerate edge (a cone's apex) has no extent
            continue
        g = box.Get()
        found.add((round(g[axis], 5), round(g[axis + 3], 5), round(math.hypot(g[u + 3] - g[u], g[v + 3] - g[v]), 5)))
    return sorted(found)


def _straight(edges: list[tuple], axis: int, lo: float, hi: float) -> None:
    """The body's long edges must run along its axis: a plane across a tilted, bent or tapered body is not its
    cross-section, and the second moment read from it is too big. An edge that runs most of the length and strays
    across by more than TILT_DEG of it says the body is not straight."""
    long = [(a, b, w) for a, b, w in edges if b - a >= LONG_EDGE * (hi - lo)]
    if not long:
        raise NotABeam(f"no edge of the body runs even {LONG_EDGE:.0%} of its length along {AXES[axis]}, so its "
                       "straightness cannot be told (ribs or grooves across every edge, or a curved body)")
    a, b, w = max(long, key=lambda e: e[2] / (e[1] - e[0]))
    if w > math.tan(math.radians(TILT_DEG)) * (b - a):
        raise NotABeam(f"an edge that runs along the body strays {w:.2f} mm across over {b - a:.1f} mm "
                       f"({math.degrees(math.atan2(w, b - a)):.1f} degrees, where {TILT_DEG:g} is the most): "
                       "a tilted, bent or tapered body is not a straight beam, and a plane across it is not "
                       "its cross-section")


def _marks(edges: list[tuple], lo: float, hi: float) -> list[float]:
    """Where along the beam an edge of the body starts or ends, and the two ends of the body: the section
    keeps its kind between two of them."""
    return _merged(sorted({lo, hi} | {x for a, b, _ in edges for x in (a, b)}))


def _stations(edges: list[tuple], marks: list[float], lo: float, hi: float, skirt: float) -> list[float]:
    """Where along the beam to cut: the middle of each of STATIONS equal cells, a little inside each end, and
    the middle of every edge's extent along the beam (a hole's diameter plane) and of every gap between marks.
    None is within `skirt` of an end but the two end stations, just beyond it: a body that is a degree off its
    axis ends in a slanted cut, which is no cross-section. A station on a face across the beam is moved off it,
    since a cut in the plane of a face does not say which side it is on."""
    length = hi - lo
    inset = max(END_FRACTION * length, 10 * MERGE_MM, 1.1 * skirt)
    if 2 * inset >= length:
        return [lo + length / 2.0]
    want = [lo + (i + 0.5) * length / STATIONS for i in range(STATIONS)]
    want += [(a + b) / 2.0 for a, b in zip(marks, marks[1:]) if b - a > 10 * MERGE_MM]
    want += [(a + b) / 2.0 for a, b, _ in edges if b - a > 10 * MERGE_MM]
    want = [x for x in want if lo + skirt <= x <= hi - skirt] + [lo + inset, hi - inset]
    cut: list[float] = []
    for x in sorted(want):
        if any(abs(x - m) < MERGE_MM for m in marks):
            x = x + NUDGE_MM if x + NUDGE_MM < hi - NUDGE_MM else x - NUDGE_MM
        if not cut or x - cut[-1] >= MERGE_MM:
            cut.append(x)
    if len(cut) > MAX_STATIONS:
        raise NotABeam(f"{len(cut)} places along the body where its shape changes: more than {MAX_STATIONS} "
                       "sections to take, so it is not a beam this can sample")
    return cut


def _merged(values: list[float]) -> list[float]:
    out: list[float] = []
    for x in values:
        if not out or x - out[-1] >= MERGE_MM:
            out.append(x)
    return out


def _joined(sections: tuple, marks: list[float], axis: int) -> None:
    """A section in several pieces is one beam only where the pieces are joined close by. A hole through a plate
    cuts its section in two at the hole's diameter, and the plate still bends as one: the material on either side
    ties the strips together. Parts joined only far away (a ladder's rails, the prongs of a fork) do not: each
    piece bends alone, or the load goes to one of them. The run of the body that is in pieces, from one mark to
    another, may be no more than SPLIT_RUN of the section's size."""
    from bisect import bisect_right
    cells = sorted({min(bisect_right(marks, s.x) - 1, len(marks) - 2) for s in sections if s.pieces != 1})
    biggest = max(max(s.extent) for s in sections)
    start = 0
    for i, cell in enumerate(cells):
        if i + 1 < len(cells) and cells[i + 1] == cell + 1:
            continue                                  # the run goes on into the next cell
        first = cells[start]
        run = marks[cell + 1] - marks[first]
        if run > SPLIT_RUN * biggest:
            raise NotABeam(f"from {AXES[axis]} = {marks[first]:.2f} mm for {run:.1f} mm the section is in separate "
                           f"pieces, more than {SPLIT_RUN:g} of its size ({biggest:.1f} mm): pieces joined only "
                           "at a distance do not bend as one beam")
        start = i + 1


def _section(shape, axis: int, x: float, centre: list, half: float, u: int, v: int) -> Section:
    """The cut at `x`: the solid's common part with a planar face across the beam, and its properties."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    origin = [x if i == axis else centre[i] for i in range(3)]
    plane = gp_Pln(gp_Pnt(*origin), gp_Dir(*[1.0 if i == axis else 0.0 for i in range(3)]))
    face = BRepBuilderAPI_MakeFace(plane, -half, half, -half, half).Face()
    common = BRepAlgoAPI_Common(shape, face)
    if not common.IsDone():
        common.Build()
    where = f"{AXES[axis]} = {x:.2f} mm"
    cut = common.Shape() if common.IsDone() else None
    if cut is None or cut.IsNull():
        raise NotABeam(f"the section at {where} could not be cut")
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(cut, props)
    area = props.Mass()
    if area <= 1e-9:
        raise NotABeam(f"the body has no section at {where}: it is cut right through there")
    pieces, ex = 0, TopExp_Explorer(cut, TopAbs_FACE)
    while ex.More():
        one = GProp_GProps()
        BRepGProp.SurfaceProperties_s(ex.Current(), one)
        pieces += one.Mass() > 1e-6 * area
        ex.Next()
    m = props.MatrixOfInertia()

    def moment(r: int, k: int) -> float:
        return m.Value(r + 1, k + 1)                                  # gp_Mat counts from 1

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(cut, box, False, False)
    g = box.Get()
    # for a flat section M[i][i] is the integral of the squares of the other two coordinates, and M[i][j] is
    # minus the integral of the product of i and j, so across the beam M[v][v] is the one for a load along u
    return Section(x=x, area=area, iu=moment(v, v), iv=moment(u, u), iuv=-moment(u, v),
                   extent=(g[u + 3] - g[u], g[v + 3] - g[v]), pieces=pieces)
