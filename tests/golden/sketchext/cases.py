"""The bodies tests/test_sketch_ext.py builds with cad_agent.feature and make.py builds in FreeCAD: sketches whose
external geometry is a face that is not flat (projectShape's hidden-line removal), an intersection with the
sketch's plane (Sketcher_Intersection, alone and with the projection), and projected arcs FreeCAD keeps reversed
(Validate's Swap Endpoints in Constraints), with constraints to them solved.

Plain Python and cad_agent.feature only, so FreeCAD's own Python can import it. The cylinder (r 5, 8 high on XY):
Face1 its side, Face2 its bottom, Face3 its top, Edge3 the top circle. The plate of tests/golden/feature/cases.py
(40 x 20 x 5): Face2 x=40, Edge5 (40,20,0)-(40,20,5). The ball: a half disc on XZ turned about Z, Face1 the sphere; the cone: Face2 its side.
The flipped half disc: Edge3 its arc at z=0, Edge4 at z=-4 (circles about -Z), Face1 the round side.
"""
import math

from cad_agent.feature import (ArcOfCircle, Circle, Constraint, LineSegment, Pad, Revolution,  # noqa: E402
                               Sketch)


def on(name, support, geometry, constraints=(), **kw):
    return Sketch(name, attachment_support=support, geometry=geometry, constraints=list(constraints), **kw)


def xy(name, refs, z=0.0, pitch=0.0, geometry=None, constraints=(), roll=0.0):
    """A sketch on XY lifted to z and tilted about Y by pitch (AttachmentOffset), external geometry of refs."""
    return on(name, [("XY_Plane", "")], geometry or [Circle((30.0, 30.0), 1.0)], constraints,
              attachment_offset=((0.0, 0.0, z), (0.0, pitch, roll)), external_geometry=refs)


def xz(name, refs, y=0.0, geometry=None, constraints=()):
    return on(name, [("XZ_Plane", "")], geometry or [Circle((30.0, 30.0), 1.0)], constraints,
              attachment_offset=((0.0, 0.0, y), (0.0, 0.0, 0.0)), external_geometry=refs)


def cylinder():
    return [Sketch("Sketch", "XY", [Circle((0.0, 0.0), 5.0)], [Constraint("Coincident", 0, 3, -1, 1),
                                                                 Constraint("Radius", 0, 5.0)]),
            Pad("Pad", "Sketch", length=8.0)]


def plate():
    return [Sketch("Sketch", "XY", [LineSegment((0.0, 0.0), (40.0, 0.0)), LineSegment((40.0, 0.0), (40.0, 20.0)),
                                    LineSegment((40.0, 20.0), (0.0, 20.0)), LineSegment((0.0, 20.0), (0.0, 0.0))],
                   [Constraint("Coincident", 0, 2, 1, 1), Constraint("Coincident", 1, 2, 2, 1),
                    Constraint("Coincident", 2, 2, 3, 1), Constraint("Coincident", 3, 2, 0, 1)]),
            Pad("Pad", "Sketch", length=5.0)]


def ball():
    """A sphere of radius 5 about the origin: a half disc on XZ (its arc and the diameter on the Z axis)."""
    hp = round(math.pi / 2, 9)
    return [Sketch("Sketch", "XZ", [ArcOfCircle((0.0, 0.0), 5.0, -hp, hp), LineSegment((0.0, 5.0), (0.0, -5.0))],
                   [Constraint("Coincident", 0, 2, 1, 1), Constraint("Coincident", 1, 2, 0, 1)]),
            Revolution("Revolution", "Sketch", reference_axis=("Sketch", "V_Axis"), angle=360.0)]


def cone():
    """A cone (r 5 at z=0, its tip at z=8): a triangle on XZ turned about Z."""
    return [Sketch("Sketch", "XZ", [LineSegment((0.0, 0.0), (5.0, 0.0)), LineSegment((5.0, 0.0), (0.0, 8.0)),
                                    LineSegment((0.0, 8.0), (0.0, 0.0))],
                   [Constraint("Coincident", 0, 2, 1, 1), Constraint("Coincident", 1, 2, 2, 1),
                    Constraint("Coincident", 2, 2, 0, 1)]),
            Revolution("Revolution", "Sketch", reference_axis=("Sketch", "V_Axis"), angle=360.0)]


def d_flipped():
    """A half disc (r 5) on XY flipped (MapReversed: its normal -Z), padded down: its arc's circle runs about -Z."""
    pi = round(math.pi, 9)
    return [on("Sketch", [("XY_Plane", "")], [ArcOfCircle((0.0, 0.0), 5.0, 0.0, pi), LineSegment((-5.0, 0.0), (5.0, 0.0))],
               [Constraint("Coincident", 0, 1, 1, 2), Constraint("Coincident", 0, 2, 1, 1)], map_mode="FlatFace",
               map_reversed=True),
            Pad("Pad", "Sketch", length=4.0)]


