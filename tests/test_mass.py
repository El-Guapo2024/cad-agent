"""[[mass]] over bodies and axes, and the `com` rule: the centre of mass over the footprint.

Both start from what a body weighs (bodies.py): a made body volume x density, a bought body what it
declares with a source, a stock body nothing. The spec kind is tried on a small machine that is built here as
a project, so the bodies are described the way a run describes them; the rule is tried on bodies made by
hand with the masses the test gives them, so that each design is only the geometry the case is about.
"""
import json
import math
import re
import textwrap
from pathlib import Path

import pytest
from build123d import Box, Cylinder, Pos, Rot, export_step

from cad_agent import registry as reg
from cad_agent import rules  # noqa: F401  (imports the rules: that registers them)
from cad_agent import state as st
from cad_agent.bodies import Assembly, BodyInfo
from cad_agent.motion import Axis
from cad_agent.registry import AssemblyCtx
from cad_agent.ruleset import com as comrule
from cad_agent.ruleset.com import com
from cad_agent.runner import check_all
from cad_agent.spec import check_spec

SLUG = "mach"

PLATE = textwrap.dedent('''\
    """A plate: 40 x 30 x 4 mm of PETG is 6.096 g."""
    from build123d import Box

    MATERIAL = "petg"
    PROCESS = "fdm"
    MIN_FEATURE_MM = 1.2
    PARAMS = {}


    def build():
        return Box(40, 30, 4)
''')

BLOCK = textwrap.dedent('''\
    """A block: 10 mm cube of aluminium is 2.7 g."""
    from build123d import Box

    MATERIAL = "aluminium"
    PROCESS = "cnc"
    MIN_FEATURE_MM = 2.0
    PARAMS = {}


    def build():
        return Box(10, 10, 10)
''')

NO_MATERIAL = textwrap.dedent('''\
    """A part that never says what it is made of."""
    from build123d import Box

    PROCESS = "cnc"
    PARAMS = {}


    def build():
        return Box(5, 5, 5)
''')

SENSOR = textwrap.dedent('''\
    """A sensor, measured."""
    from build123d import Box

    SOURCE = "datasheet p.2"
    VERIFIED = True
    MASS_G = 4.5
    MASS_SOURCE = "datasheet p.2, weight"
    PARAMS = {}


    def build():
        return Box(6, 6, 2)
''')

ASSEMBLY = textwrap.dedent('''\
    from build123d import Box, Cylinder, Pos
    from cad_agent.state import build_part, bought_solid

    SLUG = "mach"
    AXES = {
        "x": {"moves": ("plate", "block_left"), "direction": (1, 0, 0), "travel": (-50.0, 50.0)},
        "y": {"moves": ("motor_a",), "direction": (0, 1, 0), "travel": (0.0, 20.0)},
    }


    def parts():
        plate, _ = build_part(SLUG, "plate")
        block, _ = build_part(SLUG, "block")
        return {
            "plate": plate,
            "block_left": Pos(30, 0, 0) * block,
            "block_right": Pos(-30, 0, 0) * (block - Cylinder(1.5, 12)),
            "motor_a": Pos(0, 40, 0) * bought_solid(SLUG, "motor"),
            "sensor": Pos(0, 0, 30) * bought_solid(SLUG, "sensor"),
            "rail": Pos(0, 0, -20) * Box(100, 10, 10),
        }
''')

MOTOR_SIDECAR = {"source": "vendor drawing 12", "vendor": "Motors Inc", "verified": True,
                 "mass_g": 280, "mass_source": "datasheet table 2", "material": "steel"}


@pytest.fixture()
def mach(tmp_path, monkeypatch):
    """plate (6.1 g), block_left and block_right (2.7 g and 2.5 g: it has a hole), motor_a (280 g declared),
    sensor (4.5 g declared) and a stock rail with no mass at all."""
    monkeypatch.setattr(st, "ROOT", tmp_path)
    d = st.project_dir(SLUG, create=True)
    (d / "parts" / "plate.py").write_text(PLATE)
    (d / "parts" / "block.py").write_text(BLOCK)
    (d / "bought" / "sensor.py").write_text(SENSOR)
    export_step(Box(20, 20, 30), str(d / "bought" / "motor.step"))
    (d / "bought" / "motor.json").write_text(json.dumps(MOTOR_SIDECAR))
    (d / "assembly.py").write_text(ASSEMBLY)
    return d


