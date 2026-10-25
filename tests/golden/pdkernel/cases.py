"""The bodies tests/test_feature_pdkernel.py builds with cad_agent.feature and make.py builds in FreeCAD: PartDesign's
kernel behaviour beyond the features' own modules. A Pad's and a Pocket's TaperAngle and TaperAngle2
(cad_agent/feature_taper.py), the subtractive features' Operation "Common" (Pocket, Groove, Hole), PartDesign::Scaled
(cad_agent/feature_scaled.py), a Hole's DepthType "UpToFirst" and the StartType "Reference" (StartReference).

Each case is one FEATURES list for both. A case with "error" is one FreeCAD refuses: make.py records FreeCAD's message,
and the test expects a FeatureError that says the same. Plain Python and cad_agent.feature only, so FreeCAD's own Python
can import it.
"""
from cad_agent.feature import (Circle, Groove, Hole, LinearPattern, LineSegment, Mirrored, MultiTransform, Pad,
                               Pocket, PolarPattern, Revolution, Scaled, Sketch)


def rect(x0, y0, x1, y1):
    return [LineSegment((x0, y0), (x1, y0)), LineSegment((x1, y0), (x1, y1)),
            LineSegment((x1, y1), (x0, y1)), LineSegment((x0, y1), (x0, y0))]


def plate(thick=10.0, name="Pad"):
    """A 40 x 20 plate from the origin."""
    return [Sketch("Base", "XY", rect(0, 0, 40, 20)), Pad(name, "Base", length=thick)]


def top(geometry, z=10.0, name="Top"):
    """A sketch on the plate's top (the XY plane moved up)."""
    return Sketch(name, "XY", geometry, attachment_offset=(0, 0, z))


def boss(x=10.0, y=10.0, r=3.0, h=4.0):
    """A cylinder standing on the plate's top."""
    return [top([Circle((x, y), r)], name="BossSketch"), Pad("Boss", "BossSketch", length=h)]


def hole(x=10.0, y=10.0, r=3.0, depth=6.0):
    """A blind round pocket down from the plate's top."""
    return [top([Circle((x, y), r)], name="HoleSketch"), Pocket("Pocket", "HoleSketch", length=depth)]


