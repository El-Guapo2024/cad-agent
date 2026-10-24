"""The bodies of conics and B-splines tests/test_feature_curves.py builds with cad_agent.feature and make.py
builds in FreeCAD.

Each case is one FEATURES list for both, as in tests/golden/feature/cases.py. The sketches that carry FreeCAD's
internal geometry carry it as SketchObject::exposeInternalGeometry adds it (SketchObjectGeometry.cpp at
3160daf1e2b6: the same construction lines, points and circles in the same order and direction, with the same
InternalAlignment, Weight and Equal constraints), placed where it is satisfied, so the stored geometry
satisfies every constraint and the build needs no solver. Plain Python and cad_agent.feature only, so
FreeCAD's own Python can import it.
"""
import math

from cad_agent.feature import (ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, BSplineCurve, Circle, Constraint,
                               Ellipse, LineSegment, Pad, Pocket, Point, Sketch)

PI = math.pi


def rect(x0, y0, x1, y1):
    return [LineSegment((x0, y0), (x1, y0)), LineSegment((x1, y0), (x1, y1)),
            LineSegment((x1, y1), (x0, y1)), LineSegment((x0, y1), (x0, y0))]


def rect_constraints(first):
    a, b, c, d = first, first + 1, first + 2, first + 3
    return [Constraint("Coincident", a, 2, b, 1), Constraint("Coincident", b, 2, c, 1),
            Constraint("Coincident", c, 2, d, 1), Constraint("Coincident", d, 2, a, 1),
            Constraint("Horizontal", a), Constraint("Horizontal", c),
            Constraint("Vertical", b), Constraint("Vertical", d)]


def internal(geo, i):
    """exposeInternalGeometry for geometry i of geo: (the construction geometry it adds after the last
    geometry, the constraints that hold it), as SketchObject::exposeInternalGeometryForType makes them."""
    g, s = geo[i], len(geo)
    if isinstance(g, (Ellipse, ArcOfEllipse)):
        a, b = g.major_radius, g.minor_radius
        f1, f2 = g.foci()
        add = [LineSegment(g._off(a, 0), g._off(-a, 0), construction=True),
               LineSegment(g._off(0, b), g._off(0, -b), construction=True),
               Point(f1, construction=True), Point(f2, construction=True)]
        cons = [Constraint("InternalAlignment:EllipseMajorDiameter", s, i),
                Constraint("InternalAlignment:EllipseMinorDiameter", s + 1, i),
                Constraint("InternalAlignment:EllipseFocus1", s + 2, 1, i),
                Constraint("InternalAlignment:EllipseFocus2", s + 3, 1, i)]
        return add, cons
    if isinstance(g, ArcOfHyperbola):
        a, b = g.major_radius, g.minor_radius
        add = [LineSegment(g._off(a, 0), g._off(-a, 0), construction=True),
               LineSegment(g._off(a, b), g._off(a, -b), construction=True),
               Point(g.focus(), construction=True)]
        cons = [Constraint("InternalAlignment:HyperbolaMajor", s, i),
                Constraint("InternalAlignment:HyperbolaMinor", s + 1, i),
                Constraint("InternalAlignment:HyperbolaFocus", s + 2, 1, i)]
        return add, cons
    if isinstance(g, ArcOfParabola):
        add = [Point(g.focus(), construction=True), LineSegment(g.center, g.focus(), construction=True)]
        cons = [Constraint("InternalAlignment:ParabolaFocus", s, 1, i),
                Constraint("InternalAlignment:ParabolaFocalAxis", s + 1, i)]
        return add, cons
    # a B-spline: a circle on each pole (its radius the pole's weight, as the solved sketch has it), the
    # first weight dimensioned when it is 1 and the equal weights made equal to it, then the knot points
    add, cons = [], []
    first_dimensioned = False
    for k, (p, w) in enumerate(zip(g.poles, g.weights)):
        add.append(Circle(p, w, construction=True))
        cons.append(Constraint("InternalAlignment:BSplineControlPoint", s + k, 3, i, k))
        if k == 0:
            if w == 1.0:
                cons.append(Constraint("Weight", s, w))
                first_dimensioned = True
        elif first_dimensioned and w == g.weights[0]:
            cons.append(Constraint("Equal", s + k, s))
    for k, u in enumerate(g.knots):
        add.append(Point(g.value(u), construction=True))
        cons.append(Constraint("InternalAlignment:BSplineKnotPoint", s + len(g.poles) + k, 1, i, k))
    return add, cons


