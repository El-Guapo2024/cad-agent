"""`cad feature add/set` with Mirrored, LinearPattern, PolarPattern, MultiTransform and the primitives, through the real
part-file layer: each one undo step named as FreeCAD names the transaction, the part built, undo putting it back."""
from __future__ import annotations

import json

from cad_agent import cli
from cad_agent import undo as un
from test_cli import run
from test_workbench import demo  # noqa: F401 (reused fixture)

SKETCH, PAD, POCKET = "Sketcher::SketchObject", "PartDesign::Pad", "PartDesign::Pocket"


def _plate(capsys):
    assert run(capsys, "feature", "new", "demo", "Body")[0] == cli.OK
    rect = [{"type": "LineSegment", "start": a, "end": b, "construction": False}
            for a, b in [([0, 0], [40, 0]), ([40, 0], [40, 20]), ([40, 20], [0, 20]), ([0, 20], [0, 0])]]
    circle = [{"type": "Circle", "center": [6, 10], "radius": 2, "construction": False}]
    ops = [{"op": "add", "feature": {"name": "Sketch", "type": SKETCH, "support": "XY", "geometry": rect,
                                     "constraints": []}},
           {"op": "add", "feature": {"name": "Pad", "type": PAD, "profile": "Sketch", "length": 5.0}},
           {"op": "add", "feature": {"name": "Sketch001", "type": SKETCH, "support": "XY",
                                     "attachment_offset": [0, 0, 5], "geometry": circle, "constraints": []}},
           {"op": "add", "feature": {"name": "Pocket", "type": POCKET, "profile": "Sketch001", "length": 5.0}}]
    code, data = run(capsys, "feature", "apply", "demo", "Body", "--ops", json.dumps(ops))
    assert data.get("built") is True, data


def test_patterns_from_the_cli(demo, capsys):  # noqa: F811
    _plate(capsys)
    code, data = run(capsys, "feature", "add", "demo", "Body", "LinearPattern", "LinearPattern",
                     'originals=["Pocket"]', 'direction=["Sketch001", "H_Axis"]', "length=24", "occurrences=4")
    assert data.get("built") is True, data
    assert un.load(demo)["undo"][-1]["name"] == "Make LinearPattern"
    lp = data["doc"]["features"][-1]
    assert (lp["type"], lp["originals"], lp["direction"], lp["occurrences"]) == \
        ("PartDesign::LinearPattern", ["Pocket"], ["Sketch001", "H_Axis"], 4)
    assert data["doc"]["tip"] == "LinearPattern"
    text = (demo / "parts" / "Body.py").read_text()
    assert 'LinearPattern("LinearPattern", ["Pocket"], direction=("Sketch001", "H_Axis"), length=24, occurrences=4)' \
        in text and "LinearPattern" in text.split("\nFEATURES = ")[0]   # imported too
    code, data = run(capsys, "feature", "set", "demo", "Body", "LinearPattern", "occurrences=3")
    assert data["doc"]["features"][-1]["occurrences"] == 3
    assert un.load(demo)["undo"][-1]["name"] == "Edit LinearPattern.Occurrences"
    code, data = run(capsys, "feature", "set", "demo", "Body", "LinearPattern", "mode=Diagonal")
    assert code == cli.USAGE and "mode 'Diagonal'" in data["error"]
    code, data = run(capsys, "feature", "add", "demo", "Body", "PartDesign::Mirrored", "Mirrored",
                     'originals=["LinearPattern"]', "mirror_plane=YZ_Plane")
    assert code != cli.OK and "Only additive and subtractive features can be transformed" in json.dumps(data)
    code, data = run(capsys, "feature", "add", "demo", "Body", "MultiTransform", "MultiTransform",
                     'originals=["Pocket"]', 'transformations=[{"name": "Mirror", "type": "PartDesign::Mirrored", '
                     '"mirror_plane": ["Sketch", "V_Axis"]}]')
    assert data.get("built") is True, data
    assert un.load(demo)["undo"][-1]["name"] == "Make MultiTransform"
    assert run(capsys, "undo", "demo")[0] == cli.OK
    assert [f["name"] for f in run(capsys, "feature", "list", "demo", "Body")[1]["features"]][-1] == "LinearPattern"


def test_primitives_from_the_cli(demo, capsys):  # noqa: F811
    assert run(capsys, "feature", "new", "demo", "Body")[0] == cli.OK
    code, data = run(capsys, "feature", "add", "demo", "Body", "AdditiveBox", "Box", "length=40", "width=20",
                     "height=5")
    assert data.get("built") is True, data
    assert un.load(demo)["undo"][-1]["name"] == "Make additive Box"
    code, data = run(capsys, "feature", "add", "demo", "Body", "SubtractiveCylinder", "Cylinder", "radius=3",
                     "height=5", "placement=[[8, 10, 0], [0, 0, 0]]")
    assert data.get("built") is True, data
    assert un.load(demo)["undo"][-1]["name"] == "Make subtractive Cylinder"
    code, data = run(capsys, "feature", "add", "demo", "Body", "PolarPattern", "PolarPattern",
                     'originals=["Cylinder"]', "axis=Z_Axis", "occurrences=2")
    assert data.get("built") is True, data
    code, data = run(capsys, "feature", "set", "demo", "Body", "Cylinder", "operation=Common")
    assert data["doc"]["features"][1]["operation"] == "Common"
    code, data = run(capsys, "feature", "add", "demo", "Body", "SubtractiveBox", "Box", "length=4")
    assert code == cli.USAGE and "already a feature 'Box'" in data["error"]
