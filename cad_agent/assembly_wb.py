# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's Assembly workbench objects (src/Mod/Assembly, Copyright (c) 2023 Ondsel
# <development@ondsel.com>): JointObject.py's Joint (properties, setJointConnectors, updateJCSPlacements,
# findPlacement, preSolve/matchJCS, undoPreSolve, preventParallel, ensureUnconnectedIsSecondRef, onChanged,
# execute) and GroundedJoint, TaskAssemblyCreateJoint's create and accept (UtilsAssembly.generatePropertySettings),
# CommandInsertLink's App::Link components and CommandCreateJoint.createGroundedJoint. The solve itself is
# AssemblyObject.cpp's, in ui/ondsel (cad_agent/ondsel.py).
"""The Assembly workbench's objects in a project's assembly.py, and the document they make.

A project's assembly.py is the assembly's FreeCAD document (docs/EDITING_PLAN.md, "Assembly in a part file"): its
ASSEMBLY list holds, in FreeCAD's vocabulary and document order, the Assembly's components (App::Link to a part of
the project) and its JointGroup's joints:

    from cad_agent import assembly_wb as Assembly

    ASSEMBLY = [
        Assembly.Link("base", "base"),                                    # App::Link to parts/base.py
        Assembly.Link("arm", "arm", placement=((10, 0, 5), (0.0, 0.0, 0.0, 1.0))),
        Assembly.GroundedJoint("GroundedJoint", "base"),
        Assembly.Joint("Joint", "Revolute", ("arm", ["Face3", "Edge2"]), ("base", ["Face6", "Edge9"]),
                       label="Revolute"),
    ]

    def parts():
        return Assembly.parts(SLUG, ASSEMBLY)

A component's placement is its Placement as the last solve left it ((x, y, z) and a quaternion (x, y, z, w), or
yaw, pitch, roll in degrees as a hand-written one may give it); parts() recomputes the assembly as FreeCAD does on
opening it (AssemblyObject::execute, SolveOnRecompute) and returns {component: its part's shape, placed}, which is
what every gate reads. A reference is FreeCAD's (moving part, [element, vertex]): ("arm", ["Face3", "Edge2"]) is
the JCS on the arm's Face3 at the centre of its Edge2, ("arm", ["Face3", "Vertex4"]) at that vertex, ("arm",
["Face3", "Face3"]) at the face's centre.
"""
from __future__ import annotations

import math

from . import feature_kw as KW
from .attacher import Placement, Rotation

JOINT_TYPES = ["Fixed", "Revolute", "Cylindrical", "Slider", "Ball", "Distance", "Parallel", "Perpendicular",
               "Angle", "RackPinion", "Screw", "Gears", "Belt"]
# JointObject.py's lists
JOINT_USING_ANGLE = ["Angle"]
JOINT_USING_DISTANCE = ["Distance", "RackPinion", "Screw", "Gears", "Belt"]
JOINT_USING_DISTANCE2 = ["Gears", "Belt"]
JOINT_NO_NEGATIVE_DISTANCE = ["Gears", "Belt"]
JOINT_USING_OFFSET = ["Fixed", "Revolute"]
JOINT_USING_ROTATION = ["Fixed", "Slider"]
JOINT_USING_REVERSE = ["Fixed", "Revolute", "Cylindrical", "Slider", "Distance", "Parallel"]
JOINT_USING_LIMIT_LENGTH = ["Cylindrical", "Slider"]
JOINT_USING_LIMIT_ANGLE = ["Revolute", "Cylindrical"]
JOINT_USING_PRESOLVE = ["Fixed", "Revolute", "Cylindrical", "Slider", "Ball"]
JOINT_PARALLEL_FORBIDDEN = ["Angle", "Perpendicular"]


class AssemblyError(ValueError):
    pass


# The Assembly's Origin features (App::Origin, made with the Assembly, so the first of their names in the document):
# Name -> (Role, Placement's rotation) as FreeCAD 26.3 makes them; the Origin's point is "Origin001", the Origin being
# "Origin"
ORIGIN_DATUMS = {
    "X_Axis": ("X_Axis", (0.0, 0.0, 0.0, 1.0)),
    "Y_Axis": ("Y_Axis", (0.5, 0.5, 0.5, 0.5000000000000001)),
    "Z_Axis": ("Z_Axis", (0.5, -0.5, 0.5, 0.5000000000000001)),
    "XY_Plane": ("XY_Plane", (0.0, 0.0, 0.0, 1.0)),
    "XZ_Plane": ("XZ_Plane", (0.7071067811865475, 0.0, 0.0, 0.7071067811865475)),
    "YZ_Plane": ("YZ_Plane", (0.5, 0.5, 0.5, 0.5000000000000001)),
    "Origin001": ("Origin", (0.0, 0.0, 0.0, 1.0)),
}
# UtilsAssembly.findPlacement's whole-part case: an App::Line by its Role (App.Rotation(0.5, 0.5, 0.5, 0.5) for X and
# Y, App.Rotation(-0.5, 0.5, -0.5, 0.5) for Z), every other datum the identity
DATUM_JCS = {"X_Axis": (0.5, 0.5, 0.5, 0.5), "Y_Axis": (0.5, 0.5, 0.5, 0.5), "Z_Axis": (-0.5, 0.5, -0.5, 0.5)}


