"""A TechDraw page's SVG against the real FreeCAD GUI's TechDraw_ExportPageSVG (ui/scripts/fctechdraw.json, page_svg).

ui/scripts/fctechdraw.py made a page in FreeCAD 26.3's GUI from tests/golden/techdraw/breps (a view of the plate, a
projection group with its Right and Top, the four sections, a view of the bracket, dimensions, an annotation and a
balloon) and exported it. The same page is made here with cad_agent/techdraw_edit.py's ops, drawn by
techdraw_export.page_svg, and the two files' view lines are compared: every visible line FreeCAD draws (its thick
pen) lies on one of ours and every visible and hidden edge of ours on one of FreeCAD's, within 0.05 mm, after each
file's transforms. Dimensions, balloons, section lines and text are drawn in each file's own way (ui/PARITY.md,
"TechDraw") and are not compared; their numbers are, in test_techdraw_golden.py.
"""
import importlib.util
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REC = json.loads((ROOT / "ui" / "scripts" / "fctechdraw.json").read_text())
GOLDEN = ROOT / "tests" / "golden" / "techdraw"
_spec = importlib.util.spec_from_file_location("techdraw_svg_prep", GOLDEN / "prep.py")
_prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prep)
TOL_PX = 0.5                       # 0.05 mm at Rez::guiX's 10 units to the millimetre


def made(key):
    m = REC[key]["made"]
    return m if isinstance(m, list) else [m]


def our_page():
    """The recorded page, made with the ops the app sends for the same clicks."""
    from cad_agent import techdraw_edit as E
    s = E.Session(None, "Page", [], None, _prep.shape_of)
    pg = {o["Name"]: o for o in made("projgroup_made")}
    ops = [{"op": "new_page"},
           {"op": "view", "source": ["plate"]},
           {"op": "projgroup", "source": ["plate"], "direction": pg["ProjItem"]["Direction"],
            "x_direction": pg["ProjItem"]["XDirection"], "projections": ["Right", "Top"]}]
    for key, arrow, sym in (("section_made", "Right", "A"), ("section_up_made", "Up", ""), ("section_left_made", "Left", ""),
                            ("section_down_made", "Down", "")):
        ops.append({"op": "section", "base_view": "View", "direction": arrow, "origin": made(key)[0]["SectionOrigin"],
                    "symbol": sym})
    ops.append({"op": "set", "name": "View", "props": {"direction": REC["view_top"]["Direction"]}})
    for key in ("dim_horizontal", "dim_vertical", "dim_length", "dim_radius", "dim_diameter", "dim_two_vertex"):
        d = made(key)[0]
        ops.append({"op": "dimension", "type": d["Type"], "references": [[r[0], sub] for r in d["References2D"] for sub in r[1]]})
    ops.append({"op": "view", "source": ["bracket"]})
    d = made("dim_angle")[0]
    ops.append({"op": "dimension", "type": "Angle", "references": [[r[0], sub] for r in d["References2D"] for sub in r[1]]})
    ops.append({"op": "annotation"})
    b = made("balloon_made")[0]
    ops.append({"op": "balloon", "view": "View", "origin": [b["OriginX"], b["OriginY"]], "at": [b["X"], b["Y"]]})
    E.run_ops(s, ops)
    for st in REC["export_state"]:                  # where the dimensions were dragged to before the export
        if st["TypeId"] == "TechDraw::DrawViewDimension":
            E.run_ops(s, [{"op": "set", "name": st["Name"], "props": {"x": st["X"], "y": st["Y"]}}])
    from cad_agent import techdraw as T
    return s, T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()


# ── SVG paths to points ──────────────────────────────────────────────────────────────────────────────────────────

def _matrix(tf):
    m = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    for name, args in re.findall(r"(matrix|translate|scale)\s*\(([^)]*)\)", tf or ""):
        a = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        n = a if name == "matrix" else [1, 0, 0, 1, a[0], a[1] if len(a) > 1 else 0.0] if name == "translate" else \
            [a[0], 0, 0, a[1] if len(a) > 1 else a[0], 0, 0]
        m = [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3],
             m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]]
    return m


