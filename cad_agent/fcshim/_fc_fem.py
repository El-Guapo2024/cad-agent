# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's FEM mesh (src/Mod/Fem/App/FemMesh.cpp, FemMeshPyImp.cpp; Copyright (c) 2008 Jürgen
# Riegel) and of the SMESH UNV reader it reads Gmsh's meshes with and the writer it exports .unv with (src/3rdParty/
# salomesmesh/src/DriverUNV/DriverUNV_R_SMDS_Mesh.cpp, DriverUNV_W_SMDS_Mesh.cpp, UNV164/2411/2412/2417/2420_Structure.cpp;
# src/SMDS/SMDS_MeshCell.cpp, SMDS_VtkCellIterator.cpp; Copyright (C) 2007-2015 CEA/DEN, EDF R&D, OPEN CASCADE,
# LGPL-2.1-or-later).
"""Fem.FemMesh for FreeCAD's FEM Python: the nodes and elements of a mesh as SMESH holds them (by ID, iterated in ID
order), read from Gmsh's .unv as SMESH's UNV driver reads it, the lookups by shape that the CalculiX writer uses
(getNodesByFace, getccxVolumesByFace, ...: BRepExtrema_DistShapeShape within the shape's tolerance), writeABAQUS, and
write, the .unv SMESH exports (Elmer's ElmerGrid reads it)."""
from __future__ import annotations

import math

from . import _fc_base as B

# SMDSAbs element kinds by node count (FemMeshPy::getElementType's names)
_VOL, _FACE, _EDGE = "Volume", "Face", "Edge"


