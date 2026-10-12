"""Printed parts: the mesh a slicer reads (3MF and STL), the same bytes on every run, and read back.

A slicer reads triangles, so a printed part's file is a mesh of its solid. Two things decide whether the
mesh is the part's: how finely the surface is cut, and whether the file says the same thing when it is read
by someone else's code. Both are fixed here, so the file is a function of the part and nothing else.

The mesh
--------
`mesh_of(solid)` meshes a fresh copy of the solid (a shape that was meshed before keeps its triangles, and
OCCT reuses a triangulation that is fine enough, so the result would depend on what the process had done)
with an absolute linear deflection of LINEAR_MM and an angular one of ANGULAR_RAD. Those two numbers are
what holds the mesh's volume within 0.5 % of the solid's: a sphere is the worst shape, and at 0.1 rad it is
about 0.2 % short. The nodes are put on a grid of GRID_MM (0.1 micrometre) as integers, coincident nodes are
merged, and the vertices are sorted; each triangle starts at its smallest vertex and the triangles are
sorted. OCCT 7.9 and 8.0 mesh a face the same way, but they do not visit the faces, or start a triangle, in
the same order, so the bytes follow from the sorted integer mesh and not from the order the kernel gave.
Integers also keep the arithmetic exact: a normal is a cross product of integers, and a coordinate is
written from its integer, never from a float's repr.

3MF
---
`write_3mf` is a stdlib zip: [Content_Types].xml, _rels/.rels and 3D/3dmodel.model, stored without
compression and with a fixed time stamp, so that the same mesh gives the same bytes (a deflated stream
changes with the zlib that made it). It is written here and not by lib3mf for three reasons: lib3mf has no
wheel for Linux on aarch64, where pyproject leaves it out; its writer's choices (the compressor, the
metadata, the identifiers) are the library's and move with its version, and the bytes are pinned; and the
file is small enough to write by hand. lib3mf is the reader instead (`read_3mf`), which is what makes the
read-back a check: the code that reads the file is not the code that wrote it, and it is the 3MF
Consortium's own. Where lib3mf is missing, a reader of this module's own reads the file (zipfile and
ElementTree), and the row says so. The metadata is a Title and an Application and no date. A draft carries
NOT VERIFIED in the object's name, which is what a slicer lists, and in a Description.

STL
---
`write_stl` is a binary STL of the same mesh: an 80-byte header (the name, or NOT VERIFIED for a draft),
the count, and for each triangle its normal, three vertices as little-endian float32 and a zero attribute.

What the rule reads back
------------------------
`print_rows` is the rule of a printed part: the 3MF is written, read back, and its triangles are checked.

  watertight   every edge is used by exactly two triangles, one in each direction (closed, manifold, and
               every triangle wound the same way round), and lib3mf, when it reads the file, agrees
  volume       the mesh's signed volume is the solid's within 0.5 %, and positive (a mesh turned inside out
               has a negative volume)

A mesh that cannot be made, a file nobody can read, or a solid with no volume is UNCHECKED: nothing was
measured. The limit of 0.5 % is the plan's (docs/STEP6_PLAN.md, piece D).
"""
from __future__ import annotations

import copy
import io
import struct
import zipfile
from typing import NamedTuple
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from .registry import Row

LINEAR_MM = 0.01            # the most a mesh face may sit from the surface it stands for
ANGULAR_RAD = 0.1           # and the most two neighbouring normals of a curved face may turn between nodes
GRID_MM = 1e-4              # the grid every node is put on
SCALE = 10_000              # nodes per millimetre: 1 / GRID_MM
VOLUME_LIMIT = 0.005        # the mesh's volume may differ from the solid's by this fraction
ZIP_TIME = (1980, 1, 1, 0, 0, 0)        # the earliest time a zip can say

CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                 '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
                 '</Types>\n')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n')
MODEL_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
SOURCE = ("the mesh of the solid at {lin:g} mm / {ang:g} rad read back from the 3MF; the volume is the B-rep's "
          "(docs/STEP6_PLAN.md, piece D)").format(lin=LINEAR_MM, ang=ANGULAR_RAD)


class Mesh(NamedTuple):
    vertices: np.ndarray        # (n, 3) int64, in GRID_MM, sorted
    triangles: np.ndarray       # (m, 3) int64, indices into vertices; each starts at its smallest, sorted
    dropped: int = 0            # triangles that the grid collapsed to a line or a point, and were left out


