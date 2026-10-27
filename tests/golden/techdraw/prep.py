"""Writes breps/<part>.brep (parts.py) and cases.json (cases.py's ops run through cad_agent/techdraw_edit.py), the
inputs make.py hands FreeCAD and tests/test_techdraw_golden.py holds cad_agent to.

    PYTHONPATH=. .venv/bin/python tests/golden/techdraw/prep.py              (from the repository's root)
    PYTHONPATH=. .venv/bin/python tests/golden/techdraw/prep.py --show plate 0,0,1   a view's edges, to pick references

cases.json holds each case's page as the objects the ops made (techdraw.as_dict), with every property resolved, so
FreeCAD is given exactly the values cad_agent's page file would hold.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(f"techdraw_golden_{name}", HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_brep(path):
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    s = TopoDS_Shape()
    BRepTools.Read_s(s, str(path), BRep_Builder())
    return s


def shape_of(part):
    return read_brep(HERE / "breps" / f"{part}.brep")


def write_breps():
    from build123d import export_brep
    parts = _load("parts").PARTS
    for name, fn in parts.items():
        solid = fn()
        export_brep(solid, str(HERE / "breps" / f"{name}.brep"))


def run_case(case):
    from cad_agent import techdraw as T
    from cad_agent import techdraw_edit as E
    s = E.Session(None, "Page", [], None, shape_of)
    s.pdir = Path("golden")
    E.run_ops(s, [{"op": "new_page", "template": case.get("template"), "title": "golden"}] + case["ops"])
    return [T.as_dict(o) for o in s.objs]


def main():
    if "--show" in sys.argv:
        i = sys.argv.index("--show")
        part, d = sys.argv[i + 1], [float(x) for x in sys.argv[i + 2].split(",")]
        from cad_agent import techdraw_view as V
        g = V.project(V.source_compound([shape_of(part)]), d, (1, 0, 0) if abs(d[0]) < 0.9 else (0, 1, 0), 1.0, 0.0,
                      V.Flags(hard_hidden=True))
        for i, e in enumerate(g.edges):
            j = V.edge_json(e)
            print(f"Edge{i}", e.kind, e.cls, e.visible, [round(c, 3) for c in j["start"]], [round(c, 3) for c in j["end"]],
                  round(j.get("radius", 0), 3) or "")
        for i, v in enumerate(g.vertices):
            print(f"Vertex{i}", round(v.x, 3), round(v.y, 3))
        return
    write_breps()
    cases = _load("cases").CASES
    out = {}
    for name, case in cases.items():
        out[name] = {"objects": run_case(case), "template": case.get("template")}
    (HERE / "cases.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"prep: {len(out)} cases, {len(_load('parts').PARTS)} parts")


if __name__ == "__main__":
    main()
