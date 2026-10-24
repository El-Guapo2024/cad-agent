# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's PartDesign Loft, Pipe and Helix function by function and keeps
# FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text
# is in ../ui/LICENSE.
#
#   Derived from: src/Mod/PartDesign/App/FeatureLoft.cpp (Copyright (c) 2015 Stefan Tröger <stefantroeger@gmx.net>),
#                 src/Mod/PartDesign/App/FeaturePipe.cpp (Copyright (c) 2015 Stefan Tröger <stefantroeger@gmx.net>),
#                 src/Mod/PartDesign/App/FeatureHelix.cpp (Copyright (c) 2010 Juergen Riegel
#                 <FreeCAD@juergen-riegel.net>, (c) 2021 Werner Mayer), src/Mod/PartDesign/App/FeatureAddSub.cpp
#                 (Operation; Copyright (c) 2010 Juergen Riegel), src/Mod/Part/App/TopoShape.cpp (makeSpiralHelix;
#                 Copyright (c) 2002 Jürgen Riegel), src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementLoft,
#                 prepareProfiles, makeElementSolid; Copyright (c) 2022 Zheng, Lei), src/Mod/Part/App/FaceMakerCheese.cpp
#                 (isInside; Copyright (c) 2016 Victor Titov (DeepSOIC)) and src/Mod/PartDesign/Gui/Command.cpp
#                 (CmdPartDesignAdditiveHelix's ReferenceAxis) with src/Mod/PartDesign/Gui/TaskHelixParameters.cpp
#                 (initializeHelix, updateStatus; Copyright (c) 2011 Juergen Riegel)
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
#   This library is free software; you can redistribute it and/or modify it under the terms of the GNU Library
#   General Public License as published by the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
#   implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Library General Public
#   License for more details.
#
# See ../NOTICE.
"""PartDesign's Additive/Subtractive Loft, Pipe and Helix for a FEATURES list (cad_agent/feature.py).

    AdditiveLoft("AdditiveLoft", "Sketch", sections=["Sketch001", ("Sketch002", "Vertex1")], ruled=True)
    AdditivePipe("AdditivePipe", "Profile", spine="Path", mode="Frenet", transition="Round corner")
    SubtractivePipe("SubtractivePipe", "Notch", spine=("Pad", ("Edge1", "Edge5")))
    AdditiveHelix("AdditiveHelix", "Sketch", reference_axis=("Sketch", "V_Axis"), pitch=8.0, height=24.0)

The properties are FreeCAD's in snake_case, with FreeCAD's defaults. A link is FreeCAD's PropertyLinkSub: a feature's
name for the whole of it, (name, "Vertex1") for one element, (name, ("Edge1", "Edge2")) for several.

  Loft (FeatureLoft.cpp)
    profile        Profile: a sketch, or (sketch, "VertexN") for a point
    sections       Sections: [sketch | (sketch, "VertexN") | (feature, "FaceN"), ...], in order
    ruled, closed  Ruled (False), Closed (False: a closed loft goes on from the last section back to the profile)
  Pipe (FeaturePipe.cpp)
    profile        Profile: a sketch
    spine          Spine: a sketch (all of it), or (sketch | feature, ("Edge1", ...)) for some of its edges
    spine_tangent  SpineTangent (False; FreeCAD keeps it but does not read it)
    mode           Mode: "Standard" | "Fixed" | "Frenet" | "Auxiliary" | "Binormal"
    auxiliary_spine, auxiliary_spine_tangent, auxiliary_curvilinear (True)   for mode "Auxiliary"
    binormal       Binormal (0, 0, 0): the constant binormal of mode "Binormal"
    transition     Transition: "Transformed" | "Right corner" | "Round corner"
    transformation Transformation: "Constant" | "Multisection" | "Linear" | "S-shape" | "Interpolation" (the last
                   three are FreeCAD's enumeration only: built as Constant, as FreeCAD builds them)
    sections       Sections: [sketch, ...], used when transformation is "Multisection"
  Helix (FeatureHelix.cpp)
    reference_axis ReferenceAxis: (sketch, "V_Axis" | "H_Axis" | "N_Axis" | "AxisN"), "X_Axis" | "Y_Axis" | "Z_Axis",
                   or (feature, "EdgeN"). Left out: (profile, "V_Axis"), what PartDesign_AdditiveHelix sets.
    mode           Mode: "pitch-height-angle" | "pitch-turns-angle" | "height-turns-angle" | "height-turns-growth";
                   the others follow from the mode's three (Helix::execute)
    pitch (10), height (30), turns (3), angle (0, -89..89 deg), growth (0), left_handed, reversed,
    tolerance (0.1, at least 0.1)
    outside        the deprecated Outside: True is operation "Common" (Helix::onDocumentRestored)
  every one: refine (True); a subtractive one, operation "Subtraction" | "Common" (FeatureAddSub's Operation)

What is built is what each execute() builds, in the same OCCT calls: BRepOffsetAPI_ThruSections per wire, sewn with the
end faces (Loft); BRepOffsetAPI_MakePipeShell per wire of the profile face, with its end faces from Simulate (Pipe);
TopoShape::makeSpiralHelix's path and BRepOffsetAPI_MakePipe with a Frenet trihedron (Helix); then the boolean with
the solid before (Union, Subtraction or Common) and the refine.
"""
from __future__ import annotations

import math

try:                                    # the kernel; FreeCAD's Python reads the vocabulary without it
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeWire, BRepBuilderAPI_RightCorner,
                                    BRepBuilderAPI_RoundCorner, BRepBuilderAPI_Sewing, BRepBuilderAPI_Transformed)
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepLib import BRepLib
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe, BRepOffsetAPI_MakePipeShell, BRepOffsetAPI_ThruSections
    from OCP.GProp import GProp_GProps
    from OCP.Geom import Geom_BezierCurve, Geom_Plane, Geom_SurfaceOfRevolution
    from OCP.Geom2d import Geom2d_Line, Geom2d_TrimmedCurve
    from OCP.GeomAbs import GeomAbs_BSplineSurface, GeomAbs_C1, GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.GeomFill import GeomFill_IsFrenet
    from OCP.IntTools import IntTools_FClass2d
    from OCP.ShapeAnalysis import ShapeAnalysis, ShapeAnalysis_Surface
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_ShapeTolerance, ShapeFix_Solid, ShapeFix_Wire
    from OCP.TopAbs import (TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_IN, TopAbs_SHELL, TopAbs_SOLID,
                            TopAbs_VERTEX, TopAbs_WIRE)
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Iterator, TopoDS_Shell, TopoDS_Solid
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Ax3, gp_Dir, gp_Dir2d, gp_Lin2d, gp_Pnt, gp_Pnt2d, gp_Trsf, gp_Vec, gp_Vec2d
    try:
        from OCP.TColgp import TColgp_Array1OfPnt
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:                 # OCP 8 moved OCCT's collections
        from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

from .feature_kw import KwFeature, ref_name  # noqa: E402  (feature_kw imports feature.py, which imports this last)