class Resolved:
    """A reference's target: the moving part and its global placement, the object's placement in the part (None: the
    part is the object), the object's shape at the origin (None for a datum), the placement findPlacement takes off
    (the object's own: the component's, a sub-assembly child's), the datum's name."""
    __slots__ = ("part", "part_plc", "obj", "shape", "frame", "datum")

    def __init__(self, part, part_plc, obj, shape, frame, datum):
        self.part, self.part_plc, self.obj, self.shape, self.frame = part, part_plc, obj, shape, frame
        self.datum = datum


# ── placements as the file writes them ─────────────────────────────────────────────────────────────────

def to_placement(v) -> Placement:
    """None, (x, y, z), ((x, y, z), (yaw, pitch, roll)) in degrees, or ((x, y, z), (qx, qy, qz, qw))."""
    if v is None:
        return Placement()
    if isinstance(v, Placement):
        return v
    if isinstance(v, dict):
        return Placement(tuple(v.get("base", (0, 0, 0))), Rotation(tuple(v.get("rotation", (0, 0, 0, 1)))))
    if len(v) == 3 and all(isinstance(c, (int, float)) for c in v):
        return Placement(tuple(float(c) for c in v))
    pos, rot = v
    if len(rot) == 4:
        return Placement(tuple(float(c) for c in pos), Rotation(tuple(float(c) for c in rot)))
    return Placement(tuple(float(c) for c in pos), Rotation.from_ypr(*rot))


def placement_literal(p: Placement):
    """A Placement as the file writes it: ((x, y, z), (qx, qy, qz, qw)), every digit kept (the document's own
    precision, so that a solve starts where the last one ended)."""
    return (tuple(0.0 if c == 0 else c for c in p.pos), tuple(0.0 if c == 0 else c for c in p.rot.q))


def placement_json(p: Placement) -> dict:
    return {"base": list(p.pos), "rotation": list(p.rot.q)}


def is_identity(p: Placement) -> bool:
    return p.pos == (0.0, 0.0, 0.0) and p.rot.q[:3] == (0.0, 0.0, 0.0) and abs(p.rot.q[3]) == 1.0


# ── the objects ───────────────────────────────────────────────────────────────────────────────────────

def _ref(v, where):
    """A joint's reference: None, or (component, [element, vertex]); (component, "Face6") is (component,
    ["Face6", "Face6"]) as the initial selection makes it."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str):
        subs = v[1]
        if isinstance(subs, str):
            subs = [subs, subs]
        if not (isinstance(subs, (list, tuple)) and all(isinstance(s, str) for s in subs) and len(subs) <= 2):
            raise AssemblyError(f"{where}: {v!r} is not (component, [element, vertex])")
        return (v[0], tuple(subs))
    raise AssemblyError(f"{where}: {v!r} is not a reference: (component, [element, vertex]) such as "
                        "(\"arm\", [\"Face3\", \"Edge2\"])")


class AsmObject(KW.KwFeature):
    """An ASSEMBLY entry: FreeCAD's properties as keywords, as feature_kw.KwFeature declares them."""
    PLACEMENTS: tuple = ()

    def normalize(self, key, v):
        if key in self.PLACEMENTS:
            return None if v is None else placement_literal(to_placement(v)) if not _is_ypr(v) else _tuples(v)
        if key in getattr(self, "JOINT_REFS", ()):
            return _ref(v, f"{self.name}.{key}")
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key in getattr(self, "JOINT_REFS", ()):
            return None if v is None else (v[0], list(v[1]))
        return super().source_value(key, v)


def _is_ypr(v):
    return isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[1], (list, tuple)) and len(v[1]) == 3


def _tuples(v):
    return tuple(tuple(x) if isinstance(x, list) else x for x in v)


class Link(AsmObject):
    """App::Link, a component: Assembly_InsertLink makes one for each part inserted, named after the part (its
    document's root object's Label), at the origin for the first and offset for the next ones."""
    kind = "Link"
    TYPE_ID = "App::Link"
    POS = ("linked_object",)
    DEFAULTS = {"linked_object": None, "placement": None, "label": None, "visibility": True}
    PLACEMENTS = ("placement",)
    TRANSACTION = "Insert Component"

    def validate(self):
        if not isinstance(self.linked_object, str) or not self.linked_object:
            raise AssemblyError(f"{self.name}: a Link names the part it links (a part of the project)")

    def references(self):
        return []


class GroundedJoint(AsmObject):
    """JointObject.GroundedJoint: ObjectToGround's Placement is made read-only, which grounds it for the solver."""
    kind = "GroundedJoint"
    TYPE_ID = "App::FeaturePython"
    PROXY = "GroundedJoint"
    POS = ("object_to_ground",)
    DEFAULTS = {"object_to_ground": None, "label": None}
    TRANSACTION = "Toggle grounded"

    def validate(self):
        if not isinstance(self.object_to_ground, str) or not self.object_to_ground:
            raise AssemblyError(f"{self.name}: a GroundedJoint names the component it grounds")

    def references(self):
        return [self.object_to_ground]


