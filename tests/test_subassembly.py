"""Sub-assemblies, poses and the "/" in a body's name (cad_agent/subassembly.py, step 6 piece B).

A machine is a project that links other projects. These tests build small sibling projects in a temp folder, never
a real one: a plate and a block (test_cli.py's) and a few boxes, so what is measured is the linking. Most call
load_machine or a rule directly; the few that run whole gates (`check_all`, `verify.run`) say why.
"""
import json
import math
import subprocess
import textwrap

import numpy as np
import pytest
from build123d import Box, Pos, Rot

from cad_agent import cli, placements, subassembly, verify
from cad_agent import state as st
from cad_agent.geom import bbox
from cad_agent.registry import SpecCtx
from cad_agent.runner import approve_views, check_all
from cad_agent.spec import check_spec
from cad_agent.subassembly import PoseError, SubassemblyError, apply_pose
from test_buildcache import BLOCK            # the block that returns a Part, which the build cache keeps
from test_cli import PLATE, run

# The child. Its plate spans x -20..20, y -10..10, z -2..2 and its block 10 mm up, so the 1 mm of air between
# them is a required clearance, and the block rides the x axis 10 mm either way.
GANTRY = '''from build123d import Pos
from cad_agent.state import build_part

SLUG = "gantry"
CLEARANCE = {"plate|block": 1.0}
ALLOW_CONTACT = {("plate", "rail")}
AXES = {"x": {"moves": ("block",), "direction": (1, 0, 0), "travel": (-10.0, 10.0), "work": (-10.0, 10.0),
              "tool": "block", "tool_point": (3.0, 0.0, 5.0)}}
POSES = {"park": {"x": -10}}


def parts():
    plate, _ = build_part(SLUG, "plate")
    block, _ = build_part(SLUG, "block")
    return {"plate": plate, "block": Pos(0, 0, 8) * block}
'''

# The parent: one plate far below, and the gantry turned a quarter about z, 20 mm up.
MACHINE = '''from build123d import Pos
from cad_agent.state import build_part

SLUG = "machine"
SUBASSEMBLIES = @SUBS@
@EXTRA@

def parts():
    base, _ = build_part(SLUG, "plate")
    return {"plate": Pos(0, 0, -50) * base}
'''
GANTRY_AT_20 = '{"gantry": {"project": "gantry", "at": [0, 0, 20], "turn": [0, 0, 90]}}'

# A project of one box, for what needs no part: an assembly that links, or is linked, and little else.
STOCK = '''from build123d import Box

@EXTRA@

def parts():
    return {@BODIES@}
'''


def write(slug, assembly, parts=None, spec=None, **files):
    d = st.project_dir(slug, create=True)
    for name, src in (parts or {}).items():
        (d / "parts" / f"{name}.py").write_text(src)
    (d / "assembly.py").write_text(assembly)
    if spec:
        (d / "spec.toml").write_text(spec)
    for name, text in files.items():
        (d / name.replace("__", ".")).write_text(text)
    return d


def machine(subs=GANTRY_AT_20, extra=""):
    return MACHINE.replace("@SUBS@", subs).replace("@EXTRA@", extra)


def stock(slug, extra="", bodies='"base": Box(10, 10, 10)'):
    return write(slug, STOCK.replace("@EXTRA@", extra).replace("@BODIES@", bodies))


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """machine -> gantry, both made of a plate and a block."""
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    write("gantry", GANTRY, {"plate": PLATE, "block": BLOCK})
    write("machine", machine(), {"plate": PLATE})
    return tmp_path


