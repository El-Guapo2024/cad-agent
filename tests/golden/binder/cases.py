"""The bodies tests/test_feature_binder.py builds with cad_agent.feature and make.py builds in FreeCAD: a
PartDesign ShapeBinder in a Body.

Each case is the same FEATURES list for both, as tests/golden/feature/cases.py has them. The binder copies its
Support's geometry: a whole Pad, one face, several edges (a compound), a sketch, an Origin plane, line or point;
it can be referenced by a later sketch or by an UpToFace, and its own shape is not the Body's solid. The cases
also hold FreeCAD's filtering: the first Part::Feature in Support is the one copied, and an empty sub-element
means its whole shape, whatever else Support names.
"""
from cad_agent.feature import Constraint, LineSegment, Pad, Pocket, ShapeBinder, Sketch
from cad_agent.feature_attach import DatumLine, DatumPlane, DatumPoint


def rect(x0, y0, x1, y1, construction=False):
    return [LineSegment((x0, y0), (x1, y0), construction), LineSegment((x1, y0), (x1, y1), construction),
            LineSegment((x1, y1), (x0, y1), construction), LineSegment((x0, y1), (x0, y0), construction)]


def rect_constraints(first, w, h):
    a, b, c, d = first, first + 1, first + 2, first + 3
    return [Constraint("Coincident", a, 2, b, 1), Constraint("Coincident", b, 2, c, 1),
            Constraint("Coincident", c, 2, d, 1), Constraint("Coincident", d, 2, a, 1),
            Constraint("Horizontal", a), Constraint("Horizontal", c),
            Constraint("Vertical", b), Constraint("Vertical", d),
            Constraint("DistanceX", a, 1, a, 2, w), Constraint("DistanceY", b, 1, b, 2, h)]


def base_pad(length=5.0):
    """The 40 x 20 plate most cases start from, as tests/golden/feature/cases.py's base_pad."""
    return [Sketch("Sketch", "XY", rect(0, 0, 40, 20), rect_constraints(0, 40.0, 20.0)),
            Pad("Pad", "Sketch", length=length)]


def xz_pad():
    """The plate on the XZ plane: the Pad's and the sketch's Placement are the plane's (a quarter turn about X)."""
    return [Sketch("Sketch", "XZ", rect(0, 0, 40, 20), rect_constraints(0, 40.0, 20.0)),
            Pad("Pad", "Sketch", length=5.0)]


def offset_pad():
    """The plate's sketch moved off the XY plane by its AttachmentOffset: the sketch's Placement is the offset, the
    Pad's the XY plane's (positionByPrevious takes the support's)."""
    return [Sketch("Sketch", "XY", rect(0, 0, 40, 20), rect_constraints(0, 40.0, 20.0),
                   attachment_offset=(3, 4, 7)),
            Pad("Pad", "Sketch", length=5.0)]


