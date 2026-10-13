"""mini_machine: the regression fixture of step 6, a parent and a child project that use every piece of it.

tests/fixtures/mini_machine links tests/fixtures/mini_gantry (a sibling folder) by SUBASSEMBLIES, turned a quarter, so
that the child's carriage axis runs along y in the parent. Between them are 11 bodies: a laser-cut steel base, an acrylic
back wall, a polyimide insulator and an aluminium hot plate, two milled posts and a printed tool plate, and four parts
`cad lib use` copied in from the library (a 2020 extrusion, an MGN12 rail and carriage, a NEMA 8 motor) with their masses
and sources. CI runs `cad verify` and `cad done` on every folder of tests/fixtures, so each of the two is a project that
verifies by itself.

What these tests hold: every piece of step 6 is in the fixture and passes in it (and fails when it should: one run with
a failing entry for each), the BOM, the shop files and the drawing come out of it, and the verdict is UNCHECKED only for
the renders nobody has approved. `cad approve` is a person's call and is never run here: the six images wait for it.
"""
import json
import re
import shutil
from pathlib import Path

import pytest

from cad_agent import cli, verify
from cad_agent import state as st
from cad_agent.runner import check_all
from test_cli import run

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PARENT, CHILD = "mini_machine", "mini_gantry"
LIBRARY_PARTS = ("extrusion_2020", "mgn12_rail", "mgn12h", "nema8")
AWAITING = {("visual", "drift/iso"): ["back_wall", "base", "hot_plate", "insulator"],
            (f"{CHILD}:visual", "drift/iso"): ["post", "tool_plate"]}       # the six renders `cad approve` would bless
VERIFY_SECONDS = 120.0               # a guard against a rule gone slow, not a promise: about 21 s on a laptop, kernel warm


def lay(root: Path) -> None:
    """Both projects as sibling folders of `root`, with the files that are design and none of what a run writes, and none
    of the approved renders either: a person approves those (`cad approve`) and commits them under baseline/, and these
    tests judge the same things before and after that, with the six images always waiting."""
    for name in (PARENT, CHILD):
        shutil.copytree(FIXTURES / name, root / name,
                        ignore=shutil.ignore_patterns("out", ".cad", "checks.json", "verify.json", "__pycache__", "baseline"))


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    root = tmp_path_factory.mktemp("projects")
    lay(root)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(st, "ROOT", root)
        mp.delenv("CAD_PROJECTS", raising=False)
        mp.setenv("CAD_LIBRARY", str(root / "store"))          # the library's own parts need no store
        yield root


@pytest.fixture(scope="module")
def verified(tree):
    return verify.run(PARENT, fresh=True, mode="test")


def rows(record, check=None, rule=None, subject=None):
    return [r for r in record["rows"] if (check is None or r["check"] == check) and (rule is None or r["rule"] == rule)
            and (subject is None or r["subject"] == subject)]


def number(text, pattern):
    return float(re.search(pattern, text)[1])


# ─── What is in the folders ──────────────────────────────────────────────────

def test_a_parent_and_a_child_are_sibling_folders_each_with_its_own_spec():
    for name in (PARENT, CHILD):
        assert (FIXTURES / name / "assembly.py").is_file() and (FIXTURES / name / "spec.toml").read_text().strip()
        baseline = FIXTURES / name / "baseline"                    # approving is a person's step, and no test does it; what a
        wanted = AWAITING[("visual", "drift/iso") if name == PARENT else (f"{CHILD}:visual", "drift/iso")]   # person approves
        assert not baseline.exists() or {p.name for p in baseline.glob("*")} <= {f"{part}_iso.png" for part in wanted}
    source = (FIXTURES / PARENT / "assembly.py").read_text()
    assert f'"project": "{CHILD}"' in source and '"turn": [0, 0, 90]' in source         # a literal, so verify can hash it
    assert "AXES = {" in source and "POSES = {" in source and "SUBASSEMBLIES = {" in source
    assert "AXES = {" in (FIXTURES / CHILD / "assembly.py").read_text()


def test_the_library_parts_were_copied_in_with_their_masses_and_sources_and_are_pinned():
    for name in LIBRARY_PARTS:
        side = json.loads((FIXTURES / CHILD / "bought" / f"{name}.json").read_text())
        assert side["library"] and side["vendor"] and side["pn"] and side["licence"] == "MIT", name
        assert side["mass_g"] > 0 and side["mass_source"].strip(), name           # a mass with no source is not used
        assert re.fullmatch(r"[0-9a-f]{64}", side["sha256"]), name                 # and the module may not be edited by hand
        assert (FIXTURES / CHILD / "bought" / f"{name}.py").read_text().count("cad_agent.library.gen") == 1


# ─── Verify, as CI runs it ───────────────────────────────────────────────────