class Unreadable(Exception):
    """A file that could not be read back as a mesh: the reason is the message."""


# ─── The mesh ────────────────────────────────────────────────────────────────

def mesh_of(solid, linear: float = LINEAR_MM, angular: float = ANGULAR_RAD) -> Mesh:
    """The canonical mesh of a solid (see the module docstring); ValueError if the kernel made no triangles."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_Orientation
    from OCP.TopLoc import TopLoc_Location
    fresh = copy.deepcopy(solid)
    BRepMesh_IncrementalMesh(fresh.wrapped, linear, False, angular, False)
    points, tris, base = [], [], 0
    for face in fresh.faces():
        loc = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(face.wrapped, loc)
        if poly is None:
            continue
        trsf = loc.Transformation()
        flip = face.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
        for i in range(1, poly.NbNodes() + 1):
            p = poly.Node(i).Transformed(trsf)
            points.append((p.X(), p.Y(), p.Z()))
        for i in range(1, poly.NbTriangles() + 1):
            a, b, c = poly.Triangle(i).Get()
            tris.append((a - 1 + base, c - 1 + base, b - 1 + base) if flip else (a - 1 + base, b - 1 + base, c - 1 + base))
        base = len(points)
    if not tris:
        raise ValueError("the kernel made no triangles for this solid")
    return canonical(np.array(points, dtype=float), np.array(tris, dtype=np.int64))


def canonical(points: np.ndarray, tris: np.ndarray) -> Mesh:
    """Nodes on the grid, coincident ones merged, everything sorted: the same mesh whatever order it arrived in."""
    grid = np.rint(np.asarray(points, dtype=float) * SCALE).astype(np.int64)
    vertices, inverse = np.unique(grid, axis=0, return_inverse=True)
    tris = inverse.reshape(-1)[np.asarray(tris, dtype=np.int64)]
    keep = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    dropped = int((~keep).sum())
    tris = tris[keep]
    first = np.argmin(tris, axis=1)                             # each triangle starts at its smallest vertex
    rows = np.arange(len(tris))
    tris = np.stack([tris[rows, first], tris[rows, (first + 1) % 3], tris[rows, (first + 2) % 3]], axis=1)
    order = np.lexsort((tris[:, 2], tris[:, 1], tris[:, 0]))
    return Mesh(vertices, tris[order], dropped)


# ─── The numbers a mesh has ──────────────────────────────────────────────────

class Report(NamedTuple):
    volume_mm3: float
    open_edges: int             # directed edges whose opposite is missing: a hole, or a triangle turned the wrong way
    repeated_edges: int         # directed edges used more than once: more than two triangles at an edge
    triangles: int
    vertices: int


def report(mesh: Mesh) -> Report:
    v, t = mesh.vertices, mesh.triangles
    n = len(v)
    if len(t) == 0:
        return Report(0.0, 0, 0, 0, n)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    forward = np.concatenate([a * n + b, b * n + c, c * n + a])
    back = np.concatenate([b * n + a, c * n + b, a * n + c])
    codes, counts = np.unique(forward, return_counts=True)
    repeated = int((counts > 1).sum())
    open_edges = int((~np.isin(codes, back)).sum())
    p = v.astype(float) / SCALE
    volume = float(np.einsum("ij,ij->i", p[a], np.cross(p[b], p[c])).sum() / 6.0)
    return Report(volume, open_edges, repeated, len(t), n)


# ─── Writing ─────────────────────────────────────────────────────────────────

def _dec(q: int) -> str:
    """A grid integer as a decimal, exactly: 125000 is 12.5, -3 is -0.0003."""
    whole, frac = divmod(abs(q), SCALE)
    out = f"{'-' if q < 0 else ''}{whole}"
    return out + "." + f"{frac:04d}".rstrip("0") if frac else out


def write_3mf(mesh: Mesh, name: str, stamp: str | None = None) -> bytes:
    """A 3MF of one object, the same bytes for the same mesh and name (see the module docstring)."""
    title = f"{name} {stamp}" if stamp else name
    verts = "".join(f'<vertex x="{_dec(x)}" y="{_dec(y)}" z="{_dec(z)}"/>\n' for x, y, z in mesh.vertices.tolist())
    tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>\n' for a, b, c in mesh.triangles.tolist())
    meta = f'<metadata name="Title">{escape(title)}</metadata>\n<metadata name="Application">cad-agent</metadata>\n'
    if stamp:
        meta += f'<metadata name="Description">{escape(stamp)}: not from a verified design</metadata>\n'
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<model unit="millimeter" xml:lang="en-US" xmlns="{MODEL_NS}">\n{meta}'
             f'<resources>\n<object id="1" type="model" name={quoteattr(title)}>\n<mesh>\n'
             f'<vertices>\n{verts}</vertices>\n<triangles>\n{tris}</triangles>\n</mesh>\n</object>\n</resources>\n'
             '<build>\n<item objectid="1"/>\n</build>\n</model>\n')
    return _zip([("[Content_Types].xml", CONTENT_TYPES), ("_rels/.rels", RELS), ("3D/3dmodel.model", model)])


def _zip(entries: list[tuple[str, str]]) -> bytes:
    """Stored entries, in order, with one time stamp and Unix attributes whatever machine writes them."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for path, text in entries:
            info = zipfile.ZipInfo(path, ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            z.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


def write_stl(mesh: Mesh, name: str, stamp: str | None = None) -> bytes:
    """A binary STL of the mesh: normals from the integer vertices, so they are the same on every machine."""
    text = "cad-agent: " + (f"{name} {stamp}" if stamp else name)      # never "solid", which makes readers think it is ASCII
    header = text.encode("ascii", "replace")[:80].ljust(80, b" ")
    v, t = mesh.vertices, mesh.triangles
    corners = v[t]                                                      # (m, 3, 3) int64
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]).astype(float)
    length = np.sqrt((normal ** 2).sum(axis=1))
    normal = np.divide(normal, length[:, None], out=np.zeros_like(normal), where=length[:, None] > 0)
    record = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    record["n"] = normal
    record["v"] = corners.astype(float) / SCALE
    return header + struct.pack("<I", len(t)) + record.tobytes()