def spec(d, text, machine=True):
    """The spec's rows for the machine, loaded the way a run loads it (or with no machine, as a bare caller)."""
    (d / "spec.toml").write_text(text)
    with st.reusing_builds():
        m = st.load_machine(SLUG)
    return list(check_spec(SLUG, m.parts, machine=m if machine else None))


def one(d, text, **kw):
    (r,) = [r for r in spec(d, text, **kw) if r.rule == "spec/mass"]
    return r


def fields(r):
    return r.subject, r.rule, r.state, r.measured, r.limit, r.source


# ─── parts = {...}: the form that was there before step 6 ────────────────────

def test_parts_rows_are_what_they_always_were(mach):
    assert fields(one(mach, '[[mass]]\nparts = { plate = 2 }\nmax_g = 30\n')) == (
        "plate", "spec/mass", "PASS", "12.2 g (plate x2 12.2 g)", "<= 30 g", "spec.toml [[mass]] #1")
    assert fields(one(mach, '[[mass]]\nparts = { plate = 1, block = 2 }\nmax_g = 11.4\n')) == (
        "plate, block", "spec/mass", "FAIL", "11.5 g (plate x1 6.1 g; block x2 5.4 g)", "<= 11.4 g", "spec.toml [[mass]] #1")
    assert one(mach, '[[mass]]\nparts = { plate = 2 }\nmax_g = 12.192\n').state == "PASS"        # on the limit passes
    assert one(mach, '[[mass]]\nparts = { plate = 2 }\nmax_g = 12.19\n').state == "FAIL"


@pytest.mark.parametrize("body, says", [
    ("parts = { ghost = 1 }\nmax_g = 20\n", "no part module 'ghost' (parts: block, plate)"),
    ("parts = { plate = 1 }\n", "[[mass]] is missing `max_g`"),
    ("parts = []\nmax_g = 20\n", "`parts` must map part names to counts, e.g. { x_carriage = 1 }"),
    ("parts = {}\nmax_g = 20\n", "`parts` must map part names to counts, e.g. { x_carriage = 1 }"),
    ("max_g = 20\n", "[[mass]] is missing `parts`, `bodies` or `moving`"),
    ("", "[[mass]] is missing `parts`, `bodies` or `moving`"),
])
def test_an_entry_that_cannot_be_judged_is_one_unchecked_row(mach, body, says):
    got = [r for r in spec(mach, "[[mass]]\n" + body)]
    assert [(r.subject, r.state, r.measured) for r in got] == [("[[mass]] #1", "UNCHECKED", says)]


def test_a_part_with_no_material_has_no_mass_in_the_parts_form(mach):
    (mach / "parts" / "block.py").write_text(NO_MATERIAL)
    r = one(mach, '[[mass]]\nparts = { block = 1 }\nmax_g = 20\n')
    assert (r.subject, r.state, r.measured) == ("[[mass]] #1", "UNCHECKED", "block declares no MATERIAL, so its mass is unknown")


def test_an_entry_takes_one_form_only(mach):
    r = spec(mach, '[[mass]]\nparts = { plate = 1 }\nbodies = ["plate"]\nmax_g = 20\n')[0]
    assert r.state == "UNCHECKED" and r.measured == "[[mass]] takes one of `parts`, `bodies` or `moving`, and this one has parts and bodies"
    r = spec(mach, '[[mass]]\nbodies = ["plate"]\nmoving = "x"\nparts = { plate = 1 }\nmax_g = 20\n')[0]
    assert r.measured.endswith("and this one has parts and bodies and moving")


# ─── bodies = [...] ──────────────────────────────────────────────────────────

def test_bodies_weigh_what_assembly_py_holds_made_by_volume_and_bought_as_declared(mach):
    r = one(mach, '[[mass]]\nbodies = ["plate", "block_left", "motor_a"]\nmax_g = 300\n')
    assert fields(r) == ("plate, block_left, motor_a", "spec/mass", "PASS",
                         "288.8 g (plate 6.1 g; block_left 2.7 g; motor_a 280.0 g (datasheet table 2))", "<= 300 g",
                         "spec.toml [[mass]] #1")
    assert one(mach, '[[mass]]\nbodies = ["plate", "block_left", "motor_a"]\nmax_g = 288\n').state == "FAIL"
    assert one(mach, '[[mass]]\nbodies = ["sensor"]\nmax_g = 4.5\n').measured == "4.5 g (sensor 4.5 g (datasheet p.2, weight))"


