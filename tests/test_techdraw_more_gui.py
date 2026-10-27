"""TechDraw's leader line, rich text, symbol, weld symbol, surface finish, image and clip tools against what the real FreeCAD 26.3
GUI (3160daf1e2b6) did with them: ui/scripts/fctechdraw_more.json (ui/scripts/fctechdraw_more.py: the panels, the clicks on the
page, the objects made with their view providers' properties, the undo steps, the tree).
"""
import base64
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden" / "techdraw"
REC = json.loads((ROOT / "ui" / "scripts" / "fctechdraw_more.json").read_text())
_spec = importlib.util.spec_from_file_location("techdraw_more_gui_prep", GOLDEN / "prep.py")
PREP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PREP)


def fresh():
    from cad_agent import techdraw_edit as E
    s = E.Session(None, "Page", [], None, PREP.shape_of)
    E.run_ops(s, [{"op": "new_page"}, {"op": "view", "source": ["plate"], "direction": [0, 0, 1]}])
    return s, E


def test_leader_at_scale_and_rotation_equals_the_guis():
    """A view at scale 0.5 turned 30 degrees: X, Y and WayPoints are unscaled and unrotated (createLeaderFeature)."""
    rec = REC["leader_scaled"]
    s, E = fresh()
    E.run_ops(s, [{"op": "set", "name": "View", "props": {"scale_type": "Custom", "scale": 0.5, "rotation": 30.0}},
                  {"op": "leader", "view": "View", "points": rec["edit"]["points"]}])
    o = s.get("LeaderLine")
    fc = rec["made"][0]
    assert abs(o.x - fc["X"]) < 1e-9 and abs(o.y - fc["Y"]) < 1e-9
    for a, b in zip(o.way_points, fc["WayPoints"]):
        assert all(abs(x - y) < 1e-9 for x, y in zip(a, b))


def test_weld_symbol_equals_the_guis():
    from cad_agent.techdraw_more import STEP_NAMES
    rec = REC["weld"]
    s, E = fresh()
    E.run_ops(s, [{"op": "leader", "view": "View", "points": [[120, 100], [140, 125]]},
                  {"op": "weld", "leader": "LeaderLine", "arrow": {"symbol": "Welding/AWS/filletDown.svg", "left": "3", "center": "(2)", "right": "5"},
                   "other": {"symbol": "Welding/AWS/VUp.svg", "left": "4"}, "tail_text": "T1", "field_weld": True, "all_around": True}])
    t0, t1, w = s.get("TileWeld"), s.get("TileWeld001"), s.get("WeldSymbol")
    f0, f1, fw = rec["made"]
    assert (t0.left_text, t0.center_text, t0.right_text, t0.tile_row, t0.tile_parent) == (f0["LeftText"], f0["CenterText"], f0["RightText"], f0["TileRow"], f0["TileParent"])
    assert (t1.left_text, t1.tile_row) == (f1["LeftText"], f1["TileRow"])
    assert t0.symbol_file.endswith("AWS/filletDown.svg") and f0["SymbolFile"].endswith("filletDown.svg")
    assert t1.symbol_file.endswith("AWS/VUp.svg") and f1["SymbolFile"].endswith("VUp.svg")
    assert (w.tail_text, w.all_around, w.field_weld, w.alternating_weld, w.leader) == (fw["TailText"], fw["AllAround"], fw["FieldWeld"], fw["AlternatingWeld"], fw["Leader"])
    vp = fw["ViewProvider"]
    assert (w.font, w.font_size, w.tile_font_size) == (vp["Font"], vp["FontSize"], vp["TileFontSize"])
    assert STEP_NAMES["weld"] == rec["undo"]["head"][0] and STEP_NAMES["weld_edit"] == REC["weld_edit"]["undo"]["head"][0]
    tree = {r["name"]: r["depth"] for r in E.tree(s.objs)}
    for n in ("LeaderLine", "WeldSymbol", "TileWeld", "TileWeld001"):
        assert tree[n] == next(r for r in rec["tree"] if r["text"] == n)["depth"] - 1, n


def test_the_symbol_is_the_files_text_and_where_freecad_puts_it():
    from cad_agent import techdraw_objs as O
    s, E = fresh()
    E.run_ops(s, [{"op": "symbol", "file": "misc/North.svg"}, {"op": "symbol", "file": "other/Diameter.svg", "owner": "View"}])
    a, b = REC["symbol_page"]["made"][0], REC["symbol_owner"]["made"][0]
    assert s.get("Symbol").symbol == a["Symbol"] == O.symbol_path("misc/North.svg").read_text(encoding="utf-8")
    assert (s.get("Symbol").x, s.get("Symbol").y, s.get("Symbol").owner) == (a["X"], a["Y"], a["Owner"])
    assert s.get("Symbol001").symbol == b["Symbol"]
    assert (s.get("Symbol001").x, s.get("Symbol001").y, s.get("Symbol001").owner) == (b["X"], b["Y"], b["Owner"])
    assert s.get("Symbol").scale_type == a["ScaleType"] == "Custom"
    assert REC["symbol_page"]["undo"]["head"][0] == "Create Symbol"
    assert REC["symbol_page"]["file_dialogs"][0]["title"] == "Choose an SVG file to open"


