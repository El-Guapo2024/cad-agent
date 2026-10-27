"""The bodies with dress-up features (Fillet, Chamfer, Draft, Thickness) that tests/test_feature_dressup.py builds
with cad_agent.feature and make.py builds in FreeCAD 26.3 (3160daf1e2b6).

CASES: name -> {"features": [...], "params": {...}}, as tests/golden/feature/cases.py. Sub-element names are
FreeCAD's for the base feature's shape (freecad.json also records every base's faces and
edges, so the names here are checked to be the elements their comments say).

FOLLOW: name -> {"features": [...], "edit": [...], "after": [...]}: a body, an edit FreeCAD makes to it in place
(make.py applies "edit" to the open document, so FreeCAD's topological naming sees it as an edit), and the same
body after the edit as a feature list (what the part file holds). make.py records each dress-up's Base as
FreeCAD rewrites it; the test holds feature_dressup.follow() to it.
"""
import importlib.util
import math
from pathlib import Path

# tests/golden/feature/cases.py, loaded by its path: `from cases import` would take whichever golden's cases.py the
# test run imported first. make.py puts this folder and feature on sys.path, so either way still works.
_spec = importlib.util.spec_from_file_location(
    "feature_cases", Path(__file__).resolve().parent.parent / "feature" / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
base_pad, rect, rounded, step = _cases.base_pad, _cases.rect, _cases.rounded, _cases.step

from cad_agent.feature import (Chamfer, Circle, Draft, Fillet, LineSegment, Pad, Pocket,  # noqa: E402
                               Sketch, Thickness)

PI = math.pi

# The 40 x 20 x 5 plate (base_pad), as FreeCAD numbers it (freecad.json "bases"):
#   Face1 x=0, Face2 x=40, Face3 y=0, Face4 y=20, Face5 z=0, Face6 z=5
#   Edge1 (0,0) vertical, Edge2 (40,0) vertical, Edge3 y=0 bottom, Edge4 y=0 top, Edge5 (40,20) vertical,
#   Edge6 x=40 bottom, Edge7 x=40 top, Edge8 (0,20) vertical, Edge9 y=20 bottom, Edge10 y=20 top,
#   Edge11 x=0 bottom, Edge12 x=0 top


def disc():
    """A cylinder r 10, 8 high: Face1 the side, Face2 top, Face3 bottom (as FreeCAD numbers it)."""
    return [Sketch("Sketch", "XY", [Circle((0.0, 0.0), 10.0)]), Pad("Pad", "Sketch", length=8.0)]


def holed():
    """The plate with a 6 mm hole through it."""
    return base_pad() + [Sketch("Hole", "XY", [Circle((20.0, 10.0), 3.0)]),
                         Pocket("Pocket", "Hole", type="ThroughAll", reversed=True)]


def rounded_plate():
    return [Sketch("Sketch", "XY", rounded(0, 0, 40, 30, 5)), Pad("Pad", "Sketch", length=6.0)]


def box():
    """A 30 x 30 x 30 cube, for the thickness cases."""
    return [Sketch("Sketch", "XY", rect(0, 0, 30, 30)), Pad("Pad", "Sketch", length=30.0)]


CASES = {
    # ── Fillet ──
    "fillet_edge": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Edge1"]))]},
    "fillet_edges": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Edge4", "Edge7", "Edge10", "Edge12"]),
                                                      radius=2.0)]},
    "fillet_face": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Face6"]), radius=1.5)]},
    "fillet_edge_and_face": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Edge1", "Face6"]))]},
    "fillet_all_edges": {"features": base_pad() + [Fillet("Fillet", ("Pad", []), radius=1.0, use_all_edges=True)]},
    "fillet_param": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Edge2", "Edge5"]), radius="r * 2")],
                     "params": {"r": 1.25}},
    "fillet_no_refine": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Face6"]), refine=False)]},
    "fillet_disc": {"features": disc() + [Fillet("Fillet", ("Pad", ["Face2"]), radius=2.0)]},
    "fillet_hole": {"features": holed() + [Fillet("Fillet", ("Pocket", ["Edge13", "Edge15"]), radius=0.5)]},
    "fillet_step": {"features": step() + [Fillet("Fillet", ("PocketCavity", ["Face7"]), radius=0.5)]},
    "fillet_rounded": {"features": rounded_plate() + [Fillet("Fillet", ("Pad", ["Face10"]), radius=1.0)]},
    "fillet_twice": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Edge1"]), radius=3.0),
                                               Fillet("Fillet001", ("Fillet", ["Face6"]), radius=1.0)]},
    "fillet_then_pad": {"features": base_pad() + [
        Fillet("Fillet", ("Pad", ["Edge1", "Edge2", "Edge5", "Edge8"]), radius=4.0),
        Sketch("Boss", "XY", [Circle((20.0, 10.0), 4.0)], attachment_offset=(0, 0, 5)),
        Pad("Pad001", "Boss", length=3.0)]},
    "fillet_too_big": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Face6"]), radius=4.0)]},
    "fillet_zero": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Edge1"]), radius=0.0)]},
    "fillet_nothing": {"features": base_pad() + [Fillet("Fillet", ("Pad", []))]},
    # ── Chamfer ──
    "chamfer_edge": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Edge4"]))]},
    "chamfer_face": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Face6"]), size=0.8)]},
    "chamfer_two": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Edge4", "Edge7"]),
                                                      chamfer_type="Two distances", size=1.0, size2=3.0)]},
    "chamfer_two_flip": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Edge4", "Edge7"]),
                                                           chamfer_type="Two distances", size=1.0, size2=3.0,
                                                           flip_direction=True)]},
    "chamfer_angle": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Edge12"]),
                                                        chamfer_type="Distance and Angle", size=2.0, angle=30.0)]},
    "chamfer_angle_flip": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Edge12"]),
                                                             chamfer_type="Distance and Angle", size=2.0,
                                                             angle=30.0, flip_direction=True)]},
    "chamfer_all": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", []), size=0.5, use_all_edges=True)]},
    "chamfer_disc": {"features": disc() + [Chamfer("Chamfer", ("Pad", ["Face3"]), size=1.0)]},
    "chamfer_hole": {"features": holed() + [Chamfer("Chamfer", ("Pocket", ["Edge15"]), size=0.5)]},
    "chamfer_param": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Edge1"]), size="c", size2="c / 2",
                                                        chamfer_type="Two distances")], "params": {"c": 2.0}},
    "chamfer_zero": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Edge1"]), size=0.0)]},
    "chamfer_bad_angle": {"features": base_pad() + [Chamfer("Chamfer", ("Pad", ["Edge1"]),
                                                            chamfer_type="Distance and Angle", angle=180.0)]},
    # ── Draft ──
    "draft_sides": {"features": base_pad() + [Draft("Draft", ("Pad", ["Face1", "Face2", "Face3", "Face4"]),
                                                    angle=5.0, neutral_plane="XY_Plane")]},
    "draft_guess": {"features": base_pad() + [Draft("Draft", ("Pad", ["Face1"]))]},
    "draft_reversed": {"features": base_pad() + [Draft("Draft", ("Pad", ["Face1", "Face2"]), angle=3.0,
                                                       neutral_plane="XY_Plane", reversed=True)]},
    "draft_top_plane": {"features": base_pad() + [Draft("Draft", ("Pad", ["Face3", "Face4"]), angle=4.0,
                                                        neutral_plane=("Pad", "Face6"))]},
    "draft_pull_axis": {"features": base_pad() + [Draft("Draft", ("Pad", ["Face1"]), angle=6.0,
                                                        neutral_plane="XY_Plane", pull_direction="Z_Axis")]},
    "draft_pull_edge": {"features": base_pad() + [Draft("Draft", ("Pad", ["Face2"]), angle=2.0,
                                                        neutral_plane=("Pad", "Edge6"),
                                                        pull_direction=("Pad", "Edge2"))]},
    "draft_disc": {"features": disc() + [Draft("Draft", ("Pad", ["Face1"]), angle=10.0, neutral_plane="XY_Plane")]},
    "draft_none": {"features": base_pad() + [Draft("Draft", ("Pad", []))]},
    "draft_negative": {"features": base_pad() + [Draft("Draft", ("Pad", ["Face3"]), angle=-4.0,
                                                       neutral_plane="XY_Plane")]},
    # ── Thickness ──
    "thickness_top": {"features": box() + [Thickness("Thickness", ("Pad", ["Face6"]), value=2.0)]},
    "thickness_outwards": {"features": box() + [Thickness("Thickness", ("Pad", ["Face6"]), value=2.0,
                                                          reversed=False)]},
    "thickness_outwards_intersection": {"features": box() + [Thickness("Thickness", ("Pad", ["Face6"]), value=2.0,
                                                                       reversed=False, join="Intersection")]},
    "thickness_two_faces": {"features": box() + [Thickness("Thickness", ("Pad", ["Face6", "Face1"]), value=1.5)]},
    "thickness_pipe": {"features": box() + [Thickness("Thickness", ("Pad", ["Face6"]), value=2.0, mode="Pipe")]},
    "thickness_recto_verso": {"features": box() + [Thickness("Thickness", ("Pad", ["Face6"]), value=2.0,
                                                             mode="RectoVerso")]},
    "thickness_intersection": {"features": box() + [Thickness("Thickness", ("Pad", ["Face6"]), value=2.0,
                                                              intersection=True)]},
    "thickness_disc": {"features": disc() + [Thickness("Thickness", ("Pad", ["Face2"]), value=1.0)]},
    "thickness_param": {"features": box() + [Thickness("Thickness", ("Pad", ["Face5"]), value="wall")],
                        "params": {"wall": 3.0}},
    "thickness_none": {"features": box() + [Thickness("Thickness", ("Pad", []))]},
    "thickness_no_refine": {"features": box() + [Thickness("Thickness", ("Pad", ["Face6"]), value=2.0,
                                                           refine=False)]},
    # ── together ──
    "pad_fillet_chamfer": {"features": base_pad() + [Fillet("Fillet", ("Pad", ["Edge1", "Edge2"]), radius=3.0),
                                                     Chamfer("Chamfer", ("Fillet", ["Face6"]), size=0.5)]},
    "draft_then_fillet": {"features": base_pad() + [
        Draft("Draft", ("Pad", ["Face1", "Face2", "Face3", "Face4"]), angle=5.0, neutral_plane="XY_Plane"),
        Fillet("Fillet", ("Draft", ["Face6"]), radius=1.0)]},
    "base_box_fillet": {"features": [Fillet("Fillet", ("BaseFeature", ["Edge1", "Edge3"]), radius=2.0)],
                        "base": ("box", (0, 0, 0), (20, 10, 6))},
}