class FemMesh:
    """Fem::FemMesh (FemMeshPy)."""

    def __init__(self, other=None):
        self._nodes: dict[int, tuple] = {}
        self._elems: dict[int, tuple] = {}        # id -> (kind, (node ids, SMDS order))
        self._groups: dict[int, tuple] = {}       # id -> (name, element type, element ids)
        self._next_gid = 0                        # SMESH_Mesh::_groupId: groups are numbered 0, 1, ... as made
        self.Placement = B.Placement()
        if isinstance(other, FemMesh):
            self._nodes, self._elems = dict(other._nodes), dict(other._elems)
            self._groups = {g: (n, k, list(ids)) for g, (n, k, ids) in other._groups.items()}
            self._next_gid = other._next_gid
            self.Placement = B.Placement(other.Placement)

    def copy(self):
        return FemMesh(self)

    # ── building ──
    def addNode(self, x, y, z, nid=None):
        nid = int(nid) if nid is not None else (max(self._nodes) + 1 if self._nodes else 1)
        self._nodes[nid] = (float(x), float(y), float(z))
        return nid

    def _add(self, kind, nodes, eid=None):
        eid = int(eid) if eid is not None else (max([*self._elems, *self._nodes] or [0]) + 1)
        self._elems[eid] = (kind, tuple(int(n) for n in nodes))
        return eid

    def addEdge(self, *a):
        nodes, eid = (a[0], a[1] if len(a) > 1 else None) if isinstance(a[0], (list, tuple)) else (a, None)
        return self._add(_EDGE, nodes, eid)

    def addFace(self, *a):
        nodes, eid = (a[0], a[1] if len(a) > 1 else None) if isinstance(a[0], (list, tuple)) else (a, None)
        return self._add(_FACE, nodes, eid)

    def addVolume(self, *a):
        nodes, eid = (a[0], a[1] if len(a) > 1 else None) if isinstance(a[0], (list, tuple)) else (a, None)
        return self._add(_VOL, nodes, eid)

    # ── reading ──
    def read(self, filename, vtk_cell_group_array=None):
        """FemMeshPy::read: a .vtk (FemVTKTools::readVTKMesh, its cell groups from vtk_cell_group_array) or a .unv
        (SMESH's DriverUNV_R_SMDS_Mesh); the transform reset (FemMesh::read)."""
        self.Placement = B.Placement()
        name = str(filename).lower()
        if name.endswith(".vtk"):
            _read_vtk(self, str(filename), vtk_cell_group_array)
        elif name.endswith(".unv"):
            _read_unv(self, str(filename))
        else:
            raise RuntimeError(f"Unknown extension: {filename}")

    # ── what FemMeshPy shows ──
    @property
    def Nodes(self):
        m = self.Placement.toMatrix()
        return {i: m.multVec(B.Vector(*p)) for i, p in sorted(self._nodes.items())}

    @property
    def NodeCount(self):
        return len(self._nodes)

    def _ids(self, kind):
        return tuple(i for i in sorted(self._elems) if self._elems[i][0] == kind)

    @property
    def Volumes(self):
        return self._ids(_VOL)

    @property
    def Faces(self):
        return self._ids(_FACE)

    @property
    def Edges(self):
        return self._ids(_EDGE)

    @property
    def VolumeCount(self):
        return len(self.Volumes)

    @property
    def FaceCount(self):
        return len(self.Faces)

    @property
    def EdgeCount(self):
        return len(self.Edges)

    @property
    def TetraCount(self):
        return sum(1 for i in self.Volumes if len(self._elems[i][1]) in (4, 10))

    @property
    def HexaCount(self):
        return sum(1 for i in self.Volumes if len(self._elems[i][1]) in (8, 20))

    @property
    def TriangleCount(self):
        return sum(1 for i in self.Faces if len(self._elems[i][1]) in (3, 6, 7))

    @property
    def QuadrangleCount(self):
        return sum(1 for i in self.Faces if len(self._elems[i][1]) in (4, 8, 9))

    @property
    def PrismCount(self):
        return sum(1 for i in self.Volumes if len(self._elems[i][1]) in (6, 15))

    @property
    def PyramidCount(self):
        return sum(1 for i in self.Volumes if len(self._elems[i][1]) in (5, 13))

    @property
    def PolygonCount(self):
        return 0

    @property
    def PolyhedronCount(self):
        return 0

    @property
    def SubMeshCount(self):
        return 0

    @property
    def Groups(self):
        return tuple(sorted(self._groups))

    @property
    def GroupCount(self):
        return len(self._groups)

    def getGroupName(self, gid):
        return self._groups[gid][0]

    def getGroupElementType(self, gid):
        return self._groups[gid][1]

    def getGroupElements(self, gid):
        return tuple(self._groups[gid][2])

    def addGroup(self, name, typestr, gid=-1):
        """FemMesh::addGroup: SMESH_Mesh::AddGroup takes the next of its own numbers, whatever id is asked for."""
        gid = self._next_gid
        self._next_gid += 1
        self._groups[gid] = (name, typestr, [])
        return gid

    def renameGroup(self, gid, name):
        """FemMesh::renameGroup: the group's name."""
        n, kind, ids = self._groups[gid]
        self._groups[gid] = (str(name), kind, ids)

    def removeGroup(self, gid):
        return self._groups.pop(gid, None) is not None

    def addGroupElements(self, gid, elements):
        self._groups[gid][2].extend(int(e) for e in elements)

    def getElementNodes(self, eid):
        """getElementNodes: the element's nodes in SMDS order."""
        return tuple(self._elems[eid][1]) if eid in self._elems else ()

    def getElementType(self, eid):
        if eid in self._elems:
            return self._elems[eid][0]
        if eid in self._nodes:
            return "Node"
        raise ValueError("No node or element for given id")

    def getNodeById(self, nid):
        return self.Placement.toMatrix().multVec(B.Vector(*self._nodes[nid]))

    def getNodeElements(self, nid, typestr="All"):
        return tuple(i for i in sorted(self._elems) if nid in self._elems[i][1]
                     and (typestr == "All" or self._elems[i][0] == typestr))

    def setTransform(self, m):
        self.Placement = B.Placement(m)

    @property
    def BoundBox(self):
        pts = list(self.Nodes.values())
        return B.BoundBox(min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts),
                          max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))

    # ── the lookups by shape (FemMesh.cpp) ──
    def _abs(self):
        m = self.Placement.toMatrix()
        return [(i, m.multVec(B.Vector(*p))) for i, p in sorted(self._nodes.items())]

    def _near(self, shape, limit, enlarge_box=True, optimal=False):
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.gp import gp_Pnt
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box, False if optimal else True)
        if enlarge_box:
            box.Enlarge(limit)
        out = []
        for i, v in self._abs():
            p = gp_Pnt(v.x, v.y, v.z)
            if box.IsOut(p):
                continue
            d = BRepExtrema_DistShapeShape(shape, BRepBuilderAPI_MakeVertex(p).Vertex())
            d.Perform()
            if not d.IsDone() or d.NbSolution() < 1:
                continue
            if d.Value() < limit:
                out.append(i)
        return out

    def getNodesByFace(self, face):
        """FemMesh::getNodesByFace: BRepBndLib::Add(face, box, Standard_False) enlarged by the face's tolerance, then each
        node within BRep_Tool::Tolerance(face) of it."""
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS
        f = TopoDS.Face(_topods(face))
        return self._near(f, BRep_Tool.Tolerance_s(f), True, optimal=True)

    def getNodesByEdge(self, edge):
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS
        e = TopoDS.Edge(_topods(edge))
        return self._near(e, BRep_Tool.Tolerance_s(e), True)

    def getNodesBySolid(self, solid):
        """getNodesBySolid: within ShapeAnalysis_ShapeTolerance's max tolerance (mode 1) of the solid; the box not enlarged."""
        from OCP.ShapeAnalysis import ShapeAnalysis_ShapeTolerance
        from OCP.TopAbs import TopAbs_SHAPE
        s = _topods(solid)
        return self._near(s, ShapeAnalysis_ShapeTolerance().Tolerance(s, 1, TopAbs_SHAPE), False)

    def getNodesByVertex(self, vertex):
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS
        v = TopoDS.Vertex(_topods(vertex))
        limit = BRep_Tool.Tolerance_s(v) ** 2
        p = BRep_Tool.Pnt_s(v)
        return [i for i, q in self._abs() if (q.x - p.X()) ** 2 + (q.y - p.Y()) ** 2 + (q.z - p.Z()) ** 2 <= limit]

    def getFacesByFace(self, face):
        on = set(self.getNodesByFace(face))
        return sorted(i for i in self.Faces if set(self._elems[i][1]) <= on)

    def getEdgesByEdge(self, edge):
        on = set(self.getNodesByEdge(edge))
        return sorted(i for i in self.Edges if set(self._elems[i][1]) <= on)

    def getVolumesByFace(self, face):
        on = set(self.getNodesByFace(face))
        faces = {i: set(self._elems[i][1]) for i in self.Faces if set(self._elems[i][1]) <= on}
        out = [(v, f) for v in self.Volumes for f, fn in sorted(faces.items()) if fn <= set(self._elems[v][1])]
        return sorted(out)

    def getccxVolumesByFace(self, face):
        """getccxVolumesByFace: each tetrahedron with a whole face on the shape's face, and that face's CalculiX number
        (from the node of the CalculiX-ordered volume that is not on it)."""
        on = set(self.getNodesByFace(face))
        order = {4: (1, 0, 2, 3), 10: (1, 0, 2, 3, 4, 6, 5, 8, 7, 9)}
        out = {}
        for v in self.Volumes:
            nodes = self._elems[v][1]
            if len(nodes) not in order:
                continue
            ccx = [nodes[j] for j in order[len(nodes)]]
            hit = [n for n in sorted(set(ccx)) if n in on]
            if (len(hit) == 3 and len(nodes) == 4) or (len(hit) == 6 and len(nodes) == 10):
                missing = next(i + 1 for i in range(4) if ccx[i] not in hit)
                out[v] = {1: 3, 2: 4, 3: 2, 4: 1}[missing]
        return sorted(out.items())

    def getFacesOnly(self):
        vols = [set(self._elems[v][1]) for v in self.Volumes]
        return tuple(f for f in self.Faces if not any(set(self._elems[f][1]) <= v for v in vols))

    @property
    def FacesOnly(self):
        return self.getFacesOnly()

    def getEdgesOnly(self):
        faces = [set(self._elems[f][1]) for f in self.Faces]
        return tuple(e for e in self.Edges if not any(set(self._elems[e][1]) <= f for f in faces))

    @property
    def EdgesOnly(self):
        return self.getEdgesOnly()

    # ── writeABAQUS (FemMesh::writeABAQUS) ──
    def writeABAQUS(self, fileName, elemParam, groupParam, volVariant="standard", faceVariant="shell",
                    edgeVariant="beam"):
        _write_abaqus(self, fileName, int(elemParam), bool(groupParam), volVariant, faceVariant, edgeVariant)

    # ── write (FemMesh::write) ──
    def write(self, filename):
        """FemMesh::write: a .unv as SMESH_Mesh::ExportUNV writes it (DriverUNV_W_SMDS_Mesh), with every group."""
        name = str(filename)
        if not name.lower().endswith(".unv"):
            raise RuntimeError(f"Unknown extension: {filename}")
        with open(name, "w") as f:
            f.write(_unv(self))


