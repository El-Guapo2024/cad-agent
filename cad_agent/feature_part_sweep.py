# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's Part features (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/Part/App/PartFeatures.cpp (Loft, Sweep, Thickness): Copyright (c) 2010 Werner Mayer
#   src/Mod/Part/App/FeatureOffset.cpp (Offset, Offset2D): Copyright (c) 2016 Victor Titov (DeepSOIC)
#   src/Mod/Part/App/FeatureProjectOnSurface.cpp: Copyright (c) 2024 Eric Price, the FreeCAD project
#   src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementLoft, makeElementPipeShell, prepareProfiles,
#   makeElementOffset, makeElementOffset2D, makeElementThickSolid, makeElementSolid, makeElementWires, linearize):
#   Copyright (c) 2022 Zheng, Lei; 2023 Ondsel
#   src/Mod/Part/App/TopoShape.cpp (findPlane, getCenterOfGravity): Copyright (c) 2002 Jürgen Riegel
#   src/Mod/Part/App/FaceMakerBullseye.cpp (with a plane given): Copyright (c) 2016 Victor Titov (DeepSOIC)
#   src/Mod/Part/App/ShapeAnalysis_FreeBoundsFix.cpp: Copyright (c) 2024 the FreeCAD project
#   src/Mod/Part/Gui/TaskLoft.cpp, TaskSweep.cpp, Command.cpp, DlgProjectionOnSurface.cpp, ViewProviderMirror.cpp:
#   what the commands make and which inputs the tree shows under each (claimChildren)
"""Part's Loft (Part_Loft), Sweep (Part_Sweep), Offset (Part_Offset), Offset2D (Part_Offset2D), Thickness
(Part_Thickness) and ProjectOnSurface (Part_ProjectionOnSurface).

    Part.Loft("Loft", ["Sketch", "Sketch001", "Vertex"], ruled=True)
    Part.Sweep("Sweep", ["Sketch"], spine=("Helix", ""), frenet=True, transition="Round corner")
    Part.Sweep("Sweep", ["Circle"], spine=("Path", ["Edge1", "Edge2"]))
    Part.Offset("Offset", "Box", value=2, join="Intersection", fill=False)
    Part.Offset2D("Offset2D", "Sketch", value=-1.5, mode="Pipe", join="Arc", fill=True)
    Part.Thickness("Thickness", ("Box", ["Face6", "Face1"]), value=1.0, join="Intersection")
    Part.ProjectOnSurface("Projection", support_face=("Cylinder", "Face1"), projection=[("Sketch", "Edge1")],
                          direction=(0, 1, 0), mode="Edges")

Property names and defaults are FreeCAD's: a Loft's sections, solid True, ruled and closed False, max_degree 5 (2 to
25), linearize False; a Sweep's sections, spine (a link with sub-elements: the edges, or the whole object), solid
and frenet True, transition "Right corner" ("Transformed", "Round corner"), linearize False; an Offset's source,
value 1.0, mode "Skin" ("Pipe", "RectoVerso"), join "Arc" ("Tangent", "Intersection"), intersection,
self_intersection and fill False; an Offset2D the same with mode "Pipe" ("Skin" allows an open result, "RectoVerso"
is refused); a Thickness's faces (the solid and the faces to remove), value 1.0, mode, join, intersection and
self_intersection as an Offset's; a ProjectOnSurface's support_face (one face), projection (faces, wires and edges),
direction (0, 0, 1), mode "All" ("Faces", "Edges"), height 0 (a face projected is extruded by it, against the
direction, in mode All) and offset 0 (the result moved along the direction).
"""
from __future__ import annotations

import math

from . import feature as F
from . import feature_part as _P
from .feature_kw import ref
from .feature_part import PartObject, compound, register, sub_shape
from .feature_part_taper import OffsetFix, _children, _explore, element_compound, split_wires

try:
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, \
        BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakeWire, BRepBuilderAPI_RightCorner, BRepBuilderAPI_RoundCorner, \
        BRepBuilderAPI_Sewing, BRepBuilderAPI_Transformed
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepGProp import BRepGProp, BRepGProp_Face
    from OCP.BRepLib import BRepLib, BRepLib_FindSurface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepOffset import BRepOffset_Pipe, BRepOffset_RectoVerso, BRepOffset_Skin
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape, BRepOffsetAPI_MakePipeShell, \
        BRepOffsetAPI_MakeThickSolid, BRepOffsetAPI_ThruSections
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.BRepProj import BRepProj_Projection
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.GProp import GProp_GProps
    from OCP.Geom import Geom_Plane
    from OCP.GeomAbs import GeomAbs_Arc, GeomAbs_Intersection, GeomAbs_Plane, GeomAbs_Tangent
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.GeomLib import GeomLib_IsPlanarSurface
    from OCP.ShapeAnalysis import ShapeAnalysis, ShapeAnalysis_FreeBounds, ShapeAnalysis_FreeBoundsProperties
    from OCP.ShapeFix import ShapeFix_Face, ShapeFix_Shape, ShapeFix_ShapeTolerance, ShapeFix_Wire, \
        ShapeFix_Wireframe
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, \
        TopAbs_REVERSED, TopAbs_SHAPE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS, TopoDS_Wire
    from OCP.collections import HSequence_TopoDS_Shape
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7
ANGULAR = 1e-12
TRANSITIONS = ("Transformed", "Right corner", "Round corner")
MODES = ("Skin", "Pipe", "RectoVerso")
JOINS = ("Arc", "Tangent", "Intersection")
PROJECTION_MODES = ("All", "Faces", "Edges")
MAX_DEGREE = 25                          # Geom_BSplineSurface::MaxDegree()


# ── links with sub-elements ──────────────────────────────────────────────────────────────────────────────────────

