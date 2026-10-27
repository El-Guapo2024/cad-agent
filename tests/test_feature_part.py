"""cad_agent.feature_part builds what FreeCAD's Part workbench builds, object by object, from the same OBJECTS lines.

tests/golden/part/cases.py holds the documents; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature_part.to_freecad and wrote freecad.json. Here the same lines go through feature_part.evaluate and every object
must have the same shape (volume, area and length to 1e-6 relative, the box and the centre of mass to 1e-6 of the box's
size, the same shape type and counts of solids, shells, faces, wires, edges and vertices), or, where FreeCAD's recompute
marks the object invalid, fail with FreeCAD's message. Each class's DEFAULTS are FreeCAD's fresh object's.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import (TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE)

from cad_agent import attacher as A
from cad_agent import feature as F
from cad_agent import feature_part as Part

GOLDEN = Path(__file__).parent / "golden" / "part"
CASES, FREECAD = {}, {}
for _p in sorted(GOLDEN.glob("cases*.py")):          # cases.py, and each area's cases_<area>.py
    _spec = importlib.util.spec_from_file_location(f"part_{_p.stem}", _p)
    _cases = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_cases)
    _json = GOLDEN / ("freecad.json" if _p.stem == "cases" else f"freecad_{_p.stem[6:]}.json")
    _fc = json.loads(_json.read_text()) if _json.exists() else {"cases": {}}
    assert not set(_cases.CASES) & set(CASES), f"two areas name a case the same: {set(_cases.CASES) & set(CASES)}"
    CASES.update(_cases.CASES)
    FREECAD.update(_fc["cases"])
FC = json.loads((GOLDEN / "freecad.json").read_text())
# AttachExtension's properties on a fresh object of each type (make.py attach): a Part::Primitive and a Tube have the
# extension, the other types get Part::AttachExtensionPython as the Attachment editor adds it.
_EXT = GOLDEN / "freecad_attach.json"
EXT = json.loads(_EXT.read_text()).get("extension", {}) if _EXT.exists() else {}
TYPES = {"TopAbs_COMPOUND": "Compound", "TopAbs_COMPSOLID": "CompSolid", "TopAbs_SOLID": "Solid",
         "TopAbs_SHELL": "Shell", "TopAbs_FACE": "Face", "TopAbs_WIRE": "Wire", "TopAbs_EDGE": "Edge",
         "TopAbs_VERTEX": "Vertex"}

# Known differences, each in ui/PARITY.md ("Part workbench"): {(case, object): the counts that differ}; an area's
# cases_<area>.py adds its own (KNOWN there). The refine is FreeCAD's BRepBuilderAPI_RefineModel as cad_agent/refine.py
# ports it. In a cut through a cut the boolean gives FreeCAD's shape (cut_chain_norefine: 25 edges, 10 faces), and the
# port's refine joins two edges more than FreeCAD's (22 against 24, the same 9 faces and solid).
KNOWN: dict = {("cut_chain", "Cut001"): ("edges", "vertices"), ("cut_compound_tool", "Cut"): ("edges", "vertices")}
for _p in sorted(GOLDEN.glob("cases_*.py")):
    _spec = importlib.util.spec_from_file_location(f"part_known_{_p.stem}", _p)
    _m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    KNOWN.update(getattr(_m, "KNOWN", {}))


def _props(shape, fn):
    p = GProp_GProps()
    fn(shape, p)
    return p


def _com(shape):
    """make.py's centre of mass: volume-weighted over the solids, else area over the faces, else length over the
    edges, else the vertices' mean."""
    for kind, fn in ((TopAbs_SOLID, BRepGProp.VolumeProperties_s), (TopAbs_FACE, BRepGProp.SurfaceProperties_s),
                     (TopAbs_EDGE, BRepGProp.LinearProperties_s)):
        parts = F._subs(shape, kind) if kind != TopAbs_SOLID else _solids(shape)
        props = [_props(s, fn) for s in parts]
        tot = sum(p.Mass() for p in props)
        if parts and tot > 1e-12:
            return [sum(getattr(p.CentreOfMass(), k)() * p.Mass() for p in props) / tot for k in ("X", "Y", "Z")]
    vs = F._subs(shape, TopAbs_VERTEX)
    if not vs:
        return None
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in vs]
    return [sum(getattr(p, k)() for p in pts) / len(pts) for k in ("X", "Y", "Z")]


