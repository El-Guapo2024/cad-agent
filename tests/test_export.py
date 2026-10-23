"""A part's files are the same bytes whenever and wherever they are written.

A STEP is a design file (a bought part is one, and `cad verify` hashes bought/*), but OCCT puts the
process into it: the wall clock in the header, and a count of assembly occurrences that only a fresh
process starts at 1. The kernel tests below export a part that carries that count, a body returned as
`Pos(...) * body`, because a plain solid has nothing in it that moves.

The same goes for what a shop and a printer read (step 6, piece D): a DXF, a 3MF and an STL are pinned by their
hashes below, and the hashes are the ones OCCT 7.9 (build123d 0.11) and OCCT 8.0 (build123d 0.13) both write, so
this file passes on either kernel or a writer has drifted. So is a STEP, but for the one header line that names the
kernel that wrote it. Each of them is checked too against a reader that shares no code with the writer: ezdxf and
trimesh for the DXF, lib3mf for the 3MF.
"""
import hashlib
import io
import re
import struct
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from build123d import (Axis, Box, Cylinder, Edge, Face, Plane, Pos, Rot, Sphere, Vector, Wire, extrude, fillet,
                       import_step)

from cad_agent import dxf, threemf
from cad_agent import export as ex
from cad_agent import state as st
from test_cli import PLATE

REPO = Path(__file__).resolve().parent.parent

PLACED = '''"""Test plate, returned placed: STEP stores `Pos(...) * body` as an assembly of one."""
from build123d import Box, Cylinder, Pos

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0
EXPECT_FEATURES = 1

PARAMS = {"length": 40.0, "width": 20.0, "thickness": 5.0, "hole": 4.0}


def build(length, width, thickness, hole):
    body = Box(length, width, thickness) - Cylinder(hole / 2, thickness + 2)
    return Pos(0, 0, -thickness / 2) * body
'''

# What OCCT wrote for an assembly in a busy process, cut down to the lines that matter.
BUSY = b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Open CASCADE Model'),'2;1');
FILE_NAME('it''s a name','2026-10-07T21:29:16',('Author'),(
    'Open CASCADE'),'Open CASCADE STEP processor 7.9','build123d',
  'Unknown');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#7 = PRODUCT('7','7','',(#8));
