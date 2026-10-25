"""cad_agent.feature builds what FreeCAD's PartDesign builds for the references a pick in the 3D view gives a feature
(cad_agent/feature_refs.py): a datum plane, a datum line, an LCS's feature, PartDesign's own datums and an edge, as a Pad's or
Pocket's Up to face and ReferenceAxis, a Revolution's axis, a Mirrored's plane, a pattern's direction or axis and a Draft's
neutral plane and pull direction.

tests/golden/pick/cases.py holds the bodies; make.py built each in FreeCAD 26.3 (3160daf1e2b6) through
feature.to_freecad and wrote freecad.json. Here the same lines go through feature.Body and must give the same solid
(volume and area to 1e-6 relative, the box and centre of mass to 1e-6 of the box's size, the same solids and faces),
or, for a case FreeCAD refuses, a FeatureError with FreeCAD's message.
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

from cad_agent import feature
from cad_agent.feature import Body, FeatureError

GOLDEN = Path(__file__).parent / "golden" / "pick"
_spec = importlib.util.spec_from_file_location("pick_cases", GOLDEN / "cases.py")
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES = _cases.CASES


def _measure(part):
    """What make.py records of FreeCAD's Body (tests/test_feature.py measures the same way)."""
    shape = part.wrapped
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    com, vol = [0.0, 0.0, 0.0], 0.0
    for s in part.solids():
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(s.wrapped, props)
        c = props.CentreOfMass()
        vol += props.Mass()
        com = [com[0] + c.X() * props.Mass(), com[1] + c.Y() * props.Mass(), com[2] + c.Z() * props.Mass()]
    faces = []
    for f in feature._faces(shape):
        fp = GProp_GProps()
        BRepGProp.SurfaceProperties_s(f, fp)
        fc = fp.CentreOfMass()
        faces.append([fp.Mass(), fc.X(), fc.Y(), fc.Z()])
    return {"volume": part.volume, "area": part.area, "bbox": [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()],
            "center_of_mass": [x / vol for x in com], "solids": len(part.solids()), "faces": len(faces),
            "face_list": faces}

FREECAD = json.loads((GOLDEN / "freecad.json").read_text())["cases"]
BUILT = sorted(n for n in CASES if not CASES[n].get("error"))
REFUSED = sorted(n for n in CASES if CASES[n].get("error"))

FACES_DIFFER: dict = {}


def test_every_case_has_freecads_answer():
    assert set(CASES) == set(FREECAD), "run tests/golden/pick/make.py in freecadcmd"
    assert len(BUILT) >= 35
    assert not [n for n in BUILT if "error" in FREECAD[n] or not FREECAD[n]["valid"]]
    assert all("error" in FREECAD[n] for n in REFUSED)


@pytest.mark.parametrize("name", BUILT)
def test_same_solid_as_freecad(name):
    case, want = CASES[name], FREECAD[name]
    got = _measure(Body(case["features"], case.get("params")))
    assert got["volume"] == pytest.approx(want["volume"], rel=1e-6)
    assert got["area"] == pytest.approx(want["area"], rel=1e-6)
    size = math.dist(want["bbox"][:3], want["bbox"][3:])
    assert got["bbox"] == pytest.approx(want["bbox"], abs=1e-6 * size)
    assert got["center_of_mass"] == pytest.approx(want["center_of_mass"], abs=1e-6 * size)
    if name in FACES_DIFFER:
        assert (got["solids"], got["faces"]) == (want["solids"], FACES_DIFFER[name])
        return
    assert (got["solids"], got["faces"]) == (want["solids"], want["faces"])
    key = lambda f: tuple(round(x, 4) for x in f)       # noqa: E731
    assert sorted(map(key, got["face_list"])) == sorted(map(key, want["face_list"]))


@pytest.mark.parametrize("name", REFUSED)
def test_refused_as_freecad_refuses(name):
    case, want = CASES[name], FREECAD[name]["error"]
    message = want.split(": ", 1)[1]                     # "Mirrored: No mirror plane reference specified"
    with pytest.raises(FeatureError) as e:
        Body(case["features"], case.get("params"))
    assert message in str(e.value)