# ── edits that renumber the base's elements ──
# "edit" ops make.py applies in FreeCAD: ("reorder", sketch, permutation of the geometry), ("set", feature,
# property, value), ("append_circle", sketch, (cx, cy), r).


def _plate_lines():
    return rect(0, 0, 40, 20)


def _plate(lines, length=5.0):
    return [Sketch("Sketch", "XY", lines), Pad("Pad", "Sketch", length=length)]


_L = _plate_lines()
FOLLOW = {
    # FreeCAD: Edge7 (x=40 top) is Edge4 once the sketch's lines start at the second one
    "reorder_fillet": {
        "features": _plate(_L) + [Fillet("Fillet", ("Pad", ["Edge7"]), radius=2.0)],
        "edit": [("reorder", "Sketch", [1, 2, 3, 0])],
        "after": _plate(_L[1:] + _L[:1]) + [Fillet("Fillet", ("Pad", ["Edge7"]), radius=2.0)]},
    "reorder_chamfer_face": {
        "features": _plate(_L) + [Chamfer("Chamfer", ("Pad", ["Face2", "Edge3"]), size=1.0)],
        "edit": [("reorder", "Sketch", [2, 3, 0, 1])],
        "after": _plate(_L[2:] + _L[:2]) + [Chamfer("Chamfer", ("Pad", ["Face2", "Edge3"]), size=1.0)]},
    "length_fillet": {
        "features": _plate(_L) + [Fillet("Fillet", ("Pad", ["Edge1", "Edge12", "Face6"]), radius=1.0)],
        "edit": [("set", "Pad", "Length", 8.0)],
        "after": _plate(_L, 8.0) + [Fillet("Fillet", ("Pad", ["Edge1", "Edge12", "Face6"]), radius=1.0)]},
    "hole_thickness": {
        "features": _plate(_L) + [Thickness("Thickness", ("Pad", ["Face6"]), value=1.0)],
        "edit": [("append_circle", "Sketch", (20.0, 10.0), 3.0)],
        "after": _plate(_L + [Circle((20.0, 10.0), 3.0)]) + [Thickness("Thickness", ("Pad", ["Face6"]), value=1.0)]},
    "reorder_draft": {
        "features": _plate(_L) + [Draft("Draft", ("Pad", ["Face1", "Face3"]), angle=3.0, neutral_plane="XY_Plane")],
        "edit": [("reorder", "Sketch", [3, 0, 1, 2])],
        "after": _plate(_L[3:] + _L[:3]) + [Draft("Draft", ("Pad", ["Face1", "Face3"]), angle=3.0,
                                                  neutral_plane="XY_Plane")]},
}
