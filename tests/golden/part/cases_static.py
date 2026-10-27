"""Part's static objects (cad_agent/feature_part_static.py): Part_SimpleCopy and its two kin, Part_MakeSolid,
Part_CrossSections, Part_Builder and Part_ToleranceSet, the documents FreeCAD builds, its answers recorded in
freecad_static.json (make.py static).

FreeCAD makes these by running Python that sets a Part::Feature's Shape (make.py builds them the same way through
to_freecad); a part file holds the recipe. A Box's vertices: 1 (0,0,0) 2 (0,0,h) 3 (0,w,0) 4 (0,w,h) 5 (l,0,0)
6 (l,0,h) 7 (l,w,0) 8 (l,w,h); its edges: 1-4 the x=0 face's, 5-8 the x=l face's, 9-12 along x.
"""
import importlib.util as _ilu
from pathlib import Path as _Path

from cad_agent import feature_part as Part
from cad_agent.feature import Circle, Pad, Sketch  # noqa: F401

_spec = _ilu.spec_from_file_location("part_base_cases", _Path(__file__).with_name("cases.py"))
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)
rect, P = _base.rect, _base.P

KNOWN: dict = {}
CASES = {}
BOX = Part.Box("Box", length=10, width=20, height=5, placement=P)
PLAIN = Part.Box("Box", length=10, width=20, height=5)
CUT = [Part.Box("Box", length=20, width=20, height=10),
       Part.Cylinder("Cylinder", radius=5, height=20, placement=((10, 10, -5), (0, 0, 0))), Part.Cut("Cut", "Box", "Cylinder")]

# ── copies ──
CASES["copy_box"] = {"objects": [BOX, Part.Feature("Box001", "Box", label="Cube001")]}
CASES["copy_plain"] = {"objects": [PLAIN, Part.Feature("Box001", "Box")]}
CASES["copy_cut"] = {"objects": [*CUT, Part.Feature("Cut001", "Cut")]}
CASES["copy_of_copy"] = {"objects": [BOX, Part.Feature("Box001", "Box"), Part.Feature("Box002", "Box001")]}
CASES["copy_moved"] = {"objects": [BOX, Part.Feature("Box001", "Box", placement=((1, 2, 3), (0, 0, 0)))]}
CASES["copy_body_feature"] = {"features": [Sketch("Sketch", support="XZ", geometry=rect(0, 0, 30, 20)),
                                           Pad("Pad", "Sketch", length=5.0)],
                              "objects": [Part.Feature("Pad001", "Pad")]}
CASES["element_face"] = {"objects": [BOX, Part.Feature("Box001", ("Box", "Face3"))]}
CASES["element_edge"] = {"objects": [BOX, Part.Feature("Box001", ("Box", "Edge6"))]}
CASES["element_vertex"] = {"objects": [BOX, Part.Feature("Box001", ("Box", "Vertex4"))]}
CASES["element_plain_face"] = {"objects": [PLAIN, Part.Feature("Box001", ("Box", "Face6"))]}
CASES["element_cut_face"] = {"objects": [*CUT, Part.Feature("Cut001", ("Cut", "Face3"))]}

# ── Convert to solid ──
CASES["solid_of_shell"] = {"objects": [
    PLAIN, Part.ShapeBuilder("Shell", "Shell from faces", all_faces=True, elements=[("Box", "Face1"), ("Box", "Face2")]),
    Part.MakeSolid("Shell_solid", "Shell", label="Shell (Solid)")]}
CASES["solid_of_compound"] = {"objects": [
    Part.Box("Box", length=10, width=10, height=10), Part.Cylinder("Cylinder", radius=3, height=20, placement=((20, 0, 0), (0, 0, 0))),
    Part.Compound("Compound", ["Box", "Cylinder"]), Part.MakeSolid("Compound_solid", "Compound")]}
CASES["solid_of_closed_compound"] = {"objects": [
    Part.Box("Box", length=10, width=10, height=10, placement=P), Part.Compound("Compound", ["Box"]),
    Part.MakeSolid("Compound_solid", "Compound")]}

# ── Cross-sections ──
CASES["cs_box_xy"] = {"objects": [PLAIN, Part.CrossSections("Box_cs", "Box", plane="XY", positions=[2.5])]}
CASES["cs_box_many"] = {"objects": [BOX, Part.CrossSections("Box_cs", "Box", plane="XZ", positions=[-2.0, 0.0, 2.0, 4.0])]}
CASES["cs_cut_yz"] = {"objects": [*CUT, Part.CrossSections("Cut_cs", "Cut", plane="YZ", positions=[5.0, 10.0, 15.0])]}
CASES["cs_cylinder"] = {"objects": [Part.Cylinder("Cylinder", radius=4, height=10), Part.CrossSections("Cylinder_cs", "Cylinder", plane="XY", positions=[0.0, 5.0, 10.0])]}
CASES["cs_torus"] = {"objects": [Part.Torus("Torus", radius1=10, radius2=3), Part.CrossSections("Torus_cs", "Torus", plane="XZ", positions=[0.0]),
                                 Part.CrossSections("Torus_cs001", "Torus", plane="XY", positions=[0.0, 2.0])]}
CASES["cs_sphere"] = {"objects": [Part.Sphere("Sphere", radius=6), Part.CrossSections("Sphere_cs", "Sphere", plane="YZ", positions=[0.0, 3.0])]}
CASES["cs_face"] = {"objects": [Part.Plane("Plane", length=10, width=10, placement=((0, 0, 0), (0, 45, 0))),
                                Part.CrossSections("Plane_cs", "Plane", plane="XY", positions=[-1.0, -3.0])]}
