"""The Draft cases: each a script of Draft's make_* calls (the Python FreeCAD's Draft commands run), the objects'
properties set after, then one recompute. make.py runs them in freecadcmd 26.3 and records every object's shape
(freecad.json); tests/test_draft_golden.py runs the same scripts on FreeCAD's Draft Python vendored in cad_agent/fcdraft
over the stand-ins and holds the shapes to FreeCAD's. A script's names: App (FreeCAD), Draft, V (App.Vector), P
(App.Placement), R (App.Rotation), doc."""

CASES = {
    "wire": "Draft.make_wire([V(0, 0, 0), V(10, 0, 0), V(10, 5, 0), V(3, 8, 0)])",
    "wire_closed_face": "Draft.make_wire([V(0, 0, 0), V(10, 0, 0), V(10, 5, 0)], closed=True, face=True)",
    "wire_fillet": "w = Draft.make_wire([V(0, 0, 0), V(10, 0, 0), V(10, 8, 0), V(0, 8, 0)], closed=True)\n"
                   "w.FilletRadius = 2",
    "wire_chamfer": "w = Draft.make_wire([V(0, 0, 0), V(10, 0, 0), V(10, 8, 0)])\nw.ChamferSize = 1.5",
    "line": "Draft.make_line(V(0, 0, 0), V(7, 3, 2))",
    "rectangle": "Draft.make_rectangle(20, 10)",
    "rectangle_placed": "Draft.make_rectangle(20, 10, placement=P(V(5, 5, 2), R(V(0, 0, 1), 30)), face=False)",
    "rectangle_rows": "r = Draft.make_rectangle(30, 20)\nr.Rows = 2\nr.Columns = 3",
    "rectangle_fillet": "r = Draft.make_rectangle(30, 20)\nr.FilletRadius = 4",
    "circle": "Draft.make_circle(5)",
    "arc": "Draft.make_circle(8, startangle=30, endangle=200)",
    "arc_3points": "Draft.make_arc_3points([V(0, 0, 0), V(5, 5, 0), V(10, 0, 0)])",
    "ellipse": "Draft.make_ellipse(10, 4)",
    "polygon": "Draft.make_polygon(6, 4)",
    "polygon_circumscribed": "Draft.make_polygon(5, 4, inscribed=False)",
    "bspline": "Draft.make_bspline([V(0, 0, 0), V(4, 6, 0), V(9, -2, 0), V(14, 3, 0)])",
    "bspline_closed": "Draft.make_bspline([V(0, 0, 0), V(4, 6, 0), V(9, -2, 0), V(14, 3, 0)], closed=True)",
    "bezcurve": "Draft.make_bezcurve([V(0, 0, 0), V(3, 7, 0), V(8, 7, 0), V(11, 0, 0)])",
    "point": "Draft.make_point(1, 2, 3)",
    "array_ortho": "r = Draft.make_rectangle(4, 2)\nDraft.make_ortho_array(r, v_x=V(6, 0, 0), v_y=V(0, 4, 0), n_x=3, n_y=2)",
    "array_polar": "c = Draft.make_circle(1, placement=P(V(10, 0, 0), R()))\nDraft.make_polar_array(c, number=6, angle=360)",
    "array_circular": "c = Draft.make_circle(1)\nDraft.make_circular_array(c, r_distance=5, tan_distance=4, number=3, symmetry=1)",
    "array_path": "c = Draft.make_circle(0.5)\np = Draft.make_wire([V(0, 0, 0), V(20, 0, 0), V(20, 10, 0)])\n"
                  "Draft.make_path_array(c, p, count=5)",
    "array_point": "c = Draft.make_circle(0.5)\npts = Draft.make_wire([V(0, 0, 0), V(5, 3, 0), V(9, -1, 0)])\n"
                   "Draft.make_point_array(c, pts)",
    "clone": "r = Draft.make_rectangle(6, 3)\nDraft.make_clone(r, delta=V(10, 0, 0))",
    "clone_scaled": "r = Draft.make_rectangle(6, 3)\nc = Draft.make_clone(r)\nc.Scale = V(2, 1, 1)",
}