def test_a_part_cut_in_assembly_py_weighs_what_is_left(mach):
    # block_right is the block with a 3 mm hole through it; the part module still says 2.7 g
    assert one(mach, '[[mass]]\nbodies = ["block_right"]\nmax_g = 10\n').measured == "2.5 g (block_right 2.5 g)"
    assert one(mach, '[[mass]]\nparts = { block = 1 }\nmax_g = 10\n').measured == "2.7 g (block x1 2.7 g)"


def test_a_stock_body_has_no_mass_so_the_entry_is_unchecked_and_says_which_and_why(mach):
    r = one(mach, '[[mass]]\nbodies = ["plate", "rail"]\nmax_g = 500\n')
    assert (r.subject, r.state) == ("plate, rail", "UNCHECKED")
    assert r.measured.startswith("no mass for rail (assembly.py builds it itself, so it has no material or declared mass; "
                                 "make it a part module with a MATERIAL, or a bought part with mass_g and mass_source)")
    assert r.measured.endswith("; the others weigh 6.1 g (plate 6.1 g)") and r.limit == "<= 500 g"


def test_a_bought_mass_with_no_source_is_not_a_mass(mach):
    side = {k: v for k, v in MOTOR_SIDECAR.items() if k != "mass_source"}
    (mach / "bought" / "motor.json").write_text(json.dumps(side))
    r = one(mach, '[[mass]]\nbodies = ["motor_a", "plate"]\nmax_g = 500\n')
    assert r.state == "UNCHECKED" and "no mass for motor_a (mass_g is declared without a mass_source" in r.measured


def test_a_bought_part_that_declares_nothing_says_so(mach):
    (mach / "bought" / "motor.json").write_text(json.dumps({"source": "vendor drawing 12", "verified": True}))
    r = one(mach, '[[mass]]\nbodies = ["motor_a"]\nmax_g = 500\n')
    assert r.state == "UNCHECKED" and "no mass for motor_a (bought part 'motor' declares no mass_g with a mass_source)" in r.measured
    assert r.measured.endswith("; the others weigh 0.0 g (none)")


def test_a_part_with_no_material_and_one_with_an_unknown_material_say_why(mach):
    (mach / "parts" / "block.py").write_text(NO_MATERIAL)
    r = one(mach, '[[mass]]\nbodies = ["block_left"]\nmax_g = 20\n')
    assert r.state == "UNCHECKED" and "block_left (parts/block.py declares no MATERIAL, so its mass is unknown)" in r.measured
    (mach / "parts" / "block.py").write_text(BLOCK.replace('"aluminium"', '"unobtainium"'))
    assert "has no density in materials.py" in one(mach, '[[mass]]\nbodies = ["block_left"]\nmax_g = 20\n').measured


def test_a_budget_the_known_bodies_already_blow_fails_whatever_the_rest_weigh(mach):
    r = one(mach, '[[mass]]\nbodies = ["motor_a", "rail"]\nmax_g = 100\n')
    assert r.state == "FAIL" and r.measured.startswith("280.0 g already, before the bodies of unknown mass "
                                                       "(motor_a 280.0 g (datasheet table 2)); no mass for rail (")
    assert one(mach, '[[mass]]\nbodies = ["motor_a", "rail"]\nmax_g = 300\n').state == "UNCHECKED"   # it might still fit


@pytest.mark.parametrize("body, says", [
    ('bodies = ["plate", "ghost"]\nmax_g = 20\n', "no body 'ghost' in the assembly (bodies: "),
    ('bodies = ["plate", "plate"]\nmax_g = 20\n', "`bodies` lists plate more than once, which would weigh it twice"),
    ('bodies = []\nmax_g = 20\n', '`bodies` must list body names, e.g. ["x_carriage", "motor_x"]'),
    ('bodies = "plate"\nmax_g = 20\n', '`bodies` must list body names'),
    ('bodies = [1, 2]\nmax_g = 20\n', '`bodies` must list body names'),
    ('bodies = ["plate"]\n', "[[mass]] is missing `max_g`"),
])
def test_bodies_that_cannot_be_weighed_are_one_unchecked_row(mach, body, says):
    got = spec(mach, "[[mass]]\n" + body)
    assert [(r.subject, r.state) for r in got] == [("[[mass]] #1", "UNCHECKED")] and says in got[0].measured