CONFUSION = 1e-7                       # Precision::Confusion()
OPERATIONS = ("Subtraction", "Common")  # FeatureAddSub::defineSubtractive's Operation enumeration
PIPE_MODES = ("Standard", "Fixed", "Frenet", "Auxiliary", "Binormal")                    # Pipe::ModeEnums
TRANSITIONS = ("Transformed", "Right corner", "Round corner")                            # Pipe::TransitionEnums
TRANSFORMATIONS = ("Constant", "Multisection", "Linear", "S-shape", "Interpolation")     # Pipe::TransformEnums
HELIX_MODES = ("pitch-height-angle", "pitch-turns-angle", "height-turns-angle", "height-turns-growth")  # ModeEnums
HELIX_ANGLE = (-89.0, 89.0)            # Helix::floatAngle
INT_MAX = 2147483647.0


def link(v, where: str):
    """A PropertyLinkSub as the part file holds it: "Sketch", ("Sketch", "Vertex1") or ("Pad", ("Edge1", "Edge2")).
    FreeCAD's (obj, [""]) and (obj, []) are the whole object; JSON's lists become tuples."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str):
        obj, sub = v
        if isinstance(sub, (list, tuple)):
            subs = tuple(s for s in sub if s != "")
            if not all(isinstance(s, str) for s in subs):
                raise F.FeatureError(f"{where}: {v!r} is not (feature, sub-elements)")
            return obj if not subs else (obj, subs[0]) if len(subs) == 1 else (obj, subs)
        if not isinstance(sub, str):
            raise F.FeatureError(f"{where}: {v!r} is not (feature, sub-element)")
        return obj if sub == "" else (obj, sub)
    raise F.FeatureError(f"{where}: {v!r} is not a link: a feature's name, (feature, \"Vertex1\") or "
                         "(feature, (\"Edge1\", \"Edge2\"))")


def subs_of(r) -> tuple:
    """The sub-element names of a link: () for the whole object."""
    if r is None or isinstance(r, str):
        return ()
    return (r[1],) if isinstance(r[1], str) else tuple(r[1])


class _AddSub(KwFeature):
    """What Loft, Pipe and Helix share: links that may name several sub-elements, the Operation of a subtractive one,
    and the boolean with the solid before (FeatureAddSub::getBooleanMaker)."""
    additive = True
    LINKS: tuple = ()

    def normalize(self, key, v):
        if key in self.LINKS:
            if self.is_ref_list(key):
                if isinstance(v, str):
                    v = [v]
                return tuple(link(x, f"{self.name}.{key}") for x in (v or ()))
            return link(v, f"{self.name}.{key}")
        return super().normalize(key, v)

    def validate(self):
        if not self.additive and self.operation not in OPERATIONS:
            raise F.FeatureError(f"{self.name}: operation {self.operation!r} is not one of {', '.join(OPERATIONS)}")
        if not isinstance(ref_name(self.profile), str):
            raise F.FeatureError(f"a {self.kind} needs a profile, a sketch")

    def maker(self) -> str:
        return "fuse" if self.additive else "cut" if self.operation == "Subtraction" else "common"

    def boolean(self, base, tool):
        from .feature_transform import element_boolean
        return element_boolean(self.maker(), [base, tool])

    def refine_(self, shape):
        """FeatureRefine::refineShapeIfActive."""
        return refine(shape) if self.refine else shape

    def set_common(self, ctx, obj):
        obj.Refine = self.refine
        if not self.additive:
            obj.Operation = self.operation

    def __repr__(self):
        return f"{self.kind}({self.name!r}, {self.profile!r})"


def refine(shape):
    """FeatureRefine's refine, BRepBuilderAPI_RefineModel (FreeCAD's modelRefine.cpp), as feature.py's _refine makes it
    (OCCT's UnifySameDomain: the same merged faces where both merge them) with the faces in RefineModel's order:
    FaceUniter::process removes the faces it merges from the shell and sews the new faces after what is left, planes
    first, then cylinders, then B-spline surfaces, each in the order of the first face it took in."""
    u = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
    u.AllowInternalEdges(False)
    u.Build()
    out = u.Shape()
    if F._count(out, TopAbs_SOLID) != F._count(shape, TopAbs_SOLID):
        return shape
    hist = u.History()
    firsts, sizes, news = [], [], []           # per new face: the index of its first original, how many it took in
    for i, f in enumerate(F._faces(shape)):
        mods = hist.Modified(f)
        if hist.IsRemoved(f) and mods.Extent() == 0:
            continue
        nf = mods.First() if mods.Extent() else f
        for k, n in enumerate(news):
            if n.IsSame(nf):
                sizes[k] += 1
                break
        else:
            news.append(nf)
            firsts.append(i)
            sizes.append(1)

    def rank(face):
        for k, n in enumerate(news):
            if n.IsSame(face):
                if sizes[k] == 1:
                    return (0, 0, firsts[k])
                t = BRepAdaptor_Surface(TopoDS.Face(face)).GetType()
                return (1, {GeomAbs_Plane: 0, GeomAbs_Cylinder: 1, GeomAbs_BSplineSurface: 2}.get(t, 3), firsts[k])
        return (0, 0, len(news))

    b = BRep_Builder()
    solids = []
    for so in F._subs(out, TopAbs_SOLID):
        solid = TopoDS_Solid()
        b.MakeSolid(solid)
        it = TopoDS_Iterator(so)
        while it.More():
            sh = it.Value()
            faces, fit = [], TopoDS_Iterator(sh)
            while fit.More():
                faces.append(fit.Value())
                fit.Next()
            keep = [f for f in faces if rank(f)[0] == 0]
            merged = sorted((f for f in faces if rank(f)[0] == 1), key=rank)
            shell = TopoDS_Shell()
            b.MakeShell(shell)
            for f in keep:
                b.Add(shell, f)
            if merged:                         # FaceUniter: sew the new faces to what is left of the shell
                sew = BRepBuilderAPI_Sewing()
                sew.Add(shell)
                for f in merged:
                    sew.Add(f)
                sew.Perform()
                sewn = sew.SewedShape()
                shell = TopoDS.Shell(sewn) if sewn.ShapeType() == TopAbs_SHELL else shell
            shell.Orientation(sh.Orientation())
            b.Add(solid, shell)
            it.Next()
        solid.Orientation(so.Orientation())
        solids.append(solid)
    return _one(solids) if out.ShapeType() != TopAbs_SOLID else solids[0]


# ── the shapes a link names (Part::Feature::getTopoShape with a sub-element) ────────────────────────────────

def _compound(shapes):
    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for s in shapes:
        b.Add(comp, s)
    return comp


def _one(shapes):
    """TopoShape::makeElementCompound with SingleShapeCompoundCreationPolicy::returnShape."""
    return shapes[0] if len(shapes) == 1 else _compound(shapes)


def sketch_shape(sk):
    """SketchObject::buildShape, placed: the non-construction curves made into wires (makeElementWires), and with
    points, a compound of those wires and a vertex per point. None when the sketch has nothing."""
    loc = TopLoc_Location(F._trsf(sk))
    edges = [TopoDS.Edge(F._edge(g).Moved(loc)) for g in sk.geometry
             if not g.construction and not isinstance(g, F.Point)]
    wires = F._wires(edges) if edges else []
    t = F._trsf(sk)
    verts = [BRepBuilderAPI_MakeVertex(gp_Pnt(*g.point, 0.0).Transformed(t)).Vertex() for g in sk.geometry
             if not g.construction and isinstance(g, F.Point)]
    if not wires and not verts:
        return None
    if not verts:
        return _one(wires)
    return _compound(wires + verts)


def _obj_shape(name, shapes, where):
    sketches = shapes.get("_sketches", {})
    if name in sketches:
        return sketch_shape(sketches[name]), True
    if name in shapes and not name.startswith("_") and name != "Tip" and shapes[name] is not None:
        return shapes[name], False
    raise F.FeatureError(f"{where}: no feature {name!r} before it")


def _sub(shape, sub, where):
    """TopoShape::getSubTopoShape("Edge3"): the element by its index in TopExp::MapShapes order."""
    for prefix, kind in (("Vertex", TopAbs_VERTEX), ("Edge", TopAbs_EDGE), ("Wire", TopAbs_WIRE),
                         ("Face", TopAbs_FACE)):
        if sub.startswith(prefix) and sub[len(prefix):].isdigit():
            subs = F._subs(shape, kind) if shape is not None else []
            i = int(sub[len(prefix):])
            if 1 <= i <= len(subs):
                return subs[i - 1]
            break
    raise F.FeatureError(f"{where}: {sub!r} is not an element of it")


def _free_edges(shape):
    """getSubTopoShapes(TopAbs_EDGE, TopAbs_WIRE): the edges that are in no wire."""
    out, xp = [], TopExp_Explorer(shape, TopAbs_EDGE, TopAbs_WIRE)
    while xp.More():
        out.append(xp.Current())
        xp.Next()
    return out


def _is_inside(wire1, wire2) -> bool:
    """FaceMakerCheese::isInside: wire2's first vertex inside the face wire1 bounds."""
    box1, box2 = Bnd_Box(), Bnd_Box()
    BRepBndLib.Add_s(wire1, box1)
    box1.SetGap(0.0)
    BRepBndLib.Add_s(wire2, box2)
    box2.SetGap(0.0)
    if box1.IsOut(box2):
        return False
    mk = BRepBuilderAPI_MakeFace(TopoDS.Wire(wire1))
    if not mk.IsDone():
        raise F.FeatureError("Failed to create a face from wire in sketch")
    face = _validate_face(mk.Face())
    adapt = BRepAdaptor_Surface(face)
    class2d = IntTools_FClass2d(face, CONFUSION)
    surf = ShapeAnalysis_Surface(Geom_Plane(adapt.Plane()))
    xp = TopExp_Explorer(wire2, TopAbs_VERTEX)
    if xp.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex(xp.Current()))
        return class2d.Perform(surf.ValueOfUV(p, CONFUSION)) == TopAbs_IN
    return False


