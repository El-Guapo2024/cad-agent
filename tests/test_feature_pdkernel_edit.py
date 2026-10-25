"""The part-file layer (cad_agent/feature_edit.py) reads, writes and edits what tests/golden/pdkernel adds: a Pad's and a
Pocket's taper_angle, taper_angle2, operation and start_reference, a Groove's and a Hole's operation and start
reference, and PartDesign::Scaled, in place and without loss; `cad feature add/set` takes them."""
import difflib
import importlib.util
import math
import shutil
from pathlib import Path

import pytest

from cad_agent import feature as F
from cad_agent import feature_edit as E
from cad_agent import feature_kw as KW

ROOT = Path(__file__).resolve().parent
PLATE = ROOT / "fixtures" / "feature_plate" / "parts" / "plate.py"
_spec = importlib.util.spec_from_file_location("pdkernel_cases_edit", ROOT / "golden" / "pdkernel" / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)


@pytest.fixture
def plate(tmp_path):
    p = tmp_path / "plate.py"
    shutil.copy(PLATE, p)
    return p


def _build(path):
    spec = importlib.util.spec_from_file_location(f"part_{path.stem}_{id(path)}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(**mod.PARAMS)


def _diff(a, b):
    return [l for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and l[:3] not in ("+++", "---")]


def _extrude_dict(f):
    d = {"name": f.name, "type": E.TYPE_IDS[f.kind], "profile": f.profile}
    for key, attr in E.EXTRUDE_PROPS.items():
        v = getattr(f, attr)
        d[key] = list(v) if isinstance(v, tuple) else v
    return d


def test_every_golden_feature_round_trips():
    """Each Pad, Pocket and KwFeature of the goldens written as the part file writes it, read back: the same."""
    n = 0
    for case in _cases.CASES.values():
        for f in case["features"]:
            if isinstance(f, KW.KwFeature):
                text, want = E.kw_src(f), f.as_dict()
            elif isinstance(f, (F.Pad, F.Pocket)):
                text, want = E.feature_src(_extrude_dict(f)), _extrude_dict(f)
            else:
                continue
            src = f"from cad_agent.feature import *\nFEATURES = [\n    {text},\n]\n"
            got = E.read_src(src)["features"][0]
            assert got == want, text
            n += 1
    assert n >= 60


def test_set_taper_writes_in_place_and_builds(plate):
    before = plate.read_text()
    v0 = _build(plate).volume
    E.apply(plate, [{"op": "set", "name": "Boss", "props": {"taper_angle": 10}}])
    diff = _diff(before, plate.read_text())
    assert diff == ['-    Pad("Boss", "BossSketch", length="boss_h"),',
                    '+    Pad("Boss", "BossSketch", length="boss_h", taper_angle=10),']
    assert _build(plate).volume > v0                      # a positive taper widens the boss towards its top
    d = E.read(plate)
    boss = next(f for f in d["features"] if f["name"] == "Boss")
    assert (boss["taper_angle"], boss["taper_angle2"], boss["operation"]) == (10, 0.0, "Union")


def test_a_taper_takes_a_params_expression(plate):
    E.apply(plate, [{"op": "set", "name": "Boss", "props": {"taper_angle": "boss_h * 2"}}])
    assert 'taper_angle="boss_h * 2"' in plate.read_text()
    assert _build(plate).volume > 0


def test_pocket_common_keeps_only_what_the_tool_holds(plate):
    E.apply(plate, [{"op": "set", "name": "TiePocket", "props": {"operation": "Common"}}])
    assert 'Pocket("TiePocket", "TieSlot", length=2.0, operation="Common")' in plate.read_text()
    part = _build(plate)
    assert part.volume == pytest.approx(2.0 * (8 * 8 + math.pi * 16), rel=1e-9)   # the slot's 2 mm of material


def test_a_pad_has_no_common(plate):
    with pytest.raises(E.FeatureEditError, match="operation 'Common' is not one of Union"):
        E.apply(plate, [{"op": "set", "name": "Boss", "props": {"operation": "Common"}}])


def test_start_reference_is_written_renamed_and_guarded(plate):
    def boss_top(part):
        return sum(f.area for f in part.faces() if abs(f.center().Z - 10.0) < 1e-6)
    assert boss_top(_build(plate)) == pytest.approx(math.pi * (64 - 16))      # the bore opens the boss's top
    E.apply(plate, [{"op": "set", "name": "BorePocket",
                     "props": {"start_type": "Reference", "start_reference": ["Pad", "Face6"]}}])
    text = plate.read_text()
    assert 'start_type="Reference", start_reference=("Pad", "Face6")' in text
    # now it starts at the plate's top (z 6) and goes 6 mm down, under the boss, whose top is whole again
    assert boss_top(_build(plate)) == pytest.approx(math.pi * 64)
    E.apply(plate, [{"op": "rename", "name": "Pad", "to": "Plate"}])
    assert 'start_reference=("Plate", "Face6")' in plate.read_text()
    E.apply(plate, [{"op": "set", "name": "BorePocket", "props": {"start_reference": ["Boss", "Face2"]}}])
    with pytest.raises(E.FeatureEditError, match="Boss cannot be deleted: .*BorePocket"):
        E.apply(plate, [{"op": "delete", "name": "Boss"}])
    with pytest.raises(E.FeatureEditError, match="its start_reference names 'Boss', which is not before it"):
        E.apply(plate, [{"op": "move", "name": "Boss", "after": "BorePocket"}])


def test_add_a_scaled_writes_one_line_and_the_import(plate):
    before = plate.read_text()
    d = E.apply(plate, [{"op": "add", "feature": {"name": "Scaled", "type": "PartDesign::Scaled",
                                                  "originals": ["BorePocket"], "factor": 0.5, "occurrences": 3}}])
    diff = _diff(before, plate.read_text())
    assert '+    Scaled("Scaled", ["BorePocket"], factor=0.5, occurrences=3),' in diff
    assert any(l.startswith("+from cad_agent.feature import (") and "Scaled" in l for l in diff)
    assert d["features"][-1] == F.Scaled("Scaled", ["BorePocket"], factor=0.5, occurrences=3).as_dict()
    E.apply(plate, [{"op": "tip", "name": "Scaled"}])
    assert _build(plate).volume > 0
    E.apply(plate, [{"op": "set", "name": "Scaled", "props": {"factor": 2.0}}])
    assert 'Scaled("Scaled", ["BorePocket"], occurrences=3),' in plate.read_text()   # back to the default: left out


def test_a_multitransform_takes_a_scaled(plate):
    E.apply(plate, [{"op": "add", "feature": {
        "name": "MultiTransform", "type": "PartDesign::MultiTransform", "originals": ["Holes001"],
        "transformations": [{"name": "Mirror", "type": "PartDesign::Mirrored", "mirror_plane": "YZ_Plane"},
                            {"name": "Scale", "type": "PartDesign::Scaled", "factor": 0.5, "occurrences": 2}]}}])
    text = plate.read_text()
    assert 'Scaled("Scale", factor=0.5)' in text
    E.apply(plate, [{"op": "tip", "name": "MultiTransform"}])
    assert _build(plate).volume > 0


def test_hole_and_groove_take_common_and_a_start_reference():
    hole = F.Hole("Hole", "Top", diameter=6.0, operation="Common", start_type="Reference",
                  start_reference=("Pad", "Face6"))
    groove = F.Groove("Groove", "Notch", operation="Common", start_type="Reference", start_reference="YZ_Plane")
    assert E.kw_src(hole) == ('Hole("Hole", "Top", diameter=6.0, start_type="Reference", operation="Common", '
                              'start_reference=("Pad", "Face6"))')
    for f in (hole, groove):
        got = E.read_src(f"from cad_agent.feature import *\nFEATURES = [\n    {E.kw_src(f)},\n]\n")["features"][0]
        assert got == f.as_dict()
    assert (hole.operation, hole.start_reference) == ("Common", ("Pad", "Face6"))
    assert hole._state.ro >= {"HoleCutDiameter"} and "StartReference" not in hole._state.ro