# ─── moving = "x" ────────────────────────────────────────────────────────────

def test_moving_weighs_every_body_the_axis_moves(mach):
    assert fields(one(mach, '[[mass]]\nmoving = "x"\nmax_g = 10\n')) == (
        "axis x", "spec/mass", "PASS", "8.8 g (plate 6.1 g; block_left 2.7 g)", "<= 10 g", "spec.toml [[mass]] #1")
    assert one(mach, '[[mass]]\nmoving = "x"\nmax_g = 8\n').state == "FAIL"
    assert one(mach, '[[mass]]\nmoving = "y"\nmax_g = 300\n').measured == "280.0 g (motor_a 280.0 g (datasheet table 2))"


def test_an_axis_that_moves_a_stock_body_is_unchecked(mach):
    (mach / "assembly.py").write_text(ASSEMBLY.replace('("motor_a",)', '("motor_a", "rail")'))
    r = one(mach, '[[mass]]\nmoving = "y"\nmax_g = 1000\n')
    assert (r.subject, r.state) == ("axis y", "UNCHECKED") and "no mass for rail (" in r.measured


@pytest.mark.parametrize("assembly, body, says", [
    (None, 'moving = "z"\nmax_g = 20\n', "no axis 'z' in AXES (axes: x, y)"),
    (None, 'moving = ""\nmax_g = 20\n', '`moving` must name one axis, e.g. moving = "x"'),
    (None, 'moving = ["x"]\nmax_g = 20\n', '`moving` must name one axis'),
    (None, 'moving = "x"\n', "[[mass]] is missing `max_g`"),
    ("no axes", 'moving = "x"\nmax_g = 20\n', "assembly.py declares no AXES, so there is no axis 'x' to move anything"),
    ("ghost", 'moving = "x"\nmax_g = 20\n', "axis 'x' moves ghost, which the assembly does not return (bodies: "),
    ("nothing", 'moving = "x"\nmax_g = 20\n', "axis 'x' moves no body"),
])
def test_an_axis_that_cannot_be_weighed_is_one_unchecked_row(mach, assembly, body, says):
    text = ASSEMBLY
    if assembly == "no axes":
        text = ASSEMBLY.split("AXES = {")[0] + "\n\ndef parts" + ASSEMBLY.split("def parts", 1)[1]
    elif assembly == "ghost":
        text = ASSEMBLY.replace('("plate", "block_left")', '("plate", "ghost")')
    elif assembly == "nothing":
        text = ASSEMBLY.replace('("plate", "block_left")', "()")
    (mach / "assembly.py").write_text(text)
    got = spec(mach, "[[mass]]\n" + body)
    assert [(r.subject, r.state) for r in got] == [("[[mass]] #1", "UNCHECKED")] and says in got[0].measured


def test_moving_without_a_machine_is_unchecked(mach):
    got = spec(mach, '[[mass]]\nmoving = "x"\nmax_g = 20\n', machine=False)
    assert got[0].state == "UNCHECKED" and got[0].measured == "`moving` reads AXES from assembly.py, and no assembly was loaded"


def test_bodies_are_described_from_the_files_when_no_machine_came_with_the_solids(mach):
    r = one(mach, '[[mass]]\nbodies = ["plate", "motor_a"]\nmax_g = 300\n', machine=False)
    assert r.state == "PASS" and r.measured.startswith("286.1 g (plate 6.1 g; motor_a 280.0 g")


def test_a_run_reaches_the_machine_so_moving_works_there_and_the_rows_are_the_spec_rules(mach):
    (mach / "spec.toml").write_text('[[mass]]\nmoving = "x"\nmax_g = 10\n[[mass]]\nbodies = ["rail"]\nmax_g = 10\n')
    payload = check_all(SLUG, render_views=("iso",))
    got = [(r["check"], r["rule"], r["state"], r["subject"]) for r in payload["rows"] if r["rule"] == "spec/mass"]
    assert got == [("spec", "spec/mass", "PASS", "axis x"), ("spec", "spec/mass", "UNCHECKED", "rail")]


# ─── com: the centre of mass over the footprint ──────────────────────────────

