# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of the Part workbench commands that make a Part::Feature holding a shape (https://github.com/FreeCAD/FreeCAD,
# commit 3160daf1e2b6), each file LGPL-2.1-or-later as it states:
#   src/Mod/Part/Gui/CommandSimple.cpp (Part_SimpleCopy, Part_TransformedCopy, Part_ElementCopy): Copyright (c) 2002
#       Jürgen Riegel, 2011 Werner Mayer
#   src/Mod/Part/Gui/Command.cpp (Part_MakeSolid): Copyright (c) 2002 Jürgen Riegel
#   src/Mod/Part/Gui/CrossSections.cpp (Part_CrossSections): Copyright (c) 2012 Werner Mayer
#   src/Mod/Part/App/CrossSection.cpp (TopoCrossSection, behind TopoShape.slice): Copyright (c) 2012 Werner Mayer; 2022
#       Zheng, Lei
#   src/Mod/Part/Gui/TaskShapeBuilder.cpp (Part_Builder): Copyright (c) 2011 Werner Mayer
#   src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementFilledFace, makeElementSolid): Copyright (c) 2022 Zheng, Lei;
#       2023 Ondsel
#   src/Mod/Part/BOPTools/ToleranceFeatures.py (Part_ToleranceSet): Copyright (c) 2024 Eric Price (CorvusCorax)
"""Part objects that FreeCAD makes by running Python that sets a Part::Feature's Shape, and a part file holds as the
parametric recipe of that shape (docs/EDITING_PLAN.md, "Static objects in a part file"):

    Part.Feature("Box001", "Box", label="Cube001")        Part_SimpleCopy and Part_TransformedCopy: the source's placed
                                                          shape, at the source's Placement
    Part.Feature("Box002", ("Box", "Face3"))              Part_ElementCopy: one element of the source's shape
    Part.MakeSolid("Cut_solid", "Cut", label="Cut (Solid)")   Part_MakeSolid: Part.Solid of a shell, or of the shell
                                                          sewn from a compound's faces
    Part.CrossSections("Box_cs", "Box", plane="XZ", positions=[2.0, 4.0, 6.0])   Part_CrossSections: Shape.slice's wires
    Part.ShapeBuilder("Face", mode="Face from vertices", elements=[("Box", "Vertex1"), ...])   Part_Builder
    Part.ToleranceSet("Tolerance", objects=["Box"], min_tolerance=1e-07)       Part_ToleranceSet (a FeaturePython)

FreeCAD's Part::Feature holds the shape it was given; here the part file holds how the shape comes from the objects
before it, so the object follows its source when the source changes (a known difference, ui/PARITY.md). A shape made
this way sits where its source's shape does: a copy at the source's Placement (Feature::onChanged reads the Placement
from the shape's location), the others at the origin with their geometry in the document's frame.
"""
from __future__ import annotations

from . import feature as F
from .feature_part import PartObject, compound, register
from .feature_part_split import CONFUSION, _make_shell, _make_solid, _make_wire, _Python, _sort_edges, _subs

try:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Section
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_Copy, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
                                    BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeWire)
    from OCP.BRepFill import BRepFill_Filling
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
    from OCP.GeomAbs import GeomAbs_C0, GeomAbs_Plane
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_ShapeTolerance
    from OCP.TopAbs import (TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID,
                            TopAbs_VERTEX, TopAbs_WIRE)
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pln, gp_Pnt, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass


def _source_placement(ctx, name):
    from .feature_part_misc import _source_placement as sp
    return sp(ctx, name)


def _name(link):
    return link if isinstance(link, str) else link[0]


