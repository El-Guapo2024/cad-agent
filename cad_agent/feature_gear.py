# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It ports FreeCAD's PartDesign Involute Gear and Sprocket and keeps FreeCAD's licence, the GNU
# Lesser General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c:
#     src/Mod/PartDesign/InvoluteGearFeature.py: Copyright (c) 2014 Juergen Riegel (the object, its properties and
#         their defaults, execute)
#     src/Mod/PartDesign/fcgear/involute.py: (c) 2014 David Douard, (c) 2023 Jonas Bähr; based on
#         https://github.com/attoparsec/inkscape-extensions.git and gearUtils-03.js by Dr A.R.Collins (copied below
#         unchanged: CreateExternalGear, CreateInternalGear, _create_involute_profile and their helpers)
#     src/Mod/PartDesign/fcgear/fcgear.py: (c) 2014 David Douard (FCWireBuilder, midpoints)
#     src/Mod/PartDesign/SprocketFeature.py: Adam Spontarelli (the object, SprocketReferenceRollerTable)
#     src/Mod/PartDesign/fcsprocket/sprocket.py, fcsprocket.py: (c) 2020 Adam Spontarelli (CreateSprocket, copied
#         below unchanged, and its wire builder)
#
#   This library is free software; you can redistribute it and/or modify it under the terms of the GNU Library
#   General Public License as published by the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
#   implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Library General Public
#   License for more details.
#
# See ../NOTICE.
"""PartDesign's Involute Gear and Sprocket in a FEATURES list: a closed wire in the Body that a Pad or a Pocket takes
as its profile, as FreeCAD's Python features (Part::Part2DObjectPython) are.

    InvoluteGear("InvoluteGear", number_of_teeth=26, modules=2.5, pressure_angle=20.0),
    Pad("Pad", "InvoluteGear", length=5),
    Sprocket("Sprocket", number_of_teeth=50, pitch=9.525, roller_diameter=5.08),

InvoluteGear's properties (InvoluteGearFeature.py's _ensure_properties, its defaults): number_of_teeth (26), modules
(2.5 mm), pressure_angle (20°), high_precision (True: each flank two Bézier curves of degree 3, else one of degree 4),
external_gear (True), addendum_coefficient (1.0; FreeCAD's command makes an external gear, so 1.0 and not the 0.6 an
internal one would start with), dedendum_coefficient (1.25), root_fillet_coefficient (0.38, what a new gear gets; 0.375
was the old hard-coded value) and profile_shift_coefficient (0.0). Sprocket's (SprocketFeature.py): number_of_teeth
(50), pitch (0.375 in), roller_diameter (0.20 in), thickness (0.11 in, unused by the shape), sprocket_reference
("ANSI 25", the first of the task panel's list; choosing one there sets pitch, roller_diameter and thickness from
SprocketReferenceRollerTable). A length or angle may be a PARAMS name or an expression over them, as everywhere.

Both are Part2DObjects, so they carry AttachExtension's properties (attachment_support, map_mode, attachment_offset,
map_reversed, map_path_parameter, placement), as a datum's are written: FreeCAD's command leaves a gear unattached at
the identity (on the Body's XY plane), and the attachment editor places it like a sketch.

The wire is built from the same curves as fcgear's FCWireBuilder makes (Part.LineSegment, Part.Arc through three points,
Part.BezierCurve), as sketch geometry: a line, an arc of circle, and the Bézier curve as the B-spline it is (one span,
its poles, degree = the number of poles - 1). It is a sketch to the Body (a profile, its EdgeN), so feature.py's Pad,
Pocket, Revolution and every reference to an edge take it as they take a sketch; it is never solved and never checked
for crossing edges (FreeCAD does not check a Part2DObject's wire either).
"""
from __future__ import annotations

from math import acos, asin, atan, atan2, cos, degrees, hypot, pi, radians, sin, sqrt, tan
from math import comb as binom

from . import feature as F
from .feature_attach import ATTACH_DEFAULTS, Attachable, support_list
from .feature_kw import KwFeature

GEAR_KINDS = ("InvoluteGear", "Sprocket")      # a profile of the Body that is not a sketch, and not a solid


# ── src/Mod/PartDesign/fcgear/involute.py, unchanged ────────────────────────────────────────────────────────────────

def CreateExternalGear(
    w, m, Z, phi, split=True, addCoeff=1.0, dedCoeff=1.25, filletCoeff=0.375, shiftCoeff=0.0
):
    """Create an external gear (involute.py)."""
    _create_involute_profile(
        wire_builder=w,
        module=m,
        number_of_teeth=Z,
        pressure_angle=radians(phi),
        split_involute=split,
        outer_height_coefficient=addCoeff,
        inner_height_coefficient=dedCoeff,
        inner_fillet_coefficient=filletCoeff,
        profile_shift_coefficient=shiftCoeff,
    )


