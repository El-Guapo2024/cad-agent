"""TechDraw's extension commands against the real FreeCAD GUI's (ui/scripts/fctechdraw_ext.json).

ui/scripts/fctechdraw_ext.py used each command of CommandExtensionPack.cpp and CommandExtensionDims.cpp, TechDraw_ShowAll and
TechDraw_ExtensionPositionSectionView on views of the plate, a flange and a stepped shaft in FreeCAD 26.3's GUI (3160daf1e2b6)
and recorded, after each one, the view's geometry in FreeCAD's numbering, what its cosmetic objects, dimensions and balloons
hold, the undo step it made and the dialogs it raised. The same commands are run here, with the ops the app sends for the
selection the recording had, in the recording's order (the commands change each other's starting point: the line attributes
the panel set, the dimensions the earlier commands made), and the numbers are compared after each.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REC = json.loads((ROOT / "ui" / "scripts" / "fctechdraw_ext.json").read_text())
GOLDEN = ROOT / "tests" / "golden" / "techdraw"
_spec = importlib.util.spec_from_file_location("techdraw_ext_prep", GOLDEN / "prep.py")
_prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prep)

# the session's attributes after the Select Line Attributes panel of the recording: style "Symmetry" (the 5th line), Thick
# (0.7), cascade spacing 12, delta distance 4
SESSION = {"active": {"style": 5, "line_number": 5, "weight": 0.7}, "cascade_spacing": 12.0, "line_stretch": 4.0}


def close(a, b, tol=1e-5):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def pline(parallel):
    return lambda v, s: {"op": "cosmetic_pline", "view": v, "subs": s, "parallel": parallel}


def thread(kind):
    return lambda v, s: {"op": "thread", "view": v, "kind": kind, "subs": s}


def dim(op, **kw):
    return lambda v, s: {"op": op, "view": v, "vertices": s, **kw}


def extend(on):
    return lambda v, s: {"op": "extend_line", "view": v, "sub": s[0], "extend": on}


def edges_op(op):
    return lambda v, s: {"op": op, "view": v, "edges": s}


def verts_op(op):
    return lambda v, s: {"op": op, "view": v, "vertices": s}


# key -> the op the app sends for the recorded selection (view, sub-elements)
BUILD = {
    "pack_circle2": verts_op("cosmetic_circle2"), "pack_circle3": verts_op("cosmetic_circle3"), "pack_arc": verts_op("cosmetic_arc"),
    "pack_parallel": pline(True), "pack_perpendicular": pline(False), "pack_perpendicular_vertex_first": pline(False),
    "pack_parallel_bad": pline(True), "pack_circle_cl": edges_op("circle_centerlines"),
    "pack_circle_cl_line": edges_op("circle_centerlines"), "pack_extend": extend(True), "pack_shorten": extend(False),
    "pack_extend_hlr": extend(True), "pack_extend_circle": extend(True),
    "pack_cl_make": lambda v, s: {"op": "centerline", "view": v, "subs": s, "mode": "Vertical"},
    "pack_extend_cl": extend(True), "pack_shorten_cl": extend(False),
    "showall": lambda v, s: {"op": "show_all_edges", "view": v}, "showall_back": lambda v, s: {"op": "show_all_edges", "view": v},
    "attrs_change": lambda v, s: {"op": "line_attributes", "view": v, "subs": s}, "attrs_extend": extend(True),
    "attrs_circle": verts_op("cosmetic_circle2"), "attrs_perpendicular": pline(False),
    "pack_holecircle": edges_op("bolt_circle"), "pack_holecircle_three": edges_op("bolt_circle"),
    "pack_holecircle_two": edges_op("bolt_circle"), "pack_holecircle_cl": edges_op("circle_centerlines"),
    "pack_thread_hole_side": thread("hole_side"), "pack_thread_bolt_side": thread("bolt_side"),
    "pack_thread_side_one": thread("bolt_side"), "pack_thread_hole_bottom": thread("hole_bottom"),
    "pack_thread_bolt_bottom": thread("bolt_bottom"), "pack_thread_bottom_line": thread("bolt_bottom"),
    "dims_chain_h": dim("chain_dim", dir="h"), "dims_chain_v": dim("chain_dim", dir="v"), "dims_chain_o": dim("chain_dim", dir="o"),
    "dims_coord_h": dim("coord_dim", dir="h"), "dims_coord_h_rev": dim("coord_dim", dir="h"),
    "dims_coord_v": dim("coord_dim", dir="v"), "dims_coord_o": dim("coord_dim", dir="o"),
    "dims_chamfer_h": dim("chamfer_dim", dir="h"), "dims_chamfer_v": dim("chamfer_dim", dir="v"),
    "dims_chamfer_h_neg": dim("chamfer_dim", dir="h"),
    "dims_arc": lambda v, s: {"op": "arc_length_dim", "view": v, "edge": s[0]},
    "dims_arc_line": lambda v, s: {"op": "arc_length_dim", "view": v, "edge": s[0]}, "dims_chain_h_one": dim("chain_dim", dir="h"),
    "verts_intersection_lines": edges_op("vertex_at_intersection"), "verts_intersection_circle": edges_op("vertex_at_intersection"),
    "verts_intersection_one": edges_op("vertex_at_intersection"), "verts_intersection_vertex": edges_op("vertex_at_intersection"),
    "notes_area": lambda v, s: {"op": "area_annotation", "view": v, "faces": s},
    "notes_area_none": lambda v, s: {"op": "area_annotation", "view": v, "faces": s},
    "notes_arclength": lambda v, s: {"op": "arc_length_annotation", "view": v, "edges": s},
    "notes_arclength_circle": lambda v, s: {"op": "arc_length_annotation", "view": v, "edges": s},
}
# dimension commands: the dimensions are the selection (names), after the recording moved them about (REC["scatter"])
DIMS = {"lock": (None, {"op": "lock_view"}), "lock_back": (None, {"op": "lock_view"}),
        "dims_pos_h": ("chain_h", {"op": "dim_position", "dir": "h"}), "dims_pos_v": ("chain_v", {"op": "dim_position", "dir": "v"}),
        "dims_pos_o": ("chain_o", {"op": "dim_position", "dir": "o"}),
        "dims_pos_none": (None, {"op": "dim_position", "dir": "h"}),
        "dims_cascade_h": ("coord_h", {"op": "dim_position", "dir": "h", "cascade": True}),
        "dims_cascade_v": ("coord_v", {"op": "dim_position", "dir": "v", "cascade": True}),
        "dims_cascade_o": ("coord_o", {"op": "dim_position", "dir": "o", "cascade": True}),
        "dims_prefix_diameter": (None, {"op": "dim_prefix", "prefix": "⌀"}),
        "dims_prefix_square": (None, {"op": "dim_prefix", "prefix": "□"}),
        "dims_prefix_repeat": (None, {"op": "dim_prefix", "prefix": "%s× ", "text": "4"}),
        "dims_prefix_remove": (None, {"op": "dim_remove_prefix"}), "dims_prefix_remove_again": (None, {"op": "dim_remove_prefix"}),
        "dims_decimal_up": (None, {"op": "dim_decimals", "delta": 1}), "dims_decimal_down": (None, {"op": "dim_decimals", "delta": -1})}
SKIP = {"dims_decimal_limits", "dims_prefix_on_view"}
RUN_TOOL = ("attrs_select", "pack_cl_make", "offset_vertex", "customize_dim", "customize_balloon")      # recorded by run_tool: a "view", not a "state"
LIVE_ORDER = {"attrs_extend"}
LIVE_ORDER_AFTER = {"attrs_change", "pack_thread_bottom_line", "dims_chain_h_one"} | {k for k in DIMS if k.startswith("dims_")}
NO_STEP_IN_FREECAD = {"pack_extend_cl", "pack_shorten_cl"}


def new_session():
    from cad_agent import techdraw_edit as E
    s = E.Session(None, "Page", [], None, _prep.shape_of)
    E.run_ops(s, [{"op": "new_page"},
                  {"op": "view", "source": ["plate"], "direction": [0, 0, 1], "name": "View"},
                  {"op": "view", "source": ["flange"], "direction": [0, 0, 1], "name": "Flange"},
                  {"op": "view", "source": ["shaft"], "direction": [0, -1, 0], "name": "ShaftF"},
                  {"op": "view", "source": ["shaft"], "direction": [0, 0, 1], "name": "ShaftT"}])
    return s


def state_of(s, name):
    """The view's edges and vertices as ui/scripts/fctechdraw_ext_dump.py's view_state has them (unscaled, y up)."""
    from cad_agent import techdraw as T
    from cad_agent.techdraw_view import _ends
    doc = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
    assert not doc.errors, doc.errors
    geo, sc = doc.geo[name], doc.geo[name].scale
    edges = []
    for e in geo.edges:
        a, b = _ends(e.occ)
        edges.append({"start": [a[0] / sc, -a[1] / sc, 0.0], "end": [b[0] / sc, -b[1] / sc, 0.0]})
    return {"edges": edges, "vertices": [[v.x / sc, -v.y / sc, 0.0] for v in geo.vertices]}


def same_view(ours, rec, what, unordered=False):
    if unordered:       # FreeCAD numbers the centre lines before the cosmetic edges after refreshCEGeoms, until a recompute
        key = lambda e: [round(c, 4) for c in e["start"] + e["end"]]
        ours = {"edges": sorted(ours["edges"], key=key), "vertices": ours["vertices"]}
        rec = {"edges": sorted(rec["edges"], key=key), "vertices": rec["vertices"]}
    assert len(ours["edges"]) == len(rec["edges"]), f"{what}: {len(ours['edges'])} edges, FreeCAD {len(rec['edges'])}"
    for i, (o, r) in enumerate(zip(ours["edges"], rec["edges"])):
        assert close(o["start"], r["start"]) and close(o["end"], r["end"]), f"{what} Edge{i}: {o} vs {r}"
    assert len(ours["vertices"]) == len(rec["vertices"]), f"{what}: {len(ours['vertices'])} vertices"
    for i, (o, r) in enumerate(zip(ours["vertices"], rec["vertices"])):
        assert close(o, r), f"{what} Vertex{i}: {o} vs {r}"


def same_cosmetics(s, name, rec, what):
    """CosmeticEdges (Start, End, Center, Radius and the pen), CosmeticVertexes and CenterLines' Extension."""
    from cad_agent import techdraw_cosmetic as C
    v = s.get(name)
    ours = [C._thaw(c) for c in v.source_value("cosmetic_edges")]
    theirs = rec["CosmeticEdges"]
    assert len(ours) == len(theirs), f"{what}: {len(ours)} cosmetic edges, FreeCAD {len(theirs)}"
    for i, (o, r) in enumerate(zip(ours, theirs)):
        f = C.format_of(o)
        assert (f["style"], f["visible"]) == (r["Format"]["style"], r["Format"]["visible"]), f"{what} CE{i} {f}"
        assert f["weight"] == pytest.approx(r["Format"]["weight"], abs=1e-6), f"{what} CE{i}"
        if o["geom"] == "line":
            assert close(o["start"], r["Start"]) and close(o["end"], r["End"]), f"{what} CE{i}: {o} vs {r}"
        else:
            assert close(o["center"], r["Center"]) and o["radius"] == pytest.approx(r["Radius"], rel=1e-6), f"{what} CE{i}"
    cvs = [C._thaw(c) for c in v.source_value("cosmetic_vertexes")]
    assert len(cvs) == len(rec["CosmeticVertexes"]), what
    for o, r in zip(cvs, rec["CosmeticVertexes"]):
        assert close(o["point"], r["Point"]), what
    cls = [C._thaw(c) for c in v.source_value("center_lines")]
    assert [c["extend"] for c in cls] == pytest.approx([r["Extension"] for r in rec["CenterLines"]]), what


