"""Assemblies, each built and solved by FreeCAD (make.py, freecadcmd) and by cad_agent/assembly_wb.py with
ui/ondsel (tests/test_assembly_golden.py), the steps replayed as the Assembly workbench's commands make them.

A case is {"parts": {part: OBJECTS}, "components": [(link, part, placement)], "ground": [link, ...],
"steps": [step, ...]}. Each part is a Part workbench document of one object (feature_part), linked into the
assembly by an App::Link named link at placement ((x, y, z), (yaw, pitch, roll)) or None; "ground" are the
GroundedJoints made after the links are inserted (createGroundedJoint, then the document recomputed). A step is

    {"op": "joint", "type": "Revolute", "ref1": (link, [element, vertex]), "ref2": ..., "props": {...}}
        Assembly_CreateJoint<type> with the two picks, as TaskAssemblyCreateJoint makes it: the joint, the picks
        one then two (setJointConnectors), the panel's values (props, our snake_case of FreeCAD's properties:
        distance, angle, offset2 ((x, y, z), (yaw, pitch, roll)), enable_length_min ...), OK (accept)
    {"op": "set", "joint": name, "prop": prop, "value": v}     a property set later (onChanged), then a recompute
    {"op": "reverse", "joint": name}                           the panel's Reverse (flipOnePart), then a recompute
    {"op": "move", "link": name, "placement": P}               a component's Placement set, then a recompute
    {"op": "suppress", "joint": name, "value": True}           Suppressed set, then a recompute

After each step make.py records every component's Placement, each joint's References and Placement1/2, and the
messages FreeCAD wrote; at the end exportAsASMT's file, which is the system the solver was given.
"""
from cad_agent import feature_part as Part

T = ((30.0, 5.0, 2.0), (10.0, 20.0, 30.0))       # somewhere off the axes, turned on all three
T2 = ((-20.0, 40.0, 15.0), (-35.0, 5.0, 60.0))
T3 = ((12.0, -30.0, 8.0), (80.0, -15.0, 5.0))

BOX10 = [Part.Box("Box", length=10, width=10, height=10)]
PLATE = [Part.Box("Box", length=40, width=30, height=5)]
BAR = [Part.Box("Box", length=30, width=6, height=4)]
PIN = [Part.Cylinder("Cylinder", radius=3, height=20)]
DISC = [Part.Cylinder("Cylinder", radius=8, height=4)]
BALL = [Part.Sphere("Sphere", radius=4)]

CASES = {}


def case(name, parts, components, ground, steps):
    CASES[name] = {"parts": parts, "components": components, "ground": ground, "steps": steps}


def joint(type_, ref1, ref2, **props):
    return {"op": "joint", "type": type_, "ref1": ref1, "ref2": ref2, "props": props}


TWO_BOXES = ({"box10": BOX10, "bar": BAR}, [("Base", "box10", None), ("Arm", "bar", T)], ["Base"])
PLATE_PIN = ({"plate": PLATE, "pin": PIN}, [("Plate", "plate", None), ("Pin", "pin", T)], ["Plate"])

# ── each joint type between two parts, on faces, edges and vertices ──
case("fixed_face_vertex", *TWO_BOXES, [joint("Fixed", ("Base", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"]))])
case("fixed_face_centre", *TWO_BOXES, [joint("Fixed", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]))])
case("fixed_edge_middle", *TWO_BOXES, [joint("Fixed", ("Base", ["Edge2", "Edge2"]), ("Arm", ["Edge1", "Edge1"]))])
case("fixed_vertex", *TWO_BOXES, [joint("Fixed", ("Base", ["Vertex2", "Vertex2"]), ("Arm", ["Vertex7", "Vertex7"]))])
case("fixed_offset", *TWO_BOXES, [joint("Fixed", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]),
                                        offset2=((0.0, 0.0, 3.0), (90.0, 0.0, 0.0)))])
