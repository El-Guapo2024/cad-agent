"""TechDraw's annotation tools against the real FreeCAD GUI's (ui/scripts/fctechdraw_annot.json).

ui/scripts/fctechdraw_annot.py used each tool of the Add Lines, Add Vertices and Centerlines menus on a view of the plate
from above in FreeCAD 26.3's GUI (3160daf1e2b6) and recorded, after each one, the view's geometry in FreeCAD's numbering
(every edge and vertex), what its Python objects hold, the undo step it made and, at the end, the page exported as SVG
and DXF. The same tools are used here, with the ops the app sends for the values the recording typed, and the geometry,
the undo steps' names, the panels' first values, the page's pens and the DXF's lines are compared.
"""
import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REC = json.loads((ROOT / "ui" / "scripts" / "fctechdraw_annot.json").read_text())
GOLDEN = ROOT / "tests" / "golden" / "techdraw"
_spec = importlib.util.spec_from_file_location("techdraw_annot_prep", GOLDEN / "prep.py")
_prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prep)


def close(a, b, tol=1e-5):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def state(doc, name="View"):
    """The view's edges (curve, start, end) and vertices the way ui/scripts/fctechdraw_annot_dump.py's view_state has them."""
    from cad_agent.techdraw_view import _ends
    geo, s = doc.geo[name], doc.geo[name].scale
    edges = []
    for e in geo.edges:
        a, b = _ends(e.occ)
        edges.append({"start": [a[0] / s, -a[1] / s, 0.0], "end": [b[0] / s, -b[1] / s, 0.0], "kind": e.kind})
    return {"edges": edges, "vertices": [[v.x / s, -v.y / s, 0.0] for v in geo.vertices]}


def same_view(ours, rec, what):
    assert len(ours["edges"]) == len(rec["edges"]), f"{what}: {len(ours['edges'])} edges, FreeCAD {len(rec['edges'])}"
    for i, (o, r) in enumerate(zip(ours["edges"], rec["edges"])):
        assert close(o["start"], r["start"]) and close(o["end"], r["end"]), f"{what} Edge{i}: {o} vs {r}"
    assert len(ours["vertices"]) == len(rec["vertices"]), f"{what}: {len(ours['vertices'])} vertices"
    for i, (o, r) in enumerate(zip(ours["vertices"], rec["vertices"])):
        assert close(o, r), f"{what} Vertex{i}: {o} vs {r}"


# the recording's steps: (key, ops the app sends for the values typed, the undo step FreeCAD made)
def steps():
    cl = REC["cl2lines"]["edit"]
    return [
        ("cosvertex", [{"op": "cosmetic_vertex", "view": "View", "point": [5, 6]}], "Add Cosmetic Vertex"),
        ("midpoints", [{"op": "midpoints", "view": "View", "edges": ["Edge2"]}], "Add midpoint vertices"),
        ("quadrants", [{"op": "quadrants", "view": "View", "edges": ["Edge5"]}], "Add Quadrant vertices"),
        ("cosline", [{"op": "cosmetic_line", "view": "View", "p0": [-20, 15], "p1": [12, 9]}], "Create Cosmetic Line"),
        ("cosline_edit", [{"op": "cosmetic_line_edit", "view": "View", "edge": "Edge6", "p0": [-20, -3], "p1": [12, 9]}], None),
        ("coscircle", [{"op": "cosmetic_circle", "view": "View", "vertices": ["Vertex6", "Vertex8"], "radius": 3}], "Create Cosmetic Circle"),
        ("coscircle_arc", [{"op": "cosmetic_circle", "view": "View", "center": [-20, 15], "radius": 40, "arc": True,
                            "start_angle": 10, "end_angle": 100}], "Create Cosmetic Circle"),
        ("coscircle_edit", [{"op": "cosmetic_circle_edit", "view": "View", "edge": "Edge8", "radius": 6}], None),
        ("cl2lines", [{"op": "centerline", "view": "View", "subs": ["Edge0", "Edge4"], "mode": "Vertical"},
                      {"op": "centerline_edit", "view": "View", "edge": "Edge9", "h_shift": -2, "v_shift": 1.5, "rotate": 10,
                       "extend": 2, "format": {"weight": 0.7}}], "Create Centerline"),
        ("cl2points", [{"op": "centerline", "view": "View", "subs": ["Vertex3", "Vertex8"], "mode": "Vertical"}], "Create Centerline"),
        ("clface", [{"op": "centerline", "view": "View", "subs": ["Face0"], "mode": "Vertical"}], "Create Centerline"),
        ("clface_hole", [{"op": "centerline", "view": "View", "subs": ["Face1"], "mode": "Vertical"}], "Create Centerline"),
    ]


