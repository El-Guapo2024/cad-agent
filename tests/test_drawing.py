"""`cad drawing`: a plate as a dimensioned drawing, and the gates that keep a wrong one from being written.

Layers, each with its PASS, FAIL and UNCHECKED paths:

  the plate     what `plate.analyse` recognises (rounded outline, holes, slots, windows, on any thin axis) and the
                parts it refuses with the sentence that says why (a pocket, a chamfer, a counterbore, a cross hole, an
                L-shaped outline, a disc, a cutout of free form, a slanted slot, two pieces)
  the views     OCCT's hidden line removal as TechDraw uses it: visible lines solid, hidden dashed, the same lines
                once however many times OCCT gives them, first and third angle
  the sheet     which sheet and scale, the ordinates, the letters and callouts, the title block and the stamp
  the files     the DXF read back by ezdxf, the SVG parsed as XML, the PDF by this suite and by PyMuPDF if it is there,
                and every byte pinned: the same on OCCT 7.9 and 8.0
  the gates     each row of check.py fails when the sheet is damaged in the way it holds against
  the command   `cad drawing` and every exit code, on scratch copies of a project; the stamp; the commit
  the hook      `shop_drawings`, and `cad shop` writing drawings/ and the manifest listing them
  the evals     the plates among the 10 reference designs
"""
import functools
import hashlib
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from build123d import (Axis, Box, Cone, Cylinder, Edge, Ellipse, GeomType, Polygon, Pos, Rectangle, RectangleRounded, Rot,
                       SlotOverall, Sphere, chamfer, extrude, fillet)

from cad_agent import cli, dxf, evals, verify
from cad_agent import state as st
# the modules of cad_agent/drawing under the short names this file uses for them
from cad_agent.drawing import arrange as layout, hlr as V, onesheet as draw, paper as S, platefit as P, readback as check
from cad_agent.drawing import writers as render
from cad_agent.registry import Row
from cad_agent.runner import approve_views, check_all
from test_bom import BLOCK, PANEL, SLUG, make_workshop, workshop  # noqa: F401 (the workshop fixture)

REPO = Path(__file__).resolve().parent.parent


def at(x, y, shape):
    return Pos(x, y, 0) * shape


def thru(d, depth=12):
    return Cylinder(d / 2.0, depth)


def plate(t=4.0):
    """40 x 20 with two M3 holes."""
    return Box(40, 20, t) - Pos(-10, 0, 0) * thru(3.4) - Pos(10, 0, 0) * thru(3.4)


def nema():
    """70 x 46 x 4 with a pilot bore and two sizes of bolt hole: the shape of the eval's motor plate."""
    p = Box(70, 46, 4) - Pos(10, 0, 0) * thru(22.5)
    for x, y in ((25.5, 15.5), (25.5, -15.5), (-5.5, 15.5), (-5.5, -15.5)):
        p -= Pos(x, y, 0) * thru(3.4)
    for y in (15, -15):
        p -= Pos(-25, y, 0) * thru(5.5)
    return p


def panel():
    """100 x 60 x 3 with R5 corners, four M3 holes, a round hole, a rounded window and a slot."""
    p = fillet(Box(100, 60, 3).edges().filter_by(Axis.Z), 5.0)
    for sx in (-1, 1):
        for sy in (-1, 1):
            p -= Pos(sx * 45, sy * 25, 0) * thru(3.4)
    p -= Pos(-22.5, 0, 0) * thru(16)
    p -= Pos(17.5, 0, 0) * extrude(RectangleRounded(27.2, 19.76, 0.4), 6, both=True)
    p -= Pos(-5, -20, 0) * extrude(SlotOverall(20, 6), 6, both=True)
    return p


def meta(part="p", stamp="NOT VERIFIED", **kw):
    return {"part": part, "project": "scratch", "material": "aluminium", "process": "cnc", "commit": "cd05de0a1b2c3d4e",
            "dirty": False, "stamp": stamp, **kw}


@functools.lru_cache(maxsize=None)
def made(name: str, angle: str = "first", stamp: str | None = "NOT VERIFIED", size=None, scale=None) -> draw.Made:
    solid = {"plate": plate, "nema": nema, "panel": panel}[name]()
    return draw.make(name, solid, meta(name, stamp), angle, size, scale)


def states(rows) -> dict:
    return {r.rule: r.state for r in rows}


def entities(doc: render.Doc, layer: str, kind) -> list:
    return [g for l, g in doc.items if l == layer and isinstance(g, kind)]


# ─── The plate ───────────────────────────────────────────────────────────────

def test_a_plate_is_recognised_with_its_outline_and_every_cutout():
    pl = P.analyse(panel())
    assert (pl.width, pl.height, pl.thickness, pl.corner_r) == pytest.approx((100, 60, 3, 5))
    assert pl.axis == 2 and (pl.lo, pl.hi) == ((-50.0, -30.0), (50.0, 30.0))
    assert sorted((h.u, h.v, h.dia) for h in pl.holes) == [pytest.approx(t) for t in sorted(   # one approx per row:
        [(-45, -25, 3.4), (-45, 25, 3.4), (45, -25, 3.4), (45, 25, 3.4), (-22.5, 0, 16)])]    # pytest 9.2 refuses nesting
    assert [(s.u, s.v, s.width, s.length, s.along) for s in pl.slots] == [(-5.0, -20.0, 6.0, 20.0, "u")]
    assert [(w.u, w.v, w.w, w.h, w.r) for w in pl.windows] == [pytest.approx((17.5, 0, 27.2, 19.76, 0.4))]
    assert pl.describe() == "100 x 60 x 3 mm, thin in z, corners R5, 5 holes, 1 slot, 1 window"
    assert pl.n_range == pytest.approx((-1.5, 1.5)) and "end face" in pl.source


def test_a_slot_along_either_axis_and_an_obround_that_is_a_circle():
    along_v = Box(60, 30, 3) - Pos(5, 0, 0) * extrude(SlotOverall(20, 6, rotation=90), 6, both=True)
    assert [(s.width, s.length, s.along) for s in P.analyse(along_v).slots] == [(6.0, 20.0, "v")]
    round_ = Box(60, 30, 3) - Pos(5, 0, 0) * extrude(SlotOverall(6, 6), 6, both=True)
    assert [(h.dia) for h in P.analyse(round_).holes] == [6.0]


@pytest.mark.parametrize("axis,make", [
    ("z", lambda: Box(60, 30, 3) - Pos(10, 5, 0) * Cylinder(2, 5)),
    ("x", lambda: Box(3, 60, 30) - Pos(0, 10, 5) * Rot(Y=90) * Cylinder(2, 5)),
    ("y", lambda: Box(60, 3, 30) - Pos(10, 0, 5) * Rot(X=90) * Cylinder(2, 5)),
])
def test_a_plate_is_the_same_drawing_whichever_axis_it_is_thin_in(axis, make):
    # the face is looked at from the positive side of its thin axis, as the laser DXF is: a hole 10 across and 5 up
    # is there on every one, and the three sheets are the same bytes
    solid = make()
    pl = P.analyse(solid)
    assert pl.axis == "xyz".index(axis) and (pl.width, pl.height, pl.thickness) == pytest.approx((60, 30, 3))
    one = draw.make("p", solid, meta(), "first")
    assert all(r.state == "PASS" for r in one.rows), [r for r in one.rows if r.state != "PASS"]
    ref = draw.make("p", Box(60, 30, 3) - Pos(10, 5, 0) * Cylinder(2, 5), meta(), "first")
    assert one.files == ref.files


UNFIT = [
    ("a pocket", lambda: plate() - Pos(0, 0, 1) * Box(10, 6, 2), "a plane across z at z = 0.000 mm, which is neither end of the part (a pocket floor, a step or a boss)"),
    ("a blind hole", lambda: plate() - Pos(0, 0, 1.5) * Cylinder(1, 2), "pocket floor"),
    ("a counterbore", lambda: plate() - Pos(-10, 0, 1.5) * Cylinder(3, 3), "pocket floor"),
    ("a chamfer", lambda: chamfer(plate().faces().sort_by(Axis.Z)[-1].edges(), 0.5), "a plane slanted to z (a chamfer or a draft)"),
    ("a countersink", lambda: plate() - Cone(1.5, 2.5, 6.0), "a cone (a chamfer, a countersink or a taper)"),
    ("a cross hole", lambda: plate() - Rot(Y=90) * Cylinder(1, 60), "a cylinder across z, not along it (a cross hole)"),
    ("a dome", lambda: plate() + Pos(0, 0, 2) * Sphere(3), "a sphere (a dome or a ball end)"),
    ("a rounded hole edge", lambda: fillet(plate().faces().sort_by(Axis.Z)[-1].edges().filter_by(GeomType.CIRCLE)[:1], 0.4),
     "a torus (a fillet)"),
    ("a tilted plate", lambda: Rot(X=30) * plate(), "slanted"),
]


@pytest.mark.parametrize("what,make,said", UNFIT)
def test_a_part_that_needs_a_section_is_unfit_and_says_what_it_has(what, make, said):
    with pytest.raises(P.Unfit, match="it is not a prism along") as e:
        P.analyse(make())
    assert said in str(e.value) and "anything else needs a section to be understood" in str(e.value), what


def test_an_outline_that_is_not_a_rectangle_is_unfit():
    for what, solid, said in [
        ("an L", Box(40, 20, 4) + Pos(10, 15, 0) * Box(20, 10, 4), "its outline is not a rectangle with square or equally rounded corners"),
        ("a disc", Cylinder(20, 4), "its outline is not a rectangle"),
        ("a notch", Box(40, 20, 4) - Pos(20, 0, 0) * thru(6), "its outline is not a rectangle"),
        ("a plate turned 45 degrees in its plane", Rot(Z=45) * plate(), "its outline is not a rectangle"),
        ("one rounded corner", fillet(Box(40, 20, 4).edges().filter_by(Axis.Z)[:1], 5.0), "its outline is not a rectangle"),
    ]:
        with pytest.raises(P.Unfit, match=said):
            P.analyse(solid)
        assert what


def test_a_cutout_that_is_nothing_the_sheet_dimensions_is_unfit():
    triangle = extrude(Polygon((0, 0), (8, 0), (0, 6), align=None), 8, both=True)
    for what, cutout in [("a triangle", Pos(-5, -3, 0) * triangle), ("an ellipse", extrude(Ellipse(6, 3), 8, both=True)),
                         ("a slot at 30 degrees", extrude(SlotOverall(14, 5, rotation=30), 8, both=True))]:
        with pytest.raises(P.Unfit, match="it has a cutout that is not a round hole, a slot or a rectangle with equal corners"):
            P.analyse(Box(60, 30, 4) - cutout)
        assert what


