"""Geometry queries that back the gates. Thin wrappers over OCCT."""
from __future__ import annotations
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp


def _w(shape):
    return shape.wrapped if hasattr(shape, "wrapped") else shape


def min_distance(a, b) -> float:
    """Minimum distance between two solids in mm. 0.0 means touching or overlapping."""
    d = BRepExtrema_DistShapeShape(_w(a), _w(b))
    d.Perform()
    if not d.IsDone():
        raise RuntimeError("distance computation failed")
    return float(d.Value())


def closest_points(a, b):
    """Distance between two shapes and the two points that realise it.

    A failure that names a coordinate can be acted on; one that names an
    anonymous feature index cannot.
    """
    d = BRepExtrema_DistShapeShape(_w(a), _w(b))
    d.Perform()
    if not d.IsDone() or d.NbSolution() < 1:
        raise RuntimeError("distance computation failed")
    p1, p2 = d.PointOnShape1(1), d.PointOnShape2(1)
    return (float(d.Value()),
            (round(p1.X(), 3), round(p1.Y(), 3), round(p1.Z(), 3)),
            (round(p2.X(), 3), round(p2.Y(), 3), round(p2.Z(), 3)))


def intersection_volume(a, b) -> float:
    """Volume of overlap in mm^3. > 0 means the parts interfere."""
    common = BRepAlgoAPI_Common(_w(a), _w(b))
    common.Build()
    if not common.IsDone():
        raise RuntimeError("boolean common failed")
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(common.Shape(), props)
    return abs(float(props.Mass()))


def volume(a) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(_w(a), props)
    return abs(float(props.Mass()))


def bbox(a):
    bb = a.bounding_box() if hasattr(a, "bounding_box") else None
    if bb is None:
        raise TypeError("shape has no bounding_box()")
    return (
        (float(bb.min.X), float(bb.min.Y), float(bb.min.Z)),
        (float(bb.max.X), float(bb.max.Y), float(bb.max.Z)),
    )


DENSITY = {  # g/cm^3
    "aluminium": 2.70,
    "aluminum": 2.70,
    "steel": 7.85,
    "stainless": 8.00,
    "brass": 8.50,
    "copper": 8.96,
    "pla": 1.24,
    "petg": 1.27,
    "abs": 1.04,
    "nylon": 1.14,
    "acrylic": 1.18,
    "fr4": 1.85,
    "polyimide": 1.42,
}


def mass_g(a, material: str) -> float:
    key = material.strip().lower()
    if key not in DENSITY:
        raise KeyError(f"unknown material {material!r}; known: {sorted(DENSITY)}")
    return volume(a) / 1000.0 * DENSITY[key]