class _Static(PartObject):
    """A Part::Feature (or FeaturePython) whose shape a recipe makes. `world(ctx, params)` is the shape in the
    document's frame; the object sits at the origin unless it says (Placement from the shape's location)."""
    FC_TYPE = "Part::Feature"
    INPUTS = ()
    HIDES = ()
    STATIC = True                    # the object's recipe properties are not FreeCAD properties of Part::Feature

    def world(self, ctx, params):
        raise NotImplementedError

    def shape(self, ctx, params):
        return self.world(ctx, params)

    def fc_shape(self, fc):
        """The Shape FreeCAD's command sets, built in freecadcmd from the same recipe."""
        raise NotImplementedError

    def fc_obj(self, fc, shape):
        obj = fc.doc.addObject(self.FC_TYPE, self.name)
        obj.Shape = shape
        if getattr(self, "placement", None) is not None:
            (x, y, z), ypr = self.placement
            obj.Placement = fc.App.Placement(fc.App.Vector(x, y, z), fc.App.Rotation(*ypr))
        if self.label:
            obj.Label = self.label
        return obj

    def to_freecad(self, fc):
        fc.doc.recompute()
        return self.fc_obj(fc, self.fc_shape(fc))

    def fc_link_shape(self, fc, link, needs_element=False):
        """Part.getShape(obj, sub, needSubElement=...) of a link."""
        import Part as FCPart
        name, sub = (link, "") if isinstance(link, str) else link
        return FCPart.getShape(fc.made[name], sub, needSubElement=needs_element)


# ── Part_SimpleCopy, Part_TransformedCopy, Part_ElementCopy ──────────────────────────────────────────────────────

class Feature(_Static):
    """Part::Feature as _copyShape leaves it: `__shape = Part.getShape(obj, sub, needSubElement=...)` set as the Shape of
    a new Part::Feature (named after the source, labelled with its Label). The source "Box" is the whole shape (Simple
    and Transformed copy); ("Box", "Face3") is Element copy's `.copy()` of that element. The copy's Placement is the
    shape's location, the source's."""
    kind, TYPE_ID, TRANSACTION = "Part.Feature", "Part::Feature", "Simple copy"
    POS = ("source",)
    REFS = ("source",)
    DEFAULTS = {"source": None, **PartObject.COMMON}

    def _vertex(self):
        """A vertex copy has no location: its point is the placed one and its Placement the identity."""
        return not isinstance(self.source, str) and self.source[1].startswith("Vertex")

    def built_shape(self, ctx, params):
        if self.source is None:
            raise F.FeatureError("No part object linked.")
        shape = ctx.shape(self.source, f"{self.name}.Source")
        if self._vertex():
            return shape
        pl = _source_placement(ctx, _name(self.source))
        return shape.Moved(TopLoc_Location(pl.inverse().trsf()))

    def base_placement(self, ctx, params):
        if self.source is None or self._vertex() or getattr(self, "placement", None) is not None:
            return super().base_placement(ctx, params)
        return _source_placement(ctx, _name(self.source))

    def fc_shape(self, fc):
        sub = self.source[1] if not isinstance(self.source, str) else ""
        shape = self.fc_link_shape(fc, self.source, needs_element=bool(sub))
        return shape.copy() if sub else shape


# ── Part_MakeSolid ───────────────────────────────────────────────────────────────────────────────────────────────

class MakeSolid(_Static):
    """Part_MakeSolid: a compound or compsolid's faces sewn into a shell and made a solid, or a shell made a solid
    (`Part.Solid(Part.Shell(shape.Faces))`, `Part.Solid(shape)`). The command skips a solid and every other shape."""
    kind, TYPE_ID, TRANSACTION = "Part.MakeSolid", "Part::MakeSolid", "Make solid"
    POS = ("source",)
    REFS = ("source",)
    DEFAULTS = {"source": None, **PartObject.COMMON}

    def world(self, ctx, params):
        if self.source is None:
            raise F.FeatureError("No part object linked.")
        src = ctx.shape(self.source, f"{self.name}.Source")
        kind = src.ShapeType()
        if kind in (TopAbs_COMPOUND, TopAbs_COMPSOLID):
            shell = _make_shell(_subs(src, TopAbs_FACE))
        elif kind == TopAbs_SHELL:
            shell = src
        else:
            raise F.FeatureError("the shape is neither a shell nor a compound")
        return _make_solid(shell)

    def fc_shape(self, fc):
        import Part as FCPart
        src = fc.made[self.source if isinstance(self.source, str) else self.source[0]]
        if src.Shape.ShapeType in ("Compound", "CompSolid"):
            return FCPart.Solid(FCPart.Shell(src.Shape.Faces))
        return FCPart.Solid(src.Shape)


def can_make_solid(shape_type: str) -> str | None:
    """CmdPartMakeSolid's message for a shape it skips, or None when it makes a solid."""
    if shape_type == "Solid":
        return "{} is ignored because it is already a solid."
    if shape_type not in ("Compound", "CompSolid", "Shell"):
        return "{} is ignored because it is neither a shell nor a compound."
    return None


