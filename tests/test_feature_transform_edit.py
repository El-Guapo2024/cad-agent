"""The part-file layer (cad_agent/feature_edit.py) reads, writes and edits Mirrored, LinearPattern, PolarPattern,
MultiTransform and the primitives in place, through their feature_kw declarations, without loss."""
import difflib
import importlib.util
import shutil
from pathlib import Path

import pytest

from cad_agent import feature as F
from cad_agent import feature_edit as E
from cad_agent import feature_kw as KW

ROOT = Path(__file__).resolve().parent
PLATE = ROOT / "fixtures" / "feature_plate" / "parts" / "plate.py"
_spec = importlib.util.spec_from_file_location("transform_cases_edit", ROOT / "golden" / "transform" / "cases.py")
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


def _kw_features():
    for case in _cases.CASES.values():
        for f in case["features"]:
            if isinstance(f, KW.KwFeature):
                yield f


def test_every_golden_feature_round_trips():
    """Each KwFeature of the goldens written as the part file writes it, read back: the same properties."""
    n = 0
    for f in _kw_features():
        text = E.kw_src(f)
        src = f"from cad_agent.feature import *\nFEATURES = [\n    {text},\n]\n"
        got = E.read_src(src)["features"][0]
        assert got == f.as_dict(), text
        n += 1
    assert n >= 90


def test_add_a_mirror_writes_one_line_and_the_import(plate):
    before = plate.read_text()
    d = E.apply(plate, [{"op": "add", "feature": {"name": "Mirrored", "type": "PartDesign::Mirrored",
                                                  "originals": ["BorePocket"], "mirror_plane": ["Bore", "V_Axis"]}}])
    after = plate.read_text()
    diff = _diff(before, after)
    assert '+    Mirrored("Mirrored", ["BorePocket"], mirror_plane=("Bore", "V_Axis")),' in diff
    assert any(l.startswith("+from cad_agent.feature import (") and "Mirrored" in l for l in diff)
    m = d["features"][-1]
    assert m == {**F.Mirrored("Mirrored", ["BorePocket"], mirror_plane=("Bore", "V_Axis")).as_dict()}
    assert (m["transform_mode"], m["refine"], m["suppressed_indices"]) == ("Features", True, [])
    assert d["tip"] == "TiePocket"                         # TIP stays as the file has it
    E.apply(plate, [{"op": "tip", "name": "Mirrored"}])
    assert _build(plate).volume > 0


def test_set_writes_in_place_and_a_default_is_left_out(plate):
    E.apply(plate, [{"op": "add", "feature": {"name": "LinearPattern", "type": "PartDesign::LinearPattern",
                                              "originals": ["Holes001"], "direction": "X_Axis", "length": 100,
                                              "occurrences": 2}}])
    line = [l for l in plate.read_text().splitlines() if "LinearPattern(" in l][0]
    assert line.strip() == 'LinearPattern("LinearPattern", ["Holes001"], direction="X_Axis"),'
    E.apply(plate, [{"op": "set", "name": "LinearPattern", "props": {"length": 12.5, "occurrences": 3,
                                                                     "mode": "Spacing"}}])
    line = [l for l in plate.read_text().splitlines() if "LinearPattern(" in l][0]
    assert line.strip() == ('LinearPattern("LinearPattern", ["Holes001"], direction="X_Axis", length=12.5, '
                            'occurrences=3, mode="Spacing"),')
    d = E.apply(plate, [{"op": "set", "name": "LinearPattern", "props": {"mode": "Extent", "length": 100.0}}])
    line = [l for l in plate.read_text().splitlines() if "LinearPattern(" in l][0]
    assert line.strip() == 'LinearPattern("LinearPattern", ["Holes001"], direction="X_Axis", occurrences=3),'
    lp = d["features"][-1]
    assert (lp["occurrences"], lp["occurrences2"], lp["length"], lp["mode"]) == (3, 1, 100.0, "Extent")


def test_references_follow_a_rename_and_hold_a_delete(plate):
    E.apply(plate, [{"op": "add", "feature": {"name": "PolarPattern", "type": "PartDesign::PolarPattern",
                                              "originals": ["Holes001"], "axis": ["Bore", "N_Axis"]}}])
    with pytest.raises(E.FeatureEditError, match="PolarPattern uses it"):
        E.apply(plate, [{"op": "delete", "name": "Holes001"}])
    with pytest.raises(E.FeatureEditError, match="PolarPattern uses it"):
        E.apply(plate, [{"op": "delete", "name": "BorePocket"}, {"op": "delete", "name": "Bore"}])
    d = E.apply(plate, [{"op": "rename", "name": "Holes001", "to": "Corners"},
                        {"op": "rename", "name": "Bore", "to": "BoreSketch"}])
    assert d["features"][-1]["originals"] == ["Corners"]
    assert d["features"][-1]["axis"] == ["BoreSketch", "N_Axis"]
    E.apply(plate, [{"op": "delete", "name": "PolarPattern"}])
    E.apply(plate, [{"op": "delete", "name": "Corners"}])


