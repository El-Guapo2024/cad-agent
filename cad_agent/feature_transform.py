# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's PartDesign transformed features (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/PartDesign/App/FeatureTransformed.cpp, FeatureMirrored.cpp, FeatureLinearPattern.cpp, FeaturePolarPattern.cpp,
#   FeatureMultiTransform.cpp: Copyright (c) 2012 Jan Rheinländer
#   src/Mod/Part/App/LinearPatternExtension.cpp, PolarPatternExtension.cpp: Copyright (c) 2012 Jan Rheinländer
#   src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementBoolean, makeElementTransform): Copyright (c) 2022 Zheng, Lei
"""PartDesign's transformed features: Mirrored, LinearPattern, PolarPattern and MultiTransform, in a FEATURES list.

    Mirrored("Mirrored", ["Pocket"], mirror_plane=("Sketch001", "V_Axis"))
    LinearPattern("LinearPattern", ["Pocket"], direction=("Sketch001", "H_Axis"), length=30, occurrences=4)
    PolarPattern("PolarPattern", ["Pocket"], axis="Z_Axis", angle=360, occurrences=6)
    MultiTransform("MultiTransform", ["Pocket"], transformations=[
        Mirrored("Mirror", mirror_plane="YZ_Plane"),
        LinearPattern("Linear_Pattern", direction="Y_Axis", length=10, occurrences=2)])
    LinearPattern("LinearPattern001", transform_mode="Whole shape", direction="X_Axis", length=50)

Property names are FreeCAD's in snake_case, with FreeCAD's defaults (the objects' own, not the commands', which set a few
more: PartDesign_LinearPattern writes Length 100 and Occurrences 2, PartDesign_PolarPattern Angle 360 and Occurrences 2):

    all          originals (Originals: the features to transform, in any order; they are taken in the Body's order),
                 transform_mode ("Features", FreeCAD's "Transform tool shapes", or "Whole shape", "Transform body"),
                 refine (True), suppressed_indices (SuppressedIndices: occurrences left out, 0 the original)
    Mirrored     mirror_plane: a sketch's axis (("Sketch", "V_Axis"), "H_Axis", "" for its normal, "Axis0" for its first
                 construction line), an origin plane ("XY_Plane"), or a planar face (("Pad", "Face6"))
    LinearPattern direction, reversed, mode ("Extent" or "Spacing"), length (100, Extent's total), offset (10, Spacing's
                 step), spacings (each step, -1 for offset), spacing_pattern, occurrences (2), and the same with a 2 for
                 the second direction (occurrences2 1). A direction is a sketch's axis (H_Axis, V_Axis, N_Axis, Axis0),
                 an origin axis or plane ("X_Axis", "XY_Plane": its normal), a feature's straight edge or planar face
    PolarPattern axis, reversed, mode ("Extent" or "Spacing"), angle (360), offset (120), spacings, spacing_pattern,
                 occurrences (3). An axis is a sketch's axis, an origin axis, or a feature's straight or circular edge
    MultiTransform transformations: Mirrored, LinearPattern and PolarPattern calls of their own (no originals), applied
                 one after the other, each to every occurrence the ones before it made

What is built follows Transformed::execute: the transformations of the subclass, each original's AddSubShape (a Pad's
or Pocket's tool, a primitive's shape) moved by every one but the first, then fused to the support (an additive original)
or cut from it (a subtractive one) in one boolean per original, or in "Whole shape" mode the whole support fused with its
copies. An occurrence that does not touch the support is not an error: FreeCAD's Body allows compounds (AllowCompound
True), so an added occurrence stays as a solid of its own and a cut that misses removes nothing.
"""
from __future__ import annotations

import math

from . import feature as F
from .feature_kw import ORIGIN, KwFeature, ref_name

try:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line, GeomAbs_Plane
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS, TopoDS_Iterator
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

TRANSFORM_MODES = ("Features", "Whole shape")
PATTERN_MODES = ("Extent", "Spacing")
CONFUSION = 1e-7
ANGULAR = 1e-12                 # Precision::Angular()


# ── the kernel: FreeCAD's TopoShape calls ─────────────────────────────────────────────────────────────────────────

