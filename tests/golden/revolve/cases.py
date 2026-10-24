"""The bodies tests/test_feature_revolve.py builds with cad_agent.feature and make.py builds in FreeCAD: Revolution and
Groove (cad_agent/feature_revolve.py) with each reference axis form, type, side type and option.

Each case is the same FEATURES list for both: make.py feeds it to FreeCAD through feature.to_freecad, the test builds
it with feature.Body. CASES must match FreeCAD's solid; ERRORS are lists FreeCAD refuses, with the words it refuses
them in. Plain Python and cad_agent.feature only, so FreeCAD's own Python can import it.
"""
import math

from cad_agent.feature import (Circle, Groove, LineSegment, Pad, Revolution, Sketch)

PI = math.pi


def rect(x0, y0, x1, y1, construction=False):
    return [LineSegment((x0, y0), (x1, y0), construction), LineSegment((x1, y0), (x1, y1), construction),
            LineSegment((x1, y1), (x0, y1), construction), LineSegment((x0, y1), (x0, y0), construction)]


def ring():
    """A rectangle 5..15 by 0..10 on XZ: a tube about the sketch's V axis (global Z)."""
    return Sketch("Sketch", "XZ", rect(5, 0, 15, 10))


def tube():
    return [ring(), Revolution("Revolution", "Sketch")]


def plate():
    """The 40 x 20 x 5 plate the grooves cut into."""
    return [Sketch("Base", "XY", rect(0, 0, 40, 20)), Pad("Pad", "Base", length=5.0)]


def block():
    """A block beside the Z axis that a revolution about it runs into: x 10..30, y -30..-10, z 0..10."""
    return [Sketch("Base", "XY", rect(10, -30, 30, -10)), Pad("Pad", "Base", length=10.0)]