def fresh():
    from cad_agent import techdraw as T
    from cad_agent import techdraw_edit as E
    s = E.Session(None, "Page", [], None, _prep.shape_of)
    E.run_ops(s, [{"op": "new_page"}, {"op": "view", "source": ["plate"], "direction": [0, 0, 1]}])
    return s, T, E


@pytest.fixture
def session():
    return fresh()


@pytest.fixture
def final(session):
    """The page after the recording's tools, the document recomputed."""
    s, T, E = session
    for key, ops, _step in steps():
        E.run_ops(s, ops)
    return s, T, E, T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()


def test_every_step_equals_freecads(session):
    """After each tool the view has FreeCAD's edges and vertices, in FreeCAD's numbering, and the tool's undo step is
    named as FreeCAD names it."""
    from cad_agent import techdraw_annot as A
    s, T, E = session
    same_view(state(T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()), REC["start"], "start")
    for key, ops, step in steps():
        E.run_ops(s, ops)
        doc = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
        assert not doc.errors, doc.errors
        same_view(state(doc), REC[key]["view"], key)
        if step:
            assert REC[key]["undo"]["head"] == [step], key
            assert A.STEP_NAMES[ops[0]["op"]] == step


def test_the_panels_first_values():
    """What a tool's panel shows when it opens: the line's points, the circle's centre and radius."""
    def val(panel, name):
        for tv in panel:
            for w in tv:
                if w["name"] == name:
                    return float(w["text"].split()[0])
    p = REC["cosline"]["panel"]
    assert [val(p, n) for n in ("qsbx1", "qsby1", "qsbx2", "qsby2")] == [-20.0, 15.0, 14.0, 8.0]
    p = REC["coscircle"]["panel"]
    assert [val(p, n) for n in ("qsbCenterX", "qsbCenterY", "qsbRadius")] == [14.0, 8.0, 4.0]
    assert val(REC["coscircle_arc"]["panel"], "qsbRadius") == 40.0
    from cad_agent import techdraw_cosmetic as C
    assert val(REC["cl2lines"]["panel"], "qsbExtend") == C.CENTER_EXTEND
    assert val(REC["cl2lines"]["panel"], "dsbWeight") == C.DEFAULT_FORMAT["weight"]
    for tv in REC["cl2lines"]["panel"]:
        for w in tv:
            if w["name"] == "cboxStyle":
                assert w["items"][C.CENTER_LINE_NUMBER - 1] == w["current"]


def test_the_dxf_has_freecads_lines(final):
    """TechDraw.writeDXFPage of the page as the GUI had it: the view layer's entities."""
    from collections import Counter
    from cad_agent.techdraw_export import page_dxf
    gold = importlib.util.spec_from_file_location("td_golden_helpers", ROOT / "tests" / "test_techdraw_golden.py")
    g = importlib.util.module_from_spec(gold)
    gold.loader.exec_module(g)
    s, T, E, doc = final
    ours = g.dxf_entities(page_dxf(doc).decode())
    theirs = g.dxf_entities(REC["page_dxf"])
    a = Counter(g.dxf_key(e) for e in ours if e["8"][0] == "View" and e["type"] != "TEXT")
    b = Counter(g.dxf_key(e) for e in theirs if e["8"][0] == "View")
    assert a == b, f"ours not FreeCAD's {sorted((a - b).elements())[:4]}; FreeCAD's not ours {sorted((b - a).elements())[:4]}"