def _validate_face(face):
    """FaceMakerCheese::validateFace."""
    if BRepCheck_Analyzer(face).IsValid():
        return face
    outer = ShapeAnalysis.OuterWire_s(face)
    fix = ShapeFix_Wire()
    fix.SetFace(face)
    fix.Load(outer)
    fix.Perform()
    mk = BRepBuilderAPI_MakeFace(fix.WireAPIMake())
    xp = TopExp_Explorer(face, TopAbs_WIRE)
    while xp.More():
        if not xp.Current().IsSame(outer):
            fix.Load(TopoDS.Wire(xp.Current()))
            fix.Perform()
            mk.Add(fix.WireAPIMake())
        xp.Next()
    out = mk.Face()
    if not BRepCheck_Analyzer(out).IsValid():
        sf = ShapeFix_Shape(out)
        sf.SetPrecision(CONFUSION)
        sf.SetMaxTolerance(CONFUSION)
        sf.Perform()
        sf.FixWireTool().Perform()
        sf.FixFaceTool().Perform()
        out = TopoDS.Face(sf.Shape())
    return out


def _sort_by_nesting(wires):
    """FeatureLoft.cpp's sortWiresByNesting: outer wires before the wires inside them (a stable sort by depth)."""
    if len(wires) < 2 or not all(BRep_Tool.IsClosed_s(w) for w in wires):
        return wires
    depth = [0] * len(wires)
    try:
        for o in range(len(wires)):
            for i in range(len(wires)):
                if o != i and _is_inside(wires[o], wires[i]):
                    depth[i] += 1
    except Exception:            # non-planar wires keep their order (Standard_Failure)
        return wires
    return [w for _, _, w in sorted(zip(depth, range(len(wires)), wires), key=lambda t: (t[0], t[1]))]


# ── Loft ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _section_shape(label, r, shapes, where, expected=0):
    """Loft::getSectionShape: the wires (or vertices) of a profile or section."""
    name, subs = ref_name(r), subs_of(r)
    shape, is_sketch = _obj_shape(name, shapes, where)
    use_entire = is_sketch and not (subs[0] if subs else "").startswith("Vertex")
    if not subs or "" in subs or use_entire:
        if shape is None:
            raise F.FeatureError(f"Failed to get shape of {label} {name}")
        parts = [shape]
    else:
        parts = [_sub(shape, s, where) for s in subs]
    comp = _one(parts)
    wires = F._subs(comp, TopAbs_WIRE)
    edges = _free_edges(comp)
    if edges:
        wires += F._wires([TopoDS.Edge(e) for e in edges])
    msg = "Sections need to have the same amount of wires or vertices as the base section"
    if wires:
        if expected and expected != len(wires):
            raise F.FeatureError(msg)
        return _sort_by_nesting([TopoDS.Wire(w) for w in wires])
    verts = F._subs(comp, TopAbs_VERTEX)
    if not verts:
        raise F.FeatureError(f"Invalid {label} shape, expecting either wires or vertices")
    if expected and expected != len(verts):
        raise F.FeatureError(msg)
    return [TopoDS.Vertex(v) for v in verts]


def _cog(shape):
    """TopoShape::getCenterOfGravity: the point of a vertex, the centre of a wire's length."""
    if shape.ShapeType() == TopAbs_VERTEX:
        return BRep_Tool.Pnt_s(TopoDS.Vertex(shape))
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(shape, props)
    return props.CentreOfMass()


def _separated(a, b) -> bool:
    """makeElementLoft's checkProfiles: two consecutive profiles that are not the same."""
    if a.IsPartner(b):            # the same TShape: compare the locations' matrices
        t1, t2 = a.Location().Transformation(), b.Location().Transformation()
        return any(t1.Value(i, j) != t2.Value(i, j) for i in (1, 2, 3) for j in (1, 2, 3, 4))
    try:
        b1, b2 = Bnd_Box(), Bnd_Box()
        BRepBndLib.Add_s(a, b1)
        BRepBndLib.Add_s(b, b2)
        if not b1.CornerMin().IsEqual(b2.CornerMin(), CONFUSION):
            return True
        if not b1.CornerMax().IsEqual(b2.CornerMax(), CONFUSION):
            return True
    except Exception:
        return False
    return not _cog(a).IsEqual(_cog(b), CONFUSION)


