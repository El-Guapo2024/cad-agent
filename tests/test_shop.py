"""`cad shop` and the rules behind it: a laser part is a through-cut its DXF reads back to, a printed part's 3MF is the solid.

Three layers, each with its PASS, FAIL and UNCHECKED paths:

  the rows      dxf.laser_rows and threemf.print_rows on solids, and on solids made wrong on purpose: a part with a
                pocket, a chamfer, a cone; a DXF with an arc turned over, a line gone, a hole moved; a 3MF with a
                hole in it. A file is damaged by wrapping the writer, so that what is damaged is what the rule reads
  the rules     the `shop` part rule and the `[shop]` spec kind, which are silent until a project opts in
  the command   `cad shop` on `works`, a project that is done: the files, the manifest, --draft, --check and
                every exit code. `works` is verified once, in a process standing in for a fresh one, and each
                test works on a copy of it
"""
import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import numpy as np
import pytest
from build123d import Axis, Box, Cone, Cylinder, Edge, Face, GeomType, Pos, Rot, Solid, Sphere, Wire, chamfer, extrude, fillet
from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

from cad_agent import bom as bomlib
from cad_agent import cli, cmdbase, dxf, shop, threemf, verify
from cad_agent import spec as spec_module
from cad_agent import state as st
from cad_agent.runner import approve_views, check_all
from cad_agent.spec import check_spec
from test_bom import ASSEMBLY, BLOCK, CLIP, PANEL, SLUG, SPEC, make_workshop, workshop  # noqa: F401 (the workshop fixture)

SHOP_SPEC = SPEC + "\n[shop]\n"
TALLER = BLOCK.replace('"height": 12.0', '"height": 13.0')      # another block: a design change that is not a gate's business
assert TALLER != BLOCK
POCKET_PANEL = PANEL.replace("    return panel", "    return panel - Pos(0, 0, 1.0) * Box(10, 6, 1.0)")      # a pocket 1 mm deep in the top
assert POCKET_PANEL != PANEL


def replaced(text: str, old: str, new: str = "") -> str:
    assert old in text, f"{old!r} is not in the source it should change"
    return text.replace(old, new)


def states(rows) -> dict:
    return {r.rule: r.state for r in rows}


# ─── The laser rows ──────────────────────────────────────────────────────────

def plate(thickness=4.0):
    """40 x 20 with two M3 holes: a through-cut."""
    return Box(40, 20, thickness) - Pos(-10, 0, 0) * Cylinder(1.7, thickness + 2) - Pos(10, 0, 0) * Cylinder(1.7, thickness + 2)


def rounded_plate():
    """40 x 20 x 4 with R3 corners and two M3 holes: 2 circles, 4 arcs and 4 lines."""
    return fillet(Box(40, 20, 4).edges().filter_by(Axis.Z), 3.0) - Pos(-10, 0, 0) * Cylinder(1.7, 6) - Pos(10, 0, 0) * Cylinder(1.7, 6)


def nurbs(shape):
    """The same solid with every face a B-spline surface, which the faces alone cannot judge."""
    return Solid(BRepBuilderAPI_NurbsConvert(shape.wrapped, True).Shape())


def test_a_prism_passes_through_cut_and_its_dxf_reads_back_to_the_section():
    laser = dxf.laser_rows("plate", plate())
    assert states(laser.rows) == {"laser through-cut": "PASS", "dxf readback": "PASS"}
    cut, readback = laser.rows[0].measured, laser.rows[1].measured
    assert "a prism along z: its faces are 2 cylinders along it, 2 end planes, 4 flat walls" in cut
    assert "6 entities (2 circles, 4 lines) from the part's end face normal to z at z = 2 mm, read back by ezdxf" in readback
    assert "within 0.0000 mm of the mid-plane section's 6 edges, both ways" in readback
    assert laser.dxf.startswith(b"999\n") and laser.cut.source == "end face"                    # a prism is written from its end face
    assert all(r.subject == "plate" and r.source and r.limit != "n/a" for r in laser.rows)       # every row names its limit and where it came from


@pytest.mark.parametrize("what,make,said", [
    ("a pocket", lambda: plate() - Pos(0, 0, 1) * Box(10, 6, 2), "a plane across z at z = 0.000 mm, which is neither end of the part (a pocket floor, a step or a boss)"),
    ("a chamfer", lambda: chamfer(plate().faces().sort_by(Axis.Z)[-1].edges(), 0.5), "a plane slanted to z (a chamfer or a draft)"),
    ("a tapered hole", lambda: plate() - Cone(1.5, 2.5, 6.0), "a cone (a chamfer, a countersink or a taper)"),
    ("a cross hole", lambda: plate() - Rot(Y=90) * Cylinder(1, 60), "a cylinder across z, not along it (a cross hole)"),
    ("a dome", lambda: plate() + Pos(0, 0, 2) * Sphere(3), "a sphere (a dome or a ball end)"),
    ("a rounded hole edge", lambda: fillet(plate().faces().sort_by(Axis.Z)[-1].edges().filter_by(GeomType.CIRCLE)[:1], 0.4),
     "a torus (a fillet)"),
    ("a slot cut across", lambda: plate() - Pos(0, 0, 0) * Rot(Y=90) * extrude(Face(Wire([Edge.make_ellipse(2, 1)])), 60, dir=(0, 0, 1)),
     "an extrusion across z, not along it"),
])
def test_a_part_a_laser_cannot_cut_through_fails_through_cut_and_says_what_is_wrong(what, make, said):
    laser = dxf.laser_rows("plate", make())
    assert states(laser.rows)["laser through-cut"] == "FAIL", what
    assert said in laser.rows[0].measured and "A laser cuts the outline through the whole thickness, nothing else" in laser.rows[0].measured
    assert laser.dxf is not None and laser.cut.source == "section"                      # a draft still has a file: the mid-plane section
    assert states(laser.rows)["dxf readback"] == "PASS"                                 # which does read back


def test_the_same_complaint_is_said_once_with_how_many():
    laser = dxf.laser_rows("plate", chamfer(plate().faces().sort_by(Axis.Z)[-1].edges(), 0.5))
    assert "4 x a plane slanted to z (a chamfer or a draft)" in laser.rows[0].measured and "2 x a cone (" in laser.rows[0].measured


def test_a_part_tilted_off_the_axes_is_not_flat_in_any_of_them():
    laser = dxf.laser_rows("tilt", Rot(X=30) * plate())
    assert states(laser.rows)["laser through-cut"] == "FAIL" and "slanted" in laser.rows[0].measured


