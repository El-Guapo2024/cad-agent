# SPDX-License-Identifier: LGPL-2.1-or-later
# A port of FreeCAD's Part split, join and compound tools (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6),
# each file LGPL-2.1-or-later as it states:
#   src/Mod/Part/BOPTools/GeneralFuseResult.py, SplitAPI.py, SplitFeatures.py, JoinAPI.py, JoinFeatures.py,
#   ShapeMerge.py, Utils.py: Copyright (c) 2016 Victor Titov (DeepSOIC)
#   src/Mod/Part/CompoundTools/CompoundFilter.py, Explode.py, _CommandCompoundFilter.py, _CommandExplodeCompound.py:
#   Copyright (c) 2016 Victor Titov (DeepSOIC), 2017 Bernd Hahnebach
#   src/Mod/Part/App/TopoShapeExpansion.cpp (makeElementGeneralFuse, makeElementBoolean, makeElementShell,
#   makeElementSolid, makeElementCompound): Copyright (c) 2022 Zheng, Lei; 2023 Ondsel
#   src/Mod/Part/App/TopoShape.cpp, TopoShapePyImp.cpp, TopoShapeWirePyImp.cpp, AppPartPy.cpp (sort_Edges),
#   FCBRepAlgoAPI_BooleanOperation.cpp: Copyright (c) 2002 Jürgen Riegel; 2024 Eric Price
"""Part's split, join and compound tools: BooleanFragments, Slice, XOR, Connect, Embed, Cutout, CompoundFilter.

    Part.BooleanFragments("BooleanFragments", ["Box", "Sphere"])          Part_BooleanFragments (mode "Standard")
    Part.Slice("Slice", "Box", ["Plane"], mode="Split")                   Part_Slice (the command sets "Split")
    Part.XOR("XOR", ["Box", "Sphere"])                                    Part_XOR
    Part.Connect("Connect", ["Tube", "Tube001"])                          Part_JoinConnect
    Part.Embed("Embed", "Tube", "Tube001"), Part.Cutout("Cutout", ...)    Part_JoinEmbed, Part_JoinCutout
    Part.CompoundFilter("CompoundFilter", "Compound", filter_type="window-volume")   Part_CompoundFilter
    *Part.explode_compound("Slice", 3)                                    Part_ExplodeCompound (and Part_SliceApart)

Each is a Part::FeaturePython with the Proxy of BOPTools or CompoundTools; its shape is what the Proxy's execute
makes, here over OCP in the same order of OCCT calls: TopoShape::generalFuse (BRepAlgoAPI_BuilderAlgo, parallel,
non-destructive, Tolerance as the fuzzy value when it is not 0; the map is each argument's Modified pieces),
GeneralFuseResult's parsing and splitting of aggregates, ShapeMerge's grouping by shared elements, and for Embed and
Cutout the legacy cut and fuse of TopoShape.cut/fuse (makeElementBoolean, no fuzzy value).

Properties and defaults are FreeCAD's: BooleanFragments objects, mode "Standard" ("Split", "CompSolid"),
tolerance 0; Slice base, tools, mode, tolerance; XOR objects, tolerance; Connect objects, refine, tolerance; Embed and
Cutout base, tool, refine, tolerance (refine is Preferences' Part/Boolean RefineModel, False when it was never set);
CompoundFilter base, filter_type "bypass", items "", stencil, window_from 80, window_to 100, override_max_val 0,
invert False.
"""
from __future__ import annotations

from . import feature as F
from . import feature_part as _fp
from .feature_part import ENUM_PROPS, PartObject, compound, register
from .feature_part_bool import _children, _run, refine

try:
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepAlgoAPI import BRepAlgoAPI_BuilderAlgo
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeSolid, BRepBuilderAPI_MakeWire
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepLib import BRepLib
    from OCP.GProp import GProp_GProps
    from OCP.ShapeUpgrade import ShapeUpgrade_ShellSewing
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, \
        TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_CompSolid, TopoDS_Shell
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7
MODES = ("Standard", "Split", "CompSolid")
FILTERS = ("bypass", "specific items", "collision-pass", "window-volume", "window-area", "window-length",
           "window-distance")
# Mode, FilterType and items take strings that are not expressions ("0" is an item's index, not a number)
ENUM_PROPS.setdefault("Part::FeaturePython", set())
ENUM_PROPS["Part::FeaturePython"] = set(ENUM_PROPS["Part::FeaturePython"]) | {"Mode", "FilterType", "items"}


# ── TopoShape, as FreeCAD's Python sees it ───────────────────────────────────────────────────────────────────────

def _type(s) -> str:
    """TopoShape.ShapeType."""
    return {TopAbs_COMPOUND: "Compound", TopAbs_COMPSOLID: "CompSolid", TopAbs_SOLID: "Solid", TopAbs_SHELL: "Shell",
            TopAbs_FACE: "Face", TopAbs_WIRE: "Wire", TopAbs_EDGE: "Edge", TopAbs_VERTEX: "Vertex"}[s.ShapeType()]


def _subs(s, kind):
    """TopoShape.Solids, .Faces, ...: TopExp::MapShapes's order, each sub-shape once."""
    return F._subs(s, kind)


def _vertexes(s):
    return _subs(s, TopAbs_VERTEX)


def _edges(s):
    return _subs(s, TopAbs_EDGE)


def _faces(s):
    return _subs(s, TopAbs_FACE)


def _solids(s):
    return _subs(s, TopAbs_SOLID)


def _gprop(s, fn):
    p = GProp_GProps()
    fn(s, p)
    return p.Mass()


def _volume(s):
    return _gprop(s, BRepGProp.VolumeProperties_s)