def transformed(shape, trsf):
    """TopoShape::makeElementTransform: a copy for a mirror or a scale, else the shape moved by a location."""
    copy = trsf.ScaleFactor() * trsf.HVectorialPart().Determinant() < 0.0 \
        or abs(abs(trsf.ScaleFactor()) - 1) > CONFUSION
    if copy:
        return BRepBuilderAPI_Transform(shape, trsf, True).Shape().Moved(TopLoc_Location(gp_Trsf()))
    return moved(shape, trsf)


def moved(shape, trsf):
    """TopoShape::move(TopoDS_Shape&, const gp_Trsf&): the transformation's scale factor set to 1 first (above
    TopLoc_Location::ScalePrec). OCCT then calls a gp_Scale form gp_Identity and keeps its translation, so a move by
    a scaling of factor 1 about a point (a MultiTransform's Scaled at its first factor) leaves the shape where it was,
    in FreeCAD and here."""
    if abs(trsf.ScaleFactor()) > 1e-14:
        t = gp_Trsf()
        t.Multiply(trsf)                        # a copy (gp_Trsf has no copy constructor in OCP)
        t.SetScaleFactor(1.0)
        return shape.Moved(TopLoc_Location(t))
    return shape.Moved(TopLoc_Location(trsf))


def _expand(shape, out):
    if shape.ShapeType() != TopAbs_COMPOUND:
        out.append(shape)
        return
    it = TopoDS_Iterator(shape)
    while it.More():
        _expand(it.Value(), out)
        it.Next()


def element_boolean(maker: str, shapes: list, fuzzy: float = -1.0):
    """TopoShape::makeElementBoolean for "fuse", "cut" and "common" (cad_agent/topo_boolean.py)."""
    from .topo_boolean import BooleanError
    from .topo_boolean import element_boolean as boolean
    try:
        return boolean(maker, shapes, fuzzy)
    except BooleanError as e:
        raise F.FeatureError(str(e)) from None


# ── references ────────────────────────────────────────────────────────────────────────────────────────────────────

# App::Origin's features: an axis's direction and a plane's normal (ViewProviderPlane's placements, read from
# freecadcmd: Y_Axis and YZ_Plane at yaw-pitch-roll (90, 0, 90), Z_Axis at (0, -90, 90), XZ_Plane at (0, 0, 90)).
ORIGIN_DIRS = {"X_Axis": (1, 0, 0), "Y_Axis": (0, 1, 0), "Z_Axis": (0, 0, 1),
               "XY_Plane": (0, 0, 1), "XZ_Plane": (0, -1, 0), "YZ_Plane": (1, 0, 0)}


def _split(r):
    return (r, "") if isinstance(r, str) else r


def _sketch_of(name, shapes):
    return shapes.get("_sketches", {}).get(name)


def _index(sub, prefix):
    try:
        return int(sub[len(prefix):])
    except ValueError:
        return -1


def construction_line(sk, axis_id: int):
    """SketchObject::getAxis(axId): the axis_id-th construction line, (start, end - start) in the sketch's plane."""
    n = 0
    for g in sk.geometry:
        if isinstance(g, F.LineSegment) and g.construction:
            if n == axis_id:
                return (g.start[0], g.start[1], 0.0), (g.end[0] - g.start[0], g.end[1] - g.start[1], 0.0)
            n += 1
    return None


def _placed(sk, base, d):
    """Base::Axis *= the sketch's Placement: a point and a direction of the sketch's plane in global coordinates."""
    o, R = sk.placement()
    b = F._matvec(R, base)
    return (b[0] + o[0], b[1] + o[1], b[2] + o[2]), F._matvec(R, d)


SKETCH_AXES = {"H_Axis": (1.0, 0.0, 0.0), "V_Axis": (0.0, 1.0, 0.0), "N_Axis": (0.0, 0.0, 1.0)}


def _element(name, sub, shapes, kind, where):
    """A feature's sub-element (Face6, Edge3) by FreeCAD's index (TopExp::MapShapes order)."""
    shape = shapes.get(name)
    if shape is None:
        raise F.FeatureError(f"{where}: there is no feature {name!r} before it")
    prefix = "Face" if kind == TopAbs_FACE else "Edge"
    i = _index(sub, prefix)
    subs = F._subs(shape, kind)
    if not sub.startswith(prefix) or not 1 <= i <= len(subs):
        return None
    return subs[i - 1]


