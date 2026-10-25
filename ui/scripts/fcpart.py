#!/usr/bin/env python3
"""Dump what the real FreeCAD's Part workbench shows, for partcheck.mjs to compare the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcpart.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with fcpart_dump.py,
which runs the Part workbench's commands on selections as a person would (Cube, Cylinder, ..., Primitives, Cut, Union,
Intersection, Section, Extrude, Revolve, Mirror, Fillet, Chamfer, Loft, Sweep, Offset, Thickness, the split, join and
compound tools) and writes OUT_DIR/fcpart.json: the Part menu and toolbars, each command's task panel, the objects it
made and the inputs it hid, its undo name, the Primitives dialog's pages, the tree, a context menu, the property view.
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
with tempfile.TemporaryDirectory(prefix="fcpart") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcpart_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=1000)
if not (out / "fcpart.json").exists():
    sys.exit(f"fcpart: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcpart.json").read_text())
for name, err in res["errors"].items():
    print(f"fcpart: {name} failed:\n{err}")
print(f"fcpart: wrote {out / 'fcpart.json'}")