def body(kind, grams):
    """A BodyInfo of a body that weighs `grams` (None: nobody said), of the kind it is."""
    return BodyInfo(name="b", kind=kind, project="t", part=None if kind == "stock" else "b",
                    mass_g=grams, mass_source=None if grams is None else ("declared" if kind == "bought" else "volume x density"),
                    geometry="exact" if kind == "made" else "envelope")


def run(parts, masses, axes=None):
    """The com rule's rows for solids with the masses given: name -> (kind, grams)."""
    axes = axes or {}
    infos = {n: body(*masses[n]) for n in parts}
    machine = Assembly(slug="t", parts=parts, bodies=infos, axes=axes)
    ctx = AssemblyCtx(slug="t", parts=parts, clearance={}, allow_contact=set(), out_dir=Path("."), axes=axes, machine=machine)
    return list(com(ctx))


def feet(*xy, r=3.0, height=10.0):
    """Cylinders of radius r standing on z = 0 (the lowest plane), one at each (x, y)."""
    return [Pos(x, y, height / 2) * Cylinder(r, height) for x, y in xy]


CORNERS = [(-40, -20), (40, -20), (-40, 20), (40, 20)]


def table():
    """A 100 x 60 top on four 6 mm legs, one solid (230 g: 200 for the frame, 30 for a controller on it)."""
    frame = Pos(0, 0, 12) * Box(100, 60, 4)
    for foot in feet(*CORNERS):
        frame = frame + foot
    return {"frame": frame, "controller": Pos(0, 0, 19) * Box(10, 10, 10)}


TABLE_MASSES = {"frame": ("made", 200.0), "controller": ("bought", 30.0)}


def numbers(text, n=1):
    return [float(x) for x in re.findall(r"-?\d+\.\d+", text)][:n]


def margin(row):
    """How far inside the footprint a com row puts the centre of mass (negative: how far outside)."""
    m = re.search(r"([\d.]+) mm (inside|outside) the footprint", row.measured if hasattr(row, "measured") else row["measured"])
    return float(m[1]) * (1 if m[2] == "inside" else -1)


def test_registered_after_stance_and_described_in_one_line(capsys):
    spec_ = next(c for c in reg.checks("assembly") if c.name == "com")
    names = [c.name for c in reg.checks("assembly")]
    assert names.index("stance") < names.index("com") < names.index("spec") and spec_.order == 35
    assert spec_.doc.startswith("Whether the centre of mass is over the footprint")
    from cad_agent import cli
    assert cli.main(["--json", "rules"]) == cli.OK                                         # `cad rules` lists it too
    listed = json.loads([ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("{")][-1])["data"]["rules"]
    assert {"name": "com", "scope": "assembly", "order": 35, "does": spec_.doc} in listed


def test_with_every_mass_known_a_centre_over_the_legs_passes_and_the_row_says_by_how_much():
    (r,) = run(table(), TABLE_MASSES)
    assert (r.subject, r.rule, r.state, r.limit) == ("assembly", "centre of mass", "PASS", "inside the footprint")
    assert r.measured.startswith("centre of mass (0.0, 0.0) mm, 12.6 mm above the ground, 23.0 mm inside the footprint of frame;")
    assert r.measured.endswith("230.0 g in all") and "convex hull" in r.source


def test_the_footprint_is_where_the_legs_touch_not_the_box_of_the_body_that_has_them():
    # the frame's bounding box reaches x = 50, its legs only 43. A weight hung at x = 60 puts the centre of
    # mass at 41 mm (inside) or 44 mm (past the legs, though still over the top): only the second falls over.
    parts = table() | {"weight": Pos(60, 0, 20) * Box(4, 4, 4)}
    in_ = run(parts, TABLE_MASSES | {"weight": ("bought", 41 * 230 / 19)})
    out = run(parts, TABLE_MASSES | {"weight": ("bought", 44 * 230 / 16)})
    assert [r.state for r in in_] == ["PASS"] and [r.state for r in out] == ["FAIL"]
    assert margin(in_[0]) == pytest.approx(2.0, abs=0.05)
    assert "(44.0, 0.0) mm" in out[0].measured and margin(out[0]) == pytest.approx(-1.0, abs=0.05)
    assert "mm outside the footprint of frame;" in out[0].measured