def _dir(v):
    if math.sqrt(sum(c * c for c in v)) <= 1e-300:
        raise F.FeatureError("gp_Dir() - input vector has zero norm")
    return gp_Dir(*v)


# ── the features ──────────────────────────────────────────────────────────────────────────────────────────────────

class Transformed(KwFeature):
    """PartDesign::Transformed: the properties every transformed feature has, and its execute()."""
    POS = ("originals",)
    COMMON = {"originals": (), "transform_mode": "Features", "refine": True, "suppressed_indices": ()}
    REFS = ("originals",)
    NONE_SELECTED = "No features selected to be transformed."

    def validate(self):
        if self.transform_mode not in TRANSFORM_MODES:
            raise F.FeatureError(f"{self.name}: transform_mode {self.transform_mode!r} is not one of "
                                 f"{', '.join(TRANSFORM_MODES)}")
        self.suppressed_indices = tuple(int(i) for i in self.suppressed_indices)

    # what a subclass gives
    def get_transformations(self, shapes, params, originals) -> list:
        return []

    def has_original_transformation(self) -> bool:
        return True

    def is_suppressed(self, index: int) -> bool:
        return index >= 0 and index in self.suppressed_indices

    def is_multi_transform_child(self) -> bool:
        """Transformed::isMultiTransformChild: FreeCAD's own test, the default TransformMode with no Originals."""
        return self.transform_mode == "Features" and not self.originals

    def sorted_originals(self, shapes) -> list[str]:
        order = shapes.get("_order", [])
        rank = {n: i for i, n in enumerate(order)}
        return sorted(self.originals, key=lambda n: rank.get(n, len(order)))

    def execute(self, solid, shapes, params):
        """Transformed::execute, in the global frame."""
        mode = self.transform_mode
        originals = [] if mode == "Whole shape" else self.sorted_originals(shapes)
        if mode == "Features" and not originals:
            # FreeCAD returns without a shape; the Body has none at this feature
            raise F.FeatureError(self.NONE_SELECTED)
        try:
            trsfs = list(self.get_transformations(shapes, params, originals))
        except (ValueError, TypeError) as e:
            raise F.FeatureError(str(e)) from None
        if not trsfs:
            return solid                    # "No transformations defined, exit silently"
        support = solid
        if support is None:
            if originals and originals[0] in shapes:
                support = shapes[originals[0]]  # getBaseObject: the first original, for a Body with no base
            elif not originals:
                raise F.FeatureError(self.NONE_SELECTED)
        if support is None or support.IsNull():
            raise F.FeatureError("Cannot transform invalid support shape")
        whole_source = support
        addsub = shapes.get("_addsub", {})
        before = shapes.get("_before", {})

        if not self.has_original_transformation() or self.is_suppressed(0):
            if mode == "Whole shape":
                support = None
            else:
                for o in reversed(self.sorted_originals(shapes)):
                    if o not in addsub:
                        continue
                    b, after, additive = before.get(o), shapes.get(o), addsub[o][1]
                    if additive:
                        delta = after if b is None else element_boolean("cut", [after, b])
                        if delta is not None and support is not None:
                            support = element_boolean("cut", [support, delta])
                    elif b is not None:
                        delta = element_boolean("cut", [b, after])
                        if delta is not None:
                            support = delta if support is None else element_boolean("fuse", [support, delta])

        def copies(sup, orig):
            out = [sup] if sup is not None else []
            idx = 1 if self.has_original_transformation() else 0
            for t in trsfs[idx:]:
                if not self.is_suppressed(idx):
                    out.append(transformed(orig, t))
                idx += 1
            return out

        if mode == "Features":
            for o in originals:
                if o not in addsub:
                    raise F.FeatureError("Only additive and subtractive features can be transformed")
                tool, additive = addsub[o]
                if tool is None or tool.IsNull():
                    raise F.FeatureError("Shape of additive/subtractive feature is empty")
                if additive:
                    out = copies(support, tool)
                    if out:
                        support = element_boolean("fuse", out)
                else:
                    out = copies(support, tool)
                    if len(out) > 1:
                        support = element_boolean("cut", out)
        else:
            out = copies(support, whole_source)
            if out:
                support = element_boolean("fuse", out)
        if support is None or support.IsNull():
            return None
        return F._refine(support) if self.refine else support

    # ── the same feature, fed to FreeCAD ──
    def to_freecad(self, ctx):
        prev = ctx.body.Tip
        obj = ctx.body.newObject(self.TYPE_ID, self.name)
        # Transformed::execute links BaseFeature itself (Body::setBaseProperty), after the recompute has ordered the
        # features; the GUI makes the feature on a Body already built. Linked here, one recompute builds it all.
        obj.BaseFeature = prev
        self.fill_freecad(obj, ctx)
        obj.Originals = [ctx.made[o] for o in self.originals]
        obj.TransformMode = self.transform_mode
        obj.Refine = self.refine
        if self.suppressed_indices:
            obj.SuppressedIndices = list(self.suppressed_indices)
        ctx.body.Tip = obj                  # prepareTransformed: "Tip = <the new feature>"
        return obj

    def fill_freecad(self, obj, ctx):
        pass


