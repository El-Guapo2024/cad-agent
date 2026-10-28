"""Writes freecad.json: what FreeCAD's TechDraw makes of each page of cases.json, for tests/test_techdraw_golden.py
to hold cad_agent/techdraw.py, techdraw_view.py, techdraw_dim.py and techdraw_export.py to.

    $FREECAD/freecadcmd tests/golden/techdraw/make.py [CASE]     (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root after prep.py. Each case gets a fresh document labelled "golden", a Part::Feature
per part read from breps/, and the page's objects made in cases.json's order as the GUI's commands make them
(TechDraw_PageDefault's page and template, page.addView for each view, DrawProjGroup.addProjection for each
projection with the anchor's Direction set as CmdTechDrawProjectionGroup sets it, a dimension's Type, MeasureType
and References2D as dimMaker sets them), the properties cad_agent wrote set after, then one recompute. Recorded:
every view's X, Y, Scale, Direction and XDirection, each edge (getEdgeByIndex: unscaled, y up) and vertex
(getVertexByIndex) in FreeCAD's numbering with the count of visible ones, each dimension's getRawValue, getText,
FormatSpec and its points, the template's EditableTexts and size, and TechDraw.writeDXFPage's file.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "techdraw"
if not (HERE / "cases.json").exists():
    sys.exit("run make.py from the repository's root, after prep.py")

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402
import TechDraw  # noqa: E402

V = App.Vector
TEMPLATES = Path(App.getResourceDir()) / "Mod" / "TechDraw" / "Templates"


def camel(key):
    special = {"x": "X", "y": "Y", "x_direction": "XDirection", "spacing_x": "spacingX", "spacing_y": "spacingY",
               "references_2d": "References2D"}
    return special.get(key) or "".join(w[:1].upper() + w[1:] for w in key.split("_"))


def vec(v):
    return [v.x, v.y, v.z]


def q(v):
    return v.Value if hasattr(v, "Value") else v


VIEW_SKIP = {"name", "kind", "type_id", "source", "label", "cosmetic_edges", "center_lines", "cosmetic_vertexes",
             "item_type", "views", "anchor", "base_view", "template", "show_all_edges"}


def set_props(o, d, keys):
    for k in keys:
        if k in VIEW_SKIP or k not in d or d[k] is None:
            continue
        v = d[k]
        p = camel(k)
        if isinstance(v, list) and len(v) == 3 and all(isinstance(c, (int, float)) for c in v):
            v = V(*v)
        setattr(o, p, v)


def build(doc, case):
    objs = case["objects"]
    by = {o["name"]: o for o in objs}
    made = {}
    page = None
    group_of = {}
    for o in objs:
        if o["kind"] == "DrawProjGroup":
            for n in o["views"]:
                group_of[n] = o["name"]
    for o in objs:
        k, n = o["kind"], o["name"]
        if k == "DrawPage":
            page = doc.addObject("TechDraw::DrawPage", n)
            made[n] = page
        elif k == "DrawSVGTemplate":
            t = doc.addObject("TechDraw::DrawSVGTemplate", n)
            t.Template = str(TEMPLATES / o["template"])
            page.Template = t
            made[n] = t
            pd = by[page.Name]
            page.ProjectionType = pd["projection_type"]
            page.Scale = pd["scale"]
        elif k in ("DrawProjGroupItem", "DrawViewPart") and n not in group_of:
            v = doc.addObject("TechDraw::" + k, n)
            page.addView(v)
            v.Source = [doc.getObject(p) for p in o["source"]]
            v.Direction = V(*o["direction"])
            v.XDirection = V(*o["x_direction"])
            set_props(v, o, [x for x in o if x not in ("direction", "x_direction", "dim_type")])
            made[n] = v
        elif k == "DrawProjGroup":
            g = doc.addObject("TechDraw::DrawProjGroup", n)
            page.addView(g)
            g.Source = [doc.getObject(p) for p in o["source"]]
            for item in o["views"]:
                it = by[item]
                made_item = g.addProjection(it["item_type"])
                if made_item.Name != item:
                    raise RuntimeError(f"addProjection made {made_item.Name}, cad_agent {item}")
                if it["item_type"] == "Front":
                    made_item.Direction = V(*it["direction"])
                    made_item.XDirection = V(*it["x_direction"])
                    made_item.recompute()
                made[item] = made_item
            set_props(g, o, ["projection_type", "auto_distribute", "spacing_x", "spacing_y", "scale_type", "scale",
                             "x", "y", "lock_position"])
            made[n] = g
        elif k == "DrawViewSection":
            s = doc.addObject("TechDraw::DrawViewSection", n)
            page.addView(s)
            s.BaseView = made[o["base_view"]]
            s.Source = [doc.getObject(p) for p in o["source"]]
            for key in ("section_symbol", "label", "caption", "section_origin", "scale", "scale_type",
                        "section_direction", "section_normal", "direction", "x_direction", "rotation", "x", "y",
                        "hard_hidden", "smooth_visible"):
                if key == "label":
                    s.Label = o["label"]
                    continue
                set_props(s, o, [key])
            made[n] = s
        elif k == "DrawViewDimension":
            d = doc.addObject("TechDraw::DrawViewDimension", n)
            d.Type = o["dim_type"]
            d.MeasureType = o["measure_type"]
            d.References2D = [(made[r[0]], r[1]) for r in o["references_2d"]]
            page.addView(d)
            for key in ("format_spec", "arbitrary_tolerances", "equal_tolerance", "over_tolerance", "under_tolerance",
                        "format_spec_over_tolerance", "format_spec_under_tolerance", "theoretical_exact",
                        "arbitrary", "show_units", "inverted", "show_supplementary", "x", "y"):
                set_props(d, o, [key])
            made[n] = d
        elif k == "DrawViewBalloon":
            b = doc.addObject("TechDraw::DrawViewBalloon", n)
            b.SourceView = made[o["source_view"]]
            page.addView(b)
            set_props(b, o, ["origin_x", "origin_y", "text", "x", "y", "bubble_shape", "end_type"])
            made[n] = b
        elif k == "DrawViewAnnotation":
            a = doc.addObject("TechDraw::DrawViewAnnotation", n)
            page.addView(a)
            a.Text = o["text"]
            set_props(a, o, ["x", "y", "text_size", "font", "text_style"])
            made[n] = a
    return page, made


MODES = {"Vertical": 0, "Horizontal": 1, "Aligned": 2}


def add_cosmetics(doc, case, made):
    """The cosmetic vertices, cosmetic edges and centre lines of each view, made as the Python interface of
    DrawViewPart makes them (makeCosmeticVertex, makeCosmeticLine, makeCosmeticCircle, makeCosmeticCircleArc,
    makeCenterLine), in the case's order, a recompute between the kinds. Returns {view: {tag kind lists}}."""
    for o in case["objects"]:
        cv, ce, cl = o.get("cosmetic_vertexes") or [], o.get("cosmetic_edges") or [], o.get("center_lines") or []
        if not (cv or ce or cl):
            continue
        v = made[o["name"]]
        for c in cv:
            v.makeCosmeticVertex(V(*c["point"]))
        for c in ce:
            if c["geom"] == "line":
                v.makeCosmeticLine(V(*c["start"]), V(*c["end"]))
            elif c["geom"] == "circle":
                v.makeCosmeticCircle(V(*c["center"]), c["radius"])
            else:
                v.makeCosmeticCircleArc(V(*c["center"]), c["radius"], c["start_angle"], c["end_angle"])
            f = c.get("format")
            if f:                                   # the pen of a command that set one (cad_agent/techdraw_ext.py)
                v.CosmeticEdges[-1].Format = {"style": f["style"], "weight": f["weight"], "color": tuple(f["color"]),
                                              "visible": f["visible"]}
        doc.recompute()
        for c in cl:
            subs = c["faces"] or c["edges"] or c["vertexes"]
            tag = v.makeCenterLine(list(subs), MODES[c["mode"]])
            line = v.getCenterLine(tag)
            line.HorizShift, line.VertShift, line.Rotation, line.Extension = c["h_shift"], c["v_shift"], c["rotate"], c["extend"]
            line.Flip = c["flip"]
            v.touch()
        doc.recompute()