def exposed(geo, cons, which):
    """geo and cons with the internal geometry of each geometry in which."""
    geo, cons = list(geo), list(cons)
    for i in which:
        add, more = internal(geo, i)
        geo += add
        cons += more
    return geo, cons


def closed_by_line(curve, first=0):
    """curve, then the line from its end back to its start, the ends made coincident."""
    p = curve.points()
    geo = [curve, LineSegment(p[2], p[1])]
    return geo, [Constraint("Coincident", first, 2, first + 1, 1), Constraint("Coincident", first + 1, 2, first, 1)]


def sketch(name, geo, cons=(), support="XY", which=(), **kw):
    geo, cons = exposed(geo, cons, which)
    return Sketch(name, support, geo, cons, **kw)


def plate(w=60.0, h=40.0, t=10.0):
    return [Sketch("Sketch", "XY", rect(0, 0, w, h), rect_constraints(0)), Pad("Pad", "Sketch", length=t)]


TILT = (math.cos(0.5), math.sin(0.5))
ELL = Ellipse((5.0, 3.0), 20.0, 10.0, TILT)
ELL_H = Ellipse((0.0, 0.0), 15.0, 6.0)
AOE = ArcOfEllipse((2.0, 1.0), 18.0, 8.0, -1.0, 2.5, TILT)
AOE_UPPER = ArcOfEllipse((0.0, 0.0), 20.0, 9.0, 0.0, PI)
AOH = ArcOfHyperbola((1.0, 2.0), 5.0, 3.0, -1.2, 0.9, TILT)
AOP = ArcOfParabola((1.0, 2.0), 3.0, -6.0, 8.0, (0.0, 1.0))
BS_CLAMPED = BSplineCurve([(0.0, 0.0), (10.0, 12.0), (20.0, 4.0), (30.0, 14.0), (40.0, 0.0)], [4, 1, 4],
                          [0.0, 0.5, 1.0])
BS_RATIONAL = BSplineCurve([(0.0, 0.0), (10.0, 12.0), (20.0, 4.0), (30.0, 14.0), (40.0, 0.0)], [4, 1, 4],
                           [0.0, 0.5, 1.0], weights=[1.5, 2.5, 0.5, 2.0, 1.5])
BS_ONE_WEIGHT_ONE = BSplineCurve([(0.0, 0.0), (10.0, 12.0), (20.0, 4.0), (30.0, 14.0), (40.0, 0.0)], [4, 1, 4],
                                 [0.0, 0.5, 1.0], weights=[2.0, 1.0, 2.0, 2.0, 2.0])
BS_QUAD = BSplineCurve([(0.0, 0.0), (8.0, 10.0), (16.0, -2.0), (24.0, 9.0), (32.0, 0.0)], [3, 1, 1, 3],
                       [0.0, 1.0, 2.0, 3.0], degree=2)
BS_PERIODIC = BSplineCurve([(0.0, 0.0), (10.0, 15.0), (20.0, 3.0), (30.0, 14.0), (25.0, -5.0), (10.0, -8.0)],
                           [1] * 7, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0], periodic=True)
BS_PERIODIC_RATIONAL = BSplineCurve([(0.0, 0.0), (10.0, 15.0), (20.0, 3.0), (30.0, 14.0), (25.0, -5.0),
                                     (10.0, -8.0)], [2, 1, 1, 2, 2], [0.0, 1.0, 2.0, 3.0, 4.0], periodic=True,
                                    weights=[1.0, 2.0, 1.0, 3.0, 1.0, 1.0])