def CreateInternalGear(
    w, m, Z, phi, split=True, addCoeff=0.6, dedCoeff=1.25, filletCoeff=0.375, shiftCoeff=0.0
):
    """Create an internal gear (involute.py)."""
    _create_involute_profile(
        wire_builder=w,
        module=m,
        number_of_teeth=Z,
        pressure_angle=radians(phi),
        split_involute=split,
        rotation=pi / Z,  # rotate by half a tooth to align the "inner" tooth with the X-axis
        outer_height_coefficient=dedCoeff,
        inner_height_coefficient=addCoeff,
        outer_fillet_coefficient=filletCoeff,
        profile_shift_coefficient=shiftCoeff,
    )


def _create_involute_profile(
    wire_builder,
    module,
    number_of_teeth,
    pressure_angle=radians(20.0),
    split_involute=True,
    rotation=radians(0),
    outer_height_coefficient=1.0,
    inner_height_coefficient=1.0,
    outer_fillet_coefficient=0.0,
    inner_fillet_coefficient=0.0,
    profile_shift_coefficient=0.0,
):
    """Create an involute gear profile in the given wire builder (involute.py; its comments are there)."""

    profile_shift = profile_shift_coefficient * module
    outer_height = outer_height_coefficient * module + profile_shift  # ext: addendum, int: dedednum
    inner_height = inner_height_coefficient * module - profile_shift  # ext: dedendum, int: addednum

    Rref = number_of_teeth * module / 2  # reference circle radius
    Rb = Rref * cos(pressure_angle)  # base circle radius
    Ro = Rref + outer_height  # radius of outer circle (tip for external, root for internal gears)
    Ri = Rref - inner_height  # radius of inner circle (root for external, tip for internal gears)

    fi = inner_fillet_coefficient * module  # fillet radius at inner circle (ext: root fillet)
    Rci = Ri + fi  # radius at which the center of the inner fillet circle sits
    Rfi = Rci  # radius at which the inner fillet ends (for now assuming some non-involute flank)

    fo = outer_fillet_coefficient * module  # fillet radius at outer circle (int: root fillet)
    Rco = Ro - fo  # radius at which the center of the outer fillet circle sits
    Rfo = Ro  # radius at which the outer fillet ends (for now assuming no outer fillet)

    has_non_involute_flank = Rfi < Rb  # above the base circle we have the involute,
    # below we have a straight line towards the center.
    has_inner_fillet = fi > 0
    has_outer_fillet = fo > 0

    if has_inner_fillet and not has_non_involute_flank:
        q = lambda r: (sqrt(r**2 - Rb**2) / Rb - asin((-(r**2) + fi**2 + Rci**2) / (2 * fi * Rci)))  # noqa: E731
        q_prime = lambda r: (  # noqa: E731
            r / (sqrt(-(Rb**2) + r**2) * Rb)
            + r / (fi * Rci * sqrt(1 - 1 / 4 * (r**2 - fi**2 - Rci**2) ** 2 / (fi**2 * Rci**2)))
        )
        Rfi = findRootNewton(q, q_prime, x_min=max(Rb, Ri), x_max=Rci)

    if has_outer_fillet:
        phi_corr = genInvolutePolar(Rb, Ro) + atan(fo / Ro)
        q = lambda r: (  # noqa: E731
            sqrt(r**2 - Rb**2) / Rb - asin((r**2 - fo**2 - Rco**2) / (2 * fo * Rco)) - phi_corr
        )
        q_prime = lambda r: (  # noqa: E731
            r / (sqrt(-(Rb**2) + r**2) * Rb)
            - r / (fo * Rco * sqrt(1 - 1 / 4 * (r**2 - fo**2 - Rco**2) ** 2 / (fo**2 * Rco**2)))
        )
        Rfo = findRootNewton(q, q_prime, x_min=max(Rb, Rco), x_max=Ro)

    # ****** calculate angles (all in radians)
    angular_pitch = 2 * pi / number_of_teeth  # angle subtended by complete tooth/space pair
    base_to_ref = genInvolutePolar(Rb, Rref)  # angle between base and reference circle
    ref_to_stop = genInvolutePolar(Rb, Rfo) - base_to_ref  # angle between ref and involute end
    if has_non_involute_flank:  # involute starts at base circle
        start_to_ref = base_to_ref
    else:  # involute starts at top of inner fillet, i.e. somewhat above the base circle
        start_to_ref = base_to_ref - genInvolutePolar(Rb, Rfi)

    inner_fillet_width = sqrt(fi**2 - (Rci - Rfi) ** 2)
    inner_fillet_angle = atan(inner_fillet_width / Rfi)
    outer_fillet_width = sqrt(fo**2 - (Rfo - Rco) ** 2)
    outer_fillet_angle = atan(outer_fillet_width / Rfo)

    # ****** generate Higuchi involute approximation
    fe = 1  # fraction of involute length at end of approx
    fs = 0.01  # fraction of length offset from base to avoid singularity
    if not has_non_involute_flank:
        fs = (Rfi**2 - Rb**2) / (Rfo**2 - Rb**2)  # offset start to top of fillet

    if split_involute:
        # approximate in 2 sections, split 25% along the involute
        fm = fs + (fe - fs) / 4  # fraction of length at junction (25% along involute)
        part1 = BezCoeffs(Rb, Rfo, 3, fs, fm)
        part2 = BezCoeffs(Rb, Rfo, 3, fm, fe)
        inv = part1 + part2[1:]  # join the 2 sets of coeffs (skip duplicate mid point)
    else:
        inv = BezCoeffs(Rb, Rfo, 4, fs, fe)

    # ****** calculate angular tooth thickness at reference circle
    enlargement_by_shift = profile_shift * tan(pressure_angle) / Rref
    tooth_thickness_half_angle = angular_pitch / 4 + enlargement_by_shift
    psi = tooth_thickness_half_angle  # for the formulae below, a symbol is more readable

    # rotate all points to make the tooth symmetric to the X axis
    inv = [rotate(pt, -base_to_ref - psi) for pt in inv]

    # create the back profile of tooth (mirror image on X axis)
    invR = [mirror(pt) for pt in inv]

    # ****** calculate section junction points.
    inner_fillet = toCartesian(Rfi, -psi - start_to_ref)  # top of fillet
    inner_fillet_back = mirror(inner_fillet)  # flip to make same point on back of tooth
    inner_circle_back = toCartesian(Ri, psi + start_to_ref + inner_fillet_angle)
    inner_circle_next = toCartesian(Ri, angular_pitch - psi - start_to_ref - inner_fillet_angle)
    inner_fillet_next = rotate(inner_fillet, angular_pitch)  # top of fillet, front of next tooth
    outer_fillet = toCartesian(Ro, -psi + ref_to_stop + outer_fillet_angle)
    outer_circle = mirror(outer_fillet)

    # ****** build the gear profile using the provided wire builder
    thetas = [x * angular_pitch + rotation for x in range(number_of_teeth)]

    if has_inner_fillet:
        wire_builder.move(rotate(inner_fillet_next, thetas[-1]))
    else:
        wire_builder.move(rotate(inner_circle_next, thetas[-1]))

    for theta in thetas:
        wire_builder.theta = theta

        if has_non_involute_flank:
            wire_builder.line(inv[0])  # line from inner fillet up to base circle

        # front involute
        if split_involute:
            wire_builder.curve(inv[1], inv[2], inv[3])
            wire_builder.curve(inv[4], inv[5], inv[6])
        else:
            wire_builder.curve(*inv[1:])

        # is there a section of outer circle between outer fillets?
        if outer_circle[1] > outer_fillet[1]:
            if has_outer_fillet:
                wire_builder.arc(outer_fillet, fo, 1)  # outer fillet
            wire_builder.arc(outer_circle, Ro, 1)  # arc across the outer circle

        if has_outer_fillet:
            wire_builder.arc(invR[-1], fo, 1)  # outer fillet on back side

        # back involute
        if split_involute:
            wire_builder.curve(invR[5], invR[4], invR[3])
            wire_builder.curve(invR[2], invR[1], invR[0])
        else:
            wire_builder.curve(*invR[-2::-1])

        if has_non_involute_flank:
            wire_builder.line(inner_fillet_back)  # line down to top of inner fillet

        # is there a section of inner circle between inner fillets?
        if inner_circle_next[1] > inner_circle_back[1]:
            if has_inner_fillet:
                wire_builder.arc(inner_circle_back, fi, 0)  # inner fillet on back side
            wire_builder.arc(inner_circle_next, Ri, 1)  # arc across the inner circle

        if has_inner_fillet:
            wire_builder.arc(inner_fillet_next, fi, 0)

    wire_builder.close()