def _area(s):
    return _gprop(s, BRepGProp.SurfaceProperties_s)


def _length(s):
    return _gprop(s, BRepGProp.LinearProperties_s)


def _mass(s):
    """Part.cast_to_shape(sh).Mass: a solid's volume, a shell's or face's area, a wire's or edge's length."""
    t = s.ShapeType()
    if t in (TopAbs_SOLID, TopAbs_COMPSOLID):
        return _volume(s)
    if t in (TopAbs_SHELL, TopAbs_FACE):
        return _area(s)
    if t in (TopAbs_WIRE, TopAbs_EDGE):
        return _length(s)
    raise F.FeatureError(f"'Part.{_type(s)}' object has no attribute 'Mass'")


class _H:
    """Utils.HashableShape: a shape as a dict key, equal to another when isSame (TShape and Location)."""
    __slots__ = ("Shape", "h")

    def __init__(self, shape):
        self.Shape = shape
        self.h = hash(shape)            # ShapeMapHasher: orientation left out, as TopoShape.hashCode

    def __eq__(self, other):
        return self.Shape.IsSame(other.Shape)

    def __hash__(self):
        return self.h


class _HD:
    """Utils.HashableShape_Deep: equal when made of the same children (their hashes xor-ed, count and type)."""
    __slots__ = ("Shape", "h", "n", "t")

    def __init__(self, shape):
        self.Shape = shape
        kids = _children(shape)
        self.h = 0
        for el in kids:
            self.h ^= hash(el)
        self.n = len(kids)
        self.t = shape.ShapeType()

    def __eq__(self, other):
        return self.h == other.h and self.n == other.n and self.t == other.t

    def __hash__(self):
        return self.h


def _leaves(s):
    """Utils.compoundLeaves."""
    if s.ShapeType() == TopAbs_COMPOUND:
        out = []
        for c in _children(s):
            out.extend(_leaves(c))
        return out
    return [s]


def _compsolid(solids):
    """Part.CompSolid(list): makeElementBoolean's Compsolid maker."""
    b = BRep_Builder()
    cs = TopoDS_CompSolid()
    b.MakeCompSolid(cs)
    for s in solids:
        if not s.IsNull():
            b.Add(cs, s)
    return cs


def _make_shell(faces):
    """Part.makeShell(list): makeElementBoolean's Shell maker, sewn when the shell is not valid."""
    b = BRep_Builder()
    shell = TopoDS_Shell()
    b.MakeShell(shell)
    for f in faces:
        b.Add(shell, f)
    if not BRepCheck_Analyzer(shell).IsValid():
        return ShapeUpgrade_ShellSewing().ApplySewing(shell)
    return shell


def _make_solid(shape):
    """Part.makeSolid: TopoShape::makeElementSolid."""
    css = _subs(shape, TopAbs_COMPSOLID)
    if not css:
        mk = BRepBuilderAPI_MakeSolid()
        shells = _subs(shape, TopAbs_SHELL)
        for s in shells:
            mk.Add(TopoDS.Shell(s))
        if not shells:
            raise F.FeatureError("No shells or compsolids found in shape")
        if not mk.IsDone():
            raise F.FeatureError("Failed to create a solid in makeElementSolid!")
        solid = TopoDS.Solid(mk.Shape())
        BRepLib.OrientClosedSolid_s(solid)
        return solid
    if len(css) > 1:
        raise F.FeatureError("Only one compsolid can be accepted. Provided shape has more than one compsolid.")
    return BRepBuilderAPI_MakeSolid(TopoDS.CompSolid(css[0])).Shape()


def _make_wire(edges):
    """Part.Wire(list of edges): BRepBuilderAPI_MakeWire, each edge added in order."""
    mk = BRepBuilderAPI_MakeWire()
    for e in edges:
        mk.Add(TopoDS.Edge(e))
    return mk.Wire()


def _reversed_edge(edge):
    """sort_Edges's edge the other way: BRepBuilderAPI_MakeEdge on the reversed 3D curve, or None without one."""
    e = TopoDS.Edge(edge)
    BRepLib.BuildCurves3d_s(e)
    curve = BRep_Tool.Curve_s(e, 0.0, 0.0)
    if curve is None:
        return None
    first, last = BRep_Tool.Range_s(e)
    return BRepBuilderAPI_MakeEdge(curve.Reversed(), curve.ReversedParameter(last),
                                   curve.ReversedParameter(first)).Edge()


def _sort_edges(edges, tol3d=CONFUSION):
    """Part.sortEdges (AppPartPy's sort_Edges, again until no edge is left): lists of edges, each chained end to end
    from its first edge, an edge that runs the other way made anew reversed."""
    tol = tol3d * tol3d
    left = list(edges)
    roots = []
    while left:
        pts = []
        for e in left:
            ex = TopExp_Explorer(e, TopAbs_VERTEX)
            v1 = BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))
            ex.Next()
            v2 = BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))
            pts.append((v1, v2, e))
        first, last = pts[0][0], pts[0][1]
        chain = [pts[0][2]]
        pts.pop(0)
        while pts:
            found = None
            for i, (v1, v2, e) in enumerate(pts):
                if v1.SquareDistance(last) <= tol:
                    last = v2
                    chain.append(e)
                elif v2.SquareDistance(first) <= tol:
                    first = v1
                    chain.insert(0, e)
                elif v2.SquareDistance(last) <= tol:
                    last = v1
                    r = _reversed_edge(e)
                    if r is not None:
                        chain.append(r)
                elif v1.SquareDistance(first) <= tol:
                    first = v2
                    r = _reversed_edge(e)
                    if r is not None:
                        chain.insert(0, r)
                else:
                    continue
                found = i
                break
            if found is None:
                break
            pts.pop(found)
            if not pts or last.SquareDistance(first) <= tol:
                break
        roots.append(chain)
        left = [p[2] for p in pts]
    return roots