def make_loft(profiles, ruled: bool, closed: bool, solid: bool = False):
    """TopoShape::makeElementLoft: BRepOffsetAPI_ThruSections over the wires and vertices, CheckCompatibility on,
    the first profile repeated at the end when closed (unless the last is a vertex)."""
    gen = BRepOffsetAPI_ThruSections(solid, ruled)
    gen.SetMaxDegree(5)
    if len(profiles) < 2:
        raise F.FeatureError("Need at least two vertices, edges or wires to create loft face")
    for i, sh in enumerate(profiles):
        if i > 0 and not _separated(sh, profiles[i - 1]):
            raise F.FeatureError("Segments of a loft do not have sufficient separation")
        if sh.ShapeType() == TopAbs_VERTEX:
            gen.AddVertex(TopoDS.Vertex(sh))
        else:
            gen.AddWire(TopoDS.Wire(sh))
    if closed and profiles[-1].ShapeType() != TopAbs_VERTEX:
        first = profiles[0]
        if first.ShapeType() == TopAbs_VERTEX:
            gen.AddVertex(TopoDS.Vertex(first))
        else:
            gen.AddWire(TopoDS.Wire(first))
    gen.CheckCompatibility(True)
    try:
        gen.Build()
        return gen.Shape()
    except Exception as e:                       # Standard_Failure: FreeCAD reports its message
        raise F.FeatureError(_occ_message(e, "Loft: A fatal error occurred when making the loft")) from None


def _occ_message(e, fallback):
    m = str(e).strip()
    return m if m and "OCP" not in m else fallback


def _sew(shapes):
    sewer = BRepBuilderAPI_Sewing()
    sewer.SetTolerance(CONFUSION)
    for s in shapes:
        sewer.Add(s)
    sewer.Perform()
    return sewer.SewedShape()


def make_solid(shape):
    """TopoShape::makeElementSolid: a solid of the shape's shells, oriented closed (BRepLib::OrientClosedSolid)."""
    mk = BRepBuilderAPI_MakeSolid()
    shells = F._subs(shape, TopAbs_SHELL)
    if not shells:
        raise F.FeatureError("No shells or compsolids found in shape")
    for s in shells:
        mk.Add(TopoDS.Shell(s))
    if not mk.IsDone():
        raise F.FeatureError("Failed to create a solid in makeElementSolid!")
    solid = mk.Solid()
    BRepLib.OrientClosedSolid_s(solid)
    return solid


def _outward(solid):
    """The solid reversed when the infinite point classifies inside it (BRepClass3d_SolidClassifier)."""
    sc = BRepClass3d_SolidClassifier(solid)
    sc.PerformInfinitePoint(CONFUSION)
    return solid.Reversed() if sc.State() == TopAbs_IN else solid


def _solids_of(result):
    """Every shell of the result made a solid, oriented outward; the AddSubShape (one, or a compound) and the tool
    (one, or their fuse)."""
    from .feature_transform import element_boolean
    shells = F._subs(result, TopAbs_SHELL) if result is not None and not result.IsNull() else []
    if not shells:
        return None, None
    solids = [_outward(make_solid(s)) for s in shells]
    addsub = _one(solids)
    tool = element_boolean("fuse", solids) if len(solids) > 1 else solids[0]
    return addsub, tool


class _Loft(_AddSub):
    """PartDesign::Loft (FeatureLoft.cpp)."""
    POS = ("profile",)
    DEFAULTS = {"profile": None, "sections": (), "ruled": False, "closed": False, "refine": True}
    REFS = ("profile", "sections")
    LINKS = ("profile", "sections")

    def execute(self, solid, shapes, params):
        where = self.name
        if not self.sections:
            raise F.FeatureError("Loft: At least one section is needed")
        wires = _section_shape("Profile", self.profile, shapes, where)
        groups = [[w] for w in wires]
        for s in self.sections:
            for i, w in enumerate(_section_shape("Section", s, shapes, where, len(groups))):
                groups[i].append(w)
        closed = self.closed and len(self.sections) >= 2       # "invalid for less then 3 sections"
        shells = [make_loft(g, self.ruled, closed) for g in groups]
        front = back = None
        if groups[0][0].ShapeType() != TopAbs_VERTEX:
            front = _profile_face(self, shapes, where)
        if groups[0][-1].ShapeType() != TopAbs_VERTEX:
            back = F._bullseye([g[-1] for g in groups])      # FaceMakerBullseye first of makeElementFace's makers
        result = None
        if front is not None or back is not None:
            result = _sew([s for s in (front, back) if s is not None] + shells)
        if result is None or not F._count(result, TopAbs_SHELL):
            raise F.FeatureError("Loft: Failed to create shell")
        addsub, tool = _solids_of(result)
        shapes.setdefault("_addsub", {})[self.name] = (addsub, self.additive)
        if solid is None:
            return tool                                       # Loft::execute: no base, no refine
        try:
            out = self.boolean(solid, tool)
        except F.FeatureError:
            raise F.FeatureError("Failed to perform boolean operation") from None
        if out is None or out.IsNull() or not F._count(out, TopAbs_SOLID):
            raise F.FeatureError("Resulting shape is not a solid")
        return self.refine_(out)

    def to_freecad(self, ctx):
        obj = ctx.body.newObject(self.TYPE_ID, self.name)
        obj.Profile = _fc_link(ctx, self.profile)
        # CmdPartDesignAdditiveLoft: Sections += [(obj, [''])] for a whole object
        obj.Sections = [(ctx.made[ref_name(s)], list(subs_of(s)) or [""]) for s in self.sections]
        obj.Ruled = self.ruled
        obj.Closed = self.closed
        self.set_common(ctx, obj)
        return obj


def _fc_link(ctx, r):
    if r is None:
        return None
    if isinstance(r, str):
        return ctx.origin[r] if r in getattr(ctx, "origin", {}) else ctx.made[r]
    return (ctx.origin.get(r[0]) or ctx.made[r[0]], list(subs_of(r)))


def _profile_face(feat, shapes, where):
    """ProfileBased::getTopoShapeVerifiedFace (AllowMultiFace, as a new feature has it): the profile sketch's face."""
    name = ref_name(feat.profile)
    sketches = shapes.get("_sketches", {})
    if name not in sketches:
        raise F.FeatureError(f"{where}: no sketch {name!r} before it" if name not in shapes
                             else f"{where}: profile {name!r} is not a sketch")
    return F.profile_face(sketches[name])


class AdditiveLoft(_Loft):
    """PartDesign::AdditiveLoft: lofts the profile through the sections and adds it to the body."""
    kind = "AdditiveLoft"
    TYPE_ID = "PartDesign::AdditiveLoft"
    TRANSACTION = "Make AdditiveLoft"


class SubtractiveLoft(_Loft):
    """PartDesign::SubtractiveLoft: lofts the profile through the sections and removes it from the body."""
    kind = "SubtractiveLoft"
    TYPE_ID = "PartDesign::SubtractiveLoft"
    TRANSACTION = "Make SubtractiveLoft"
    additive = False
    DEFAULTS = {**_Loft.DEFAULTS, "operation": "Subtraction"}


