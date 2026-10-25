"""Part workbench documents for Loft, Sweep, Offset, Offset2D, Thickness, ProjectOnSurface and the tapered Extrusion
(cad_agent/feature_part_sweep.py, feature_part_taper.py), each built by FreeCAD (make.py sweep, freecadcmd, into
freecad_sweep.json) and by cad_agent (tests/test_feature_part.py), every object's shape compared.
"""
from cad_agent import feature_part as Part
from cad_agent.feature import ArcOfCircle, Circle, LineSegment, Point, Sketch  # noqa: F401


def rect(x0, y0, x1, y1):
    return [LineSegment((x0, y0), (x1, y0)), LineSegment((x1, y0), (x1, y1)),
            LineSegment((x1, y1), (x0, y1)), LineSegment((x0, y1), (x0, y0))]


def sk(name, geometry, support="XY", **kw):
    return Sketch(name, support=support, geometry=geometry, **kw)


CASES = {}
KNOWN: dict = {}

# ── tapered extrusions (Extrusion::extrudeShape's tapered branch, ExtrusionHelper::makeElementDraft) ──
SQUARE = sk("Sketch", rect(0, 0, 20, 20))
HOLES = sk("Sketch", rect(0, 0, 30, 20) + [Circle((10, 10), 4), Circle((22, 10), 3)])
POLYHOLE = sk("Sketch", rect(0, 0, 30, 30) + rect(10, 10, 20, 20))
CASES["sweep_taper_pos"] = {"objects": [SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd=8, solid=True,
                                                               taper_angle=10)]}
CASES["sweep_taper_neg"] = {"objects": [SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd=8, solid=True,
                                                               taper_angle=-12)]}
CASES["sweep_taper_rev"] = {"objects": [SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd=8, length_rev=4,
                                                               solid=True, taper_angle=5, taper_angle_rev=10)]}
CASES["sweep_taper_rev_only"] = {"objects": [SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd=6, length_rev=3,
                                                                    solid=True, taper_angle_rev=-8)]}
CASES["sweep_taper_symmetric"] = {"objects": [SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd=10,
                                                                     symmetric=True, solid=True, taper_angle=7,
                                                                     taper_angle_rev=-7)]}
CASES["sweep_taper_reversed"] = {"objects": [SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd=5, reversed=True,
                                                                    solid=True, taper_angle=15)]}
for mode in ("Inverted", "SameAsOuter"):
    CASES[f"sweep_taper_holes_{mode.lower()}"] = {"objects": [HOLES, Part.Extrusion(
        "Extrude", "Sketch", length_fwd=6, solid=True, taper_angle=8, inner_wire_taper=mode)]}
    CASES[f"sweep_taper_polyhole_{mode.lower()}"] = {"objects": [POLYHOLE, Part.Extrusion(
        "Extrude", "Sketch", length_fwd=5, length_rev=2, solid=True, taper_angle=-6, taper_angle_rev=4,
        inner_wire_taper=mode)]}
CASES["sweep_taper_shell"] = {"objects": [SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd=8, taper_angle=10)]}
CASES["sweep_taper_shell_holes"] = {"objects": [HOLES, Part.Extrusion("Extrude", "Sketch", length_fwd=6,
                                                                      taper_angle=5)]}
CASES["sweep_taper_open"] = {"objects": [sk("Sketch", [LineSegment((0, 0), (10, 0)), LineSegment((10, 0), (10, 8))]),
                                         Part.Extrusion("Extrude", "Sketch", length_fwd=5, taper_angle=10)]}
CASES["sweep_taper_circle"] = {"objects": [Part.Circle("Circle", radius=5, placement=((3, 4, 1), (0, 0, 0))),
                                           Part.Extrusion("Extrude", "Circle", length_fwd=6, solid=True,
                                                          taper_angle=-10)]}
CASES["sweep_taper_face"] = {"objects": [Part.Plane("Plane", length=10, width=6),
                                         Part.Extrusion("Extrude", "Plane", length_fwd=4, taper_angle=20)]}
CASES["sweep_taper_params"] = {"params": {"tilt": 6.0, "depth": 7.0}, "objects": [
    SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd="depth", length_rev="depth / 2", solid=True,
                           taper_angle="tilt", taper_angle_rev="-tilt")]}
