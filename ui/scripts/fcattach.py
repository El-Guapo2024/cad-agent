#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Dump what the real FreeCAD does with attachment, for attachcheck.mjs to compare the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcattach.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with fcattach_dump.py,
which makes a Body with a plate and then New Sketch on its top face, the four datums of Edit > Create > Datums with a
selection and without, a Cancel, and a datum's double-click, and writes OUT_DIR/fcattach.json (the task panels'
widgets, the objects made, the transactions, the tree's rows). attachcheck.mjs reads that file.
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
with tempfile.TemporaryDirectory(prefix="fcattach") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcattach_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=700)
if not (out / "fcattach.json").exists():
    sys.exit(f"fcattach: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcattach.json").read_text())
for name, err in res["errors"].items():
    print(f"fcattach: {name} failed:\n{err}")
print(f"fcattach: wrote {out / 'fcattach.json'}")
