"""shop: a laser part is a through-cut its DXF reads back to, and a printed part's 3MF is the solid.

The rules of a part that is going to a shop (step 6, piece D). They are the ones `cad shop` runs on what it is about to
write, so a design that passes here is one whose files will pass there:

  laser_cut   `shop/laser through-cut`  every face is an end plane or runs along the thickness: a pocket, a step, a
                                        chamfer, a countersink, a draft or a cross hole is a FAIL (dxf.py)
              `shop/dxf readback`       the DXF, read back by ezdxf, is the mid-plane section within 0.001 mm, entity
                                        for entity and in millimetres
  fdm         `shop/3mf watertight`     the 3MF, read back by lib3mf (or the built-in reader where lib3mf is not
                                        installed), is closed, manifold and wound one way round
              `shop/3mf volume`         its volume is the solid's within 0.5 %

Anything that cannot be measured is UNCHECKED, never PASS. A part with another process (cnc, or none) has no row here.

Opt-in. Writing a DXF and reading it back costs a few hundred milliseconds and a 3MF up to a second or two, and a
design that never goes to a shop should not pay it or be held to it, so the rule is silent unless the project's
spec.toml has a `[shop]` table (speckinds/shop.py). `cad check`, the edit loop's `cad check --part` and `cad verify`
all run it from then on.
"""
from __future__ import annotations

from ..registry import register


@register(scope="part", name="shop", order=70)
def shop(ctx):
    """A laser part is a through-cut its DXF reads back to; a printed part's 3MF is closed and the solid's volume (with [shop])."""
    from ..shop import shop_spec
    if shop_spec(ctx.slug) is None:
        return
    process = ctx.meta.get("process")
    if process == "laser_cut":
        from ..dxf import laser_rows
        yield from laser_rows(ctx.name, ctx.solid).rows
    elif process == "fdm":
        from ..threemf import print_rows
        yield from print_rows(ctx.name, ctx.solid).rows
