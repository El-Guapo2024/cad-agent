"""`cad feature add/set` with a taper, a Common operation, a start reference and PartDesign::Scaled, through the real
part-file layer: each one undo step named as FreeCAD names the transaction, the part built, undo putting it back."""
from __future__ import annotations

import json

from cad_agent import cli
from cad_agent import undo as un
from test_cli import run
from test_featurecmd_transform import _plate
from test_workbench import demo  # noqa: F401 (reused fixture)


def test_taper_common_and_start_reference_from_the_cli(demo, capsys):  # noqa: F811
    _plate(capsys)
    code, data = run(capsys, "feature", "set", "demo", "Body", "Pocket", "taper_angle=10")
    assert data.get("built") is True, data
    assert un.load(demo)["undo"][-1]["name"] == "Edit Pocket.TaperAngle"
    assert data["doc"]["features"][-1]["taper_angle"] == 10
    code, data = run(capsys, "feature", "set", "demo", "Body", "Pocket", "operation=Common")
    assert data.get("built") is True, data
    assert un.load(demo)["undo"][-1]["name"] == "Edit Pocket.Operation"
    text = (demo / "parts" / "Body.py").read_text()
    assert 'Pocket("Pocket", "Sketch001", taper_angle=10, operation="Common")' in text   # 5 mm: the default
    code, data = run(capsys, "feature", "set", "demo", "Body", "Pocket", "operation=Union")
    assert code == cli.USAGE and "operation 'Union' is not one of Subtraction, Common" in data["error"]
    code, data = run(capsys, "feature", "set", "demo", "Body", "Pocket", "start_type=Reference",
                     'start_reference=["Pad", "Face6"]')
    assert data.get("built") is True, data
    assert data["doc"]["features"][-1]["start_reference"] == ["Pad", "Face6"]
    assert run(capsys, "undo", "demo")[0] == cli.OK
    assert run(capsys, "feature", "list", "demo", "Body")[1]["features"][-1]["start_type"] == "Profile plane"


def test_scaled_from_the_cli(demo, capsys):  # noqa: F811
    _plate(capsys)
    code, data = run(capsys, "feature", "add", "demo", "Body", "Scaled", "Scaled", 'originals=["Pocket"]',
                     "factor=0.5", "occurrences=3")
    assert data.get("built") is True, data
    assert un.load(demo)["undo"][-1]["name"] == "Make Scaled"
    sc = data["doc"]["features"][-1]
    assert (sc["type"], sc["originals"], sc["factor"], sc["occurrences"]) == ("PartDesign::Scaled", ["Pocket"], 0.5, 3)
    text = (demo / "parts" / "Body.py").read_text()
    assert 'Scaled("Scaled", ["Pocket"], factor=0.5, occurrences=3)' in text and \
        "Scaled" in text.split("\nFEATURES = ")[0]
    code, data = run(capsys, "feature", "set", "demo", "Body", "Scaled", "occurrences=1")
    assert code != cli.OK and "At least two occurrences required" in json.dumps(data)
    code, data = run(capsys, "feature", "add", "demo", "Body", "MultiTransform", "MultiTransform",
                     'originals=["Pocket"]', 'transformations=[{"name": "Linear_Pattern", "type": '
                     '"PartDesign::LinearPattern", "direction": "X_Axis", "length": 20, "occurrences": 2}, '
                     '{"name": "Scale", "type": "PartDesign::Scaled", "factor": 0.5, "occurrences": 2}]')
    assert data.get("built") is True, data