def same_dims(s, rec, what, xy=None):
    """Type, References2D, FormatSpec and Arbitrary of every dimension; X and Y of the ones the command made or moved (the GUI
    snaps a dimension's text when it draws it, "Drag Dimension", which moves the others a little between the commands)."""
    from cad_agent import techdraw as T
    ours = {o.name: o for o in s.objs if isinstance(o, T.DrawViewDimension)}
    assert set(ours) == set(rec["dims"]), f"{what}: dimensions {sorted(ours)} vs {sorted(rec['dims'])}"
    for n, r in rec["dims"].items():
        o = ours[n]
        assert o.type == r["Type"], f"{what} {n}"
        refs = [[o.references_2d[0][0], [ref[1] for ref in o.references_2d]]]       # FreeCAD's PropertyLinkSubList: object, subs
        assert refs == [[a, b] for a, b in r["References2D"]], f"{what} {n}: {o.references_2d} vs {r['References2D']}"
        if xy is None or n in xy:
            assert o.x == pytest.approx(r["X"], abs=1e-5) and o.y == pytest.approx(r["Y"], abs=1e-5), \
                f"{what} {n}: {(o.x, o.y)} vs {(r['X'], r['Y'])}"
        assert o.format_spec == r["FormatSpec"], f"{what} {n}: {o.format_spec!r} vs {r['FormatSpec']!r}"
        assert bool(o.arbitrary) == r["Arbitrary"], f"{what} {n}"


