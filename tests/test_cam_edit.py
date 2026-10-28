"""cam/<Job>.py edited by cad_agent/cam_edit.py and `cad cam`: FreeCAD's commands give the names the file records (the
same names freecadcmd gives, tests/golden/cam), untouched entries keep their text, each change is one undo step."""
import importlib.util
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "feature_plate"
GOLDEN = REPO / "tests" / "golden" / "cam"
_spec = importlib.util.spec_from_file_location("cam_edit_cases", GOLDEN / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    from cad_agent import cam_runtime
    try:
        cam_runtime.activate()
    except cam_runtime.CamUnavailable as e:
        pytest.skip(str(e))
    from cad_agent import state as st
    monkeypatch.setattr(st, "ROOT", tmp_path)
    shutil.copytree(FIXTURE, tmp_path / "feature_plate")
    return tmp_path / "feature_plate"


def test_commands_give_freecads_names(proj):
    from cad_agent import cam_edit as E
    E.apply(proj, "Job", [{"op": "new_job", "parts": ["plate"]}], recompute=False)
    E.apply(proj, "Job", [{"op": "op", "type": "Profile"},
                          {"op": "op", "type": "PocketShape", "base": [["plate", ["Face17"]]]},
                          {"op": "op", "type": "Drilling", "base": [["plate", ["Face7", "Face8", "Face9", "Face10"]]]},
                          {"op": "op", "type": "MillFace", "base": [["plate", ["Face5"]]]},
                          {"op": "dressup", "type": "DressupTag", "base": "Profile"},
                          {"op": "dressup", "type": "DressupDogbone", "base": "Pocket_Shape"}], recompute=False)
    got = [(e.kind, e.name, e.props) for e in E.load(proj, "Job")]
    want = [(k, n, {a: (list(b) if isinstance(b, tuple) else b) for a, b in p.items()})
            for k, n, p in _cases.CASES["plate_default"]["jobs"]["Job"]]
    norm = [(k, n, {a: [list(x) for x in b] if a == "Base" and isinstance(b, list) else b for a, b in p.items()})
            for k, n, p in got]
    want = [(k, n, {a: [list(x) for x in b] if a == "Base" and isinstance(b, list) else b for a, b in p.items()})
            for k, n, p in want]
    assert norm == want


def test_tool_and_set_keep_untouched_text(proj):
    from cad_agent import cam_edit as E
    E.apply(proj, "Job", [{"op": "new_job", "parts": ["plate"]}], recompute=False)
    path = proj / "cam" / "Job.py"
    path.write_text(path.read_text().replace('CAM.Job("Job", Model=["plate"]),',
                                             'CAM.Job("Job", Model=["plate"]),   # the plate'))
    out = E.apply(proj, "Job", [{"op": "tool", "bit": "3.175mm_Endmill", "props": {"HorizFeed": "600 mm/min"}},
                                {"op": "op", "type": "Profile", "props": {"ToolController": "TC__3_175mm_Endmill"}},
                                {"op": "set", "name": "Profile", "props": {"StepDown": "2 mm",
                                                                           "ExpressionEngine": {"StepDown": None}}}])
    text = path.read_text()
    assert "# the plate" in text
    assert 'CAM.ToolBit("_3_175mm_Endmill", Bit="3.175mm_Endmill")' in text
    assert 'CAM.ToolController("TC__3_175mm_Endmill", Tool="_3_175mm_Endmill", HorizFeed="600 mm/min")' in text
    prof = next(o for o in out["result"]["objects"] if o["name"] == "Profile")
    step = next(p for p in prof["props"] if p["name"] == "StepDown")
    assert step["value"]["value"] == 2.0 and step["expression"] is None
    assert len(prof["commands"]) > 10


def test_delete_refuses_a_used_object(proj):
    from cad_agent import cam_edit as E
    E.apply(proj, "Job", [{"op": "new_job", "parts": ["plate"]}, {"op": "op", "type": "Profile"},
                          {"op": "dressup", "type": "DressupTag", "base": "Profile"}], recompute=False)
    with pytest.raises(E.CamEditError, match="used by DressupTag"):
        E.apply(proj, "Job", [{"op": "delete", "name": "Profile"}], recompute=False)


def test_cli_steps_and_post(proj, capsys):
    from cad_agent import cli
    from cad_agent import undo as un
    root = str(proj.parent)
    assert cli.main(["--projects", root, "cam", "new", "feature_plate", "plate"]) == 0
    assert cli.main(["--projects", root, "cam", "op", "feature_plate", "Job", "Drilling",
                     "--base", "plate:Face7,Face8"]) == 0
    assert cli.main(["--projects", root, "cam", "post", "feature_plate", "Job", "--post", "grbl"]) == 0
    gcode = (proj / "out" / "cam" / "Job.nc").read_text()
    assert "(Post Processor: grbl_post)" in gcode and "G81" in gcode
    assert [s["name"] for s in un.load(proj)["undo"]][-2:] == ["Create Job", "Create Drilling"]
