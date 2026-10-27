"""The Sketcher's text against FreeCAD 26.3: cad_agent/sketch_text.py's glyphs (makeTextWires,
transformAndConvertToGeometry, setTextAndFont), compared glyph by glyph to 1e-9 with tests/golden/sketchtext/freecad.json
(make.py), and the solver's Text groups (ui/planegcs: the glyphs left out of the solve and moved with the handle).
Also the part file's Text constraint, `cad feature text` and FreeCAD's font list rules."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from cad_agent import sketch_text as T
from cad_agent import sketch_commands as SC

GOLDEN = Path(__file__).parent / "golden" / "sketchtext" / "freecad.json"
TOL = 1e-9
NUMS = {"LineSegment": ("start", "end"), "BSplineCurve": ("poles", "knots", "mults", "degree"),
        "Circle": ("center", "radius"), "Point": ("at",)}


def _flat(v):
    if isinstance(v, (list, tuple)):
        return [x for e in v for x in _flat(e)]
    return [float(v)]


def geometry_diff(ours, theirs, tol=TOL) -> str:
    if len(ours) != len(theirs):
        return f"{len(ours)} geometries, FreeCAD {len(theirs)}"
    for i, (a, b) in enumerate(zip(ours, theirs)):
        if a["type"] != b["type"]:
            return f"geometry {i}: {a['type']}, FreeCAD {b['type']}"
        if bool(a.get("construction")) != bool(b.get("construction")):
            return f"geometry {i}: construction {a.get('construction')}, FreeCAD {b.get('construction')}"
        for k in NUMS.get(a["type"], ()):
            x, y = _flat(a[k]), _flat(b[k])
            if len(x) != len(y) or any(abs(p - q) > tol for p, q in zip(x, y)):
                return f"geometry {i} {k}: {a[k]}, FreeCAD {b[k]}"
    return ""


def constraint_view(c: dict) -> dict:
    if c["type"] == "Text":
        return {"type": "Text", "elements": [int(v) for v in c["args"]], "text": c["text"], "font": c["font"],
                "is_text_height": c["is_text_height"]}
    f = SC.fields(c)
    d = {"type": f["type"], "elements": [f["first"], f["first_pos"], f["second"], f["second_pos"], f["third"],
                                         f["third_pos"]]}
    if f["type"] in ("Distance", "DistanceX", "DistanceY", "Angle"):
        d["value"] = f["value"]
    return d


def constraints_diff(ours, theirs, tol=TOL) -> str:
    if len(ours) != len(theirs):
        return f"{len(ours)} constraints, FreeCAD {len(theirs)}"
    for i, (c, t) in enumerate(zip(ours, theirs)):
        a = constraint_view(c)
        for k in ("type", "elements", "text", "font", "is_text_height"):
            if k in t and a.get(k) != t[k]:
                return f"constraint {i} {k}: {a.get(k)}, FreeCAD {t[k]}"
        if "value" in t and abs(a["value"] - t["value"]) > tol:
            return f"constraint {i} value: {a['value']}, FreeCAD {t['value']}"
    return ""


def _font(name: str, digest: str | None) -> str | None:
    """The machine's file of that name, when it is the font the golden was made with."""
    for p in T.fonts().values():
        if os.path.basename(p) == name:
            if digest and hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest:
                return None
            return p
    return None


def _solve(geometry, constraints):
    from cad_agent import planegcs
    out = planegcs.solve({"geometry": geometry, "constraints": constraints})
    assert out["status"] == "solved", out.get("status")
    return [{k: v for k, v in g.items() if k not in ("start_point", "end_point")} for g in out["geometry"]]


def _clean(geo):
    return [{k: v for k, v in g.items() if k not in ("start_point", "end_point", "weights", "periodic")} for g in geo]


