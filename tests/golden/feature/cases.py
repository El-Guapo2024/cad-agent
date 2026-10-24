"""The bodies tests/test_feature.py builds with cad_agent.feature and make.py builds in FreeCAD.

Each case is the same FEATURES list for both: make.py feeds it to FreeCAD through feature.to_freecad, the
test builds it with feature.Body, and the two must give the same volume, area, bounding box and centre of
mass. Plain Python and cad_agent.feature only, so FreeCAD's own Python can import it.
"""
import math

from cad_agent.feature import (ArcOfCircle, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                               Sketch)

PI = math.pi


def rect(x0, y0, x1, y1, construction=False):
    return [LineSegment((x0, y0), (x1, y0), construction), LineSegment((x1, y0), (x1, y1), construction),
            LineSegment((x1, y1), (x0, y1), construction), LineSegment((x0, y1), (x0, y0), construction)]


def rect_constraints(first, w, h):
    """Sketcher's rectangle tool's constraints, and its two dimensions."""
    a, b, c, d = first, first + 1, first + 2, first + 3
    return [Constraint("Coincident", a, 2, b, 1), Constraint("Coincident", b, 2, c, 1),
            Constraint("Coincident", c, 2, d, 1), Constraint("Coincident", d, 2, a, 1),
            Constraint("Horizontal", a), Constraint("Horizontal", c),
            Constraint("Vertical", b), Constraint("Vertical", d),
            Constraint("DistanceX", a, 1, a, 2, w), Constraint("DistanceY", b, 1, b, 2, h)]


def slot(x0, y0, length, r):
    """A slot along x from (x0, y0), centres length apart: two lines and two half circles."""
    x1 = x0 + length
    return [LineSegment((x1, y0 + r), (x0, y0 + r)), ArcOfCircle((x0, y0), r, PI / 2, 3 * PI / 2),
            LineSegment((x0, y0 - r), (x1, y0 - r)), ArcOfCircle((x1, y0), r, -PI / 2, PI / 2)]


def rounded(x0, y0, x1, y1, r):
    return [LineSegment((x0 + r, y0), (x1 - r, y0)), ArcOfCircle((x1 - r, y0 + r), r, -PI / 2, 0),
            LineSegment((x1, y0 + r), (x1, y1 - r)), ArcOfCircle((x1 - r, y1 - r), r, 0, PI / 2),
            LineSegment((x1 - r, y1), (x0 + r, y1)), ArcOfCircle((x0 + r, y1 - r), r, PI / 2, PI),
            LineSegment((x0, y1 - r), (x0, y0 + r)), ArcOfCircle((x0 + r, y0 + r), r, PI, 3 * PI / 2)]


def base_pad(length=5.0):
    """The 40 x 20 plate most cases start from, its rectangle fully constrained."""
    return [Sketch("Sketch", "XY", rect(0, 0, 40, 20), rect_constraints(0, 40.0, 20.0)),
            Pad("Pad", "Sketch", length=length)]


def step():
    """A plate 40 x 20 x 5 with a 10 x 10 x 2 pocket up into its underside: faces at z = 0, 2 and 5
    along the line through (20, 10)."""
    return base_pad() + [Sketch("Cavity", "XY", rect(15, 5, 25, 15)),
                         Pocket("PocketCavity", "Cavity", length=2.0, reversed=True)]


def two_plates():
    """The plate, and a second one 5 mm above it: two solids, as a Body that allows compounds keeps."""
    return base_pad() + [Sketch("Upper", "XY", rect(0, 0, 40, 20), attachment_offset=(0, 0, 10)),
                         Pad("Pad001", "Upper", length=5.0)]