def _shell_if_faces(shape):
    """TopoShape::makeElementShell(silent): a compound of free faces alone becomes one shell."""
    if shape is None or shape.IsNull() or shape.ShapeType() != TopAbs_COMPOUND:
        return shape
    if TopExp_Explorer(shape, TopAbs_SHELL).More():
        return shape
    for kind, avoid in ((TopAbs_WIRE, TopAbs_FACE), (TopAbs_EDGE, TopAbs_WIRE), (TopAbs_VERTEX, TopAbs_EDGE)):
        if TopExp_Explorer(shape, kind, avoid).More():
            return shape
    faces = _faces(shape)
    if not faces:
        return shape
    try:
        out = _make_shell(faces)
    except Exception:  # noqa: BLE001 - silent
        return shape
    if out is None or out.IsNull() or out.ShapeType() != TopAbs_SHELL:
        return shape
    return out


def _expand(s, out):
    if s.ShapeType() != TopAbs_COMPOUND:
        out.append(s)
        return
    for c in _children(s):
        _expand(c, out)


def topo_boolean(maker, shapes):
    """TopoShape.cut / .fuse (makeElementBoolean, tolerance 0): compound tools expanded (a fuse's first shape too),
    FCBRepAlgoAPI_Cut or _Fuse with no fuzzy value, then makeElementShell."""
    _shapes = []
    if maker == "fuse":
        for i, s in enumerate(shapes):
            if s.ShapeType() == TopAbs_COMPOUND:
                if not _shapes:
                    _shapes += shapes[:i]
                _expand(s, _shapes)
            elif _shapes:
                _shapes.append(s)
    else:
        for i in range(1, len(shapes)):
            s = shapes[i]
            if s.ShapeType() == TopAbs_COMPOUND:
                if not _shapes:
                    _shapes += shapes[:i]
                _expand(s, _shapes)
            elif _shapes:
                _shapes.append(s)
    inputs = _shapes or shapes
    if not inputs:
        raise F.FeatureError("Null input shape")
    if len(inputs) == 1:
        return inputs[0]
    if maker == "cut" and len(inputs) == 2 and inputs[0].ShapeType() == TopAbs_COMPOUND \
            and inputs[1].ShapeType() != TopAbs_COMPOUND:          # FCBRepAlgoAPI's RecursiveCutCompound
        b = BRep_Builder()
        comp = TopoDS_Compound()
        b.MakeCompound(comp)
        for c in _children(inputs[0]):
            r = _run("cut", [c], [inputs[1]], 0.0)
            if r is None:
                raise F.FeatureError("Boolean operation failed")
            b.Add(comp, r)
        res = comp
    else:
        res = _run(maker, inputs[:1], inputs[1:], 0.0)
        if res is None:
            raise F.FeatureError("Boolean operation failed")
    return _shell_if_faces(res)


def general_fuse(shapes, tolerance=0.0):
    """shapes[0].generalFuse(shapes[1:], tolerance): TopoShape::makeElementGeneralFuse. Returns the result compound
    and, for each argument, the pieces BRepAlgoAPI_BuilderAlgo::Modified gives for it."""
    for s in shapes:
        if s is None or s.IsNull():
            raise F.FeatureError("Null input shape")
    mk = BRepAlgoAPI_BuilderAlgo()
    mk.SetRunParallel(True)
    args = F.TopTools_ListOfShape()
    for s in shapes:
        args.Append(s)
    mk.SetArguments(args)
    if tolerance > 0.0:
        mk.SetFuzzyValue(tolerance)
    mk.SetNonDestructive(True)
    mk.Build()
    if not mk.IsDone():
        raise F.FeatureError("GeneralFuse failed")
    res = mk.Shape()
    return res, [list(mk.Modified(s)) for s in shapes]


# ── BOPTools.GeneralFuseResult ───────────────────────────────────────────────────────────────────────────────────

AGGREGATE = ("Wire", "Shell", "CompSolid", "Compound")
NONAGGREGATE = ("Vertex", "Edge", "Face", "Solid")


