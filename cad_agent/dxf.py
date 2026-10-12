"""Laser parts: a DXF of the part's outline, written the way FreeCAD's ImpExpDxf writes one, and read back.

A laser cuts the outline of a flat part. The outline is the section of the solid by the plane half way through
its thickness (along the thinnest bounding-box axis), as 2D curves in the part's own frame: the drawing's x and
y are the part's two other axes looked at from the positive side, so a plate flat in z is drawn as it is seen
from above, not mirrored. Units are millimetres (`$INSUNITS 4`) and the origin is the part's origin, not the
corner of a sheet.

What FreeCAD does, and what is kept
-----------------------------------
FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6, LGPL-2.1-or-later) writes a DXF from a
shape in `ImpExpDxfWrite::exportShape` (src/Mod/Import/App/dxf/ImpExpDxf.cpp), through `CDxfWrite`
(src/Mod/Import/App/dxf/dxf.cpp), and `Import.writeDXFShape` (src/Mod/Import/App/AppImportPy.cpp) calls it. It
reads its options from the `Mod/Draft` group (`ImpExpDxfWrite::setOptions`), and this module takes each of
them at FreeCAD's default:

  DxfVersionOut        14  so the entities of release 14 are written: ELLIPSE and SPLINE as they are, LWPOLYLINE
                           where a curve has no entity of its own. The file says AC1014 and declares
                           millimetres in its header, as FreeCAD's header14.rub does. Release 12, the other
                           value there, is not offered
  DiscretizeEllipses   false  ellipses and splines stay ELLIPSE and SPLINE, so `maxsegmentlength` (5.0), the
                           length of the polyline segments FreeCAD makes where it does discretize, is not used.
                           A curve with no entity (a rational or periodic spline, a Bezier, an offset curve)
                           is cut into a polyline at FLATTEN_MM instead: FreeCAD drops a Bezier ("BCurve dxf
                           export not yet supported"), and a laser must not lose an edge
  ExportPoints         false  no POINT entities

and the way `exportShape` maps an edge to an entity:

  line                             LINE
  circle, closed (over 1 radian, ends within 0.03 mm)
                                   CIRCLE
  circle, open                     ARC, counter-clockwise from its start angle to its end angle (`writeArc`)
  ellipse                          ELLIPSE: centre, major axis vector, ratio, start and end parameter
  B-spline                         SPLINE: degree, knots, control points

The layer is `none`, which is what `writeDXFShape` names it, and the group codes follow `CDxfWrite` for a
version above 12 (owner handle 330, subclass markers 100). Where this differs from FreeCAD, and why:

  digits            FreeCAD prints 9 decimals ("use lots of digits to avoid rounding errors"). OCCT's own
                    tolerance is 1e-7 mm and its versions differ in the digits past that, so every number is
                    snapped to 1e-6 mm, a nanometre, and 6 are printed: the same bytes on OCCT 7.9 and 8.0
  order             FreeCAD walks the edges in the order the kernel's explorer gives them. These are put in
                    an order of their own: the holes first, by position, and the outline last, as a laser
                    should cut, and within a loop by kind and position
  header            FreeCAD's comment line is its build ("FreeCAD v1.0 ..."); this one names the part, where
                    the outline came from and the FreeCAD commit, and has no date. Its tables are the ones a
                    laser reader needs: FreeCAD's DIMSTYLE record is left out
  line ends         "\\n", whatever machine writes it

Where the outline comes from. For a part that passes `laser through-cut` (below), it is the boundary of the end
face at the top of the part, which is the section exactly and is made of the curves the part was built from.
The kernel's own section of a surface that is not a plane or a quadric (an extruded ellipse, say) is an
approximating B-spline of degree 8 with 160 poles that differs between OCCT 7.9 and 8.0 in the fourth decimal; the
end face has the ellipse, and the bytes repeat. Any other part (a draft) is written from the mid-plane section.
The file is read back against the mid-plane section either way.

Reading it back
---------------
`read_dxf` parses a file with ezdxf (a core dependency), an implementation that shares no code with this
writer, and `compare` holds what it found to the mid-plane section, by geometry: every point of the section's
edges, sampled finely, is within `TOL_MM` of the file's curves and every point of the file's curves is within
`TOL_MM` of the section, the file holds the entities that were written, as many of each kind, the units are
millimetres, and the cut length agrees. A wrong arc direction, a missing hole, a doubled entity or a shifted
outline each fail it. The section is sampled from OCCT's curves (`BRepAdaptor_Curve`), not from the entities
this module made, so an error in the conversion cannot hide itself.

The part rules
--------------
`laser_rows` gives the rows of a laser-cut part, which `cad shop`, the `shop` part rule and `[shop]` run:

  laser through-cut   the part is a prism of its outline, the one thing a laser can make. Every face is either
                      a plane across the thickness at one end of the part, or a surface that runs along the
                      thickness (a plane parallel to it, a cylinder or an extrusion with its axis along it);
                      anything else is a pocket floor, a step, a chamfer, a countersink, a draft or a
                      fillet, and is named. A face of another kind (a B-spline surface) is judged by the
                      sections alone: the section at 5 %, 50 % and 95 % of the thickness has one area,
                      and the volume is that area times the thickness. UNCHECKED if the mid-plane cuts no
                      material, so there is no outline to read
  dxf readback        the file reads back, with ezdxf, to the mid-plane section (above)

A section that cannot be made, or a curve that cannot be written, is UNCHECKED; nothing is passed on the
strength of a file that was not read.
"""
from __future__ import annotations

import io
import math
from collections import Counter
from typing import NamedTuple

import numpy as np

from .registry import Row