# ── Pipe ─────────────────────────────────────────────────────────────────────────────────────────────────────

def build_pipe_path(shape, subs, where):
    """Pipe::buildPipePath: the wire to sweep along, from the named edges or the whole shape."""
    if shape is None or shape.IsNull():
        return None
    if subs:
        wires = F._wires([TopoDS.Edge(_sub(shape, s, where)) for s in subs])
        return _one(wires)
    t = shape.ShapeType()
    if t == TopAbs_EDGE:
        return shape
    if t == TopAbs_WIRE:
        return _one(F._wires([TopoDS.Edge(e) for e in F._subs(shape, TopAbs_EDGE)]))
    if t == TopAbs_COMPOUND:
        it = TopoDS_Iterator(shape)
        while it.More():
            if it.Value().IsNull():
                raise F.FeatureError("Invalid element in spine.")
            if it.Value().ShapeType() not in (TopAbs_EDGE, TopAbs_WIRE):
                raise F.FeatureError("Element in spine is neither an edge nor a wire.")
            it.Next()
        return _one(F._wires([TopoDS.Edge(e) for e in F._subs(shape, TopAbs_EDGE)]))
    raise F.FeatureError("Spine is neither an edge nor a wire.")


def _wire(shape):
    """TopoDS::Wire, which FreeCAD's catch reports as Standard_TypeMismatch's message."""
    if shape is None or shape.ShapeType() != TopAbs_WIRE:
        raise F.FeatureError("TopoDS::Wire")
    return TopoDS.Wire(shape)


def _placement_of(feat, shapes):
    """ProfileBased::positionByPrevious: the Placement of the solid feature before, else of the profile sketch's
    support. Pipe's Fixed and Binormal modes are in this frame (the feature's own)."""
    ctx = shapes.get("_attach")
    if ctx is None:
        return None
    order = shapes.get("_order", [])
    before = order[:order.index(feat.name)] if feat.name in order else order
    prev = next((n for n in reversed(before) if ctx.kinds.get(n) == "solid"), None)
    if prev is None and "BaseFeature" in shapes:
        prev = "BaseFeature" if "BaseFeature" in ctx.placements else None
    if prev is not None:
        return ctx.placements.get(prev)
    sk = shapes.get("_sketches", {}).get(ref_name(feat.profile))
    return ctx.first_placement(sk) if sk is not None else None


class _Pipe(_AddSub):
    """PartDesign::Pipe (FeaturePipe.cpp)."""
    POS = ("profile",)
    DEFAULTS = {"profile": None, "spine": None, "spine_tangent": False, "auxiliary_spine": None,
                "auxiliary_spine_tangent": False, "auxiliary_curvilinear": True, "mode": "Standard",
                "binormal": (0.0, 0.0, 0.0), "transition": "Transformed", "transformation": "Constant",
                "sections": (), "refine": True}
    REFS = ("profile", "spine", "auxiliary_spine", "sections")
    LINKS = ("profile", "spine", "auxiliary_spine", "sections")

    def validate(self):
        super().validate()
        for key, allowed in (("mode", PIPE_MODES), ("transition", TRANSITIONS), ("transformation", TRANSFORMATIONS)):
            if getattr(self, key) not in allowed:
                raise F.FeatureError(f"{self.name}: {key} {getattr(self, key)!r} is not one of {', '.join(allowed)}")
        b = self.binormal
        if not (isinstance(b, (list, tuple)) and len(b) == 3 and all(isinstance(x, (int, float)) for x in b)):
            raise F.FeatureError(f"{self.name}: binormal {b!r} is not (x, y, z)")
        self.binormal = tuple(float(x) for x in b)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "binormal":
            return tuple(v)
        return super().source_value(key, v)

    def _setup(self, mk, aux, pl):
        """Pipe::setupAlgorithm."""
        mk.SetTolerance(CONFUSION)
        mk.SetTransitionMode({"Transformed": BRepBuilderAPI_Transformed, "Right corner": BRepBuilderAPI_RightCorner,
                              "Round corner": BRepBuilderAPI_RoundCorner}[self.transition])
        if self.mode == "Fixed":
            ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))
            if pl is not None:
                ax = ax.Transformed(_trsf_of(pl))
            mk.SetMode(ax)
        elif self.mode == "Frenet":
            mk.SetMode(True)
        elif self.mode == "Auxiliary":
            mk.SetMode(_wire(aux), self.auxiliary_curvilinear)
        elif self.mode == "Binormal":
            d = gp_Dir(*self.binormal)                  # gp_Dir of (0, 0, 0) is Standard_ConstructionError
            if pl is not None:
                d = d.Transformed(_trsf_of(pl))
            mk.SetMode(d)

    def execute(self, solid, shapes, params):
        where = self.name
        base = solid
        profile = _profile_face(self, shapes, where)
        if self.spine is None:
            raise F.FeatureError("No spine linked")
        sshape, _ = _obj_shape(ref_name(self.spine), shapes, where)
        path = build_pipe_path(sshape, subs_of(self.spine), where)
        aux = None
        if self.mode == "Auxiliary":
            if self.auxiliary_spine is None:
                raise F.FeatureError("No auxiliary spine linked.")
            ashape, _ = _obj_shape(ref_name(self.auxiliary_spine), shapes, where)
            aux = build_pipe_path(ashape, subs_of(self.auxiliary_spine), where)
        groups = [[TopoDS.Wire(w)] for w in F._subs(profile, TopAbs_WIRE)]
        if not groups:
            raise F.FeatureError("Pipe: At least one section is needed when using a single point for profile")
        last_vertex = False
        if self.transformation == "Multisection":
            for s in self.sections:
                sec = _section_face(s, shapes, where)
                ws = F._subs(sec, TopAbs_WIRE)
                if len(ws) > len(groups):
                    raise F.FeatureError("Pipe: Sections need to have the same amount of inner wires (except "
                                         "profile and last section, which can be points)")
                for i, w in enumerate(ws):
                    groups[i].append(TopoDS.Wire(w))
                if not ws:
                    for v in F._subs(sec, TopAbs_VERTEX):
                        if last_vertex:
                            raise F.FeatureError("Pipe: Only the profile and last section can be vertices")
                        last_vertex = True
                        for g in groups:
                            g.append(v)
                if not last_vertex and len(ws) < len(groups):
                    raise F.FeatureError("Multisections need to have the same amount of inner wires as the base "
                                         "section")
        if path is None:
            raise F.FeatureError("Path must not be a null shape")
        pl = _placement_of(self, shapes) if self.mode in ("Fixed", "Binormal") else None
        shells, fronts, backs = [], [], []
        try:
            for g in groups:
                mk = BRepOffsetAPI_MakePipeShell(_wire(path))
                self._setup(mk, aux, pl)
                for w in g:
                    mk.Add(w)
                if not mk.IsReady():
                    raise F.FeatureError("Pipe could not be built")
                mk.Build()
                shell = mk.Shape()
                shells.append(shell)
                closed = shell.ShapeType() in (TopAbs_SHELL, TopAbs_WIRE, TopAbs_EDGE) and BRep_Tool.IsClosed_s(shell)
                if not closed:
                    sim = TopTools_ListOfShape()
                    mk.Simulate(2, sim)
                    if g[0].ShapeType() != TopAbs_VERTEX:
                        fronts.append(sim.First())
                    if g[-1].ShapeType() != TopAbs_VERTEX:
                        backs.append(sim.Last())
        except F.FeatureError:
            raise
        except Exception as e:
            raise F.FeatureError(_occ_message(e, "A fatal error occurred when making the pipe")) from None
        if fronts or backs:
            ends = [_end_face(w) for w in (fronts, backs) if w and F._count(_one(w), TopAbs_EDGE)]
            result = make_solid(_sew(shells + ends))
        else:
            result = make_solid(_compound(shells))
        if not F._count(result, TopAbs_SHELL):
            raise F.FeatureError("Loft: Failed to create shell")
        addsub, tool = _solids_of(result)
        shapes.setdefault("_addsub", {})[self.name] = (addsub, self.additive)
        if base is None:
            if not self.additive:
                raise F.FeatureError("Pipe: There is nothing to subtract from")
            return self.refine_(tool)
        try:
            out = self.boolean(base, tool)
        except F.FeatureError:
            raise F.FeatureError("Failed to perform boolean operation") from None
        if out is None or out.IsNull() or not F._count(out, TopAbs_SOLID):
            raise F.FeatureError("Resulting shape is not a solid")
        return self.refine_(out)

    def to_freecad(self, ctx):
        obj = ctx.body.newObject(self.TYPE_ID, self.name)
        obj.Profile = _fc_link(ctx, self.profile)
        if self.spine is not None:
            obj.Spine = _fc_link(ctx, self.spine)
        obj.SpineTangent = self.spine_tangent
        if self.auxiliary_spine is not None:
            obj.AuxiliarySpine = _fc_link(ctx, self.auxiliary_spine)
        obj.AuxiliarySpineTangent = self.auxiliary_spine_tangent
        obj.AuxiliaryCurvilinear = self.auxiliary_curvilinear
        obj.Mode = self.mode
        obj.Binormal = ctx.App.Vector(*self.binormal)
        obj.Transition = self.transition
        obj.Transformation = self.transformation
        obj.Sections = [(ctx.made[ref_name(s)], list(subs_of(s)) or [""]) for s in self.sections]
        self.set_common(ctx, obj)
        return obj


