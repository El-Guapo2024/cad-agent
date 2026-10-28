"""The app's CAM (cad_agent/cam_doc.py: FreeCAD's CAM Python over cad_agent/fcshim, libarea built from FreeCAD's
sources) against what FreeCAD 26.3 makes of the same jobs (tests/golden/cam/freecad.json, make.py): every Path object's
commands number by number to 1e-6, the document's objects and their names, and each post-processor's G-code text."""
import importlib.util
import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "golden" / "cam"
_spec = importlib.util.spec_from_file_location("cam_golden_cases", GOLDEN / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
FC = json.loads((GOLDEN / "freecad.json").read_text())


def _native():
    from cad_agent import cam_runtime
    try:
        cam_runtime.activate()
    except cam_runtime.CamUnavailable as e:
        pytest.skip(str(e))


def _shape_of(part):
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    s = TopoDS_Shape()
    BRepTools.Read_s(s, str(GOLDEN / "breps" / f"{part}.brep"), BRep_Builder())
    return s


_built = {}


def built(name):
    if name not in _built:
        _native()
        from cad_agent import cam as C
        from cad_agent import cam_doc
        case = _cases.CASES[name]
        jobs = [(f, [C.Entry(k, n, p) for k, n, p in job]) for f, job in case["jobs"].items()]
        _built[name] = cam_doc.build("golden", jobs, _shape_of)
    return _built[name]


def _same_cmd(a, b):
    if a[0] != b[0] or set(a[1]) != set(b[1]):
        return False
    return all(abs(a[1][k] - b[1][k]) <= 1e-6 for k in a[1])


@pytest.mark.parametrize("name", sorted(_cases.CASES))
def test_paths(name):
    doc = built(name)
    fc = FC[name]
    assert not fc["errors"]
    assert [e[1] for e in doc.doc._errors] == []
    ours = {o.Name: [[c.Name, dict(c._params)] for c in o.Path._cmds] for o in doc.doc.Objects
            if o.TypeId == "Path::FeaturePython" and o._props.get("Path") is not None and o._props["Path"].value}
    for op, cmds in fc["paths"].items():
        mine = ours.get(op, [])
        assert len(mine) == len(cmds), op
        for i, (a, b) in enumerate(zip(cmds, mine)):
            assert _same_cmd(a, b), f"{op} command {i}: FreeCAD {a}, ours {b}"


@pytest.mark.parametrize("name", sorted(_cases.CASES))
def test_objects(name):
    """The document's objects and their names, the tool bits' shape bodies left out: FreeCAD copies a bit's whole
    PartDesign Body (sketch, revolution, origin) from its shape file, the app its Body alone (ui/PARITY.md)."""
    doc = built(name)
    parts = _cases.CASES[name]["parts"]

    def keep(n, t):
        return n not in parts and t.split("::")[0] in ("Path", "App", "Part") and not t.startswith(
            ("App::Line", "App::Plane", "App::Point", "App::Origin")) and not n.startswith("PropertyBag")
    fc = [n for n, t, _ in FC[name]["objects"] if keep(n, t) and t != "PartDesign::Body"]
    ours = [o.Name for o in doc.doc.Objects if keep(o.Name, o.TypeId) and o.TypeId != "PartDesign::Body"]
    assert ours == fc


def _text(g):
    return [ln for ln in g.splitlines() if "Output Time" not in ln]


@pytest.mark.parametrize("name", sorted(_cases.CASES))
def test_posts(name):
    doc = built(name)
    case = _cases.CASES[name]
    for file, job in case["jobs"].items():
        for post, args in case.get("posts", []):
            want = FC[name]["posts"][f"{file}/{post}"]
            got = doc.post(job[0][1], post, args)
            assert [s for s, _ in got] == [s for s, _ in want]
            for (_, g), (_, w) in zip(got, want):
                assert _text(g) == _text(w), f"{file}/{post}"
