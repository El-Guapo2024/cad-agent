"""Writes freecad.json: what FreeCAD's SketchObject does with a constraint's active state, its virtual space,
its name and its driving state, for tests/test_sketcher_panels.py (the Sketcher's task panel, ui/src/sketchpanels.tsx,
and the part file's Constraint(..., active=False, virtual_space=True)).

    python3 tests/golden/sketcher_panels/make.py <freecadcmd>

<freecadcmd> may also come from $FREECADCMD (FreeCAD 26.3, weekly-2026.09.30 at 3160daf1e2b6: its AppImage
extracted, squashfs-root/usr/bin/freecadcmd). Each solve case is a Sketcher::SketchObject made with addGeometry
and addConstraint, then the calls the case names (setActive, setVirtualSpace, toggleActive, toggleVirtualSpace,
setDriving), then solve(): its status, DoF, the conflicting and redundant constraints, the geometry and the
constraints' Value, IsActive, InVirtualSpace and Driving. The API cases record what renameConstraint and
toggleDriving accept and what they raise (the exception's class and message), the names and states after.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

RECT = [{"type": "LineSegment", "start": [0, 0], "end": [30, 0]}, {"type": "LineSegment", "start": [30, 0], "end": [30, 20]},
        {"type": "LineSegment", "start": [30, 20], "end": [0, 20]}, {"type": "LineSegment", "start": [0, 20], "end": [0, 0]}]
RECT_CONS = [["Coincident", 0, 2, 1, 1], ["Coincident", 1, 2, 2, 1], ["Coincident", 2, 2, 3, 1], ["Coincident", 3, 2, 0, 1],
             ["Horizontal", 0], ["Horizontal", 2], ["Vertical", 1], ["Vertical", 3], ["Coincident", 0, 1, -1, 1]]
CASES = [
    # an over-constrained rectangle, and the same with the second width switched off
    {"name": "conflict", "geometry": RECT, "constraints": RECT_CONS + [["DistanceX", 0, 1, 0, 2, 30.0], ["DistanceX", 0, 1, 0, 2, 40.0],
                                                                         ["DistanceY", 1, 1, 1, 2, 20.0]], "calls": []},
    {"name": "conflict-inactive", "geometry": RECT, "constraints": RECT_CONS + [["DistanceX", 0, 1, 0, 2, 30.0], ["DistanceX", 0, 1, 0, 2, 40.0],
                                                                                  ["DistanceY", 1, 1, 1, 2, 20.0]], "calls": [["setActive", 10, False]]},
    # the inactive one is the width the sketch keeps: the other moves it
    {"name": "inactive-first", "geometry": RECT, "constraints": RECT_CONS + [["DistanceX", 0, 1, 0, 2, 30.0], ["DistanceX", 0, 1, 0, 2, 40.0],
                                                                               ["DistanceY", 1, 1, 1, 2, 20.0]], "calls": [["setActive", 9, False]]},
    # an inactive geometric constraint gives back its degree of freedom
    {"name": "inactive-horizontal", "geometry": RECT, "constraints": RECT_CONS, "calls": [["setActive", 4, False]]},
    {"name": "toggle-active-twice", "geometry": RECT, "constraints": RECT_CONS, "calls": [["toggleActive", 5], ["toggleActive", 5], ["toggleActive", 6]]},
    # the virtual space changes nothing the solver sees
    {"name": "virtual-space", "geometry": RECT, "constraints": RECT_CONS + [["DistanceX", 0, 1, 0, 2, 30.0]],
     "calls": [["setVirtualSpace", [4, 9], True], ["toggleVirtualSpace", 4]]},
    {"name": "reference-then-inactive", "geometry": RECT, "constraints": RECT_CONS + [["DistanceX", 0, 1, 0, 2, 30.0], ["DistanceY", 1, 1, 1, 2, 20.0]],
     "calls": [["setDriving", 10, False], ["setActive", 9, False]]},
]
API = [
    {"name": "rename", "constraints": RECT_CONS + [["DistanceX", 0, 1, 0, 2, 30.0]],
     "calls": [["renameConstraint", 9, "width"], ["renameConstraint", 4, "width"], ["renameConstraint", 4, "1x"], ["renameConstraint", 4, "a b"],
               ["renameConstraint", 9, ""], ["renameConstraint", 5, "h"], ["renameConstraint", 20, "far"]]},
    {"name": "toggle-driving", "constraints": RECT_CONS + [["DistanceX", 0, 1, 0, 2, 30.0], ["DistanceX", -1, 1, -2, 1, 0.0]],
     "calls": [["toggleDriving", 0], ["toggleDriving", 9], ["toggleDriving", 9], ["setDriving", 10, False], ["setDriving", 10, True]]},
    {"name": "virtual-api", "constraints": RECT_CONS,
     "calls": [["toggleVirtualSpace", 0], ["setVirtualSpace", [0, 1, 2], True], ["setVirtualSpace", 3, True], ["getVirtualSpace", 1],
               ["toggleVirtualSpace", 40]]},
]

SCRIPT = r'''
import json, sys, traceback
import FreeCAD as App, Part, Sketcher
import os
d = os.environ["FCPANELS_DIR"]
cases, api, out = json.load(open(d + "/cases.json")), json.load(open(d + "/api.json")), d + "/out.json"
def make(doc, c):
    sk = doc.addObject("Sketcher::SketchObject", "S")
    V = lambda p: App.Vector(p[0], p[1], 0)
    for g in c.get("geometry", []):
        sk.addGeometry(Part.LineSegment(V(g["start"]), V(g["end"])), False)
    for k in c["constraints"]:
        sk.addConstraint(Sketcher.Constraint(*k))
    return sk
def state(sk):
    return [{"type": k.Type, "value": k.Value, "active": k.IsActive, "virtual_space": k.InVirtualSpace, "driving": k.Driving, "name": k.Name}
            for k in sk.Constraints]
def call(sk, c):
    try:
        r = getattr(sk, c[0])(*c[1:])
        return {"ok": True, **({"result": r} if isinstance(r, (bool, int, float)) else {})}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "message": str(e)}
res = {"solve": {}, "api": {}}
for c in cases:
    doc = App.newDocument("D")
    if not c.get("geometry"):
        c["geometry"] = []
    sk = make(doc, c)
    calls = [call(sk, x) for x in c["calls"]]
    status = sk.solve()
    res["solve"][c["name"]] = {"status": status, "dof": sk.DoF,
        "conflicting": list(sk.ConflictingConstraints), "redundant": list(sk.RedundantConstraints),
        "geometry": [[g.StartPoint.x, g.StartPoint.y, g.EndPoint.x, g.EndPoint.y] for g in sk.Geometry],
        "constraints": state(sk), "calls": calls}
    App.closeDocument(doc.Name)
for c in api:
    doc = App.newDocument("D")
    c["geometry"] = [{"start": [0, 0], "end": [30, 0]}, {"start": [30, 0], "end": [30, 20]}, {"start": [30, 20], "end": [0, 20]}, {"start": [0, 20], "end": [0, 0]}]
    sk = make(doc, c)
    res["api"][c["name"]] = {"calls": [call(sk, x) for x in c["calls"]], "constraints": state(sk)}
    App.closeDocument(doc.Name)
json.dump(res, open(out, "w"), indent=1)
'''


def main():
    fc = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("FREECADCMD", "")
    if not fc:
        sys.exit("usage: make.py <freecadcmd>")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "run.py").write_text(SCRIPT)
        (t / "cases.json").write_text(json.dumps(CASES))
        (t / "api.json").write_text(json.dumps(API))
        r = subprocess.run([fc, str(t / "run.py")], capture_output=True, text=True, timeout=600,
                           env={**os.environ, "FCPANELS_DIR": str(t)})
        if not (t / "out.json").exists():
            sys.exit(f"freecadcmd wrote nothing:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        res = json.loads((t / "out.json").read_text())
    res = {"about": "FreeCAD 26.3 (3160daf1e2b6), tests/golden/sketcher_panels/make.py", "cases": CASES, "api_cases": API, **res}
    (HERE / "freecad.json").write_text(json.dumps(res, indent=1) + "\n")
    print(f"wrote {HERE / 'freecad.json'}: {len(res['solve'])} solves, {len(res['api'])} API cases")


if __name__ == "__main__":
    main()
