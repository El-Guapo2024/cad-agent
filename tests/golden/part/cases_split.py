"""Part's split, join and compound tools (cad_agent/feature_part_split.py): BooleanFragments, Slice (and Slice apart),
XOR, Connect, Embed, Cutout, CompoundFilter (and Explode compound), each mode and FreeCAD's failures. make.py split
writes freecad_split.json.
"""
from cad_agent import feature_part as Part
from cad_agent.feature import Circle, LineSegment, Sketch  # noqa: F401
from cases import rect, sk

CASES = {}
KNOWN: dict = {}


def at(x, y, z, ypr=(0, 0, 0)):
    return ((x, y, z), ypr)


BOX = Part.Box("Box", length=10, width=10, height=10)
SPHERE = Part.Sphere("Sphere", radius=6, placement=at(10, 10, 10))
CYL = Part.Cylinder("Cylinder", radius=3, height=20, placement=at(5, 5, -5))
PLANE = Part.Plane("Plane", length=20, width=20, placement=at(-5, -5, 5))         # z = 5, across the box
PLANE_X = Part.Plane("PlaneX", length=20, width=20, placement=at(4, -5, -5, (0, -90, 0)))   # x = 4
TWO = [BOX, SPHERE]
THREE = [BOX, SPHERE, CYL]

# ── BooleanFragments ──
for mode in ("Standard", "Split", "CompSolid"):
    CASES[f"split_bf_{mode.lower()}"] = {"objects": TWO + [Part.BooleanFragments("BooleanFragments", ["Box", "Sphere"],
                                                                                mode=mode)]}
    CASES[f"split_bf_three_{mode.lower()}"] = {"objects": THREE + [Part.BooleanFragments(
        "BooleanFragments", ["Box", "Sphere", "Cylinder"], mode=mode)]}
CASES["split_bf_compound"] = {"objects": THREE + [Part.Compound("Compound", ["Box", "Sphere", "Cylinder"]),
                                                  Part.BooleanFragments("BooleanFragments", ["Compound"])]}
NEAR = [BOX, Part.Box("Box001", length=10, width=10, height=10, placement=at(10.00005, 3, 2))]
CASES["split_bf_gap"] = {"objects": NEAR + [Part.BooleanFragments("BooleanFragments", ["Box", "Box001"],
                                                                  mode="CompSolid")]}
CASES["split_bf_tolerance"] = {"objects": NEAR + [Part.BooleanFragments("BooleanFragments", ["Box", "Box001"],
                                                                        mode="CompSolid", tolerance=0.001)]}
CASES["split_bf_touching"] = {"objects": [BOX, Part.Box("Box001", length=10, width=10, height=10,
                                                        placement=at(10, 3, 2)),
                                          Part.BooleanFragments("BooleanFragments", ["Box", "Box001"],
                                                                mode="CompSolid")]}
FACES = [Part.Plane("Plane", length=10, width=10),
         Part.Plane("Plane001", length=10, width=10, placement=at(5, 5, -5, (0, -90, 0)))]
for mode in ("Standard", "Split"):
    CASES[f"split_bf_faces_{mode.lower()}"] = {"objects": FACES + [Part.BooleanFragments(
        "BooleanFragments", ["Plane", "Plane001"], mode=mode)]}
SHELLS = [sk("Sketch", rect(0, 0, 10, 10)), Part.Extrusion("Extrude", "Sketch", length_fwd=10),
          sk("Sketch001", rect(-5, 3, 15, 7), support="XZ", attachment_offset=(0, 0, -5)),
          Part.Extrusion("Extrude001", "Sketch001", dir=(0, 1, 0), length_fwd=20)]
for mode in ("Standard", "Split"):
    CASES[f"split_bf_shells_{mode.lower()}"] = {"objects": SHELLS + [Part.BooleanFragments(
        "BooleanFragments", ["Extrude", "Extrude001"], mode=mode)]}
WIRES = [sk("Sketch", rect(0, 0, 10, 10)), Part.Line("Line", x1=5, y1=-5, z1=0, x2=5, y2=15, z2=0),
         Part.Circle("Circle", radius=4, placement=at(10, 10, 0))]
