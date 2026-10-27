"""The spreadsheet cases tests/golden/spreadsheet/make.py runs through FreeCAD and tests/test_spreadsheet_golden.py through
cad_agent/spreadsheet_sheet.py. Each case is a list of steps on one fresh document:

    ("@sheet", Name[, Label])          Spreadsheet_CreateSheet: doc.addObject("Spreadsheet::Sheet", Name)
    (Name, method, *args)              a Spreadsheet::Sheet Python method (SheetPyImp.cpp), as the GUI's commands call them
    ("@recompute",)                    App.ActiveDocument.recompute(): the state is recorded after each
    ("@restore",)                      the document saved, closed and opened again (Sheet::onDocumentRestored), recorded
    ("@part", name, params, expressions)   a part as a Body: a 40 x 20 rectangle padded by `length`, PARAMS as the
                                       spreadsheet "Params_<name>" and the Pad's Length bound to PARAMS["length"] as
                                       EXPRESSIONS (or the literal) say; recorded: the Pad's Length and the volume
    ("@export", Name)                  Sheet.exportFile (tab, ", \\), the file's text recorded
    ("@import", Name, text)            Sheet.importFile of that text
"""

S = "Spreadsheet"

CASES = {
    # Cell::setContent's reading of what is typed
    "content_kinds": [
        ("@sheet", S),
        (S, "set", "A1", "5"), (S, "set", "A2", "-3"), (S, "set", "A3", "+7"), (S, "set", "A4", " 5"),
        (S, "set", "A5", "5 "), (S, "set", "A6", "2.5"), (S, "set", "A7", ".5"), (S, "set", "A8", "5."),
        (S, "set", "A9", "1e3"), (S, "set", "A10", "12,5"), (S, "set", "A11", "0x10"), (S, "set", "A12", "1e999"),
        (S, "set", "A13", "1e-999"), (S, "set", "A14", "3 mm"), (S, "set", "A15", "1/2"), (S, "set", "A16", "1m/2s"),
        (S, "set", "A17", "1/m"), (S, "set", "A18", "2*3"), (S, "set", "A19", "-3 mm"), (S, "set", "A20", "hello"),
        (S, "set", "B1", "'hello"), (S, "set", "B2", "'"), (S, "set", "B3", "''x"), (S, "set", "B4", "=2.5"),
        (S, "set", "B5", "=A1*2"), (S, "set", "B6", "=A1 mm"), (S, "set", "B7", "=foo("), (S, "set", "B8", "=<<abc>>"),
        (S, "set", "B9", "=True"), (S, "set", "B10", "=None"), (S, "set", "B11", "=list(1;2)"),
        (S, "set", "B12", "=vector(1;2;3)"), (S, "set", "B13", "=4/2"), (S, "set", "B14", "=pi"), (S, "set", "B15", "inf"),
        (S, "set", "B16", "12 mm 3"), (S, "set", "B17", "3 in"), (S, "set", "B18", "=1 m * 1 m"),
        (S, "set", "B19", "=(1+2)*3"), (S, "set", "B20", "=2^0.5"), (S, "set", "C1", "=Spreadsheet.A1"),
        (S, "set", "C2", "=-A1"), (S, "set", "C3", "=A1 > 2 ? 1 mm : 2 mm"), (S, "set", "C4", "=str(A1)"),
        (S, "set", "C5", "=<<x>> + <<y>>"), (S, "set", "C6", "=A1 / 0"), (S, "set", "C7", "=7 % 3"),
        (S, "set", "C8", "=-0.0"), (S, "set", "C9", "1 2"), (S, "set", "C10", "=$A$1 + $A1 + A$1"),
        ("@recompute",),
        ("@restore",),
    ],
    # references, ranges and the aggregate functions
    "aggregates": [
        ("@sheet", S),
        (S, "set", "A1", "1"), (S, "set", "A2", "2.5"), (S, "set", "A3", "4"), (S, "set", "A4", "'text"),
        (S, "set", "B1", "1 mm"), (S, "set", "B2", "2 mm"), (S, "set", "B3", "4 mm"), (S, "set", "B5", "1 s"),
        (S, "set", "C1", "=sum(A1:A3)"), (S, "set", "C2", "=average(A1:A3)"), (S, "set", "C3", "=min(A1:A3)"),
        (S, "set", "C4", "=max(A1:A3)"), (S, "set", "C5", "=count(A1:A3)"), (S, "set", "C6", "=stddev(A1:A3)"),
        (S, "set", "C7", "=sum(B1:B3)"), (S, "set", "C8", "=average(B1:B3)"), (S, "set", "C9", "=stddev(B1:B3)"),
        (S, "set", "C10", "=sum(A1:A4)"), (S, "set", "C11", "=sum(B1:B5)"), (S, "set", "C12", "=sum(A3:A1)"),
        (S, "set", "C13", "=sum(A1:B3)"), (S, "set", "C14", "=count(A1:A9)"), (S, "set", "C15", "=sum(A1:A3; 10)"),
        (S, "set", "C16", "=list(A1:B2)"), (S, "set", "C17", "=stddev(A1:A1)"), (S, "set", "C18", "=max(B1:B3) * 2"),
        (S, "set", "C19", "=min(A1; B1)"), (S, "set", "C20", "=sum(A1:A3) / count(A1:A3)"),
        (S, "set", "D1", "=and(A1:A3)"), (S, "set", "D2", "=or(A1; 0)"), (S, "set", "D3", "=A1 + B1"),
        (S, "set", "D4", "=A4 + 1"), (S, "set", "D5", "=E9"), (S, "set", "D6", "=A2 * B2"),
        (S, "set", "D7", "=sum(Q1:Q4)"), (S, "set", "D8", "=average(Q1:Q4)"),
        ("@recompute",),
        ("@restore",),
    ],
    # aliases: defined before and after the cells that use them, their errors, renaming one
    "aliases": [
        ("@sheet", S),
        (S, "set", "A1", "7.5 mm"), (S, "setAlias", "A1", "thick"), (S, "set", "B1", "=thick * 2"),
        (S, "set", "B2", "=later + 1"), (S, "set", "A2", "3"), (S, "setAlias", "A2", "later"),
        (S, "set", "B3", "=Spreadsheet.thick"), (S, "set", "B4", "=sum(thick:A2)"),
        ("@recompute",),
        ("@recompute",),
        (S, "setAlias", "A1", "wall"),
        ("@recompute",),
        (S, "setAlias", "A3", "wall"), (S, "setAlias", "A3", "pi"), (S, "setAlias", "A3", "mm"),
        (S, "setAlias", "A3", "B7"), (S, "setAlias", "A3", "1x"), (S, "setAlias", "A3", "_x"),
        (S, "setAlias", "A3", "Label"), (S, "setAlias", "A3", "ok_1"), (S, "setAlias", "A3", ""),
        (S, "setAlias", "A3", "Spreadsheet"), (S, "setAlias", "A3", "in"), (S, "setAlias", "A3", "e"),
        ("@recompute",),
        ("@restore",),
    ],
    # dependency errors inside a sheet: a cycle fails the whole sheet
    "cycles": [
        ("@sheet", S),
        (S, "set", "A1", "=A2 + 1"), (S, "set", "A2", "=A1"), (S, "set", "A3", "=A3"), (S, "set", "B1", "5"),
        (S, "set", "B2", "=B1 * 2"),
        ("@recompute",),
        (S, "set", "A2", "4"), (S, "set", "A3", "1"),
        ("@recompute",),
    ],
    "cycle_long": [
        ("@sheet", S),
        (S, "set", "A1", "=A4"), (S, "set", "A2", "=A1"), (S, "set", "A3", "=A2"), (S, "set", "A4", "=A3"),
        (S, "set", "C1", "=D1"), (S, "set", "D1", "=C1"), (S, "set", "E1", "2"),
        ("@recompute",),
    ],
    # recompute order: what the topological sort decides, and an alias the order cannot see
    "order": [
        ("@sheet", S),
        (S, "set", "C3", "=B2 + A1"), (S, "set", "B2", "=A1 * 2"), (S, "set", "A1", "3"), (S, "set", "D4", "=C3 + B2"),
        (S, "set", "A5", "=total"), (S, "set", "B5", "10"), (S, "setAlias", "B5", "total"),
        ("@recompute",),
        (S, "set", "A1", "4"),
        ("@recompute",),
        ("@recompute",),
    ],
    # evaluation errors: their messages and the "ERR:" property
    "errors": [
        ("@sheet", S),
        (S, "set", "A1", "=1/0"), (S, "set", "A2", "=nothing"), (S, "set", "A3", "=1 mm + 1 s"),
        (S, "set", "A4", "=sqrt(-1 mm^2)"), (S, "set", "A5", "=<<a>> * <<b>>"), (S, "set", "A6", "=A1 + 1"),
        (S, "set", "A7", "=sin(1 mm)"), (S, "set", "A8", "=pow(2 mm; 0.5)"), (S, "set", "A9", "=Spreadsheet002.A1"),
        (S, "set", "A10", "=Label"), (S, "set", "A11", "=Label2"), (S, "set", "A12", "=A1.Value"),
        ("@recompute",),
        ("@restore",),
    ],
    # the look: styles, alignment, colours, display units, merged cells, sizes
    "look": [
        ("@sheet", S),
        (S, "set", "A1", "1.234"), (S, "set", "A2", "1 m"), (S, "set", "A3", "12 mm"), (S, "set", "A4", "'abc"),
        (S, "setStyle", "A1:A2", "bold", "add"), (S, "setStyle", "A2", "italic", "add"),
        (S, "setStyle", "A1", "bold", "remove"), (S, "setStyle", "A3", "underline|bold"),
        (S, "setStyle", "A4", "italic", "invert"), (S, "setStyle", "A4", "italic|bold", "invert"),
        (S, "setAlignment", "A1", "right", "keep"), (S, "setAlignment", "A2", "center|top"),
        (S, "setAlignment", "A3", "bottom", "keep"), (S, "setAlignment", "A4", "left|vcenter|himplied"),
        (S, "setForeground", "A1", (1, 0, 0)), (S, "setBackground", "A1:A2", (0.5, 0.25, 1.0, 1.0)),
        (S, "setForeground", "A3", (0, 0.5, 0)), (S, "clearForeground", "A3"),
        (S, "setDisplayUnit", "A2", "cm"), (S, "setDisplayUnit", "A1", "mm"), (S, "setDisplayUnit", "A3", "s"),
        (S, "setDisplayUnit", "A4", "bogus"),
        (S, "set", "B1", "x"), (S, "set", "C2", "y"), (S, "mergeCells", "B1:C2"), (S, "set", "D1", "=B1"),
        (S, "set", "E1", "e"), (S, "mergeCells", "E1:F1"), (S, "splitCell", "F1"),
        (S, "setColumnWidth", "A", 140), (S, "setColumnWidth", "C", 60), (S, "setRowHeight", "2", 45),
        ("@recompute",),
        ("@restore",),
    ],
    # rows and columns inserted and removed: references, ranges, aliases, merged cells and sizes follow
    "rows_columns": [
        ("@sheet", S),
        (S, "set", "A1", "1"), (S, "set", "A2", "2"), (S, "set", "A3", "3"), (S, "set", "B1", "=A3 * 10"),
        (S, "set", "B2", "=sum(A1:A3)"), (S, "set", "B3", "=$A$2"), (S, "setAlias", "A3", "three"),
        (S, "set", "B4", "=three + 1"), (S, "set", "C1", "c"), (S, "mergeCells", "C1:D2"),
        (S, "setRowHeight", "3", 50), (S, "setColumnWidth", "B", 120), (S, "setColumnWidth", "D", 70),
        ("@recompute",),
        (S, "insertRows", "2", 2),
        ("@recompute",),
        (S, "insertColumns", "A", 1),
        ("@recompute",),
        (S, "removeRows", "3", 1),
        ("@recompute",),
        (S, "removeColumns", "A", 1),
        ("@recompute",),
        ("@restore",),
    ],
    # clearing cells, merges hiding cells, used ranges
    "clear": [
        ("@sheet", S),
        (S, "set", "A1", "1"), (S, "set", "A2", "=A1 + 1"), (S, "setAlias", "A1", "one"), (S, "set", "B1", "b"),
        (S, "setStyle", "B2", "bold"),
        ("@recompute",),
        (S, "clear", "A1"),
        ("@recompute",),
        (S, "set", "A1", "5"),
        ("@recompute",),
        (S, "clear", "A1:B2"),
        ("@recompute",),
    ],
    # other objects: a second sheet by Name, by Label, <<Label>>; a cycle between two sheets
    "two_sheets": [
        ("@sheet", S, "Params"),
        ("@sheet", "Spreadsheet001"),
        (S, "set", "A1", "10 mm"), (S, "setAlias", "A1", "len"),
        ("Spreadsheet001", "set", "A1", "=Spreadsheet.len * 2"), ("Spreadsheet001", "set", "A2", "=Params.A1"),
        ("Spreadsheet001", "set", "A3", "=<<Params>>.len + 1 mm"), ("Spreadsheet001", "set", "A4", "=Params.nothing"),
        ("Spreadsheet001", "set", "A5", "=Nope.A1"), ("Spreadsheet001", "set", "A6", "=<<Nope>>.A1"),
        (S, "set", "A2", "=Params.A1"),
        ("@recompute",),
        (S, "set", "A1", "12 mm"),
        ("@recompute",),
        ("@restore",),
    ],
    "sheet_cycle": [
        ("@sheet", S),
        ("@sheet", "Spreadsheet001"),
        (S, "set", "A1", "=Spreadsheet001.A1 + 1"), ("Spreadsheet001", "set", "A1", "=Spreadsheet.A1"),
        (S, "set", "B1", "3"),
        ("@recompute",),
    ],
    # a Pad's Length driven by a cell through the part's parameter
    "pad": [
        ("@sheet", S),
        (S, "set", "A1", "7.5 mm"), (S, "setAlias", "A1", "thick"),
        ("@part", "plate", {"length": 5.0}, {"length": "Spreadsheet.thick"}),
        ("@recompute",),
        (S, "set", "A1", "=3 mm + 1 mm"),
        ("@recompute",),
        (S, "set", "A1", "=2 cm"),
        ("@recompute",),
        ("@restore",),
    ],
    "pad_expression": [
        ("@sheet", S, "Dims"),
        (S, "set", "A1", "4"), (S, "set", "A2", "=A1 * 1.5 mm"),
        ("@part", "plate", {"length": 5.0}, {"length": "<<Dims>>.A2 + 1 mm"}),
        ("@recompute",),
        (S, "set", "A1", "10"),
        ("@recompute",),
    ],
    "pad_cycle": [
        ("@sheet", S),
        (S, "set", "A1", "2 mm"),
        ("@part", "plate", {"length": 5.0}, {"length": "Spreadsheet.A1 * 3"}),
        ("@recompute",),
        (S, "set", "A2", "=plate.length * 2"),
        ("@recompute",),
        ("@bind", "plate", "length", "Spreadsheet.A2"),
        ("@recompute",),
    ],
    # CSV
    "csv": [
        ("@sheet", S),
        (S, "set", "A1", "'name"), (S, "set", "B1", "'value"), (S, "set", "A2", "'a\tb"), (S, "set", "B2", "1.5"),
        (S, "set", "A3", "'say \"hi\""), (S, "set", "B3", "=2 mm"), (S, "set", "C4", "=1/3"), (S, "set", "B5", "12"),
        ("@recompute",),
        ("@export", S),
        ("@import", S, "x\ty\n1\t=A2*2\n\"q\tr\"\t3 mm\n\n\tlast\n"),
        ("@recompute",),
        ("@export", S),
    ],
}
