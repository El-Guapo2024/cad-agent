# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's exploded views (src/Mod/Assembly/CommandCreateView.py, Copyright (c) 2023 Ondsel
# <development@ondsel.com>): ExplodedView (its Group of moves, applyMoves, _calculateExplodedPlacements),
# ExplodedViewStep (References, MovementTransform, MoveType Normal/Radial, applyStep), movementLabel,
# isPureRotationMovement, movementEditMode, setMovementDistance, setMovementAngle, rotationCenterFromTransform and the
# panel's adjustDependentMoves; UtilsAssembly.getViewGroup ("Exploded Views", Assembly::ViewGroup) and getComAndSize.
"""Exploded views of an Assembly: Assembly_CreateView's objects in a project's ASSEMBLY.

    Assembly.ExplodedView("Exploded_View", group=["Move", "Move001"], label="Exploded View"),
    Assembly.ExplodedViewStep("Move", references=["Plate", "Pin"], movement_transform=((0.0, 0.0, 20.0),
                              (0.0, 0.0, 0.0, 1.0)), label="TranslationZ"),

An ExplodedView lives in the Assembly's ViewGroup ("Exploded_Views", made with the first view), its moves in the
Assembly (FreeCAD makes each with assembly.newObject("App::FeaturePython", "Move")) and in the view's Group, in order.
A move's References are the components it moves (FreeCAD's (Assembly, ["Plate.", "Pin."]): with "Parts as single
solid" a pick names its component); MovementTransform the move: a Normal move puts each at MovementTransform times
its placement, a Radial one pushes each away from the Assembly's centre by 4 x |MovementTransform.Base| / the
Assembly's size times its offset from it. Nothing moves in the document: the view is shown (the panel open, or the
view selected in the tree) and taken away again.
"""
from __future__ import annotations

import math

from . import assembly_wb as W
from .attacher import Placement, Rotation

MOVE_TYPES = ["Normal", "Radial"]
CONFUSION = 1e-7                       # Precision::Confusion()
ANGULAR = 1e-12                        # Precision::Angular()
SINGLE_PRECISION_EPSILON = 2 ** -23    # SoTransformDragger keeps its position in an SbVec3f


class ViewGroup(W.AsmObject):
    """Assembly::ViewGroup, "Exploded Views": the Assembly's exploded views (getViewGroup makes it)."""
    kind = "ViewGroup"
    TYPE_ID = "Assembly::ViewGroup"
    POS = ()
    DEFAULTS = {"label": None}

    def references(self):
        return []


class ExplodedView(W.AsmObject):
    """CommandCreateView.ExplodedView (App::FeaturePython with a GroupExtension): its moves, in order."""
    kind = "ExplodedView"
    TYPE_ID = "App::FeaturePython"
    PROXY = "ExplodedView"
    POS = ()
    DEFAULTS = {"group": (), "label": None}
    TRANSACTION = "Create Exploded View"

    def normalize(self, key, v):
        if key == "group":
            if isinstance(v, str):
                v = [v]
            return tuple(v or ())
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "group":
            return list(v)
        return super().source_value(key, v)

    def references(self):
        return []


class ExplodedViewStep(W.AsmObject):
    """CommandCreateView.ExplodedViewStep: References, MovementTransform, MoveType."""
    kind = "ExplodedViewStep"
    TYPE_ID = "App::FeaturePython"
    PROXY = "ExplodedViewStep"
    POS = ()
    DEFAULTS = {"references": (), "movement_transform": None, "move_type": "Normal", "label": None}
    PLACEMENTS = ("movement_transform",)

    def normalize(self, key, v):
        if key == "references":
            if isinstance(v, str):
                v = [v]
            return tuple(v or ())
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "references":
            return list(v)
        return super().source_value(key, v)

    def validate(self):
        if self.move_type not in MOVE_TYPES:
            raise W.AssemblyError(f"{self.name}: {self.move_type!r} is not a MoveType ({', '.join(MOVE_TYPES)})")

    @property
    def transform(self) -> Placement:
        return W.to_placement(self.movement_transform)


