#!/usr/bin/env python3
"""Measure the real FreeCAD 3D view's behaviour, for the comparison with the workbench's (oursbehave.mjs measures ours).

    python3 scripts/fcbehave.py OUT_DIR

Starts FreeCAD's GUI (the weekly build at ~/.cad-agent/freecad/FreeCAD.app; FREECAD_APP overrides) on the Mac's Qt platform
with every window kept off the screen (fclaunch.py) and writes OUT_DIR/fcbehave.json: the camera orientation after each
standard view (viewFront ... viewTrimetric, viewDefaultOrientation, Home, rotate left and right), the zoom of a wheel
notch, a Mac trackpad scroll and the zoom commands (synthetic Qt events sent to the 3D view: no real pointer), the
navigation style, and what the Navigation preference page's widgets hold. FreeCAD's user files are a temporary folder.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fclaunch import run_freecad  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
out = Path(sys.argv[1]).expanduser()
with tempfile.TemporaryDirectory(prefix="fcbehave") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcbehave_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5, timeout=240)
if not (out / "fcbehave.json").exists():
    sys.exit(f"fcbehave: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcbehave.json").read_text())
for name, err in res["errors"].items():
    print(f"fcbehave: {name} failed:\n{err}")
print(f"fcbehave: wrote {out / 'fcbehave.json'}")
