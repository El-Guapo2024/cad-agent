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