# a line to the projected geometry: its start on GeoId -3's start, its end free (the solver moves the start only)
def _line_to(first=-3, pos=1):
    return [LineSegment((20.0, 20.0), (25.0, 24.0))], [Constraint("Coincident", 0, 1, first, pos)]


CASES = {
    # projectShape: a face that is not flat, seen along the sketch's normal
    "hlr_cylinder_side_xz": {"features": cylinder() + [xz("Sketch001", [("Pad", "Face1")], y=-20.0)]},
    "hlr_cylinder_side_top": {"features": cylinder() + [xy("Sketch001", [("Pad", "Face1")], z=12.0)]},
    "hlr_cylinder_side_tilted": {"features": cylinder() + [xy("Sketch001", [("Pad", "Face1")], z=14.0, pitch=30.0)]},
    "hlr_cylinder_side_constrained": {"features": cylinder() + [
        xz("Sketch001", [("Pad", "Face1")], y=-20.0, geometry=_line_to()[0], constraints=_line_to()[1])]},
    "hlr_ball_top": {"features": ball() + [xy("Sketch001", [("Revolution", "Face1")], z=9.0)]},
    "hlr_ball_tilted": {"features": ball() + [xy("Sketch001", [("Revolution", "Face1")], z=9.0, pitch=40.0)]},
    "hlr_cone_side": {"features": cone() + [xz("Sketch001", [("Revolution", "Face2")], y=-10.0)]},
    "hlr_cone_tilted": {"features": cone() + [xy("Sketch001", [("Revolution", "Face2")], z=12.0, pitch=50.0)]},
    "int_cone_tilted": {"features": cone() + [
        xy("Sketch001", [("Revolution", "Face2", "Intersection")], z=3.0, pitch=20.0)]},
    "int_cone_axial": {"features": cone() + [xz("Sketch001", [("Revolution", "Face2", "Intersection")])]},
    # Sketcher_Intersection: the section with the sketch's plane
    "int_cylinder_side_xz": {"features": cylinder() + [xz("Sketch001", [("Pad", "Face1", "Intersection")])]},
    "int_cylinder_side_mid": {"features": cylinder() + [xy("Sketch001", [("Pad", "Face1", "Intersection")], z=4.0)]},
    "int_cylinder_side_tilted": {"features": cylinder() + [
        xy("Sketch001", [("Pad", "Face1", "Intersection")], z=4.0, pitch=30.0)]},
    "int_cylinder_edge": {"features": cylinder() + [xz("Sketch001", [("Pad", "Edge3", "Intersection")])]},
    "int_plate_face": {"features": plate() + [xy("Sketch001", [("Pad", "Face2", "Intersection")], z=2.0)]},
    "int_plate_edge": {"features": plate() + [xy("Sketch001", [("Pad", "Edge5", "Intersection")], z=2.0)]},
    "int_ball_mid": {"features": ball() + [xy("Sketch001", [("Revolution", "Face1", "Intersection")], z=3.0)]},
    "int_ball_tilted": {"features": ball() + [
        xy("Sketch001", [("Revolution", "Face1", "Intersection")], z=1.0, pitch=35.0)]},
    "int_constrained": {"features": cylinder() + [
        xz("Sketch001", [("Pad", "Face1", "Intersection")], geometry=_line_to()[0], constraints=_line_to()[1])]},
    "both_cylinder_side_xz": {"features": cylinder() + [
        xz("Sketch001", [("Pad", "Face1", "Both"), ("Pad", "Edge3")], y=0.0)]},
    # reversed arcs: the arc of a sketch flipped onto XY, projected onto XY (a circle about -Z), a line to its start
    "reversed_arc": {"features": d_flipped() + [
        xy("Sketch001", [("Pad", "Edge3")], z=6.0, geometry=_line_to()[0], constraints=_line_to()[1])]},
    "reversed_arc_two": {"features": d_flipped() + [
        xy("Sketch001", [("Pad", "Edge4"), ("Pad", "Edge3")], z=6.0, geometry=_line_to(-4, 2)[0],
           constraints=_line_to(-4, 2)[1] + [Constraint("Coincident", 0, 2, -3, 1)])]},
    "reversed_arc_section": {"features": d_flipped() + [
        xy("Sketch001", [("Pad", "Face1", "Intersection")], z=-2.0, geometry=_line_to()[0],
           constraints=_line_to()[1])]},
    # a flipped sketch's own arc as the reference (no solid), as scripts/sketchobjcheck.mjs validates its Sketch004
    "reversed_sketch_edge": {"features": [
        on("Sketch003", [("XY_Plane", "")], [ArcOfCircle((20.0, 30.0), 5.0, 0.0, round(math.pi, 9))],
           map_mode="FlatFace", map_reversed=True),
        xy("Sketch001", [("Sketch003", "Edge1")], z=7.0, geometry=[LineSegment((10.0, 10.0), (14.0, 6.0))],
           constraints=[Constraint("Coincident", 0, 1, -3, 1)])]},
}
