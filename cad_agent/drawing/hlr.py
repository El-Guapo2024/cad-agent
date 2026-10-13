"""Views by hidden line removal: what TechDraw's `GeometryObject::projectShape` does, and the canonical lines it gives.

TechDraw (FreeCAD commit 3160daf1e2b6, src/Mod/TechDraw/App/GeometryObject.cpp) projects a shape like this:

  1. `DrawViewPart::getProjectionCS` is `gp_Ax2(origin, Direction, XDirection)`: the view direction is the Z of the
     coordinate system and points to the viewer, XDirection is the sheet's horizontal, and Y = Z x X is up
  2. `projectShape` makes an `HLRBRep_Algo`, adds the shape (`Add(shape, isoCount)`), gives it
     `HLRAlgo_Projector(viewAxis)`, and calls `Update()` and `Hide()`
  3. `HLRBRep_HLRToShape` gives ten compounds: for the visible and the hidden side each, the sharp edges
     (`VCompound`, `HCompound`), the smooth ones where two faces meet tangent (`Rg1Line*`), the seams of a closed
     surface (`RgNLine*`), the outlines of curved surfaces (`OutLine*`) and the iso-parametric lines (`IsoLine*`)
  4. `makeTDGeometry` keeps what a view shows: the hard and the outline edges that are visible, always, and the rest as
     the view's properties ask (their defaults are in DrawViewPart.cpp): the visible smooth edges (`SmoothVisible`,
     on by default), the visible seam and iso ones (`SeamVisible`, `IsoVisible`, off), and the hidden hard and outline
     edges only with `HardHidden` (off by default, and it is what makes a drawing's hidden lines), the hidden smooth,
     seam and iso ones with their own (off)

This does the same with the same OCCT classes: the visible lines are `VCompound` and `OutLineVCompound`, the hidden
lines `HCompound` and `OutLineHCompound` (HardHidden on, since a drawing of a plate shows its holes through). Where it
differs from TechDraw, and why:

  smooth edges    TechDraw's defaults draw the visible ones (`Rg1LineVCompound`). Here they are left out: the line where
                  a fillet runs out tangent into a flat is not an edge of the part, and a mechanical drawing usually
                  leaves it out
  centre, scale   TechDraw copies the shape, moves its centroid to the origin and scales it (`ShapeUtils::centerShape`,
                  `scaleShape`) before the projection, and flips y afterwards (`invertGeometry`) for Qt's downward
                  axis. A part is already near its own origin and the sheet's scale is applied to the lines, and
                  a DXF's y is up, so none of the three is done
  coincident      OCCT returns, for a plate seen face on, the edges of the bottom face as hidden lines under the
                  visible ones of the top, and for a hole seen edge-on its circle as a curve that goes along a
                  line and back. A drawing shows a hidden line only where nothing visible is drawn over it, so
                  lines are joined where they lie on one another and the hidden ones are cut where a visible
                  line covers them
  canonical       OCCT 7.9 and 8.0 give the same lines to about 1e-9 mm and in another order and split in other
                  places. Everything is put on a 1e-4 mm grid, joined where it touches, and sorted, so a view
                  is the same entities on either kernel and the same bytes in every run

The result of a projection is a `View`: the entities of `dxf.py` (Line, Circle, Arc, ...) in the view's own x and y, in
millimetres at scale 1:1, and how long OCCT's hidden line removal took.
"""
from __future__ import annotations

import math
import time
from typing import NamedTuple

from .. import dxf

FREECAD_COMMIT = dxf.FREECAD_COMMIT
SOURCE = (f"FreeCAD {FREECAD_COMMIT} src/Mod/TechDraw/App/GeometryObject.cpp GeometryObject::projectShape and makeTDGeometry "
          "(HLRBRep_Algo, HLRAlgo_Projector, HLRBRep_HLRToShape: hard and outline edges, visible solid and hidden dashed)")
GRID = 10_000                   # 1e-4 mm
ANGLE_GRID = 10_000             # 1e-4 degrees
VIEW_FRAME = dxf.frame_at(2, 0.0)       # HLR's edges lie in the XY plane of the projector: the identity frame
VISIBLE = ("VCompound", "OutLineVCompound")
HIDDEN = ("HCompound", "OutLineHCompound")


class View(NamedTuple):
    name: str
    visible: list           # entities in the view's x and y
    hidden: list
    seconds: float          # OCCT's hidden line removal and the conversion of its edges
    box: tuple              # (x0, y0, x1, y1) of the visible lines


