"""[[mass]]: a weight budget over part modules.

The format is in cad_agent/spec.py.
"""
from __future__ import annotations

from ..registry import TOL_MM, spec_kind
from .kit import (Unusable as _Unusable, require as _need, row as _row)


@spec_kind("mass", order=70)
def mass(entry: dict, ctx):
    """The mass of counted part modules against max_g."""
    from .. import state as st
    slug = ctx.slug
    from ..geom import mass_g
    counts = _need(entry, "parts", "[[mass]]")
    limit = float(_need(entry, "max_g", "[[mass]]"))
    if not isinstance(counts, dict) or not counts:
        raise _Unusable("`parts` must map part names to counts, e.g. { x_carriage = 1 }")
    total, lines = 0.0, []
    for name, n in counts.items():
        if name not in st.part_names(slug):
            raise _Unusable(f"no part module {name!r} (parts: {', '.join(st.part_names(slug))})")
        solid, meta = st.build_part(slug, name)
        if not meta["material"]:
            raise _Unusable(f"{name} declares no MATERIAL, so its mass is unknown")
        g = mass_g(solid, meta["material"]) * float(n)
        total += g
        lines.append(f"{name} x{n} {g:.1f} g")
    yield _row(", ".join(counts), "mass", "PASS" if total <= limit + TOL_MM else "FAIL",
               f"{total:.1f} g ({'; '.join(lines)})", f"<= {limit:g} g")