def genInvolutePolar(Rb, R):
    """return the involute angle as function of radius R. Rb = base circle radius"""
    return (sqrt(R * R - Rb * Rb) / Rb) - acos(Rb / R)


def rotate(pt, rads):
    """rotate pt by rads radians about origin"""
    sinA = sin(rads)
    cosA = cos(rads)
    return (pt[0] * cosA - pt[1] * sinA, pt[0] * sinA + pt[1] * cosA)


def mirror(pt):
    """mirror pt on the X axis, i.e. flip its Y"""
    return (pt[0], -pt[1])


def toCartesian(radius, angle):
    """convert polar coords to cartesian"""
    return (radius * cos(angle), radius * sin(angle))


def findRootNewton(f, f_prime, x_min, x_max):
    """Apply Newton's Method to find the root of f within x_min and x_max (involute.py)."""
    x = (x_min + x_max) / 2
    PRECISION_INTERSECTION = 1e-9
    for i in range(6):
        f_x = f(x)
        if abs(f_x) < PRECISION_INTERSECTION:
            return x
        x = x - f_x / f_prime(x)
    raise RuntimeError(f"No convergence after {i+1} iterations.")


def chebyExpnCoeffs(j, func):
    N = 50  # a suitably large number  N>>p
    c = 0
    for k in range(1, N + 1):
        c += func(cos(pi * (k - 0.5) / N)) * cos(pi * j * (k - 0.5) / N)
    return 2 * c / N