# ─── The projection ──────────────────────────────────────────────────────────

def compound_edges(comp) -> list:
    """The edges of an OCCT compound (None or null: none), as build123d Edges."""
    from build123d import Compound
    if comp is None or comp.IsNull():
        return []
    return list(Compound(comp).edges())


def hlr_edges(solid, z_dir, x_dir) -> tuple:
    """(visible edges, hidden edges) of a solid looked at along -z_dir, with x_dir to the right (see the docstring)."""
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    algo = HLRBRep_Algo()
    algo.Add(solid.wrapped, 0)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*z_dir), gp_Dir(*x_dir))))
    algo.Update()
    algo.Hide()
    shapes = HLRBRep_HLRToShape(algo)
    visible = [e for name in VISIBLE for e in compound_edges(getattr(shapes, name)())]
    hidden = [e for name in HIDDEN for e in compound_edges(getattr(shapes, name)())]
    return visible, hidden


def project(solid, name: str, z_dir, x_dir) -> View:
    """One view of a solid: z_dir points at the viewer and x_dir is the sheet's horizontal (TechDraw's Direction and
    XDirection), y_dir = z_dir x x_dir is up."""
    t0 = time.perf_counter()
    visible, hidden = hlr_edges(solid, z_dir, x_dir)
    vis = canonical([e for edge in visible for e in entities(edge)])
    hid = cover(canonical([e for edge in hidden for e in entities(edge)]), vis)
    seconds = time.perf_counter() - t0
    if not vis:
        raise ValueError(f"the {name} view has no visible lines")
    return View(name, vis, hid, seconds, box_of(vis))


def box_of(entities_) -> tuple:
    xs, ys = zip(*(pt for p in entities_ for pt in dxf.extent_points(p)))
    return (min(xs), min(ys), max(xs), max(ys))


# ─── Edges to entities ───────────────────────────────────────────────────────