class GeneralFuseResult:
    """GeneralFuseResult: the pieces of a generalFuse and which source each came from."""

    def __init__(self, source_shapes, gf_return):
        self.gfa_return = gf_return
        self.source_shapes = source_shapes
        self.parse()

    def parse(self):
        compound_, map_ = self.gfa_return
        self._element_to_source = {}
        self.pieces = _children(compound_)
        self._piece_to_index = {}
        for i, p in enumerate(self.pieces):
            h = _H(p)
            if h in self._piece_to_index:
                raise F.FeatureError("GeneralFuseAnalyzer.parse: duplicate piece shape detected.")
            self._piece_to_index[h] = i
        self._source_to_index = {}
        for i, s in enumerate(self.source_shapes):
            h = _H(s)
            if h in self._source_to_index:
                raise F.FeatureError("GeneralFuseAnalyzer.parse: duplicate source shape detected.")
            self._source_to_index[h] = i
        if any(len(m) == 0 for m in map_):
            types = {_type(p) for p in self.pieces}
            take = types & set(NONAGGREGATE)

            def extractor(sh):
                return ((_vertexes(sh) if "Vertex" in take else []) + (_edges(sh) if "Edge" in take else [])
                        + (_faces(sh) if "Face" in take else []) + (_solids(sh) if "Solid" in take else []))

            agg_sources = [self.index_of_source(sh) for sh in self.source_shapes if _type(sh) in AGGREGATE]
            agg_pieces = [sh for sh in self.pieces if _type(sh) in AGGREGATE]
            if len(agg_sources) != len(agg_pieces):
                raise F.FeatureError("AssertionError")
            for i, i_source in enumerate(agg_sources):
                if len(map_[i_source]) == 0:
                    map_[i_source] = [agg_pieces[i]]
                    for sh in extractor(agg_pieces[i]):
                        i_piece = self._piece_to_index.get(_H(sh))
                        if i_piece is not None and not map_[i_source][-1].IsSame(self.pieces[i_piece]):
                            map_[i_source].append(self.pieces[i_piece])
        self._pieces_of_source = [[] for _ in self.source_shapes]
        self._sources_of_piece = [[] for _ in self.pieces]
        assert len(map_) == len(self.source_shapes)
        for i_source in range(len(self.source_shapes)):
            for piece in map_[i_source]:
                i_piece = self.index_of_piece(piece)
                self._sources_of_piece[i_piece].append(i_source)
                self._pieces_of_source[i_source].append(i_piece)

    def parse_elements(self):
        if self._element_to_source:
            return
        for i, piece in enumerate(self.pieces):
            for el in _vertexes(piece) + _edges(piece) + _faces(piece) + _solids(piece):
                h = _H(el)
                self._element_to_source.setdefault(h, set()).update(self._sources_of_piece[i])

    def index_of_piece(self, piece):
        try:
            return self._piece_to_index[_H(piece)]
        except KeyError:
            raise F.FeatureError("KeyError: a piece of the map is not in the result") from None

    def index_of_source(self, source):
        return self._source_to_index[_H(source)]

    def pieces_from_source(self, source):
        return [self.pieces[i] for i in self._pieces_of_source[self.index_of_source(source)]]

    def sources_of_piece(self, piece):
        return [self.source_shapes[i] for i in self._sources_of_piece[self.index_of_piece(piece)]]

    def largest_overlap_count(self):
        return max(len(il) for il in self._sources_of_piece)

    def split_aggregates(self, pieces_to_split=None):
        if pieces_to_split is None:
            pieces_to_split = self.pieces
        to_split = {_H(p) for p in pieces_to_split}
        self.parse_elements()
        new_data = _ReturnBuilder(self.source_shapes)
        changed = False
        for i, piece in enumerate(self.pieces):
            if _H(piece) in to_split:
                new_pieces = self.make_split_pieces(piece)
                changed = changed or len(new_pieces) > 1
                for np_ in new_pieces:
                    new_data.add_piece(np_, self._sources_of_piece[i])
            else:
                new_data.add_piece(piece, self._sources_of_piece[i])
        existing = dict(new_data._piece_to_index)
        for i, np_ in enumerate(new_data.pieces):
            if _H(np_) in to_split and np_.ShapeType() == TopAbs_COMPOUND:
                ret = self._split_in_compound(np_, existing)
                if ret is not None:
                    changed = True
                    new_data.replace_piece(i, ret)
        if len(new_data.pieces) > len(self.pieces) or changed:
            self.gfa_return = new_data.gf_return()
            self.parse()

    def _split_in_compound(self, comp, existing):
        changed = False
        new_children = []
        for piece in _children(comp):
            if piece.ShapeType() == TopAbs_COMPOUND:
                sub = self._split_in_compound(piece, existing)
                if sub is None:
                    new_children.append(piece)
                else:
                    new_children.append(sub)
                    changed = True
            else:
                new_pieces = self.make_split_pieces(piece)
                changed = changed or len(new_pieces) > 1
                for np_ in new_pieces:
                    h = _HD(np_)
                    _, ex = existing.get(h, (None, None))
                    if ex is not None:
                        new_children.append(ex)
                        changed = True
                    else:
                        new_children.append(np_)
                        existing[h] = (-1, np_)
        return compound(new_children) if changed else None

    def make_split_pieces(self, shape):
        t = shape.ShapeType()
        if t == TopAbs_WIRE:
            bits, joints = _edges, _vertexes
        elif t == TopAbs_SHELL:
            bits, joints = _faces, _edges
        elif t == TopAbs_COMPSOLID:
            bits, joints = _solids, _faces
        else:
            return [shape]
        splits = []
        all_bits = None
        for joint in joints(shape):
            joint_count = len(self._element_to_source[_H(joint)])
            if joint_count > 1:
                if all_bits is None:
                    all_bits = [(b, joints(b)) for b in bits(self.gfa_return[0])]
                for bit, bit_joints in all_bits:
                    for jb in bit_joints:
                        if jb.IsSame(joint):
                            bit_count = len(self._element_to_source[_H(bit)])
                            assert bit_count <= joint_count
                            if bit_count < joint_count:
                                if not splits or splits[-1] is not joint:
                                    splits.append(joint)
        if not splits:
            return [shape]
        new_pieces = _children(merge_shapes(bits(shape), split_connections=splits, bool_compsolid=True))
        if len(new_pieces) == 1:
            return [shape]
        return new_pieces

    def explode_compounds(self):
        if not any(p.ShapeType() == TopAbs_COMPOUND for p in self.pieces):
            return
        new_data = _ReturnBuilder(self.source_shapes, _H)
        for i, piece in enumerate(self.pieces):
            if piece.ShapeType() == TopAbs_COMPOUND:
                for child in _leaves(piece):
                    new_data.add_piece(child, self._sources_of_piece[i])
            else:
                new_data.add_piece(piece, self._sources_of_piece[i])
        self.gfa_return = new_data.gf_return()
        self.parse()