# ── the move's helpers (CommandCreateView.py's module functions) ─────────────────────────────────────────────

def _angle(rot: Rotation) -> float:
    """Rotation.Angle: the angle about its axis, 0 to 2 pi (getRawValue)."""
    w = max(-1.0, min(1.0, rot.q[3]))
    return 2.0 * math.acos(w) if -1.0 < w < 1.0 else 0.0


def _axis(rot: Rotation):
    x, y, z, w = rot.q
    s = math.sqrt(max(0.0, 1.0 - w * w))
    return (x / s, y / s, z / s) if s > 0 else (0.0, 0.0, 1.0)


def _len(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def is_pure_rotation(t: Placement) -> bool:
    """isPureRotationMovement: a rotation with no translation along its axis."""
    if _angle(t.rot) <= ANGULAR:
        return False
    axis = _axis(t.rot)
    n = _len(axis)
    if n <= CONFUSION:
        return False
    axis = tuple(c / n for c in axis)
    return abs(sum(a * b for a, b in zip(t.pos, axis))) <= CONFUSION


def edit_mode(step: ExplodedViewStep) -> str:
    """movementEditMode: what the step list's spin box edits."""
    if step.move_type == "Radial":
        return "Distance"
    return "Angle" if is_pure_rotation(step.transform) else "Distance"


def movement_label(step: ExplodedViewStep) -> str:
    """movementLabel: Radial Translation, or Translation/Rotation and the axes the vector has a part along."""
    if step.move_type == "Radial":
        return "Radial Translation"
    t = step.transform
    if is_pure_rotation(t):
        movement, vector = "Rotation", _axis(t.rot)
    else:
        movement, vector = "Translation", t.pos
    tolerance = max(CONFUSION, 4 * SINGLE_PRECISION_EPSILON * _len(vector))
    return movement + "".join(a for a, c in zip("XYZ", vector) if abs(c) > tolerance)


def set_distance(step: ExplodedViewStep, distance: float, direction=None):
    """setMovementDistance: the translation's length, its direction and rotation kept."""
    t = step.transform
    if _len(t.pos) > 0:
        d = t.pos
    elif direction is not None and _len(direction) > 0:
        d = tuple(direction)
    elif step.move_type == "Radial":
        d = (1.0, 0.0, 0.0)
    else:
        return None
    n = _len(d)
    d = tuple(c / n for c in d)
    step.movement_transform = W.placement_literal(Placement(tuple(c * max(0.0, distance) for c in d), t.rot))
    return d


def rotation_center(t: Placement):
    """rotationCenterFromTransform: a point on the rotation's axis."""
    angle = _angle(t.rot)
    if angle <= ANGULAR:
        return (0.0, 0.0, 0.0)
    axis = _axis(t.rot)
    n = _len(axis)
    axis = tuple(c / n for c in axis)
    tr = t.pos
    k = sum(a * b for a, b in zip(tr, axis))
    perp = tuple(tr[i] - axis[i] * k for i in range(3))
    cot = 1.0 / math.tan(angle / 2.0)
    cross = (axis[1] * perp[2] - axis[2] * perp[1], axis[2] * perp[0] - axis[0] * perp[2],
             axis[0] * perp[1] - axis[1] * perp[0])
    return tuple((perp[i] + cross[i] * cot) * 0.5 for i in range(3))


def set_angle(step: ExplodedViewStep, angle_deg: float) -> bool:
    """setMovementAngle: the rotation's angle, its axis and centre kept."""
    t = step.transform
    if not is_pure_rotation(t):
        return False
    axis = _axis(t.rot)
    n = _len(axis)
    axis = tuple(c / n for c in axis)
    center = rotation_center(t)
    rot = Rotation.from_axis_angle(axis, math.radians(angle_deg))
    step.movement_transform = W.placement_literal(Placement(center, rot) * Placement(center).inverse())
    return True


def placement_is_identity(t: Placement) -> bool:
    return _len(t.pos) <= CONFUSION and _angle(t.rot) <= ANGULAR


# ── the document's views ──────────────────────────────────────────────────────────────────────────────────

def views(doc) -> list[ExplodedView]:
    return [o for o in doc.objects if isinstance(o, ExplodedView)]


def steps_of(doc, view: ExplodedView) -> list[ExplodedViewStep]:
    out = []
    for n in view.group:
        o = doc.get(n)
        if isinstance(o, ExplodedViewStep):
            out.append(o)
    return out


def _limits(box):
    """TopoShape's BoundBox: BRepBndLib::Add, then SetGap(0.0)."""
    box.SetGap(0.0)
    lo, hi = box.CornerMin(), box.CornerMax()
    return lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()


def com_and_size(doc):
    """UtilsAssembly.getComAndSize(assembly): the centre and diagonal of the Assembly's bounding box (the view
    provider's, in the GUI; headless FreeCAD has none and takes (0, 0, 0) and 100)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from . import assembly_jcs as J
    box = Bnd_Box()
    for _name, shape, plc in doc.leaves():
        BRepBndLib.Add_s(J.placed(shape, plc), box)
    if box.IsVoid():
        return (0.0, 0.0, 0.0), 100.0
    x0, y0, z0, x1, y1, z1 = _limits(box)
    return ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)


def _center(doc, comp: str, plc: Placement):
    """A component's shape's bounding box centre at a placement (obj.Shape.BoundBox.Center)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from . import assembly_jcs as J
    box = Bnd_Box()
    for name, shape, p in doc.leaves():
        if name == comp:
            BRepBndLib.Add_s(J.placed(shape, plc), box)
        elif name in doc.child_of and doc.child_of[name][0] == comp:      # a rigid sub-assembly's children
            BRepBndLib.Add_s(J.placed(shape, plc * doc.child_plc[name]), box)
    if box.IsVoid():
        return plc.pos
    x0, y0, z0, x1, y1, z1 = _limits(box)
    return ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def exploded_placements(doc, view: ExplodedView, headless: bool = False, applied: bool = True):
    """({component: its placement exploded}, the explosion lines [start, end]): the moves one after the other, each
    from where the ones before left the parts. applied is the view as it is shown (applyMoves, applyStep: the parts
    really moved, each line from the part's centre before the move to after it, a Radial move's push from the part's
    centre where it is); else _calculateExplodedPlacements (getExplodedShape's: each line from the part's centre in the
    document, a Radial push from there). Headless FreeCAD has no bounding boxes to take centres from (getComAndSize
    gives (0, 0, 0) and 100 for the Assembly and each part)."""
    placements = {n: doc.plc[n] for n in doc.solver_parts()}
    com, size = ((0.0, 0.0, 0.0), 100.0) if headless else com_and_size(doc)
    final, lines = {}, []
    factor = 1
    for step in steps_of(doc, view):
        refs = [r for r in step.references if r in placements]
        if not refs:
            continue
        t = step.transform
        if step.move_type == "Radial":
            factor = 4 * _len(t.pos) / size
        for r in refs:
            current = placements[r]
            # obj.Shape.BoundBox.Center: where the part is drawn (applied), or the document's shape
            at = current if applied else doc.plc[r]
            start = _center(doc, r, at)
            if step.move_type == "Radial":
                obj_com = (0.0, 0.0, 0.0) if headless else _center(doc, r, at)
                init = tuple(obj_com[i] - com[i] for i in range(3))
                new = Placement(tuple(current.pos[i] + init[i] * factor for i in range(3)), current.rot)
            else:
                new = t * current
            placements[r] = new
            final[r] = new
            delta = new * current.inverse()
            lines.append([start, delta.mult_vec(start)])
    return final, lines


def adjust_dependent_moves(doc, view: ExplodedView, changed: ExplodedViewStep, old_transform: Placement):
    """TaskAssemblyCreateView.adjustDependentMoves: a move changed, the Normal moves after it of the same parts turned
    into the parts' new frame so they keep acting as they did on them."""
    moves = steps_of(doc, view)
    if changed not in moves:
        return
    k = moves.index(changed)
    old = {n: doc.plc[n] for n in doc.solver_parts()}
    new = dict(old)
    for i, move in enumerate(moves):
        names = [r for r in move.references if r in old]
        before = move.transform
        if i > k and move.move_type == "Normal":
            for n in names:
                delta = new[n] * old[n].inverse()
                if placement_is_identity(delta):
                    continue
                move.movement_transform = W.placement_literal(delta * move.transform * delta.inverse())
                break
        t_old = old_transform if move is changed else before
        t_new = move.transform
        for n in names:
            old[n] = t_old * old[n]
            new[n] = t_new * new[n]


def ensure_view_group(doc) -> ViewGroup:
    """UtilsAssembly.getViewGroup: the Assembly's ViewGroup, made ("Exploded Views") with its first view."""
    for o in doc.objects:
        if isinstance(o, ViewGroup):
            return o
    g = ViewGroup(W.unique_name(doc.all_names(), "Exploded_Views"))
    doc.objects.append(g)
    return g


def set_view(doc, moves: list[dict], name: str | None = None) -> ExplodedView:
    """TaskAssemblyCreateView's accept: the view made (createExplodedViewObject: "Exploded View" in the ViewGroup) or
    edited, its moves as the panel left them (each createExplodedStepObject's "Move" in the Assembly, its Label
    movementLabel's), the moves the panel deleted removed."""
    if name is None:
        ensure_view_group(doc)
        # newObject("App::FeaturePython", "Exploded View"): Name and Label "Exploded_View"
        view = ExplodedView(W.unique_name(doc.all_names(), "Exploded_View"))
        doc.objects.append(view)
    else:
        view = doc.get(name)
        if not isinstance(view, ExplodedView):
            raise W.AssemblyError(f"there is no exploded view {name!r}")
    old = {s.name: s for s in steps_of(doc, view)}
    keep = []
    parts = set(doc.solver_parts())
    for m in moves:
        refs = list(m.get("references") or [])
        bad = [r for r in refs if r not in parts]
        if bad:
            raise W.AssemblyError(f"{', '.join(bad)}: not a component of the Assembly")
        step = old.get(m.get("name")) if m.get("name") else None
        if step is None:
            step = ExplodedViewStep(W.unique_name(doc.all_names(), "Move"), move_type=m.get("move_type", "Normal"))
            doc.objects.append(step)
        step.references = tuple(refs)
        step.movement_transform = (None if m.get("movement_transform") is None else
                                   W.placement_literal(W.to_placement(m["movement_transform"])))
        if "move_type" in m:
            step.move_type = m["move_type"]
            step.validate()
        step.label = m.get("label") or movement_label(step)
        keep.append(step.name)
    for n, s in old.items():
        if n not in keep:
            doc.objects.remove(s)
    view.group = tuple(keep)
    return view


def delete_view(doc, view: ExplodedView):
    """ViewProviderExplodedView.onDelete: its moves go with it."""
    for s in steps_of(doc, view):
        doc.objects.remove(s)
    doc.objects.remove(view)


W.CLASSES[ViewGroup.kind] = ViewGroup
W.CLASSES[ExplodedView.kind] = ExplodedView
W.CLASSES[ExplodedViewStep.kind] = ExplodedViewStep
W.ViewGroup, W.ExplodedView, W.ExplodedViewStep = ViewGroup, ExplodedView, ExplodedViewStep