def test_a_frame_on_two_feet_has_the_gap_between_them_in_its_footprint():
    # a bridge on two legs 60 mm apart: the hull covers the gap, so a centre in the middle is inside
    u = Pos(0, 0, 12) * Box(80, 20, 4)
    for foot in feet((-30, 0), (30, 0), r=5):
        u = u + foot
    parts = {"u": u, "pcb": Pos(0, 0, 16) * Box(4, 4, 2)}
    (r,) = run(parts, {"u": ("made", 100.0), "pcb": ("bought", 5.0)})
    assert r.state == "PASS" and "inside the footprint of u" in r.measured and margin(r) == pytest.approx(5.0, abs=0.05)   # the hull is 10 mm wide


def test_wheels_on_their_sides_give_a_strip_each_and_the_footprint_is_the_hull_of_them():
    wheels = {f"wheel_{i}": Pos(x, y, 10) * Rot(90, 0, 0) * Cylinder(10, 8)
              for i, (x, y) in enumerate([(-30, -40), (30, -40), (-30, 40), (30, 40)])}
    parts = wheels | {"chassis": Pos(0, 0, 14) * Box(80, 100, 4), "pcb": Pos(0, 0, 18) * Box(30, 30, 4)}
    masses = {w: ("made", 25.0) for w in wheels} | {"chassis": ("made", 300.0), "pcb": ("bought", 40.0)}
    (home,) = run(parts, masses)
    assert home.state == "PASS" and margin(home) == pytest.approx(31.0, abs=0.1)                   # 30 + the strip's 1.0
    heavy = parts | {"battery": Pos(60, 0, 18) * Box(4, 4, 4)}
    (over,) = run(heavy, masses | {"battery": ("bought", 33 * 440 / 27)})                          # centre of mass at x = 33
    assert over.state == "FAIL" and margin(over) == pytest.approx(-2.0, abs=0.1)


def test_a_ball_on_the_ground_is_a_dot_and_a_centre_off_it_falls():
    from build123d import Sphere
    parts = {"ball": Pos(0, 0, 5) * Sphere(5), "rod": Pos(7, 0, 30) * Box(4, 4, 40)}
    (r,) = run(parts, {"ball": ("made", 10.0), "rod": ("bought", 90.0)})
    assert r.state == "FAIL" and "mm outside the footprint of ball;" in r.measured       # 6.3 mm off a 0.7 mm dot


# ─── com: when it applies, and what it says when it cannot ───────────────────

def test_a_design_that_declares_no_mass_is_not_judged_and_the_row_says_what_turns_it_on():
    parts = table()
    (r,) = run(parts, {"frame": ("made", 200.0), "controller": ("bought", None)})
    assert (r.state, r.rule) == ("N/A", "centre of mass")
    assert r.measured == ("no bought part declares a mass_g with a mass_source, so nothing says what the assembly "
                          "weighs (1 of 2 bodies have no mass)")
    assert "judged once a bought part declares a mass" in r.source
    (r,) = run(parts, {"frame": ("made", 200.0), "controller": ("stock", None)})
    assert r.state == "N/A"                                                              # a stock body declares nothing either
    assert run(parts, {"frame": ("made", 200.0), "controller": ("made", 5.0)})[0].state == "N/A"   # made masses are not declared


def test_no_assembly_is_not_applicable():
    (r,) = run({}, {})
    assert (r.state, r.measured) == ("N/A", "no assembly")


def test_once_a_mass_is_declared_every_body_needs_one_and_each_that_lacks_one_is_named():
    parts = table() | {"rail": Pos(0, 0, -5) * Box(100, 5, 5), "motor": Pos(0, 30, 19) * Box(5, 5, 5)}
    (r,) = run(parts, TABLE_MASSES | {"rail": ("stock", None), "motor": ("bought", None)})
    assert (r.state, r.limit) == ("UNCHECKED", "every body's mass known")
    assert r.measured.startswith("no mass for 2 of 4 bodies: motor (bought part 'b' declares no mass_g with a mass_source); "
                                 "rail (stock: assembly.py builds it itself;")


def test_what_a_body_has_no_mass_for_is_the_reason_bodies_py_gave():
    info = BodyInfo(name="b", kind="made", project="t", part="b", notes=("parts/b.py declares no MATERIAL, so its mass is unknown",))
    assert comrule._why_no_mass(info) == "parts/b.py declares no MATERIAL, so its mass is unknown"
    assert comrule._why_no_mass(None).startswith("stock: assembly.py builds it itself")


