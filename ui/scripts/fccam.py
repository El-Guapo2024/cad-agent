#!/usr/bin/env python3
"""Dump what the real FreeCAD's CAM workbench shows, for the CAM page to be compared with.

    FREECAD_APP=<unpacked AppImage> xvfb-run -a -s "-screen 0 1600x1000x24" python3 scripts/fccam.py OUT_DIR

Starts FreeCAD's GUI (fclaunch.py: user files in a temporary folder, windows kept off the screen) with fccam_dump.py,
which uses the workbench as a person would on tests/golden/cam/breps/plate.brep (CAM_Job with the plate selected and
its dialog's OK, the Job's task panel, CAM_Profile, CAM_Pocket_Shape, CAM_Drilling and CAM_MillFace with faces
selected, CAM_DressupTag and CAM_DressupDogbone on a selected op, each task panel's OK, Std_Undo and Std_Redo) and
writes OUT_DIR/fccam.json: the CAM menu and toolbars before and after, each dialog and task panel, the tree, the
property view of each kind of object, and the undo steps. ui/scripts/camcheck.mjs holds the page to it.
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
breps = Path(__file__).resolve().parents[2] / "tests" / "golden" / "cam" / "breps"
with tempfile.TemporaryDirectory(prefix="fccam") as tmp:
    (Path(tmp) / "home").mkdir()
    r = run_freecad(Path(__file__).with_name("fccam_dump.py"), out, Path(tmp) / "home", platform="cocoa",
                    scale=0.5, timeout=900, show=True, env={"FCCAM_BREPS": str(breps)})
if not (out / "fccam.json").exists():
    sys.exit(f"fccam: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-4000:]}")
res = json.loads((out / "fccam.json").read_text())
for name, err in res["errors"].items():
    print(f"fccam: {name} failed:\n{err}")
print(f"fccam: wrote {out / 'fccam.json'}")