# ─── Reading ─────────────────────────────────────────────────────────────────

class Read(NamedTuple):
    mesh: Mesh
    reader: str                 # "lib3mf" or "built-in"
    manifold: bool | None       # lib3mf's own verdict (IsManifoldAndOriented); None when it did not read the file
    objects: int
    items: int                  # build items


def read_3mf(data: bytes, prefer_lib3mf: bool = True) -> Read:
    """The mesh in a 3MF, by lib3mf where it is installed, else by the built-in reader. Unreadable if it cannot."""
    lib = _lib3mf() if prefer_lib3mf else None
    if lib is not None:
        return _read_lib3mf(lib, data)
    return _read_builtin(data)


def _lib3mf():
    try:
        import lib3mf
    except Exception:           # not installed (Linux on aarch64 has no wheel), or its library will not load
        return None
    return lib3mf


def _read_lib3mf(lib, data: bytes) -> Read:
    try:
        wrapper = lib.Wrapper()
        model = wrapper.CreateModel()
        model.QueryReader("3mf").ReadFromBuffer(bytearray(data))
        points, tris, manifold, objects = [], [], True, 0
        meshes = model.GetMeshObjects()
        while meshes.MoveNext():
            obj = meshes.GetCurrentMeshObject()
            objects += 1
            base = len(points)
            points += [tuple(p.Coordinates) for p in obj.GetVertices()]
            tris += [tuple(base + i for i in t.Indices) for t in obj.GetTriangleIndices()]
            manifold = manifold and bool(obj.IsManifoldAndOriented())
        items, build = 0, model.GetBuildItems()
        while build.MoveNext():
            items += 1
    except Exception as e:
        raise Unreadable(f"lib3mf cannot read it: {type(e).__name__}: {e}") from None
    if not tris:
        raise Unreadable("lib3mf read it and found no triangles")
    return Read(canonical(np.array(points, dtype=float), np.array(tris, dtype=np.int64)), "lib3mf", manifold,
                objects, items)


