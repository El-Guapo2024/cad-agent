"""The bodies tests/test_feature_pdlast.py builds with cad_agent.feature and make.py builds in FreeCAD: PartDesign's
last commands, each a feature of a FEATURES list (Involute Gear, Sprocket; Defeaturing; Sub-Shape Binder).

Each case is the same FEATURES list for both, as tests/golden/feature/cases.py has them. CASES[name] is
{"features": [...], "params": {...} (optional)}. The groups (GEAR, ...) say which feature a case is about, so a test of
one feature runs its own cases.
"""
from cad_agent.feature import Constraint, InvoluteGear, LineSegment, Pad, Pocket, Sketch, Sprocket


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


def plate(x0, y0, w, h, length=5.0, name="Sketch", pad="Pad"):
    return [Sketch(name, "XY", rect(x0, y0, x0 + w, y0 + h), rect_constraints(0, float(w), float(h))),
            Pad(pad, name, length=length)]


# ── Involute Gear, Sprocket (InvoluteGearFeature.py, SprocketFeature.py) ─────────────────────────────────────────────
GEAR = {
    "gear_default": {"features": [InvoluteGear("InvoluteGear"), Pad("Pad", "InvoluteGear", length=5.0)]},
    "gear_small_low_precision": {"features": [
        InvoluteGear("InvoluteGear", number_of_teeth=9, modules=1.0, high_precision=False),
        Pad("Pad", "InvoluteGear", length=3.0)]},
    "gear_flank_lines": {"features": [            # few teeth: the base circle is above the fillet, the flank a line
        InvoluteGear("InvoluteGear", number_of_teeth=12, modules=2.0, pressure_angle=14.5),
        Pad("Pad", "InvoluteGear", length=4.0)]},
    "gear_internal": {"features": [
        InvoluteGear("InvoluteGear", number_of_teeth=40, modules=1.5, external_gear=False, addendum_coefficient=0.6),
        Pad("Pad", "InvoluteGear", length=2.0)]},
    "gear_internal_in_ring": {"features": [      # an internal gear cut through a plate, as a ring gear is made
        *plate(-40, -40, 80, 80, 6.0),
        InvoluteGear("InvoluteGear", number_of_teeth=40, modules=1.5, external_gear=False, addendum_coefficient=0.6),
        Pocket("Pocket", "InvoluteGear", type="ThroughAll", reversed=True)]},
    "gear_shifted_no_fillet": {"features": [
        InvoluteGear("InvoluteGear", number_of_teeth=17, modules=3.0, profile_shift_coefficient=0.4,
                     root_fillet_coefficient=0.0, dedendum_coefficient=1.4),
        Pad("Pad", "InvoluteGear", length=6.0)]},
    "gear_params": {"params": {"mod": 1.25, "teeth": 30.0, "width": 8.0}, "features": [
        InvoluteGear("InvoluteGear", number_of_teeth="teeth", modules="mod", pressure_angle="10 + 10"),
        Pad("Pad", "InvoluteGear", length="width")]},
    "gear_on_xz": {"features": [
        InvoluteGear("InvoluteGear", number_of_teeth=20, modules=1.0, attachment_support=[("XZ_Plane", "")],
                     map_mode="FlatFace", attachment_offset=((5.0, 3.0, 2.0), (30.0, 0.0, 0.0))),
        Pad("Pad", "InvoluteGear", length=4.0, reversed=True)]},
    "gear_pocket_symmetric": {"features": [
        *plate(-30, -30, 60, 60, 10.0),
        InvoluteGear("InvoluteGear", number_of_teeth=15, modules=1.5, attachment_support=[("Pad", "Face6")],
                     map_mode="FlatFace"),
        Pocket("Pocket", "InvoluteGear", length=4.0)]},
    "sprocket_default": {"features": [Sprocket("Sprocket"), Pad("Pad", "Sprocket", length=2.794)]},
    "sprocket_ansi40": {"features": [
        Sprocket("Sprocket", number_of_teeth=17, pitch=12.7, roller_diameter=7.9248, thickness=7.2136,
                 sprocket_reference="ANSI 40"),
        Pad("Pad", "Sprocket", length=7.2136)]},
    "sprocket_few_teeth": {"features": [
        Sprocket("Sprocket", number_of_teeth=9, pitch=8.0, roller_diameter=5.0),
        Pad("Pad", "Sprocket", length=3.0, side_type="Symmetric")]},
}

CASES = {**GEAR}