def link_sub(v, where):
    """A PropertyLinkSub as the part file holds it: a name, (name, "Edge1") or (name, ("Edge1", "Edge2"))."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str):
        sub = v[1]
        if isinstance(sub, (list, tuple)):
            subs = tuple(s for s in sub)
            if not all(isinstance(s, str) for s in subs):
                raise F.FeatureError(f"{where}: {v!r} is not (object, [sub-elements])")
            return (v[0], subs[0]) if len(subs) == 1 else (v[0], subs) if subs else v[0]
        if not isinstance(sub, str):
            raise F.FeatureError(f"{where}: {v!r} is not (object, sub-element)")
        return (v[0], sub) if sub else v[0]
    raise F.FeatureError(f"{where}: {v!r} is not a link: an object's name, (name, \"Edge1\") or "
                         "(name, [\"Edge1\", \"Edge2\"])")


def _subs_of(link):
    if link is None or isinstance(link, str):
        return []
    sub = link[1]
    return list(sub) if isinstance(sub, tuple) else [sub] if sub else []


class _LinkSubMixin:
    """A class whose LINK_SUBS hold one link with several sub-elements (FreeCAD's PropertyLinkSub)."""
    LINK_SUBS: tuple = ()

    def normalize(self, key, v):
        if key in self.LINK_SUBS:
            return link_sub(v, f"{self.name}.{key}")
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        if key in self.LINK_SUBS:
            v = getattr(self, key) if v is None else v
            if isinstance(v, tuple) and isinstance(v[1], tuple):
                return (v[0], list(v[1]))
            return v
        return super().source_value(key, v)


# ── TopoShape's helpers ──────────────────────────────────────────────────────────────────────────────────────────

def make_wires(shape):
    """TopoShape::makeElementWires (mergeWithTolerance): the shape's edges joined to wires, one wire alone itself."""
    edges = [TopoDS.Edge(e) for e in F._subs(shape, TopAbs_EDGE)]
    if not edges:
        return compound([])
    return element_compound(F._wires(edges))


def _shape_props(shape):
    """getShapeProperties: the centre of the solids, else the faces, else the edges, else the vertices' mean."""
    p = GProp_GProps()
    if _explore(shape, TopAbs_SOLID):
        BRepGProp.VolumeProperties_s(shape, p)
        return p.Mass(), p.CentreOfMass()
    if _explore(shape, TopAbs_FACE):
        BRepGProp.SurfaceProperties_s(shape, p)
        return p.Mass(), p.CentreOfMass()
    if _explore(shape, TopAbs_EDGE):
        BRepGProp.LinearProperties_s(shape, p)
        return p.Mass(), p.CentreOfMass()
    vs = _explore(shape, TopAbs_VERTEX)
    if vs:
        pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in vs]
        return 0.0, gp_Pnt(sum(q.X() for q in pts) / len(pts), sum(q.Y() for q in pts) / len(pts),
                           sum(q.Z() for q in pts) / len(pts))
    return None


def _trsf_values(loc):
    t = loc.Transformation()
    return [t.Value(i, j) for i in (1, 2, 3) for j in (1, 2, 3, 4)]


def _check_profiles(sh1, sh2):
    """makeElementLoft's checkProfiles: whether two profiles are apart."""
    if sh1.IsPartner(sh2):
        return _trsf_values(sh1.Location()) != _trsf_values(sh2.Location())
    try:
        b1, b2 = Bnd_Box(), Bnd_Box()
        BRepBndLib.Add_s(sh1, b1)
        BRepBndLib.Add_s(sh2, b2)
        if not b1.CornerMin().IsEqual(b2.CornerMin(), CONFUSION):
            return True
        if not b1.CornerMax().IsEqual(b2.CornerMax(), CONFUSION):
            return True
    except Exception:  # noqa: BLE001 - Standard_Failure
        return False
    c1, c2 = _shape_props(sh1), _shape_props(sh2)
    if c1 is None or c1[0] > 2e100 or c2 is None or c2[0] > 2e100:
        return True
    return c1[1].Distance(c2[1]) > CONFUSION


def prepare_profiles(shapes, offset=0):
    """prepareProfiles: each section a wire or a vertex (a face its outer wire, edges joined to a wire)."""
    out = []
    for shape in shapes[offset:]:
        if shape is None or shape.IsNull():
            raise F.FeatureError("Null input shape")
        if F._count(shape, TopAbs_FACE) == 1:
            shape = split_wires(F._subs(shape, TopAbs_FACE)[0])[0]
        elif F._count(shape, TopAbs_WIRE) == 0 and F._count(shape, TopAbs_EDGE) > 0:
            shape = make_wires(shape)
        if F._count(shape, TopAbs_WIRE) == 1:
            out.append(F._subs(shape, TopAbs_WIRE)[0])
            continue
        if F._count(shape, TopAbs_VERTEX) == 1:
            out.append(F._subs(shape, TopAbs_VERTEX)[0])
            continue
        raise F.FeatureError("Profile shape is not a single vertex, edge, wire nor face.")
    if not out:
        raise F.FeatureError("No profile")
    return out


