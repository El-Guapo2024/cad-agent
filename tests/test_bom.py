"""The bill of materials: one line for each distinct thing, how many, and what a shop needs to know of it.

`workshop` is the project these tests (and test_shop.py's) read: a laser-cut panel, two printed clips (one the
mirror image of the other), a machined block and a motor that is bought. Its BOM is four lines. Every case that
changes it writes the change into a scratch copy of the project, the way a design is edited.
"""
import csv
import io
import json
import textwrap
from pathlib import Path

import pytest
from build123d import Box, Pos

from cad_agent import bom as bomlib
from cad_agent import cli
from cad_agent import export as ex
from cad_agent import state as st
from cad_agent.bodies import BodyInfo
from cad_agent.geom import mass_g

SLUG = "works"

PANEL = textwrap.dedent('''\
    """Front panel: 3 mm acrylic, laser cut, with two bolt holes."""
    from build123d import Axis, Box, Cylinder, Pos, fillet

    MATERIAL = "acrylic"
    PROCESS = "laser_cut"
    MIN_FEATURE_MM = 3.0
    EXPECT_FEATURES = 2
    PARAMS = {"width": 60.0, "depth": 30.0, "thickness": 3.0, "hole": 4.0}


    def build(width, depth, thickness, hole):
        panel = fillet(Box(width, depth, thickness).edges().filter_by(Axis.Z), 3.0)
        for x in (-15, 15):
            panel -= Pos(x, 0, 0) * Cylinder(hole / 2.0, thickness + 2)
        return panel
''')

CLIP = textwrap.dedent('''\
    """Clip: a printed tab with an M3 clearance hole."""
    from build123d import Box, Cylinder

    MATERIAL = "petg"
    PROCESS = "fdm"
    MIN_FEATURE_MM = 1.2
    EXPECT_FEATURES = 1
    PARAMS = {"length": 20.0, "width": 12.0, "thickness": 5.0}


    def build(length, width, thickness):
        return Box(length, width, thickness) - Cylinder(1.7, thickness + 2)
''')

BLOCK = textwrap.dedent('''\
    """Block: machined from 24 mm bar, with one through bore."""
    from build123d import Box, Cylinder

    MATERIAL = "aluminium"
    PROCESS = "cnc"
    MIN_FEATURE_MM = 2.0
    PARAMS = {"size": 24.0, "height": 12.0}


    def build(size, height):
        return Box(size, size, height) - Cylinder(2.5, height + 2)
''')

ASSEMBLY = textwrap.dedent('''\
    from build123d import Plane, Pos, mirror
    from cad_agent.state import build_part, bought_solid

    SLUG = "works"
    ALLOW_CONTACT = set()


    def parts():
        panel, _ = build_part(SLUG, "panel")
        clip, _ = build_part(SLUG, "clip")
        block, _ = build_part(SLUG, "block")
        left = Pos(-20, 0, 6) * clip
        return {
            "panel": panel,
            "clip_left": left,
            "clip_right": mirror(left, Plane.YZ),
            "block": Pos(0, 0, 18) * block,
            "motor": Pos(0, 0, 40) * bought_solid(SLUG, "motor"),
        }
''')

MOTOR = {"source": "the test rig, drawn here", "vendor": "Acme Motors", "pn": "AM-200", "verified": True}
SPEC = "[envelope]\nmax_mm = [100, 100, 100]\n"


