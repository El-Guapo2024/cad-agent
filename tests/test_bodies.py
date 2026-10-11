"""bodies.py: what each body of an assembly is, and the machine load_machine returns.

Every rule of step 6 starts from the BodyInfo of a body (is it made, bought or stock; its material,
mass and temperature; whether its geometry is exact), so these tests hold what they rely on:
a bought part is known by the tag bought_solid gives it and not by its name, a mass with no source
is not a mass, and load_assembly is still the four things it always returned.
"""
import json
import sys
import textwrap
import types

import pytest
from build123d import Box, Plane, Pos, export_step, mirror

from cad_agent import bodies, cmdbase, geom, materials, placements
from cad_agent import state as st
from cad_agent.bodies import Assembly, BodyInfo
from cad_agent.registry import SpecCtx
from cad_agent.runner import check_all

SLUG = "mach"

PLATE = textwrap.dedent('''\
    """A plate."""
    from build123d import Box

    MATERIAL = "petg"
    PROCESS = "fdm"
    MIN_FEATURE_MM = 1.2
    PARAMS = {}


    def build():
        return Box(40, 30, 4)
''')

BLOCK = textwrap.dedent('''\
    """A block."""
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
    VENDOR = "Example"
    VERIFIED = True
    PN = "S-100"
    MASS_G = 4.5
    MASS_SOURCE = "datasheet p.2, weight"
    MATERIAL = "fr4"
    MAX_TEMP_C = 85
    MAX_TEMP_SOURCE = "datasheet p.1, operating range"
    PARAMS = {"size": 6.0}


    def build(size):
        return Box(size, size, 2)
''')

ASSEMBLY = textwrap.dedent('''\
    from build123d import Box, Plane, Pos, mirror
    from cad_agent.state import build_part, bought_solid

    SLUG = "mach"
    CLEARANCE = {"plate|block_left": 1.0}
    ALLOW_CONTACT = {"plate|rail"}
    POSES = {"park": {"x": 10}}


    def parts():
        plate, _ = build_part(SLUG, "plate")
        block, _ = build_part(SLUG, "block")
        motor = bought_solid(SLUG, "motor")
        return {
            "plate": plate,
            "block_left": Pos(30, 0, 0) * block,
            "motor_a": Pos(0, 40, 0) * motor,
            "motor_b": mirror(Pos(0, -40, 0) * motor, Plane.XZ),
            "sensor": Pos(0, 0, 30) * bought_solid(SLUG, "sensor"),
            "rail": Pos(0, 0, -20) * Box(100, 10, 10),
        }
''')


