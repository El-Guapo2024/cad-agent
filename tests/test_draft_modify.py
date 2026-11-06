"""cad_agent.draft_modify makes of a part file what FreeCAD's own Draft.move / rotate / scale / offset make of the same
document (tests/golden/draft_modify: cases.py, freecad.json from make.py in freecadcmd 26.3): every object's part-file
properties after the steps, each step applied through the editor (feature_edit.apply), as `cad feature draft` does.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from cad_agent import draft_modify as M
from cad_agent import feature as F
from cad_agent import feature_attach as FA
from cad_agent import feature_edit as E
from cad_agent import feature_edit_part as EP

GOLDEN = Path(__file__).parent / "golden" / "draft_modify"
_spec = importlib.util.spec_from_file_location("draft_modify_cases", GOLDEN / "cases.py")
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)
CASES = _m.CASES
FC = json.loads((GOLDEN / "freecad.json").read_text())
REFUSED = {"scale_polygon"}            # Draft.scale makes a plain Part::FeaturePython of a polygon: no part-file object


def _run(tmp_path, case):
    p = tmp_path / "doc.py"
    p.write_text(EP.new_document("doc", "petg", "fdm"))
    E.apply(p, [{"op": "add", "feature": o.as_dict()} for o in case["objects"]])
    for op, names, kw in case["steps"]:
        mod, feats, params, base, objects = FA._load(p)
        ops = M.modify(objects, params, names, op, kw.get("vector"), kw.get("angle"), kw.get("center"),
                       kw.get("axis"), kw.get("radius"), kw.get("copy", False))
        E.apply(p, ops)
    return {o.name: o for o in FA._load(p)[4]}


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return a == pytest.approx(b, abs=1e-7)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


@pytest.mark.parametrize("name", sorted(set(CASES) - REFUSED))
def test_same_properties_as_freecads_draft(tmp_path, name):
    got = _run(tmp_path, CASES[name])
    want = FC[name]
    assert sorted(got) == sorted(want)
    for n, props in want.items():
        o = got[n]
        for k, v in props.items():
            ours = getattr(o, k)
            if k == "placement" and ours is None:
                ours = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            if k == "placement":        # yaw-pitch-roll of the same rotation can differ by a turn: compare the matrix
                from cad_agent import attacher as A
                a, b = A.Placement.from_offset(ours), A.Placement.from_offset(v)
                assert a.pos == pytest.approx(b.pos, abs=1e-7), (n, k, ours, v)
                assert [c for r in a.rot.matrix() for c in r] == pytest.approx([c for r in b.rot.matrix() for c in r], abs=1e-9), (n, k, ours, v)
                continue
            assert _same(ours, v), (n, k, ours, v)


def test_a_scale_freecad_makes_a_plain_shape_of_is_refused(tmp_path):
    with pytest.raises(F.FeatureError, match="plain Part::FeaturePython"):
        _run(tmp_path, CASES["scale_polygon"])