def test_faces_the_kernel_gives_as_b_spline_surfaces_are_judged_by_the_sections_alone():
    passing = dxf.laser_rows("plate", nurbs(plate()))
    assert states(passing.rows) == {"laser through-cut": "PASS", "dxf readback": "PASS"}
    assert "its 8 faces are B-spline surfaces judged by the sections alone: 781.86 mm^2 at 5 %" in passing.rows[0].measured
    from build123d import Location, Rectangle
    a = Rectangle(20, 20).face()
    b = Rectangle(10, 10).face().moved(Location((0, 0, 4)))
    funnel = nurbs(Solid.make_loft([a.outer_wire(), b.outer_wire()]))                    # a square getting smaller as it rises
    failing = dxf.laser_rows("funnel", funnel)
    assert states(failing.rows)["laser through-cut"] == "FAIL"
    assert "6 faces are B-spline surfaces, which only the sections can judge" in failing.rows[0].measured
    assert "380.25 mm^2 at 5 %, 225.00 at 50 % and 110.25 at 95 %" in failing.rows[0].measured


def test_a_part_whose_mid_plane_misses_the_material_is_unchecked_not_passed():
    two = Pos(0, 0, -5) * Box(20, 20, 1) + Pos(0, 0, 5) * Box(20, 20, 1)
    laser = dxf.laser_rows("gap", two)
    assert states(laser.rows) == {"laser through-cut": "UNCHECKED", "dxf readback": "UNCHECKED"}
    assert "mid-plane cuts no material" in laser.rows[0].measured and laser.dxf is None