def _samples(d, m, step=3.0):
    """Points along a path's M, L, C, A and Z (absolute), every `step` units, through the transform m."""
    from cad_agent.techdraw_export import _arc_beziers, _svg_path_segs
    T = lambda x, y: (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])  # noqa: E731
    pts, cur, start = [], (0.0, 0.0), (0.0, 0.0)

    def line(a, b):
        n = max(1, int(math.dist(a, b) / step))
        pts.extend(((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)))

    def cubic(p0, c1, c2, p3):
        n = max(2, int((math.dist(p0, c1) + math.dist(c1, c2) + math.dist(c2, p3)) / step))
        for i in range(n + 1):
            t = i / n
            u = 1 - t
            pts.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0],
                        u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]))
    for sg in _svg_path_segs(d):
        if sg[0] == "M":
            cur = start = (sg[1], sg[2])
        elif sg[0] == "L":
            line(T(*cur), T(sg[1], sg[2]))
            cur = (sg[1], sg[2])
        elif sg[0] == "C":
            cubic(T(*cur), T(sg[1], sg[2]), T(sg[3], sg[4]), T(sg[5], sg[6]))
            cur = (sg[5], sg[6])
        elif sg[0] == "A":
            for c1, c2, q in _arc_beziers(cur[0], cur[1], sg[1], sg[2], sg[3], sg[4], sg[5]):
                cubic(T(*cur), T(*c1), T(*c2), T(*q))
                cur = q
            cur = (sg[4], sg[5])
        elif sg[0] == "Z":
            line(T(*cur), T(*start))
            cur = start
    return pts


def strokes(svg: str, want, step=3.0):
    """[(width, points)] of the stroked paths `want(path element, inherited attributes)` keeps, a point every `step`."""
    root = ET.fromstring(svg.encode())
    out = []

    def walk(el, m, inh):
        tag = el.tag.split("}")[-1]
        m = [*m]
        if el.get("transform"):
            from cad_agent.techdraw_export import _mul
            m = _mul(m, _matrix(el.get("transform")))
        a = dict(inh)
        for k in ("stroke", "stroke-width", "fill", "id"):
            if el.get(k) is not None:
                a[k] = el.get(k)
        if tag == "g" and a.get("id", "").endswith(".svg") and "template" not in a:
            a["template"] = True
        if tag == "path" and el.get("d") and not a.get("template") and want(el, a):
            out.append((float(a.get("stroke-width", "1")), _samples(el.get("d"), m, step)))
        for c in el:
            walk(c, m, a)
    walk(root, [1.0, 0.0, 0.0, 1.0, 0.0, 0.0], {})
    return out


def _grid(pts, cell=2.0):
    g = {}
    for p in pts:
        g.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(p)
    return g


