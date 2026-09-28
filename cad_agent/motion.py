"""Axes: what moves, along what, how far — and what that costs in clearance.

Every fit check before this one judged a single pose. That is the pose the
assembly happens to return, which for a machine is home, and home is the one
place a gantry is least likely to crash. A beam that clears the frame at
x = 0 can bury itself in the upright at x = +150, and nothing in the registry
would have said a word.

So a project declares its axes in assembly.py:

    AXES = {
        "x": {
            "moves": ("gantry_beam", "carriage", "laser_head"),
            "direction": (1, 0, 0),
            "travel": (-150.0, 150.0),   # relative to the pose assembly returns
            "work": (-120.0, 120.0),     # span the tool point must cover
            "tool": "laser_head",        # body carrying the tool point
            "tool_point": (0.0, 0.0, -20.0),
        },
    }

`travel` is the mechanical limit and `work` is the promise made to the user of
the machine. They are different numbers on purpose: the reach rule exists to
catch a build where the second quietly exceeds the first.

Two deliberate limits, since a gate that overstates what it proved is worse
than no gate:

  Axes are swept one at a time, each from the home pose. A crash that needs
  x and y simultaneously off-home is not found. Sweeping the product of two
  axes is the honest fix and costs the product of the sample counts; for now
  the rows say which axis they moved, so nobody reads more into them.

  Sampling is finite. A thin obstacle between two samples is missed. The
  samples are dense at the ends, where travel limits actually bite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
from build123d import Pos

from .geom import bbox, intersection_volume, min_distance

# Overlap below this is OCCT noise on coincident faces, matching checks.fit.
VOLUME_NOISE_MM3 = 1e-6

# How many poses per axis. Both ends are always sampled, because the ends are
# where a travel limit is either respected or not.
DEFAULT_SAMPLES = 7


@dataclass
class Axis:
    name: str
    moves: tuple
    direction: tuple
    travel: tuple
    work: tuple | None = None
    tool: str | None = None
    tool_point: tuple = (0.0, 0.0, 0.0)

    @property
    def unit(self):
        v = np.array(self.direction, dtype=float)
        n = float(np.linalg.norm(v))
        if n == 0.0:
            raise ValueError(f"axis {self.name!r} has a zero direction vector")
        return v / n

    @property
    def span(self) -> float:
        return float(self.travel[1] - self.travel[0])


def load_axes(mod) -> dict:
    """Read AXES off a loaded assembly module. Absent means a static assembly."""
    raw = getattr(mod, "AXES", None) or {}
    out = {}
    for name, d in raw.items():
        if isinstance(d, Axis):
            out[name] = d
            continue
        d = dict(d)
        travel = tuple(float(x) for x in d["travel"])
        if travel[1] <= travel[0]:
            raise ValueError(
                f"axis {name!r}: travel {travel} does not increase; give it "
                "as (min, max) relative to the pose assembly.py returns")
        work = d.get("work")
        out[name] = Axis(
            name=name,
            moves=tuple(d["moves"]),
            direction=tuple(float(x) for x in d["direction"]),
            travel=travel,
            work=tuple(float(x) for x in work) if work else None,
            tool=d.get("tool"),
            tool_point=tuple(float(x) for x in d.get("tool_point", (0, 0, 0))),
        )
    return out


def sample_travel(axis: Axis, samples: int = DEFAULT_SAMPLES):
    """Positions across travel, both ends included."""
    n = max(2, int(samples))
    return [float(t) for t in np.linspace(axis.travel[0], axis.travel[1], n)]


def pose(parts: dict, axis: Axis, t: float) -> dict:
    """The assembly with this axis driven to t. Bodies not on the axis stay put."""
    missing = [m for m in axis.moves if m not in parts]
    if missing:
        raise KeyError(
            f"axis {axis.name!r} moves {missing}, which the assembly does not "
            f"return; known bodies are {sorted(parts)}")
    d = axis.unit * float(t)
    shift = Pos(float(d[0]), float(d[1]), float(d[2]))
    return {n: (shift * s if n in axis.moves else s) for n, s in parts.items()}


def _bbox_gap(a, b) -> float:
    """Separation between two bounding boxes: a lower bound on true distance.

    This is what makes sweeping affordable. A boolean intersection is the
    expensive call, and for most pairs at most poses the boxes are nowhere
    near each other, which this settles in microseconds without OCCT.
    """
    (alo, ahi), (blo, bhi) = bbox(a), bbox(b)
    gaps = [max(blo[i] - ahi[i], alo[i] - bhi[i]) for i in range(3)]
    sep = [g for g in gaps if g > 0.0]
    if not sep:
        return 0.0      # boxes overlap in all three axes; solids may or may not
    return float(np.linalg.norm(sep))


@dataclass
class SweepHit:
    """The worst thing seen for one pair over one axis."""
    pair: tuple
    distance: float = float("inf")
    at: float = 0.0
    overlap: float = 0.0
    exact: bool = False   # True when the figure came from OCCT, not a bbox
    poses_exact: int = 0


def sweep_axis(parts: dict, axis: Axis, required: dict, allow_contact: set,
               samples: int = DEFAULT_SAMPLES, default_clearance: float = 0.0):
    """Drive one axis across travel; report the worst approach for each pair.

    Only pairs with at least one moving body are judged: a pair of static
    bodies cannot change, and the static fit check already covers it.
    """
    moving = set(axis.moves)
    pairs = [tuple(sorted(p)) for p in combinations(sorted(parts), 2)
             if moving & set(p)]
    hits = {p: SweepHit(pair=p) for p in pairs}

    for t in sample_travel(axis, samples):
        posed = pose(parts, axis, t)
        for key in pairs:
            a, b = posed[key[0]], posed[key[1]]
            need = required.get(key, default_clearance)
            hit = hits[key]
            # Cheap lower bound first. If the boxes are already further apart
            # than the requirement and than anything seen so far, nothing an
            # exact call could return would change the verdict.
            lower = _bbox_gap(a, b)
            if lower > need and lower >= hit.distance:
                continue
            overlap = intersection_volume(a, b)
            if overlap > VOLUME_NOISE_MM3:
                if overlap > hit.overlap:
                    hit.overlap, hit.at, hit.distance = overlap, t, 0.0
                    hit.exact = True
                hit.poses_exact += 1
                continue
            d = min_distance(a, b)
            hit.poses_exact += 1
            if d < hit.distance:
                hit.distance, hit.at, hit.exact = d, t, True
    return hits


def tool_span(axis: Axis) -> tuple:
    """Where the tool point reaches along the axis, as (min, max) of travel."""
    p = np.array(axis.tool_point, dtype=float)
    ends = [p + axis.unit * t for t in axis.travel]
    # Report along the axis direction, which is the only component that moves.
    proj = sorted(float(np.dot(e, axis.unit)) for e in ends)
    return proj[0], proj[1]