CASES = {
    # Pad, Length, and its sides
    "pad_rect": dict(features=base_pad()),
    "pad_rect_reversed": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20)),
                                        Pad("Pad", "Sketch", length=5.0, reversed=True)]),
    "pad_rect_negative": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20)),
                                        Pad("Pad", "Sketch", length=-5.0)]),
    "pad_midplane": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20)),
                                   Pad("Pad", "Sketch", length=6.0, midplane=True)]),
    "pad_symmetric": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20)),
                                    Pad("Pad", "Sketch", length=6.0, side_type="Symmetric")]),
    "pad_two_sides": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20)),
                                    Pad("Pad", "Sketch", side_type="Two sides", length=5.0, length2=3.0)]),
    "pad_two_sides_reversed": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20)),
                                             Pad("Pad", "Sketch", side_type="Two sides", length=5.0,
                                                 length2=3.0, reversed=True)]),
    "pad_default_length": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20)),
                                         Pad("Pad", "Sketch")]),
    "pad_params": dict(params={"width": 40.0, "height": 20.0, "thick": 5.0, "half": 2.5},
                       features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20),
                                        rect_constraints(0, "width", "height")),
                                 Pad("Pad", "Sketch", side_type="Two sides", length="thick",
                                     length2="half * 2 - 1")]),
    # profiles: holes, islands, arcs, loops side by side
    "pad_plate_hole": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20) + [Circle((20, 10), 4)]),
                                     Pad("Pad", "Sketch", length=5.0)]),
    "pad_holes_island": dict(features=[
        Sketch("Sketch", "XY", rect(0, 0, 60, 40) + [Circle((10, 10), 3), Circle((50, 30), 3)]
               + rect(20, 10, 40, 30) + [Circle((30, 20), 5)]),
        Pad("Pad", "Sketch", length=4.0)]),
    "pad_two_loops": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 10, 10) + rect(20, 0, 30, 10)),
                                    Pad("Pad", "Sketch", length=3.0)]),
    "pad_slot": dict(features=[Sketch("Sketch", "XY", slot(0, 0, 30, 5)), Pad("Pad", "Sketch", length=4.0)]),
    "pad_rounded_slots": dict(features=[
        Sketch("Sketch", "XY", rounded(0, 0, 50, 30, 6) + slot(10, 10, 15, 2.5) + slot(10, 20, 30, 3)
               + [Point((25, 15)), LineSegment((0, 15), (50, 15), construction=True)]),
        Pad("Pad", "Sketch", length=6.0)]),
    "pad_d_shape": dict(features=[
        Sketch("Sketch", "XY", [LineSegment((0, -10), (0, 10)), ArcOfCircle((0, 0), 10, -PI / 2, PI / 2)],
               [Constraint("Coincident", 0, 2, 1, 2), Constraint("Coincident", 0, 1, 1, 1),
                Constraint("PointOnObject", 1, 3, -1), Constraint("Radius", 1, 10.0),
                Constraint("Vertical", 0)]),
        Pad("Pad", "Sketch", length=7.0)]),
    "pad_angled": dict(features=[
        Sketch("Sketch", "XY", [LineSegment((0, 0), (30, 0)),
                                LineSegment((30, 0), (30 + 20 * math.cos(PI / 3), 20 * math.sin(PI / 3))),
                                LineSegment((30 + 20 * math.cos(PI / 3), 20 * math.sin(PI / 3)), (0, 0))],
               [Constraint("Coincident", 0, 2, 1, 1), Constraint("Coincident", 1, 2, 2, 1),
                Constraint("Coincident", 2, 2, 0, 1), Constraint("Horizontal", 0),
                Constraint("Distance", 1, 20.0), Constraint("Angle", 0, 1, "angle")]),
        Pad("Pad", "Sketch", length=2.0)], params={"angle": 60.0}),
    # sketch planes and attachment offsets
    "pad_xz": dict(features=[Sketch("Sketch", "XZ", rect(0, 0, 40, 20) + [Circle((10, 10), 3)]),
                             Pad("Pad", "Sketch", length=5.0)]),
    "pad_xz_reversed": dict(features=[Sketch("Sketch", "XZ", rect(0, 0, 40, 20)),
                                      Pad("Pad", "Sketch", length=5.0, reversed=True)]),
    "pad_yz": dict(features=[Sketch("Sketch", "YZ", slot(5, 5, 20, 4)), Pad("Pad", "Sketch", length=8.0)]),
    "pad_offset_plane": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 40, 20), attachment_offset=(0, 0, 10)),
                                       Pad("Pad", "Sketch", length=5.0)]),
    "pad_offset_rotated": dict(features=[
        Sketch("Sketch", "XZ", rect(0, 0, 40, 20), attachment_offset=((5, 3, -7), (30, 0, 0))),
        Pad("Pad", "Sketch", length=5.0)]),
    "pad_offset_tilted": dict(features=[
        Sketch("Sketch", "YZ", rect(-10, -5, 10, 5), attachment_offset=((0, 0, 4), (0, 20, 10))),
        Pad("Pad", "Sketch", length=5.0, side_type="Symmetric")]),
    # direction and start
    "pad_custom_direction": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 10, 10)),
                                           Pad("Pad", "Sketch", length=10.0, use_custom_vector=True,
                                               direction=(1, 0, 1))]),
    "pad_custom_direction_along": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 10, 10)),
                                                 Pad("Pad", "Sketch", length=10.0, use_custom_vector=True,
                                                     direction=(1, 0, 1), along_sketch_normal=False)]),
    "pad_start_offset": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 10, 10)),
                                       Pad("Pad", "Sketch", length=4.0, start_type="Offset", start_offset=3.0)]),
    # Pad, up to
    "pad_up_to_first": dict(features=step() + [
        Sketch("Below", "XY", rect(17, 7, 23, 13), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToFirst")]),
    "pad_up_to_last": dict(features=two_plates() + [
        Sketch("Below", "XY", rect(17, 7, 23, 13), attachment_offset=(0, 0, -10)),
        Pad("Pad002", "Below", type="UpToLast")]),
    "pad_up_to_first_gap": dict(features=two_plates() + [
        Sketch("Below", "XY", rect(17, 7, 23, 13), attachment_offset=(0, 0, -10)),
        Pad("Pad002", "Below", type="UpToFirst")]),
    "pad_up_to_last_step": dict(features=step() + [
        Sketch("Below", "XY", rect(17, 7, 23, 13), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToLast")]),
    "pad_up_to_first_wide": dict(features=step() + [
        Sketch("Below", "XY", rect(10, 2, 30, 18), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToFirst")]),
    "pad_up_to_face": dict(features=base_pad() + [
        Sketch("Below", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToFace", up_to_face=("Pad", "Face6"))]),
    "pad_up_to_face_offset": dict(features=base_pad() + [
        Sketch("Below", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToFace", up_to_face=("Pad", "Face6"), offset=2.0)]),
    "pad_up_to_face_larger": dict(features=base_pad() + [
        Sketch("Below", "XY", rect(-5, -5, 50, 30), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToFace", up_to_face=("Pad", "Face5"))]),
    "pad_up_to_plane": dict(features=[Sketch("Sketch", "XY", rect(0, 0, 10, 10), attachment_offset=(0, 0, 8)),
                                      Pad("Pad", "Sketch", type="UpToFace", up_to_face="XY_Plane")]),
    "pad_up_to_shape": dict(features=step() + [
        Sketch("Below", "XY", rect(17, 7, 23, 13), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToShape", up_to_shape=["PocketCavity"])]),
    "pad_up_to_shape_face": dict(features=base_pad() + [
        Sketch("Below", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToShape", up_to_shape=[("Pad", ["Face6"])])]),
    "pad_up_to_shape_base": dict(features=step() + [
        Sketch("Below", "XY", rect(17, 7, 23, 13), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToShape")]),
    "pad_symmetric_up_to_face": dict(features=base_pad() + [
        Sketch("Side", "XZ", rect(5, 1, 15, 4), attachment_offset=(0, 0, -30)),
        Pad("Pad001", "Side", side_type="Symmetric", type="UpToFace", up_to_face=("Pad", "Face1"))]),
    "pad_two_sides_up_to": dict(features=step() + [
        Sketch("Below", "XY", rect(17, 7, 23, 13), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", side_type="Two sides", type="UpToFirst", type2="Length", length2=3.0)]),
    "pad_two_sides_length_up_to": dict(features=base_pad() + [
        Sketch("Below", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", side_type="Two sides", type="Length", length=2.0, type2="UpToFace",
            up_to_face2="XY_Plane")]),
    # Pocket
    "pocket_length": dict(features=base_pad(10.0) + [
        Sketch("Top", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, 10)),
        Pocket("Pocket", "Top", length=4.0)]),
    "pocket_default_length": dict(features=base_pad(10.0) + [
        Sketch("Top", "XY", [Circle((20, 10), 6)], attachment_offset=(0, 0, 10)),
        Pocket("Pocket", "Top")]),
    "pocket_through_all": dict(features=base_pad(10.0) + [
        Sketch("Top", "XY", [Circle((10, 10), 3), Circle((30, 10), 3)] + slot(16, 10, 8, 2),
               attachment_offset=(0, 0, 10)),
        Pocket("Pocket", "Top", type="ThroughAll")]),
    "pocket_through_all_reversed": dict(features=base_pad(10.0) + [
        Sketch("Bottom", "XY", rect(5, 5, 35, 15) + [Circle((20, 10), 2)]),
        Pocket("Pocket", "Bottom", type="ThroughAll", reversed=True)]),
    "pocket_symmetric_through_all": dict(features=base_pad(10.0) + [
        Sketch("Mid", "XZ", [Circle((20, 5), 3)], attachment_offset=(0, 0, -10)),
        Pocket("Pocket", "Mid", type="ThroughAll", side_type="Symmetric")]),
    "pocket_symmetric_length": dict(features=base_pad(10.0) + [
        Sketch("Mid", "XZ", [Circle((20, 5), 3)], attachment_offset=(0, 0, -10)),
        Pocket("Pocket", "Mid", length=8.0, midplane=True)]),
    "pocket_two_sides": dict(features=base_pad(10.0) + [
        Sketch("Mid", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, 5)),
        Pocket("Pocket", "Mid", side_type="Two sides", length=2.0, length2=3.0)]),
    "pocket_two_sides_through": dict(features=base_pad(10.0) + [
        Sketch("Mid", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, 5)),
        Pocket("Pocket", "Mid", side_type="Two sides", type="Length", length=2.0, type2="ThroughAll")]),
    "pocket_up_to_first": dict(features=step() + [
        Sketch("Top", "XY", rect(12, 3, 28, 17), attachment_offset=(0, 0, 5)),
        Pocket("Pocket", "Top", type="UpToFirst")]),
    "pocket_up_to_face_plane": dict(features=base_pad(10.0) + [
        Sketch("Top", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, 10)),
        Pocket("Pocket", "Top", type="UpToFace", up_to_face="XY_Plane", offset=-3.0)]),
    "pocket_up_to_face": dict(features=step() + [
        Sketch("Top", "XY", rect(17, 7, 23, 13), attachment_offset=(0, 0, 5)),
        Pocket("Pocket", "Top", type="UpToFace", up_to_face=("PocketCavity", "Face11"))]),
    "pocket_yz_slot": dict(features=base_pad(10.0) + [
        Sketch("Side", "YZ", slot(4, 5, 12, 2), attachment_offset=(0, 0, 40)),
        Pocket("Pocket", "Side", length=15.0)]),
    "pocket_xz_through": dict(features=base_pad(10.0) + [
        Sketch("Front", "XZ", rounded(5, 2, 35, 8, 2)),
        Pocket("Pocket", "Front", type="ThroughAll")]),
    "pocket_no_refine": dict(features=base_pad(10.0) + [
        Sketch("Top", "XY", rect(0, 0, 20, 20), attachment_offset=(0, 0, 10)),
        Pocket("Pocket", "Top", length=5.0, refine=False)]),
    "pad_pad_refine": dict(features=base_pad(10.0) + [
        Sketch("Top", "XY", rect(0, 0, 20, 20), attachment_offset=(0, 0, 10)),
        Pad("Pad001", "Top", length=5.0)]),
    # BaseFeature: a hand-built solid the features start from
    "base_box_pocket": dict(base=("box", (0, 0, 0), (30, 20, 10)), features=[
        Sketch("Top", "XY", [Circle((15, 10), 4)], attachment_offset=(0, 0, 10)),
        Pocket("Pocket", "Top", type="ThroughAll")]),
    "base_box_pad": dict(base=("box", (-5, -5, 0), (10, 10, 10)), features=[
        Sketch("Sketch", "XY", rect(-10, -10, 10, 10), attachment_offset=(0, 0, -10)),
        Pad("Pad", "Sketch", type="UpToFirst")]),
}