def make_loft(shapes, solid, ruled, closed, max_degree):
    """TopoShape::makeElementLoft: BRepOffsetAPI_ThruSections through the profiles, the first again when closed."""
    gen = BRepOffsetAPI_ThruSections(bool(solid), bool(ruled))
    gen.SetMaxDegree(max_degree)
    profiles = prepare_profiles(shapes)
    if len(shapes) < 2:
        raise F.FeatureError("Need at least two vertices, edges or wires to create loft face")
    for i, sh in enumerate(profiles):
        if i > 0 and not _check_profiles(sh, profiles[i - 1]):
            raise F.FeatureError("Segments of a loft do not have sufficient separation")
        if sh.ShapeType() == TopAbs_VERTEX:
            gen.AddVertex(TopoDS.Vertex(sh))
        else:
            gen.AddWire(TopoDS.Wire(sh))
    if closed and profiles[-1].ShapeType() != TopAbs_VERTEX:      # a vertex last: 'Closed' ignored
        first = profiles[0]
        if first.ShapeType() == TopAbs_VERTEX:
            gen.AddVertex(TopoDS.Vertex(first))
        elif first.ShapeType() == TopAbs_EDGE:
            gen.AddWire(BRepBuilderAPI_MakeWire(TopoDS.Edge(first)).Wire())
        elif first.ShapeType() == TopAbs_WIRE:
            gen.AddWire(TopoDS.Wire(first))
    gen.CheckCompatibility(True)
    gen.Build()
    return gen.Shape()


def linearize_faces(shape):
    """TopoShape::linearize(linearizeFaces, noEdges): every face whose surface is a plane in disguise given that
    plane (GeomLib_IsPlanarSurface, 1e-7), its edges as they are."""
    b = BRep_Builder()
    for f in F._subs(shape, TopAbs_FACE):
        face = TopoDS.Face(f)
        ad = BRepAdaptor_Surface(face)
        if ad.GetType() == GeomAbs_Plane:
            continue
        if not GeomLib_IsPlanarSurface(ad.Surface().Surface(), 1e-7).IsPlanar():
            continue
        geo = BRepAdaptor_Surface(TopoDS.Face(face.Located(TopLoc_Location()).Oriented(TopAbs_FORWARD)))
        check = GeomLib_IsPlanarSurface(geo.Surface().Surface(), 1e-7)
        if check.IsPlanar():
            b.UpdateFace(face, Geom_Plane(check.Plan()), face.Location(), BRep_Tool.Tolerance_s(face))
    return shape


def make_pipe_shell(shapes, solid, frenet, transition):
    """TopoShape::makeElementPipeShell: the profiles (shapes[1:]) swept along the spine (shapes[0], one wire)."""
    if len(shapes) < 2:
        raise F.FeatureError("Not enough input shapes")
    spine = make_wires(shapes[0])
    if spine is None or spine.IsNull():
        raise F.FeatureError("Null input shape")
    if spine.ShapeType() != TopAbs_WIRE:
        raise F.FeatureError("Spine shape cannot form a single wire")
    mk = BRepOffsetAPI_MakePipeShell(TopoDS.Wire(spine))
    mode = {"Right corner": BRepBuilderAPI_RightCorner, "Round corner": BRepBuilderAPI_RoundCorner}.get(
        transition, BRepBuilderAPI_Transformed)
    mk.SetMode(bool(frenet))
    mk.SetTransitionMode(mode)
    for sh in prepare_profiles(shapes, 1):
        mk.Add(sh)
    if not mk.IsReady():
        raise F.FeatureError("shape is not ready to build")
    mk.Build()
    if solid:
        mk.MakeSolid()
    return mk.Shape()


def make_solid(shape):
    """TopoShape::makeElementSolid: a compsolid's solid, else a solid of the shells, oriented closed."""
    if shape is None or shape.IsNull():
        raise F.FeatureError("Null shape")
    comps = F._subs(shape, TopAbs_COMPSOLID)
    if not comps:
        mk = BRepBuilderAPI_MakeSolid()
        shells = F._subs(shape, TopAbs_SHELL)
        for s in shells:
            mk.Add(TopoDS.Shell(s))
        if not shells:
            raise F.FeatureError("No shells or compsolids found in shape")
        if not mk.IsDone():
            raise F.FeatureError("Failed to create a solid in makeElementSolid!")
        solid = TopoDS.Solid(mk.Shape())
        BRepLib.OrientClosedSolid_s(solid)
        return solid
    if len(comps) == 1:
        return BRepBuilderAPI_MakeSolid(TopoDS.CompSolid(comps[0])).Shape()
    raise F.FeatureError("Only one compsolid can be accepted. Provided shape has more than one compsolid.")


def _offset_mode(i):
    return (BRepOffset_Skin, BRepOffset_Pipe, BRepOffset_RectoVerso)[i]


def _join(i):
    return (GeomAbs_Arc, GeomAbs_Tangent, GeomAbs_Intersection)[i]


def make_offset(shape, offset, tol, intersection, self_inter, mode, join, fill):
    """TopoShape::makeElementOffset: BRepOffsetAPI_MakeOffsetShape by join, a solid of it when the source was one;
    fill: the source's free bounds lofted to their offsets and sewn with both, a solid when that closes."""
    mk = BRepOffsetAPI_MakeOffsetShape()
    mk.PerformByJoin(shape, offset, tol, _offset_mode(mode), bool(intersection), bool(self_inter), _join(join))
    if not mk.IsDone():
        raise F.FeatureError("BRepOffsetAPI_MakeOffsetShape not done")
    res = mk.Shape()
    if _explore(shape, TopAbs_SOLID) and not _explore(res, TopAbs_SOLID):
        try:
            res = make_solid(res)
        except F.FeatureError:
            raise
        except Exception:  # noqa: BLE001 - Standard_Failure: FreeCAD warns "failed to make solid" and goes on
            pass
    if not fill:
        return res
    free = ShapeAnalysis_FreeBoundsProperties(shape)
    free.Perform()
    if free.NbClosedFreeBounds() < 1:
        raise F.FeatureError("no closed bounds")
    b = BRep_Builder()
    shapes = []
    for i in range(1, free.NbClosedFreeBounds() + 1):
        original = free.ClosedFreeBound(i).FreeBound()
        img = mk.MakeOffset().OffsetEdgesFromShapes()
        wire = TopoDS_Wire()
        b.MakeWire(wire)
        for s in F._subs(original, TopAbs_EDGE):
            if not img.HasImage(s):
                raise F.FeatureError("no image for shape")
            edges = [x for x in img.Image(s) if x.ShapeType() == TopAbs_EDGE]
            if len(edges) != 1:
                raise F.FeatureError(f"wrong edge count: {len(edges)}\n")
            b.Add(wire, TopoDS.Edge(edges[-1]))
        gen = BRepOffsetAPI_ThruSections()
        gen.AddWire(TopoDS.Wire(original))
        gen.AddWire(wire)
        gen.Build()
        if not gen.IsDone():
            raise F.FeatureError("ThruSections failed")
        shapes.append(gen.Shape())
    perimeter = compound(shapes)                        # makeElementCompound: forceCompound
    sew = BRepBuilderAPI_Sewing()
    sew.Add(shape)
    sew.Add(perimeter)
    sew.Add(res)
    sew.Perform()
    out = sew.SewedShape()
    if out.ShapeType() == TopAbs_SHELL and out.Closed():
        ms = BRepBuilderAPI_MakeSolid(TopoDS.Shell(out))
        if ms.IsDone():
            temp = ms.Solid()
            if BRepLib.OrientClosedSolid_s(temp):
                out = temp
    return out


