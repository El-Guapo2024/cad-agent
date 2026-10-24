"""The bodies tests/test_feature_sweep.py builds with cad_agent.feature and make.py builds in FreeCAD: Additive and
Subtractive Loft, Pipe and Helix (cad_agent/feature_sweep.py) with each option, mode and link form.

Each case is the same FEATURES list for both: make.py feeds it to FreeCAD through feature.to_freecad, the test builds
it with feature.Body. CASES must match FreeCAD's solid; ERRORS are lists FreeCAD refuses, with the words it refuses
them in. Plain Python and cad_agent.feature only, so FreeCAD's own Python can import it.
"""
import math

from cad_agent.feature import (AdditiveHelix, AdditiveLoft, AdditivePipe, ArcOfCircle, Circle, LineSegment, Pad,
                               Point, Sketch, SubtractiveHelix, SubtractiveLoft, SubtractivePipe)

PI = math.pi


def rect(x0, y0, x1, y1, construction=False):
    return [LineSegment((x0, y0), (x1, y0), construction), LineSegment((x1, y0), (x1, y1), construction),
            LineSegment((x1, y1), (x0, y1), construction), LineSegment((x0, y1), (x0, y0), construction)]


def poly(*pts):
    return [LineSegment(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def on_xy(name, geometry, z):
    return Sketch(name, "XY", geometry, attachment_offset=(0.0, 0.0, z))


def square(name, half, z):
    return on_xy(name, rect(-half, -half, half, half), z)


def block():
    """A 40 x 40 x 20 block centred on the Z axis, z 0..20, that the subtractive features cut."""
    return [Sketch("Base", "XY", rect(-20, -20, 20, 20)), Pad("Pad", "Base", length=20.0)]


def cylinder():
    """A cylinder of radius 6 on the Z axis, z 0..30, that a helix threads."""
    return [Sketch("Base", "XY", [Circle((0.0, 0.0), 6.0)]), Pad("Pad", "Base", length=30.0)]


def ring_profile():
    """A rectangle at x 5..7, z 0..2 on XZ: a helix's profile beside the sketch's V axis (global Z)."""
    return Sketch("Sketch", "XZ", rect(5, 0, 7, 2))


def path_sketch(name="Path", plane="XZ"):
    """An L-shaped path on XZ: up the Z axis 0..30, then a quarter arc of radius 20 towards +X, tangent."""
    return Sketch(name, plane, [LineSegment((0.0, 0.0), (0.0, 30.0)),
                                ArcOfCircle((20.0, 30.0), 20.0, PI / 2, PI)])


def corner_path(name="Path"):
    """A path with two sharp corners on XZ (for the transition modes)."""
    return Sketch(name, "XZ", poly((0.0, 0.0), (0.0, 30.0), (20.0, 30.0), (20.0, 50.0)))


def disc(name="Profile", r=3.0, hole=None):
    """A circle (with a hole) on XY at the origin: the profile a pipe sweeps up a path on XZ."""
    g = [Circle((0.0, 0.0), r)] + ([Circle((0.0, 0.0), hole)] if hole else [])
    return Sketch(name, "XY", g)


CASES = {
    # ── Loft ──
    "loft_square_to_square": dict(features=[square("Sketch", 10, 0), square("Sketch001", 5, 20),
                                            AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])]),
    "loft_ruled": dict(features=[square("Sketch", 10, 0), on_xy("Sketch001", rect(-4, -6, 6, 4), 20),
                                 AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"], ruled=True)]),
    "loft_three_sections": dict(features=[square("Sketch", 10, 0), on_xy("Sketch001", [Circle((0.0, 0.0), 6.0)], 15),
                                          square("Sketch002", 4, 30),
                                          AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001", "Sketch002"])]),
    "loft_three_sections_ruled": dict(features=[square("Sketch", 10, 0), square("Sketch001", 6, 15),
                                                square("Sketch002", 8, 30),
                                                AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001", "Sketch002"],
                                                             ruled=True)]),
    "loft_circle_to_circle": dict(features=[on_xy("Sketch", [Circle((0.0, 0.0), 10.0)], 0),
                                            on_xy("Sketch001", [Circle((5.0, 0.0), 4.0)], 25),
                                            AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])]),
    "loft_square_to_circle": dict(features=[square("Sketch", 10, 0), on_xy("Sketch001", [Circle((0.0, 0.0), 6.0)], 20),
                                            AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])]),
    "loft_to_point": dict(features=[square("Sketch", 10, 0), on_xy("Apex", [Point((0.0, 0.0))], 15),
                                    AdditiveLoft("AdditiveLoft", "Sketch", sections=[("Apex", "Vertex1")])]),
    "loft_to_point_whole_sketch": dict(features=[square("Sketch", 10, 0), on_xy("Apex", [Point((2.0, 3.0))], 15),
                                                 AdditiveLoft("AdditiveLoft", "Sketch", sections=["Apex"])]),
    "loft_from_point": dict(features=[on_xy("Apex", [Point((0.0, 0.0))], 0), square("Sketch001", 8, 12),
                                      AdditiveLoft("AdditiveLoft", ("Apex", "Vertex1"), sections=["Sketch001"])]),
    "loft_tube": dict(features=[on_xy("Sketch", rect(-10, -10, 10, 10) + rect(-5, -5, 5, 5), 0),
                                on_xy("Sketch001", [Circle((0.0, 0.0), 9.0), Circle((0.0, 0.0), 3.0)], 20),
                                AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])]),
    "loft_tube_inner_first": dict(features=[on_xy("Sketch", rect(-5, -5, 5, 5) + rect(-10, -10, 10, 10), 0),
                                            on_xy("Sketch001", [Circle((0.0, 0.0), 3.0), Circle((0.0, 0.0), 9.0)], 20),
                                            AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])]),
    "loft_closed": dict(features=[Sketch("Sketch", "XZ", rect(10, 0, 14, 4)),
                                  Sketch("Sketch001", "YZ", rect(10, 0, 13, 3)),
                                  Sketch("Sketch002", "XZ", rect(-14, 0, -10, 4)),
                                  AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001", "Sketch002"],
                                               closed=True)]),
    "loft_closed_one_section_ignored": dict(features=[square("Sketch", 10, 0), square("Sketch001", 5, 20),
                                                      AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"],
                                                                   closed=True)]),
    "loft_on_plate": dict(features=block() + [square("Sketch", 10, 20), on_xy("Sketch001", [Circle((0.0, 0.0), 4.0)], 35),
                                              AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])]),
    "loft_on_plate_no_refine": dict(features=block() + [square("Sketch", 10, 20), square("Sketch001", 4, 35),
                                                        AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"],
                                                                     refine=False)]),
    "loft_tilted_section": dict(features=[square("Sketch", 10, 0),
                                          Sketch("Sketch001", "XZ", rect(-4, 10, 4, 18), attachment_offset=(0.0, 0.0, -10.0)),
                                          AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])]),
    "loft_section_face_of_pad": dict(features=[Sketch("Base", "XY", rect(-5, -5, 5, 5), attachment_offset=(0.0, 0.0, 20.0)),
                                               Pad("Pad", "Base", length=5.0), square("Sketch", 10, 0),
                                               AdditiveLoft("AdditiveLoft", "Sketch", sections=[("Pad", "Face5")])]),
    "subloft_through_block": dict(features=block() + [square("Sketch", 8, -5), square("Sketch001", 3, 25),
                                                      SubtractiveLoft("SubtractiveLoft", "Sketch", sections=["Sketch001"])]),
    "subloft_pocket_to_point": dict(features=block() + [square("Sketch", 8, 20), on_xy("Apex", [Point((0.0, 0.0))], 8),
                                                        SubtractiveLoft("SubtractiveLoft", "Sketch",
                                                                        sections=[("Apex", "Vertex1")])]),
    "subloft_common": dict(features=block() + [square("Sketch", 25, -5), square("Sketch001", 10, 25),
                                               SubtractiveLoft("SubtractiveLoft", "Sketch", sections=["Sketch001"],
                                                               operation="Common")]),
    "subloft_first_in_body": dict(features=[square("Sketch", 10, 0), square("Sketch001", 5, 20),
                                            SubtractiveLoft("SubtractiveLoft", "Sketch", sections=["Sketch001"])]),
    # ── Pipe ──
    "pipe_straight": dict(features=[disc(), Sketch("Path", "XZ", [LineSegment((0.0, 0.0), (0.0, 40.0))]),
                                    AdditivePipe("AdditivePipe", "Profile", spine="Path")]),
    "pipe_l_path": dict(features=[disc(), path_sketch(), AdditivePipe("AdditivePipe", "Profile", spine="Path")]),
    "pipe_tube": dict(features=[disc(hole=1.5), path_sketch(), AdditivePipe("AdditivePipe", "Profile", spine="Path")]),
    "pipe_square_profile": dict(features=[Sketch("Profile", "XY", rect(-2, -2, 2, 2)), path_sketch(),
                                          AdditivePipe("AdditivePipe", "Profile", spine="Path")]),
    "pipe_frenet": dict(features=[Sketch("Profile", "XY", rect(-2, -1, 2, 1)), path_sketch(),
                                  AdditivePipe("AdditivePipe", "Profile", spine="Path", mode="Frenet")]),
    "pipe_fixed": dict(features=[Sketch("Profile", "XY", rect(-2, -1, 2, 1)), path_sketch(),
                                 AdditivePipe("AdditivePipe", "Profile", spine="Path", mode="Fixed")]),
    "pipe_binormal": dict(features=[Sketch("Profile", "XY", rect(-2, -1, 2, 1)), path_sketch(),
                                    AdditivePipe("AdditivePipe", "Profile", spine="Path", mode="Binormal",
                                                 binormal=(0.0, 1.0, 0.0))]),
    "pipe_auxiliary": dict(features=[Sketch("Profile", "XY", rect(-2, -1, 2, 1)), path_sketch(),
                                     Sketch("Aux", "XZ", [LineSegment((10.0, 0.0), (10.0, 30.0)),
                                                          ArcOfCircle((20.0, 30.0), 10.0, PI / 2, PI)]),
                                     AdditivePipe("AdditivePipe", "Profile", spine="Path", mode="Auxiliary",
                                                  auxiliary_spine="Aux")]),
    "pipe_auxiliary_not_curvilinear": dict(features=[Sketch("Profile", "XY", rect(-2, -1, 2, 1)), path_sketch(),
                                                     Sketch("Aux", "XZ", [LineSegment((10.0, 0.0), (10.0, 30.0)),
                                                                          ArcOfCircle((20.0, 30.0), 10.0, PI / 2, PI)]),
                                                     AdditivePipe("AdditivePipe", "Profile", spine="Path",
                                                                  mode="Auxiliary", auxiliary_spine="Aux",
                                                                  auxiliary_curvilinear=False)]),
    "pipe_transformed_corners": dict(features=[disc(r=2.0), corner_path(),
                                               AdditivePipe("AdditivePipe", "Profile", spine="Path")]),
    "pipe_right_corners": dict(features=[disc(r=2.0), corner_path(),
                                         AdditivePipe("AdditivePipe", "Profile", spine="Path", transition="Right corner")]),
    "pipe_round_corners": dict(features=[disc(r=2.0), corner_path(),
                                         AdditivePipe("AdditivePipe", "Profile", spine="Path", transition="Round corner")]),
    "pipe_square_right_corners": dict(features=[Sketch("Profile", "XY", rect(-2, -2, 2, 2)), corner_path(),
                                                AdditivePipe("AdditivePipe", "Profile", spine="Path",
                                                             transition="Right corner")]),
    "pipe_spine_edges": dict(features=[disc(r=2.0), corner_path(),
                                       AdditivePipe("AdditivePipe", "Profile", spine=("Path", ("Edge1", "Edge2")),
                                                    transition="Right corner")]),
    "pipe_spine_one_edge": dict(features=[disc(r=2.0), corner_path(),
                                          AdditivePipe("AdditivePipe", "Profile", spine=("Path", "Edge1"))]),
    "pipe_spine_pad_edges": dict(features=[Sketch("Base", "XY", rect(0, 0, 30, 20)), Pad("Pad", "Base", length=10.0),
                                           Sketch("Profile", "YZ", [Circle((0.0, 0.0), 2.0)]),
                                           AdditivePipe("AdditivePipe", "Profile", spine=("Pad", ("Edge3", "Edge6")),
                                                        transition="Round corner")]),
    "pipe_multisection": dict(features=[disc(r=3.0), Sketch("Path", "XZ", [LineSegment((0.0, 0.0), (0.0, 40.0))]),
                                        on_xy("Mid", [Circle((0.0, 0.0), 6.0)], 20), on_xy("Top", [Circle((0.0, 0.0), 2.0)], 40),
                                        AdditivePipe("AdditivePipe", "Profile", spine="Path", transformation="Multisection",
                                                     sections=["Mid", "Top"])]),
    "pipe_multisection_square": dict(features=[Sketch("Profile", "XY", rect(-3, -3, 3, 3)), path_sketch(),
                                               Sketch("End", "YZ", rect(-1, 29, 1, 31), attachment_offset=(0.0, 0.0, 20.0)),
                                               AdditivePipe("AdditivePipe", "Profile", spine="Path",
                                                            transformation="Multisection", sections=["End"])]),
    "pipe_sections_ignored_when_constant": dict(features=[disc(r=3.0), Sketch("Path", "XZ", [LineSegment((0.0, 0.0), (0.0, 40.0))]),
                                                          on_xy("Mid", [Circle((0.0, 0.0), 6.0)], 20),
                                                          AdditivePipe("AdditivePipe", "Profile", spine="Path",
                                                                       sections=["Mid"])]),
    "pipe_linear_is_constant": dict(features=[disc(r=3.0), Sketch("Path", "XZ", [LineSegment((0.0, 0.0), (0.0, 40.0))]),
                                              on_xy("Mid", [Circle((0.0, 0.0), 6.0)], 20),
                                              AdditivePipe("AdditivePipe", "Profile", spine="Path", transformation="Linear",
                                                           sections=["Mid"])]),
    "pipe_on_block": dict(features=block() + [on_xy("Profile", [Circle((0.0, 0.0), 3.0)], 20),
                                              Sketch("Path", "XZ", [LineSegment((0.0, 20.0), (0.0, 30.0)),
                                                                    ArcOfCircle((10.0, 30.0), 10.0, PI / 2, PI)]),
                                              AdditivePipe("AdditivePipe", "Profile", spine="Path")]),
    "subpipe_groove": dict(features=block() + [Sketch("Profile", "YZ", [Circle((0.0, 20.0), 3.0)],
                                                      attachment_offset=(0.0, 0.0, -25.0)),
                                               Sketch("Path", "XY", poly((-25.0, 0.0), (25.0, 0.0)),
                                                      attachment_offset=(0.0, 0.0, 20.0)),
                                               SubtractivePipe("SubtractivePipe", "Profile", spine="Path")]),
    "subpipe_curved_channel": dict(features=block() + [Sketch("Profile", "YZ", [Circle((0.0, 15.0), 3.0)],
                                                              attachment_offset=(0.0, 0.0, -25.0)),
                                                       Sketch("Path", "XY", [LineSegment((-25.0, 0.0), (-10.0, 0.0)),
                                                                             ArcOfCircle((-10.0, 10.0), 10.0, -PI / 2, 0.0)],
                                                              attachment_offset=(0.0, 0.0, 15.0)),
                                                       SubtractivePipe("SubtractivePipe", "Profile", spine="Path")]),
    "subpipe_common": dict(features=block() + [disc(r=8.0), Sketch("Path", "XZ", [LineSegment((0.0, -5.0), (0.0, 30.0))]),
                                               SubtractivePipe("SubtractivePipe", "Profile", spine="Path", operation="Common")]),
    # ── Helix ──
    "helix_default": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch")]),
    "helix_pitch_height": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch=5.0, height=15.0)]),
    "helix_fraction_turns": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch=4.0, height=10.0)]),
    "helix_left_handed": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch=5.0, height=15.0,
                                                                      left_handed=True)]),
    "helix_reversed": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch=5.0, height=15.0,
                                                                   reversed=True)]),
    "helix_cone": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch=5.0, height=15.0,
                                                               angle=10.0)]),
    "helix_cone_negative": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch=5.0,
                                                                        height=10.0, angle=-8.0)]),
    "helix_pitch_turns": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", mode="pitch-turns-angle",
                                                                      pitch=4.0, turns=2.5)]),
    "helix_height_turns": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch",
                                                                       mode="height-turns-angle", height=12.0, turns=4.0)]),
    "helix_height_turns_growth": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch",
                                                                              mode="height-turns-growth", height=12.0,
                                                                              turns=3.0, growth=1.5)]),
    "helix_flat_spiral": dict(features=[Sketch("Sketch", "XZ", rect(5, 0, 6, 2)),
                                        AdditiveHelix("AdditiveHelix", "Sketch", mode="height-turns-growth", height=0.0,
                                                      turns=2.0, growth=2.5)]),
    "helix_z_axis": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", reference_axis="Z_Axis",
                                                                 pitch=5.0, height=10.0)]),
    "helix_h_axis": dict(features=[Sketch("Sketch", "XY", rect(0, 5, 2, 7)),
                                   AdditiveHelix("AdditiveHelix", "Sketch", reference_axis=("Sketch", "H_Axis"),
                                                 pitch=5.0, height=10.0)]),
    "helix_x_axis_on_xy": dict(features=[Sketch("Sketch", "XY", rect(0, 5, 2, 7)),
                                         AdditiveHelix("AdditiveHelix", "Sketch", reference_axis="X_Axis", pitch=5.0,
                                                       height=10.0)]),
    "helix_construction_line": dict(features=[Sketch("Sketch", "XZ", rect(5, 0, 7, 2) +
                                                     [LineSegment((10.0, 0.0), (10.0, 4.0), construction=True)]),
                                              AdditiveHelix("AdditiveHelix", "Sketch",
                                                            reference_axis=("Sketch", "Axis0"), pitch=5.0, height=10.0)]),
    "helix_profile_offset_along_axis": dict(features=[Sketch("Sketch", "XZ", rect(5, 6, 7, 8)),
                                                      AdditiveHelix("AdditiveHelix", "Sketch", pitch=5.0, height=10.0)]),
    "helix_n_axis_twist": dict(features=[Sketch("Sketch", "XY", rect(-2, -1, 2, 1)),
                                         AdditiveHelix("AdditiveHelix", "Sketch", reference_axis=("Sketch", "N_Axis"),
                                                       pitch=20.0, height=20.0)]),
    "helix_crossing_axis": dict(features=[Sketch("Sketch", "XZ", rect(-1, 0, 3, 2)),
                                          AdditiveHelix("AdditiveHelix", "Sketch", pitch=5.0, height=10.0)]),
    "helix_circle_profile": dict(features=[Sketch("Sketch", "XZ", [Circle((8.0, 1.0), 1.0)]),
                                           AdditiveHelix("AdditiveHelix", "Sketch", pitch=4.0, height=12.0)]),
    "helix_tolerance": dict(features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch=5.0, height=10.0,
                                                                    tolerance=0.5)]),
    "helix_params": dict(params={"lead": 5.0, "tall": 15.0},
                         features=[ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch="lead", height="tall")]),
    "helix_on_cylinder": dict(features=cylinder() + [Sketch("Sketch", "XZ", rect(5.5, 0, 7.5, 1.5)),
                                                     AdditiveHelix("AdditiveHelix", "Sketch", pitch=3.0, height=27.0)]),
    "subhelix_thread": dict(features=cylinder() + [Sketch("Sketch", "XZ", [LineSegment((6.5, 1.0), (5.2, 1.75)),
                                                                           LineSegment((5.2, 1.75), (6.5, 2.5)),
                                                                           LineSegment((6.5, 2.5), (6.5, 1.0))]),
                                                   SubtractiveHelix("SubtractiveHelix", "Sketch", pitch=3.0, height=24.0)]),
    "subhelix_common": dict(features=cylinder() + [Sketch("Sketch", "XZ", rect(4, 0, 7, 2)),
                                                   SubtractiveHelix("SubtractiveHelix", "Sketch", pitch=5.0, height=20.0,
                                                                    operation="Common")]),
    "subhelix_outside_deprecated": dict(features=cylinder() + [Sketch("Sketch", "XZ", rect(4, 0, 7, 2)),
                                                               SubtractiveHelix("SubtractiveHelix", "Sketch", pitch=5.0,
                                                                                height=20.0, outside=True)]),
}

