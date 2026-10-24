"""`cad feature` and /api/<slug>/features: a part's PartDesign feature list, edited from the CLI and the page.

The part-file layer (cad_agent/feature_edit.py) is another piece's; these tests put a fake behind the one seam
both reach it through, serve.feature_layer(), so what is tested here is this side of it: the commands, the undo
journal, the rebuild, the endpoints. The fake keeps the list in the part file as a FEATURES literal (so undo,
which restores files, round-trips it) and builds a box a pad's length tall, so a build can fail on purpose.
"""
from __future__ import annotations

import ast
import json

import pytest

from cad_agent import cli, featurecmd, serve
from cad_agent import undo as un
from test_cli import run
from test_workbench import demo, inproc, serving  # noqa: F401 (reused fixtures)

SKETCH, PAD, POCKET = "Sketcher::SketchObject", "PartDesign::Pad", "PartDesign::Pocket"

BODY = '''"""A body for the feature tests."""
from build123d import Box

MATERIAL = "petg"
PROCESS = "fdm"

PARAMS = {"thick": 5.0}

FEATURES = []
TIP = None


def build(thick):
    pads = [f for f in FEATURES if f["type"] != "Sketcher::SketchObject"]
    if not pads:
        raise ValueError("the Body has no solid: FEATURES has no Pad and there is no base")
    if any(f.get("length", 1) <= 0 for f in pads):
        raise ValueError("Length too small")
    return Box(10, 10, sum(f.get("length", 10) for f in pads if f["type"] == "PartDesign::Pad") or thick)
'''