def cosmetic_record(v):
    """What the Python objects of a view's cosmetic geometry say: CosmeticVertex.Point, CosmeticEdge.Format, ..."""
    out = {"vertexes": [vec(c.Point) for c in v.CosmeticVertexes],
           "edges": [dict(c.Format) for c in v.CosmeticEdges],
           "centerlines": [{"Format": dict(c.Format), "Mode": c.Mode, "Type": c.Type, "Edges": list(c.Edges),
                            "Faces": list(c.Faces), "Points": list(c.Points), "HorizShift": c.HorizShift,
                            "VertShift": c.VertShift, "Rotation": c.Rotation, "Extension": c.Extension,
                            "Flip": c.Flip} for c in v.CenterLines]}
    return out


def view_record(v):
    out = {"X": q(v.X), "Y": q(v.Y), "Scale": v.Scale, "ScaleType": v.ScaleType, "Direction": vec(v.Direction),
           "XDirection": vec(v.XDirection), "Rotation": q(v.Rotation), "nvis": len(v.getVisibleEdges()),
           "nhid": len(v.getHiddenEdges())}
    edges = []
    i = 0
    while True:
        try:
            e = v.getEdgeByIndex(i)
        except Exception:
            break
        c = e.Curve
        d = {"curve": type(c).__name__, "start": vec(e.Vertexes[0].Point), "end": vec(e.Vertexes[-1].Point),
             "length": e.Length}
        if hasattr(c, "Radius"):
            d["radius"], d["center"] = c.Radius, vec(c.Center)
        if hasattr(c, "MajorRadius"):
            d["major"], d["minor"], d["center"] = c.MajorRadius, c.MinorRadius, vec(c.Center)
        edges.append(d)
        i += 1
    verts = []
    i = 0
    while True:
        try:
            verts.append(vec(v.getVertexByIndex(i).Point))
        except Exception:
            break
        i += 1
    out["edges"], out["vertices"] = edges, verts
    if len(v.CosmeticVertexes) or len(v.CosmeticEdges) or len(v.CenterLines):
        out["cosmetic"] = cosmetic_record(v)
    return out


