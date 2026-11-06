# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of what FreeCAD 3160daf1e2b6's FEM constraints compute in C++ (src/Mod/Fem/App/FemConstraint.cpp,
# FemConstraintForce.cpp: Copyright (c) 2013 Jan Rheinländer; FemTools.cpp: Copyright (c) 2015 Werner Mayer).
"""Fem::Constraint's onChanged for the stand-ins: a new References gives NormalDirection (the first face's normal at
its parametric centre); a ConstraintForce's Direction and Reversed give DirectionVector (getDirection: a planar face's
normal or a linear edge's direction, of the global shape)."""
from __future__ import annotations

from . import _fc_base as B

CONFUSION = 1e-7


def on_changed(obj, prop):
    if not obj.isDerivedFrom("Fem::Constraint"):
        return
    if prop == "References":
        _normal(obj)
    if obj.isDerivedFrom("Fem::ConstraintForce"):
        _force(obj, prop)


def _sub_shape(feat, sub):
    """Tools::getFeatureSubShape: the feature's shape's sub-element, placed (the stand-in's shapes carry it)."""
    try:
        s = feat.Shape.getElement(sub) if sub else feat.Shape
    except Exception:  # noqa: BLE001 - FreeCAD's returns a null shape
        return None
    return getattr(s, "_s", None)


def _normal(obj):
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt, gp_Vec
    for o, sub in obj._props["References"].value or []:
        if not hasattr(o, "Shape"):
            continue
        sh = _sub_shape(o, sub)
        if sh is not None and not sh.IsNull() and sh.ShapeType() == TopAbs_FACE:
            props = BRepGProp_Face(TopoDS.Face(sh))
            u1, u2, v1, v2 = props.Bounds()
            n, c = gp_Vec(), gp_Pnt()
            props.Normal((u1 + u2) / 2.0, (v1 + v2) / 2.0, c, n)
            n.Normalize()
            obj._props["NormalDirection"].value = B.Vector(n.X(), n.Y(), n.Z())
            break


def get_direction(link):
    """Constraint::getDirection: a datum's Z, else a Part feature's sub-element's direction (getDirectionFromShape)."""
    if not link:
        return B.Vector(0, 0, 0)
    o, subs = link if isinstance(link, tuple) else (link, [])
    if isinstance(subs, str):
        subs = [subs]
    if o.isDerivedFrom("App::DatumElement") or o.isDerivedFrom("Part::Datum"):
        return o.Placement.Rotation.multVec(B.Vector(0, 0, 1))
    if not o.isDerivedFrom("Part::Feature"):
        raise TypeError("Type is not a line, plane or Part object")
    if not subs:
        return B.Vector(0, 0, 0)
    sh = _sub_shape(o, subs[0])
    if sh is None or sh.IsNull():
        return B.Vector(0, 0, 0)
    return B.Vector(*_direction_from_shape(sh))


def _direction_from_shape(sh):
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Plane
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopoDS import TopoDS
    if sh.ShapeType() == TopAbs_FACE:
        s = BRepAdaptor_Surface(TopoDS.Face(sh))
        if s.GetType() == GeomAbs_Plane:
            d = s.Plane().Axis().Direction()
            return d.X(), d.Y(), d.Z()
    elif sh.ShapeType() == TopAbs_EDGE:
        c = BRepAdaptor_Curve(TopoDS.Edge(sh))
        if c.GetType() == GeomAbs_Line:
            d = c.Line().Direction()
            return d.X(), d.Y(), d.Z()
    # FemTools' B-spline and Bezier planes and lines (from their poles) are not ported: (0, 0, 0), no direction
    return 0.0, 0.0, 0.0


def _force(obj, prop):
    """ConstraintForce::onChanged."""
    d = obj.__dict__
    if prop == "Direction":
        direction = get_direction(obj._props["Direction"].value)
        if direction.Length < CONFUSION:
            return
        d["_natural"] = B.Vector(direction)
        if obj._props["Reversed"].value:
            direction = -direction
        obj._props["DirectionVector"].value = direction
    elif prop == "Reversed":
        nat = d.get("_natural", B.Vector(0, 0, 0))
        if nat.Length < CONFUSION:
            nat = get_direction(obj._props["Direction"].value)
            d["_natural"] = nat
        if nat.Length >= CONFUSION:
            cur = obj._props["DirectionVector"].value
            if obj._props["Reversed"].value and cur == nat:
                obj._props["DirectionVector"].value = -nat
            elif not obj._props["Reversed"].value and cur != nat:
                obj._props["DirectionVector"].value = B.Vector(nat)