def find_plane(shape, tol=-1.0, atol=-1.0):
    """TopoShape::findPlane: the plane of the shape's faces and free edges and vertices, or None."""
    if shape is None or shape.IsNull():
        return None
    tol = CONFUSION if tol < 0 else tol
    atol = ANGULAR if atol < 0 else atol
    work = BRepBuilderAPI_Copy(shape).Shape() if F._count(shape, TopAbs_EDGE) == 1 else shape
    try:
        found, pln = False, None
        for f in F._subs(shape, TopAbs_FACE):
            face = TopoDS.Face(f)
            ad = BRepAdaptor_Surface(face)
            if ad.GetType() == GeomAbs_Plane:
                plane = ad.Plane()
            else:
                surf = BRep_Tool.Surface_s(face, TopLoc_Location())
                check = GeomLib_IsPlanarSurface(surf, tol)
                if not check.IsPlanar():
                    return None
                plane = check.Plan()
            if not found:
                found, pln = True, plane
            elif not pln.Position().IsCoplanar(plane.Position(), tol, atol):
                return None
        if _explore(shape, TopAbs_EDGE, TopAbs_FACE):
            finder = BRepLib_FindSurface(BRepBuilderAPI_Copy(work).Shape(), tol, True)
            if not finder.Found():
                return None
            pln = GeomAdaptor_Surface(finder.Surface()).Plane()
            found = True
        verts = _explore(shape, TopAbs_VERTEX, TopAbs_EDGE)
        if verts:
            if not found and len(verts) > 2:
                edges = [BRepBuilderAPI_MakeEdge(TopoDS.Vertex(verts[i]), TopoDS.Vertex(verts[i + 1])).Edge()
                         for i in range(len(verts) - 1)]
                finder = BRepLib_FindSurface(compound(edges), tol, True)
                if not finder.Found():
                    return None
                return GeomAdaptor_Surface(finder.Surface()).Plane()
            for v in verts:
                if pln is None or pln.SquareDistance(BRep_Tool.Pnt_s(TopoDS.Vertex(v))) > tol * tol:
                    return None
        faces = F._subs(shape, TopAbs_FACE)
        if faces:
            face = TopoDS.Face(faces[0])
            ad = BRepAdaptor_Surface(face)
            u = ad.FirstUParameter() + (ad.LastUParameter() - ad.FirstUParameter()) / 2.0
            v = ad.FirstVParameter() + (ad.LastVParameter() - ad.FirstVParameter()) / 2.0
            prop = BRepLProp_SLProps(ad, u, v, 2, CONFUSION)
            if prop.IsNormalDefined():
                pnt, vec = gp_Pnt(), gp_Vec()
                BRepGProp_Face(face).Normal(u, v, pnt, vec)
                pln = gp_Pln(pnt, gp_Dir(vec))
        return pln
    except Exception:  # noqa: BLE001 - Standard_Failure: no plane, as FreeCAD's catch has it
        return None


def bullseye_face(wires, plane):
    """makeElementFace(wires, FaceMakerBullseye, plane): FaceMakerBullseye with the plane supplied, then the
    repair of an invalid result."""
    ws = []
    for w in wires:
        if w.ShapeType() == TopAbs_EDGE:
            w = BRepBuilderAPI_MakeWire(TopoDS.Edge(w)).Wire()
        ws.append(TopoDS.Wire(w))
    for w in ws:
        if not BRep_Tool.IsClosed_s(w):
            raise F.FeatureError("Wire is not closed.")
    infos = []
    for w in ws:
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(w, box, False)
        if not box.IsVoid():
            infos.append((math.sqrt(box.SquareExtent()), w))
    infos = F._stable_sort_desc(infos)
    faces = []
    for _, w in infos:
        found = None
        for f in reversed(faces):
            if f.hit_test(w) == "hit":
                found = f
        if found is not None:
            found.add_hole(w)
        else:
            faces.append(F._Driller(plane, w))
    shapes = [f.face for f in faces]
    if not shapes:
        return None
    result = shapes[0] if len(shapes) == 1 else compound(shapes)
    if not BRepCheck_Analyzer(result).IsValid():
        ShapeFix_ShapeTolerance().LimitTolerance(result, CONFUSION, CONFUSION, TopAbs_SHAPE)
        fx = ShapeFix_Shape(result)
        fx.Perform()
        result = fx.Shape()
    return result