def freecad_link(r, ctx):
    """A reference as FreeCAD's PropertyLinkSub value: (object, [sub])."""
    name, sub = _split(r)
    obj = ctx.origin[name] if name in ORIGIN else ctx.made[name]
    return (obj, [sub])


class Mirrored(Transformed):
    """PartDesign::Mirrored: the originals and their mirror image in a plane."""
    kind = "Mirrored"
    TYPE_ID = "PartDesign::Mirrored"
    TRANSACTION = "Make Mirrored"
    DEFAULTS = {**Transformed.COMMON, "mirror_plane": None}
    REFS = ("originals", "mirror_plane")
    NONE_SELECTED = "No features selected to be mirrored."

    def plane(self, shapes):
        """Mirrored::getTransformations' axis checkers: the plane's point and normal."""
        r = self.mirror_plane
        if r is None:
            raise F.FeatureError("No mirror plane reference specified")
        name, sub = _split(r)
        sk = _sketch_of(name, shapes)
        if sk is not None:                                 # axisOfSketch
            if not sub:
                base, d = (0.0, 0.0, 0.0), SKETCH_AXES["N_Axis"]
            elif sub == "H_Axis":
                base, d = (0.0, 0.0, 0.0), SKETCH_AXES["V_Axis"]
            elif sub == "V_Axis":
                base, d = (0.0, 0.0, 0.0), SKETCH_AXES["H_Axis"]
            elif sub.startswith("Axis"):
                line = construction_line(sk, _index(sub, "Axis"))
                if line is None:
                    raise F.FeatureError("No valid axis specified")
                (bx, by, bz), (dx, dy, dz) = line
                base, d = (bx + 0.5 * dx, by + 0.5 * dy, bz + 0.5 * dz), (-dy, dx, dz)
            else:
                raise F.FeatureError(f"{self.name}: a sketch's mirror plane is given by its V_Axis, H_Axis, its "
                                     "normal ('') or a construction line (Axis0, ...)")
            return _placed(sk, base, d)
        if name in ORIGIN:
            if name.endswith("_Plane"):                    # axisOfPlane (App::Plane)
                return (0.0, 0.0, 0.0), ORIGIN_DIRS[name]
            raise F.FeatureError("Mirror plane reference must be a sketch axis, a face of a feature or a datum plane")
        if name not in shapes:
            raise F.FeatureError(f"{self.name}: there is no feature {name!r} before it")
        if not sub:                                        # axisOfPlanarShape
            raise F.FeatureError("No direction reference specified")
        face = _element(name, sub, shapes, TopAbs_FACE, self.name)
        if face is None:
            raise F.FeatureError("Failed to extract mirror plane")
        adapt = BRepAdaptor_Surface(TopoDS.Face(face))
        if adapt.GetType() != GeomAbs_Plane:
            raise F.FeatureError("Mirror face must be planar")
        exp = TopExp_Explorer(face, TopAbs_VERTEX)         # Feature::getPointFromFace
        if not exp.More():
            raise F.FeatureError("getPointFromFace(): Not implemented yet for this case")
        p = BRep_Tool.Pnt_s(TopoDS.Vertex(exp.Current()))
        n = adapt.Plane().Axis().Direction()
        return (p.X(), p.Y(), p.Z()), (n.X(), n.Y(), n.Z())

    def get_transformations(self, shapes, params, originals):
        base, d = self.plane(shapes)
        mirror = gp_Trsf()
        mirror.SetMirror(gp_Ax2(gp_Pnt(*base), _dir(d)))
        return [gp_Trsf(), mirror]

    def fill_freecad(self, obj, ctx):
        if self.mirror_plane is not None:
            obj.MirrorPlane = freecad_link(self.mirror_plane, ctx)


