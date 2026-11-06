"""Writes freecad.json: every object's shape after each case of cases.py, as FreeCAD 26.3's Draft makes it.

    $FREECAD/freecadcmd tests/golden/draft/make.py [CASE]     (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. Each case gets a fresh document, its script run and the document recomputed."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd())
sys.path.insert(0, str(ROOT / "tests" / "golden" / "draft"))

import FreeCAD as App  # noqa: E402
import Draft  # noqa: E402

from cases import CASES  # noqa: E402
from record import record  # noqa: E402


def run(script):
    doc = App.newDocument("Unnamed")
    ns = {"App": App, "Draft": Draft, "V": App.Vector, "P": App.Placement, "R": App.Rotation, "doc": doc}
    exec(script, ns)
    doc.recompute()
    out = record(doc)
    App.closeDocument(doc.Name)
    return out


path = ROOT / "tests" / "golden" / "draft" / "freecad.json"
data = json.loads(path.read_text()) if path.exists() else {}
names = [a for a in sys.argv[1:] if not a.endswith(".py")] or list(CASES)
for n in names:
    try:
        data[n] = run(CASES[n])
    except Exception:
        import traceback
        data[n] = {"error": traceback.format_exc()}
    print(n, len(data[n]) if isinstance(data[n], list) else data[n])
path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
