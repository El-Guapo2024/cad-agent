"""The bodies tests/test_feature_attach.py builds with cad_agent.feature and make_bodies.py builds in FreeCAD:
sketches attached to faces and datums, datum features, and sketches with external geometry.

Plain Python and cad_agent.feature only, so FreeCAD's own Python can import it. The 40 x 20 x 5 plate of
tests/golden/feature/cases.py numbers its elements as FreeCAD does: Face1 y=0, Face2 x=40, Face3 y=20, Face4 x=0,
Face5 z=0, Face6 z=5; Edge4 (0,0,5)-(40,0,5), Edge7 (40,0,5)-(40,20,5), Edge5 (40,20,0)-(40,20,5), Edge10
(40,20,5)-(0,20,5); Vertex1 (0,0,0), Vertex2 (0,0,5), Vertex4 (40,0,5), Vertex6 (40,20,5), Vertex7 (0,20,0). The
cylinder (r 5, 8 high on XY): Face1 its side, Face3 its top, Edge3 the top circle, Vertex1 (5,0,0).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "feature"))

from cases import base_pad, rect, rect_constraints  # noqa: E402

from cad_agent.feature import (Circle, Constraint, DatumLine, DatumPlane, DatumPoint,  # noqa: E402
                               LineSegment, LocalCoordinateSystem, Pad, PartDesignCoordinateSystem,
                               PartDesignLine, PartDesignPlane, PartDesignPoint, Pocket, Sketch)
from cad_agent.feature import AdditiveBox, SubtractiveCylinder  # noqa: E402
from cad_agent.feature import ArcOfCircle, BSplineCurve, Ellipse  # noqa: E402


def on(name, support, geometry, constraints=(), **kw):
    return Sketch(name, attachment_support=support, geometry=geometry, constraints=list(constraints), **kw)


def cylinder():
    return [Sketch("Sketch", "XY", [Circle((0.0, 0.0), 5.0)], [Constraint("Coincident", 0, 3, -1, 1),
                                                                 Constraint("Radius", 0, 5.0)]),
            Pad("Pad", "Sketch", length=8.0)]


def triangle(p0, p1, p2):
    return [LineSegment(p0, p1), LineSegment(p1, p2), LineSegment(p2, p0)]


def padded(geometry, constraints=(), length=5.0):
    """A Body of one sketch on XY padded: the side face(s) first, then the bottom, then the top."""
    return [Sketch("Sketch", "XY", geometry, list(constraints)), Pad("Pad", "Sketch", length=length)]


def d_shape():
    """A half disc (r 5): its arc and its diameter."""
    import math
    return padded([ArcOfCircle((0.0, 0.0), 5.0, 0.0, round(math.pi, 9)), LineSegment((-5.0, 0.0), (5.0, 0.0))],
                  (), 6.0)                       # the ends meet within 2e-9 (the part file writes pi as 3.141592654)


def ring_bspline():
    import math
    poles = [(round(8.0 * math.cos(2 * math.pi * i / 6) + (1.5 if i % 2 else 0.0), 6), round(6.0 * math.sin(2 * math.pi * i / 6), 6))
             for i in range(6)]                     # rounded: the part file writes 9 decimals
    return padded([BSplineCurve(poles, [1] * 7, [float(i) for i in range(7)], periodic=True, degree=3)], length=4.0)


def tilted(name, refs, pitch=30.0, z=14.0):
    """A sketch on XY lifted and tilted about Y (AttachmentOffset), external geometry of refs."""
    return on(name, [("XY_Plane", "")], [Circle((0.0, 0.0), 1.0)], attachment_offset=((0.0, 0.0, z), (0.0, pitch, 0.0)),
              external_geometry=refs)


CASES = {
    # FlatFace on each kind of face of the plate: the sketch's x and y as AttachEngine's legacy orientation
    # picks them from the Pad's Placement, its origin the Pad's origin projected onto the face
    "top_face_pad": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face6")], [Circle((10.0, 10.0), 3.0)]),
        Pad("Pad001", "Sketch001", length=4.0)]},
    "top_face_pocket": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face6")], rect(5, 5, 15, 12), rect_constraints(0, 10.0, 7.0)),
        Pocket("Pocket", "Sketch001", length=2.0)]},
    "front_face_pad": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face1")], [Circle((20.0, 2.5), 2.0)]),
        Pad("Pad001", "Sketch001", length=6.0)]},
    "right_face_pocket": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face2")], rect(5, 1, 15, 4)),
        Pocket("Pocket", "Sketch001", length=10.0)]},
    "bottom_face_pad": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face5")], [Circle((20.0, -10.0), 4.0)]),
        Pad("Pad001", "Sketch001", length=3.0)]},
    "face_offset_flipped": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face6")], rect(0, 0, 6, 3),
           attachment_offset=((4.0, 2.0, -8.0), (30.0, 0.0, 0.0)), map_reversed=True),
        Pad("Pad001", "Sketch001", length=3.0)]},
    "xz_body_face": {"features": [
        Sketch("Sketch", "XZ", rect(0, 0, 30, 10), rect_constraints(0, 30.0, 10.0)),
        Pad("Pad", "Sketch", length=20.0),
        on("Sketch001", [("Pad", "Face6")], [Circle((8.0, 4.0), 3.0)]),
        Pocket("Pocket", "Sketch001", length=5.0),
        on("Sketch002", [("Pad", "Face2")], rect(2, 2, 6, 5)),
        Pad("Pad001", "Sketch002", length=2.0)]},
    "on_pocket_floor": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face6")], rect(5, 5, 25, 15)),
        Pocket("Pocket", "Sketch001", length=3.0),
        on("Sketch002", [("Pocket", "Face11")], [Circle((15.0, 10.0), 2.0)]),
        Pad("Pad001", "Sketch002", length=1.5)]},
    # datum planes, and sketches on them
    "datum_plane_offset": {"features": [
        DatumPlane("DatumPlane", attachment_support=[("XY_Plane", "")], map_mode="FlatFace",
                   attachment_offset=((0.0, 0.0, 12.0), (0.0, 0.0, 0.0))),
        on("Sketch", [("DatumPlane", "")], rect(0, 0, 20, 10), rect_constraints(0, 20.0, 10.0)),
        Pad("Pad", "Sketch", length=5.0),
        on("Sketch001", [("Pad", "Face6")], [Circle((5.0, 5.0), 2.0)]),
        Pocket("Pocket", "Sketch001", length=3.0)]},
    "datum_three_points": {"features": base_pad() + [
        DatumPlane("DatumPlane", attachment_support=[("Pad", "Vertex2"), ("Pad", "Vertex4"), ("Pad", "Vertex7")],
                   map_mode="ThreePointsPlane"),
        on("Sketch001", [("DatumPlane", "")], [Circle((0.0, 0.0), 3.0)]),
        Pocket("Pocket", "Sketch001", type="ThroughAll")]},
    "datum_tangent": {"features": cylinder() + [
        DatumPlane("DatumPlane", attachment_support=[("Pad", "Face1"), ("Pad", "Vertex1")],
                   map_mode="TangentPlane"),
        on("Sketch001", [("DatumPlane", "")], rect(-2, -1, 2, 3)),
        Pad("Pad001", "Sketch001", length=3.0)]},
    "datum_mid_plane": {"features": base_pad() + [
        DatumPlane("DatumPlane", attachment_support=[("Pad", "Face1"), ("Pad", "Face3")], map_mode="MidPlane"),
        on("Sketch001", [("DatumPlane", "")], [Circle((-20.0, 9.0), 2.5)]),
        Pad("Pad001", "Sketch001", length=26.0, side_type="Symmetric")]},
    "datum_unattached": {"features": base_pad() + [
        DatumPlane("DatumPlane", placement=((10.0, 10.0, 2.5), (0.0, 90.0, 0.0))),
        on("Sketch001", [("DatumPlane", "")], [Circle((0.0, 0.0), 1.5)]),
        Pocket("Pocket", "Sketch001", type="ThroughAll", side_type="Symmetric")]},
    "datum_best_fit": {"features": base_pad() + [
        DatumPlane("DatumPlane", attachment_support=[("Pad", "Face2")]),
        on("Sketch001", [("DatumPlane", "")], rect(3, 1, 9, 4)),
        Pad("Pad001", "Sketch001", length=2.0)]},
    # other modes for a sketch
    "normal_to_edge": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Edge4")], [Circle((0.0, 0.0), 2.0)], map_mode="NormalToEdge",
           map_path_parameter=0.5),
        Pad("Pad001", "Sketch001", length=8.0)]},
    "object_xz_on_plane": {"features": base_pad() + [
        on("Sketch001", [("XY_Plane", "")], rect(5, 1, 12, 4), map_mode="ObjectXZ"),
        Pad("Pad001", "Sketch001", length=3.0)]},
    "local_cs_sketch": {"features": base_pad() + [
        LocalCoordinateSystem("LCS", attachment_support=[("Pad", "Vertex6"), ("Pad", "Edge5"), ("Pad", "Edge10")],
                              map_mode="OXY"),
        on("Sketch001", [("LCS", "")], [Circle((-2.5, 10.0), 2.0)], map_mode="ObjectXZ"),
        Pad("Pad001", "Sketch001", length=4.0),
        on("Sketch002", [("LCS", "YZ_Plane")], rect(1, 1, 3, 2)),
        Pad("Pad002", "Sketch002", length=1.0, side_type="Symmetric")]},
    "partdesign_datums": {"features": base_pad() + [
        PartDesignPlane("DatumPlane", attachment_support=[("Pad", "Face6")], map_mode="FlatFace",
                        attachment_offset=((5.0, 0.0, 3.0), (0.0, 0.0, 0.0)), resize_mode="Manual", length=30.0),
        on("Sketch001", [("DatumPlane", "")], [Circle((15.0, 10.0), 2.0)]),
        Pad("Pad001", "Sketch001", length=2.0, reversed=True),
        PartDesignLine("DatumLine", attachment_support=[("Pad", "Edge7")]),
        PartDesignPoint("DatumPoint", attachment_support=[("DatumLine", ""), ("Pad", "Face1")],
                        map_mode="ProximityPoint1"),
        PartDesignCoordinateSystem("Local_CS", attachment_support=[("DatumPoint", "")], map_mode="Translate"),
        on("Sketch002", [("Local_CS", "X")], [Circle((2.0, 2.0), 1.0)]),
        Pocket("Pocket", "Sketch002", type="ThroughAll", side_type="Symmetric")]},
    # datum lines and points: their placements
    "datum_lines_points": {"features": base_pad() + [
        DatumLine("DatumLine", attachment_support=[("Pad", "Vertex1"), ("Pad", "Vertex6")],
                  map_mode="TwoPointLine"),
        DatumLine("DatumLine001", attachment_support=[("Pad", "Face6"), ("Pad", "Face2")],
                  map_mode="IntersectionLine"),
        DatumLine("DatumLine002", attachment_support=[("Pad", "Edge4")]),
        DatumPoint("DatumPoint", attachment_support=[("Pad", "Edge4")], map_mode="OnEdge",
                   map_path_parameter=0.25),
        DatumPoint("DatumPoint001", attachment_support=[("Pad", "Face6")], map_mode="CenterOfMass"),
        DatumPoint("DatumPoint002", attachment_support=[("DatumLine", ""), ("Pad", "Face2")],
                   map_mode="ProximityPoint1"),
        DatumPoint("DatumPoint003", placement=(3.0, 4.0, 5.0)),
        DatumPlane("DatumPlane", attachment_support=[("DatumPoint001", ""), ("DatumLine001", "")],
                   map_mode="ThreePointsPlane"),
        ]},
    # an LCS's elements (its origin's features by role); in a case of its own, see make_bodies.py on App::Line
    "lcs_elements": {"features": base_pad() + [
        LocalCoordinateSystem("LCS", attachment_support=[("Pad", "Face2")], map_mode="FlatFace",
                              attachment_offset=((1.0, 2.0, 3.0), (10.0, 20.0, 30.0))),
        DatumLine("DatumLine", attachment_support=[("LCS", "Y_Axis")], map_mode="TwoPointLine"),
        DatumPoint("DatumPoint", attachment_support=[("LCS", "Origin")]),
        DatumPlane("DatumPlane", attachment_support=[("LCS", "XZ_Plane")])]},
    # a sketch on an LCS's plane picked as FreeCAD's TaskAttacher takes it: the plane object itself
    "lcs_plane_sketch": {"features": [
        LocalCoordinateSystem("LCS", attachment_support=[("XY_Plane", "")], map_mode="FlatFace",
                              attachment_offset=((5.0, 5.0, 2.0), (30.0, 0.0, 0.0))),
        on("Sketch", [("LCS", "XZ_Plane.")], rect(0, 0, 12, 6), map_mode="FlatFace"),
        Pad("Pad", "Sketch", length=4.0),
        on("Sketch001", [("Pad", "Face6")], [Circle((6.0, 3.0), 1.5)]),
        Pocket("Pocket", "Sketch001", type="ThroughAll")]},
    # external geometry: projected, fixed, constrained to, then padded or pocketed
    "external_top_edges": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face6")], triangle((1.0, 1.0), (39.0, 9.0), (39.0, 19.0)), [
            Constraint("Coincident", 0, 2, 1, 1), Constraint("Coincident", 1, 2, 2, 1),
            Constraint("Coincident", 2, 2, 0, 1),
            Constraint("Coincident", 0, 1, -3, 1), Constraint("PointOnObject", 0, 2, -4),
            Constraint("DistanceY", -3, 1, 0, 2, 8.0), Constraint("Coincident", 1, 2, -5, 1)],
           external_geometry=[("Pad", "Edge4"), ("Pad", "Edge7"), ("Pad", "Vertex6")]),
        Pocket("Pocket", "Sketch001", length=2.0)]},
    "external_circle": {"features": cylinder() + [
        on("Sketch001", [("Pad", "Face3")], [Circle((0.5, 0.3), 2.3)],
           [Constraint("Coincident", 0, 3, -3, 3), Constraint("Radius", 0, 2.0)],
           external_geometry=[("Pad", "Edge3")]),
        Pad("Pad001", "Sketch001", length=3.0)]},
    "external_on_xz": {"features": base_pad() + [
        Sketch("Sketch001", "XZ", rect(14.0, 5.5, 24.5, 9.0), rect_constraints(0, 10.0, 4.0) + [
            Constraint("PointOnObject", 0, 1, -3), Constraint("DistanceX", -4, 1, 0, 1, 15.0)],
            external_geometry=[("Pad", "Edge4"), ("Pad", "Vertex1")]),
        Pad("Pad001", "Sketch001", length=3.0)]},
    "external_edge_on_face": {"features": base_pad() + [
        on("Sketch001", [("Pad", "Face6")], rect(30.0, 4.0, 38.0, 12.0), rect_constraints(0, 6.0, 6.0) + [
            Constraint("PointOnObject", 1, 1, -3), Constraint("DistanceY", -3, 1, 0, 1, 4.0)],
           external_geometry=[("Pad", "Face2")]),
        Pocket("Pocket", "Sketch001", length=2.0)]},
    "external_datum_and_origin": {"features": base_pad() + [
        DatumPoint("DatumPoint", attachment_support=[("Pad", "Edge7")], map_mode="OnEdge", map_path_parameter=0.5),
        on("Sketch001", [("Pad", "Face6")], [Circle((30.0, 9.0), 1.0)],
           [Constraint("Coincident", 0, 3, -3, 1), Constraint("Radius", 0, 3.0)],
           external_geometry=[("DatumPoint", ""), ("Y_Axis", "")]),
        Pocket("Pocket", "Sketch001", length=1.0)]},
    # PartDesign primitives attached (FeaturePrimitive's AttachExtension, engine 3D): the shape in the attached frame
    # external geometry of curves the sketch's plane does not hold as they are: a circle at an angle (an ellipse), an
    # ellipse, a B-spline (moved onto a parallel sketch, normal-projected onto a tilted one, a line edge-on)
    "external_oblique_circle": {"features": cylinder() + [tilted("Sketch001", [("Pad", "Edge3")])]},
    "external_oblique_arc": {"features": d_shape() + [tilted("Sketch001", [("Pad", "Face4")], pitch=40.0)]},
    "external_ellipse": {"features": padded([Ellipse((0.0, 0.0), 6.0, 3.0, (0.6, 0.8))]) + [
        tilted("Sketch001", [("Pad", "Edge3")], pitch=35.0),
        on("Sketch002", [("XY_Plane", "")], [Circle((0.0, 0.0), 1.0)], attachment_offset=((1.0, 2.0, 9.0), (15.0, 0.0, 0.0)),
           external_geometry=[("Pad", "Edge3")])]},
    "external_bspline": {"features": ring_bspline() + [
        on("Sketch001", [("XY_Plane", "")], [Circle((0.0, 0.0), 1.0)], attachment_offset=((0.0, 0.0, 10.0), (0.0, 0.0, 0.0)),
           external_geometry=[("Pad", "Edge3")]),
        tilted("Sketch002", [("Pad", "Edge3")], pitch=25.0),
        Sketch("Sketch003", "XZ", [Circle((0.0, 20.0), 1.0)], external_geometry=[("Pad", "Edge3")])]},
    "primitive_on_side_face": {"features": base_pad() + [
        AdditiveBox("Box", length=6.0, width=4.0, height=3.0, attachment_support=[("Pad", "Face2")],
                    map_mode="FlatFace", attachment_offset=((2.0, 1.0, 0.0), (15.0, 0.0, 0.0)))]},
    "primitive_cut_top": {"features": base_pad() + [
        SubtractiveCylinder("Cylinder", radius=3.0, height=4.0, attachment_support=[("Pad", "Face6")],
                            map_mode="FlatFace", attachment_offset=((5.0, 5.0, -4.0), (0.0, 0.0, 0.0)))]},
    "primitive_on_datum": {"features": base_pad() + [
        DatumPlane("DatumPlane", attachment_support=[("Pad", "Edge7")], map_mode="NormalToEdge",
                   map_path_parameter=0.25),
        AdditiveBox("Box", length=2.0, width=2.0, height=2.0, attachment_support=[("DatumPlane", "")],
                    map_mode="ObjectXY", map_reversed=True)]},
}
