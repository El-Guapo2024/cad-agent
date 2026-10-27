#!/usr/bin/env python3
"""Dump what the real FreeCAD's Part workbench shows for the commands that make a Part::Feature holding a shape.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcpart_static.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py) with fcpart_static_dump.py, which runs Simple, Transformed and Element copy, Convert to
solid, Set tolerance, Cross-sections, the Shape builder and Check geometry as a person would, and writes
OUT_DIR/fcpart_static.json (copy it to scripts/fcpart_static.json for partcheck.mjs).
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
with tempfile.TemporaryDirectory(prefix="fcpartst") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcpart_static_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=1000)
if not (out / "fcpart_static.json").exists():
    sys.exit(f"fcpart: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcpart_static.json").read_text())
for name, err in res["errors"].items():
    print(f"fcpart: {name} failed:\n{err}")
print(f"fcpart: wrote {out / 'fcpart_static.json'}")
