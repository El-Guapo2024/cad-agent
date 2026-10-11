"""[[deflection]]: a body held as a beam, and the most it may sag under a load.

    [[deflection]]
    body = "gantry_beam"     # a placed body with exact geometry: a part module, or a bought part that says so
    support = "simple"       # simple (pinned at both ends), fixed (clamped at both) or cantilever (clamped at one)
    span_mm = 400            # between the supports; default the body's length along its axis
    load_g = 350             # one of load_n (newtons), load_g (a mass hung on it, in grams) or
                             # load_moving = "y" (the mass that axis y moves); self_weight alone is a load too
    at = "worst"             # center, end (a cantilever's free end) or worst (the default): where the load acts
    self_weight = true       # also its own weight, spread over the span
    max_um = 50              # the most it may deflect, in micrometres
    direction = "-z"         # which way the load pushes: x, y or z, a sign allowed and ignored; default gravity
    axis = "x"               # which way the beam runs, when the body is not clearly longest along one

The method and its limits are in cad_agent/beam.py: Euler-Bernoulli superposition from Roark's Table 8.1, the
second moment of area read from the body's own cross-sections (the weakest of 21 and of the places its shape
changes), Young's modulus from materials.py with the source it cites. A beam is a formula and not a finite-element
model, so the rule says UNCHECKED, with its reason, wherever the formula would not hold, and never a guess:

  * the body's geometry is an envelope: stock that assembly.py builds (extrusion_blank is a box, not a profile),
    or a bought part not declared `geometry = "exact"`, or one whose dimensions are unverified;
  * the body has no material, or materials.py has no Young's modulus with a source for it;
  * a mass it needs is unknown: `load_moving` adds up the masses of the bodies the axis moves (the beam itself
    left out: `self_weight` is its own) and `self_weight` uses the body's, each as bodies.py gives them (a
    made part's volume x density, a bought part's declared mass with its source);
  * the body is not a beam: not one solid, not clearly longest along one axis, a long edge tilted or bent, a
    section cut through or in pieces over a long run (see beam.profile);
  * span/depth is under 10 (20 for fixed ends, whose shear is four times a simple beam's): shear then matters
    and Euler-Bernoulli leaves it out;
  * the section varies so much that the verdict depends on which section stands for the beam: the weakest one
    gives the deflection it could not exceed, the stiffest one the least it could have, and a limit between the
    two is UNCHECKED. There is no ratio to tune: a limit above the weakest section's deflection passes and one
    below the stiffest section's fails, however much the section varies.

A malformed entry is UNCHECKED as for every section: a missing or unknown key (a typo in `self_weight` would
quietly drop the weight), a bad value, a load of more than one kind, an axis or a body that is not there. The
row's measured text carries the deflection, where it is, the load, the second moment, E with its source and
span/depth; its limit is `<= max_um um`.

The load is taken through the section's centre: no twist, so an open section such as a channel or an angle is
better judged some other way. Loads in one plane add; a load across gravity (`direction`) with `self_weight`
is two planes, and their deflections are combined as vectors.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import beam, materials
from ..registry import TOL_MM, spec_kind
from .kit import Unusable as _Unusable, get_body as _body, require as _need, row as _row

KEYS = ("body", "support", "span_mm", "load_n", "load_g", "load_moving", "at", "self_weight", "max_um",
        "direction", "axis")
LOADS = ("load_n", "load_g", "load_moving")
GRAVITY_AXIS = 2                                         # z: the weight of the body acts along it


class _Cannot(Exception):
    """The rule cannot judge this body, and why: one UNCHECKED row that carries it."""


@dataclass(frozen=True)
class _Request:
    body: str
    support: str
    span: float | None
    load_n: float | None
    load_g: float | None
    moving: str | None
    at: str
    self_weight: bool
    max_um: float
    direction: int
    axis: int | None

    @property
    def limit(self) -> str:
        return f"<= {self.max_um:g} um"


@dataclass(frozen=True)
class _Plane:
    """One plane of bending: the load in it, the weakest and the stiffest second moment, and the deflection each gives."""
    axis: int
    i_min: float
    i_max: float
    point_n: float
    udl_n: float
    weak: beam.Deflection
    stiff: beam.Deflection


@spec_kind("deflection", order=80)
def deflection(entry: dict, ctx):
    """One body held as a beam: its bending deflection against max_um (Euler-Bernoulli, Roark's Table 8.1)."""
    request = _read(entry)
    solid = _body(ctx.parts, request.body)
    try:
        row = _judge(request, solid, ctx)
    except (_Cannot, beam.NotABeam) as e:
        row = _row(request.body, "deflection", "UNCHECKED", str(e), request.limit)
    yield row


# ─── The entry ───────────────────────────────────────────────────────────────

def _read(entry: dict) -> _Request:
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        raise _Unusable(f"[[deflection]] has no key `{unknown[0]}` (keys: {', '.join(KEYS)})")
    body = _need(entry, "body", "[[deflection]]")
    if not isinstance(body, str):
        raise _Unusable("[[deflection]] `body` must be the name of a body")
    support, at = _need(entry, "support", "[[deflection]]"), entry.get("at", "worst")
    try:
        beam.place_of(support, at)
    except ValueError as e:
        raise _Unusable(f"[[deflection]] {e}") from None
    _need(entry, "max_um", "[[deflection]]")
    given = [k for k in LOADS if k in entry]
    if len(given) > 1:
        raise _Unusable(f"[[deflection]] takes one load, not {' and '.join(given)}")
    self_weight = entry.get("self_weight", False)
    if not isinstance(self_weight, bool):
        raise _Unusable(f"[[deflection]] `self_weight` must be true or false, not {self_weight!r}")
    if not given and not self_weight:
        raise _Unusable("[[deflection]] has no load: give load_n, load_g or load_moving, or self_weight = true")
    moving = entry.get("load_moving")
    if "load_moving" in entry and not (isinstance(moving, str) and moving):
        raise _Unusable("[[deflection]] `load_moving` must be the name of an axis")
    return _Request(
        body=body, support=support, span=_number(entry, "span_mm") if "span_mm" in entry else None,
        load_n=_number(entry, "load_n") if "load_n" in entry else None,
        load_g=_number(entry, "load_g") if "load_g" in entry else None,
        moving=moving, at=at, self_weight=self_weight, max_um=_number(entry, "max_um"),
        direction=_axis(entry.get("direction", "-z"), "direction"),
        axis=_axis(entry["axis"], "axis") if "axis" in entry else None)


def _number(entry: dict, key: str) -> float:
    v = entry[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise _Unusable(f"[[deflection]] `{key}` must be a positive number, not {v!r}")
    return float(v)


def _axis(value, key: str) -> int:
    text = value.strip().lower().lstrip("+-") if isinstance(value, str) else ""
    if text not in ("x", "y", "z"):
        raise _Unusable(f"[[deflection]] `{key}` must be x, y or z (a sign is allowed on `direction`), not {value!r}")
    return "xyz".index(text)


# ─── The judgement ───────────────────────────────────────────────────────────

def _judge(r: _Request, solid, ctx):
    bodies = ctx.bodies
    info = bodies.get(r.body)
    if info is None:
        raise _Cannot(f"nothing describes {r.body} (bodies.describe has no entry for it)")
    if info.geometry != "exact":
        raise _Cannot(_envelope(info))
    if not info.verified:
        raise _Cannot(f"{r.body} is a bought part whose dimensions are unverified (VERIFIED = False): a section "
                      "read from them is a claim and not a measurement")
    modulus = _modulus(info)
    point = _point(r, ctx, bodies)
    weight = _own_weight(r, info)
    prof = _profile(ctx, r, solid)
    span = r.span if r.span is not None else prof.length
    if span > prof.length + TOL_MM:
        raise _Unusable(f"[[deflection]] `span_mm` {span:g} is longer than the body ({prof.length:.2f} mm)")
    if r.direction == prof.axis:
        raise _Cannot(f"the load acts along {'xyz'[r.direction]}, the beam's own axis: that is compression and not "
                      "bending (say which way it pushes across the beam with `direction`)")
    planes: dict = {}                                    # the axis a load acts along -> [newtons at a point, spread]
    if point is not None:
        planes.setdefault(r.direction, [0.0, 0.0])[0] += point[0]
    if weight is not None and prof.axis != GRAVITY_AXIS:
        planes.setdefault(GRAVITY_AXIS, [0.0, 0.0])[1] += weight * span / prof.length
    if not planes:
        raise _Cannot("nothing bends this beam: the only load is its own weight, and gravity acts along it")
    results, ratio = [], math.inf
    for axis, (point_n, udl_n) in sorted(planes.items()):
        depth, least = prof.depth(axis), beam.SLENDER[r.support]
        if span / depth < least:
            raise _Cannot(f"span/depth is {span / depth:.1f} ({span:g} mm over {depth:.1f} mm deep along "
                          f"{'xyz'[axis]}), under {least:g}: shear, which this does not model, matters there")
        ratio = min(ratio, span / depth)
        i_min, i_max = prof.second_moment(axis)
        results.append(_Plane(axis, i_min, i_max, point_n, udl_n,
                              beam.deflection(r.support, span, modulus.value, i_min, point_n, udl_n, r.at),
                              beam.deflection(r.support, span, modulus.value, i_max, point_n, udl_n, r.at)))
    return _finish(r, modulus, span, ratio, results, point)


def _profile(ctx, r: _Request, solid):
    """The body's sections: about 25 cuts, 1.5 s for a T-slot extrusion, made once for every entry of this run that
    names the body and its axis (a beam judged as simple, fixed and cantilever is cut once)."""
    cache = ctx.__dict__.setdefault("_beam_profiles", {})
    if (r.body, r.axis) not in cache:
        cache[(r.body, r.axis)] = beam.profile(solid, r.axis)
    return cache[(r.body, r.axis)]


def _finish(r: _Request, modulus, span: float, ratio: float, planes: list, point):
    upper = math.sqrt(sum(p.weak.mm ** 2 for p in planes))      # the weakest section the whole way: no more than this
    lower = math.sqrt(sum(p.stiff.mm ** 2 for p in planes))     # the stiffest the whole way: no less than this
    limit, spread, where = r.max_um / 1000.0, upper - lower > 1e-9 * upper, planes[0].weak.where
    if upper <= limit + TOL_MM:
        state = "PASS"
        shown = f"{_um(upper)} um" + (f" or less at {where} (the weakest section)" if spread else f" at {where}")
    elif lower > limit + TOL_MM:
        state = "FAIL"
        shown = f"{_um(lower)} um" + (f" or more at {where} (the stiffest section)" if spread else f" at {where}")
    else:
        state = "UNCHECKED"
        shown = (f"between {_um(lower)} and {_um(upper)} um at {where}: the section varies along the body, and the "
                 "limit falls between what its stiffest and its weakest section give")
    return _row(r.body, "deflection", state, f"{shown}; {_basis(r, modulus, span, ratio, planes, point)}", r.limit)


def _basis(r: _Request, modulus, span: float, ratio: float, planes: list, point) -> str:
    """What the number rests on: the span, the load, the second moment, E and where it came from."""
    several = len(planes) > 1
    loads = [point[1] + (f" along {'xyz'[r.direction]}" if several else "")] if point is not None else []
    loads += [f"{p.udl_n:.4g} N own weight" for p in planes if p.udl_n > 0]
    inertia = [f"{p.i_min:.5g}" + (f" (largest {p.i_max:.5g})" if p.i_max - p.i_min > 1e-9 * p.i_max else "") + " mm^4"
               + (f" for a load along {'xyz'[p.axis]}" if several else "") for p in planes]
    cases = []
    for p in planes:
        for used, case in ((p.point_n, p.weak.cases[0]), (p.udl_n, p.weak.cases[1])):
            if used > 0 and case not in cases:
                cases.append(case)
    return (f"{r.support} span {span:g} mm, load {' + '.join(loads)}; I {', '.join(inertia)}; "
            f"E {modulus.value:g} MPa ({modulus.source}); span/depth {ratio:.1f}; "
            f"Roark Table 8.1 case{'s' if len(cases) > 1 else ''} {', '.join(cases)}")


def _um(mm: float) -> str:
    return f"{mm * 1000.0:.3f}"


# ─── What the body is, and what loads it ─────────────────────────────────────

def _envelope(info) -> str:
    what = {"stock": "stock that assembly.py builds, a box standing for the part",
            "bought": "a bought part that is not declared `geometry = \"exact\"`"}.get(info.kind, "not exact geometry")
    return (f"{info.name} is {what}: an envelope has no cross-section to take a second moment of area from "
            "(use a part module, or a bought part whose sidecar says geometry = \"exact\")")


def _modulus(info):
    if not info.material:
        raise _Cannot(f"{info.name} has no material (MATERIAL in its part module, or `material` in a bought "
                      "part's sidecar), so there is no Young's modulus")
    key = materials.key(info.material)
    if key is None:
        raise _Cannot(f"material {info.material!r} is not in materials.py, so there is no Young's modulus")
    prop = materials.prop(info.material, "youngs_modulus_mpa")
    if prop is None:
        raise _Cannot(f"materials.py has no Young's modulus for {key} (nothing it can cite)")
    if not (prop.source and prop.source.strip()):
        raise _Cannot(f"materials.py gives {key} a Young's modulus with no source")
    return prop


def _point(r: _Request, ctx, bodies):
    """(newtons, how to say it) of the load, or None when there is only the body's own weight."""
    if r.load_n is not None:
        return r.load_n, f"{r.load_n:.4g} N"
    if r.load_g is not None:
        newtons = beam.weight_n(r.load_g)
        return newtons, f"{r.load_g:g} g = {newtons:.4g} N"
    if r.moving is None:
        return None
    axes = getattr(ctx.machine, "axes", None) or {}
    if not axes:
        raise _Cannot(f"load_moving = {r.moving!r} needs the AXES of the project's assembly.py, and it has none")
    if r.moving not in axes:
        raise _Unusable(f"[[deflection]] has no axis {r.moving!r} to take the load from (axes: {', '.join(sorted(axes))})")
    named = [n for n in axes[r.moving].moves if n != r.body]
    if not named:
        raise _Unusable(f"[[deflection]] axis {r.moving!r} moves nothing but {r.body}, so it puts no load on it")
    grams, parts, unknown = 0.0, [], []
    for name in named:
        info = bodies.get(name)
        if info is None:
            raise _Unusable(f"[[deflection]] axis {r.moving!r} moves {name!r}, which is not a body of the assembly")
        if info.mass_g is None:
            unknown.append(f"{name} ({info.notes[0] if info.notes else _no_mass(info)})")
        else:
            grams += info.mass_g
            parts.append(f"{name} {info.mass_g:.4g} g")
    if unknown:
        raise _Cannot(f"the mass axis {r.moving} moves is not known: {'; '.join(unknown)}")
    newtons = beam.weight_n(grams)
    return newtons, f"{newtons:.4g} N ({grams:.4g} g moved by axis {r.moving}: {', '.join(parts)})"


def _no_mass(info) -> str:
    return {"stock": "stock built in assembly.py has no material, so no mass",
            "bought": "a bought part with no declared mass and mass_source"}.get(info.kind, "no mass")


def _own_weight(r: _Request, info):
    """The newtons the body weighs, or None when `self_weight` is off."""
    if not r.self_weight:
        return None
    if info.mass_g is None:
        raise _Cannot(f"self_weight needs the mass of {info.name}, and it is not known "
                      f"({info.notes[0] if info.notes else _no_mass(info)})")
    return beam.weight_n(info.mass_g)