def test_the_parent_verifies_with_only_the_unapproved_renders_open(verified):
    assert verified["verdict"] == "UNCHECKED" and verified["summary"]["by_state"].get("FAIL", 0) == 0
    assert verified["summary"]["parts_failed"] == 0 and not verified["notes"] and verified["process"]["fresh"]
    open_ = {}
    for r in verified["rows"]:
        if r["state"] in ("FAIL", "UNCHECKED"):
            assert (r["state"], r["measured"]) == ("UNCHECKED", "no approved image"), r
            open_.setdefault((r["check"], r["rule"]), []).append(r["subject"])
    assert {k: sorted(v) for k, v in open_.items()} == AWAITING
    assert verified["summary"]["rows"] >= 200 and verified["tree"]["projects"].keys() == {CHILD}
    assert verified["seconds"] < VERIFY_SECONDS


def test_the_child_verifies_on_its_own_the_same_way(tree):
    record = verify.run(CHILD, fresh=True, mode="test")
    assert record["verdict"] == "UNCHECKED" and "tree" not in record               # no sub-assemblies of its own
    assert [(r["rule"], r["subject"]) for r in record["rows"] if r["state"] != "PASS" and r["state"] != "N/A"] == [
        ("drift/iso", "post"), ("drift/iso", "tool_plate")]
    assert record["seconds"] < VERIFY_SECONDS


def test_every_piece_of_step_6_is_judged_in_the_fixture_and_passes(verified):
    """One line per piece: the rows it contributes, by (check, rule), and how many there must be."""
    expect = {
        # P0 and B: a sub-assembly, its axes and poses, the spec kinds that ask for them
        ("subassembly", "linked"): 1, ("poses", "pose"): 3, ("sweep", "sweep/slide"): 1, ("sweep", "sweep/gantry/x"): 1,
        ("reach", "reach"): 2, ("spec", "spec/axis"): 2, ("spec", "spec/bodies"): 1,
        # C1: heat, mass (bodies, and what an axis moves) and the centre of mass, N/A until a bought part declares a mass
        ("spec", "spec/heat"): 4, ("spec", "spec/mass"): 3, ("com", "centre of mass"): 1,
        ("com", "centre of mass/slide"): 1, ("com", "centre of mass/gantry/x"): 1,
        # C2: a beam's deflection, in the parent under the lifted names and in the child under its own
        ("spec", "spec/deflection"): 1, (f"{CHILD}:spec", "spec/deflection"): 1,
        # A: the library's parts, each hashed
        (f"{CHILD}:provenance", "sha256"): 4, (f"{CHILD}:provenance", "source"): 4,
        # D: the BOM and shop rules (one summary row, a row for each key, the files), laser and printed parts' rows
        ("spec", "spec/shop"): 14, ("spec", "spec/shop file"): 4, ("shop", "laser through-cut"): 2,
        ("shop", "dxf readback"): 2, (f"{CHILD}:shop", "3mf watertight"): 1, (f"{CHILD}:shop", "3mf volume"): 1,
        # the older kinds, on a body of a sub-assembly and across the quarter turn
        ("spec", "spec/interface"): 4, ("spec", "spec/clearance"): 2, ("spec", "spec/position"): 2,
    }
    for (check, rule), n in expect.items():
        got = rows(verified, check, rule)
        assert len(got) >= n and {r["state"] for r in got} == {"PASS"}, (check, rule, [(r["subject"], r["state"]) for r in got])


def test_heat_judges_the_insulator_and_the_base_and_keeps_the_motor_and_the_printed_plate_out(verified):
    got = {r["subject"]: r for r in rows(verified, "spec", "spec/heat")}
    assert sorted(got) == ["base", "gantry/motor", "gantry/tool_plate", "insulator"]           # the source is exempt
    assert got["insulator"]["measured"] == "polyimide (Tg) rated 360 C, 0.00 mm from hot_plate"
    assert got["base"]["measured"] == "steel (stated service limit) rated 400 C, 6.00 mm from hot_plate"
    assert got["insulator"]["limit"] == ">= 200 C (180 + 20 margin), a zone, not a thermal model"
    for kept_out in ("gantry/motor", "gantry/tool_plate"):             # rated 50 C and 68 C: only their distance is judged
        assert got[kept_out]["measured"].endswith("outside the 15 mm zone")