# the lower half of a profile whose upper half is AOE_UPPER: from (-20, 0) to (20, 0) below the axis
BS_LOWER = BSplineCurve([(-20.0, 0.0), (-15.0, -12.0), (0.0, -4.0), (15.0, -12.0), (20.0, 0.0)], [4, 1, 4],
                        [0.0, 0.5, 1.0])


CASES = {
    # a whole ellipse, tilted, without and with its internal geometry
    "pad_ellipse": dict(features=[sketch("Sketch", [ELL]), Pad("Pad", "Sketch", length=8.0)]),
    "pad_ellipse_internal": dict(features=[
        sketch("Sketch", [ELL_H], [Constraint("Coincident", 0, 3, -1, 1)], which=[0]),
        Pad("Pad", "Sketch", length=8.0)]),
    "pad_ellipse_dimensioned": dict(features=[
        sketch("Sketch", [ELL_H], [Constraint("Coincident", 0, 3, -1, 1), Constraint("Horizontal", 1),
                                   Constraint("Distance", 1, 30.0), Constraint("Distance", 2, 12.0)],
               which=[0]),
        Pad("Pad", "Sketch", length=5.0)]),
    "pad_ellipse_xz": dict(features=[sketch("Sketch", [ELL], support="XZ", which=[0]),
                                     Pad("Pad", "Sketch", length=6.0)]),
    "pad_two_ellipses": dict(features=[
        sketch("Sketch", [Ellipse((0.0, 0.0), 10.0, 4.0), Ellipse((30.0, 0.0), 8.0, 5.0, (0.0, 1.0))],
               which=[0, 1]),
        Pad("Pad", "Sketch", length=4.0)]),
    "pad_ellipse_ring": dict(features=[
        sketch("Sketch", [Ellipse((0.0, 0.0), 20.0, 12.0), Ellipse((0.0, 0.0), 12.0, 6.0)], which=[0, 1]),
        Pad("Pad", "Sketch", length=3.0)]),
    "pad_equal_ellipses": dict(features=[
        sketch("Sketch", [Ellipse((0.0, 0.0), 10.0, 4.0), Ellipse((30.0, 5.0), 10.0, 4.0, TILT)],
               [Constraint("Equal", 0, 1)]),
        Pad("Pad", "Sketch", length=4.0)]),
    # an ellipse as a hole in a rectangle, and pocketed through a plate
    "pad_rect_ellipse_hole": dict(features=[
        sketch("Sketch", rect(0, 0, 60, 40) + [Ellipse((30.0, 20.0), 15.0, 8.0, TILT)], rect_constraints(0),
               which=[4]),
        Pad("Pad", "Sketch", length=10.0)]),
    "pocket_ellipse_through_all": dict(features=plate() + [
        sketch("Hole", [Ellipse((30.0, 20.0), 12.0, 7.0, TILT)], which=[0], attachment_offset=(0.0, 0.0, 10.0)),
        Pocket("Pocket", "Hole", type="ThroughAll")]),
    "pocket_ellipse_reversed": dict(features=plate() + [
        sketch("Hole", [Ellipse((30.0, 20.0), 12.0, 7.0)], which=[0]),
        Pocket("Pocket", "Hole", length=4.0, reversed=True)]),
    # conic arcs closed by a line
    "pad_arc_of_ellipse": dict(features=[sketch("Sketch", *closed_by_line(AOE), which=[0]),
                                         Pad("Pad", "Sketch", length=7.0)]),
    "pad_arc_of_ellipse_bare": dict(features=[sketch("Sketch", *closed_by_line(AOE)),
                                              Pad("Pad", "Sketch", length=7.0)]),
    "pad_arc_of_hyperbola": dict(features=[sketch("Sketch", *closed_by_line(AOH), which=[0]),
                                           Pad("Pad", "Sketch", length=5.0)]),
    "pad_arc_of_parabola": dict(features=[sketch("Sketch", *closed_by_line(AOP), which=[0]),
                                          Pad("Pad", "Sketch", length=5.0)]),
    "pad_arc_of_parabola_symmetric": dict(features=[
        sketch("Sketch", *closed_by_line(ArcOfParabola((0.0, 0.0), 2.0, -8.0, 8.0)), which=[0]),
        Pad("Pad", "Sketch", length=6.0, side_type="Symmetric")]),
    "pocket_arc_of_hyperbola": dict(features=plate() + [
        sketch("Cut", *closed_by_line(ArcOfHyperbola((20.0, 20.0), 6.0, 4.0, -1.0, 1.0)), which=[0]),
        Pocket("Pocket", "Cut", length=4.0, reversed=True)]),
    "pocket_arc_of_parabola_xz": dict(features=plate() + [
        Sketch("Cut", "XZ", *closed_by_line(ArcOfParabola((30.0, 2.0), 1.5, -6.0, 6.0, (0.0, 1.0))),
               attachment_offset=(0.0, 0.0, -40.0)),
        Pocket("Pocket", "Cut", type="ThroughAll", reversed=True)]),
    # B-splines: clamped and closed by a line, rational, degree 2, periodic, with their internal geometry
    "pad_bspline_clamped": dict(features=[sketch("Sketch", *closed_by_line(BS_CLAMPED), which=[0]),
                                          Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_clamped_bare": dict(features=[sketch("Sketch", *closed_by_line(BS_CLAMPED)),
                                               Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_rational": dict(features=[sketch("Sketch", *closed_by_line(BS_RATIONAL), which=[0]),
                                           Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_rational_bare": dict(features=[sketch("Sketch", *closed_by_line(BS_RATIONAL)),
                                                Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_one_weight_one": dict(features=[sketch("Sketch", *closed_by_line(BS_ONE_WEIGHT_ONE), which=[0]),
                                                 Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_one_weight_one_bare": dict(features=[sketch("Sketch", *closed_by_line(BS_ONE_WEIGHT_ONE)),
                                                      Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_degree2":dict(features=[sketch("Sketch", *closed_by_line(BS_QUAD), which=[0]),
                                          Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_periodic": dict(features=[sketch("Sketch", [BS_PERIODIC], which=[0]),
                                           Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_periodic_bare": dict(features=[sketch("Sketch", [BS_PERIODIC]),
                                                Pad("Pad", "Sketch", length=6.0)]),
    "pad_bspline_periodic_rational": dict(features=[sketch("Sketch", [BS_PERIODIC_RATIONAL], which=[0]),
                                                    Pad("Pad", "Sketch", length=6.0)]),
    "pocket_bspline_periodic": dict(features=plate() + [
        Sketch("Cut", "XY", [BSplineCurve([(15.0, 10.0), (30.0, 5.0), (45.0, 12.0), (40.0, 30.0), (20.0, 32.0)],
                                          [1] * 6, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], periodic=True)],
               attachment_offset=(0.0, 0.0, 10.0)),
        Pocket("Pocket", "Cut", length=3.0)]),
    # mixes: an arc of ellipse and a B-spline, a rectangle with an ellipse and a B-spline hole
    "pad_ellipse_arc_and_bspline": dict(features=[
        sketch("Sketch", [AOE_UPPER, BS_LOWER], [Constraint("Coincident", 0, 2, 1, 1),
                                                 Constraint("Coincident", 1, 2, 0, 1),
                                                 Constraint("Coincident", 0, 3, -1, 1)], which=[0, 1]),
        Pad("Pad", "Sketch", length=5.0)]),
    "pad_rect_two_holes": dict(features=[
        sketch("Sketch", rect(0, 0, 80, 40) + [Ellipse((20.0, 20.0), 12.0, 6.0, (0.0, 1.0)),
                                               BSplineCurve([(45.0, 10.0), (60.0, 5.0), (72.0, 15.0), (65.0, 32.0),
                                                             (50.0, 30.0)], [1] * 6,
                                                            [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], periodic=True)],
               rect_constraints(0), which=[4, 5]),
        Pad("Pad", "Sketch", length=8.0)]),
}
