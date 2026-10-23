# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run by freecadcmd for hlrdiff.py: TechDraw's own views of STEP files, the visible smooth edges of each.

HLRDIFF_IN is a JSON job, {"views": [{"step": path, "name": ..., "direction": [x, y, z], "xdirection": [x, y, z]}, ...]},
and HLRDIFF_OUT where the answer goes, {"freecad": the build, "views": [{"name": ..., "smooth": [edge, ...], "hard": [...],
"error": text}]}, an edge being {"a": [x, y], "b": [x, y], "length": mm} in the view's x and y (y up).

Each view is a TechDraw::DrawViewPart in a document (src/Mod/TechDraw/App/DrawViewPart.cpp at FreeCAD 3160daf1e2b6), its
Source a Part::Feature holding the STEP's shape, Direction and XDirection the view's, Scale 1, recomputed: so the
projection is GeometryObject::projectShape and makeTDGeometry (GeometryObject.cpp:264-266 keeps the visible smooth edges
when SmoothVisible is on). DrawViewPart's Python API gives the visible edges of all classes together
(DrawViewPartPyImp.cpp:63-87, `getVisibleEdges(True)`: conventional coordinates, y turned back up by invertGeometry), so the view is recomputed twice,
SmoothVisible off and on, and the smooth edges are the ones the second has over the first. TechDraw centres the shape on the
centre of its bounding box as seen along Direction before it projects (DrawViewPart.cpp, ShapeUtils::centerShape and
findCentroid, ShapeUtils.cpp:190-211): the projection of that point, TechDraw.findCentroid, is added back so the edges are in
the frame of the shape as given, which is the frame hlr.py projects in.
"""
import json
import os
import traceback

import FreeCAD as App
import Part
import TechDraw

job = json.load(open(os.environ["HLRDIFF_IN"], encoding="utf-8"))


def edge_json(e, dx, dy):
    a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
    return {"a": [a.x + dx, a.y + dy], "b": [b.x + dx, b.y + dy], "length": e.Length}


def key(e):
    a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
    m = e.valueAt((e.FirstParameter + e.LastParameter) / 2.0)
    return tuple(round(v, 4) for v in (a.x, a.y, b.x, b.y, m.x, m.y, e.Length))


out = {"freecad": " ".join(App.Version()[:4]), "views": []}
for v in job["views"]:
    res = {"name": v["name"]}
    try:
        doc = App.newDocument("hlrdiff")
        feat = doc.addObject("Part::Feature", "Shape")
        feat.Shape = Part.read(v["step"])
        page = doc.addObject("TechDraw::DrawPage", "Page")
        template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")     # a page without one does not recompute
        template.Template = os.path.join(App.getResourceDir(), "Mod", "TechDraw", "Templates", "Default_Template_A4_Landscape.svg")
        page.Template = template
        view = doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [feat]
        view.Direction = App.Vector(*v["direction"])
        view.XDirection = App.Vector(*v["xdirection"])
        view.ScaleType = "Custom"
        view.Scale = 1.0
        view.HardHidden = False
        edges = {}
        for smooth in (False, True):
            view.SmoothVisible = smooth
            view.recompute()
            doc.recompute()
            edges[smooth] = view.getVisibleEdges(True)       # conventionalCoords: y up
        # the centre TechDraw moved to the origin, in the view's x and y
        c = TechDraw.findCentroid(feat.Shape, view.Direction)
        x = App.Vector(*v["xdirection"]).normalize()
        z = App.Vector(*v["direction"]).normalize()
        y = z.cross(x)
        dx, dy = c.dot(x), c.dot(y)
        hard = {}
        for e in edges[False]:
            hard.setdefault(key(e), []).append(e)
        smooth = []
        for e in edges[True]:
            k = key(e)
            if hard.get(k):
                hard[k].pop()
            else:
                smooth.append(e)
        res["smooth"] = [edge_json(e, dx, dy) for e in smooth]
        res["hard"] = [edge_json(e, dx, dy) for e in edges[False]]
        res["centroid"] = [dx, dy]
        App.closeDocument(doc.Name)
    except Exception:  # noqa: BLE001 - one view that fails is an answer of its own
        res["error"] = traceback.format_exc()
    out["views"].append(res)

with open(os.environ["HLRDIFF_OUT"], "w", encoding="utf-8") as f:
    json.dump(out, f)