ERRORS = {
    "loft_no_sections": [square("Sketch", 10, 0), AdditiveLoft("AdditiveLoft", "Sketch")],
    "loft_wire_count": [on_xy("Sketch", rect(-10, -10, 10, 10) + rect(-5, -5, 5, 5), 0), square("Sketch001", 5, 20),
                        AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])],
    "loft_same_place": [square("Sketch", 10, 0), square("Sketch001", 10, 0),
                        AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001"])],
    "loft_point_square_point": [on_xy("Bottom", [Point((0.0, 0.0))], -10), square("Sketch", 8, 0),
                                on_xy("Apex", [Point((0.0, 0.0))], 12),
                                AdditiveLoft("AdditiveLoft", ("Bottom", "Vertex1"), sections=["Sketch", ("Apex", "Vertex1")])],
    "pipe_no_spine": [disc(), AdditivePipe("AdditivePipe", "Profile")],
    "pipe_nothing_to_subtract": [disc(), Sketch("Path", "XZ", [LineSegment((0.0, 0.0), (0.0, 40.0))]),
                                 SubtractivePipe("SubtractivePipe", "Profile", spine="Path")],
    "pipe_spine_not_one_wire": [disc(), Sketch("Path", "XZ", [LineSegment((0.0, 0.0), (0.0, 10.0)),
                                                              LineSegment((5.0, 20.0), (5.0, 30.0))]),
                                AdditivePipe("AdditivePipe", "Profile", spine="Path")],
    "pipe_multisection_wires": [disc(r=3.0, hole=1.0), Sketch("Path", "XZ", [LineSegment((0.0, 0.0), (0.0, 40.0))]),
                                on_xy("Mid", [Circle((0.0, 0.0), 6.0)], 20),
                                AdditivePipe("AdditivePipe", "Profile", spine="Path", transformation="Multisection",
                                             sections=["Mid"])],
    "helix_pitch_zero": [ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", pitch=0.0)],
    "helix_height_zero": [ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", height=0.0)],
    "helix_pitch_turns_zero_pitch": [ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", mode="pitch-turns-angle",
                                                                   pitch=0.0)],
    "helix_height_turns_zero_height": [ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch",
                                                                     mode="height-turns-angle", height=0.0)],
    "helix_growth_and_height_zero": [ring_profile(), AdditiveHelix("AdditiveHelix", "Sketch", mode="height-turns-growth",
                                                                   height=0.0, growth=0.0, turns=2.0)],
    "helix_on_axis": [Sketch("Sketch", "XZ", rect(-1, 0, 1, 2)), AdditiveHelix("AdditiveHelix", "Sketch")],
    "subhelix_nothing_to_subtract": [ring_profile(), SubtractiveHelix("SubtractiveHelix", "Sketch")],
}