FREECAD_COMMIT = "3160daf1e2b6"
VERSION = 14                    # DxfVersionOut
FLATTEN_MM = 2e-4               # the deviation allowed where a curve with no entity of its own is cut into a polyline
LAYER = "none"                  # what Import.writeDXFShape names it
STAMP_LAYER = "NOT_VERIFIED"
GRID = 1_000_000                # numbers are snapped to 1 / GRID mm (and degrees) and printed with 6 decimals
TOL_MM = 1e-3                   # how far the file's curves may be from the section's
CHORD_MM = 2e-4                 # the chord error of the polylines both sides are sampled into
LENGTH_REL = 1e-4               # the cut length may differ by this fraction
CLOSED_SPAN = 1.0               # FreeCAD: an arc over this many radians whose ends meet is a full circle
CLOSED_GAP_SQ = 0.001           # ... meet means the squared distance between the ends is under this (mm^2)
LEVELS = (0.05, 0.5, 0.95)      # where through-cut takes the section, as fractions of the thickness
PRISM_REL = 1e-4                # the areas, and the volume against area x thickness, may differ by this fraction
END_TOL_MM = 1e-5               # a plane across the thickness is an end of the part when it is this close to it
SOURCE_WRITE = (f"FreeCAD {FREECAD_COMMIT} src/Mod/Import/App/dxf/ImpExpDxf.cpp ImpExpDxfWrite::exportShape "
                f"and dxf.cpp CDxfWrite (DxfVersionOut {VERSION}, DiscretizeEllipses false, ExportPoints false)")

# The two other axes of the part and the way the section is looked at, per thin axis: x_dir, y_dir, normal.
# These are build123d's Plane.YZ, Plane.XZ and Plane.XY, the same orientation the web rule draws.
FRAMES = {0: ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
          1: ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
          2: ((1, 0, 0), (0, 1, 0), (0, 0, 1))}
AXIS_NAME = "xyz"


class Unsupported(Exception):
    """A shape this module cannot make a DXF of; the message says what."""


class Line(NamedTuple):
    a: tuple
    b: tuple


class Circle(NamedTuple):
    c: tuple
    r: float


class Arc(NamedTuple):
    c: tuple
    r: float
    a0: float          # degrees, counter-clockwise from a0 to a1
    a1: float


class Ellipse(NamedTuple):
    c: tuple
    major: tuple       # the major axis from the centre to its end: a vector, not a length
    ratio: float
    t0: float          # radians from the major axis, counter-clockwise
    t1: float


class Spline(NamedTuple):
    degree: int
    knots: tuple
    poles: tuple


class Poly(NamedTuple):
    points: tuple
    closed: bool


KIND_ORDER = {"CIRCLE": 0, "ARC": 1, "LINE": 2, "ELLIPSE": 3, "SPLINE": 4, "POLY": 5}


def kind(p) -> str:
    return {Line: "LINE", Circle: "CIRCLE", Arc: "ARC", Ellipse: "ELLIPSE", Spline: "SPLINE", Poly: "POLY"}[type(p)]


# ─── Numbers ─────────────────────────────────────────────────────────────────

def snap(v: float) -> float:
    """A number on the 1e-6 grid, and never a negative zero."""
    return round(v * GRID) / GRID + 0.0


def snap2(p) -> tuple:
    return (snap(p[0]), snap(p[1]))


def angle(deg: float) -> float:
    """An angle in degrees on the grid and in [0, 360): 359.9999999 is 0, not 360."""
    a = snap(deg % 360.0)
    return 0.0 if a >= 360.0 else a


def num(v: float) -> str:
    """A grid number as FreeCAD writes one, fixed, but with 6 decimals; exact, from the integer."""
    q = round(v * GRID)
    whole, frac = divmod(abs(q), GRID)
    return f"{'-' if q < 0 else ''}{whole}.{frac:06d}"


# ─── The outline: a section, or the end face of a prism ──────────────────────

class Frame(NamedTuple):
    axis: int
    level: float                # the plane's position along the thin axis, in the part's frame
    origin: tuple
    u: tuple
    v: tuple
    n: tuple


class Cut(NamedTuple):
    frame: Frame
    loops: list                 # [(is_outer, [edge, ...]), ...] in the kernel's order
    area: float
    length: float
    thickness: float
    source: str                 # where the loops came from: "section" (the mid-plane's) or "end face" (the top's)

    def where(self) -> str:
        name = AXIS_NAME[self.frame.axis]
        return f"{self.source} normal to {name} at {name} = {self.frame.level:g} mm"


def frame_at(axis: int, level: float) -> Frame:
    u, v, n = FRAMES[axis]
    origin = tuple(level if i == axis else 0.0 for i in range(3))
    return Frame(axis, level, origin, u, v, n)


def _loops_of_faces(faces) -> list:
    loops = []
    for face in faces:
        loops.append((True, list(face.outer_wire().edges())))
        loops.extend((False, list(w.edges())) for w in face.inner_wires())
    return loops


def faces_at(solid, axis: int | None, fraction: float):
    """(frame, faces, thickness) of the section of a solid by the plane a fraction of the way through its
    thickness along `axis` (default: the thinnest).

    The plane is built at its position and not offset along a base plane's normal, which for build123d's
    Plane.XZ points toward -y: an offset of +y would then cut at -y.
    """
    from build123d import Plane, section
    from .checks.web import thin_axis
    from .geom import bbox
    if axis is None:
        axis = thin_axis(solid)
    lo, hi = bbox(solid)
    frame = frame_at(axis, lo[axis] + fraction * (hi[axis] - lo[axis]))
    sk = section(solid, Plane(origin=frame.origin, x_dir=frame.u, z_dir=frame.n))
    return frame, list(sk.faces()), hi[axis] - lo[axis]


def cut_at(solid, axis: int | None = None, fraction: float = 0.5) -> Cut:
    """The section of a solid: the boundary loops of its faces (the outline and the holes), area and length."""
    frame, faces, thickness = faces_at(solid, axis, fraction)
    loops = _loops_of_faces(faces)
    length = sum(e.length for _, edges in loops for e in edges)
    return Cut(frame, loops, sum(f.area for f in faces), length, thickness, "section")


PLURAL = {"flat wall": "flat walls", "end plane": "end planes", "cylinder along it": "cylinders along it",
          "extrusion along it": "extrusions along it"}


class Faces(NamedTuple):
    counts: Counter             # what kind of face the part has (a noun, singular), for the PASS row
    bad: list                   # a sentence for each face that is not part of a prism
    unknown: int                # faces of a kind this cannot judge (B-spline surfaces)
    top: list                   # the planes across the thickness at its top end