# ── Part_CrossSections ───────────────────────────────────────────────────────────────────────────────────────────

PLANES = {"XY": (0.0, 0.0, 1.0), "XZ": (0.0, 1.0, 0.0), "YZ": (1.0, 0.0, 0.0)}


def _slice_non_solid(a, b, c, d, shape, wires):
    """TopoCrossSection::sliceNonSolid: the section with the plane, its edges made wires."""
    cs = BRepAlgoAPI_Section(shape, gp_Pln(a, b, c, -d))
    cs.Build()
    if cs.IsDone():
        wires.extend(F._wires([TopoDS.Edge(e) for e in _subs(cs.Shape(), TopAbs_EDGE)]))


def _slice_solid(a, b, c, d, shape, wires):
    """TopoCrossSection::sliceSolid: the solid cut by the half space behind the plane, the planar faces left on the
    plane made wires."""
    plane = gp_Pln(a, b, c, -d)
    face = BRepBuilderAPI_MakeFace(plane).Face()
    v = gp_Vec(a, b, c)
    v.Normalize()
    v.Multiply(d + 1.0)
    ref = gp_Pnt(0.0, 0.0, 0.0)
    ref.Translate(v)
    half = BRepPrimAPI_MakeHalfSpace(face, ref).Solid()
    cut = BRepAlgoAPI_Cut(shape, half)
    cut.Build()
    if not cut.IsDone():
        return
    for f in _subs(cut.Shape(), TopAbs_FACE):
        adapt = BRepAdaptor_Surface(TopoDS.Face(f))
        if adapt.GetType() == GeomAbs_Plane:
            pl = adapt.Plane()
            if pl.Axis().IsParallel(plane.Axis(), CONFUSION) and pl.Distance(plane.Location()) < CONFUSION:
                wires.extend(F._wires([TopoDS.Edge(e) for e in _subs(f, TopAbs_EDGE)]))


def slice_shape(shape, normal, d):
    """TopoShape.slice(normal, d): the wires where the plane through distance d along normal cuts the shape's solids
    (or, with none, its shells, or its faces)."""
    a, b, c = normal
    wires: list = []
    solids = _subs(shape, TopAbs_SOLID)
    if solids:
        for s in solids:
            _slice_solid(a, b, c, d, s, wires)
    else:
        shells = _subs(shape, TopAbs_SHELL)
        if shells:
            for s in shells:
                _slice_non_solid(a, b, c, d, s, wires)
        else:
            for s in _subs(shape, TopAbs_FACE):
                _slice_non_solid(a, b, c, d, s, wires)
    return wires


def cross_section_planes(bbox, plane, position, count=1, distance=0.0, both=False, sections=True):
    """CrossSections::getPlanes: the positions of the planes the dialog's Sections box gives (Count, Distance, On both
    sides), or the one Position when the box is off."""
    if not sections:
        return [position]
    if both:
        start = position - 0.5 * (count - 1) * distance
        return [start + i * distance for i in range(count)]
    return [position + i * distance for i in range(count)]


class CrossSections(_Static):
    """Part_CrossSections: `shape.slice(Vector(a, b, c), d)` for each position, the wires of all of them one compound
    ("<name>_cs"). plane is the dialog's Guiding Plane (XY: normal Z, XZ: normal Y, YZ: normal X)."""
    kind, TYPE_ID, TRANSACTION = "Part.CrossSections", "Part::CrossSections", "Cross-sections"
    POS = ("base",)
    REFS = ("base",)
    DEFAULTS = {"base": None, "plane": "XY", "positions": (0.0,), **PartObject.COMMON}
    ENUMS = {"plane": tuple(PLANES)}

    def world(self, ctx, params):
        if self.base is None:
            raise F.FeatureError("No part object linked.")
        src = ctx.shape(self.base, f"{self.name}.Base")
        normal = PLANES[self.plane]
        wires: list = []
        for d in self.positions:
            wires.extend(slice_shape(src, normal, F.value(d, params, "positions")))
        return compound(wires)

    def fc_shape(self, fc):
        import Part as FCPart
        src = fc.made[_name(self.base)].Shape
        normal = fc.App.Vector(*PLANES[self.plane])
        wires = []
        for d in self.positions:
            wires.extend(src.slice(normal, d))
        return FCPart.makeCompound(wires)


# ── Part_Builder ─────────────────────────────────────────────────────────────────────────────────────────────────

