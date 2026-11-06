"""cad_agent/assembly_array.py held to FreeCAD 26.3's link arrays (tests/golden/link_array, make.py): each element's
Placement, every case."""
import importlib.util
import json
from pathlib import Path

import pytest

from cad_agent import assembly_wb as W

HERE = Path(__file__).parent / "golden" / "link_array"
_spec = importlib.util.spec_from_file_location("link_array_cases", HERE / "cases.py")   # each golden folder has its cases.py
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES

FC = json.loads((HERE / "freecad.json").read_text())
KEYS = {"Direction": "direction", "Direction2": "direction2", "Axis": "axis", "Reversed": "reversed",
        "Reversed2": "reversed2", "Mode": "mode", "Mode2": "mode2", "Length": "length", "Length2": "length2",
        "Offset": "offset", "Offset2": "offset2", "Occurrences": "occurrences", "Occurrences2": "occurrences2",
        "Spacings": "spacings", "Angle": "angle", "NumberCircles": "number_circles", "RadialDistance": "radial_distance",
        "TangentialDistance": "tangential_distance", "Symmetry": "symmetry"}
CLASSES = {"Part::LinkArrayLinear": "LinkArrayLinear", "Part::LinkArrayPolar": "LinkArrayPolar",
           "Part::LinkArrayCircular": "LinkArrayCircular"}


def same(a, b):
    q = [abs(x - y) for x, y in zip(a[3:], b[3:])]
    nq = [abs(x + y) for x, y in zip(a[3:], b[3:])]
    return all(abs(x - y) < 1e-9 for x, y in zip(a[:3], b[:3])) and (max(q) < 1e-12 or max(nq) < 1e-12)


@pytest.mark.parametrize("name", sorted(CASES))
def test_element_placements(name):
    type_id, props = CASES[name]
    cls = W.CLASSES[CLASSES[type_id]]
    a = cls("A", "pin", **{KEYS[k]: v for k, v in props.items()})
    ours = [[*p.pos, *p.rot.q] for p in a.element_placements()]
    want = FC[name]
    assert len(ours) == len(want)
    for i, (o, w) in enumerate(zip(ours, want)):
        assert same(o, w), f"element {i}: ours {o}, FreeCAD {w}"


# ── in a project: `cad assembly apply` with an array op, written to assembly.py, one body for the gates ──────────

def test_a_link_array_is_made_written_and_seen_as_one_body(tmp_path, monkeypatch, capsys):
    from cad_agent import ondsel
    from cad_agent import state as st
    from test_assembly_edit import PART
    from test_cli import run
    if not ondsel.available():
        pytest.skip("ui/ondsel is not built")
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    monkeypatch.setenv("CAD_WARM", "0")
    d = tmp_path / "asm"
    (d / "parts").mkdir(parents=True)
    (d / "parts" / "plate.py").write_text(PART.format(name="plate", obj='Part.Box("Box", length=40, width=30, height=5)'))
    (d / "parts" / "pin.py").write_text(PART.format(name="pin", obj='Part.Cylinder("Cylinder", radius=3, height=20)'))
    run(capsys, "assembly", "insert", "asm", "plate")
    code, data = run(capsys, "assembly", "apply", "asm", "--ops", json.dumps(
        [{"op": "array", "kind": "LinkArrayLinear", "part": "pin", "props": {"occurrences": 3, "length": 20}}]))
    assert code == 0, data
    src = (d / "assembly.py").read_text()
    assert 'Assembly.LinkArrayLinear("LinearLinkArray", "pin", length=20, occurrences=3),' in src, src
    objs = __import__("cad_agent.assembly_edit", fromlist=["x"]).objects_of(src)
    parts = W.parts("asm", objs)
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    ex, n = TopExp_Explorer(parts["LinearLinkArray"].wrapped, TopAbs_SOLID), 0
    while ex.More():
        n += 1
        ex.Next()
    assert n == 3
    bb = parts["LinearLinkArray"].bounding_box()
    assert abs(bb.max.X - bb.min.X - 26.0) < 1e-6          # three 6 mm pins, 10 mm apart
    code, data = run(capsys, "assembly", "apply", "asm", "--ops", json.dumps(
        [{"op": "set", "name": "LinearLinkArray", "props": {"occurrences": 4}}]))
    assert code == 0, data
    assert "occurrences=4" in (d / "assembly.py").read_text()
    code, data = run(capsys, "assembly", "apply", "asm", "--ops", json.dumps(
        [{"op": "set", "name": "LinearLinkArray", "props": {"direction": "W_Axis"}}]))
    assert code != 0


# ── Path and Point Link Arrays (tests/golden/link_array/cases_path.py, make_path.py) ──────────────────────────────

_pspec = importlib.util.spec_from_file_location("link_array_cases_path", HERE / "cases_path.py")
_pcases = importlib.util.module_from_spec(_pspec)
_pspec.loader.exec_module(_pcases)
PATH_CASES = _pcases.CASES
FC_PATH = json.loads((HERE / "freecad_path.json").read_text())
PKEYS = {"Count": "count", "SpacingMode": "spacing_mode", "Spacing": "spacing", "StartOffset": "start_offset",
         "EndOffset": "end_offset", "ReversePath": "reverse_path", "Align": "align", "VerticalVector": "vertical_vector"}


def _shape(spec):
    """make_path.py's shapes, made by the stand-ins' Part (cad_agent/fcshim) as FreeCAD's Part makes them."""
    from cad_agent import cam_runtime
    cam_runtime.activate()
    import FreeCAD as App
    import Part
    V = App.Vector
    kind = spec[0]
    if kind == "polygon":
        s = Part.makePolygon([V(*p) for p in spec[1]])
    elif kind == "circle":
        s = Part.Wire([Part.makeCircle(spec[1])])
    elif kind == "arc":
        s = Part.Wire([Part.makeCircle(spec[1], V(0, 0, 0), V(0, 0, 1), 0, spec[2])])
    elif kind == "bspline":
        b = Part.BSplineCurve()
        b.interpolate([V(*p) for p in spec[1]])
        s = Part.Wire([b.toShape()])
    else:
        s = Part.makeBox(*spec[1:])
    return s._s


@pytest.mark.parametrize("name", sorted(PATH_CASES))
def test_path_and_point_element_placements(name):
    type_id, props, spec = PATH_CASES[name]
    if type_id.endswith("Path"):
        a = W.LinkArrayPath("A", "pin", path=("path", props.get("Path") or []),
                            **{PKEYS[k]: v for k, v in props.items() if k != "Path"})
    else:
        a = W.LinkArrayPoint("A", "pin", point_object="path")
    a._shapes = {"path": _shape(spec)}
    ours = [[*p.pos, *p.rot.q] for p in a.element_placements()]
    want = FC_PATH[name]
    assert len(ours) == len(want), (ours, want)
    for i, (o, w) in enumerate(zip(ours, want)):
        assert same(o, w), f"element {i}: ours {o}, FreeCAD {w}"
