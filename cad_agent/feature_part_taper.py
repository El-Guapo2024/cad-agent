# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's tapered extrusion (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file
# LGPL-2.1-or-later as it states:
#   src/Mod/Part/App/FeatureExtrusion.cpp (Extrusion::extrudeShape, its tapered branch): Copyright (c) 2008 Werner Mayer
#   src/Mod/Part/App/ExtrusionHelper.cpp (makeElementDraft, createTaperedPrismOffset): Copyright (c) 2022 Uwe Stöhr
#   src/Mod/Part/App/BRepOffsetAPI_MakeOffsetFix.cpp: Copyright (c) 2019 Werner Mayer
#   src/Mod/Part/App/TopoShapeExpansion.cpp (splitWires, makeElementBoolean, makeElementShell, makeElementCompound):
#   Copyright (c) 2022 Zheng, Lei; 2023 Ondsel
"""Part::Extrusion with a taper (TaperAngle, TaperAngleRev): ExtrusionHelper::makeElementDraft, every wire of the
source lofted (BRepOffsetAPI_ThruSections, ruled) through its 2D offsets at the ends, a face's holes lofted on their
own (their taper inverted, InnerWireTaper "Inverted", or the same, "SameAsOuter") and cut from its outer loft.

    tapered(source, u, fwd, rev, taper_fwd_rad, taper_rev_rad, solid, maker, inner_wire_taper)

is what feature_part_ops.Extrusion calls: u the direction (a gp_Dir, already reversed when Reversed), fwd and rev the
lengths (after Symmetric's halving), maker the face maker's class name, inner_wire_taper the enumeration's string.
OffsetFix is FreeCAD's BRepOffsetAPI_MakeOffsetFix, which Part::Offset2D uses too.
"""
from __future__ import annotations

import math

from . import feature as F
from .feature_part import compound

try:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_MakeWire, BRepBuilderAPI_DisconnectedWire
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset, BRepOffsetAPI_ThruSections
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Arc, GeomAbs_Intersection
    from OCP.ShapeFix import ShapeFix_Wire
    from OCP.ShapeUpgrade import ShapeUpgrade_ShellSewing
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_FORWARD, TopAbs_REVERSED, \
        TopAbs_SHELL, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS, TopoDS_Iterator, TopoDS_Shell, TopoDS_Wire
    from OCP.BRep import BRep_Builder
    from OCP.gp import gp_Trsf, gp_Vec
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7


def _explore(shape, kind, avoid=None):
    out = []
    ex = TopExp_Explorer(shape, kind) if avoid is None else TopExp_Explorer(shape, kind, avoid)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _children(shape):
    out = []
    it = TopoDS_Iterator(shape)
    while it.More():
        out.append(it.Value())
        it.Next()
    return out


def _list(lst):
    """A TopTools_ListOfShape as a Python list."""
    return list(lst)


# ── BRepOffsetAPI_MakeOffsetFix ──────────────────────────────────────────────────────────────────────────────────