def _spacings_updated(spacings, offset, occurrences):
    """LinearPatternExtension/PolarPatternExtension::updateSpacings: a spacing equal to the offset is -1 (use the
    offset), and the list one shorter than the occurrences."""
    out = [-1.0 if s == offset else float(s) for s in spacings]
    target = max(occurrences - 1, 0)
    return (out + [-1.0] * target)[:target]


class _Pattern(Transformed):
    NONE_SELECTED = "No features selected to be patterned."

    def check_mode(self, *keys):
        for k in keys:
            if getattr(self, k) not in PATTERN_MODES:
                raise F.FeatureError(f"{self.name}: {k} {getattr(self, k)!r} is not one of {', '.join(PATTERN_MODES)}")


class LinearPattern(_Pattern):
    """PartDesign::LinearPattern (Part::LinearPatternExtension): copies along one direction, or a grid along two."""
    kind = "LinearPattern"
    TYPE_ID = "PartDesign::LinearPattern"
    TRANSACTION = "Make LinearPattern"
    DEFAULTS = {**Transformed.COMMON,
                "direction": None, "reversed": False, "mode": "Extent", "length": 100.0, "offset": 10.0,
                "spacings": (-1.0,), "spacing_pattern": (0.0,), "occurrences": 2,
                "direction2": None, "reversed2": False, "mode2": "Extent", "length2": 100.0, "offset2": 10.0,
                "spacings2": (0.0,), "spacing_pattern2": (0.0,), "occurrences2": 1}
    REFS = ("originals", "direction", "direction2")

    def validate(self):
        super().validate()
        self.check_mode("mode", "mode2")
        for k in ("spacings", "spacing_pattern", "spacings2", "spacing_pattern2"):
            setattr(self, k, tuple(float(x) for x in getattr(self, k)))

    def direction_of(self, r, shapes):
        """LinearPatternExtension::getDirectionFromProperty: a global direction."""
        name, sub = _split(r)
        sk = _sketch_of(name, shapes)
        if sk is not None:
            if sub in SKETCH_AXES:
                d = SKETCH_AXES[sub]
            elif sub.startswith("Axis"):
                line = construction_line(sk, _index(sub, "Axis"))
                d = line[1] if line is not None else (0.0, 0.0, 0.0)
            elif sub.startswith("Edge"):
                raise F.FeatureError(f"{self.name}: a sketch's edge as the direction is not supported yet; use its "
                                     "axis or a construction line (Axis0, ...)")
            else:
                d = (0.0, 0.0, 0.0)
            return _dir(_placed(sk, (0.0, 0.0, 0.0), d)[1])
        if name in ORIGIN:
            return gp_Dir(*ORIGIN_DIRS[name])
        if name not in shapes:
            raise F.FeatureError(f"{self.name}: there is no feature {name!r} before it")
        if not sub:
            raise F.FeatureError("No direction reference specified")
        if sub.startswith("Face"):
            face = _element(name, sub, shapes, TopAbs_FACE, self.name)
            if face is None:
                raise F.FeatureError("Failed to extract direction plane")
            adapt = BRepAdaptor_Surface(TopoDS.Face(face))
            if adapt.GetType() != GeomAbs_Plane:
                raise F.FeatureError("Direction face must be planar")
            return adapt.Plane().Axis().Direction()
        if sub.startswith("Edge"):
            edge = _element(name, sub, shapes, TopAbs_EDGE, self.name)
            if edge is None:
                raise F.FeatureError("Failed to extract direction edge")
            adapt = BRepAdaptor_Curve(TopoDS.Edge(edge))
            if adapt.GetType() != GeomAbs_Line:
                raise F.FeatureError("Direction edge must be a straight line")
            return adapt.Line().Direction()
        raise F.FeatureError("Direction reference must be edge or face")

    def _steps(self, second, shapes, params):
        """calculateOffsetVector and calculateSteps for one direction: the offsets from the first occurrence."""
        s = "2" if second else ""
        occ = int(round(F.value(getattr(self, "occurrences" + s), params, f"{self.name}.occurrences{s}")))
        if occ <= 1:
            return [gp_Vec()]
        r = getattr(self, "direction" + s)
        mode = getattr(self, "mode" + s)
        offset = F.value(getattr(self, "offset" + s), params, f"{self.name}.offset{s}")
        # syncLengthAndOffset: in Spacing mode FreeCAD keeps Length at Offset times the steps
        length = offset * (occ - 1) if mode == "Spacing" else \
            F.value(getattr(self, "length" + s), params, f"{self.name}.length{s}")
        if r is None:
            vec = gp_Vec()
        else:
            if length < CONFUSION:
                raise F.FeatureError("Pattern length too small")
            vec = gp_Vec(self.direction_of(r, shapes))
            if getattr(self, "reversed" + s):
                vec.Reverse()
            if mode == "Extent":
                vec.Multiply(length / (occ - 1))
        steps = [gp_Vec()]
        if mode == "Spacing":
            spacings = _spacings_updated(getattr(self, "spacings" + s), offset, occ)
            pattern = getattr(self, "spacing_pattern" + s)
            total = 0.0
            for i in range(1, occ):
                if spacings[i - 1] != -1.0:
                    sp = spacings[i - 1]
                elif len(pattern) > 1:
                    sp = pattern[(i - 1) % len(pattern)]
                else:
                    sp = offset
                total += sp
                steps.append(vec.Multiplied(total))
        else:
            steps += [vec.Multiplied(i) for i in range(1, occ)]
        return steps

    def occurrence_counts(self, params):
        return (int(round(F.value(self.occurrences, params, f"{self.name}.occurrences"))),
                int(round(F.value(self.occurrences2, params, f"{self.name}.occurrences2"))))

    def get_transformations(self, shapes, params, originals):
        n1, n2 = self.occurrence_counts(params)
        if n1 < 1 or n2 < 1:
            raise F.FeatureError("At least one occurrence required")
        if n1 == 1 and n2 == 1:
            return [gp_Trsf()]
        steps1, steps2 = self._steps(False, shapes, params), self._steps(True, shapes, params)
        out = []
        for a in steps1:
            for b in steps2:
                t = gp_Trsf()
                t.SetTranslation(a.Added(b))
                out.append(t)
        return out

    def fill_freecad(self, obj, ctx):
        for s in ("", "2"):
            r = getattr(self, "direction" + s)
            if r is not None:
                setattr(obj, "Direction" + s, freecad_link(r, ctx))
            setattr(obj, "Reversed" + s, getattr(self, "reversed" + s))
            setattr(obj, "Mode" + s, getattr(self, "mode" + s))
            ctx.setint(obj, "Occurrences" + s, getattr(self, "occurrences" + s))
            if getattr(self, "mode" + s) == "Spacing":
                ctx.setv(obj, "Offset" + s, getattr(self, "offset" + s))
            else:
                ctx.setv(obj, "Length" + s, getattr(self, "length" + s))
            if not self.is_default("spacings" + s):
                setattr(obj, "Spacings" + s, list(getattr(self, "spacings" + s)))
            if not self.is_default("spacing_pattern" + s):
                setattr(obj, "SpacingPattern" + s, list(getattr(self, "spacing_pattern" + s)))