CASES["sweep_taper_too_much"] = {"objects": [SQUARE, Part.Extrusion("Extrude", "Sketch", length_fwd=20, solid=True,
                                                                    taper_angle=-40)]}

# ── loft ──
BASE = sk("Sketch", rect(-10, -10, 10, 10))
MID = sk("Sketch001", [Circle((0, 0), 6)], attachment_offset=(0, 0, 10))
TOP = sk("Sketch002", rect(-4, -4, 4, 4), attachment_offset=((1, 2, 20), (30, 0, 0)))
LOFT3 = [BASE, MID, TOP]
CASES["sweep_loft"] = {"objects": LOFT3 + [Part.Loft("Loft", ["Sketch", "Sketch001", "Sketch002"])]}
CASES["sweep_loft_ruled"] = {"objects": LOFT3 + [Part.Loft("Loft", ["Sketch", "Sketch001", "Sketch002"],
                                                           ruled=True)]}
CASES["sweep_loft_shell"] = {"objects": LOFT3 + [Part.Loft("Loft", ["Sketch", "Sketch001", "Sketch002"],
                                                           solid=False)]}
CASES["sweep_loft_degree"] = {"objects": LOFT3 + [Part.Loft("Loft", ["Sketch", "Sketch001", "Sketch002"],
                                                            max_degree=2)]}
CASES["sweep_loft_degree_clamped"] = {"objects": LOFT3 + [Part.Loft("Loft", ["Sketch", "Sketch001"],
                                                                    max_degree=1)]}
CASES["sweep_loft_apex"] = {"objects": [BASE, Part.Vertex("Vertex", x=2, y=1, z=15),
                                        Part.Loft("Loft", ["Sketch", "Vertex"])]}
CASES["sweep_loft_apex_both"] = {"objects": [Part.Vertex("Vertex", z=-8), MID, Part.Vertex("Vertex001", z=25),
                                             Part.Loft("Loft", ["Vertex", "Sketch001", "Vertex001"], closed=True)]}
CASES["sweep_loft_two_wires"] = {"objects": [BASE, sk("Sketch001", rect(-10, -10, 10, 10),
                                                      attachment_offset=(0, 0, 12)),
                                             Part.Loft("Loft", ["Sketch", "Sketch001"], linearize=True)]}
CASES["sweep_loft_two_wires_curved"] = {"objects": [BASE, sk("Sketch001", rect(-10, -10, 10, 10),
                                                             attachment_offset=(0, 0, 12)),
                                                    Part.Loft("Loft", ["Sketch", "Sketch001"])]}
RING = [Part.Circle(f"Circle{i}", radius=2, placement=((10 * c, 10 * s, 0), (a, 0, -90)))
        for i, (c, s, a) in enumerate(((1, 0, 0), (0, 1, 90), (-1, 0, 180), (0, -1, 270)))]
CASES["sweep_loft_closed"] = {"objects": RING + [Part.Loft("Loft", [c.name for c in RING], closed=True)]}
CASES["sweep_loft_closed_ruled"] = {"objects": RING + [Part.Loft("Loft", [c.name for c in RING], closed=True,
                                                                 ruled=True)]}
CASES["sweep_loft_face_edge"] = {"objects": [Part.Plane("Plane", length=10, width=6),
                                             Part.Circle("Circle", radius=3, placement=((5, 3, 8), (0, 0, 0))),
                                             Part.Loft("Loft", ["Plane", "Circle"])]}
CASES["sweep_loft_open_wires"] = {"objects": [
    sk("Sketch", [LineSegment((0, 0), (10, 0)), LineSegment((10, 0), (10, 5))]),
    sk("Sketch001", [ArcOfCircle((5, 0), 5, 0.0, 3.14159265)], attachment_offset=(0, 0, 8)),
    Part.Loft("Loft", ["Sketch", "Sketch001"], solid=False)]}
CASES["sweep_loft_errors"] = {"objects": [
    BASE, sk("Holes", rect(0, 0, 4, 4) + rect(6, 0, 10, 4)),
    Part.Loft("Loft", []), Part.Loft("Loft001", ["Sketch"]), Part.Loft("Loft002", ["Sketch", "Sketch"]),
    Part.Loft("Loft003", ["Sketch", "Holes"])]}

