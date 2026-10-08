"""Wall thickness, measured rather than declared.

Until this existed, a part told the DFM gate how thin it was and the gate
believed it. That is the one place the system could not tell a fact from an
assumption, so a mistyped number passed silently.

The method is ray casting against the tessellated solid. Sample points across
the surface, step just inside, and shoot a ray along the inward normal. The
distance to the first exit is the local thickness at that point. Sampling the
whole surface gives a distribution, and its low end is what a process limit
has to be compared against.

The rays are cast by Embree when the optional `embreex` is installed and by
trimesh's own Python caster when it is not. Embree finds the same triangles,
so a design measures the same on either (the distances of 600,000 rays over
the repo's designs agree to 1e-13 mm); it is some thirty times faster.

Two honest limits:

  It is a sample, not a proof. A thin spot smaller than the sample spacing can
  be missed, so raise `samples` when a part has fine features.

  It measures across the solid, so a genuinely thin *part* reads as a thin
  wall. A 0.5 mm shim is 0.5 mm thick and that is correct, not a defect; the
  process limit is what decides whether it matters.

Percentiles matter more than the raw minimum: a single grazing ray at a sharp
edge can return a near-zero distance that describes the tessellation rather
than the part. `p01` is the number to gate on.
"""
from __future__ import annotations

import numpy as np

from .render import tessellate


def _trimesh(solid, tolerance: float, embree: bool = True):
    import trimesh
    m = tessellate(solid, tolerance, 0.2)
    return trimesh.Trimesh(vertices=m.verts, faces=m.tris, process=True, use_embree=embree)


def _first_hits(mesh, origins, directions):
    """Where each ray first meets the mesh: (locations, index_ray, index_tri).

    A fault inside Embree is no fault of the part, so the rays are cast again on the Python
    caster rather than failing the rule.
    """
    from trimesh.ray import ray_triangle
    try:
        return mesh.ray.intersects_location(origins, directions, multiple_hits=False)
    except Exception:
        if isinstance(mesh.ray, ray_triangle.RayMeshIntersector):
            raise
        return ray_triangle.RayMeshIntersector(mesh).intersects_location(
            origins, directions, multiple_hits=False)


def thickness_samples(solid, samples: int = 4000, tolerance: float = 0.1,
                      seed: int = 0, embree: bool = True) -> np.ndarray:
    """Local thickness at points across the surface, in mm.

    Deterministic for a given seed, so a rebuild that changes nothing reports
    the same numbers and a changed number means the geometry changed. `embree`
    False casts the rays on the Python caster even where Embree is installed.
    """
    import trimesh

    mesh = _trimesh(solid, tolerance, embree)
    if mesh.faces.shape[0] == 0:
        return np.array([])

    rng = np.random.default_rng(seed)
    points, face_idx = trimesh.sample.sample_surface(mesh, samples, seed=seed)
    normals = mesh.face_normals[face_idx]

    # Step inside by a hair so the ray does not re-hit its own starting face.
    eps = max(mesh.scale * 1e-6, 1e-9)
    origins = points - normals * eps
    directions = -normals

    locations, index_ray, _ = _first_hits(mesh, origins, directions)
    if len(index_ray) == 0:
        return np.array([])
    dist = np.linalg.norm(locations - origins[index_ray], axis=1)
    return dist[dist > eps * 10]


def measure_min_wall(solid, samples: int = 4000, tolerance: float = 0.1,
                     seed: int = 0) -> dict:
    """Thickness statistics for the DFM gate to compare against a limit."""
    d = thickness_samples(solid, samples, tolerance, seed)
    if len(d) == 0:
        return {
            "state": "UNMEASURABLE",
            "note": ("no inward ray found an exit; the solid may be open, "
                     "inside out, or too coarsely tessellated"),
            "samples": 0,
        }
    return {
        "state": "MEASURED",
        "samples": int(len(d)),
        "min_mm": round(float(d.min()), 4),
        "p01_mm": round(float(np.percentile(d, 1)), 4),
        "p05_mm": round(float(np.percentile(d, 5)), 4),
        "median_mm": round(float(np.median(d)), 4),
        "max_mm": round(float(d.max()), 4),
        "note": ("p01 is the gating figure; the bare minimum can reflect a "
                 "grazing ray at an edge rather than the part"),
    }