class Joint(AsmObject):
    """JointObject.Joint: JointType, Reference1/2 with Placement1/2 (recomputed from the references unless
    Detach1/2), Offset1/2, Angle, Distance, Distance2, the limits, Suppressed."""
    kind = "Joint"
    TYPE_ID = "App::FeaturePython"
    PROXY = "Joint"
    POS = ("joint_type", "reference1", "reference2")
    DEFAULTS = {
        "joint_type": "Fixed", "reference1": None, "reference2": None,
        "placement1": None, "placement2": None, "detach1": False, "detach2": False,
        "offset1": None, "offset2": None,
        "angle": 0.0, "distance": 0.0, "distance2": 0.0,
        "enable_length_min": False, "enable_length_max": False, "enable_angle_min": False, "enable_angle_max": False,
        "length_min": 0.0, "length_max": 0.0, "angle_min": 0.0, "angle_max": 0.0,
        "suppressed": False, "label": None,
    }
    JOINT_REFS = ("reference1", "reference2")
    PLACEMENTS = ("placement1", "placement2", "offset1", "offset2")
    TRANSACTION = "Create Joint"

    def validate(self):
        if self.joint_type not in JOINT_TYPES:
            raise AssemblyError(f"{self.name}: {self.joint_type!r} is not a JointType ({', '.join(JOINT_TYPES)})")

    def references(self):
        return [r[0] for r in (self.reference1, self.reference2) if r]

    def source_props(self):
        """What the file writes: not FreeCAD's defaults, and Placement1/2 only when they are detached (else
        they are what the references give)."""
        out = [k for k in self.DEFAULTS if not self.is_default(k)]
        if not self.detach1 and "placement1" in out:
            out.remove("placement1")
        if not self.detach2 and "placement2" in out:
            out.remove("placement2")
        return out


class RigidGroupJoint(AsmObject):
    """JointObject.RigidGroupJoint (Assembly_CreateJointRigidGroup): ObjectsToRigidGroup, the components locked
    together (the solver makes them one body: AssemblyObject::rebuildRigidClusters), RigidPlacements (hidden: each
    member's placement relative to the first, kept for restoreFromPlacements), and Suppressed."""
    kind = "RigidGroupJoint"
    TYPE_ID = "App::FeaturePython"
    PROXY = "RigidGroupJoint"
    POS = ("objects_to_rigid_group",)
    DEFAULTS = {"objects_to_rigid_group": (), "rigid_placements": (), "suppressed": False, "label": None}
    TRANSACTION = "Create Rigid Group"

    def normalize(self, key, v):
        if key == "objects_to_rigid_group":
            if isinstance(v, str):
                v = [v]
            if not all(isinstance(x, str) and x for x in (v or ())):
                raise AssemblyError(f"{self.name}: ObjectsToRigidGroup names components: {v!r}")
            return tuple(v or ())
        if key == "rigid_placements":
            return tuple(placement_literal(to_placement(p)) for p in (v or ()))
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "objects_to_rigid_group":
            return list(v)
        if key == "rigid_placements":
            return list(v)
        return super().source_value(key, v)

    def references(self):
        return list(self.objects_to_rigid_group)


CLASSES = {c.kind: c for c in (Link, GroundedJoint, Joint, RigidGroupJoint)}


def from_dict(d: dict) -> AsmObject:
    kind = d.get("kind") or d.get("type")
    cls = CLASSES.get(kind)
    if cls is None:
        raise AssemblyError(f"{kind!r} is not an assembly object ({', '.join(CLASSES)})")
    kw = {k: v for k, v in d.items() if k not in ("name", "type", "kind")}
    return cls(d.get("name"), **kw)


def as_dict(o: AsmObject) -> dict:
    d = {"name": o.name, "kind": o.kind, "type": o.TYPE_ID}
    for k in o.DEFAULTS:
        v = getattr(o, k)
        d[k] = KW._json(v)
    return d


# ── the document ──────────────────────────────────────────────────────────────────────────────────────