def test_two_pieces_and_a_part_whose_mid_plane_misses_the_material_are_unfit():
    with pytest.raises(P.Unfit, match="its outline is 2 separate pieces"):
        P.analyse(Pos(-15, 0, 0) * Box(10, 10, 4) + Pos(15, 0, 0) * Box(10, 10, 4))
    with pytest.raises(P.Unfit, match="its mid-plane cuts no material"):
        P.analyse(Pos(0, 0, -5) * Box(20, 20, 1) + Pos(0, 0, 5) * Box(20, 20, 1))


def test_a_size_iso_2768_gives_no_tolerance_for_is_said_on_the_sheet_and_not_promised():
    # the R0.4 of a laser-cut window, a sheet under half a millimetre, a hole as small, a plate over four metres
    assert "NO GENERAL TOLERANCE: WINDOW CORNER R0.4 (UNDER 0.5)" in made("panel", stamp=None).sheet.notes
    thin = draw.make("thin", Box(40, 20, 0.3) - thru(0.4), meta("thin", None), "first")
    assert thin.judged() and thin.sheet.notes[-2:] == ["NO GENERAL TOLERANCE: THICKNESS 0.3 (UNDER 0.5)",
                                                       "NO GENERAL TOLERANCE: HOLE %%c0.4 (UNDER 0.5)"]
    long_ = draw.make("long", Box(4200, 100, 5), meta("long", None), "first")
    assert long_.judged() and long_.sheet.notes[-1] == "NO GENERAL TOLERANCE: WIDTH 4200 (OVER 4000)" and long_.sheet.size == "A0"
    assert P.uncovered(P.analyse(Box(40, 20, 0.5) - thru(0.5))) == [] and P.uncovered(P.analyse(Box(4000, 100, 5))) == []        # the table's own ends
    assert P.uncovered(P.analyse(fillet(Box(40, 20, 4).edges().filter_by(Axis.Z), 0.3))) == [("OUTLINE CORNER R", 0.3, "UNDER 0.5")]
    slot_and_window = Box(60, 30, 4) - extrude(SlotOverall(20, 0.4), 6, both=True) - Pos(20, 8, 0) * extrude(Rectangle(10, 0.4), 6, both=True)
    assert [(w, v) for w, v, _ in P.uncovered(P.analyse(slot_and_window))] == [("SLOT WIDTH", 0.4), ("WINDOW HEIGHT", 0.4)]
    # a sheet that leaves the note out, or says one where none is due, fails its gate
    doc = render.read(thin.files["dxf"])
    gone = doc._replace(items=[i for i in doc.items if not (isinstance(i[1], S.Text) and i[1].value.startswith("NO GENERAL"))])
    complaint(check.sheet_row("thin", thin.plate, gone, thin.files["dxf"], meta("thin", None), "first", None),
              "the notes do not say 'NO GENERAL TOLERANCE: THICKNESS 0.3 (UNDER 0.5)'")
    plain = made("plate", stamp=None)
    pdoc = render.read(plain.files["dxf"])
    stray = pdoc._replace(items=pdoc.items + [("TEXT", S.Text((10.0, 100.0), 3.5, "NO GENERAL TOLERANCE: X 1 (UNDER 0.5)"))])
    complaint(check.sheet_row("plate", plain.plate, stray, plain.files["dxf"], meta("plate", None), "first", None),
              "the notes say a size has no general tolerance and none lacks it")


def test_the_hole_finder_and_the_outline_must_agree_or_the_plate_is_not_drawn(monkeypatch):
    from cad_agent import spec
    real = spec.holes
    solid = plate()
    monkeypatch.setattr(spec, "holes", lambda s: real(s)[:1])
    with pytest.raises(P.Unfit, match="the outline has 2 round holes and the hole finder 1"):
        P.analyse(solid)
    monkeypatch.setattr(spec, "holes", lambda s: [{**real(s)[0], "bores": [3.4, 6.0]}])
    with pytest.raises(P.Unfit, match="a stepped hole"):
        P.analyse(solid)
    from build123d import Vector
    monkeypatch.setattr(spec, "holes", lambda s: [{**real(s)[0], "dir": Vector(1, 0, 0)}])
    with pytest.raises(P.Unfit, match="does not run along the thin axis"):
        P.analyse(solid)
    slot = Box(60, 30, 3) - extrude(SlotOverall(20, 6), 6, both=True)
    monkeypatch.setattr(spec, "holes", lambda s: [])
    with pytest.raises(P.Unfit, match="the outline has 1 slots and the hole finder 0"):
        P.analyse(slot)