# ── sweep ──
HELIX = Part.Helix("Helix", pitch=6, height=18, radius=5)
RINGP = sk("Profile", [Circle((5, 0), 1)], support="XZ")
CASES["sweep_helix"] = {"objects": [HELIX, RINGP, Part.Sweep("Sweep", ["Profile"], spine="Helix")]}
CASES["sweep_helix_nofrenet"] = {"objects": [HELIX, RINGP, Part.Sweep("Sweep", ["Profile"], spine="Helix",
                                                                      frenet=False)]}
CASES["sweep_helix_shell"] = {"objects": [HELIX, RINGP, Part.Sweep("Sweep", ["Profile"], spine=("Helix", "Edge1"),
                                                                   solid=False)]}
PATH = sk("Path", [LineSegment((0, 0), (20, 0)), LineSegment((20, 0), (20, 15)), LineSegment((20, 15), (5, 25))])
SQ = sk("Square", rect(-2, -2, 2, 2), support="YZ")
for tr in ("Transformed", "Right corner", "Round corner"):
    CASES[f"sweep_path_{tr.split()[0].lower()}"] = {"objects": [PATH, SQ, Part.Sweep(
        "Sweep", ["Square"], spine=("Path", ["Edge1", "Edge2", "Edge3"]), transition=tr)]}
CASES["sweep_path_two_edges"] = {"objects": [PATH, SQ, Part.Sweep("Sweep", ["Square"],
                                                                  spine=("Path", ["Edge1", "Edge2"]),
                                                                  transition="Round corner", frenet=False)]}
CASES["sweep_path_one_edge"] = {"objects": [PATH, SQ, Part.Sweep("Sweep", ["Square"], spine=("Path", "Edge1"))]}
CASES["sweep_path_whole"] = {"objects": [PATH, SQ, Part.Sweep("Sweep", ["Square"], spine="Path", linearize=True)]}
CASES["sweep_two_sections"] = {"objects": [
    sk("Sketch", rect(-3, -3, 3, 3)), sk("Sketch001", [Circle((0, 0), 2)], attachment_offset=(0, 0, 20)),
    Part.Line("Line", z2=20), Part.Sweep("Sweep", ["Sketch", "Sketch001"], spine="Line")]}
CASES["sweep_errors"] = {"objects": [
    PATH, SQ, Part.Sweep("Sweep", ["Square"]), Part.Sweep("Sweep001", [], spine="Path"),
    Part.Sweep("Sweep002", ["Square"], spine=("Path", ["Edge1", "Edge3"]))]}

# ── offset (3D) ──
BOX = Part.Box("Box", length=20, width=10, height=8)
for v in (2, -1.5):
    for j in ("Arc", "Tangent", "Intersection"):
        CASES[f"sweep_offset_{j.lower()}_{'out' if v > 0 else 'in'}"] = {"objects": [BOX, Part.Offset(
            "Offset", "Box", value=v, join=j)]}
CASES["sweep_offset_cylinder"] = {"objects": [Part.Cylinder("Cylinder", radius=4, height=6),
                                              Part.Offset("Offset", "Cylinder", value=1.25)]}
CASES["sweep_offset_intersection_flag"] = {"objects": [BOX, Part.Offset("Offset", "Box", value=1, join="Intersection",
                                                                         intersection=True, self_intersection=True)]}
for m in ("Pipe", "RectoVerso"):
    CASES[f"sweep_offset_mode_{m.lower()}"] = {"objects": [BOX, Part.Offset("Offset", "Box", value=1, mode=m)]}
CASES["sweep_offset_face_fill"] = {"objects": [Part.Plane("Plane", length=10, width=6),
                                               Part.Offset("Offset", "Plane", value=2, fill=True)]}
CASES["sweep_offset_face"] = {"objects": [Part.Plane("Plane", length=10, width=6),
                                          Part.Offset("Offset", "Plane", value=-2)]}
CASES["sweep_offset_params"] = {"params": {"gap": 0.75}, "objects": [BOX, Part.Offset("Offset", "Box",
                                                                                       value="gap * 2")]}
CASES["sweep_offset_errors"] = {"objects": [Part.Offset("Offset")]}