def _trsf_of(pl):
    """An attacher.Placement as a gp_Trsf."""
    t = gp_Trsf()
    m = pl.rot.matrix()
    (x, y, z) = pl.pos
    t.SetValues(m[0][0], m[0][1], m[0][2], x, m[1][0], m[1][1], m[1][2], y, m[2][0], m[2][1], m[2][2], z)
    return t


def _section_face(r, shapes, where):
    """Pipe's getTopoShapeVerifiedFace(false, false, section): a section sketch's face."""
    name = ref_name(r)
    sketches = shapes.get("_sketches", {})
    if name in sketches:
        return F.profile_face(sketches[name])
    shape, _ = _obj_shape(name, shapes, where)
    subs = subs_of(r)
    sub = _one([_sub(shape, s, where) for s in subs]) if subs else shape
    if not F._count(sub, TopAbs_FACE):
        raise F.FeatureError("Cannot make face from profile")
    return sub


def _end_face(wires):
    """A pipe's end: makeElementFace of the end wires when they are planar (FaceMakerBullseye)."""
    from .feature_revolve import _find_plane
    if _find_plane(_one(wires)) is None:
        raise F.FeatureError("not supported: a pipe whose ends are not planar (FreeCAD fills them with a B-spline "
                             "face, makeElementBSplineFace)")
    return F._bullseye([TopoDS.Wire(w) for w in wires])


class AdditivePipe(_Pipe):
    """PartDesign::AdditivePipe: sweeps the profile along the spine and adds it to the body."""
    kind = "AdditivePipe"
    TYPE_ID = "PartDesign::AdditivePipe"
    TRANSACTION = "Make AdditivePipe"


class SubtractivePipe(_Pipe):
    """PartDesign::SubtractivePipe: sweeps the profile along the spine and removes it from the body."""
    kind = "SubtractivePipe"
    TYPE_ID = "PartDesign::SubtractivePipe"
    TRANSACTION = "Make SubtractivePipe"
    additive = False
    DEFAULTS = {**_Pipe.DEFAULTS, "operation": "Subtraction"}


# ── Helix ────────────────────────────────────────────────────────────────────────────────────────────────────

def make_spiral_helix(rb, rt, height, turns, breakperiod, left_handed):
    """TopoShape::makeSpiralHelix: a wire on the surface of revolution of the line (rb, 0, 0)-(rt, 0, height),
    one edge per breakperiod turns."""
    if breakperiod < 0 or breakperiod > 1000:
        raise F.FeatureError("Break period must be in [0, 1000]")
    if breakperiod == 0:
        breakperiod = 1000
    if turns <= 0:
        raise F.FeatureError("Number of turns must be greater than 0")
    periods = turns / breakperiod
    full = math.floor(periods)
    part = periods - full
    poles = TColgp_Array1OfPnt(1, 2)
    poles.SetValue(1, gp_Pnt(rb, 0, 0))
    poles.SetValue(2, gp_Pnt(rt, 0, height))
    surf = Geom_SurfaceOfRevolution(Geom_BezierCurve(poles), gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)))
    beg = gp_Pnt2d(0, 0)
    d = gp_Vec2d((-1 if left_handed else 1) * breakperiod * 2.0 * math.pi, 1 / periods)
    mk = BRepBuilderAPI_MakeWire()

    def segment(a, b):            # GCE2d_MakeSegment: the line from a to b, trimmed at 0 and |ab|
        dist = a.Distance(b)
        line = Geom2d_Line(gp_Lin2d(a, gp_Dir2d(b.X() - a.X(), b.Y() - a.Y())))
        return Geom2d_TrimmedCurve(line, 0.0, dist)

    i = 0
    while i < full:
        end = beg.Translated(d)
        mk.Add(BRepBuilderAPI_MakeEdge(segment(beg, end), surf).Edge())
        beg = end
        i += 1
    if part > CONFUSION:
        d.Scale(part)
        end = beg.Translated(d)
        mk.Add(BRepBuilderAPI_MakeEdge(segment(beg, end), surf).Edge())
    wire = mk.Wire()
    BRepLib.BuildCurves3d_s(wire, CONFUSION * 1e-6 * (rb + rt), GeomAbs_C1, 14, 10000)
    return wire


def _clamp(x, lo, hi):
    return hi if x > hi else lo if x < lo else x