class _ReturnBuilder:
    """GeneralFuseReturnBuilder: a generalFuse return made up again, for re-parsing."""

    def __init__(self, source_shapes, hasher=None):
        self.pieces = []
        self._piece_to_index = {}
        self._pieces_from_source = [[] for _ in source_shapes]
        self.hasher = hasher or _HD

    def add_piece(self, piece, sources):
        existing, h = None, None
        if piece.ShapeType() != TopAbs_COMPOUND:
            h = self.hasher(piece)
            existing, _ = self._piece_to_index.get(h, (None, None))
        if existing is None:
            self.pieces.append(piece)
            existing = len(self.pieces) - 1
            if h is not None:
                self._piece_to_index[h] = (existing, piece)
        for i_source in sources:
            if existing not in self._pieces_from_source[i_source]:
                self._pieces_from_source[i_source].append(existing)

    def replace_piece(self, i, shape):
        self.pieces[i] = shape

    def gf_return(self):
        return compound(self.pieces), [[self.pieces[i] for i in il] for il in self._pieces_from_source]


# ── BOPTools.ShapeMerge ──────────────────────────────────────────────────────────────────────────────────────────

def find_shared_elements(shapes, extractor):
    if len(shapes) < 2:
        raise F.FeatureError(f"findSharedElements: at least two shapes must be provided (have {len(shapes)})")
    shared = None
    for s in shapes:
        els = {_H(e) for e in extractor(s)}
        shared = els if shared is None else shared & els
    return [e.Shape for e in shared]


def is_connected(s1, s2, dim=-1):
    if dim == -1:
        dim = dimension_of_shapes([s1, s2])
    extractor = {1: _vertexes, 2: _edges, 3: _faces}.get(dim)
    if extractor is None:
        raise F.FeatureError("'NoneType' object is not callable")
    return len(find_shared_elements([s1, s2], extractor)) > 0


def split_into_groups_by_sharing(shapes, extractor, split_connections=()):
    split = {_H(e) for e in split_connections}
    groups = []                          # (shapes, elements)
    for shape in shapes:
        els = {_H(e) for e in extractor(shape)} - split
        connected_to, not_connected = [], []
        for i, g in enumerate(groups):
            if any(e in g[1] for e in els):
                connected_to.append(i)
            else:
                not_connected.append(i)
        if len(connected_to) > 1:
            sup = ([], set())
            for i in connected_to:
                sup[0].extend(groups[i][0])
                sup[1].update(groups[i][1])
            n = len(groups)
            groups = [sup] + [groups[i] for i in not_connected if i < n]
            connected_to = [0]
        if connected_to:
            groups[connected_to[0]][0].append(shape)
            groups[connected_to[0]][1].update(els)
        else:
            groups.append(([shape], els))
    return [g[0] for g in groups]


def merge_solids(shapes, flag_single=False, split_connections=(), bool_compsolid=False):
    solids = []
    for sh in shapes:
        solids.extend(_solids(sh))
    if flag_single:
        cs = _compsolid(solids)
        return cs if bool_compsolid else _make_solid(cs)
    if not solids:
        return compound([])
    groups = split_into_groups_by_sharing(solids, _faces, split_connections)
    if bool_compsolid:
        return compound([_compsolid(g) for g in groups])
    return compound([_make_solid(_compsolid(g)) for g in groups])


def merge_shells(shapes, flag_single=False, split_connections=()):
    faces = []
    for sh in shapes:
        faces.extend(_faces(sh))
    if flag_single:
        return _make_shell(faces)
    groups = split_into_groups_by_sharing(faces, _edges, split_connections)
    return compound([_make_shell(g) for g in groups])


def merge_wires(shapes, flag_single=False, split_connections=()):
    edges = []
    for sh in shapes:
        edges.extend(_edges(sh))
    if flag_single:
        return _make_wire(edges)
    groups = split_into_groups_by_sharing(edges, _vertexes, split_connections)
    return compound([_make_wire(_sort_edges(g)[0]) for g in groups])


def remove_duplicates(shapes):
    seen, out = set(), []
    for s in shapes:
        h = _H(s)
        if h not in seen:
            out.append(s)
            seen.add(h)
    return out


def merge_shapes(shapes, flag_single=False, split_connections=(), bool_compsolid=False):
    if not shapes:
        return compound([])
    dim = dimension_of_shapes(shapes)
    if dim == 0:
        return compound(remove_duplicates(shapes))
    if dim == 1:
        return merge_wires(shapes, flag_single, split_connections)
    if dim == 2:
        return merge_shells(shapes, flag_single, split_connections)
    if dim == 3:
        return merge_solids(shapes, flag_single, split_connections, bool_compsolid)
    raise F.FeatureError("AssertionError")


def dimension_of_shapes(shapes):
    dims = (("Vertex",), ("Edge", "Wire"), ("Face", "Shell"), ("Solid", "CompSolid"))
    dim = -1
    for sh in shapes:
        t = _type(sh)
        for i, names in enumerate(dims):
            if t in names:
                if dim == -1:
                    dim = i
                if i != dim:
                    raise F.FeatureError(f"Shapes are of different dimensions ({_type(shapes[0])} and {t}), and "
                                         "cannot be merged or compared.")
    return dim


# ── BOPTools.SplitAPI ────────────────────────────────────────────────────────────────────────────────────────────

def boolean_fragments(shapes, mode, tolerance=0.0):
    pieces, map_ = general_fuse(shapes, tolerance)
    if mode == "Standard":
        return pieces
    if mode == "CompSolid":
        solids = _solids(pieces)
        if not solids:
            raise F.FeatureError("No solids in the result. Can't make CompSolid.")
        return merge_solids(solids, bool_compsolid=True)
    if mode == "Split":
        gr = GeneralFuseResult(shapes, (pieces, map_))
        gr.split_aggregates()
        return compound(gr.pieces)
    raise F.FeatureError(f"Unknown mode: {mode}")