for mode in ("Standard", "Split"):
    CASES[f"split_bf_wires_{mode.lower()}"] = {"objects": WIRES + [Part.BooleanFragments(
        "BooleanFragments", ["Sketch", "Line", "Circle"], mode=mode)]}
CASES["split_bf_solid_face"] = {"objects": [BOX, PLANE, Part.BooleanFragments("BooleanFragments", ["Box", "Plane"])]}
CASES["split_bf_errors"] = {"objects": FACES + [
    Part.BooleanFragments("BooleanFragments", ["Plane"]),
    Part.BooleanFragments("BooleanFragments001", ["Plane", "Plane001"], mode="CompSolid"),
    Part.BooleanFragments("BooleanFragments002", []),
    Part.BooleanFragments("BooleanFragments003", ["Plane", "Plane"])]}

# ── Slice, Slice apart ──
for mode in ("Standard", "Split", "CompSolid"):
    CASES[f"split_slice_plane_{mode.lower()}"] = {"objects": [BOX, PLANE, Part.Slice("Slice", "Box", ["Plane"],
                                                                                     mode=mode)]}
    CASES[f"split_slice_solids_{mode.lower()}"] = {"objects": THREE + [Part.Slice("Slice", "Box",
                                                                                  ["Sphere", "Cylinder"], mode=mode)]}
CASES["split_slice_two_planes"] = {"objects": [BOX, PLANE, PLANE_X, Part.Slice("Slice", "Box", ["Plane", "PlaneX"],
                                                                               mode="Split")]}
CASES["split_slice_tolerance"] = {"objects": NEAR + [Part.Slice("Slice", "Box", ["Box001"], tolerance=0.001)]}
for mode in ("Standard", "Split"):
    CASES[f"split_slice_shell_{mode.lower()}"] = {"objects": SHELLS[:2] + [
        Part.Plane("Plane", length=20, width=20, placement=at(-5, -5, 5)),
        Part.Slice("Slice", "Extrude", ["Plane"], mode=mode)]}
    CASES[f"split_slice_wire_{mode.lower()}"] = {"objects": WIRES[:2] + [Part.Slice("Slice", "Sketch", ["Line"],
                                                                                    mode=mode)]}
CASES["split_slice_errors"] = {"objects": [BOX, FACES[0], Part.Slice("Slice", "Box", []),
                                           Part.Slice("Slice001", None, ["Box"]),
                                           Part.Slice("Slice002", "Plane", ["Box"], mode="CompSolid")]}
CASES["split_slice_apart"] = {"objects": [BOX, PLANE, PLANE_X, *Part.slice_apart("Slice", "Box", ["Plane", "PlaneX"],
                                                                                 4)]}

# ── XOR ──
CASES["split_xor_two"] = {"objects": TWO + [Part.XOR("XOR", ["Box", "Sphere"])]}
CASES["split_xor_three"] = {"objects": [BOX, Part.Sphere("Sphere", radius=6, placement=at(8, 5, 5)),
                                        Part.Cylinder("Cylinder", radius=3, height=20, placement=at(6, 5, -5)),
                                        Part.XOR("XOR", ["Box", "Sphere", "Cylinder"], tolerance=0.0)]}
CASES["split_xor_compound"] = {"objects": THREE + [Part.Compound("Compound", ["Box", "Sphere", "Cylinder"]),
                                                   Part.XOR("XOR", ["Compound"])]}
CASES["split_xor_faces"] = {"objects": [Part.Plane("Plane", length=10, width=10),
                                        Part.Plane("Plane001", length=10, width=10, placement=at(4, 3, 0)),
                                        Part.XOR("XOR", ["Plane", "Plane001"])]}
CASES["split_xor_shell_face"] = {"objects": SHELLS[:2] + [Part.Plane("Plane", length=20, width=20,
                                                                     placement=at(-5, -5, 5)),
                                                          Part.XOR("XOR", ["Extrude", "Plane"])]}
CASES["split_xor_errors"] = {"objects": [BOX, Part.XOR("XOR", ["Box"])]}

# ── Connect, Embed, Cutout ──
TUBES = [Part.Tube("Tube", outer_radius=5, inner_radius=3, height=20, placement=at(0, 0, -10)),
         Part.Tube("Tube001", outer_radius=4, inner_radius=2, height=20, placement=at(-10, 0, 0, (0, 90, 0)))]