def _near(g, p, tol, cell=2.0):
    cx, cy = int(p[0] // cell), int(p[1] // cell)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for q in g.get((cx + dx, cy + dy), ()):
                if (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 <= tol * tol:
                    return True
    return False


@pytest.fixture(scope="module")
def svgs():
    from cad_agent.techdraw_export import page_svg
    _, doc = our_page()
    return page_svg(doc), REC["page_svg"]


def test_the_page_is_freecads_size(svgs):
    ours, theirs = svgs
    r0, r1 = ET.fromstring(ours.encode()), ET.fromstring(theirs.encode())
    assert (r0.get("width"), r0.get("height"), r0.get("viewBox")) == (r1.get("width"), r1.get("height"), r1.get("viewBox"))


def test_every_visible_line_freecad_draws_lies_on_ours(svgs):
    ours, theirs = svgs
    fc = [pts for w, pts in strokes(theirs, lambda el, a: a.get("stroke", "none") != "none" and a.get("fill", "none") == "none")
          if w > 7.1]                    # the view's visible lines (QGIEdge's pen); the section lines' are 7.0
    mine = [p for _, pts in strokes(ours, lambda el, a: el.get("data-sub") is not None, 0.25) for p in pts]
    g = _grid(mine)
    off = [pts for pts in fc if not all(_near(g, p, TOL_PX) for p in pts)]
    assert fc and not off, f"{len(off)} of {len(fc)} of FreeCAD's visible lines are not on ours, e.g. {off[0][:3] if off else ''}"


def test_every_edge_of_ours_lies_on_one_of_freecads(svgs):
    ours, theirs = svgs
    fc = [p for w, pts in strokes(theirs, lambda el, a: a.get("stroke", "none") != "none" and a.get("fill", "none") == "none", 0.25)
          if w > 3.0 for p in pts]
    mine = [pts for _, pts in strokes(ours, lambda el, a: el.get("data-sub") is not None)]
    g = _grid(fc)
    off = [pts for pts in mine if not all(_near(g, p, TOL_PX) for p in pts)]
    assert mine and not off, f"{len(off)} of {len(mine)} of our edges are not on FreeCAD's, e.g. {off[0][:3] if off else ''}"


def test_the_recorded_objects_are_ours():
    """The names, labels, directions and places FreeCAD's commands gave the objects (fctechdraw.json's *_made)."""
    s, doc = our_page()
    by = {o.name: o for o in s.objs}
    for key in ("view_made", "projgroup_made", "section_made", "section_up_made", "section_left_made", "section_down_made",
                "annotation_made", "balloon_made", "view_bracket"):
        for fo in made(key):
            o = by[fo["Name"]]
            assert (o.label or o.name) == fo["Label"], fo["Name"]
            for k, ours in (("Direction", getattr(o, "direction", None)), ("XDirection", getattr(o, "x_direction", None)),
                            ("SectionNormal", getattr(o, "section_normal", None))):
                if fo.get(k) is not None and ours is not None and key != "view_made":
                    assert all(abs(a - b) <= 1e-9 for a, b in zip(ours, fo[k])), (fo["Name"], k, ours, fo[k])
            if fo.get("Rotation") is not None and hasattr(o, "rotation"):
                assert abs(o.rotation - fo["Rotation"]) <= 1e-9, fo["Name"]
            if fo["Name"] in doc.pos:
                g = doc.group_of(fo["Name"])
                x, y = doc.pos[fo["Name"]]
                if g is not None:
                    x, y = x - g.x, y - g.y
                assert abs(x - fo["X"]) <= 1e-6 and abs(y - fo["Y"]) <= 1e-6, (fo["Name"], x, y, fo["X"], fo["Y"])


def test_the_recorded_dimensions_are_ours():
    """Each dimension command's object as FreeCAD's dimMaker and positionDimText made it: Type, FormatSpec, X, Y (before
    the GUI's "Drag Dimension"), getRawValue and getText, and its undo step."""
    from cad_agent import techdraw as T
    from cad_agent import techdraw_edit as E
    s = E.Session(None, "Page", [], None, _prep.shape_of)
    E.run_ops(s, [{"op": "new_page"}, {"op": "view", "source": ["plate"]},
                  {"op": "set", "name": "View", "props": {"direction": REC["view_top"]["Direction"]}},
                  {"op": "view", "source": ["bracket"]}])
    keys = ("dim_horizontal", "dim_vertical", "dim_length", "dim_radius", "dim_diameter", "dim_two_vertex", "dim_angle")
    for key in keys:
        fo = REC[key]["dimensions"][0]
        refs = [[r[0], sub] for r in fo["References2D"] for sub in r[1]]
        E.run_ops(s, [{"op": "dimension", "type": fo["Type"], "references": refs, "name": fo["Name"]}])
    doc = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
    for key in keys:
        fo = REC[key]["dimensions"][0]
        o = doc.get(fo["Name"])
        assert (o.type, o.format_spec, o.measure_type) == (fo["Type"], fo["FormatSpec"], fo["MeasureType"]), key
        assert abs(o.x - fo["X"]) <= 1e-6 and abs(o.y - fo["Y"]) <= 1e-6, (key, o.x, o.y, fo["X"], fo["Y"])
        m = doc.dims[fo["Name"]]
        assert abs(m["value"] - fo["getRawValue"]) <= 1e-9 and m["unaltered"] == fo["getText"], (key, m["value"], m["unaltered"])
        assert REC[key]["undo"]["head"] == ["Create dimension"]
