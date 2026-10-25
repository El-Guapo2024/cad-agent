"""The bodies tests/test_feature_pick.py builds with cad_agent.feature and make.py builds in FreeCAD: the references a
3D-view pick gives a feature (cad_agent/feature_refs.py), the Body's datums above all: a Pad's or Pocket's Up to face and
ReferenceAxis (Direction/edge), a Revolution's axis, a Mirrored's plane, a pattern's direction or axis and a Draft's
neutral plane and pull direction, each on a Part datum (Part::DatumPlane, Part::DatumLine), an LCS's feature,
PartDesign's own datums (PartDesign::Plane, PartDesign::Line) and an edge of a solid.

Each case is one FEATURES list for both. A case with "error" is one FreeCAD refuses: make.py records FreeCAD's message,
and the test expects a FeatureError that says the same. Plain Python and cad_agent.feature only, so FreeCAD's own Python
can import it.
"""
from cad_agent.feature import (Circle, DatumLine, DatumPlane, DatumPoint, Draft, LinearPattern, LineSegment,
                               LocalCoordinateSystem, Mirrored, Pad, PartDesignLine, PartDesignPlane, PartDesignPoint, Pocket,
                               PolarPattern, Revolution, Sketch)


def rect(x0, y0, x1, y1):
    return [LineSegment((x0, y0), (x1, y0)), LineSegment((x1, y0), (x1, y1)),
            LineSegment((x1, y1), (x0, y1)), LineSegment((x0, y1), (x0, y0))]


def plate(centered=False):
    """A 40 x 20 x 5 plate, from (0, 0) or centred on the origin."""
    return [Sketch("Sketch", "XY", rect(-20, -10, 20, 10) if centered else rect(0, 0, 40, 20)), Pad("Pad", "Sketch", length=5)]


def top(x=10.0, y=10.0, r=3.0, name="Sketch001"):
    """A circle on the plate's top (5 mm up)."""
    return Sketch(name, "XY", [Circle((x, y), r)], attachment_offset=(0, 0, 5))


def hole(x=8.0, y=10.0, r=3.0):
    return [top(x, y, r), Pocket("Pocket", "Sketch001", length=5)]


def at(pos, ypr=(0.0, 0.0, 0.0)):
    return (tuple(float(c) for c in pos), tuple(float(c) for c in ypr))


