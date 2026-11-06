"""Path and Point Link Arrays (cad_agent/assembly_array.py): (type, properties, the path's or points' shape), each made in
FreeCAD 26.3 by make_path.py with the shape as a Part::Feature and recorded in freecad_path.json.

A shape is ("polygon", points), ("circle", radius), ("arc", radius, degrees), ("bspline", points) or ("box", l, w, h);
"Path" is [sub-elements] of it (empty: its first wire, else its edges).
"""
L = ("polygon", [(0, 0, 0), (30, 0, 0), (30, 20, 0)])
SQ = ("polygon", [(0, 0, 0), (20, 0, 0), (20, 20, 0), (0, 20, 0), (0, 0, 0)])
CASES = {
    "path_defaults": ("Part::LinkArrayPath", {"Path": []}, L),
    "path_count_7": ("Part::LinkArrayPath", {"Path": [], "Count": 7}, L),
    "path_one_edge": ("Part::LinkArrayPath", {"Path": ["Edge2"], "Count": 3}, L),
    "path_edges_out_of_order": ("Part::LinkArrayPath", {"Path": ["Edge2", "Edge1"], "Count": 5}, L),
    "path_closed": ("Part::LinkArrayPath", {"Path": [], "Count": 4}, SQ),
    "path_spacing": ("Part::LinkArrayPath", {"Path": [], "SpacingMode": "Fixed spacing", "Spacing": 12.0}, L),
    "path_count_and_spacing": ("Part::LinkArrayPath", {"Path": [], "SpacingMode": "Fixed count and spacing",
                                                       "Spacing": 7.0, "Count": 3}, L),
    "path_offsets": ("Part::LinkArrayPath", {"Path": [], "Count": 4, "StartOffset": 5.0, "EndOffset": 10.0}, L),
    "path_reversed": ("Part::LinkArrayPath", {"Path": [], "Count": 4, "ReversePath": True}, L),
    "path_aligned": ("Part::LinkArrayPath", {"Path": [], "Count": 5, "Align": True}, L),
    "path_circle_aligned": ("Part::LinkArrayPath", {"Path": [], "Count": 6, "Align": True}, ("circle", 10.0)),
    "path_arc_vertical": ("Part::LinkArrayPath", {"Path": [], "Count": 4, "Align": True,
                                                  "VerticalVector": (0, 1, 0)}, ("arc", 15.0, 120.0)),
    "path_bspline": ("Part::LinkArrayPath", {"Path": [], "Count": 5, "Align": True},
                     ("bspline", [(0, 0, 0), (10, 8, 0), (20, -4, 3), (30, 0, 0)])),
    "point_polygon": ("Part::LinkArrayPoint", {}, ("polygon", [(0, 0, 0), (10, 0, 0), (10, 5, 2), (0, 0, 0)])),
    "point_box": ("Part::LinkArrayPoint", {}, ("box", 4, 3, 2)),
}
