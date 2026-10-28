"""Writes breps/: the shapes the CAM goldens machine, for make.py (FreeCAD) and tests/test_cam_golden.py (the app).

    .venv/bin/python tests/golden/cam/prep.py          (from the repository's root)

plate.brep is tests/fixtures/feature_plate's plate as the app builds it (a 60 x 40 x 6 mm Body centred on the origin:
four holes, a boss with a bore, a slot pocket). pocket_plate.brep is a 100 x 60 x 10 mm block from (-10, -5, 0) with a
40 x 20 x 5 mm pocket and four 6 mm holes through, made with OCCT's primitives and FreeCAD's booleans and refine.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
HERE = ROOT / "tests" / "golden" / "cam"


def main():
    from OCP.BRepTools import BRepTools
    from cad_agent import state as st
    out = HERE / "breps"
    out.mkdir(exist_ok=True)
    st.ROOT = ROOT / "tests" / "fixtures"
    from cad_agent.techdraw_edit import shape_loader
    BRepTools.Write_s(shape_loader("feature_plate")("plate"), str(out / "plate.brep"))
    from cad_agent import cam_runtime
    cam_runtime.activate()
    import FreeCAD
    import Part
    box = Part.makeBox(100, 60, 10)
    s = box.cut(Part.makeBox(40, 20, 5, FreeCAD.Vector(30, 20, 5)))
    for x, y in ((10, 10), (90, 10), (10, 50), (90, 50)):
        s = s.cut(Part.makeCylinder(3, 10, FreeCAD.Vector(x, y, 0)))
    s = s.removeSplitter()
    s.translate(FreeCAD.Vector(-10, -5, 0))
    BRepTools.Write_s(s._s, str(out / "pocket_plate.brep"))
    print("wrote", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main()