def _expand(shape, out):
    if shape is None or shape.IsNull():
        raise F.FeatureError("Null input shape")
    if shape.ShapeType() != TopAbs_COMPOUND:
        out.append(shape)
        return out
    for c in _children(shape):
        _expand(c, out)
    return out


def _wire_ends(wire):
    xp = BRepTools_WireExplorer()
    xp.Init(TopoDS.Wire(wire))
    v1 = xp.CurrentVertex()
    while xp.More():
        xp.Next()
    return v1, xp.CurrentVertex()


def _wire_edges(wire):
    out = []
    xp = BRepTools_WireExplorer()
    xp.Init(TopoDS.Wire(wire))
    while xp.More():
        out.append(xp.Current())
        xp.Next()
    return out


def make_offset2d(shape, offset, join, fill, open_result, intersection):
    """TopoShape::makeElementOffset2D: the edges, wires or faces offset in their plane (BRepOffsetAPI_MakeOffsetFix),
    a compound's children each on its own unless intersection; fill: the band between the source and the offset
    made a face (FaceMakerBullseye), an open wire's ends joined by new edges."""
    if shape is None or shape.IsNull():
        raise F.FeatureError("makeOffset2D: input shape is null!")
    to_process, to_return = [], []
    force = False
    if shape.ShapeType() == TopAbs_COMPOUND:
        if not intersection:
            for c in _children(shape):
                to_return.append(make_offset2d(c, offset, join, fill, open_result, intersection))
                force = True
        else:
            for s in _children(shape):
                if s.ShapeType() == TopAbs_COMPOUND:
                    to_return.append(make_offset2d(s, offset, join, fill, open_result, intersection))
                    force = True
                else:
                    to_process.append(s)
    else:
        to_process.append(shape)

    if to_process:
        source_wires = []
        have_wires = have_faces = False
        for s in to_process:
            t = s.ShapeType()
            if t == TopAbs_EDGE:
                source_wires.append(make_wires(s))
                have_wires = True
            elif t == TopAbs_WIRE:
                source_wires.append(s)
                have_wires = True
            elif t == TopAbs_FACE:
                source_wires += F._subs(s, TopAbs_WIRE)
                have_faces = True
            else:
                raise F.FeatureError("makeOffset2D: input shape is not an edge, wire or face or compound of those.")
        if have_wires and have_faces:
            raise F.FeatureError("makeOffset2D: collective offset of a mix of wires and faces is not supported")
        if have_faces:
            open_result = False
        plane = find_plane(element_compound(source_wires))
        if plane is None:
            raise F.FeatureError("makeOffset2D: wires are nonplanar or noncoplanar")
        if abs(offset) > CONFUSION:
            mk = OffsetFix(_join(join), bool(open_result))
            for w in source_wires:
                mk.add_wire(TopoDS.Wire(w))
            mk.perform(offset)
            if mk.shape().IsNull():
                raise F.FeatureError("makeOffset2D: result of offsetting is null!")
            offset_shape = BRepBuilderAPI_Copy(mk.shape()).Shape()      # makeElementCopy, bug #2699
        else:
            offset_shape = element_compound(source_wires)
        offset_wires = _expand(offset_shape, [])
        if not offset_wires:
            raise F.FeatureError("makeOffset2D: offset result has no wires.")
        face_wires = []
        if not fill:
            if have_faces:
                face_wires += offset_wires
            else:
                to_return += offset_wires
        else:
            if abs(offset) < CONFUSION:
                raise F.FeatureError("makeOffset2D: offset distance is zero. Can't fill offset.")
            closed, opened = [], []
            for w in source_wires + offset_wires:
                (closed if BRep_Tool.IsClosed_s(TopoDS.Wire(w)) else opened).append(w)
            face_wires += closed
            if open_result and opened:
                if len(opened) != 2:
                    raise F.FeatureError("makeOffset2D: collective offset with filling of multiple wires is not "
                                         "supported yet.")
                w1, w2 = opened[0], opened[-1]
                v1, v2 = _wire_ends(w1)
                v3, v4 = _wire_ends(w2)
                for n, v in (("v1", v1), ("v2", v2), ("v3", v3), ("v4", v4)):
                    if v.IsNull():
                        raise F.FeatureError(f"{n} is null")
                p2 = BRep_Tool.Pnt_s(v2)
                if abs(gp_Vec(p2, BRep_Tool.Pnt_s(v3)).Magnitude() - abs(offset)) <= \
                        BRep_Tool.Tolerance_s(v2) + BRep_Tool.Tolerance_s(v3):
                    w2 = w2.Reversed()
                    v3, v4 = TopoDS.Vertex(v4.Reversed()), TopoDS.Vertex(v3.Reversed())
                elif abs(gp_Vec(p2, BRep_Tool.Pnt_s(v4)).Magnitude() - abs(offset)) <= \
                        BRep_Tool.Tolerance_s(v2) + BRep_Tool.Tolerance_s(v4):
                    pass
                else:
                    raise F.FeatureError("makeOffset2D: fill offset: failed to establish open vertex relationship.")
                mkw = BRepBuilderAPI_MakeWire()
                for e in _wire_edges(w1):
                    mkw.Add(e)
                mkw.Add(BRepBuilderAPI_MakeEdge(v2, v4).Edge())
                w2 = w2.Reversed()
                for e in _wire_edges(w2):
                    mkw.Add(e)
                mkw.Add(BRepBuilderAPI_MakeEdge(v3, v1).Edge())
                mkw.Build()
                face_wires.append(mkw.Shape())
        if face_wires:
            face = bullseye_face(face_wires, plane)
            if face is None:
                raise F.FeatureError("Null input shape")
            _expand(face, to_return)
    return element_compound(to_return, force)