def _read_builtin(data: bytes) -> Read:
    import xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if "[Content_Types].xml" not in names or "_rels/.rels" not in names:
                raise Unreadable("the zip has no [Content_Types].xml and _rels/.rels: not a 3MF package")
            model = ET.fromstring(z.read("3D/3dmodel.model"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise Unreadable(f"the built-in reader cannot read it: {type(e).__name__}: {e}") from None
    ns = "{" + MODEL_NS + "}"
    if model.get("unit") != "millimeter":
        raise Unreadable(f"the model's unit is {model.get('unit')!r}, not millimeter")
    points, tris, objects = [], [], 0
    for obj in model.iter(ns + "object"):
        mesh = obj.find(ns + "mesh")
        if mesh is None:
            continue
        objects += 1
        base = len(points)
        points += [(float(v.get("x")), float(v.get("y")), float(v.get("z"))) for v in mesh.iter(ns + "vertex")]
        for t in mesh.iter(ns + "triangle"):
            idx = tuple(int(t.get(k)) for k in ("v1", "v2", "v3"))
            if not all(0 <= i < len(points) - base for i in idx):
                raise Unreadable(f"a triangle names a vertex that does not exist: {idx}")
            tris.append(tuple(base + i for i in idx))
    items = sum(1 for _ in model.iter(ns + "item"))
    if not tris:
        raise Unreadable("the model has no triangles")
    return Read(canonical(np.array(points, dtype=float), np.array(tris, dtype=np.int64)), "built-in", None,
                objects, items)


# ─── The rule ────────────────────────────────────────────────────────────────

class Printed(NamedTuple):
    rows: list
    three_mf: bytes | None
    stl: bytes | None
    mesh: Mesh | None


def print_rows(name: str, solid, stamp: str | None = None) -> Printed:
    """The files of a printed part and the rows that say whether the 3MF reads back as the part.

    The bytes are returned even when a row fails, so that `cad shop --draft` can write what there is; the
    caller decides. They are None only when no mesh could be made at all.
    """
    from .geom import volume
    rows = []

    def row(rule, state, measured, limit):
        rows.append(Row(subject=name, rule=rule, state=state, measured=measured, limit=limit, source=SOURCE))

    try:
        mesh = mesh_of(solid)
        data = write_3mf(mesh, name, stamp)
        stl = write_stl(mesh, name, stamp)
    except Exception as e:      # noqa: BLE001 - say so, never pass what could not be made
        for rule, limit in (("3mf watertight", "closed, manifold, one way round"),
                            ("3mf volume", f"within {VOLUME_LIMIT * 100:g} % of the solid's")):
            row(rule, "UNCHECKED", f"no mesh: {type(e).__name__}: {e}", limit)
        return Printed(rows, None, None, None)
    try:
        read = read_3mf(data)
    except Unreadable as e:
        row("3mf watertight", "FAIL", f"the file does not read back: {e}", "a 3MF that lib3mf reads")
        row("3mf volume", "UNCHECKED", "the file does not read back", f"within {VOLUME_LIMIT * 100:g} % of the solid's")
        return Printed(rows, data, stl, mesh)

    got = report(read.mesh)
    how = f"read by {read.reader}" + ("" if read.reader == "lib3mf" else " (lib3mf is not installed)")
    shape = f"{got.triangles} triangles, {got.vertices} vertices"
    if mesh.dropped:        # the pole of a sphere: a triangle with two nodes at one point has no area; the edge check still binds
        shape += f" ({mesh.dropped} zero-area left out)"
    problems = []
    if got.open_edges:
        problems.append(f"{got.open_edges} edges have no triangle on their other side")
    if got.repeated_edges:
        problems.append(f"{got.repeated_edges} edges are used by more than two triangles")
    if read.manifold is False:
        problems.append("lib3mf says it is not manifold and oriented")
    if read.objects != 1 or read.items != 1:
        problems.append(f"{read.objects} objects and {read.items} build items, not one of each")
    row("3mf watertight", "FAIL" if problems else "PASS",
        (f"{shape}; " + "; ".join(problems)) if problems else f"{shape}, every edge shared by two triangles, {how}",
        "closed, manifold, one way round")

    exact = volume(solid)
    if exact <= 0:
        row("3mf volume", "UNCHECKED", "the solid has no volume to compare with", f"within {VOLUME_LIMIT * 100:g} % of the solid's")
    elif got.volume_mm3 <= 0:
        row("3mf volume", "FAIL", f"{got.volume_mm3:.1f} mm^3: the mesh is turned inside out or empty (the solid is {exact:.1f})",
            "positive, and within 0.5 % of the solid's")
    else:
        diff = (got.volume_mm3 - exact) / exact
        row("3mf volume", "PASS" if abs(diff) <= VOLUME_LIMIT else "FAIL",
            f"{got.volume_mm3:.1f} mm^3 against the solid's {exact:.1f}: {diff * 100:+.3f} %",
            f"within {VOLUME_LIMIT * 100:g} % of the solid's")
    return Printed(rows, data, stl, mesh)
