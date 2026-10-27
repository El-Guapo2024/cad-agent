"""Spreadsheets in a project (docs/EDITING_PLAN.md, "Spreadsheets in a project"): the sheet file written and read back,
the edits (spreadsheet_edit.apply), a part's PARAMS bound to a cell through EXPRESSIONS and the Pad that follows it,
the binding's refusals, CSV, and SheetModel's display strings."""
import pytest

from cad_agent import params as P
from cad_agent import spreadsheet_edit as E
from cad_agent import state
from cad_agent.spreadsheet_doc import Document

PART = '''from cad_agent.feature import Body, Constraint, LineSegment, Pad, Sketch

PARAMS = {"thick": 5.0}
EXPRESSIONS = {"thick": "Spreadsheet.thick"}

FEATURES = [
    Sketch("Sketch", support="XY",
           geometry=[LineSegment((0.0, 0.0), (40.0, 0.0)), LineSegment((40.0, 0.0), (40.0, 20.0)),
                     LineSegment((40.0, 20.0), (0.0, 20.0)), LineSegment((0.0, 20.0), (0.0, 0.0))],
           constraints=[]),
    Pad("Pad", "Sketch", length="thick"),
]


def build(**p):
    return Body(FEATURES, p)
'''


@pytest.fixture
def project(tmp_path):
    pdir = tmp_path / "demo"
    (pdir / "parts").mkdir(parents=True)
    E.apply(pdir, "Spreadsheet", [{"op": "new"}, {"op": "set", "args": ["A1", "'Thickness"]},
                                  {"op": "set", "args": ["B1", "7.5 mm"]}, {"op": "setAlias", "args": ["B1", "thick"]}])
    (pdir / "parts" / "plate.py").write_text(PART)
    return pdir


def test_the_sheet_file_holds_what_freecad_saves(project):
    src = (project / "spreadsheet" / "Spreadsheet.py").read_text()
    assert 'Spreadsheet.Sheet("Spreadsheet"),' in src
    assert 'Spreadsheet.Cell("A1", "\'Thickness"),' in src
    assert 'Spreadsheet.Cell("B1", "=7.5 mm", alias="thick"),' in src
    doc = E.read(project, "Spreadsheet")
    b1 = doc["sheet"]["cells"]["B1"]
    assert b1["value"] == {"kind": "quantity", "v": 7.5, "dims": [1, 0, 0, 0, 0, 0, 0, 0], "s": "7.5 mm"}
    assert b1["view"]["display"] == "7.50 mm" and b1["view"]["bg"] == "#bac8ff" and b1["view"]["tooltip"] == "thick"


def test_a_pad_follows_the_cell(project):
    mod = state._load_module(project / "parts" / "plate.py")
    assert mod.PARAMS["thick"] == 7.5
    assert mod.build(**mod.PARAMS).volume == pytest.approx(40 * 20 * 7.5)
    E.apply(project, "Spreadsheet", [{"op": "set", "args": ["B1", "=2 mm * 3"]}])
    mod = state._load_module(project / "parts" / "plate.py")
    assert mod.PARAMS["thick"] == 6.0
    assert mod.build(**mod.PARAMS).volume == pytest.approx(40 * 20 * 6.0)


def test_a_bound_parameter_is_read_only(project):
    with pytest.raises(P.ParamError, match="thick is bound to Spreadsheet.thick"):
        P.write(project / "parts" / "plate.py", {"thick": 9.0})


def test_untouched_entries_keep_their_text(project):
    path = project / "spreadsheet" / "Spreadsheet.py"
    path.write_text(path.read_text().replace('"\'Thickness"),', '"\'Thickness"),   # a label'))
    E.apply(project, "Spreadsheet", [{"op": "setStyle", "args": ["B1", "bold", "add"]}])
    src = path.read_text()
    assert "# a label" in src and 'Spreadsheet.Cell("B1", "=7.5 mm", style="bold", alias="thick"),' in src


def test_bind_and_its_cycle(project):
    E.apply(project, "Spreadsheet", [{"op": "set", "args": ["C1", "=plate.thick * 2"]}])
    doc = E.read(project, "Spreadsheet")
    assert doc["sheet"]["cells"]["C1"]["value"]["s"] == "15.0 mm"
    with pytest.raises(E.SpreadsheetEditError, match=r"cyclic reference to demo#Spreadsheet.C1"):
        E.apply(project, "Spreadsheet", [{"op": "bind", "part": "plate", "param": "thick", "expression": "Spreadsheet.C1"}])
    # validateExpression refuses any reference to an object that reads the part, as FreeCAD does
    with pytest.raises(E.SpreadsheetEditError, match=r"cyclic reference to demo#Spreadsheet.B1"):
        E.apply(project, "Spreadsheet", [{"op": "bind", "part": "plate", "param": "thick", "expression": "Spreadsheet.B1"}])
    E.apply(project, "Spreadsheet", [{"op": "clear", "args": ["C1"]}])
    out = E.apply(project, "Spreadsheet", [{"op": "bind", "part": "plate", "param": "thick",
                                            "expression": "<<Spreadsheet>>.B1 + 1 mm"}])
    assert "parts/plate.py" in out["written"]
    assert 'EXPRESSIONS = {"thick": "<<Spreadsheet>>.B1 + 1 mm"}' in (project / "parts" / "plate.py").read_text()
    assert state._load_module(project / "parts" / "plate.py").PARAMS["thick"] == 8.5


def test_csv_round_trip(project):
    doc = Document.of_project(project)
    doc.recompute()
    text = doc.objects["Spreadsheet"].export_text()
    assert text == "Thickness\t7.5\n"
    E.apply(project, "Spreadsheet", [{"op": "import", "text": "a\t1\n\"b\tc\"\t=B1*2\n"}])
    cells = E.read(project, "Spreadsheet")["sheet"]["cells"]
    assert cells["A2"]["content"] == "'b\tc" and cells["B2"]["value"]["v"] == 2


def test_rows_inserted_rewrite_other_sheets(project):
    E.apply(project, "Other", [{"op": "new"}, {"op": "set", "args": ["A1", "=Spreadsheet.B1 * 2"]}])
    E.apply(project, "Spreadsheet", [{"op": "insertRows", "args": ["1", 2]}])
    other = E.read(project, "Other")["sheet"]["cells"]["A1"]
    assert other["content"] == "=Spreadsheet.B3 * 2" and other["value"]["s"] == "15.0 mm"