def _topods(s):
    return s._s if hasattr(s, "_s") else s


def _g(x):
    """std::ostream at precision 13 (the default floatfield): %.13g."""
    return "%.13g" % x


_VOL_VARIANTS = {"standard": {}, "reduced": {"Hexa8": "C3D8R", "Hexa20": "C3D20R"},
                 "incompatible": {"Hexa8": "C3D8I"}, "modified": {"Tetra10": "C3D10T"},
                 "fluid": {"Tetra4": "F3D4", "Penta6": "F3D6", "Hexa8": "F3D8"}}
_FACE_VARIANTS = {
    "shell": ("S3", "S4", "S6", "S8"), "shell reduced": ("S3", "S4R", "S6", "S8R"),
    "membrane": ("M3D3", "M3D4", "M3D6", "M3D8"), "membrane reduced": ("M3D3", "M3D4R", "M3D6", "M3D8R"),
    "stress": ("CPS3", "CPS4", "CPS6", "CPS8"), "stress reduced": ("CPS3", "CPS4R", "CPS6", "CPS8R"),
    "strain": ("CPE3", "CPE4", "CPE6", "CPE8"), "strain reduced": ("CPE3", "CPE4R", "CPE6", "CPE8R"),
    "axisymmetric": ("CAX3", "CAX4", "CAX6", "CAX8"), "axisymmetric reduced": ("CAX3", "CAX4R", "CAX6", "CAX8R")}