def same_balloons(s, rec, what):
    from cad_agent import techdraw as T
    ours = {o.name: o for o in s.objs if isinstance(o, T.DrawViewBalloon)}
    assert set(ours) == set(rec["balloons"]), f"{what}: balloons {sorted(ours)} vs {sorted(rec['balloons'])}"
    for n, r in rec["balloons"].items():
        o = ours[n]
        assert o.text == r["Text"], f"{what} {n}: {o.text!r} vs {r['Text']!r}"
        for a, b in (("x", "X"), ("y", "Y"), ("origin_x", "OriginX"), ("origin_y", "OriginY"), ("kink_length", "KinkLength")):
            assert getattr(o, a) == pytest.approx(r[b], abs=1e-5), f"{what} {n} {a}"
        assert (o.bubble_shape, o.end_type) == (r["BubbleShape"], r["EndType"]), f"{what} {n}"
        vp = r["vp"]
        assert (o.font_size, o.line_width, o.line_visible) == (vp["Fontsize"], pytest.approx(vp["LineWidth"], abs=1e-6), vp["LineVisible"])
        assert list(o.color)[:3] == pytest.approx(vp["Color"][:3], abs=1e-6) if vp["Color"][0] == 1.0 else True


def snapshot_of(s):
    from cad_agent import techdraw as T
    return [T.as_dict(o) for o in s.objs]