class AssemblyDocument:
    """An Assembly: its components with their shapes and Placements, its joints, and what JointObject.py and
    AssemblyObject do to them. shapes maps a component's linked part to its shape (a TopoDS_Shape at the origin).

    Joints are edited in place (their attributes are FreeCAD's properties); component placements live in plc;
    jcs[joint] is each joint's (Placement1, Placement2), recomputed from the references as updateJCSPlacements
    does unless the joint is detached."""

    def __init__(self, objects, shapes: dict, document: str = "Unnamed", origin: str = "Origin"):
        self.objects = list(objects)
        self.shapes = dict(shapes)
        self.document = document
        self.origin = origin
        self.plc = {o.name: to_placement(o.placement) for o in self.components()}
        self.jcs = {}
        self.messages = []          # Console warnings and errors, as FreeCAD's report view shows them
        self.log = ""
        self.last = None            # the last solve's result
        self._presolve_backup = {}  # Joint.partsMovedByPresolved, per joint
        self._previous = []         # AssemblyObject::previousPositions (solve(storePrev))
        # AssemblyObject::rigidPlacementCache: each active rigid group member's placement at the last solve. A
        # document read from its file starts where that solve left it, so the members' placements are the cache
        # (a member moved before the next solve then drags the others: syncActiveRigidGroupPlacements)
        self.rigid_cache = [(m, self.plc[m]) for g in self.rigid_groups() if not g.suppressed
                            for m in dict.fromkeys(g.objects_to_rigid_group) if m in self.plc]
        for j in self.joints():
            self.update_jcs(j)

    # ── what is in it ──
    def components(self) -> list[Link]:
        return [o for o in self.objects if isinstance(o, Link)]

    def joints(self) -> list[Joint]:
        return [o for o in self.objects if isinstance(o, Joint)]

    def grounded_joints(self) -> list[GroundedJoint]:
        return [o for o in self.objects if isinstance(o, GroundedJoint)]

    def rigid_groups(self) -> list[RigidGroupJoint]:
        return [o for o in self.objects if isinstance(o, RigidGroupJoint)]

    def labels(self) -> list[str]:
        """Every Label in the document: the objects', and the Assembly's own and its Origin's."""
        out = ["Assembly", "Joints", self.origin, "X_Axis", "Y_Axis", "Z_Axis", "XY_Plane", "XZ_Plane", "YZ_Plane"]
        return out + [getattr(o, "label", None) or o.name for o in self.objects]

    def get(self, name):
        for o in self.objects:
            if o.name == name:
                return o
        return None

    def grounded(self) -> set:
        """The components whose Placement a GroundedJoint has made read-only."""
        names = {c.name for c in self.components()}
        return {g.object_to_ground for g in self.grounded_joints() if g.object_to_ground in names}

    def shape_of(self, comp: str):
        link = self.get(comp)
        if not isinstance(link, Link):
            raise AssemblyError(f"there is no component {comp!r}")
        try:
            return self.shapes[link.linked_object]
        except KeyError:
            raise AssemblyError(f"{comp}: its part {link.linked_object!r} is not built") from None

    # ── what a reference names (UtilsAssembly.getObject, getGlobalPlacement) ──
    def resolve(self, ref) -> Resolved | None:
        """The object a reference's sub-name reaches from its moving part: a component's own shape, or a feature of
        the Assembly's Origin (the moving part is the Origin, the object its datum: UtilsAssembly.getObject's
        LocalCoordinateSystem branch); None when it names nothing."""
        if ref is None or not ref[0]:
            return None
        comp = ref[0]
        first = ref[1][0].split(".")[0] if ref[1] else ""
        if comp == self.origin:
            datum = ORIGIN_DATUMS.get(first)
            if datum is None:
                return None
            return Resolved(comp, Placement(), Placement((0.0, 0.0, 0.0), Rotation(datum[1], normalize=False)), None, Placement(), first)
        o = self.get(comp)
        if isinstance(o, Link):
            return Resolved(comp, self.plc[comp], None, self.shape_of(comp), self.plc[comp], None)
        return None

    # ── JointObject.Joint ──
    def find_placement(self, joint: Joint, ref, index: int) -> Placement:
        """Joint.findPlacement: UtilsAssembly.findPlacement times Offset1/2."""
        return self.raw_jcs(joint, ref) * to_placement(joint.offset1 if index == 0 else joint.offset2)

    def raw_jcs(self, joint: Joint, ref) -> Placement:
        """UtilsAssembly.findPlacement(ref, ignoreVertex): the JCS relative to the object the reference names; a datum
        (an element name that is empty) is the whole-part case: an axis's own rotation, else the identity."""
        from . import assembly_jcs as J
        r = self.resolve(ref) if J.is_ref_valid(ref, 2) else None
        if r is None:
            return Placement()
        if r.datum is not None:
            return Placement((0.0, 0.0, 0.0), Rotation(DATUM_JCS.get(r.datum, (0.0, 0.0, 0.0, 1.0))))
        return J.find_placement(r.shape, r.frame, list(ref[1]), joint.joint_type == "Distance")

    def update_jcs(self, joint: Joint):
        """updateJCSPlacements."""
        p1, p2 = self.jcs.get(joint.name, (to_placement(joint.placement1), to_placement(joint.placement2)))
        if not joint.detach1:
            p1 = self.find_placement(joint, joint.reference1, 0)
        if not joint.detach2:
            p2 = self.find_placement(joint, joint.reference2, 1)
        self.jcs[joint.name] = (p1, p2)

    def global_jcs(self, joint: Joint, index: int) -> Placement:
        """UtilsAssembly.getJcsGlobalPlc(Placement1/2, Reference1/2)."""
        ref = joint.reference1 if index == 0 else joint.reference2
        p = self.jcs[joint.name][index]
        r = self.resolve(ref)
        if r is None:
            return p
        return r.part_plc * p if r.obj is None else r.part_plc * r.obj * p

    def set_joint_connectors(self, joint: Joint, refs):
        """Joint.setJointConnectors(joint, refs): the panel's picks, one then two."""
        is_assembly = True
        if len(refs) >= 1:
            joint.reference1 = _ref(refs[0], joint.name)
        else:
            joint.reference1 = None
            self.jcs[joint.name] = (Placement(), self.jcs.get(joint.name, (Placement(), Placement()))[1])
        self.update_jcs(joint)                 # onChanged Reference1: joint.recompute()
        if len(refs) >= 2:
            joint.reference2 = _ref(refs[1], joint.name)
            self.update_jcs(joint)             # onChanged Reference2: joint.recompute()
            self.ensure_unconnected_is_second_ref(joint)
            if joint.joint_type in JOINT_USING_PRESOLVE:
                self.pre_solve(joint)
            elif joint.joint_type in JOINT_PARALLEL_FORBIDDEN:
                self.prevent_parallel(joint)
            if is_assembly:
                self.solve_if_allowed(True)
            else:
                self.update_jcs(joint)
        else:
            joint.reference2 = None
            self.jcs[joint.name] = (self.jcs.get(joint.name, (Placement(), Placement()))[0], Placement())
            self.undo_solve()
            self.undo_pre_solve(joint)

    def pre_solve(self, joint: Joint, save_plc: bool = True) -> bool:
        return self.match_jcs(joint, save_plc)

    def flip_one_part(self, joint: Joint):
        """Joint.flipOnePart (the panel's Reverse button)."""
        self.match_jcs(joint, False, True)

    def match_jcs(self, joint: Joint, save_plc: bool = True, reverse: bool = False) -> bool:
        from . import assembly_jcs as J
        same = J.same_dir(self.global_jcs(joint, 0), self.global_jcs(joint, 1))
        if reverse:
            same = not same
        part1 = joint.reference1[0] if joint.reference1 else None
        part2 = joint.reference2[0] if joint.reference2 else None
        if not part1 or not part2:
            return False
        was = joint.suppressed
        joint.suppressed = True
        part1_connected = self.query("isPartConnected", part1)
        part2_connected = self.query("isPartConnected", part2)
        joint.suppressed = False
        if not part1_connected:
            moving, moving_idx, fixed_idx = part1, 0, 1
        elif not part2_connected:
            moving, moving_idx, fixed_idx = part2, 1, 0
        else:
            return False
        parts_to_move = [moving] + self.query("getDownstreamParts", moving, joint.name)
        if save_plc:
            self._presolve_backup[joint.name] = {p: self.plc[p] for p in parts_to_move}
        moving_jcs = self.global_jcs(joint, moving_idx)
        fixed_jcs = self.global_jcs(joint, fixed_idx)
        if not same:
            moving_jcs = J.flip_placement(moving_jcs)
        transform = fixed_jcs * moving_jcs.inverse()
        for p in parts_to_move:
            self.plc[p] = transform * self.plc[p]
        del was
        return True

    def undo_pre_solve(self, joint: Joint):
        backup = self._presolve_backup.pop(joint.name, None)
        if backup:
            for p, plc in backup.items():
                if p in self.plc:
                    self.plc[p] = plc

    def prevent_parallel(self, joint: Joint):
        """Joint.preventParallel: Angle and Perpendicular cannot start from parallel JCS; one part is turned
        10 degrees about its JCS's X axis."""
        from . import assembly_jcs as J
        if not J.z_parallel(self.global_jcs(joint, 0), self.global_jcs(joint, 1)):
            return
        part1 = joint.reference1[0]
        part2 = joint.reference2[0]
        c1 = self.query("isJointConnectingPartToGround", joint.name, "Reference1")
        c2 = self.query("isJointConnectingPartToGround", joint.name, "Reference2")
        if c2:
            g = self.global_jcs(joint, 1)
            axis = g.rot.mult_vec((1.0, 0.0, 0.0))
            self.plc[part2] = J.rotate_along_axis(self.plc[part2], 10, axis)
        elif c1:
            g = self.global_jcs(joint, 0)
            axis = g.rot.mult_vec((1.0, 0.0, 0.0))
            self.plc[part1] = J.rotate_along_axis(self.plc[part1], 10, axis)

    def ensure_unconnected_is_second_ref(self, joint: Joint):
        part1 = joint.reference1[0] if joint.reference1 else None
        part2 = joint.reference2[0] if joint.reference2 else None
        if not part1 or not part2:
            return
        backup = joint.suppressed
        joint.suppressed = True
        c1 = self.query("isPartConnected", part1)
        c2 = self.query("isPartConnected", part2)
        joint.suppressed = backup
        if not c1 and c2:
            # each assignment as FreeCAD makes it: a reference's onChanged recomputes the joint, and an Offset's
            # (a placement property fires onChanged even when its value does not change) presolves or solves
            ref1 = joint.reference1
            joint.reference1 = joint.reference2
            self.update_jcs(joint)
            joint.reference2 = ref1
            self.update_jcs(joint)
            p1, p2 = self.jcs[joint.name]
            self.jcs[joint.name] = (p2, p1)
            off1 = joint.offset1
            joint.offset1 = joint.offset2
            self.on_changed(joint, "offset1")
            joint.offset2 = off1
            self.on_changed(joint, "offset2")
            joint.detach1, joint.detach2 = joint.detach2, joint.detach1

    def on_changed(self, joint: Joint, prop: str):
        """Joint.onChanged, for a property the panel or the property view set."""
        if prop in ("reference1", "reference2"):
            self.update_jcs(joint)
        if joint.reference1 is None or joint.reference2 is None:
            return
        if prop in ("offset1", "offset2"):
            self.update_jcs(joint)
            presolved = joint.joint_type in JOINT_USING_PRESOLVE and self.pre_solve(joint, False)
            if not presolved:
                self.solve_if_allowed()
            else:
                self.update_jcs(joint)
        if prop == "distance" and joint.joint_type == "Distance":
            self.solve_if_allowed()
        if prop == "angle" and joint.joint_type == "Angle":
            if joint.angle != 0.0:
                self.prevent_parallel(joint)
            self.solve_if_allowed()

    def set(self, joint: Joint, prop: str, value):
        """joint.<Prop> = value, then its onChanged."""
        setattr(joint, prop, joint.normalize(prop, value))
        if prop == "joint_type":
            joint.validate()
        self.on_changed(joint, prop)

    def accept(self, joint: Joint):
        """TaskAssemblyCreateJoint.accept: generatePropertySettings's commands (every placement property set
        again, rounded to 5 decimals in its yaw-pitch-roll form, which for Offset1/2 runs onChanged), then
        assembly.recompute(True): the joints' updateJCSPlacements, then the solve."""
        for prop in self.property_list_order(joint):
            if prop in ("offset1", "offset2"):
                v = to_placement(getattr(joint, prop))
                y, p, r = v.rot.ypr()
                rounded = Placement(tuple(float(f"{c:.5f}") for c in v.pos),
                                    Rotation.from_ypr(round(y, 5), round(p, 5), round(r, 5)))
                setattr(joint, prop, placement_literal(rounded) if not is_identity(rounded) else None)
                self.on_changed(joint, prop)
            elif prop in ("placement1", "placement2"):
                i = 0 if prop == "placement1" else 1
                v = self.jcs[joint.name][i]
                y, p, r = v.rot.ypr()
                rounded = Placement(tuple(float(f"{c:.5f}") for c in v.pos),
                                    Rotation.from_ypr(round(y, 5), round(p, 5), round(r, 5)))
                pair = list(self.jcs[joint.name])
                pair[i] = rounded
                self.jcs[joint.name] = tuple(pair)
        self.recompute()

    @staticmethod
    def property_list_order(joint):
        """The order generatePropertySettings walks a joint's PropertiesList in (the placement properties):
        FreeCAD's dynamic properties sorted by name."""
        return ["offset1", "offset2", "placement1", "placement2"]

    def recompute(self):
        """assembly.recompute(True): each joint's execute (updateJCSPlacements), then AssemblyObject::execute's
        solve (SolveOnRecompute)."""
        for j in self.joints():
            self.update_jcs(j)
        return self.solve()

    def solve_if_allowed(self, store_prev: bool = False):
        """JointObject.solveIfAllowed: SolveInJointCreation (true by default)."""
        return self.solve(store_prev)

    # ── the solver ──
    def solver_doc(self) -> dict:
        from . import assembly_jcs as J
        grounded = self.grounded()
        parts = [{"name": c.name, "label": c.label or c.name, "placement": placement_json(self.plc[c.name]),
                  "grounded": c.name in grounded} for c in self.components()]
        joints = []
        for j in self.joints():
            p1, p2 = self.jcs[j.name]

            def ref(r, j=j):
                if r is None:
                    return None
                res = self.resolve(r)
                part = res.part if res is not None else ""
                geo = J.element_geometry(res.shape, r[1][0]) if res is not None and res.shape is not None and r[1] \
                    else {"geom": "", "radius": 0}
                raw = self.raw_jcs(j, r) if part else Placement()
                out = {"part": part, "subs": list(r[1]), **geo, "jcs": placement_json(raw)}
                if res is not None and res.obj is not None:
                    out["obj"] = placement_json(res.obj)
                return out
            joints.append({
                "name": j.name, "label": j.label or j.name, "type": j.joint_type, "suppressed": j.suppressed,
                "reference1": ref(j.reference1), "reference2": ref(j.reference2),
                "placement1": placement_json(p1), "placement2": placement_json(p2),
                "offset1": placement_json(to_placement(j.offset1)), "offset2": placement_json(to_placement(j.offset2)),
                "detach1": j.detach1, "detach2": j.detach2,
                "distance": float(j.distance), "distance2": float(j.distance2), "angle": float(j.angle),
                "enable_length_min": j.enable_length_min, "enable_length_max": j.enable_length_max,
                "enable_angle_min": j.enable_angle_min, "enable_angle_max": j.enable_angle_max,
                "length_min": float(j.length_min), "length_max": float(j.length_max),
                "angle_min": float(j.angle_min), "angle_max": float(j.angle_max)})
        rigid = [{"name": g.name, "suppressed": g.suppressed, "members": list(g.objects_to_rigid_group)}
                 for g in self.rigid_groups()]
        return {"document": self.document, "origin": self.origin, "parts": parts, "joints": joints,
                "rigid_groups": rigid, "rigid_cache": [[n, placement_json(p)] for n, p in self.rigid_cache]}

    def query(self, op, *args):
        from . import ondsel
        return ondsel.query(self.solver_doc(), op, *args)

    def solve(self, store_prev: bool = False) -> dict:
        """AssemblyObject::solve(storePrev): the placements it finds written back, the joints it swapped
        (getDistanceType, Screw, RackPinion) swapped here too, its messages kept."""
        from . import ondsel
        if store_prev:
            self._previous = [(n, p) for n, p in self.plc.items()]
        out = ondsel.solve(self.solver_doc())
        self._apply(out)
        return out

    def _apply(self, out: dict):
        for name, p in out.get("placements", {}).items():
            if name in self.plc:
                self.plc[name] = to_placement(p)
        jd_of = {jd["name"]: jd for jd in out.get("joints", [])}
        for name in out.get("swapped", []):
            j = self.get(name)
            if isinstance(j, Joint):           # swapJCS: the references swapped, Placement1/2 as it left them
                j.reference1, j.reference2 = j.reference2, j.reference1
                jd = jd_of.get(name)
                if jd:
                    self.jcs[j.name] = (to_placement(jd["placement1"]), to_placement(jd["placement2"]))
        for jd in out.get("joints", []):
            j = self.get(jd["name"])
            if isinstance(j, Joint):          # makeMbdJoint swaps limits given the wrong way round
                for k in ("enable_length_min", "enable_length_max", "enable_angle_min", "enable_angle_max",
                          "length_min", "length_max", "angle_min", "angle_max"):
                    setattr(j, k, jd[k])
        if "rigid_cache" in out:
            self.rigid_cache = [(n, to_placement(p)) for n, p in out["rigid_cache"]]
        for name, members in (out.get("rigid_groups") or {}).items():
            g = self.get(name)                  # getRigidGroups' prop->setValue(validMembers)
            if isinstance(g, RigidGroupJoint):
                g.objects_to_rigid_group = tuple(members)
        self.messages += [("warning", w) for w in out.get("warnings", [])]
        self.messages += [("error", e) for e in out.get("errors", [])]
        self.log += out.get("log", "")
        self.last = out

    def undo_solve(self):
        """AssemblyObject::undoSolve: the placements before the last solve(storePrev)."""
        if not self._previous:
            return
        for n, p in self._previous:
            self.plc[n] = p
        self._previous = []

    def export_asmt(self) -> str:
        from . import ondsel
        return ondsel.export_asmt(self.solver_doc())["asmt"]

    # ── what the file keeps ──
    def write_back(self):
        """The objects with the solved state written into them: component placements, joint references (a swap
        is FreeCAD's too), detached JCS."""
        for c in self.components():
            p = self.plc[c.name]
            c.placement = None if is_identity(p) else placement_literal(p)
        for j in self.joints():
            p1, p2 = self.jcs[j.name]
            j.placement1 = placement_literal(p1) if j.detach1 else None
            j.placement2 = placement_literal(p2) if j.detach2 else None
        return self.objects

    def located(self) -> dict:
        """{component: its part's shape at its Placement} (a TopoDS_Shape each)."""
        from . import assembly_jcs as J
        return {c.name: J.placed(self.shape_of(c.name), self.plc[c.name]) for c in self.components()}

    def status(self) -> dict:
        """ViewProviderAssembly::UpdateSolverInformation's message, from the last solve (the joints by Label)."""
        labels = {o.name: (o.label or o.name) for o in self.objects}
        return solver_message(self.last, len(self.components()), labels)


