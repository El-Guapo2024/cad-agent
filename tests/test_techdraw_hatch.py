"""TechDraw's hatching against FreeCAD: the geometric hatch's lines (makeGeomHatch in freecadcmd, the GUI's exported page),
the objects the tools make, the undo steps and the tree (ui/scripts/fctechdraw_hatch.json).

ui/scripts/fctechdraw_hatch.py used TechDraw_GeometricHatch and TechDraw_Hatch on the faces of a view of the plate from
above in FreeCAD 26.3's GUI (3160daf1e2b6): the panels (TaskGeomHatch, TaskHatch), the objects made with their properties
and their view providers', the undo steps, the tree and the page exported as SVG. The same hatches are made here with the
ops the app sends and compared; tests/golden/techdraw (make.py) holds the hatch lines to freecadcmd's makeGeomHatch for
patterns with dashes, rotations and offsets too.
"""
import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REC = json.loads((ROOT / "ui" / "scripts" / "fctechdraw_hatch.json").read_text())
GOLDEN = ROOT / "tests" / "golden" / "techdraw"
_spec = importlib.util.spec_from_file_location("techdraw_hatch_prep", GOLDEN / "prep.py")
_prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prep)


def fresh():
    from cad_agent import techdraw as T
    from cad_agent import techdraw_edit as E
    s = E.Session(None, "Page", [], None, _prep.shape_of)
    E.run_ops(s, [{"op": "new_page"}, {"op": "view", "source": ["plate"], "direction": [0, 0, 1]}])
    return s, T, E


def doc_of(s, T):
    return T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()


def obj(key, type_id):
    return next(o for o in REC[key]["hatches"]["objects"] if o["TypeId"] == type_id)


GEOM = {"op": "geomhatch", "view": "View", "faces": ["Face0"], "name_pattern": "Diagonal4", "scale_pattern": 2.0,
        "pattern_rotation": 15.0, "pattern_offset": [1.0, 2.0, 0.0], "weight_pattern": 0.3}


def _segments(svg, stroke):
    """The straight strokes of the page's drawing in `stroke`: ((x0, y0), (x1, y1)) in the SVG's units about the view."""
    import xml.etree.ElementTree as ET
    ns = "{http://www.w3.org/2000/svg}"
    root = ET.fromstring(svg.encode())
    out = []
    for g in root.iter(ns + "g"):
        if g.get("id") != "DrawingContent":
            continue

        def walk(el, off, st):
            tf = re.search(r"matrix[(]1,0,0,1,([-0-9.]+),([-0-9.]+)[)]", el.get("transform", ""))
            if tf:
                off = (off[0] + float(tf.group(1)), off[1] + float(tf.group(2)))
            st = el.get("stroke", st)
            if el.tag == ns + "path" and st == stroke:
                nums = [float(x) for x in re.findall(r"-?[0-9]+[.]?[0-9]*", el.get("d"))]
                if len(nums) == 4:
                    out.append(((off[0] + nums[0], off[1] + nums[1]), (off[0] + nums[2], off[1] + nums[3])))
            for c in el:
                walk(c, off, st)
        walk(g, (0.0, 0.0), None)
    return out


def test_the_geometric_hatch_draws_freecads_lines():
    """The 7 lines Diagonal4 leaves in the plate's face at scale 2, turned 15 degrees and moved by (1, 2): FreeCAD's page
    has them as separate strokes in the hatch colour, 0.3 mm wide."""
    from cad_agent.techdraw_export import page_svg
    s, T, E = fresh()
    E.run_ops(s, [GEOM])
    doc = doc_of(s, T)
    ours = _segments(page_svg(doc), "#00ff00")
    theirs = _segments(REC["geomhatch_svg"], "#00ff00")
    assert len(ours) == len(theirs) == 7
    # the page's own offset: FreeCAD's strokes are about the view's centre, ours about the page's corner
    ox, oy = ours[0][0][0] - theirs[0][0][0], ours[0][0][1] - theirs[0][0][1]

    def key(seg):
        (a, b), (c, d) = seg
        return tuple(round(v, 0) for v in sorted([(a, b), (c, d)])[0] + sorted([(a, b), (c, d)])[1])
    to = sorted(((round(a[0] - ox, 1), round(a[1] - oy, 1)), (round(b[0] - ox, 1), round(b[1] - oy, 1))) for a, b in ours)
    for (a, b), (c, d) in zip(sorted(((a, b) if a <= b else (b, a)) for a, b in to),
                              sorted(((a, b) if a <= b else (b, a)) for a, b in theirs)):
        assert math.dist(a, c) < 0.5 and math.dist(b, d) < 0.5, (a, b, c, d)
    assert key