def entities(edge) -> list:
    """An HLR edge as entities of dxf.py: what FreeCAD's exportShape makes of it, except that a curve that is a
    straight line gone along and back (a circle seen edge on) is the line."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Ellipse, GeomAbs_Line
    a = BRepAdaptor_Curve(edge.wrapped)
    t = a.GetType()
    if t not in (GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse):
        straight = _straight(a)
        if straight is not None:
            return [straight]
    try:
        return [dxf.primitive(edge, VIEW_FRAME)]
    except dxf.Unsupported:
        return []


def _on_line(a, b, q, tol: float = 1e-6) -> bool:
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    return d > 0 and abs((b[0] - a[0]) * (a[1] - q[1]) - (a[0] - q[0]) * (b[1] - a[1])) / d <= tol


def _straight(a):
    """The Line a curve is, if every point of it lies on one, from the furthest two it reaches; else None."""
    f, l = a.FirstParameter(), a.LastParameter()
    pts = [a.Value(f + (l - f) * i / 64.0) for i in range(65)]
    if any(abs(p.Z()) > 1e-6 for p in pts):
        return None
    xy = [(p.X(), p.Y()) for p in pts]
    p0, q0 = max(((p, q) for p in xy for q in xy), key=lambda pq: math.dist(*pq))
    span = math.dist(p0, q0)
    if span < 1e-9 or not all(_on_line(p0, q0, q) for q in xy):
        return None
    return dxf.Line(*sorted((dxf.snap2(p0), dxf.snap2(q0))))


# ─── The same lines, once ────────────────────────────────────────────────────

def _g(x: float) -> int:
    return round(x * GRID)


def _line_key(a, b):
    """((dx, dy), c, t0, t1): the line through two points on the grid as integers, and the span of it they hold."""
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    g = math.gcd(abs(dx), abs(dy))
    dx, dy = dx // g, dy // g
    if dx < 0 or (dx == 0 and dy < 0):
        dx, dy = -dx, -dy
    ta, tb = ax * dx + ay * dy, bx * dx + by * dy
    return (dx, dy, ax * dy - ay * dx), min(ta, tb), max(ta, tb)


def _line_ends(key, t0, t1):
    dx, dy, c = key
    n = dx * dx + dy * dy
    return [((t * dx + c * dy) / n / GRID, (t * dy - c * dx) / n / GRID) for t in (t0, t1)]


def _union(spans) -> list:
    out = []
    for lo, hi in sorted(spans):
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def _minus(spans, covers) -> list:
    out = []
    for lo, hi in spans:
        cur = lo
        for c0, c1 in covers:
            if c1 <= cur or c0 >= hi:
                continue
            if c0 > cur:
                out.append([cur, c0])
            cur = max(cur, c1)
        if cur < hi:
            out.append([cur, hi])
    return out


def _arc_spans(p) -> list:
    """The angular spans (a0, a1) of an arc or circle in grid degrees, a1 > a0, cut at 360 so each stays in [0, 360)."""
    full = 360 * ANGLE_GRID
    if isinstance(p, dxf.Circle):
        return [[0, full]]
    a0 = round(p.a0 * ANGLE_GRID) % full
    sweep = round(((p.a1 - p.a0) % 360.0 or 360.0) * ANGLE_GRID)
    return [[a0, a0 + sweep]] if a0 + sweep <= full else [[a0, full], [0, a0 + sweep - full]]


def _circle_key(p):
    return (_g(p.c[0]), _g(p.c[1]), _g(p.r))


def _arc_from(key, lo: int, hi: int):
    c, r = (key[0] / GRID, key[1] / GRID), key[2] / GRID
    if hi - lo >= 360 * ANGLE_GRID:
        return dxf.Circle(dxf.snap2(c), dxf.snap(r))
    return dxf.Arc(dxf.snap2(c), dxf.snap(r), dxf.angle(lo / ANGLE_GRID), dxf.angle(hi / ANGLE_GRID))


def _join_wrap(spans: list) -> list:
    """Spans of a circle merged, the last one joined to the first when it runs up to 360 and the first starts at 0."""
    spans = _union(spans)
    full = 360 * ANGLE_GRID
    if len(spans) > 1 and spans[0][0] == 0 and spans[-1][1] == full:
        first = spans.pop(0)
        spans[-1] = [spans[-1][0], full + first[1]]
    return spans


def canonical(ents: list) -> list:
    """The entities with every coincident line joined, every arc of one circle joined, on the 1e-4 mm grid, sorted."""
    lines: dict = {}
    arcs: dict = {}
    other = []
    for p in ents:
        if isinstance(p, dxf.Line):
            a, b = (_g(p.a[0]), _g(p.a[1])), (_g(p.b[0]), _g(p.b[1]))
            if a != b:
                key, t0, t1 = _line_key(a, b)
                lines.setdefault(key, []).append([t0, t1])
        elif isinstance(p, (dxf.Circle, dxf.Arc)):
            arcs.setdefault(_circle_key(p), []).extend(_arc_spans(p))
        else:
            other.append(p)
    out = []
    for key, spans in lines.items():
        for lo, hi in _union(spans):
            out.append(dxf.Line(*sorted(dxf.snap2(q) for q in _line_ends(key, lo, hi))))
    for key, spans in arcs.items():
        for lo, hi in _join_wrap(spans):
            out.append(_arc_from(key, lo, hi))
    out += other
    return sorted(out, key=dxf._key)


def cover(hidden: list, visible: list) -> list:
    """The hidden entities with what a visible entity is drawn over cut away."""
    vis_lines: dict = {}
    vis_arcs: dict = {}
    for p in visible:
        if isinstance(p, dxf.Line):
            key, t0, t1 = _line_key((_g(p.a[0]), _g(p.a[1])), (_g(p.b[0]), _g(p.b[1])))
            vis_lines.setdefault(key, []).append([t0, t1])
        elif isinstance(p, (dxf.Circle, dxf.Arc)):
            vis_arcs.setdefault(_circle_key(p), []).extend(_arc_spans(p))
    hid_lines: dict = {}
    hid_arcs: dict = {}
    keep = []
    for p in hidden:
        if isinstance(p, dxf.Line):
            key, t0, t1 = _line_key((_g(p.a[0]), _g(p.a[1])), (_g(p.b[0]), _g(p.b[1])))
            hid_lines.setdefault(key, []).append([t0, t1])
        elif isinstance(p, (dxf.Circle, dxf.Arc)):
            hid_arcs.setdefault(_circle_key(p), []).extend(_arc_spans(p))
        else:
            keep.append(p)
    out = list(keep)
    for key, spans in hid_lines.items():
        for lo, hi in _minus(_union(spans), _union(vis_lines.get(key, []))):
            if hi > lo:
                out.append(dxf.Line(*sorted(dxf.snap2(q) for q in _line_ends(key, lo, hi))))
    for key, spans in hid_arcs.items():
        for lo, hi in _join_wrap(_minus(_union(spans), _union(vis_arcs.get(key, [])))):
            if hi > lo:
                out.append(_arc_from(key, lo, hi))
    return sorted(out, key=dxf._key)