def chebyPolyCoeffs(p, func):
    coeffs = [0] * (p + 1)
    fnCoeff = []
    T = [coeffs[:] for i in range(p + 1)]
    T[0][0] = 1
    T[1][1] = 1
    for k in range(1, p):
        for j in range(len(T[k]) - 1):
            T[k + 1][j + 1] = 2 * T[k][j]
        for j in range(len(T[k - 1])):
            T[k + 1][j] -= T[k - 1][j]
    for k in range(p + 1):
        fnCoeff.append(chebyExpnCoeffs(k, func))
    for k in range(p + 1):
        for pwr in range(p + 1):
            coeffs[pwr] += fnCoeff[k] * T[k][pwr]
    coeffs[0] -= fnCoeff[0] / 2  # fix the 0th coeff
    return coeffs


def bezCoeff(i, p, polyCoeffs):
    """generate the polynomial coeffs in one go"""
    return sum(binom(i, j) * polyCoeffs[j] / binom(p, j) for j in range(i + 1))


def BezCoeffs(baseRadius, limitRadius, order, fstart, fstop):
    """Approximates an involute using a Bezier-curve (involute.py)."""
    Rb = baseRadius
    Ra = limitRadius
    ta = sqrt(Ra * Ra - Rb * Rb) / Rb  # involute angle at the limit radius
    te = sqrt(fstop) * ta  # involute angle, theta, at end of approx
    ts = sqrt(fstart) * ta  # involute angle, theta, at start of approx
    p = order  # order of Bezier approximation

    def involuteXbez(t):
        x = t * 2 - 1
        theta = x * (te - ts) / 2 + (ts + te) / 2
        return Rb * (cos(theta) + theta * sin(theta))

    def involuteYbez(t):
        x = t * 2 - 1
        theta = x * (te - ts) / 2 + (ts + te) / 2
        return Rb * (sin(theta) - theta * cos(theta))

    bzCoeffs = []
    polyCoeffsX = chebyPolyCoeffs(p, involuteXbez)
    polyCoeffsY = chebyPolyCoeffs(p, involuteYbez)
    for i in range(p + 1):
        bx = bezCoeff(i, p, polyCoeffsX)
        by = bezCoeff(i, p, polyCoeffsY)
        bzCoeffs.append((bx, by))
    return bzCoeffs


# ── src/Mod/PartDesign/fcsprocket/sprocket.py, unchanged ────────────────────────────────────────────────────────────