def faces_report(solid, axis: int) -> Faces:
    """Sort the faces of a part by whether a laser can make them (see the module docstring)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import (GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere,
                             GeomAbs_SurfaceOfExtrusion, GeomAbs_SurfaceOfRevolution, GeomAbs_Torus)
    from .geom import bbox
    name = AXIS_NAME[axis]
    lo, hi = bbox(solid)
    counts, bad, top, unknown = Counter(), [], [], 0

    def along(d) -> float:
        return abs((d.X(), d.Y(), d.Z())[axis])

    for face in solid.faces():
        s = BRepAdaptor_Surface(face.wrapped)
        t = s.GetType()
        if t == GeomAbs_Plane:
            d = along(s.Plane().Axis().Direction())
            if d < 1e-9:
                counts["flat wall"] += 1
            elif d > 1.0 - 1e-9:
                flo, fhi = bbox(face)
                z = flo[axis]
                if abs(z - hi[axis]) <= END_TOL_MM:
                    counts["end plane"] += 1
                    top.append(face)
                elif abs(z - lo[axis]) <= END_TOL_MM:
                    counts["end plane"] += 1
                else:
                    bad.append(f"a plane across {name} at {name} = {z:.3f} mm, which is neither end of the part (a pocket floor, a step or a boss)")
            else:
                bad.append(f"a plane slanted to {name} (a chamfer or a draft)")
        elif t == GeomAbs_Cylinder:
            if along(s.Cylinder().Axis().Direction()) > 1.0 - 1e-9:
                counts["cylinder along it"] += 1
            else:
                bad.append(f"a cylinder across {name}, not along it (a cross hole)")
        elif t == GeomAbs_SurfaceOfExtrusion:
            if along(s.Direction()) > 1.0 - 1e-9:
                counts["extrusion along it"] += 1
            else:
                bad.append(f"an extrusion across {name}, not along it")
        elif t == GeomAbs_Cone:
            bad.append("a cone (a chamfer, a countersink or a taper)")
        elif t == GeomAbs_Sphere:
            bad.append("a sphere (a dome or a ball end)")
        elif t == GeomAbs_Torus:
            bad.append("a torus (a fillet)")
        elif t == GeomAbs_SurfaceOfRevolution:
            bad.append("a surface of revolution (a turned feature)")
        else:
            unknown += 1
    return Faces(counts, bad, unknown, top)


def end_cut(solid, mid: Cut, faces: Faces) -> Cut | None:
    """The top end face of a prism as a Cut: its outline is the section, made of the part's own curves."""
    if not faces.top:
        return None
    axis = mid.frame.axis
    from .geom import bbox
    level = bbox(solid)[1][axis]
    loops = _loops_of_faces(faces.top)
    return Cut(frame_at(axis, level), loops, sum(f.area for f in faces.top), sum(e.length for _, es in loops for e in es),
               mid.thickness, "end face")


# ─── Edges to entities ───────────────────────────────────────────────────────

def local(frame: Frame, p) -> tuple:
    """A point (gp_Pnt) as the drawing's (x, y)."""
    d = (p.X() - frame.origin[0], p.Y() - frame.origin[1], p.Z() - frame.origin[2])
    return (d[0] * frame.u[0] + d[1] * frame.u[1] + d[2] * frame.u[2],
            d[0] * frame.v[0] + d[1] * frame.v[1] + d[2] * frame.v[2])


def _dir(frame: Frame, d) -> tuple:
    """A direction (gp_Dir) as the drawing's (x, y)."""
    return (d.X() * frame.u[0] + d.Y() * frame.u[1] + d.Z() * frame.u[2],
            d.X() * frame.v[0] + d.Y() * frame.v[1] + d.Z() * frame.v[2])


def _along(frame: Frame, d) -> float:
    """How far a direction (gp_Dir) runs along the section's normal: +1 counter-clockwise, -1 clockwise."""
    return d.X() * frame.n[0] + d.Y() * frame.n[1] + d.Z() * frame.n[2]