CASES["cs_shell"] = {"objects": [PLAIN, Part.ShapeBuilder("Shell", "Shell from faces", all_faces=True, elements=[("Box", "Face1"), ("Box", "Face2")]),
                                 Part.CrossSections("Shell_cs", "Shell", plane="XY", positions=[2.0])]}

# ── Shape builder ──
CASES["sb_edge"] = {"objects": [BOX, Part.ShapeBuilder("Edge", "Edge from vertices", elements=[("Box", "Vertex1"), ("Box", "Vertex8")])]}
CASES["sb_wire"] = {"objects": [BOX, Part.ShapeBuilder("Wire", "Wire from edges", elements=[("Box", "Edge2"), ("Box", "Edge10"), ("Box", "Edge6"), ("Box", "Edge12")])]}
CASES["sb_wire_unsorted"] = {"objects": [PLAIN, Part.ShapeBuilder("Wire", "Wire from edges", elements=[("Box", "Edge12"), ("Box", "Edge2"), ("Box", "Edge6"), ("Box", "Edge10")])]}
CASES["sb_wire_open"] = {"objects": [PLAIN, Part.ShapeBuilder("Wire", "Wire from edges", elements=[("Box", "Edge1"), ("Box", "Edge2"), ("Box", "Edge3")])]}
CASES["sb_face_vertices_planar"] = {"objects": [BOX, Part.ShapeBuilder("Face", "Face from vertices", planar=True, elements=[("Box", "Vertex2"), ("Box", "Vertex4"), ("Box", "Vertex8"), ("Box", "Vertex6")])]}
CASES["sb_face_vertices_filled"] = {"objects": [BOX, Part.ShapeBuilder("Face", "Face from vertices", elements=[("Box", "Vertex2"), ("Box", "Vertex4"), ("Box", "Vertex8"), ("Box", "Vertex6")])]}
CASES["sb_face_vertices_twisted"] = {"objects": [PLAIN, Part.ShapeBuilder("Face", "Face from vertices", elements=[("Box", "Vertex1"), ("Box", "Vertex4"), ("Box", "Vertex6"), ("Box", "Vertex7")])]}
CASES["sb_face_vertices_triangle"] = {"objects": [PLAIN, Part.ShapeBuilder("Face", "Face from vertices", planar=True, elements=[("Box", "Vertex1"), ("Box", "Vertex4"), ("Box", "Vertex6")])]}
CASES["sb_face_edges_planar"] = {"objects": [BOX, Part.ShapeBuilder("Face", "Face from edges", planar=True, elements=[("Box", "Edge2"), ("Box", "Edge10"), ("Box", "Edge6"), ("Box", "Edge12")])]}
CASES["sb_face_edges_filled"] = {"objects": [PLAIN, Part.ShapeBuilder("Face", "Face from edges", elements=[("Box", "Edge2"), ("Box", "Edge10"), ("Box", "Edge6"), ("Box", "Edge12")])]}
CASES["sb_shell"] = {"objects": [PLAIN, Part.ShapeBuilder("Shell", "Shell from faces", refine=False, elements=[("Box", "Face1"), ("Box", "Face3"), ("Box", "Face5")])]}
CASES["sb_shell_refined"] = {"objects": [PLAIN, Part.ShapeBuilder("Shell", "Shell from faces", elements=[("Box", "Face1"), ("Box", "Face3"), ("Box", "Face5")])]}
CASES["sb_shell_all"] = {"objects": [BOX, Part.ShapeBuilder("Shell", "Shell from faces", all_faces=True, elements=[("Box", "Face2"), ("Box", "Face4")])]}
CASES["sb_solid"] = {"objects": [PLAIN, Part.ShapeBuilder("Shell", "Shell from faces", all_faces=True, elements=[("Box", "Face1"), ("Box", "Face2")]),
                                 Part.ShapeBuilder("Solid", "Solid from shell", elements=["Shell"])]}
CASES["sb_solid_unrefined"] = {"objects": [BOX, Part.ShapeBuilder("Shell", "Shell from faces", refine=False, all_faces=True, elements=[("Box", "Face1"), ("Box", "Face2")]),
                                           Part.ShapeBuilder("Solid", "Solid from shell", refine=False, elements=["Shell"])]}

# ── Set tolerance ──
CASES["tol_box"] = {"objects": [PLAIN, Part.ToleranceSet("Tolerance", ["Box"], min_tolerance=1e-05)]}
CASES["tol_default"] = {"objects": [PLAIN, Part.ToleranceSet("Tolerance", ["Box"])]}
CASES["tol_placed"] = {"objects": [BOX, Part.ToleranceSet("Tolerance", ["Box"], min_tolerance=1e-07)]}
CASES["tol_two"] = {"objects": [*CUT, Part.ToleranceSet("Tolerance", ["Cut", "Cylinder"], min_tolerance=1e-06)]}
CASES["tol_refine"] = {"objects": [*CUT, Part.ToleranceSet("Tolerance", ["Cut"], min_tolerance=1e-06, refine=True)]}
CASES["tol_max"] = {"objects": [PLAIN, Part.ToleranceSet("Tolerance", ["Box"], min_tolerance=1e-03, max_tolerance=1e-02)]}