def CreateSprocket(w, P, N, Dr):
    """Create a sprocket: w the wire builder, P the chain pitch, N the number of teeth, Dr the roller diameter
    (sprocket.py; the remaining variables are the Standard Handbook of Chains')."""
    Ds = 1.005 * Dr + (0.003 * 25.4)
    R = Ds / 2
    M = 0.8 * Dr * cos(radians(35) + radians(60 / N))
    T = 0.8 * Dr * sin(radians(35) + radians(60 / N))
    E = 1.3025 * Dr + (0.0015 * 25.4)
    W = 1.4 * Dr * cos(radians(180 / N))
    V = 1.4 * Dr * sin(radians(180 / N))
    F_ = Dr * (
        0.8 * cos(radians(18) - radians(56) / N) + 1.4 * cos(radians(17) - radians(64) / N) - 1.3025
    ) - (0.0015 * 25.4)
    PD = P / (sin(radians(180) / N))

    # The sprocket tooth gullet consists of four segments
    x0 = 0
    y0 = PD / 2 - R

    # ---- Segment 1 -----
    alpha = 35 + 60 / N
    x1 = -R * cos(radians(alpha))
    y1 = PD / 2 - R * sin(radians(alpha))

    # ---- Segment 2 -----
    alpha = 35 + 60 / N
    beta = 18 - 56 / N
    x2 = M - E * cos(radians(alpha - beta))
    y2 = T - E * sin(radians(alpha - beta)) + PD / 2

    # # ---- Segment 3 -----
    y2o = y2 - PD / 2
    hyp = sqrt((-W - x2) ** 2 + (-V - y2o) ** 2)
    AP = sqrt(hyp**2 - F_**2)
    gamma = atan((y2o + V) / (x2 + W))
    alpha = asin(AP / hyp)
    beta = 180 - (90 - degrees(alpha)) - (90 - degrees(gamma))
    x3o = AP * sin(radians(beta))
    y3o = AP * cos(radians(beta))
    x3 = x2 - x3o
    y3 = y2 + y3o

    # ---- Segment 4 -----
    alpha = 180 / N
    m = -1 / tan(radians(alpha))
    yf = PD / 2 - V
    A = 1 + m**2
    B = 2 * m * yf - 2 * W
    C = W**2 + yf**2 - F_**2
    x4b = (-B + sqrt(B**2 - 4 * A * C)) / (2 * A)
    x4 = -x4b
    y4 = m * x4

    p0 = [x0, y0]
    p1 = [x1, y1]
    p2 = [x2, y2]
    p3 = [x3, y3]
    p4 = [x4, y4]
    p5 = [-x1, y1]
    p6 = [-x2, y2]
    p7 = [-x3, y3]
    p8 = [-x4, y4]

    w.move(p4)  # vectors are lists [x,y]
    w.arc(p3, F_, 0)
    w.line(p2)
    w.arc(p1, E, 1)
    w.arc(p0, R, 1)

    # ---- Mirror -----
    w.arc(p5, R, 1)
    w.arc(p6, E, 1)
    w.line(p7)
    w.arc(p8, F_, 0)

    # ---- Polar Array ----
    alpha = -radians(360 / N)
    for n in range(1, N):
        # falling gullet slope
        w.arc(rotate(p3, alpha * n), F_, 0)
        w.line(rotate(p2, alpha * n))
        w.arc(rotate(p1, alpha * n), E, 1)
        w.arc(rotate(p0, alpha * n), R, 1)

        # rising gullet slope
        w.arc(rotate(p5, alpha * n), R, 1)
        w.line(rotate(p6, alpha * n))
        w.arc(rotate(p7, alpha * n), E, 0)
        w.arc(rotate(p8, alpha * n), F_, 0)

    w.close()

    return w


# ── fcgear.py's FCWireBuilder, making sketch geometry ───────────────────────────────────────────────────────────────

def midpoints(p1, p2, r):
    """fcgear.py: the midpoint of p1 and p2 on each of the two circles of radius r through them."""
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    b = (vx**2 + vy**2) ** 0.5
    v = (vx / b, vy / b)
    cosA = b**2 / (2 * b * r)
    A = acos(cosA)

    vx, vy = rotate(v, A)
    c1 = (p1[0] + r * vx, p1[1] + r * vy)
    m1x, m1y = ((p1[0] + p2[0]) / 2 - c1[0], (p1[1] + p2[1]) / 2 - c1[1])
    dm1 = (m1x**2 + m1y**2) ** 0.5
    m1x, m1y = (c1[0] + r * m1x / dm1, c1[1] + r * m1y / dm1)
    m1 = (m1x, m1y)

    vx, vy = rotate(v, -A)
    c2 = (p1[0] + r * vx, p1[1] + r * vy)
    m2x, m2y = ((p1[0] + p2[0]) / 2 - c2[0], (p1[1] + p2[1]) / 2 - c2[1])
    dm2 = (m2x**2 + m2y**2) ** 0.5
    m2x, m2y = (c2[0] + r * m2x / dm2, c2[1] + r * m2y / dm2)
    m2 = (m2x, m2y)

    return m1, m2