def solver_message(out: dict | None, n_components: int, labels: dict | None = None) -> dict:
    """The Solver messages panel (TaskAssemblyMessages), as ViewProviderAssembly::UpdateSolverInformation writes
    it: {"state", "text", "link"}."""
    if n_components == 0:
        return {"state": "empty", "text": "Empty Assembly", "link": ""}
    if out is None:
        return {"state": "under_constrained", "text": "Under-constrained: ",
                "link": _dofs((n_components + 1) * 6)}
    dofs = out.get("dof", 0)
    if dofs < 0 or out.get("redundant"):
        names = [(labels or {}).get(n, n) for n in out.get("redundant", [])]
        return {"state": "conflicting_constraints", "text": "Over-constrained: ", "link": f"({_list(names)})"}
    if out.get("status", 0) not in (0, -6) or out.get("solver_status", 0) != 0:
        return {"state": "solver_failed", "text": "Solver failed to converge", "link": ""}
    if dofs > 0:
        return {"state": "under_constrained", "text": "Under-constrained: ", "link": _dofs(dofs)}
    return {"state": "fully_constrained", "text": "Fully constrained", "link": ""}


def _dofs(n):
    """tr("%n Degrees of Freedom", "", dofs): FreeCAD ships no English translation, so Qt fills in %n alone."""
    return f"{n} Degrees of Freedom"


