#!/usr/bin/env python3
"""Dump what the real FreeCAD's PartDesign shows for its last commands, for pdlastcheck.mjs to compare the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcpdlast.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with fcpdlast_dump.py,
which runs Involute Gear, Sprocket, Defeaturing and Sub-Shape Binder (each on a Body with a Pad, as their buttons do) and
writes OUT_DIR/fcpdlast.json: each command's task panel and its values, the objects and properties it makes, the undo
step, the tree, the property view and the tree's context menu, and what a second edit, Cancel and a double-click do.
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
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fcpdlast") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcpdlast_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=700)
if not (out / "fcpdlast.json").exists():
    sys.exit(f"fcpdlast: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcpdlast.json").read_text())
for name, err in res["errors"].items():
    print(f"fcpdlast: {name} failed:\n{err}")
print(f"fcpdlast: wrote {out / 'fcpdlast.json'}")