def ours_numbering(s, view, subs):
    """After Change Line Attributes the live geometry of FreeCAD's view lists the centre lines before the cosmetic edges
    (refreshCEGeoms appends the cosmetic edges to what is left), until the next recompute; the recording's Edge<n> of that
    moment is our Edge<n>, where the cosmetic edges come first."""
    from cad_agent import techdraw as T
    doc = T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute()
    edges = doc.geo[view].edges
    first = next(i for i, e in enumerate(edges) if e.cls in ("cosmetic", "centerline"))
    n_ce = sum(e.cls == "cosmetic" for e in edges)
    n_cl = sum(e.cls == "centerline" for e in edges)
    out = []
    for sub in subs:
        k = int(sub[4:]) if sub.startswith("Edge") else -1
        if k >= first + n_cl:
            k -= n_cl
        elif k >= first:
            k += n_ce
        out.append(f"Edge{k}" if k >= 0 else sub)
    return out


def op_of(key, s=None):
    rec = REC[key]
    view, subs = rec["selection"][0]
    if key in LIVE_ORDER:
        subs = ours_numbering(s, view, subs)
    return BUILD[key](view, subs), view


def with_session(op, on):
    return {**SESSION, **op} if on else op


def replay_all():
    """Yields (key, session, E, ops-run, error) after each recorded step, in the recording's order."""
    from cad_agent import techdraw_edit as E
    from cad_agent import techdraw_ext as X
    s = new_session()
    on = False
    for key in REC:
        if key == "dims_decimal_limits":        # three decreases and eleven increases of Dimension001's decimals
            two = REC["dims_prefix_square"]["selection"][0][0]
            E.run_ops(s, [{"op": "dim_decimals", "names": [two], "delta": d} for d in [-1] * 3 + [1] * 11])
            continue
        if key in SKIP or not isinstance(REC[key], dict) or ("state" not in REC[key] and key not in RUN_TOOL):
            continue
        if key == "attrs_select":
            on = True
            continue
        rec = REC[key]
        before = snapshot_of(s)
        err = None
        if key in DIMS:
            group, op = DIMS[key]
            names = [x[0] for x in rec["selection"]]
            if group:
                E.run_ops(s, [{"op": "set", "name": n, "props": {"x": xy[0], "y": xy[1]}} for n, xy in REC["scatter"][group].items()])
                before = snapshot_of(s)
            op = {**op, "names": names}
            view = "View"
        elif key == "offset_vertex":      # TaskAddOffsetVertex: the offset typed, OK
            (view, subs), = [REC[key]["selection"][0]]
            op = {"op": "offset_vertex", "view": view, "vertex": subs[0], "offset": [REC[key]["edit"]["dSpinBoxX"], REC[key]["edit"]["dSpinBoxY"]]}
        elif key.startswith("customize_"):
            name = REC[key]["selection"][0][0]
            prop = "format_spec" if key.endswith("dim") else "text"
            op = {"op": "set", "name": name, "props": {prop: REC[key]["after"]["FormatSpec" if prop == "format_spec" else "Text"]}}
            view = "View"
        elif key == "offset_vertex_cancel":
            continue                      # Cancel takes the preview away: nothing is made
        elif key in BUILD:
            op, view = op_of(key, s)
        else:
            continue
        op = with_session(op, on)
        try:
            E.run_ops(s, [op])
        except E.TechDrawEditError as e:
            err = str(e)
        except ValueError as e:
            raise AssertionError(f"{key}: {e}") from e
        yield key, s, E, X, op, view, before, err


