"""Sub-assemblies, poses and the "/" in a body's name (cad_agent/subassembly.py, step 6 piece B).

A machine is a project that links other projects. These tests build small sibling projects in a temp folder, never
a real one: a plate and a block (test_cli.py's) and a few boxes, so what is measured is the linking. Most call
load_machine or a rule directly; the few that run whole gates (`check_all`, `verify.run`) say why.
"""
import json
import subprocess
import textwrap
import threading
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from build123d import Box, Pos, Rot

from cad_agent import buildcache, cli, placements, serve, subassembly, verify
from cad_agent import state as st
from cad_agent.geom import bbox
from cad_agent.runner import approve_views, check_all
from cad_agent.spec import check_spec
from cad_agent.subassembly import PoseError, SubassemblyError, apply_pose
from test_buildcache import BLOCK            # the block that returns a Part, which the build cache keeps
from test_cli import PLATE, log_lines, run
from test_workbench import inproc

# The child. Its plate spans x -20..20, y -10..10, z -2..2 and its block 10 mm up, so the 1 mm of air between
# them is a required clearance, and the block rides the x axis 10 mm either way.
GANTRY = '''from build123d import Pos
from cad_agent.state import build_part

SLUG = "gantry"
CLEARANCE = {"plate|block": 1.0}
ALLOW_CONTACT = {("plate", "rail")}
AXES = {"x": {"moves": ("block",), "direction": (1, 0, 0), "travel": (-10.0, 10.0), "work": (-7.0, 7.0),
              "tool": "block", "tool_point": (3.0, 0.0, 5.0)}}      # the tool point reaches 3 mm along x, so -7 to 13
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


def add_motor(mass_g=120):
    """A bought motor in the gantry, 30 mm up, with a declared mass: from then on every body of the gantry has one."""
    from build123d import export_step
    d = st.project_dir("gantry")
    (d / "bought").mkdir(exist_ok=True)
    export_step(Box(8, 8, 8), str(d / "bought" / "motor.step"))
    (d / "bought" / "motor.json").write_text(json.dumps(
        {"source": "vendor drawing 1", "mass_g": mass_g, "mass_source": "datasheet", "material": "steel"}))
    (d / "assembly.py").write_text(GANTRY.replace(
        'return {"plate": plate, "block": Pos(0, 0, 8) * block}',
        'from cad_agent.state import bought_solid\n    return {"plate": plate, "block": Pos(0, 0, 8) * block,'
        ' "motor": Pos(0, 0, 30) * bought_solid(SLUG, "motor")}'))


def test_a_bought_body_stays_the_bought_part_it_is_and_keeps_its_declared_mass(tree):
    add_motor()
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
    assert ax.travel == (-10.0, 10.0) and ax.work == (-7.0, 7.0)             # distances along the axis do not turn
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


def test_apply_pose_says_which_part_of_a_pose_cannot_be_applied(tree):
    m = st.load_machine("machine")
    with pytest.raises(PoseError, match="no pose 'nope' in POSES .poses: gantry/park."):
        apply_pose(m, "nope")
    m.poses.update({"ghost": {"w": 1}, "over": {"gantry/x": 11}, "text": {"gantry/x": "left"}, "nan": {"gantry/x": float("nan")}})
    with pytest.raises(PoseError, match=r"drives 'w', which is not an axis of AXES \(axes: gantry/x\)"):
        apply_pose(m, "ghost")
    with pytest.raises(PoseError, match=r"puts gantry/x at 11 mm, outside its travel -10 to 10 mm"):
        apply_pose(m, "over")
    with pytest.raises(PoseError, match="not a number of mm"):
        apply_pose(m, "text")
    with pytest.raises(PoseError, match="not a number of mm"):
        apply_pose(m, "nan")
    assert apply_pose(m, "gantry/park", {"gantry/block": m.parts["gantry/block"]}).keys() == {"gantry/block"}   # the solids it is given
    m.poses["end"] = {"gantry/x": 10.0 + 1e-9}                                  # a position a hair past the end is the end
    apply_pose(m, "end")


def test_a_name_is_split_at_its_first_slash_and_a_file_made_from_it_is_one_file():
    assert subassembly.split("gantry/x_carriage") == ("gantry", "x_carriage")
    assert subassembly.split("line/left/block") == ("line", "left/block")
    assert subassembly.split("plate") == (None, "plate")
    assert subassembly.file_stem("gantry/x_carriage") == "gantry__x_carriage" and subassembly.file_stem("plate") == "plate"
    assert "/" not in subassembly.file_stem("a/b/c") and "gantry/x_carriage" in subassembly.name_rule("a/b")


def test_a_child_whose_axis_cannot_be_moved_is_a_problem_of_its_own_not_a_crash(tree, capsys):
    (st.project_dir("gantry") / "assembly.py").write_text(GANTRY.replace('"direction": (1, 0, 0)', '"direction": (1, 0)'))
    assert st.load_machine("gantry").axes["x"].direction == (1.0, 0.0)           # on its own it loads
    (p,) = problems("machine")
    assert p.kind == "build" and p.subject == "gantry" and "could not be flattened in" in p.message
    code, data = run(capsys, "check", "machine")
    assert code == cli.FAIL and rows_of(data, "subassembly", "build", "FAIL")


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


# ─── The tree is hashed, rebuilt and judged as a whole ───────────────────────

GANTRY_SPEC = "[envelope]\nmax_mm = [50, 30, 30]\n"
MACHINE_SPEC = ('[bodies]\ncount = 3\n\n[[axis]]\nname = "gantry/x"\ndirection = [0, 1, 0]\n\n'
                '[[position]]\nbody = "gantry/block"\ncenter_mm = [0, -10, 28]\npose = "gantry/park"\n')


@pytest.fixture()
def approved(tree):
    """The tree with a spec each and every render approved, so that nothing waits on a person."""
    (tree / "gantry" / "spec.toml").write_text(GANTRY_SPEC)
    (tree / "machine" / "spec.toml").write_text(MACHINE_SPEC)
    check_all("machine")                          # draws a render of every part, the child's too
    approve_views("gantry")
    approve_views("machine")
    return tree


def unsettled(rec):
    return [(r["check"], r["rule"], r["state"], r["measured"]) for r in rec["rows"] if r["state"] not in ("PASS", "N/A")]


def git(d, *args):
    return subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def test_a_tree_is_verified_as_a_whole_and_an_edit_to_a_child_makes_the_verdict_stale(approved):
    rec = verify.run("machine", fresh=True, mode="test")
    assert rec["verdict"] == "PASS", unsettled(rec)
    assert {r["check"].split(":")[0] for r in rec["rows"] if ":" in r["check"]} == {"gantry"}      # the child's gates ran
    assert [s["project"] for s in rec["tree"]["subassemblies"]] == ["gantry"]
    own = verify._own_hash(st.project_dir("gantry"))
    assert rec["tree"]["projects"] == {"gantry": {"source_hash": own[0], "design_files": own[1]}}
    assert rec["design_files"] == len(verify.design_files(st.project_dir("machine"))) + own[1]
    assert verify.status("machine")["done"] is True
    block = st.project_dir("gantry") / "parts" / "block.py"
    block.write_text(block.read_text().replace('"size": 10.0', '"size": 9.0'))
    s = verify.status("machine")
    assert s["done"] is False and "the design changed since it was verified" in s["reasons"]


def test_a_project_that_links_nothing_verifies_and_hashes_as_it_always_did(approved):
    import hashlib
    child = st.project_dir("gantry")
    h = hashlib.sha256()
    for p in verify.design_files(child):
        h.update(p.relative_to(child).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    assert verify.source_hash(child) == (h.hexdigest(), len(verify.design_files(child)))
    rec = verify.run("gantry", fresh=True, mode="test")
    assert rec["verdict"] == "PASS", unsettled(rec)
    assert "tree" not in rec and verify.git_info(child) is None                   # nothing new in its record


def test_the_source_hash_follows_every_design_file_of_every_project_below_and_nothing_else(approved):
    machine_dir, child = st.project_dir("machine"), st.project_dir("gantry")
    base, n = verify.source_hash(machine_dir)
    for output in (child / "checks.json", child / "verify.json", child / "out" / "notes.txt", child / ".cad" / "x.json"):
        output.parent.mkdir(exist_ok=True)
        output.write_text("changed")
    assert verify.source_hash(machine_dir) == (base, n)                         # a run's outputs are not design
    seen = {base}
    for name, write_it in {
        "a part": lambda: (child / "parts" / "block.py").write_text(BLOCK + "# edit\n"),
        "its spec": lambda: (child / "spec.toml").write_text(GANTRY_SPEC + "# edit\n"),
        "its hand moves": lambda: (child / "placements.toml").write_text("[block]\nmove = [1.0, 0.0, 0.0]\n"),
        "its bought parts": lambda: ((child / "bought").mkdir(exist_ok=True), (child / "bought" / "m.step").write_text("x")),
        "an approved render": lambda: sorted((child / "baseline").glob("*.png"))[0].write_bytes(b"other"),
        "its assembly": lambda: (child / "assembly.py").write_text(GANTRY + "# edit\n"),
    }.items():
        write_it()
        now, count = verify.source_hash(machine_dir)
        assert now not in seen, name
        seen.add(now)
    assert count == n + 2                                                         # the hand moves and the bought part are two more
    (machine_dir / "parts" / "plate.py").write_text(PLATE + "# edit\n")           # and the parent's own, as before
    assert verify.source_hash(machine_dir)[0] not in seen


def test_the_tree_goes_all_the_way_down(light):
    write("gantry", GANTRY, {"plate": PLATE, "block": BLOCK})
    write("machine", machine(), {"plate": PLATE})
    write("plant", machine('{"line": {"project": "machine"}}').replace('SLUG = "machine"', 'SLUG = "plant"'), {"plate": PLATE})
    assert subassembly.tree_projects(st.project_dir("plant")) == (["machine", "gantry"], True)
    before = verify.source_hash(st.project_dir("plant"))[0]
    block = st.project_dir("gantry") / "parts" / "block.py"
    block.write_text(BLOCK + "# edit\n")
    assert verify.source_hash(st.project_dir("plant"))[0] != before               # a grandchild is part of the plant
    assert [p for p, _ in subassembly.tree_dirs(st.project_dir("plant"))] == ["gantry", "machine"]


@pytest.mark.parametrize("src,names,whole", [
    ("", [], True),
    ("SUBASSEMBLIES = {}\n", [], True),
    ('SUBASSEMBLIES = {"a": {"project": "p1"}, "b": {"project": "p2", "at": [X, 0, 0]}}\n', ["p1", "p2"], True),
    ('SUBASSEMBLIES = dict(a=dict(project="p1"), b={"project": "p2"})\n', ["p1", "p2"], True),
    ('SUBASSEMBLIES: dict = {"a": {"project": "p1"}}\n', ["p1"], True),
    ('K = "a"\nSUBASSEMBLIES = {K: {"project": "p1"}}\n', ["p1"], True),                        # a computed key is no matter
    ('SUBASSEMBLIES = {"a": {"project": "p1"}}\nSUBASSEMBLIES["b"] = {"project": "p2"}\n', ["p1", "p2"], True),
    ('SUBASSEMBLIES = {"a": {"project": "p" + "1"}}\n', [], False),
    ('SUBASSEMBLIES = {"a": {"project": NAME}}\n', [], False),
    ('SUBASSEMBLIES = {"a": "p1"}\n', [], False),
    ('SUBASSEMBLIES = {"a": {"project": "p1"}, **MORE}\n', ["p1"], False),
    ('SUBASSEMBLIES = {"a": {"project": "p1"}}\nSUBASSEMBLIES["b"] = make()\n', ["p1"], False),
    ('SUBASSEMBLIES = {"a": {"project": "p1"}}\nSUBASSEMBLIES.update(b={"project": "p2"})\n', ["p1"], False),
    ('SUBASSEMBLIES = {"a": {"project": "p1"}}\nSUBASSEMBLIES |= more()\n', ["p1"], False),
    ("from elsewhere import SUBASSEMBLIES\n", [], False),
    ("SUBASSEMBLIES = make()\n", [], False),
    ("SUBASSEMBLIES = {\n", [], False),                                                           # unreadable
])
def test_the_projects_a_design_links_are_read_from_its_source_and_a_doubt_is_said(light, src, names, whole):
    d = st.project_dir("par", create=True)
    (d / "assembly.py").write_text(src)
    assert subassembly.static_children(d) == (names, whole)
    assert subassembly.static_children(light / "nobody") == ([], True)                           # no assembly.py: nothing linked


def test_a_run_that_loaded_a_project_the_hashes_miss_cannot_pass(approved):
    (st.project_dir("machine") / "assembly.py").write_text(
        machine('{"gantry": {"project": "gan" + "try", "at": [0, 0, 20], "turn": [0, 0, 90]}}'))
    assert subassembly.tree_projects(st.project_dir("machine")) == ([], False)
    rec = verify.run("machine", fresh=True, mode="test")
    assert rec["verdict"] == "UNCHECKED" and not [r for r in rec["rows"] if r["state"] == "FAIL"]
    assert "loaded gantry, which assembly.py's source does not name as a plain string" in " ".join(rec["notes"])
    assert verify.status("machine")["done"] is False


def test_a_parents_verify_never_reads_a_childs_verify_or_checks_and_a_failing_child_fails_it(approved, monkeypatch):
    child = st.project_dir("gantry")
    (child / "spec.toml").write_text("[envelope]\nmax_mm = [1, 1, 1]\n")          # it fails its own spec
    (child / "verify.json").write_text(json.dumps({"project": "gantry", "verdict": "PASS"}))     # and says it passes
    (child / "checks.json").write_text("not json at all")
    looked = []
    for owner, name in ((verify, "status"), (st, "read_checks")):
        real = getattr(owner, name)
        monkeypatch.setattr(owner, name, lambda slug, *a, _real=real, _name=name: (looked.append((_name, slug)), _real(slug, *a))[1])
    rec = verify.run("machine", fresh=True, mode="test")
    assert rec["verdict"] == "FAIL"
    (bad,) = [r for r in rec["rows"] if r["state"] == "FAIL"]
    assert (bad["check"], bad["rule"]) == ("gantry:spec", "spec/envelope") and bad["subject"] == "assembly"
    assert not [seen for seen in looked if seen[1] == "gantry"]
    assert (child / "checks.json").read_text() == "not json at all"              # nor did it write them
    assert json.loads((child / "verify.json").read_text())["verdict"] == "PASS"


def test_git_answers_for_every_child_and_a_child_outside_a_repo_is_not_committed(approved):
    root = approved
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "the machine")
    info = verify.git_info(root / "machine")
    assert info["dirty"] is False and set(info["children"]) == {"gantry"}
    assert info["children"]["gantry"]["commit"] == info["commit"] and info["children"]["gantry"]["path"] == "gantry"
    rec = verify.run("machine", fresh=True, mode="test")
    assert rec["git"]["children"]["gantry"]["tree"] and verify.status("machine")["done"] is True
    block = root / "gantry" / "parts" / "block.py"
    block.write_text(block.read_text() + "# edit\n")
    info = verify.git_info(root / "machine")
    assert info["dirty"] is True and info["uncommitted"] == ["gantry/parts/block.py"]
    assert info["children"]["gantry"]["dirty"] is True and info["children"]["gantry"]["uncommitted"] == ["gantry/parts/block.py"]
    (root / "gantry" / "out" / "x.png").write_bytes(b"x")                         # a run's output is no change
    assert verify.git_info(root / "machine")["uncommitted"] == ["gantry/parts/block.py"]
    assert verify.run("machine", fresh=True, mode="test")["git"]["dirty"] is True  # a verdict on uncommitted work is said so
    s = verify.status("machine")
    assert s["done"] is False and any("uncommitted" in r for r in s["reasons"])
    git(root, "commit", "-q", "-am", "edit the child")
    verify.run("machine", fresh=True, mode="test")
    assert verify.status("machine")["done"] is True


def test_a_child_with_a_repository_of_its_own_is_named_in_the_parents_list(approved):
    for name in ("machine", "gantry"):
        git(approved / name, "init", "-q", "-b", "main")
        git(approved / name, "add", "-A")
        git(approved / name, "commit", "-q", "-m", name)
    clean = verify.git_info(approved / "machine")
    assert clean["dirty"] is False and clean["children"]["gantry"]["commit"] != clean["commit"]
    block = approved / "gantry" / "parts" / "block.py"
    block.write_text(block.read_text() + "# edit\n")
    info = verify.git_info(approved / "machine")
    assert info["dirty"] is True and info["uncommitted"] == ["gantry/parts/block.py"]       # its own repo's path, under its name
    assert info["children"]["gantry"]["uncommitted"] == ["parts/block.py"]


def test_a_child_outside_the_repo_or_gone_counts_as_uncommitted_and_says_so(approved):
    git(approved / "machine", "init", "-q", "-b", "main")                         # only the parent is in a repo
    git(approved / "machine", "add", "-A")
    git(approved / "machine", "commit", "-q", "-m", "machine")
    info = verify.git_info(approved / "machine")
    assert info["dirty"] is True and info["children"] == {"gantry": None}
    assert info["uncommitted"] == ["gantry: not in a git repository"]
    import shutil
    shutil.rmtree(approved / "gantry")
    assert verify.git_info(approved / "machine")["uncommitted"] == ["gantry: no such project"]


# ─── The parent's check runs every gate of every project in the tree ─────────

def key(row):
    return (row["check"], row["rule"], row["subject"], row["state"], row["measured"], row["limit"], row["source"])


def test_the_childs_rows_in_the_parents_check_are_the_ones_its_own_check_gives(approved):
    parent = check_all("machine")
    own = check_all("gantry")
    from_child = [r for r in parent["rows"] if r["check"].startswith("gantry:")]
    assert from_child and [key({**r, "check": r["check"].split(":", 1)[1]}) for r in from_child] == [key(r) for r in own["rows"]]
    assert {r["check"] for r in from_child} >= {"gantry:geometry", "gantry:fit", "gantry:sweep", "gantry:spec", "gantry:visual"}
    assert parent["tree"]["projects"] == ["gantry"] and parent["tree"]["subassemblies"][0]["bodies"] == 2
    assert "tree" not in own and parent["summary"]["parts_built"] == 1             # the child's parts are not the parent's
    assert any(r["artifacts"] for r in own["rows"]) and not any(r["artifacts"] for r in from_child)   # its renders are in its folder
    assert json.loads((st.project_dir("machine") / "checks.json").read_text())["tree"] == parent["tree"]


def test_a_child_that_fails_its_own_gates_fails_the_parent_whatever_the_parent_says(approved):
    child = st.project_dir("gantry")
    (child / "spec.toml").write_text(GANTRY_SPEC + '\n[[mass]]\nparts = { block = 1 }\nmax_g = 1\n')
    (child / "parts" / "spare.py").write_text(BLOCK.replace("return", "raise ValueError('no wall')\n    return"))
    rows = check_all("machine")["rows"]
    bad = {(r["check"], r["rule"], r["subject"]) for r in rows if r["state"] == "FAIL"}
    assert bad == {("gantry:spec", "spec/mass", "block"), ("gantry:build", "build", "spare")}
    assert [r["measured"] for r in rows if r["check"] == "gantry:build"] == ["ValueError: no wall"]


def test_two_instances_of_a_project_run_its_gates_once(light):
    write("gantry", GANTRY, {"plate": PLATE, "block": BLOCK}, spec=GANTRY_SPEC)
    write("machine", machine('{"left": {"project": "gantry", "at": [-50, 0, 0]}, "right": {"project": "gantry", "at": [50, 0, 0]}}'),
          {"plate": PLATE})
    rows = check_all("machine")["rows"]
    assert len([r for r in rows if r["check"] == "gantry:spec"]) == 1
    assert len([r for r in rows if r["check"] == "subassembly" and r["rule"] == "linked"]) == 2
    assert len([r for r in rows if r["check"] == "sweep" and r["rule"] == "sweep/left/x"]) == 1
    assert [r for r in rows if r["check"] == "sweep" and r["rule"] == "sweep/right/x"]


# ─── The build cache: an edit to a child is a miss ───────────────────────────

def parts_got(data, how):
    return sorted(b["part"] for b in data["builds"] if b["how"] == how)


def test_a_child_edit_misses_the_cache_and_the_parent_sees_the_new_geometry(tree, capsys):
    buildcache.forget()
    ask = ("measure", "machine", "gantry/block", "plate", "--posed")
    code, first = run(capsys, *ask)
    assert first["min_distance_mm"] == pytest.approx(71.0)             # the block's underside, 23 up, over the plate's top, -48
    assert parts_got(first, "built") == ["block", "plate", "plate"] and parts_got(first, "cache") == []
    code, second = run(capsys, *ask)
    assert parts_got(second, "built") == [] and parts_got(second, "cache") == ["block", "plate", "plate"]
    assert second["min_distance_mm"] == first["min_distance_mm"]
    (st.project_dir("gantry") / "parts" / "block.py").write_text(BLOCK.replace('"size": 10.0', '"size": 14.0'))
    code, third = run(capsys, *ask)
    assert parts_got(third, "built") == ["block"] and parts_got(third, "cache") == ["plate", "plate"]
    assert third["min_distance_mm"] == pytest.approx(69.0)             # the block is 2 mm taller each way: the new geometry
    code, scene = run(capsys, "scene", "machine")
    assert parts_got(scene, "built") == [] and "gantry/block" in scene["bodies"]      # and the edit was kept for the next command
    assert sorted(p.name for p in buildcache.cache_dir(st.project_dir("gantry")).glob("*.part"))   # in the child's own cache


def test_checking_the_parent_after_a_child_edit_reads_the_new_geometry(tree, capsys):
    buildcache.forget()
    (tree / "machine" / "spec.toml").write_text('[[size]]\nbody = "gantry/block"\nmax_mm = [20, 20, 20]\n')
    sizes = lambda data: [r["measured"] for r in data["rows"] if r["rule"] == "spec/size"]
    code, first = run(capsys, "check", "machine", "--all")
    assert sizes(first) == ["10.0 x 10.0 x 10.0 mm"] and parts_got(first, "built") == ["block", "plate", "plate"]
    code, second = run(capsys, "check", "machine", "--all")
    assert sizes(second) == sizes(first) and parts_got(second, "built") == [] and parts_got(second, "cache") == ["block", "plate", "plate"]
    (tree / "gantry" / "parts" / "block.py").write_text(BLOCK.replace('"size": 10.0', '"size": 14.0'))
    code, third = run(capsys, "check", "machine", "--all")
    assert sizes(third) == ["14.0 x 14.0 x 14.0 mm"] and parts_got(third, "built") == ["block"]
    code, fresh = run(capsys, "check", "machine", "--all", "--no-cache")               # a run that trusts no cache says the same
    assert [key(r) for r in fresh["rows"]] == [key(r) for r in third["rows"]]
    assert parts_got(fresh, "built") == ["block", "plate", "plate"]


def test_a_part_that_runs_a_childs_files_is_keyed_by_them_and_the_rest_is_not(tree):
    buildcache.forget()
    machine_dir, child = st.project_dir("machine"), st.project_dir("gantry")
    (machine_dir / "parts" / "bracket.py").write_text(
        BLOCK + "\nfrom cad_agent.state import build_part\n\nOTHER = build_part('gantry', 'block')\n")
    (machine_dir / "parts" / "plain.py").write_text(BLOCK)
    stranger = write("stranger", GANTRY, {"plate": PLATE, "block": BLOCK})          # a project nothing links
    keys = lambda: {n: buildcache.key(machine_dir, n) for n in ("bracket", "plain", "plate")}
    before = keys()
    (child / "parts" / "block.py").write_text(BLOCK + "# edit\n")
    after = keys()
    assert after["bracket"] != before["bracket"]                                    # it builds from the child's block
    assert after["plain"] == before["plain"] and after["plate"] == before["plate"]  # these do not
    (child / "checks.json").write_text("{}")
    (child / "out").mkdir(exist_ok=True)
    (child / "out" / "x.png").write_bytes(b"x")
    (stranger / "parts" / "block.py").write_text(BLOCK + "# edit\n")
    assert keys() == after                                                           # outputs, and a project not linked, are no input
    (child / "assembly.py").write_text(GANTRY + "# edit\n")
    assert keys()["bracket"] != after["bracket"]


def test_the_workbench_watches_a_childs_files_for_the_parent(tree):
    bench = serve.Bench([tree], runner=inproc)
    before = bench._design_sig(tree / "machine")
    assert bench._design_sig(tree / "gantry") != before                              # its own watch is its own
    (tree / "gantry" / "parts" / "block.py").write_text(BLOCK + "# edit\n")
    assert bench._design_sig(tree / "machine") != before                             # a child's edit is the machine's
    again = bench._design_sig(tree / "machine")
    (tree / "gantry" / "checks.json").write_text("{}")
    assert bench._design_sig(tree / "machine") == again


# ─── "/" in a name: every command takes it or refuses it cleanly ─────────────

CHILD_BODY = "gantry/plate"


def paths_under(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def stray(before, after):
    """New folders or files that a child's body name made: the name as a path under a project's own folders."""
    return sorted(p for p in after - before
                  if "gantry" in Path(p).parts[1:] or "gantry" in Path(p).name.split("_") or Path(p).name.startswith("gantry"))


@pytest.mark.parametrize("argv", [
    ["build", "machine", CHILD_BODY],
    ["render", "machine", CHILD_BODY],
    ["export", "machine", CHILD_BODY],
    ["export", "machine", CHILD_BODY, "--format", "step"],
    ["export", "machine", CHILD_BODY, "--format", "stl"],
    ["set", "machine", CHILD_BODY, "thickness=5"],
    ["check", "machine", "--part", CHILD_BODY],
    ["approve", "machine", "--part", CHILD_BODY],
    ["measure", "machine", CHILD_BODY, "plate"],            # without --posed the names are part modules
    ["check", CHILD_BODY],                                  # where a project goes
    ["ls", CHILD_BODY],
    ["status", CHILD_BODY],
    ["bom", CHILD_BODY],
    ["shop", CHILD_BODY],
    ["place", CHILD_BODY, "plate", "--by=1,0,0"],
    ["gui", "select", "machine", "gantry/nope"],
])
def test_a_command_that_takes_a_part_module_or_a_project_refuses_a_childs_body_name_cleanly(tree, capsys, argv):
    before = paths_under(tree)
    code, data = run(capsys, *argv)
    assert code == cli.USAGE and data["error"]                                       # 3, with a message; never 4
    after = paths_under(tree)
    assert stray(before, after) == []
    assert not [p for p in after - before if not p.startswith((".cad", "machine/.cad", "gantry/.cad"))]    # it wrote nothing at all


def test_a_refusal_names_the_modules_there_are_and_the_log_keeps_the_name(tree, capsys):
    code, data = run(capsys, "export", "machine", CHILD_BODY)
    assert "no part 'gantry/plate' in machine (parts: plate)" in data["error"]
    entries = log_lines(tree / "machine")
    assert entries[-1]["cmd"] == "export" and entries[-1]["argv"][-1] == CHILD_BODY and entries[-1]["exit"] == cli.USAGE
    code, data = run(capsys, "check", CHILD_BODY)                                    # no project to log into: the root's log
    assert code == cli.USAGE and log_lines(tree)[-1]["argv"] == ["--json", "check", CHILD_BODY]
    assert not (tree / "gantry" / "gantry").exists() and not (tree / "machine" / "gantry").exists()


def test_the_child_is_asked_for_its_own_parts_and_writes_into_itself(tree, capsys):
    code, data = run(capsys, "export", "gantry", "plate")                            # what the refusals point to
    assert code == cli.OK and data["path"].endswith("gantry/out/plate.step")
    assert (tree / "gantry" / "out" / "plate.step").is_file() and not (tree / "machine" / "out" / "plate.step").exists()


@pytest.mark.parametrize("argv", [
    ["measure", "machine", CHILD_BODY, "plate", "--posed"],
    ["measure", "machine", "gantry/block", CHILD_BODY, "--posed"],
    ["mass", "machine", CHILD_BODY, "gantry/block"],
    ["place", "machine", "gantry/block", "--by=0,1,0"],
    ["place", "machine", "gantry/block", "--reset"],
    ["scene", "machine"],
    ["bom", "machine"],
    ["bom", "machine", "--flat"],
    ["cutlist", "machine"],
    ["render", "machine"],
    ["check", "machine", "--part", "plate"],
    ["page", "machine"],
    ["ls", "machine"],
    ["status", "machine"],
    ["gui", "select", "machine", CHILD_BODY],
    ["gui", "select", "machine", "gantry/plate.Face1", "gantry/block"],
    ["gui", "hide", "machine", CHILD_BODY],
])
def test_a_command_that_takes_a_body_takes_a_childs_and_makes_no_stray_folder(tree, capsys, argv):
    before = paths_under(tree)
    code, data = run(capsys, *argv)
    assert code in (cli.OK, cli.FAIL, cli.UNCHECKED), data                           # a verdict or "no workbench is up", not usage or a crash
    if argv[0] == "gui":
        assert code == cli.UNCHECKED and "workbench" in data["error"]                # the name was accepted; nothing is serving
    assert stray(before, paths_under(tree)) == []


def test_a_childs_body_is_placed_by_its_full_name_in_the_parents_file_and_the_move_is_undone_cleanly(tree, capsys):
    code, data = run(capsys, "place", "machine", "gantry/block", "--by=0,3,0")
    assert code == cli.OK and data["placement"]["move"] == [0.0, 3.0, 0.0]
    text = (tree / "machine" / "placements.toml").read_text()
    assert '["gantry/block"]' in text and not (tree / "gantry" / "placements.toml").exists()
    code, data = run(capsys, "check", "machine", "--all")
    moved = [r for r in data["rows"] if r["check"] == "placements"]
    assert [(r["subject"], r["state"]) for r in moved] == [("gantry/block", "PASS")]
    code, data = run(capsys, "mass", "machine", "gantry/block")
    assert data["bodies"][0]["material"] == "aluminium" and data["default_density"] == []         # the child's material
    assert np.allclose(data["cog"], [0, 3, 28])
    code, data = run(capsys, "undo", "machine")
    assert code == cli.OK and not (tree / "machine" / "placements.toml").exists()
    code, data = run(capsys, "place", "machine", "gantry/ghost", "--by=1,0,0")
    assert code == cli.USAGE and "gantry/block" in data["error"]


def test_a_childs_body_in_a_hand_moved_file_that_names_nobody_is_unchecked_by_name(tree, capsys):
    (tree / "machine" / "placements.toml").write_text('["gantry/ghost"]\nmove = [1.0, 0.0, 0.0]\n')
    code, data = run(capsys, "check", "machine")
    ghost = [r for r in data["rows"] if r["check"] == "placements"]
    assert [(r["subject"], r["state"]) for r in ghost] == [("gantry/ghost", "UNCHECKED")] and code == cli.UNCHECKED


@pytest.fixture()
def served(tree, monkeypatch):
    bench = serve.Bench([tree], runner=inproc)
    scheduled = []
    monkeypatch.setattr(bench, "schedule", lambda slug, kind="check": scheduled.append((slug, kind)))
    srv = serve.make_server(bench, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None):
        req = urllib.request.Request(base + path)
        if body is not None:
            req.data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
            req.add_header("X-CAD", "1")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    yield call, bench, scheduled
    srv.shutdown()
    srv.server_close()


def test_the_scene_hands_the_viewer_a_flat_name_and_the_page_a_childs_own_facts(served, tree):
    call, _, _ = served
    code, scene = call("/api/scene?slug=machine")
    assert code == 200 and {b["name"] for b in scene["bodies"]} == {"plate", "gantry/plate", "gantry/block"}
    ids = {p["id"] for p in scene["viewer"]["shapes"]["parts"]}
    assert ids == {"/Group/plate", "/Group/gantry%2Fplate", "/Group/gantry%2Fblock"}      # no group of the viewer's own
    assert all(b["path"] in ids for b in scene["bodies"])
    child = next(b for b in scene["bodies"] if b["name"] == "gantry/plate")
    assert (child["part"], child["kind"], child["material"], child["project"], child["from_part"]) == (
        None, "made", "petg", "gantry", "plate")
    assert child["params"] == {} and child["mass_g"] > 0 and child["used_by"] == []     # the parameters are the child's to edit
    own = next(b for b in scene["bodies"] if b["name"] == "plate")
    assert own["part"] == "plate" and "project" not in own and own["params"]["thickness"]["editable"] is True
    assert [a["name"] for a in scene["axes"]] == ["gantry/x"] and scene["axes"][0]["moves"] == ["gantry/block"]
    assert scene["source_hash"] == verify.source_hash(tree / "machine")[0]


def test_the_scene_follows_an_edit_to_a_child(served, tree):
    call, _, _ = served
    first = call("/api/scene?slug=machine")[1]
    (tree / "gantry" / "parts" / "block.py").write_text(BLOCK.replace('"size": 10.0', '"size": 14.0'))
    again = call("/api/scene?slug=machine")[1]
    assert again["source_hash"] != first["source_hash"]
    old, new = (next(b for b in s["bodies"] if b["name"] == "gantry/block")["bbox"] for s in (first, again))
    assert new[1][2] - new[0][2] == pytest.approx(14.0) and old[1][2] - old[0][2] == pytest.approx(10.0)


def test_the_page_moves_measures_and_weighs_a_childs_body_through_the_cli(served, tree):
    call, _, scheduled = served
    code, r = call("/api/place", {"slug": "machine", "body": "gantry/block", "move": [0, 3, 0], "turn": [0, 0, 0],
                                  "about": [0, 0, 28]})
    assert code == 200 and r["exit"] == cli.OK and scheduled == [("machine", "check")]
    assert placements.load(tree / "machine")["gantry/block"]["move"] == (0.0, 3.0, 0.0)
    assert '["gantry/block"]' in (tree / "machine" / "placements.toml").read_text()
    block = next(b for b in call("/api/scene?slug=machine")[1]["bodies"] if b["name"] == "gantry/block")
    assert block["placement"]["move"] == [0.0, 3.0, 0.0]
    code, r = call("/api/measure", {"slug": "machine", "a": "gantry/block", "b": "plate"})
    assert r["exit"] == cli.OK and r["data"]["min_distance_mm"] == pytest.approx(71.0)
    code, r = call("/api/mass", {"slug": "machine", "bodies": ["gantry/plate"]})
    assert r["exit"] == cli.OK and r["data"]["bodies"][0]["material"] == "petg" and r["data"]["default_density"] == []
    code, r = call("/api/place", {"slug": "machine", "body": "gantry/block", "reset": True})
    assert r["exit"] == cli.OK and not (tree / "machine" / "placements.toml").exists()
    log = (tree / "machine" / ".cad" / "log.jsonl").read_text()
    assert '"gantry/block"' in log                                                       # the page's moves are in the activity log


@pytest.mark.parametrize("path,body", [
    ("/api/set", {"part": CHILD_BODY, "values": {"thickness": 5}}),
    ("/api/export", {"part": CHILD_BODY, "format": "step"}),
    ("/api/approve", {"part": CHILD_BODY}),
    ("/api/place", {"body": "gantry/ghost", "reset": True}),
])
def test_the_page_asking_for_a_childs_part_gets_a_usage_answer_not_a_server_error(served, path, body):
    call, _, _ = served
    code, r = call(path, {"slug": "machine", **body})
    assert code == 200 and r["exit"] == cli.USAGE and r["data"]["error"]


def test_a_name_is_never_a_path_to_the_server(served, tree, monkeypatch):
    call, _, _ = served
    for rel in ("out/gantry/plate_iso.png", "../gantry/assembly.py", "out/../../gantry/assembly.py",
                "out%2F..%2F..%2Fgantry%2Fassembly.py", "baseline/gantry%2Fplate_iso.png"):
        code, r = call("/api/file?slug=machine&path=" + rel)
        assert code == 404, rel
    opened = []
    monkeypatch.setattr(serve.subprocess, "Popen", lambda cmd, **kw: opened.append(cmd))
    code, r = call("/api/reveal", {"slug": "machine", "part": CHILD_BODY})
    assert code == 200 and r["revealed"] == str(tree / "machine") and len(opened) == 1       # the project, not a path from the name
    code, r = call("/api/reveal", {"slug": "machine", "part": "plate"})
    assert r["revealed"].endswith("machine/parts/plate.py")


def test_the_page_selects_and_hides_a_childs_body_by_its_name(served):
    call, _, _ = served
    code, r = call("/api/gui/do", {"slug": "machine", "cmd": "select", "args": [CHILD_BODY, "gantry/block.Face2"]})
    assert code == 200 and r["ok"] is True
    code, r = call("/api/gui/do", {"slug": "machine", "cmd": "hide", "args": ["gantry/block"]})
    assert code == 200
    code, state = call("/api/gui?slug=machine")
    assert state["selected"] == [CHILD_BODY, "gantry/block.Face2"] and state["hidden"] == ["gantry/block"]


# ─── What the other rules and commands make of a sub-assembly ────────────────

def test_the_centre_of_mass_rule_moves_it_along_the_axis_as_the_instance_turned_it(tree):
    from cad_agent.ruleset.com import com
    add_motor(120)
    ctx = actx("machine")
    infos = ctx.machine.bodies
    assert all(i.mass_g for i in infos.values())                                     # a mass for every body, so the rule judges
    rows = {r.rule: r for r in com(ctx)}
    assert rows["centre of mass"].state == "PASS" and rows["centre of mass/gantry/x"].state == "PASS"
    total = sum(i.mass_g for i in infos.values())
    share = infos["gantry/block"].mass_g / total
    # the centre of mass is on the plate's centre line; x turned a quarter runs along y, where the plate is 10 either side
    assert f"closest {10 - share * 10:.1f} mm from its edge" in rows["centre of mass/gantry/x"].measured
    assert f"({share * 100:.0f}% of the mass moves)" in rows["centre of mass/gantry/x"].measured


def test_a_mass_budget_over_everything_a_lifted_axis_moves_weighs_the_prefixed_bodies(tree):
    add_motor(120)
    write("gantry", (st.project_dir("gantry") / "assembly.py").read_text().replace(
        '"moves": ("block",)', '"moves": ("block", "motor")'), {"plate": PLATE, "block": BLOCK})
    mass = lambda text: only(spec_rows("machine", text))
    loose = mass('[[mass]]\nmoving = "gantry/x"\nmax_g = 200\n')
    assert loose.state == "PASS" and "gantry/block" in loose.measured and "gantry/motor 120.0 g" in loose.measured
    assert mass('[[mass]]\nmoving = "gantry/x"\nmax_g = 100\n').state == "FAIL"
    assert mass('[[mass]]\nmoving = "x"\nmax_g = 100\n').state == "UNCHECKED"          # the child's name is not the machine's
    assert mass('[[mass]]\nbodies = ["gantry/block", "plate"]\nmax_g = 20\n').state == "PASS"


def test_the_bom_nests_a_sub_assemblys_bodies_under_a_line_of_its_own(tree, capsys):
    code, data = run(capsys, "bom", "machine")
    lines = [(ln["index"], ln["name"], ln["kind"], ln["project"], ln["depth"]) for ln in data["lines"]]
    assert lines == [("1", "plate", "made", "machine", 0), ("2", "gantry", "assembly", "gantry", 0),
                     ("2.1", "plate", "made", "gantry", 1), ("2.2", "block", "made", "gantry", 1)]
    assert data["lines"][0]["shop_files"] == ["plate.step", "plate.3mf", "plate.stl"]       # the parent's own part has files
    assert data["lines"][2]["shop_files"] == [] and data["lines"][2]["file_name"] == "parts/plate.py"
    flat = run(capsys, "bom", "machine", "--flat")[1]
    assert [ln["kind"] for ln in flat["lines"]] == ["made", "assembly"] and flat["totals"]["bodies"] == 3


def test_the_parents_shop_makes_files_for_its_own_parts_only(tree, capsys):
    code, data = run(capsys, "shop", "machine", "--draft")
    assert code in (cli.OK, cli.UNCHECKED), data                                     # a draft of a design nobody verified
    out = tree / "machine" / "out" / "shop"
    assert sorted(p.name for p in out.iterdir()) == ["bom.csv", "bom.json", "manifest.json", "plate.3mf", "plate.step", "plate.stl"]
    manifest = json.loads((out / "manifest.json").read_text())
    assert not [f for f in manifest["files"] if "gantry" in f["path"] or "block" in f["path"]]
    assert manifest["skipped"] == [] and manifest["bom"]["bodies"] == 3                # the BOM counts the child's, the shop does not make them
    bom = json.loads((out / "bom.json").read_text())
    assert [ln["name"] for ln in bom["lines"]] == ["plate", "gantry", "plate", "block"]
    assert not (tree / "gantry" / "out" / "shop").exists()                            # that is the child's shop