class PolarPattern(_Pattern):
    """PartDesign::PolarPattern (Part::PolarPatternExtension): copies rotated about an axis."""
    kind = "PolarPattern"
    TYPE_ID = "PartDesign::PolarPattern"
    TRANSACTION = "Make PolarPattern"
    DEFAULTS = {**Transformed.COMMON, "axis": None, "reversed": False, "mode": "Extent", "angle": 360.0,
                "offset": 120.0, "spacings": (-1.0, -1.0, -1.0), "spacing_pattern": (0.0,), "occurrences": 3}
    REFS = ("originals", "axis")

    def validate(self):
        super().validate()
        self.check_mode("mode")
        for k in ("spacings", "spacing_pattern"):
            setattr(self, k, tuple(float(x) for x in getattr(self, k)))

    def rotation_axis(self, shapes):
        """PolarPatternExtension::getRotation: the axis, a point and a direction."""
        r = self.axis
        if r is None:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)     # gp_Ax2()
        name, sub = _split(r)
        sk = _sketch_of(name, shapes)
        if sk is not None:
            if sub in SKETCH_AXES:
                base, d = _placed(sk, (0.0, 0.0, 0.0), SKETCH_AXES[sub])
            elif sub.startswith("Axis"):
                line = construction_line(sk, _index(sub, "Axis"))
                base, d = _placed(sk, *(line or ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))))
            elif sub.startswith("Edge"):
                raise F.FeatureError(f"{self.name}: a sketch's edge as the axis is not supported yet; use its "
                                     "axis or a construction line (Axis0, ...)")
            else:
                base, d = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        elif name in ORIGIN:
            if not name.endswith("_Axis"):
                raise F.FeatureError("Axis reference must be edge of a feature or datum line")
            base, d = (0.0, 0.0, 0.0), ORIGIN_DIRS[name]
        else:
            if name not in shapes:
                raise F.FeatureError(f"{self.name}: there is no feature {name!r} before it")
            if not sub:
                raise F.FeatureError("No axis reference specified")
            if not sub.startswith("Edge"):
                raise F.FeatureError("Axis reference must be an edge")
            edge = _element(name, sub, shapes, TopAbs_EDGE, self.name)
            if edge is None:
                raise F.FeatureError("Failed to extract axis edge")
            adapt = BRepAdaptor_Curve(TopoDS.Edge(edge))
            if adapt.GetType() == GeomAbs_Line:
                p, dd = adapt.Line().Location(), adapt.Line().Direction()
            elif adapt.GetType() == GeomAbs_Circle:
                p, dd = adapt.Circle().Location(), adapt.Circle().Axis().Direction()
            else:
                raise F.FeatureError("Rotation edge must be a straight line, circle or arc of circle")
            base, d = (p.X(), p.Y(), p.Z()), (dd.X(), dd.Y(), dd.Z())
        if self.reversed:
            d = tuple(-c for c in d)
        return base, d

    def get_transformations(self, shapes, params, originals):
        occ = int(round(F.value(self.occurrences, params, f"{self.name}.occurrences")))
        if occ < 1:
            raise F.FeatureError("At least one occurrence required")
        if occ == 1:
            return [gp_Trsf()]
        base, d = self.rotation_axis(shapes)
        axis = gp_Ax1(gp_Pnt(*base), _dir(d))
        angle = 0.0
        if self.mode == "Extent":
            angle = F.value(self.angle, params, f"{self.name}.angle")
            angle = angle / occ if abs(angle - 360.0) < CONFUSION else angle / (occ - 1)
            angle = math.radians(angle)
            if abs(angle) < ANGULAR:
                raise F.FeatureError("Pattern angle can't be null")
        offset = F.value(self.offset, params, f"{self.name}.offset")
        spacings = _spacings_updated(self.spacings, offset, occ)
        pattern = self.spacing_pattern
        out, total = [gp_Trsf()], 0.0
        for i in range(1, occ):
            t = gp_Trsf()
            if self.mode == "Spacing":
                if spacings[i - 1] != -1.0:
                    sp = spacings[i - 1]
                elif len(pattern) > 1:
                    sp = pattern[(i - 1) % len(pattern)]
                else:
                    sp = offset
                total += math.radians(sp)
                t.SetRotation(axis, total)
            else:
                t.SetRotation(axis, angle * i)
            out.append(t)
        return out

    def fill_freecad(self, obj, ctx):
        if self.axis is not None:
            obj.Axis = freecad_link(self.axis, ctx)
        obj.Reversed = self.reversed
        obj.Mode = self.mode
        ctx.setint(obj, "Occurrences", self.occurrences)
        ctx.setv(obj, "Angle", self.angle)
        ctx.setv(obj, "Offset", self.offset)
        if not self.is_default("spacings"):
            obj.Spacings = list(self.spacings)
        if not self.is_default("spacing_pattern"):
            obj.SpacingPattern = list(self.spacing_pattern)


