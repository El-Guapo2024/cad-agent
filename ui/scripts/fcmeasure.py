#!/usr/bin/env python3
"""The numbers of FreeCAD's real widgets, and the colours it draws a selection in, for the quick look fixes.

    python3 scripts/fcmeasure.py OUT_DIR [--scale 0.5] [--timeout 200]

Starts the real FreeCAD GUI (the weekly build at ~/.cad-agent/freecad/FreeCAD.app; FREECAD_APP overrides) on the Mac's Qt
platform with every window kept off the screen (fclaunch.py) and writes OUT_DIR/fcmeasure.json and freecad-sel-<state>.png:
the geometry of the docks, toolbars, tool buttons, tabs, tree, property view, status bar and Report view as laid out in a
1280 x 800 window (QWidget::geometry, no pixel counting), the fonts, what a fresh profile holds for the parameters the
comparison needs, and the colours of a selected, a preselected and a face-selected Part (fcmeasure_dump.py has the list).
FreeCAD's user files are a temporary folder. fcshots.py takes the screenshots these numbers are read against.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fclaunch import run_freecad  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--scale", type=float, default=0.5)
ap.add_argument("--timeout", type=int, default=200)
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fcmeasure") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcmeasure_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=a.scale, timeout=a.timeout)
if not (out / "fcmeasure.json").exists():
    sys.exit(f"fcmeasure: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcmeasure.json").read_text())
for name, err in res["errors"].items():
    print(f"fcmeasure: {name} failed:\n{err}")
print(f"fcmeasure: wrote {out / 'fcmeasure.json'}")
