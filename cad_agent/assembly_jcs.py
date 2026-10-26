# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's src/Mod/Assembly/UtilsAssembly.py (Copyright (c) 2023 Ondsel
# <development@ondsel.com>): findPlacement, findElementClosestVertex and the JCS helpers JointObject.py
# uses (getJcsGlobalPlc, flipPlacement, arePlacementSameDir, arePlacementZParallel,
# applyRotationToPlacementAlongAxis, getJointDistance, getJointXYAngle), and of what
# src/Mod/Assembly/App/AssemblyUtils.cpp reads off an element (its BRepAdaptor type, getFaceRadius,
# getEdgeRadius). Part's Python accessors these use are Part's own code: Edge.Curve and Face.Surface
# (TopoShapeEdgePyImp.cpp, TopoShapeFacePyImp.cpp: the BRepAdaptor's gp primitive), Curve.Rotation and
# Surface.Rotation (GeometryCurvePyImp.cpp, GeometrySurfacePyImp.cpp: gp_Trsf::SetTransformation(Position,
# gp_Ax3()).GetRotation()), CenterOfGravity (TopoShape::getCenterOfGravity), Vector.projectToLine
# (Base/Vector3D.cpp).
"""Joint coordinate systems: where a joint's Placement1/2 sit on the element its reference names.

A component's shape is the part's shape at the origin and its Placement where the assembly puts it; FreeCAD's
findPlacement works on the link's shape, which is the part's shape moved by the link's Placement, and takes that
placement off at the end, so the JCS is in the component's own frame. This module does the same, on the same
OpenCascade calls, so the numbers are FreeCAD's.
"""
from __future__ import annotations

import math

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import (GeomAbs_BSplineCurve, GeomAbs_Circle, GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Ellipse,
                         GeomAbs_Line, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus)
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

from .attacher import Placement, Rotation
from .feature import _subs
from .feature_attach import sub_shape

CURVES = {GeomAbs_Line: "Line", GeomAbs_Circle: "Circle", GeomAbs_Ellipse: "Ellipse",
          GeomAbs_BSplineCurve: "BSplineCurve"}
SURFACES = {GeomAbs_Plane: "Plane", GeomAbs_Cylinder: "Cylinder", GeomAbs_Cone: "Cone", GeomAbs_Sphere: "Sphere",
            GeomAbs_Torus: "Torus"}


# ── Part's accessors ────────────────────────────────────────────────────────────────────────────────────

def _rot_of_ax3(ax3: gp_Ax3) -> Rotation:
    """Curve.Rotation / Surface.Rotation: gp_Trsf::SetTransformation(position, gp_Ax3()).GetRotation()."""
    t = gp_Trsf()
    t.SetTransformation(ax3, gp_Ax3())
    q = t.GetRotation()
    return Rotation((q.X(), q.Y(), q.Z(), q.W()))


def _xyz(p):
    return (p.X(), p.Y(), p.Z())


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def project_to_line(point, line):
    """Base::Vector3::ProjectToLine (Vector().projectToLine(point, line)): the vector from point to its foot on
    the line through the origin along line."""
    k = _dot(point, line) / _dot(line, line)
    return (k * line[0] - point[0], k * line[1] - point[1], k * line[2] - point[2])


def curve(edge) -> dict:
    """Edge.Curve, as far as the Assembly reads it: {"type", "location", "rotation", "direction", "radius"}."""
    a = BRepAdaptor_Curve(TopoDS.Edge(edge))
    t = a.GetType()
    out = {"type": CURVES.get(t, "Other")}
    if t == GeomAbs_Circle:
        c = a.Circle()
        out.update(location=_xyz(c.Location()), rotation=_rot_of_ax3(gp_Ax3(c.Position())), radius=c.Radius())
    elif t == GeomAbs_Line:
        out["direction"] = _xyz(a.Line().Direction())
    elif t == GeomAbs_Ellipse:
        e = a.Ellipse()
        out.update(location=_xyz(e.Location()), rotation=_rot_of_ax3(gp_Ax3(e.Position())))
    return out


