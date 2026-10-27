"""PartDesign's last commands in a FEATURES list are what FreeCAD's PartDesign makes: the Involute Gear and the
Sprocket (cad_agent/feature_gear.py), ...

tests/golden/pdlast/cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote freecad.json. Here the same lines go through feature.evaluate and Body: the Body's solid,
and every object's shape, must be FreeCAD's. Each feature also goes through the part file (feature_edit), as every
feature_kw.KwFeature does.
"""
import importlib.util
import json
import math
from pathlib import Path

import pytest
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX

from cad_agent import feature
from cad_agent import feature_edit as E
from cad_agent.feature import Body

GOLDEN = Path(__file__).parent / "golden" / "pdlast"
_spec = importlib.util.spec_from_file_location("pdlast_cases", GOLDEN / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES
FREECAD = json.loads((GOLDEN / "freecad.json").read_text())["cases"]


def _r(v):
    return round(v, 9) + 0.0


def _box(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    return [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()]


def _measure(shape) -> dict:
    out = {"solids": feature._count(shape, TopAbs_SOLID), "faces": feature._count(shape, TopAbs_FACE),
           "edges": feature._count(shape, TopAbs_EDGE), "vertices": feature._count(shape, TopAbs_VERTEX),
           "bbox": _box(shape)}
    if out["solids"]:
        v, a = GProp_GProps(), GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, v)
        BRepGProp.SurfaceProperties_s(shape, a)
        c = v.CentreOfMass()
        out.update(volume=v.Mass(), area=a.Mass(), center=[c.X(), c.Y(), c.Z()])
    elif out["faces"]:
        a = GProp_GProps()
        BRepGProp.SurfaceProperties_s(shape, a)
        out.update(area=a.Mass())
    else:
        g = GProp_GProps()
        BRepGProp.LinearProperties_s(shape, g)
        out.update(length=g.Mass())
    return out


def _same(got, want, what):
    size = max(math.dist(want["bbox"][:3], want["bbox"][3:]), 1.0)
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size), f"{what}: bbox"
    for k in ("volume", "area", "length"):
        if k in want:
            assert got[k] == pytest.approx(want[k], rel=1e-7, abs=1e-7), f"{what}: {k}"
    if "center" in want:
        assert got["center"] == pytest.approx(want["center"], abs=1e-6 * size), f"{what}: centre"


def _evaluate(name):
    case = CASES[name]
    return feature.evaluate(case["features"], case.get("params"))


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/pdlast/make.py in freecadcmd"
    assert not [n for n, g in FREECAD.items() if "error" in g]


@pytest.mark.parametrize("name", sorted(CASES))
def test_same_body_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    part = Body(case["features"], case.get("params"))
    got = _measure(part.wrapped)
    w = want["body"]
    _same(got, w, "body")
    assert (got["solids"], got["faces"], got["edges"], got["vertices"]) == \
        (w["solids"], w["faces"], w["edges"], w["vertices"])


@pytest.mark.parametrize("name", sorted(_cases.GEAR))
def test_gear_wire_as_freecad(name):
    """The gear's (or sprocket's) Shape: FreeCAD's wire, edge for edge, where its Placement puts it."""
    case, want = CASES[name], FREECAD[name]
    ev = _evaluate(name)
    ctx = ev["_attach"]
    for f in case["features"]:
        if not getattr(f, "is_part2d", False):
            continue
        w = want["objects"][f.name]
        assert w["type"] == "Part::Part2DObjectPython"
        assert ctx.kinds[f.name] == "sketch"
        got = _measure(ctx.sketch_shape(f.name))
        ws = w["shape"]
        assert ws["type"] == "Wire" and ws["closed"]
        assert (got["edges"], got["vertices"]) == (ws["edges"], ws["edges"] * 2)   # loose edges here, a wire there
        _same(got, ws, f"{f.name} wire")
        pl = ctx.placements[f.name]
        assert [_r(c) for c in (*pl.pos, *pl.rot.ypr())] == pytest.approx(w["placement"], abs=1e-9)


@pytest.mark.parametrize("name", sorted(CASES))
def test_tip_as_freecad(name):
    """The Tip our part file reads for these FEATURES (no TIP =): a gear is not a solid feature, as a sketch is not."""
    case, want = CASES[name], FREECAD[name]
    src = "FEATURES = [\n" + "".join(
        f"    {type(f).__name__}({f.name!r}" + (f", {f.profile!r}" if hasattr(f, "profile") else "") + "),\n"
        for f in case["features"]) + "]\n"
    assert E.read_src(src)["tip"] == want["tip"]


NEW_BODY = """from cad_agent.feature import Body

PARAMS = {"teeth": 13.0}

FEATURES = [
]
TIP = None


def build(**p):
    return Body(FEATURES, p, tip=TIP)
"""


def _build(src, tmp_path, name="part"):
    path = tmp_path / f"{name}.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location(f"pdlast_{name}_{id(path)}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(**mod.PARAMS)


def test_gear_part_file_round_trip(tmp_path):
    src = E.apply_src(NEW_BODY, [
        {"op": "add", "feature": {"name": "InvoluteGear", "type": "Part::InvoluteGear"}},
        {"op": "add", "feature": {"name": "Pad", "type": "PartDesign::Pad", "profile": "InvoluteGear", "length": 4.0}},
        {"op": "set", "name": "InvoluteGear", "props": {"number_of_teeth": "teeth", "modules": 1.5}},
        {"op": "add", "feature": {"name": "Sprocket", "type": "Part::Sprocket", "sprocket_reference": "ANSI 40",
                                  "pitch": 12.7, "attachment_support": [["XY_Plane", ""]], "map_mode": "FlatFace",
                                  "attachment_offset": [[0.0, 0.0, 4.0], [0.0, 0.0, 0.0]]}},
    ])
    assert 'InvoluteGear("InvoluteGear", number_of_teeth="teeth", modules=1.5)' in src
    d = E.read_src(src)
    gear = next(f for f in d["features"] if f["name"] == "InvoluteGear")
    assert gear["type"] == "Part::InvoluteGear" and gear["pressure_angle"] == 20.0 and gear["high_precision"] is True
    assert d["tip"] == "Pad"                         # neither the gear nor the sprocket is a solid feature
    part = _build(src, tmp_path)
    want = Body([feature.InvoluteGear("InvoluteGear", number_of_teeth=13, modules=1.5),
                 feature.Pad("Pad", "InvoluteGear", length=4.0)])
    assert part.volume == pytest.approx(want.volume, rel=1e-12)
    # a gear something uses is not deleted; a Pad's profile must be a sketch or a gear before it
    with pytest.raises(E.FeatureEditError, match="Pad"):
        E.apply_src(src, [{"op": "delete", "name": "InvoluteGear"}])
    with pytest.raises(E.FeatureEditError, match="not one of"):
        E.apply_src(src, [{"op": "set", "name": "Sprocket", "props": {"sprocket_reference": "ANSI 99"}}])