#54 = NEXT_ASSEMBLY_USAGE_OCCURRENCE('27','inner','',#5,#31,$);
#403 = NEXT_ASSEMBLY_USAGE_OCCURRENCE('25','=>[0:1:1:3]','',#31,#58,$);
#752 = NEXT_ASSEMBLY_USAGE_OCCURRENCE('26','=>[0:1:1:4]','',#31,#407,$);
ENDSEC;
END-ISO-10303-21;
"""


@pytest.fixture()
def shop(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    parts = tmp_path / "shop" / "parts"
    parts.mkdir(parents=True)
    (parts / "placed.py").write_text(PLACED)
    (parts / "plate.py").write_text(PLATE)
    return tmp_path / "shop"


# ─── What changes, with no kernel ────────────────────────────────────────────

def test_the_stamp_is_pinned_and_the_occurrences_count_from_one():
    out = ex.canonical_step(BUSY)
    assert b"FILE_NAME('it''s a name','1970-01-01T00:00:00',('Author')" in out      # the name is left alone
    assert re.findall(rb"OCCURRENCE\('(\d+)'", out) == [b"3", b"1", b"2"]           # 27, 25, 26 keep their order
    assert b"PRODUCT('7','7'" in out                                                # other numbers are not touched
    assert ex.canonical_step(out) == out
    changed = [a for a, b in zip(BUSY.splitlines(), out.splitlines()) if a != b]
    assert len(out.splitlines()) == len(BUSY.splitlines()) and len(changed) == 4    # the stamp, three occurrences


def test_a_stamp_that_wraps_onto_the_next_line_is_still_found():
    wrapped = BUSY.replace(b"'it''s a name','2026", b"'a label long enough that OCCT starts a new line before the stamp',\n  '2026")
    assert b"\n  '1970-01-01T00:00:00'," in ex.canonical_step(wrapped)


# ─── The same part, any process ──────────────────────────────────────────────

def test_one_part_is_one_file_in_a_busy_process_and_in_a_fresh_one(shop, tmp_path):
    first = ex.export_part("shop", "placed").read_bytes()
    assert b"OCCURRENCE('1'," in first                       # whatever this process has exported before
    assert f"'{ex.STEP_STAMP}'".encode() in first            # and whatever the clock says
    for _ in range(3):                                       # a worker that has done other exports
        ex.export_part("shop", "plate")
        ex.export_part("shop", "placed")
    assert ex.export_part("shop", "placed").read_bytes() == first
    # the code `cad export` runs, in an interpreter that has exported nothing
    fresh = subprocess.run([sys.executable, "-m", "cad_agent", "--projects", str(tmp_path), "export",
                            "shop", "placed"], cwd=REPO, capture_output=True, text=True, timeout=300)
    assert fresh.returncode == 0, fresh.stderr
    assert (shop / "out" / "placed.step").read_bytes() == first


def test_the_file_still_reads_back_as_the_same_solid(shop):
    solid, _ = st.build_part("shop", "placed")
    data = ex.export_part("shop", "placed").read_bytes()
    assert data.startswith(b"ISO-10303-21;") and data.rstrip().endswith(b"END-ISO-10303-21;")
    assert b"AUTOMOTIVE_DESIGN { 1 0 10303 214" in data      # still AP214, as before
    back = import_step(str(shop / "out" / "placed.step"))
    assert back.volume == pytest.approx(solid.volume, rel=1e-9)
    a, b = solid.bounding_box(), back.bounding_box()
    for u, v in ((a.min, b.min), (a.max, b.max)):
        assert (u.X, u.Y, u.Z) == pytest.approx((v.X, v.Y, v.Z), abs=1e-6)


def test_write_step_takes_any_shape_and_a_str_path(tmp_path):
    p = ex.write_step(Pos(1, 2, 3) * (Box(10, 10, 10) - Cylinder(2, 12)), str(tmp_path / "x.step"))
    assert p == tmp_path / "x.step" and p.read_bytes().startswith(b"ISO-10303-21;")


def test_every_step_the_repo_writes_goes_through_write_step():
    # A raw build123d export_step brings the clock and the counter back. That includes the scripts
    # that make the eval tasks' given files, which is where the counter first showed.
    raw = [p.relative_to(REPO).as_posix() for base in ("cad_agent", "evals") for p in (REPO / base).rglob("*.py")
           if p != REPO / "cad_agent" / "export.py" and re.search(r"\bexport_step\b", p.read_text())]
    assert raw == [], f"use cad_agent.export.write_step: {raw}"


# ─── What a shop and a printer read: pinned, and read back by code that is not ours ──────────────────

# sha256 of each format of the two test parts, written by OCCT 7.9 and by OCCT 8.0 alike (a STEP without the
# processor line that names the kernel: `kernel_free`). If a hash moves, either the writer changed on purpose (pin
# the new one), or the kernel changed what it gives it (a bug here).
PINNED = {
    ("plate", "step"): "7ca950f6e062bd6d31ac05b8cf71d6d9f9d82aa679b94142be00d1269e5d6b9e",
    ("plate", "stl"): "f5cd088af9256d7e9b6b351d08fa8af77b89f7ce673c138b963e9af1dfc4cc38",
    ("plate", "3mf"): "8c6840d1e86519f0f0ace81e66d7d7434287005c4a46970f105f72a97c98c147",
    ("plate", "dxf"): "960fedb4993416a215544d6255d1cae5325e19a91679df56744461c04f28ef29",
    ("placed", "step"): "70f82db32de16c5d106971cc661349091c9108e87046f69749247822814e0fdd",
    ("placed", "stl"): "b1c71ccdb5663c4ff96bb2a8718d4be120d7cd62bec070d08df73224b3d5f753",
    ("placed", "3mf"): "b8efe6eed0b291b83b270be62499587d89009fd06a36ecf17ed01717d5c27b4e",
    ("placed", "dxf"): "8212d5b0381bf034ebc753c91c30814630e9585ce4d18f8bfa3b8f74af0b5f58",
}


def test_export_writes_every_format_and_refuses_one_it_does_not_know(shop):
    assert ex.FORMATS == ("step", "stl", "3mf", "dxf")
    for fmt in ex.FORMATS:
        p = ex.export_part("shop", "plate", fmt)
        assert p == shop / "out" / f"plate.{fmt}" and p.stat().st_size > 100
    with pytest.raises(ValueError, match="unsupported format 'obj'"):
        ex.export_part("shop", "plate", "obj")
    solid, _ = st.build_part("shop", "plate")
    with pytest.raises(ValueError, match="unsupported format"):
        ex.render(solid, "plate", "obj")


@pytest.mark.parametrize("name,fmt", sorted(PINNED))
def test_a_part_is_the_same_bytes_in_every_format_on_either_kernel(shop, name, fmt):
    data = ex.export_part("shop", name, fmt).read_bytes()
    got = hashlib.sha256(ex.kernel_free(data) if fmt == "step" else data).hexdigest()
    assert got == PINNED[name, fmt], (f"{name}.{fmt} is {got}. If the writer changed on purpose, pin this; if not, the "
                                      "kernel gave it other triangles, edges or numbers: OCCT 7.9 and 8.0 must agree")


def test_a_fresh_process_writes_the_same_dxf_3mf_and_stl(shop, tmp_path):
    first = {fmt: ex.export_part("shop", "plate", fmt).read_bytes() for fmt in ("dxf", "3mf", "stl")}
    code = ("import sys\nfrom cad_agent import cli\n"
            "for fmt in ('dxf', '3mf', 'stl'):\n"
            "    assert cli.main(['--projects', sys.argv[1], 'export', 'shop', 'plate', '--format', fmt]) == 0\n")
    fresh = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=REPO, capture_output=True, text=True, timeout=300)
    assert fresh.returncode == 0, fresh.stderr
    for fmt, data in first.items():
        assert (shop / "out" / f"plate.{fmt}").read_bytes() == data


def test_a_step_keeps_the_kernel_it_names_and_kernel_free_is_the_same_file_without_it():
    head = b"FILE_NAME('a','2026-01-01T00:00:00',('x'),(\n 'o'),'Open CASCADE STEP processor "
    for version in (b"7.9", b"8.0", b"8.1.2"):
        text = head + version + b"','b','u');\n"
        assert b"processor " + version + b"'" in ex.canonical_step(text)                      # true, and left as it is
        assert b"STEP processor','b','u')" in ex.kernel_free(text)
    assert ex.kernel_free(head + b"7.9','b','u');\n") == ex.kernel_free(head + b"8.0','b','u');\n")
    assert ex.kernel_free(b"no header") == b"no header"


def test_a_stamp_goes_into_the_step_description_and_the_file_still_reads_back(shop, tmp_path):
    solid, _ = st.build_part("shop", "plate")
    plain, draft = ex.render(solid, "plate", "step"), ex.render(solid, "plate", "step", "NOT VERIFIED")
    assert b"FILE_DESCRIPTION(('NOT VERIFIED','Open CASCADE Model'),'2;1')" in draft and plain != draft
    assert draft.replace(b"'NOT VERIFIED',", b"", 1) == plain                    # nothing else moved
    (tmp_path / "draft.step").write_bytes(draft)
    assert import_step(str(tmp_path / "draft.step")).volume == pytest.approx(solid.volume, rel=1e-9)
    assert b"it''s" in ex.stamp_step(b"FILE_DESCRIPTION(('x'),'2;1');", "it's")        # an apostrophe is doubled


# ─── A DXF: FreeCAD's entities, in millimetres, read back by ezdxf and by trimesh ───────────────────────────

@pytest.fixture(scope="module")
def rounded():
    """60 x 30 x 3 with R5 corners, a round hole and a rectangular window: 1 circle, 4 arcs and 8 lines."""
    plate = fillet(Box(60, 30, 3).edges().filter_by(Axis.Z), 5.0)
    return plate - Pos(-15, 0, 0) * Cylinder(3, 5) - Pos(15, 0, 0) * Box(12, 4, 5)


def read_dxf(data: bytes):
    ezdxf = pytest.importorskip("ezdxf")
    return ezdxf.read(io.StringIO(data.decode("ascii")))


def test_a_dxf_holds_the_outline_in_millimetres_the_way_freecad_writes_it(rounded):
    data = dxf.dxf_of(rounded, "rounded")
    text = data.decode("ascii")
    comment = text.split("\n", 2)[1]
    assert text.startswith("999\n") and "3160daf1e2b6" in comment and "units mm" in comment and "FreeCAD" in comment
    assert re.search(r"\b20\d\d-\d\d", text) is None                       # no date: the same bytes tomorrow
    assert "AC1014" in text and "\r" not in text                             # release 14, as DxfVersionOut says
    doc = read_dxf(data)
    assert doc.header["$INSUNITS"] == 4 and doc.header["$MEASUREMENT"] == 1
    entities = list(doc.modelspace())
    assert {e.dxf.layer for e in entities} == {"none"}                    # writeDXFShape's layer
    assert [e.dxftype() for e in entities] == ["CIRCLE"] + ["LINE"] * 4 + ["ARC"] * 4 + ["LINE"] * 4    # holes first, the outline last
    circle = entities[0]
    assert (circle.dxf.center.x, circle.dxf.center.y, circle.dxf.radius) == pytest.approx((-15, 0, 3))
    arcs = sorted((round(e.dxf.center.x), round(e.dxf.center.y), round(e.dxf.start_angle), round(e.dxf.end_angle))
                  for e in entities if e.dxftype() == "ARC")
    assert arcs == [(-25, -10, 180, -90), (-25, 10, 90, 180), (25, -10, -90, 0), (25, 10, 0, 90)]       # counter-clockwise, atan2's (-180, 180]
    assert all(round(e.dxf.radius) == 5 for e in entities if e.dxftype() == "ARC")


def test_trimesh_reads_the_same_outline(rounded, tmp_path):
    trimesh = pytest.importorskip("trimesh")
    (tmp_path / "rounded.dxf").write_bytes(dxf.dxf_of(rounded, "rounded"))
    loaded = trimesh.load(str(tmp_path / "rounded.dxf"), file_type="dxf")
    assert len(loaded.entities) == 13
    assert np.allclose(loaded.bounds, [[-30, -15], [30, 15]])
    assert sorted(type(e).__name__ for e in loaded.entities) == sorted(["Arc"] * 4 + ["Line"] * 8 + ["Arc"])      # the circle is an arc of 360 degrees to it
    assert sum(1 for e in loaded.entities if type(e).__name__ == "Line") == 8


@pytest.mark.parametrize("axis,make", [
    ("z", lambda: Box(60, 30, 3) - Pos(10, 5, 0) * Cylinder(2, 5)),
    ("x", lambda: Box(3, 60, 30) - Pos(0, 10, 5) * Rot(Y=90) * Cylinder(2, 5)),
    ("y", lambda: Box(60, 3, 30) - Pos(10, 0, 5) * Rot(X=90) * Cylinder(2, 5)),
])
def test_the_drawing_is_the_part_seen_from_its_positive_side_wherever_it_stands(axis, make):
    # a hole at 10 across and 5 up, whichever axis the plate is thin in: the same drawing, not mirrored
    assert circle_at(make()) == pytest.approx((10, 5))
    across = {"z": (4, 7), "x": (7, 9), "y": (4, 9)}[axis]                          # which of x, y, z are the drawing's x and y
    assert circle_at(Pos(4, 7, 9) * make()) == pytest.approx((10 + across[0], 5 + across[1]))     # and off the origin, on every axis


def circle_at(solid):
    circles = [e for e in read_dxf(dxf.dxf_of(solid, "p")).modelspace() if e.dxftype() == "CIRCLE"]
    assert len(circles) == 1
    return (circles[0].dxf.center.x, circles[0].dxf.center.y)


def test_numbers_are_on_a_nanometre_grid_and_never_a_negative_zero():
    assert dxf.num(-0.0000001) == "0.000000" and dxf.num(-1.5) == "-1.500000" and dxf.num(12) == "12.000000"
    assert dxf.num(0.0000006) == "0.000001" and dxf.num(1234.5678914) == "1234.567891"
    assert str(dxf.snap(-1e-9)) == "0.0" and dxf.snap(2.0000004) == 2.0
    assert dxf.angle(359.9999999) == 0.0 and dxf.angle(-90) == 270.0 and dxf.angle(450.25) == 90.25


def test_a_section_with_no_material_has_no_dxf():
    two = Pos(0, 0, -5) * Box(20, 20, 1) + Pos(0, 0, 5) * Box(20, 20, 1)             # thin in z overall, nothing at its middle
    with pytest.raises(dxf.Unsupported, match="cuts no material"):
        dxf.dxf_of(two, "gap")


def prism(*edges, thickness=3.0):
    """The solid a closed profile of edges makes when extruded."""
    return extrude(Face(Wire(list(edges))), thickness)


def segment(a, b):
    return Edge.make_line(Vector(*a, 0), Vector(*b, 0))


def test_an_ellipse_is_an_ellipse_in_either_direction_and_a_curve_without_an_entity_is_a_polyline():
    # a half ellipse, counter-clockwise and then clockwise (a plane turned over has its axis the other way)
    for plane in (Plane.XY, Plane.XY.rotated((180, 0, 0))):
        arc = Edge.make_ellipse(15, 8, plane, start_angle=-90, end_angle=90)
        a, b = arc.start_point(), arc.end_point()
        solid = prism(arc, segment((b.X, b.Y), (-20, b.Y)), segment((-20, b.Y), (-20, a.Y)), segment((-20, a.Y), (a.X, a.Y)))
        kinds = Counter(e.dxftype() for e in read_dxf(dxf.dxf_of(solid, "d")).modelspace())
        assert kinds == {"ELLIPSE": 1, "LINE": 3}
        assert all(r.state == "PASS" for r in dxf.laser_rows("d", solid).rows)            # and it is the section, both ways
    # a Bezier has no entity of its own: FreeCAD drops it, this cuts it into a polyline within 0.2 micrometre
    from build123d import BuildLine, BuildPart, BuildSketch, Bezier, Polyline, make_face
    with BuildPart() as bez:
        with BuildSketch():
            with BuildLine():
                Bezier((-20, -10), (-5, 10), (10, -15), (20, 0))
                Polyline((20, 0), (20, 15), (-20, 15), (-20, -10))
            make_face()
        extrude(amount=3)
    laser = dxf.laser_rows("bez", bez.part)
    assert Counter(dxf.kind(p) for _, ps in dxf.loops_of(laser.cut) for p in ps) == {"LINE": 3, "POLY": 1}
    assert [r.state for r in laser.rows] == ["PASS", "PASS"]


def test_a_spline_is_a_spline_unless_the_part_trims_it():
    from build123d import BuildLine, BuildPart, BuildSketch, Polyline, Spline, make_face
    with BuildPart() as spl:
        with BuildSketch():
            with BuildLine():
                Spline((-20, -10), (-5, 4), (8, -6), (20, 0), tangents=((1, 0), (1, 0)))
                Polyline((20, 0), (20, 15), (-20, 15), (-20, -10))
            make_face()
        extrude(amount=3)
    whole = dxf.laser_rows("whole", spl.part)
    assert Counter(dxf.kind(p) for _, ps in dxf.loops_of(whole.cut) for p in ps) == {"LINE": 3, "SPLINE": 1}
    trimmed = dxf.laser_rows("trimmed", spl.part - Pos(-20, 0, 0) * Box(20, 60, 10))        # the edge is part of its curve now
    assert Counter(dxf.kind(p) for _, ps in dxf.loops_of(trimmed.cut) for p in ps) == {"LINE": 3, "POLY": 1}
    assert [r.state for r in whole.rows + trimmed.rows] == ["PASS"] * 4


# ─── A 3MF and an STL: one mesh of integers, a zip of our own, and lib3mf to read it ─────────────────────

CUBE_POINTS = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=float) * 10
CUBE_TRIANGLES = np.array([(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
                           (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)])        # outward, counter-clockwise from outside


def cube() -> "threemf.Mesh":
    return threemf.canonical(CUBE_POINTS, CUBE_TRIANGLES)


def test_a_mesh_is_the_same_whatever_order_the_kernel_gave_it_in():
    rng = np.random.default_rng(7)
    order = rng.permutation(len(CUBE_POINTS))
    where = np.argsort(order)                                                   # old index -> new
    shuffled = threemf.canonical(CUBE_POINTS[order], where[CUBE_TRIANGLES][rng.permutation(12)][:, [1, 2, 0]])
    mesh = cube()
    assert np.array_equal(mesh.vertices, shuffled.vertices) and np.array_equal(mesh.triangles, shuffled.triangles)
    assert (mesh.vertices == np.unique(mesh.vertices, axis=0)).all() and mesh.vertices.dtype == np.int64
    assert all(t[0] == min(t) for t in mesh.triangles.tolist()) and mesh.triangles.tolist() == sorted(mesh.triangles.tolist())
    assert mesh.vertices.max() == 10 * threemf.SCALE and mesh.dropped == 0


def test_the_numbers_a_mesh_has_are_exact_and_say_what_is_wrong_with_it():
    good = threemf.report(cube())
    assert (good.volume_mm3, good.open_edges, good.repeated_edges, good.triangles, good.vertices) == (1000.0, 0, 0, 12, 8)
    gone = threemf.report(threemf.canonical(CUBE_POINTS, CUBE_TRIANGLES[1:]))             # a triangle missing: a hole
    assert gone.open_edges == 3 and gone.repeated_edges == 0
    twice = threemf.report(threemf.canonical(CUBE_POINTS, np.vstack([CUBE_TRIANGLES, CUBE_TRIANGLES[:1]])))
    assert twice.repeated_edges == 3
    inside_out = threemf.report(threemf.canonical(CUBE_POINTS, CUBE_TRIANGLES[:, ::-1]))      # closed, but turned inside out
    assert inside_out.volume_mm3 == -1000.0 and inside_out.open_edges == 0
    one_flipped = CUBE_TRIANGLES.copy()
    one_flipped[0] = one_flipped[0][::-1]
    assert threemf.report(threemf.canonical(CUBE_POINTS, one_flipped)).open_edges > 0         # wound the wrong way round
    assert threemf.report(threemf.canonical(CUBE_POINTS, CUBE_TRIANGLES[:0])).triangles == 0


def test_a_coordinate_is_written_from_its_integer_and_never_from_a_float():
    assert [threemf._dec(q) for q in (0, 10_000, 125_000, -3, 1, -10_000, 99_999, 123_456_789)] == [
        "0", "1", "12.5", "-0.0003", "0.0001", "-1", "9.9999", "12345.6789"]


def test_a_3mf_is_a_zip_of_our_own_with_nothing_in_it_that_moves():
    data = threemf.write_3mf(cube(), "cube")
    z = zipfile.ZipFile(io.BytesIO(data))
    assert [i.filename for i in z.infolist()] == ["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"]
    assert {(i.compress_type, i.date_time, i.create_system, i.external_attr >> 16) for i in z.infolist()} == {
        (zipfile.ZIP_STORED, (1980, 1, 1, 0, 0, 0), 3, 0o644)}
    model = z.read("3D/3dmodel.model").decode()
    assert 'unit="millimeter"' in model and '<vertex x="10" y="10" z="10"/>' in model and '<item objectid="1"/>' in model
    assert '<metadata name="Title">cube</metadata>' in model and "Description" not in model
    assert data == threemf.write_3mf(cube(), "cube") != threemf.write_3mf(cube(), "other")
    draft = zipfile.ZipFile(io.BytesIO(threemf.write_3mf(cube(), "cube", "NOT VERIFIED"))).read("3D/3dmodel.model").decode()
    assert '<metadata name="Title">cube NOT VERIFIED</metadata>' in draft and 'name="cube NOT VERIFIED"' in draft
    assert '<metadata name="Description">NOT VERIFIED: not from a verified design</metadata>' in draft


def test_an_stl_is_the_same_mesh_in_the_binary_layout_every_reader_knows():
    data = threemf.write_stl(cube(), "cube")
    assert data[:80] == b"cad-agent: cube".ljust(80, b" ") and struct.unpack("<I", data[80:84])[0] == 12
    assert len(data) == 84 + 12 * 50
    rec = np.frombuffer(data[84:], dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    assert np.allclose(np.linalg.norm(rec["n"], axis=1), 1.0) and rec["a"].max() == 0
    assert sorted(map(tuple, np.unique(rec["n"], axis=0).tolist())) == sorted(
        [(0, 0, -1), (0, 0, 1), (0, -1, 0), (0, 1, 0), (-1, 0, 0), (1, 0, 0)])
    assert threemf.write_stl(cube(), "cube", "NOT VERIFIED")[:80].startswith(b"cad-agent: cube NOT VERIFIED")


def test_a_3mf_reads_back_by_the_built_in_reader_and_by_lib3mf_as_the_mesh_it_was():
    mesh = cube()
    data = threemf.write_3mf(mesh, "cube")
    read = threemf.read_3mf(data, prefer_lib3mf=False)
    assert read.reader == "built-in" and read.manifold is None and (read.objects, read.items) == (1, 1)
    assert np.array_equal(read.mesh.vertices, mesh.vertices) and np.array_equal(read.mesh.triangles, mesh.triangles)
    pytest.importorskip("lib3mf")
    both = threemf.read_3mf(data)
    assert both.reader == "lib3mf" and both.manifold is True and (both.objects, both.items) == (1, 1)
    assert np.array_equal(both.mesh.vertices, mesh.vertices) and np.array_equal(both.mesh.triangles, mesh.triangles)


def test_a_3mf_nobody_can_read_is_unreadable_not_a_crash():
    good = threemf.write_3mf(cube(), "cube")
    model = zipfile.ZipFile(io.BytesIO(good)).read("3D/3dmodel.model").decode()
    package = [("[Content_Types].xml", "x"), ("_rels/.rels", "x")]
    broken = {
        "not a zip": b"this is not a zip file",
        "no package parts": threemf._zip([("hello.txt", "hi")]),
        "not xml": threemf._zip(package + [("3D/3dmodel.model", "<model")]),
        "inches": threemf._zip(package + [("3D/3dmodel.model", model.replace('unit="millimeter"', 'unit="inch"'))]),
        "a triangle off the end": threemf._zip(package + [("3D/3dmodel.model", model.replace('v3="1"', 'v3="99"', 1))]),
        "no triangles": threemf._zip(package + [("3D/3dmodel.model",
                                                 re.sub(r"<triangles>.*</triangles>", "<triangles></triangles>", model, flags=re.S))]),
    }
    for data in broken.values():
        with pytest.raises(threemf.Unreadable):
            threemf.read_3mf(data, prefer_lib3mf=False)
    pytest.importorskip("lib3mf")
    for why in ("not a zip", "a triangle off the end", "no triangles"):
        with pytest.raises(threemf.Unreadable):
            threemf.read_3mf(broken[why])


def test_a_curved_solid_is_meshed_within_half_a_percent_of_its_volume_on_the_worst_shape_there_is():
    ball = Sphere(8)
    mesh = threemf.mesh_of(ball)
    got = threemf.report(mesh)
    assert got.open_edges == got.repeated_edges == 0
    assert abs(got.volume_mm3 - ball.volume) / ball.volume < threemf.VOLUME_LIMIT
    assert threemf.mesh_of(ball).vertices.tolist() == mesh.vertices.tolist()                 # and the mesh repeats


def test_a_part_that_is_not_a_prism_still_exports_its_mid_plane_section_and_a_prism_its_end_face(monkeypatch):
    def comment(solid):
        return dxf.dxf_of(solid, "p").decode().split("\n", 2)[1]
    assert "end face normal to z at z = 2.000000 mm" in comment(Box(40, 20, 4))
    assert "section normal to z at z = 0.000000 mm" in comment(Box(40, 20, 4) - Pos(0, 0, 1) * Box(10, 6, 2))      # a blind pocket
    monkeypatch.setattr(dxf, "faces_report", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no faces")))
    assert "section normal to z at z = 0.000000 mm" in comment(Box(40, 20, 4))                                    # and a part it cannot sort
