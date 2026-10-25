# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's Part features that stand alone (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each
# file LGPL-2.1-or-later as it states:
#   src/Mod/Part/App/PartFeatures.cpp (Reverse, RuledSurface): Copyright (c) 2011 Werner Mayer
#   src/Mod/Part/App/FeatureScale.cpp: Copyright (c) 2023 Wanderer Fan
#   src/Mod/Part/App/FeatureFace.cpp: Copyright (c) 2011 Werner Mayer
#   src/Mod/Part/App/FaceMaker.cpp (addShape, useCompound): Copyright (c) 2016 Victor Titov (DeepSOIC)
#   src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementRuledSurface): Copyright (c) 2022 Zheng, Lei; 2023 Ondsel
"""Four Part objects that need no panel of their own:

    Part.Reverse("Box_rev", "Box")                        Part::Reverse (Part_ReverseShape): the source's shape with
                                                          its orientation reversed, where the source sits
    Part.Scale("Scale", "Box", scale=2.0)                 Part::Scale (Part_Scale): the base scaled about the origin,
    Part.Scale("Scale", "Box", uniform=False,             uniformly or per axis
               x_scale=2.0, z_scale=0.5)
    Part.Face("Face", ["Sketch", "Other"])                Part::Face (Part_MakeFace, "Face From Wires"): faces from
                                                          the wires of its Sources, through a face maker
    Part.RuledSurface("Ruled", ("Box", "Edge9"),          Part::RuledSurface (Part_RuledSurface): a face between two
                     ("Box", "Edge10"))                   edges, or a shell between two wires

Property names and defaults are FreeCAD's: a Reverse's source; a Scale's base, uniform (True), uniform_scale (1.0),
x_scale, y_scale and z_scale (1.0); a Face's sources and face_maker_class ("Part::FaceMakerUnified" on a new object,
as Face::setupObject sets it; a document written before that says Cheese) and a RuledSurface's curve1, curve2 and
orientation ("Automatic", "Forward", "Reversed").

A Reverse's Placement is its source's: Reverse::execute takes the source's placed shape and leaves its Placement on the
object, so the reversed geometry is the source's own (built_shape) and Context.add moves it to the source's Placement
(base_placement). A Scale's, Face's and RuledSurface's shapes are built from the sources' placed shapes and sit at
their own Placement (identity, unless attached).
"""
from __future__ import annotations

from . import feature as F
from .feature_part import PartObject, compound, register
from .feature_part_face import MAKERS, make_face

try:
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve, BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_GTransform, BRepBuilderAPI_Transform
    from OCP.BRepFill import BRepFill
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_REVERSED, TopAbs_WIRE
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_GTrsf, gp_Pnt, gp_Trsf, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass


class Reverse(PartObject):
    """Part::Reverse (Part_ReverseShape): its Source's shape with its orientation reversed, at the Source's Placement."""
    kind, TYPE_ID, TRANSACTION = "Part.Reverse", "Part::Reverse", "Reverse"
    POS = ("source",)
    REFS = ("source",)
    INPUTS = ()                     # ViewProviderReverse claims no children: the source stays at the top of the tree
    HIDES = ()                      # and the command leaves it shown
    DEFAULTS = {"source": None, **PartObject.COMMON}

    def built_shape(self, ctx, params):
        """The source's own reversed geometry: Reverse::execute's myShape.Reversed(), before the Placement it takes
        from the source (base_placement)."""
        if self.source is None:
            raise F.FeatureError("No part object linked.")
        from . import attacher as A
        shape = ctx.shape(self.source, f"{self.name}.Source")
        pl = ctx.placements.get(self.source, A.Placement())
        return shape.Moved(TopLoc_Location(pl.inverse().trsf())).Reversed()

    def base_placement(self, ctx, params):
        from . import attacher as A
        if self.source is None:
            return super().base_placement(ctx, params)
        return ctx.placements.get(self.source, A.Placement())