def surface(face) -> dict:
    """Face.Surface, as far as the Assembly reads it: {"type", "rotation", "center", "axis", "apex", "radius"}."""
    a = BRepAdaptor_Surface(TopoDS.Face(face))
    t = a.GetType()
    out = {"type": SURFACES.get(t, "Other")}
    if t == GeomAbs_Plane:
        p = a.Plane()
        out.update(rotation=_rot_of_ax3(gp_Ax3(p.Position().Ax2())))
    elif t == GeomAbs_Cylinder:
        c = a.Cylinder()
        pos = c.Position()
        out.update(rotation=_rot_of_ax3(gp_Ax3(pos.Ax2())), center=_xyz(pos.Location()),
                   axis=_xyz(pos.Direction()), radius=c.Radius())
    elif t == GeomAbs_Cone:
        c = a.Cone()
        pos = c.Position()
        out.update(rotation=_rot_of_ax3(gp_Ax3(pos.Ax2())), center=_xyz(pos.Location()),
                   axis=_xyz(pos.Direction()), apex=_xyz(c.Apex()))
    elif t == GeomAbs_Sphere:
        s = a.Sphere()
        pos = s.Position()
        out.update(rotation=_rot_of_ax3(gp_Ax3(pos.Ax2())), center=_xyz(pos.Location()), radius=s.Radius())
    elif t == GeomAbs_Torus:
        s = a.Torus()
        pos = s.Position()
        out.update(rotation=_rot_of_ax3(gp_Ax3(pos.Ax2())), center=_xyz(pos.Location()))
    return out


def center_of_gravity(shape):
    """TopoShape::getCenterOfGravity: volume, else surface, else linear properties' centre of mass."""
    prop = GProp_GProps()
    if TopExp_Explorer(shape, TopAbs_SOLID).More():
        BRepGProp.VolumeProperties_s(shape, prop)
    elif TopExp_Explorer(shape, TopAbs_FACE).More():
        BRepGProp.SurfaceProperties_s(shape, prop)
    elif TopExp_Explorer(shape, TopAbs_EDGE).More():
        BRepGProp.LinearProperties_s(shape, prop)
    else:
        pts = []
        ex = TopExp_Explorer(shape, TopAbs_VERTEX)
        while ex.More():
            pts.append(_xyz(BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))))
            ex.Next()
        n = len(pts)
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)
    return _xyz(prop.CentreOfMass())


def vertex_point(v):
    return _xyz(BRep_Tool.Pnt_s(TopoDS.Vertex(v)))


def _vertexes(shape) -> list:
    """TopoShape.Vertexes: TopExp::MapShapes order."""
    return _subs(shape, TopAbs_VERTEX)


def _sub_list(shape, kind) -> list:
    return _subs(shape, kind)


def plane_rotation(normal) -> Rotation:
    """Part.Plane(App.Vector(0, 0, 0), normal).Rotation."""
    pln = gp_Pln(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(*normal))
    return _rot_of_ax3(gp_Ax3(pln.Position().Ax2()))


def round_vector(v, decimals=10):
    return (round(v[0], decimals), round(v[1], decimals), round(v[2], decimals))


def placed(shape, plc: Placement):
    """The link's shape: the part's shape moved by the component's Placement."""
    return shape.Moved(TopLoc_Location(plc.trsf()))


# ── UtilsAssembly ───────────────────────────────────────────────────────────────────────────────────────

def element_name(full_name: str) -> str:
    """getElementName: the last name of a sub-name ("" for a datum's X, Y, Z, Point, Line, Plane)."""
    parts = full_name.split(".")
    if parts[-1] in {"X", "Y", "Z", "Point", "Line", "Plane"}:
        return ""
    return parts[-1]


def extract_type_and_number(name: str):
    t, n = "", ""
    for ch in name:
        if ch.isalpha():
            t += ch
        elif ch.isdigit():
            n += ch
        else:
            break
    if t and n:
        return t, int(n)
    return None, None


def is_ref_valid(ref, number_sub: int) -> bool:
    if ref is None or len(ref) != 2 or ref[0] is None:
        return False
    if len(ref[1]) < number_sub:
        return False
    return ref[1][0].find("?") == -1