def make_workshop(root: Path, assembly: str = ASSEMBLY, motor: dict | None = None, spec: str = SPEC) -> Path:
    """The workshop project under `root`, the files only: nothing is built, checked or verified."""
    d = root / SLUG
    for sub in ("parts", "bought", "out"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    for name, text in (("panel", PANEL), ("clip", CLIP), ("block", BLOCK)):
        (d / "parts" / f"{name}.py").write_text(text)
    ex.write_step(Pos(0, 0, 0) * Box(30, 20, 20), d / "bought" / "motor.step")
    (d / "bought" / "motor.json").write_text(json.dumps(motor if motor is not None else MOTOR))
    (d / "assembly.py").write_text(assembly)
    (d / "spec.toml").write_text(spec)
    return d


@pytest.fixture()
def workshop(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    return make_workshop(tmp_path)


def edit(d: Path, assembly: str) -> None:
    (d / "assembly.py").write_text(assembly)


def bill(slug: str = SLUG, **kw) -> bomlib.Bom:
    with st.reusing_builds():
        return bomlib.build(slug, **kw)


def by_name(b: bomlib.Bom) -> dict:
    return {ln.name: ln for ln in b.lines}


# ─── The lines ───────────────────────────────────────────────────────────────

def test_the_workshop_is_four_lines_in_the_order_assembly_py_places_them(workshop):
    b = bill()
    assert b.assembly is True
    assert [(ln.index, ln.name, ln.quantity, ln.kind) for ln in b.lines] == [
        ("1", "panel", 1, "made"), ("2", "clip", 2, "made"), ("3", "block", 1, "made"), ("4", "motor", 1, "bought")]
    clip = by_name(b)["clip"]
    assert clip.bodies == ["clip_left", "clip_right"]              # the mirror image is a clip too
    assert (clip.material, clip.process, clip.file_name) == ("petg", "fdm", "parts/clip.py")
    assert clip.description == "Clip: a printed tab with an M3 clearance hole."
    assert clip.shop_files == ["clip.step", "clip.3mf", "clip.stl"] and clip.shop_file() == "clip.3mf"
    assert by_name(b)["panel"].shop_files == ["panel.step", "panel.dxf"] and by_name(b)["panel"].shop_file() == "panel.dxf"
    assert by_name(b)["block"].shop_files == ["block.step"] and by_name(b)["block"].shop_file() == "block.step"


def test_a_bought_line_says_what_the_part_declares_and_nothing_it_does_not(workshop):
    motor = by_name(bill())["motor"]
    assert (motor.vendor, motor.pn, motor.licence, motor.material) == ("Acme Motors", "AM-200", None, None)
    assert motor.file_name == "bought/motor.step" and motor.source == "the test rig, drawn here"
    assert motor.shop_files == [] and motor.shop_file() == ""         # nobody makes it here
    assert motor.mass_g is None and motor.mass_source.startswith("unknown: bought part 'motor' declares no mass_g")
    side = json.loads((workshop / "bought" / "motor.json").read_text())
    (workshop / "bought" / "motor.json").write_text(json.dumps({
        **side, "mass_g": 150.0, "mass_source": "the datasheet", "licence": "CC-BY-3.0", "material": "steel"}))
    motor = by_name(bill())["motor"]
    assert (motor.mass_g, motor.mass_source, motor.licence, motor.material) == (150.0, "the datasheet", "CC-BY-3.0", "steel")


def test_a_mass_nobody_declared_says_unknown_and_never_a_number(workshop):
    b = bill()
    lines = by_name(b)
    panel, _ = st.build_part(SLUG, "panel")
    assert lines["panel"].mass_g == pytest.approx(mass_g(panel, "acrylic"), abs=0.01)
    assert "volume x density of acrylic" in lines["panel"].mass_source
    assert lines["motor"].mass_g is None
    totals = b.totals()
    assert totals["bodies"] == 5 and totals["bodies_without_mass"] == 1 and totals["mass_complete"] is False
    assert totals["mass_known_g"] == pytest.approx(sum(ln.mass_g * ln.quantity for ln in b.lines if ln.mass_g is not None), abs=0.01)
    text = bomlib.table_text(b)
    assert "unknown" in text and "1 of 5 bodies have no known mass, so this is not the weight of the machine" in text
    (workshop / "parts" / "block.py").write_text(BLOCK.replace('"aluminium"', '"unobtainium"'))
    block = by_name(bill())["block"]
    assert block.mass_g is None and "unobtainium" in block.mass_source and "no density" in block.mass_source


def test_a_stock_body_with_the_shape_and_name_of_a_line_is_counted_with_it_and_says_so(workshop):
    edit(workshop, ASSEMBLY.replace('"motor": Pos(0, 0, 40) * bought_solid(SLUG, "motor"),',
                                    '"motor_left": Pos(-20, 0, 40) * bought_solid(SLUG, "motor"),\n'
                                    '            "motor_right": mirror(Pos(20, 0, 40) * bought_solid(SLUG, "motor"), Plane.YZ),\n'
                                    '            "rail_front": Pos(0, -20, 40) * Box(50, 4, 4),\n'
                                    '            "rail_back": Pos(0, 20, 40) * Box(50, 4, 4),\n'
                                    '            "rod": Pos(0, 0, 60) * Box(50, 4, 6),').replace(
        "from build123d import Plane, Pos, mirror", "from build123d import Box, Plane, Pos, mirror"))
    lines = by_name(bill())
    motor = lines["motor"]
    assert motor.quantity == 2 and motor.bodies == ["motor_left", "motor_right"]
    assert "motor_right is stock in assembly.py (mirror() drops what a body is)" in " ".join(motor.notes)
    assert lines["rail"].kind == "stock" and lines["rail"].quantity == 2 and lines["rail"].bodies == ["rail_front", "rail_back"]
    assert lines["rod"].kind == "stock" and lines["rod"].quantity == 1            # another shape: its own line
    assert lines["rail"].shop_files == [] and lines["rail"].mass_source.startswith("unknown: assembly.py builds it itself")


def test_a_part_assembly_py_cuts_is_a_line_of_its_own_and_its_shop_file_is_not_that_body(workshop):
    edit(workshop, ASSEMBLY.replace('"block": Pos(0, 0, 18) * block,', '"block": Pos(0, 0, 18) * (block - Pos(8, 0, 0) * Cylinder(3, 20)),')
         .replace("from build123d import Plane, Pos, mirror", "from build123d import Cylinder, Plane, Pos, mirror"))
    b = bill()
    rows = bomlib.module_rows(SLUG, b, b.solids)
    states = {r.subject: r.state for r in rows}
    assert states == {"panel": "PASS", "clip_left": "PASS", "clip_right": "PASS", "block": "FAIL"}
    block = next(r for r in rows if r.subject == "block")
    assert "parts/block.py builds" in block.measured and "the shop file would not be this body" in block.measured
    edit(workshop, ASSEMBLY)
    b = bill()
    assert {r.state for r in bomlib.module_rows(SLUG, b, b.solids)} == {"PASS"}
    (workshop / "parts" / "block.py").write_text("raise RuntimeError('broken')\n")      # a module that cannot be built is not measured
    unchecked = [r for r in bomlib.module_rows(SLUG, b, b.solids) if r.subject == "block"]
    assert [r.state for r in unchecked] == ["UNCHECKED"] and "could not be measured" in unchecked[0].measured


def test_one_part_built_with_other_parameters_is_two_lines(workshop):
    edit(workshop, ASSEMBLY.replace('"clip_right": mirror(left, Plane.YZ),',
                                    '"clip_right": Pos(20, 0, 6) * build_part(SLUG, "clip", {"length": 24.0})[0],'))
    b = bill()
    clips = [ln for ln in b.lines if ln.name == "clip"]
    assert [(ln.quantity, ln.bodies) for ln in clips] == [(1, ["clip_left"]), (1, ["clip_right"])]


def test_only_parts_leaves_out_what_is_bought_or_stock(workshop):
    b = bill(only_parts=True)
    assert [ln.name for ln in b.lines] == ["panel", "clip", "block"] and b.only_parts is True


def test_a_project_with_no_assembly_py_lists_each_part_and_bought_part_once(workshop):
    (workshop / "assembly.py").unlink()
    b = bill()
    assert b.assembly is False
    assert [(ln.name, ln.kind, ln.quantity) for ln in b.lines] == [
        ("block", "made", 1), ("clip", "made", 1), ("panel", "made", 1), ("motor", "bought", 1)]
    assert "no assembly.py: one of each part and bought part" in bomlib.table_text(b)
    assert [ln.name for ln in bill(only_parts=True).lines] == ["block", "clip", "panel"]


def test_a_sub_assembly_is_a_line_and_its_parts_follow_it_by_the_names_of_the_bodies():
    def info(name, project, part, kind="made", mass=None):
        return BodyInfo(name=name, kind=kind, project=project, part=part, mass_g=mass, mass_source="declared" if mass else None,
                        geometry="exact", source=f"parts/{part}.py")
    parts = {"frame": Box(10, 10, 10), "z/plate": Box(20, 20, 2), "z/rail_a": Box(5, 5, 30), "z/rail_b": Pos(8, 0, 0) * Box(5, 5, 30),
             "nut": Box(3, 3, 3)}
    infos = {"frame": info("frame", "top", "frame", mass=100.0), "z/plate": info("z/plate", "z", "plate", mass=20.0),
             "z/rail_a": info("z/rail_a", "z", "rail", mass=5.0), "z/rail_b": info("z/rail_b", "z", "rail", mass=5.0),
             "nut": info("nut", "top", "nut", mass=1.0)}
    b = bomlib.from_parts("top", parts, infos)
    assert [(ln.index, ln.name, ln.kind, ln.quantity, ln.depth) for ln in b.lines] == [
        ("1", "frame", "made", 1, 0), ("2", "z", "assembly", 1, 0), ("2.1", "plate", "made", 1, 1),
        ("2.2", "rail", "made", 2, 1), ("3", "nut", "made", 1, 0)]
    z = b.lines[1]
    assert z.project == "z" and z.bodies == ["z/plate", "z/rail_a", "z/rail_b"] and z.mass_g == 30.0
    assert z.mass_source == "sum of the masses of its bodies" and z.file_name == "z/assembly.py"
    assert b.totals()["bodies"] == 5 and b.totals()["mass_known_g"] == 131.0 and b.totals()["mass_complete"] is True
    flat = bomlib.from_parts("top", parts, infos, detail=False)
    assert [(ln.index, ln.name) for ln in flat.lines] == [("1", "frame"), ("2", "z"), ("3", "nut")]
    assert flat.totals()["bodies"] == 5 and flat.totals()["mass_known_g"] == 131.0          # and its bodies still weigh
    infos["z/plate"] = info("z/plate", "z", "plate")                                          # one of them has no mass
    unknown = bomlib.from_parts("top", parts, infos)
    assert unknown.lines[1].mass_g is None and unknown.lines[1].mass_source.startswith("unknown: 1 of its 3 bodies have no mass")
    assert unknown.totals()["bodies_without_mass"] == 1 and bomlib.from_parts("top", parts, infos, only_parts=True).lines[1].kind == "assembly"


# ─── The files ───────────────────────────────────────────────────────────────

def test_the_csv_starts_with_the_five_columns_freecad_starts_with(workshop):
    text = bomlib.csv_text(bill())
    rows = list(csv.reader(io.StringIO(text)))
    assert tuple(rows[0]) == bomlib.COLUMNS and rows[0][:5] == ["Index", "Name", "Description", "File Name", "Quantity"]
    assert len(rows) == 5 and all(len(r) == len(bomlib.COLUMNS) for r in rows)
    clip = dict(zip(rows[0], rows[2]))
    assert (clip["Name"], clip["Quantity"], clip["Kind"], clip["Material"], clip["Process"], clip["Shop file"]) == (
        "clip", "2", "made", "petg", "fdm", "clip.3mf")
    assert clip["Bodies"] == "clip_left, clip_right" and clip["Mass (g)"] == f"{by_name(bill())['clip'].mass_g:.2f}"
    motor = dict(zip(rows[0], rows[4]))
    assert (motor["Vendor"], motor["PN"], motor["Mass (g)"], motor["Shop file"]) == ("Acme Motors", "AM-200", "unknown", "")
    assert motor["Mass source"].startswith("unknown: bought part 'motor'")
    assert "\r" not in text and text.endswith("\n")


def test_the_json_has_the_lines_the_totals_and_where_it_was_ported_from(workshop):
    data = json.loads(bomlib.json_text(bill()))
    assert data["project"] == SLUG and data["assembly"] is True and data["columns"] == list(bomlib.COLUMNS)
    assert data["options"] == {"only_parts": False, "detail_subassemblies": True}
    assert data["totals"] == {"lines": 4, "bodies": 5, "mass_known_g": data["totals"]["mass_known_g"], "bodies_without_mass": 1,
                              "mass_complete": False}
    clip = data["lines"][1]
    assert clip["mass_total_g"] == pytest.approx(clip["mass_g"] * 2, abs=0.01) and clip["shop_files"] == ["clip.step", "clip.3mf", "clip.stl"]
    assert data["lines"][3]["mass_g"] is None and data["lines"][3]["mass_total_g"] is None
    assert "3160daf1e2b6" in data["source"] and "CommandCreateBom" in data["source"]


def test_a_draft_stamps_every_row_and_the_json(workshop):
    csv_rows = list(csv.reader(io.StringIO(bomlib.csv_text(bill(), "NOT VERIFIED"))))
    assert csv_rows[0][-1] == "Status" and {r[-1] for r in csv_rows[1:]} == {"NOT VERIFIED"}
    data = json.loads(bomlib.json_text(bill(), "NOT VERIFIED"))
    assert data["verified"] is False and data["stamp"] == "NOT VERIFIED"
    assert "verified" not in json.loads(bomlib.json_text(bill()))


def test_the_same_design_is_the_same_bytes(workshop):
    assert bomlib.csv_text(bill()) == bomlib.csv_text(bill()) and bomlib.json_text(bill()) == bomlib.json_text(bill())


# ─── The command ─────────────────────────────────────────────────────────────

def run(capsys, *argv):
    code = cli.main(["--json", *argv])
    out = capsys.readouterr().out.strip().splitlines()
    return code, json.loads(out[-1])["data"]


def test_cad_bom_writes_out_bom_csv_and_json_and_exits_0(workshop, capsys):
    code, data = run(capsys, "bom", SLUG)
    assert code == cli.OK
    assert [Path(f).name for f in data["files"]] == ["bom.csv", "bom.json"]
    assert (workshop / "out" / "bom.csv").read_text() == bomlib.csv_text(bill())
    assert json.loads((workshop / "out" / "bom.json").read_text())["totals"] == data["totals"]
    assert [ln["name"] for ln in data["lines"]] == ["panel", "clip", "block", "motor"] and data["totals"]["bodies"] == 5


def test_cad_bom_options_and_errors(workshop, capsys):
    code, data = run(capsys, "bom", SLUG, "--only-parts", "--flat", "--no-cache")
    assert code == cli.OK and [ln["name"] for ln in data["lines"]] == ["panel", "clip", "block"]
    assert data["options"] == {"only_parts": True, "detail_subassemblies": False}
    code, data = run(capsys, "bom", "nope")
    assert code == cli.USAGE and "no project 'nope'" in data["error"]
    (workshop / "assembly.py").write_text("raise RuntimeError('the assembly is broken')\n")
    code, data = run(capsys, "bom", SLUG)
    assert code == cli.FAIL and "did not build" in data["error"] and "the assembly is broken" in data["error"]
    code = cli.main(["bom", SLUG, "--nonsense"])
    assert code == cli.USAGE