class Scale(PartObject):
    """Part::Scale (Part_Scale): its Base's placed shape scaled about the origin, uniformly or along each axis."""
    kind, TYPE_ID, TRANSACTION = "Part.Scale", "Part::Scale", "Scale"
    POS = ("base",)
    REFS = ("base",)
    INPUTS = ("base",)
    HIDES = ("base",)               # DlgScale::apply hides the shape it scaled
    DEFAULTS = {"base": None, "uniform": True, "uniform_scale": 1.0, "x_scale": 1.0, "y_scale": 1.0,
                "z_scale": 1.0, **PartObject.COMMON}

    def shape(self, ctx, params):
        if self.base is None:
            raise F.FeatureError("No object linked")
        src = ctx.shape(self.base, f"{self.name}.Base")
        if self.uniform:
            # Scale::uniformScale: BRepBuilderAPI_Transform(shape, gp_Trsf().SetScale(origin, factor)), not copied.
            t = gp_Trsf()
            t.SetScale(gp_Pnt(0.0, 0.0, 0.0), F.value(self.uniform_scale, params, "UniformScale"))
            scaled = BRepBuilderAPI_Transform(src, t).Shape()
        else:
            # Scale::nonuniformScale: a copy first, then BRepBuilderAPI_GTransform with the diagonal matrix.
            m = gp_GTrsf()
            for i, (v, prop) in enumerate(((self.x_scale, "XScale"), (self.y_scale, "YScale"),
                                           (self.z_scale, "ZScale")), 1):
                m.SetValue(i, i, F.value(v, params, prop))
            scaled = BRepBuilderAPI_GTransform(BRepBuilderAPI_Copy(src).Shape(), m, True).Shape()
        # The result carries the source placement's residue in its Location (the scaling is baked into the geometry
        # around it). Feature::onChanged sets the Shape's location to the object's Placement whenever Shape is set
        # during a recompute, and Scale's is identity unless attached: the stored shape is the result without it.
        return scaled.Located(TopLoc_Location())


class Face(PartObject):
    """Part::Face (Part_MakeFace, "Face From Wires"): faces made from the wires of its Sources by one face maker."""
    kind, TYPE_ID, TRANSACTION = "Part.Face", "Part::Face", "Make face"
    POS = ("sources",)
    REFS = ("sources",)
    INPUTS = ("sources",)
    HIDES = ()                      # CmdPartMakeFace leaves the sources shown
    DEFAULTS = {"sources": (), "face_maker_class": "Part::FaceMakerUnified", **PartObject.COMMON}
    ENUMS = {"face_maker_class": MAKERS}

    def shape(self, ctx, params):
        if not self.sources:
            raise F.FeatureError("No shapes linked")
        shapes = [ctx.shape(r, f"{self.name}.Sources") for r in self.sources]
        # Face::execute: one compound link is its useCompound (each child addShape'd); otherwise each shape is
        # addShape'd. A compound of the links hands make_face the same children in the same order.
        sh = shapes[0] if len(shapes) == 1 and shapes[0].ShapeType() == TopAbs_COMPOUND else compound(shapes)
        face = make_face(sh, self.face_maker_class)
        if face is None or face.IsNull():
            raise F.FeatureError("Creating face failed (null shape result)")
        return face


class RuledSurface(PartObject):
    """Part::RuledSurface (Part_RuledSurface): a face between two edges or a shell between two wires."""
    kind, TYPE_ID, TRANSACTION = "Part.RuledSurface", "Part::RuledSurface", "Create ruled surface"
    POS = ("curve1", "curve2")
    REFS = ("curve1", "curve2")
    INPUTS = ("curve1", "curve2")
    HIDES = ()                      # ViewProviderRuledSurface leaves the curves shown
    DEFAULTS = {"curve1": None, "curve2": None, "orientation": "Automatic", **PartObject.COMMON}
    ENUMS = {"orientation": ("Automatic", "Forward", "Reversed")}

    def shape(self, ctx, params):
        shapes = []
        for key in ("curve1", "curve2"):
            link = getattr(self, key)
            if link is None:
                raise F.FeatureError("No shape linked.")
            shapes.append(ctx.shape(link, f"{self.name}.{key.title()}"))
        try:
            return ruled_surface(shapes, self.orientation)
        except F.FeatureError:
            # makeElementRuledSurface's own errors are Base::CADKernelError / NullShapeException, which
            # RuledSurface::execute's catch (Standard_Failure&) misses: FreeCAD reports the general message.
            raise F.FeatureError("General error in RuledSurface::execute()") from None


