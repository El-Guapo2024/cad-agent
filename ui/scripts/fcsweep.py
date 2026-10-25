#!/usr/bin/env python3
"""Dump what the real FreeCAD's PartDesign shows for Additive/Subtractive Loft, Pipe and Helix, for sweepcheck.mjs to
compare the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcsweep.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with fcsweep_dump.py,
which runs PartDesign_AdditiveLoft, _SubtractiveLoft, _AdditivePipe, _SubtractivePipe, _AdditiveHelix and
_SubtractiveHelix through their task panels and writes OUT_DIR/fcsweep.json: each panel's widgets as it opens and
after a few changes, the features' properties (values, groups, editor modes, enumerations) and their property view.
ui/scripts/fcsweep.json is the copy the check reads.
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
with tempfile.TemporaryDirectory(prefix="fcsweep") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcsweep_dump.py"), out, Path(tmp) / "home", platform="cocoa",
                    scale=0.5, timeout=700)
if not (out / "fcsweep.json").exists():
    sys.exit(f"fcsweep: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcsweep.json").read_text())
for name, err in res["errors"].items():
    print(f"fcsweep: {name} failed:\n{err}")
print(f"fcsweep: wrote {out / 'fcsweep.json'}")
