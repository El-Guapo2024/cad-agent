"""The Bill of Materials cases: an Assembly's components (App::Links to parts, AssemblyLinks to other Assemblies), the
BOM's columns and options, and cells typed into it before a recompute. make.py builds each in FreeCAD 26.3 and
records the sheet's cells after each recompute; tests/test_assembly_bom.py holds cad_agent/assembly_bom.py to them."""

PARTS = {"plate": "Plate", "pin": "Pin", "bracket": "Bracket"}

CASES = {
    # Assembly_CreateBom's defaults: the five columns, sub-assemblies detailed
    "flat": {"components": [("Plate", "plate"), ("Pin", "pin"), ("Pin001", "pin"), ("Bracket", "bracket")]},
    # a custom column and Description typed in, kept by the Name of their row; a component added after
    "custom": {"components": [("Plate", "plate"), ("Pin", "pin")],
               "columns": ["Index", "Name", "Description", "Notes", "Quantity"],
               "steps": [{"set": {"C2": "the base", "D3": "steel"}},
                         {"add": [("Pin001", "pin")]},
                         {"add": [("Bracket", "bracket")], "set": {"D5": "printed"}}]},
    # a sub-assembly, detailed and not, and with Only parts
    "sub": {"subs": {"Gantry": [("Bracket", "bracket"), ("Pin", "pin"), ("Pin001", "pin")]},
            "components": [("Plate", "plate"), ("Gantry", "@Gantry"), ("Pin", "pin"), ("Gantry001", "@Gantry")],
            "steps": [{"props": {"detailSubAssemblies": False}}, {"props": {"detailSubAssemblies": True,
                                                                            "onlyParts": True}}]},
    # no Quantity column (every link a row of its own), a property column and one that is not there
    "props": {"components": [("Plate", "plate"), ("Pin", "pin"), ("Pin001", "pin")],
              "columns": ["Name", ".Label", ".Nothing", "Index"]},
}