def _solids(shape):
    """TopoShape.Solids: TopExp_Explorer's solids (one per occurrence, as FreeCAD's getSubShapes)."""
    from OCP.TopExp import TopExp_Explorer
    out, ex = [], TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def measure(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    return {
        "type": TYPES[shape.ShapeType().name], "valid": BRepCheck_Analyzer(shape).IsValid(),
        "volume": _props(shape, BRepGProp.VolumeProperties_s).Mass(),
        "area": _props(shape, BRepGProp.SurfaceProperties_s).Mass(),
        "length": _props(shape, BRepGProp.LinearProperties_s).Mass(),
        "bbox": [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()], "center_of_mass": _com(shape),
        "solids": len(F._subs(shape, TopAbs_SOLID)), "shells": len(F._subs(shape, TopAbs_SHELL)),
        "faces": len(F._subs(shape, TopAbs_FACE)), "wires": len(F._subs(shape, TopAbs_WIRE)),
        "edges": len(F._subs(shape, TopAbs_EDGE)), "vertices": len(F._subs(shape, TopAbs_VERTEX)),
    }


PAIRS = sorted((c, o) for c in CASES for o in FREECAD.get(c, {}) if not o.startswith("_"))


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/part/make.py in freecadcmd"
    assert not [c for c in CASES if "_error" in FREECAD[c]], "a case FreeCAD could not take"


@pytest.fixture(scope="module")
def built():
    out = {}
    for name, case in CASES.items():
        out[name] = Part.evaluate(case["objects"], case.get("params"), case.get("features"), keep_going=True)
    return out


@pytest.mark.parametrize("case,obj", PAIRS)
def test_same_shape_as_freecad(built, case, obj):
    want = FREECAD[case][obj]
    shapes = built[case]
    if "error" in want:
        assert obj in shapes["_errors"], f"{case}/{obj}: FreeCAD fails ({want['error']}), this built it"
        assert want["error"].strip() in shapes["_errors"][obj], shapes["_errors"][obj]
        return
    assert obj not in shapes["_errors"], f"{case}/{obj}: {shapes['_errors'].get(obj)}"
    got = measure(shapes[obj])
    known = KNOWN.get((case, obj), ())
    for k in ("volume", "area", "length"):
        assert got[k] == pytest.approx(want[k], rel=1e-6, abs=1e-6), k
    size = max(math.dist(want["bbox"][:3], want["bbox"][3:]), 1e-3)
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size)
    if want["center_of_mass"] is not None:
        assert got["center_of_mass"] == pytest.approx(want["center_of_mass"], abs=1e-6 * size)
    assert got["valid"] == want["valid"]
    for k in ("type", "solids", "shells", "faces", "wires", "edges", "vertices"):
        if k not in known:
            assert got[k] == want[k], k
    if "placement" in want:                     # where the object sits: its attachment's, else its placement=
        pl = shapes["_ctx"].placements[obj]
        pos, ypr = want["placement"]
        assert pl.pos == pytest.approx(pos, abs=1e-6 * size), "placement"
        got_m = [c for row in pl.rot.matrix() for c in row]
        want_m = [c for row in A.Rotation.from_ypr(*ypr).matrix() for c in row]
        assert got_m == pytest.approx(want_m, abs=1e-9), "placement rotation"


CLASSES = sorted(Part.OBJECTS.items())


@pytest.mark.parametrize("kind,cls", CLASSES, ids=[k for k, _ in CLASSES])
def test_defaults_are_freecads(kind, cls):
    fc = FC["defaults"][cls.TYPE_ID]
    assert "error" not in fc, fc
    ext = EXT.get(cls.TYPE_ID, {})
    for key, d in cls.DEFAULTS.items():
        if key in ("label", "visibility"):          # the Label, and the ViewObject's Visibility
            continue
        if key == "placement":
            assert "Placement" in fc
            continue
        prop = cls.prop_name(key)
        if key in cls.ATTACH:                       # AttachExtension's properties, as make.py attach recorded them
            assert "error" not in ext, ext
            assert prop in ext, f"{prop} is not a property of FreeCAD's {cls.TYPE_ID} with AttachExtension"
            v = ext[prop]
            if key == "attachment_offset":          # ours None is FreeCAD's identity Placement
                ours = list(A.Placement.from_offset(d).pos) + list(A.Placement.from_offset(d).rot.ypr())
                assert ours == pytest.approx(v[0] + v[1], abs=1e-9), (prop, ours, v)
                continue
            ours = json.loads(json.dumps(d))
            if key == "attachment_support":
                assert v in (None, [], "None") or isinstance(v, str), (prop, v)
            elif isinstance(v, (int, float, list)) and not isinstance(v, bool):
                assert ours == pytest.approx(v), (prop, ours, v)
            else:
                assert ours == v, (prop, ours, v)
            continue
        assert prop in fc, f"{prop} is not a property of FreeCAD's {cls.TYPE_ID}"
        v = fc[prop]
        if key in cls.REFS:
            assert v in (None, [], "None") or isinstance(v, str), (prop, v)
            continue
        ours = json.loads(json.dumps(d))
        if isinstance(v, list) and v and isinstance(v[0], list):
            assert len(ours) == len(v) and all(a == pytest.approx(b) for a, b in zip(ours, v)), (prop, ours, v)
        elif isinstance(v, (int, float, list)) and not isinstance(v, bool):
            assert ours == pytest.approx(v), (prop, ours, v)
        else:
            assert ours == v, (prop, ours, v)


def test_a_reverse_without_a_source_fails_as_its_execute_does():
    """FreeCAD's recompute never runs Reverse::execute on a fresh, source-less Part::Reverse: it stays Valid with a null
    Shape and no message. A part file is a document to build, so the object fails with the message execute returns
    (Reverse::execute: "No part object linked."); no golden case can record FreeCAD's side of it."""
    built = Part.evaluate([Part.Reverse("Reverse")], keep_going=True)
    assert "No part object linked." in built["_errors"]["Reverse"]
