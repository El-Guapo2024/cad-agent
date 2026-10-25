"""Part workbench documents, each built by FreeCAD (make.py, freecadcmd) and by cad_agent/feature_part*.py
(tests/test_feature_part.py), every object's shape compared.

Each case is {"objects": OBJECTS, "params": PARAMS, "features": FEATURES (a Body) or absent}. An area of its own keeps
its cases in cases_<area>.py next to this one (a CASES dict there too, names unique across the areas) and its answers
in freecad_<area>.json (make.py AREA).
"""
from pathlib import Path

from cad_agent import feature_part as Part
from cad_agent.feature import (ArcOfCircle, Circle, Constraint, LineSegment, Pad, Point, Sketch)  # noqa: F401

HERE = Path(__file__).resolve().parent


def rect(x0, y0, x1, y1):
    return [LineSegment((x0, y0), (x1, y0)), LineSegment((x1, y0), (x1, y1)),
            LineSegment((x1, y1), (x0, y1)), LineSegment((x0, y1), (x0, y0))]


def sk(name, geometry, support="XY", **kw):
    return Sketch(name, support=support, geometry=geometry, **kw)


P = ((5.0, -3.0, 2.0), (30.0, 15.0, -10.0))         # a placement off the axes, turned on all three
CASES = {}

# ── primitives: defaults, then values and a placement ──
CASES["prim_defaults"] = {"objects": [
    Part.Box("Box"), Part.Cylinder("Cylinder"), Part.Sphere("Sphere"), Part.Cone("Cone"), Part.Torus("Torus"),
    Part.Tube("Tube"), Part.Prism("Prism"), Part.Wedge("Wedge"), Part.Helix("Helix"), Part.Spiral("Spiral"),
    Part.Ellipsoid("Ellipsoid"), Part.Plane("Plane"), Part.Circle("Circle"), Part.Ellipse("Ellipse"),
    Part.Line("Line"), Part.Vertex("Vertex"), Part.RegularPolygon("RegularPolygon"),
    Part.Polygon("Polygon", nodes=[(0, 0, 0), (10, 0, 0), (10, 5, 3)]),
]}
CASES["prim_values"] = {"objects": [
    Part.Box("Box", length=40, width=20, height=5, placement=P),
    Part.Cylinder("Cylinder", radius=3, height=12, angle=270, placement=P),
    Part.Cylinder("Skewed", radius=3, height=12, first_angle=20, second_angle=-10),
    Part.Sphere("Sphere", radius=7, angle1=-30, angle2=60, angle3=200, placement=P),
    Part.Cone("Cone", radius1=5, radius2=0, height=8, angle=300),
    Part.Cone("ConeCyl", radius1=3, radius2=3, height=4),
    Part.Torus("Torus", radius1=12, radius2=3, angle1=-90, angle2=120, angle3=270, placement=P),
    Part.Tube("Tube", outer_radius=6, inner_radius=4, height=3, placement=P),
    Part.Tube("Rod", outer_radius=6, inner_radius=0, height=3),
    Part.Prism("Prism", polygon=5, circumradius=4, height=6, first_angle=15),
    Part.Wedge("Wedge", xmin=-2, ymin=1, zmin=0, x2min=1, z2min=3, xmax=8, ymax=7, zmax=9, x2max=5, z2max=6),
    Part.Helix("Helix", pitch=2.5, height=12, radius=4, angle=10, local_coord="Left-handed"),
    Part.Helix("HelixSeg", pitch=1.5, height=7, radius=2, segment_length=1.0, placement=P),
    Part.Spiral("Spiral", growth=2, radius=1.5, rotations=3.5, segment_length=0.5),
    Part.Ellipsoid("Ellipsoid", radius1=3, radius2=6, radius3=4, angle1=-60, angle2=70, angle3=300),
    Part.Plane("Plane", length=30, width=12, placement=P),
    Part.Circle("Circle", radius=5, angle1=30, angle2=250, placement=P),
    Part.Ellipse("Ellipse", major_radius=8, minor_radius=3, angle1=0, angle2=180),
    Part.Line("Line", x1=1, y1=2, z1=3, x2=-4, y2=6, z2=0),
    Part.Vertex("Vertex", x=3, y=-2, z=7),
    Part.RegularPolygon("RegularPolygon", polygon=8, circumradius=5, placement=P),
    Part.Polygon("Polygon", nodes=[(0, 0, 0), (10, 0, 0), (10, 5, 0), (0, 5, 0)], close=True),
]}
CASES["prim_params"] = {"params": {"w": 25.0, "r": 4.0, "n": 7}, "objects": [
    Part.Box("Box", length="w", width="w / 2", height="r + 1"),
    Part.Cylinder("Cylinder", radius="r", height="w"),
    Part.Prism("Prism", polygon="n", circumradius="r", height=3),
]}
CASES["prim_errors"] = {"objects": [
    Part.Box("Box", length=0),
    Part.Ellipse("Ellipse", major_radius=2, minor_radius=3),
    Part.Tube("Tube", outer_radius=2, inner_radius=3),
    Part.Prism("Prism", polygon=2),
]}