MODES = ("Edge from vertices", "Wire from edges", "Face from vertices", "Face from edges", "Shell from faces",
         "Solid from shell")
NAMES = {"Edge from vertices": "Edge", "Wire from edges": "Wire", "Face from vertices": "Face",
         "Face from edges": "Face", "Shell from faces": "Shell", "Solid from shell": "Solid"}
MIN_ELEMENTS = {"Edge from vertices": 2, "Wire from edges": 1, "Face from vertices": 3, "Face from edges": 1,
                "Shell from faces": 2, "Solid from shell": 1}
SELECT = {"Edge from vertices": "Vertex", "Wire from edges": "Edge", "Face from vertices": "Vertex",
          "Face from edges": "Edge", "Shell from faces": "Face", "Solid from shell": None}
WRONG = {"Edge from vertices": "Select two vertices", "Wire from edges": "Select at least 1 edge",
         "Face from vertices": "Select three or more vertices", "Face from edges": "Select at least 1 edge",
         "Shell from faces": "Select at least 2 faces", "Solid from shell": "Select only 1 shape object"}


def make_filled_face(shapes):
    """Part.makeFilledFace(shapes) with its defaults: TopoShape::makeElementFilledFace over BRepOffsetAPI_MakeFilling
    (degree 3, 15 points on a curve, 2 iterations, tolerances 1e-5, 1e-4, 1e-2, 1e-1, degree 8, 9 segments): the wire
    (the closed one first) is the boundary, every other edge a constraint."""
    shapes = list(shapes)
    bound = None
    best = -1
    for i, s in enumerate(shapes):
        if s is None or s.IsNull() or s.ShapeType() != TopAbs_WIRE or not _subs(s, TopAbs_EDGE):
            continue
        if BRep_Tool.IsClosed_s(s):
            best = i
            break
        if best < 0:
            best = i
    wires: list = []
    if best >= 0:
        bound = shapes.pop(best)
    else:
        edges = [s for s in shapes if s.ShapeType() == TopAbs_EDGE]
        shapes = [s for s in shapes if s.ShapeType() != TopAbs_EDGE]
        if edges:
            wires = F._wires([TopoDS.Edge(e) for e in edges])
        best = -1
        for i, s in enumerate(wires):
            if not _subs(s, TopAbs_EDGE):
                continue
            if BRep_Tool.IsClosed_s(s):
                best = i
                break
            if best < 0:
                best = i
        if best >= 0:
            bound = wires.pop(best)
    if bound is None:
        raise F.FeatureError("No boundary wire")
    shapes += wires
    bound = _fix(bound, CONFUSION, CONFUSION, CONFUSION)
    maker = BRepFill_Filling(3, 15, 2, False, 1e-5, 1e-4, 1e-2, 1e-1, 8, 9)
    for e in _ordered_edges(bound):
        maker.Add(TopoDS.Edge(e), GeomAbs_C0, True)
    for s in shapes:
        if s is None or s.IsNull():
            continue
        kind = s.ShapeType()
        if kind == TopAbs_WIRE:
            for e in _subs(s, TopAbs_EDGE):
                maker.Add(TopoDS.Edge(e), GeomAbs_C0, False)
        elif kind == TopAbs_EDGE:
            maker.Add(TopoDS.Edge(s), GeomAbs_C0, False)
        elif kind == TopAbs_FACE:
            maker.Add(TopoDS.Face(s), GeomAbs_C0)
        elif kind == TopAbs_VERTEX:
            maker.Add(BRep_Tool.Pnt_s(TopoDS.Vertex(s)))
    maker.Build()
    if not maker.IsDone():
        raise F.FeatureError("Failed to created face by filling edges")
    return maker.Face()


def _ordered_edges(wire):
    """TopoShape::getOrderedEdges: the wire's edges in connection order (BRepTools_WireExplorer)."""
    from OCP.BRepTools import BRepTools_WireExplorer
    out = []
    if wire.ShapeType() == TopAbs_WIRE:
        ex = BRepTools_WireExplorer(TopoDS.Wire(wire))
        while ex.More():
            out.append(ex.Current())
            ex.Next()
        return out
    return _subs(wire, TopAbs_EDGE)