def compare(case: dict) -> str | None:
    """'' when ours is FreeCAD's at every step, None when the case's font is not on this machine."""
    fc = case["freecad"]
    if "error" in fc:
        return "FreeCAD: " + fc["error"].strip().splitlines()[-1]
    font = _font(case["font_name"], case.get("font_sha256"))
    if font is None:
        return None
    fonts = {case["font_name"]: font}
    if case.get("edit_font_name"):
        f2 = _font(case["edit_font_name"], case.get("edit_font_sha256"))
        if f2 is None:
            return None
        fonts[case["edit_font_name"]] = f2
    geo = [dict(g) for g in case.get("before", [])]
    geo.append({"type": "LineSegment", "start": list(case["p1"]), "end": list(case["p2"]), "construction": True})
    cons = [T.text_constraint([(len(geo) - 1, 0)], case["text"], font, case["height"])]
    r = T.set_text_and_font(geo, cons, 0, case["text"], font, case["height"], case["construction"])
    geo, cons = r["geometry"], r["constraints"]
    steps = fc["steps"]
    why = geometry_diff(geo, _clean(steps[0]["geometry"])) or constraints_diff(cons, steps[0]["constraints"])
    if why:
        return "made: " + why
    for i, e in enumerate(case.get("edits", [])):
        if e["op"] == "set":
            r = T.set_text_and_font(geo, cons, e["index"], e["text"], fonts.get(e["font"], e["font"]), e["height"],
                                    e["construction"])
            geo, cons = r["geometry"], r["constraints"]
        elif e["op"] == "geometry":
            geo = geo + [dict(e["geo"])]
        elif e["op"] == "constraint":
            c = {"type": e["type"], "args": list(e["args"]), "driving": True, "name": ""}
            if "value" in e:
                c["value"] = e["value"]
            cons = cons + [c]
        geo = _solve(geo, cons)
        want = steps[i + 1]
        why = geometry_diff(geo, _clean(want["geometry"])) or constraints_diff(cons, want["constraints"])
        if why:
            return f"edit {i} ({e['op']}): {why}"
    return ""


def compare_all(cases):
    bad, skipped = [], 0
    for c in cases:
        why = compare(c)
        if why is None:
            skipped += 1
        elif why:
            bad.append((c["name"], why))
    return bad, skipped


def _planegcs() -> bool:
    try:
        from cad_agent import planegcs
        planegcs.solve({"name": "probe", "geometry": [], "constraints": []})
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def test_glyphs_as_freecad_makes_them(golden):
    """Every string, font and method of the golden through setTextAndFont, glyph by glyph."""
    made = [c for c in golden if not c.get("edits")]
    assert len(made) > 40
    bad, skipped = compare_all(made)
    assert not bad, f"{len(bad)} of {len(made)} differ: " + "; ".join(f"{n}: {w}" for n, w in bad[:5])
    assert skipped < len(made) - 20                    # the shipped font's cases always run


@pytest.mark.skipif(not _planegcs(), reason="the native PlaneGCS (ui/planegcs/build.sh native) is not built")
def test_edits_and_the_handles_solve(golden):
    """EditTextDialog's changes and constraints on the handle: the glyphs follow it as FreeCAD's solve moves them."""
    edited = [c for c in golden if c.get("edits")]
    assert len(edited) >= 12
    bad, _ = compare_all(edited)
    assert not bad, f"{len(bad)} of {len(edited)} differ: " + "; ".join(f"{n}: {w}" for n, w in bad[:5])