def _list(names, limit=3):
    """ViewProviderAssembly's objListHelper: the first three names, then "and N more"."""
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f" and {len(names) - limit} more"


# ── commands, as FreeCAD's ───────────────────────────────────────────────────────────────────────────────

def unique_name(doc_names, base: str) -> str:
    """Document::getUniqueObjectName: base, then base001, base002, ..."""
    import re
    if base not in doc_names:
        return base
    stem = re.sub(r"\d+$", "", base) or base
    i = 1
    while f"{stem}{i:03d}" in doc_names:
        i += 1
    return f"{stem}{i:03d}"


def rename_label(label: str, new_type: str, taken) -> str:
    """Joint.onChanged("JointType"): the first other type's name found in the Label replaced by the new one's (the
    Label then made unique, as DocumentObject's Label always is)."""
    for old in JOINT_TYPES:
        if old == new_type:
            continue
        if old in label:
            return unique_name(taken, label.replace(old, new_type))
    return label


def create_joint(doc: AssemblyDocument, joint_type: str, ref1, ref2, props: dict | None = None,
                 name: str | None = None, reverse: bool = False) -> Joint:
    """Assembly_CreateJoint<Type> with two picks, as TaskAssemblyCreateJoint makes it: the joint object (Name
    Joint, Label the type), adaptUi's defaults, the picks one then two (setJointConnectors: presolve and solve),
    the panel's values, accept."""
    if joint_type not in JOINT_TYPES:
        raise AssemblyError(f"{joint_type!r} is not a JointType")
    names = [o.name for o in doc.objects]
    jname = name or unique_name(names, "Joint")
    taken = set(doc.labels())
    # createJointObject: Label = the type; then Joint(): JointType = JointTypes (the list, which selects Fixed)
    # and JointType = the type, each onChanged replacing the old type's name in the Label, made unique each time
    label = unique_name(taken, joint_type)
    label = rename_label(label, "Fixed", taken)
    label = rename_label(label, joint_type, taken)
    j = Joint(jname, joint_type, label=label)
    doc.objects.append(j)
    doc.jcs[j.name] = (Placement(), Placement())
    # adaptUi: Gears and Belt radii cannot start at 0
    if joint_type in JOINT_NO_NEGATIVE_DISTANCE:
        if j.distance == 0.0:
            j.distance = 1.0
        if joint_type in ("Gears", "Belt") and j.distance2 == 0.0:
            j.distance2 = 1.0
    doc.set_joint_connectors(j, [ref1])
    doc.set_joint_connectors(j, [ref1, ref2])
    for k, v in (props or {}).items():
        doc.set(j, k, v)
    if reverse:                                  # the panel's Reverse button
        doc.flip_one_part(j)
    doc.accept(j)
    return j


