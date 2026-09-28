"""Exports. STEP for a machine shop, STL for printing, DXF for laser cutting."""
from __future__ import annotations
from pathlib import Path
from build123d import export_step, export_stl
from .state import project_dir, build_part


def export_part(slug: str, name: str, fmt: str = "step") -> Path:
    solid, _ = build_part(slug, name)
    out = project_dir(slug) / "out"
    out.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "step":
        p = out / f"{name}.step"
        export_step(solid, str(p))
    elif fmt == "stl":
        p = out / f"{name}.stl"
        export_stl(solid, str(p))
    else:
        raise ValueError(f"unsupported format {fmt!r}; use step or stl")
    return p
