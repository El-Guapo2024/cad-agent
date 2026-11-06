"""cad_agent/assembly_bom.py held to FreeCAD 26.3's Bill of Materials (tests/golden/assembly_bom, make.py): the cells
after each recompute, every case. File Name is left out: FreeCAD's is the unsaved document's file, ""."""
import importlib.util
import json
from pathlib import Path

import pytest

from cad_agent import assembly_bom as B
from cad_agent.spreadsheet import CellAddress, string_to_address
from cad_agent.spreadsheet_doc import Document

HERE = Path(__file__).parent / "golden" / "assembly_bom"
_spec = importlib.util.spec_from_file_location("bom_cases", HERE / "cases.py")   # each golden folder has its cases.py
_cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cases)
CASES, PARTS = _cases.CASES, _cases.PARTS

FC = json.loads((HERE / "freecad.json").read_text())


def nodes(comps, subs):
    out = [B.Node("other", "Joints", "Joints")]           # the JointGroup, which the BOM skips
    for _name, target in comps:
        if target.startswith("@"):
            s = target[1:]
            out.append(B.Node("assembly", target, s, props={"Label": s}, children=nodes(subs[s], subs)))
        else:
            out.append(B.Node("part", target, PARTS[target], props={"Label": PARTS[target]}))
    return out


def cells(sheet):
    out = {}
    for a in sheet.cells.used_cells():
        t = sheet.cells.get(a).string_content() or ""
        if t:
            out[a.to_string()] = t
    return out


def without_file_name(c, header):
    col = next((k[0] for k, v in header.items() if v == "'File Name" and k[1:] == "1"), None)
    return {k: v for k, v in c.items() if col is None or k[0] != col or k == f"{col}1"}


@pytest.mark.parametrize("name", sorted(CASES))
def test_bom(name):
    case = CASES[name]
    sheet = Document("Unnamed").add_sheet("Bill_of_Materials", "Bill of Materials")
    comps = list(case["components"])
    props = {"detail_sub_assemblies": True, "detail_parts": True, "only_parts": False}
    names = {"detailSubAssemblies": "detail_sub_assemblies", "detailParts": "detail_parts", "onlyParts": "only_parts"}
    columns = case.get("columns", B.COLUMN_NAMES)
    ours = []
    for st in [{}] + case.get("steps", []):
        comps += st.get("add", [])
        for a, v in st.get("set", {}).items():
            sheet.set_cell(string_to_address(a), v)
        for k, v in st.get("props", {}).items():
            props[names[k]] = v
        B.generate(sheet, nodes(comps, case.get("subs", {})), columns, **props)
        sheet.execute()
        ours.append(cells(sheet))
    want = FC[name]
    assert len(ours) == len(want)
    for i, (o, w) in enumerate(zip(ours, want)):
        assert without_file_name(o, o) == without_file_name(w, w), f"after step {i}"


# ── the BOM in a project: `cad sheet bom`, a spreadsheet the Assembly fills ─────────────────────────────────

def test_a_bom_of_the_project_is_made_filled_and_keeps_what_is_typed(tmp_path, monkeypatch, capsys):
    from cad_agent import state as st
    from test_cli import run
    monkeypatch.setattr(st, "ROOT", tmp_path)
    monkeypatch.delenv("CAD_PROJECTS", raising=False)
    d = tmp_path / "asm"
    (d / "parts").mkdir(parents=True)
    for p in ("plate", "pin"):
        (d / "parts" / f"{p}.py").write_text(f'"""{p}"""\nPARAMS = {{}}\n\n\ndef build(**p):\n    return None\n')
    (d / "assembly.py").write_text(
        'from cad_agent import assembly_wb as Assembly\n\nASSEMBLY = [\n'
        '    Assembly.Link("plate", "plate"),\n    Assembly.Link("pin", "pin"),\n    Assembly.Link("pin001", "pin"),\n'
        '    Assembly.GroundedJoint("GroundedJoint", "plate"),\n]\n')
    code, data = run(capsys, "sheet", "bom", "asm")
    assert code == 0 and data["step"] == "Create Bill Of Materials" and data["sheet"] == "Bill_of_Materials"
    src = (d / "spreadsheet" / "Bill_of_Materials.py").read_text()
    assert 'Spreadsheet.Bom("Bill_of_Materials", label="Bill of Materials", columns_names=[' in src
    cells = data["doc"]["sheet"]["cells"]
    assert [cells[a]["content"] for a in ("A2", "B2", "D2", "E2", "A3", "B3", "D3", "E3")] == \
        ["'1", "'plate", "'parts/plate.py", "1", "'2", "'pin", "'parts/pin.py", "2"]
    run(capsys, "sheet", "set", "asm", "Bill_of_Materials", "C3", "'steel pin")
    code, data = run(capsys, "sheet", "bom", "asm", "--sheet", "Bill_of_Materials", "--no-detail-sub-assemblies")
    assert code == 0 and data["step"] == "Edit Bill Of Materials"
    assert data["doc"]["sheet"]["cells"]["C3"]["content"] == "'steel pin"
    assert "detail_sub_assemblies=False" in (d / "spreadsheet" / "Bill_of_Materials.py").read_text()
