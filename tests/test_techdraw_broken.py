"""TechDraw_BrokenView beyond the goldens (tests/golden/techdraw rod_broken, rod_broken_two, shaft_broken hold the view's
geometry to FreeCAD's): a break given as a part's edge, and the break lines on the page."""
import importlib.util
from pathlib import Path

from cad_agent import techdraw as T
from cad_agent import techdraw_edit as E
from cad_agent import techdraw_export as X

HERE = Path(__file__).parent / "golden" / "techdraw"
_spec = importlib.util.spec_from_file_location("techdraw_prep", HERE / "prep.py")
_prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prep)


def _page(ops):
    s = E.Session(None, "Page", [], None, _prep.shape_of)
    s.pdir = Path("golden")
    E.run_ops(s, [{"op": "new_page"}] + ops)
    return s


def test_a_break_given_as_a_parts_edge_takes_its_ends():
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from cad_agent.feature import _subs
    edges = [TopoDS.Edge(e) for e in _subs(_prep.shape_of("rod"), TopAbs_EDGE)]
    # the rod's first edge along x, as the 3D view numbers it
    k = 1 + next(i for i, e in enumerate(edges)
                 if abs(BRep_Tool.Pnt_s(TopExp.FirstVertex_s(e)).X() - BRep_Tool.Pnt_s(TopExp.LastVertex_s(e)).X()) > 100)
    s = _page([{"op": "broken_view", "source": ["rod"], "breaks": [["rod", f"Edge{k}"]]}])
    v = next(o for o in s.objs if isinstance(o, T.DrawBrokenView))
    (p0, p1), = v.breaks
    assert abs(abs(p1[0] - p0[0]) - 200.0) < 1e-9


def test_the_break_lines_are_drawn_on_the_page():
    s = _page([{"op": "view", "source": ["rod"], "direction": [0, 0, 1]},
               {"op": "broken_view", "base_view": "View", "breaks": [[[-60, 0, 6], [50, 0, 6]]]}])
    doc = T.PageDocument(s.objs, _prep.shape_of, "golden").recompute()
    res = doc.result()
    (b,) = res["views"]["BrokenView"]["break_lines"]
    assert [ln[0][0] for ln in b["lines"]] == [-60.0, 50.0]          # Simple: a line at each end of the break
    prims = [p for p in X.display(doc) if p.attrs.get("class") == "td-break"]
    assert len(prims) == 2
