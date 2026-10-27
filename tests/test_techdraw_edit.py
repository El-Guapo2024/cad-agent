"""`cad techdraw` and cad_agent/techdraw_edit.py: a project's TechDraw pages edited from the CLI, written back into
techdraw/<Page>.py, read again the same, undone as one step, and exported; and `cad drawing` and the gates untouched."""
from __future__ import annotations

import json

import pytest

from cad_agent import cli
from cad_agent import state as st
from cad_agent import techdraw as T
from cad_agent import techdraw_edit as E
from test_cli import run

PLATE = '''"""plate: a test plate with a hole and a rounded corner."""
from build123d import Axis, Box, Cylinder, Pos, fillet

MATERIAL = "al6061"
PROCESS = "cnc"
PARAMS = {}


def build(**p):
    b = Box(40, 30, 10)
    b = b - Pos(10, 8, 0) * Cylinder(4, 20)
    return fillet(b.edges().filter_by(Axis.Z)[0:1], 3)
'''


@pytest.fixture
def proj(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    monkeypatch.setenv("CAD_WARM_DIR", str(tmp_path / ".warm"))
    monkeypatch.setenv("CAD_WARM", "0")
    d = tmp_path / "td"
    (d / "parts").mkdir(parents=True)
    (d / "parts" / "plate.py").write_text(PLATE)
    return d


def page_src(d, page="Page"):
    return (d / "techdraw" / f"{page}.py").read_text()


def test_a_page_a_view_and_a_dimension_from_the_cli(proj, capsys):
    code, data = run(capsys, "techdraw", "new", "td", "--template", "ISO/A4_Landscape_TD.svg")
    assert code == cli.OK and data["step"] == "Drawing create page"
    objs = E.objects_of(page_src(proj))
    assert [o.kind for o in objs] == ["DrawPage", "DrawSVGTemplate"]
    assert objs[1].editable_texts["FC-Title"] == "td"           # DrawTemplate::getAutofillValue: the document's Label
    code, data = run(capsys, "techdraw", "view", "td", "Page", "plate", "--direction", "0,0,1")
    assert code == cli.OK and data["step"] == "Create view"
    v = E.objects_of(page_src(proj))[2]
    assert (v.name, v.kind, v.direction, v.x, v.y) == ("View", "DrawProjGroupItem", (0.0, 0.0, 1.0), 148.5, 105.0)
    code, data = run(capsys, "techdraw", "dimension", "td", "Page", "DistanceX", "View:Edge2")
    assert code == cli.OK and data["step"] == "Create dimension"
    dim = data["doc"]["result"]["dimensions"]["Dimension"]
    assert dim["value"] == pytest.approx(40.0) and dim["text"] == "40" and dim["unaltered"] == "40.00 mm"
    # the file reads back as what was written, and is plain Python
    again = E.read(proj, "Page")
    assert [o["name"] for o in again["objects"]] == ["Page", "Template", "View", "Dimension"]
    assert 'TechDraw.DrawViewDimension("Dimension", type="DistanceX", references_2d=[("View", "Edge2")]' in page_src(proj)


def test_an_edit_keeps_the_text_of_the_entries_it_does_not_change(proj, capsys):
    run(capsys, "techdraw", "new", "td")
    run(capsys, "techdraw", "view", "td", "Page", "plate")
    src = page_src(proj).replace('TechDraw.DrawPage("Page", "Template"),', 'TechDraw.DrawPage("Page", "Template"),  # mine')
    (proj / "techdraw" / "Page.py").write_text(src)
    run(capsys, "techdraw", "set", "td", "Page", "View", "hard_hidden=true", "scale_type=Custom", "scale=0.5")
    after = page_src(proj)
    assert '# mine' in after and "hard_hidden=True" in after and "scale=0.5" in after
    assert E.objects_of(after)[2].scale == 0.5


def test_a_projection_group_and_its_items(proj, capsys):
    run(capsys, "techdraw", "new", "td")
    code, data = run(capsys, "techdraw", "projgroup", "td", "Page", "plate", "--projections", "Top,Right")
    assert code == cli.OK and data["step"] == "Create projection group"
    objs = {o.name: o for o in E.objects_of(page_src(proj))}
    g = objs["ProjGroup"]
    assert g.views == ("ProjItem", "ProjItem001", "ProjItem002") and g.anchor == "ProjItem"
    assert [objs[n].label for n in g.views] == ["Front", "Top", "Right"]
    views = data["doc"]["result"]["views"]
    # first angle: the Top below the Front, the Right on its left (DrawProjGroup::getXYPosition)
    assert views["ProjItem001"]["y"] < views["ProjItem"]["y"] and views["ProjItem002"]["x"] < views["ProjItem"]["x"]
    # unticking leaves the group; unticking the last but the Front makes the Front a view again (turnProjGroupToView)
    run(capsys, "techdraw", "projection", "td", "Page", "ProjGroup", "Top", "--off")
    run(capsys, "techdraw", "projection", "td", "Page", "ProjGroup", "Right", "--off")
    objs = {o.name: o for o in E.objects_of(page_src(proj))}
    assert "ProjGroup" not in objs and objs["ProjItem"].label == "View" and objs["ProjItem"].source == ("plate",)


def test_a_view_turns_into_a_group_when_a_projection_is_ticked(proj, capsys):
    run(capsys, "techdraw", "new", "td")
    run(capsys, "techdraw", "view", "td", "Page", "plate")
    run(capsys, "techdraw", "projection", "td", "Page", "View", "Top")
    objs = {o.name: o for o in E.objects_of(page_src(proj))}
    g = objs["ProjGroup"]                                   # TaskProjGroup::turnViewToProjGroup
    assert g.anchor == "View" and g.views == ("View", "ProjItem") and (g.x, g.y) == (148.5, 105.0)
    assert (objs["View"].label, objs["View"].lock_position, objs["View"].x) == ("Front", True, 0.0)


def test_a_section_by_each_arrow(proj, capsys):
    run(capsys, "techdraw", "new", "td")
    run(capsys, "techdraw", "view", "td", "Page", "plate")
    code, data = run(capsys, "techdraw", "section", "td", "Page", "View", "--direction", "Right", "--symbol", "A")
    assert code == cli.OK and data["step"] == "Create Section View"
    s = [o for o in E.objects_of(page_src(proj)) if o.kind == "DrawViewSection"][0]
    # what the real FreeCAD's TaskSectionView gave for the Right arrow (ui/scripts/fctechdraw.json, section_made)
    assert s.section_normal == pytest.approx((-1.0, 0.0, 0.0), abs=1e-12) and s.rotation == -90.0
    assert (s.name, s.label, s.section_direction, s.caption) == ("SectionView", "Section", "Aligned", "SECTION <REF> - <REF>")
    run(capsys, "techdraw", "apply", "td", "Page", "--ops", json.dumps([{"op": "section_edit", "name": "SectionView", "direction": "Up"}]))
    s = [o for o in E.objects_of(page_src(proj)) if o.kind == "DrawViewSection"][0]
    assert s.section_normal == pytest.approx((0.0, 0.0, -1.0), abs=1e-12) and s.rotation == 0.0


def test_delete_takes_a_views_dimensions_with_it_and_undo_brings_them_back(proj, capsys):
    run(capsys, "techdraw", "new", "td")
    run(capsys, "techdraw", "view", "td", "Page", "plate", "--direction", "0,0,1")
    run(capsys, "techdraw", "dimension", "td", "Page", "Diameter", "View:Edge5")
    before = page_src(proj)
    code, data = run(capsys, "techdraw", "delete", "td", "Page", "View")
    assert code == cli.OK and [o.name for o in E.objects_of(page_src(proj))] == ["Page", "Template"]
    code, _ = run(capsys, "undo", "td")
    assert code == cli.OK and page_src(proj) == before


def test_cosmetic_geometry_and_centerlines_from_the_cli_and_back(proj, capsys):
    """Each tool of the Add Lines / Add Vertices menus: written into the view's entry as FreeCAD's properties, read
    again the same, one undo step named as FreeCAD's transaction, and drawn on the page."""
    run(capsys, "techdraw", "new", "td")
    run(capsys, "techdraw", "view", "td", "Page", "plate", "--direction", "0,0,1")
    steps = {}
    for argv, step in (
            (("cosmetic-vertex", "Page", "View", "5,6"), "Add Cosmetic Vertex"),
            (("cosmetic-line", "Page", "View", "--p0=-5,-4", "--p1=12,9"), "Create Cosmetic Line"),
            (("cosmetic-circle", "Page", "View", "--center", "3,4", "--radius", "2.5"), "Create Cosmetic Circle"),
            (("cosmetic-circle", "Page", "View", "--center", "1,2", "--radius", "3", "--arc", "10,100"), "Create Cosmetic Circle"),
            (("midpoints", "Page", "View", "Edge2"), "Add midpoint vertices"),
            (("quadrants", "Page", "View", "Edge5"), "Add Quadrant vertices"),
            (("centerline", "Page", "View", "Edge0", "Edge4", "--mode", "Vertical"), "Create Centerline"),
            (("centerline", "Page", "View", "Vertex3", "Vertex8", "--mode", "Horizontal", "--extend", "2"), "Create Centerline")):
        code, data = run(capsys, "techdraw", *argv[:1], "td", *argv[1:])
        assert code == cli.OK and data["step"] == step, (argv, data)
        steps[argv[0]] = data
    v = E.objects_of(page_src(proj))[2]
    assert [c["point"][:2] for c in v.source_value("cosmetic_vertexes")][0] == [5.0, 6.0]
    assert len(v.cosmetic_vertexes) == 5 and len(v.cosmetic_edges) == 3 and len(v.center_lines) == 2
    assert [c["geom"] for c in v.source_value("cosmetic_edges")] == ["line", "circle", "arc"]
    cl = v.source_value("center_lines")
    assert (cl[0]["type"], cl[0]["edges"], cl[0]["mode"]) == ("Edge", ["Edge0", "Edge4"], "Vertical")
    assert (cl[1]["type"], cl[1]["vertexes"], cl[1]["extend"]) == ("Vertex", ["Vertex3", "Vertex8"], 2.0)
    assert "cosmetic_vertexes=[" in page_src(proj) and "center_lines=[" in page_src(proj)
    # the geometry: FreeCAD numbers the cosmetic edges after the HLR ones, the centre lines after those
    res = E.recomputed(proj, "Page", svg=True)["result"]["views"]["View"]
    assert [e["cls"] for e in res["edges"]][6:] == ["cosmetic"] * 3 + ["centerline"] * 2
    assert [bool(x.get("tag")) for x in res["vertices"]][9:] == [True] * 5
    assert 'data-sub="Edge9"' in E.recomputed(proj, "Page", svg=True)["svg"]
    # the eraser takes the circle (Edge7), a centre line (Edge9) and a vertex (Vertex9) away
    code, data = run(capsys, "techdraw", "erase", "td", "Page", "View", "Edge7", "Edge9", "Vertex9", "Edge0")
    assert code == cli.OK and data["step"] == "Remove Cosmetic Object"
    v = E.objects_of(page_src(proj))[2]
    assert (len(v.cosmetic_vertexes), len(v.cosmetic_edges), len(v.center_lines)) == (4, 2, 1)
    code, _ = run(capsys, "undo", "td")
    assert code == cli.OK
    assert len(E.objects_of(page_src(proj))[2].cosmetic_edges) == 3
    # a cosmetic line changed, as TaskCosmeticLine's edit does
    code, data = run(capsys, "techdraw", "cosmetic-line", "td", "Page", "View", "--edge", "Edge6", "--p0", "0,0", "--p1", "1,1")
    assert code == cli.OK and data["step"] == "Update Cosmetic Line"
    assert E.objects_of(page_src(proj))[2].source_value("cosmetic_edges")[0]["end"] == [1.0, 1.0, 0.0]
    # a wrong selection is refused, nothing is written
    before = page_src(proj)
    for argv in (("cosmetic-line", "Page", "View", "--edge", "Edge0", "--p0", "0,0", "--p1", "1,1"),
                 ("centerline", "Page", "View", "Edge0", "--mode", "Vertical"),
                 ("cosmetic-circle", "Page", "View", "--center", "1,1", "--radius", "0")):
        code, _ = run(capsys, "techdraw", argv[0], "td", *argv[1:])
        assert code == cli.USAGE and page_src(proj) == before, argv


def test_a_wrong_selection_is_refused_and_nothing_is_written(proj, capsys):
    run(capsys, "techdraw", "new", "td")
    run(capsys, "techdraw", "view", "td", "Page", "plate", "--direction", "0,0,1")
    before = page_src(proj)
    code, _ = run(capsys, "techdraw", "dimension", "td", "Page", "Radius", "View:Edge2", "View:Edge3")
    assert code == cli.USAGE and page_src(proj) == before


def test_export_writes_svg_dxf_and_pdf(proj, capsys):
    run(capsys, "techdraw", "new", "td", "--template", "ISO/A3_Landscape_TD.svg")
    run(capsys, "techdraw", "view", "td", "Page", "plate")
    run(capsys, "techdraw", "annotation", "td", "Page", "NOTE 1", "--at", "50,50")
    code, data = run(capsys, "techdraw", "export", "td", "Page")
    assert code == cli.OK
    out = proj / "out" / "techdraw"
    svg, dxf, pdf = (out / "Page.svg").read_text(), (out / "Page.dxf").read_text(), (out / "Page.pdf").read_bytes()
    assert 'width="420mm" height="297mm" viewBox="0 0 4200 2970"' in svg and "A3_Landscape_TD.svg" in svg
    assert "\nView\n" in dxf and "NOTE 1" in dxf
    assert pdf.startswith(b"%PDF-1.4") and b"/MediaBox [0 0 1190.551 841.890]" in pdf


def test_pages_are_not_design_inputs(proj, capsys):
    """A page is documentation: verify.DESIGN does not hold techdraw/, so editing a page never makes a verdict stale."""
    from cad_agent import verify
    run(capsys, "techdraw", "new", "td")
    files = [p.relative_to(proj).as_posix() for p in verify.design_files(proj)]
    assert not any(f.startswith("techdraw/") for f in files)


def test_the_object_classes_round_trip_through_their_dicts():
    for cls in T.CLASSES.values():
        args = {"DrawPage": ("Page", "Template")}.get(cls.kind, (cls.kind,))
        o = cls(*args)
        again = T.from_dict(json.loads(json.dumps(T.as_dict(o))))
        assert T.as_dict(again) == T.as_dict(o), cls.kind


def test_every_techdraw_help_runs(capsys):
    """argparse %-formats help strings: a bare % in one (format_spec='%.1f') made `cad techdraw --help` exit 4."""
    import argparse
    parser = cli.build_parser()
    top = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices["techdraw"]
    names = next(a for a in top._actions if isinstance(a, argparse._SubParsersAction)).choices
    assert len(names) > 5
    for argv in (["techdraw", "--help"], *(["techdraw", n, "--help"] for n in names)):
        assert cli.main(argv) == 0, argv
    capsys.readouterr()