CASES = {
    # Support of a whole Pad: the solid, in the Body's coordinates
    "whole_pad": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Pad", "")])]),
    # one face, and two faces: the face, and a compound of them
    "one_face": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Pad", "Face6")])]),
    "two_faces": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Pad", "Face1"), ("Pad", "Face6")])]),
    # edges, at different heights: a compound, its own location identity
    "two_edges": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Pad", "Edge1"), ("Pad", "Edge3")])]),
    # a sketch is a Part::Feature too: its wire, and one of its edges
    "sketch_wire": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Sketch", "")])]),
    "sketch_edge": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Sketch", "Edge1")])]),
    # the Body's origin features: an infinite face, an infinite edge, a vertex
    "origin_plane": dict(features=base_pad() + [ShapeBinder("Binder", support=[("XY_Plane", "")])]),
    "origin_axes": dict(features=base_pad() + [ShapeBinder("Binder", support=[("X_Axis", "")]),
                                               ShapeBinder("Binder001", support=[("Origin", "")])]),
    # no Support: a null shape, and the Body still has Pad's solid
    "empty": dict(features=base_pad() + [ShapeBinder("Binder")]),
    # a binder of a binder: the first one's shape again
    "binder_of_binder": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Pad", "Face6")]),
                                                    ShapeBinder("Binder001", support=[("Binder", "")])]),
    # getFilteredReferences: the first Part::Feature in Support is the one copied, and if its first entry has no
    # sub-element the whole shape is copied, whatever the other entries name
    "first_part_feature": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Sketch", "Edge1"),
                                                                                     ("Pad", "Edge1")])]),
    "whole_before_subs": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Pad", ""),
                                                                                   ("Sketch", "Edge1")])]),
    # TraceSupport: inside one Body (one container) it changes nothing, and the file keeps it
    "trace": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Pad", "Face6")], trace_support=True)]),
    # a sketch attached to a binder's face, and a Pad from it
    "sketch_on_binder": dict(features=base_pad() + [
        ShapeBinder("Binder", support=[("Pad", "Face6")]),
        Sketch("OnBinder", attachment_support=[("Binder", "Face1")], map_mode="FlatFace",
               geometry=rect(5, 5, 15, 15), constraints=rect_constraints(0, 10.0, 10.0)),
        Pad("Pad001", "OnBinder", length=3.0)]),
    # a Pad up to a binder's face, from a sketch below the plate: nothing of the binder is added to the Body
    "pad_up_to_binder": dict(features=base_pad() + [
        ShapeBinder("Binder", support=[("Pad", "Face6")]),
        Sketch("Below", "XY", rect(10, 5, 20, 15), attachment_offset=(0, 0, -4)),
        Pad("Pad001", "Below", type="UpToFace", up_to_face=("Binder", "Face1"))]),
    # a Pocket up to a binder's face: the binder is the plate's underside (z = 0), the cavity cuts down to it
    "pocket_up_to_binder": dict(features=[
        Sketch("Sketch", "XY", rect(0, 0, 40, 20), rect_constraints(0, 40.0, 20.0)),
        Pad("Pad", "Sketch", length=5.0),
        ShapeBinder("Binder", support=[("Pad", "Face5")]),
        Sketch("Cavity", "XY", rect(15, 5, 25, 15), attachment_offset=(0, 0, 5)),
        Pocket("Pocket", "Cavity", type="UpToFace", up_to_face=("Binder", "Face1"))]),
    # a support away from the identity: a whole object's Shape carries the object's Placement, which the binder
    # takes (ShapeBinder::execute: Placement = shape.getTransform()); one element keeps its own location in it
    "xz_whole_pad": dict(features=xz_pad() + [ShapeBinder("Binder", support=[("Pad", "")])]),
    "xz_one_face": dict(features=xz_pad() + [ShapeBinder("Binder", support=[("Pad", "Face6")])]),
    "xz_two_faces": dict(features=xz_pad() + [ShapeBinder("Binder", support=[("Pad", "Face1"), ("Pad", "Face6")])]),
    "xz_sketch_wire": dict(features=xz_pad() + [ShapeBinder("Binder", support=[("Sketch", "")])]),
    "xz_sketch_edge": dict(features=xz_pad() + [ShapeBinder("Binder", support=[("Sketch", "Edge1")])]),
    "xz_binder_of_binder": dict(features=xz_pad() + [ShapeBinder("Binder", support=[("Pad", "")]),
                                                     ShapeBinder("Binder001", support=[("Binder", "")]),
                                                     ShapeBinder("Binder002", support=[("Binder", "Face6")])]),
    "xz_sketch_on_binder": dict(features=xz_pad() + [
        ShapeBinder("Binder", support=[("Pad", "")]),
        Sketch("OnBinder", attachment_support=[("Binder", "Face6")], map_mode="FlatFace",
               geometry=rect(5, 5, 15, 15), constraints=rect_constraints(0, 10.0, 10.0)),
        Pad("Pad001", "OnBinder", length=3.0)]),
    "offset_whole_pad": dict(features=offset_pad() + [ShapeBinder("Binder", support=[("Pad", "")])]),
    "offset_sketch_wire": dict(features=offset_pad() + [ShapeBinder("Binder", support=[("Sketch", "")])]),
    "offset_one_face": dict(features=offset_pad() + [ShapeBinder("Binder", support=[("Pad", "Face6")])]),
    # an App::Line's binder is an edge on gp_Lin(), the Z axis, at the line's Placement: X_Axis's is along Z, Y_Axis's
    # along X; an App::Plane's a face on gp_Pln() at its Placement
    "origin_y_axis_xz_plane": dict(features=base_pad() + [ShapeBinder("Binder", support=[("Y_Axis", "")]),
                                                          ShapeBinder("Binder001", support=[("XZ_Plane", "")])]),
    # Part's datums are App::Plane, App::Line and App::Point, not Part::Feature: getFilteredReferences falls back to
    # them as to an Origin feature, and a Part::Feature named with them is still the one copied
    "part_datums": dict(features=base_pad() + [
        DatumPlane("DatumPlane", attachment_support=[("Pad", "Face6")], map_mode="FlatFace"),
        DatumLine("DatumLine", attachment_support=[("Pad", "Vertex2"), ("Pad", "Vertex4")], map_mode="TwoPointLine"),
        DatumPoint("DatumPoint", attachment_support=[("Pad", "Vertex2")], map_mode="Vertex"),
        ShapeBinder("Binder", support=[("DatumPlane", "")]),
        ShapeBinder("Binder001", support=[("DatumLine", "")]),
        ShapeBinder("Binder002", support=[("DatumPoint", "")]),
        ShapeBinder("Binder003", support=[("DatumPlane", ""), ("Pad", "Face1")])]),
    # a Pad up to a list of shapes naming a binder whole: its faces and the XY plane (getUpToShapeFromLinkSubList)
    "pad_up_to_shape_list": dict(features=base_pad() + [
        ShapeBinder("Binder", support=[("Pad", "Face6")]),
        Sketch("Below", "XY", rect(10, 5, 20, 15), attachment_offset=(0, 0, -4)),
        Pad("Pad001", "Below", type="UpToShape", up_to_shape=["Binder", "XY_Plane"])]),
    # and naming a Part::DatumPlane, an App::Plane: its plane (makeTopoShapeFromPlane), as an origin plane's
    "pad_up_to_shape_list_datum": dict(features=base_pad() + [
        DatumPlane("DatumPlane", attachment_support=[("Pad", "Face6")], map_mode="FlatFace"),
        Sketch("Below", "XY", rect(10, 5, 20, 15), attachment_offset=(0, 0, -4)),
        Pad("Pad001", "Below", type="UpToShape", up_to_shape=["DatumPlane", "XY_Plane"])]),
}
