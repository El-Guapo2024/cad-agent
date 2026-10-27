#!/usr/bin/env python3
"""Dump what the real FreeCAD's TechDraw leader line, rich text, symbol, weld, surface finish, image and clip tools do, for the
TechDraw page to be compared with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fctechdraw_more.py OUT_DIR [SECTION,...]

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with
fctechdraw_more_dump.py, which draws a part (a page, a view of the plate from above) and then uses the tools the way a person does
(the leader line's points are clicked on the page, a file dialog is answered), and writes
OUT_DIR/fctechdraw_more.json: the menu entries' state for each selection, each task panel, what it made (the objects, their view
provider properties), the undo steps, the tree, the property views and the page exported. techdrawcheck.mjs holds the workbench to it
(ui/scripts/fctechdraw_more.json). SECTION names the sections to run (default: all).
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
ap.add_argument("only", nargs="?", default="")
a = ap.parse_args()
out = Path(a.out).expanduser()
HERE = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="fctechdrawmore") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(HERE / "fctechdraw_more_dump.py", out, Path(tmp) / "home", platform="cocoa", scale=0.5, timeout=1700,
                    env={"FCTECHDRAW_BREPS": str(HERE.parents[1] / "tests/golden/techdraw/breps"),
                         "FCTECHDRAW_HELPERS": str(HERE / "fctechdraw_hatch_dump.py"), "FCTECHDRAW_ONLY": a.only,
                         "FCTECHDRAW_REPO": str(HERE.parents[1])})
if not (out / "fctechdraw_more.json").exists():
    sys.exit(f"fctechdraw_more: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
text = (out / "fctechdraw_more.json").read_text()
text = re.sub(r'"(?:[^"\\]|\\.)*?/(?:usr/share|share)/Mod/TechDraw/', '"<FreeCAD>/Mod/TechDraw/', text)
text = text.replace(str(HERE.parents[1]), "<repo>")
text = re.sub(r'"(?:[^"\\]|\\.)*?/FreeCAD_Doc_[0-9a-f_-]+/', '"<document>/', text)
(out / "fctechdraw_more.json").write_text(text)
res = json.loads(text)
for name, err in res["errors"].items():
    print(f"fctechdraw_more: {name} failed:\n{err}")
print(f"fctechdraw_more: wrote {out / 'fctechdraw_more.json'}")
