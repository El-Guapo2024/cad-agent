"""The link array cases: a Part::LinkArrayLinear or Part::LinkArrayPolar on a part, its pattern properties (FreeCAD's
names; an axis or direction is a role of the document's Origin, "X_Axis"), and make.py records each element's
Placement (Base and Rotation.Q) as FreeCAD 26.3 computes it; tests/test_link_array.py holds cad_agent/assembly_array.py
to them."""

CASES = {
    "linear_default": ("Part::LinkArrayLinear", {}),
    "linear_grid": ("Part::LinkArrayLinear", {"Occurrences": 3, "Length": 40, "Occurrences2": 2, "Length2": 15}),
    "linear_spacing": ("Part::LinkArrayLinear", {"Mode": "Spacing", "Offset": 12.5, "Occurrences": 4}),
    "linear_spacings": ("Part::LinkArrayLinear", {"Mode": "Spacing", "Offset": 10, "Occurrences": 4,
                                                  "Spacings": [5, -1, 20]}),
    "linear_reversed_z": ("Part::LinkArrayLinear", {"Direction": "Z_Axis", "Reversed": True, "Occurrences": 3,
                                                    "Length": 30}),
    "linear_y_and_z": ("Part::LinkArrayLinear", {"Direction": "Y_Axis", "Direction2": "Z_Axis", "Occurrences": 2,
                                                 "Occurrences2": 3, "Mode2": "Spacing", "Offset2": 7}),
    "polar_default": ("Part::LinkArrayPolar", {}),
    "polar_half": ("Part::LinkArrayPolar", {"Angle": 180, "Occurrences": 4}),
    "polar_spacing_x": ("Part::LinkArrayPolar", {"Axis": "X_Axis", "Mode": "Spacing", "Offset": 30, "Occurrences": 5}),
    "polar_reversed_y": ("Part::LinkArrayPolar", {"Axis": "Y_Axis", "Reversed": True, "Occurrences": 6}),
}
