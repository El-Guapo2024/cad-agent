"""A part's STEP is the same bytes whenever and wherever it is written.

A STEP is a design file (a bought part is one, and `cad verify` hashes bought/*), but OCCT puts the
process into it: the wall clock in the header, and a count of assembly occurrences that only a fresh
process starts at 1. The kernel tests below export a part that carries that count, a body returned as
`Pos(...) * body`, because a plain solid has nothing in it that moves.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest
from build123d import Box, Cylinder, Pos, import_step

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