class ShapeBuilder(_Static):
    """Part_Builder (TaskShapeBuilder): one of its six modes on the elements picked, the Python it runs:
    Edge from vertices `Part.makeLine(p0, p1)`; Wire from edges `Part.Wire(Part.__sortEdges__(edges))`; Face from
    vertices `Part.Face(Part.makePolygon(points, True))` (Planar) or `Part.makeFilledFace(polygon.Edges)`; Face from
    edges `Part.Face(Part.Wire(sorted))` or `Part.makeFilledFace(sorted)`; Shell from faces `Part.Shell(faces)` (All
    faces: the faces of every shape picked from), refined by removeSplitter when Refine shape is on; Solid from shell
    `Part.Solid(shell)` likewise. The new object is named Edge, Wire, Face, Shell or Solid."""
    kind, TYPE_ID, TRANSACTION = "Part.ShapeBuilder", "Part::ShapeBuilder", "Shape builder"
    POS = ("mode",)
    REFS = ("elements",)
    DEFAULTS = {"mode": MODES[0], "elements": (), "planar": False, "refine": True, "all_faces": False,
                **PartObject.COMMON}
    ENUMS = {"mode": MODES}

    def _pick(self, ctx, what):
        """The picked shapes: a (name, "VertexN") tuple is that element, a bare name the whole shape."""
        return [ctx.shape(r, f"{self.name}.Elements") for r in self.elements]

    def world(self, ctx, params):
        from .feature_part_bool import refine
        mode = self.mode
        picks = self._pick(ctx, SELECT[mode])
        if len(picks) < MIN_ELEMENTS[mode] or (mode in ("Edge from vertices", "Solid from shell")
                                                and len(picks) != MIN_ELEMENTS[mode]):
            raise F.FeatureError(WRONG[mode])
        if mode == "Edge from vertices":
            p = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in picks]
            mk = BRepBuilderAPI_MakeEdge(p[0], p[1])
            if not mk.IsDone():
                raise F.FeatureError("Failed to create edge")
            return mk.Edge()
        if mode == "Wire from edges":
            return _make_wire(_sort_edges(picks)[0])
        if mode == "Face from vertices":
            poly = _polygon([BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in picks])
            if self.planar:
                return _face_of_wire(poly)
            return make_filled_face(_subs(poly, TopAbs_EDGE))
        if mode == "Face from edges":
            chain = _sort_edges(picks)[0]
            if self.planar:
                return _face_of_wire(_make_wire(chain))
            return make_filled_face(chain)
        if mode == "Shell from faces":
            faces = picks
            if self.all_faces:
                faces = []
                seen: list = []
                for r in self.elements:
                    n = _name(r)
                    if n not in seen:
                        seen.append(n)
                        faces += _subs(ctx.shape(n, f"{self.name}.Elements"), TopAbs_FACE)
            shell = _make_shell(faces)
            if shell is None or shell.IsNull():
                raise F.FeatureError("Failed to create shell")
            return refine(shell) if self.refine else shell
        shell = picks[0]
        if shell.ShapeType() != TopAbs_SHELL:
            raise F.FeatureError("Part object is not a shell")
        solid = _make_solid(shell)
        if solid is None or solid.IsNull():
            raise F.FeatureError("Failed to create solid")
        return refine(solid) if self.refine else solid

    def fc_shape(self, fc):
        import Part as FCPart
        mode = self.mode

        def sub(r):
            n, s = (r, "") if isinstance(r, str) else r
            sh = fc.made[n].Shape
            return sh.getElement(s) if s else sh
        picks = [sub(r) for r in self.elements]
        if mode == "Edge from vertices":
            return FCPart.makeLine(picks[0].Point, picks[1].Point)
        if mode == "Wire from edges":
            return FCPart.Wire(FCPart.__sortEdges__(picks))
        if mode == "Face from vertices":
            poly = FCPart.makePolygon([v.Point for v in picks], True)
            return FCPart.Face(poly) if self.planar else FCPart.makeFilledFace(poly.Edges)
        if mode == "Face from edges":
            return FCPart.Face(FCPart.Wire(FCPart.__sortEdges__(picks))) if self.planar \
                else FCPart.makeFilledFace(FCPart.__sortEdges__(picks))
        if mode == "Shell from faces":
            faces = picks
            if self.all_faces:
                faces = []
                seen = []
                for r in self.elements:
                    n = _name(r)
                    if n not in seen:
                        seen.append(n)
                        faces += fc.made[n].Shape.Faces
            shell = FCPart.Shell(faces)
            return shell.removeSplitter() if self.refine else shell
        shell = picks[0]
        solid = FCPart.Solid(shell)
        return solid.removeSplitter() if self.refine else solid


