"""Writes hatch.json: the lines TechDraw.makeGeomHatch (DrawGeomHatch::getTrimmedLines) leaves in the faces of the plate's top
view for FCPAT.pat's patterns and tests/golden/techdraw/hatch.pat's (dashes, shifts, origins), for tests/test_techdraw_hatch.py
to hold cad_agent/techdraw_hatch.py to.

    $FREECAD/freecadcmd tests/golden/techdraw/make_hatch.py     (from the repository's root, after prep.py)

The faces are the view's closed wires made into Part faces: the outline (Edge0 to Edge4) and the hole (Edge5), in the view's
conventional (y up) coordinates, as getEdgeByIndex gives them at scale 1.
"""
import json
import os
from pathlib import Path

import FreeCAD as App
import Part
import TechDraw

HERE = Path(os.getcwd()) / "tests" / "golden" / "techdraw"
V = App.Vector
TEMPLATES = Path(App.getResourceDir()) / "Mod" / "TechDraw" / "Templates"
FCPAT = str(Path(App.getResourceDir()) / "Mod" / "TechDraw" / "PAT" / "FCPAT.pat")
DASHES = str(HERE / "hatch.pat")

doc = App.newDocument("golden")
f = doc.addObject("Part::Feature", "plate")
f.Shape = Part.read(str(HERE / "breps" / "plate.brep"))
page = doc.addObject("TechDraw::DrawPage", "Page")
t = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
t.Template = str(TEMPLATES / "ISO" / "A4_Landscape_TD.svg")
page.Template = t
v = doc.addObject("TechDraw::DrawViewPart", "View")
page.addView(v)
v.Source = [f]
v.Direction = V(0, 0, 1)
v.XDirection = V(1, 0, 0)
doc.recompute()
edges = [v.getEdgeByIndex(i) for i in range(6)]
faces = [Part.Face(Part.Wire(Part.__sortEdges__(edges[:5]))), Part.Face(Part.Wire([edges[5]]))]


def segments(comp):
    out = []
    for e in comp.Edges:
        a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
        p, q = sorted([(round(a.x, 5), round(a.y, 5)), (round(b.x, 5), round(b.y, 5))])
        out.append([p[0], p[1], q[0], q[1]])
    return sorted(out)


CASES = [(FCPAT, "FCPAT.pat", "Diamond", 1.0), (FCPAT, "FCPAT.pat", "Diagonal4", 2.0), (FCPAT, "FCPAT.pat", "Square", 2.5),
         (DASHES, "hatch.pat", "Dashed", 1.0), (DASHES, "hatch.pat", "Dashed", 0.6), (DASHES, "hatch.pat", "Dashdot", 1.0),
         (DASHES, "hatch.pat", "Cross", 1.5), (DASHES, "hatch.pat", "Brick", 1.0), (DASHES, "hatch.pat", "Steep", 1.2)]
out = {"freecad": App.Version()[:4], "cases": []}
for path, fname, name, scale in CASES:
    for i, face in enumerate(faces):
        comp = TechDraw.makeGeomHatch(face, scale, name, path)
        out["cases"].append({"file": fname, "name": name, "scale": scale, "face": i, "segments": segments(comp) if comp is not None else []})
(HERE / "hatch.json").write_text(json.dumps(out, indent=1) + "\n")
print(f"make_hatch: {len(out['cases'])} cases")