def insert_link(doc: AssemblyDocument, part: str, shape, name: str | None = None, ground_first: bool = True,
                placement=None) -> Link:
    """Assembly_InsertLink for one part: an App::Link named after it; the first one of an ungrounded assembly
    grounded (GroundFirstPart answered Yes), as CommandCreateJoint.createGroundedJoint does."""
    names = [o.name for o in doc.objects]
    lname = name or unique_name(names, part)
    link = Link(lname, part, placement=placement)
    doc.objects.insert(len(doc.components()), link)
    doc.shapes[part] = shape
    doc.plc[lname] = to_placement(placement)
    if ground_first and len(doc.components()) == 1 and not doc.grounded():
        doc.objects.append(GroundedJoint(unique_name([o.name for o in doc.objects], "GroundedJoint"), lname))
    return link


def toggle_grounded(doc: AssemblyDocument, comp: str):
    """Assembly_ToggleGrounded: a GroundedJoint made for the component, or its GroundedJoint deleted."""
    for g in doc.grounded_joints():
        if g.object_to_ground == comp:
            doc.objects.remove(g)
            return None
    g = GroundedJoint(unique_name([o.name for o in doc.objects], "GroundedJoint"), comp)
    doc.objects.append(g)
    return g


# ── JointObject.RigidGroupJoint and CommandCreateJoint.createJointRigidGroupJoint ─────────────────────────────