class OffsetFix:
    """BRepOffsetAPI_MakeOffsetFix: BRepOffsetAPI_MakeOffset, a one-edge wire offset with its edge's placement taken
    off and put back on the result (OCCT offsets a placed circle wrongly otherwise)."""

    def __init__(self, join=None, open_result=False):
        self.mk = BRepOffsetAPI_MakeOffset()
        if join is not None:
            self.mk.Init(join, open_result)
        self.locations = []
        self.result = None

    def init(self, join, open_result=False):
        self.mk.Init(join, open_result)

    def add_wire(self, spine):
        wire = spine
        edges = _explore(wire, TopAbs_EDGE)
        if len(edges) == 1:
            mkw = BRepBuilderAPI_MakeWire()
            for e in edges:
                loc = e.Location()
                edge = TopoDS.Edge(e.Located(TopLoc_Location()))
                mkw.Add(edge)
                self.locations.append((edge, loc))
            wire = TopoDS.Wire(mkw.Wire().Oriented(spine.Orientation()))
        self.mk.AddWire(wire)
        self.result = None

    def perform(self, offset, alt=0.0):
        self.mk.Perform(offset, alt)

    def is_done(self):
        return self.mk.IsDone()

    def _make_wire(self, wire):
        amap = _explore(wire, TopAbs_EDGE)
        edge_list = []
        for e0, loc in self.locations:
            new = _list(self.mk.Generated(e0))
            for v in _explore(e0, TopAbs_VERTEX):
                ne = self.mk.Generated(v)
                if not ne.IsEmpty():
                    new += _list(ne)
            for s in new:
                if any(s.IsSame(m) for m in amap):
                    edge_list.append(TopoDS.Edge(s.Moved(loc)))
        if edge_list:
            mkw = BRepBuilderAPI_MakeWire()
            mkw.Add(edge_list.pop(0))
            wire = mkw.Wire()
            found = True
            while found:
                found = False
                for i, e in enumerate(edge_list):
                    mkw.Add(e)
                    if mkw.Error() != BRepBuilderAPI_DisconnectedWire:
                        found = True
                        edge_list.pop(i)
                        wire = mkw.Wire()
                        break
        return wire

    def shape(self):
        if self.result is None:
            r = self.mk.Shape()
            if r.IsNull():
                self.result = r
                return r
            if r.ShapeType() == TopAbs_WIRE:
                r = self._make_wire(TopoDS.Wire(r))
            elif r.ShapeType() == TopAbs_COMPOUND:
                r = compound([self._make_wire(TopoDS.Wire(w)) for w in _explore(r, TopAbs_WIRE)])
            self.result = r
        return self.result


# ── TopoShape helpers ────────────────────────────────────────────────────────────────────────────────────────────

NO_REORIENT, REORIENT, REORIENT_FORWARD, REORIENT_REVERSED = range(4)


def split_wires(shape, reorient=REORIENT):
    """TopoShape::splitWires: (the outer wire, the inner wires) of a face (BRepTools::OuterWire), each reoriented."""
    outer = None
    if shape.ShapeType() == TopAbs_FACE:
        outer = BRepTools.OuterWire_s(TopoDS.Face(shape))
    elif F._count(shape, TopAbs_FACE) == 1:
        outer = BRepTools.OuterWire_s(TopoDS.Face(F._subs(shape, TopAbs_FACE)[0]))
    if outer is None or outer.IsNull():
        return None, []
    if reorient == REORIENT_REVERSED:
        o_out = o_in = TopAbs_REVERSED
    elif reorient == REORIENT_FORWARD:
        o_out = o_in = TopAbs_FORWARD
    else:
        o_out, o_in = TopAbs_FORWARD, TopAbs_REVERSED

    def fix(w, orient):
        if reorient == NO_REORIENT:
            return w
        edges = F._subs(w, TopAbs_EDGE)
        if len(edges) == 1:
            edge = edges[0]
            if edge.Orientation() == orient:
                if w.Orientation() == orient:
                    return w
            else:
                edge = edge.Oriented(orient)
            return BRepBuilderAPI_MakeWire(TopoDS.Edge(edge)).Shape()
        if w.Orientation() != orient:
            return w.Oriented(orient)
        return w

    out, inner = None, []
    for w in F._subs(shape, TopAbs_WIRE):
        if w.IsSame(outer):
            out = fix(w, o_out)
            continue
        inner.append(fix(w, o_in))
    return out, inner


def element_compound(shapes, force=False):
    """makeElementCompound: one shape alone is itself (returnShape), unless force (forceCompound)."""
    if len(shapes) == 1 and not force:
        return shapes[0]
    return compound(shapes)