@pytest.fixture()
def light(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    return tmp_path


def box(name, m):
    """[x0, y0, z0, x1, y1, z1] of a body of a machine, or of a dict of posed solids."""
    lo, hi = bbox(getattr(m, "parts", m)[name])
    return np.array([*lo, *hi])


def rows_of(payload, check=None, rule=None, state=None):
    return [r for r in payload["rows"] if (check is None or r["check"] == check)
            and (rule is None or r["rule"] == rule) and (state is None or r["state"] == state)]


def problems(slug):
    with pytest.raises(SubassemblyError) as e:
        st.load_machine(slug)
    return e.value.problems


# ─── Flattening ──────────────────────────────────────────────────────────────

def test_a_child_is_flattened_in_under_its_name_and_moved_by_its_frame(tree):
    m = st.load_machine("machine")
    assert sorted(m.parts) == ["gantry/block", "gantry/plate", "plate"]
    c = m.children["gantry"]
    assert (c.name, c.project, c.at, c.turn, c.depth) == ("gantry", "gantry", (0.0, 0.0, 20.0), (0.0, 0.0, 90.0), 1)
    assert c.bodies == ("gantry/plate", "gantry/block") and c.projects == ("gantry",) and c.axes == ("gantry/x",)
    # the 40 x 20 plate is turned a quarter about z and stands 20 up; the block stays 10 over it
    assert np.allclose(box("gantry/plate", m), [-10, -20, 18, 10, 20, 22])
    assert np.allclose(box("gantry/block", m), [-5, -5, 23, 5, 5, 33])
    assert np.allclose(box("plate", m), [-20, -10, -52, 20, 10, -48])          # the parent's own body is where it was
    own = st.load_machine("gantry")                                             # the child alone is untouched
    assert sorted(own.parts) == ["block", "plate"] and own.children == {}
    assert np.allclose(box("plate", own), [-20, -10, -2, 20, 10, 2])


def test_the_frame_of_an_instance_is_pos_times_rot_and_placements_toml_s(tree):
    at, turn = (10.0, -4.0, 7.0), (30.0, 45.0, 60.0)
    probe = Pos(3, 5, -2) * Box(1, 1, 1)
    want = (Pos(*at) * Rot(*turn) * probe).center()
    got = probe.moved(subassembly.instance_location(at, turn)).center()
    assert np.allclose([got.X, got.Y, got.Z], [want.X, want.Y, want.Z], atol=1e-9)
    m = np.array(subassembly.instance_matrix(at, turn))
    assert np.allclose(m[:, 3], at)
    r = placements.matrix({"move": at, "turn": turn, "about": (0.0, 0.0, 0.0)})
    assert np.allclose(m, r)                                                    # a hand move means the same
    # a quarter turn about z takes x to y; the move comes after the turn
    q = np.array(subassembly.instance_matrix((1.0, 2.0, 3.0), (0.0, 0.0, 90.0)))
    assert np.allclose(q @ [1, 0, 0, 1], [1, 3, 3])


def test_a_bodys_info_is_its_projects_with_the_name_prefixed(tree):
    m = st.load_machine("machine")
    info, own = m.bodies["gantry/block"], st.load_machine("gantry").bodies["block"]
    assert (info.name, info.project, info.part, info.kind) == ("gantry/block", "gantry", "block", "made")
    assert info.mass_g == pytest.approx(own.mass_g) and info.material == "aluminium" == own.material
    assert m.bodies["plate"].project == "machine" and set(m.bodies) == set(m.parts)


def test_a_bought_body_stays_the_bought_part_it_is_and_keeps_its_declared_mass(tree):
    d = st.project_dir("gantry")
    (d / "bought").mkdir(exist_ok=True)
    from build123d import export_step
    export_step(Box(8, 8, 8), str(d / "bought" / "motor.step"))
    (d / "bought" / "motor.json").write_text(json.dumps(
        {"source": "vendor drawing 1", "mass_g": 120, "mass_source": "datasheet", "material": "steel"}))
    (d / "assembly.py").write_text(GANTRY.replace(
        'return {"plate": plate, "block": Pos(0, 0, 8) * block}',
        'from cad_agent.state import bought_solid\n    return {"plate": plate, "block": Pos(0, 0, 8) * block,'
        ' "motor": Pos(0, 0, 30) * bought_solid(SLUG, "motor")}'))
    info = st.load_machine("machine").bodies["gantry/motor"]
    assert (info.kind, info.project, info.part, info.mass_g) == ("bought", "gantry", "motor", 120.0)
    assert info.mass_source == "datasheet"


def test_clearance_and_allow_contact_are_lifted_with_the_prefix_and_the_parents_entry_wins(tree):
    m = st.load_machine("machine")
    assert m.clearance == {"gantry/plate|gantry/block": 1.0}
    assert m.allow_contact == {("gantry/plate", "gantry/rail")}                 # a tuple key stays a tuple
    write("machine", machine(extra='CLEARANCE = {"gantry/plate|gantry/block": 0.25}\nALLOW_CONTACT = {"plate|x"}'),
          {"plate": PLATE})
    m = st.load_machine("machine")
    assert m.clearance == {"gantry/plate|gantry/block": 0.25}
    assert m.allow_contact == {"plate|x", ("gantry/plate", "gantry/rail")}


def test_axes_and_poses_are_lifted_and_turn_with_the_instance(tree):
    ax = st.load_machine("machine").axes["gantry/x"]
    assert ax.name == "gantry/x" and ax.moves == ("gantry/block",) and ax.tool == "gantry/block"
    assert np.allclose(ax.direction, (0, 1, 0), atol=1e-12)                    # x turned a quarter about z is y
    assert np.allclose(ax.tool_point, (0, 3, 5), atol=1e-12)
    assert ax.travel == (-10.0, 10.0) and ax.work == (-10.0, 10.0)             # distances along the axis do not turn
    assert st.load_machine("machine").poses == {"gantry/park": {"gantry/x": -10}}
    own = st.load_machine("gantry").axes["x"]                                  # the child's own axis is still x
    assert own.direction == (1.0, 0.0, 0.0) and own.moves == ("block",)


def test_the_reach_of_a_lifted_axis_is_the_childs(tree):
    from cad_agent.motion import tool_span
    assert tool_span(st.load_machine("machine").axes["gantry/x"]) == pytest.approx(tool_span(st.load_machine("gantry").axes["x"]))


def test_a_pose_drives_the_lifted_axis_along_the_direction_it_turned_to(tree):
    m = st.load_machine("machine")
    home = box("gantry/block", m)
    posed = apply_pose(m, "gantry/park")
    lo, hi = bbox(posed["gantry/block"])
    assert np.allclose([*lo, *hi], home + [0, -10, 0, 0, -10, 0])               # -10 along (0, 1, 0)
    assert np.allclose(bbox(posed["gantry/plate"])[0], bbox(m.parts["gantry/plate"])[0])   # the rest stays
    assert np.allclose(box("gantry/block", m), home)                            # and the machine itself is not moved


def test_two_instances_of_one_project_and_a_grandchild(light):
    write("gantry", GANTRY, {"plate": PLATE, "block": BLOCK})
    write("machine", machine('{"left": {"project": "gantry", "at": [-50, 0, 0]},'
                             ' "right": {"project": "gantry", "at": [50, 0, 0], "turn": [0, 0, 180]}}'), {"plate": PLATE})
    m = st.load_machine("machine")
    assert sorted(m.parts) == ["left/block", "left/plate", "plate", "right/block", "right/plate"]
    assert sorted(m.axes) == ["left/x", "right/x"]
    assert np.allclose(m.axes["right/x"].direction, (-1, 0, 0), atol=1e-12)
    assert subassembly.projects_of(m)[0][0] == "gantry" and len(subassembly.projects_of(m)) == 1   # once, not twice
    # a project that links the machine in turn: names nest, axes keep their path, projects list every level
    write("plant", machine('{"line": {"project": "machine", "at": [0, 0, 5]}}').replace('SLUG = "machine"', 'SLUG = "plant"'),
          {"plate": PLATE})
    p = st.load_machine("plant")
    assert "line/left/block" in p.parts and "line/plate" in p.parts and "plate" in p.parts
    assert sorted(p.axes) == ["line/left/x", "line/right/x"]
    assert p.children["line"].projects == ("machine", "gantry") and p.children["line"].depth == 1
    assert [name for name, _ in subassembly.projects_of(p)] == ["machine", "gantry"]
    assert p.bodies["line/left/block"].project == "gantry"
    assert np.allclose(box("line/left/block", p)[:3], box("left/block", m)[:3] + [0, 0, 5])


def test_a_parent_axis_can_move_a_whole_sub_assembly_with_slash_star(tree):
    write("machine", machine(extra=textwrap.dedent('''\
        AXES = {"z": {"moves": ("gantry/*", "plate"), "direction": (0, 0, 1), "travel": (0.0, 30.0)}}
        POSES = {"up": {"z": 30, "gantry/x": 10}}''')), {"plate": PLATE})
    m = st.load_machine("machine")
    assert m.axes["z"].moves == ("gantry/plate", "gantry/block", "plate")
    posed = apply_pose(m, "up")
    # z lifts everything 30; x then slides the block along the turned direction, which adds up
    assert np.allclose(box("gantry/block", posed) - box("gantry/block", m), [0, 10, 30, 0, 10, 30])
    assert np.allclose(box("gantry/plate", posed) - box("gantry/plate", m), [0, 0, 30, 0, 0, 30])
    assert m.poses["up"] == {"z": 30, "gantry/x": 10} and "gantry/park" in m.poses


def test_the_childs_own_hand_moves_apply_and_the_parents_move_a_child_body_by_its_full_name(tree):
    (st.project_dir("gantry") / "placements.toml").write_text('[block]\nmove = [0.0, 0.0, 1.0]\nturn = [0.0, 0.0, 0.0]\n'
                                                              'about = [0.0, 0.0, 8.0]\n')
    assert np.allclose(box("gantry/block", st.load_machine("machine")), [-5, -5, 24, 5, 5, 34])    # the child's design
    placements.save(st.project_dir("machine"), {"gantry/block": {"move": (0.0, 5.0, 0.0), "turn": (0.0, 0.0, 0.0),
                                                                 "about": (0.0, 0.0, 28.0)}})
    text = (st.project_dir("machine") / "placements.toml").read_text()
    assert '["gantry/block"]' in text                                            # a quoted key, or the file would not parse
    assert placements.load(st.project_dir("machine"))["gantry/block"]["move"] == (0.0, 5.0, 0.0)
    moved = st.load_machine("machine")
    assert np.allclose(box("gantry/block", moved), [-5, -5 + 5, 24, 5, 5 + 5, 34])
    assert np.allclose(box("gantry/block", st.load_machine("machine", placed=False)), [-5, -5, 24, 5, 5, 34])
    assert "plate" in moved.parts and "[plate]" not in text


def test_a_name_that_is_not_a_bare_key_is_quoted_and_a_bare_one_is_not(tmp_path):
    placements.save(tmp_path, {"plate": {"move": (1.0, 0.0, 0.0), "turn": (0.0, 0.0, 0.0), "about": (0.0, 0.0, 0.0)},
                               "a/b": {"move": (1.0, 0.0, 0.0), "turn": (0.0, 0.0, 0.0), "about": (0.0, 0.0, 0.0)},
                               "a.b": {"move": (2.0, 0.0, 0.0), "turn": (0.0, 0.0, 0.0), "about": (0.0, 0.0, 0.0)}})
    text = (tmp_path / "placements.toml").read_text()
    assert "[plate]" in text and '["a/b"]' in text and '["a.b"]' in text
    assert sorted(placements.load(tmp_path)) == ["a.b", "a/b", "plate"]          # a dotted name is no longer a nested table


# ─── Failures are rows, never a crash ────────────────────────────────────────

def test_a_cycle_is_a_fail_row_that_gives_the_chain(light, capsys):
    stock("a", 'SUBASSEMBLIES = {"b": {"project": "b"}}')
    stock("b", 'SUBASSEMBLIES = {"a": {"project": "a"}}')
    (p,) = problems("a")
    assert p.kind == "cycle" and "a -> b -> a" in p.message
    (p,) = problems("b")
    assert p.kind == "cycle" and "b -> a -> b" in p.message            # from the other end, the same cycle
    stock("me", 'SUBASSEMBLIES = {"again": {"project": "me"}}')
    assert problems("me")[0].kind == "cycle"
    code, data = run(capsys, "check", "a", "--all")
    assert code == cli.FAIL                                              # 1, a verdict; not 4, a crash
    (row,) = rows_of(data, "subassembly", "cycle")
    assert row["state"] == "FAIL" and "a -> b -> a" in row["measured"] and row["subject"] == "a"   # b's link back to a
    payload = check_all("a")
    assert rows_of(payload, "subassembly", "cycle", "FAIL") and payload["summary"]["ok"] is False


def test_eight_levels_of_sub_assemblies_load_and_nine_are_a_fail_row(light, capsys):
    def chain(n):
        for i in range(n):
            stock(f"p{i}", f'SUBASSEMBLIES = {{"next": {{"project": "p{i + 1}"}}}}' if i < n - 1 else "",
                  bodies=f'"b{i}": Box(5, 5, 5)')
    chain(9)                                                             # p0 and eight below it
    m = st.load_machine("p0")
    assert sorted(m.parts)[0] == "b0" and "next/" * 8 + "b8" in m.parts
    chain(10)
    (p,) = problems("p0")
    assert p.kind == "depth" and "level 9" in p.message and "limit is 8" in p.message
    code, data = run(capsys, "check", "p0")
    assert code == cli.FAIL and rows_of(data, "subassembly", "depth", "FAIL")
    assert st.load_machine("p1").parts                                  # p1 has only eight levels under it: it loads


def test_a_slash_in_a_body_name_is_a_fail_row_whether_or_not_anything_is_linked(light, capsys):
    stock("plain", bodies='"left/rail": Box(5, 5, 5), "ok": Box(5, 5, 5)')
    assert sorted(st.load_machine("plain").parts) == ["left/rail", "ok"]          # it loads: the rule is what fails it
    code, data = run(capsys, "check", "plain", "--all")
    (row,) = rows_of(data, "subassembly", "name")
    assert code == cli.FAIL and row["state"] == "FAIL" and row["subject"] == "left/rail"
    assert "gantry/x_carriage" in row["measured"]
    stock("kid", bodies='"x/y": Box(5, 5, 5)')                                    # a child with one
    stock("par", 'SUBASSEMBLIES = {"g": {"project": "kid"}}')
    (p,) = problems("par")
    assert p.kind == "name" and p.subject == "g/x/y" and "'kid'" in p.message
    stock("kid2")                                                                 # an instance with one
    stock("par2", 'SUBASSEMBLIES = {"a/b": {"project": "kid2"}}')
    assert problems("par2")[0].kind == "name"
    stock("par3", 'SUBASSEMBLIES = {"base": {"project": "kid2"}}')               # a body called like an instance
    (p,) = problems("par3")
    assert p.kind == "name" and "body and of a sub-assembly" in p.message


@pytest.mark.parametrize("subs,kind,text", [
    ('{"g": {"project": "kid", "bogus": 1}}', "declaration", "does not take bogus"),
    ('{"g": {"at": [0, 0, 0]}}', "declaration", "needs `project`"),
    ('{"g": {"project": "kid", "at": [0, 0]}}', "declaration", "`at` must be three numbers"),
    ('{"g": {"project": "kid", "turn": [0, 0, "x"]}}', "declaration", "`turn` must be three numbers"),
    ('{"g": {"project": "kid", "at": [0, float("nan"), 0]}}', "declaration", "three numbers"),
    ('{"g": {"project": "../kid"}}', "declaration", "needs `project`"),
    ('{"g": "kid"}', "declaration", "must be"),
    ('["kid"]', "declaration", "SUBASSEMBLIES must be"),
    ('{"g": {"project": "nope"}}', "project", "does not exist"),
    ('{"g": {"project": "empty"}}', "project", "has no assembly.py"),
    ('{"g": {"project": "broken"}}', "build", "boom"),
])
def test_a_declaration_that_cannot_be_used_is_a_problem_of_its_kind(light, subs, kind, text):
    stock("kid")
    st.project_dir("empty", create=True)
    write("broken", 'def parts():\n    raise RuntimeError("boom")\n')
    stock("par", f"SUBASSEMBLIES = {subs}")
    (p,) = problems("par")
    assert p.kind == kind and text in p.message


def test_every_fault_gets_its_own_row_and_the_check_still_exits_1(light, capsys):
    stock("kid")
    stock("par", 'SUBASSEMBLIES = {"ghost": {"project": "nope"}, "bad": {"project": "kid", "at": [1, 2]},'
                 ' "a/b": {"project": "kid"}, "fine": {"project": "kid"}}',
          bodies='"base": Box(5, 5, 5)')
    code, data = run(capsys, "check", "par", "--all")
    assert code == cli.FAIL
    found = {(r["rule"], r["subject"]) for r in data["rows"] if r["check"] == "subassembly"}
    assert found == {("project", "ghost"), ("declaration", "bad"), ("name", "a/b")}
    assert all(r["state"] == "FAIL" and r["source"] == "SUBASSEMBLIES in assembly.py" for r in rows_of(data, "subassembly"))


def test_a_parent_axis_over_a_sub_assembly_that_is_not_there_is_a_moves_problem(tree):
    write("machine", machine(extra='AXES = {"z": {"moves": ("ghost/*",), "direction": (0, 0, 1), "travel": (0.0, 5.0)}}'),
          {"plate": PLATE})
    (p,) = problems("machine")
    assert p.kind == "moves" and "'ghost'" in p.message and "sub-assemblies: gantry" in p.message


def test_a_malformed_placements_file_in_a_child_fails_closed_naming_it(tree, capsys):
    (st.project_dir("gantry") / "placements.toml").write_text("[block\n")
    with pytest.raises(placements.PlacementError, match=r"sub-assembly 'gantry' \(gantry\): placements.toml does not parse"):
        st.load_machine("machine")
    code, data = run(capsys, "check", "machine")
    assert code == cli.FAIL and "sub-assembly 'gantry'" in data["error"]


def test_a_child_that_fails_to_build_names_the_instance_and_the_cause(tree):
    (st.project_dir("gantry") / "parts" / "block.py").write_text(
        BLOCK.replace("return", "raise ValueError('wall came out negative')\n    return"))
    (p,) = problems("machine")
    assert p.kind == "build" and p.subject == "gantry" and "wall came out negative" in p.message


# ─── Poses in the spec, and the rule that checks POSES ───────────────────────

# Two boxes 10 apart along x and a slider on a rail. The poses bring it to 2 mm from the fixed one, into it, away.
RIG = '''from build123d import Box, Pos

AXES = {
    "x": {"moves": ("slider",), "direction": (1, 0, 0), "travel": (-20.0, 5.0), "work": (-20.0, 5.0), "tool": "slider"},
    "y": {"moves": ("nobody",), "direction": (0, 1, 0), "travel": (0.0, 5.0)},
    "xy": {"moves": ("slider", "fixed"), "direction": (1, 0, 0), "travel": (-1.0, 1.0)},
}
POSES = {"in": {"x": -8}, "hit": {"x": -12}, "far": {"x": 5}, "home": {}, "ghost": {"nothing": 1}, "over": {"x": 9},
         "gone": {"y": 1}, "words": {"x": "left"}}


def parts():
    return {"fixed": Box(10, 10, 10), "slider": Pos(20, 0, 0) * Box(10, 10, 10)}
'''


@pytest.fixture()
def rig(light):
    write("rig", RIG)
    return light


def spec_rows(slug, text, machine=True):
    (st.project_dir(slug) / "spec.toml").write_text(text)
    m = st.load_machine(slug)
    return list(check_spec(slug, m.parts, machine=m if machine else None))


def only(rows):
    assert len(rows) == 1, [(r.rule, r.state, r.measured) for r in rows]
    return rows[0]


def actx(slug):
    from cad_agent.registry import AssemblyCtx
    m = st.load_machine(slug)
    return AssemblyCtx(slug=slug, parts=m.parts, clearance=m.clearance, allow_contact=m.allow_contact,
                       out_dir=None, axes=m.axes, machine=m)


def test_a_clearance_is_judged_with_the_machine_at_the_pose_it_names(rig):
    entry = '[[clearance]]\na = "fixed"\nb = "slider"\nmin_mm = 5\n'
    home = only(spec_rows("rig", entry))
    assert (home.state, home.measured) == ("PASS", "10.000 mm")                  # a row without a pose reads as it did
    far = only(spec_rows("rig", entry + 'pose = "far"\n'))
    assert (far.state, far.measured) == ("PASS", "15.000 mm at pose far")
    near = only(spec_rows("rig", entry + 'pose = "in"\n'))
    assert (near.state, near.measured) == ("FAIL", "2.000 mm at pose in, too close")
    hit = only(spec_rows("rig", entry + 'pose = "hit"\n'))
    assert hit.state == "FAIL" and hit.measured == "they interfere, overlap 200.000 mm^3 at pose hit"
    assert near.subject == "fixed|slider" and near.rule == "spec/clearance"       # the subject is still the pair


def test_a_position_is_judged_with_the_machine_at_the_pose_it_names(rig):
    at = lambda x, pose="": spec_rows("rig", f'[[position]]\nbody = "slider"\ncenter_mm = [{x}, 0, 0]\n{pose}')
    assert only(at(20)).state == "PASS" and only(at(20)).measured == "center (20.00, 0.00, 0.00) mm, offset 0.000 mm"
    assert only(at(12, 'pose = "in"\n')).state == "PASS"
    miss = only(at(20, 'pose = "in"\n'))
    assert miss.state == "FAIL" and "at pose in (dx -8.00" in miss.measured


def test_a_keepout_is_judged_with_the_machine_at_the_pose_it_names(rig):
    entry = '[[keepout]]\ntool = "drill"\nparams = { diameter = 6, flute = 20 }\nat = [10, 0, -5]\nclear = ["slider"]\n'
    home = only(spec_rows("rig", entry))
    assert (home.state, home.measured) == ("PASS", "clear by 2.000 mm")
    posed = only(spec_rows("rig", entry + 'pose = "in"\n'))                        # the tool stays; the slider comes to it
    assert posed.state == "FAIL" and "inside the drill envelope" in posed.measured and posed.measured.endswith("at pose in")
    ok = only(spec_rows("rig", entry + 'pose = "far"\n'))
    assert ok.state == "PASS" and ok.measured == "clear by 7.000 mm at pose far"


@pytest.mark.parametrize("pose,text", [
    ('"nope"', "no pose 'nope' in POSES (poses: far, ghost, gone, hit, home, in, over, words)"),
    ('"ghost"', "drives 'nothing', which is not an axis of AXES (axes: x, xy, y)"),
    ('"over"', "puts x at 9 mm, outside its travel -20 to 5 mm"),
    ('"words"', "puts x at 'left', which is not a number of mm"),
    ('"gone"', "which the assembly does not return"),
    ("5", "`pose` must name a pose of POSES, got 5"),
])
def test_a_pose_that_cannot_be_applied_makes_the_entry_unchecked_and_says_why(rig, pose, text):
    row = only(spec_rows("rig", f'[[clearance]]\na = "fixed"\nb = "slider"\nmin_mm = 5\npose = {pose}\n'))
    assert row.state == "UNCHECKED" and text in row.measured and row.subject == "[[clearance]] #1"


def test_a_pose_needs_an_assembly_to_pose(rig):
    row = only(spec_rows("rig", '[[position]]\nbody = "fixed"\ncenter_mm = [0, 0, 0]\npose = "in"\n', machine=False))
    assert row.state == "UNCHECKED" and "no assembly was loaded" in row.measured


def test_the_poses_rule_passes_a_good_pose_and_fails_each_way_a_pose_can_be_wrong(rig):
    from cad_agent.ruleset.subassembly import poses
    rows = {r.subject: r for r in poses(actx("rig"))}
    for good in ("in", "hit", "far"):
        assert rows[f"pose {good}"].state == "PASS" and "inside travel" in rows[f"pose {good}"].measured
    assert rows["pose home"].state == "PASS" and "no axis driven" in rows["pose home"].measured
    assert rows["pose far"].measured == "x = 5 mm; inside travel"
    assert rows["pose ghost"].state == "FAIL" and "'nothing' is not an axis of AXES" in rows["pose ghost"].measured
    assert rows["pose over"].state == "FAIL" and "outside its travel -20 to 5 mm" in rows["pose over"].measured
    assert rows["pose gone"].state == "FAIL" and "y moves nobody, which the assembly does not return" in rows["pose gone"].measured
    assert rows["pose words"].state == "FAIL" and "not a number of mm" in rows["pose words"].measured
    assert all(r.rule == "pose" for r in rows.values())


def test_a_section_that_does_not_read_a_pose_but_is_given_one_is_unchecked_not_judged_at_home(rig):
    from cad_agent.ruleset.subassembly import poses
    (st.project_dir("rig") / "spec.toml").write_text(
        '[[size]]\nbody = "fixed"\nmin_mm = [1, 1, 1]\npose = "in"\n\n[envelope]\nmax_mm = [99, 99, 99]\npose = "in"\n\n'
        '[[clearance]]\na = "fixed"\nb = "slider"\nmin_mm = 1\npose = "in"\n')
    ignored = [r for r in poses(actx("rig")) if r.state == "UNCHECKED"]
    assert [r.subject for r in ignored] == ["[[size]] #1", "[envelope]"]
    assert all(r.rule == "pose" and "ignores it" in r.measured for r in ignored)
    (st.project_dir("rig") / "spec.toml").write_text("[envelope\n")                # a spec that does not parse: the spec rule's
    assert not [r for r in poses(actx("rig")) if r.state == "UNCHECKED"]


def test_the_rules_say_nothing_of_a_project_with_no_sub_assemblies_no_poses_and_no_slash(light):
    from cad_agent.ruleset.subassembly import poses, subassembly
    stock("plain")
    ctx = actx("plain")
    assert list(subassembly(ctx)) == [] and list(poses(ctx)) == []                # so every old verdict is what it was


def test_each_sub_assembly_gets_a_pass_row_that_says_what_was_linked(tree):
    from cad_agent.ruleset.subassembly import subassembly
    (row,) = list(subassembly(actx("machine")))
    assert (row.subject, row.rule, row.state) == ("gantry", "linked", "PASS")
    assert row.measured == "project gantry at (0, 0, 20) mm, turned (0, 0, 90) deg: 2 bodies, 1 axes"


# ─── [[axis]] and [bodies]: what the grader could not ask before ─────────────

def axis_row(text, slug="rig"):
    return only(spec_rows(slug, text))


def test_an_axis_requirement_passes_when_the_declaration_does_what_was_asked(rig):
    row = axis_row('[[axis]]\nname = "x"\nmoves = ["slider"]\nonly = true\ndirection = [1, 0, 0]\ntravel_min_mm = 25\n'
                   'travel_max_mm = 25\nwork_min_mm = 25\ntool = "slider"\n')
    assert (row.state, row.subject, row.rule) == ("PASS", "axis x", "spec/axis")
    assert "moves slider; along (1.000, 0.000, 0.000); travel -20 to 5 mm (25 mm); work -20 to 5 mm" == row.measured
    assert axis_row('[[axis]]\nname = "x"\ndirection = [-1, 0, 0]\n').state == "PASS"              # either way along the line
    assert axis_row('[[axis]]\nname = "x"\ndirection = [0, 1, 0]\ntol_deg = 90\n').state == "PASS"


@pytest.mark.parametrize("entry,text", [
    ('name = "z"', "no axis 'z' in AXES (axes: x, xy, y)"),
    ('name = "x"\nmoves = ["slider", "fixed"]', "does not move fixed"),
    ('name = "xy"\nmoves = ["slider"]\nonly = true', "also moves fixed"),
    ('name = "x"\ndirection = [0, 1, 0]', "runs 90.0 deg off the line asked for"),
    ('name = "x"\ntravel_min_mm = 30', "travels 25 mm, short of 30"),
    ('name = "x"\ntravel_max_mm = 20', "travels 25 mm, past 20"),
    ('name = "x"\nwork_min_mm = 30', "promises 25 mm of work, short of 30"),
    ('name = "xy"\nwork_min_mm = 1', "declares no work span"),
    ('name = "x"\ntool = "fixed"', "carries its tool on 'slider', not 'fixed'"),
])
def test_an_axis_requirement_fails_when_the_design_does_less(rig, entry, text):
    row = axis_row(f"[[axis]]\n{entry}\n")
    assert row.state == "FAIL" and text in row.measured and "declared in AXES" in row.limit


def test_a_design_with_no_axes_at_all_fails_a_requirement_for_one(light):
    stock("bare")
    row = axis_row('[[axis]]\nname = "x"\nmoves = ["base"]\n', "bare")
    assert row.state == "FAIL" and "none: assembly.py declares no AXES" in row.measured


@pytest.mark.parametrize("entry,text", [
    ('moves = ["slider"]', "missing `name`"),
    ('name = 3', "must be the name of an axis"),
    ('name = "x"\nbogus = 1', "does not take bogus"),
    ('name = "x"\nmoves = "slider"', "`moves` must be a list of body names"),
    ('name = "x"\nmoves = []', "`moves` must be a list of body names"),
    ('name = "x"\nmoves = ["ghost"]', "no body 'ghost' in the assembly"),
    ('name = "x"\nmoves = ["slider", "slider"]', "lists a body twice"),
    ('name = "x"\nonly = true', "`only` says no other body moves"),
    ('name = "x"\nonly = "yes"\nmoves = ["slider"]', "`only` must be true or false"),
    ('name = "x"\ntool = 4', "`tool` must name a body"),
    ('name = "x"\ntool = "ghost"', "no body 'ghost' in the assembly"),
    ('name = "x"\ndirection = [0, 0, 0]', "zero length"),
    ('name = "x"\ndirection = [1, 0]', "direction must be [x, y, z]"),
    ('name = "x"\ntol_deg = -1', "must be at least 0"),
    ('name = "x"\ntravel_min_mm = "far"', "must be a number"),
    ('name = "x"\ntravel_min_mm = 9\ntravel_max_mm = 3', "above travel_max_mm"),
])
def test_an_axis_entry_that_cannot_be_read_is_unchecked(rig, entry, text):
    row = axis_row(f"[[axis]]\n{entry}\n")
    assert row.state == "UNCHECKED" and text in row.measured


def test_an_axis_requirement_needs_an_assembly_to_read_axes_from(rig):
    row = only(spec_rows("rig", '[[axis]]\nname = "x"\n', machine=False))
    assert row.state == "UNCHECKED" and "no assembly was loaded" in row.measured


def test_an_axis_requirement_reads_a_lifted_axis_by_its_full_name_and_its_turned_direction(tree):
    ok = axis_row('[[axis]]\nname = "gantry/x"\nmoves = ["gantry/block"]\ndirection = [0, 1, 0]\ntravel_min_mm = 20\n', "machine")
    assert ok.state == "PASS" and "along (0.000, 1.000, 0.000)" in ok.measured
    off = axis_row('[[axis]]\nname = "gantry/x"\ndirection = [1, 0, 0]\n', "machine")           # the child's x is not the machine's
    assert off.state == "FAIL" and "90.0 deg off" in off.measured
    assert axis_row('[[axis]]\nname = "x"\n', "machine").state == "FAIL"                         # the child's name is not the lifted one


def test_a_body_count_passes_fails_and_names_what_is_missing_or_extra(rig):
    count = lambda body: only(spec_rows("rig", body))
    assert (count("[bodies]\ncount = 2\n").state, count("[bodies]\ncount = 2\n").measured) == ("PASS", "2 bodies: fixed, slider")
    assert count("[bodies]\ncount = 2\n").subject == "assembly" and count("[bodies]\ncount = 2\n").rule == "spec/bodies"
    assert count('[bodies]\nnames = ["slider", "fixed"]\n').state == "PASS"
    assert count('[bodies]\ncount = 2\nnames = ["fixed", "slider"]\n').limit == "exactly 2 bodies; exactly the bodies fixed, slider"
    few, many = count("[bodies]\ncount = 3\n"), count("[bodies]\ncount = 1\n")
    assert few.state == "FAIL" and few.measured == "2 bodies, 1 fewer than 3"
    assert many.state == "FAIL" and many.measured == "2 bodies, 1 more than 1"
    names = count('[bodies]\nnames = ["fixed", "tool"]\n')
    assert names.state == "FAIL" and names.measured == "missing tool; not asked for: slider"
    both = count('[bodies]\ncount = 3\nnames = ["fixed", "slider", "tool"]\n')
    assert both.state == "FAIL" and both.measured == "2 bodies, 1 fewer than 3; missing tool"


@pytest.mark.parametrize("body,text", [
    ("", "needs `count` and/or `names`"),
    ("bogus = 1", "does not take bogus"),
    ("count = true", "`count` must be a whole number of bodies"),
    ("count = 2.5", "`count` must be a whole number of bodies"),
    ("count = -1", "`count` must be a whole number of bodies"),
    ('names = "fixed"', "`names` must be a list of body names"),
    ('names = ["fixed", ""]', "`names` must be a list of body names"),
    ('names = ["fixed", "fixed"]', "lists fixed more than once"),
    ('count = 3\nnames = ["fixed"]', "`count` is 3 and `names` lists 1"),
])
def test_a_body_count_that_cannot_be_read_is_unchecked(rig, body, text):
    row = only(spec_rows("rig", f"[bodies]\n{body}\n"))
    assert row.state == "UNCHECKED" and text in row.measured and row.subject == "[bodies]"


def test_a_body_count_has_nothing_to_count_without_an_assembly_and_counts_a_sub_assemblys_full_names(tree):
    st.project_dir("bare", create=True)
    (st.project_dir("bare") / "spec.toml").write_text("[bodies]\ncount = 0\n")
    row = only(list(check_spec("bare", {}, machine=None)))
    assert row.state == "UNCHECKED" and "no assembly.py, so there are no bodies to count" in row.measured
    ok = only(spec_rows("machine", '[bodies]\ncount = 3\nnames = ["plate", "gantry/plate", "gantry/block"]\n'))
    assert ok.state == "PASS" and ok.measured == "3 bodies: gantry/block, gantry/plate, plate"
    assert only(spec_rows("machine", '[bodies]\nnames = ["plate", "plate"]\n')).state == "UNCHECKED"
    assert only(spec_rows("machine", '[bodies]\nnames = ["plate", "plate_2"]\n')).state == "FAIL"