def test_whatever_cannot_be_made_or_read_is_unchecked_and_names_why(monkeypatch):
    # the section cannot be made
    with monkeypatch.context() as m:
        m.setattr(dxf, "cut_at", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the kernel refused")))
        laser = dxf.laser_rows("plate", plate())
        assert states(laser.rows) == {"laser through-cut": "UNCHECKED", "dxf readback": "UNCHECKED"} and laser.dxf is None
        assert "mid-plane section could not be made: RuntimeError: the kernel refused" in laser.rows[1].measured
    # the faces cannot be sorted: through-cut is unchecked and the file is still written and read
    with monkeypatch.context() as m:
        m.setattr(dxf, "faces_report", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no faces")))
        assert states(dxf.laser_rows("plate", plate()).rows) == {"laser through-cut": "UNCHECKED", "dxf readback": "PASS"}
    # a curve it cannot write
    with monkeypatch.context() as m:
        m.setattr(dxf, "primitive", lambda *a, **k: (_ for _ in ()).throw(dxf.Unsupported("a curve of the outline is not in its plane")))
        laser = dxf.laser_rows("plate", plate())
        assert laser.rows[1].state == "UNCHECKED" and "not in its plane" in laser.rows[1].measured and laser.dxf is None
    with monkeypatch.context() as m:
        m.setattr(dxf, "write_dxf", lambda *a, **k: (_ for _ in ()).throw(ValueError("disk full")))
        laser = dxf.laser_rows("plate", plate())
        assert laser.rows[1].state == "UNCHECKED" and "could not be written: ValueError: disk full" in laser.rows[1].measured
    # no ezdxf to read it with: a clear message, never a pass
    with monkeypatch.context() as m:
        m.setattr(dxf, "ezdxf_module", lambda: (_ for _ in ()).throw(dxf.NeedsExtra('reading a DXF back needs ezdxf: pip install "ezdxf>=1.4"')))
        laser = dxf.laser_rows("plate", plate())
        assert laser.rows[1].state == "UNCHECKED" and 'pip install "ezdxf>=1.4"' in laser.rows[1].measured and laser.dxf
    # a file it read and could not compare
    with monkeypatch.context() as m:
        m.setattr(dxf, "compare", lambda *a, **k: (_ for _ in ()).throw(MemoryError("too big")))
        assert dxf.laser_rows("plate", plate()).rows[1].state == "UNCHECKED"


def text_of(write):
    """A replacement for dxf.write_dxf that hands the rule the file after `write(text)` has damaged it."""
    real = dxf.write_dxf

    def damaged(cut, name, stamp=None, loops=None):
        out = write(real(cut, name, stamp, loops).decode("ascii"))
        return out.encode("ascii") if isinstance(out, str) else out
    return damaged


FIRST_LINE = re.compile(r"  0\nLINE\n.*?(?=  0\n[A-Z])", re.S)
FIRST_ARC = re.compile(r"AcDbArc\n 50\n([0-9.]+)\n 51\n([0-9.]+)\n")
FIRST_CIRCLE_X = re.compile(r"AcDbCircle\n 10\n([-0-9.]+)\n")


def swap_arc(text):
    m = FIRST_ARC.search(text)
    return text[:m.start(1)] + m.group(2) + "\n 51\n" + m.group(1) + "\n" + text[m.end():]


def drop_line(text):
    m = FIRST_LINE.search(text)
    return text[:m.start()] + text[m.end():]


def double_line(text):
    m = FIRST_LINE.search(text)
    copy = re.sub(r"  5\n[0-9A-F]+\n", "  5\nFFFF\n", m.group(0), count=1)         # a new handle: the copy is another entity
    return text[:m.end()] + copy + text[m.end():]


def move_circle(text):
    m = FIRST_CIRCLE_X.search(text)
    return text[:m.start(1)] + str(float(m.group(1)) + 0.5) + text[m.end(1):]


@pytest.mark.parametrize("what,damage,said", [
    ("an arc turned over", swap_arc, "the curves are more than 2 mm from the section's"),
    ("a line gone", drop_line, "it was written with 2 circles, 4 arcs, 4 lines but the file holds 2 circles, 4 arcs, 3 lines"),
    ("a line twice", double_line, "the file holds 2 circles, 4 arcs, 5 lines"),
    ("a hole 0.5 mm out", move_circle, "the curves are 0.5000 mm from the section's at their worst, over 0.001 mm"),
    ("inches", lambda t: t.replace(" 70\n4\n  9\n$EXTMIN", " 70\n1\n  9\n$EXTMIN"), "its units are code 1, not 4 (millimetres)"),
    ("no units", lambda t: t.replace("  9\n$INSUNITS\n 70\n4\n", ""), "millimetres"),
    ("a point in the outline", lambda t: t.replace("  0\nENDSEC\n  0\nSECTION\n  2\nOBJECTS", "  0\nPOINT\n  5\nFFFE\n330\n11\n100\nAcDbEntity\n  8\nnone\n100\nAcDbPoint\n 10\n1.0\n 20\n1.0\n 30\n0.0\n  0\nENDSEC\n  0\nSECTION\n  2\nOBJECTS"),
     "the file also holds 1 point, which are not outline"),
])
def test_a_dxf_that_is_not_the_section_fails_the_readback_and_says_how(monkeypatch, what, damage, said):
    monkeypatch.setattr(dxf, "write_dxf", text_of(damage))
    pytest.importorskip("ezdxf")
    laser = dxf.laser_rows("p", rounded_plate())
    assert laser.rows[0].state == "PASS" and laser.rows[1].state == "FAIL", what
    assert said in laser.rows[1].measured, laser.rows[1].measured


def test_a_file_ezdxf_cannot_read_fails_the_readback(monkeypatch):
    monkeypatch.setattr(dxf, "write_dxf", text_of(lambda text: b"this is not a drawing"))
    pytest.importorskip("ezdxf")
    laser = dxf.laser_rows("plate", plate())
    assert laser.rows[1].state == "FAIL" and "the file does not read back: ezdxf cannot read it" in laser.rows[1].measured


def test_a_draft_stamp_is_written_into_the_dxf_and_read_back_and_a_missing_or_stray_one_fails(monkeypatch):
    pytest.importorskip("ezdxf")
    draft = dxf.laser_rows("plate", plate(), "NOT VERIFIED")
    assert states(draft.rows) == {"laser through-cut": "PASS", "dxf readback": "PASS"}
    text = draft.dxf.decode()
    assert text.startswith("999\nNOT VERIFIED: not from a verified design. cad-agent part plate") and "NOT_VERIFIED" in text
    assert dxf.dxf_of(plate(), "plate", "NOT VERIFIED") == draft.dxf != dxf.dxf_of(plate(), "plate")
    real = dxf.write_dxf
    with monkeypatch.context() as m:                    # asked for a stamp, the file has none
        m.setattr(dxf, "write_dxf", lambda cut, name, stamp=None, loops=None: real(cut, name, None, loops))
        assert "the draft stamp is missing from the file" in dxf.laser_rows("plate", plate(), "NOT VERIFIED").rows[1].measured
    with monkeypatch.context() as m:                    # asked for none, the file has one
        m.setattr(dxf, "write_dxf", lambda cut, name, stamp=None, loops=None: real(cut, name, "NOT VERIFIED", loops))
        assert "the file carries a draft stamp it should not" in dxf.laser_rows("plate", plate()).rows[1].measured


# ─── The printed rows ────────────────────────────────────────────────────────

def test_a_printed_part_passes_when_its_3mf_is_closed_and_the_solids_volume():
    printed = threemf.print_rows("plate", plate())
    assert states(printed.rows) == {"3mf watertight": "PASS", "3mf volume": "PASS"}
    assert "1028 triangles, 512 vertices, every edge shared by two triangles, read by" in printed.rows[0].measured
    assert "against the solid's 3127.4" in printed.rows[1].measured and printed.rows[1].limit == "within 0.5 % of the solid's"
    assert printed.three_mf == threemf.write_3mf(printed.mesh, "plate") and printed.stl == threemf.write_stl(printed.mesh, "plate")
    stamped = threemf.print_rows("plate", plate(), "NOT VERIFIED")
    assert b"NOT VERIFIED" in stamped.stl[:80] and stamped.three_mf != printed.three_mf


def damaged_mesh(monkeypatch, make):
    real = threemf.mesh_of
    monkeypatch.setattr(threemf, "mesh_of", lambda solid, *a, **k: make(real(solid, *a, **k)))


def test_a_3mf_with_a_hole_in_it_fails_watertight(monkeypatch):
    damaged_mesh(monkeypatch, lambda m: threemf.Mesh(m.vertices, m.triangles[1:], 0))
    printed = threemf.print_rows("plate", plate())
    assert printed.rows[0].state == "FAIL" and "3 edges have no triangle on their other side" in printed.rows[0].measured


def test_a_3mf_with_a_triangle_twice_fails_watertight(monkeypatch):
    damaged_mesh(monkeypatch, lambda m: threemf.Mesh(m.vertices, np.vstack([m.triangles, m.triangles[:1]]), 0))
    printed = threemf.print_rows("plate", plate())
    assert printed.rows[0].state == "FAIL" and "edges are used by more than two triangles" in printed.rows[0].measured


def test_a_3mf_the_wrong_size_fails_volume_and_one_turned_inside_out_fails_it_too(monkeypatch):
    damaged_mesh(monkeypatch, lambda m: threemf.Mesh((m.vertices * 1.01).astype(np.int64), m.triangles, 0))
    printed = threemf.print_rows("plate", plate())
    assert states(printed.rows) == {"3mf watertight": "PASS", "3mf volume": "FAIL"} and "+3.03" in printed.rows[1].measured
    damaged_mesh(monkeypatch, lambda m: threemf.Mesh(m.vertices, m.triangles[:, ::-1], 0))
    printed = threemf.print_rows("plate", plate())
    assert states(printed.rows) == {"3mf watertight": "PASS", "3mf volume": "FAIL"}
    assert "the mesh is turned inside out or empty" in printed.rows[1].measured


def test_a_3mf_that_is_not_one_object_fails_and_so_does_one_lib3mf_calls_not_manifold(monkeypatch):
    real = threemf.read_3mf
    monkeypatch.setattr(threemf, "read_3mf", lambda data, prefer_lib3mf=True: real(data, prefer_lib3mf)._replace(objects=2, items=3))
    assert "2 objects and 3 build items, not one of each" in threemf.print_rows("plate", plate()).rows[0].measured
    monkeypatch.setattr(threemf, "read_3mf", lambda data, prefer_lib3mf=True: real(data, prefer_lib3mf)._replace(manifold=False))
    assert "lib3mf says it is not manifold and oriented" in threemf.print_rows("plate", plate()).rows[0].measured


def test_a_3mf_nobody_can_read_fails_watertight_and_leaves_volume_unchecked(monkeypatch):
    monkeypatch.setattr(threemf, "read_3mf", lambda *a, **k: (_ for _ in ()).throw(threemf.Unreadable("lib3mf cannot read it: bad zip")))
    printed = threemf.print_rows("plate", plate())
    assert states(printed.rows) == {"3mf watertight": "FAIL", "3mf volume": "UNCHECKED"}
    assert "the file does not read back: lib3mf cannot read it: bad zip" in printed.rows[0].measured and printed.three_mf


def test_whatever_cannot_be_measured_of_a_printed_part_is_unchecked(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(threemf, "mesh_of", lambda *a, **k: (_ for _ in ()).throw(ValueError("the kernel made no triangles for this solid")))
        printed = threemf.print_rows("plate", plate())
        assert states(printed.rows) == {"3mf watertight": "UNCHECKED", "3mf volume": "UNCHECKED"} and printed.three_mf is None
        assert "no mesh: ValueError: the kernel made no triangles" in printed.rows[0].measured
    with monkeypatch.context() as m:
        m.setattr("cad_agent.geom.volume", lambda shape: 0.0)
        printed = threemf.print_rows("plate", plate())
        assert states(printed.rows) == {"3mf watertight": "PASS", "3mf volume": "UNCHECKED"}
        assert "the solid has no volume to compare with" in printed.rows[1].measured


def test_without_lib3mf_the_built_in_reader_reads_the_file_and_the_row_says_so(monkeypatch):
    monkeypatch.setattr(threemf, "_lib3mf", lambda: None)
    printed = threemf.print_rows("plate", plate())
    assert states(printed.rows) == {"3mf watertight": "PASS", "3mf volume": "PASS"}
    assert "read by built-in (lib3mf is not installed)" in printed.rows[0].measured


# ─── The part rule and the [shop] kind: silent until a project opts in ───────────────────────

def rows_of(slug=SLUG):
    with st.reusing_builds():
        machine = st.load_machine(slug)
        return list(check_spec(slug, machine.parts, machine=machine))


def shop_rows(d, text):
    (d / "spec.toml").write_text(SPEC + text)
    return [r for r in rows_of() if r.rule.startswith("spec/shop")]


def test_the_shop_part_rule_is_silent_without_a_shop_table_and_runs_with_one(workshop):
    def shop_checks():
        payload = check_all(SLUG)
        return {(r["subject"], r["rule"]): r["state"] for r in payload["rows"] if r["check"] == "shop"}
    assert shop_checks() == {}                                             # and checks.json has no new row at all
    assert shop.shop_spec(SLUG) is None
    (workshop / "spec.toml").write_text(SHOP_SPEC)
    assert shop.shop_spec(SLUG) == {}
    got = shop_checks()
    assert got == {("panel", "laser through-cut"): "PASS", ("panel", "dxf readback"): "PASS",
                   ("clip", "3mf watertight"): "PASS", ("clip", "3mf volume"): "PASS"}       # and nothing for the cnc block
    (workshop / "spec.toml").write_text("[shop\nnot toml")
    assert shop.shop_spec(SLUG) is None                                    # a spec that does not parse is the spec rule's to say
    (workshop / "spec.toml").write_text("shop = 3\n" + SPEC)
    assert shop.shop_spec(SLUG) is None                                    # a `shop` that is not a table is not an opt-in


def test_the_shop_rule_fails_a_laser_part_with_a_pocket_in_check(workshop):
    (workshop / "spec.toml").write_text(SHOP_SPEC)
    (workshop / "parts" / "panel.py").write_text(POCKET_PANEL)
    got = {(r["subject"], r["rule"]): r["state"] for r in check_all(SLUG)["rows"] if r["check"] == "shop"}
    assert got[("panel", "laser through-cut")] == "FAIL" and got[("panel", "dxf readback")] == "PASS"


def test_the_shop_kind_is_registered_last_and_judges_a_table(workshop):
    from cad_agent import registry as reg
    kinds = {k.name: k for k in reg.spec_kinds()}
    assert kinds["shop"].table is True and kinds["shop"].order == 90 > kinds["heat"].order
    assert reg.spec_kinds()[-1].name == "shop" and "shop" in spec_module.KINDS


def test_an_empty_shop_table_says_how_big_the_bom_is_and_holds_every_made_body_to_its_part(workshop):
    got = shop_rows(workshop, "[shop]\n")
    assert [(r.subject, r.state) for r in got] == [("bom", "PASS"), ("panel", "PASS"), ("clip_left", "PASS"), ("clip_right", "PASS"),
                                                   ("block", "PASS")]
    assert got[0].measured == "4 lines, 5 bodies, 3 to be made here" and got[1].rule == "spec/shop file"
    assert all(r.rule in ("spec/shop", "spec/shop file") and r.source and r.limit != "n/a" for r in got)


def test_bom_holds_each_line_to_its_quantity(workshop):
    got = {r.subject: r for r in shop_rows(workshop, "[shop]\nbom = { panel = 1, clip = 3, block = 0, clip_left = 1, gone = 0, nope = 2, motor = 1 }\n")
           if r.rule == "spec/shop" and r.subject != "bom"}
    assert got["panel"].state == "PASS" and got["motor"].state == "PASS"
    assert (got["clip"].state, got["clip"].measured) == ("FAIL", "2 in the BOM (clip_left, clip_right)")
    assert got["block"].state == "FAIL"                                   # 0 means it must not be there
    assert got["clip_left"].state == "FAIL" and got["clip_left"].measured.startswith("2 in the BOM")        # a body's line is both
    assert got["gone"].state == "PASS" and got["gone"].measured == "not in the BOM"
    assert got["nope"].state == "UNCHECKED" and "no BOM line or body called 'nope' (lines: panel, clip, block, motor)" in got["nope"].measured
    assert got["clip"].limit == "3 of clip"


def test_orderable_asks_a_bought_line_for_a_vendor_and_a_part_number(workshop):
    assert [(r.subject, r.state) for r in shop_rows(workshop, "[shop]\norderable = true\n") if r.rule == "spec/shop" and r.subject != "bom"] == [
        ("bought parts", "PASS")]
    side = json.loads((workshop / "bought" / "motor.json").read_text())
    (workshop / "bought" / "motor.json").write_text(json.dumps({k: v for k, v in side.items() if k != "pn"}))
    got = [r for r in shop_rows(workshop, "[shop]\norderable = true\n") if r.subject == "motor"]
    assert [(r.state, r.measured) for r in got] == [("UNCHECKED", "motor declares no part number: it cannot be ordered from the BOM")]
    (workshop / "bought" / "motor.json").write_text(json.dumps({"source": "x", "verified": True}))
    assert "declares no vendor and no part number" in [r for r in shop_rows(workshop, "[shop]\norderable = true\n") if r.subject == "motor"][0].measured
    (workshop / "assembly.py").write_text(replaced(ASSEMBLY, '        "motor": Pos(0, 0, 40) * bought_solid(SLUG, "motor"),\n'))
    got = [r for r in shop_rows(workshop, "[shop]\norderable = true\n") if r.rule == "spec/shop" and r.subject != "bom"]
    assert [(r.subject, r.state, r.measured) for r in got] == [("bought parts", "N/A", "nothing bought")]


def test_mass_known_asks_every_line_for_a_mass_and_names_the_ones_without(workshop):
    got = [r for r in shop_rows(workshop, '[shop]\nmass = "known"\n') if r.subject == "masses"]
    assert [r.state for r in got] == ["UNCHECKED"]
    assert "1 of 4 lines have no mass: motor (bought part 'motor' declares no mass_g with a mass_source)" in got[0].measured
    side = json.loads((workshop / "bought" / "motor.json").read_text())
    (workshop / "bought" / "motor.json").write_text(json.dumps({**side, "mass_g": 150.0, "mass_source": "the datasheet"}))
    got = [r for r in shop_rows(workshop, '[shop]\nmass = "known"\n') if r.subject == "masses"]
    assert got[0].state == "PASS" and got[0].measured.startswith("every line has a mass, ")
    assert not [r for r in shop_rows(workshop, '[shop]\nmass = "any"\n') if r.subject == "masses"]


def test_files_must_be_ones_cad_shop_makes_for_this_bom(workshop):
    got = {r.subject: r for r in shop_rows(workshop, '[shop]\nfiles = ["panel.dxf", "clip.3mf", "block.step", "bom.csv", "manifest.json"]\n')
           if r.rule == "spec/shop" and r.subject != "bom"}
    assert got["files"].state == "PASS" and "5 files, all made" in got["files"].measured
    bad = {r.subject: r for r in shop_rows(workshop, '[shop]\nfiles = ["panel.3mf", "block.dxf", "motor.step", "ghost.dxf", "drawings/block.pdf", "panel.dxf"]\n')
           if r.rule == "spec/shop" and r.subject != "bom"}
    assert "files" not in bad
    assert bad["panel.3mf"].state == "FAIL" and "panel is laser_cut, which gets panel.step, panel.dxf" in bad["panel.3mf"].measured
    assert bad["block.dxf"].state == "FAIL" and "block is cnc, which gets block.step" in bad["block.dxf"].measured
    assert bad["motor.step"].state == "FAIL" and "motor is not made in this project" in bad["motor.step"].measured
    assert bad["ghost.dxf"].state == "FAIL" and "no part 'ghost' in the BOM" in bad["ghost.dxf"].measured
    assert bad["drawings/block.pdf"].state == "UNCHECKED" and "piece E's" in bad["drawings/block.pdf"].measured


def test_a_body_assembly_py_changes_is_not_the_part_its_file_is_made_from(workshop):
    cut = replaced(ASSEMBLY, '"block": Pos(0, 0, 18) * block,', '"block": Pos(0, 0, 18) * (block - Pos(8, 0, 0) * Cylinder(3, 20)),')
    (workshop / "assembly.py").write_text(replaced(cut, "from build123d import Plane, Pos, mirror", "from build123d import Cylinder, Plane, Pos, mirror"))
    got = {r.subject: r.state for r in shop_rows(workshop, "[shop]\n") if r.rule == "spec/shop file"}
    assert got == {"panel": "PASS", "clip_left": "PASS", "clip_right": "PASS", "block": "FAIL"}


def test_a_shop_table_that_cannot_be_used_is_one_unchecked_row_not_a_crash(workshop):
    for text, said in [("[shop]\nfiles = [1]\n", "files must be a list of file names"),
                       ("[shop]\nbom = { a = 1.5 }\n", "bom must map BOM line names to whole numbers"),
                       ('[shop]\nmass = "all"\n', "mass must be one of known, any"),
                       ("[shop]\norderable = 1\n", "orderable must be true or false"),
                       ("[shop]\nvendors = true\n", "[shop] does not take vendors (keys: bom, orderable, mass, files)")]:
        got = shop_rows(workshop, text)
        assert [(r.state, r.subject) for r in got] == [("UNCHECKED", "[shop]")], text
        assert said in got[0].measured
    (workshop / "assembly.py").write_text("def parts():\n    return {}\n")
    got = shop_rows(workshop, "[shop]\n")
    assert [(r.state, r.subject) for r in got] == [("UNCHECKED", "bom")] and "no bodies" in got[0].measured


# ─── The command ─────────────────────────────────────────────────────────────

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
    """A copy of the verified project to change."""
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    shutil.copytree(verified, tmp_path / SLUG)
    return tmp_path / SLUG


def run(capsys, *argv):
    code = cli.main(["--json", *argv])
    out = capsys.readouterr().out.strip().splitlines()
    return code, json.loads(out[-1])["data"]


def reverify(d: Path) -> None:
    """After a test changed a part: render it, approve the render, verify, and see that the design is done."""
    check_all(SLUG)
    approve_views(SLUG)
    record = verify.run(SLUG, fresh=True, mode="test")
    assert record["verdict"] == "PASS", [r for r in record["rows"] if r["state"] != "PASS"]
    assert verify.status(SLUG)["done"] is True


def folder_bytes(d: Path) -> dict:
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def no_drawings(monkeypatch):
    """Piece E's module out of the way, whatever state it is in."""
    real = cmdbase.resolve
    monkeypatch.setattr(cmdbase, "resolve", lambda target: None if target == shop.DRAWINGS else real(target))


EXPECTED = ["block.step", "bom.csv", "bom.json", "clip.3mf", "clip.step", "clip.stl", "panel.dxf", "panel.step"]


def test_cad_shop_writes_the_files_the_bom_names_and_a_manifest_that_vouches_for_them(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.OK and data["done"] is True and data["draft"] is False
    folder = project / "out" / "shop"
    files = folder_bytes(folder)
    assert sorted(files) == sorted(EXPECTED + ["manifest.json"])
    manifest = json.loads(files["manifest.json"])
    assert manifest["verdict"] == "PASS" and manifest["draft"] is False and manifest["done"] is True and manifest["reasons"] == []
    assert manifest["verified"]["verdict"] == "PASS" and manifest["verified"]["at"] and manifest["commit"] is None
    assert [f["path"] for f in manifest["files"]] == EXPECTED
    for f in manifest["files"]:
        assert hashlib.sha256(files[f["path"]]).hexdigest() == f["sha256"] and len(files[f["path"]]) == f["bytes"]
    assert {(f["path"], f["part"], f["format"]) for f in manifest["files"]} >= {
        ("panel.dxf", "panel", "dxf"), ("clip.3mf", "clip", "3mf"), ("clip.stl", "clip", "stl"), ("block.step", "block", "step"),
        ("bom.csv", None, "csv")}
    assert manifest["rows"] == [{"rule": "3mf watertight", "subject": "clip", "state": "PASS"},
                                {"rule": "3mf volume", "subject": "clip", "state": "PASS"},
                                {"rule": "laser through-cut", "subject": "panel", "state": "PASS"},
                                {"rule": "dxf readback", "subject": "panel", "state": "PASS"}] + [
        {"rule": "shop file", "subject": s, "state": "PASS"} for s in ("panel", "clip_left", "clip_right", "block")]
    assert manifest["bom"] == {"lines": 4, "bodies": 5, "mass_known_g": manifest["bom"]["mass_known_g"], "mass_complete": False}
    assert manifest["skipped"] == [] and manifest["missing"] == []
    assert manifest["drawings"]["built"] is False and "drawings are not built yet" in manifest["drawings"]["why"]
    assert files["bom.csv"].decode() == bomlib.csv_text(bomlib.build(SLUG)) and data["wrote"][-1].endswith("manifest.json")
    for name in ("panel.dxf", "clip.3mf", "clip.stl", "panel.step", "bom.json"):
        assert b"NOT VERIFIED" not in files[name]                               # a verified run is not stamped
    # the files are the ones `cad export` writes
    assert files["panel.dxf"] == dxf.dxf_of(st.build_part(SLUG, "panel")[0], "panel")


def test_the_same_design_writes_the_same_folder_every_time(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    first = folder_bytes(project / "out" / "shop")
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    assert folder_bytes(project / "out" / "shop") == first


def test_cad_shop_leaves_what_it_did_not_write_alone_and_removes_what_it_no_longer_makes(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    folder = project / "out" / "shop"
    folder.mkdir(parents=True)
    (folder / "my nesting.txt").write_text("keep me")
    assert run(capsys, "shop", SLUG)[0] == cli.OK and (folder / "my nesting.txt").read_text() == "keep me"
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["files"].append({"path": "old.dxf", "part": "old", "format": "dxf", "sha256": "0" * 64, "bytes": 1})
    (folder / "manifest.json").write_text(json.dumps(manifest))
    (folder / "old.dxf").write_text("a part that is gone")
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    assert not (folder / "old.dxf").exists() and (folder / "my nesting.txt").exists() and not list(folder.glob("*.tmp"))


def test_a_part_the_assembly_does_not_use_is_left_out_and_the_manifest_says_so(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    (project / "parts" / "spare.py").write_text(CLIP.replace("Clip:", "Spare:"))
    code, data = run(capsys, "shop", SLUG, "--draft")                      # a part nobody verified: a draft
    assert data["skipped"] == [{"part": "spare", "why": "assembly.py does not use it"}]
    assert not (project / "out" / "shop" / "spare.step").exists()
    assert json.loads((project / "out" / "shop" / "manifest.json").read_text())["skipped"] == data["skipped"]


def test_a_project_with_no_assembly_makes_one_of_each_part(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    (project / "assembly.py").unlink()
    code, data = run(capsys, "shop", SLUG, "--draft")
    assert code == cli.UNCHECKED and data["skipped"] == []
    assert sorted(f["path"] for f in data["files"]) == sorted(EXPECTED)


def test_a_design_that_is_not_done_writes_nothing_and_exits_2(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    (project / "parts" / "block.py").write_text(TALLER)
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.UNCHECKED and data["done"] is False and "the design changed since it was verified" in data["reasons"]
    assert data["wrote"] == [] and not (project / "out" / "shop").exists()
    out = cli.main(["shop", SLUG])
    assert out == cli.UNCHECKED and "NOT DONE" in capsys.readouterr().out
    # and a folder from an earlier run is not touched
    (project / "parts" / "block.py").write_text(BLOCK)
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    before = folder_bytes(project / "out" / "shop")
    (project / "parts" / "block.py").write_text(TALLER)
    assert run(capsys, "shop", SLUG)[0] == cli.UNCHECKED and folder_bytes(project / "out" / "shop") == before


def test_a_design_with_no_verdict_at_all_is_not_done_either(project, capsys):
    (project / "verify.json").unlink()
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.UNCHECKED and data["reasons"] == ["never verified: run `cad verify`"]


def test_a_draft_is_written_stamped_everywhere_and_exits_2_while_the_design_is_not_done(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    (project / "parts" / "block.py").write_text(TALLER)
    code, data = run(capsys, "shop", SLUG, "--draft")
    assert code == cli.UNCHECKED and data["draft"] is True and data["done"] is False
    folder = project / "out" / "shop"
    files = folder_bytes(folder)
    assert sorted(files) == sorted(EXPECTED + ["manifest.json"])
    manifest = json.loads(files["manifest.json"])
    assert manifest["verdict"] == "NOT VERIFIED" and manifest["draft"] is True and manifest["done"] is False
    assert files["panel.dxf"].decode().startswith("999\nNOT VERIFIED: not from a verified design.") and b"NOT_VERIFIED" in files["panel.dxf"]
    assert b"FILE_DESCRIPTION(('NOT VERIFIED','Open CASCADE Model')" in files["panel.step"]
    assert files["clip.stl"][:80].startswith(b"cad-agent: clip NOT VERIFIED")
    assert b"clip NOT VERIFIED" in zipfile.ZipFile(io.BytesIO(files["clip.3mf"])).read("3D/3dmodel.model")
    assert files["bom.csv"].decode().splitlines()[0].endswith(",Status") and files["bom.csv"].decode().count("NOT VERIFIED") == 4
    assert json.loads(files["bom.json"])["stamp"] == "NOT VERIFIED"
    assert all(f["sha256"] == hashlib.sha256(files[f["path"]]).hexdigest() for f in manifest["files"])


def test_a_draft_of_a_design_that_is_done_still_says_so_and_exits_0(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    code, data = run(capsys, "shop", SLUG, "--draft")
    assert code == cli.OK and data["done"] is True
    assert json.loads((project / "out" / "shop" / "manifest.json").read_text())["draft"] is True


def test_a_row_that_fails_stops_cad_shop_and_a_draft_writes_the_file_anyway(project, capsys, monkeypatch):
    # a pocket passes verify (nothing opted in to the rule) and the shop is where a laser cutter would find out
    no_drawings(monkeypatch)
    (project / "parts" / "panel.py").write_text(POCKET_PANEL)
    reverify(project)
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.FAIL and not (project / "out" / "shop").exists() and data["wrote"] == []
    assert [(r["subject"], r["rule"], r["state"]) for r in data["rows"]] == [("panel", "laser through-cut", "FAIL")]
    assert "a plane across z at z = 0.500 mm" in data["rows"][0]["measured"]
    text = cli.main(["shop", SLUG])
    assert text == cli.FAIL and "nothing was written: a row failed" in capsys.readouterr().out
    code, data = run(capsys, "shop", SLUG, "--draft")
    assert code == cli.FAIL and (project / "out" / "shop" / "panel.dxf").exists()           # a draft is for looking at
    assert {"rule": "laser through-cut", "subject": "panel", "state": "FAIL"} in json.loads(
        (project / "out" / "shop" / "manifest.json").read_text())["rows"]


def test_a_row_that_cannot_be_settled_stops_cad_shop_with_2(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    monkeypatch.setattr(threemf, "mesh_of", lambda *a, **k: (_ for _ in ()).throw(ValueError("the kernel made no triangles for this solid")))
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.UNCHECKED and not (project / "out" / "shop").exists()
    assert {(r["subject"], r["rule"], r["state"]) for r in data["rows"]} == {("clip", "3mf watertight", "UNCHECKED"), ("clip", "3mf volume", "UNCHECKED")}
    assert cli.main(["shop", SLUG]) == cli.UNCHECKED and "a row could not be settled" in capsys.readouterr().out
    code, data = run(capsys, "shop", SLUG, "--draft")                       # and a draft has everything but the printed part's mesh
    assert code == cli.UNCHECKED and data["missing"] == ["clip.3mf", "clip.stl"]
    assert json.loads((project / "out" / "shop" / "manifest.json").read_text())["missing"] == ["clip.3mf", "clip.stl"]


def test_bad_arguments_and_a_library_that_is_missing_are_usage_errors(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    assert run(capsys, "shop", "nope")[0] == cli.USAGE
    assert cli.main(["shop", SLUG, "--draft", "--check"]) == cli.USAGE
    assert "not allowed with argument" in capsys.readouterr().err
    assert cli.main(["shop", SLUG, "--nonsense"]) == cli.USAGE
    monkeypatch.setattr(dxf, "ezdxf_module", lambda: (_ for _ in ()).throw(dxf.NeedsExtra('reading a DXF back needs ezdxf: pip install "ezdxf>=1.4"')))
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.USAGE and 'pip install "ezdxf>=1.4"' in data["error"] and not (project / "out" / "shop").exists()
    (project / "parts" / "panel.py").unlink()                                 # no laser part, so nothing needs it
    (project / "assembly.py").write_text(replaced(replaced(ASSEMBLY, '        "panel": panel,\n'), '    panel, _ = build_part(SLUG, "panel")\n'))
    assert run(capsys, "shop", SLUG, "--draft")[0] == cli.UNCHECKED


def test_an_unexpected_failure_is_a_crash_and_exit_4(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    monkeypatch.setattr(shop, "write_folder", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.CRASH and "RuntimeError: boom" in data["error"]


def test_a_part_that_will_not_build_is_a_fail(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    monkeypatch.setattr(st, "build_part", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no such solid")))
    code, data = run(capsys, "shop", SLUG, "--draft")
    assert code == cli.FAIL and "did not build" in data["error"] and "no such solid" in data["error"]


def test_cad_shop_builds_from_source_and_never_from_the_cache(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    seen = []
    real = st._cache_lookup
    monkeypatch.setattr(st, "_cache_lookup", lambda *a, **k: (seen.append(a), real(*a, **k))[1])
    with st.caching_builds(True):                                              # even where something outside asked for it
        assert run(capsys, "shop", SLUG)[0] == cli.OK
    assert seen == []


# ─── --check ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def shopped(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    return project / "out" / "shop"


def test_check_is_clean_when_the_folder_is_what_a_fresh_run_writes(shopped, capsys):
    before = folder_bytes(shopped)
    code, data = run(capsys, "shop", SLUG, "--check")
    assert code == cli.OK and data["differences"] == [] and data["check"] is True
    assert folder_bytes(shopped) == before                                      # and it wrote nothing
    assert cli.main(["shop", SLUG, "--check"]) == cli.OK
    assert "is what a fresh run writes: 8 files, byte for byte" in capsys.readouterr().out


def test_check_names_every_way_a_folder_can_differ(shopped, capsys):
    (shopped / "clip.stl").write_bytes((shopped / "clip.stl").read_bytes() + b"x")                  # edited: not what the manifest recorded
    (shopped / "panel.step").unlink()                                                                # missing
    (shopped / "stray.txt").write_text("not ours")                                                   # extra
    manifest = json.loads((shopped / "manifest.json").read_text())
    by_path = {f["path"]: f for f in manifest["files"]}
    (shopped / "block.step").write_bytes(b"another block")                                           # stale: as recorded, but not as made now
    by_path["block.step"]["sha256"] = hashlib.sha256(b"another block").hexdigest()
    manifest["files"] = [f for f in manifest["files"] if f["path"] != "bom.json"] + [                # new: bom.json is made and not listed
        {"path": "gone.dxf", "part": "gone", "format": "dxf", "sha256": "1" * 64, "bytes": 1}]       # gone: listed and no longer made
    (shopped / "manifest.json").write_text(json.dumps(manifest))
    code, data = run(capsys, "shop", SLUG, "--check")
    assert code == cli.FAIL
    assert {(d["path"], d["why"]) for d in data["differences"]} == {
        ("clip.stl", "edited"), ("panel.step", "missing"), ("block.step", "stale"), ("bom.json", "new"), ("gone.dxf", "gone"),
        ("stray.txt", "extra")}
    assert all(d["detail"] for d in data["differences"])
    assert cli.main(["shop", SLUG, "--check"]) == cli.FAIL
    text = capsys.readouterr().out
    assert "edited   clip.stl" in text and "missing  panel.step" in text and "extra    stray.txt" in text


def test_check_does_not_mind_a_step_the_other_kernel_wrote(shopped, capsys):
    step = shopped / "block.step"
    other = re.sub(rb"processor [0-9.]+", b"processor 6.1", step.read_bytes(), count=1)
    assert other != step.read_bytes()
    step.write_bytes(other)
    manifest = json.loads((shopped / "manifest.json").read_text())
    next(f for f in manifest["files"] if f["path"] == "block.step")["sha256"] = hashlib.sha256(other).hexdigest()
    (shopped / "manifest.json").write_text(json.dumps(manifest))                     # as if `cad shop` had run on that kernel
    assert run(capsys, "shop", SLUG, "--check")[0] == cli.OK
    step.write_bytes(other.replace(b"DATA;", b"DATA; ", 1))                          # but any other change to it is stale
    manifest["files"][[f["path"] for f in manifest["files"]].index("block.step")]["sha256"] = hashlib.sha256(step.read_bytes()).hexdigest()
    (shopped / "manifest.json").write_text(json.dumps(manifest))
    code, data = run(capsys, "shop", SLUG, "--check")
    assert code == cli.FAIL and [(d["path"], d["why"]) for d in data["differences"]] == [("block.step", "stale")]


def test_check_cannot_say_when_there_is_nothing_to_compare_or_nothing_that_could_pass(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    code, data = run(capsys, "shop", SLUG, "--check")                                  # no out/shop yet
    assert code == cli.UNCHECKED and data["reasons"] == ["no out/shop/manifest.json"]
    assert run(capsys, "shop", SLUG, "--draft")[0] == cli.OK
    code, data = run(capsys, "shop", SLUG, "--check")                                  # a draft is nothing to certify
    assert code == cli.UNCHECKED and data["reasons"] == ["out/shop/ is a draft"]
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    (project / "parts" / "block.py").write_text(TALLER)
    code, data = run(capsys, "shop", SLUG, "--check")                                  # the design moved on
    assert code == cli.UNCHECKED and data["done"] is False
    (project / "out" / "shop" / "manifest.json").write_text("{ not json")
    (project / "parts" / "block.py").write_text(BLOCK)
    assert run(capsys, "shop", SLUG, "--check")[0] == cli.UNCHECKED                    # a manifest nobody can read is no manifest


def test_check_fails_when_a_fresh_run_would_fail_and_is_unchecked_when_it_could_not_settle(shopped, capsys, project, monkeypatch):
    (project / "parts" / "panel.py").write_text(POCKET_PANEL)
    reverify(project)
    code, data = run(capsys, "shop", SLUG, "--check")
    assert code == cli.FAIL and data["rows"][0]["rule"] == "laser through-cut"
    (project / "parts" / "panel.py").write_text(PANEL)
    reverify(project)
    monkeypatch.setattr(threemf, "mesh_of", lambda *a, **k: (_ for _ in ()).throw(ValueError("no triangles")))
    code, data = run(capsys, "shop", SLUG, "--check")                                  # the two files it could not make are not "gone"
    assert code == cli.UNCHECKED and {r["state"] for r in data["rows"]} == {"UNCHECKED"}
    assert not any(d["why"] == "gone" for d in data["differences"])


# ─── The commit ──────────────────────────────────────────────────────────────

def git(d, *args):
    return subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_the_manifest_records_the_commit_and_a_commit_that_leaves_the_design_alone_keeps_it_done(project, capsys, monkeypatch):
    no_drawings(monkeypatch)
    git(project, "init", "-q", "-b", "main")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "design")
    verify.run(SLUG, fresh=True, mode="test")
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    head = git(project, "rev-parse", "HEAD")
    manifest = json.loads((project / "out" / "shop" / "manifest.json").read_text())
    assert (manifest["commit"], manifest["dirty"], manifest["verified"]["commit"]) == (head, False, head)
    assert manifest["tree"] == git(project, "rev-parse", "HEAD^{tree}")
    (project / "notes.md").write_text("not the design")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "notes")
    code, data = run(capsys, "shop", SLUG, "--check")                                  # HEAD moved, the design did not
    assert code == cli.OK and data["differences"] == []
    (project / "parts" / "block.py").write_text(TALLER)
    check_all(SLUG)
    approve_views(SLUG)                                                                # the taller block's render is the baseline now
    verify.run(SLUG, fresh=True, mode="test")                                          # verified, but not committed
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.UNCHECKED and any("uncommitted" in r for r in data["reasons"])
    git(project, "commit", "-q", "-am", "taller block")
    verify.run(SLUG, fresh=True, mode="test")
    assert run(capsys, "shop", SLUG)[0] == cli.OK
    assert json.loads((project / "out" / "shop" / "manifest.json").read_text())["commit"] == git(project, "rev-parse", "HEAD") != head


# ─── Piece E's drawings ──────────────────────────────────────────────────────

def hook(monkeypatch, fn):
    real = cmdbase.resolve
    monkeypatch.setattr(cmdbase, "resolve", lambda target: fn if target == shop.DRAWINGS else real(target))


def test_drawings_are_written_when_the_module_provides_them_and_the_manifest_lists_them(project, capsys, monkeypatch):
    calls = []

    def shop_drawings(slug, parts, processes, stamp):
        calls.append((slug, sorted(parts), dict(processes), stamp, all(hasattr(s, "bounding_box") for s in parts.values())))
        return {"files": {"drawings/block.pdf": b"%PDF fake", "drawings/block.dxf": b"drawing dxf"}, "skipped": {"panel": "not machined"}}
    hook(monkeypatch, shop_drawings)
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.OK and calls == [(SLUG, ["block", "clip", "panel"], {"block": "cnc", "clip": "fdm", "panel": "laser_cut"}, None, True)]
    folder = project / "out" / "shop"
    assert (folder / "drawings" / "block.pdf").read_bytes() == b"%PDF fake"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["drawings"] == {"built": True, "files": ["drawings/block.dxf", "drawings/block.pdf"], "skipped": {"panel": "not machined"}}
    assert {"drawings/block.pdf", "drawings/block.dxf"} <= {f["path"] for f in manifest["files"]}
    assert {"rule": "drawings", "subject": "drawings", "state": "PASS"} in manifest["rows"]
    assert run(capsys, "shop", SLUG, "--check")[0] == cli.OK
    calls.clear()
    assert run(capsys, "shop", SLUG, "--draft")[0] == cli.OK and calls[0][3] == "NOT VERIFIED"        # the stamp goes to the hook
    hook(monkeypatch, lambda *a: {"files": {}, "skipped": {}})                                          # and a drawing no longer made goes
    assert run(capsys, "shop", SLUG)[0] == cli.OK and not (folder / "drawings").exists()


def test_drawings_that_cannot_be_made_are_an_unchecked_row_and_say_what_to_install(project, capsys, monkeypatch):
    def missing(*a):
        raise ModuleNotFoundError("No module named 'ezdxf'", name="ezdxf")

    def wrong_place(*a):
        return {"files": {"../outside.pdf": b"x"}}

    def broken(*a):
        raise RuntimeError("the sheet is full")

    hook(monkeypatch, missing)
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.UNCHECKED and not (project / "out" / "shop").exists()
    measured = data["rows"][-1]["measured"]            # a core library has no extra to name, and no extra is named for drawings
    assert data["rows"][-1]["rule"] == "drawings" and "the drawings need ezdxf, which is not installed" in measured
    assert "cad-agent[" not in measured and "matplotlib" not in measured
    hook(monkeypatch, wrong_place)
    assert "not under drawings/" in run(capsys, "shop", SLUG)[1]["rows"][-1]["measured"]
    hook(monkeypatch, broken)
    code, data = run(capsys, "shop", SLUG)
    assert code == cli.UNCHECKED and "RuntimeError: the sheet is full" in data["rows"][-1]["measured"]
    real = cmdbase.resolve
    monkeypatch.setattr(cmdbase, "resolve", lambda target: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'bd_warehouse'", name="bd_warehouse"))
                        if target == shop.DRAWINGS else real(target))
    assert 'pip install "cad-agent[fasteners]"' in run(capsys, "shop", SLUG)[1]["rows"][-1]["measured"]
    code, data = run(capsys, "shop", SLUG, "--draft")                                  # and a draft goes on without them
    assert code == cli.UNCHECKED and (project / "out" / "shop" / "panel.dxf").exists()
    assert data["drawings"]["built"] is False and "bd_warehouse" in data["drawings"]["why"]