# ── booleans ──
TWO = [Part.Box("Box", length=20, width=20, height=10),
       Part.Cylinder("Cylinder", radius=6, height=20, placement=((10, 10, -5), (0, 0, 0)))]
CASES["cut"] = {"objects": TWO + [Part.Cut("Cut", "Box", "Cylinder")]}
CASES["cut_norefine"] = {"objects": TWO + [Part.Cut("Cut", "Box", "Cylinder", refine=False)]}
CASES["fuse"] = {"objects": TWO + [Part.Fuse("Fusion", "Box", "Cylinder")]}
CASES["common"] = {"objects": TWO + [Part.Common("Common", "Box", "Cylinder")]}
CASES["section"] = {"objects": TWO + [Part.Section("Section", "Box", "Cylinder")]}
THREE = [Part.Box("Box", length=20, width=20, height=10), Part.Sphere("Sphere", radius=8,
                                                                       placement=((20, 20, 10), (0, 0, 0))),
         Part.Cylinder("Cylinder", radius=4, height=30, placement=((0, 10, -10), (0, 0, 0)))]
CASES["multifuse"] = {"objects": THREE + [Part.MultiFuse("Fusion", ["Box", "Sphere", "Cylinder"])]}
CASES["multifuse_norefine"] = {"objects": THREE + [Part.MultiFuse("Fusion", ["Box", "Sphere", "Cylinder"],
                                                                  refine=False)]}
CASES["multicommon"] = {"objects": THREE + [Part.MultiCommon("Common", ["Box", "Sphere"])]}
CASES["multicommon3"] = {"objects": [Part.Box("Box", length=20, width=20, height=10),
                                     Part.Sphere("Sphere", radius=12, placement=((10, 10, 5), (0, 0, 0))),
                                     Part.Cylinder("Cylinder", radius=8, height=30,
                                                   placement=((10, 10, -10), (0, 0, 0))),
                                     Part.MultiCommon("Common", ["Box", "Sphere", "Cylinder"])]}
CASES["cut_chain"] = {"objects": THREE + [Part.Cut("Cut", "Box", "Sphere"), Part.Cut("Cut001", "Cut", "Cylinder")]}
CASES["cut_chain_norefine"] = {"objects": THREE + [Part.Cut("Cut", "Box", "Sphere"), Part.Cut("Cut001", "Cut", "Cylinder", refine=False)]}
CASES["cut_compound_tool"] = {"objects": THREE + [Part.Compound("Compound", ["Sphere", "Cylinder"]),
                                                  Part.Cut("Cut", "Box", "Compound")]}

# ── extrude ──
PLATE = sk("Sketch", rect(0, 0, 30, 20) + [Circle((10, 10), 4), Circle((22, 10), 3)])
CASES["extrude_shell"] = {"objects": [PLATE, Part.Extrusion("Extrude", "Sketch", length_fwd=8)]}
CASES["extrude_solid"] = {"objects": [PLATE, Part.Extrusion("Extrude", "Sketch", length_fwd=8, solid=True)]}
CASES["extrude_both"] = {"objects": [PLATE, Part.Extrusion("Extrude", "Sketch", length_fwd=8, length_rev=3,
                                                           solid=True, reversed=True)]}
CASES["extrude_symmetric"] = {"objects": [PLATE, Part.Extrusion("Extrude", "Sketch", length_fwd=8, symmetric=True,
                                                                solid=True)]}
CASES["extrude_dir"] = {"objects": [PLATE, Part.Extrusion("Extrude", "Sketch", dir=(1, 0, 2), solid=True)]}
CASES["extrude_normal"] = {"objects": [sk("Sketch", rect(0, 0, 10, 6), support="XZ",
                                          attachment_offset=(0, 0, 4)),
                                       Part.Extrusion("Extrude", "Sketch", dir_mode="Normal", length_fwd=5,
                                                      solid=True)]}
CASES["extrude_edge"] = {"objects": [PLATE, Part.Line("Line", x1=0, y1=0, z1=0, x2=1, y2=1, z2=3),
                                     Part.Extrusion("Extrude", "Sketch", dir_mode="Edge", dir_link=("Line", "Edge1"),
                                                    length_fwd=6, solid=True)]}
NESTED = sk("Sketch", rect(0, 0, 40, 40) + rect(5, 5, 35, 35) + [Circle((20, 20), 8), Circle((20, 20), 3)])
for maker in ("Simple", "Cheese", "Extrusion", "Bullseye", "Unified"):
    CASES[f"extrude_maker_{maker.lower()}"] = {"objects": [NESTED, Part.Extrusion(
        "Extrude", "Sketch", length_fwd=4, solid=True, face_maker_mode=maker)]}
OVERLAP = sk("Sketch", rect(0, 0, 20, 10) + rect(10, 5, 30, 15))
CASES["extrude_overlap_unified"] = {"objects": [OVERLAP, Part.Extrusion("Extrude", "Sketch", length_fwd=3,
                                                                        solid=True)]}
