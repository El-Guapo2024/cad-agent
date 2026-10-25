#!/usr/bin/env python3
"""Dump what the real FreeCAD's PartDesign task panels do with a pick in the 3D view while they ask for a reference, for
pickcheck.mjs.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcpick.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py) with fcpick_dump.py, which makes a Body with a Pad and datums and, case by case, opens
a panel and picks through its selection gate (Pad and Pocket's Up to face, Up to shape and Direction/edge, Revolution's
axis, Mirrored's plane, the patterns' direction and axis and Add Feature, Draft's neutral plane and pull direction), with
the tree's context menu, the primitive toolbar button, PartDesign's datum commands and Std_Delete. Writes
OUT_DIR/fcpick.json (scripts/fcpick.json is the copy the check reads).
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
with tempfile.TemporaryDirectory(prefix="fcpick") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcpick_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=1000)
if not (out / "fcpick.json").exists():
    sys.exit(f"fcpick: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcpick.json").read_text())
for name, err in res["errors"].items():
    print(f"fcpick: {name} failed:\n{err}")
print(f"fcpick: wrote {out / 'fcpick.json'}")