def make_thick_solid(shape, faces, offset, tol, intersection, self_inter, mode, join):
    """TopoShape::makeElementThickSolid: BRepOffsetAPI_MakeThickSolid by join, the faces removed (no tangent join:
    it is made intersection)."""
    if join not in (0, 2):
        join = 2
    if shape is None or shape.IsNull():
        raise F.FeatureError("Null shape")
    if not faces:
        raise F.FeatureError("Null input shape")
    if abs(offset) <= 2 * tol:
        return shape
    rem = F.TopTools_ListOfShape()
    mine = F._subs(shape, TopAbs_FACE)
    for f in faces:
        if f is None or f.IsNull():
            raise F.FeatureError("Null input shape")
        if not any(f.IsSame(m) for m in mine):
            raise F.FeatureError("face does not belong to the shape")
        rem.Append(f)
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidByJoin(shape, rem, offset, tol, _offset_mode(mode), bool(intersection), bool(self_inter),
                            _join(join))
    return mk.Shape()


# ── the objects ──────────────────────────────────────────────────────────────────────────────────────────────────

class Loft(PartObject):
    """Part::Loft (Part_Loft, TaskLoft): a surface or solid through its sections (vertices, edges, wires, faces)."""
    kind, TYPE_ID, TRANSACTION = "Part.Loft", "Part::Loft", "Loft"
    POS = ("sections",)
    REFS = ("sections",)
    INPUTS = ("sections",)
    DEFAULTS = {"sections": (), "solid": True, "ruled": False, "closed": False, "max_degree": 5, "linearize": False,
                **PartObject.COMMON}
    RANGES = {"max_degree": (2, MAX_DEGREE)}

    def shape(self, ctx, params):
        if not self.sections:
            raise F.FeatureError("No sections linked.")
        shapes = []
        for s in self.sections:
            sh = ctx.shape(s, f"{self.name}.Sections")
            if sh is None or sh.IsNull():
                raise F.FeatureError("Invalid section link")
            shapes.append(sh)
        res = make_loft(shapes, self.solid, self.ruled, self.closed, int(round(self.v("max_degree", params))))
        if self.linearize:
            res = linearize_faces(res)
        return res


class Sweep(_LinkSubMixin, PartObject):
    """Part::Sweep (Part_Sweep, TaskSweep): its sections swept along the spine, the edges picked of one object."""
    kind, TYPE_ID, TRANSACTION = "Part.Sweep", "Part::Sweep", "Sweep"
    POS = ("sections",)
    REFS = ("sections", "spine")
    LINK_SUBS = ("spine",)
    INPUTS = ("sections", "spine")
    DEFAULTS = {"sections": (), "spine": None, "solid": True, "frenet": True, "transition": "Right corner",
                "linearize": False, **PartObject.COMMON}
    ENUMS = {"transition": TRANSITIONS}

    def shape(self, ctx, params):
        if not self.sections:
            raise F.FeatureError("No sections linked.")
        if self.spine is None:
            raise F.FeatureError("No spine")
        spine = ctx.shape(self.spine, f"{self.name}.Spine")
        if spine is None or spine.IsNull():
            raise F.FeatureError("Invalid spine")
        shapes = [spine]
        for s in self.sections:
            sh = ctx.shape(s, f"{self.name}.Sections")
            if sh is None or sh.IsNull():
                raise F.FeatureError("Invalid section link")
            shapes.append(sh)
        try:
            res = make_pipe_shell(shapes, self.solid, self.frenet, self.transition)
        except F.FeatureError:          # not a Standard_Failure: Sweep::execute's catch (...)
            raise F.FeatureError("A fatal error occurred when making the sweep") from None
        if self.linearize:
            res = linearize_faces(res)
        return res


class Offset(PartObject):
    """Part::Offset (Part_Offset, 3D Offset): its source's faces offset by value."""
    kind, TYPE_ID, TRANSACTION = "Part.Offset", "Part::Offset", "Make Offset"
    POS = ("source",)
    REFS = ("source",)
    INPUTS = ("source",)
    DEFAULTS = {"source": None, "value": 1.0, "mode": "Skin", "join": "Arc", "intersection": False,
                "self_intersection": False, "fill": False, **PartObject.COMMON}
    ENUMS = {"mode": MODES, "join": JOINS}

    def shape(self, ctx, params):
        if self.source is None:
            raise F.FeatureError("No source shape linked.")
        shape = ctx.shape(self.source, f"{self.name}.Source")
        if shape is None or shape.IsNull():
            raise F.FeatureError("Invalid source link")
        return make_offset(shape, self.v("value", params), CONFUSION, self.intersection, self.self_intersection,
                           MODES.index(self.mode), JOINS.index(self.join), self.fill)


class Offset2D(PartObject):
    """Part::Offset2D (Part_Offset2D, 2D Offset): its source's planar edges, wires or faces offset in their plane."""
    kind, TYPE_ID, TRANSACTION = "Part.Offset2D", "Part::Offset2D", "Make 2D Offset"
    POS = ("source",)
    REFS = ("source",)
    INPUTS = ("source",)
    DEFAULTS = {"source": None, "value": 1.0, "mode": "Pipe", "join": "Arc", "intersection": False,
                "self_intersection": False, "fill": False, **PartObject.COMMON}
    ENUMS = {"mode": MODES, "join": JOINS}

    def shape(self, ctx, params):
        if self.source is None:
            raise F.FeatureError("No source shape linked.")
        shape = ctx.shape(self.source, f"{self.name}.Source")
        if shape is None or shape.IsNull():
            raise F.FeatureError("No source shape linked.")
        if self.mode == "RectoVerso":
            raise F.FeatureError("Mode 'Recto-Verso' is not supported for 2D offset.")
        return make_offset2d(shape, self.v("value", params), JOINS.index(self.join), self.fill,
                             self.mode == "Skin", self.intersection)