SUBS = ("Mirrored", "LinearPattern", "PolarPattern", "Scaled")      # Scaled: cad_agent/feature_scaled.py


class MultiTransform(Transformed):
    """PartDesign::MultiTransform: its transformations applied one after the other, each to every occurrence before."""
    kind = "MultiTransform"
    TYPE_ID = "PartDesign::MultiTransform"
    TRANSACTION = "Make MultiTransform"
    DEFAULTS = {**Transformed.COMMON, "transformations": []}
    NESTED = ("transformations",)

    def validate(self):
        super().validate()
        for t in self.transformations:
            if not isinstance(t, Transformed) or t.kind not in SUBS:
                raise F.FeatureError(f"{self.name}: its transformations are Mirrored, LinearPattern, PolarPattern and "
                                     f"Scaled, not {t!r}")
            if t.originals or t.transform_mode != "Features":
                raise F.FeatureError(f"{self.name}: {t.name} is one of its transformations, so it has no originals "
                                     "and no transform mode of its own")
        self._first_identity = True
        self._generated: list[bool] = []

    def has_original_transformation(self):
        return self._first_identity

    def is_suppressed(self, index):
        return super().is_suppressed(index) or (0 <= index < len(self._generated) and self._generated[index])

    def get_transformations(self, shapes, params, originals):
        """MultiTransform::getTransformations: the product of its transformations' lists, the later ones outer; a
        Scaled scales each slice of the occurrences before it about their own centres."""
        from .feature_scaled import first_original_cog
        self._generated, self._first_identity = [], True
        if not self.transformations:
            return []
        cog = first_original_cog(shapes, originals)
        instances = None                        # [(trsf, centre, suppressed)]
        for sub in self.transformations:
            ts = sub.get_transformations(shapes, params, originals)
            if instances is None:
                instances = [(t, cog.Transformed(t), sub.is_suppressed(i)) for i, t in enumerate(ts)]
                continue
            if not instances:
                continue                        # an empty product must not restart at the next helper
            if sub.kind == "Scaled":
                if not ts or len(instances) % len(ts):
                    raise ValueError("Number of occurrences must be a divisor of previous number of occurrences")
                step, old, scaled = len(instances) // len(ts), iter(instances), []
                for i, t in enumerate(ts):
                    s = sub.is_suppressed(i)
                    for _ in range(step):
                        old_t, centre, old_s = next(old)
                        if t.ScaleFactor() > CONFUSION:
                            c = gp_Trsf()
                            c.SetScale(centre, t.ScaleFactor())
                            c.Multiply(old_t)
                        else:
                            c, centre = t.Multiplied(old_t), centre.Transformed(t)
                        scaled.append((c, centre, old_s or s))
                instances = scaled
                continue
            instances = [(t.Multiplied(old), centre.Transformed(t), old_s or sub.is_suppressed(i))
                         for i, t in enumerate(ts) for old, centre, old_s in instances]
        if not instances:
            self._generated = [True]
            return [gp_Trsf()]
        first = instances[0][0]
        for row in range(1, 4):
            for col in range(1, 5):
                if abs(first.Value(row, col) - (1.0 if row == col else 0.0)) > CONFUSION:
                    self._first_identity = False
        self._generated = [s for _, _, s in instances]
        return [t for t, _, _ in instances]

    def to_freecad(self, ctx):
        obj = super().to_freecad(ctx)
        subs = []
        for t in self.transformations:
            sub = ctx.body.newObject(t.TYPE_ID, t.name)
            t.fill_freecad(sub, ctx)
            sub.Refine = t.refine
            if t.suppressed_indices:
                sub.SuppressedIndices = list(t.suppressed_indices)
            subs.append(sub)
        obj.Transformations = subs
        if not subs and obj.BaseFeature is not None:
            # CmdPartDesignMultiTransform: "Shape = <the Tip>.Shape", so the new feature shows the Body until it has
            # a transformation (execute leaves the shape alone while there is none)
            ctx.doc.recompute()
            obj.Shape = obj.BaseFeature.Shape
        ctx.body.Tip = obj
        return obj


TRANSFORMED = {c.kind: c for c in (Mirrored, LinearPattern, PolarPattern, MultiTransform)}