def _bounds(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    box.SetGap(0.0)
    return box


class _Helix(_AddSub):
    """PartDesign::Helix (FeatureHelix.cpp)."""
    POS = ("profile",)
    DEFAULTS = {"profile": None, "reference_axis": None, "mode": "pitch-height-angle", "pitch": 10.0,
                "height": 30.0, "turns": 3.0, "angle": 0.0, "growth": 0.0, "left_handed": False, "reversed": False,
                "tolerance": 0.1, "outside": False, "refine": True}
    REFS = ("profile", "reference_axis")
    LINKS = ("profile",)

    def validate(self):
        super().validate()
        if self.mode not in HELIX_MODES:
            raise F.FeatureError(f"{self.name}: mode {self.mode!r} is not one of {', '.join(HELIX_MODES)}")
        if self.outside and not self.additive:
            self.operation = "Common"           # Helix::onDocumentRestored: the deprecated Outside is Common
        self.outside = False
        from .feature_revolve import _axis_ref
        self.reference_axis = (ref_name(self.profile), "V_Axis") if self.reference_axis is None \
            else _axis_ref(self.reference_axis, self.name)
        for k in ("pitch", "height", "turns", "angle", "growth", "tolerance"):
            if not isinstance(getattr(self, k), (int, float, str)) or isinstance(getattr(self, k), bool):
                raise F.FeatureError(f"{self.name}: {k} is {getattr(self, k)!r}, not a number or a PARAMS expression")

    def __repr__(self):
        return f"{self.kind}({self.name!r}, {self.profile!r}, mode={self.mode!r})"

    def values(self, params) -> dict:
        """Helix::execute's first part: the mode's three values checked, the others computed from them, each clamped
        as its property is (Turns at least Confusion, Angle -89..89, Tolerance at least 0.1)."""
        v = {k: F.value(getattr(self, k), params, f"{self.name}.{k}")
             for k in ("pitch", "height", "turns", "angle", "growth", "tolerance")}
        v["turns"] = _clamp(v["turns"], CONFUSION, INT_MAX)
        v["angle"] = _clamp(v["angle"], *HELIX_ANGLE)
        v["tolerance"] = _clamp(v["tolerance"], 0.1, INT_MAX)
        m = self.mode
        if m == "pitch-height-angle":
            if v["pitch"] < CONFUSION:
                raise F.FeatureError("Error: Pitch too small!")
            if v["height"] < CONFUSION:
                raise F.FeatureError("Error: height too small!")
            v["turns"] = _clamp(v["height"] / v["pitch"], CONFUSION, INT_MAX)
            v["growth"] = v["pitch"] * math.tan(math.radians(v["angle"]))
        elif m == "pitch-turns-angle":
            if v["pitch"] < CONFUSION:
                raise F.FeatureError("Error: pitch too small!")
            if v["turns"] < CONFUSION:
                raise F.FeatureError("Error: turns too small!")
            v["height"] = v["turns"] * v["pitch"]
            v["growth"] = v["pitch"] * math.tan(math.radians(v["angle"]))
        elif m == "height-turns-angle":
            if v["height"] < CONFUSION:
                raise F.FeatureError("Error: height too small!")
            if v["turns"] < CONFUSION:
                raise F.FeatureError("Error: turns too small!")
            v["pitch"] = v["height"] / v["turns"]
            v["growth"] = v["pitch"] * math.tan(math.radians(v["angle"]))
        else:
            if v["turns"] < CONFUSION:
                raise F.FeatureError("Error: turns too small!")
            if v["height"] < CONFUSION and abs(v["growth"]) < CONFUSION and v["turns"] > 1.0:
                raise F.FeatureError("Error: either height or growth must not be zero!")
            v["pitch"] = v["height"] / v["turns"]
            if v["height"] > 0:
                v["angle"] = _clamp(math.degrees(math.atan(v["turns"] * v["growth"] / v["height"])), *HELIX_ANGLE)
        return v

    def axis(self, sketch, shapes):
        """Helix::updateAxis: ProfileBased::getAxis with ForbiddenAxis::NoCheck; (Base, Axis) as gp_Pnt, gp_Vec."""
        from types import SimpleNamespace

        from .feature_revolve import get_axis
        proxy = SimpleNamespace(name=self.name, reference_axis=self.reference_axis, project_axis=True)
        sketches = dict(shapes.get("_sketches", {}), **{sketch.name: sketch})
        return get_axis(proxy, sketch, shapes, sketches)

    def path(self, v, face, sketch, base, axis_vec, break_at):
        """Helix::generateHelixPath, in the Body's frame (the face is not moved to the feature's either)."""
        turns, height, angle, growth = v["turns"], v["height"], v["angle"], v["growth"]
        if abs(angle) < CONFUSION:
            angle = 0.0
        ax = axis_vec
        d = gp_Dir(ax)
        n = gp_Vec(*sketch.normal())
        start = ax.Crossed(n)
        if start.X() == 0 and start.Y() == 0 and start.Z() == 0:        # Base::Vector3d::IsNull
            start = n.Crossed(gp_Vec(1.0, 2.0, 3.0))
            if start.X() == 0 and start.Y() == 0 and start.Z() == 0:
                start = n.Crossed(gp_Vec(3.0, 2.0, 1.0))
        dir_start = gp_Dir(start)
        box = _bounds(face)
        lo, hi = box.CornerMin(), box.CornerMax()
        center = gp_Vec((lo.X() + hi.X()) / 2, (lo.Y() + hi.Y()) / 2, (lo.Z() + hi.Z()) / 2)
        bv = gp_Vec(base.XYZ())
        axis_offset = 100.0 * (center.Dot(start) - bv.Dot(start))
        radius = abs(axis_offset)
        turned = axis_offset < 0
        start_offset = 10000.0 * abs((1.0 if angle <= 0.0 else 0.0) * center.Dot(ax) - bv.Dot(ax))
        if radius < CONFUSION:
            if abs(ax.Dot(n)) < CONFUSION:
                raise F.FeatureError("Error: Result is self intersecting")
            radius = 1000.0
        if "growth" in self.mode:
            top = radius + turns * growth
        else:
            top = radius + height * math.tan(math.radians(angle))
        path = make_spiral_helix(radius, top, height, turns, break_at, self.left_handed)
        origo, a1, a2 = gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0)
        mov = gp_Trsf()
        if abs(start_offset) > 0:
            mov.SetTranslation(gp_Vec(a1).Multiplied(start_offset))
            path = path.Moved(TopLoc_Location(mov))
        if self.reversed:
            mov.SetRotation(gp_Ax1(origo, a2), math.pi)
            path = path.Moved(TopLoc_Location(mov))
        if turned:
            mov.SetRotation(gp_Ax1(origo, a1), math.pi)
            path = path.Moved(TopLoc_Location(mov))
        mov.SetTransformation(gp_Ax3(origo, a1, a2), gp_Ax3(base, d, dir_start))
        return path.Moved(TopLoc_Location(mov).Inverted())

    def execute(self, solid, shapes, params):
        where = self.name
        v = self.values(params)
        face = _profile_face(self, shapes, where)
        if face.ShapeType() != TopAbs_FACE:
            raise F.FeatureError("Error: Could not create face from sketch")
        if BRepAdaptor_Surface(TopoDS.Face(face)).GetType() != GeomAbs_Plane:
            raise F.FeatureError("Error: Face must be planar")
        sketch = shapes["_sketches"][ref_name(self.profile)]
        base_pt, axis_vec = self.axis(sketch, shapes)
        if axis_vec.Magnitude() < 1e-300:
            raise F.FeatureError("Error: Result is self intersecting")
        try:
            path = self.path(v, face, sketch, base_pt, axis_vec, 1.0 if v["angle"] == 0.0 else 1000.0)
            size = math.sqrt(_bounds_raw(path).SquareExtent())
            fix = ShapeFix_ShapeTolerance()
            fix.LimitTolerance(path, CONFUSION * 1e-6 * size)
            mk = BRepOffsetAPI_MakePipe(TopoDS.Wire(path), face, GeomFill_IsFrenet, False)
            result = _outward(mk.Shape())
            fix.LimitTolerance(result, CONFUSION * size * v["tolerance"])
            fixer = ShapeFix_Solid()
            fixer.Init(TopoDS.Solid(result))
            if fixer.Perform():
                result = fixer.Solid()
        except F.FeatureError:
            raise
        except Exception as e:
            raise F.FeatureError(_occ_message(e, "Error: Could not create face from sketch")) from None
        shapes.setdefault("_addsub", {})[self.name] = (result, self.additive)
        if solid is None:
            if not self.additive:
                raise F.FeatureError("Error: There is nothing to subtract")
            return result                                     # Helix::execute: no base, no refine
        try:
            out = self.boolean(solid, result)
        except F.FeatureError as e:
            raise F.FeatureError(str(e)) from None
        if out is None or out.IsNull() or not F._count(out, TopAbs_SOLID):
            raise F.FeatureError("Resulting shape is not a solid")
        return self.refine_(out)

    def to_freecad(self, ctx):
        obj = ctx.body.newObject(self.TYPE_ID, self.name)
        obj.Profile = ctx.made[ref_name(self.profile)]
        r = self.reference_axis
        obj.ReferenceAxis = (ctx.origin[r], [""]) if isinstance(r, str) else (ctx.made[r[0]], [r[1]])
        obj.Mode = self.mode
        # the mode's three (the others are read-only in this mode and follow from them, Helix::execute)
        for k in MODE_INPUTS[self.mode]:
            ctx.setv(obj, k[:1].upper() + k[1:], getattr(self, k))
        obj.LeftHanded = self.left_handed
        obj.Reversed = self.reversed
        ctx.setv(obj, "Tolerance", self.tolerance)
        self.set_common(ctx, obj)
        return obj


