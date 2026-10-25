"""The Sketcher's transform operations (ui/src/sketchxform.ts: mirror, copy, clone, move, rectangular array, remove
axes alignment) against FreeCAD.

tests/golden/sketchxform/freecad.json holds what FreeCAD 26.3's SketchObject (3160daf1e2b6) makes of 260 sketches for
one operation each, as the Copy, Clone, Move, Rectangular Array, Symmetry and Remove Axes Alignment tools call them
from Python (tests/golden/sketchxform/make.py wrote it with freecadcmd): the sketch before (as FreeCAD solved it) and
the geometry, the construction flags and every constraint after. The port, bundled as tests/golden/sketchxform/engine.mjs
(ui/scripts/sketchxform-bundle.sh), runs the same cases under node from the sketch before; the geometry must agree to
1e-9 and the constraints (type, elements, alignment, value, name, driving) exactly.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "sketchxform"
spec = importlib.util.spec_from_file_location("sketchxform_make", GOLDEN / "make.py")
make = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make)

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed: ui/src/sketchxform.ts is not checked")


def test_operations_agree_with_freecad():
    cases = json.loads((GOLDEN / "freecad.json").read_text())
    r = subprocess.run(["node", str(GOLDEN / "ours.mjs"), str(GOLDEN / "freecad.json")], capture_output=True, text=True,
                       check=True, cwd=ROOT)
    bad = []
    for case, me in zip(cases, json.loads(r.stdout)):
        d = make.compare(case, case["freecad"], me)
        if d:
            bad.append(case["name"] + "\n    " + "\n    ".join(d[:4]))
    assert not bad, f"{len(bad)} of {len(cases)} operations differ from FreeCAD:\n" + "\n".join(bad[:15])
    ops = {c["op"][0] for c in cases}
    assert ops == {"symmetric", "copy", "move", "array", "removeAxes"}
    # the refusal (internal geometry without the curve it defines) is among them
    assert any(c["freecad"]["ok"] is not True for c in cases)


@pytest.mark.skipif(not (ROOT / "ui" / "node_modules" / ".bin" / "rolldown").exists(),
                    reason="ui/node_modules is not installed: the bundle is not rebuilt to compare")
def test_engine_is_built_from_the_sources(tmp_path):
    # engine.mjs is ui/src/sketchxform.ts and what it imports, bundled; it must not lag behind them
    out = tmp_path / "engine.mjs"
    subprocess.run([str(ROOT / "ui" / "node_modules" / ".bin" / "rolldown"), "ui/scripts/sketchxform-entry.ts",
                    "--format", "esm", "--file", str(out), "--platform", "neutral"], check=True, capture_output=True, cwd=ROOT)
    assert out.read_text() == (GOLDEN / "engine.mjs").read_text(), \
        "tests/golden/sketchxform/engine.mjs is not what ui/src/sketchxform.ts bundles to: run ui/scripts/sketchxform-bundle.sh"