_EDGE_VARIANTS = {"beam": ("B31", "B32"), "beam reduced": ("B31R", "B32R"), "truss": ("T3D2", "T3D3"),
                  "network": ("B31", "D")}


def _write_abaqus(mesh, filename, elem_param, group_param, vol_v, face_v, edge_v):
    if vol_v not in _VOL_VARIANTS or face_v not in _FACE_VARIANTS or edge_v not in _EDGE_VARIANTS:
        raise ValueError("Invalid variant value")
    var = {"Tetra4": "C3D4", "Penta6": "C3D6", "Hexa8": "C3D8", "Tetra10": "C3D10", "Penta15": "C3D15",
           "Hexa20": "C3D20", **_VOL_VARIANTS[vol_v]}
    var.update(zip(("Tria3", "Quad4", "Tria6", "Quad8"), _FACE_VARIANTS[face_v]))
    var.update(zip(("Seg2", "Seg3"), _EDGE_VARIANTS[edge_v]))
    order = {var["Seg2"]: (0, 1), var["Seg3"]: (0, 2, 1),
             var["Tria3"]: (0, 1, 2), var["Tria6"]: (0, 1, 2, 3, 4, 5), var["Quad4"]: (0, 1, 2, 3),
             var["Quad8"]: (0, 1, 2, 3, 4, 5, 6, 7),
             var["Tetra4"]: (1, 0, 2, 3), var["Tetra10"]: (1, 0, 2, 3, 4, 6, 5, 8, 7, 9),
             var["Hexa8"]: (5, 6, 7, 4, 1, 2, 3, 0),
             var["Hexa20"]: (5, 6, 7, 4, 1, 2, 3, 0, 13, 14, 15, 12, 9, 10, 11, 8, 17, 18, 19, 16),
             var["Penta6"]: (4, 5, 3, 1, 2, 0), var["Penta15"]: (4, 5, 3, 1, 2, 0, 10, 11, 9, 7, 8, 6, 13, 14, 12)}
    # the type maps by node count (std::map::insert keeps the first of a key)
    edge_t = {2: var["Seg2"], 3: var["Seg3"]}
    face_t = {3: var["Tria3"], 6: var["Tria6"], 4: var["Quad4"], 8: var["Quad8"]}
    vol_t = {4: var["Tetra4"], 10: var["Tetra10"], 8: var["Hexa8"], 20: var["Hexa20"], 6: var["Penta6"],
             15: var["Penta15"]}

    def collect(ids, types):
        out: dict[str, dict] = {}
        for i in ids:
            nodes = mesh._elems[i][1]
            t = types.get(len(nodes))
            if t is not None:
                out.setdefault(t, {})[i] = [nodes[j] for j in order[t]]
        return out

    m = mesh.Placement.toMatrix()
    verts = {i: m.multVec(B.Vector(*p)) for i, p in sorted(mesh._nodes.items())}
    vols = collect(mesh.Volumes, vol_t)
    faces = {}
    if elem_param == 0 or (elem_param == 1 and not vols):
        faces = collect(mesh.Faces, face_t)
    if elem_param == 2:
        faces = collect(mesh.getFacesOnly(), face_t)
    edges = {}
    if elem_param == 0 or (elem_param == 1 and not vols and not faces):
        edges = collect(mesh.Edges, edge_t)
    if elem_param == 2:
        edges = collect(mesh.getEdgesOnly(), edge_t)
    lines = ["** written by FreeCAD inp file writer for CalculiX,Abaqus meshes"]
    head = {0: "** all mesh elements.", 1: "** highest dimension mesh elements only.",
            2: "** FEM mesh elements only (edges if they do not belong to faces and faces if they do not belong to "
               "volumes)."}
    if elem_param not in head:
        raise RuntimeError("Unknown ABAQUS element choice parameter, [0|1|2] are allowed.")
    lines += [head[elem_param], ""]
    lines += ["** Nodes", "*Node, NSET=Nall"]
    if face_v.split(" ")[0] in ("stress", "strain", "axisymmetric"):
        for t in faces.values():
            for nodes in t.values():
                for n in nodes:
                    verts[n] = B.Vector(verts[n].x, verts[n].y, 0.0)
    for i, v in verts.items():
        lines.append(f"{i}, {_g(v.x)}, {_g(v.y)}, {_g(v.z)}")
    lines += ["", ""]
    elset = []
    if vols:
        for t, els in sorted(vols.items()):
            lines += ["** Volume elements", f"*Element, TYPE={t}, ELSET=Evolumes"]
            for i, nodes in sorted(els.items()):
                s = str(i)
                for k, n in enumerate(nodes):     # CalculiX takes at most 16 entries a line
                    s += f", {n}" if k < 15 else (f",\n{n}" if k == 15 else f", {n}")
                lines.append(s)
        elset.append("Evolumes")
        lines.append("")
    if faces:
        for t, els in sorted(faces.items()):
            lines += ["** Face elements", f"*Element, TYPE={t}, ELSET=Efaces"]
            lines += [str(i) + "".join(f", {n}" for n in nodes) for i, nodes in sorted(els.items())]
        elset.append("Efaces")
        lines.append("")
    if edges:
        for t, els in sorted(edges.items()):
            lines += ["** Edge elements", f"*Element, TYPE={t}, ELSET=Eedges"]
            lines += [str(i) + "".join(f", {n}" for n in nodes) for i, nodes in sorted(els.items())]
        elset.append("Eedges")
        lines.append("")
    _tail(mesh, lines, elset, group_param)
    with open(filename, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _tail(mesh, lines, elset, group_param):
    """writeABAQUS's end: the element set Eall, then with groupParam each group's ids."""
    lines += ["** Define element set Eall", "*ELSET, ELSET=Eall", ", ".join(elset)]
    if group_param:
        lines += ["", "** Group data"]
        for gid in sorted(mesh._groups):
            name, kind, ids = mesh._groups[gid]
            lines.append(f"** GroupID: {gid} --> GroupName: {name} --> GroupElementType: {kind}")
            lines.append(f"*NSET, NSET={name}" if kind == "Node" else f"*ELSET, ELSET={name}")
            lines += [str(i) for i in sorted(set(ids))]
            lines.append("")


# ── SMESH's UNV reader (DriverUNV_R_SMDS_Mesh) ───────────────────────────────────────────────────────────────────────

def _d_to_e(s):
    return float(s.replace("D", "E").replace("d", "e"))


def _datasets(text):
    """The UNV file's datasets: (number, the lines between its -1 delimiters)."""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip() == "-1" and i + 1 < len(lines):
            num = lines[i + 1].strip()
            j = i + 2
            while j < len(lines) and lines[j].strip() != "-1":
                j += 1
            out.append((num, lines[i + 2:j]))
            i = j + 1
        else:
            i += 1
    return out


# DriverUNV_R_SMDS_Mesh::Perform's node order per FE descriptor: UNV's labels into SMDS's
_UNV_ORDER = {
    111: (0, 2, 1, 3), 118: (0, 4, 2, 9, 5, 3, 1, 6, 8, 7), 112: (0, 2, 1, 3, 5, 4),
    113: (0, 4, 2, 9, 13, 11, 5, 3, 1, 14, 12, 10, 6, 8, 7), 115: (0, 3, 2, 1, 4, 7, 6, 5),
    116: (0, 6, 4, 2, 12, 18, 16, 14, 7, 5, 3, 1, 19, 17, 15, 13, 8, 11, 10, 9),
    114: (0, 6, 4, 2, 7, 5, 3, 1, 8, 11, 10, 9, 12)}
_TRI3 = (41, 51, 61, 74, 81, 91)
_TRI6 = (42, 52, 62, 72, 82, 92)
_QUAD4 = (44, 54, 64, 71, 84, 94)
_QUAD8 = (45, 55, 65, 75, 85, 95)
_BEAM = (11, 21, 22, 23, 24, 25)


def _read_unv(mesh, path):
    with open(path, "rb") as f:
        text = f.read().decode("latin-1")
    sets = _datasets(text)
    for num, body in sets:
        if num == "164":
            factor = _d_to_e(body[1].split()[0]) if len(body) > 1 else 1.0
            mesh._len_factor = factor
    for num, body in sets:
        if num != "2411":
            continue
        toks = " ".join(body).split()
        i = 0
        while i + 6 < len(toks) + 1 and i < len(toks):
            label = int(toks[i])
            x, y, z = (_d_to_e(t) for t in toks[i + 4:i + 7])
            f = getattr(mesh, "_len_factor", 1.0)
            mesh._nodes[label] = (x * f, y * f, z * f)
            i += 7
    for num, body in sets:
        if num != "2412":
            continue
        toks = " ".join(body).split()
        i = 0
        while i < len(toks):
            label, fe, _phys, _mat, _color, n = (int(t) for t in toks[i:i + 6])
            i += 6
            if fe in _BEAM:
                i += 3                                    # beam orientation, fore and aft ends
            nodes = [int(t) for t in toks[i:i + n]]
            i += n
            if fe in _BEAM:
                mesh._elems[label] = (_EDGE, tuple(nodes) if n == 2 else (nodes[0], nodes[2], nodes[1]))
            elif fe in _TRI3 or fe in _QUAD4:
                mesh._elems[label] = (_FACE, tuple(nodes))
            elif fe in _TRI6:
                o = (0, 2, 4, 1, 3, 5) + ((6,) if n == 7 else ())
                mesh._elems[label] = (_FACE, tuple(nodes[j] for j in o))
            elif fe in _QUAD8:
                o = (0, 2, 4, 6, 1, 3, 5, 7) + ((8,) if n == 9 else ())
                mesh._elems[label] = (_FACE, tuple(nodes[j] for j in o))
            elif fe in _UNV_ORDER:
                mesh._elems[label] = (_VOL, tuple(nodes[j] for j in _UNV_ORDER[fe]))
    if hasattr(mesh, "_len_factor"):
        del mesh._len_factor


# ── FemVTKTools::importVTKMesh, over a legacy VTK file ───────────────────────────────────────────────────────────────

# SMDS_MeshCell::toVtkOrder per SMDS entity (SMESH's SMDS_MeshCell.cpp); fromVtkOrder is each one's inverse
_TO_VTK = {10: (0, 2, 1, 3), 24: (0, 2, 1, 3, 6, 5, 4, 7, 9, 8), 14: (0, 3, 2, 1, 4),
           27: (0, 3, 2, 1, 4, 8, 7, 6, 5, 9, 12, 11, 10), 12: (0, 3, 2, 1, 4, 7, 6, 5),
           25: (0, 3, 2, 1, 4, 7, 6, 5, 11, 10, 9, 8, 15, 14, 13, 12, 16, 19, 18, 17)}
_FROM_VTK = {t: tuple(sorted(range(len(o)), key=lambda i: o[i])) for t, o in _TO_VTK.items()}
# VTK cell type -> (SMDS kind, dimension)
_VTK_KIND = {1: ("0DElement", 0), 3: (_EDGE, 1), 21: (_EDGE, 1), 5: (_FACE, 2), 22: (_FACE, 2), 9: (_FACE, 2),
             23: (_FACE, 2), 10: (_VOL, 3), 24: (_VOL, 3), 12: (_VOL, 3), 25: (_VOL, 3), 13: (_VOL, 3), 26: (_VOL, 3),
             14: (_VOL, 3), 27: (_VOL, 3)}


def _read_vtk(mesh, path, group_array=None):
    with open(path) as f:
        toks = f.read().split()
    i = toks.index("POINTS")
    n = int(toks[i + 1])
    i += 3
    pts = [tuple(float(t) for t in toks[i + 3 * k:i + 3 * k + 3]) for k in range(n)]
    mesh._nodes, mesh._elems = {}, {}
    for k, p in enumerate(pts):                   # AddNodeWithID(..., i + 1)
        mesh._nodes[k + 1] = p
    i = toks.index("CELLS")
    ncells = int(toks[i + 1])
    i += 3
    if toks[i] == "OFFSETS":                      # the VTK 5.1 layout: OFFSETS and CONNECTIVITY arrays
        i += 2
        offs = [int(t) for t in toks[i:i + ncells]]
        i += ncells
        i += 2
        conn = [int(t) for t in toks[i:i + offs[-1]]]
        cells = [conn[offs[c]:offs[c + 1]] for c in range(ncells - 1)]
    else:
        cells = []
        for _ in range(ncells):
            m = int(toks[i])
            cells.append([int(t) for t in toks[i + 1:i + 1 + m]])
            i += m + 1
    j = toks.index("CELL_TYPES")
    types = [int(t) for t in toks[j + 2:j + 2 + len(cells)]]
    dims = {}
    for c, (ids, vt) in enumerate(zip(cells, types)):
        kind = _VTK_KIND.get(vt)
        if kind is None:
            continue                              # "Only common 1D, 2D and 3D Cells are supported"
        order = _FROM_VTK.get(vt)
        nodes = tuple(ids[order[k]] + 1 for k in range(len(ids))) if order else tuple(x + 1 for x in ids)
        mesh._elems[c + 1] = (kind[0], nodes)
        dims[c + 1] = kind[1]
    if group_array:
        _vtk_groups(mesh, toks, group_array, dims, len(cells))


def _vtk_groups(mesh, toks, name, dims, ncells):
    """FemVTKTools::importVTKCellGroup: an integer cell array's values as groups (named by the value, the value its
    id), each of one dimension's elements."""
    try:
        i = toks.index("CELL_DATA")
    except ValueError:
        return
    while i < len(toks) and not (toks[i] in ("SCALARS", "FIELD") and name in toks[i:i + 8]):
        i += 1
    if i >= len(toks):
        return
    if toks[i] == "SCALARS":
        i += 3 + (1 if toks[i + 3].isdigit() else 0)
        if toks[i] == "LOOKUP_TABLE":
            i += 2
        vals = [int(float(t)) for t in toks[i:i + ncells]]
    else:
        k = toks.index(name, i)
        vals = [int(float(t)) for t in toks[k + 4:k + 4 + ncells]]
    groups: dict[int, list] = {}
    for c, v in enumerate(vals):
        if v >= 0:
            groups.setdefault(v, []).append(c + 1)
    kinds = {0: "0DElement", 1: "Edge", 2: "Face", 3: "Volume"}
    for v, els in sorted(groups.items()):
        gid = mesh.addGroup(str(v), kinds[dims.get(els[0], 3)], v)
        mesh.addGroupElements(gid, sorted(set(els)))


# SMESH's UNV writer (DriverUNV_W_SMDS_Mesh::Perform): each element kind by (SMDS kind, node count) -> (its UNV
# fe_descriptor_id, the order of its nodes as written). The order is SMDS -> VTK (SMDS_MeshCell::toVtkOrder, which
# the cell is stored in) and then SMDS_VtkCellIteratorToUNV's ids over the VTK cell; a 27 node hexahedron writes 20
# and a 9 node quadrangle 8. Pyramids and polyhedra are not written.
def _unv_order(to_vtk, to_unv, n):
    vtk = list(to_vtk) if to_vtk else list(range(n))
    return tuple(vtk[i] for i in to_unv) if to_unv else tuple(vtk[:n])


_UNV_KIND = {
    (_EDGE, 2): (11, (0, 1)), (_EDGE, 3): (22, (0, 2, 1)),
    (_FACE, 3): (41, (0, 1, 2)), (_FACE, 4): (44, (0, 1, 2, 3)),
    (_FACE, 6): (42, (0, 3, 1, 4, 2, 5)), (_FACE, 7): (42, (0, 3, 1, 4, 2, 5)),
    (_FACE, 8): (45, (0, 4, 1, 5, 2, 6, 3, 7)), (_FACE, 9): (45, (0, 4, 1, 5, 2, 6, 3, 7)),
    (_VOL, 4): (111, _unv_order((0, 2, 1, 3), None, 4)),
    (_VOL, 10): (118, _unv_order((0, 2, 1, 3, 6, 5, 4, 7, 9, 8), (0, 4, 1, 5, 2, 6, 7, 8, 9, 3), 10)),
    (_VOL, 6): (112, _unv_order(None, (0, 2, 1, 3, 5, 4), 6)),
    (_VOL, 15): (113, _unv_order(None, (0, 8, 2, 7, 1, 6, 12, 14, 13, 3, 11, 5, 10, 4, 9), 15)),
    (_VOL, 8): (115, _unv_order((0, 3, 2, 1, 4, 7, 6, 5), None, 8)),
    (_VOL, 20): (116, _unv_order((0, 3, 2, 1, 4, 7, 6, 5, 11, 10, 9, 8, 15, 14, 13, 12, 16, 19, 18, 17),
                                 (0, 8, 1, 9, 2, 10, 3, 11, 16, 17, 18, 19, 4, 12, 5, 13, 6, 14, 7, 15), 20)),
    (_VOL, 27): (116, _unv_order((0, 3, 2, 1, 4, 7, 6, 5, 11, 10, 9, 8, 15, 14, 13, 12, 16, 19, 18, 17,
                                  21, 23, 24, 22, 20, 25, 26),
                                 (0, 8, 1, 9, 2, 10, 3, 11, 16, 17, 18, 19, 4, 12, 5, 13, 6, 14, 7, 15), 27)),
}


def _unv(mesh):
    """The text of SMESH's UNV export: datasets 164 (units), 2420 (coordinate system), 2411 (nodes), 2412 (edges,
    faces, then volumes, each in ID order) and 2467 (the groups, labelled by their id + 1). The elements are
    labelled as SMESH's VTK cells number them: their ids without the 0D elements, which a group names as 0."""
    out = ["    -1", "   164", "         1  SI: Meter (newton)         2",
           "    1.0000000000000000E+0    1.0000000000000000E+0    1.0000000000000000E+0",
           "    2.7314999999999998E+2", "    -1",
           "    -1", "  2420", "         1", "SMESH_Mesh", "         1         0         0",
           "Global Cartesian Coordinate System",
           "    1.0000000000000000E+0    0.0000000000000000E+0    0.0000000000000000E+0",
           "    0.0000000000000000E+0    1.0000000000000000E+0    0.0000000000000000E+0",
           "    0.0000000000000000E+0    0.0000000000000000E+0    1.0000000000000000E+0",
           "    0.0000000000000000E+0    0.0000000000000000E+0    0.0000000000000000E+0", "    -1",
           "    -1", "  2411"]
    for nid, (x, y, z) in sorted(mesh._nodes.items()):
        out.append("%10d%10d%10d%10d" % (nid, 1, 1, 11))
        out.append("%25.16E%25.16E%25.16E" % (x, y, z))
    out += ["    -1", "    -1", "  2412"]
    label, zero_d = {}, 0
    for eid in sorted(mesh._elems):
        if mesh._elems[eid][0] == "0DElement":
            zero_d += 1
            label[eid] = 0
        else:
            label[eid] = eid - zero_d
    for kind in (_EDGE, _FACE, _VOL):
        for eid in sorted(mesh._elems):
            k, nodes = mesh._elems[eid]
            if k != kind or (k, len(nodes)) not in _UNV_KIND:
                continue
            fe, order = _UNV_KIND[(k, len(nodes))]
            labels = [nodes[i] for i in order[:20]]
            out.append("%10d%10d%10d%10d%10d%10d" % (label[eid], fe, 2, 1, 7, len(labels)))
            if fe in (11, 21, 22, 23, 24, 25):                       # UNV2412::IsBeam
                out.append("%10d%10d%10d" % (0, 1, 1))
            for i in range(0, len(labels), 8):
                out.append("".join("%10d" % n for n in labels[i:i + 8]))
    out.append("    -1")
    if mesh._groups:
        out += ["    -1", "  2467"]
        for gid in sorted(mesh._groups):
            name, kind, ids = mesh._groups[gid]
            ids = sorted(set(ids))
            recs = [(7, i) for i in ids] if kind == "Node" else [(8, label.get(i, i)) for i in ids]
            out.append("%10d%10d%10d%10d%10d%10d%10d%10d" % (gid + 1, 0, 0, 0, 0, 0, 0, len(recs)))
            out.append(name)
            for i in range(0, len(recs), 2):
                out.append("".join("%10d%10d%10d%10d" % (t, n, 0, 0) for t, n in recs[i:i + 2]))
            if not recs:
                out.append("")
        out.append("    -1")
    return "\n".join(out) + "\n"


def read(filename):
    """Fem.read: a mesh file as a Fem::FemMeshObject's mesh (here the FemMesh)."""
    m = FemMesh()
    m.read(filename)
    return m


def isnan(x):
    return math.isnan(x)
