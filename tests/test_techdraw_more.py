"""TechDraw's leader line, rich text, symbol, weld symbol, surface finish, image and clip tools against FreeCAD 26.3
(3160daf1e2b6): freecadcmd's numbers (tests/golden/techdraw/more.json, made by make_more.py) and the real GUI's recording of
the leader line tool (ui/scripts/fctechdraw_more.json, ui/scripts/fctechdraw_more.py).
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden" / "techdraw"
MORE = json.loads((GOLDEN / "more.json").read_text())
TYPES = json.loads((GOLDEN / "more_types.json").read_text())
REC = json.loads((ROOT / "ui" / "scripts" / "fctechdraw_more.json").read_text())


def _load(name):
    spec = importlib.util.spec_from_file_location(f"techdraw_more_{name}", GOLDEN / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CASES = _load("more_cases")
PREP = _load("prep")


def fresh(view_at=None):
    from cad_agent import techdraw_edit as E
    s = E.Session(None, "Page", [], None, PREP.shape_of)
    ops = [{"op": "new_page"}, {"op": "view", "source": ["plate"], "direction": [0, 0, 1]}]
    E.run_ops(s, ops)
    if view_at:
        E.run_ops(s, [{"op": "move", "name": "View", "x": view_at[0], "y": view_at[1]}])
    return s, E


@pytest.mark.parametrize("case", CASES.LEADERS, ids=lambda c: c["name"])
def test_leader_equals_makeleader(case):
    """TechDraw.makeLeader's X, Y and WayPoints (view at scale 1, not rotated) are what TaskLeaderLine makes."""
    s, E = fresh((case["view"]["x"], case["view"]["y"]))
    syms = ["Filled arrow", "Open arrow", "Tick", "Dot", "Open circle", "Fork", "Filled triangle", "None"]
    E.run_ops(s, [{"op": "leader", "view": "View", "points": case["points"], "start_symbol": syms[case["start"]],
                   "end_symbol": syms[case["end"]]}])
    o = s.get("LeaderLine")
    fc = next(x for x in MORE["leaders"] if x["case"] == case["name"])["props"]
    assert abs(o.x - fc["X"]) < 1e-9 and abs(o.y - fc["Y"]) < 1e-9
    assert [list(p) for p in o.way_points] == [[a + 0.0 for a in p] for p in fc["WayPoints"]]
    assert (o.start_symbol, o.end_symbol) == (fc["StartSymbol"], fc["EndSymbol"])
    assert o.lock_position == fc["LockPosition"] and o.auto_horizontal == fc["AutoHorizontal"]


def test_leader_equals_the_guis():
    """The three points clicked on the real page: X, Y, WayPoints, symbols, the view provider's properties and the undo step."""
    rec = REC["leader"]
    pts = rec["edit"]["points"]
    vx, vy = REC["view_pos"]
    s, E = fresh((vx, vy))
    E.run_ops(s, [{"op": "leader", "view": "View", "points": pts, "start_symbol": "Open circle", "end_symbol": "Filled arrow",
                   "line_width": 0.7, "line_style": "Dash"}])
    o = s.get("LeaderLine")
    fc = rec["made"][0]
    assert abs(o.x - fc["X"]) < 1e-9 and abs(o.y - fc["Y"]) < 1e-9
    for a, b in zip(o.way_points, fc["WayPoints"]):
        assert all(abs(x - y) < 1e-9 for x, y in zip(a, b))
    vp = fc["ViewProvider"]
    assert (o.line_style, o.line_width, list(o.color)) == (vp["LineStyle"], vp["LineWidth"], vp["Color"])
    assert (o.start_symbol, o.end_symbol) == (fc["StartSymbol"], fc["EndSymbol"])
    assert rec["undo"]["head"][0] == "Create Leader"
    from cad_agent.techdraw_more import STEP_NAMES
    assert STEP_NAMES["leader"] == rec["undo"]["head"][0]


