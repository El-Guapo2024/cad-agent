"""[[heat]]: a hot zone, and whether every body inside it is rated for the heat. A zone, not a thermal model.

    [[heat]]
    source = "hot_plate"      # the body that is hot; or `at = [x, y, z]` for a point (mm)
    temp_c = 250              # what the zone is held at, in degrees C
    radius_mm = 15            # a body is in the zone when its surface is this close to the source's (or the point)
    margin_c = 20             # optional headroom over temp_c; default 0
    clear = ["pcb"]           # optional: bodies that must stay out of the zone whatever they are rated, or "all"

Every other body within `radius_mm` of the source needs a maximum service temperature of at least
`temp_c + margin_c`. The distance is the exact B-rep distance (the way [[clearance]] measures a gap),
with a bounding-box test first so that a body nowhere near costs nothing. The source is exempt: it is what
makes the heat. A body that overlaps the source or the point is at distance 0, so it is inside.

Where a body's rating comes from is bodies.py (BodyInfo.max_temp_c): a made body, the
`max_service_temp_c` of its MATERIAL in materials.py (the basis and the datasheet are in `cad tables
materials`); a bought body, the `max_temp_c` it declares with a `max_temp_source`, else that of its
declared `material`; a stock body, nothing. A rating below `temp_c + margin_c` is a FAIL. A body in the
zone with no rating is UNCHECKED, and the row says why: no MATERIAL, a material the table has no number for,
a bought part that declares none, a stock body. A source that is not a body, a missing `temp_c` or
`radius_mm`, a key this section does not have, are one UNCHECKED row for the entry, like any other kind.

`clear` is [[keepout]]'s `clear` for a hot zone: a body listed there must be outside the zone (farther than
`radius_mm`) however well it is rated, PASS if it is, FAIL if it is not, and it is not also rated. An entry
with no body in its zone gives one PASS row saying so.

What this is not. The zone is a distance, and every body inside it is held to the zone's temperature, as if
the whole sphere sat at it. Nothing conducts, radiates or cools: a body at the edge is judged as hot as one
touching the source, so inside the radius an air gap, an insulating standoff or a heat sink buys nothing
here, and a bracket that really would sit below `temp_c` is held to it all the same. Every row says "a zone,
not a thermal model", and `margin_c` is how a designer asks for headroom the table's numbers do not have
(the service temperature of a thermoplastic is its heat deflection temperature, not a life rating).
"""
from __future__ import annotations

import math

from ..registry import TOL_MM, spec_kind
from .kit import Unusable as _Unusable, get_body as _body, row as _row, vec3 as _vec3

KEYS = ("source", "at", "temp_c", "radius_mm", "margin_c", "clear")
ZONE = "a zone, not a thermal model"


@spec_kind("heat", order=80)
def heat(entry: dict, ctx):
    """Whether every body in a hot zone is rated for its temperature (a zone, not a thermal model)."""
    from build123d import Vertex
    from ..geom import BOX_MARGIN_MM, apart, box
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        raise _Unusable(f"[[heat]] does not take {', '.join(unknown)} (keys: {', '.join(KEYS)})")
    if "source" in entry and "at" in entry:
        raise _Unusable("[[heat]] takes `source` (a body) or `at` (a point), not both")
    if "source" not in entry and "at" not in entry:
        raise _Unusable("[[heat]] is missing `source` (a body) or `at` (a point)")
    temp = _number(entry, "temp_c")
    if temp <= -273.15:
        raise _Unusable(f"temp_c must be above absolute zero, got {temp:g}")
    radius = _number(entry, "radius_mm", least=0.0)
    margin = _number(entry, "margin_c", least=0.0, default=0.0)

    parts = ctx.parts
    point = None
    if "source" in entry:
        where = entry["source"]
        if not isinstance(where, str):
            raise _Unusable("`source` must name a body")
        shape, exempt = _body(parts, where), {where}
    else:
        point = _vec3(entry["at"], "at")
        shape, exempt, where = Vertex(*point), set(), f"({point[0]:g}, {point[1]:g}, {point[2]:g})"
    clear = _clear(entry.get("clear"), parts, exempt)

    need = temp + margin
    limit = f">= {need:g} C" + (f" ({temp:g} + {margin:g} margin)" if margin else "") + f", {ZONE}"
    infos = ctx.bodies
    zone_box = box(shape)
    inside = 0
    for name in sorted(parts):
        if name in exempt:
            continue
        solid = parts[name]
        solid_box = box(solid)
        if name not in clear and apart(zone_box, solid_box, radius + BOX_MARGIN_MM):
            continue                                    # nowhere near: the exact distance cannot change that
        gap = _distance(shape, point, solid, apart(zone_box, solid_box))
        in_zone = gap <= radius + TOL_MM
        inside += in_zone
        if name in clear:
            yield _row(name, "heat", "FAIL" if in_zone else "PASS",
                       f"{gap:.2f} mm from {where}, " + (f"inside the {radius:g} mm zone" if in_zone
                                                         else f"outside the {radius:g} mm zone"),
                       f"outside {radius:g} mm of {where}, {ZONE}")
            continue
        if not in_zone:
            continue
        info = infos.get(name)
        rating = info.max_temp_c if info is not None else None
        if rating is None:
            yield _row(name, "heat", "UNCHECKED",
                       f"no rated temperature: {_why_unrated(info)}; {gap:.2f} mm from {where}", limit)
        else:
            yield _row(name, "heat", "PASS" if rating >= need - 1e-9 else "FAIL",
                       f"{_rated(info)}, {gap:.2f} mm from {where}", limit)
    if not inside:
        yield _row(f"zone {where}", "heat", "PASS",
                   f"no other body within {radius:g} mm of {where}"
                   + (f" ({len(parts) - len(exempt)} checked)" if len(parts) > len(exempt) else ""), limit)


