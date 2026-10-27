# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's sub-assemblies (src/Mod/Assembly, Copyright (c) 2023 Ondsel <development@ondsel.com>):
# App/AssemblyLink.cpp (Rigid, LinkedObject, onChanged's Rigid switch, updateParentJoints, updateContents,
# synchronizeComponents, synchronizeJoints, handleJointReference, numberOfComponents), App/AssemblyUtils.cpp's
# collectComponentsRecursively and getMovingPartFromSel's flexible case, CommandInsertLink.py's insertion of an Assembly
# (Rigid sub-assemblies, handleFirstInsertion's grounding of a flexible one) and Gui/ViewProviderAssemblyLink.cpp's
# Turn flexible / Turn rigid.
"""Sub-assemblies: an Assembly::AssemblyLink in a project's ASSEMBLY, linking the Assembly of another project.

FreeCAD's AssemblyLink links an Assembly of another document. Here a project's assembly.py is its Assembly's document
(docs/EDITING_PLAN.md, "Sub-assemblies"), so the link names a sibling project, whose ASSEMBLY is the sub-assembly:

    Assembly.AssemblyLink("Assembly001", "gantry", placement=((50.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)),
                          components=[["Plate001", "Plate"], ["Pin", "Pin"]], label="Assembly")

The link mirrors the sub-assembly's components (synchronizeComponents): each is an App::Link of this document, named as
FreeCAD names it (the source's Name made unique here), stored with the source's name so the names stay. A rigid link
(Rigid, the default) is one body of this Assembly: its Placement is solved here, its children keep the source's
placements. A flexible one has the identity Placement; its children are components of this Assembly, placed by its
solve (placements=[[child, P], ...] in the entry), and its JointGroup holds copies of the source's joints
(synchronizeJoints, joints=[[copy, source], ...]), pointed at the children, which this Assembly solves with its own.
A reference into a rigid link is (link, ["Child.Face3", "Child.Edge1"]), into a flexible one's child (child, ["Face3",
"Edge1"]), as getComponentReference makes them.
"""
from __future__ import annotations

from . import assembly_wb as W
from .attacher import Placement


class AssemblyLink(W.AsmObject):
    """Assembly::AssemblyLink: LinkedObject (a project whose assembly.py has an ASSEMBLY), Rigid, Placement, and the
    mirrored contents (components, joints, a flexible link's children's placements)."""
    kind = "AssemblyLink"
    TYPE_ID = "Assembly::AssemblyLink"
    POS = ("linked_object",)
    DEFAULTS = {"linked_object": None, "rigid": True, "placement": None, "label": None,
                "components": (), "joints": (), "placements": ()}
    PLACEMENTS = ("placement",)
    TRANSACTION = "Insert Component"

    def normalize(self, key, v):
        if key in ("components", "joints"):
            out = []
            for x in v or ():
                if not (isinstance(x, (list, tuple)) and len(x) == 2 and all(isinstance(s, str) and s for s in x)):
                    raise W.AssemblyError(f"{self.name}.{key}: {x!r} is not [name here, name in the sub-assembly]")
                out.append((x[0], x[1]))
            return tuple(out)
        if key == "placements":
            out = []
            for x in v or ():
                if not (isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[0], str)):
                    raise W.AssemblyError(f"{self.name}.placements: {x!r} is not [child, placement]")
                out.append((x[0], W.placement_literal(W.to_placement(x[1]))))
            return tuple(out)
        if key == "rigid":
            return bool(v)
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key in ("components", "joints", "placements"):
            return [list(x) for x in v]
        return super().source_value(key, v)

    def validate(self):
        if not isinstance(self.linked_object, str) or not self.linked_object:
            raise W.AssemblyError(f"{self.name}: an AssemblyLink names the project whose Assembly it links")

    def references(self):
        return []

    def children(self) -> list[str]:
        return [c for c, _ in self.components]


class SubSource:
    """The linked Assembly as its document holds it: its objects (the source ASSEMBLY list), its components' shapes
    ({part: TopoDS_Shape}) and Placements."""

    def __init__(self, project: str, objects, shapes: dict):
        self.project = project
        self.objects = list(objects)
        self.shapes = dict(shapes)
        nested = [o.name for o in self.objects if isinstance(o, AssemblyLink)]
        if nested:
            raise W.AssemblyError(f"{project}: its Assembly links sub-assemblies of its own ({', '.join(nested)}); "
                                  "a sub-assembly inside a sub-assembly is not ported")

    def components(self) -> list[W.Link]:
        return [o for o in self.objects if isinstance(o, W.Link)]

    def get(self, name):
        return next((o for o in self.objects if o.name == name), None)

    def placement(self, name) -> Placement:
        return W.to_placement(self.get(name).placement)

    def joints(self) -> list[W.Joint]:
        """AssemblyObject::getJoints(false, false): the joints that are not suppressed, with two parts that differ."""
        out = []
        for j in self.objects:
            if not isinstance(j, W.Joint) or j.suppressed:
                continue
            p1 = j.reference1[0] if j.reference1 else None
            p2 = j.reference2[0] if j.reference2 else None
            if not p1 or not p2 or p1 == p2:
                continue
            out.append(j)
        return out

    def grounded(self) -> list[str]:
        return [g.object_to_ground for g in self.objects if isinstance(g, W.GroundedJoint)]