def test_every_step_equals_freecads():
    """After each command the view has FreeCAD's edges and vertices in FreeCAD's numbering, its cosmetic objects, its
    dimensions and balloons hold FreeCAD's numbers, the dialog FreeCAD raised is our error and the undo step is named as
    FreeCAD names it (none where FreeCAD's command changes no property)."""
    s0 = new_session()
    same_view(state_of(s0, "View"), REC["start"], "start")
    same_view(state_of(s0, "Flange"), REC["start_flange"], "start_flange")
    same_view(state_of(s0, "ShaftF"), REC["start_shaftf"], "start_shaftf")
    same_view(state_of(s0, "ShaftT"), REC["start_shaftt"], "start_shaftt")
    n = 0
    last = {"dims": {}, "balloons": {}}
    for key, s, E, X, op, view, before, err in replay_all():
        rec = REC[key]
        dialogs = [d["text"] for d in rec["dialogs"] if d["title"] != "Prefix Text"]
        if dialogs:
            assert err == dialogs[0], f"{key}: error {err!r}, FreeCAD's dialog {dialogs!r}"
        else:
            assert err is None, f"{key}: {err}"
        st = rec.get("state")
        if st is None:      # run_tool's record: the view, and the dimensions and balloons the step before left (a customized one changed)
            st = {**rec["view"], "dims": json.loads(json.dumps(last["dims"])), "balloons": json.loads(json.dumps(last["balloons"])),
                  "lock": {}, "showall": {}}
            if key.startswith("customize_"):
                tgt = rec["selection"][0][0]
                (st["dims"] if key.endswith("dim") else st["balloons"])[tgt]["FormatSpec" if key.endswith("dim") else "Text"] = \
                    rec["after"]["FormatSpec" if key.endswith("dim") else "Text"]
        last = st
        same_view(state_of(s, view), st, key, unordered=key in LIVE_ORDER_AFTER)
        same_cosmetics(s, view, st, key)
        moved = set(rec.get("new_objects") or []) | (set(op.get("names") or []) if op["op"] == "dim_position" and err is None else set())
        same_dims(s, st, key, moved)
        same_balloons(s, st, key)
        changed = snapshot_of(s) != before
        from cad_agent import techdraw_annot as A
        step = "Customize Format" if op["op"] == "set" else X.step_name(op) if op["op"] in X.OPS else A.STEP_NAMES[op["op"]]
        if key in NO_STEP_IN_FREECAD or op["op"] in X.NO_STEP_IN_FREECAD:       # no property changes, no step there
            assert rec["undo"]["head"] == [] and changed, key
            continue
        assert rec["undo"]["head"] == ([step] if changed and step else []), f"{key}: step {rec['undo']['head']} vs {step} changed={changed}"
        if st["lock"]:
            assert {o.name: o.lock_position for o in s.objs if o.kind == "DrawProjGroupItem"} == st["lock"], key
            assert {o.name: o.show_all_edges for o in s.objs if o.kind == "DrawProjGroupItem"} == st["showall"], key
        n += 1
    assert n >= 60, n


