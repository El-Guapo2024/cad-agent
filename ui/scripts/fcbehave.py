#!/usr/bin/env python3
"""Measure the real FreeCAD 3D view's behaviour, for the comparison with the workbench's (oursbehave.mjs measures ours).

    python3 scripts/fcbehave.py OUT_DIR [--only views,fit,align,...]

Starts FreeCAD's GUI (the weekly build at ~/.cad-agent/freecad/FreeCAD.app; FREECAD_APP overrides) on the Mac's Qt platform
with every window kept off the screen (fclaunch.py) and writes OUT_DIR/fcbehave.json. Sections:

* views, rotates, home: the camera orientation after each standard view (viewFront ... viewTrimetric,
  viewDefaultOrientation), rotate left and right, Home;
* zoom, drags: the zoom of a wheel notch, a Mac trackpad scroll and the zoom commands, and the CAD style's mouse drags
  (synthetic Qt events sent to the 3D view: no real pointer);
* nav_page: the navigation style and what the Navigation preference page's widgets hold, and the lists its combo boxes offer;
* dblclick: QApplication's double-click interval and drag distance (what NavigationStyle and the NaviCube ask the OS for);
* fit: Std_ViewFitAll and Std_ViewFitSelection on a perspective and an orthographic camera, in a wide and a tall viewer, for
  whole parts and for faces, edges and vertices of three solids (the scratch project "probe" is the same three solids);
* align: Std_AlignToSelection from twelve starting orientations, for faces, edges and several elements;
* tree_menu: the entries of the tree's context menu on a part, on two parts and on the document.
* quickmeasure: the words QuickMeasure puts in the status bar's right side for thirteen selections of circles, discs, cylinders,
  lines and points (a fourth solid, a post turned 30 degrees about x, is added to the document for it).

--only limits the run to the named sections. FreeCAD's user files are a temporary folder.
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
ap.add_argument("--only", default="")
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fcbehave") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcbehave_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5, timeout=1000,
                    env={"FCBEHAVE_ONLY": a.only})
if not (out / "fcbehave.json").exists():
    sys.exit(f"fcbehave: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcbehave.json").read_text())
for name, err in res["errors"].items():
    print(f"fcbehave: {name} failed:\n{err}")
print(f"fcbehave: wrote {out / 'fcbehave.json'}")