def test_the_machine_is_judged_in_two_poses_and_the_poses_are_the_machines_own(verified):
    clearance = {r["subject"]: r for r in rows(verified, "spec", "spec/clearance")}
    assert clearance["gantry/beam|back_wall"]["measured"] == "18.000 mm at pose park"
    assert clearance["gantry/tool_plate|hot_plate"]["measured"] == "67.000 mm at pose work"
    (motor,) = [r for r in rows(verified, "spec", "spec/position") if r["subject"] == "gantry/motor"]
    assert motor["measured"] == "center (60.00, -36.75, 97.00) mm, offset 0.000 mm at pose park"     # slide + carriage back
    names = {r["subject"] for r in rows(verified, "poses", "pose")}
    assert names == {"pose gantry/park", "pose park", "pose work"}      # the child's own park comes up as gantry/park
    axes = {r["subject"]: r["measured"] for r in rows(verified, "spec", "spec/axis")}
    assert "along (0.000, 1.000, 0.000)" in axes["axis gantry/x"]          # the child's x, turned a quarter, runs along y
    assert "along (1.000, 0.000, 0.000)" in axes["axis slide"]


def test_the_beams_deflection_is_the_same_number_judged_from_either_project(verified):
    (parent,) = rows(verified, "spec", "spec/deflection")
    (child,) = rows(verified, f"{CHILD}:spec", "spec/deflection")
    um = lambda row: number(row["measured"], r"^([\d.]+) um at midspan")
    assert um(parent) == pytest.approx(um(child), abs=1e-9) and 0.5 < um(parent) < 1.5          # of the 2 um it may sag
    assert "140 g moved by axis gantry/x" in parent["measured"] and "140 g moved by axis x" in child["measured"]
    assert "span/depth 11.0" in parent["measured"]                                             # 220 mm over a 20 mm section


def test_the_centre_of_mass_is_judged_because_the_library_parts_declare_masses(verified):
    (home,) = rows(verified, "com", "centre of mass")
    assert home["state"] == "PASS" and "inside the footprint of base" in home["measured"]
    assert number(home["measured"], r"([\d.]+) g in all") == pytest.approx(2179.76, abs=0.1)       # all 11 bodies' masses
    child = rows(verified, f"{CHILD}:com", "centre of mass")[0]
    assert "inside the footprint of post_left, post_right" in child["measured"]


# ─── One failing entry for each piece: the rows are live, not just green ─────

BREAKS = '''

# ---- appended by the test: each of these must fail ----
[[heat]]
source = "hot_plate"
temp_c = 380                # polyimide is rated 360 C
radius_mm = 15

[[deflection]]
body = "gantry/beam"
support = "simple"
span_mm = 220
load_moving = "gantry/x"
self_weight = true
max_um = 0.5                # it sags 0.9

[[mass]]
moving = "slide"
max_g = 400                 # the gantry weighs 563 g

[[clearance]]
a = "gantry/beam"
b = "back_wall"
min_mm = 30                 # 18 mm, with the slide at the wall
pose = "park"

[[axis]]
name = "gantry/x"
direction = [1, 0, 0]       # the quarter turn made it run along y
'''