def slice_shape(base, tools, mode, tolerance=0.0):
    shapes = [base] + [compound([t]) for t in tools]      # tools in compounds keep their pieces out of the result
    if len(shapes) < 2:
        raise F.FeatureError("No slicing objects supplied!")
    pieces, map_ = general_fuse(shapes, tolerance)
    gr = GeneralFuseResult(shapes, (pieces, map_))
    result = None
    if mode == "Standard":
        result = gr.pieces_from_source(shapes[0])
    elif mode == "CompSolid":
        solids = _solids(compound(gr.pieces_from_source(shapes[0])))
        if not solids:
            raise F.FeatureError("No solids in the result. Can't make compsolid.")
        result = _children(merge_solids(solids, bool_compsolid=True))
    elif mode == "Split":
        gr.split_aggregates(gr.pieces_from_source(shapes[0]))
        result = gr.pieces_from_source(shapes[0])
    if result is None:
        return None
    return result[0] if len(result) == 1 else compound(result)


def _upgrade_to_aggregate(shapes, types=None):
    """Utils.upgradeToAggregateIfNeeded."""
    if types is None:
        types = set()
    for s in shapes:
        types.add(_type(s))
        for sub in _leaves(s):
            types.add(_type(sub))
    if "Wire" in types:
        shapes = [_make_wire([s]) if s.ShapeType() == TopAbs_EDGE else s for s in shapes]
    if "Shell" in types:
        shapes = [_make_shell([s]) if s.ShapeType() == TopAbs_FACE else s for s in shapes]
    if "CompSolid" in types:
        shapes = [_compsolid([s]) if s.ShapeType() == TopAbs_SOLID else s for s in shapes]
    if "Compound" in types:
        shapes = [compound(_upgrade_to_aggregate(_children(s), types)) if s.ShapeType() == TopAbs_COMPOUND else s
                  for s in shapes]
    return shapes


def xor(shapes, tolerance=0.0):
    shapes = _upgrade_to_aggregate(shapes)
    pieces, map_ = general_fuse(shapes, tolerance)
    gr = GeneralFuseResult(shapes, (pieces, map_))
    gr.explode_compounds()
    gr.split_aggregates()
    return compound([p for p in gr.pieces if len(gr.sources_of_piece(p)) % 2 == 1])


# ── BOPTools.JoinAPI ─────────────────────────────────────────────────────────────────────────────────────────────

def shape_of_max_size(shapes):
    dimension_of_shapes(shapes)
    rel = 1e-8
    max_size, count, best = -1e100, 0, None
    for sh in shapes:
        v = abs(_mass(sh))
        if v > max_size * (1 + rel):
            max_size, best, count = v, sh, 1
        elif (1 - rel) * max_size <= v <= (1 + rel) * max_size:
            count += 1
    if count > 1:
        raise F.FeatureError("There is more than one largest piece!")
    return best


def connect(shapes, tolerance=0.0):
    leaves = []
    for s in shapes:
        leaves.extend(_leaves(s))
    shapes = leaves
    dim = dimension_of_shapes(shapes)
    if dim == 0:
        raise F.FeatureError("Cannot connect vertices!")
    if len(shapes) < 2:
        return compound(shapes)
    pieces, map_ = general_fuse(shapes, tolerance)
    ao = GeneralFuseResult(shapes, (pieces, map_))
    ao.split_aggregates()
    keepers = []
    for src in ao.source_shapes:
        danglers = [p for p in ao.pieces_from_source(src) if len(ao.sources_of_piece(p)) == 1]
        largest = shape_of_max_size(danglers)
        if largest is not None:
            keepers.append(largest)
    touch = compound(keepers)
    for ii in range(2, ao.largest_overlap_count() + 1):
        add = [p for p in ao.pieces if len(ao.sources_of_piece(p)) == ii and is_connected(p, touch)]
        if not add:
            break
        keepers.extend(add)
        touch = compound(add)
    return merge_shapes(keepers)


def embed_legacy(base, tool):
    pieces = _leaves(topo_boolean("cut", [base, tool]))
    piece = shape_of_max_size(pieces)
    if piece is None:
        raise F.FeatureError("'NoneType' object has no attribute 'fuse'")
    result = topo_boolean("fuse", [piece, tool])
    dim = dimension_of_shapes(pieces)
    if dim == 2:
        result = merge_shapes(_faces(result))
    elif dim == 1:
        result = merge_shapes(_edges(result))
    return result


def cutout_legacy(base, tool):
    bases = _leaves(base)
    if len(bases) > 1:
        raise F.FeatureError("name 'cutout' is not defined")       # JoinAPI calls a cutout() it does not define
    pieces = _leaves(topo_boolean("cut", [bases[0], tool]))
    return shape_of_max_size(pieces)


# ── the features ─────────────────────────────────────────────────────────────────────────────────────────────────

class _Python(PartObject):
    """A Part::FeaturePython with a BOPTools or CompoundTools Proxy (TypeId "Part::FeaturePython")."""
    FC_TYPE = "Part::FeaturePython"
    PROXY = ("", "")                     # (module, class) of the Proxy

    def fc_setup(self, obj, fc):
        import importlib
        mod, cls = self.PROXY
        getattr(importlib.import_module(mod), cls)(obj)

    def tol(self, params):
        """Tolerance, a PropertyLength (never negative): the fuzzy value when it is more than 0."""
        return max(self.v("tolerance", params), 0.0)


def _objects_shapes(self, ctx, what):
    shapes = [ctx.shape(o, f"{self.name}.Objects") for o in self.objects]
    if len(shapes) == 1 and shapes[0].ShapeType() == TopAbs_COMPOUND:
        shapes = _children(shapes[0])
    if len(shapes) < 2:
        raise F.FeatureError(f"At least two shapes are needed for computing {what}. Got only {len(shapes)}.")
    return shapes