def test_the_step_names():
    """A command's undo step is the name FreeCAD gives openCommand (and none where it makes none)."""
    from cad_agent import techdraw_ext as X
    assert X.step_name({"op": "chain_dim", "dir": "o"}) == "Create oblique chain dimension"
    assert X.step_name({"op": "dim_position", "dir": "v", "cascade": True}) == "Cascade Vertical Dimension"
    assert X.step_name({"op": "dim_position", "dir": "v"}) == "Position Vert Chain Dimension"
    assert X.step_name({"op": "thread", "kind": "hole_bottom"}) == "Cosmetic thread hole bottom"
    assert X.step_name({"op": "position_section"}) == "Position Section View" and set(X.NO_STEP_IN_FREECAD) >= {"show_all_edges"}


def test_the_decimals_stop_at_nought_and_nine():
    from cad_agent import techdraw_edit as E
    s = new_session()
    E.run_ops(s, [{"op": "chain_dim", "view": "View", "vertices": ["Vertex1", "Vertex3"], "dir": "h"}])
    n = s.objs[-1].name
    seen = []
    for _ in range(3):
        E.run_ops(s, [{"op": "dim_decimals", "names": [n], "delta": -1}])
        seen.append(s.get(n).format_spec)
    for _ in range(11):
        E.run_ops(s, [{"op": "dim_decimals", "names": [n], "delta": 1}])
    seen.append(s.get(n).format_spec)
    assert seen == ["%.1w", "%.0w", "%.0w", "%.9w"] and REC["dims_decimal_limits"][-1] == "%.9w" and REC["dims_decimal_limits"][2] == "%.0w"


def section_session():
    """The recording's page: a projection group of the plate at (100, 150) and a section of its Front item."""
    from cad_agent import techdraw as T
    from cad_agent import techdraw_edit as E
    s = new_session()
    E.run_ops(s, [{"op": "projgroup", "source": ["plate"]}])
    E.run_ops(s, [{"op": "set", "name": "ProjGroup", "props": {"x": 100.0, "y": 150.0}}])
    s.add(T.DrawViewSection("Section", base_view="ProjItem", source=("plate",), section_normal=(0.0, 1.0, 0.0), direction=(0.0, -1.0, 0.0),
                            x_direction=(1.0, 0.0, 0.0), section_origin=(0.0, 0.0, 0.0), section_direction="Down", scale=1.0,
                            x=160.0, y=40.0))
    return s, E


def test_position_section_view_equals_freecads():
    """TechDraw_ExtensionPositionSectionView: a section view lined up with its base (the group, for a projection group's
    item) and an edge of the section lined up with a vertex of the base; a single view as the base fails as in Python."""
    s, E = section_session()
    rec = REC["section_group"]
    assert rec["group"] == [100.0, 150.0] and rec["item_xy"] == [0.0, 0.0]
    assert (s.get("ProjGroup").x, s.get("ProjGroup").y, s.get("ProjItem").x, s.get("ProjItem").y) == (100.0, 150.0, 0.0, 0.0)
    E.run_ops(s, [{"op": "position_section", "section": "Section"}])
    got = REC["section_pos"]["state"]["sections"]["Section"]
    assert (s.get("Section").x, s.get("Section").y) == (got["X"], got["Y"])
    # the section's own edges, in FreeCAD's numbering
    E.run_ops(s, [{"op": "set", "name": "Section", "props": {"x": 140.0, "y": 52.0}}])
    ours = state_of(s, "Section")
    assert len(ours["edges"]) == len(REC["section_edges"])
    for i, (o, r) in enumerate(zip(ours["edges"], REC["section_edges"])):
        assert close(o["start"], r[2], 1e-6) and close(o["end"], r[3], 1e-6), (i, o, r)
    sel = REC["section_edge_vertex"]["selection"]
    E.run_ops(s, [{"op": "position_section", "section": "Section", "edge": sel[0][1][0], "base": sel[1][0], "vertex": sel[1][1][0]}])
    got = REC["section_edge_vertex"]["state"]["sections"]["Section"]
    assert (s.get("Section").x, s.get("Section").y) == pytest.approx((got["X"], got["Y"]))
    E.run_ops(s, [{"op": "set", "name": "Section", "props": {"x": 140.0, "y": 52.0}}])
    sel = REC["section_edge_vertex_h"]["selection"]
    E.run_ops(s, [{"op": "position_section", "section": "Section", "edge": sel[0][1][0], "base": sel[1][0], "vertex": sel[1][1][0]}])
    got = REC["section_edge_vertex_h"]["state"]["sections"]["Section"]
    assert (s.get("Section").x, s.get("Section").y) == pytest.approx((got["X"], got["Y"]))
    # a single view is not in a group: baseView.InList[0] is the page, which has no X
    from cad_agent import techdraw as T
    s.add(T.DrawViewSection("SectionB", base_view="View", source=("plate",), section_normal=(0.0, 1.0, 0.0), direction=(0.0, -1.0, 0.0),
                            x_direction=(1.0, 0.0, 0.0), section_origin=(0.0, 0.0, 0.0), section_direction="Down", scale=1.0,
                            x=120.0, y=40.0))
    with pytest.raises(E.TechDrawEditError):
        E.run_ops(s, [{"op": "position_section", "section": "SectionB"}])


