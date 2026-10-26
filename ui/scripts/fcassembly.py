#!/usr/bin/env python3
"""Dump what the real FreeCAD's Assembly workbench shows, for assemblycheck.mjs to compare the page with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fcassembly.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fcassembly_dump.py, which makes an Assembly as a person would (New Assembly, components, Toggle Grounded, joints from
a selection of two elements and OK) and writes OUT_DIR/fcassembly.json: the Assembly menu and toolbars, each joint
panel, the Insert Component panel, the Solver messages, the joints made, the tree and a joint's property view.
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
with tempfile.TemporaryDirectory(prefix="fcassembly") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fcassembly_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=700)
if not (out / "fcassembly.json").exists():
    sys.exit(f"fcassembly: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fcassembly.json").read_text())
for name, err in res["errors"].items():
    print(f"fcassembly: {name} failed:\n{err}")
print(f"fcassembly: wrote {out / 'fcassembly.json'}")