@pytest.fixture()
def mach(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    d = st.project_dir(SLUG, create=True)
    (d / "parts" / "plate.py").write_text(PLATE)
    (d / "parts" / "block.py").write_text(BLOCK)
    (d / "bought" / "sensor.py").write_text(SENSOR)
    export_step(Box(20, 20, 30), str(d / "bought" / "motor.step"))
    (d / "bought" / "motor.json").write_text(json.dumps({
        "source": "vendor drawing 12", "vendor": "Motors Inc", "verified": True, "pn": "M-17",
        "mass_g": 280, "mass_source": "datasheet table 2", "material": "steel"}))
    (d / "assembly.py").write_text(ASSEMBLY)
    return d


# ─── load_machine ────────────────────────────────────────────────────────────

def test_load_machine_returns_the_assembly_with_everything_assembly_py_declares(mach):
    m = st.load_machine(SLUG)
    assert isinstance(m, Assembly) and m.slug == SLUG
    assert sorted(m.parts) == ["block_left", "motor_a", "motor_b", "plate", "rail", "sensor"]
    assert m.clearance == {"plate|block_left": 1.0} and m.allow_contact == {"plate|rail"}
    assert m.axes == {} and m.children == {}
    assert m.poses == {"park": {"x": 10}}
    assert set(m.bodies) == set(m.parts) and all(isinstance(b, BodyInfo) for b in m.bodies.values())


def test_load_machine_can_be_asked_of_either_module(mach):
    a, b = st.load_machine(SLUG), bodies.load_machine(SLUG)
    assert isinstance(b, Assembly) and sorted(a.parts) == sorted(b.parts) and a.bodies == b.bodies
    assert bodies.load_machine(SLUG, describe=False).bodies == {}


def test_a_project_with_no_assembly_has_no_machine(mach):
    (mach / "assembly.py").unlink()
    assert st.load_machine(SLUG) is None
    assert st.load_assembly(SLUG) == (None, {}, set(), {})


def test_load_assembly_stays_the_four_things_it_returned(mach):
    parts, clearance, allow_contact, axes = st.load_assembly(SLUG)
    m = st.load_machine(SLUG)
    assert sorted(parts) == sorted(m.parts) and clearance == m.clearance
    assert allow_contact == m.allow_contact and axes == m.axes
    assert m.as_tuple()[1:] == (m.clearance, m.allow_contact, m.axes)


def test_describe_false_skips_the_bodies(mach):
    assert st.load_machine(SLUG, describe=False).bodies == {}


def test_moves_by_hand_apply_to_the_machine_and_a_move_keeps_a_body_bought(mach):
    placements.save(mach, {"motor_a": {"move": (5.0, 0.0, 0.0), "turn": (0.0, 0.0, 0.0), "about": (0.0, 0.0, 0.0)}})
    moved, base = st.load_machine(SLUG), st.load_machine(SLUG, placed=False)
    assert geom.bbox(moved.parts["motor_a"])[0][0] == pytest.approx(geom.bbox(base.parts["motor_a"])[0][0] + 5.0)
    assert moved.bodies["motor_a"].kind == "bought"                  # the tag follows the move


def test_poses_must_be_a_dict_of_dicts(mach):
    (mach / "assembly.py").write_text(ASSEMBLY.replace('POSES = {"park": {"x": 10}}', 'POSES = ["park"]'))
    with pytest.raises(TypeError, match="POSES"):
        st.load_machine(SLUG)


def test_assembly_py_that_returns_no_solids_still_fails_as_it_did(mach):
    (mach / "assembly.py").write_text("def parts():\n    return [1, 2]\n")
    with pytest.raises(TypeError, match="must return"):
        st.load_machine(SLUG)


# ─── What a body is ──────────────────────────────────────────────────────────

def test_a_body_is_made_bought_or_stock(mach):
    b = st.load_machine(SLUG).bodies
    assert (b["plate"].kind, b["plate"].part, b["plate"].project) == ("made", "plate", SLUG)
    assert (b["block_left"].kind, b["block_left"].part) == ("made", "block")        # no suffix to a part module
    assert (b["motor_a"].kind, b["motor_a"].part) == ("bought", "motor")           # by its tag: not called motor
    assert (b["sensor"].kind, b["sensor"].part) == ("bought", "sensor")
    assert b["rail"].kind == "stock" and b["rail"].part is None


def test_a_mirrored_copy_loses_the_tag_and_so_its_kind(mach):
    # mirror() builds a new solid; `.moved()`, Pos * and rotate keep the tag. A body of that kind is
    # stock to every rule, so UNCHECKED where a mass is needed: it fails closed.
    assert bodies.describe(SLUG, {"m": mirror(Pos(0, 0, 0) * Box(5, 5, 5), Plane.XZ)})["m"].kind == "stock"
    assert st.load_machine(SLUG).bodies["motor_b"].kind == "stock"


def test_a_made_body_has_its_material_process_mass_and_exact_geometry(mach):
    m = st.load_machine(SLUG)
    plate = m.bodies["plate"]
    assert (plate.material, plate.process, plate.geometry) == ("petg", "fdm", "exact")
    assert plate.mass_g == pytest.approx(geom.mass_g(m.parts["plate"], "petg"))
    assert plate.mass_g == pytest.approx(40 * 30 * 4 / 1000 * 1.27)
    assert plate.mass_source == "volume x density of petg (materials.py)"
    assert plate.source == "parts/plate.py" and plate.verified is True and plate.notes == ()
    block = m.bodies["block_left"]
    assert block.mass_g == pytest.approx(10 * 10 * 10 / 1000 * 2.70) and block.process == "cnc"


def test_a_made_bodys_temperature_comes_from_its_material_if_the_table_has_one(mach):
    for name, material in (("plate", "petg"), ("block_left", "aluminium")):
        got = st.load_machine(SLUG).bodies[name]
        want = materials.prop(material, "max_service_temp_c")
        assert got.max_temp_c == (want.value if want else None)
        assert (got.max_temp_source is None) == (want is None)


def test_a_bought_body_has_what_it_declares_and_nothing_it_does_not(mach):
    m = st.load_machine(SLUG)
    motor = m.bodies["motor_a"]
    assert (motor.mass_g, motor.mass_source) == (280.0, "datasheet table 2")
    assert (motor.material, motor.vendor, motor.pn, motor.source) == ("steel", "Motors Inc", "M-17", "vendor drawing 12")
    assert motor.geometry == "envelope"                                 # a STEP is an envelope until it says otherwise
    steel = materials.prop("steel", "max_service_temp_c")             # it names a material and no temperature of its own
    assert motor.max_temp_c == steel.value and motor.max_temp_source.startswith(f"materials.py steel ({steel.basis})")
    assert motor.process is None and motor.notes == ()
    sensor = m.bodies["sensor"]
    assert (sensor.mass_g, sensor.max_temp_c, sensor.max_temp_source) == (4.5, 85.0, "datasheet p.1, operating range")
    assert (sensor.material, sensor.pn, sensor.verified) == ("fr4", "S-100", True)


def test_a_bought_geometry_that_says_exact_is_exact(mach):
    side = json.loads((mach / "bought" / "motor.json").read_text())
    (mach / "bought" / "motor.json").write_text(json.dumps({**side, "geometry": "exact"}))
    assert st.load_machine(SLUG).bodies["motor_a"].geometry == "exact"


def test_a_mass_with_no_source_is_not_a_mass(mach):
    side = json.loads((mach / "bought" / "motor.json").read_text())
    del side["mass_source"]
    (mach / "bought" / "motor.json").write_text(json.dumps(side))
    motor = st.load_machine(SLUG).bodies["motor_a"]
    assert motor.mass_g is None and motor.mass_source is None
    assert any("mass_g is declared without a mass_source" in n for n in motor.notes)


def test_stock_has_no_material_mass_or_exact_geometry(mach):
    rail = st.load_machine(SLUG).bodies["rail"]
    assert (rail.kind, rail.material, rail.mass_g, rail.max_temp_c, rail.geometry, rail.source) == (
        "stock", None, None, None, "envelope", "assembly.py")


def test_a_part_with_no_material_or_an_unknown_one_says_why_it_has_no_mass(mach):
    (mach / "parts" / "plate.py").write_text(NO_MATERIAL)
    plate = st.load_machine(SLUG).bodies["plate"]
    assert plate.material is None and plate.mass_g is None and "declares no MATERIAL" in plate.notes[0]
    (mach / "parts" / "plate.py").write_text(PLATE.replace('"petg"', '"unobtainium"'))
    plate = st.load_machine(SLUG).bodies["plate"]
    assert plate.material == "unobtainium" and plate.mass_g is None and "no density" in plate.notes[0]


def test_a_name_that_is_a_bought_file_is_bought_even_without_the_tag(mach):
    solids = {"motor": Box(1, 1, 1), "sensor_left": Box(1, 1, 1)}
    b = bodies.describe(SLUG, solids)
    assert (b["motor"].kind, b["motor"].part) == ("bought", "motor")
    assert b["sensor_left"].kind == "stock"                              # a position word is only stripped for part modules


def test_a_bought_part_whose_file_has_gone_is_bought_with_a_note_not_a_crash(mach):
    solid = st.bought_solid(SLUG, "sensor")
    (mach / "bought" / "sensor.py").unlink()
    info = bodies.describe(SLUG, {"s": solid})["s"]
    assert info.kind == "bought" and info.mass_g is None and "no bought part 'sensor'" in info.notes[0]


def test_a_body_that_cannot_be_described_is_stock_with_a_note_and_the_rest_still_are(mach):
    info = bodies.describe(SLUG, {"plate": object(), "rail": Box(1, 1, 1)})
    assert info["plate"].kind == "stock" and info["plate"].notes[0].startswith("could not be described:")
    assert info["rail"].kind == "stock" and info["rail"].notes == ()


def test_part_for_is_the_rule_scene_py_colours_bodies_by():
    from cad_agent import scene
    assert scene._part_for is bodies.part_for and scene._bought_names is bodies.bought_stems
    assert bodies.part_for("end_plate_left", ["end_plate"]) == "end_plate"
    assert bodies.part_for("standoff_fl", ["plate_standoff"]) == "plate_standoff"
    assert bodies.part_for("gantry_beam", ["gantry_end"]) is None


def test_body_info_is_plain_data_and_frozen():
    info = BodyInfo(name="x", kind="stock", project="p", notes=("a",))
    assert info.as_dict()["notes"] == ["a"] and info.as_dict()["geometry"] == "envelope"
    json.dumps(info.as_dict())
    with pytest.raises(Exception):
        info.kind = "made"
    assert bodies.KINDS == ("made", "bought", "stock")


# ─── The rules get it ────────────────────────────────────────────────────────

def test_the_spec_context_describes_the_bodies_with_or_without_a_machine(mach):
    solids = st.load_machine(SLUG, describe=False).parts
    assert SpecCtx(slug=SLUG, parts=solids).bodies["motor_a"].mass_g == 280.0
    m = st.load_machine(SLUG)
    assert SpecCtx(slug=SLUG, parts=m.parts, machine=m).bodies is m.bodies


def test_a_run_hands_the_machine_to_a_spec_kind(mach, monkeypatch):
    from cad_agent import registry as reg
    seen = []
    monkeypatch.setattr(reg, "_SPEC_KINDS", dict(reg._SPEC_KINDS))

    @reg.spec_kind("probe")
    def probe(entry, ctx):
        seen.append(ctx.machine)
        return []

    (mach / "spec.toml").write_text("[[probe]]\nx = 1\n")
    check_all(SLUG, render_views=("iso",))
    (machine,) = seen
    assert isinstance(machine, Assembly) and machine.bodies["motor_a"].kind == "bought"


# ─── Sub-assemblies: piece B plugs in here ───────────────────────────────────

def declares_subassemblies(mach):
    (mach / "assembly.py").write_text(ASSEMBLY + '\nSUBASSEMBLIES = {"gantry": {"project": "gantry", "at": [0, 0, 0]}}\n')


@pytest.mark.skipif(cmdbase.resolve("cad_agent.subassembly:expand") is not None, reason="piece B has been built")
def test_a_design_that_declares_subassemblies_does_not_load_until_they_are_built(mach):
    declares_subassemblies(mach)
    with pytest.raises(cmdbase.NotBuilt, match="SUBASSEMBLIES"):
        st.load_machine(SLUG)
    with pytest.raises(cmdbase.NotBuilt):
        st.load_assembly(SLUG)


def test_the_expand_hook_gets_the_machine_and_the_declaration_and_its_answer_is_the_machine(mach, monkeypatch):
    declares_subassemblies(mach)
    calls = []

    def expand(machine, declared):
        calls.append((machine, declared))
        machine.parts["gantry/x_carriage"] = Pos(0, 0, 60) * Box(8, 8, 8)
        machine.bodies["gantry/x_carriage"] = BodyInfo(name="gantry/x_carriage", kind="made", project="gantry",
                                                       part="x_carriage", geometry="exact")
        machine.children["gantry"] = {"project": "gantry"}
        return machine

    stub = types.ModuleType("cad_agent.subassembly")
    stub.expand = expand
    monkeypatch.setitem(sys.modules, "cad_agent.subassembly", stub)
    m = st.load_machine(SLUG)
    (machine, declared), = calls
    assert declared == {"gantry": {"project": "gantry", "at": [0, 0, 0]}} and machine.slug == SLUG
    assert "gantry/x_carriage" in m.parts and m.children == {"gantry": {"project": "gantry"}}
    assert m.bodies["gantry/x_carriage"].project == "gantry"             # what expand described is kept
    assert m.bodies["motor_a"].kind == "bought" and m.bodies["plate"].kind == "made"   # the rest is described here
    assert st.load_machine(SLUG, describe=False).bodies == {"gantry/x_carriage": m.bodies["gantry/x_carriage"]}
