"""The Sketcher's solver (ui/planegcs: FreeCAD's PlaneGCS and a port of its Sketch.cpp) against FreeCAD.

tests/golden/sketcher/freecad.json holds FreeCAD 26.3's answers (3160daf1e2b6) for 971 sketches, made by
tests/golden/sketcher/make.py in a Sketcher::SketchObject: solve()'s status, the DoF, the conflicting,
redundant, partially redundant and malformed constraints, the geometry and every constraint's value
after solving and after each drag (moveGeometry). Both builds are held to them:

- the native library, through cad_agent/planegcs.py. If it is not built, the test builds it with
  ui/planegcs/build.sh native, which needs Eigen 5.0.0 (EIGEN_DIR or PLANEGCS_TOOLCHAIN; CI downloads
  it) and Boost's headers; without them the native tests are skipped, and say why.
- the WebAssembly build committed in ui/planegcs/dist, run by Node (skipped without node).

Geometry and values must agree to 1e-9 relative (built with Eigen 5.0.0, as FreeCAD is, the native
build agrees bit for bit on this machine). The cases make.py marks rounding-sensitive are those whose
answer FreeCAD itself moves by more than 1e-9 when the input moves by one ulp; there an arithmetic that
rounds differently in the last bit may land elsewhere (the wasm build's libm, musl, is not glibc), so
only the diagnosis (status, DoF and the constraint lists) is held to FreeCAD's. FreeCAD's own answer
for an under-constrained sketch depends on the order of its parameters in memory; make.py records it
with them in creation order (bump_malloc.c), the order the port always uses.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "sketcher"
spec = importlib.util.spec_from_file_location("sketcher_make", GOLDEN / "make.py")
make = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make)

CASES = json.loads((GOLDEN / "freecad.json").read_text())
DIAGNOSIS = ("status", "dof", "conflicting", "redundant", "partially_redundant", "malformed")


def _native():
    from cad_agent import planegcs
    if planegcs.available():
        return planegcs, None
    if not (os.environ.get("EIGEN_DIR") or os.environ.get("PLANEGCS_TOOLCHAIN")):
        return None, ("the native sketch solver is not built and Eigen 5.0.0 is not at hand to build it: "
                      "set EIGEN_DIR (or PLANEGCS_TOOLCHAIN) and run ui/planegcs/build.sh native")
    r = subprocess.run(["bash", str(ROOT / "ui" / "planegcs" / "build.sh"), "native"], capture_output=True, text=True)
    if r.returncode != 0 or not planegcs.available():
        return None, f"ui/planegcs/build.sh native failed:\n{r.stderr[-2000:]}"
    return planegcs, None


@pytest.fixture(scope="module")
def native():
    lib, why = _native()
    if lib is None:
        pytest.skip(why)
    return lib


def check(answers, label):
    bad, diagnosis = [], []
    for case, me in zip(CASES, answers):
        fc = case["freecad"]
        diffs = make.compare(case, fc, me)
        if not diffs:
            continue
        if case["rounding_sensitive"] and "error" not in fc and "error" not in me:
            d = [k for k in DIAGNOSIS if fc[k] != me[k]]
            if d:
                diagnosis.append(f"{case['name']}: {d}")
            continue
        bad.append(case["name"] + "\n    " + "\n    ".join(diffs[:6]))
    assert not bad, f"{label}: {len(bad)} sketches differ from FreeCAD:\n" + "\n".join(bad[:20])
    assert not diagnosis, f"{label}: diagnosis differs:\n" + "\n".join(diagnosis[:20])


def test_native_agrees_with_freecad(native):
    check([make.ours(case) for case in CASES], "native")


def test_native_is_exact_where_it_can_be(native):
    # With Eigen 5.0.0 and glibc, FreeCAD's own build, every answer is FreeCAD's to the bit. Another libm
    # or CPU may round sin, cos and atan2 differently in the last bit, so this one only counts.
    exact = sum(not make.compare(c, c["freecad"], make.ours(c), tol=0.0) for c in CASES)
    assert exact >= len(CASES) * 0.75, f"only {exact} of {len(CASES)} sketches agree with FreeCAD bit for bit"


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed: the WebAssembly build is not checked")
def test_wasm_agrees_with_freecad():
    r = subprocess.run(["node", str(GOLDEN / "ours_wasm.mjs"), str(GOLDEN / "freecad.json")],
                       capture_output=True, text=True, check=True, cwd=ROOT)
    check(json.loads(r.stdout), "wasm")


def test_wasm_size():
    size = (ROOT / "ui" / "planegcs" / "dist" / "planegcs.wasm").stat().st_size
    assert size < 1_000_000, f"planegcs.wasm is {size} bytes"


# ─── the Python API ─────────────────────────────────────────────────────────

def rectangle(w=20.0, h=8.0):
    pts = [(0, 0), (10, 1), (11, 6), (0, 5)]
    geo = [{"type": "LineSegment", "start": list(pts[i]), "end": list(pts[(i + 1) % 4])} for i in range(4)]
    cons = [{"type": "Coincident", "args": [i, 2, (i + 1) % 4, 1]} for i in range(4)]
    cons += [{"type": "Horizontal", "args": [0]}, {"type": "Horizontal", "args": [2]},
             {"type": "Vertical", "args": [1]}, {"type": "Vertical", "args": [3]}]
    return {"geometry": geo, "constraints": cons}


def test_solve_rectangle(native):
    sk = rectangle()
    sk["constraints"] += [{"type": "Coincident", "args": [0, 1, -1, 1]},
                          {"type": "DistanceX", "args": [0], "value": 20.0},
                          {"type": "DistanceY", "args": [1], "value": 8.0},
                          {"type": "Distance", "args": [0, 1, 1, 2], "value": 1.0, "driving": False}]
    r = native.solve(sk)
    assert r["status"] == "solved" and r["dof"] == 0 and r["fully_constrained"]
    assert r["geometry"][1] == {"type": "LineSegment", "start": [20, 0], "end": [20, 8], "construction": False}
    assert math.isclose(r["constraints"][-1]["value"], math.hypot(20, 8))      # a reference measures
    sk["constraints"].append({"type": "Horizontal", "args": [0]})
    r = native.solve(sk)
    assert r["status"] == "failed" and r["redundant"] == [12]                 # 0-based, as the UI wants
    sk["constraints"][-1] = {"type": "Distance", "args": [2], "value": 30.0}
    r = native.solve(sk)
    assert r["status"] == "conflicting" and 12 in r["conflicting"] and r["status_code"] == -4


def test_python_argument_lists(native):
    # The whole Sketcher.Constraint argument list works too, ints and floats as Python has them.
    sk = {"geometry": [{"type": "Circle", "args": [[1, 2], [0, 0, 1], 3]},
                       {"type": "ArcOfCircle", "args": [[[10, 0], [0, 0, 1], 2], 0.0, 1.5]}],
          "constraints": [["Radius", 0, 4.0], ["Coincident", 0, 3, -1, 1], ["Equal", 0, 1]]}
    r = native.solve(sk)
    assert r["status"] == "solved" and r["dof"] == 4
    c, a = r["geometry"]
    assert c["center"] == [0, 0] and c["radius"] == 4 and math.isclose(a["radius"], 4)
    assert set(a) == {"type", "center", "radius", "start_angle", "end_angle", "construction"}


def test_drag(native):
    sk = rectangle()
    r = native.drag(sk, 0, 1, [[1, 1], [2, 3]])
    assert r["status"] == "solved" and r["geometry"][0]["start"] == [2, 3]
    with native.Sketch(sk) as s:
        s.solve()
        assert s.begin_drag([(1, native.EDGE)])["move_status"] == 0
        for x in range(5):
            r = s.drag_to(12 + x, 3)
        assert r["move_status"] == 0 and r["geometry"][1]["start"][0] == 16
        assert r["stored_geometry"][1]["start"][0] == 10      # temporary moves leave the sketch alone
        s.end_drag()
        r = s.move_geometry([(1, native.EDGE)], (16, 3))
        assert r["stored_geometry"][1]["start"][0] == 16


def test_errors(native):
    with pytest.raises(ValueError, match="invalid index"):
        native.solve({"geometry": [{"type": "Point", "at": [0, 0]}], "constraints": [["Horizontal", 5]]})
    with pytest.raises(ValueError, match="unsupported geometry"):
        native.solve({"geometry": [{"type": "Ellipse"}], "constraints": []})
    r = native.solve({"geometry": [{"type": "LineSegment", "start": [0, 0], "end": [1, 0]}],
                      "constraints": [{"type": "Radius", "args": [0], "value": 2.0}]})
    assert r["status"] == "malformed" and r["malformed"] == [0]


def test_missing_library_says_how_to_build(monkeypatch, tmp_path):
    from cad_agent import planegcs
    monkeypatch.setattr(planegcs, "_LIB", None)
    monkeypatch.setattr(planegcs, "library_paths", lambda: [tmp_path / "nope.so"])
    with pytest.raises(planegcs.PlaneGCSNotBuilt, match="ui/planegcs/build.sh native"):
        planegcs.solve({"geometry": [], "constraints": []})