def test_a_body_with_no_volume_cannot_carry_a_mass():
    parts = table() | {"ghost": (Pos(0, 0, 40) * Box(1, 1, 1)) - (Pos(0, 0, 40) * Box(2, 2, 2))}      # nothing left
    (r,) = run(parts, TABLE_MASSES | {"ghost": ("bought", 5.0)})
    assert r.state == "UNCHECKED" and "ghost has no volume" in r.measured


# ─── com over an axis's travel ───────────────────────────────────────────────

def gantry(grams):
    """A 200 x 200 base on the ground (1080 g) and a carriage on it that an axis moves, of `grams`."""
    return ({"base": Pos(0, 0, 5) * Box(200, 200, 10), "carriage": Pos(0, 0, 20) * Box(20, 20, 20)},
            {"base": ("made", 1080.0), "carriage": ("bought", grams)})


def axis_x(moves=("carriage",), travel=(-150.0, 150.0), direction=(1, 0, 0)):
    return {"x": Axis(name="x", moves=moves, direction=direction, travel=travel)}


def test_a_carriage_that_stays_over_the_base_to_the_end_of_its_travel_passes():
    parts, masses = gantry(400.0)
    home, travel = run(parts, masses, axis_x())
    assert home.state == "PASS" and travel.state == "PASS" and (travel.subject, travel.rule) == ("axis x", "centre of mass/x")
    assert "27% of the mass moves" in travel.measured
    assert travel.measured.startswith("over x = -150.0 to +150.0 mm the centre of mass stays inside the footprint, closest 59.5 mm")


def test_a_heavy_carriage_at_the_end_of_its_travel_tips_the_machine_though_it_is_stable_at_home():
    parts, masses = gantry(4000.0)
    home, travel = run(parts, masses, axis_x())
    assert home.state == "PASS" and travel.state == "FAIL"
    assert "centre of mass (-118.1, 0.0) mm is 18.1 mm outside the footprint (79% of the mass moves)" in travel.measured
    assert travel.measured.startswith("at x = -150.0 mm")
    assert run(parts, masses, axis_x(travel=(-100.0, 100.0)))[1].state == "PASS"       # 78.7 mm: inside the 100


def test_the_axis_is_swept_along_its_own_direction():
    parts, masses = gantry(4000.0)
    along_y = {"x": Axis(name="x", moves=("carriage",), direction=(0, 1, 0), travel=(-150.0, 150.0))}
    assert run(parts, masses, along_y)[1].state == "FAIL"
    assert run(parts, masses, {"x": Axis(name="x", moves=("carriage",), direction=(0, 0, 1), travel=(-150.0, 150.0))})[1].state == "PASS"


def test_an_axis_that_moves_a_body_on_the_ground_changes_the_footprint_and_is_unchecked():
    parts, masses = gantry(400.0)
    got = run(parts, masses, axis_x(moves=("base",)))
    assert got[0].state == "PASS" and got[1].state == "UNCHECKED"
    assert got[1].measured == "axis x moves base, which stands on the ground, so the footprint changes along its travel"


def test_an_axis_that_moves_a_body_the_assembly_does_not_return_is_unchecked():
    parts, masses = gantry(400.0)
    assert run(parts, masses, axis_x(moves=("ghost",)))[1].measured == "axis x moves ghost, which the assembly does not return"
    assert run(parts, masses, axis_x(direction=(0, 0, 0)))[1].state == "UNCHECKED"          # motion.Axis refuses a zero direction


# ─── com: the geometry helpers ───────────────────────────────────────────────

def test_a_hull_of_points_drops_what_is_inside_and_is_counter_clockwise():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hull = comrule._hull(square + [(5, 5), (2, 8), (10, 5)])
    assert sorted(hull) == sorted(square)
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(hull, hull[1:] + hull[:1])) / 2
    assert area == pytest.approx(100.0)                                                    # positive: counter-clockwise
    assert len(comrule._hull([(0, 0), (1, 1), (2, 2)])) < 3                                  # collinear: no area
    assert comrule._hull([(1, 1)]) == [(1, 1)] and comrule._hull([]) == []