def _bounds_raw(shape):
    """BRepBndLib::Add without SetGap(0) (Helix::execute's size of the path)."""
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return box


# Helix::setReadWriteStatusForMode: the properties a mode reads; the rest are read-only in it
MODE_INPUTS = {"pitch-height-angle": ("pitch", "height", "angle"), "pitch-turns-angle": ("pitch", "turns", "angle"),
               "height-turns-angle": ("height", "turns", "angle"), "height-turns-growth": ("height", "turns", "growth")}


class AdditiveHelix(_Helix):
    """PartDesign::AdditiveHelix: sweeps the profile along a helix and adds it to the body."""
    kind = "AdditiveHelix"
    TYPE_ID = "PartDesign::AdditiveHelix"
    TRANSACTION = "Make AdditiveHelix"


class SubtractiveHelix(_Helix):
    """PartDesign::SubtractiveHelix: sweeps the profile along a helix and removes it from the body."""
    kind = "SubtractiveHelix"
    TYPE_ID = "PartDesign::SubtractiveHelix"
    TRANSACTION = "Make SubtractiveHelix"
    additive = False
    DEFAULTS = {**_Helix.DEFAULTS, "operation": "Subtraction"}


def propose(sketch) -> tuple[float, float]:
    """Helix::proposeParameters: Pitch 1.1 times the profile's box diagonal, Height three pitches."""
    box = _bounds(F.profile_face(sketch))
    pitch = 1.1 * math.sqrt(box.SquareExtent())
    return pitch, 3.0 * pitch


def safe_pitch(feat: _Helix, sketch, params=None, shapes=None) -> float:
    """Helix::safePitch: the smallest pitch at which the helix does not run into itself, for the panel's status."""
    v = feat.values(params or {})
    _, ax = feat.axis(sketch, shapes or {"_sketches": {sketch.name: sketch}})
    n = gp_Vec(*sketch.normal())
    start = ax.Crossed(n)
    if start.Magnitude() < CONFUSION:
        if feat.mode != "height-turns-growth":
            return CONFUSION
        if abs(v["turns"]) >= 1.0 and abs(v["growth"]) > 0.0:
            return math.inf
    d, ds = gp_Dir(ax), gp_Dir(start)
    box = _bounds_raw(F.profile_face(sketch))
    lo, hi = box.CornerMin(), box.CornerMax()
    bb = gp_Vec(hi.X() - lo.X(), hi.Y() - lo.Y(), hi.Z() - lo.Z())
    pitch0 = bb.Dot(gp_Vec(d))
    across = abs(bb.Dot(gp_Vec(ds)))
    if feat.mode == "height-turns-growth":
        if abs(v["growth"]) > across:
            return 0.0
        return 0.0 if v["turns"] < 1.0 else pitch0
    a = math.radians(v["angle"])
    if math.tan(abs(a)) * pitch0 > across:
        return across / math.tan(abs(a))
    return pitch0


def status(feature: dict, sketch, params=None) -> str:
    """TaskHelixParameters::updateStatus for a valid helix: the warning when the pitch is below safePitch, else ""."""
    cls = AdditiveHelix if feature.get("type") == AdditiveHelix.TYPE_ID else SubtractiveHelix
    f = cls.from_dict({**feature, "name": feature.get("name") or "Helix"})
    try:
        return "Warning: helix might be self intersecting" if safe_pitch(f, sketch, params) > \
            f.values(params or {})["pitch"] else ""
    except F.FeatureError as e:
        return str(e)


def helix_command_defaults(feature: dict, sketch=None) -> dict:
    """What CmdPartDesignAdditiveHelix sets (ReferenceAxis the profile's V_Axis) and what its panel then proposes
    (TaskHelixParameters::initializeHelix: Pitch and Height from the profile when it was not edited)."""
    out = dict(feature)
    prof = feature.get("profile")
    out.setdefault("reference_axis", [prof[0] if isinstance(prof, (list, tuple)) else prof, "V_Axis"])
    if sketch is not None and "pitch" not in feature and "height" not in feature:
        try:
            out["pitch"], out["height"] = (round(x, 9) for x in propose(sketch))
        except F.FeatureError:
            pass
    return out


_Helix.command_defaults = staticmethod(helix_command_defaults)      # feature_edit's add calls it

SWEEPS = {c.kind: c for c in (AdditiveLoft, SubtractiveLoft, AdditivePipe, SubtractivePipe, AdditiveHelix,
                              SubtractiveHelix)}

# Last, so that importing this module first works: feature.py imports it back at its end, and finds it complete.
from . import feature as F  # noqa: E402

__all__ = ["AdditiveLoft", "SubtractiveLoft", "AdditivePipe", "SubtractivePipe", "AdditiveHelix", "SubtractiveHelix",
           "SWEEPS", "make_loft", "make_spiral_helix", "safe_pitch", "propose", "status", "sketch_shape"]