C = True
CASES = {
    # ── Pad / Pocket: Up to face on a datum ──
    "pad_upto_datum_plane": {"features": plate() + [DatumPlane("DatumPlane", placement=at((0, 0, 12))), top(),
                                                    Pad("Pad001", "Sketch001", type="UpToFace", up_to_face="DatumPlane")]},
    "pad_upto_datum_plane_tilted": {"features": plate() + [DatumPlane("DatumPlane", placement=at((0, 0, 15), (0, 20, 0))), top(),
                                                           Pad("Pad001", "Sketch001", type="UpToFace", up_to_face="DatumPlane")]},
    "pad_upto_datum_plane_offset": {"features": plate() + [DatumPlane("DatumPlane", placement=at((0, 0, 12))), top(),
                                                           Pad("Pad001", "Sketch001", type="UpToFace", up_to_face="DatumPlane",
                                                               offset=2)]},
    "pad_upto_lcs_plane": {"features": plate() + [LocalCoordinateSystem("LCS", placement=at((0, 0, 9))), top(),
                                                  Pad("Pad001", "Sketch001", type="UpToFace", up_to_face=("LCS", "XY_Plane"))]},
    "pad_upto_lcs_plane_turned": {"features": plate() + [LocalCoordinateSystem("LCS", placement=at((0, 0, 14), (0, 0, 25))), top(),
                                                         Pad("Pad001", "Sketch001", type="UpToFace",
                                                             up_to_face=("LCS", "XY_Plane"))]},
    "pad_upto_pd_plane": {"features": plate() + [PartDesignPlane("DatumPlane", placement=at((0, 0, 11))), top(),
                                                 Pad("Pad001", "Sketch001", type="UpToFace", up_to_face="DatumPlane")]},
    "pocket_upto_datum_plane": {"features": plate() + [DatumPlane("DatumPlane", placement=at((0, 0, 2))), top(),
                                                       Pocket("Pocket", "Sketch001", type="UpToFace", up_to_face="DatumPlane")]},
    "pad_upto_face_two_sides": {"features": plate() + [DatumPlane("DatumPlane", placement=at((0, 0, 12))), top(),
                                                       Pad("Pad001", "Sketch001", side_type="Two sides", type="UpToFace",
                                                           up_to_face="DatumPlane", length2=3)]},
    # ── Pad / Pocket: ReferenceAxis (Direction/edge) ──
    "pad_axis_datum_line": {"features": plate() + [DatumLine("DatumLine", placement=at((0, 0, 0), (0, 30, 0))), top(),
                                                   Pad("Pad001", "Sketch001", length=6, reference_axis="DatumLine")]},
    "pad_axis_datum_line_along": {"features": plate() + [DatumLine("DatumLine", placement=at((0, 0, 0), (0, 30, 0))), top(),
                                                         Pad("Pad001", "Sketch001", length=6, reference_axis="DatumLine",
                                                             along_sketch_normal=False)]},
    "pad_axis_z_axis": {"features": plate() + [top(), Pad("Pad001", "Sketch001", length=6, reference_axis="Z_Axis")]},
    "pad_axis_pd_line": {"features": plate() + [PartDesignLine("DatumLine", placement=at((0, 0, 0), (40, 25, 0))), top(),
                                                Pad("Pad001", "Sketch001", length=6, reference_axis="DatumLine")]},
    "pad_axis_lcs_axis": {"features": plate() + [LocalCoordinateSystem("LCS", placement=at((0, 0, 0), (0, -20, 0))), top(),
                                                 Pad("Pad001", "Sketch001", length=6, reference_axis=("LCS", "Z_Axis"))]},
    "pad_axis_plate_edge": {"features": plate() + [top(), Pad("Pad001", "Sketch001", length=4, reference_axis=("Pad", "Edge1"))]},
    "pocket_axis_datum_line": {"features": plate() + [DatumLine("DatumLine", placement=at((0, 0, 0), (0, 20, 0))), top(),
                                                      Pocket("Pocket", "Sketch001", length=3, reference_axis="DatumLine")]},
    "pad_axis_in_plane": {"features": plate() + [top(), Pad("Pad001", "Sketch001", length=6, reference_axis="X_Axis")],
                          "error": True},
    "pad_axis_datum_plane": {"features": plate() + [DatumPlane("DatumPlane", placement=at((0, 0, 12))), top(),
                                                    Pad("Pad001", "Sketch001", length=6, reference_axis="DatumPlane")],
                             "error": True},
    # ── Revolution: the axis on a datum ──
    "revolution_datum_line": {"features": [DatumLine("DatumLine", placement=at((0, 0, 0))),
                                           Sketch("Sketch", "XZ", rect(5, 0, 10, 8)),
                                           Revolution("Revolution", "Sketch", reference_axis="DatumLine", angle=270)]},
    "revolution_datum_line_off": {"features": [DatumLine("DatumLine", placement=at((2, 0, 0))),
                                               Sketch("Sketch", "XZ", rect(5, 0, 10, 8)),
                                               Revolution("Revolution", "Sketch", reference_axis="DatumLine")]},
    "revolution_lcs_axis": {"features": [LocalCoordinateSystem("LCS", placement=at((1, 0, 0))),
                                         Sketch("Sketch", "XZ", rect(5, 0, 10, 8)),
                                         Revolution("Revolution", "Sketch", reference_axis=("LCS", "Z_Axis"), angle=180)]},
    "revolution_pd_line": {"features": [PartDesignLine("DatumLine", placement=at((0, 0, 0))),
                                        Sketch("Sketch", "XZ", rect(5, 0, 10, 8)),
                                        Revolution("Revolution", "Sketch", reference_axis="DatumLine", angle=90)]},
    "revolution_datum_plane": {"features": [DatumPlane("DatumPlane", placement=at((0, 0, 0))),
                                            Sketch("Sketch", "XZ", rect(5, 0, 10, 8)),
                                            Revolution("Revolution", "Sketch", reference_axis="DatumPlane")], "error": True},
    "revolution_normal_line": {"features": [DatumLine("DatumLine", placement=at((0, 0, 0), (0, 0, 90))),
                                            Sketch("Sketch", "XZ", rect(5, 0, 10, 8)),
                                            Revolution("Revolution", "Sketch", reference_axis="DatumLine")], "error": True},
    # ── Mirrored: the plane on a datum ──
    "mirror_datum_plane": {"features": plate(C) + hole(8, 3) + [DatumPlane("DatumPlane", placement=at((0, 0, 0), (0, 90, 0))),
                                                                Mirrored("Mirrored", ["Pocket"], mirror_plane="DatumPlane")]},
    "mirror_datum_plane_off": {"features": plate(C) + hole(8, 3) + [DatumPlane("DatumPlane", placement=at((4, 0, 0), (0, 90, 0))),
                                                                    Mirrored("Mirrored", ["Pocket"], mirror_plane="DatumPlane")]},
    "mirror_lcs_plane": {"features": plate(C) + hole(8, 3) + [LocalCoordinateSystem("LCS", placement=at((3, 0, 0))),
                                                              Mirrored("Mirrored", ["Pocket"], mirror_plane=("LCS", "YZ_Plane"))]},
    "mirror_pd_plane": {"features": plate(C) + hole(8, 3) + [PartDesignPlane("DatumPlane", placement=at((-2, 0, 0), (0, 90, 0))),
                                                             Mirrored("Mirrored", ["Pocket"], mirror_plane="DatumPlane")]},
    "mirror_datum_line": {"features": plate(C) + hole(8, 3) + [DatumLine("DatumLine", placement=at((0, 0, 0))),
                                                               Mirrored("Mirrored", ["Pocket"], mirror_plane="DatumLine")],
                          "error": True},
    "mirror_pd_line": {"features": plate(C) + hole(8, 3) + [PartDesignLine("DatumLine", placement=at((0, 0, 0))),
                                                            Mirrored("Mirrored", ["Pocket"], mirror_plane="DatumLine")],
                       "error": True},
    # ── LinearPattern: the direction on a datum ──
    "linear_datum_line": {"features": plate() + hole(5, 10) + [DatumLine("DatumLine", placement=at((0, 0, 0), (0, 90, 0))),
                                                               LinearPattern("LinearPattern", ["Pocket"], direction="DatumLine",
                                                                             length=24, occurrences=3)]},
    "linear_datum_line_turned": {"features": plate() + hole(5, 5) + [DatumLine("DatumLine", placement=at((0, 0, 0), (30, 90, 0))),
                                                                     LinearPattern("LinearPattern", ["Pocket"], direction="DatumLine",
                                                                                   length=20, occurrences=2)]},
    "linear_datum_plane": {"features": plate() + hole(5, 10) + [DatumPlane("DatumPlane", placement=at((0, 0, 0), (0, 90, 0))),
                                                                LinearPattern("LinearPattern", ["Pocket"], direction="DatumPlane",
                                                                              length=20, occurrences=3)]},
    "linear_lcs_axis": {"features": plate() + hole(5, 4) + [LocalCoordinateSystem("LCS", placement=at((7, 7, 0), (90, 0, 0))),
                                                            LinearPattern("LinearPattern", ["Pocket"], direction=("LCS", "X_Axis"),
                                                                          length=10, occurrences=2)]},
    "linear_pd_line": {"features": plate() + hole(5, 10) + [PartDesignLine("DatumLine", placement=at((0, 0, 0), (0, 90, 0))),
                                                            LinearPattern("LinearPattern", ["Pocket"], direction="DatumLine",
                                                                          length=20, occurrences=3)]},
    "linear_datum_point": {"features": plate() + hole(5, 10) + [DatumPoint("DatumPoint", placement=at((1, 2, 3))),
                                                                LinearPattern("LinearPattern", ["Pocket"], direction="DatumPoint",
                                                                              length=20, occurrences=3)], "error": True},
    "linear_pd_point": {"features": plate() + hole(5, 10) + [PartDesignPoint("DatumPoint", placement=at((1, 2, 3))),
                                                             LinearPattern("LinearPattern", ["Pocket"], direction="DatumPoint",
                                                                           length=20, occurrences=3)], "error": True},
    "linear_pd_plane": {"features": plate() + hole(5, 10) + [PartDesignPlane("DatumPlane", placement=at((0, 0, 0), (0, 90, 0))),
                                                             LinearPattern("LinearPattern", ["Pocket"], direction="DatumPlane",
                                                                           length=20, occurrences=3)]},
    # ── PolarPattern: the axis on a datum ──
    "polar_datum_line": {"features": plate(C) + hole(12, 0, 2) + [DatumLine("DatumLine", placement=at((0, 0, 0))),
                                                                  PolarPattern("PolarPattern", ["Pocket"], axis="DatumLine",
                                                                               occurrences=4)]},
    "polar_datum_line_off": {"features": plate(C) + hole(12, 0, 2) + [DatumLine("DatumLine", placement=at((5, 2, 0))),
                                                                      PolarPattern("PolarPattern", ["Pocket"], axis="DatumLine",
                                                                                   angle=90, occurrences=3)]},
    "polar_lcs_axis": {"features": plate(C) + hole(12, 0, 2) + [LocalCoordinateSystem("LCS", placement=at((3, 1, 0))),
                                                                PolarPattern("PolarPattern", ["Pocket"], axis=("LCS", "Z_Axis"),
                                                                             occurrences=3)]},
    "polar_pd_line": {"features": plate(C) + hole(12, 0, 2) + [PartDesignLine("DatumLine", placement=at((0, 0, 0))),
                                                               PolarPattern("PolarPattern", ["Pocket"], axis="DatumLine",
                                                                            occurrences=4)]},
    "polar_pd_plane": {"features": plate(C) + hole(12, 0, 2) + [PartDesignPlane("DatumPlane", placement=at((0, 0, 0))),
                                                                PolarPattern("PolarPattern", ["Pocket"], axis="DatumPlane",
                                                                             occurrences=4)], "error": True},
    "polar_datum_plane": {"features": plate(C) + hole(12, 0, 2) + [DatumPlane("DatumPlane", placement=at((0, 0, 0))),
                                                                   PolarPattern("PolarPattern", ["Pocket"], axis="DatumPlane",
                                                                                occurrences=4)], "error": True},
    # ── Draft: the neutral plane and pull direction on a datum ──
    "draft_neutral_datum_plane": {"features": plate() + [DatumPlane("DatumPlane", placement=at((0, 0, 2.5))),
                                                         Draft("Draft", ("Pad", ["Face1", "Face2"]), angle=4,
                                                               neutral_plane="DatumPlane", pull_direction="Z_Axis")]},
    "draft_neutral_lcs_plane": {"features": plate() + [LocalCoordinateSystem("LCS", placement=at((0, 0, 3))),
                                                       Draft("Draft", ("Pad", ["Face1"]), angle=4,
                                                             neutral_plane=("LCS", "XY_Plane"), pull_direction="Z_Axis")]},
    "draft_neutral_pd_plane": {"features": plate() + [PartDesignPlane("DatumPlane", placement=at((0, 0, 2))),
                                                      Draft("Draft", ("Pad", ["Face1"]), angle=4, neutral_plane="DatumPlane")]},
    "draft_pull_datum_line": {"features": plate() + [DatumLine("DatumLine", placement=at((0, 0, 0))),
                                                     Draft("Draft", ("Pad", ["Face1"]), angle=4, neutral_plane="XY_Plane",
                                                           pull_direction="DatumLine")]},
    "draft_pull_pd_line": {"features": plate() + [PartDesignLine("DatumLine", placement=at((0, 0, 0), (0, 180, 0))),
                                                  Draft("Draft", ("Pad", ["Face1"]), angle=4, neutral_plane="XY_Plane",
                                                        pull_direction="DatumLine")]},
    "draft_pull_lcs_axis": {"features": plate() + [LocalCoordinateSystem("LCS", placement=at((4, 4, 4))),
                                                   Draft("Draft", ("Pad", ["Face1"]), angle=4, neutral_plane="XY_Plane",
                                                         pull_direction=("LCS", "Z_Axis"))]},
    "draft_neutral_datum_line": {"features": plate() + [DatumLine("DatumLine", placement=at((0, 0, 0))),
                                                        Draft("Draft", ("Pad", ["Face1"]), angle=4, neutral_plane="DatumLine")],
                                 "error": True},
    "draft_neutral_pd_line": {"features": plate() + [PartDesignLine("DatumLine", placement=at((0, 0, 0))),
                                                     Draft("Draft", ("Pad", ["Face1"]), angle=4, neutral_plane="DatumLine")],
                              "error": True},
    "draft_pull_datum_plane": {"features": plate() + [DatumPlane("DatumPlane", placement=at((0, 0, 0))),
                                                      Draft("Draft", ("Pad", ["Face1"]), angle=4, neutral_plane="XY_Plane",
                                                            pull_direction="DatumPlane")], "error": True},
    "draft_pull_pd_plane": {"features": plate() + [PartDesignPlane("DatumPlane", placement=at((0, 0, 0))),
                                                   Draft("Draft", ("Pad", ["Face1"]), angle=4, neutral_plane="XY_Plane",
                                                         pull_direction="DatumPlane")], "error": True},
}
