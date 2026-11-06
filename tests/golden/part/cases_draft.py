"""Draft's objects in a part file (cad_agent/feature_draft.py): the documents FreeCAD builds, its answers recorded in
freecad_draft.json (make.py draft).

Each object is its draftobjects proxy on a fresh object with the keywords' properties set, as a document read back
holds it; a link to a Part object or a sketch is the shape that object makes.
"""
from cad_agent import feature_draft as Draft
from cad_agent import feature_part as Part

CASES = {}
SQ = [(0, 0, 0), (10, 0, 0), (10, 6, 0), (0, 6, 0)]

CASES["draft_rectangle"] = {"objects": [
    Draft.Rectangle("Rectangle", length=40, height=20),
    Draft.Rectangle("Rounded", length=30, height=10, fillet_radius=2, placement=((0, 30, 0), (0, 0, 0))),
    Draft.Rectangle("Chamfered", length=30, height=10, chamfer_size=3, make_face=False,
                    placement=((0, 50, 5), (30, 0, 0))),
    Draft.Rectangle("Grid", length=30, height=20, rows=2, columns=3, placement=((50, 0, 0), (0, 0, 0)))]}
CASES["draft_wire"] = {"objects": [
    Draft.Wire("Open", points=SQ),
    Draft.Wire("Closed", points=SQ, closed=True, placement=((0, 10, 0), (0, 0, 0))),
    Draft.Wire("Filleted", points=SQ, closed=True, fillet_radius=1.5, placement=((20, 0, 0), (0, 0, 0))),
    Draft.Wire("Subdivided", points=[(0, 0, 0), (10, 0, 0), (10, 10, 5)], subdivisions=2)]}
CASES["draft_circle"] = {"objects": [
    Draft.Circle("Circle", radius=5),
    Draft.Circle("Arc", radius=8, first_angle=30, last_angle=200, placement=((20, 0, 0), (0, 0, 0))),
    Draft.Ellipse("Ellipse", major_radius=10, minor_radius=4, placement=((0, 20, 0), (0, 0, 0))),
    Draft.Polygon("Hexagon", faces_number=6, radius=5, placement=((40, 0, 0), (0, 0, 0))),
    Draft.Polygon("Square", faces_number=4, radius=5, draw_mode="circumscribed", fillet_radius=1,
                  placement=((40, 20, 0), (0, 90, 0)))]}
CASES["draft_curves"] = {"objects": [
    Draft.BSpline("BSpline", points=[(0, 0, 0), (5, 4, 0), (10, 0, 0), (15, 3, 2)]),
    Draft.BSpline("ClosedBSpline", points=[(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], closed=True,
                  placement=((20, 0, 0), (0, 0, 0))),
    Draft.BezCurve("Bezier", points=[(0, 0, 0), (3, 6, 0), (7, 6, 0), (10, 0, 0)]),
    Draft.Point("Point", x=3, y=4, z=5)]}
CASES["draft_arrays"] = {"objects": [
    Draft.Rectangle("Rectangle", length=4, height=2),
    Draft.Array("Ortho", "Rectangle", number_x=3, number_y=2, interval_x=(6, 0, 0), interval_y=(0, 4, 0)),
    Draft.Circle("Circle", radius=1, placement=((10, 0, 0), (0, 0, 0))),
    Draft.Array("Polar", "Circle", array_type="polar", number_polar=6),
    Draft.Array("Circular", "Circle", array_type="circular", radial_distance=4, tangential_distance=3,
                number_circles=2)]}
CASES["draft_array_of_part"] = {"objects": [
    Part.Box("Box", length=4, width=3, height=2),
    Draft.Array("Array", "Box", number_x=2, number_y=3, number_z=2, interval_x=(10, 0, 0),
                interval_y=(0, 8, 0), interval_z=(0, 0, 5)),
    Part.Cylinder("Cylinder", radius=1, height=3, placement=((20, 0, 0), (0, 0, 0))),
    Draft.Array("PolarFused", "Cylinder", array_type="polar", number_polar=4, angle=180, fuse=True)]}
CASES["draft_path_point_arrays"] = {"objects": [
    Draft.Wire("Path", points=[(0, 0, 0), (30, 0, 0), (30, 20, 0)]),
    Draft.Circle("Dot", radius=1),
    Draft.PathArray("PathArray", "Dot", "Path", count=5),
    Draft.Wire("Points", points=[(0, 40, 0), (10, 45, 0), (20, 40, 0)]),
    Draft.PointArray("PointArray", "Dot", "Points")]}
CASES["draft_clone"] = {"objects": [
    Draft.Rectangle("Rectangle", length=6, height=3),
    Draft.Clone("Clone", ["Rectangle"], placement=((10, 0, 0), (0, 0, 0))),
    Draft.Clone("Scaled", ["Rectangle"], scale=(2, 1, 1)),
    Part.Box("Box", length=2, width=2, height=2),
    Draft.Clone("BoxClone", ["Box"], scale=(1, 2, 3), placement=((0, 10, 0), (0, 0, 0)))]}
CASES["draft_params"] = {"params": {"w": 12.0, "n": 4}, "objects": [
    Draft.Rectangle("Rectangle", length="w", height="w / 2"),
    Draft.Array("Array", "Rectangle", number_x="n", interval_x=(15, 0, 0), number_y=1)]}
