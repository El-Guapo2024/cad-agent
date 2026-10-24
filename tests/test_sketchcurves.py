"""The Sketcher's curve tools (ui/src/sketchbspline.ts, the B-spline and curve-fillet paths of ui/src/sketchops.ts, with
the sketch kernel cad_agent/sketch_kernel.py) against FreeCAD.

tests/golden/sketchcurves/freecad.json holds what FreeCAD 26.3's Sketcher (3160daf1e2b6) makes of 408 sketches for one
curve tool each, done as the tool's command calls SketchObject (tests/golden/sketchcurves/make.py wrote it with
freecadcmd): Geometry to B-spline, Increase/Decrease B-spline degree, Increase/Decrease knot multiplicity, Insert knot,
Join curves, Trim and Split on B-splines, Fillet between curves other than two lines, B-spline by knots, and Carbon
copy (another sketch placed parallel, turned over or refused, as CarbonCopySelection lets it through). The port,
bundled as tests/golden/sketchcurves/engine.mjs (ui/scripts/sketchcurves-bundle.sh), runs the same cases under node,
the kernel's answers given by cad_agent/sketch_kernel.py on the same OCCT as FreeCAD's. Geometry must agree to 1e-9 and
constraints exactly; a fillet's curves, moved by the solver to the fillet's ends in an under-constrained sketch, to
1e-7 (the WebAssembly solver's drag settles within that of FreeCAD's, as tests/golden/sketcher notes).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "sketchcurves"
spec = importlib.util.spec_from_file_location("sketchcurves_make", GOLDEN / "make.py")
make = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make)

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed: ui/src/sketchbspline.ts is not checked")


def test_curve_tools_agree_with_freecad():
    pytest.importorskip("OCP")
    cases = json.loads((GOLDEN / "freecad.json").read_text())
    mine = make.ours(cases)
    bad = []
    for case, me in zip(cases, mine):
        tol = 1e-7 if case["op"][0] == "fillet" else 1e-9
        d = make.compare(case, case["freecad"], me, tol)
        if d:
            bad.append(case["name"] + "\n    " + "\n    ".join(d[:4]))
    assert not bad, f"{len(bad)} of {len(cases)} operations differ from FreeCAD:\n" + "\n".join(bad[:15])
    ops = {c["op"][0] for c in cases}
    assert ops == {"convert", "degree_up", "degree_down", "knot_mult", "insert_knot", "join", "trim", "split", "fillet",
                   "bspline_by_knots", "carbon_copy"}
    # FreeCAD does each of them somewhere (not only refusals)
    done = {c["op"][0] for c in cases if c["freecad"]["ok"] is True}
    assert done == ops


@pytest.mark.skipif(not (ROOT / "ui" / "node_modules" / ".bin" / "rolldown").exists(),
                    reason="ui/node_modules is not installed: the bundle is not rebuilt to compare")
def test_engine_is_built_from_the_sources(tmp_path):
    out = tmp_path / "engine.mjs"
    subprocess.run([str(ROOT / "ui" / "node_modules" / ".bin" / "rolldown"), "ui/scripts/sketchcurves-entry.ts",
                    "--format", "esm", "--file", str(out), "--platform", "neutral"], check=True, capture_output=True, cwd=ROOT)
    assert out.read_text() == (GOLDEN / "engine.mjs").read_text(), \
        "tests/golden/sketchcurves/engine.mjs is not what ui/src/sketchbspline.ts bundles to: run ui/scripts/sketchcurves-bundle.sh"


def test_kernel_command():
    """`cad feature sketchkernel` answers a list of requests, a refusal as {"error"}."""
    pytest.importorskip("OCP")
    from cad_agent import sketch_kernel as K
    line = {"type": "LineSegment", "start": [0.0, 0.0], "end": [3.0, 4.0]}
    out = K.run_all([{"op": "nurbs", "geo": line}, {"op": "degree", "geo": line, "degree": 2}, {"op": "nope"}])
    assert out[0]["geo"]["poles"] == [[0.0, 0.0], [3.0, 4.0]] and out[0]["geo"]["knots"] == [0.0, 5.0]
    assert "error" in out[1] and "error" in out[2]
