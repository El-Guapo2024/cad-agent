"""The bodies tests/test_feature_transform.py builds with cad_agent.feature and make.py builds in FreeCAD: Mirrored,
LinearPattern, PolarPattern and MultiTransform (cad_agent/feature_transform.py), and the additive and subtractive
primitives (cad_agent/feature_primitive.py).

Each case is one FEATURES list for both. A case with "error" is one FreeCAD refuses: make.py records FreeCAD's message,
and the test expects a FeatureError that says the same. Plain Python and cad_agent.feature only, so FreeCAD's own Python
can import it.
"""
from cad_agent.feature import (AdditiveBox, AdditiveCone, AdditiveCylinder, AdditiveEllipsoid, AdditivePrism,
                               AdditiveSphere, AdditiveTorus, AdditiveWedge, Circle, LinearPattern, LineSegment,
                               Mirrored, MultiTransform, Pad, Pocket, PolarPattern, Sketch, SubtractiveBox,
                               SubtractiveCone, SubtractiveCylinder, SubtractiveEllipsoid, SubtractivePrism,
                               SubtractiveSphere, SubtractiveTorus, SubtractiveWedge)


def rect(x0, y0, x1, y1, construction=False):
    return [LineSegment((x0, y0), (x1, y0), construction), LineSegment((x1, y0), (x1, y1), construction),
            LineSegment((x1, y1), (x0, y1), construction), LineSegment((x0, y1), (x0, y0), construction)]


def plate(centered=False):
    """A 40 x 20 x 5 plate, from (0, 0) or centred on the origin."""
    r = rect(-20, -10, 20, 10) if centered else rect(0, 0, 40, 20)
    return [Sketch("Sketch", "XY", r), Pad("Pad", "Sketch", length=5)]


def hole(x=8.0, y=10.0, r=3.0, name="Pocket", sketch="Sketch001", extra=()):
    """A hole down through the plate from its top (a sketch 5 mm up, pocketed 5 mm)."""
    return [Sketch(sketch, "XY", [Circle((x, y), r), *extra], attachment_offset=(0, 0, 5)),
            Pocket(name, sketch, length=5)]


def boss(x=8.0, y=10.0, r=3.0, h=3.0, name="Boss", sketch="BossSketch"):
    """A cylinder standing on the plate's top."""
    return [Sketch(sketch, "XY", [Circle((x, y), r)], attachment_offset=(0, 0, 5)), Pad(name, sketch, length=h)]


