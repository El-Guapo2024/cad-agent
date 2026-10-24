#!/usr/bin/env python3
"""Dump what the real FreeCAD's PartDesign workbench shows for Mirror, Linear Pattern, Polar Pattern, Multi-Transform and
the additive and subtractive primitives, for transformcheck.mjs to compare the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fctransform.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fctransform_dump.py, which writes OUT_DIR/fctransform.json (its header says what is in it). Copy that file to
ui/scripts/fctransform.json, which transformcheck.mjs reads.
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
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="fctransform") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fctransform_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=1000)
if not (out / "fctransform.json").exists():
    sys.exit(f"fctransform: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fctransform.json").read_text())
for name, err in res["errors"].items():
    print(f"fctransform: {name} failed:\n{err}")
print(f"fctransform: wrote {out / 'fctransform.json'}")
