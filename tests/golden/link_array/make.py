"""Writes freecad.json: each element's Placement of each case of cases.py, as FreeCAD 26.3 computes it.

    $FREECAD/freecadcmd tests/golden/link_array/make.py [CASE]     (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. Each case gets a fresh document with a Part::Feature box and an App::Origin; the
array is made as Part_LinkArray<Kind> makes it (addObject, then LinkedObject), its properties set (a direction or axis
as (Origin, [role])), and the document recomputed.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
sys.path.insert(0, str(ROOT / "tests" / "golden" / "link_array"))

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

from cases import CASES  # noqa: E402

NAMES = {"Part::LinkArrayLinear": "LinearLinkArray", "Part::LinkArrayPolar": "PolarLinkArray"}


def run(type_id, props):
    doc = App.newDocument("Unnamed")
    box = doc.addObject("Part::Feature", "pin")
    box.Shape = Part.makeBox(4, 3, 2)
    origin = doc.addObject("App::Origin", "Origin")
    a = doc.addObject(type_id, NAMES[type_id])
    a.LinkedObject = box
    for k, v in props.items():
        if k in ("Direction", "Direction2", "Axis"):
            v = (origin, [v])
        setattr(a, k, v)
    doc.recompute()
    out = [[*e.Placement.Base, *e.Placement.Rotation.Q] for e in a.ElementList]
    App.closeDocument(doc.Name)
    return out


path = ROOT / "tests" / "golden" / "link_array" / "freecad.json"
data = json.loads(path.read_text()) if path.exists() else {}
names = [a for a in sys.argv[1:] if not a.endswith(".py")] or list(CASES)
for n in names:
    data[n] = run(*CASES[n])
    print(n, len(data[n]))
path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
