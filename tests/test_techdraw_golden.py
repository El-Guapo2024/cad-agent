"""TechDraw pages against FreeCAD 26.3 (3160daf1e2b6): tests/golden/techdraw.

prep.py made each case's page with cad_agent/techdraw_edit.py's ops (cases.json) and the parts' BREPs; make.py had
freecadcmd make the same objects and recompute them (freecad.json). Here cad_agent's PageDocument recomputes them and
every view's edges and vertices (FreeCAD's numbering, which References2D uses), its place on the page, scale and
directions, each dimension's value, text and points, and the template's fields are held to FreeCAD's.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "golden" / "techdraw"
CASES = json.loads((GOLDEN / "cases.json").read_text())
FREECAD = json.loads((GOLDEN / "freecad.json").read_text())["cases"]

_spec = importlib.util.spec_from_file_location("techdraw_golden_prep", GOLDEN / "prep.py")
_prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prep)

TOL = 1e-6
CURVES = {0: "Line", 1: "Circle", 2: "Ellipse", 3: "Hyperbola", 4: "Parabola", 5: "BezierCurve",
          6: "BSplineCurve", 7: "OffsetCurve", 8: "OtherCurve"}


def _doc(name):
    from cad_agent import techdraw as T
    objs = [T.from_dict(o) for o in CASES[name]["objects"]]
    return T.PageDocument(objs, _prep.shape_of, "golden").recompute()


_DOCS = {}


def doc(name):
    if name not in _DOCS:
        _DOCS[name] = _doc(name)
    return _DOCS[name]


def close(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b)) and len(a) == len(b)


def ours_edges(geo):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from cad_agent.techdraw_view import _ends
    out = []
    s = geo.scale
    for e in geo.edges:
        a = BRepAdaptor_Curve(e.occ)
        p, q = _ends(e.occ)
        d = {"curve": CURVES[int(a.GetType().value)], "start": [p[0] / s, -p[1] / s, 0.0],
             "end": [q[0] / s, -q[1] / s, 0.0], "visible": e.visible}
        if d["curve"] == "Circle":
            c = a.Circle()
            d["radius"] = c.Radius() / s
            d["center"] = [c.Location().X() / s, -c.Location().Y() / s, 0.0]
        out.append(d)
    return out


VIEW_CASES = [(c, v) for c in CASES for v, r in FREECAD[c].get("views", {}).items() if "edges" in r]


@pytest.mark.parametrize("case,view", VIEW_CASES)
def test_view_edges(case, view):
    fc = FREECAD[case]["views"][view]
    d = doc(case)
    assert view in d.geo, d.errors.get(view)
    ours = ours_edges(d.geo[view])
    assert len(ours) == len(fc["edges"]), f"{len(ours)} edges, FreeCAD {len(fc['edges'])}"
    assert sum(1 for e in ours if e["visible"]) == fc["nvis"]
    for i, (o, f) in enumerate(zip(ours, fc["edges"])):
        assert o["curve"] == f["curve"], f"Edge{i}"
        assert close(o["start"], f["start"], 1e-5) and close(o["end"], f["end"], 1e-5), f"Edge{i}: {o} vs {f}"
        if "radius" in f and "radius" in o:
            assert abs(o["radius"] - f["radius"]) <= 1e-6 and close(o["center"], f["center"], 1e-5), f"Edge{i}"
    verts = [[v.x / d.geo[view].scale, -v.y / d.geo[view].scale, 0.0] for v in d.geo[view].vertices]
    assert len(verts) == len(fc["vertices"])
    for i, (o, f) in enumerate(zip(verts, fc["vertices"])):
        assert close(o, f, 1e-5), f"Vertex{i}: {o} vs {f}"


@pytest.mark.parametrize("case,view", VIEW_CASES)
def test_view_placement(case, view):
    """X and Y (a group's item: relative to the group, as FreeCAD stores them), Scale, Direction, XDirection."""
    from cad_agent import techdraw as T
    fc = FREECAD[case]["views"][view]
    d = doc(case)
    o = d.get(view)
    g = d.group_of(view)
    x, y = d.pos[view]
    if g is not None:
        x, y = x - g.x, y - g.y
    assert abs(x - fc["X"]) <= 1e-6 and abs(y - fc["Y"]) <= 1e-6, f"({x}, {y}) vs ({fc['X']}, {fc['Y']})"
    assert abs(d.geo[view].scale - fc["Scale"]) <= 1e-9
    assert close(o.direction, fc["Direction"], 1e-9) and close(o.x_direction, fc["XDirection"], 1e-9)
    if isinstance(o, T.DrawProjGroupItem) and g is None or not isinstance(o, T.DrawProjGroupItem):
        assert abs(o.rotation - fc["Rotation"]) <= 1e-9


def dxf_pairs(text):
    lines = text.split("\n")
    return [(lines[i].strip(), lines[i + 1]) for i in range(0, len(lines) - 1, 2)]


def dxf_entities(text):
    """The ENTITIES section as [{"type", code: [values]}]."""
    out, cur, inside = [], None, False
    for code, value in dxf_pairs(text):
        if code == "2" and value == "ENTITIES" and cur is None:
            inside = True
            continue
        if not inside:
            continue
        if code == "0":
            if cur is not None:
                out.append(cur)
            if value == "ENDSEC":
                break
            cur = {"type": value}
        elif cur is not None:
            cur.setdefault(code, []).append(value)
    return out


def dxf_texts(case):
    return {e["8"][0]: e["1"][0] for e in dxf_entities(FREECAD[case]["dxf"]) if e["type"] == "DIMENSION"}


DIM_CASES = [(c, n) for c in CASES for n in FREECAD[c].get("dims", {})]


@pytest.mark.parametrize("case,dim", DIM_CASES)
def test_dimension(case, dim):
    fc = FREECAD[case]["dims"][dim]
    d = doc(case)
    o = d.get(dim)
    assert o.format_spec == fc["FormatSpec"]
    assert abs(o.under_tolerance - fc["UnderTolerance"]) <= 1e-12
    assert o.format_spec_under_tolerance == fc["FormatSpecUnderTolerance"]
    if fc["raw"] == 0.0 and dim not in d.dims:      # FreeCAD failed it too (concentric circles: gp_Dir of zero)
        assert dim in d.errors
        return
    m = d.dims[dim]
    assert abs(m["value"] - fc["raw"]) <= 1e-9 * max(1.0, abs(fc["raw"]))
    assert m["unaltered"] == fc["text"]                 # getText(): Format::UNALTERED
    shown = dxf_texts(case).get(dim)                    # writeDXFPage writes the FORMATTED text the page shows
    if shown is not None:
        assert m["text"] == shown
    if "linear" in fc:
        assert close(m["first"], fc["linear"][0][:2], 1e-6) and close(m["second"], fc["linear"][1][:2], 1e-6)
    if "arc" in fc:
        assert close(m["center"], fc["arc"][0][:2], 1e-6)
        assert close(m["onCurve"][0], fc["arc"][1][:2], 1e-6)
    if "angle" in fc:
        assert close(m["first"], fc["angle"][0][:2], 1e-6) and close(m["second"], fc["angle"][1][:2], 1e-6)
        assert close(m["vertex"], fc["angle"][2][:2], 1e-6)


@pytest.mark.parametrize("case", sorted(CASES))
def test_template(case):
    fc = FREECAD[case]["template"]
    d = doc(case)
    w, h = d.page_size()
    assert (w, h) == (fc["Width"], fc["Height"])
    ours = dict(d.template.editable_texts)
    theirs = dict(fc["EditableTexts"])
    for k in ("FC-Date",):              # the day each was made
        ours.pop(k, None), theirs.pop(k, None)
    assert ours == theirs