class BooleanFragments(_Python):
    """SplitFeatures.FeatureBooleanFragments: the pieces of all Objects cut where they meet (generalFuse); one
    compound alone is its children's. Mode Split also splits wires and shells there, CompSolid glues the solid pieces
    into compsolids."""
    kind, TYPE_ID, TRANSACTION = "Part.BooleanFragments", "Part::BooleanFragments", "Create Boolean Fragments"
    PROXY = ("BOPTools.SplitFeatures", "FeatureBooleanFragments")
    POS = ("objects",)
    REFS = ("objects",)
    INPUTS = ("objects",)
    DEFAULTS = {"objects": (), "mode": "Standard", "tolerance": 0.0, **PartObject.COMMON}
    ENUMS = {"mode": MODES}

    def shape(self, ctx, params):
        shapes = _objects_shapes(self, ctx, "boolean fragments")
        return boolean_fragments(shapes, self.mode, self.tol(params))


class Slice(_Python):
    """SplitFeatures.FeatureSlice: Base split by Tools, its pieces alone (Part_Slice sets Mode Split; Part_SliceApart
    is that and explode_compound of it)."""
    kind, TYPE_ID, TRANSACTION = "Part.Slice", "Part::Slice", "Create Slice"
    PROXY = ("BOPTools.SplitFeatures", "FeatureSlice")
    POS = ("base", "tools")
    REFS = ("base", "tools")
    INPUTS = ("base", "tools")
    DEFAULTS = {"base": None, "tools": (), "mode": "Standard", "tolerance": 0.0, **PartObject.COMMON}
    ENUMS = {"mode": MODES}

    def shape(self, ctx, params):
        if len(self.tools) < 1:
            raise F.FeatureError("No slicing objects supplied!")
        if self.base is None:
            raise F.FeatureError("Base object has no valid shape!")
        base = ctx.shape(self.base, f"{self.name}.Base")
        tools = [ctx.shape(t, f"{self.name}.Tools") for t in self.tools]
        out = slice_shape(base, tools, self.mode, self.tol(params))
        if out is None or out.IsNull():
            raise F.FeatureError("Slice: the result is a null shape")
        return out


class XOR(_Python):
    """SplitFeatures.FeatureXOR: the pieces of Objects that an odd number of them hold."""
    kind, TYPE_ID, TRANSACTION = "Part.XOR", "Part::XOR", "Create Boolean XOR"
    PROXY = ("BOPTools.SplitFeatures", "FeatureXOR")
    POS = ("objects",)
    REFS = ("objects",)
    INPUTS = ("objects",)
    DEFAULTS = {"objects": (), "tolerance": 0.0, **PartObject.COMMON}

    def shape(self, ctx, params):
        return xor(_objects_shapes(self, ctx, "XOR"), self.tol(params))


class Connect(_Python):
    """JoinFeatures.FeatureConnect: Objects fused, keeping their voids (JoinAPI.connect)."""
    kind, TYPE_ID, TRANSACTION = "Part.Connect", "Part::Connect", "Create Connect"
    PROXY = ("BOPTools.JoinFeatures", "FeatureConnect")
    POS = ("objects",)
    REFS = ("objects",)
    INPUTS = ("objects",)
    DEFAULTS = {"objects": (), "refine": False, "tolerance": 0.0, **PartObject.COMMON}

    def shape(self, ctx, params):
        shapes = [ctx.shape(o, f"{self.name}.Objects") for o in self.objects]
        rst = connect(shapes, self.tol(params))
        return refine(rst) if self.refine else rst


class _Join(_Python):
    POS = ("base", "tool")
    REFS = ("base", "tool")
    INPUTS = ("base", "tool")
    DEFAULTS = {"base": None, "tool": None, "refine": False, "tolerance": 0.0, **PartObject.COMMON}

    def shape(self, ctx, params):
        if self.base is None or self.tool is None:
            raise F.FeatureError("'NoneType' object has no attribute 'Shape'")
        base, tool = ctx.shape(self.base, f"{self.name}.Base"), ctx.shape(self.tool, f"{self.name}.Tool")
        self.tol(params)                 # the legacy joins warn that they take no tolerance
        rst = self.join(base, tool)
        return refine(rst) if self.refine else rst


class Embed(_Join):
    """JoinFeatures.FeatureEmbed: Tool fused into the largest piece of Base cut by Tool (JoinAPI.embed_legacy)."""
    kind, TYPE_ID, TRANSACTION = "Part.Embed", "Part::Embed", "Create Embed"
    PROXY = ("BOPTools.JoinFeatures", "FeatureEmbed")

    def join(self, base, tool):
        return embed_legacy(base, tool)


class Cutout(_Join):
    """JoinFeatures.FeatureCutout: the largest piece of Base cut by Tool (JoinAPI.cutout_legacy)."""
    kind, TYPE_ID, TRANSACTION = "Part.Cutout", "Part::Cutout", "Create Cutout"
    PROXY = ("BOPTools.JoinFeatures", "FeatureCutout")

    def join(self, base, tool):
        return cutout_legacy(base, tool)


def _dist(a, b):
    """TopoShape.distToShape(b)[0]: BRepExtrema_DistShapeShape, deflection Precision::Confusion."""
    ext = BRepExtrema_DistShapeShape()
    ext.SetDeflection(CONFUSION)
    ext.SetMultiThread(True)
    ext.LoadS1(a)
    ext.LoadS2(b)
    ext.Perform()
    if not ext.IsDone():
        raise F.FeatureError("BRepExtrema_DistShapeShape failed")
    return ext.Value()