def arc3(p1, p2, p3):
    """Part.Arc(p1, p2, p3): GC_MakeArcOfCircle through three points, kept as FreeCAD makes it (its circle's centre,
    radius, axis and the start of its parameter at p1, which BRepLib_FuseEdges compares before it joins two arcs of a
    refined face), and as an ArcOfCircle for what reads the geometry (counter-clockwise from one end to the other)."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    from OCP.gce import gce_MakeCirc
    from OCP.gp import gp_Pnt
    mk = gce_MakeCirc(gp_Pnt(ax, ay, 0.0), gp_Pnt(bx, by, 0.0), gp_Pnt(cx, cy, 0.0))
    if not mk.IsDone():
        raise F.FeatureError("Part.Arc: the three points are on one line")
    circ = mk.Value()
    ux, uy, r = circ.Location().X(), circ.Location().Y(), circ.Radius()
    a1, a3 = atan2(ay - uy, ax - ux), atan2(cy - uy, cx - ux)
    ccw = (bx - ax) * (cy - by) - (by - ay) * (cx - bx) > 0
    arc = _Arc((ux, uy), r, a1, a3) if ccw else _Arc((ux, uy), r, a3, a1)
    arc.through = (tuple(p1), tuple(p2), tuple(p3))
    return arc


class _Arc(F.ArcOfCircle):
    """An ArcOfCircle whose edge is Part.Arc's (feature._edge asks occ_edge first)."""
    through = None

    def occ_edge(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.GC import GC_MakeArcOfCircle
        from OCP.gp import gp_Pnt
        p1, p2, p3 = (gp_Pnt(x, y, 0.0) for x, y in self.through)
        return BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(p1, p2, p3).Value()).Edge()


