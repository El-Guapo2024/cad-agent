#!/usr/bin/env python3
"""Dump what the real FreeCAD's PartDesign workbench shows, for editcheck.mjs to compare the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcedit.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with fcedit_dump.py, which
makes a Body with Create body, a sketch with New Sketch's plane picker, a Pad and a Pocket through their task panels, and
writes OUT_DIR/fcedit.json: the Sketch and Part Design menus, the toolbars, the task panels' widgets and defaults, the
feature's properties and their groups, the tree's rows (and their icons as PNGs), the tree's context menus on a feature, a
sketch and the Body, the Tip moved, and Std_Delete's warning for a sketch in use. editcheck.mjs reads that file.
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
with tempfile.TemporaryDirectory(prefix="fcedit") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcedit_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5, timeout=700)
if not (out / "fcedit.json").exists():
    sys.exit(f"fcedit: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcedit.json").read_text())
for name, err in res["errors"].items():
    print(f"fcedit: {name} failed:\n{err}")
print(f"fcedit: wrote {out / 'fcedit.json'}")