def _dashed(svg):
    """[(width, dash lengths in pen widths, first and last point)] of the dashed strokes of the page's drawing."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(svg.encode())
    ns = "{http://www.w3.org/2000/svg}"
    out = []

    def walk(el, off, inh):
        attrs = {**inh, **el.attrib}
        tf = re.search(r"matrix[(]1,0,0,1,([-0-9.]+),([-0-9.]+)[)]", el.get("transform", ""))
        if tf:
            off = (off[0] + float(tf.group(1)), off[1] + float(tf.group(2)))
        if el.tag == ns + "path" and attrs.get("stroke-dasharray") and attrs.get("stroke", "none") != "none":
            w = float(attrs["stroke-width"])
            dash = [float(x) / w for x in attrs["stroke-dasharray"].split(",")]
            nums = [float(x) for x in re.findall(r"-?[0-9]+[.]?[0-9]*", el.get("d"))]
            out.append((w, dash, [(off[0] + nums[0], off[1] + nums[1]), (off[0] + nums[-2], off[1] + nums[-1])]))
        for c in el:
            walk(c, off, {k: v for k, v in attrs.items() if k in ("stroke", "stroke-width", "stroke-dasharray")})
    for g in root.iter(ns + "g"):
        if g.get("id") == "DrawingContent":
            walk(g, (0.0, 0.0), {})
    return out


def test_the_pens(final):
    """The dashed lines of the page: FreeCAD draws a cosmetic edge or a centre line with the ASME line its style names,
    its dash and gap in pen widths, at its weight, from end to end (the SVG's units: 10 to the millimetre)."""
    from cad_agent.techdraw_export import page_svg
    s, T, E, doc = final
    ours, theirs = _dashed(page_svg(doc)), _dashed(REC["page_svg"])
    assert len(ours) == len(theirs) == 7

    def key(t):
        return tuple(round(c, -1) for p in t[2] for c in p)
    for a, b in zip(sorted(ours, key=key), sorted(theirs, key=key)):
        assert a[1] == pytest.approx(b[1], rel=1e-3), (a, b)
        assert a[0] == pytest.approx(b[0], rel=0.05)
        for p, q in zip(a[2], b[2]):
            assert math.dist(p, q) < 1.5, (a, b)


def test_the_eraser(final):
    """The eraser takes the first cosmetic edge, the first centre line and a cosmetic vertex, as in the recording; an
    HLR edge stays."""
    s, T, E, doc = final
    idx = REC["eraser_indexes"]
    assert idx["first_cosmetic_edge"] == 6
    for key in ("edge", "centerline", "vertex", "hlr_edge"):
        cur = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
        edges = cur.geo["View"].edges
        sub = {"edge": "Edge6", "vertex": f"Vertex{idx['first_cosmetic_vertex']}", "hlr_edge": "Edge0",
               "centerline": f"Edge{next(i for i, e in enumerate(edges) if e.cls == 'centerline')}"}[key]
        E.run_ops(s, [{"op": "erase", "view": "View", "subs": [sub]}])
        cur = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
        rec = REC["eraser"][key]["view"]
        assert (len(cur.geo["View"].edges), len(cur.geo["View"].vertices)) == (len(rec["edges"]), len(rec["vertices"])), key


def _stroked(svg):
    """How many stroked paths the page's drawing has."""
    import xml.etree.ElementTree as ET
    ns = "{http://www.w3.org/2000/svg}"
    root = ET.fromstring(svg.encode())
    n = 0
    for g in root.iter(ns + "g"):
        if g.get("id") != "DrawingContent":
            continue

        def walk(el, stroke):
            nonlocal n
            stroke = el.get("stroke", stroke)
            if el.tag == ns + "path" and stroke not in (None, "none") and el.get("fill", "none") == "none":
                n += 1
            for c in el:
                walk(c, stroke)
        walk(g, None)
    return n


def test_line_appearance(final):
    """TaskLineDecor: the style, weight and visibility given to a cosmetic edge and a centre line, then to two HLR
    edges (which get a GeomFormat each); a line made invisible is not drawn, as in the exported page."""
    from cad_agent.techdraw_export import page_svg
    s, T, E, doc = final
    before = _stroked(page_svg(doc))
    fmt = {"op": "format", "view": "View", "style": 2, "weight": 0.9, "visible": False, "line_number": 4}
    E.run_ops(s, [{**fmt, "subs": ["Edge6", "Edge9"]}])
    doc = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
    after_cosmetic = _stroked(page_svg(doc))
    assert before - after_cosmetic == _stroked(REC["page_svg"]) - _stroked(REC["page_svg_formatted"]) == 2
    assert [c["format"]["weight"] for c in doc.get("View").source_value("cosmetic_edges") if "format" in c] == [0.9]
    E.run_ops(s, [{**fmt, "subs": ["Edge0", "Edge1"]}])
    doc = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
    assert after_cosmetic - _stroked(page_svg(doc)) == _stroked(REC["page_svg_formatted"]) - _stroked(REC["page_svg_hlr_formatted"]) == 2
    assert len(doc.get("View").geom_formats) == 2 and doc.get("View").source_value("geom_formats")[0]["index"] == 0
    # Restore Invisible Lines: all visible again
    E.run_ops(s, [{"op": "restore_lines", "view": "View", "kinds": ["all"]}])
    doc = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
    assert _stroked(page_svg(doc)) == before
