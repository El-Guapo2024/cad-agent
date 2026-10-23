# SPDX-License-Identifier: LGPL-2.1-or-later
"""dxfdiff.py's FreeCAD half: runs inside freecadcmd. Reads a STEP, takes its flat face at a height (the end face
cad_agent/dxf.py writes from too: Part's slice of an elliptic hole would be a fitted B-spline), writes its edges with
Import.writeDXFShape (ImpExpDxfWrite, the DXF export of FreeCAD's File > Export), and reads a second DXF
back with Import.readDXF, reporting what it found as JSON.

    DXFDIFF_IN   a JSON file: {"step": path, "z": the face's height, "out": the DXF to write, "read": the DXF to read back}
    DXFDIFF_OUT  the JSON written: {"read": {"edges": n, "length": mm, "box": [x0, y0, x1, y1]}, "freecad": build}
"""
import json
import os

import FreeCAD as App
import Import
import Part

job = json.load(open(os.environ["DXFDIFF_IN"], encoding="utf-8"))
shape = Part.read(job["step"])
face = next(f for f in shape.Faces if f.Surface.TypeId == "Part::GeomPlane" and abs(f.BoundBox.ZMin - job["z"]) < 1e-9
            and abs(f.BoundBox.ZMax - job["z"]) < 1e-9)
edges = face.Edges
Import.writeDXFShape(edges, job["out"])

doc = App.newDocument("Read")
Import.readDXF(job["read"])
doc.recompute()
read = [e for o in doc.Objects if hasattr(o, "Shape") for e in o.Shape.Edges]
box = None
for e in read:
    box = e.BoundBox if box is None else box.united(e.BoundBox)
cfg = App.ConfigGet
json.dump({"read": {"edges": len(read), "length": sum(e.Length for e in read),
                    "box": [box.XMin, box.YMin, box.XMax, box.YMax] if box else None},
           "freecad": f"{cfg('BuildVersionMajor')}.{cfg('BuildVersionMinor')} {cfg('BuildRevision')}"},
          open(os.environ["DXFDIFF_OUT"], "w", encoding="utf-8"))