def test_a_section_that_cannot_be_made_or_faces_that_cannot_be_sorted_are_unfit_not_a_crash(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(dxf, "cut_at", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the kernel refused")))
        with pytest.raises(P.Unfit, match="its mid-plane section could not be made: RuntimeError: the kernel refused"):
            P.analyse(plate())
    with monkeypatch.context() as m:
        m.setattr(dxf, "faces_report", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no faces")))
        with pytest.raises(P.Unfit, match="its faces could not be sorted: RuntimeError: no faces"):
            P.analyse(plate())


def test_faces_the_kernel_gives_as_b_spline_surfaces_are_unfit_since_no_end_plane_is_there_to_read():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
    from build123d import Solid
    nurbs = Solid(BRepBuilderAPI_NurbsConvert(plate().wrapped, True).Shape())
    with pytest.raises(P.Unfit, match="its end faces across z are not planes the outline can be read from"):
        P.analyse(nurbs)


def test_recognising_a_loop_by_building_what_it_should_be():
    r = P.rounded_rectangle(0, 0, 20, 10, 2)
    assert P.recognise(r, True) == ("rect", (0, 0, 20, 10), 2) and len(r) == 8
    assert P.recognise(P.rounded_rectangle(0, 0, 20, 10, 0), True)[0] == "rect"
    assert P.recognise(P.obround(0, 0, 20, 6), False)[0] == "obround" and P.recognise(P.obround(0, 0, 6, 20), False)[0] == "obround"
    assert P.recognise(P.obround(0, 0, 6, 6), False) == ("round", (0, 0, 6, 6), 6)
    assert P.recognise(P.rounded_rectangle(0, 0, 20, 10, 0)[:3], False) is None                # a side missing
    half = [dxf.Arc((0, 0), 3, 0.0, 90.0), dxf.Arc((0, 0), 3, 90.0, 180.0), dxf.Arc((0, 0), 3, 180.0, 0.0)]
    assert [type(p).__name__ for p in P.merged(half)] == ["Circle"]                              # a circle cut in three is one
    assert P.same_entities([dxf.Line((0, 0), (1, 0))], [dxf.Line((0, 0), (1.00005, 0))]) and not P.same_entities(
        [dxf.Line((0, 0), (1, 0))], [dxf.Circle((0, 0), 1)])


def test_a_plate_rebuilt_from_its_numbers_is_the_plate_and_a_wrong_number_is_not(monkeypatch):
    pl = P.analyse(panel())
    values = check.values_of(pl)
    diff, _ = P.reconstruct(pl, values)
    assert diff < 1e-6
    assert check.dimensions_row("p", pl).state == "PASS"
    moved = {**values, "holes": [(u + 1.0, v, d) if i == 0 else (u, v, d) for i, (u, v, d) in enumerate(values["holes"])]}
    assert P.reconstruct(pl, moved)[0] > 5.0
    for what, wrong in [("a hole left out", {**values, "holes": values["holes"][1:]}),
                        ("a hole made a window", {**values, "windows": values["windows"] + [(20, 20, 3.4, 3.4, 0)]}),
                        ("a hole too big", {**values, "holes": [(u, v, d + 0.5) for u, v, d in values["holes"]]}),
                        ("corners too round", {**values, "r": 6.0}),
                        ("a slot turned", {**values, "slots": [(u, v, w, l, "v") for u, v, w, l, _ in values["slots"]]})]:
        monkeypatch.setattr(check, "values_of", lambda plate, wrong=wrong: wrong)
        got = check.dimensions_row("p", pl)
        assert got.state == "FAIL" and "differs from the solid's end face" in got.measured, what
    monkeypatch.setattr(check, "values_of", lambda plate: (_ for _ in ()).throw(RuntimeError("no sketch")))
    got = check.dimensions_row("p", pl)
    assert got.state == "UNCHECKED" and "RuntimeError: no sketch" in got.measured


# ─── The views ───────────────────────────────────────────────────────────────

def test_a_plate_seen_face_on_has_its_outline_and_holes_visible_and_nothing_hidden():
    solid = plate()
    pl = P.analyse(solid)
    face, side = draw.views_of(solid, pl, "first")
    assert face.hidden == [] and face.box == (-20.0, -10.0, 20.0, 10.0)
    assert sorted(type(p).__name__ for p in face.visible) == ["Circle", "Circle", "Line", "Line", "Line", "Line"]
    assert [(p.c, p.r) for p in face.visible if isinstance(p, dxf.Circle)] == [((-10.0, 0.0), 1.7), ((10.0, 0.0), 1.7)]


def test_the_thickness_view_shows_the_holes_dashed_and_the_outline_solid():
    solid = plate()
    face, side = draw.views_of(solid, P.analyse(solid), "first")
    assert side.box == (-2.0, -10.0, 2.0, 10.0) and len(side.visible) == 4                      # the edge-on circles are covered
    assert [(p.a, p.b) for p in side.hidden] == [((-2.0, -1.7), (2.0, -1.7)), ((-2.0, 1.7), (2.0, 1.7))]
    # and they are lines the whole thickness long, at the two edges of the hole: through
    assert side.seconds > 0 and face.seconds > 0


def test_the_visible_smooth_edges_are_drawn_and_the_hidden_ones_are_not():
    # TechDraw's defaults: SmoothVisible on, SmoothHidden off (DrawViewPart.cpp:134, 143; GeometryObject.cpp:264-279).
    # The R5 corners of the panel meet its end face tangent 5 mm in from each side: two lines across the side view. The
    # rounded window and slot meet their flats tangent behind the end face (hidden smooth), and the face view sees every
    # tangent edge end on, as a point: neither is drawn
    solid = panel()
    face, side = draw.views_of(solid, P.analyse(solid), "first")
    assert face.smooth == []
    assert [(p.a, p.b) for p in side.smooth] == [((-1.5, -25.0), (1.5, -25.0)), ((-1.5, 25.0), (1.5, 25.0))]
    assert not set(side.smooth) & set(side.visible)
    plain = plate()
    assert all(v.smooth == [] for v in draw.views_of(plain, P.analyse(plain), "first"))        # a box has no tangent faces


def test_first_angle_looks_from_the_left_and_third_from_the_right():
    # TechDraw's DrawProjGroup::getViewIndex: the view from the left stands to the right of the front view in first angle,
    # the view from the right in third. A plate standing at z = 8 to 12 shows which way x runs in each
    solid = Pos(0, 0, 10) * plate()
    pl = P.analyse(solid)
    assert pl.n_range == pytest.approx((8, 12))
    first = draw.views_of(solid, pl, "first")[1]
    third = draw.views_of(solid, pl, "third")[1]
    assert first.name == "left" and third.name == "right"
    assert first.box == (8.0, -10.0, 12.0, 10.0) and third.box == (-12.0, -10.0, -8.0, 10.0)


def test_a_view_is_the_same_lines_every_time_and_on_either_kernel():
    solid = nema()
    pl = P.analyse(solid)
    a, b = draw.views_of(solid, pl, "first"), draw.views_of(solid, pl, "first")
    assert [x[:2] + (x.box,) for x in a] == [x[:2] + (x.box,) for x in b]
    assert all(p == q for p, q in zip(a[0].visible, b[0].visible))
    face, side = a
    assert len(face.visible) == 11 and face.hidden == [] and len(side.visible) == 4 and len(side.hidden) == 10


def test_coincident_lines_and_arcs_are_joined_and_a_hidden_line_is_cut_where_a_visible_one_covers_it():
    L, A = dxf.Line, dxf.Arc
    # two touching pieces and a duplicate are one line; a gap is not
    assert V.canonical([L((0, 0), (5, 0)), L((5, 0), (10, 0)), L((2, 0), (3, 0)), L((12, 0), (14, 0))]) == [
        L((0.0, 0.0), (10.0, 0.0)), L((12.0, 0.0), (14.0, 0.0))]
    assert V.canonical([L((0, 0), (0, 0))]) == []                                              # a point is nothing
    # two half turns are a circle; arcs that meet across 0 degrees are one arc
    assert V.canonical([A((0, 0), 2, 0.0, 180.0), A((0, 0), 2, 180.0, 0.0)]) == [dxf.Circle((0.0, 0.0), 2.0)]
    assert V.canonical([A((0, 0), 2, 270.0, 0.0), A((0, 0), 2, 0.0, 90.0)]) == [A((0.0, 0.0), 2.0, 270.0, 90.0)]
    hidden = V.canonical([L((0, 0), (10, 0)), A((0, 0), 5, 0.0, 180.0)])
    visible = [L((3, 0), (6, 0)), A((0, 0), 5, 0.0, 90.0)]
    assert V.cover(hidden, visible) == [A((0.0, 0.0), 5.0, 90.0, 180.0), L((0.0, 0.0), (3.0, 0.0)), L((6.0, 0.0), (10.0, 0.0))]
    assert V.cover(hidden, hidden) == []                                                        # all of it is covered


def test_a_curve_that_is_a_straight_line_gone_along_and_back_is_the_line():
    spline = Edge.make_spline([(0, 0), (5, 0), (10, 0)])
    assert V.entities(spline) == [dxf.Line((0.0, 0.0), (10.0, 0.0))]
    bent = Edge.make_spline([(0, 0), (5, 3), (10, 0)])
    assert [type(p).__name__ for p in V.entities(bent)] in (["Spline"], ["Poly"])


# ─── The sheet ───────────────────────────────────────────────────────────────

def test_the_sheet_and_scale_are_the_smallest_sheet_that_holds_the_views_at_the_largest_scale():
    def pick(w, h, t=3.0):
        solid = Box(w, h, t)
        pl = P.analyse(solid)
        face, side = draw.views_of(solid, pl, "first")
        sh = layout.build(pl, face, side, meta(stamp=None))
        return sh.size, S.scale_text(sh.scale)

    assert pick(10, 10) == ("A4", "5:1")                                            # not bigger than 5:1 of itself
    assert pick(70, 46) == ("A4", "2:1")
    assert pick(100, 60) == ("A4", "1:1")
    assert pick(250, 150)[0] == "A3" and pick(250, 150)[1] == "1:1"
    assert pick(500, 300)[0] == "A2"
    assert pick(2400, 1200, 5)[0] == "A0" and pick(2400, 1200, 5)[1] == "1:5"        # too big at 1:1: A0, reduced


def test_a_sheet_or_a_scale_that_was_asked_for_is_used_or_the_plate_does_not_fit():
    solid = Box(70, 46, 4)
    pl = P.analyse(solid)
    face, side = draw.views_of(solid, pl, "first")
    sh = layout.build(pl, face, side, meta(stamp=None), size="A3")
    assert (sh.size, sh.scale) == ("A3", (2, 1))                                    # the largest that fits A3 (5:1 is 350 mm wide)
    sh = layout.build(pl, face, side, meta(stamp=None), scale=(1, 5))
    assert (sh.size, sh.scale) == ("A4", (1, 5))
    with pytest.raises(layout.DoesNotFit, match="do not fit A4 at 20:1"):
        layout.build(pl, face, side, meta(stamp=None), size="A4", scale=(20, 1))
    assert S.parse_scale("1:2") == (1, 2) and S.parse_scale("5:1") == (5, 1)
    for bad in ("1:3", "a:b", "12", "3:1"):
        with pytest.raises(ValueError):
            S.parse_scale(bad)


def test_the_cutouts_are_lettered_by_kind_and_size_and_the_notes_say_what_each_is():
    got = made("panel", stamp=None)
    assert got.sheet.notes == ["A  4X %%c3.4 THRU", "B  %%c16 THRU", "C  SLOT 6 X 20 THRU", "D  WINDOW 27.2 X 19.76 CORNERS R0.4 THRU",
                               "ALL OUTLINE CORNERS R5", "ORDINATES FROM LOWER LEFT CORNER", "DIMENSIONS IN mm", "GENERAL TOLERANCES ISO 2768-m",
                               "NO GENERAL TOLERANCE: WINDOW CORNER R0.4 (UNDER 0.5)"]
    groups = [d for d in got.sheet.dims if d["kind"] == "group"]
    assert [(d["tag"], d["what"], d["count"]) for d in groups] == [("A", "hole", 4), ("B", "hole", 1), ("C", "slot", 1), ("D", "window", 1)]
    doc = render.read(got.files["dxf"])
    tags = sorted(g.value for _, g in doc.items if isinstance(g, S.Text) and len(g.value) == 1 and g.value in S.TAGS)
    assert tags == ["A"] * 4 + ["B", "C", "D"]                                       # a letter on every cutout


def test_slots_of_one_size_are_one_group_whichever_way_they_lie_and_windows_are_not():
    solid = Box(80, 40, 3) - Pos(-20, 0, 0) * extrude(SlotOverall(20, 6), 6, both=True) - Pos(20, 0, 0) * extrude(SlotOverall(20, 6, rotation=90), 6, both=True)
    got = draw.make("s", solid, meta("s", None), "first")
    assert got.judged() and got.sheet.notes[0] == "A  2X SLOT 6 X 20 THRU"
    wide = Box(80, 40, 3) - Pos(-20, 0, 0) * extrude(Rectangle(20, 6), 6, both=True) - Pos(20, 0, 0) * extrude(Rectangle(6, 20), 6, both=True)
    got = draw.make("w", wide, meta("w", None), "first")
    assert got.judged() and got.sheet.notes[:2] == ["A  WINDOW 6 X 20 THRU", "B  WINDOW 20 X 6 THRU"]      # a window is as it lies on the plate


def test_ordinates_are_written_once_from_the_corner_and_labels_that_would_touch_go_on_another_row():
    feats = layout.features(P.analyse(nema()))
    u, v = layout.ordinates(feats)
    assert u.texts() == ["0", "10", "29.5", "45", "60.5"] and v.texts() == ["0", "7.5", "8", "23", "38", "38.5"]
    assert S.schedule([(0, 4), (3, 7), (8, 12), (5, 9)], 1.0) == [0, 1, 0, 2]           # a label goes on the first row it clears
    assert S.schedule([], 1.0) == []
    assert S.schedule([(0.0, 2.0), (2.5, 4.5), (3.0, 5.0)], 1.5) == [0, 1, 2]           # each too near the one before


def test_more_cutouts_than_a_sheet_takes_or_more_sizes_than_letters_is_unfit():
    many = Box(300, 100, 4)
    for i in range(41):
        many -= Pos(-140 + 7 * (i % 40), -30 + 8 * (i // 40), 0) * thru(2)
    pl = P.analyse(many)
    face, side = draw.views_of(many, pl, "first")
    with pytest.raises(P.Unfit, match="it has 41 cutouts and a sheet takes 40"):
        layout.build(pl, face, side, meta())
    sizes = Box(300, 60, 4)
    for i in range(24):
        sizes -= Pos(-140 + 11 * i, 0, 0) * thru(2 + 0.1 * i)
    pl = P.analyse(sizes)
    face, side = draw.views_of(sizes, pl, "first")
    with pytest.raises(P.Unfit, match="it has 24 different sizes of cutout and the sheet has letters for 23"):
        layout.build(pl, face, side, meta())


def test_the_title_block_says_the_part_the_material_the_commit_and_whether_the_design_is_verified():
    stamped, clean = made("panel", stamp="NOT VERIFIED"), made("panel", stamp=None)
    for got, status in ((stamped, "NOT VERIFIED"), (clean, "VERIFIED")):
        doc = render.read(got.files["dxf"])
        words = {g.value for _, g in doc.items if isinstance(g, S.Text)}
        assert {"panel", "scratch/panel", "ALUMINIUM", "CNC MACHINED", "1:1", "A4   1/1", "cd05de0a1b2c", "ISO 2768-m", status} <= words
        assert "FIRST ANGLE" in words and "PROJECTION" in words
        assert ("NOT VERIFIED" in [g.value for l, g in doc.items if l == dxf.STAMP_LAYER and isinstance(g, S.Text)]) == (status == "NOT VERIFIED")
    assert [g.value for l, g in render.read(stamped.files["dxf"]).items if l == dxf.STAMP_LAYER and isinstance(g, S.Text)] == \
        ["NOT VERIFIED", "NOT VERIFIED"]                                              # the banner and the status cell
    comment = stamped.files["dxf"].decode().split("\n")[1]
    assert comment.startswith("NOT VERIFIED: not from a verified design. cad-agent drawing scratch/panel: first angle, scale 1:1, sheet A4;") and len(comment) <= 255
    dirty = draw.make("panel", panel(), meta("panel", None, dirty=True), "first")
    assert "cd05de0a1b2c +UNCOMMITTED" in {g.value for _, g in render.read(dirty.files["dxf"]).items if isinstance(g, S.Text)}
    none = draw.make("panel", panel(), meta("panel", None, commit=None, material=None, process=None), "first")
    words = {g.value for _, g in render.read(none.files["dxf"]).items if isinstance(g, S.Text)}
    assert {"NONE (NOT IN GIT)", "NOT DECLARED"} <= words                             # nothing is made up for what is not known


def test_third_angle_puts_the_circles_of_the_symbol_first_and_says_so():
    first, third = made("panel", "first"), made("panel", "third")
    f, t = render.read(first.files["dxf"]), render.read(third.files["dxf"])
    assert "FIRST ANGLE" in {g.value for _, g in f.items if isinstance(g, S.Text)} and "THIRD ANGLE" in {g.value for _, g in t.items if isinstance(g, S.Text)}

    def symbol(doc, sheet):
        left = sheet.regions["title"][0] + 130.0                                     # the projection cell of the title block
        circles = [g.c[0] for l, g in doc.items if l == "TITLE" and isinstance(g, dxf.Circle)]
        cone = [min(g.a[0], g.b[0]) for l, g in doc.items if l == "TITLE" and isinstance(g, dxf.Line) and g.a[0] != g.b[0] and min(g.a[0], g.b[0]) > left]
        return min(circles), min(cone)
    (cf, kf), (ct, kt) = symbol(f, first.sheet), symbol(t, third.sheet)
    assert cf > kf and ct < kt                                                       # first: the cone, then the circles; third: the reverse


# ─── The files ───────────────────────────────────────────────────────────────

def test_the_dxf_holds_layers_linetypes_text_and_arrowheads_that_ezdxf_reads():
    got = made("panel", stamp="NOT VERIFIED")
    data = got.files["dxf"]
    ezdxf = pytest.importorskip("ezdxf")
    doc = ezdxf.read(io.StringIO(data.decode("ascii")))
    assert doc.header["$INSUNITS"] == 4 and b"AC1014" in data[:2000] and b"\r" not in data
    assert doc.header["$LTSCALE"] == 1.0 and tuple(doc.header["$LIMMAX"])[:2] == (297.0, 210.0) and tuple(doc.header["$EXTMAX"])[:2] == (297.0, 210.0)
    layers = {l.dxf.name: (l.dxf.color, l.dxf.linetype) for l in doc.layers}
    assert {k: v for k, v in layers.items() if k in S.LAYERS} == {k: (v.colour, v.linetype) for k, v in S.LAYERS.items()}
    patterns = {lt.dxf.name: [t.value for t in lt.pattern_tags.tags if t.code == 49] for lt in doc.linetypes}
    assert patterns["DASHED"] == [3.0, -0.75] and patterns["CENTER"] == [6.0, -0.75, 0.125, -0.75]
    kinds = {}
    for e in doc.modelspace():
        kinds.setdefault(e.dxf.layer, set()).add(e.dxftype())
    assert kinds["VISIBLE"] == {"LINE", "ARC", "CIRCLE"} and kinds["HIDDEN"] == {"LINE"} and kinds["CENTRE"] == {"LINE"}
    assert kinds["DIMENSION"] == {"LINE", "SOLID"} and kinds["DIM_TEXT"] == {"TEXT"} and kinds["DIM_ORD"] == {"LINE", "TEXT"}
    texts = [e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"]
    assert "4X %%c3.4 THRU" in " ".join(texts) and "A  4X %%c3.4 THRU" in texts
    assert not doc.audit().errors
    doc.modelspace()                                                                 # and it loads again
    assert render.read(data).problems == [] and render.read(data).units == 4


def test_trimesh_reads_the_same_lines_and_arcs_from_the_sheet(tmp_path):
    trimesh = pytest.importorskip("trimesh")                                         # a second reader, as test_export has for the outline
    got = made("panel", stamp=None)
    (tmp_path / "panel.dxf").write_bytes(got.files["dxf"])
    loaded = trimesh.load(str(tmp_path / "panel.dxf"), file_type="dxf")
    doc = render.read(got.files["dxf"])
    kinds = Counter(type(e).__name__ for e in loaded.entities)
    assert kinds["Line"] == sum(isinstance(g, dxf.Line) for _, g in doc.items)
    assert kinds["Arc"] == sum(isinstance(g, (dxf.Arc, dxf.Circle)) for _, g in doc.items)
    assert np.allclose(loaded.bounds, [[0.0, 0.0], [297.0, 210.0]])                  # the centring marks run out to the edges of the sheet


def test_names_with_accents_are_put_in_ascii_for_the_sheet_and_the_files_keep_their_own():
    assert S.ascii_text("tapa_\u00f1") == "tapa_n" and S.ascii_text("alumin\u00edo \u00e9\u00e8") == "aluminio ee" and S.ascii_text("\u4e2d") == "?"
    got = draw.make("tapa_\u00f1", plate(), meta("tapa_\u00f1", None, material="alumin\u00edo"), "first")
    words = {g.value for _, g in render.read(got.files["dxf"]).items if isinstance(g, S.Text)}
    assert got.judged() and {"tapa_n", "scratch/tapa_n", "ALUMINIO"} <= words and got.rows[0].subject == "tapa_\u00f1"


def test_the_writer_makes_text_arrowheads_and_linetypes_and_the_old_outline_is_unchanged():
    w = dxf.DxfWriter("c", (0, 0), (10, 10), [dxf.Layer("A", 3, "DASHED")], [dxf.Linetype("DASHED", "d", (2.0, -1.0))],
                      [("$LTSCALE", [(40, "2.0")])])
    w.entity(dxf.Line((0, 0), (5, 5)), "A")
    w.text("A", (1, 2), 3.5, "x %%c1", 90.0, 1, 2)
    w.text("A", (1, 2), 3.5, "left")
    w.solid("A", [(0, 0), (1, 0), (1, 1)])
    w.solid("A", [(0, 0), (1, 0), (1, 1), (0, 1)])
    with pytest.raises(ValueError, match="three or four corners"):
        w.solid("A", [(0, 0), (1, 1)])
    with pytest.raises(TypeError):
        w.entity("not an entity", "A")
    data = w.finish()
    doc = pytest.importorskip("ezdxf").read(io.StringIO(data.decode("ascii")))
    ents = list(doc.modelspace())
    assert [e.dxftype() for e in ents] == ["LINE", "TEXT", "TEXT", "SOLID", "SOLID"] and doc.header["$LTSCALE"] == 2.0
    t = ents[1]
    assert (t.dxf.text, t.dxf.height, t.dxf.rotation, t.dxf.halign, t.dxf.valign) == ("x %%c1", 3.5, 90.0, 1, 2)
    assert (ents[2].dxf.halign, ents[2].dxf.valign, ents[2].dxf.rotation) == (0, 0, 0)
    assert not doc.audit().errors
    # an outline written the old way is what it was: layer none, no extra layer, no linetype beyond the three
    old = dxf.dxf_of(plate(), "plate")
    assert b"DASHED" not in old and b"\nnone\n" in old


def test_the_svg_is_plain_xml_with_an_element_for_each_entity_and_the_stamp_in_red():
    got = made("panel", stamp="NOT VERIFIED")
    root = ET.fromstring(got.files["svg"])
    ns = "{http://www.w3.org/2000/svg}"
    assert root.tag == ns + "svg" and root.get("viewBox") == "0 0 297 210" and root.get("width") == "297mm"
    kinds = {}
    for el in root:
        kinds[el.tag.replace(ns, "")] = kinds.get(el.tag.replace(ns, ""), 0) + 1
    assert {"line", "circle", "path", "polygon", "text"} <= set(kinds)
    hidden = [el for el in root if el.get("class") == "HIDDEN"]
    assert hidden and all(el.get("stroke-dasharray") == "3 0.75" for el in hidden)
    centre = [el for el in root if el.get("class") == "CENTRE"]
    assert centre and all(el.get("stroke-dasharray") == "6 0.75 0.125 0.75" for el in centre)
    visible = [el for el in root if el.get("class") == "VISIBLE"]
    assert visible and {el.get("stroke-width") for el in visible} == {"0.5"}
    smooth = [el for el in root if el.get("class") == "SMOOTH"]          # thin and continuous, as QGIViewPart.cpp:468-473
    assert len(smooth) == 2 and {el.get("stroke-width") for el in smooth} == {"0.25"} and not any(el.get("stroke-dasharray") for el in smooth)
    texts = [el.text for el in root if el.tag == ns + "text"]
    assert "A  4X Ø3.4 THRU" in texts and "NOT VERIFIED" in texts and "%%c" not in got.files["svg"].decode()
    assert all(el.get("{http://www.w3.org/XML/1998/namespace}space") == "preserve" for el in root if el.tag == ns + "text")      # the two spaces after a letter stay
    red = [el for el in root if el.tag == ns + "text" and el.text == "NOT VERIFIED"]
    assert red and all(el.get("fill") == "#cc0000" for el in red)
    assert b"<?xml" in got.files["svg"][:40] and got.files["svg"].endswith(b"</svg>\n")


def test_the_pdf_is_a_well_formed_one_page_vector_file_the_size_of_the_sheet():
    got = made("panel", stamp="NOT VERIFIED")
    pdf = got.files["pdf"]
    assert pdf.startswith(b"%PDF-1.4\n") and pdf.endswith(b"%%EOF\n") and b"/BaseFont /Helvetica" in pdf and b"/Count 1" in pdf
    assert b"/MediaBox [0 0 841.8898 595.2756]" in pdf
    assert b"CreationDate" not in pdf and b"/ID" not in pdf                           # nothing that changes between runs
    assert b"\xd8" in pdf and b"4X " in pdf                                           # the diameter sign is WinAnsi 0xD8
    assert check.pdf_row("panel", render.read(got.files["dxf"]), pdf).state == "PASS"


def test_a_pdf_renders_the_sheet_when_pymupdf_is_there():
    fitz = pytest.importorskip("pymupdf")
    got = made("panel", stamp="NOT VERIFIED")
    doc = fitz.open(stream=got.files["pdf"], filetype="pdf")
    page = doc[0]
    assert len(doc) == 1 and round(page.rect.width, 1) == 841.9 and round(page.rect.height, 1) == 595.3
    text = page.get_text()
    assert "NOT VERIFIED" in text and "A  4X Ø3.4 THRU" in text and "ISO 2768-m" in text and "CNC MACHINED" in text
    pix = page.get_pixmap(dpi=40)
    samples = pix.samples
    dark = sum(1 for i in range(0, len(samples), pix.n) if samples[i] < 100)
    assert 0.002 < dark / (pix.width * pix.height) < 0.2                              # a drawing: some ink, mostly paper


def test_every_run_gives_the_same_bytes_in_this_process_and_in_a_fresh_one(tmp_path):
    a, b = draw.make("nema", nema(), meta("nema"), "first"), draw.make("nema", nema(), meta("nema"), "first")
    assert a.files == b.files
    code = ("import hashlib\nfrom build123d import Box, Cylinder, Pos\nfrom cad_agent.drawing import onesheet as draw\n"
            + inspect.getsource(thru) + inspect.getsource(nema) + f"meta = {meta('nema')!r}\n"
            "m = draw.make('nema', nema(), meta, 'first')\n"
            "print(','.join(hashlib.sha256(m.files[e]).hexdigest() for e in ('dxf', 'svg', 'pdf')))\n")
    fresh = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=300,
                           env={**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO), *os.environ.get("PYTHONPATH", "").split(os.pathsep)])})
    assert fresh.returncode == 0, fresh.stderr
    assert fresh.stdout.strip().splitlines()[-1].split(",") == [hashlib.sha256(a.files[e]).hexdigest() for e in ("dxf", "svg", "pdf")]


# sha256 of the files of three sheets, written by OCCT 7.9 and by OCCT 8.0 alike on the machine that pinned them: hidden
# line removal gives the same lines on both to 1e-9 mm, and the sheet is built on a 1e-4 mm grid. tests/golden/drawings
# holds the three DXF files. Another platform may move a coordinate in its last place, which is no reason to fail
# the build: then the DXF must still be the golden one to 2e-3 mm, and that is all the kernels may differ by, the way
# test_library.py holds a STEP of another kernel to its own to a tolerance. The SVG and the PDF are functions of the DXF,
# so they are pinned as drawn from the golden DXF and are the same on every platform. If a hash moves, either the layout
# or a writer changed on purpose (write the three DXF files of `made(...)` over tests/golden/drawings and pin the new
# hashes), or a kernel gave other lines (a bug in hlr.py: OCCT 7.9 and 8.0 must agree). The golden files are not in
# tests/fixtures: CI runs `cad verify` on every folder there, as a project.
GOLDEN = REPO / "tests" / "golden" / "drawings"
PINNED = {
    ("nema", "first", "dxf"): "23810bbebef2d1a5673fa6cfde2e2f1b20db89f5fcfa73197e43df056441ea90",
    ("nema", "first", "svg"): "a59a7a878a8c1bb3cdeee8a1ba055110e0ad5de458d6e9c75ec90148eaade85e",
    ("nema", "first", "pdf"): "c2660c12e93053e71da39a67c162f518df5ebb61cae703f808f5908d65d940af",
    ("panel", "first", "dxf"): "dc3333d54377cd03bc17c5531fe7b047631182bb2fb2042299d976eebe185a7b",
    ("panel", "first", "svg"): "edbed6d5f11c6f3802e68b9a9c33ad2a6d7ad2f44314b51f497fe67e2b9f4c11",
    ("panel", "first", "pdf"): "d9355d608685b591e24ec826cc83062002ca0e344ad5a9edb7f4883f5348e40e",
    ("panel", "third", "dxf"): "c47c5b694a00ce640400f99c8607d9bd52f2fcb38ce14642f831e65728cd0d58",
    ("panel", "third", "svg"): "8e9fc6767878d636dc3998ee9ccccc4f3dfce52671327b053fa1d41457f4655e",
    ("panel", "third", "pdf"): "11df7db3012fe03094ec7b416f33e257a696a92ad4cae95d7fbdcfaced91220d",
}


def same_dxf(got: bytes, want: bytes, tol: float = 2e-3) -> str | None:
    """None when two DXF files are the same line for line with every number within `tol` mm, else the first difference."""
    a, b = got.decode("ascii").split("\n"), want.decode("ascii").split("\n")
    if len(a) != len(b):
        return f"{len(a)} lines against {len(b)}"
    for n, (x, y) in enumerate(zip(a, b), 1):
        if x == y:
            continue
        try:
            close = abs(float(x) - float(y)) <= tol
        except ValueError:
            close = False
        if not close:
            return f"line {n}: {x[:60]!r} against {y[:60]!r}"
    return None


def test_same_dxf_is_tolerant_of_a_last_digit_and_of_nothing_else():
    one = b"999\ncomment\n 10\n12.345678\n 20\n0.000000\nEOF\n"
    assert same_dxf(one, one) is None
    assert same_dxf(one, one.replace(b"12.345678", b"12.345001")) is None                    # a coordinate a hair off
    assert "line 4: '12.345678' against '12.350000'" in same_dxf(one, one.replace(b"12.345678", b"12.350000"))
    assert "line 2:" in same_dxf(one, one.replace(b"comment", b"another"))                   # text must be the text
    assert same_dxf(one, one + b"EOF\n") == "8 lines against 9"                               # and so must the number of lines


@pytest.mark.parametrize("name,angle,stamp", [("nema", "first", "NOT VERIFIED"), ("panel", "first", None), ("panel", "third", "NOT VERIFIED")])
def test_a_sheet_is_the_same_bytes_on_either_kernel(name, angle, stamp):
    got = made(name, angle, stamp)
    golden = (GOLDEN / f"{name}_{angle}.dxf").read_bytes()
    assert hashlib.sha256(golden).hexdigest() == PINNED[name, angle, "dxf"], "the golden DXF is not the pinned one"
    digest = hashlib.sha256(got.files["dxf"]).hexdigest()
    assert digest == PINNED[name, angle, "dxf"] or same_dxf(got.files["dxf"], golden) is None, (
        f"{name} {angle} .dxf is {digest} and is not the golden sheet to 2e-3 mm either: {same_dxf(got.files['dxf'], golden)}. If the layout "
        "or a writer changed on purpose, write the golden files again and pin the new hashes; if not, a kernel gave other lines")
    doc = render.read(golden)
    for ext, make in (("svg", render.svg), ("pdf", render.pdf)):
        digest = hashlib.sha256(make(doc, f"scratch/{name}")).hexdigest()
        assert digest == PINNED[name, angle, ext], f"{name} {angle} .{ext} drawn from the golden DXF is {digest}"
    if digest_matches(got, name, angle):                       # on the machine that pinned them nothing may have moved, in any file
        assert hashlib.sha256(got.files["svg"]).hexdigest() == PINNED[name, angle, "svg"]
        assert hashlib.sha256(got.files["pdf"]).hexdigest() == PINNED[name, angle, "pdf"]


def digest_matches(got, name: str, angle: str) -> bool:
    return hashlib.sha256(got.files["dxf"]).hexdigest() == PINNED[name, angle, "dxf"]


# ─── The gates fail when the sheet is damaged ────────────────────────────────

@pytest.fixture(scope="module")
def good():
    """The panel drawn without a stamp, its plate, and its DXF read back."""
    got = made("panel", stamp=None)
    return got, render.read(got.files["dxf"])


def sheet_row(good, edit=None, data=None, stamp=None, **kw):
    got, doc = good
    if edit:
        doc = doc._replace(items=edit(list(doc.items)))
    return check.sheet_row("panel", got.plate, doc._replace(**kw) if kw else doc, data or got.files["dxf"], meta("panel", stamp), "first", stamp)


def complaint(row: Row, said: str) -> None:
    assert row.state == "FAIL" and said in row.measured, row.measured


def test_a_sheet_that_says_what_the_plate_is_passes_and_names_what_it_checked(good):
    row = sheet_row(good)
    assert row.state == "PASS" and row.check == "drawing" and row.limit and row.source
    assert row.measured.startswith("sheet A4 at 1:1; face view 100 x 60, side view 3 thick; 5 holes where the B-rep has them")


def test_a_hole_that_is_not_where_the_b_rep_has_it_fails_the_sheet(good):
    big = lambda it: isinstance(it[1], dxf.Circle) and it[0] == "VISIBLE" and it[1].r > 5          # noqa: E731
    complaint(sheet_row(good, lambda items: [i for i in items if not big(i)]), "the face view has circles")
    moved = lambda items: [(l, dxf.Circle((g.c[0] + 0.5, g.c[1]), g.r)) if big((l, g)) else (l, g) for l, g in items]       # noqa: E731
    complaint(sheet_row(good, moved), "and the B-rep has holes")
    smaller = lambda items: [(l, dxf.Circle(g.c, g.r - 0.2)) if big((l, g)) else (l, g) for l, g in items]                  # noqa: E731
    complaint(sheet_row(good, smaller), "and the B-rep has holes")


def test_a_view_that_is_not_the_size_of_the_plate_at_the_stated_scale_fails_the_sheet(good):
    def scale_text(items):
        return [(l, S.Text(g.at, g.height, "1:2", g.rotation, g.halign, g.valign)) if isinstance(g, S.Text) and g.value == "1:1" else (l, g)
                for l, g in items]
    complaint(sheet_row(good, scale_text), "the face view is 200.000 x 120.000 mm in the plate, which is 100.000 x 60.000")
    twice = lambda items: items + [("TEXT", S.Text((10.0, 10.0), 3.5, "1:5"))]                  # noqa: E731
    complaint(sheet_row(good, twice), "it states 2 scales")
    far = lambda items: items + [("VISIBLE", dxf.Line((10.0, 190.0), (12.0, 190.0)))]            # noqa: E731
    complaint(sheet_row(good, far), "the visible lines fall into 3 views, not two")
    thick = lambda items: [(l, dxf.Line((g.a[0] + 1.0, g.a[1]), (g.b[0] + 1.0, g.b[1]))) if l == "VISIBLE" and isinstance(g, dxf.Line)
                           and g.a[0] == g.b[0] and g.a[0] > 200 and g.a[0] == max(h.a[0] for k, h in items if k == "VISIBLE" and isinstance(h, dxf.Line)) else (l, g)
                           for l, g in items]                                                    # noqa: E731
    complaint(sheet_row(good, thick), "the side view is 4.000 thick")


def test_an_ordinate_label_that_is_not_the_distance_it_names_fails_the_sheet(good):
    def label(text, new):
        return lambda items: [(l, S.Text(g.at, g.height, new, g.rotation, g.halign, g.valign)) if l == "DIM_ORD" and isinstance(g, S.Text)
                              and g.value == text else (l, g) for l, g in items]
    complaint(sheet_row(good, label("27.5", "28")), "an ordinate label says 28 and its line is 27.500 mm from the corner at 1:1")
    complaint(sheet_row(good, label("55", "56")), "an ordinate label says 56 and its line is 55.000 mm")
    gone = lambda items: [(l, g) for l, g in items if not (l == "DIM_ORD" and isinstance(g, S.Text) and g.value == "67.5")]     # noqa: E731
    complaint(sheet_row(good, gone), "an ordinate line of the x axis has 0 labels at its end, not one")
    short = lambda items: [(l, dxf.Line((g.a[0], min(g.a[1], g.b[1])), (g.a[0], min(g.a[1], g.b[1]) + 1.0))) if l == "DIM_ORD"
                           and isinstance(g, dxf.Line) and g.a[0] == g.b[0] else (l, g) for l, g in items]       # noqa: E731
    complaint(sheet_row(good, short), "no ordinate line of x runs through the centre of the cutout at")       # the labels are where they were; the lines stop short


def test_a_dimension_that_is_not_the_length_it_says_fails_the_sheet(good):
    def text(old, new):
        return lambda items: [(l, S.Text(g.at, g.height, new, g.rotation, g.halign, g.valign)) if l == "DIM_TEXT" and isinstance(g, S.Text)
                              and g.value == old else (l, g) for l, g in items]
    complaint(sheet_row(good, text("100", "101")), "the dimensions read ['101', '3', '60'] and the plate is ['100', '3', '60']")
    shortened = lambda items: [(l, dxf.Line(g.a, (g.b[0] - 2.0, g.b[1]))) if l == "DIMENSION" and isinstance(g, dxf.Line) and g.a[1] == g.b[1]
                               and g.b[0] - g.a[0] > 90 else (l, g) for l, g in items]            # noqa: E731
    complaint(sheet_row(good, shortened), "no dimension line of the sheet is as long as the width")
    noarrow = lambda items: [i for n, i in enumerate(items) if not (i[0] == "DIMENSION" and isinstance(i[1], S.Solid))] + [
        i for i in items if i[0] == "DIMENSION" and isinstance(i[1], S.Solid)][:5]                  # noqa: E731
    complaint(sheet_row(good, noarrow), "the arrowheads (5) are not six, each on the end of a dimension line")


def test_notes_letters_hidden_lines_title_block_and_stamp_are_held_to_the_plate(good):
    complaint(sheet_row(good, lambda items: [i for i in items if not (isinstance(i[1], S.Text) and i[1].value == "A  4X %%c3.4 THRU")]),
              "the notes do not say 'A  4X %%c3.4 THRU'")
    one_a = lambda items: [i for i in items if not (isinstance(i[1], S.Text) and i[1].value == "A")][1:] + [i for i in items if isinstance(i[1], S.Text) and i[1].value == "A"][:3]
    complaint(sheet_row(good, one_a), "the letter A is written 3 times and 4 cutouts have it")
    complaint(sheet_row(good, lambda items: [i for i in items if i[0] != "HIDDEN"]), "is not dashed through the side view at y =")
    complaint(sheet_row(good, lambda items: [i for i in items if not (isinstance(i[1], S.Text) and i[1].value == "ISO 2768-m")]),
              "the title block does not say the tolerance: 'ISO 2768-m'")
    complaint(sheet_row(good, lambda items: items + [(dxf.STAMP_LAYER, S.Text((10.0, 10.0), 8.0, "NOT VERIFIED"))]), "the sheet carries a stamp it should not")
    stamped = made("panel", stamp="NOT VERIFIED")
    doc = render.read(stamped.files["dxf"])
    row = check.sheet_row("panel", stamped.plate, doc._replace(items=[i for i in doc.items if i[0] != dxf.STAMP_LAYER]), stamped.files["dxf"],
                          meta("panel"), "first", "NOT VERIFIED")
    complaint(row, "the stamp NOT VERIFIED is missing from the sheet")
    assert check.sheet_row("panel", stamped.plate, doc, stamped.files["dxf"], meta("panel"), "first", "NOT VERIFIED").state == "PASS"
    complaint(check.sheet_row("panel", stamped.plate, doc, stamped.files["dxf"].replace(b"NOT VERIFIED:", b"VERIFIED:", 1), meta("panel"), "first", "NOT VERIFIED"),
              "the comment of the file does not agree with the stamp")


def test_a_file_that_is_not_what_the_writer_says_it_is_fails_the_sheet(good):
    got, doc = good
    complaint(sheet_row(good, units=1), "its units are code 1, not 4 (millimetres)")
    complaint(sheet_row(good, units=None), "it does not say millimetres")
    complaint(sheet_row(good, stray=Counter({"HATCH": 2})), "it holds entities a drawing does not have: 2 HATCH")
    complaint(sheet_row(good, problems=["bad handle"]), "ezdxf's audit of it found: bad handle")
    complaint(sheet_row(good, linetypes={}), "its linetype DASHED is missing")
    complaint(sheet_row(good, layers={}), "which its layer table does not declare")
    complaint(sheet_row(good, extmax=(300.0, 200.0)), "are not a sheet of ISO 5457")
    complaint(sheet_row(good, data=got.files["dxf"].replace(b"AC1014", b"AC1009")), "it does not say it is release 14")
    complaint(sheet_row(good, lambda items: [i for i in items if not (isinstance(i[1], S.Text) and i[1].value == "1:1")]), "it states 0 scales")


def test_labels_that_overlap_or_lines_off_the_sheet_are_unchecked_and_no_drawing_is_made(good):
    got, doc = good
    assert check.layout_row("panel", doc).state == "PASS"
    texts = [i for i in doc.items if isinstance(i[1], S.Text)]
    row = check.layout_row("panel", doc._replace(items=doc.items + [texts[10]]))
    assert row.state == "UNCHECKED" and "labels overlap:" in row.measured and "no drawing is made" in row.measured
    row = check.layout_row("panel", doc._replace(items=doc.items + [("VISIBLE", dxf.Line((1.0, 1.0), (400.0, 1.0)))]))
    assert row.state == "UNCHECKED" and "1 entities are outside the sheet" in row.measured


def test_an_svg_that_lost_an_element_or_changed_a_number_fails(good):
    got, doc = good
    svg = got.files["svg"]
    assert check.svg_row("panel", doc, svg).state == "PASS"
    lines = svg.decode().split("\n")
    first = next(i for i, l in enumerate(lines) if l.startswith("<line"))
    assert "an element of the right kind" not in check.svg_row("panel", doc, "\n".join(lines[:first] + lines[first + 1:]).encode()).measured
    assert check.svg_row("panel", doc, "\n".join(lines[:first] + lines[first + 1:]).encode()).state == "FAIL"
    assert "its texts are not the DXF's" in check.svg_row("panel", doc, svg.replace(b">100<", b">101<")).measured
    assert "a hidden line is not dashed" in check.svg_row("panel", doc, svg.replace(b' stroke-dasharray="3 0.75"', b"", 1)).measured
    assert "it holds a script" in check.svg_row("panel", doc, svg.replace(b"</svg>", b"<script>alert(1)</script></svg>")).measured
    assert "its view box is" in check.svg_row("panel", doc, svg.replace(b'viewBox="0 0 297 210"', b'viewBox="0 0 210 297"')).measured
    row = check.svg_row("panel", doc, svg[:200])
    assert row.state == "FAIL" and "not well formed XML" in row.measured


def test_a_pdf_that_is_damaged_in_any_of_the_ways_it_is_held_against_fails(good):
    got, doc = good
    pdf = got.files["pdf"]
    assert check.pdf_row("panel", doc, pdf).state == "PASS"
    assert "does not start with %PDF-1.4" in check.pdf_row("panel", doc, b"%PDF-1.7\n" + pdf[9:]).measured
    assert "its structure cannot be read" in check.pdf_row("panel", doc, pdf[:pdf.rfind(b"startxref")] + b"%%EOF\n").measured
    assert "the cross reference points at 16 for object 1, which is not it" in check.pdf_row(
        "panel", doc, pdf.replace(b"0000000015 00000 n", b"0000000016 00000 n", 1)).measured
    assert "its page is not the sheet's size" in check.pdf_row("panel", doc, pdf.replace(b"/MediaBox [0 0 841.8898", b"/MediaBox [0 0 595.2756", 1)).measured
    assert "strokes" in check.pdf_row("panel", doc, pdf.replace(b" l S\n", b" l\n", 1)).measured
    ok = check.pdf_row("panel", doc, pdf)
    assert "6 objects at their offsets, one page of the sheet's size" in ok.measured


# ─── The command ─────────────────────────────────────────────────────────────

def run(capsys, *argv):
    code = cli.main(["--json", *argv])
    out = capsys.readouterr().out.strip().splitlines()
    return code, json.loads(out[-1])["data"]


def log_of(project: Path) -> list:
    return [json.loads(x) for x in (project / ".cad" / "log.jsonl").read_text().splitlines()]


def test_cad_drawing_draws_a_part_stamps_it_while_the_design_is_not_done_and_exits_2(workshop, capsys):
    code, data = run(capsys, "drawing", SLUG, "panel")
    assert code == cli.UNCHECKED and data["stamp"] == "NOT VERIFIED" and data["done"] is False and data["rows"] == []
    assert data["rows_total"] == 7 and data["plate"] == "60 x 30 x 3 mm, thin in z, corners R3, 2 holes" and data["process"] == "laser_cut"
    assert data["sheet"] == {"size": "A4", "scale": "2:1"} and data["angle"] == "first"
    out = workshop / "out" / "drawings"
    assert sorted(p.name for p in out.iterdir()) == ["panel.dxf", "panel.pdf", "panel.svg"] and data["wrote"] == [str(out / n) for n in ("panel.dxf", "panel.svg", "panel.pdf")]
    assert [f["path"] for f in data["files"]] == ["panel.dxf", "panel.pdf", "panel.svg"]
    for f in data["files"]:
        assert hashlib.sha256((out / f["path"]).read_bytes()).hexdigest() == f["sha256"] and (out / f["path"]).stat().st_size == f["bytes"]
    assert b"NOT VERIFIED" in (out / "panel.dxf").read_bytes() and b"NOT VERIFIED" in (out / "panel.svg").read_bytes()
    assert set(data["hlr_seconds"]) == {"face", "side", "total"} and all(v > 0 for v in data["hlr_seconds"].values())
    last = log_of(workshop)[-1]
    assert last["cmd"] == "drawing" and last["exit"] == cli.UNCHECKED and last["files"] == data["wrote"] and last["summary"] == "draft: wrote 3 files"
    code, data = run(capsys, "drawing", SLUG, "panel", "--all")
    assert len(data["rows"]) == 7 and {r["state"] for r in data["rows"]} == {"PASS"} and {r["check"] for r in data["rows"]} == {"drawing"}
    assert [r["rule"] for r in data["rows"]] == ["scope", "views", "dimensions", "sheet", "layout", "svg", "pdf"]


def test_the_text_of_the_command_says_what_was_drawn_and_what_was_written(workshop, capsys):
    assert cli.main(["drawing", SLUG, "block", "--format", "dxf"]) == cli.UNCHECKED
    text = capsys.readouterr().out
    assert text.startswith("works/block  cad drawing: A4 2:1, first angle  [NOT VERIFIED]") and "wrote " in text and "block.dxf" in text
    assert (workshop / "out" / "drawings" / "block.dxf").exists() and not (workshop / "out" / "drawings" / "block.svg").exists()


def test_a_format_a_folder_an_angle_a_sheet_and_a_scale_can_be_asked_for(workshop, capsys, tmp_path):
    out = tmp_path / "elsewhere"
    code, data = run(capsys, "drawing", SLUG, "panel", "--format", "pdf,svg", "--out", str(out), "--angle", "third", "--sheet", "a3", "--scale", "1:1")
    assert code == cli.UNCHECKED and sorted(p.name for p in out.iterdir()) == ["panel.pdf", "panel.svg"] and not (workshop / "out" / "drawings").exists()
    assert data["sheet"] == {"size": "A3", "scale": "1:1"} and data["angle"] == "third"
    assert "THIRD ANGLE" in out.joinpath("panel.svg").read_text()


@pytest.mark.parametrize("argv,said", [
    (["drawing", "nope", "panel"], "no project 'nope'"),
    (["drawing", SLUG, "nope"], "no part 'nope' in works"),
    (["drawing", SLUG, "gantry/panel"], "'gantry/panel' is a body of the sub-assembly 'gantry', not a part of works: a child's part is drawn by the child project, `cad drawing gantry panel`"),
    (["drawing", SLUG, "clip"], "clip is made by 'fdm' (PROCESS in parts/clip.py): cad drawing draws parts made by 'cnc' (machined) or 'laser_cut'"),
    (["drawing", SLUG, "panel", "--format", "png"], "--format takes a comma list of dxf, svg, pdf, got 'png'"),
    (["drawing", SLUG, "panel", "--format", ","], "--format takes a comma list"),
    (["drawing", SLUG, "panel", "--sheet", "A5"], "--sheet is one of A4, A3, A2, A1, A0 or auto, got 'A5'"),
    (["drawing", SLUG, "panel", "--scale", "1:3"], "1:3 is not a scale of ISO 5455"),
    (["drawing", SLUG, "panel", "--scale", "half"], "a scale is written 1:2 or 2:1"),
    (["drawing", SLUG, "panel", "--scale", "50:1"], "do not fit A4, A3, A2, A1, A0 at 50:1"),
    (["drawing", SLUG, "panel", "--sheet", "A4", "--scale", "5:1"], "do not fit A4 at 5:1"),
    (["drawing", SLUG, "panel", "--angle", "second"], "invalid choice"),
])
def test_a_request_that_is_wrong_is_exit_3_and_writes_nothing(workshop, capsys, argv, said):
    code = cli.main(["--json", *argv])
    captured = capsys.readouterr()
    reported = json.loads(captured.out.strip().splitlines()[-1])["data"].get("error", "") if captured.out.strip() else ""
    assert code == cli.USAGE and said in captured.err + reported            # argparse says its own errors on stderr, a handler's go in the data
    assert not (workshop / "out" / "drawings").exists()


def test_a_part_with_no_process_is_exit_3_and_the_message_says_where_to_declare_it(workshop, capsys):
    (workshop / "parts" / "block.py").write_text(BLOCK.replace('PROCESS = "cnc"\n', ""))
    code, data = run(capsys, "drawing", SLUG, "block")
    assert code == cli.USAGE and "block declares no PROCESS in parts/block.py: cad drawing draws parts made by 'cnc' (machined) or 'laser_cut'" in data["error"]


def test_a_part_that_does_not_build_is_exit_1_not_a_drawing(workshop, capsys):
    (workshop / "parts" / "block.py").write_text(BLOCK.replace("Box(size, size, height)", "Box(size, size, -1)"))
    code, data = run(capsys, "drawing", SLUG, "block")
    assert code == cli.FAIL and "block did not build" in data["error"]


def test_a_part_that_is_not_a_plate_is_exit_2_with_the_reason_and_nothing_is_written(workshop, capsys):
    (workshop / "parts" / "panel.py").write_text(PANEL.replace("    return panel", "    return panel - Pos(0, 0, 1.0) * Box(10, 6, 1.0)"))
    code = cli.main(["drawing", SLUG, "panel"])
    text = capsys.readouterr().out
    assert code == cli.UNCHECKED and "UNCHECKED" in text and "panel is not a plate this drawing can show: it is not a prism along z" in text
    assert "a pocket floor, a step or a boss" in text and "nothing was written: the part is not a plate this drawing can show" in text
    assert not (workshop / "out" / "drawings").exists()
    code, data = run(capsys, "drawing", SLUG, "panel")
    assert [(r["rule"], r["state"]) for r in data["rows"]] == [("scope", "UNCHECKED")] and data["sheet"] is None and data["files"] == []
    assert log_of(workshop)[-1]["summary"].startswith("not drawn: it is not a prism along z")


def test_a_plate_that_fits_no_sheet_is_exit_2_unless_the_arguments_made_it_a_usage_error(workshop, capsys, monkeypatch):
    giant = P.Plate(2, dxf.frame_at(2, 2.5), 5.0, (0.0, 0.0), (2.0e6, 1.0e6), 0.0)             # 2 km by 1 km: nothing a sheet holds at 1:1000
    with pytest.raises(layout.DoesNotFit, match="do not fit A0 even at 1:1000"):
        layout.choose(giant, [], (layout.Labels(), layout.Labels()), 45.0, False, None, None)
    code, data = run(capsys, "drawing", SLUG, "block", "--sheet", "A4", "--scale", "50:1")
    assert code == cli.USAGE and "do not fit A4 at 50:1" in data["error"]                          # asked for, so the arguments are wrong
    monkeypatch.setattr(layout, "choose", lambda *a: (_ for _ in ()).throw(layout.DoesNotFit("the views and their dimensions do not fit A0 even at 1:1000")))
    code, data = run(capsys, "drawing", SLUG, "block")
    assert code == cli.UNCHECKED and data["rows"][0]["rule"] == "scope" and "block does not fit a sheet: the views" in data["rows"][0]["measured"]
    assert data["wrote"] == [] and not (workshop / "out" / "drawings").exists()


def test_a_drawing_that_would_say_something_wrong_is_exit_1_and_is_not_written(workshop, capsys, monkeypatch):
    real = render.write

    def lose_a_hole(sheet, meta_):
        first = next(i for i, (l, g) in enumerate(sheet.items) if l == "VISIBLE" and isinstance(g, dxf.Circle))
        del sheet.items[first]
        return real(sheet, meta_)
    monkeypatch.setattr(render, "write", lose_a_hole)
    code = cli.main(["drawing", SLUG, "panel"])
    text = capsys.readouterr().out
    assert code == cli.FAIL and "FAIL" in text and "the face view has circles" in text and "nothing was written: a row failed" in text
    assert not (workshop / "out" / "drawings").exists()


def test_a_row_that_cannot_be_settled_is_exit_2_and_nothing_is_written(workshop, capsys, monkeypatch):
    monkeypatch.setattr(check, "values_of", lambda plate: (_ for _ in ()).throw(RuntimeError("no sketch")))
    code = cli.main(["drawing", SLUG, "panel"])
    text = capsys.readouterr().out
    assert code == cli.UNCHECKED and "RuntimeError: no sketch" in text and "nothing was written: a row could not be settled" in text
    assert not (workshop / "out" / "drawings").exists()


def test_a_kernel_that_cannot_project_is_an_unchecked_row_not_a_crash(workshop, capsys, monkeypatch):
    monkeypatch.setattr(V, "hlr_edges", lambda *a: (_ for _ in ()).throw(RuntimeError("HLR failed")))
    code, data = run(capsys, "drawing", SLUG, "panel")
    assert code == cli.UNCHECKED and any("the views could not be made: RuntimeError: HLR failed" in r["measured"] for r in data["rows"])
    assert not (workshop / "out" / "drawings").exists()


def test_a_bug_in_the_drawing_code_is_exit_4(workshop, capsys, monkeypatch):
    monkeypatch.setattr(P, "analyse", lambda solid: (_ for _ in ()).throw(RuntimeError("bug")))
    code = cli.main(["drawing", SLUG, "panel"])
    assert code == cli.CRASH and "cad crashed, this is a cad-agent bug" in capsys.readouterr().err


def test_a_missing_ezdxf_is_a_usage_error_that_says_what_to_install(workshop, capsys, monkeypatch):
    monkeypatch.setattr(dxf, "ezdxf_module", lambda: (_ for _ in ()).throw(dxf.NeedsExtra('reading a DXF back needs ezdxf: install it with: pip install "ezdxf>=1.4"')))
    code, data = run(capsys, "drawing", SLUG, "panel")
    assert code == cli.USAGE and 'pip install "ezdxf>=1.4"' in data["error"] and not (workshop / "out" / "drawings").exists()


@pytest.mark.parametrize("gate,rule", [("sheet_row", "sheet"), ("layout_row", "layout"), ("svg_row", "svg"), ("pdf_row", "pdf")])
def test_a_gate_that_raises_is_an_unchecked_row_and_not_a_crash_or_a_pass(monkeypatch, gate, rule):
    monkeypatch.setattr(check, gate, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    got = draw.make("p", plate(), meta("p", None), "first")
    bad = [r for r in got.rows if r.state != "PASS"]
    assert [(r.rule, r.state) for r in bad] == [(rule, "UNCHECKED")] and "the gate could not be run: RuntimeError: boom" in bad[0].measured
    assert not got.judged()


def git(d, *args):
    return subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_the_sheet_carries_the_commit_and_says_when_the_design_has_changes_not_committed(workshop, capsys):
    git(workshop, "init", "-q", "-b", "main")
    git(workshop, "add", "-A")
    git(workshop, "commit", "-q", "-m", "design")
    head = git(workshop, "rev-parse", "HEAD")
    assert run(capsys, "drawing", SLUG, "panel", "--format", "dxf")[0] == cli.UNCHECKED
    words = {g.value for _, g in render.read((workshop / "out" / "drawings" / "panel.dxf").read_bytes()).items if isinstance(g, S.Text)}
    assert head[:12] in words and "NONE (NOT IN GIT)" not in words
    (workshop / "parts" / "block.py").write_text(BLOCK.replace('"height": 12.0', '"height": 13.0'))
    run(capsys, "drawing", SLUG, "panel", "--format", "dxf")
    words = {g.value for _, g in render.read((workshop / "out" / "drawings" / "panel.dxf").read_bytes()).items if isinstance(g, S.Text)}
    assert head[:12] + " +UNCOMMITTED" in words


@pytest.fixture(scope="module")
def verified(tmp_path_factory):
    """`works`, approved and verified in a process standing in for a fresh one, so `cad done` holds."""
    root = tmp_path_factory.mktemp("verified")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(st, "ROOT", root)
        mp.delenv("CAD_PROJECTS", raising=False)
        d = make_workshop(root)
        check_all(SLUG)
        approve_views(SLUG)
        record = verify.run(SLUG, fresh=True, mode="test")
        assert record["verdict"] == "PASS", [r for r in record["rows"] if r["state"] != "PASS"]
        assert verify.status(SLUG)["done"] is True
        yield d


@pytest.fixture()
def project(verified, tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    shutil.copytree(verified, tmp_path / SLUG)
    return tmp_path / SLUG


def test_a_design_that_is_done_gets_a_drawing_that_is_not_stamped_and_exit_0(project, capsys):
    code, data = run(capsys, "drawing", SLUG, "panel")
    assert code == cli.OK and data["stamp"] is None and data["done"] is True and data["reasons"] == []
    files = {p.suffix: p.read_bytes() for p in (project / "out" / "drawings").iterdir()}
    assert b"NOT VERIFIED" not in files[".dxf"] and b"NOT VERIFIED" not in files[".svg"] and b"NOT VERIFIED" not in files[".pdf"]
    words = {g.value for _, g in render.read(files[".dxf"]).items if isinstance(g, S.Text)}
    assert "VERIFIED" in words and "NOT VERIFIED" not in words
    assert run(capsys, "drawing", SLUG, "panel")[0] == cli.OK                          # and again


def test_the_same_design_changed_after_it_was_verified_is_stamped_again(project, capsys):
    (project / "parts" / "block.py").write_text(BLOCK.replace('"height": 12.0', '"height": 13.0'))
    code, data = run(capsys, "drawing", SLUG, "panel")
    assert code == cli.UNCHECKED and data["stamp"] == "NOT VERIFIED" and "the design changed since it was verified" in data["reasons"]


# ─── The hook of `cad shop` ──────────────────────────────────────────────────

def solids_of(slug=SLUG):
    names = ("block", "clip", "panel")
    return {n: st.build_part(slug, n)[0] for n in names}, {"block": "cnc", "clip": "fdm", "panel": "laser_cut"}


def test_shop_drawings_draws_each_plate_under_drawings_and_says_why_it_skipped_the_rest(workshop):
    from cad_agent import drawing
    solids, processes = solids_of()
    got = drawing.shop_drawings(SLUG, solids, processes, None)
    assert sorted(got["files"]) == [f"drawings/{n}.{e}" for n in ("block", "panel") for e in ("dxf", "pdf", "svg")]
    assert got["skipped"] == {"clip": "made by 'fdm', and drawings are for cnc and laser_cut parts"}
    assert all(isinstance(v, bytes) for v in got["files"].values()) and all(p.startswith("drawings/") for p in got["files"])
    assert b"NOT VERIFIED" not in got["files"]["drawings/panel.dxf"]
    assert drawing.shop_drawings(SLUG, solids, processes, None) == got                               # the same bytes every time
    stamped = drawing.shop_drawings(SLUG, solids, processes, "NOT VERIFIED")
    for ext in ("dxf", "svg", "pdf"):
        assert b"NOT VERIFIED" in stamped["files"][f"drawings/panel.{ext}"] and stamped["files"][f"drawings/panel.{ext}"] != got["files"][f"drawings/panel.{ext}"]
    assert [g.value for l, g in render.read(stamped["files"]["drawings/block.dxf"]).items if l == dxf.STAMP_LAYER and isinstance(g, S.Text)] == ["NOT VERIFIED"] * 2


def test_the_hook_names_files_by_file_stem_and_skips_what_it_cannot_draw_without_stopping(workshop, monkeypatch):
    from cad_agent import drawing
    solids, processes = solids_of()
    pocket = solids["panel"] - Pos(0, 0, 1) * Box(10, 6, 2)
    got = drawing.shop_drawings(SLUG, {"gantry/plate": solids["block"], "pocket": pocket, "none": solids["block"]},
                                {"gantry/plate": "cnc", "pocket": "cnc", "none": None}, None)
    assert sorted(got["files"]) == [f"drawings/gantry__plate.{e}" for e in ("dxf", "pdf", "svg")]       # subassembly.file_stem: no folder from a "/"
    assert "a pocket floor" in got["skipped"]["pocket"] and got["skipped"]["pocket"].startswith("not a plate this drawing can show: it is not a prism along z")
    assert got["skipped"]["none"] == "declares no PROCESS, so it is not known to be machined or cut"
    assert "NOT DECLARED" in {g.value for _, g in render.read(got["files"]["drawings/gantry__plate.dxf"]).items if isinstance(g, S.Text)}
    with monkeypatch.context() as m:
        m.setattr(check, "sheet_row", lambda *a, **k: check.row("block", "sheet", "FAIL", "a hole is missing", "x"))
        failed = drawing.shop_drawings(SLUG, {"block": solids["block"]}, {"block": "cnc"}, None)
    assert failed == {"files": {}, "skipped": {"block": "its drawing did not pass its own gates: sheet: a hole is missing"}}
    with monkeypatch.context() as m:
        m.setattr(draw, "make", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no kernel")))
        assert drawing.shop_drawings(SLUG, {"block": solids["block"]}, {"block": "cnc"}, None)["skipped"] == {
            "block": "its drawing could not be made: RuntimeError: no kernel"}
    with monkeypatch.context() as m:
        m.setattr(draw, "make", lambda *a, **k: (_ for _ in ()).throw(layout.DoesNotFit("too big")))
        assert drawing.shop_drawings(SLUG, {"block": solids["block"]}, {"block": "cnc"}, None)["skipped"] == {"block": "too big"}


def test_cad_shop_writes_the_drawings_and_the_manifest_lists_them_and_check_agrees(project, capsys):
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.OK
    folder = project / "out" / "shop"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["drawings"]["built"] is True and manifest["drawings"]["skipped"] == {"clip": "made by 'fdm', and drawings are for cnc and laser_cut parts"}
    assert manifest["drawings"]["files"] == [f"drawings/{n}.{e}" for n in ("block", "panel") for e in ("dxf", "pdf", "svg")]
    listed = {f["path"]: f for f in manifest["files"]}
    for path in manifest["drawings"]["files"]:
        assert listed[path]["format"] == "drawing" and hashlib.sha256((folder / path).read_bytes()).hexdigest() == listed[path]["sha256"]
    assert {"rule": "drawings", "subject": "drawings", "state": "PASS"} in manifest["rows"]
    assert b"NOT VERIFIED" not in (folder / "drawings" / "panel.dxf").read_bytes()
    first = (folder / "drawings" / "panel.pdf").read_bytes()
    assert run(capsys, "shop", SLUG, "--check")[0] == cli.OK
    assert run(capsys, "shop", SLUG)[0] == cli.OK and (folder / "drawings" / "panel.pdf").read_bytes() == first
    code, data = run(capsys, "shop", SLUG, "--draft")
    assert code == cli.OK and b"NOT VERIFIED" in (folder / "drawings" / "panel.dxf").read_bytes()      # a draft is stamped inside the drawings too
    # `cad shop` and `cad drawing` draw the same sheet: the same bytes
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    assert run(capsys, "drawing", SLUG, "panel", "--out", str(project / "elsewhere"))[0] == cli.OK
    for ext in ("dxf", "svg", "pdf"):
        assert (project / "elsewhere" / f"panel.{ext}").read_bytes() == (folder / "drawings" / f"panel.{ext}").read_bytes()


# ─── The evals ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def evals_laid(tmp_path_factory):
    root = tmp_path_factory.mktemp("evals")
    for name in ("laser_panel", "nema17_mount", "galvo_mount", "endstop_bracket"):
        evals.lay(evals.get_task(REPO / "evals", name), REPO / "evals" / name / "reference", root / name)
    return root


@pytest.mark.parametrize("task,part,plate_text,size", [
    ("laser_panel", "panel", "100 x 60 x 3 mm, thin in z, corners R5, 5 holes, 1 window", ("A4", "1:1")),
    ("nema17_mount", "bracket", "70 x 46 x 4 mm, thin in z, 7 holes", ("A4", "2:1")),
])
def test_the_plates_among_the_reference_designs_are_drawn_and_every_row_passes(evals_laid, monkeypatch, capsys, task, part, plate_text, size):
    monkeypatch.setattr(st, "ROOT", evals_laid)
    code, data = run(capsys, "drawing", task, part, "--all")
    assert code == cli.UNCHECKED and data["stamp"] == "NOT VERIFIED"                       # not verified: the design was not run through `cad verify` here
    assert {r["state"] for r in data["rows"]} == {"PASS"} and data["plate"] == plate_text
    assert (data["sheet"]["size"], data["sheet"]["scale"]) == size and len(data["wrote"]) == 3


def test_the_other_reference_designs_are_refused_for_the_right_reason(evals_laid, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", evals_laid)
    code, data = run(capsys, "drawing", "galvo_mount", "galvo_mount", "--all")
    assert code == cli.UNCHECKED and "it is not a prism along y" in data["rows"][0]["measured"] and data["wrote"] == []
    code, data = run(capsys, "drawing", "endstop_bracket", "bracket")
    assert code == cli.USAGE and "bracket is made by 'fdm'" in data["error"]


# ─── No extra ────────────────────────────────────────────────────────────────

def test_drawings_have_no_extra_and_no_message_sends_a_user_to_one():
    """The SVG and the PDF are written by hand, so the `drawings` extra (matplotlib) went from pyproject.toml, and nothing
    in the package may still say `pip install "cad-agent[drawings]"` or import a plotting package."""
    import tomllib
    extras = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    assert set(extras) == {"metal", "embree", "fasteners", "dev"}
    assert not any("matplotlib" in requirement for requirements in extras.values() for requirement in requirements)
    for path in sorted((REPO / "cad_agent").rglob("*.py")):
        text = path.read_text()
        assert "cad-agent[drawings]" not in text and "matplotlib" not in text, path