def test_the_margin_is_the_distance_to_the_nearest_edge_inside_and_to_the_polygon_outside():
    hull = comrule._hull([(0, 0), (10, 0), (10, 10), (0, 10)])
    assert comrule._margin(hull, (5, 5)) == pytest.approx(5.0)
    assert comrule._margin(hull, (1, 5)) == pytest.approx(1.0)
    assert comrule._margin(hull, (12, 5)) == pytest.approx(-2.0)
    assert comrule._margin(hull, (13, 14)) == pytest.approx(-5.0)                            # past a corner: the corner's distance
    assert comrule._margin(hull, (10, 5)) == pytest.approx(0.0)
    assert comrule._margin([(0, 0), (1, 0)], (0.5, 0)) is None and comrule._margin([], (0, 0)) is None


def test_a_footprint_with_no_area_is_a_fail_not_a_pass(monkeypatch):
    monkeypatch.setattr(comrule, "_patch", lambda solid, ground, name: [(0.0, 0.0), (10.0, 0.0), (5.0, 0.0)])
    (r,) = run(table(), TABLE_MASSES)
    assert r.state == "FAIL" and "is a line or a point, so there is nothing for the centre of mass" in r.measured


def test_a_contact_that_cannot_be_measured_is_unchecked(monkeypatch):
    def broken(solid, ground, name):
        raise comrule._Unmeasurable(f"where {name} touches the ground could not be measured: boom")
    monkeypatch.setattr(comrule, "_patch", broken)
    (r,) = run(table(), TABLE_MASSES)
    assert r.state == "UNCHECKED" and r.measured == "where frame touches the ground could not be measured: boom"


# ─── com in a run ────────────────────────────────────────────────────────────

STAND = textwrap.dedent('''\
    from build123d import Pos
    from cad_agent.state import build_part, bought_solid

    SLUG = "mach"


    def parts():
        plate, _ = build_part(SLUG, "base")
        return {"base": plate, "motor": Pos(0, 0, 20) * bought_solid(SLUG, "motor")}
''')

BASE = textwrap.dedent('''\
    """A 100 mm square base, 10 mm thick: 270 g of aluminium."""
    from build123d import Box, Pos

    MATERIAL = "aluminium"
    PROCESS = "cnc"
    MIN_FEATURE_MM = 2.0
    PARAMS = {}


    def build():
        return Pos(0, 0, 5) * Box(100, 100, 10)
''')


@pytest.fixture()
def stand(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    d = st.project_dir(SLUG, create=True)
    (d / "parts" / "base.py").write_text(BASE)
    export_step(Pos(0, 0, 15) * Box(20, 20, 30), str(d / "bought" / "motor.step"))
    (d / "bought" / "motor.json").write_text(json.dumps({"source": "vendor drawing 12", "verified": True}))
    (d / "assembly.py").write_text(STAND)
    return d


def com_rows(payload):
    return [r for r in payload["rows"] if r["check"] == "com"]


def test_a_design_that_declares_no_mass_gets_one_not_applicable_row_and_the_verdict_is_untouched(stand):
    payload = check_all(SLUG, render_views=("iso",))
    (r,) = com_rows(payload)
    assert (r["state"], r["rule"]) == ("N/A", "centre of mass") and "1 of 2 bodies have no mass" in r["measured"]
    assert payload["summary"]["by_check"]["com"] == {"N/A": 1}
    assert {x["state"] for x in payload["rows"] if x["check"] == "stance"} == {"PASS"}


def test_declare_the_motors_mass_and_the_same_design_is_judged(stand):
    side = json.loads((stand / "bought" / "motor.json").read_text())
    (stand / "bought" / "motor.json").write_text(json.dumps({**side, "mass_g": 280, "mass_source": "datasheet table 2"}))
    payload = check_all(SLUG, render_views=("iso",))
    (r,) = com_rows(payload)
    assert r["state"] == "PASS" and "(0.0, 0.0) mm" in r["measured"] and "inside the footprint of base" in r["measured"]
    (stand / "assembly.py").write_text(STAND.replace("Pos(0, 0, 20)", "Pos(150, 0, 20)"))     # the motor far out on a boom
    (r,) = com_rows(check_all(SLUG, render_views=("iso",)))
    assert r["state"] == "FAIL" and "mm outside the footprint of base" in r["measured"]
    assert math.isclose(numbers(r["measured"], 1)[0], 280 * 150 / (270 + 280), abs_tol=0.1)   # the centre of mass at x = 76.4