# ── the edit layer and `cad techdraw`: the page file holds what the commands made, and reads back as written ──────────

def test_the_commands_round_trip_through_the_page_file_and_the_cli(tmp_path, monkeypatch, capsys):
    """Cosmetic geometry, dimensions, a balloon and the view's flags written into techdraw/<Page>.py read back the same,
    each command one undo step named as FreeCAD names it, and a command that changes nothing leaves the file alone."""
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    from cad_agent import cli
    from cad_agent import state as st
    from cad_agent import techdraw_edit as E
    from test_cli import run
    from test_techdraw_edit import PLATE
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    monkeypatch.setenv("CAD_WARM", "0")
    d = tmp_path / "td"
    (d / "parts").mkdir(parents=True)
    (d / "parts" / "plate.py").write_text(PLATE)
    run(capsys, "techdraw", "new", "td")
    run(capsys, "techdraw", "view", "td", "Page", "plate", "--direction", "0,0,1")

    def step(*args):
        code, data = run(capsys, "techdraw", *args)
        assert code == cli.OK, data
        return data["step"]
    assert step("cosmetic-circle2", "td", "Page", "View", "Vertex6", "Vertex8") == "Cosmetic Circle"
    assert step("cosmetic-circle3", "td", "Page", "View", "Vertex1", "Vertex4", "Vertex5") == "Cosmetic Circle 3 Points"
    assert step("cosmetic-arc", "td", "Page", "View", "Vertex6", "Vertex8", "Vertex4") == "Cosmetic arc"
    assert step("cosmetic-parallel", "td", "Page", "View", "Edge2", "Vertex8") == "Cosmetic Line Parallel/Perpendicular"
    assert step("thread-hole-bottom", "td", "Page", "View", "Edge5") == "Cosmetic thread hole bottom"
    assert step("extend-line", "td", "Page", "View", "Edge9", "--delta-distance", "4") == "Extend/shorten line"
    assert step("chain-dim", "td", "Page", "View", "Vertex1", "Vertex3", "Vertex8", "--dir", "h", "--cascade-spacing", "9") == \
        "Create Horizontal Chain Dimension"
    assert step("dim-prefix", "td", "Page", "Dimension", "--prefix", "⌀") == "Insert Prefix"
    assert step("dim-decimals", "td", "Page", "Dimension001", "--delta", "1") == "Increase/Decrease Decimal"
    assert step("intersection-vertices", "td", "Page", "View", "Edge2", "Edge4") == "Cosmetic intersection vertices"
    assert step("offset-vertex", "td", "Page", "View", "Vertex8", "--dx", "3", "--dy", "-2") == "Add offset vertex"
    assert step("customize-format", "td", "Page", "Dimension", "%.1f mm") == "Customize Format"
    assert step("toggle-edges", "td", "Page", "View") == "Toggle Edge Visibility"
    assert step("lock-view", "td", "Page", "View") == "Lock/Unlock View"
    src = (d / "techdraw" / "Page.py").read_text()
    objs = E.objects_of(src)
    v = next(o for o in objs if o.name == "View")
    assert v.show_all_edges and v.lock_position
    assert [c["geom"] for c in map(__import__("cad_agent.techdraw_cosmetic", fromlist=["x"])._thaw, v.cosmetic_edges)][:3] == \
        ["circle", "circle", "arc"]
    dims = {o.name: o for o in objs if o.kind == "DrawViewDimension"}
    assert dims["Dimension"].format_spec == "%.1f mm" and dims["Dimension001"].format_spec == "%.3w"
    assert [C["point"] for C in map(__import__("cad_agent.techdraw_cosmetic", fromlist=["x"])._thaw, v.cosmetic_vertexes)][-2:] == \
        [[20.0, 15.0, 0.0], [13.0, 6.0, 0.0]]
    # written and read again: the same objects
    from cad_agent import techdraw as T
    again = E.read_src(src, "Page", "td")
    assert [o["name"] for o in again["objects"]] == [o.name for o in objs]
    assert [T.as_dict(o) for o in E.objects_of(E.write_src(src, objs))] == [T.as_dict(o) for o in objs]
    # undo: each command went; the last step is Edit page's Toggle...
    code, data = run(capsys, "undo", "td")
    assert code == cli.OK