CASES = {
    # ── TaperAngle: ExtrusionHelper::makeElementDraft ──
    "pad_taper_out": dict(features=[Sketch("S", "XY", rect(0, 0, 40, 20)), Pad("Pad", "S", length=10, taper_angle=5)]),
    "pad_taper_in": dict(features=[Sketch("S", "XY", rect(0, 0, 40, 20)), Pad("Pad", "S", length=10, taper_angle=-8)]),
    "pad_taper_circle": dict(features=[Sketch("S", "XY", [Circle((0, 0), 10)]), Pad("Pad", "S", length=8,
                                                                                    taper_angle=10)]),
    "pad_taper_circle_in": dict(features=[Sketch("S", "XY", [Circle((0, 0), 10)]), Pad("Pad", "S", length=8,
                                                                                       taper_angle=-10)]),
    "pad_taper_hole": dict(features=[Sketch("S", "XY", rect(0, 0, 40, 20) + [Circle((20, 10), 4)]),
                                     Pad("Pad", "S", length=6, taper_angle=4)]),
    "pad_taper_two_islands": dict(features=[Sketch("S", "XY", rect(0, 0, 10, 10) + rect(20, 0, 30, 10)),
                                            Pad("Pad", "S", length=5, taper_angle=-6)]),
    "pad_taper_reversed": dict(features=[Sketch("S", "XY", rect(0, 0, 40, 20)),
                                         Pad("Pad", "S", length=10, taper_angle=5, reversed=True)]),
    "pad_taper_param": dict(params={"draft": 3.0, "height": 12.0},
                            features=[Sketch("S", "XY", rect(0, 0, 40, 20)),
                                      Pad("Pad", "S", length="height", taper_angle="draft")]),
    "pad_taper_symmetric": dict(features=[Sketch("S", "XY", rect(0, 0, 40, 20)),
                                          Pad("Pad", "S", length=10, side_type="Symmetric", taper_angle=5)]),
    "pad_taper_two_sides": dict(features=[Sketch("S", "XY", rect(0, 0, 40, 20)),
                                          Pad("Pad", "S", length=10, side_type="Two sides", length2=4,
                                              taper_angle=5, taper_angle2=-3)]),
    "pad_taper_two_sides_second_only": dict(features=[Sketch("S", "XY", rect(0, 0, 40, 20)),
                                                      Pad("Pad", "S", length=6, side_type="Two sides", length2=6,
                                                          taper_angle2=10)]),
    "pad_taper_on_plate": dict(features=plate() + [top([Circle((20, 10), 5)]),
                                                   Pad("Boss", "Top", length=8, taper_angle=-15)]),
    "pad_taper_up_to_face_ignored": dict(features=plate() + [
        Sketch("Below", "XY", rect(5, 5, 15, 15), attachment_offset=(0, 0, -10)),
        Pad("Pad001", "Below", type="UpToFace", up_to_face=("Pad", "Face6"), taper_angle=10)]),
    "pad_taper_too_large": dict(features=[Sketch("S", "XY", rect(0, 0, 10, 10)),
                                          Pad("Pad", "S", length=20, taper_angle=-40)], error=True),
    "pad_taper_ninety": dict(features=[Sketch("S", "XY", rect(0, 0, 10, 10)),
                                       Pad("Pad", "S", length=5, taper_angle=90)], error=True),
    "pocket_taper": dict(features=plate() + [top([Circle((20, 10), 6)]),
                                             Pocket("Pocket", "Top", length=6, taper_angle=10)]),
    "pocket_taper_rect_in": dict(features=plate() + [top(rect(10, 4, 30, 16)),
                                                     Pocket("Pocket", "Top", length=5, taper_angle=-12)]),
    "pocket_taper_through_all": dict(features=plate() + [top([Circle((20, 10), 3)]),
                                                         Pocket("Pocket", "Top", type="ThroughAll", taper_angle=4)]),
    "pocket_taper_symmetric_through_all": dict(features=plate() + [
        Sketch("Mid", "XY", [Circle((20, 10), 3)], attachment_offset=(0, 0, 5)),
        Pocket("Pocket", "Mid", type="ThroughAll", side_type="Symmetric", taper_angle=5)]),
    # ── Operation "Common": FeatureAddSub::getBooleanMaker ──
    "pocket_common": dict(features=plate() + [top([Circle((20, 10), 6)]),
                                              Pocket("Pocket", "Top", length=6, operation="Common")]),
    "pocket_common_through_all": dict(features=plate() + [top(rect(5, 5, 25, 15)),
                                                          Pocket("Pocket", "Top", type="ThroughAll",
                                                                 operation="Common")]),
    "pocket_common_taper": dict(features=plate() + [top([Circle((20, 10), 8)]),
                                                    Pocket("Pocket", "Top", length=10, taper_angle=20,
                                                           operation="Common")]),
    "pocket_common_up_to_face": dict(features=plate() + [top(rect(5, 5, 25, 15)),
                                                         Pocket("Pocket", "Top", type="UpToFace",
                                                                up_to_face=("Pad", "Face5"), operation="Common")]),
    "groove_common": dict(features=[Sketch("Ring", "XZ", rect(5, 0, 15, 10)), Revolution("Revolution", "Ring"),
                                    Sketch("Notch", "XZ", rect(13, 4, 18, 6)),
                                    Groove("Groove", "Notch", operation="Common")]),
    "groove_common_90": dict(features=[Sketch("Ring", "XZ", rect(5, 0, 15, 10)), Revolution("Revolution", "Ring"),
                                       Sketch("Notch", "XZ", rect(3, 2, 18, 8)),
                                       Groove("Groove", "Notch", angle=90.0, operation="Common")]),
    "hole_common": dict(features=plate() + [top([Circle((10, 10), 4)]),
                                            Hole("Hole", "Top", diameter=8.0, depth=6.0, operation="Common")]),
    "hole_common_two": dict(features=plate() + [top([Circle((10, 10), 3), Circle((30, 10), 3)]),
                                                Hole("Hole", "Top", diameter=6.0, depth_type="ThroughAll",
                                                     operation="Common")]),
    # ── PartDesign::Scaled ──
    "scaled_boss": dict(features=plate() + boss() + [Scaled("Scaled", ["Boss"], factor=2.0, occurrences=2)]),
    "scaled_boss_three": dict(features=plate() + boss(20, 10, 2, 3) + [
        Scaled("Scaled", ["Boss"], factor=3.0, occurrences=3)]),
    "scaled_pocket_shrink": dict(features=plate() + hole(20, 10, 6, 6) + [
        Scaled("Scaled", ["Pocket"], factor=0.5, occurrences=3)]),
    "scaled_pocket_grow": dict(features=plate() + hole(20, 10, 3, 4) + [
        Scaled("Scaled", ["Pocket"], factor=1.5, occurrences=2)]),
    "scaled_suppressed": dict(features=plate() + boss(20, 10, 2, 3) + [
        Scaled("Scaled", ["Boss"], factor=3.0, occurrences=3, suppressed_indices=[1])]),
    "scaled_param": dict(params={"grow": 2.5, "copies": 2}, features=plate() + boss() + [
        Scaled("Scaled", ["Boss"], factor="grow", occurrences="copies")]),
    "scaled_refine_off": dict(features=plate() + boss() + [
        Scaled("Scaled", ["Boss"], factor=2.0, occurrences=2, refine=False)]),
    "scaled_whole_shape": dict(features=[Sketch("S", "XY", rect(10, 10, 20, 20)), Pad("Pad", "S", length=5),
                                         Scaled("Scaled", transform_mode="Whole shape", factor=0.5, occurrences=2)]),
    "scaled_factor_too_small": dict(features=plate() + boss() + [
        Scaled("Scaled", ["Boss"], factor=0.0, occurrences=2)], error=True),
    "scaled_one_occurrence": dict(features=plate() + boss() + [
        Scaled("Scaled", ["Boss"], factor=2.0, occurrences=1)], error=True),
    "multi_linear_scaled": dict(features=plate() + boss(5, 10, 2, 3) + [
        MultiTransform("MultiTransform", ["Boss"], transformations=[
            LinearPattern("Linear_Pattern", direction="X_Axis", length=24, occurrences=3),
            Scaled("Scale", factor=2.0, occurrences=3)])]),
    "multi_linear_scaled_slices": dict(features=plate() + hole(5, 6, 2, 4) + [
        MultiTransform("MultiTransform", ["Pocket"], transformations=[
            LinearPattern("Linear_Pattern", direction="X_Axis", length=27, occurrences=4),
            Scaled("Scale", factor=0.5, occurrences=2)])]),
    "multi_scaled_then_polar": dict(features=plate() + boss(20, 4, 2, 3) + [
        MultiTransform("MultiTransform", ["Boss"], transformations=[
            Scaled("Scale", factor=1.5, occurrences=2),
            Mirrored("Mirror", mirror_plane=("BossSketch", "H_Axis"))])]),
    "multi_scaled_factor_one": dict(features=plate() + hole(5, 6, 2, 4) + [
        MultiTransform("MultiTransform", ["Pocket"], transformations=[
            LinearPattern("Linear_Pattern", direction="X_Axis", length=27, occurrences=4),
            Scaled("Scale", factor=1.0, occurrences=2)])]),
    "multi_scaled_not_divisor": dict(features=plate() + boss(5, 10, 2, 3) + [
        MultiTransform("MultiTransform", ["Boss"], transformations=[
            LinearPattern("Linear_Pattern", direction="X_Axis", length=24, occurrences=3),
            Scaled("Scale", factor=2.0, occurrences=2)])], error=True),
    # ── StartType "Reference": ProfileBased::getStartReferenceOffset, Revolved::getStartReferenceAngle ──
    "pad_start_reference_face": dict(features=plate() + [
        Sketch("Under", "XY", rect(10, 5, 20, 15)),
        Pad("Pad001", "Under", length=5, start_type="Reference", start_reference=("Pad", "Face6"))]),
    "pad_start_reference_plane_offset": dict(features=[
        Sketch("Low", "XY", rect(0, 0, 10, 10), attachment_offset=(0, 0, -10)),
        Pad("Pad", "Low", length=4, start_type="Reference", start_reference="XY_Plane", start_offset=2.0)]),
    "pad_start_reference_sketch": dict(features=plate() + [top([Circle((30, 10), 3)], z=14.0, name="High"),
                                                           Sketch("Under", "XY", rect(5, 5, 15, 15)),
                                                           Pad("Pad001", "Under", length=3, start_type="Reference",
                                                               start_reference="High")]),
    "pad_start_reference_none": dict(features=[Sketch("S", "XY", rect(0, 0, 10, 10)),
                                               Pad("Pad", "S", length=4, start_type="Reference", start_offset=3.0)]),
    "pad_start_reference_curved": dict(features=[
        Sketch("Rod", "XZ", [Circle((0, 0), 5)]), Pad("RodPad", "Rod", length=20, side_type="Symmetric"),
        Sketch("Under", "XY", rect(-2, -2, 2, 2), attachment_offset=(0, 0, -20)),
        Pad("Pad", "Under", length=3, start_type="Reference", start_reference=("RodPad", "Face1"))]),
    "pad_start_reference_misses": dict(features=[
        Sketch("Rod", "XZ", [Circle((0, 0), 5)]), Pad("RodPad", "Rod", length=20, side_type="Symmetric"),
        Sketch("Under", "XY", rect(30, -2, 34, 2), attachment_offset=(0, 0, -20)),
        Pad("Pad", "Under", length=3, start_type="Reference", start_reference=("RodPad", "Face1"))], error=True),
    "pocket_start_reference": dict(features=plate() + [
        Sketch("Under", "XY", [Circle((20, 10), 4)], attachment_offset=(0, 0, -5)),
        Pocket("Pocket", "Under", length=3, start_type="Reference", start_reference=("Pad", "Face6"))]),
    "revolution_start_reference_plane": dict(features=[
        Sketch("Ring", "XZ", rect(5, 0, 15, 10)),
        Revolution("Revolution", "Ring", angle=60.0, start_type="Reference", start_reference="YZ_Plane")]),
    "revolution_start_reference_offset": dict(features=[
        Sketch("Ring", "XZ", rect(5, 0, 15, 10)),
        Revolution("Revolution", "Ring", angle=45.0, start_type="Reference", start_reference="YZ_Plane",
                   start_offset=30.0)]),
    "revolution_start_reference_cylinder": dict(features=[
        Sketch("Post", "XY", [Circle((0, 20), 3)]), Pad("PostPad", "Post", length=10),
        Sketch("Ring", "XZ", rect(18, 2, 22, 4)),
        Revolution("Revolution", "Ring", angle=40.0, start_type="Reference", start_reference=("PostPad", "Face1"))]),
    "groove_start_reference": dict(features=[
        Sketch("Ring", "XZ", rect(5, 0, 15, 10)), Revolution("Revolution", "Ring"),
        Sketch("Notch", "XZ", rect(13, 4, 18, 6)),
        Groove("Groove", "Notch", angle=90.0, start_type="Reference", start_reference="YZ_Plane")]),
    "hole_start_reference_face": dict(features=plate() + [
        Sketch("Under", "XY", [Circle((10, 10), 3), Circle((30, 10), 3)], attachment_offset=(0, 0, -6)),
        Hole("Hole", "Under", diameter=5.0, depth=4.0, start_type="Reference", start_reference=("Pad", "Face6"))]),
    "hole_start_reference_offset": dict(features=plate() + [
        Sketch("Under", "XY", [Circle((10, 10), 3)], attachment_offset=(0, 0, -6)),
        Hole("Hole", "Under", diameter=6.0, depth=3.0, start_type="Reference", start_reference=("Pad", "Face6"),
             start_offset=2.0)]),
    # the line from the profile's centre meets the rod's curved face 24 mm up; 10 back from there is inside the block
    "hole_start_reference_curved": dict(features=[
        Sketch("Rod", "XZ", [Circle((0, 0), 6)]), Pad("RodPad", "Rod", length=20, side_type="Symmetric"),
        Sketch("Block", "XY", rect(-10, -10, 10, 10), attachment_offset=(0, 0, -20)),
        Pad("BlockPad", "Block", length=16),
        Sketch("Under", "XY", [Circle((0, 0), 1)], attachment_offset=(0, 0, -30)),
        Hole("Hole", "Under", diameter=2.0, depth=4.0, reversed=True, start_type="Reference",
             start_reference=("RodPad", "Face1"), start_offset=-10.0)]),
}