def test_a_reference_must_come_before(plate):
    with pytest.raises(E.FeatureEditError, match="'TiePocket', which is not before it"):
        E.apply(plate, [{"op": "add", "after": "Pad", "feature": {
            "name": "Mirrored", "type": "PartDesign::Mirrored", "originals": ["TiePocket"],
            "mirror_plane": "YZ_Plane"}}])
    with pytest.raises(E.FeatureEditError, match="spacing is not a property of a LinearPattern"):
        E.apply(plate, [{"op": "add", "feature": {"name": "LP", "type": "PartDesign::LinearPattern", "spacing": 3}}])
    with pytest.raises(E.FeatureEditError, match="transform_mode 'Body'"):
        E.apply(plate, [{"op": "add", "feature": {"name": "LP", "type": "PartDesign::LinearPattern",
                                                  "transform_mode": "Body"}}])


def test_multi_transform_nests_its_transformations(plate):
    feat = {"name": "MultiTransform", "type": "PartDesign::MultiTransform", "originals": ["Holes001"],
            "transformations": [{"name": "Mirror", "type": "PartDesign::Mirrored", "mirror_plane": "YZ_Plane"},
                                {"name": "Linear_Pattern", "type": "PartDesign::LinearPattern",
                                 "direction": "Y_Axis", "length": 4, "occurrences": 2}]}
    d = E.apply(plate, [{"op": "add", "feature": feat}, {"op": "tip", "name": "MultiTransform"}])
    text = plate.read_text()
    assert ('    MultiTransform("MultiTransform", ["Holes001"], transformations=[\n'
            '        Mirrored("Mirror", mirror_plane="YZ_Plane"),\n'
            '        LinearPattern("Linear_Pattern", direction="Y_Axis", length=4),\n'
            '    ]),\n') in text
    mt = d["features"][-1]
    assert [t["name"] for t in mt["transformations"]] == ["Mirror", "Linear_Pattern"]
    assert mt["transformations"][1]["occurrences"] == 2
    assert _build(plate).volume > 0
    # a transformation renamed, a third added: the list rewritten
    subs = mt["transformations"] + [{"name": "Polar_Pattern", "type": "PartDesign::PolarPattern", "axis": "Z_Axis",
                                     "occurrences": 2}]
    d = E.apply(plate, [{"op": "set", "name": "MultiTransform", "props": {"transformations": subs}}])
    assert [t["name"] for t in d["features"][-1]["transformations"]] == ["Mirror", "Linear_Pattern", "Polar_Pattern"]
    with pytest.raises(E.FeatureEditError, match="'Pad' is not a name its transformation can take"):
        E.apply(plate, [{"op": "set", "name": "MultiTransform", "props": {"transformations": [
            {"name": "Pad", "type": "PartDesign::Mirrored", "mirror_plane": "YZ_Plane"}]}}])
    with pytest.raises(E.FeatureEditError, match="no originals"):
        E.apply(plate, [{"op": "set", "name": "MultiTransform", "props": {"transformations": [
            {"name": "M2", "type": "PartDesign::Mirrored", "originals": ["Pad"], "mirror_plane": "YZ_Plane"}]}}])


def test_a_primitive_with_its_placement(plate):
    d = E.apply(plate, [{"op": "add", "feature": {"name": "Cylinder", "type": "PartDesign::SubtractiveCylinder",
                                                  "radius": 2, "height": 20,
                                                  "placement": [[10, 0, -5], [0, 0, 0]]}},
                        {"op": "tip", "name": "Cylinder"}])
    line = [l for l in plate.read_text().splitlines() if "SubtractiveCylinder(" in l and "FEATURES" not in l][-1]
    assert line.strip() == ('SubtractiveCylinder("Cylinder", radius=2, height=20, placement=((10.0, 0.0, -5.0), '
                            '(0.0, 0.0, 0.0))),')
    c = d["features"][-1]
    assert (c["angle"], c["operation"], c["placement"]) == (360.0, "Subtraction", [[10.0, 0.0, -5.0], [0.0, 0.0, 0.0]])
    v = _build(plate).volume
    E.apply(plate, [{"op": "set", "name": "Cylinder", "props": {"radius": "boss_h", "operation": "Subtraction"}}])
    assert 'radius="boss_h"' in plate.read_text()
    assert _build(plate).volume < v
    E.apply(plate, [{"op": "set", "name": "Cylinder", "props": {"placement": None}}])
    assert "placement=" not in [l for l in plate.read_text().splitlines() if "SubtractiveCylinder(\"" in l][0]


def test_the_feature_classes_are_feature_edits_types():
    for kind in ("Mirrored", "LinearPattern", "PolarPattern", "MultiTransform", "AdditiveBox", "SubtractiveWedge"):
        assert E.TYPE_IDS[kind] == f"PartDesign::{kind}" and E.KINDS[f"PartDesign::{kind}"] == kind
    assert len([k for k in E.TYPE_IDS if k.startswith(("Additive", "Subtractive"))]) >= 16


def test_ensure_import_keeps_what_is_there():
    src = '"""doc"""\nfrom cad_agent.feature import (Body, Pad,\n                               Sketch)\n\nX = 1\n'
    out = E.ensure_import(src, {"Mirrored", "Pad"})
    assert out == '"""doc"""\nfrom cad_agent.feature import (Body, Mirrored, Pad, Sketch)\n\nX = 1\n'
    assert E.ensure_import(out, {"Pad"}) == out
    assert E.ensure_import('"""d"""\nX = 1\n', {"Pad"}) == '"""d"""\nfrom cad_agent.feature import (Pad)\nX = 1\n'
