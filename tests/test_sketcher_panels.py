"""The Sketcher's constraint states as the task panel edits them (ui/src/sketchpanels.tsx), against FreeCAD.

A constraint may be deactivated (SketchObject.setActive: the solver leaves it out), put in the other virtual space
(setVirtualSpace: drawn only while the view shows that space), and have its value bound to an expression over the
part's PARAMS. The part file writes them as Constraint(..., active=False, virtual_space=True) and a string value;
cad_agent/feature_edit.py reads and rewrites them, and the solver (cad_agent/planegcs.py, the WebAssembly build the
page runs is the same code) gives FreeCAD's answers for them: tests/golden/sketcher_panels/freecad.json, made by
make.py there with freecadcmd 26.3 (3160daf1e2b6).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cad_agent import feature as F
from cad_agent import feature_edit as E

ROOT = Path(__file__).resolve().parent
GOLDEN = json.loads((ROOT / "golden" / "sketcher_panels" / "freecad.json").read_text())
PLATE = ROOT / "fixtures" / "feature_plate" / "parts" / "plate.py"
UI = ROOT.parent / "ui" / "src"


@pytest.fixture
def plate(tmp_path):
    p = tmp_path / "plate.py"
    shutil.copy(PLATE, p)
    return p


def test_part_file_round_trip(plate):
    d = E.read(plate)
    cons = [dict(c) for c in d["features"][0]["constraints"]]
    cons[4] = dict(cons[4], active=False)                         # Horizontal 0, deactivated
    cons[5] = dict(cons[5], virtual_space=True)                   # Horizontal 2, in the other virtual space
    cons[11] = dict(cons[11], value=20.0, expr="depth + 0")       # DistanceY bound to an expression
    E.apply(plate, [{"op": "set", "name": "Sketch", "props": {"constraints": cons}}])
    src = plate.read_text()
    assert 'Constraint("Horizontal", 0, active=False),' in src
    assert 'Constraint("Horizontal", 2, virtual_space=True),' in src
    assert 'Constraint("DistanceY", 1, 1, 1, 2, "depth + 0"),' in src
    back = E.read(plate)["features"][0]["constraints"]
    assert back[4] == {"type": "Horizontal", "args": [0], "driving": True, "name": "", "active": False}
    assert back[5] == {"type": "Horizontal", "args": [2], "driving": True, "name": "", "virtual_space": True}
    assert back[11]["value"] == "depth + 0" and "active" not in back[11]
    # and back again: the defaults leave no keyword behind
    back[4].pop("active")
    back[5].pop("virtual_space")
    E.apply(plate, [{"op": "set", "name": "Sketch", "props": {"constraints": back}}])
    assert "active=" not in plate.read_text() and "virtual_space=" not in plate.read_text()


def test_constraint_keywords():
    c = F.Constraint("DistanceX", 0, 1, 0, 2, 30.0, name="w", driving=False, active=False, virtual_space=True)
    assert (c.active, c.virtual_space) == (False, True)
    assert repr(c) == "Constraint('DistanceX', 0, 1, 0, 2, 30.0, name='w', driving=False, active=False, virtual_space=True)"
    assert repr(F.Constraint("Horizontal", 0)) == "Constraint('Horizontal', 0)"


def _sketch(case, calls=()):
    """A golden case as the solver's sketch, with its setActive / setVirtualSpace / setDriving / toggles applied."""
    cons = []
    for k in case["constraints"]:
        t, *a = k
        dim = t in F.DIMENSIONAL
        cons.append({"type": t, "args": a[:-1] if dim else a, **({"value": a[-1]} if dim else {})})
    for name, *args in calls:
        ids = args[0] if isinstance(args[0], list) else [args[0]]
        for i in ids:
            c = cons[i]
            if name == "setActive":
                c["active"] = args[1]
            elif name == "toggleActive":
                c["active"] = not c.get("active", True)
            elif name == "setDriving":
                c["driving"] = args[1]
            elif name in ("setVirtualSpace", "toggleVirtualSpace"):
                pass                                               # nothing the solver sees
    return {"geometry": [dict(g) for g in case["geometry"]], "constraints": cons}


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_solver_leaves_inactive_constraints_out(case):
    planegcs = pytest.importorskip("cad_agent.planegcs")
    try:
        r = planegcs.solve(_sketch(case, case["calls"]))
    except planegcs.PlaneGCSNotBuilt as e:
        pytest.skip(str(e))
    want = GOLDEN["solve"][case["name"]]
    assert r["status_code"] == want["status"]
    assert r["dof"] == want["dof"]
    assert [i + 1 for i in r["conflicting"]] == want["conflicting"]
    assert [i + 1 for i in r["redundant"]] == want["redundant"]
    geo = [v for g in r["stored_geometry"] for v in (*g["start"], *g["end"])]
    assert geo == pytest.approx([v for g in want["geometry"] for v in g], abs=1e-9)


def test_part_file_solve_skips_inactive():
    """Sketch.solved(): an inactive constraint is not one the geometry has to satisfy."""
    case = next(c for c in GOLDEN["cases"] if c["name"] == "conflict-inactive")
    geo = [F.LineSegment(tuple(g["start"]), tuple(g["end"])) for g in case["geometry"]]
    cons = [F.Constraint(*k) for k in case["constraints"]]
    cons[10] = F.Constraint(*case["constraints"][10], active=False)
    sk = F.Sketch("S", "XY", geo, cons)
    assert sk.unsatisfied() == []
    assert sk.as_dict()["constraints"][10]["active"] is False


def test_panel_messages_are_freecads():
    """The SketchObject errors the panel reports (renameConstraint's duplicate), as FreeCAD raises them."""
    rename = GOLDEN["api"]["rename"]["calls"]
    assert rename[1] == {"ok": False, "error": "ValueError", "message": "Duplicate constraint not allowed"}
    # renameConstraint itself takes any non-empty name: the GUI's checkConstraintName refuses what is no identifier
    assert rename[2]["ok"] and rename[3]["ok"]
    src = (UI / "sketchpanels.tsx").read_text()
    assert "Duplicate constraint not allowed" in src
    assert "Invalid constraint name (must only contain alphanumericals and underscores, and must not start with digit)" in src
    assert GOLDEN["api"]["toggle-driving"]["calls"][0]["message"].replace(": 0", ": ") in (UI / "sketchcons.ts").read_text()