class FakeLayer:
    """read/apply as feature_edit.py's contract has them, over FEATURES/TIP literals in the file."""

    class Error(ValueError):
        pass

    @staticmethod
    def _literals(src: str):
        out = {}
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                try:
                    out[node.targets[0].id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
        return out

    def read(self, path):
        lit = self._literals(path.read_text())
        if "FEATURES" not in lit:
            return {"part": path.stem, "params": lit.get("PARAMS", {}), "base": True, "features": [], "tip": None}
        feats = lit["FEATURES"]
        tip = lit.get("TIP") or next((f["name"] for f in reversed(feats) if f["type"] != SKETCH), None)
        return {"part": path.stem, "params": lit.get("PARAMS", {}), "base": False, "features": feats, "tip": tip}

    def apply(self, path, ops):
        doc = self.read(path)
        feats = [dict(f) for f in doc["features"]]
        tip = (self._literals(path.read_text())).get("TIP")
        names = lambda: [f["name"] for f in feats]
        for op in ops:
            kind = op["op"]
            if kind == "add":
                f = dict(op["feature"])
                if f["name"] in names():
                    raise self.Error(f"there is already a feature named {f['name']}")
                if f["type"] != SKETCH and f.get("profile") not in names():
                    raise self.Error(f"{f['name']}: no sketch {f.get('profile')!r} before it")
                if "after" not in op:           # feature_edit: no "after" appends, "after": None goes first
                    at = len(feats)
                else:
                    at = names().index(op["after"]) + 1 if op["after"] in names() else 0
                feats.insert(at, f)
            elif kind == "set":
                f = next((f for f in feats if f["name"] == op["name"]), None)
                if f is None:
                    raise self.Error(f"no feature {op['name']}")
                f.update(op["props"])
            elif kind == "delete":
                if op["name"] not in names():
                    raise self.Error(f"no feature {op['name']}")
                users = [f["name"] for f in feats if f.get("profile") == op["name"]]
                if users:
                    raise self.Error(f"{op['name']} is used by {', '.join(users)}")
                feats = [f for f in feats if f["name"] != op["name"]]
            elif kind == "rename":
                for f in feats:
                    if f["name"] == op["name"]:
                        f["name"] = op["to"]
                    if f.get("profile") == op["name"]:
                        f["profile"] = op["to"]
            elif kind == "move":
                f = next(f for f in feats if f["name"] == op["name"])
                feats.remove(f)
                at = names().index(op["after"]) + 1 if op.get("after") else 0
                feats.insert(at, f)
            elif kind == "tip":
                tip = op["name"]
            else:
                raise self.Error(f"unknown op {kind}")
        src = path.read_text()
        lines = [("FEATURES = " + repr(feats)) if ln.startswith("FEATURES = ") else
                 ("TIP = " + repr(tip)) if ln.startswith("TIP = ") else ln for ln in src.splitlines()]
        path.write_text("\n".join(lines) + "\n")
        return self.read(path)


@pytest.fixture()
def fake(monkeypatch):
    lay = FakeLayer()
    monkeypatch.setattr(serve, "feature_layer", lambda: lay)
    return lay


@pytest.fixture()
def body(demo, fake):
    (demo / "parts" / "body.py").write_text(BODY)
    return demo / "parts" / "body.py"


def _sketch_and_pad(capsys, length=6.0):
    assert run(capsys, "feature", "add", "demo", "body", "Sketch", "Sketch", "support=XY")[0] == cli.OK
    return run(capsys, "feature", "add", "demo", "body", "Pad", "Pad", "profile=Sketch", f"length={length}")


# ── the CLI ──────────────────────────────────────────────────────────────────────────────────────

def test_list_shows_a_hand_written_part_as_base_and_a_body_as_its_features(body, capsys):
    code, data = run(capsys, "feature", "list", "demo")
    assert code == cli.OK
    assert data["parts"]["plate"]["base"] is True and data["parts"]["plate"]["features"] == []
    assert data["parts"]["body"] == {"part": "body", "params": {"thick": 5.0}, "base": False, "features": [], "tip": None}
    code, data = run(capsys, "feature", "list", "demo", "body")
    assert code == cli.OK and data["part"] == "body" and data["features"] == []


def test_add_sketch_then_pad_builds_and_journals_one_step_each(body, demo, capsys):
    code, data = run(capsys, "feature", "add", "demo", "body", "Sketch", "Sketch", "support=XY")
    assert code == cli.OK and data["built"] is False           # only a sketch: nothing to build yet
    code, data = run(capsys, "feature", "add", "demo", "body", "Pad", "Pad", "profile=Sketch", "length=6")
    assert code in (cli.OK, cli.FAIL, cli.UNCHECKED) and data["built"] is True, data
    assert [f["name"] for f in data["doc"]["features"]] == ["Sketch", "Pad"] and data["doc"]["tip"] == "Pad"
    assert data["doc"]["features"][1]["length"] == 6
    steps = [e["name"] for e in un.load(demo)["undo"]]
    assert steps == ["New Sketch", "Make Pad"]
    log = (demo / ".cad" / "log.jsonl").read_text()
    assert '"cmd": "feature add"' in log


def test_set_names_the_step_as_freecads_property_editor(body, demo, capsys):
    _sketch_and_pad(capsys)
    code, data = run(capsys, "feature", "set", "demo", "body", "Pad", "length=8")
    assert data["doc"]["features"][1]["length"] == 8
    assert un.load(demo)["undo"][-1]["name"] == "Edit Pad.Length"
    run(capsys, "feature", "set", "demo", "body", "Pad", "length=9", "reversed=true")
    assert un.load(demo)["undo"][-1]["name"] == "Edit Pad.Length..."
    assert un.load(demo)["undo"][-1]["cmd"] == "cad feature set demo body Pad length=9 reversed=true"


def test_a_change_that_breaks_the_body_is_put_back(body, demo, capsys):
    _sketch_and_pad(capsys)
    before = body.read_text()
    n = len(un.load(demo)["undo"])
    code, data = run(capsys, "feature", "set", "demo", "body", "Pad", "length=0")
    assert code == cli.FAIL and "Length too small" in data["error"] and "as it was" in data["error"]
    assert body.read_text() == before and len(un.load(demo)["undo"]) == n


def test_the_layers_refusal_is_a_usage_error_and_the_file_stays(body, demo, capsys):
    _sketch_and_pad(capsys)
    before = body.read_text()
    code, data = run(capsys, "feature", "delete", "demo", "body", "Sketch")
    assert code == cli.USAGE and data["error"] == "Sketch is used by Pad"
    assert body.read_text() == before


def test_rename_move_tip_and_delete(body, demo, capsys):
    _sketch_and_pad(capsys)
    run(capsys, "feature", "add", "demo", "body", "Sketch", "Sketch001", "support=XZ")
    code, data = run(capsys, "feature", "add", "demo", "body", "Pocket", "Pocket", "profile=Sketch001",
                     "type1=ThroughAll", "--after", "Sketch001")
    assert [f["name"] for f in data["doc"]["features"]] == ["Sketch", "Pad", "Sketch001", "Pocket"]
    code, data = run(capsys, "feature", "rename", "demo", "body", "Sketch001", "Profile")
    assert data["doc"]["features"][3]["profile"] == "Profile"
    assert un.load(demo)["undo"][-1]["name"] == "Rename Sketch001.Label"
    code, data = run(capsys, "feature", "move", "demo", "body", "Profile", "--first")
    assert [f["name"] for f in data["doc"]["features"]][0] == "Profile"
    assert un.load(demo)["undo"][-1]["name"] == "Move a feature inside body"
    code, data = run(capsys, "feature", "tip", "demo", "body", "Pad")
    assert data["doc"]["tip"] == "Pad" and un.load(demo)["undo"][-1]["name"] == "Move tip to selected feature"
    code, data = run(capsys, "feature", "delete", "demo", "body", "Pocket", "Profile")
    assert code != cli.USAGE and [f["name"] for f in data["doc"]["features"]] == ["Sketch", "Pad"]
    assert un.load(demo)["undo"][-1]["name"] == "Delete"
    code, _ = run(capsys, "feature", "move", "demo", "body", "Pad")
    assert code == cli.USAGE                                  # where to: --after or --first


def test_apply_runs_several_ops_as_one_step_and_undo_takes_them_back(body, demo, capsys):
    ops = [{"op": "add", "feature": {"name": "Sketch", "type": SKETCH, "support": "XY"}},
           {"op": "add", "feature": {"name": "Pad", "type": PAD, "profile": "Sketch", "length": 4.0}, "after": "Sketch"}]
    code, data = run(capsys, "feature", "apply", "demo", "body", "--ops", json.dumps(ops))
    assert data["step"] == "Make Pad" and len(un.load(demo)["undo"]) == 1
    code, _ = run(capsys, "undo", "demo")
    assert code == cli.OK and FakeLayer().read(body)["features"] == []
    code, _ = run(capsys, "redo", "demo")
    assert [f["name"] for f in FakeLayer().read(body)["features"]] == ["Sketch", "Pad"]
    code, data = run(capsys, "feature", "apply", "demo", "body", "--name", "Edit Pad", "--ops",
                     json.dumps([{"op": "set", "name": "Pad", "props": {"length": 7.0}}]))
    assert data["step"] == "Edit Pad" and un.load(demo)["undo"][-1]["name"] == "Edit Pad"
    code, data = run(capsys, "feature", "apply", "demo", "body", "--ops", "not json")
    assert code == cli.USAGE and "JSON" in data["error"]


def test_new_writes_an_empty_body_module_and_undo_removes_it(demo, fake, capsys):
    code, data = run(capsys, "feature", "new", "demo", "bracket")
    path = demo / "parts" / "bracket.py"
    assert code == cli.OK and path.exists()
    src = path.read_text()
    assert "FEATURES = []" in src and "return Body(FEATURES, p)" in src and "/home/" not in src
    assert data["doc"]["features"] == [] and data["doc"]["base"] is False
    assert un.load(demo)["undo"][-1]["name"] == "Add a Body"
    assert run(capsys, "feature", "new", "demo", "bracket")[0] == cli.USAGE      # already there
    assert run(capsys, "feature", "new", "demo", "9lives")[0] == cli.USAGE       # not a module name
    run(capsys, "undo", "demo")
    assert not path.exists()


def test_without_the_layer_the_commands_say_not_built(demo, capsys, monkeypatch):
    def missing():
        raise ModuleNotFoundError("No module named 'cad_agent.feature_edit'", name="cad_agent.feature_edit")
    monkeypatch.setattr(serve, "feature_layer", missing)
    code, data = run(capsys, "feature", "list", "demo", "plate")
    assert code == cli.USAGE and data.get("not_built") and "feature_edit" in data["error"]


def test_step_names_follow_freecads_transactions():
    assert featurecmd.name_of([{"op": "add", "feature": {"type": POCKET}}], {}) == "Make Pocket"
    assert featurecmd.name_of([{"op": "set", "name": "Pad", "props": {"up_to_face": "x"}}], {}) == "Edit Pad.UpToFace"
    assert featurecmd._camel("length2") == "Length2" and featurecmd._camel("type1") == "Type"


# ── the server ───────────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def server(demo, monkeypatch):
    bench = serve.Bench([demo.parent], runner=inproc)
    events = []
    monkeypatch.setattr(bench, "broadcast", lambda e: events.append(e) or 0)
    call, scheduled, stop = serving(bench, monkeypatch)
    yield call, scheduled, events
    stop()


def test_get_features_of_one_part_and_of_all(server, body):
    call, _, _ = server
    code, raw = call("/api/demo/features/body")
    r = json.loads(raw)
    assert code == 200 and r["exit"] == cli.OK and r["data"]["features"] == [] and r["data"]["base"] is False
    code, raw = call("/api/demo/features")
    r = json.loads(raw)
    assert set(r["data"]["parts"]) == {"block", "body", "plate"}
    code, raw = call("/api/nope/features")
    assert code == 404


def test_post_features_is_one_undo_step_marked_ui_then_a_check(server, body, demo):
    call, scheduled, events = server
    ops = [{"op": "add", "feature": {"name": "Sketch", "type": SKETCH, "support": "XY"}},
           {"op": "add", "feature": {"name": "Pad", "type": PAD, "profile": "Sketch", "length": 5.0}, "after": "Sketch"}]
    code, raw = call("/api/demo/features/body", {"ops": ops})
    r = json.loads(raw)
    assert code == 200 and r["data"]["doc"]["tip"] == "Pad", r
    entry = un.load(demo)["undo"][-1]
    assert entry["name"] == "Make Pad" and entry["by"] == "ui"
    assert ("demo", "check") in scheduled
    assert {"type": "features", "slug": "demo", "part": "body"} in events
    # the page's Undo is the same journal
    code, raw = call("/api/undo", {"slug": "demo"})
    assert json.loads(raw)["exit"] == cli.OK and FakeLayer().read(body)["features"] == []


def test_post_features_refusals(server, body):
    call, scheduled, _ = server
    code, raw = call("/api/demo/features/body", {"ops": []})
    assert code == 400
    code, raw = call("/api/demo/features", {"ops": [{"op": "tip", "name": "x"}]})
    assert code == 400
    code, raw = call("/api/demo/features/body", {"ops": [{"op": "delete", "name": "Nope"}]})
    r = json.loads(raw)
    assert code == 200 and r["exit"] == cli.USAGE and r["data"]["error"] == "no feature Nope"
    assert scheduled == []
    code, raw = call("/api/demo/features/body", {"ops": [{"op": "tip", "name": "x"}]}, header=False)
    assert code == 403


def test_an_empty_body_is_left_out_of_the_scene_of_a_project_without_assembly(demo, fake, capsys):
    (demo / "assembly.py").unlink()
    (demo / "parts" / "block.py").unlink()
    assert run(capsys, "feature", "new", "demo", "bracket")[0] == cli.OK
    code, data = run(capsys, "scene", "demo")
    assert code == cli.OK and data["bodies"] == ["plate"], data


def test_the_scene_says_where_each_part_is_drawn(demo, capsys):
    code, _ = run(capsys, "scene", "demo")
    scene = json.loads((demo / "out" / "scene.json").read_text())
    for b in scene["bodies"]:
        m = b["matrix"]
        assert len(m) == 16 and m[12:] == [0.0, 0.0, 0.0, 1.0]


# ── the real part-file layer (cad_agent/feature_edit.py) behind the same seam ───────────────────

def test_a_body_from_nothing_through_the_real_layer(demo, capsys):
    """New Body, a sketch, a Pad, a Pocket, the Tip and undo, with feature_edit.py and feature.py doing the work."""
    assert run(capsys, "feature", "new", "demo", "Body")[0] == cli.OK
    rect = [{"type": "LineSegment", "start": a, "end": b, "construction": False}
            for a, b in [([0, 0], [40, 0]), ([40, 0], [40, 20]), ([40, 20], [0, 20]), ([0, 20], [0, 0])]]
    ops = [{"op": "add", "feature": {"name": "Sketch", "type": SKETCH, "support": "XY", "geometry": rect, "constraints": []}},
           {"op": "add", "feature": {"name": "Pad", "type": PAD, "profile": "Sketch", "length": 5.0}}]
    code, data = run(capsys, "feature", "apply", "demo", "Body", "--ops", json.dumps(ops))
    assert data.get("built") is True, data
    assert [f["name"] for f in data["doc"]["features"]] == ["Sketch", "Pad"]
    circle = [{"type": "Circle", "center": [20, 10], "radius": 4, "construction": False}]
    ops = [{"op": "add", "feature": {"name": "Sketch001", "type": SKETCH, "support": "XY", "attachment_offset": [0, 0, 5],
                                     "geometry": circle, "constraints": []}},
           {"op": "add", "feature": {"name": "Pocket", "type": POCKET, "profile": "Sketch001", "type1": "ThroughAll"}}]
    code, data = run(capsys, "feature", "apply", "demo", "Body", "--ops", json.dumps(ops))
    assert data.get("built") is True, data
    assert data["doc"]["features"][-1]["type1"] == "ThroughAll" and data["doc"]["tip"] == "Pocket"
    code, data = run(capsys, "feature", "set", "demo", "Body", "Pad", "length=8")
    assert data["doc"]["features"][1]["length"] == 8 and un.load(demo)["undo"][-1]["name"] == "Edit Pad.Length"
    code, data = run(capsys, "feature", "tip", "demo", "Body", "Pad")
    assert data["doc"]["tip"] == "Pad"
    before = (demo / "parts" / "Body.py").read_text()
    code, data = run(capsys, "feature", "set", "demo", "Body", "Pad", "length=0")
    assert code in (cli.FAIL, cli.USAGE) and (demo / "parts" / "Body.py").read_text() == before
    assert run(capsys, "undo", "demo")[0] == cli.OK              # the Tip back on the Pocket
    assert run(capsys, "feature", "list", "demo", "Body")[1]["tip"] == "Pocket"