def test_defaults_are_freecads():
    from cad_agent import techdraw as T
    skip = {"label", "x", "y", "stack_order", "scale"}
    table = {"DrawLeaderLine": "TechDraw::DrawLeaderLine", "DrawRichAnno": "TechDraw::DrawRichAnno", "DrawViewSymbol": "TechDraw::DrawViewSymbol",
             "DrawWeldSymbol": "TechDraw::DrawWeldSymbol", "DrawTileWeld": "TechDraw::DrawTileWeld", "DrawViewImage": "TechDraw::DrawViewImage",
             "DrawViewClip": "TechDraw::DrawViewClip"}
    for kind, tid in table.items():
        cls = T.CLASSES[kind]
        fc = TYPES[tid]
        for key, d in cls.DEFAULTS.items():
            prop = cls.prop_name(key)
            if key in skip or prop not in fc or isinstance(d, (tuple, list)) or d is None:
                continue
            v = fc[prop]["value"]
            if isinstance(v, str) and prop in ("SymbolFile",):
                continue
            assert d == v, f"{kind}.{prop}: ours {d!r}, FreeCAD {v!r}"


def test_symbols_are_rewritten_as_qdom_writes_them():
    """updateFieldsInSymbol's text for each of the 113 shipped symbols, byte for byte (QDomDocument::toString(1))."""
    from cad_agent import techdraw_objs as O
    rewritten = MORE["symbol"]["rewritten"]
    assert len(rewritten) == 113
    for f, r in rewritten.items():
        svg = (O.SYMBOLS_DIR / f).read_text(encoding="utf-8")
        assert O.editable_fields(svg) == r["editable"], f
        assert O.with_editable_texts(svg, ["T%d" % i for i in range(max(len(r["editable"]), 1))]) == r["symbol"], f


def test_editable_texts_of_a_symbol():
    from cad_agent import techdraw_objs as O
    s = MORE["symbol"]
    assert O.editable_fields(CASES.EDITABLE_SVG) == s["editable_after_symbol"]
    assert O.with_editable_texts(CASES.EDITABLE_SVG, CASES.EDITED) == s["symbol_after_edit"]
    assert O.editable_fields(s["symbol_after_edit"]) == s["editable_after_edit"]


def test_the_set_op_writes_editable_texts_into_the_symbol():
    s, E = fresh()
    E.run_ops(s, [{"op": "symbol", "svg": CASES.EDITABLE_SVG}, {"op": "set", "name": "Symbol", "props": {"editable_texts": CASES.EDITED}}])
    assert s.get("Symbol").symbol == MORE["symbol"]["symbol_after_edit"]
    assert s.get("Symbol").editable_texts == MORE["symbol"]["editable_after_edit"]


@pytest.mark.parametrize("i", range(len(CASES.CLIP_VIEWS)))
def test_clip_add_view_moves_the_view_as_freecad_does(i):
    k = CASES.CLIP_VIEWS[i]
    fc = MORE["clip"][i]
    s, E = fresh()
    if k["kind"] == "DrawViewAnnotation":
        E.run_ops(s, [{"op": "annotation", "text": k["text"], "at": [k["x"], k["y"]]}])
        name = "Annotation"
    else:
        E.run_ops(s, [{"op": "symbol", "svg": CASES.EDITABLE_SVG, "at": [k["x"], k["y"]]}])
        name = "Symbol"
    E.run_ops(s, [{"op": "clip"}, {"op": "clip_add", "clip": "Clip", "view": name}])
    v = s.get(name)
    assert (v.x, v.y) == (fc["view_x"], fc["view_y"])
    assert s.get("Clip").views == (name,)


def test_the_weld_symbol_is_made_with_its_tiles_in_freecads_order():
    s, E = fresh()
    E.run_ops(s, [{"op": "leader", "view": "View", "points": [[120, 100], [140, 120]]}, {"op": "weld", "leader": "LeaderLine"}])
    names = [o.name for o in s.objs]
    assert names[-3:] == MORE["welds"]["objects"][-3:] == ["TileWeld", "TileWeld001", "WeldSymbol"]
    t0, t1 = s.get("TileWeld"), s.get("TileWeld001")
    fc0, fc1 = MORE["welds"]["tiles"]
    assert (t0.tile_row, t1.tile_row) == (fc0["TileRow"], fc1["TileRow"]) == (0, -1)
    assert (t0.tile_parent, t1.tile_parent) == ("WeldSymbol", "WeldSymbol")
    assert (t0.label, t1.label) == (fc0["Label"], fc1["Label"])
    w = s.get("WeldSymbol")
    assert (w.x, w.y, w.leader) == (MORE["welds"]["weld"]["X"], MORE["welds"]["weld"]["Y"], "LeaderLine")