# ── offset2D ──
RECT = sk("Sketch", rect(0, 0, 20, 10))
OPEN = sk("Sketch", [LineSegment((0, 0), (10, 0)), LineSegment((10, 0), (10, 8))])
POLY = Part.Polygon("Polygon", nodes=[(0, 0, 0), (10, 0, 0), (10, 8, 0), (4, 12, 0)])
for v in (2, -1.5):
    for j in ("Arc", "Tangent", "Intersection"):
        CASES[f"sweep_offset2d_{j.lower()}_{'out' if v > 0 else 'in'}"] = {"objects": [RECT, Part.Offset2D(
            "Offset2D", "Sketch", value=v, join=j)]}
CASES["sweep_offset2d_fill"] = {"objects": [RECT, Part.Offset2D("Offset2D", "Sketch", value=2, fill=True)]}
CASES["sweep_offset2d_fill_in"] = {"objects": [RECT, Part.Offset2D("Offset2D", "Sketch", value=-2, fill=True,
                                                                   join="Intersection")]}
CASES["sweep_offset2d_face"] = {"objects": [Part.Plane("Plane", length=10, width=6),
                                            Part.Offset2D("Offset2D", "Plane", value=1.5)]}
CASES["sweep_offset2d_face_fill"] = {"objects": [Part.Plane("Plane", length=10, width=6, placement=((1, 2, 3),
                                                                                                    (0, 30, 0))),
                                                 Part.Offset2D("Offset2D", "Plane", value=1, fill=True)]}
CASES["sweep_offset2d_holes"] = {"objects": [HOLES, Part.Offset2D("Offset2D", "Sketch", value=1)]}
CASES["sweep_offset2d_holes_intersection"] = {"objects": [HOLES, Part.Offset2D("Offset2D", "Sketch", value=1,
                                                                               intersection=True)]}
CASES["sweep_offset2d_holes_fill"] = {"objects": [HOLES, Part.Offset2D("Offset2D", "Sketch", value=-1,
                                                                       intersection=True, fill=True)]}
CASES["sweep_offset2d_overlap"] = {"objects": [sk("Sketch", rect(0, 0, 10, 10) + rect(12, 0, 22, 10)),
                                               Part.Offset2D("Offset2D", "Sketch", value=2, intersection=True)]}
CASES["sweep_offset2d_circle"] = {"objects": [Part.Circle("Circle", radius=4, placement=((2, 3, 4), (10, 20, 30))),
                                              Part.Offset2D("Offset2D", "Circle", value=1)]}
CASES["sweep_offset2d_open_pipe"] = {"objects": [POLY, Part.Offset2D("Offset2D", "Polygon", value=1)]}
CASES["sweep_offset2d_open_skin"] = {"objects": [POLY, Part.Offset2D("Offset2D", "Polygon", value=1, mode="Skin")]}
CASES["sweep_offset2d_open_skin_fill"] = {"objects": [POLY, Part.Offset2D("Offset2D", "Polygon", value=-1,
                                                                          mode="Skin", fill=True)]}
CASES["sweep_offset2d_open_pipe_fill"] = {"objects": [POLY, Part.Offset2D("Offset2D", "Polygon", value=1,
                                                                          fill=True, join="Intersection")]}
CASES["sweep_offset2d_open_line"] = {"objects": [Part.Line("Line", x2=10, z2=0), Part.Offset2D(
    "Offset2D", "Line", value=2, mode="Skin", fill=True)]}
# An open sketch: FreeCAD's SketchObject::buildShape makes its InternalShape with FaceMakerBuildFace, which leaves
# pcurves on a plane on the Shape's own (shared) edges; BRepFill_OffsetWire, offsetting an open wire, uses them and
# splits an offset edge where this sketch's edges (no pcurves) are not split. The same shape, more edges.
CASES["sweep_offset2d_open_sketch"] = {"objects": [OPEN, Part.Offset2D("Offset2D", "Sketch", value=1, mode="Skin")]}
KNOWN[("sweep_offset2d_open_sketch", "Offset2D")] = ("edges", "vertices")
CASES["sweep_offset2d_zero"] = {"objects": [RECT, Part.Offset2D("Offset2D", "Sketch", value=0)]}
CASES["sweep_offset2d_errors"] = {"objects": [
    RECT, BOX, HELIX, Part.Offset2D("Offset2D", "Sketch", mode="RectoVerso"),
    Part.Offset2D("Offset2D001", "Sketch", value=0, fill=True), Part.Offset2D("Offset2D002", "Box"),
    Part.Offset2D("Offset2D003", "Helix"), Part.Offset2D("Offset2D004")]}