def test_the_font_list_follows_fontprovider(tmp_path, monkeypatch):
    """The shipped font first, a name being a file's baseName, the first of a name (any case) winning, only
    .ttf/.otf/.ttc; the default osifont-lgpl3fe."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    for p in (a / "Zed.TTF", a / "zed.otf", a / "two.parts.ttf", a / "skip.pfb", b / "Alpha.otf"):
        p.write_bytes(b"x")
    monkeypatch.setattr(T, "_platform_font_files", lambda: [str(a / n) for n in sorted(os.listdir(a))] +
                        [str(b / "Alpha.otf")])
    table = T.fonts(refresh=True)
    try:
        assert "osifont-lgpl3fe" in table and table["osifont-lgpl3fe"].endswith("cad_agent/fonts/osifont-lgpl3fe.ttf")
        assert "Zed" in table and "zed" not in table and "two" in table and "skip" not in table and "Alpha" in table
        assert T.font_names() == sorted(table, key=lambda n: (n.casefold(), n))
        assert T.default_font() == "osifont-lgpl3fe"
        assert T.file_name_pure("/x/y/two.parts.ttf") == "two.parts"
    finally:
        T.fonts(refresh=True)


def test_the_part_file_keeps_the_text_constraint():
    from cad_agent import feature as F
    from cad_agent import feature_edit as E
    geo = [{"type": "LineSegment", "start": [0, 0], "end": [0, 5], "construction": True}]
    r = T.set_text_and_font(geo, [T.text_constraint([(0, 0)], "A", T.font_path("osifont-lgpl3fe"))], 0, "A",
                            "osifont-lgpl3fe")
    c = r["constraints"][0]
    src = E.constraint_src(c)
    assert src.startswith('Constraint("Text", [0, 0, 1, 0, ') and src.endswith('], "A", "osifont-lgpl3fe", True)')
    k = F.constraint_from_dict(c)
    assert k.elements[0] == (0, 0) and k.text == "A" and k.font == "osifont-lgpl3fe" and k.is_text_height
    assert E._constraint_dict(k) == {**c, "driving": True, "name": ""}
    sk = F.Sketch("S", geometry=[F.geometry_from_dict(g) for g in r["geometry"]], constraints=[k])
    assert sk.unsatisfied() == [] and sk.as_dict()["constraints"][0]["text"] == "A"
    assert F.profile_face(sk) is not None              # the glyphs make a face, as FreeCAD's sketch shape does
    with pytest.raises(F.FeatureError, match="even number"):
        F.Constraint("Text", [0], "A", "f")


def test_a_padded_text_in_a_part_file(tmp_path):
    """The workbench's save of a sketch with a text (feature_edit's ops), built: the glyphs pad, the file reads back
    as it was written, and moving the handle by a constraint moves the glyphs (the solver's group)."""
    import importlib.util
    import shutil
    from cad_agent import feature_edit as E
    plate = tmp_path / "plate.py"
    shutil.copy(Path(__file__).parent / "fixtures" / "feature_plate" / "parts" / "plate.py", plate)

    def volume(path):
        spec = importlib.util.spec_from_file_location(f"p{id(path)}{path.stat().st_mtime_ns}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.build(**mod.PARAMS).volume
    before = volume(plate)
    geo = [{"type": "LineSegment", "start": [-20, -5], "end": [-20, 5], "construction": True}]
    r = T.set_text_and_font(geo, [T.text_constraint([(0, 0)], "Hi", T.font_path("osifont-lgpl3fe"))], 0, "Hi",
                            "osifont-lgpl3fe")
    sketch = {"name": "Label", "type": "Sketcher::SketchObject", "support": "XY", "attachment_offset": [0, 0, 6],
              "geometry": r["geometry"], "constraints": r["constraints"]}
    pad = {"name": "LabelPad", "type": "PartDesign::Pad", "profile": "Label", "length": 1.0}
    E.apply(plate, [{"op": "add", "feature": sketch}, {"op": "add", "feature": pad}, {"op": "tip", "name": "LabelPad"}])
    src = plate.read_text()
    assert 'Constraint("Text", [0, 0, 1, 0, 2, 0,' in src and '"Hi", "osifont-lgpl3fe", True)' in src
    back = next(f for f in E.read(plate)["features"] if f["name"] == "Label")
    assert back["constraints"] == [dict(c, driving=True, name="") for c in r["constraints"]]
    assert geometry_diff(back["geometry"], r["geometry"], 1e-8) == ""   # written to 9 decimals, as all geometry is

    assert volume(plate) > before + 1.0                # the letters, 1 mm high, on the plate
    if _planegcs():
        cons = r["constraints"] + [{"type": "DistanceY", "args": [0, 1, 0, 2], "value": 20.0, "driving": True, "name": ""}]
        geo2 = _solve(r["geometry"], cons)
        assert geo2[0]["end"][1] - geo2[0]["start"][1] == pytest.approx(20.0)
        h0 = max(p[1] for g in r["geometry"][1:] for p in g.get("poles", [g.get("start"), g.get("end")])) - \
            min(p[1] for g in r["geometry"][1:] for p in g.get("poles", [g.get("start"), g.get("end")]))
        h1 = max(p[1] for g in geo2[1:] for p in g.get("poles", [g.get("start"), g.get("end")])) - \
            min(p[1] for g in geo2[1:] for p in g.get("poles", [g.get("start"), g.get("end")]))
        assert h1 == pytest.approx(2 * h0, rel=1e-9)   # the handle doubled: so did the glyphs


def test_cad_feature_text(capsys):
    from cad_agent import cli
    from test_cli import run
    code, data = run(capsys, "feature", "text", "--req", json.dumps([
        {"op": "fonts"}, {"op": "shapes", "text": "o"},
        {"op": "geometry", "text": "o", "p1": [0, 0], "p2": [0, 5], "height": True}, {"op": "nope"}]))
    assert code == cli.OK
    fonts, shapes, geo, bad = data["answers"]
    assert fonts["default"] == "osifont-lgpl3fe" and "osifont-lgpl3fe" in fonts["fonts"]
    assert shapes["box"] and shapes["geometry"] and geo["geometry"]
    assert "unknown op" in bad["error"]