CASES = {
    # Revolution, Angle, about the sketch's axes and the Body's
    "rev_full": dict(features=tube()),
    "rev_90": dict(features=[ring(), Revolution("Revolution", "Sketch", angle=90.0)]),
    "rev_90_reversed": dict(features=[ring(), Revolution("Revolution", "Sketch", angle=90.0, reversed=True)]),
    "rev_negative": dict(features=[ring(), Revolution("Revolution", "Sketch", angle=-45.0)]),
    "rev_symmetric": dict(features=[ring(), Revolution("Revolution", "Sketch", angle=120.0, side_type="Symmetric")]),
    "rev_midplane": dict(features=[ring(), Revolution("Revolution", "Sketch", angle=120.0, midplane=True)]),
    "rev_two_sides": dict(features=[ring(), Revolution("Revolution", "Sketch", side_type="Two sides", angle=60.0,
                                                       angle2=30.0)]),
    "rev_two_sides_same_side": dict(features=[ring(), Revolution("Revolution", "Sketch", side_type="Two sides",
                                                                 angle=50.0, angle2=-20.0)]),
    "rev_two_sides_full": dict(features=[ring(), Revolution("Revolution", "Sketch", side_type="Two sides",
                                                            angle=200.0, angle2=170.0)]),
    "rev_two_angles_deprecated": dict(features=[ring(), Revolution("Revolution", "Sketch", type="TwoAngles",
                                                                   angle=60.0, angle2=30.0)]),
    "rev_h_axis": dict(features=[Sketch("Sketch", "XY", rect(0, 5, 10, 15)),
                                 Revolution("Revolution", "Sketch", reference_axis=("Sketch", "H_Axis"), angle=180.0)]),
    "rev_construction_line": dict(features=[Sketch("Sketch", "XZ", rect(5, 0, 15, 10) + [
        LineSegment((20.0, 0.0), (20.0, 10.0), construction=True)]),
        Revolution("Revolution", "Sketch", reference_axis=("Sketch", "Axis0"), angle=90.0)]),
    "rev_second_construction_line": dict(features=[Sketch("Sketch", "XY", [
        LineSegment((-5.0, 0.0), (-5.0, 10.0), construction=True)] + rect(5, 0, 15, 10) + [
        LineSegment((0.0, -3.0), (10.0, -3.0), construction=True)]),
        Revolution("Revolution", "Sketch", reference_axis=("Sketch", "Axis1"), angle=270.0)]),
    # the sketch's normal through its origin: the face turns in its own plane, a solid of no thickness, as FreeCAD makes
    "rev_n_axis": dict(features=[ring(), Revolution("Revolution", "Sketch", reference_axis=("Sketch", "N_Axis"),
                                                    angle=90.0)]),
    "rev_origin_z": dict(features=[ring(), Revolution("Revolution", "Sketch", reference_axis="Z_Axis", angle=90.0)]),
    "rev_origin_x": dict(features=[Sketch("Sketch", "XY", rect(0, 5, 10, 15)),
                                   Revolution("Revolution", "Sketch", reference_axis="X_Axis", angle=90.0)]),
    "rev_origin_y_on_yz": dict(features=[Sketch("Sketch", "YZ", rect(5, 0, 15, 10)),
                                         Revolution("Revolution", "Sketch", reference_axis="Z_Axis", angle=60.0)]),
    "rev_edge_of_profile": dict(features=[Sketch("Sketch", "XZ", rect(0, 0, 10, 10)),
                                          Revolution("Revolution", "Sketch", reference_axis=("Sketch", "Edge4"),
                                                     angle=90.0)]),
    "rev_edge_of_other_sketch": dict(features=[ring(), Sketch("Axis", "XZ", [LineSegment((20.0, 0.0), (20.0, 5.0))]),
                                               Revolution("Revolution", "Sketch", reference_axis=("Axis", "Edge1"),
                                                          angle=90.0)]),
    "rev_edge_of_pad": dict(features=plate() + [Sketch("Sketch", "XZ", rect(5, 6, 15, 12)),
                                                Revolution("Revolution", "Sketch", reference_axis=("Pad", "Edge1"),
                                                           angle=90.0)]),
    "rev_circle": dict(features=[Sketch("Sketch", "XZ", [Circle((20.0, 5.0), 4.0)]),
                                 Revolution("Revolution", "Sketch")]),
    "rev_two_loops": dict(features=[Sketch("Sketch", "XZ", rect(5, 0, 10, 10) + rect(15, 0, 20, 4)),
                                    Revolution("Revolution", "Sketch", angle=180.0)]),
    "rev_on_plate": dict(features=plate() + [Sketch("Sketch", "XZ", rect(10, 0, 20, 12)),
                                             Revolution("Revolution", "Sketch", reference_axis="Z_Axis",
                                                        angle=60.0)]),
    "rev_no_refine": dict(features=plate() + [Sketch("Sketch", "XZ", rect(10, 0, 20, 12)),
                                              Revolution("Revolution", "Sketch", reference_axis="Z_Axis", angle=60.0,
                                                         refine=False)]),
    "rev_start_offset": dict(features=[ring(), Revolution("Revolution", "Sketch", angle=90.0, start_type="Offset",
                                                          start_offset=30.0)]),
    "rev_param_angle": dict(params={"turn": 150.0},
                            features=[ring(), Revolution("Revolution", "Sketch", angle="turn / 2")]),
    "rev_axis_above": dict(features=[ring(), Sketch("Axis", "XY", [LineSegment((-10.0, 30.0), (10.0, 30.0))],
                                                    attachment_offset=(0, 0, 12)),
                           Revolution("Revolution", "Sketch", reference_axis=("Axis", "Edge1"), angle=40.0)]),
    "rev_project_axis": dict(features=[Sketch("Sketch", "XY", rect(0, 5, 10, 15)),
                                       Sketch("Axis", "XY", [LineSegment((-10.0, 0.0), (10.0, 0.0))],
                                              attachment_offset=(0, 0, 7)),
                                       Revolution("Revolution", "Sketch", reference_axis=("Axis", "Edge1"),
                                                  angle=90.0, project_axis=True)]),
    # Revolution, up to a face
    "rev_up_to_first": dict(features=block() + [Sketch("Sketch", "XZ", rect(15, 2, 25, 6)),
                                                Revolution("Revolution", "Sketch", reference_axis="Z_Axis",
                                                           type="UpToFirst")]),
    "rev_up_to_last": dict(features=block() + [Sketch("Sketch", "XZ", rect(15, 2, 25, 6)),
                                               Revolution("Revolution", "Sketch", reference_axis="Z_Axis",
                                                          type="UpToLast")]),
    "rev_up_to_face": dict(features=block() + [Sketch("Sketch", "XZ", rect(15, 2, 25, 6)),
                                               Revolution("Revolution", "Sketch", reference_axis="Z_Axis",
                                                          type="UpToFace", up_to_face=("Pad", "Face3"))]),
    "rev_angle_clamped": dict(features=[ring(), Revolution("Revolution", "Sketch", angle=400.0)]),
    "rev_up_to_plane": dict(features=block() + [Sketch("Sketch", "XZ", rect(15, 2, 25, 6)),
                                                Revolution("Revolution", "Sketch", reference_axis="Z_Axis",
                                                           type="UpToFace", up_to_face="YZ_Plane")]),
    "rev_symmetric_up_to_first": dict(features=block() + [Sketch("Sketch", "XZ", rect(15, 2, 25, 6)),
                                                          Revolution("Revolution", "Sketch", reference_axis="Z_Axis",
                                                                     type="UpToFirst", side_type="Symmetric")]),
    "rev_two_sides_up_to": dict(features=block() + [Sketch("Sketch", "XZ", rect(15, 2, 25, 6)),
                                                    Revolution("Revolution", "Sketch", reference_axis="Z_Axis",
                                                               side_type="Two sides", type="UpToFirst",
                                                               type2="Angle", angle2=30.0)]),
    # Groove
    "groove_full": dict(features=tube() + [Sketch("Notch", "XZ", rect(13, 4, 16, 6)), Groove("Groove", "Notch")]),
    "groove_through_all": dict(features=tube() + [Sketch("Notch", "XZ", rect(13, 4, 16, 6)),
                                                  Groove("Groove", "Notch", type="ThroughAll")]),
    "groove_90": dict(features=tube() + [Sketch("Notch", "XZ", rect(13, 4, 16, 6)),
                                         Groove("Groove", "Notch", angle=90.0)]),
    "groove_90_reversed": dict(features=tube() + [Sketch("Notch", "XZ", rect(13, 4, 16, 6)),
                                                  Groove("Groove", "Notch", angle=90.0, reversed=True)]),
    "groove_symmetric": dict(features=tube() + [Sketch("Notch", "XZ", rect(13, 4, 16, 6)),
                                                Groove("Groove", "Notch", angle=100.0, side_type="Symmetric")]),
    "groove_two_sides": dict(features=tube() + [Sketch("Notch", "XZ", rect(13, 4, 16, 6)),
                                                Groove("Groove", "Notch", side_type="Two sides", angle=40.0,
                                                       angle2=80.0)]),
    "groove_symmetric_through_all": dict(features=tube() + [Sketch("Notch", "XZ", rect(13, 4, 16, 6)),
                                                            Groove("Groove", "Notch", type="ThroughAll",
                                                                   side_type="Symmetric")]),
    "groove_plate_x_axis": dict(features=plate() + [Sketch("Notch", "YZ", rect(2, 3, 18, 7)),
                                                    Groove("Groove", "Notch", reference_axis="Y_Axis", angle=30.0)]),
    "groove_plate_construction": dict(features=plate() + [Sketch("Notch", "XZ", rect(22, 3, 28, 6) + [
        LineSegment((20.0, 6.0), (20.0, 0.0), construction=True)]),
        Groove("Groove", "Notch", reference_axis=("Notch", "Axis0"))]),
    "groove_up_to_first": dict(features=block() + [Sketch("Notch", "XZ", rect(15, 2, 25, 6)),
                                                   Groove("Groove", "Notch", reference_axis="Z_Axis",
                                                          type="UpToFirst")]),
    "groove_up_to_face": dict(features=block() + [Sketch("Notch", "XZ", rect(15, 2, 25, 6)),
                                                  Groove("Groove", "Notch", reference_axis="Z_Axis",
                                                         type="UpToFace", up_to_face=("Pad", "Face3"))]),
    "groove_param": dict(params={"a": 45.0}, features=tube() + [Sketch("Notch", "XZ", rect(13, 4, 16, 6)),
                                                                Groove("Groove", "Notch", angle="a * 2")]),
}

# Lists FreeCAD refuses: make.py records its words (the feature's status string), the test wants the same FeatureError.
ERRORS = {
    "rev_axis_crosses": [Sketch("Sketch", "XZ", rect(-5, 0, 15, 10)), Revolution("Revolution", "Sketch")],
    "rev_up_to_face_out_of_reach": block() + [Sketch("Sketch", "XZ", rect(15, 2, 25, 6)),
                                              Revolution("Revolution", "Sketch", reference_axis="Z_Axis",
                                                         type="UpToFace", up_to_face=("Pad", "Face1"))],
    "groove_axis_crosses": plate() + [Sketch("Notch", "XZ", rect(15, 3, 25, 6) + [
        LineSegment((20.0, 6.0), (20.0, 0.0), construction=True)]),
        Groove("Groove", "Notch", reference_axis=("Notch", "Axis0"))],
    "rev_angle_too_small": [ring(), Revolution("Revolution", "Sketch", angle=0.0)],
    "rev_axis_normal": [ring(), Revolution("Revolution", "Sketch", reference_axis="Y_Axis")],
    "rev_up_to_nothing": [ring(), Revolution("Revolution", "Sketch", type="UpToFirst")],
}
