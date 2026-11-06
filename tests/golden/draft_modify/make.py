"""Writes freecad.json: each case of cases.py built in FreeCAD 26.3 (feature_part.to_freecad), its steps run with
FreeCAD's own Draft.move / rotate / scale / offset as the GUI commands' lines call them, then every object's part-file
properties (draft_modify._props) recorded.

    $FREECAD/freecadcmd tests/golden/draft_modify/make.py        (from the repository's root)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "draft_modify"))
import FreeCAD as App  # noqa: E402
import Draft  # noqa: E402

from cad_agent import draft_modify as M  # noqa: E402
from cad_agent import feature_draft as D  # noqa: E402
from cad_agent import feature_part as Part  # noqa: E402
from cases import CASES  # noqa: E402

V = lambda s: App.Vector(*[float(c) for c in s.split(",")])     # noqa: E731
kinds = {(c.PROXY[1], c.LINK): c for c in D.OBJECTS.values()}
out = {}
for name, case in CASES.items():
    doc = App.newDocument(name)
    made = Part.to_freecad(case["objects"], doc=doc)
    doc.recompute()
    for op, names, kw in case["steps"]:
        objs = [doc.getObject(n) for n in names]
        if op == "move":
            Draft.move(objs, V(kw["vector"]), copy=kw.get("copy", False))
        elif op == "rotate":
            Draft.rotate(objs, kw["angle"], V(kw.get("center", "0,0,0")), V(kw.get("axis", "0,0,1")), copy=kw.get("copy", False))
        elif op == "scale":
            Draft.scale(objs, V(kw["vector"]), V(kw.get("center", "0,0,0")), copy=kw.get("copy", False))
        else:
            Draft.offset(objs[0], float(kw["radius"]) if "radius" in kw else V(kw["vector"]), copy=kw.get("copy", False))
        doc.recompute()
    res = {}
    for o in doc.Objects:
        px = getattr(o, "Proxy", None)
        cls = kinds.get((getattr(px, "Type", None), bool(getattr(px, "use_link", False))))
        res[o.Name] = ({k: M._plain(v) for k, v in M._props(cls, o).items()} if cls is not None
                       else {"placement": M._plain(M._placement(o.Placement))})
    out[name] = res
    App.closeDocument(doc.Name)
    print(name, sorted(res))
(ROOT / "tests" / "golden" / "draft_modify" / "freecad.json").write_text(json.dumps(out, indent=1) + "\n")
