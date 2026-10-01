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


def mass_properties(items) -> dict:
    """FreeCAD's Mass Properties (Measure/App/MassPropertiesResult.cpp) for solids
    with densities in kg/mm^3: volume and surface area, mass, centres of gravity and
    volume, the inertia matrix at the centre of gravity, and its principal moments
    and axes. Units are FreeCAD's: mm, kg, kg*mm^2."""
    from OCP.GProp import GProp_PrincipalProps
    mass_p, surf_p, vol_p = GProp_GProps(), GProp_GProps(), GProp_GProps()
    total_volume, any_shape = 0.0, False
    for shape, density in items:
        v, s = GProp_GProps(), GProp_GProps()
        BRepGProp.VolumeProperties_s(_w(shape), v)
        vol_p.Add(v)
        BRepGProp.SurfaceProperties_s(_w(shape), s)
        total_volume += v.Mass()
        mass_p.Add(v, density)
        surf_p.Add(s)
        any_shape = True
    if not any_shape:
        return {}
    mass = mass_p.Mass()
    cog, cov = mass_p.CentreOfMass(), vol_p.CentreOfMass()
    m = mass_p.MatrixOfInertia()
    inertia = [[m.Value(r, c) for c in (1, 2, 3)] for r in (1, 2, 3)]
    pr = mass_p.PrincipalProperties()

    def unit(v):
        n = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5 or 1.0
        return [v[0] / n, v[1] / n, v[2] / n]

    def cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    if pr.HasSymmetryPoint():
        a1, a2, a3 = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
    elif pr.HasSymmetryAxis():
        f = pr.FirstAxisOfInertia()
        a3 = unit([f.X(), f.Y(), f.Z()])
        ref = [0.0, 1.0, 0.0] if abs(a3[2]) > 0.9 else [0.0, 0.0, 1.0]
        a1 = unit(cross(ref, a3))
        a2 = unit(cross(a3, a1))
    else:
        f, g = pr.FirstAxisOfInertia(), pr.SecondAxisOfInertia()
        a3, a1 = unit([f.X(), f.Y(), f.Z()]), unit([g.X(), g.Y(), g.Z()])
        a2 = cross(a3, a1)

    def moment(u):
        return sum(u[r] * sum(inertia[r][c] * u[c] for c in range(3)) for r in range(3))

    return {
        "volume_mm3": total_volume, "mass_kg": mass, "surface_area_mm2": surf_p.Mass(),
        "density_kg_mm3": mass / total_volume if total_volume > 0 else None,
        "cog": [cog.X(), cog.Y(), cog.Z()], "cov": [cov.X(), cov.Y(), cov.Z()],
        "inertia_kg_mm2": inertia,
        "principal_moments": [moment(a1), moment(a2), moment(a3)],
        "principal_axes": [a1, a2, a3],
    }
