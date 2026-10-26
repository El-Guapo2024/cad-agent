"""`cad assembly` and cad_agent/assembly_edit.py: a project's Assembly edited from the CLI, written back into
assembly.py, read again the same, undone as one step, and seen by the gates where the solver put it."""
from __future__ import annotations

import ast
import json

import pytest

from cad_agent import assembly_edit as E
from cad_agent import assembly_wb as W
from cad_agent import cli, ondsel
from cad_agent import state as st
from test_cli import run

pytestmark = pytest.mark.skipif(not ondsel.available(), reason="ui/ondsel is not built (ui/ondsel/build.sh native)")

PART = '''"""{name}: a Part workbench document."""
from cad_agent import feature_part as Part

MATERIAL = "petg"
PROCESS = "fdm"
PARAMS = {{}}

OBJECTS = [
    {obj},
]


def build(**p):
    return Part.Document(OBJECTS, p)
'''


@pytest.fixture
def proj(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    monkeypatch.setenv("CAD_WARM", "0")
    d = tmp_path / "asm"
    (d / "parts").mkdir(parents=True)
    (d / "parts" / "plate.py").write_text(PART.format(name="plate", obj='Part.Box("Box", length=40, width=30, height=5)'))
    (d / "parts" / "pin.py").write_text(PART.format(name="pin", obj='Part.Cylinder("Cylinder", radius=3, height=20)'))
    (d / "parts" / "bar.py").write_text(PART.format(name="bar", obj='Part.Box("Box", length=30, width=6, height=4)'))
    return d


def asm_src(d):
    return (d / "assembly.py").read_text()


def test_insert_makes_the_assembly_and_grounds_the_first_part(proj, capsys):
    code, data = run(capsys, "assembly", "insert", "asm", "plate")
    assert code == cli.OK and data["step"] == "Insert Component"
    objs = E.objects_of(asm_src(proj))
    assert [type(o).__name__ for o in objs] == ["Link", "GroundedJoint"]
    assert objs[1].object_to_ground == "plate"
    code, data = run(capsys, "assembly", "insert", "asm", "plate", "--at", "50,0,0")
    names = [o.name for o in E.objects_of(asm_src(proj)) if isinstance(o, W.Link)]
    assert names == ["plate", "plate001"]                    # Document::getUniqueObjectName
    assert data["doc"]["status"]["state"] == "under_constrained"


def test_a_joint_is_made_as_freecads_panel_makes_it_and_reads_back(proj, capsys):
    run(capsys, "assembly", "insert", "asm", "plate")
    run(capsys, "assembly", "insert", "asm", "pin", "--at", "30,5,2")
    code, data = run(capsys, "assembly", "joint", "asm", "Revolute", "plate:Face6", "pin:Face3:Edge1")
    assert code == cli.OK and data["step"] == "Create Revolute Joint"
    # FreeCAD's answer for the same picks (tests/golden/assembly, revolute_pin, but the pin started elsewhere)
    p = data["doc"]["placements"]["pin"]
    assert p["base"] == pytest.approx([20.0, 15.0, -15.0], abs=1e-9)
    assert data["doc"]["status"] == {"state": "under_constrained", "text": "Under-constrained: ",
                                     "link": "1 Degrees of Freedom"}
    j = [o for o in E.objects_of(asm_src(proj)) if isinstance(o, W.Joint)][0]
    assert (j.name, j.label, j.joint_type) == ("Joint", "Revolute", "Revolute")
    assert j.reference1 == ("plate", ("Face6", "Face6")) and j.reference2 == ("pin", ("Face3", "Edge1"))
    assert "placement1" not in asm_src(proj)                # recomputed from the references, not kept


def test_set_then_recompute_and_an_unchanged_entry_keeps_its_text(proj, capsys):
    run(capsys, "assembly", "insert", "asm", "plate")
    run(capsys, "assembly", "insert", "asm", "bar", "--at", "30,5,2")
    run(capsys, "assembly", "joint", "asm", "Distance", "plate:Face6", "bar:Face5", "distance=5")
    src = asm_src(proj).replace('Assembly.Link("plate", "plate"),', 'Assembly.Link("plate", "plate"),  # the base')
    (proj / "assembly.py").write_text(src)
    code, data = run(capsys, "assembly", "set", "asm", "Joint", "distance=12")
    assert code == cli.OK and data["step"] == "Edit Joint.Distance"
    assert '# the base' in asm_src(proj)
    bar = data["doc"]["placements"]["bar"]
    plate_top = 5.0
    z_axis = W.to_placement(bar).rot.mult_vec((0, 0, 1))
    assert abs(z_axis[2]) == pytest.approx(1.0)              # PlanePlane: the faces stay parallel, 12 apart
    jcs = data["doc"]["jcs"]["Joint"]
    assert abs(jcs["global2"]["base"][2] - plate_top) == pytest.approx(12.0, abs=1e-7)


def test_undo_takes_a_joint_back_as_one_step(proj, capsys):
    run(capsys, "assembly", "insert", "asm", "plate")
    run(capsys, "assembly", "insert", "asm", "pin", "--at", "30,5,2")
    before = asm_src(proj)
    run(capsys, "assembly", "joint", "asm", "Fixed", "plate:Face6", "pin:Face3:Edge1")
    assert asm_src(proj) != before
    code, data = run(capsys, "undo", "asm")
    assert code == cli.OK
    assert asm_src(proj) == before


def test_delete_a_component_takes_its_joints_and_rename_follows_the_references(proj, capsys):
    run(capsys, "assembly", "insert", "asm", "plate")
    run(capsys, "assembly", "insert", "asm", "pin", "--at", "30,5,2")
    run(capsys, "assembly", "joint", "asm", "Revolute", "plate:Face6", "pin:Face3:Edge1")
    run(capsys, "assembly", "rename", "asm", "pin", "axle")
    objs = E.objects_of(asm_src(proj))
    j = [o for o in objs if isinstance(o, W.Joint)][0]
    assert j.reference2[0] == "axle"
    run(capsys, "assembly", "delete", "asm", "axle")
    assert [o.name for o in E.objects_of(asm_src(proj))] == ["plate", "GroundedJoint"]


def test_ground_toggles_and_move_is_refused_on_a_grounded_part(proj, capsys):
    run(capsys, "assembly", "insert", "asm", "plate")
    code, data = run(capsys, "assembly", "move", "asm", "plate", "--at", "1,2,3")
    assert code != cli.OK and "read-only" in json.dumps(data)
    run(capsys, "assembly", "ground", "asm", "plate")
    assert not [o for o in E.objects_of(asm_src(proj)) if isinstance(o, W.GroundedJoint)]
    code, data = run(capsys, "assembly", "move", "asm", "plate", "--at", "1,2,3")
    assert code == cli.OK and data["doc"]["placements"]["plate"]["base"] == [1.0, 2.0, 3.0]


def test_a_bad_edit_leaves_the_file_as_it_was(proj, capsys):
    run(capsys, "assembly", "insert", "asm", "plate")
    before = asm_src(proj)
    code, data = run(capsys, "assembly", "joint", "asm", "Revolute", "plate:Face6", "plate:Face5")
    assert code != cli.OK and "2 separate parts" in json.dumps(data)
    code, data = run(capsys, "assembly", "joint", "asm", "Hinge", "plate:Face6", "nope:Face5")
    assert code != cli.OK
    assert asm_src(proj) == before


def test_the_gates_see_the_solved_assembly(proj, capsys):
    run(capsys, "assembly", "insert", "asm", "plate")
    run(capsys, "assembly", "insert", "asm", "pin", "--at", "30,5,2")
    run(capsys, "assembly", "joint", "asm", "Revolute", "plate:Face6", "pin:Face3:Edge1")
    machine = st.load_machine("asm", describe=False)
    bb = machine.parts["pin"].bounding_box()
    assert (bb.min.Z, bb.max.Z) == pytest.approx((-15.0, 5.0), abs=1e-6)
    code, data = run(capsys, "measure", "asm", "plate", "pin")
    assert "INTERFERENCE" in json.dumps(data) or data.get("overlap_mm3", 0) > 0 or code != cli.OK


def test_a_hand_written_assembly_keeps_its_parts(proj, capsys):
    (proj / "assembly.py").write_text('''"""by hand"""
from build123d import Pos
from cad_agent.state import build_part


def parts():
    bar, _ = build_part("asm", "bar")
    return {"rail": Pos(0, 0, 50) * bar}
''')
    code, data = run(capsys, "assembly", "insert", "asm", "plate")
    assert code == cli.OK
    src = asm_src(proj)
    assert "def placed_parts():" in src and "**placed_parts()" in src and 'SLUG = "asm"' in src
    ast.parse(src)
    machine = st.load_machine("asm", describe=False)
    assert set(machine.parts) == {"rail", "plate"}


def test_read_and_write_round_trip_every_property():
    objs = [W.Link("a", "plate", placement=((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)), label="Plate"),
            W.Link("b", "pin"), W.GroundedJoint("GroundedJoint", "a"),
            W.Joint("Joint", "Slider", ("a", ["Face6", "Vertex2"]), ("b", ["Face1", "Face1"]),
                    offset2=((0.0, 0.0, 3.0), (90.0, 0.0, 0.0)), enable_length_min=True, length_min=2.5,
                    suppressed=True, label="Slider")]
    src = E.write_src(E.new_src(None, "x"), objs)
    back = E.objects_of(src)
    assert [W.as_dict(o) for o in back] == [W.as_dict(o) for o in objs]
    assert E.write_src(src, back) == src