def shell_silent(shape):
    """makeElementShell(silent=true): a compound of nothing but faces made one shell."""
    if shape is None or shape.IsNull() or shape.ShapeType() != TopAbs_COMPOUND:
        return shape
    if _explore(shape, TopAbs_SHELL) or _explore(shape, TopAbs_WIRE, TopAbs_FACE) or \
            _explore(shape, TopAbs_EDGE, TopAbs_WIRE) or _explore(shape, TopAbs_VERTEX, TopAbs_EDGE):
        return shape
    b = BRep_Builder()
    shell = TopoDS_Shell()
    b.MakeShell(shell)
    try:
        for f in F._subs(shape, TopAbs_FACE):
            b.Add(shell, f)
        out = shell
        if not BRepCheck_Analyzer(shell).IsValid():
            out = ShapeUpgrade_ShellSewing().ApplySewing(shell)
        if out is None or out.IsNull() or out.ShapeType() != TopAbs_SHELL:
            return shape
        return out
    except Exception:  # noqa: BLE001 - Standard_Failure, which the silent shell ignores
        return shape


def element_cut(shapes):
    """makeElementCut(shapes) (makeElementBoolean, tolerance -1: the automatic fuzzy value): the tools' compounds
    expanded, FCBRepAlgoAPI_Cut, then the silent shell."""
    from .feature_part_bool import auto_fuzzy
    inputs = []
    for i in range(1, len(shapes)):
        s = shapes[i]
        if s is None or s.IsNull():
            raise F.FeatureError("Null input shape")
        if s.ShapeType() == TopAbs_COMPOUND:
            if not inputs:
                inputs += shapes[:i]
            _expand(s, inputs)
        elif inputs:
            inputs.append(s)
    inputs = inputs or list(shapes)
    if len(inputs) == 1:
        return inputs[0]
    res = fc_cut(inputs[0], inputs[1:], auto_fuzzy(inputs))
    if res is None:
        raise F.FeatureError("BRep_API: command not done")
    return shell_silent(res)


def fc_cut(base, tools, fuzzy):
    """FCBRepAlgoAPI_Cut::Build: a compound tool alone fused first (RecursiveCutFusedTools), a compound argument cut
    child by child (RecursiveCutCompound); None when OCCT did not finish."""
    from .feature_part_bool import _run, fc_boolean
    if len(tools) == 1 and tools[0].ShapeType() == TopAbs_COMPOUND:
        return fc_boolean("cut", base, tools[0], fuzzy)
    if base.ShapeType() == TopAbs_COMPOUND:
        parts = [fc_cut(c, tools, fuzzy) for c in _children(base)]
        return None if any(p is None for p in parts) else compound(parts)
    return _run("cut", [base], tools, fuzzy)


def _expand(shape, out):
    """expandCompound."""
    if shape.ShapeType() != TopAbs_COMPOUND:
        out.append(shape)
        return
    for c in _children(shape):
        _expand(c, out)


# ── ExtrusionHelper ──────────────────────────────────────────────────────────────────────────────────────────────

def tapered_offset(wire, translation, offset, is_second):
    """ExtrusionHelper::createTaperedPrismOffset: the wire moved by translation and offset in its plane; a null wire
    when the offset is not one wire."""
    t = gp_Trsf()
    t.SetTranslation(translation)
    moved = TopoDS.Wire(wire.Moved(TopLoc_Location(t)))
    if abs(offset) > CONFUSION:
        mk = OffsetFix()
        mk.init(GeomAbs_Arc)
        mk.init(GeomAbs_Intersection)
        mk.add_wire(moved)
        mk.perform(offset)
        shape = mk.shape()
        if not mk.is_done():
            raise F.FeatureError("Extrusion: Offset could not be created")
    else:
        shape = moved
    if shape.IsNull():
        raise F.FeatureError("Extrusion: end face of tapered extrusion is empty")
    if shape.ShapeType() == TopAbs_WIRE:
        return TopoDS.Wire(shape)
    if shape.ShapeType() == TopAbs_EDGE:
        return BRepBuilderAPI_MakeWire(TopoDS.Edge(shape)).Wire()
    return TopoDS_Wire()