CASES["split_connect_tubes"] = {"objects": TUBES + [Part.Connect("Connect", ["Tube", "Tube001"])]}
CASES["split_connect_refine"] = {"objects": [BOX, Part.Box("Box001", length=10, width=10, height=10,
                                                           placement=at(10, 0, 2)),
                                             Part.Connect("Connect", ["Box", "Box001"], refine=True)]}
CASES["split_connect_compound"] = {"objects": TUBES + [Part.Compound("Compound", ["Tube", "Tube001"]),
                                                       Part.Connect("Connect", ["Compound"])]}
CASES["split_connect_touching"] = {"objects": [BOX, Part.Box("Box001", length=10, width=10, height=10,
                                                             placement=at(10, 3, 2)),
                                               Part.Connect("Connect", ["Box", "Box001"])]}
CASES["split_connect_faces"] = {"objects": FACES + [Part.Connect("Connect", ["Plane", "Plane001"])]}
CASES["split_connect_wires"] = {"objects": WIRES[:2] + [Part.Connect("Connect", ["Sketch", "Line"])]}
CASES["split_connect_one"] = {"objects": [BOX, Part.Connect("Connect", ["Box"])]}
CASES["split_connect_errors"] = {"objects": [BOX, PLANE, Part.Vertex("Vertex"),
                                             Part.Vertex("Vertex001", x=1),
                                             Part.Connect("Connect", ["Box", "Plane"]),
                                             Part.Connect("Connect001", ["Vertex", "Vertex001"])]}
STUD = Part.Cylinder("Cylinder", radius=2, height=10, placement=at(5, 5, 5))
CASES["split_embed"] = {"objects": [BOX, STUD, Part.Embed("Embed", "Box", "Cylinder")]}
CASES["split_embed_tube"] = {"objects": [Part.Box("Box", length=20, width=20, height=4, placement=at(-10, -10, -2)),
                                         TUBES[0], Part.Embed("Embed", "Box", "Tube")]}
CASES["split_embed_refine"] = {"objects": [BOX, STUD, Part.Embed("Embed", "Box", "Cylinder", refine=True)]}
CASES["split_embed_touching"] = {"objects": [BOX, Part.Cylinder("Cylinder", radius=2, height=5,
                                                                placement=at(5, 5, 10)),
                                             Part.Embed("Embed", "Box", "Cylinder")]}
CASES["split_embed_apart"] = {"objects": [BOX, Part.Sphere("Sphere", radius=2, placement=at(20, 0, 0)),
                                          Part.Embed("Embed", "Box", "Sphere")]}
CASES["split_embed_faces"] = {"objects": FACES + [Part.Embed("Embed", "Plane", "Plane001")]}
SLAB = Part.Box("Slab", length=20, width=2, height=20, placement=at(-5, 4, -5))
CASES["split_embed_errors"] = {"objects": [BOX, SLAB, Part.Embed("Embed", "Box", "Slab"),
                                           Part.Embed("Embed001", "Box", None)]}
CASES["split_cutout"] = {"objects": [BOX, STUD, Part.Cutout("Cutout", "Box", "Cylinder")]}
CASES["split_cutout_tube"] = {"objects": [Part.Box("Box", length=20, width=20, height=4, placement=at(-10, -10, -2)),
                                          TUBES[0], Part.Cutout("Cutout", "Box", "Tube")]}
CASES["split_cutout_offcentre"] = {"objects": [BOX, Part.Box("Slab", length=20, width=2, height=20,
                                                             placement=at(-5, 2, -5)),
                                               Part.Cutout("Cutout", "Box", "Slab", refine=True)]}
CASES["split_cutout_apart"] = {"objects": [BOX, Part.Sphere("Sphere", radius=2, placement=at(20, 0, 0)),
                                           Part.Cutout("Cutout", "Box", "Sphere")]}
CASES["split_cutout_errors"] = {"objects": [BOX, SLAB, STUD, Part.Compound("Compound", ["Box", "Slab"]),
                                            Part.Cutout("Cutout", "Box", "Slab"),
                                            Part.Cutout("Cutout001", "Compound", "Cylinder")]}