def _valid_members(doc: AssemblyDocument, g: RigidGroupJoint) -> list:
    """RigidGroupJoint._validMembers: the members that exist and have a Placement, each once."""
    out = []
    for n in g.objects_to_rigid_group:
        if n in doc.plc and n not in out:
            out.append(n)
    return out


def update_stored_positions(doc: AssemblyDocument, g: RigidGroupJoint, force: bool = False) -> bool:
    """RigidGroupJoint.updateStoredPositions: each member's placement relative to the first (the anchor), only
    while the group is suppressed unless forced (as at creation)."""
    if not force and not g.suppressed:
        doc.messages.append(("warning", "Assembly: 'updateStoredPositions' is only available while suppressed."))
        return False
    members = _valid_members(doc, g)
    if len(members) < 2:
        g.rigid_placements = ()
        doc.messages.append(("error", "Assembly: Rigid group needs at least 2 valid components."))
        return False
    if tuple(members) != g.objects_to_rigid_group:
        g.objects_to_rigid_group = tuple(members)
    anchor = doc.plc[members[0]]
    g.rigid_placements = tuple(placement_literal(anchor.inverse() * doc.plc[m]) for m in members)
    doc.messages.append(("message", "Assembly: Rigid group positions updated."))
    return True


def restore_from_placements(doc: AssemblyDocument, g: RigidGroupJoint):
    """RigidGroupJoint.restoreFromPlacements: the members put back where RigidPlacements has them, relative to
    where the anchor is now."""
    members = _valid_members(doc, g)
    placements = list(g.rigid_placements or ())
    if len(members) < 2 or len(members) != len(placements):
        doc.messages.append(("warning", "Assembly: Rigid group sync broken, skipping restore."))
        return
    anchor_now = doc.plc[members[0]]
    for m, rel in zip(members, placements):
        doc.plc[m] = anchor_now * to_placement(rel)


def set_rigid(doc: AssemblyDocument, g: RigidGroupJoint, prop: str, value):
    """A RigidGroupJoint's property set, then its onChanged: a new member list stores the positions again;
    unsuppressing restores the members from RigidPlacements and solves (solveIfAllowed)."""
    if prop not in ("objects_to_rigid_group", "suppressed", "label"):
        raise AssemblyError(f"{prop} is not a property the app sets on a RigidGroupJoint")
    setattr(g, prop, g.normalize(prop, value))
    if prop == "objects_to_rigid_group":
        update_stored_positions(doc, g, True)
    elif prop == "suppressed" and not g.suppressed:
        restore_from_placements(doc, g)
        doc.solve_if_allowed()


def create_rigid_group(doc: AssemblyDocument, parts, name: str | None = None) -> RigidGroupJoint | None:
    """Assembly_CreateJointRigidGroup: the selected components locked together (createJointRigidGroupJoint: a
    RigidGroupJoint in the JointGroup, its positions stored, the document recomputed). Fewer than two: a warning."""
    if len(parts) < 2:
        doc.messages.append(("warning", "Select at least 2 components to create a rigid group"))
        return None
    names = [o.name for o in doc.objects]
    gname = name or unique_name(names, "RigidGroupJoint")
    label = unique_name(set(doc.labels()), "RigidGroupJoint")
    g = RigidGroupJoint(gname, list(parts), label=label if label != gname else None)
    doc.objects.append(g)
    update_stored_positions(doc, g, True)
    doc.recompute()
    return g


# ── what assembly.py's parts() calls ──────────────────────────────────────────────────────────────────

def load(slug: str, objects) -> AssemblyDocument:
    """The document of a project's ASSEMBLY, its parts built (state.build_part)."""
    from .state import build_part
    shapes = {}
    for o in objects:
        if isinstance(o, Link) and o.linked_object not in shapes:
            solid, _ = build_part(slug, o.linked_object)
            shapes[o.linked_object] = solid.wrapped
    return AssemblyDocument(objects, shapes, document=slug)


def parts(slug: str, objects, solve: bool = True) -> dict:
    """{component: its part, located where the solved assembly puts it} (build123d shapes), for the gates. The
    assembly is recomputed as FreeCAD does on opening it, from the placements the file holds; without the solver
    library (ui/ondsel/build.sh native) the file's placements are used as they are."""
    from build123d import Compound, Location
    from . import ondsel
    doc = load(slug, objects)
    if solve and ondsel.available() and doc.joints():
        doc.recompute()
    from .state import build_part
    out = {}
    for c in doc.components():
        solid, _ = build_part(slug, c.linked_object)
        p = doc.plc[c.name]
        loc = Location(p.trsf())
        out[c.name] = solid.moved(loc) if hasattr(solid, "moved") else Compound(solid.wrapped).moved(loc)
    return out


def angle_of(p: Placement) -> float:
    return math.degrees(2 * math.acos(max(-1.0, min(1.0, p.rot.q[3]))))