class CompoundFilter(_Python):
    """CompoundTools.CompoundFilter: the children of Base's shape that pass FilterType's test (Part_CompoundFilter
    sets "window-volume", or "collision-pass" with a second object as Stencil; Part_ExplodeCompound makes one
    "specific items" filter per child, explode_compound)."""
    kind, TYPE_ID, TRANSACTION = "Part.CompoundFilter", "Part::CompoundFilter", "Create CompoundFilter"
    PROXY = ("CompoundTools.CompoundFilter", "_CompoundFilter")
    POS = ("base",)
    REFS = ("base", "stencil")
    INPUTS = ("base", "stencil")
    PROPS = {"items": "items"}
    DEFAULTS = {"base": None, "filter_type": "bypass", "items": "", "stencil": None, "window_from": 80.0,
                "window_to": 100.0, "override_max_val": 0.0, "invert": False, **PartObject.COMMON}
    ENUMS = {"filter_type": FILTERS}

    def shape(self, ctx, params):
        if self.base is None:
            raise F.FeatureError("'NoneType' object has no attribute 'Shape'")
        base = ctx.shape(self.base, f"{self.name}.Base")
        stencil = ctx.shape(self.stencil, f"{self.name}.Stencil") if self.stencil is not None else None
        shps = _children(base)
        ft = self.filter_type
        rst = []
        if ft == "bypass":
            rst = shps
        elif ft == "specific items":
            flags = [False] * len(shps)
            if not self.items:
                raise F.FeatureError(f"The 'items' property must have a number to use this filter: '{ft}'")
            for r in self.items.split(";"):
                r_v = r.split(":")
                if len(r_v) == 1:
                    try:
                        i = int(r_v[0])
                    except ValueError:
                        raise F.FeatureError("Make sure the 'item' does not have spaces; a semicolon (;) can only "
                                             f"appear between two numbers; filter: '{ft}'") from None
                    try:
                        rst.append(shps[i])
                    except IndexError:
                        raise F.FeatureError(f"Item index '{i}' is out of range for this filter: '{ft}'") from None
                    flags[i] = True
                elif len(r_v) in (2, 3):
                    if len(r_v) == 2:
                        r_v.append("")
                    try:
                        ifrom, ito, istep = (None if not x.strip() else int(x) for x in r_v)
                    except ValueError as e:
                        raise F.FeatureError(str(e)) from None
                    if istep == 0:
                        raise F.FeatureError("slice step cannot be zero")
                    rst = rst + shps[ifrom:ito:istep]
                    # FreeCAD's loop sets a copy of each flag (b = True), so a range is not inverted
                else:
                    raise F.FeatureError(f"index range cannot be parsed: '{r}'")
            if self.invert:
                rst = [s for i, s in enumerate(shps) if not flags[i]]
        elif ft == "collision-pass":
            if stencil is None:
                raise F.FeatureError(f"A 'Stencil' object must be set to use this filter: '{ft}'")
            for s in shps:
                if bool(_dist(s, stencil) < CONFUSION) ^ bool(self.invert):
                    rst.append(s)
        else:
            vals = []
            for s in shps:
                if ft == "window-volume":
                    vals.append(_volume(s))
                elif ft == "window-area":
                    vals.append(_area(s))
                elif ft == "window-length":
                    vals.append(_length(s))
                else:
                    if stencil is None:
                        raise F.FeatureError(f"A 'Stencil' object must be set to use this filter: '{ft}'")
                    vals.append(_dist(s, stencil))
            if not vals:
                raise F.FeatureError("max() arg is an empty sequence")
            maxval = max(vals)
            if stencil is not None:
                if ft == "window-volume":
                    maxval = _volume(stencil)
                elif ft == "window-area":
                    maxval = _area(stencil)
                elif ft == "window-length":
                    maxval = _length(stencil)
            omv = self.v("override_max_val", params)
            if omv:
                maxval = omv
            lo = self.v("window_from", params) / 100.0 * maxval
            hi = self.v("window_to", params) / 100.0 * maxval
            for v, s in zip(vals, shps):
                if bool(lo <= v <= hi) ^ bool(self.invert):
                    rst.append(s)
        if not rst:
            raise F.FeatureError("Nothing passes through the filter")
        if len(rst) > 1:
            return compound(rst)
        return rst[0]                    # one shape is the output itself, its placement baked in (the same shape)


def explode_compound(compound_name, n, label=None):
    """CompoundTools.Explode.explodeCompound (Part_ExplodeCompound, and the second half of Part_SliceApart): a
    CompoundFilter per child of the compound's n children, Name "<Name>_child<i>", Label "<Label>.<i>", filter type
    "specific items" with items "<i>". FreeCAD puts them in a group, App::DocumentObjectGroup "GrExplode_<Name>"
    labelled "Exploded <Label>", when there is more than one child; a part file has no groups, so they are listed
    as they are."""
    lab = label or compound_name
    return [CompoundFilter(f"{compound_name}_child{i}", compound_name, filter_type="specific items", items=str(i),
                           label=f"{lab}.{i}") for i in range(n)]


SLICE_APART = "Slice apart"              # Part_SliceApart's transaction: a Slice in mode Split, then explode_compound


def slice_apart(name, base, tools, n, label=None):
    """Part_SliceApart: Slice(name, base, tools, mode="Split") and a CompoundFilter per piece of it."""
    return [Slice(name, base, tools, mode="Split", label=label)] + explode_compound(name, n, label)


SPLIT = (BooleanFragments, Slice, XOR, Connect, Embed, Cutout, CompoundFilter)
register(*SPLIT)
_fp.explode_compound, _fp.slice_apart = explode_compound, slice_apart       # Part.explode_compound(...) in a part file