def dim_record(d):
    out = {"raw": d.getRawValue(), "text": d.getText(), "FormatSpec": d.FormatSpec,
           "FormatSpecUnderTolerance": d.FormatSpecUnderTolerance, "OverTolerance": q(d.OverTolerance),
           "UnderTolerance": q(d.UnderTolerance), "X": q(d.X), "Y": q(d.Y)}
    if d.Type in ("Distance", "DistanceX", "DistanceY"):
        out["linear"] = [vec(p) for p in d.getLinearPoints()]
    elif d.Type in ("Radius", "Diameter"):
        out["arc"] = [vec(p) for p in d.getArcPoints()]
    elif d.Type in ("Angle", "Angle3Pt"):
        out["angle"] = [vec(p) for p in d.getAnglePoints()]
    return out


def run(name, case):
    doc = App.newDocument("golden")
    doc.Label = "golden"
    for p in sorted({p for o in case["objects"] for p in (o.get("source") or [])}):
        f = doc.addObject("Part::Feature", p)
        f.Shape = Part.read(str(HERE / "breps" / f"{p}.brep"))
    page, made = build(doc, case)
    doc.recompute()
    add_cosmetics(doc, case, made)
    out = {"views": {}, "dims": {}, "page": {"Scale": page.Scale, "ProjectionType": page.ProjectionType,
                                             "Views": [v.Name for v in page.Views]}}
    t = page.Template
    out["template"] = {"Width": q(t.Width), "Height": q(t.Height), "Orientation": t.Orientation,
                       "EditableTexts": dict(t.EditableTexts)}
    for n, o in made.items():
        if o.isDerivedFrom("TechDraw::DrawViewPart"):
            out["views"][n] = view_record(o)
        elif o.isDerivedFrom("TechDraw::DrawProjGroup"):
            out["views"][n] = {"X": q(o.X), "Y": q(o.Y), "Scale": o.Scale, "ScaleType": o.ScaleType,
                               "Views": [v.Name for v in o.Views], "Anchor": o.Anchor.Name}
        elif o.isDerivedFrom("TechDraw::DrawViewDimension"):
            out["dims"][n] = dim_record(o)
        elif o.isDerivedFrom("TechDraw::DrawViewBalloon"):
            out["views"][n] = {"X": q(o.X), "Y": q(o.Y), "OriginX": q(o.OriginX), "OriginY": q(o.OriginY),
                               "Text": o.Text, "BubbleShape": o.BubbleShape, "EndType": o.EndType}
        elif o.isDerivedFrom("TechDraw::DrawViewAnnotation"):
            out["views"][n] = {"X": q(o.X), "Y": q(o.Y), "Text": list(o.Text), "TextSize": q(o.TextSize)}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "page.dxf")
        TechDraw.writeDXFPage(page, path)
        out["dxf"] = open(path, encoding="utf-8", errors="replace").read()
    App.closeDocument(doc.Name)
    return out


def main():
    cases = json.loads((HERE / "cases.json").read_text())
    only = sys.argv[1:] and [a for a in sys.argv[1:] if a in cases]
    path = HERE / "freecad.json"
    res = json.loads(path.read_text()) if only and path.exists() else {"freecad": App.Version()[:4], "cases": {}}
    for name, case in cases.items():
        if only and name not in only:
            continue
        try:
            res["cases"][name] = run(name, case)
        except Exception as e:
            import traceback
            res["cases"][name] = {"error": traceback.format_exc()}
            print(f"make: {name} failed: {e}")
    path.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(f"make: {len(res['cases'])} cases")


main()