C = True        # the centred plate
CASES = {
    # ── Mirrored ──
    "mirror_sketch_v_axis": {"features": plate(C) + hole(8, 3) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane=("Sketch001", "V_Axis"))]},
    "mirror_sketch_h_axis": {"features": plate(C) + hole(8, 3) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane=("Sketch001", "H_Axis"))]},
    "mirror_sketch_normal_misses": {"features": plate(C) + hole(8, 3) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane=("Sketch001", ""))]},
    "mirror_yz_plane": {"features": plate(C) + hole(8, 3) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane="YZ_Plane")]},
    "mirror_xz_plane": {"features": plate(C) + hole(8, 3) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane="XZ_Plane")]},
    "mirror_off_plate_misses": {"features": plate() + hole() + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane=("Sketch001", "V_Axis"))]},
    "mirror_boss_yz_plane": {"features": plate(C) + boss(8, 3) + [
        Mirrored("Mirrored", ["Boss"], mirror_plane="YZ_Plane")]},
    "mirror_boss_xy_plane_apart": {"features": plate(C) + boss(8, 3) + [
        Mirrored("Mirrored", ["Boss"], mirror_plane="XY_Plane")]},
    "mirror_boss_face_apart": {"features": plate() + boss(36, 10) + [
        Mirrored("Mirrored", ["Boss"], mirror_plane=("Pad", "Face2"))]},
    "mirror_pocket_face": {"features": plate() + hole(36, 10, 2) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane=("Pad", "Face4"))]},
    "mirror_two_originals": {"features": plate(C) + hole(8, 3) + boss(-12, -4, 2) + [
        Mirrored("Mirrored", ["Boss", "Pocket"], mirror_plane="XZ_Plane")]},
    "mirror_construction_line": {"features": plate(C) + hole(8, 3, 2, extra=[
        LineSegment((-5.0, -5.0), (5.0, 5.0), construction=True)]) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane=("Sketch001", "Axis0"))]},
    "mirror_whole_shape": {"features": plate() + hole() + [
        Mirrored("Mirrored", transform_mode="Whole shape", mirror_plane="YZ_Plane")]},
    "mirror_refine_off": {"features": plate(C) + boss(8, 3) + [
        Mirrored("Mirrored", ["Boss"], mirror_plane="YZ_Plane", refine=False)]},
    "mirror_suppressed_copy": {"features": plate(C) + hole(8, 3) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane="YZ_Plane", suppressed_indices=[1])]},
    "mirror_suppressed_original": {"features": plate(C) + hole(8, 3) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane="YZ_Plane", suppressed_indices=[0])]},
    "mirror_suppressed_original_boss": {"features": plate(C) + boss(8, 3) + [
        Mirrored("Mirrored", ["Boss"], mirror_plane="YZ_Plane", suppressed_indices=[0])]},
    "mirror_then_pad": {"features": plate(C) + hole(8, 3) + [
        Mirrored("Mirrored", ["Pocket"], mirror_plane="YZ_Plane")] + boss(0, 0, 2, name="Pad001")},
    "mirror_no_plane": {"features": plate(C) + hole(8, 3) + [Mirrored("Mirrored", ["Pocket"])], "error": True},
    "mirror_boss_face1": {"features": plate() + boss() + [
        Mirrored("Mirrored", ["Boss"], mirror_plane=("Boss", "Face1"))]},
    "mirror_of_sketch": {"features": plate() + hole() + [
        Mirrored("Mirrored", ["Sketch001"], mirror_plane="YZ_Plane")], "error": True},

    # ── LinearPattern ──
    "linear_sketch_h_axis": {"features": plate() + hole(6, 10, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction=("Sketch001", "H_Axis"), length=24, occurrences=4)]},
    "linear_sketch_v_axis": {"features": plate() + hole(6, 4, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction=("Sketch001", "V_Axis"), length=12, occurrences=3)]},
    "linear_spacing": {"features": plate() + hole(6, 10, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", mode="Spacing", offset=7, occurrences=4)]},
    "linear_reversed": {"features": plate() + hole(34, 10, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", reversed=True, length=20, occurrences=3)]},
    "linear_y_axis": {"features": plate() + hole(20, 4, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="Y_Axis", length=12, occurrences=2)]},
    "linear_plane_normal_stack": {"features": plate() + boss(20, 10, 3, 3) + [
        LinearPattern("LinearPattern", ["Boss"], direction="XY_Plane", length=6, occurrences=3)]},
    "linear_edge": {"features": plate() + hole(6, 10, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction=("Pad", "Edge4"), length=20, occurrences=3)]},
    "linear_face_normal": {"features": plate() + hole(6, 10, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction=("Pad", "Face1"), length=20, occurrences=3)]},
    "linear_two_directions": {"features": plate() + hole(6, 5, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction=("Sketch001", "H_Axis"), length=28, occurrences=3,
                      direction2=("Sketch001", "V_Axis"), length2=10, occurrences2=2)]},
    "linear_two_directions_spacing": {"features": plate() + hole(6, 5, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", length=28, occurrences=3,
                      direction2="Y_Axis", mode2="Spacing", offset2=10, occurrences2=2)]},
    "linear_spacings": {"features": plate() + hole(4, 10, 1.5) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", mode="Spacing", offset=6, occurrences=4,
                      spacings=[5, -1, 12])]},
    "linear_spacing_pattern": {"features": plate() + hole(4, 10, 1.5) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", mode="Spacing", offset=6, occurrences=5,
                      spacing_pattern=[4, 9])]},
    "linear_misses": {"features": plate() + hole(6, 10, 2) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", length=100, occurrences=2)]},
    "linear_boss_apart": {"features": plate() + boss(36, 10, 3) + [
        LinearPattern("LinearPattern", ["Boss"], direction="X_Axis", length=20, occurrences=3)]},
    "linear_whole_shape": {"features": plate() + hole() + [
        LinearPattern("LinearPattern", transform_mode="Whole shape", direction="X_Axis", length=40, occurrences=3)]},
    "linear_whole_shape_apart": {"features": plate() + [
        LinearPattern("LinearPattern", transform_mode="Whole shape", direction="Y_Axis", length=50, occurrences=2)]},
    "linear_no_direction": {"features": plate() + hole() + [
        LinearPattern("LinearPattern", ["Pocket"], length=20, occurrences=3)]},
    "linear_one_occurrence": {"features": plate() + hole() + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", occurrences=1)]},
    "linear_suppressed": {"features": plate() + hole(4, 10, 1.5) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", length=30, occurrences=4,
                      suppressed_indices=[1, 3])]},
    "linear_params": {"params": {"pitch": 8.0, "count": 4.0}, "features": plate() + hole(4, 10, 1.5) + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", length="pitch * (count - 1)", occurrences="count")]},
    "linear_two_originals": {"features": plate() + hole(4, 5, 1.5) + boss(4, 15, 1.5) + [
        LinearPattern("LinearPattern", ["Pocket", "Boss"], direction="X_Axis", length=30, occurrences=3)]},
    "linear_length_zero": {"features": plate() + hole() + [
        LinearPattern("LinearPattern", ["Pocket"], direction="X_Axis", length=0, occurrences=3)], "error": True},
    "linear_boss_face1": {"features": plate() + boss() + [
        LinearPattern("LinearPattern", ["Boss"], direction=("Boss", "Face1"), occurrences=2)]},

    # ── PolarPattern ──
    "polar_z_axis_six": {"features": plate(C) + hole(7, 0, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis="Z_Axis", angle=360, occurrences=6)]},
    "polar_extent_partial": {"features": plate(C) + hole(7, 0, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis="Z_Axis", angle=180, occurrences=3)]},
    "polar_spacing": {"features": plate(C) + hole(7, 0, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis="Z_Axis", mode="Spacing", offset=45, occurrences=4)]},
    "polar_spacings": {"features": plate(C) + hole(7, 0, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis="Z_Axis", mode="Spacing", offset=30, occurrences=4,
                     spacings=[60, -1, 90])]},
    "polar_reversed": {"features": plate(C) + hole(7, 2, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis="Z_Axis", reversed=True, angle=90, occurrences=2)]},
    "polar_sketch_normal": {"features": plate(C) + hole(7, 0, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis=("Sketch001", "N_Axis"), occurrences=4)]},
    "polar_default_occurrences": {"features": plate(C) + hole(7, 0, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis="Z_Axis")]},
    "polar_circular_edge": {"features": plate() + boss(20, 10, 6, 2) + hole(24, 10, 1, sketch="HoleSketch") + [
        PolarPattern("PolarPattern", ["Pocket"], axis=("Boss", "Edge1"), occurrences=5)]},
    "polar_straight_edge": {"features": plate() + hole(36, 4, 2) + [
        PolarPattern("PolarPattern", ["Pocket"], axis=("Pad", "Edge2"), angle=180, occurrences=2)]},
    "polar_construction_axis": {"features": plate(C) + hole(9, 0, 1.5, extra=[
        LineSegment((3.0, 0.0), (3.0, 4.0), construction=True)]) + [
        PolarPattern("PolarPattern", ["Pocket"], axis=("Sketch001", "Axis0"), occurrences=2)]},
    "polar_boss_apart": {"features": plate(C) + boss(16, 0, 2) + [
        PolarPattern("PolarPattern", ["Boss"], axis="Z_Axis", occurrences=4)]},
    "polar_whole_shape_x": {"features": plate(C) + hole(8, 3) + [
        PolarPattern("PolarPattern", transform_mode="Whole shape", axis="X_Axis", occurrences=2)]},
    "polar_angle_zero": {"features": plate(C) + hole(7, 0, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis="Z_Axis", angle=0, occurrences=3)], "error": True},
    "polar_plane_axis": {"features": plate(C) + hole(7, 0, 1.5) + [
        PolarPattern("PolarPattern", ["Pocket"], axis="XY_Plane", occurrences=3)], "error": True},

    # ── MultiTransform ──
    "multi_mirror_linear": {"features": plate(C) + hole(4, 3, 1.5) + [
        MultiTransform("MultiTransform", ["Pocket"], transformations=[
            Mirrored("Mirror", mirror_plane="YZ_Plane"),
            LinearPattern("Linear_Pattern", direction="X_Axis", length=10, occurrences=2)])]},
    "multi_linear_polar": {"features": plate(C) + hole(6, 0, 1) + [
        MultiTransform("MultiTransform", ["Pocket"], transformations=[
            LinearPattern("Linear_Pattern", direction="X_Axis", length=4, occurrences=2),
            PolarPattern("Polar_Pattern", axis="Z_Axis", occurrences=4)])]},
    "multi_grid": {"features": plate() + hole(5, 5, 1.5) + [
        MultiTransform("MultiTransform", ["Pocket"], transformations=[
            LinearPattern("Linear_Pattern", direction="X_Axis", length=30, occurrences=4),
            LinearPattern("Linear_Pattern001", direction="Y_Axis", length=10, occurrences=2)])]},
    "multi_empty": {"features": plate() + hole() + [MultiTransform("MultiTransform", ["Pocket"])]},
    "multi_suppressed": {"features": plate() + hole(5, 5, 1.5) + [
        MultiTransform("MultiTransform", ["Pocket"], suppressed_indices=[2], transformations=[
            LinearPattern("Linear_Pattern", direction="X_Axis", length=30, occurrences=4),
            LinearPattern("Linear_Pattern001", direction="Y_Axis", length=10, occurrences=2,
                          suppressed_indices=[1])])]},
    "multi_whole_shape": {"features": plate() + hole() + [
        MultiTransform("MultiTransform", transform_mode="Whole shape", transformations=[
            Mirrored("Mirror", mirror_plane="YZ_Plane"),
            Mirrored("Mirror001", mirror_plane="XZ_Plane")])]},
    "multi_boss": {"features": plate(C) + boss(12, 4, 2) + [
        MultiTransform("MultiTransform", ["Boss"], transformations=[
            Mirrored("Mirror", mirror_plane="YZ_Plane"),
            Mirrored("Mirror001", mirror_plane="XZ_Plane")])]},

    # ── the primitives ──
    **{f"prim_{c.kind}": {"features": [c(c.kind[8:])]} for c in (
        AdditiveBox, AdditiveCylinder, AdditiveSphere, AdditiveCone, AdditiveEllipsoid, AdditiveTorus,
        AdditivePrism, AdditiveWedge)},
    **{f"prim_{c.kind}": {"features": [AdditiveBox("Base", length=30, width=30, height=30),
                                       c(c.kind[11:], placement=((3, 4, 5), (0, 0, 0)))]} for c in (
        SubtractiveBox, SubtractiveCylinder, SubtractiveSphere, SubtractiveCone, SubtractiveEllipsoid,
        SubtractiveTorus, SubtractivePrism, SubtractiveWedge)},
    "prim_box_placed_rotated": {"features": [AdditiveBox("Box", length=20, width=10, height=4,
                                                         placement=((5, -3, 2), (30, 0, 0)))]},
    "prim_cylinder_pitched": {"features": [AdditiveCylinder("Cylinder", radius=4, height=12,
                                                            placement=((0, 0, 0), (0, 45, 0)))]},
    "prim_cylinder_angle_skew": {"features": [AdditiveCylinder("Cylinder", radius=5, height=8, angle=270,
                                                               first_angle=20, second_angle=-10)]},
    "prim_cylinder_angle_clamped": {"features": [AdditiveCylinder("Cylinder", radius=5, height=8, angle=400)]},
    "prim_sphere_partial": {"features": [AdditiveSphere("Sphere", radius=6, angle1=-30, angle2=60, angle3=270)]},
    "prim_cone_apex": {"features": [AdditiveCone("Cone", radius1=0, radius2=5, height=10, angle=180)]},
    "prim_cone_cylinder": {"features": [AdditiveCone("Cone", radius1=3, radius2=3, height=7)]},
    "prim_ellipsoid_three_radii": {"features": [AdditiveEllipsoid("Ellipsoid", radius1=3, radius2=6, radius3=4.5,
                                                                  angle1=-45, angle3=300)]},
    "prim_torus_partial": {"features": [AdditiveTorus("Torus", radius1=8, radius2=3, angle1=-90, angle2=90,
                                                      angle3=180)]},
    "prim_prism_triangle_skew": {"features": [AdditivePrism("Prism", polygon=3, circumradius=5, height=6,
                                                            first_angle=15)]},
    "prim_prism_octagon": {"features": [AdditivePrism("Prism", polygon=8, circumradius=4, height=3)]},
    "prim_wedge_custom": {"features": [AdditiveWedge("Wedge", xmin=-2, ymin=1, zmin=0, x2min=1, z2min=3,
                                                     xmax=8, ymax=6, zmax=9, x2max=4, z2max=5)]},
    "prim_common": {"features": [AdditiveBox("Base", length=30, width=30, height=30),
                                 SubtractiveSphere("Sphere", radius=20, operation="Common")]},
    "prim_on_pad": {"features": plate() + [SubtractiveCylinder("Cylinder", radius=3, height=5,
                                                               placement=((8, 10, 0), (0, 0, 0))),
                                           AdditiveBox("Box", length=10, width=10, height=10,
                                                       placement=((30, 5, 5), (0, 0, 0)))]},
    "prim_apart": {"features": plate() + [AdditiveSphere("Sphere", radius=4, placement=((60, 10, 2), (0, 0, 0)))]},
    "prim_refine_off": {"features": [AdditiveBox("Box", length=10, width=10, height=10),
                                     AdditiveBox("Box001", length=10, width=10, height=10,
                                                 placement=((10, 0, 0), (0, 0, 0)), refine=False)]},
    "prim_params": {"params": {"boss_r": 4.0, "boss_h": 9.0}, "features": [
        AdditiveCylinder("Cylinder", radius="boss_r", height="boss_h * 2")]},
    "prim_pattern": {"features": plate() + [SubtractiveCylinder("Cylinder", radius=2, height=5,
                                                                placement=((5, 10, 0), (0, 0, 0))),
                                            LinearPattern("LinearPattern", ["Cylinder"], direction="X_Axis",
                                                          length=30, occurrences=4)]},
    "prim_mirror": {"features": [AdditiveBox("Box", length=10, width=10, height=10, placement=((5, 0, 0), (0, 0, 0))),
                                 Mirrored("Mirrored", ["Box"], mirror_plane="YZ_Plane")]},
    "prim_subtract_no_base": {"features": [SubtractiveBox("Box")], "error": True},
    "prim_prism_two_sides": {"features": [AdditivePrism("Prism", polygon=2)], "error": True},
}