CASES["extrude_face"] = {"objects": [Part.Plane("Plane", length=10, width=5),
                                     Part.Extrusion("Extrude", "Plane", length_fwd=2)]}
CASES["extrude_circle"] = {"objects": [Part.Circle("Circle", radius=3),
                                       Part.Extrusion("Extrude", "Circle", length_fwd=4, solid=True)]}

# ── revolve ──
PROFILE = sk("Sketch", rect(5, 0, 10, 8), support="XZ")
CASES["revolve"] = {"objects": [PROFILE, Part.Revolution("Revolve", "Sketch")]}
CASES["revolve_solid"] = {"objects": [PROFILE, Part.Revolution("Revolve", "Sketch", angle=120, solid=True)]}
CASES["revolve_symmetric"] = {"objects": [PROFILE, Part.Revolution("Revolve", "Sketch", angle=90, symmetric=True,
                                                                   solid=True)]}
CASES["revolve_axis"] = {"objects": [sk("Sketch", [Circle((15, 0), 3)]),
                                     Part.Revolution("Revolve", "Sketch", base=(0, 0, 0), axis=(0, 1, 0),
                                                     angle=270, solid=True)]}
CASES["revolve_axis_link"] = {"objects": [sk("Sketch", [Circle((15, 0), 3)]),
                                          Part.Line("Line", x1=0, y1=-5, z1=0, x2=0, y2=5, z2=0),
                                          Part.Revolution("Revolve", "Sketch", axis_link=("Line", "Edge1"),
                                                          angle=180, solid=True)]}
CASES["revolve_arc_link"] = {"objects": [sk("Sketch", [Circle((15, 0), 3)]),
                                         Part.Circle("Arc", radius=2, angle1=0, angle2=90,
                                                     placement=((0, 0, 0), (0, 0, 90))),
                                         Part.Revolution("Revolve", "Sketch", axis_link=("Arc", "Edge1"), angle=0,
                                                         solid=True)]}

# ── mirror ──
CASES["mirror"] = {"objects": [Part.Box("Box", length=10, width=5, height=3, placement=P),
                               Part.Mirroring("Mirror", "Box", normal=(1, 0, 0), base=(-4, 0, 0))]}
CASES["mirror_face"] = {"objects": [Part.Box("Box", length=10, width=5, height=3),
                                    Part.Cylinder("Cylinder", radius=2, height=4, placement=((3, 2, 3), (0, 0, 0))),
                                    Part.Mirroring("Mirror", "Cylinder", mirror_plane=("Box", "Face6"))]}
CASES["mirror_plane_obj"] = {"objects": [Part.Sphere("Sphere", radius=3, placement=((5, 5, 5), (0, 0, 0))),
                                         Part.Plane("Plane", placement=((0, 0, 2), (0, 45, 0))),
                                         Part.Mirroring("Mirror", "Sphere", mirror_plane="Plane")]}

# ── fillet, chamfer ──
CASES["fillet"] = {"objects": [Part.Box("Box", length=20, width=10, height=8),
                               Part.Fillet("Fillet", "Box", edges=[(1, 2.0, 2.0), (3, 2.0, 2.0), (11, 1.0, 3.0)])]}
CASES["chamfer"] = {"objects": [Part.Box("Box", length=20, width=10, height=8),
                                Part.Chamfer("Chamfer", "Box", edges=[(1, 2.0, 2.0), (5, 1.0, 3.0)])]}
CASES["fillet_cut"] = {"objects": TWO + [Part.Cut("Cut", "Box", "Cylinder"),
                                         Part.Fillet("Fillet", "Cut", edges=[(2, 1.5, 1.5), (4, 1.5, 1.5)])]}

# ── compound, refine ──
CASES["compound"] = {"objects": THREE + [Part.Compound("Compound", ["Box", "Sphere", "Cylinder", "Box"])]}
CASES["refine"] = {"objects": [Part.Box("Box", length=10, width=10, height=10),
                               Part.Box("Box001", length=10, width=10, height=10,
                                        placement=((10, 0, 0), (0, 0, 0))),
                               Part.MultiFuse("Fusion", ["Box", "Box001"], refine=False),
                               Part.Refine("Refine", "Fusion")]}

# ── Part objects on a PartDesign Body ──
BODY = [Sketch("Sketch", support="XY", geometry=rect(0, 0, 30, 20)), Pad("Pad", "Sketch", length=6)]
CASES["body_cut"] = {"features": BODY, "objects": [
    Part.Cylinder("Cylinder", radius=4, height=10, placement=((15, 10, -2), (0, 0, 0))),
    Part.Cut("Cut", "Body", "Cylinder")]}
CASES["body_extrude_sketch"] = {"features": BODY, "objects": [
    Part.Extrusion("Extrude", "Sketch", length_fwd=3, reversed=True, solid=True),
    Part.MultiFuse("Fusion", ["Body", "Extrude"])]}