def find_placement(shape, comp_plc: Placement, subs, ignore_vertex: bool = False) -> Placement:
    """UtilsAssembly.findPlacement(ref, ignoreVertex): the JCS on the element subs[0] at the vertex subs[1] of a
    component whose part's shape is shape and whose Placement is comp_plc, relative to the component."""
    if len(subs) < 2:
        return Placement()
    elt = element_name(subs[0])
    vtx = element_name(subs[1])
    if not elt or not vtx:
        return Placement()

    obj_shape = placed(shape, comp_plc)
    pos = (0.0, 0.0, 0.0)
    rot = Rotation()

    elt_type, elt_index = extract_type_and_number(elt)
    vtx_type, _ = extract_type_and_number(vtx)
    is_line = False

    def get(name, within=None):
        try:
            return sub_shape(within if within is not None else obj_shape, name)
        except Exception:
            return None

    if elt_type == "Vertex":
        vertex = get(elt)
        if vertex is None:
            return Placement()
        pos = vertex_point(vertex)
    elif elt_type == "Edge":
        edge = get(elt)
        if edge is None:
            return Placement()
        c = curve(edge)
        if vtx_type == "Edge" or ignore_vertex:
            if c["type"] == "Circle":
                pos = c["location"]
            elif c["type"] == "Line":
                pts = [vertex_point(v) for v in _vertexes(edge)]
                pos = tuple((pts[0][k] + pts[1][k]) * 0.5 for k in range(3))
        else:
            vertex = get(vtx)
            if vertex is None:
                return Placement()
            pos = vertex_point(vertex)
        if c["type"] == "Circle":
            rot = c["rotation"]
        if c["type"] == "Line":
            is_line = True
            rot = plane_rotation(round_vector(c["direction"]))
    elif elt_type == "Face":
        face = get(elt)
        if face is None:
            return Placement()
        s = surface(face)
        if vtx_type == "Face" or ignore_vertex:
            if s["type"] == "Cylinder":
                g = _sub(center_of_gravity(face), s["center"])
                center = _add(s["center"], g)
                pos = _add(center, project_to_line(g, s["axis"]))
            elif s["type"] in ("Torus", "Sphere"):
                pos = s["center"]
            elif s["type"] == "Cone":
                pos = s["apex"]
            else:
                pos = center_of_gravity(face)
        elif vtx_type == "Edge":
            edge = get(vtx, face)
            if edge is None:
                return Placement()
            c = curve(edge)
            if c["type"] == "Circle":
                pos = c["location"]
            elif s["type"] == "Cylinder" and c["type"] == "BSplineCurve":
                raise NotImplementedError("the JCS at the intersection of two cylinders (findCylindersIntersection) "
                                          "is not ported")
        else:
            vertex = get(vtx)
            if vertex is None:
                return Placement()
            pos = vertex_point(vertex)
        if "rotation" in s:
            rot = s["rotation"]

    plc = Placement(pos, rot)
    plc = comp_plc.inverse() * plc

    if elt_type == "Vertex":
        plc = Placement(plc.pos, Rotation())
    elif is_line:
        normal = round_vector(plc.rot.mult_vec((0.0, 0.0, 1.0)))
        plc = Placement(plc.pos, plane_rotation(normal))
    return plc


def find_element_closest_vertex(shape, comp_plc: Placement, element: str, mouse) -> str:
    """UtilsAssembly.findElementClosestVertex(ref, mousePos): the vertex (or the element itself, for a centre)
    nearest the picked point, a global point."""
    name = element_name(element)
    if name == "":
        return ""
    # the point in the object's frame: FreeCAD takes global_plc.inverse() and then obj.Placement, which for a
    # component that is its own object leave it where it is
    p = Placement(tuple(mouse))
    p = comp_plc.inverse() * p
    p = comp_plc * p
    mouse = p.pos
    obj_shape = placed(shape, comp_plc)

    elt_type, elt_index = extract_type_and_number(name)
    if elt_type == "Vertex":
        return name

    def closest(points):
        best, dmin = None, None
        for i, q in enumerate(points):
            d = _len(_sub(mouse, q))
            if best is None or d < dmin:
                best, dmin = i, d
        return best, dmin

    def vertex_name_in_obj(v):
        pt = vertex_point(v)
        for i, w in enumerate(_vertexes(obj_shape)):
            if vertex_point(w) == pt:
                return f"Vertex{i + 1}"
        return ""

    if elt_type == "Edge":
        edge = sub_shape(obj_shape, name)
        c = curve(edge)
        if c["type"] == "Circle":
            return name
        verts = _vertexes(edge)
        pts = [vertex_point(v) for v in verts]
        if c["type"] == "Line":
            pts.append(tuple((pts[0][k] + pts[1][k]) * 0.5 for k in range(3)))
        i, _ = closest(pts)
        if c["type"] == "Line" and i == 2:
            return name
        return vertex_name_in_obj(verts[i])

    if elt_type == "Face":
        face = sub_shape(obj_shape, name)
        s = surface(face)
        if s["type"] in ("Sphere", "Torus"):
            return name
        centers, center_edges = [], []
        for i, e in enumerate(_sub_list(face, TopAbs_EDGE)):
            c = curve(e)
            if c["type"] in ("Circle", "Ellipse"):
                centers.append(c["location"])
                center_edges.append(i)
        if centers:
            ci, cd = closest(centers)
        face_verts = _vertexes(face)
        pts = []
        if s["type"] not in ("Cylinder", "Cone"):
            pts = [vertex_point(v) for v in face_verts]
        if s["type"] in ("Cylinder", "Cone"):
            g = _sub(center_of_gravity(face), s["center"])
            center = _add(s["center"], g)
            pts.append(_add(center, project_to_line(g, s["axis"])))
        else:
            pts.append(center_of_gravity(face))
        vi, vd = closest(pts)
        if centers and cd < vd:
            return f"Edge{center_edges[ci] + 1}"
        if s["type"] in ("Cylinder", "Cone"):
            return name
        if vi == len(face_verts):
            return name
        return vertex_name_in_obj(face_verts[vi])
    return ""