# ── thickness ──
for j in ("Arc", "Tangent", "Intersection"):
    CASES[f"sweep_thickness_{j.lower()}"] = {"objects": [BOX, Part.Thickness("Thickness", ("Box", ["Face6"]),
                                                                             join=j)]}
CASES["sweep_thickness_two"] = {"objects": [BOX, Part.Thickness("Thickness", ("Box", ["Face6", "Face1"]), value=1.5,
                                                                join="Intersection")]}
CASES["sweep_thickness_inward"] = {"objects": [BOX, Part.Thickness("Thickness", ("Box", "Face2"), value=-1)]}
CASES["sweep_thickness_flags"] = {"objects": [BOX, Part.Thickness("Thickness", ("Box", ["Face6"]), value=0.5,
                                                                  intersection=True, self_intersection=True)]}
for m in ("Pipe", "RectoVerso"):
    CASES[f"sweep_thickness_mode_{m.lower()}"] = {"objects": [BOX, Part.Thickness("Thickness", ("Box", ["Face6"]),
                                                                                  mode=m)]}
CASES["sweep_thickness_cylinder"] = {"objects": [Part.Cylinder("Cylinder", radius=5, height=8),
                                                 Part.Thickness("Thickness", ("Cylinder", ["Face2"]), value=0.8)]}
CASES["sweep_thickness_zero"] = {"objects": [BOX, Part.Thickness("Thickness", ("Box", ["Face6"]), value=0)]}
CASES["sweep_thickness_errors"] = {"objects": [
    BOX, Part.Box("Box001", placement=((30, 0, 0), (0, 0, 0))), Part.Compound("Compound", ["Box", "Box001"]),
    Part.Thickness("Thickness", ("Box", [])), Part.Thickness("Thickness001", ("Compound", ["Face1"])),
    Part.Thickness("Thickness002", ("Box", ["Edge1"])), Part.Thickness("Thickness003")]}

# ── projection on surface ──
DRUM = Part.Cylinder("Cylinder", radius=10, height=30)
WINDOW = sk("Sketch", rect(-4, 5, 4, 15) + rect(-2, 8, 2, 12), support="XZ", attachment_offset=(0, 0, 20))
FRAME = sk("Sketch", rect(-4, 5, 4, 15), support="XZ", attachment_offset=(0, 0, 20))
PANE = Part.Plane("Plane", length=8, width=10, placement=((-4, -20, 5), (0, 0, 90)))
for m in ("All", "Faces", "Edges"):
    CASES[f"sweep_project_{m.lower()}"] = {"objects": [DRUM, FRAME, PANE, Part.ProjectOnSurface(
        "Projection", support_face=("Cylinder", "Face1"), projection=["Sketch", ("Plane", "Face1")],
        direction=(0, 1, 0), mode=m)]}
CASES["sweep_project_height"] = {"objects": [DRUM, PANE, Part.ProjectOnSurface(
    "Projection", support_face=("Cylinder", "Face1"), projection=[("Plane", "Face1")], direction=(0, 1, 0),
    height=2)]}
CASES["sweep_project_offset"] = {"objects": [DRUM, PANE, Part.ProjectOnSurface(
    "Projection", support_face=("Cylinder", "Face1"), projection=[("Plane", "Face1")], direction=(0, 2, 0),
    height=1.5, offset=-1)]}
CASES["sweep_project_edges_of"] = {"objects": [DRUM, WINDOW, Part.ProjectOnSurface(
    "Projection", support_face=("Cylinder", "Face1"), projection=[("Sketch", ["Edge1", "Edge6"])],
    direction=(0, 1, 0))]}
CASES["sweep_project_plane"] = {"objects": [BOX, Part.Circle("Circle", radius=3, placement=((10, 5, 20), (0, 0, 0))),
                                            Part.ProjectOnSurface("Projection", support_face=("Box", "Face6"),
                                                                  projection=["Circle"], direction=(0.2, 0, -1))]}
CASES["sweep_project_errors"] = {"objects": [
    DRUM, FRAME, Part.ProjectOnSurface("Projection", projection=["Sketch"]),
    Part.ProjectOnSurface("Projection001", support_face=("Cylinder", ["Face1", "Face2"]), projection=["Sketch"])]}
