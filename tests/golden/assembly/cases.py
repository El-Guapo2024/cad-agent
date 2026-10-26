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