def _polygon(points):
    """Part.makePolygon(points, True): the polygon closed back to its first vertex."""
    mk = BRepBuilderAPI_MakePolygon()
    for p in points:
        mk.Add(p)
    if not mk.IsDone():
        raise F.FeatureError("Cannot create polygon because less than two vertices are given")
    if not mk.FirstVertex().IsSame(mk.LastVertex()):
        mk.Add(mk.FirstVertex())
    return mk.Wire()


def _face_of_wire(wire):
    """Part.Face(wire): BRepBuilderAPI_MakeFace on the wire, a plane found if there is one."""
    if wire is None or wire.IsNull():
        raise F.FeatureError("cannot create face out of empty wire")
    mk = BRepBuilderAPI_MakeFace(TopoDS.Wire(wire))
    if not mk.IsDone():
        raise F.FeatureError("Failed to create face from wire")
    return mk.Face()


# ── Part_ToleranceSet ────────────────────────────────────────────────────────────────────────────────────────────

class ToleranceSet(_Python):
    """BOPTools.ToleranceFeatures.FeatureToleranceSet (Part_ToleranceSet): a copy of each of Objects with every
    tolerance in it limited to at least min_tolerance (and at most max_tolerance when that is more than 0), refined
    when Refine is on; several make one compound. The command gives it min_tolerance 1e-7."""
    kind, TYPE_ID, TRANSACTION = "Part.ToleranceSet", "Part::ToleranceSet", "Create ToleranceSet"
    PROXY = ("BOPTools.ToleranceFeatures", "FeatureToleranceSet")
    POS = ("objects",)
    REFS = ("objects",)
    INPUTS = ("objects",)
    PROPS = {"objects": "Objects", "refine": "Refine", "min_tolerance": "minTolerance", "max_tolerance": "maxTolerance"}
    DEFAULTS = {"objects": (), "refine": False, "min_tolerance": 0.0, "max_tolerance": 0.0, **PartObject.COMMON}

    def shape(self, ctx, params):
        from .feature_part_bool import refine
        lo, hi = self.v("min_tolerance", params), self.v("max_tolerance", params)
        shapes = []
        for o in self.objects:
            sh = BRepBuilderAPI_Copy(ctx.shape(o, f"{self.name}.Objects")).Shape()
            ShapeFix_ShapeTolerance().LimitTolerance(sh, lo, hi)
            if self.refine:
                sh = _fix(sh, lo, lo, hi)
                sh = refine(sh)
                sh = _fix(sh, lo, lo, hi)
            shapes.append(sh)
        if not shapes:
            raise F.FeatureError("list index out of range")
        # Feature::onChanged sets the Shape's location to the object's Placement whenever Shape is set during a
        # recompute (a FeaturePython's execute): the copy's own location goes, a compound's children keep theirs
        return (compound(shapes) if len(shapes) > 1 else shapes[0]).Located(TopLoc_Location())


def _fix(shape, precision, mintol, maxtol):
    """TopoShape::fix(precision, mintol, maxtol): ShapeFix_Shape, with the tools its type calls."""
    kind = shape.ShapeType()
    fix = ShapeFix_Shape(shape)
    fix.SetPrecision(precision)
    fix.SetMinTolerance(mintol)
    fix.SetMaxTolerance(maxtol)
    fix.Perform()
    if kind == TopAbs_SOLID:
        fix.FixWireTool().Perform()
        fix.FixFaceTool().Perform()
        fix.FixShellTool().Perform()
        fix.FixSolidTool().Perform()
        return fix.FixSolidTool().Shape()
    if kind == TopAbs_SHELL:
        fix.FixWireTool().Perform()
        fix.FixFaceTool().Perform()
        fix.FixShellTool().Perform()
        return fix.FixShellTool().Shape()
    if kind == TopAbs_FACE:
        fix.FixWireTool().Perform()
        fix.FixFaceTool().Perform()
        return fix.Shape()
    if kind == TopAbs_WIRE:
        fix.FixWireTool().Perform()
        return fix.Shape()
    return fix.Shape()


STATIC = (Feature, MakeSolid, CrossSections, ShapeBuilder, ToleranceSet)
register(*STATIC)