def test_rich_text_equals_the_guis():
    rec = REC["richanno_plain"]["made"][0]
    s, E = fresh()
    E.run_ops(s, [{"op": "richanno", "at": [rec["X"], rec["Y"]], "text": rec["AnnoText"], "show_frame": False}])
    o = s.get("RichTextAnnotation")
    assert (o.x, o.y, o.anno_parent, o.show_frame, o.max_width, o.label) == (rec["X"], rec["Y"], None, rec["ShowFrame"], rec["MaxWidth"], rec["Label"])
    assert o.anno_text == rec["AnnoText"]
    vp = rec["ViewProvider"]
    assert (o.line_width, o.line_style, list(o.line_color)) == (vp["LineWidth"], vp["LineStyle"], vp["LineColor"])
    v = REC["richanno_view"]["made"][0]
    E.run_ops(s, [{"op": "richanno", "parent": "View", "at": [v["X"], v["Y"]], "max_width": 40.0, "show_frame": True}])
    o = s.get("RichTextAnnotation001")
    assert (o.anno_parent, o.max_width, o.show_frame, o.label) == (v["AnnoParent"], v["MaxWidth"], v["ShowFrame"], v["Label"])
    assert REC["richanno_plain"]["undo"]["head"][0] == "Create Annotation" and REC["richanno_edit"]["undo"]["head"][0] == "Edit Annotation"


def test_surface_finish_symbols_equal_the_guis():
    from cad_agent.techdraw_more import surface_svg
    v, e = REC["surface_vertex"]["made"][0], REC["surface_edge"]["made"][0]
    assert surface_svg(1, True, "milled", 3, "⟂", "x") == v["Symbol"]
    assert surface_svg(4, False, "ground", 0, "=", "", "0.8", "N3", "N5") == e["Symbol"]
    assert surface_svg(0, True, "", 0) == REC["surface_none"]["made"][0]["Symbol"]
    s, E = fresh()
    E.run_ops(s, [{"op": "surface", "owner": "View.Vertex1", "icon": 1, "method": "milled", "ra": 3, "lay": "⟂", "addition": "x", "angle": 30.0},
                  {"op": "surface", "owner": "View.Edge2"}, {"op": "surface", "owner": "Page"}, {"op": "surface", "owner": "View.Face0"},
                  {"op": "leader", "view": "View", "points": [[120, 100], [140, 125]]}, {"op": "surface", "owner": "LeaderLine"}])
    for n, k in (("SurfaceSymbol", "surface_vertex"), ("SurfaceSymbol001", "surface_edge"), ("SurfaceSymbol002", "surface_none"),
                 ("SurfaceSymbol003", "surface_face"), ("SurfaceSymbol004", "surface_leader")):
        o, f = s.get(n), REC[k]["made"][0]
        assert (o.owner, round(o.x, 9), round(o.y, 9), o.rotation, o.stack_order) == (f["Owner"], round(f["X"], 9), round(f["Y"], 9), f["Rotation"],
                                                                                      f["ViewProvider"]["StackOrder"]), n
    assert REC["surface_none"]["undo"]["head"][0] == "Surface Finish Symbols"
    assert REC["surface_wrong_page"]["dialogs"][0]["text"] == "Selected object is not a part view, nor a leader line"


def test_image_and_clip_equal_the_guis(tmp_path):
    s, E = fresh()
    s.pdir = tmp_path
    (tmp_path / "pic.png").write_bytes(base64.b64decode(REC["image_png_b64"]))
    E.run_ops(s, [{"op": "image", "file": "pic.png"}, {"op": "image", "file": "pic.png", "owner": "View"}])
    a, b = REC["image_page"]["made"][0], REC["image_owner"]["made"][0]
    im = s.get("Image")
    assert (im.x, im.y, im.owner, im.width, im.scale_type) == (a["X"], a["Y"], a["Owner"], a["Width"], a["ScaleType"])
    assert (s.get("Image001").x, s.get("Image001").y, s.get("Image001").owner) == (b["X"], b["Y"], b["Owner"])
    assert REC["image_page"]["undo"]["head"][0] == "Create Image"
    E.run_ops(s, [{"op": "clip"}, {"op": "set", "name": "Clip", "props": {"width": 60.0, "height": 40.0, "show_frame": True}},
                  {"op": "clip_add", "clip": "Clip", "view": "View"}])
    c = REC["clip"]["made"][0]
    assert (s.get("Clip").x, s.get("Clip").y, s.get("Clip").clip_children) == (c["X"], c["Y"], c["ViewProvider"]["ClipChildren"])
    assert (s.get("View").x, s.get("View").y) == (REC["clip_after_add"]["view"]["X"], REC["clip_after_add"]["view"]["Y"])
    assert list(s.get("Clip").views) == REC["clip_after_add"]["clip"]["Views"]
    E.run_ops(s, [{"op": "clip_remove", "view": "View"}])
    assert list(s.get("Clip").views) == REC["clip_after_remove"]["clip"]["Views"] == []
    assert [REC[k]["undo"]["head"][0] for k in ("clip", "clip_add", "clip_remove")] == ["Create clip", "Add clip group", "Remove clip group"]
    with pytest.raises(E.TechDrawEditError, match="does not belong"):
        E.run_ops(s, [{"op": "clip_remove", "view": "View"}])
