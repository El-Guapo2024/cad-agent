"""The `mechanism` rule: a turning part must be held, a belt on its pulleys and tensioned, an axis guided and driven.

Each test writes a tiny assembly (boxes and cylinders) into a temporary project tree and runs the rule on it.
"""
import pytest

from cad_agent import state as st
from cad_agent.registry import AssemblyCtx
from cad_agent.ruleset.mechanism import mechanism

HEAD = '''from build123d import Box, Cylinder, Pos, Rot
'''

# a shaft along y, 100 long, 10 across, between two blocks at its ends (or not)
SHAFT = HEAD + '''
def parts():
    out = {"shaft": Rot(90, 0, 0) * Cylinder(5, 100)}
    for k, y in (("block_a", -45.0), ("block_b", 45.0)):
        out[k] = Pos(0, y, 0) * (Box(20, 10, 20) - Rot(90, 0, 0) * Cylinder(5, 12))
    return out
'''


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    return tmp_path


def run(slug, assembly):
    d = st.project_dir(slug, create=True)
    (d / "assembly.py").write_text(assembly)
    m = st.load_machine(slug)
    ctx = AssemblyCtx(slug=slug, parts=m.parts, clearance=m.clearance, allow_contact=m.allow_contact,
                      out_dir=None, axes=m.axes, machine=m)
    return {(r.subject, r.rule): r for r in mechanism(ctx)}


def test_a_design_that_declares_no_mechanism_is_not_judged(tree):
    rows = run("plain", SHAFT)
    (row,) = rows.values()
    assert row.state == "N/A" and "declare one" in row.measured


def test_a_shaft_held_at_both_ends_passes(tree):
    rows = run("held", SHAFT + 'MECHANISM = {"rotating": {"shaft": {"axis": (0, 1, 0), "supports": ["block_a", "block_b"]}}}\n')
    assert rows[("shaft", "mechanism/supported")].state == "PASS"


def test_a_shaft_held_by_nothing_fails(tree):
    rows = run("float", SHAFT + 'MECHANISM = {"rotating": {"shaft": {"axis": (0, 1, 0), "supports": []}}}\n')
    assert rows[("shaft", "mechanism/supported")].state == "FAIL"


def test_a_shaft_held_at_one_spot_wobbles(tree):
    rows = run("one", SHAFT + 'MECHANISM = {"rotating": {"shaft": {"axis": (0, 1, 0), "supports": ["block_a"]}}}\n')
    r = rows[("shaft", "mechanism/supported")]
    assert r.state == "FAIL" and "wobble" in r.measured


def test_a_support_through_a_clearance_hole_does_not_hold(tree):
    loose = SHAFT.replace("Cylinder(5, 12)", "Cylinder(8, 12)")              # a 16 bore on a 10 shaft
    rows = run("loose", loose + 'MECHANISM = {"rotating": {"shaft": {"axis": (0, 1, 0), "supports": ["block_a", "block_b"]}}}\n')
    r = rows[("shaft", "mechanism/supported")]
    assert r.state == "FAIL" and "3.00 mm away" in r.measured


def test_an_undeclared_part_named_like_it_turns_fails_and_its_holder_does_not(tree):
    src = SHAFT.replace('"shaft"', '"lead_screw"').replace('block_a', 'screw_block_a')
    rows = run("undeclared", src + 'MECHANISM = {}\n')
    assert rows[("lead_screw", "mechanism/declared")].state == "FAIL"
    assert ("screw_block_a", "mechanism/declared") not in rows


def test_a_belt_without_a_tensioner_fails(tree):
    src = HEAD + '''
def parts():
    return {"belt": Box(10, 2, 10), "p1": Pos(0, 1.5, 0) * Box(4, 1, 4), "p2": Pos(0, -1.5, 0) * Box(4, 1, 4),
            "axle1": Pos(0, 3, 0) * Box(2, 1, 2), "axle2": Pos(0, -3, 0) * Box(2, 1, 2)}
MECHANISM = {"rotating": {"p1": {"axis": (0, 1, 0), "supports": ["axle1"], "cantilever": True},
                          "p2": {"axis": (0, 1, 0), "supports": ["axle2"], "cantilever": True}},
             "belts": {"belt": {"pulleys": ["p1", "p2"]}}}
'''
    rows = run("belt", src)
    assert rows[("belt", "mechanism/belt")].state == "PASS"
    assert rows[("belt", "mechanism/tension")].state == "FAIL"


AXIS = HEAD + '''
def parts():
    return {"rail": Box(100, 10, 5), "carriage": Pos(0, 0, 5) * Box(20, 10, 5),
            "screw": Pos(0, 20, 5) * Rot(0, 90, 0) * Cylinder(3, 100), "motor": Pos(60, 20, 5) * Box(10, 10, 10)}
AXES = {"x": {"moves": ("carriage",), "direction": (1, 0, 0), "travel": (-30.0, 30.0)}}
'''


def test_an_axis_whose_drive_reaches_nothing_it_moves_fails(tree):
    rows = run("axis", AXIS + 'MECHANISM = {"rotating": {"screw": {"axis": (1, 0, 0), "supports": ["motor"], "cantilever": True}}, '
                              '"axes": {"x": {"guides": [["carriage", "rail"]], "drive": "screw", "actuator": "motor"}}}\n')
    assert rows[("axis x", "mechanism/guided")].state == "PASS"
    d = rows[("axis x", "mechanism/driven")]
    assert d.state == "FAIL" and "pushes nothing" in d.measured
    assert rows[("axis x", "mechanism/actuated")].state == "PASS"


def test_an_axis_with_no_declaration_fails(tree):
    rows = run("bare", AXIS + 'MECHANISM = {"static": {"screw": "a tie rod"}}\n')
    assert rows[("axis x", "mechanism/axis")].state == "FAIL"