def test_a_section_view_is_two_undo_steps_as_freecads(tmp_path, monkeypatch, capsys):
    """TaskSectionView::apply in create mode: createSectionView ("Create Section View") and then updateSectionView ("Edit
    Section View"); the second is a step even where it sets what is there (--keep-step), and undo takes them one at a time."""
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    from cad_agent import cli
    from cad_agent import state as st
    from test_cli import run
    from test_techdraw_edit import PLATE
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    monkeypatch.setenv("CAD_WARM", "0")
    d = tmp_path / "td"
    (d / "parts").mkdir(parents=True)
    (d / "parts" / "plate.py").write_text(PLATE)
    run(capsys, "techdraw", "new", "td")
    run(capsys, "techdraw", "view", "td", "Page", "plate", "--direction", "0,0,1")
    code, data = run(capsys, "techdraw", "apply", "td", "Page", "--name", "Create Section View", "--ops",
                     json.dumps([{"op": "section", "base_view": "View", "direction": "Right", "origin": [0.0, 0.0, 0.0], "symbol": "A"}]))
    assert code == cli.OK and data["step"] == "Create Section View"
    code, data = run(capsys, "techdraw", "apply", "td", "Page", "--name", "Edit Section View", "--keep-step", "--ops",
                     json.dumps([{"op": "section_edit", "name": "SectionView", "origin": [0.0, 0.0, 0.0], "symbol": "A", "scale": 1.0}]))
    assert code == cli.OK and data["step"] == "Edit Section View"
    code, data = run(capsys, "history", "td")
    names = [u["name"] for u in data["undo"][:3]]
    assert names[:2] == ["Edit Section View", "Create Section View"], names
    # without --keep-step the same edit is an empty transaction and makes no step
    code, data = run(capsys, "techdraw", "apply", "td", "Page", "--name", "Edit Section View", "--ops",
                     json.dumps([{"op": "section_edit", "name": "SectionView", "origin": [0.0, 0.0, 0.0], "symbol": "A", "scale": 1.0}]))
    code, data = run(capsys, "history", "td")
    assert [u["name"] for u in data["undo"][:2]] == ["Edit Section View", "Create Section View"]


def test_toggle_edge_visibility_draws_the_invisible_lines():
    """ShowAllEdges (TechDraw_ShowAll): a line whose pen is not visible (Edit Line Appearance) is drawn all the same while the
    view's flag is on (QGIViewPart: `if (!vp->ShowAllEdges.getValue() && !showItem) item->hide()`)."""
    from cad_agent import techdraw as T
    from cad_agent import techdraw_edit as E
    from cad_agent.techdraw_export import page_svg
    s = new_session()
    E.run_ops(s, [{"op": "cosmetic_circle2", "view": "View", "vertices": ["Vertex6", "Vertex8"]},
                  {"op": "format", "view": "View", "subs": ["Edge6"], "visible": False}])
    sub = 'data-view="View" data-sub="Edge6"'

    def drawn():
        return sub in page_svg(T.PageDocument(s.objs, _prep.shape_of, "Unnamed").recompute())
    assert not drawn()
    E.run_ops(s, [{"op": "show_all_edges", "view": "View"}])
    assert drawn()
    E.run_ops(s, [{"op": "show_all_edges", "view": "View"}])
    assert not drawn()
