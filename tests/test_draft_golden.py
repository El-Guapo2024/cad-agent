"""FreeCAD's Draft Python (cad_agent/fcdraft, vendored unchanged) over the stand-ins, held to FreeCAD 26.3
(tests/golden/draft, make.py): each case's objects, their shapes' type, size, box and vertices."""
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent / "golden" / "draft"
FC = json.loads((HERE / "freecad.json").read_text())


def _load(name):
    spec = importlib.util.spec_from_file_location(f"draft_golden_{name}", HERE / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CASES = _load("cases").CASES
record = _load("record").record


def _run(script):
    from cad_agent import draft_runtime
    draft_runtime.activate()
    import FreeCAD as App
    import Draft
    doc = App.newDocument("Unnamed")
    ns = {"App": App, "Draft": Draft, "V": App.Vector, "P": App.Placement, "R": App.Rotation, "doc": doc}
    exec(script, ns)
    doc.recompute()
    out = record(doc)
    App.closeDocument(doc.Name)
    return out


def _close(a, b, tol=1e-6):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], tol) for k in a)
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= tol * max(1.0, abs(b))
    return a == b


@pytest.mark.parametrize("name", sorted(CASES))
def test_draft_case(name):
    want = FC[name]
    assert not (isinstance(want, dict) and "error" in want), want
    ours = _run(CASES[name])
    assert [o["name"] for o in ours] == [o["name"] for o in want]
    for o, w in zip(ours, want):
        assert _close(o, w), f"{o['name']}:\n  ours    {o}\n  FreeCAD {w}"