def element_geometry(shape, element: str) -> dict:
    """What AssemblyUtils.cpp reads off a reference's element: {"geom": its BRepAdaptor type, "radius":
    getFaceRadius / getEdgeRadius}. The solver (ui/ondsel/api.cpp) takes these with each reference."""
    name = element_name(element) if element else ""
    t, _ = extract_type_and_number(name) if name else (None, None)
    try:
        if t == "Face":
            s = surface(sub_shape(shape, name))
            return {"geom": s["type"], "radius": s.get("radius", 0.0) if s["type"] in ("Cylinder", "Sphere") else 0.0}
        if t == "Edge":
            c = curve(sub_shape(shape, name))
            return {"geom": c["type"], "radius": c.get("radius", 0.0) if c["type"] == "Circle" else 0.0}
    except Exception:
        pass
    return {"geom": "", "radius": 0.0}


def jcs_global(jcs: Placement, comp_plc: Placement) -> Placement:
    """getJcsGlobalPlc(jcsPlc, ref): the component's global placement times the JCS."""
    return comp_plc * jcs


def rotate_along_axis(plc: Placement, angle_deg: float, axis) -> Placement:
    """applyRotationToPlacementAlongAxis: plc.Rotation * App.Rotation(axis, angle) (degrees)."""
    return Placement(plc.pos, plc.rot * Rotation.from_axis_angle(axis, math.radians(angle_deg)))


def flip_placement(plc: Placement) -> Placement:
    return rotate_along_axis(plc, 180, (1.0, 0.0, 0.0))


def same_dir(plc1: Placement, plc2: Placement) -> bool:
    z1 = plc1.rot.mult_vec((0.0, 0.0, 1.0))
    z2 = plc2.rot.mult_vec((0.0, 0.0, 1.0))
    return _dot(z1, z2) > 0


def z_parallel(plc1: Placement, plc2: Placement) -> bool:
    z1 = plc1.rot.mult_vec((0.0, 0.0, 1.0))
    z2 = plc2.rot.mult_vec((0.0, 0.0, 1.0))
    c = (z1[1] * z2[2] - z1[2] * z2[1], z1[2] * z2[0] - z1[0] * z2[2], z1[0] * z2[1] - z1[1] * z2[0])
    return _len(c) < 1e-06


def joint_distance(plc1: Placement, plc2: Placement) -> float:
    """getJointDistance: the signed distance between the two global JCS (the sign of plc2's z in plc1)."""
    plc3 = plc1.inverse() * plc2
    sign = -1 if plc3.pos[2] < 0 else 1
    return sign * _len(_sub(plc1.pos, plc2.pos))


def joint_xy_angle(plc1: Placement, plc2: Placement) -> float:
    """getJointXYAngle, radians."""
    plc3 = plc1.inverse() * plc2
    x = plc3.rot.mult_vec((1.0, 0.0, 0.0))
    return math.atan2(x[1], x[0])
