#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Dump what the real FreeCAD does with the Sketcher's commands on sketch objects, for sketchobjcheck.mjs to compare
the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 ui/scripts/fcsketchobj.py OUT_DIR [--ref]

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fcsketchobj_dump.py, which makes a Body with a plate and a few sketches, then runs Sketcher_MirrorSketch,
Sketcher_MergeSketches, Sketcher_ReorientSketch, Sketcher_MapSketch and Sketcher_ValidateSketch on them as a person
does (the tree's selection, the dialogs answered as the case says), and writes OUT_DIR/fcsketchobj.json: each
dialog's widgets, the objects made or changed (placement, attachment, geometry, constraints), the transactions,
the Report view's lines and the commands' enabled state. --ref also writes ui/scripts/fcsketchobj.json, the copy
sketchobjcheck.mjs reads.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fclaunch import run_freecad  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--ref", action="store_true", help="also copy the answer to ui/scripts/fcsketchobj.json")
a = ap.parse_args()
out = Path(a.out).expanduser()
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="fcsketchobj") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcsketchobj_dump.py"), out, Path(tmp) / "home", platform="cocoa",
                    scale=0.5, timeout=700)
if not (out / "fcsketchobj.json").exists():
    sys.exit(f"fcsketchobj: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcsketchobj.json").read_text())
for name, err in res["errors"].items():
    print(f"fcsketchobj: {name} failed:\n{err}")
print(f"fcsketchobj: wrote {out / 'fcsketchobj.json'}")
if a.ref:
    dst = Path(__file__).with_name("fcsketchobj.json")
    shutil.copy(out / "fcsketchobj.json", dst)
    print(f"fcsketchobj: wrote {dst}")