def load_source(project: str) -> SubSource:
    """A sibling project's Assembly, its components' parts built (state.build_part)."""
    from . import assembly_edit as E
    from . import state as st
    path = st.project_dir(project) / "assembly.py"
    objs = E.objects_of(path.read_text()) if path.exists() else None
    if not objs:
        raise W.AssemblyError(f"{project!r} has no Assembly (its assembly.py has no ASSEMBLY list)")
    shapes = {}
    for o in objs:
        if isinstance(o, W.Link) and o.linked_object not in shapes:
            solid, _ = st.build_part(project, o.linked_object)
            shapes[o.linked_object] = solid.wrapped
    return SubSource(project, objs, shapes)


# ── AssemblyLink::updateContents ───────────────────────────────────────────────────────────────────────────

def update_contents(doc, link: AssemblyLink):
    """updateContents: synchronizeComponents, then the JointGroup's copies for a flexible link (synchronizeJoints)."""
    synchronize_components(doc, link)
    if link.rigid:
        doc.sub_joints[link.name] = []          # ensureNoJointGroup
        link.joints = ()
    else:
        synchronize_joints(doc, link)


def synchronize_components(doc, link: AssemblyLink):
    """synchronizeComponents: an App::Link here for each of the source's components (made with the source's Name,
    unique in this document, Label the source's, unique too), the ones whose source went removed; a rigid link's
    children placed as their sources are (syncPlacements)."""
    src = doc.subs[link.name]
    have = {s: c for c, s in link.components}
    out = []
    for o in src.components():
        child = have.get(o.name)
        if child is None:
            child = W.unique_name(doc.all_names(), o.name)
            doc.child_labels[child] = W.unique_name(set(doc.labels()), o.label or o.name)
            if not link.rigid:
                doc.plc[child] = src.placement(o.name)
        out.append((child, o.name))
        doc.child_of[child] = (link.name, o.name)
    gone = [c for c, s in link.components if (c, s) not in out]
    for c in gone:
        doc.child_of.pop(c, None)
        doc.plc.pop(c, None)
        doc.child_plc.pop(c, None)
    link.components = tuple(out)
    for child, s in out:
        doc.child_labels.setdefault(child, s)
        if link.rigid:
            doc.child_plc[child] = src.placement(s)
            doc.plc.pop(child, None)
        else:
            doc.child_plc.pop(child, None)
            doc.plc.setdefault(child, src.placement(s))


def synchronize_joints(doc, link: AssemblyLink):
    """synchronizeJoints: one copy per active joint of the source, in order (copyObject: the source's Name made unique
    here), its properties copied from the source (copyPropertyIfDifferent's list) and its references pointed at this
    link's children (handleJointReference)."""
    src = doc.subs[link.name]
    by_source = {c: s for c, s in link.components}
    to_child = {s: c for c, s in by_source.items()}
    old = list(link.joints)
    copies, pairs = [], []
    for i, j in enumerate(src.joints()):
        name = old[i][0] if i < len(old) else W.unique_name(doc.all_names() + [p[0] for p in pairs], j.name)
        prev = next((x for x in doc.sub_joints.get(link.name, []) if x.name == name), None)
        if prev is None:
            prev = W.Joint(name, j.joint_type, label=W.unique_name(set(doc.labels()), j.label or j.name))
            prev.angle = j.angle                # copyObject copies every property; later only the listed ones
            prev.placement1, prev.placement2 = j.placement1, j.placement2
        for k in ("suppressed", "distance", "distance2", "joint_type", "offset1", "offset2", "detach1", "detach2",
                  "angle_max", "angle_min", "length_max", "length_min", "enable_angle_max", "enable_angle_min",
                  "enable_length_max", "enable_length_min"):
            setattr(prev, k, getattr(j, k))
        for k in ("reference1", "reference2"):
            r = getattr(j, k)
            if r is not None and r[0] in to_child:
                setattr(prev, k, (to_child[r[0]], r[1]))
            elif r is not None:
                doc.messages.append(("warning", f"AssemblyLink: Could not map external component {r[0]} to a local "
                                                f"link for joint {j.name}"))
        copies.append(prev)
        pairs.append((name, j.name))
    doc.sub_joints[link.name] = copies
    link.joints = tuple(pairs)