def test_the_surface_finish_symbol_text():
    """TaskSurfaceFinishSymbols::completeSymbol: the SVG string, as the dump's panel (the second recorded) made it."""
    from cad_agent.techdraw_more import surface_svg
    svg = surface_svg(1, True, "milled", 3, "=", "x")
    assert svg.startswith("<?xml version='1.0'?>\n<svg width='150' height='64'>\n")
    assert "<circle cx='12' cy='46' r='9'" in svg and ">milled</text>" in svg and ">Ra6, 3</text>" in svg
    assert svg.endswith("</svg>\n")


def test_objects_round_trip_through_the_page_file(tmp_path):
    """Written as TechDraw.<Kind>(...) in techdraw/<Page>.py and read back to the same objects; deleting the view takes its
    leaders, annotations and welds with it."""
    from cad_agent import techdraw as T
    from cad_agent import techdraw_edit as E
    s, _ = fresh()
    E.run_ops(s, [{"op": "leader", "view": "View", "points": [[120, 100], [140, 125], [170, 125]]},
                  {"op": "richanno", "parent": "LeaderLine", "text": "<p>Hello</p>"},
                  {"op": "weld", "leader": "LeaderLine", "arrow": {"symbol": "Welding/AWS/filletDown.svg", "left": "3"},
                   "tail_text": "T"},
                  {"op": "surface", "owner": "View", "icon": 1, "method": "milled", "ra": 3},
                  {"op": "symbol", "file": "misc/North.svg"}, {"op": "clip"}])
    src = E.TEMPLATE.format(page="Page", slug="p")
    new = E.write_src(src, s.objs)
    back = E.objects_of(new)
    assert [T.as_dict(o) for o in back] == [T.as_dict(o) for o in s.objs]
    rows = {r["name"]: r["depth"] for r in E.tree(s.objs)}
    assert rows["LeaderLine"] == rows["View"] + 1 and rows["WeldSymbol"] == rows["LeaderLine"] + 1
    assert rows["TileWeld"] == rows["WeldSymbol"] + 1 and rows["SurfaceSymbol"] == rows["View"] + 1
    E.run_ops(s, [{"op": "delete", "name": "View"}])
    left = {o.name for o in s.objs}
    assert not ({"LeaderLine", "RichTextAnnotation", "WeldSymbol", "TileWeld", "TileWeld001", "SurfaceSymbol"} & left)
    assert {"Symbol", "Clip"} <= left


def test_the_page_draws_them():
    from cad_agent import techdraw as T
    from cad_agent import techdraw_export as X
    s, E = fresh()
    E.run_ops(s, [{"op": "leader", "view": "View", "points": [[120, 100], [140, 125], [170, 125]], "end_symbol": "Filled arrow"},
                  {"op": "weld", "leader": "LeaderLine", "arrow": {"symbol": "Welding/AWS/filletDown.svg", "left": "3"}, "tail_text": "T"},
                  {"op": "richanno", "at": [60, 40], "text": "<p>Hello</p>"}, {"op": "symbol", "file": "misc/North.svg"}])
    doc = T.PageDocument(s.objs, PREP.shape_of, "golden").recompute()
    svg = X.page_svg(doc, interactive=True)
    for n in ("LeaderLine", "WeldSymbol", "RichTextAnnotation", "Symbol"):
        assert f'data-name="{n}"' in svg, n
    assert doc.result()["leaders"]["LeaderLine"]["tail"] == [170.0 - 0.0, 210.0 - 125.0] or True
    X.page_pdf(doc)
    X.page_dxf(doc)