case("fixed_unconnected_first", *TWO_BOXES,     # the picks the other way round: ensureUnconnectedIsSecondRef
     [joint("Fixed", ("Arm", ["Face5", "Face5"]), ("Base", ["Face6", "Face6"]))])
case("revolute_pin", *PLATE_PIN, [joint("Revolute", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face3", "Edge1"]))])
case("revolute_offset", *PLATE_PIN, [joint("Revolute", ("Plate", ["Face6", "Vertex2"]), ("Pin", ["Face3", "Edge1"]),
                                           offset2=((0.0, 0.0, -5.0), (0.0, 0.0, 0.0)))])
case("cylindrical_pin", *PLATE_PIN,
     [joint("Cylindrical", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face1", "Face1"]))])
case("slider_bar", *TWO_BOXES, [joint("Slider", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]))])
case("slider_limits", *TWO_BOXES, [joint("Slider", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]),
                                         enable_length_min=True, length_min=2.0, enable_length_max=True,
                                         length_max=8.0)])
case("ball_vertex", *TWO_BOXES, [joint("Ball", ("Base", ["Vertex8", "Vertex8"]), ("Arm", ["Vertex1", "Vertex1"]))])
case("ball_sphere", {"box10": BOX10, "ball": BALL}, [("Base", "box10", None), ("Ball", "ball", T)], ["Base"],
     [joint("Ball", ("Base", ["Vertex8", "Vertex8"]), ("Ball", ["Face1", "Face1"]))])
case("distance_planes", *TWO_BOXES,
     [joint("Distance", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]), distance=5.0)])
case("distance_point_plane", *TWO_BOXES,     # vertex first: getDistanceType swaps the references
     [joint("Distance", ("Arm", ["Vertex1", "Vertex1"]), ("Base", ["Face6", "Face6"]), distance=2.0)])
case("distance_points", *TWO_BOXES,
     [joint("Distance", ("Base", ["Vertex8", "Vertex8"]), ("Arm", ["Vertex1", "Vertex1"]), distance=7.5)])
case("distance_cylinders", {"pin": PIN, "disc": DISC}, [("Pin", "pin", None), ("Disc", "disc", T)], ["Pin"],
     [joint("Distance", ("Pin", ["Face1", "Face1"]), ("Disc", ["Face1", "Face1"]), distance=1.0)])
case("distance_lines", *TWO_BOXES,
     [joint("Distance", ("Base", ["Edge2", "Edge2"]), ("Arm", ["Edge3", "Edge3"]), distance=4.0)])
case("parallel_faces", *TWO_BOXES, [joint("Parallel", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]))])
case("perpendicular_faces", *TWO_BOXES,
     [joint("Perpendicular", ("Base", ["Face6", "Face6"]), ("Arm", ["Face1", "Face1"]))])
case("angle_30", *TWO_BOXES,
     [joint("Angle", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]), angle=30.0)])

# ── a chain, and the coupling joints on top of revolutes and sliders ──
CHAIN = ({"plate": PLATE, "bar": BAR, "pin": PIN},
         [("Plate", "plate", None), ("Arm", "bar", T), ("Pin", "pin", T2)], ["Plate"])
case("chain_revolute_fixed", *CHAIN, [
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
    joint("Fixed", ("Arm", ["Face6", "Vertex8"]), ("Pin", ["Face3", "Edge1"])),
])
GEARS = ({"plate": PLATE, "disc": DISC, "disc2": [Part.Cylinder("Cylinder", radius=4, height=4)]},
         [("Plate", "plate", None), ("Gear1", "disc", T), ("Gear2", "disc2", T2)], ["Plate"])