def test_a_failing_entry_for_each_piece_fails_on_its_own_row_and_nothing_else_moves(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("broken")
    lay(root)
    spec = root / PARENT / "spec.toml"
    text = spec.read_text()
    assert "base = 1\n" in text
    assert '"drawings/base.pdf",' in text                                                    # the drawings of the two laser plates
    spec.write_text((text.replace("base = 1\n", "base = 2\n")                              # and one BOM quantity that is wrong,
                     .replace('"drawings/base.pdf",', '"drawings/base.pdf", "drawings/nowhere.pdf",') + BREAKS))   # and a drawing that is not
    monkeypatch.setattr(st, "ROOT", root)
    monkeypatch.setenv("CAD_LIBRARY", str(root / "store"))
    payload = check_all(PARENT, render_views=("iso",))
    failing = [(r["rule"], r["subject"]) for r in payload["rows"] if r["state"] == "FAIL"]
    assert sorted(failing) == sorted([
        ("spec/heat", "insulator"), ("spec/deflection", "gantry/beam"), ("spec/mass", "axis slide"),
        ("spec/clearance", "gantry/beam|back_wall"), ("spec/axis", "axis gantry/x"), ("spec/shop", "base"),
        ("spec/shop", "drawings/nowhere.pdf")])
    got = {(r["rule"], r["subject"]): r["measured"] for r in payload["rows"] if r["state"] == "FAIL"}
    assert got[("spec/heat", "insulator")] == "polyimide (Tg) rated 360 C, 0.00 mm from hot_plate"
    assert number(got[("spec/deflection", "gantry/beam")], r"^([\d.]+) um") == pytest.approx(0.905, abs=0.01)
    assert got[("spec/clearance", "gantry/beam|back_wall")] == "18.000 mm at pose park, too close"
    assert "runs 90.0 deg off the line asked for" in got[("spec/axis", "axis gantry/x")]
    assert got[("spec/shop", "base")].startswith("1 in the BOM")
    assert got[("spec/shop", "drawings/nowhere.pdf")] == "cad shop does not draw it: no part 'nowhere' in the BOM"


# ─── cad bom, cad shop and cad drawing on it ─────────────────────────────────

def test_the_bom_nests_the_gantry_and_says_where_each_library_part_came_from(tree, capsys):
    code, data = run(capsys, "bom", PARENT)
    assert code == cli.OK and data["totals"]["lines"] == 11 and data["totals"]["mass_complete"] is True
    lines = {ln["index"]: ln for ln in data["lines"]}
    assert [lines[i]["name"] for i in ("1", "2", "3", "4")] == ["base", "insulator", "hot_plate", "back_wall"]
    assert lines["5"]["kind"] == "assembly" and lines["5"]["name"] == "gantry" and lines["5"]["quantity"] == 1
    nested = {ln["name"]: ln for i, ln in lines.items() if i.startswith("5.")}
    assert sorted(nested) == ["extrusion_2020", "mgn12_rail", "mgn12h", "nema8", "post", "tool_plate"]
    assert nested["post"]["quantity"] == 2 and nested["post"]["bodies"] == ["gantry/post_left", "gantry/post_right"]
    for name in LIBRARY_PARTS:                                         # vendor, part number, a mass and its source, each
        ln = nested[name]
        assert ln["kind"] == "bought" and ln["vendor"] and ln["pn"] and ln["mass_g"] > 0 and ln["mass_source"], name
    assert nested["mgn12h"]["vendor"] == "HIWIN" and nested["nema8"]["pn"] == "ST2018M0804-A"
    assert lines["1"]["shop_files"] == ["base.step", "base.dxf"] and lines["1"]["process"] == "laser_cut"
    assert data["totals"]["mass_known_g"] == pytest.approx(2179.76, abs=0.01)


def test_a_draft_of_the_shop_files_is_stamped_and_exits_2_until_the_design_is_done(tree, capsys):
    code, data = run(capsys, "shop", PARENT)                            # not done: nothing is written
    assert code == cli.UNCHECKED and not (tree / PARENT / "out" / "shop").exists()
    code, data = run(capsys, "shop", PARENT, "--draft")
    assert code == cli.UNCHECKED and data["draft"] is True and data["done"] is False
    folder = tree / PARENT / "out" / "shop"
    made = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert {"back_wall.dxf", "base.dxf", "base.step", "back_wall.step", "insulator.step", "hot_plate.step", "bom.csv",
            "bom.json", "manifest.json"} <= set(made)
    assert [f for f in made if f.startswith("drawings/") and f.endswith(".pdf")] == [
        f"drawings/{p}.pdf" for p in ("back_wall", "base", "hot_plate", "insulator")]     # a drawing for each plate
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["draft"] is True and manifest["verdict"] == "NOT VERIFIED" and manifest["drawings"]["built"] is True
    assert {"drawings/base.pdf", "drawings/base.dxf", "drawings/back_wall.svg"} <= set(manifest["drawings"]["files"])   # [shop] files
    assert "NOT VERIFIED" in (folder / "base.dxf").read_text() and "NOT VERIFIED" in (folder / "bom.csv").read_text()
    assert not any(p.startswith(("post", "tool_plate", "gantry")) for p in made)              # the child's files are its own
    assert not [r for r in data["rows"] if r["state"] == "FAIL"]                              # and no row refused a file


def test_a_drawing_of_the_laser_base_is_stamped_and_every_gate_passes(tree, capsys):
    code, data = run(capsys, "drawing", PARENT, "base", "--all")
    assert code == cli.UNCHECKED and data["stamp"] == "NOT VERIFIED" and data["process"] == "laser_cut"
    assert data["plate"] == "200 x 300 x 3 mm, thin in z, corners R5, 4 holes, 2 slots"
    assert {r["state"] for r in data["rows"]} == {"PASS"} and len(data["wrote"]) == 3
    assert (data["sheet"]["size"], data["sheet"]["scale"]) == ("A2", "1:1")
    code, data = run(capsys, "drawing", PARENT, "gantry/post")                                 # a child's is the child's
    assert code == cli.USAGE and f"cad drawing {CHILD} post" in data["error"]
    code, data = run(capsys, "drawing", CHILD, "tool_plate")                                   # and a printed one is no plate
    assert code == cli.USAGE and "made by 'fdm'" in data["error"]


def test_done_says_the_six_renders_are_all_that_is_left(verified, capsys):
    code, data = run(capsys, "done", PARENT)
    assert code == cli.UNCHECKED and data["done"] is False and data["verdict"] == "UNCHECKED"
    assert sorted(r["subject"] for r in data["failing"]) == ["back_wall", "base", "hot_plate", "insulator", "post", "tool_plate"]
    assert {(r["rule"], r["measured"]) for r in data["failing"]} == {("drift/iso", "no approved image")}
