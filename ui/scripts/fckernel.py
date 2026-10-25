#!/usr/bin/env python3
"""Dump what the real FreeCAD's PartDesign shows for a Pocket's Start Reference, Taper angle and Operation Common, and
Multi-Transform's Add Scale Transformation, for kernelcheck.mjs to compare the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fckernel.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fckernel_dump.py and writes OUT_DIR/fckernel.json; ui/scripts/fckernel.json is the copy the check reads.
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
with tempfile.TemporaryDirectory(prefix="fckernel") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fckernel_dump.py"), out, Path(tmp) / "home", platform="cocoa",
                    scale=0.5, timeout=500)
if not (out / "fckernel.json").exists():
    sys.exit(f"fckernel: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fckernel.json").read_text())
for name, err in res["errors"].items():
    print(f"fckernel: {name} failed:\n{err}")
print(f"fckernel: wrote {out / 'fckernel.json'}")