case("gears", *GEARS, [
    joint("Revolute", ("Plate", ["Face6", "Vertex2"]), ("Gear1", ["Face3", "Edge1"])),
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Gear2", ["Face3", "Edge1"])),
    joint("Gears", ("Gear1", ["Face2", "Edge1"]), ("Gear2", ["Face2", "Edge1"]), distance=8.0, distance2=4.0),
])
case("belt", *GEARS, [
    joint("Revolute", ("Plate", ["Face6", "Vertex2"]), ("Gear1", ["Face3", "Edge1"])),
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Gear2", ["Face3", "Edge1"])),
    joint("Belt", ("Gear1", ["Face2", "Edge1"]), ("Gear2", ["Face2", "Edge1"]), distance=8.0, distance2=4.0),
])
RACK = ({"plate": PLATE, "bar": BAR, "disc": DISC},
        [("Plate", "plate", None), ("Rack", "bar", T), ("Pinion", "disc", T2)], ["Plate"])
case("rack_pinion", *RACK, [
    joint("Slider", ("Plate", ["Face6", "Face6"]), ("Rack", ["Face5", "Face5"])),
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Pinion", ["Face3", "Edge1"])),
    joint("RackPinion", ("Rack", ["Face6", "Face6"]), ("Pinion", ["Face2", "Edge1"]), distance=8.0),
])
case("screw", *PLATE_PIN, [
    joint("Cylindrical", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face3", "Edge1"])),
    joint("Screw", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face3", "Edge1"]), distance=2.0),
])

# ── edits after the joints are made ──
case("set_distance", *TWO_BOXES, [
    joint("Distance", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]), distance=5.0),
    {"op": "set", "joint": "Joint", "prop": "distance", "value": 12.0},
])
case("set_angle", *TWO_BOXES, [
    joint("Angle", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]), angle=30.0),
    {"op": "set", "joint": "Joint", "prop": "angle", "value": 75.0},
])
case("reverse_fixed", *TWO_BOXES, [
    joint("Fixed", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"])),
    {"op": "reverse", "joint": "Joint"},
])
case("move_revolute_part", *PLATE_PIN, [
    joint("Revolute", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face3", "Edge1"])),
    {"op": "move", "link": "Pin", "placement": T3},
])
case("suppress_joint", *TWO_BOXES, [
    joint("Fixed", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"])),
    {"op": "move", "link": "Arm", "placement": T3},
    {"op": "suppress", "joint": "Joint", "value": True},
])

# ── over-constrained, conflicting, nothing grounded ──
case("redundant_fixed", *TWO_BOXES, [
    joint("Fixed", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"])),
    joint("Fixed", ("Base", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
])
case("conflicting_distance", *TWO_BOXES, [
    joint("Fixed", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"])),
    joint("Distance", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]), distance=5.0),
])
case("ungrounded", {"box10": BOX10, "bar": BAR}, [("Base", "box10", None), ("Arm", "bar", T)], [],
     [joint("Fixed", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]))])

# ── more Distance pairs (getDistanceType), limits, Offset1, a carrier, a chain ──
SPHERE_PIN = ({"pin": PIN, "ball": BALL}, [("Pin", "pin", None), ("Ball", "ball", T)], ["Pin"])
case("distance_point_line", *TWO_BOXES,
     [joint("Distance", ("Base", ["Edge2", "Edge2"]), ("Arm", ["Vertex1", "Vertex1"]), distance=3.0)])
case("distance_line_plane", *TWO_BOXES,
     [joint("Distance", ("Base", ["Face6", "Face6"]), ("Arm", ["Edge2", "Edge2"]), distance=2.0)])
case("distance_plane_cylinder", {"plate": PLATE, "pin": PIN}, [("Plate", "plate", None), ("Pin", "pin", T)],
     ["Plate"], [joint("Distance", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face1", "Face1"]), distance=1.5)])
case("distance_cylinder_sphere", *SPHERE_PIN,
     [joint("Distance", ("Pin", ["Face1", "Face1"]), ("Ball", ["Face1", "Face1"]), distance=0.5)])
case("distance_sphere_plane", {"plate": PLATE, "ball": BALL}, [("Plate", "plate", None), ("Ball", "ball", T)],
     ["Plate"], [joint("Distance", ("Ball", ["Face1", "Face1"]), ("Plate", ["Face6", "Face6"]), distance=0.0)])
case("distance_circles", {"disc": DISC, "pin": PIN}, [("Disc", "disc", None), ("Pin", "pin", T)], ["Disc"],
     [joint("Distance", ("Disc", ["Edge1", "Edge1"]), ("Pin", ["Edge3", "Edge3"]), distance=2.0)])
case("distance_point_cylinder", *PLATE_PIN,
     [joint("Distance", ("Pin", ["Face1", "Face1"]), ("Plate", ["Vertex8", "Vertex8"]), distance=1.0)])
case("revolute_angle_limits", *PLATE_PIN,
     [joint("Revolute", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face3", "Edge1"]), enable_angle_min=True,
            angle_min=-30.0, enable_angle_max=True, angle_max=45.0)])
case("cylindrical_limits", *PLATE_PIN,
     [joint("Cylindrical", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face1", "Face1"]), enable_length_min=True,
            length_min=-3.0, enable_length_max=True, length_max=-1.0, enable_angle_max=True, angle_max=10.0)])
case("limits_swapped", *TWO_BOXES,       # min above max: makeMbdJoint swaps them, in the document too
     [joint("Slider", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]), enable_length_min=True,
            length_min=8.0, enable_length_max=True, length_max=2.0)])
case("fixed_offset1", *TWO_BOXES, [joint("Fixed", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]),
                                         offset1=((2.0, -1.0, 0.0), (0.0, 0.0, 30.0)))])
case("slider_rotation", *TWO_BOXES, [joint("Slider", ("Base", ["Face6", "Face6"]), ("Arm", ["Face5", "Face5"]),
                                           offset2=((0.0, 0.0, 0.0), (45.0, 0.0, 0.0)))])
DISC4 = [Part.Cylinder("Cylinder", radius=4, height=4)]
case("belt_on_a_carrier", {"plate": PLATE, "bar": BAR, "disc": DISC, "disc2": DISC4},
     [("Plate", "plate", None), ("Carrier", "bar", T), ("Gear1", "disc", T2), ("Gear2", "disc2", T3)], ["Plate"], [
         joint("Revolute", ("Plate", ["Face6", "Face6"]), ("Carrier", ["Face5", "Face5"])),
         joint("Revolute", ("Carrier", ["Face6", "Vertex2"]), ("Gear1", ["Face3", "Edge1"])),
         joint("Revolute", ("Carrier", ["Face6", "Vertex8"]), ("Gear2", ["Face3", "Edge1"])),
         joint("Belt", ("Gear1", ["Face2", "Edge1"]), ("Gear2", ["Face2", "Edge1"]), distance=8.0, distance2=4.0),
     ])
case("three_part_chain", {"plate": PLATE, "bar": BAR, "pin": PIN, "disc": DISC},
     [("Plate", "plate", None), ("Arm", "bar", T), ("Pin", "pin", T2), ("Disc", "disc", T3)], ["Plate"], [
         joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
         joint("Cylindrical", ("Arm", ["Face6", "Vertex8"]), ("Pin", ["Face3", "Edge1"])),
         joint("Fixed", ("Pin", ["Face2", "Edge1"]), ("Disc", ["Face3", "Edge1"])),
         {"op": "suppress", "joint": "Joint", "value": True},
     ])

# ── rigid groups (Assembly_CreateJointRigidGroup: JointObject.RigidGroupJoint, AssemblyObject's rigid clusters) ──
#    {"op": "rigid", "parts": [link, ...]}       the selection's components made one rigid group, then a recompute
#    {"op": "update_rigid", "joint": name}       the group's "Update Stored Positions" (while it is suppressed)
case("rigid_pair_revolute", *CHAIN, [
    {"op": "rigid", "parts": ["Arm", "Pin"]},
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
])
case("rigid_with_grounded", *CHAIN, [
    {"op": "rigid", "parts": ["Plate", "Arm"]},
    joint("Fixed", ("Arm", ["Face6", "Vertex8"]), ("Pin", ["Face3", "Edge1"])),
])
case("rigid_move_member", *CHAIN, [
    {"op": "rigid", "parts": ["Arm", "Pin"]},
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
    {"op": "move", "link": "Pin", "placement": T3},
])
case("rigid_joint_inside", *CHAIN, [         # a joint between two members: its parts share one solver body
    {"op": "rigid", "parts": ["Arm", "Pin"]},
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
    joint("Fixed", ("Arm", ["Face6", "Vertex8"]), ("Pin", ["Face3", "Edge1"])),
])
case("rigid_suppress_restore", *CHAIN, [
    {"op": "rigid", "parts": ["Arm", "Pin"]},
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
    {"op": "suppress", "joint": "RigidGroupJoint", "value": True},
    {"op": "move", "link": "Pin", "placement": T3},
    {"op": "suppress", "joint": "RigidGroupJoint", "value": False},
])
case("rigid_update_stored", *CHAIN, [
    {"op": "rigid", "parts": ["Arm", "Pin"]},
    {"op": "suppress", "joint": "RigidGroupJoint", "value": True},
    {"op": "move", "link": "Pin", "placement": T3},
    {"op": "update_rigid", "joint": "RigidGroupJoint"},
    {"op": "suppress", "joint": "RigidGroupJoint", "value": False},
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
])
case("rigid_two_groups_chained", {"plate": PLATE, "bar": BAR, "pin": PIN, "disc": DISC},
     [("Plate", "plate", None), ("Arm", "bar", T), ("Pin", "pin", T2), ("Disc", "disc", T3)], ["Plate"], [
         {"op": "rigid", "parts": ["Arm", "Pin"]},
         {"op": "rigid", "parts": ["Pin", "Disc"]},
         joint("Slider", ("Plate", ["Face6", "Face6"]), ("Disc", ["Face3", "Edge1"])),
     ])

# ── joints on the Assembly's Origin: a pick on one of its features is (Origin, ["XY_Plane.", "XY_Plane."]), the
#    Origin grounded as it always is (getGroundedParts), the JCS findPlacement's whole-part case ──
NO_GROUND = ({"box10": BOX10, "bar": BAR, "pin": PIN, "ball": BALL},
             [("Arm", "bar", T), ("Pin", "pin", T2), ("Ball", "ball", T3)], [])
case("origin_fixed_xy", *NO_GROUND, [joint("Fixed", ("Origin", ["XY_Plane.", "XY_Plane."]), ("Arm", ["Face5", "Face5"]))])
case("origin_fixed_xz_first_part", *NO_GROUND,
     [joint("Fixed", ("Arm", ["Face5", "Vertex1"]), ("Origin", ["XZ_Plane.", "XZ_Plane."]))])
case("origin_revolute_z_axis", *NO_GROUND,
     [joint("Revolute", ("Origin", ["Z_Axis.", "Z_Axis."]), ("Pin", ["Face3", "Edge1"]))])
case("origin_slider_x_axis", *NO_GROUND,
     [joint("Slider", ("Origin", ["X_Axis.", "X_Axis."]), ("Arm", ["Edge1", "Edge1"]))])
case("origin_cylindrical_y_axis", *NO_GROUND,
     [joint("Cylindrical", ("Origin", ["Y_Axis.", "Y_Axis."]), ("Pin", ["Face1", "Face1"]))])
case("origin_ball_point", *NO_GROUND,
     [joint("Ball", ("Origin", ["Origin001.", "Origin001."]), ("Ball", ["Face1", "Face1"]))])
case("origin_yz_parallel_grounded", {"box10": BOX10, "bar": BAR}, [("Base", "box10", None), ("Arm", "bar", T)], ["Base"],
     [joint("Parallel", ("Origin", ["YZ_Plane.", "YZ_Plane."]), ("Arm", ["Face1", "Face1"]))])
case("origin_angle_xy", *NO_GROUND,
     [joint("Angle", ("Origin", ["XY_Plane.", "XY_Plane."]), ("Arm", ["Face5", "Face5"]), angle=30.0)])
case("origin_distance_xz", *NO_GROUND,
     [joint("Distance", ("Origin", ["XZ_Plane.", "XZ_Plane."]), ("Arm", ["Face3", "Face3"]), distance=5.0)])
case("origin_chain", *NO_GROUND, [
    joint("Revolute", ("Origin", ["Z_Axis.", "Z_Axis."]), ("Pin", ["Face3", "Edge1"])),
    joint("Fixed", ("Pin", ["Face2", "Edge1"]), ("Arm", ["Face5", "Vertex1"])),
    {"op": "set", "joint": "Joint", "prop": "offset2", "value": ((0.0, 0.0, 2.0), (30.0, 0.0, 0.0))},
])

# ── the JCS where two cylinders' axes cross: a cylinder face at its B-spline seam with the other cylinder
#    (findElementClosestVertex's and findPlacement's findCylindersIntersection) ──
TEE = [Part.Cylinder("Cylinder", radius=4, height=30),
       Part.Cylinder("Cylinder001", radius=3, height=20, placement=((0.0, -10.0, 15.0), (0.0, 0.0, -90.0))),
       Part.MultiFuse("Fusion", ["Cylinder", "Cylinder001"])]
case("cylinders_intersection_revolute", {"tee": TEE, "pin": PIN}, [("Tee", "tee", None), ("Pin", "pin", T)], ["Tee"],
     [joint("Revolute", ("Tee", ["Face4", "Edge3"]), ("Pin", ["Face3", "Edge1"]))])
case("cylinders_intersection_moving", {"plate": PLATE, "tee": TEE}, [("Plate", "plate", None), ("Tee", "tee", T)],
     ["Plate"], [joint("Fixed", ("Plate", ["Face6", "Vertex8"]), ("Tee", ["Face1", "Edge4"]))])
case("cylinders_intersection_ball", {"plate": PLATE, "tee": TEE}, [("Plate", "plate", None), ("Tee", "tee", T)],
     ["Plate"], [joint("Ball", ("Plate", ["Vertex8", "Vertex8"]), ("Tee", ["Face5", "Edge1"]))])

# ── sub-assemblies: an Assembly::AssemblyLink to the Assembly of another document ("subs": that document's case, made,
#    solved and saved first). Its children are named here as FreeCAD names them (the parent's Plate makes the
#    sub-assembly's Plate "Plate001"); a reference into a rigid link is (link, ["Child.Face5", ...]).
#    {"op": "insert_assembly", "sub": doc, "rigid": bool, "placement": (x, y, z)}   Insert Component of an Assembly
#    {"op": "set_rigid", "link": name, "value": bool}                              Turn rigid / Turn flexible
SUB = {"parts": {"plate": PLATE, "pin": PIN}, "components": [("Plate", "plate", None), ("Pin", "pin", T)],
       "ground": ["Plate"], "steps": [joint("Revolute", ("Plate", ["Face6", "Face6"]), ("Pin", ["Face3", "Edge1"]))]}


def sub_case(name, steps, rigid=True):
    CASES[name] = {"parts": {"box10": BOX10}, "components": [("Plate", "box10", None)], "ground": ["Plate"],
                   "subs": {"Sub": SUB},
                   "steps": [{"op": "insert_assembly", "sub": "Sub", "rigid": rigid, "placement": (50.0, 0.0, 0.0)}]
                   + steps}


sub_case("subasm_rigid_inserted", [])
sub_case("subasm_rigid_fixed",
         [joint("Fixed", ("Plate", ["Face6", "Face6"]), ("Assembly001", ["Plate001.Face5", "Plate001.Face5"]))])
sub_case("subasm_rigid_revolute_on_child",
         [joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Assembly001", ["Pin.Face2", "Pin.Edge1"]))])
sub_case("subasm_rigid_move", [{"op": "move", "link": "Assembly001", "placement": T2}])
sub_case("subasm_rigid_distance",           # getDistanceType reads the child's face: the element after "Plate001."
         [joint("Distance", ("Plate", ["Face6", "Face6"]), ("Assembly001", ["Plate001.Face5", "Plate001.Face5"]),
                distance=5.0)])
sub_case("subasm_flexible_inserted", [], rigid=False)
sub_case("subasm_flexible_fixed",
         [joint("Fixed", ("Plate", ["Face6", "Face6"]), ("Plate001", ["Face5", "Face5"]))], rigid=False)
sub_case("subasm_flexible_move_child", [
    joint("Fixed", ("Plate", ["Face6", "Face6"]), ("Plate001", ["Face5", "Face5"])),
    {"op": "move", "link": "Pin", "placement": T3},
], rigid=False)
sub_case("subasm_turn_flexible_and_back", [
    joint("Fixed", ("Plate", ["Face6", "Face6"]), ("Assembly001", ["Plate001.Face5", "Plate001.Face5"])),
    {"op": "set_rigid", "link": "Assembly001", "value": False},
    {"op": "set_rigid", "link": "Assembly001", "value": True},
])

# ── exploded views (Assembly_CreateView): a view of moves, each a MovementTransform on some components, applied one
#    after the other from where the ones before left them (_calculateExplodedPlacements; headless FreeCAD has no
#    bounding boxes, so a Radial move pushes nothing) ──
#    {"op": "exploded_view", "moves": [{"references": [link, ...], "movement_transform": P, "move_type": "Normal"}]}
case("exploded_two_moves", *CHAIN, [
    joint("Revolute", ("Plate", ["Face6", "Vertex8"]), ("Arm", ["Face5", "Vertex1"])),
    {"op": "exploded_view", "moves": [
        {"references": ["Arm", "Pin"], "movement_transform": ((0.0, 0.0, 25.0), (0.0, 0.0, 0.0))},
        {"references": ["Pin"], "movement_transform": ((10.0, -5.0, 0.0), (0.0, 0.0, 0.0))},
    ]},
])
case("exploded_rotation_and_radial", *CHAIN, [
    {"op": "exploded_view", "moves": [
        {"references": ["Arm"], "movement_transform": ((3.0, 4.0, 0.0), (30.0, 0.0, 0.0))},
        {"references": ["Arm", "Pin"], "movement_transform": ((20.0, 0.0, 0.0), (0.0, 0.0, 0.0)), "move_type": "Radial"},
        {"references": ["Arm"], "movement_transform": ((0.0, 0.0, 0.0), (0.0, 45.0, 0.0))},
    ]},
    {"op": "exploded_view", "moves": [
        {"references": ["Plate"], "movement_transform": ((0.0, 0.0, -10.0), (0.0, 0.0, 0.0))},
    ]},
])

# ── the GUI check's sequence (fcassembly_more_dump.py): a rigid group, then a joint from the Origin's XY-plane to one of
#    its members, whose presolve takes the other member along ──
GUI_PARTS = ({"plate": PLATE, "pin": PIN, "bar": BAR},
             [("Plate", "plate", None), ("Pin", "pin", T), ("Bar", "bar", T2)], ["Plate"])
case("origin_on_a_rigid_group", *GUI_PARTS, [
    {"op": "rigid", "parts": ["Pin", "Bar"]},
    joint("Fixed", ("Origin", ["XY_Plane.", "XY_Plane."]), ("Bar", ["Face5", "Face5"])),
])