def test_the_objects_and_their_properties():
    s, T, E = fresh()
    E.run_ops(s, [GEOM, {"op": "hatch", "view": "View", "faces": ["Face1"], "hatch_scale": 3.0}])
    g, h = s.get("GeomHatch"), s.get("Hatch")
    fg, fh = obj("geomhatch_edit", "TechDraw::DrawGeomHatch"), obj("hatch_edit", "TechDraw::DrawHatch")
    assert (g.name, g.source, list(g.faces), g.name_pattern) == (fg["Name"], fg["Source"][0], fg["Source"][1], fg["NamePattern"])
    assert (g.file_pattern, g.pattern_rotation, list(g.pattern_offset)) == (fg["FilePattern"].rsplit("/", 1)[1], fg["PatternRotation"], fg["PatternOffset"])
    assert g.weight_pattern == fg["ViewProvider"]["WeightPattern"] and list(g.color_pattern)[:3] == fg["ViewProvider"]["ColorPattern"][:3]
    assert (h.name, h.source, list(h.faces)) == (fh["Name"], fh["Source"][0], fh["Source"][1])
    assert h.hatch_pattern == fh["HatchPattern"].rsplit("/", 1)[1] and list(h.hatch_color)[:3] == fh["ViewProvider"]["HatchColor"][:3]
    assert (h.hatch_scale, h.hatch_rotation, list(h.hatch_offset)) == (3.0, fh["ViewProvider"]["HatchRotation"], fh["ViewProvider"]["HatchOffset"])
    # the tree: the hatches under their view
    rows = [(r["label"], r["depth"]) for r in E.tree(s.objs)]
    assert rows == [(t["text"], t["depth"] - 1) for t in REC["tree"][3:]]


def test_undo_steps_and_messages():
    from cad_agent import techdraw_annot as A
    assert A.STEP_NAMES["geomhatch"] == REC["geomhatch"]["undo"]["head"][0] == "Create GeomHatch"
    assert A.STEP_NAMES["hatch"] == "Create Hatch" and "Create Hatch" in REC["undo_names"]
    s, T, E = fresh()
    E.run_ops(s, [{"op": "hatch", "view": "View", "faces": ["Face1"]}])
    with pytest.raises(E.TechDrawEditError, match="already hatched"):
        E.run_ops(s, [{"op": "hatch", "view": "View", "faces": ["Face1"]}])
    E.run_ops(s, [{"op": "hatch", "view": "View", "faces": ["Face1"], "replace": True}])   # Remove old hatch, then Create Hatch
    assert [o.name for o in s.objs if o.kind == "DrawHatch"] == ["Hatch"]
    with pytest.raises(E.TechDrawEditError, match="No faces"):
        E.run_ops(s, [{"op": "geomhatch", "view": "View", "faces": []}])
    with pytest.raises(E.TechDrawEditError, match="no Face9"):
        E.run_ops(s, [{"op": "geomhatch", "view": "View", "faces": ["Face9"]}])
    E.run_ops(s, [{"op": "delete", "name": "View"}])         # the view takes its hatches with it
    assert not [o for o in s.objs if o.kind in ("DrawHatch", "DrawGeomHatch")]


def test_the_panels_first_values():
    def text(panel, name):
        for tv in panel:
            for w in tv:
                if w["name"] == name:
                    return w.get("text", w.get("current"))
    p = REC["geomhatch"]["panel"]
    assert [text(p, n) for n in ("cbName", "sbScale", "sbWeight", "dsbRotation", "dsbOffsetX", "dsbOffsetY")] == \
        ["Diamond", "1.00", "0.50", "0.00", "0.00", "0.00"]
    from cad_agent import techdraw_hatch as H
    assert [w for tv in p for w in tv if w["name"] == "cbName"][0]["items"] == H.pattern_names(H.DEFAULT_PAT)


HATCH_GOLDEN = json.loads((GOLDEN / "hatch.json").read_text())["cases"]


@pytest.fixture(scope="module")
def plate_faces():
    from cad_agent import techdraw_cosmetic as C
    s, T, E = fresh()
    doc = doc_of(s, T)
    return C.faces_of(doc.geo["View"], doc.get("View"))


@pytest.mark.parametrize("case", HATCH_GOLDEN, ids=lambda c: f"{c['name']}-{c['scale']}-face{c['face']}")
def test_the_trimmed_lines_equal_makegeomhatch(case, plate_faces):
    """DrawGeomHatch::getTrimmedLines through TechDraw.makeGeomHatch: the lines of each pattern row left in the face, dashes
    included, for FCPAT.pat's patterns and hatch.pat's."""
    from cad_agent import techdraw_hatch as H
    lines = ((GOLDEN / "hatch.pat").read_text().splitlines() if case["file"] == "hatch.pat"
             else (H.PAT_DIR / case["file"]).read_text().splitlines())
    specs = H.specs_in(lines, case["name"])
    assert specs
    sets = H.trimmed_lines(H.face_of(plate_faces[case["face"]]), specs, case["scale"])
    ours = sorted([*sorted([(round(a[0], 5), round(a[1], 5)), (round(b[0], 5), round(b[1], 5))])[0],
                   *sorted([(round(a[0], 5), round(a[1], 5)), (round(b[0], 5), round(b[1], 5))])[1]]
                  for seg in sets for a, b in seg)
    theirs = case["segments"]
    assert len(ours) == len(theirs), f"{len(ours)} lines, FreeCAD {len(theirs)}"
    for o, t in zip(ours, theirs):
        assert all(abs(x - y) < 2e-4 for x, y in zip(o, t)), (o, t)
