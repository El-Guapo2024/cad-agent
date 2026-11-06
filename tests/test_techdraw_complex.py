"""TechDraw_ComplexSection beyond the goldens (tests/golden/techdraw plate_complex_section, bracket_complex_section hold
the view's geometry to FreeCAD's): a profile given as a part's edges, and the section line along the profile."""
import importlib.util
from pathlib import Path

import pytest

from cad_agent import techdraw as T
from cad_agent import techdraw_edit as E

HERE = Path(__file__).parent / "golden" / "techdraw"
_spec = importlib.util.spec_from_file_location("techdraw_prep_cx", HERE / "prep.py")
_prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prep)


def _page(ops):
    s = E.Session(None, "Page", [], None, _prep.shape_of)
    s.pdir = Path("golden")
    E.run_ops(s, [{"op": "new_page"}] + ops)
    return s


def _edges(part):
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from cad_agent.feature import _subs
    out = []
    for e in _subs(_prep.shape_of(part), TopAbs_EDGE):
        e = TopoDS.Edge(e)
        a, b = BRep_Tool.Pnt_s(TopExp.FirstVertex_s(e)), BRep_Tool.Pnt_s(TopExp.LastVertex_s(e))
        out.append(((a.X(), a.Y(), a.Z()), (b.X(), b.Y(), b.Z())))
    return out


def test_a_profile_of_picked_edges_is_joined_end_to_end():
    edges = _edges("plate")
    # two edges of the plate's top face that meet at a corner, picked last one first
    top = [i for i, (a, b) in enumerate(edges) if a[2] == 5 and b[2] == 5 and (a[0] == b[0] or a[1] == b[1])]
    pair = next((i, j) for i in top for j in top if i != j and set(edges[i]) & set(edges[j]))
    s = _page([{"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
               {"op": "complex_section", "base_view": "View", "direction": "Up",
                "profile": [["plate", f"Edge{pair[1] + 1}"], ["plate", f"Edge{pair[0] + 1}"]]}])
    cx = next(o for o in s.objs if isinstance(o, T.DrawComplexSection))
    assert len(cx.cutting_tool_wire_object) == 3
    corner = (set(edges[pair[0]]) & set(edges[pair[1]])).pop()
    assert tuple(cx.cutting_tool_wire_object[1]) == corner


def test_edges_that_do_not_join_are_refused():
    edges = _edges("plate")
    far = next((i, j) for i in range(len(edges)) for j in range(len(edges))
               if i != j and not set(edges[i]) & set(edges[j]))
    with pytest.raises(E.TechDrawEditError, match="do not join"):
        _page([{"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
               {"op": "complex_section", "base_view": "View", "direction": "Up",
                "profile": [["plate", f"Edge{far[0] + 1}"], ["plate", f"Edge{far[1] + 1}"]]}])


def test_the_section_line_follows_the_profile():
    s = _page([{"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
               {"op": "complex_section", "base_view": "View", "direction": "Up", "symbol": "A",
                "profile": [[-25, -5, 5], [0, -5, 5], [0, 8, 5], [25, 8, 5]]}])
    res = T.PageDocument(s.objs, _prep.shape_of, "golden").recompute().result()
    line = res["sections"]["ComplexSection"]
    assert len(line["points"]) == 4 and line["ends"] == [line["points"][0], line["points"][-1]]


# Aligned and NoParallel are not in the goldens: FreeCAD 26.3 computes them on a QtConcurrent thread that freecadcmd
# never finishes, and its GUI under xvfb crashed while making one (2026-11-06). These hold what makeAlignedPieces lays
# out: one piece per profile segment, each as wide as the stretch of the plate that segment cuts, side by side.

def _aligned(strategy, profile):
    s = _page([{"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
               {"op": "complex_section", "base_view": "View", "direction": "Up", "strategy": strategy,
                "profile": profile}])
    doc = T.PageDocument(s.objs, _prep.shape_of, "golden").recompute()
    assert not doc.errors
    return doc.geo["ComplexSection"]


def test_aligned_lays_the_pieces_side_by_side():
    import math
    g = _aligned("Aligned", [[-25, -5, 5], [0, -5, 5], [10, 8, 5], [25, 8, 5]])
    # the plate spans x -20..20: 20 mm of the first segment, all of the slanted one, 10 mm of the last
    width = 20.0 + math.hypot(10, 13) + 10.0
    assert abs((g.box[2] - g.box[0]) - width) < 1e-6
    assert abs((g.box[3] - g.box[1]) - 10.0) < 1e-6          # the plate's thickness, seen from the section direction
    assert len(g.faces) == 3          # a face for each segment (the slanted one ends at the hole's centre)


def test_noparallel_leaves_out_the_segment_along_the_section_normal():
    g = _aligned("NoParallel", [[-25, -5, 5], [0, -5, 5], [0, 8, 5], [25, 8, 5]])
    assert abs((g.box[2] - g.box[0]) - 40.0) < 1e-6           # 20 + 20: the segment along y is not shown
    assert len(g.faces) == 3          # the first piece's face, and the last's in two: its segment runs through the hole