class Thickness(_LinkSubMixin, PartObject):
    """Part::Thickness (Part_Thickness): a solid hollowed to a wall of value, the chosen faces removed."""
    kind, TYPE_ID, TRANSACTION = "Part.Thickness", "Part::Thickness", "Make Thickness"
    POS = ("faces",)
    REFS = ("faces",)
    LINK_SUBS = ("faces",)
    INPUTS = ("faces",)
    DEFAULTS = {"faces": None, "value": 1.0, "mode": "Skin", "join": "Arc", "intersection": False,
                "self_intersection": False, **PartObject.COMMON}
    ENUMS = {"mode": MODES, "join": JOINS}

    def shape(self, ctx, params):
        if self.faces is None:
            raise F.FeatureError("Invalid source shape")
        name = self.faces if isinstance(self.faces, str) else self.faces[0]
        base = ctx.shape(name, f"{self.name}.Faces")
        if base is None or base.IsNull():
            raise F.FeatureError("Invalid source shape")
        if F._count(base, TopAbs_SOLID) != 1:
            raise F.FeatureError("Source shape is not single solid.")
        faces = []
        for sub in _subs_of(self.faces):
            f = sub_shape(base, sub, f"{self.name}.Faces")
            if f.ShapeType() != TopAbs_FACE:
                raise F.FeatureError("Invalid face selection")
            faces.append(f)
        return make_thick_solid(base, faces, self.v("value", params), CONFUSION, self.intersection,
                                self.self_intersection, MODES.index(self.mode), JOINS.index(self.join))


# ── ProjectOnSurface ─────────────────────────────────────────────────────────────────────────────────────────────

def _connect_edges(edges, tol, shared):
    """Fix_ShapeAnalysis_FreeBounds_ConnectEdgesToWires (OCCT 8: no filtering)."""
    seq = HSequence_TopoDS_Shape()
    for e in edges:
        seq.Append(e)
    out = HSequence_TopoDS_Shape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(seq, tol, shared, out)
    return out


def _fix_wire(edges, face):
    """ProjectOnSurface::fixWire: the edges sorted to wires and healed on the face, the first wire."""
    wires = _connect_edges(edges, 0.0001, False)
    out = HSequence_TopoDS_Shape()
    ShapeAnalysis_FreeBounds.ConnectWiresToWires_s(wires, 0.0001, False, out)
    for i in range(1, out.Length() + 1):
        w = TopoDS.Wire(out.Value(i))
        fix = ShapeFix_Wire(w, face, 0.0001)
        _set_mode(fix.FixAddCurve3dMode, 1)
        _set_mode(fix.FixAddPCurveMode, 1)
        fix.Perform()
        frame = ShapeFix_Wireframe(fix.Wire())
        frame.FixWireGaps()
        frame.FixSmallEdges()
        return TopoDS.Wire(frame.Shape())
    return TopoDS_Wire()


def _set_mode(accessor, value):
    """ShapeFix's mode accessors return a reference FreeCAD assigns to; 1 is what -1 (the default) does for
    FixAddCurve3d and FixAddPCurve, so where OCP cannot assign there is nothing to change."""
    try:
        accessor(value)
    except TypeError:
        pass


def _projected_wire(proj, reference):
    """getProjectedWire: of the projection's wires the one nearest the reference (the last of equals)."""
    best, take = math.inf, TopoDS_Wire()
    while proj.More():
        w = proj.Current()
        d = BRepExtrema_DistShapeShape(w, reference)
        d.Perform()
        dist = d.Value()
        proj.Next()
        if dist > best:
            continue
        take, best = w, dist
    return take


def _face_wires(face):
    """ProjectOnSurface::getWires: the outer wire (ShapeAnalysis::OuterWire), then the others."""
    outer = ShapeAnalysis.OuterWire_s(face)
    out = [outer]
    for w in _explore(face, TopAbs_WIRE):
        if not w.IsSame(outer):
            out.append(TopoDS.Wire(w))
    return out


