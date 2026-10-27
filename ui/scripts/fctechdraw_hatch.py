#!/usr/bin/env python3
"""Dump what the real FreeCAD's TechDraw hatching tools do, for the TechDraw page to be compared with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fctechdraw_hatch.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fctechdraw_hatch_dump.py, which draws a part (a page, a view of the plate from above) and then uses the tools of the
Hatching menu the way a person does, and writes
OUT_DIR/fctechdraw_hatch.json: the menu entries' state for each selection, each task panel, what it made (the hatch objects, their view provider properties), the undo steps, the
property view and the page exported. techdrawcheck.mjs holds the workbench to it (ui/scripts/fctechdraw_hatch.json).
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fclaunch import run_freecad  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
a = ap.parse_args()
out = Path(a.out).expanduser()
with tempfile.TemporaryDirectory(prefix="fctechdrawhatch") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fctechdraw_hatch_dump.py"), out, Path(tmp) / "home", platform="cocoa", scale=0.5,
                    timeout=1700,
                    env={"FCTECHDRAW_BREPS": str(Path(__file__).resolve().parents[2] / "tests/golden/techdraw/breps")})
if not (out / "fctechdraw_hatch.json").exists():
    sys.exit(f"fctechdraw_hatch: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
text = (out / "fctechdraw_hatch.json").read_text()
text = re.sub(r'"(?:[^"\\]|\\.)*?/(?:usr/share|share)/Mod/TechDraw/', '"<FreeCAD>/Mod/TechDraw/', text)
text = text.replace(str(Path(__file__).resolve().parents[2]), "<repo>")
text = re.sub(r'"(?:[^"\\]|\\.)*?/FreeCAD_Doc_[0-9a-f_-]+/', '"<document>/', text)
(out / "fctechdraw_hatch.json").write_text(text)
res = json.loads(text)
for name, err in res["errors"].items():
    print(f"fctechdraw_hatch: {name} failed:\n{err}")
print(f"fctechdraw_hatch: wrote {out / 'fctechdraw_hatch.json'}")