# ── AssemblyLink::onChanged(Rigid) and updateParentJoints ──────────────────────────────────────────────────────

def set_rigid(doc, link: AssemblyLink, rigid: bool):
    """Rigid set (ViewProviderAssemblyLink's Turn rigid / Turn flexible: "Toggle Rigid"), then onChanged: the
    grounding a flexible link cannot keep removed, updateContents, the Placement moved between the link and its
    children so nothing moves, the parent's joints pointed at the link or at its children (updateParentJoints)."""
    if bool(rigid) == link.rigid:
        return
    link.rigid = bool(rigid)
    children = set(link.children())
    for g in list(doc.grounded_joints()):
        if (g.object_to_ground in children) if link.rigid else (g.object_to_ground == link.name):
            doc.objects.remove(g)
    move = None
    if link.rigid:
        # movePlc, before updateContents: the first child's placement relative to its source's
        if link.components:
            first, src_name = link.components[0]
            move = doc.plc.get(first, Placement()) * doc.subs[link.name].placement(src_name).inverse()
        for c in children:
            doc.plc.pop(c, None)
        doc.plc[link.name] = Placement()
    else:
        for c in children:                  # the children keep where they were drawn (synchronizeComponents leaves
            doc.plc[c] = doc.child_plc.get(c, Placement())   # a flexible link's placements alone)
    update_contents(doc, link)
    if not link.rigid:
        plc = doc.plc.pop(link.name, Placement())
        if not W.is_identity(plc):
            for c in link.children():
                doc.plc[c] = plc * doc.plc[c]
    elif move is not None and not W.is_identity(move):
        doc.plc[link.name] = move
    update_parent_joints(doc, link)


def update_parent_joints(doc, link: AssemblyLink):
    """updateParentJoints: the parent's own joints (getJoints(false, false): not suppressed), each reference that
    named a child of the link now naming the link with the child's name before the sub-elements (rigid), or the
    other way round (flexible); a joint changed is recomputed."""
    children = set(link.children())
    for j in [o for o in doc.objects if isinstance(o, W.Joint) and not o.suppressed]:
        if not (j.reference1 and j.reference2) or j.reference1[0] == j.reference2[0]:
            continue
        touched = False
        for k in ("reference1", "reference2"):
            r = getattr(j, k)
            if link.rigid and r[0] in children:
                setattr(j, k, (link.name, tuple(f"{r[0]}.{s}" for s in r[1])))
                touched = True
            elif not link.rigid and r[0] == link.name and r[1]:
                child = r[1][0].split(".")[0]
                if child in children:
                    n = len(child) + 1
                    setattr(j, k, (child, tuple(s[n:] if len(s) >= n else s for s in r[1])))
                    touched = True
        if touched:
            doc.update_jcs(j)


# ── CommandInsertLink for an Assembly ───────────────────────────────────────────────────────────────────────

def insert_assembly_link(doc, project: str, source: SubSource, name: str | None = None, rigid: bool = True,
                         placement=None, ground_first: bool = True) -> AssemblyLink:
    """TaskAssemblyInsertLink's insertion of an Assembly: an Assembly::AssemblyLink named after the Assembly's Label
    (made unique: the parent is "Assembly" too), LinkedObject the Assembly, recomputed (updateContents, rigid as it is
    made), placed, then Rigid set from "Rigid sub-assemblies"; the first insertion into an ungrounded Assembly grounds
    it, or for a flexible one the child linked to the source's grounded component (or the first child)."""
    lname = name or W.unique_name(doc.all_names(), "Assembly")
    link = AssemblyLink(lname, project, label="Assembly")
    doc.objects.insert(len(doc.component_entries()), link)
    doc.subs[lname] = source
    doc.plc[lname] = Placement()
    update_contents(doc, link)
    doc.plc[lname] = W.to_placement(placement)
    if not rigid:
        set_rigid(doc, link, False)
    if ground_first and len(doc.component_entries()) == 1 and not doc.grounded():
        target = lname
        if not link.rigid:
            src_grounded = source.grounded()
            target = None
            for child, s in link.components:
                if target is None:
                    target = child
                if src_grounded and s == src_grounded[0]:
                    target = child
                    break
        if target is not None:
            doc.objects.append(W.GroundedJoint(W.unique_name(doc.all_names(), "GroundedJoint"), target))
    return link


W.CLASSES[AssemblyLink.kind] = AssemblyLink
W.AssemblyLink = AssemblyLink