class _Params:
    def __init__(self, u, fwd, rev, t1, t2, solid, maker, inner):
        self.u, self.fwd, self.rev, self.t1, self.t2 = u, fwd, rev, t1, t2
        self.solid, self.maker, self.inner = solid, maker, inner

    def inverted(self):
        return _Params(self.u, self.fwd, self.rev, -self.t1, -self.t2, self.solid, self.maker, self.inner)


def make_draft(p, shape, drafts):
    """ExtrusionHelper::makeElementDraft: the drafted lofts of shape appended to drafts."""
    from .feature_part_face import make_face
    dist_fwd = math.tan(p.t1) * p.fwd
    dist_rev = math.tan(p.t2) * p.rev
    vec_fwd = gp_Vec(p.u).Multiplied(p.fwd)
    vec_rev = gp_Vec(p.u.Reversed()).Multiplied(p.rev)
    b_fwd = abs(p.fwd) > CONFUSION
    b_rev = abs(p.rev) > CONFUSION
    b_mid = not b_fwd or not b_rev or p.fwd * p.rev > 0.0
    if shape is None or shape.IsNull():
        raise F.FeatureError("Not a valid shape")
    if p.solid and not F._count(shape, TopAbs_FACE):
        shape = make_face(shape, p.maker)
        if shape is None or shape.IsNull():
            raise F.FeatureError("Null shape")
    if shape.ShapeType() == TopAbs_FACE:
        outer, inner = split_wires(shape, REORIENT_FORWARD)
        if outer is None:
            raise F.FeatureError("Missing outer wire")
        if not inner:
            shape = outer
        else:
            pos = len(drafts)
            make_draft(p, outer, drafts)
            if len(drafts) != pos + 1:
                raise F.FeatureError("Failed to make drafted extrusion")
            holes = []
            for w in inner:
                make_draft(p.inverted() if p.inner == "Inverted" else p, w, holes)
            if not holes:
                raise F.FeatureError("Failed to make drafted extrusion with inner hole")
            drafts[-1] = element_cut([drafts[-1]] + holes)
            return
    source = None
    if shape.ShapeType() == TopAbs_WIRE:
        fix = ShapeFix_Wire()
        fix.Load(TopoDS.Wire(shape))
        fix.FixReorder()
        fix.FixConnected()
        fix.FixClosed()
        source = fix.Wire()
    elif shape.ShapeType() == TopAbs_COMPOUND:
        for s in _children(shape):
            make_draft(p, s, drafts)
    else:
        raise F.FeatureError("Only a wire or a face is supported")
    if source is not None and not source.IsNull():
        sections = []
        if b_rev:
            sections.append(tapered_offset(source, vec_rev, dist_rev, False))
        if b_mid:
            sections.append(source)
        if b_fwd:
            sections.append(tapered_offset(source, vec_fwd, dist_fwd, False))
        mk = BRepOffsetAPI_ThruSections(bool(p.solid), True)
        for s in sections:
            mk.AddWire(s)
        mk.Build()
        drafts.append(mk.Shape())


def tapered(source, u, fwd, rev, taper_fwd, taper_rev, solid, maker, inner_wire_taper):
    """Extrusion::extrudeShape, tapered: the source copied (makeElementCopy), drafted, the drafts one compound
    (returnShape: one draft is itself)."""
    if source is None or source.IsNull():
        raise F.FeatureError("Not a valid shape")
    shape = BRepBuilderAPI_Copy(source).Shape()
    drafts = []
    make_draft(_Params(u, fwd, rev, taper_fwd, taper_rev, solid, maker, inner_wire_taper), shape, drafts)
    if not drafts:
        raise F.FeatureError("Drafting shape failed")
    return element_compound(drafts)