def primitive(edge, frame: Frame):
    """One edge as the entity FreeCAD's exportShape makes of it (see the module docstring)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import (GeomAbs_BSplineCurve, GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_Line)
    a = BRepAdaptor_Curve(edge.wrapped)
    kind_ = a.GetType()
    f, l = a.FirstParameter(), a.LastParameter()
    start, end = local(frame, a.Value(f)), local(frame, a.Value(l))
    if kind_ == GeomAbs_Line:
        return Line(*sorted((snap2(start), snap2(end))))
    if kind_ == GeomAbs_Circle:
        circ = a.Circle()
        centre, r = local(frame, circ.Location()), circ.Radius()
        ccw = _along(frame, circ.Axis().Direction())
        if abs(abs(ccw) - 1.0) > 1e-6:
            raise Unsupported("a circle of the outline is not in its plane")
        if abs(l - f) > CLOSED_SPAN and (start[0] - end[0]) ** 2 + (start[1] - end[1]) ** 2 < CLOSED_GAP_SQ:
            return Circle(snap2(centre), snap(r))
        s, e = (start, end) if ccw > 0 else (end, start)           # an arc is counter-clockwise start to end
        a0 = math.degrees(math.atan2(s[1] - centre[1], s[0] - centre[0]))
        a1 = math.degrees(math.atan2(e[1] - centre[1], e[0] - centre[0]))
        return Arc(snap2(centre), snap(r), angle(a0), angle(a1))
    if kind_ == GeomAbs_Ellipse:
        el = a.Ellipse()
        ccw = _along(frame, el.Axis().Direction())
        if abs(abs(ccw) - 1.0) > 1e-6:
            raise Unsupported("an ellipse of the outline is not in its plane")
        centre = local(frame, el.Location())
        x = _dir(frame, el.XAxis().Direction())
        major = (x[0] * el.MajorRadius(), x[1] * el.MajorRadius())
        ratio = el.MinorRadius() / el.MajorRadius()
        if abs(l - f) > CLOSED_SPAN and (start[0] - end[0]) ** 2 + (start[1] - end[1]) ** 2 < CLOSED_GAP_SQ:
            t0, t1 = 0.0, 2.0 * math.pi
        elif ccw > 0:
            t0, t1 = f % (2.0 * math.pi), l % (2.0 * math.pi)
        else:                                                      # the parameter runs clockwise: counter-clockwise it is -l to -f
            t0, t1 = (-l) % (2.0 * math.pi), (-f) % (2.0 * math.pi)
        return Ellipse(snap2(centre), snap2(major), snap(ratio), snap(t0), snap(t1))
    if kind_ == GeomAbs_BSplineCurve:
        spline = _spline(a, frame)
        if spline is not None:
            return spline
    return _poly(a, frame)


def _spline(a, frame: Frame):
    """The edge's B-spline as a SPLINE, or None for one a SPLINE here cannot hold: a rational or periodic one, or an
    edge that is only part of its curve (the part's other cuts trimmed it), which `BSpline()` answers with the whole
    curve. Those are cut into a polyline instead."""
    bs = a.BSpline()
    if abs(a.FirstParameter() - bs.FirstParameter()) > 1e-9 or abs(a.LastParameter() - bs.LastParameter()) > 1e-9:
        return None
    if bs.IsRational() or bs.IsPeriodic():
        return None
    n = bs.NbPoles()
    poles = [local(frame, bs.Pole(i)) for i in range(1, n + 1)]
    knots = []
    for i in range(1, bs.NbKnots() + 1):
        knots += [bs.Knot(i)] * bs.Multiplicity(i)
    if len(knots) != n + bs.Degree() + 1:
        return None
    if poles[0] > poles[-1]:                                       # start at the smaller end, whatever way the kernel ran it
        poles.reverse()
        top = knots[0] + knots[-1]
        knots = [top - k for k in reversed(knots)]
    return Spline(bs.Degree(), tuple(snap(k) for k in knots), tuple(snap2(p) for p in poles))


def _poly(a, frame: Frame) -> Poly:
    """A curve with no entity of its own, cut into a polyline that stays within FLATTEN_MM of it."""
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    d = GCPnts_QuasiUniformDeflection(a, FLATTEN_MM)
    if not d.IsDone() or d.NbPoints() < 2:
        raise Unsupported(f"a curve of the outline (type {a.GetType()}) could not be cut into a polyline")
    pts = [snap2(local(frame, d.Value(i))) for i in range(1, d.NbPoints() + 1)]
    if pts[0] > pts[-1]:
        pts.reverse()
    closed = (pts[0][0] - pts[-1][0]) ** 2 + (pts[0][1] - pts[-1][1]) ** 2 < 1e-12
    return Poly(tuple(pts[:-1] if closed else pts), closed)


def loops_of(cut: Cut) -> list:
    """[(is_outer, [entity, ...])] in the order they are written: holes first, by position, the outline last."""
    out = []
    for outer, edges in cut.loops:
        prims = sorted((primitive(e, cut.frame) for e in edges), key=_key)
        out.append((outer, prims))
    out.sort(key=lambda lp: (lp[0], _loop_key(lp[1])))
    return out


def _key(p) -> tuple:
    return (KIND_ORDER[kind(p)],) + tuple(_flat(p))


def _flat(p):
    for v in p:
        if isinstance(v, tuple):
            yield from _flat(v)
        elif isinstance(v, bool):
            yield float(v)
        else:
            yield v


def _loop_key(prims) -> tuple:
    xs, ys = zip(*(pt for p in prims for pt in extent_points(p)))
    return (min(xs), min(ys), max(xs), max(ys))


def extent_points(p) -> list:
    """Points that bound an entity: its ends and, for a circle or an arc, the extremes in x and y it reaches."""
    t = type(p)
    if t is Line:
        return [p.a, p.b]
    if t is Poly:
        return list(p.points)
    if t is Circle:
        return [(p.c[0] + dx * p.r, p.c[1] + dy * p.r) for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1))]
    if t is Arc:
        sweep = (p.a1 - p.a0) % 360.0 or 360.0
        pts = [(p.c[0] + p.r * math.cos(math.radians(a)), p.c[1] + p.r * math.sin(math.radians(a))) for a in (p.a0, p.a0 + sweep)]
        for k, (dx, dy) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):          # the extremes the sweep passes through
            if (90.0 * k - p.a0) % 360.0 <= sweep:
                pts.append((p.c[0] + dx * p.r, p.c[1] + dy * p.r))
        return pts
    return [tuple(pt) for pt in flatten(p, 0.01)]


# ─── Flattening (the same for the outline's entities and the file's) ─────────

def _arc_points(c, r, a0, a1, chord) -> np.ndarray:
    """Points along a counter-clockwise arc (angles in degrees) with no more than `chord` between arc and chord."""
    sweep = (a1 - a0) % 360.0 or 360.0
    step = 2.0 * math.acos(max(0.0, 1.0 - chord / r)) if r > chord else math.pi / 2
    n = max(2, int(math.ceil(math.radians(sweep) / step)) + 1)
    t = np.radians(a0 + np.linspace(0.0, sweep, n))
    return np.stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)], axis=1)


def flatten(p, chord: float = CHORD_MM) -> np.ndarray:
    """An entity as a polyline (n, 2) that stays within `chord` of it."""
    t = type(p)
    if t is Line:
        return np.array([p.a, p.b], dtype=float)
    if t is Circle:
        return _arc_points(p.c, p.r, 0.0, 360.0, chord)
    if t is Arc:
        return _arc_points(p.c, p.r, p.a0, p.a1, chord)
    if t is Poly:
        pts = list(p.points) + ([p.points[0]] if p.closed else [])
        return np.array(pts, dtype=float)
    if t is Ellipse:
        major = math.hypot(*p.major)
        step = 2.0 * math.acos(max(0.0, 1.0 - chord / major)) if major > chord else math.pi / 2
        span = (p.t1 - p.t0) % (2.0 * math.pi) or 2.0 * math.pi
        if p.t1 - p.t0 >= 2.0 * math.pi - 1e-5:
            span = 2.0 * math.pi
        n = max(8, int(math.ceil(span / step)) + 1)
        tt = p.t0 + np.linspace(0.0, span, n)
        ang = math.atan2(p.major[1], p.major[0])
        ex, ey = major * np.cos(tt), major * p.ratio * np.sin(tt)
        return np.stack([p.c[0] + ex * math.cos(ang) - ey * math.sin(ang),
                         p.c[1] + ex * math.sin(ang) + ey * math.cos(ang)], axis=1)
    if t is Spline:
        return _spline_points(p, chord)
    raise TypeError(p)


def _spline_points(p: Spline, chord: float) -> np.ndarray:
    """A clamped B-spline evaluated (de Boor) finely enough for `chord`."""
    poles = np.array(p.poles, dtype=float)
    knots = np.array(p.knots, dtype=float)
    d = p.degree
    t0, t1 = knots[d], knots[len(poles)]
    hull = float(np.sum(np.hypot(*np.diff(poles, axis=0).T)))
    n = int(min(5000, max(16, math.ceil(hull / max(chord * 20.0, 0.01)))))
    out = []
    for t in np.linspace(t0, t1, n):
        k = int(np.searchsorted(knots, t, side="right")) - 1
        k = min(max(k, d), len(poles) - 1)
        dd = [poles[j + k - d].copy() for j in range(d + 1)]
        for r in range(1, d + 1):
            for j in range(d, r - 1, -1):
                left, right = knots[j + k - d], knots[j + 1 + k - r]
                alpha = 0.0 if right == left else (t - left) / (right - left)
                dd[j] = (1.0 - alpha) * dd[j - 1] + alpha * dd[j]
        out.append(dd[d])
    return np.array(out)


# ─── Writing ─────────────────────────────────────────────────────────────────

class _Out:
    """The text of a DXF as group code and value pairs, "\\n" ended, codes right-justified to 3 as FreeCAD writes them."""

    def __init__(self):
        self.lines: list[str] = []

    def put(self, code: int, value) -> None:
        self.lines.append(f"{code:3d}")
        self.lines.append(str(value))

    def point(self, code: int, *xyz: float) -> None:
        for i, v in enumerate(xyz):
            self.put(code + 10 * i, num(v))

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def write_dxf(cut: Cut, name: str, stamp: str | None = None, loops: list | None = None) -> bytes:
    """The DXF of an outline: the same bytes for the same outline (see the module docstring)."""
    loops = loops_of(cut) if loops is None else loops
    prims = [p for _, ps in loops for p in ps]
    if not prims:
        raise Unsupported("the outline has no edges: the mid-plane cuts no material")
    pts = [pt for p in prims for pt in extent_points(p)]
    xs, ys = zip(*pts)
    lo, hi = (min(xs), min(ys)), (max(xs), max(ys))
    frame = cut.frame
    over = [AXIS_NAME[i] for i in range(3) if i != frame.axis]
    thin = AXIS_NAME[frame.axis]
    out = _Out()
    comment = (f"cad-agent part {name}: {cut.source} normal to {thin} at {thin} = {num(frame.level)} mm; "
               f"drawing x,y = part {over[0]},{over[1]}; units mm; entities as FreeCAD {FREECAD_COMMIT} ImpExpDxf, "
               f"version {VERSION}")
    if stamp:
        comment = f"{stamp}: not from a verified design. " + comment
    out.put(999, comment)

    h = [0]

    def handle() -> str:
        h[0] += 1
        return f"{h[0]:X}"

    # HEADER
    out.put(0, "SECTION"); out.put(2, "HEADER")
    out.put(9, "$ACADVER"); out.put(1, "AC1014")
    out.put(9, "$ACADMAINTVER"); out.put(70, 9)
    out.put(9, "$DWGCODEPAGE"); out.put(3, "ANSI_1252")
    out.put(9, "$TEXTSTYLE"); out.put(7, "STANDARD")
    out.put(9, "$LUNITS"); out.put(70, 2)
    out.put(9, "$MEASUREMENT"); out.put(70, 1)
    out.put(9, "$INSUNITS"); out.put(70, 4)
    out.put(9, "$EXTMIN"); out.point(10, lo[0], lo[1], 0.0)
    out.put(9, "$EXTMAX"); out.point(10, hi[0], hi[1], 0.0)
    out.put(9, "$HANDSEED"); seed_at = len(out.lines); out.put(5, "0")
    out.put(0, "ENDSEC")

    # CLASSES: the one an LWPOLYLINE needs
    out.put(0, "SECTION"); out.put(2, "CLASSES")
    out.put(0, "CLASS"); out.put(1, "LWPOLYLINE"); out.put(2, "AcDbPolyline"); out.put(3, "ObjectDBX Classes")
    out.put(90, 0); out.put(280, 0); out.put(281, 1)
    out.put(0, "ENDSEC")

    # TABLES
    layers = [LAYER] + ([STAMP_LAYER] if stamp else [])
    out.put(0, "SECTION"); out.put(2, "TABLES")

    def table(tname: str, count: int):
        owner = handle()
        out.put(0, "TABLE"); out.put(2, tname); out.put(5, owner); out.put(330, 0)
        out.put(100, "AcDbSymbolTable"); out.put(70, count)
        return owner

    def record(rname: str, owner: str, marker: str):
        hd = handle()
        out.put(0, rname); out.put(5, hd); out.put(330, owner)
        out.put(100, "AcDbSymbolTableRecord"); out.put(100, marker)
        return hd

    owner = table("VPORT", 1)
    record("VPORT", owner, "AcDbViewportTableRecord"); out.put(2, "*ACTIVE"); out.put(70, 0)
    out.put(0, "ENDTAB")
    owner = table("LTYPE", 3)
    for lname, desc in (("BYBLOCK", ""), ("BYLAYER", ""), ("CONTINUOUS", "Solid line")):
        record("LTYPE", owner, "AcDbLinetypeTableRecord")
        out.put(2, lname); out.put(70, 0); out.put(3, desc); out.put(72, 65); out.put(73, 0); out.put(40, "0.0")
    out.put(0, "ENDTAB")
    owner = table("LAYER", len(layers) + 1)
    for lname in ["0"] + layers:
        record("LAYER", owner, "AcDbLayerTableRecord")
        out.put(2, lname); out.put(70, 0); out.put(62, 7); out.put(6, "CONTINUOUS")
    out.put(0, "ENDTAB")
    owner = table("STYLE", 1)
    record("STYLE", owner, "AcDbTextStyleTableRecord")
    out.put(2, "STANDARD"); out.put(70, 0); out.put(40, "0.0"); out.put(41, "1.0"); out.put(50, "0.0"); out.put(71, 0)
    out.put(42, "2.5"); out.put(3, "txt"); out.put(4, "")
    out.put(0, "ENDTAB")
    table("VIEW", 0); out.put(0, "ENDTAB")
    table("UCS", 0); out.put(0, "ENDTAB")
    owner = table("APPID", 1)
    record("APPID", owner, "AcDbRegAppTableRecord"); out.put(2, "ACAD"); out.put(70, 0)
    out.put(0, "ENDTAB")
    owner = table("BLOCK_RECORD", 2)
    model_record = handle()
    paper_record = handle()
    for hd, bname in ((model_record, "*MODEL_SPACE"), (paper_record, "*PAPER_SPACE")):
        out.put(0, "BLOCK_RECORD"); out.put(5, hd); out.put(330, owner)
        out.put(100, "AcDbSymbolTableRecord"); out.put(100, "AcDbBlockTableRecord"); out.put(2, bname)
    out.put(0, "ENDTAB")
    out.put(0, "ENDSEC")

    # BLOCKS: model and paper space, empty
    out.put(0, "SECTION"); out.put(2, "BLOCKS")
    for owner_record, bname, paper in ((model_record, "*MODEL_SPACE", False), (paper_record, "*PAPER_SPACE", True)):
        out.put(0, "BLOCK"); out.put(5, handle()); out.put(330, owner_record)
        out.put(100, "AcDbEntity")
        if paper:
            out.put(67, 1)
        out.put(8, "0"); out.put(100, "AcDbBlockBegin"); out.put(2, bname); out.put(70, 0)
        out.point(10, 0.0, 0.0, 0.0); out.put(3, bname); out.put(1, "")
        out.put(0, "ENDBLK"); out.put(5, handle()); out.put(330, owner_record)
        out.put(100, "AcDbEntity")
        if paper:
            out.put(67, 1)
        out.put(8, "0"); out.put(100, "AcDbBlockEnd")
    out.put(0, "ENDSEC")

    # ENTITIES
    out.put(0, "SECTION"); out.put(2, "ENTITIES")

    def head(etype: str, sub: str, layer: str = LAYER):
        out.put(0, etype); out.put(5, handle()); out.put(330, model_record)
        out.put(100, "AcDbEntity"); out.put(8, layer)
        if sub:
            out.put(100, sub)

    for p in prims:
        t = type(p)
        if t is Line:
            head("LINE", "AcDbLine"); out.point(10, p.a[0], p.a[1], 0.0); out.point(11, p.b[0], p.b[1], 0.0)
        elif t is Circle:
            head("CIRCLE", "AcDbCircle"); out.point(10, p.c[0], p.c[1], 0.0); out.put(40, num(p.r))
        elif t is Arc:
            head("ARC", "AcDbCircle"); out.point(10, p.c[0], p.c[1], 0.0); out.put(40, num(p.r))
            out.put(100, "AcDbArc"); out.put(50, num(p.a0)); out.put(51, num(p.a1))
        elif t is Ellipse:
            head("ELLIPSE", "AcDbEllipse"); out.point(10, p.c[0], p.c[1], 0.0)
            out.point(11, p.major[0], p.major[1], 0.0); out.put(40, num(p.ratio))
            out.put(41, num(p.t0)); out.put(42, num(p.t1))
        elif t is Spline:
            head("SPLINE", "AcDbSpline"); out.point(210, 0.0, 0.0, 1.0)
            out.put(70, 8); out.put(71, p.degree); out.put(72, len(p.knots)); out.put(73, len(p.poles)); out.put(74, 0)
            for k in p.knots:
                out.put(40, num(k))
            for x, y in p.poles:
                out.point(10, x, y, 0.0)
        elif t is Poly:
            head("LWPOLYLINE", "AcDbPolyline"); out.put(90, len(p.points)); out.put(70, 1 if p.closed else 0)
            for x, y in p.points:
                out.put(10, num(x)); out.put(20, num(y))
    if stamp:
        head("TEXT", "AcDbText", STAMP_LAYER)
        out.point(10, lo[0], lo[1] - 10.0, 0.0); out.put(40, num(4.0)); out.put(1, stamp); out.put(7, "STANDARD")
        out.put(100, "AcDbText")
    out.put(0, "ENDSEC")

    # OBJECTS: the root dictionary and the group dictionary FreeCAD's objects14.rub has
    out.put(0, "SECTION"); out.put(2, "OBJECTS")
    root, groups = handle(), handle()
    out.put(0, "DICTIONARY"); out.put(5, root); out.put(330, 0); out.put(100, "AcDbDictionary")
    out.put(3, "ACAD_GROUP"); out.put(350, groups)
    out.put(0, "DICTIONARY"); out.put(5, groups); out.put(330, root); out.put(100, "AcDbDictionary")
    out.put(0, "ENDSEC")
    out.put(0, "EOF")
    out.lines[seed_at + 1] = f"{h[0] + 1:X}"
    return out.text().encode("ascii", "replace")


# ─── Reading ─────────────────────────────────────────────────────────────────

class NeedsExtra(Exception):
    """A library this path needs is not installed; the message says what to install."""


class Unreadable(Exception):
    """A file that could not be read back as a drawing; the message says why."""


class Drawing(NamedTuple):
    entities: list              # Line, Circle, Arc, Ellipse, Spline and Poly, as the file holds them (not snapped)
    units: int | None           # $INSUNITS
    version: str
    stray: Counter              # entities that are not geometry and not the draft's stamp, by type
    stamped: bool               # the NOT_VERIFIED text of a draft is in it


def ezdxf_module():
    try:
        import ezdxf
    except ImportError:
        raise NeedsExtra('reading a DXF back needs ezdxf, a dependency of cad-agent that is missing here: '
                         'install it with: pip install "ezdxf>=1.4"') from None
    return ezdxf


def read_dxf(data: bytes) -> Drawing:
    """What a DXF holds, by ezdxf: the geometry of its model space as the entities above."""
    ezdxf = ezdxf_module()

    def xy(v) -> tuple:             # a Vec3 or a row of an array: ezdxf hands back either, by entity and by version
        return (float(v[0]), float(v[1]))

    try:
        doc = ezdxf.read(io.StringIO(data.decode("ascii", "replace")))
        units = doc.header.get("$INSUNITS")
        entities, stray, stamped = [], Counter(), False
        for e in doc.modelspace():
            t = e.dxftype()
            if t == "TEXT" and e.dxf.layer == STAMP_LAYER:
                stamped = True
            elif t == "LINE":
                entities.append(Line(*sorted((xy(e.dxf.start), xy(e.dxf.end)))))
            elif t == "CIRCLE":
                entities.append(Circle(xy(e.dxf.center), float(e.dxf.radius)))
            elif t == "ARC":
                entities.append(Arc(xy(e.dxf.center), float(e.dxf.radius), float(e.dxf.start_angle), float(e.dxf.end_angle)))
            elif t == "ELLIPSE":
                entities.append(Ellipse(xy(e.dxf.center), xy(e.dxf.major_axis), float(e.dxf.ratio),
                                        float(e.dxf.start_param), float(e.dxf.end_param)))
            elif t == "SPLINE":
                entities.append(Spline(int(e.dxf.degree), tuple(float(k) for k in e.knots),
                                       tuple(xy(v) for v in e.control_points)))
            elif t == "LWPOLYLINE":
                entities.append(Poly(tuple((float(x), float(y)) for x, y in e.get_points("xy")), bool(e.closed)))
            elif t == "POLYLINE":
                entities.append(Poly(tuple(xy(v.dxf.location) for v in e.vertices), bool(e.is_closed)))
            else:
                stray[t] += 1
        return Drawing(entities, units, doc.acad_release, stray, stamped)
    except NeedsExtra:
        raise
    except Exception as e:          # ezdxf's DXFError family, and whatever a malformed file raises
        raise Unreadable(f"ezdxf cannot read it: {type(e).__name__}: {e}") from None


# ─── Comparing the file with the section ─────────────────────────────────────

def reference(cut: Cut, chord: float = CHORD_MM) -> list:
    """Every edge of the section as a polyline of points on OCCT's own curve (not on this module's entities)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
    out = []
    for _, edges in cut.loops:
        for edge in edges:
            a = BRepAdaptor_Curve(edge.wrapped)
            f, l = a.FirstParameter(), a.LastParameter()
            t = a.GetType()
            if t == GeomAbs_Line:
                n = 2 + int(edge.length // 5.0)
            elif t == GeomAbs_Circle:
                r = a.Circle().Radius()
                step = 2.0 * math.acos(max(0.0, 1.0 - chord / r)) if r > chord else math.pi / 2
                n = max(2, int(math.ceil(abs(l - f) / step)) + 1)
            else:
                n = int(min(6000, max(32, math.ceil(edge.length / 0.05))))
            out.append(np.array([local(cut.frame, a.Value(float(x))) for x in np.linspace(f, l, n)]))
    return out


def max_distance(points: np.ndarray, polylines: list, reach: float = 2.0) -> float:
    """The largest distance from a point of `points` to the nearest segment of `polylines` (inf: farther than `reach`).

    The segments are filed by the 2 mm cells their box, grown by `reach`, covers, and the points are
    measured against the segments of their own cell, so a point has every segment within `reach` of it.
    """
    segs = [pl for pl in polylines if len(pl) > 1]
    if not segs or not len(points):
        return math.inf
    a = np.concatenate([pl[:-1] for pl in segs])
    b = np.concatenate([pl[1:] for pl in segs])
    cell = 2.0
    lo = np.floor((np.minimum(a, b) - reach) / cell).astype(np.int64)
    hi = np.floor((np.maximum(a, b) + reach) / cell).astype(np.int64)
    grid: dict = {}
    for i in range(len(a)):
        for ix in range(lo[i, 0], hi[i, 0] + 1):
            for iy in range(lo[i, 1], hi[i, 1] + 1):
                grid.setdefault((ix, iy), []).append(i)
    cells = np.floor(points / cell).astype(np.int64)
    keys, inverse = np.unique(cells, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    worst = 0.0
    for k, key in enumerate(map(tuple, keys.tolist())):
        near = grid.get(key)
        if not near:
            return math.inf
        p = points[inverse == k]
        sa, sb = a[near], b[near]
        ab = sb - sa
        length2 = (ab ** 2).sum(axis=1)
        ap = p[:, None, :] - sa[None, :, :]
        t = np.clip((ap * ab[None]).sum(axis=2) / np.where(length2 > 0, length2, 1.0), 0.0, 1.0)
        d = np.linalg.norm(p[:, None, :] - (sa[None] + t[..., None] * ab[None]), axis=2).min(axis=1)
        worst = max(worst, float(d.max()))
    return worst


class Compared(NamedTuple):
    problems: list
    held: Counter               # what the file holds, by kind
    deviation: float            # the largest distance either way, mm
    length: float               # the file's cut length, mm


def compare(cut: Cut, prims: list, drawing: Drawing) -> Compared:
    """Hold what the file says to the section it should show (see the module docstring)."""
    problems = []
    if drawing.units != 4:
        problems.append("it does not say millimetres" if drawing.units is None
                        else f"its units are code {drawing.units}, not 4 (millimetres)")
    want = Counter(kind(p) for p in prims)
    held = Counter(kind(p) for p in drawing.entities)
    if want != held:
        problems.append("it was written with " + _count(want) + " but the file holds " + _count(held))
    if drawing.stray:
        problems.append("the file also holds " + _count(drawing.stray) + ", which are not outline")
    ref = reference(cut)
    flat = [flatten(p) for p in drawing.entities]
    deviation, length = math.inf, sum(float(np.hypot(*np.diff(pl, axis=0).T).sum()) for pl in flat if len(pl) > 1)
    if ref and flat:
        deviation = max(max_distance(np.concatenate(ref), flat), max_distance(np.concatenate(flat), ref))
        if deviation > TOL_MM:
            problems.append("the curves are " + ("more than 2 mm" if math.isinf(deviation) else f"{deviation:.4f} mm")
                            + f" from the section's at their worst, over {TOL_MM:g} mm")
    elif ref:
        problems.append("the file holds no outline")
    if abs(length - cut.length) > LENGTH_REL * cut.length + 2 * TOL_MM:
        problems.append(f"the file cuts {length:.3f} mm and the section is {cut.length:.3f} mm round")
    return Compared(problems, held, deviation, length)


def _count(c: Counter) -> str:
    return ", ".join(f"{n} {k.lower()}{'' if n == 1 else 's'}" for k, n in sorted(c.items(), key=lambda kv: KIND_ORDER.get(kv[0], 9))) \
        or "nothing"


# ─── The part rules ──────────────────────────────────────────────────────────

class Prism(NamedTuple):
    state: str
    measured: str
    faces: Faces | None


def through_cut(solid, mid: Cut) -> Prism:
    """Whether the part is a prism of its outline: the faces, then the sections (see the module docstring)."""
    from .geom import volume
    if mid.thickness <= 0 or mid.area <= 0:
        return Prism("UNCHECKED", "the mid-plane cuts no material, so there is no outline to compare the part with", None)
    axis = mid.frame.axis
    name = AXIS_NAME[axis]
    faces = faces_report(solid, axis)
    if faces.bad:
        said = Counter(faces.bad)
        shown = "; ".join((f"{n} x " if n > 1 else "") + text for text, n in list(said.items())[:3])
        more = f"; and {len(said) - 3} other kinds" if len(said) > 3 else ""
        return Prism("FAIL", f"not a through-cut: the part has {shown}{more}. A laser cuts the outline through the "
                             f"whole thickness, nothing else", faces)
    made = ", ".join(f"{n} {k if n == 1 else PLURAL[k]}" for k, n in sorted(faces.counts.items()))
    if not faces.unknown:       # every face is a kind that is exact, so the sections would only repeat what the faces say
        return Prism("PASS", f"a prism along {name}: its faces are {made or 'none'}", faces)
    areas = [mid.area if f == 0.5 else sum(face.area for face in faces_at(solid, axis, f)[1]) for f in LEVELS]
    vol, a = volume(solid), mid.area
    flat = max(abs(areas[0] - a), abs(areas[2] - a)) / a
    prism = abs(vol - a * mid.thickness) / vol if vol > 0 else math.inf
    where = (f"{areas[0]:.2f} mm^2 at 5 %, {a:.2f} at 50 % and {areas[2]:.2f} at 95 % "
             f"of its {mid.thickness:.2f} mm along {name}")
    if flat > PRISM_REL or prism > PRISM_REL:
        return Prism("FAIL", f"not a through-cut: {faces.unknown} faces are B-spline surfaces, which only the sections can "
                             f"judge, and the section is {where}; volume {vol:.2f} mm^3 against area x thickness "
                             f"{a * mid.thickness:.2f}. Something does not go all the way through", faces)
    kinds = (f"its faces are {made}, and {faces.unknown} B-spline faces" if made
             else f"its {faces.unknown} faces are B-spline surfaces")
    return Prism("PASS", f"a prism along {name}: {kinds} judged by the sections alone: {where}; volume {vol:.2f} mm^3 "
                         f"= area x thickness (off by {prism * 100:.3f} %)", faces)


class Laser(NamedTuple):
    rows: list
    dxf: bytes | None
    cut: Cut | None


def laser_rows(name: str, solid, stamp: str | None = None) -> Laser:
    """The rows of a laser-cut part and its DXF: through-cut, and the file read back to the section.

    The bytes are returned even when a row fails, so that `cad shop --draft` has a file to write; they are
    None when none could be made. A `stamp` ("NOT VERIFIED") is written into the file and read back.
    """
    rows = []
    limit_prism = ("a prism of its outline: every face an end plane or running along the thickness (a B-spline face: "
                   f"the same section area at {', '.join(f'{f * 100:g}' for f in LEVELS)} % of it and volume = area x "
                   f"thickness within {PRISM_REL * 100:g} %)")
    limit_file = (f"the file's curves within {TOL_MM:g} mm of the mid-plane section's, both ways, the entities that were "
                  "written, in millimetres")
    source_prism = ("the type and direction of every face of the solid (OCCT's BRepAdaptor_Surface); for a B-spline face, "
                    "its sections at 5 %, 50 % and 95 % of the thinnest axis against its volume")

    def row(rule, state, measured, limit, source):
        rows.append(Row(subject=name, rule=rule, state=state, measured=measured, limit=limit, source=source))

    try:
        mid = cut_at(solid)
    except Exception as e:      # noqa: BLE001 - say so, never pass what could not be made
        why = f"the mid-plane section could not be made: {type(e).__name__}: {e}"
        row("laser through-cut", "UNCHECKED", why, limit_prism, source_prism)
        row("dxf readback", "UNCHECKED", why, limit_file, SOURCE_WRITE)
        return Laser(rows, None, None)
    try:
        verdict = through_cut(solid, mid)
    except Exception as e:      # noqa: BLE001
        verdict = Prism("UNCHECKED", f"the sections could not be made: {type(e).__name__}: {e}", None)
    row("laser through-cut", verdict.state, verdict.measured, limit_prism, source_prism)

    target = mid
    if verdict.state == "PASS":
        try:
            target = end_cut(solid, mid, verdict.faces) or mid
        except Exception:       # noqa: BLE001 - the end face is the better source, not the only one
            target = mid
    try:
        loops = loops_of(target)
        prims = [p for _, ps in loops for p in ps]
        data = write_dxf(target, name, stamp, loops)
    except Unsupported as e:
        row("dxf readback", "UNCHECKED", str(e), limit_file, SOURCE_WRITE)
        return Laser(rows, None, mid)
    except Exception as e:      # noqa: BLE001
        row("dxf readback", "UNCHECKED", f"the DXF could not be written: {type(e).__name__}: {e}", limit_file, SOURCE_WRITE)
        return Laser(rows, None, mid)
    try:
        drawing = read_dxf(data)
    except NeedsExtra as e:
        row("dxf readback", "UNCHECKED", str(e), limit_file, SOURCE_WRITE)
        return Laser(rows, data, target)
    except Unreadable as e:
        row("dxf readback", "FAIL", f"the file does not read back: {e}", limit_file, SOURCE_WRITE)
        return Laser(rows, data, target)
    source = f"{SOURCE_WRITE}; read with ezdxf {ezdxf_module().__version__}"
    try:
        found = compare(mid, prims, drawing)
    except Exception as e:      # noqa: BLE001
        row("dxf readback", "UNCHECKED", f"the file could not be compared: {type(e).__name__}: {e}", limit_file, source)
        return Laser(rows, data, target)
    problems = list(found.problems)
    if bool(stamp) != drawing.stamped:
        problems.append("the draft stamp is missing from the file" if stamp else "the file carries a draft stamp it should not")
    if problems:
        row("dxf readback", "FAIL", "; ".join(problems), limit_file, source)
    else:
        row("dxf readback", "PASS",
            f"{len(drawing.entities)} entities ({_count(found.held)}) from the part's {target.where()}, read back by ezdxf, "
            f"lie within {max(found.deviation, 0.0):.4f} mm of the mid-plane section's {sum(len(e) for _, e in mid.loops)} "
            f"edges, both ways; {found.length:.1f} mm of cut", limit_file, source)
    return Laser(rows, data, target)


def dxf_of(solid, name: str, stamp: str | None = None) -> bytes:
    """The DXF of a solid's outline, for `cad export`: its end face if it is a prism, else its mid-plane section."""
    mid = cut_at(solid)
    target = mid
    try:
        verdict = through_cut(solid, mid)
        if verdict.state == "PASS":
            target = end_cut(solid, mid, verdict.faces) or mid
    except Exception:           # noqa: BLE001 - the section is a file too
        target = mid
    return write_dxf(target, name, stamp)