class _Bezier(F._curves.BSplineCurve):
    """The B-spline a Bézier curve is, whose edge is Part.BezierCurve's (Geom_BezierCurve)."""

    def occ_edge(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.Geom import Geom_BezierCurve
        from OCP.gp import gp_Pnt
        from .feature_curves import TColgp_Array1OfPnt         # whichever name this OCP build has
        arr = TColgp_Array1OfPnt(1, len(self.poles))
        for i, (x, y) in enumerate(self.poles, 1):
            arr.SetValue(i, gp_Pnt(x, y, 0.0))
        return BRepBuilderAPI_MakeEdge(Geom_BezierCurve(arr)).Edge()


def bezier(poles):
    """Part.BezierCurve with these poles, as the B-spline it is: one span, every pole, degree len(poles) - 1."""
    n = len(poles) - 1
    return _Bezier([tuple(p) for p in poles], [n + 1, n + 1], [0.0, 1.0], degree=n)


class WireBuilder:
    """fcgear.py's FCWireBuilder (and fcsprocket.py's, the same), its curves made sketch geometry."""

    def __init__(self):
        self.pos = None
        self.theta = 0.0
        self.wire = []

    def move(self, p):
        self.pos = (p[0], p[1])

    def line(self, p):
        p = rotate(p, self.theta)
        self.wire.append(F.LineSegment(self.pos, p))
        self.pos = p

    def arc(self, p, r, sweep):
        p = rotate(p, self.theta)
        mid = midpoints(p, self.pos, r)[sweep]
        self.wire.append(arc3(self.pos, mid, p))
        self.pos = p

    def curve(self, *points):
        points = [rotate(p, self.theta) for p in points]
        self.wire.append(bezier([self.pos] + points))
        self.pos = points[-1]

    def close(self):
        pass


# ── the objects ─────────────────────────────────────────────────────────────────────────────────────────────────────

class _Profile2D(F.Sketch):
    """The wire as the Body sees it: a sketch that is never solved and never checked for crossing edges."""
    part2d = True

    def solved(self, params=None):
        return self


class _Gear(KwFeature, Attachable):
    """A Part::Part2DObjectPython of PartDesign's (InvoluteGear, Sprocket): its own properties (PROPS), then
    AttachExtension's. execute() is the wire's geometry."""
    is_part2d = True
    PROPS: dict = {}
    LENGTHS: tuple = ()          # PropertyLength (mm), a PARAMS expression allowed
    ANGLES: tuple = ()           # PropertyAngle (degrees)
    INTS: tuple = ()             # PropertyInteger
    REFS = ("attachment_support",)

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        cls.DEFAULTS = {**cls.PROPS, **ATTACH_DEFAULTS}

    def normalize(self, key, v):
        if key == "attachment_support":
            return tuple(support_list(self.name, v))
        if key in ("map_mode", "attachment_offset", "placement", "map_path_parameter"):
            return v
        return super().normalize(key, v)

    def validate(self):
        self.init_attachment(self.name, list(self.attachment_support), self.map_mode, self.attachment_offset,
                             self.map_reversed, self.map_path_parameter, self.placement)
        self.attachment_support = tuple(self.attachment_support)
        for k in self.LENGTHS + self.ANGLES + self.INTS:
            v = getattr(self, k)
            if isinstance(v, bool) or not isinstance(v, (int, float, str)):
                raise F.FeatureError(f"{self.name}: {k} {v!r} is not a number or a PARAMS expression")
        for k, d in self.PROPS.items():
            if isinstance(d, float) and k not in self.LENGTHS + self.ANGLES:
                try:
                    setattr(self, k, float(getattr(self, k)))
                except (TypeError, ValueError):
                    raise F.FeatureError(f"{self.name}: {k} {getattr(self, k)!r} is not a number") from None

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key in ("attachment_offset", "placement") and isinstance(v, (list, tuple)):
            return tuple(tuple(x) if isinstance(x, (list, tuple)) else x for x in v)
        return super().source_value(key, v)

    def source_props(self) -> list[str]:
        return [k for k in self.DEFAULTS if not self.is_default(k)
                and not (k == "map_mode" and self.map_mode == "Deactivated" and not self.attachment_support)]

    def references(self) -> list[str]:
        from .feature_attach import ORIGIN
        return [n for n in Attachable.references(self) if n not in ORIGIN]

    def num(self, key, params) -> float:
        return F.value(getattr(self, key), params, f"{self.name}.{key}")

    def count(self, key, params) -> int:
        return int(round(self.num(key, params)))

    def geometry(self, params) -> list:
        raise NotImplementedError

    def profile_sketch(self, params) -> F.Sketch:
        """The wire as a sketch of the Body, attached as the object is (AttachExtension's properties)."""
        try:
            geo = self.geometry(params)
        except (ValueError, ZeroDivisionError, RuntimeError) as e:
            raise F.FeatureError(f"{self.name}: {e}") from None
        kw = self.attachment_kwargs()
        if not kw["attachment_support"]:
            kw.update(attachment_support=None, map_mode="Deactivated")
        return _Profile2D(self.name, None, geo, [], **kw)

    # ── freecadcmd ──
    PROXY = ""

    def fc_object(self, ctx):
        raise NotImplementedError

    def to_freecad(self, ctx):
        """makeInvoluteGear / makeSprocket: the Python feature in the active Body's Group (body.Group + [obj]), its
        properties, then its attachment."""
        obj = self.fc_object(ctx)
        ctx.body.Group = ctx.body.Group + [obj]
        for k in self.PROPS:
            prop = self.FC[k]
            v = getattr(self, k)
            if k in self.INTS:
                ctx.setint(obj, prop, v)
            elif k in self.LENGTHS + self.ANGLES:
                ctx.setv(obj, prop, v)
            else:
                setattr(obj, prop, v)
        if self.attachment_support or self.map_mode not in (None, "Deactivated") or self.placement is not None:
            ctx.attach(obj, self)
        return obj


class InvoluteGear(_Gear):
    """InvoluteGearFeature.py's _InvoluteGear: an involute gear's outline."""
    kind = "InvoluteGear"
    TYPE_ID = "Part::InvoluteGear"         # Part::Part2DObjectPython, its Proxy's Type "InvoluteGear"
    TRANSACTION = "Create involute gear"   # CommandInvoluteGear.Activated: openTransaction("Create involute gear")
    PROPS = {"number_of_teeth": 26, "modules": 2.5, "pressure_angle": 20.0, "high_precision": True,
             "external_gear": True, "addendum_coefficient": 1.0, "dedendum_coefficient": 1.25,
             "root_fillet_coefficient": 0.38, "profile_shift_coefficient": 0.0}
    FC = {"number_of_teeth": "NumberOfTeeth", "modules": "Modules", "pressure_angle": "PressureAngle",
          "high_precision": "HighPrecision", "external_gear": "ExternalGear",
          "addendum_coefficient": "AddendumCoefficient", "dedendum_coefficient": "DedendumCoefficient",
          "root_fillet_coefficient": "RootFilletCoefficient", "profile_shift_coefficient": "ProfileShiftCoefficient"}
    LENGTHS = ("modules",)
    ANGLES = ("pressure_angle",)
    INTS = ("number_of_teeth",)

    def geometry(self, params) -> list:
        """_InvoluteGear.execute: CreateExternalGear or CreateInternalGear into the wire builder."""
        w = WireBuilder()
        make = CreateExternalGear if self.external_gear else CreateInternalGear
        make(w, self.num("modules", params), self.count("number_of_teeth", params),
             self.num("pressure_angle", params), split=self.high_precision,
             addCoeff=self.addendum_coefficient, dedCoeff=self.dedendum_coefficient,
             filletCoeff=self.root_fillet_coefficient, shiftCoeff=self.profile_shift_coefficient)
        return w.wire

    def fc_object(self, ctx):
        import InvoluteGearFeature
        obj = ctx.doc.addObject("Part::Part2DObjectPython", self.name)
        InvoluteGearFeature._InvoluteGear(obj)
        return obj


# SprocketFeature.py's Sprocket.SprocketReferenceRollerTable {index: [pitch, roller diameter, thickness] in inches}, with
# the task panel's names for them (SprocketFeature.ui's comboBox_SprocketReference, which the object's enumeration is)
SPROCKET_REFERENCES = [
    ("ANSI 25", 0.250, 0.130, 0.110), ("ANSI 35", 0.375, 0.200, 0.168), ("ANSI 41", 0.500, 0.306, 0.227),
    ("ANSI 40", 0.500, 0.312, 0.284), ("ANSI 50", 0.625, 0.400, 0.343), ("ANSI 60", 0.750, 0.469, 0.459),
    ("ANSI 80", 1.000, 0.625, 0.575), ("ANSI 100", 1.250, 0.750, 0.692), ("ANSI 120", 1.500, 0.875, 0.924),
    ("ANSI 140", 1.750, 1.000, 0.924), ("ANSI 160", 2.000, 1.125, 1.156), ("ANSI 180", 2.250, 1.460, 1.301),
    ("ANSI 200", 2.500, 1.562, 1.389), ("ANSI 240", 3.000, 1.875, 1.738),
    ("Bicycle with derailleur", 0.500, 0.3125, 0.11), ("Bicycle without derailleur", 0.500, 0.3125, 0.084),
    ("ISO 606 06B", 0.375, 6.35 / 25.4, 5.2 / 25.4), ("ISO 606 08B", 0.500, 8.51 / 25.4, 7.0 / 25.4),
    ("ISO 606 10B", 0.625, 10.16 / 25.4, 9.1 / 25.4), ("ISO 606 12B", 0.750, 12.07 / 25.4, 11.1 / 25.4),
    ("ISO 606 16B", 1.000, 15.88 / 25.4, 16.2 / 25.4), ("ISO 606 20B", 1.250, 19.05 / 25.4, 18.5 / 25.4),
    ("ISO 606 24B", 1.500, 25.4 / 25.4, 24.1 / 25.4), ("Motorcycle 420", 0.500, 0.3125, 0.227),
    ("Motorcycle 425", 0.500, 0.3125, 0.284), ("Motorcycle 428", 0.500, 0.335, 0.284),
    ("Motorcycle 520", 0.625, 0.400, 0.227), ("Motorcycle 525", 0.625, 0.400, 0.284),
    ("Motorcycle 530", 0.625, 0.400, 0.343), ("Motorcycle 630", 0.750, 0.400, 0.343),
]
INCH = 25.4


class Sprocket(_Gear):
    """SprocketFeature.py's Sprocket: a roller chain sprocket's outline."""
    kind = "Sprocket"
    TYPE_ID = "Part::Sprocket"             # Part::Part2DObjectPython, its Proxy's Type "Sprocket"
    TRANSACTION = "Create Sprocket"        # CommandSprocket.Activated: openTransaction("Create Sprocket")
    PROPS = {"number_of_teeth": 50, "pitch": 0.375 * INCH, "roller_diameter": 0.20 * INCH,
             "thickness": 0.11 * INCH, "sprocket_reference": "ANSI 25"}
    FC = {"number_of_teeth": "NumberOfTeeth", "pitch": "Pitch", "roller_diameter": "RollerDiameter",
          "thickness": "Thickness", "sprocket_reference": "SprocketReference"}
    LENGTHS = ("pitch", "roller_diameter", "thickness")
    INTS = ("number_of_teeth",)

    def validate(self):
        super().validate()
        names = [r[0] for r in SPROCKET_REFERENCES]
        if self.sprocket_reference not in names:
            raise F.FeatureError(f"{self.name}: sprocket_reference {self.sprocket_reference!r} is not one of "
                                 f"{', '.join(names)}")

    def geometry(self, params) -> list:
        """Sprocket.execute: CreateSprocket(w, Pitch, NumberOfTeeth, RollerDiameter)."""
        w = WireBuilder()
        CreateSprocket(w, self.num("pitch", params), self.count("number_of_teeth", params),
                       self.num("roller_diameter", params))
        return w.wire

    def fc_object(self, ctx):
        import SprocketFeature
        obj = ctx.doc.addObject("Part::Part2DObjectPython", self.name)
        SprocketFeature.Sprocket(obj)       # its __init__ reads the task panel's .ui for the enumeration's names
        return obj


GEARS = {c.kind: c for c in (InvoluteGear, Sprocket)}
F.FEATURES.update(GEARS)                # also when this module is imported before feature.py has finished
F.InvoluteGear, F.Sprocket = InvoluteGear, Sprocket