class ProjectOnSurface(_LinkSubMixin, PartObject):
    """Part::ProjectOnSurface (Part_ProjectionOnSurface): faces, wires and edges projected along a direction onto a
    support face; a face made a face on the support (extruded back by height in mode All), the result moved by
    offset along the direction."""
    kind, TYPE_ID, TRANSACTION = "Part.ProjectOnSurface", "Part::ProjectOnSurface", "Project on surface"
    POS = ()
    REFS = ("support_face", "projection")
    LINK_SUBS = ("support_face",)
    DEFAULTS = {"mode": "All", "height": 0.0, "offset": 0.0, "direction": (0.0, 0.0, 1.0), "support_face": None,
                "projection": (), **PartObject.COMMON}
    ENUMS = {"mode": PROJECTION_MODES}
    RANGES = {"height": (0.0, math.inf)}

    def normalize(self, key, v):
        if key == "direction":
            try:
                return tuple(float(c) for c in v)
            except (TypeError, ValueError):
                raise F.FeatureError(f"{self.name}.direction: {v!r} is not (x, y, z)") from None
        if key == "projection":             # PropertyLinkSubList: one entry per sub-element
            out = []
            for x in ([v] if isinstance(v, str) else (v or ())):
                if isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[1], (list, tuple)):
                    out += [ref((x[0], s), f"{self.name}.projection") for s in x[1]] or [x[0]]
                else:
                    out.append(ref(x, f"{self.name}.projection"))
            return tuple(out)
        return super().normalize(key, v)

    def _support(self, ctx):
        if self.support_face is None:
            raise F.FeatureError("No support face specified")
        subs = _subs_of(self.support_face)
        if len(subs) != 1:
            raise F.FeatureError("Expect exactly one support face")
        f = ctx.shape(self.support_face, f"{self.name}.SupportFace")
        if f.ShapeType() != TopAbs_FACE:
            raise F.FeatureError("Standard_TypeMismatch: TopoDS::Face")
        return TopoDS.Face(f)

    def shape(self, ctx, params):
        try:
            return self._shape(ctx, params)
        except F.FeatureError:
            raise
        except Exception as e:  # noqa: BLE001 - Standard_Failure, which execute turns into a ValueError
            raise F.FeatureError(getattr(e, "GetMessageString", lambda: str(e))()) from None

    def _shape(self, ctx, params):
        support = self._support(ctx)
        shapes = [ctx.shape(r, f"{self.name}.Projection") for r in self.projection]
        d = gp_Dir(*self.direction)
        results = []
        for s in shapes:
            results += self.projected(s, support, d, params)
        results = self.filtered(results)
        return self.combined(results, params)

    def projected(self, shape, support, d, params):
        """createProjectedWire."""
        if shape is None or shape.IsNull():
            return []
        t = shape.ShapeType()
        if t == TopAbs_FACE:
            wires = self.project_face(TopoDS.Face(shape), support, d)
            face = self.face_from_wires(wires, support)
            solid = self.solid_if_height(face, params)
            if solid is not None and not solid.IsNull():
                return [solid]
            if face is not None and not face.IsNull():
                return [face]
            return wires
        if t in (TopAbs_WIRE, TopAbs_EDGE):
            proj = BRepProj_Projection(shape, support, d)
            take = _projected_wire(proj, shape)
            return [TopoDS.Edge(e) for e in _explore(take, TopAbs_EDGE)]
        return []

    def project_face(self, face, support, d):
        out = []
        for w in _face_wires(face):
            proj = BRepProj_Projection(w, support, d)
            take = _projected_wire(proj, face)
            out.append(_fix_wire([TopoDS.Edge(e) for e in _explore(take, TopAbs_EDGE)], support))
        return out

    def face_from_wires(self, wires, support):
        """createFaceFromWire: the wires remade in the support's parameter space and made one face of it."""
        if not wires:
            return None
        surface = BRep_Tool.Surface_s(support)
        para = []
        for w in wires:
            edges = [TopoDS.Edge(e) for e in _explore(w, TopAbs_EDGE)]
            if not edges:
                continue
            pedges = []
            for e in edges:
                c2d = BRep_Tool.CurveOnSurface_s(e, support, 0.0, 0.0)
                if c2d is None:
                    continue
                first, last = BRep_Tool.Range_s(e, support)
                pedges.append(BRepBuilderAPI_MakeEdge(c2d, surface, first, last).Edge())
            para.append(_fix_wire(pedges, support))
        return self.face_from_parametric(para, surface, support)

    def face_from_parametric(self, wires, surface, support):
        mk = BRepBuilderAPI_MakeFace()
        first = True
        for w in wires:
            if first:
                first = False
                cur = TopoDS.Wire(w.Reversed())
                if support.Orientation() == TopAbs_REVERSED:
                    cur = w
                mk = BRepBuilderAPI_MakeFace(surface, cur)
                fix = ShapeFix_Face(mk.Face())
                fix.Perform()
                if not BRepCheck_Analyzer(fix.Face()).IsValid():
                    mk = BRepBuilderAPI_MakeFace(surface, TopoDS.Wire(cur.Reversed()))
            else:
                temp = BRepBuilderAPI_MakeFace(mk.Face()).Face()
                mk.Add(TopoDS.Wire(w.Reversed()))
                fix = ShapeFix_Face(mk.Face())
                fix.Perform()
                if not BRepCheck_Analyzer(fix.Face()).IsValid():
                    mk = BRepBuilderAPI_MakeFace(temp)
                    mk.Add(TopoDS.Wire(w))
        return mk.Face()

    def solid_if_height(self, face, params):
        if face is None or face.IsNull():
            return face
        h = self.v("height", params)
        if h < CONFUSION or self.mode != "All":
            return face
        v = gp_Vec(*self.direction)
        v.Reverse()
        v.Multiply(h)
        return BRepPrimAPI_MakePrism(face, v).Shape()

    def filtered(self, shapes):
        out = []
        for s in shapes:
            if s is None or s.IsNull():
                continue
            t = s.ShapeType()
            if self.mode == "All":
                out.append(s)
            elif self.mode == "Faces":
                if t == TopAbs_FACE:
                    out.append(s)
            elif t in (TopAbs_EDGE, TopAbs_WIRE):
                out.append(s)
            elif t == TopAbs_FACE:
                out += _face_wires(TopoDS.Face(s))
        return out

    def combined(self, shapes, params):
        """createCompound, moved by getOffsetPlacement; no shapes: a null compound."""
        off = self.v("offset", params)
        loc = None
        if off != 0:
            x, y, z = self.direction
            n = math.sqrt(x * x + y * y + z * z)
            t = gp_Trsf()
            t.SetTranslation(gp_Vec(x / n * off, y / n * off, z / n * off))
            loc = TopLoc_Location(t)
        if not shapes:
            return None
        return compound([s if loc is None else s.Moved(loc) for s in shapes])


SWEEPS = (Loft, Sweep, Offset, Offset2D, Thickness, ProjectOnSurface)
_P.ENUM_PROPS.update({"Part::Sweep": ("Transition",), "Part::Offset": ("Mode", "Join"),
                      "Part::Offset2D": ("Mode", "Join"), "Part::Thickness": ("Mode", "Join"),
                      "Part::ProjectOnSurface": ("Mode",)})
register(*SWEEPS)