def _curve(shape):
    """makeElementRuledSurface's reduction of one input to an edge or a wire."""
    if shape is None or shape.IsNull():
        raise F.FeatureError("Null input shape")
    kind = shape.ShapeType()
    if kind in (TopAbs_EDGE, TopAbs_WIRE):
        return shape
    wires = F._subs(shape, TopAbs_WIRE)
    if len(wires) > 1:                              # getSubTopoShape(TopAbs_WIRE, 1)
        return wires[0]
    edges = F._subs(shape, TopAbs_EDGE)
    if not edges:
        raise F.FeatureError("Input shape has no edge")
    if len(edges) == 1:                             # getSubTopoShape(TopAbs_EDGE, 1)
        return edges[0]
    made = F._wires([TopoDS.Edge(e) for e in edges])    # makeElementWires
    if not made:
        raise F.FeatureError("Null input shape")
    if len(made) > 1:
        raise F.FeatureError("Input shape forms more than one wire")
    return made[0]


def _adaptor(curve):
    """BRepAdaptor_HCurve for an edge, BRepAdaptor_HCompCurve for a wire (their Value/FirstParameter/LastParameter)."""
    return BRepAdaptor_Curve(TopoDS.Edge(curve)) if curve.ShapeType() == TopAbs_EDGE \
        else BRepAdaptor_CompCurve(TopoDS.Wire(curve))


def ruled_surface(shapes, orientation="Automatic"):
    """TopoShape::makeElementRuledSurface(shapes, orientation): the two shapes reduced to edges or wires, the second
    reversed where the fill would be twisted, then BRepFill::Face or BRepFill::Shell."""
    if len(shapes) != 2:
        raise F.FeatureError("Wrong number of input shapes")
    curves = [_curve(s) for s in shapes]
    if curves[0].ShapeType() != curves[1].ShapeType():      # an edge becomes a wire, to match the other
        for i, curve in enumerate(curves):
            if curve.ShapeType() == TopAbs_EDGE:
                curves[i] = F._wires([TopoDS.Edge(curve)])[0]
    s1, s2 = curves
    is_wire = s1.ShapeType() == TopAbs_WIRE

    if orientation == "Automatic":
        a1, a2 = _adaptor(s1), _adaptor(s2)
        p1 = a1.Value(0.9 * a1.FirstParameter() + 0.1 * a1.LastParameter())
        p2 = a1.Value(0.1 * a1.FirstParameter() + 0.9 * a1.LastParameter())
        if s1.Orientation() == TopAbs_REVERSED:
            p1, p2 = p2, p1
        p3 = a2.Value(0.9 * a2.FirstParameter() + 0.1 * a2.LastParameter())
        p4 = a2.Value(0.1 * a2.FirstParameter() + 0.9 * a2.LastParameter())
        if s2.Orientation() == TopAbs_REVERSED:
            p3, p4 = p4, p3
        n1 = gp_Vec(p1, p2).Crossed(gp_Vec(p1, p3))         # triangles (p1, p2, p3) and (p4, p3, p2)
        n2 = gp_Vec(p4, p3).Crossed(gp_Vec(p4, p2))
        if n1.Dot(n2) < 0:                                  # twisted: reverse the second curve
            s2 = s2.Reversed()
    elif orientation == "Reversed":
        s2 = s2.Reversed()

    ruled = BRepFill.Shell_s(TopoDS.Wire(s1), TopoDS.Wire(s2)) if is_wire \
        else BRepFill.Face_s(TopoDS.Edge(s1), TopoDS.Edge(s2))
    return ruled.Located(TopLoc_Location())


MISC = (Reverse, Scale, Face, RuledSurface)
register(*MISC)
