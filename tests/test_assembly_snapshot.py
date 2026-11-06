"""Assembly_CreateSnapshot (cad_agent/assembly_snapshot.py): a Snapshot keeps the movable parts' Placements and
Visibilities; restoring it puts them back (restoreState), one undo step each, named as FreeCAD's."""
import json

import pytest

from cad_agent import assembly_edit as E
from cad_agent import ondsel
from test_assembly_edit import proj  # noqa: F401  (the fixture)
from test_cli import run

pytestmark = pytest.mark.skipif(not ondsel.available(), reason="ui/ondsel is not built (ui/ondsel/build.sh native)")


def test_a_snapshot_is_made_and_restored(proj, capsys):  # noqa: F811
    run(capsys, "assembly", "insert", "asm", "plate")
    run(capsys, "assembly", "insert", "asm", "pin", "--at", "30,5,2")
    code, data = run(capsys, "assembly", "apply", "asm", "--ops", json.dumps([{"op": "snapshot"}]))
    assert code == 0 and data["step"] == "Create Snapshot"
    src = (proj / "assembly.py").read_text()
    assert 'Assembly.SnapshotGroup("Snapshots")' in src and 'Assembly.Snapshot("Snapshot", components=["plate", "pin"]' in src
    run(capsys, "assembly", "apply", "asm", "--ops", json.dumps(
        [{"op": "move", "name": "pin", "placement": [[60, 0, 0], [0, 0, 0, 1]]}]))
    code, data = run(capsys, "assembly", "apply", "asm", "--ops", json.dumps([{"op": "restore_snapshot", "name": "Snapshot"}]))
    assert code == 0 and data["step"] == "Restore Snapshot 'Snapshot'"
    objs = E.objects_of((proj / "assembly.py").read_text())
    pin = next(o for o in objs if o.name == "pin")
    assert tuple(pin.placement[0]) == (30.0, 5.0, 2.0)