def _distance(shape, point, solid, boxes_apart: bool) -> float:
    """The exact distance from the zone's source (a solid, or a point) to a body, and 0 when they overlap.

    The kernel measures between surfaces, so a point in the bulk of a plate is 5 mm from it and a part sunk
    into another touches nothing: both are inside the zone, which the volume says. A pair whose boxes are
    apart cannot overlap, so only the others pay for the check.
    """
    from ..geom import intersection_volume, min_distance
    gap = min_distance(shape, solid)
    if gap == 0.0 or boxes_apart:
        return gap
    overlap = solid.is_inside(point) if point is not None else intersection_volume(shape, solid) > 1e-6
    return 0.0 if overlap else gap


def _number(entry: dict, key: str, least: float | None = None, default: float | None = None) -> float:
    if key not in entry:
        if default is not None:
            return default
        raise _Unusable(f"[[heat]] is missing `{key}`")
    v = entry[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise _Unusable(f"{key} must be a number, got {v!r}")
    if least is not None and v < least:
        raise _Unusable(f"{key} must be at least {least:g}, got {v:g}")
    return float(v)


def _clear(value, parts: dict, exempt: set) -> set:
    """The bodies that must stay out of the zone."""
    if value is None:
        return set()
    if value == "all":
        return {n for n in parts if n not in exempt}
    if not (isinstance(value, list) and value and all(isinstance(n, str) for n in value)):
        raise _Unusable('`clear` must be a list of body names, or "all"')
    for name in value:
        _body(parts, name)
    if exempt & set(value):
        raise _Unusable("`clear` names the source itself, which is the zone")
    return set(value)


def _rated(info) -> str:
    """What a body is rated for and where that came from, as BodyInfo.max_temp_source says it."""
    src = info.max_temp_source or ""
    if src.startswith("materials.py "):
        return f"{src[len('materials.py '):].split(': ', 1)[0]} rated {info.max_temp_c:g} C"
    return f"declared {info.max_temp_c:g} C ({src})"


def _why_unrated(info) -> str:
    """Why a body has no rated temperature, from what BodyInfo knows of it."""
    from .. import materials
    if info is None or info.kind == "stock":
        why = ("assembly.py builds it itself, so it has no material and no rating; make it a part module with a "
               "MATERIAL, or a bought part with max_temp_c and max_temp_source")
    elif not info.material and info.kind == "made":
        why = f"its part module {info.part!r} declares no MATERIAL"
    elif info.material and materials.key(info.material) is None:
        why = f"material {info.material!r} is not in materials.py"
    elif info.material:
        why = (f"materials.py has no maximum service temperature for {materials.key(info.material)}"
               + (", and the bought part declares no max_temp_c" if info.kind == "bought" else ""))
    else:
        why = f"bought part {info.part!r} declares neither max_temp_c with a max_temp_source nor a material"
    return why + (f" ({'; '.join(info.notes)})" if info is not None and info.notes else "")
