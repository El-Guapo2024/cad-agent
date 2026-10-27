"""The Assembly workbench's later commands through `cad assembly` and cad_agent/assembly_edit.py: rigid groups
(Assembly_CreateJointRigidGroup), written back into assembly.py, read again the same, undone as one step."""
from __future__ import annotations

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


def objs(d):
    return E.objects_of((d / "assembly.py").read_text())


def three(capsys):
    run(capsys, "assembly", "insert", "asm", "plate")
    run(capsys, "assembly", "insert", "asm", "bar", "--at", "30,5,2")
    run(capsys, "assembly", "insert", "asm", "pin", "--at=-20,40,15")


def test_rigid_group_locks_its_members_and_round_trips(proj, capsys):
    three(capsys)
    code, data = run(capsys, "assembly", "rigid", "asm", "bar", "pin")
    assert code == cli.OK and data["step"] == "Create Rigid Group"
    g = next(o for o in objs(proj) if isinstance(o, W.RigidGroupJoint))
    assert g.name == "RigidGroupJoint" and g.objects_to_rigid_group == ("bar", "pin")
    assert len(g.rigid_placements) == 2
    src = (proj / "assembly.py").read_text()
    assert 'Assembly.RigidGroupJoint("RigidGroupJoint", ["bar", "pin"], rigid_placements=' in src
    tree = {r["name"]: r for r in data["doc"]["tree"]}
    assert tree["RigidGroupJoint"]["icon"] == "Assembly_CreateJointRigidGroup"
    # the pin rides along when the bar is jointed to the plate
    before = W.to_placement(data["doc"]["placements"]["pin"])
    code, data = run(capsys, "assembly", "joint", "asm", "Revolute", "plate:Face6:Vertex8", "bar:Face5:Vertex1")
    assert code == cli.OK
    bar0 = W.to_placement(next(o for o in objs(proj) if o.name == "bar").placement)
    pin = W.to_placement(data["doc"]["placements"]["pin"])
    rel = W.to_placement(g.rigid_placements[1])
    want = bar0 * rel
    assert max(abs(a - b) for a, b in zip(pin.pos, want.pos)) < 1e-6
    assert max(abs(a - b) for a, b in zip(pin.pos, before.pos)) > 1.0
    # one undo step takes the joint away again
    code, data = run(capsys, "undo", "asm")
    assert code == cli.OK and not any(isinstance(o, W.Joint) for o in objs(proj))


def test_rigid_group_needs_two_components_and_follows_renames_and_deletes(proj, capsys):
    three(capsys)
    code, data = run(capsys, "assembly", "rigid", "asm", "bar")
    assert code != cli.OK and "at least 2 components" in str(data)
    run(capsys, "assembly", "rigid", "asm", "bar", "pin")
    run(capsys, "assembly", "rename", "asm", "pin", "pin2")
    g = next(o for o in objs(proj) if isinstance(o, W.RigidGroupJoint))
    assert g.objects_to_rigid_group == ("bar", "pin2")
    run(capsys, "assembly", "delete", "asm", "pin2")
    g = next(o for o in objs(proj) if isinstance(o, W.RigidGroupJoint))
    assert g.objects_to_rigid_group == ("bar",)


def test_update_stored_positions_only_while_suppressed(proj, capsys):
    three(capsys)
    run(capsys, "assembly", "rigid", "asm", "bar", "pin")
    code, data = run(capsys, "assembly", "update-rigid", "asm", "RigidGroupJoint")
    assert code != cli.OK and "only available while suppressed" in str(data)
    run(capsys, "assembly", "set", "asm", "RigidGroupJoint", "suppressed=true")
    run(capsys, "assembly", "move", "asm", "pin", "--at=12,-30,8")
    code, data = run(capsys, "assembly", "update-rigid", "asm", "RigidGroupJoint")
    assert code == cli.OK and data["step"] == "Update Stored Positions"
    g = next(o for o in objs(proj) if isinstance(o, W.RigidGroupJoint))
    bar = W.to_placement(next(o for o in objs(proj) if o.name == "bar").placement)
    assert max(abs(a - b) for a, b in zip((bar * W.to_placement(g.rigid_placements[1])).pos, (12, -30, 8))) < 1e-9


def test_moving_a_member_drags_the_group(proj, capsys):
    three(capsys)
    run(capsys, "assembly", "rigid", "asm", "bar", "pin")
    code, data = run(capsys, "assembly", "move", "asm", "pin", "--at", "0,0,50")
    assert code == cli.OK
    pin = W.to_placement(data["doc"]["placements"]["pin"])
    bar = W.to_placement(data["doc"]["placements"]["bar"])
    assert max(abs(a - b) for a, b in zip(pin.pos, (0, 0, 50))) < 1e-9
    assert max(abs(a - b) for a, b in zip(bar.pos, (50, -35, 37))) < 1e-9     # moved by the same (+20, -40, +35)


def test_a_joint_on_the_assemblys_origin(proj, capsys):
    run(capsys, "assembly", "insert", "asm", "bar", "--at", "30,5,2", "--no-ground")
    code, data = run(capsys, "assembly", "joint", "asm", "Fixed", "Origin:XY_Plane", "bar:Face5")
    assert code == cli.OK, data
    j = next(o for o in objs(proj) if isinstance(o, W.Joint))
    assert j.reference1 == ("Origin", ("XY_Plane.", "XY_Plane.")) and j.reference2[0] == "bar"
    p = W.to_placement(data["doc"]["placements"]["bar"])
    assert abs(p.pos[2]) < 1e-9 and data["doc"]["status"]["state"] == "fully_constrained"
    code, data = run(capsys, "assembly", "jcs", "asm", "Origin", "Z_Axis")
    assert code == cli.OK and data["subs"] == ["Z_Axis.", "Z_Axis."]
    z = W.to_placement(data["global"]).rot.mult_vec((0, 0, 1))
    assert max(abs(a - b) for a, b in zip(z, (0, 0, 1))) < 1e-12
    code, data = run(capsys, "assembly", "joint", "asm", "Fixed", "Origin:XYZ_Plane", "bar:Face3")
    assert code != cli.OK and "not a feature of the Assembly's Origin" in str(data)
