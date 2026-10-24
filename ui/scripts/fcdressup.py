#!/usr/bin/env python3
"""Dump what the real FreeCAD's PartDesign dress-up features (Fillet, Chamfer, Draft, Thickness) show, for dressupcheck.mjs.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcdressup.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py) with fcdressup_dump.py, which makes a Body with a Pad, selects edges or faces of it and
runs each dress-up command: the task panel, Select and a pick in the 3D view, OK, the property view and the tree. Writes
OUT_DIR/fcdressup.json (scripts/fcdressup.json is the copy the check reads).
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
with tempfile.TemporaryDirectory(prefix="fcdressup") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcdressup_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=700)
if not (out / "fcdressup.json").exists():
    sys.exit(f"fcdressup: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcdressup.json").read_text())
for name, err in res["errors"].items():
    print(f"fcdressup: {name} failed:\n{err}")
print(f"fcdressup: wrote {out / 'fcdressup.json'}")