# ── CompoundFilter, Explode compound ──
PIECES = [Part.Box("Box", length=10, width=10, height=10),
          Part.Box("Box001", length=4, width=4, height=4, placement=at(20, 0, 0)),
          Part.Sphere("Sphere", radius=3, placement=at(0, 20, 0)),
          Part.Cylinder("Cylinder", radius=1, height=30, placement=at(30, 30, 0)),
          Part.Compound("Compound", ["Box", "Box001", "Sphere", "Cylinder"])]
CF = Part.CompoundFilter
CASES["split_cf_bypass"] = {"objects": PIECES + [CF("CompoundFilter", "Compound")]}
CASES["split_cf_items"] = {"objects": PIECES + [
    CF("CompoundFilter", "Compound", filter_type="specific items", items="0;2"),
    CF("CompoundFilter001", "Compound", filter_type="specific items", items="1:"),
    CF("CompoundFilter002", "Compound", filter_type="specific items", items="::2"),
    CF("CompoundFilter003", "Compound", filter_type="specific items", items="-1"),
    CF("CompoundFilter004", "Compound", filter_type="specific items", items="1;3", invert=True),
    CF("CompoundFilter005", "Compound", filter_type="specific items", items="0;1:3", invert=True),
    CF("CompoundFilter006", "Compound", filter_type="specific items", items="3:0:-1"),
    CF("CompoundFilter007", "Compound", filter_type="specific items", items="2")]}
CASES["split_cf_window"] = {"objects": PIECES + [
    CF("CompoundFilter", "Compound", filter_type="window-volume"),
    CF("CompoundFilter001", "Compound", filter_type="window-volume", window_from=5, window_to=50),
    CF("CompoundFilter002", "Compound", filter_type="window-volume", invert=True),
    CF("CompoundFilter003", "Compound", filter_type="window-area", window_from=20, window_to=70),
    CF("CompoundFilter004", "Compound", filter_type="window-length", window_from=0, window_to=40),
    CF("CompoundFilter005", "Compound", filter_type="window-volume", override_max_val=200, window_from=0,
       window_to=100)]}
STENCIL = Part.Box("Stencil", length=25, width=3, height=3, placement=at(5, 1, 1))
CASES["split_cf_stencil"] = {"objects": PIECES + [STENCIL,
    CF("CompoundFilter", "Compound", filter_type="collision-pass", stencil="Stencil"),
    CF("CompoundFilter001", "Compound", filter_type="collision-pass", stencil="Stencil", invert=True),
    CF("CompoundFilter002", "Compound", filter_type="window-distance", stencil="Stencil", window_from=0,
       window_to=50),
    CF("CompoundFilter003", "Compound", filter_type="window-volume", stencil="Stencil", window_from=0,
       window_to=60)]}
CASES["split_cf_errors"] = {"objects": PIECES + [
    CF("CompoundFilter", "Compound", filter_type="specific items"),
    CF("CompoundFilter001", "Compound", filter_type="specific items", items="7"),
    CF("CompoundFilter002", "Compound", filter_type="specific items", items="1 ;x"),
    CF("CompoundFilter003", "Compound", filter_type="collision-pass"),
    CF("CompoundFilter004", "Compound", filter_type="window-distance"),
    CF("CompoundFilter005", "Compound", filter_type="window-volume", window_from=101, window_to=200),
    CF("CompoundFilter006", "Compound", filter_type="specific items", items="1:2:3:4"),
    CF("CompoundFilter007", None)]}
CASES["split_cf_solid"] = {"objects": [BOX, CF("CompoundFilter", "Box")]}     # a solid's children are its shells
CASES["split_cf_fragments"] = {"objects": TWO + [Part.BooleanFragments("BooleanFragments", ["Box", "Sphere"]),
                                                 CF("CompoundFilter", "BooleanFragments",
                                                    filter_type="window-volume")]}
CASES["split_explode"] = {"objects": PIECES + Part.explode_compound("Compound", 4)}
CASES["split_explode_fragments"] = {"objects": THREE + [
    Part.BooleanFragments("BooleanFragments", ["Box", "Sphere", "Cylinder"]),
    *Part.explode_compound("BooleanFragments", 8)]}
