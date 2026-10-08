"""Manufacturability gate, per process.

Every row names the rule, the measured value, the limit, and where the limit
came from. A rule that could not be measured returns UNCHECKED, never PASS,
and `done_check` fails on UNCHECKED, so silence cannot be mistaken for a pass.

Rules measured from the geometry rather than declared:

  envelope    bounding box against the machine's working volume
  wall        ray-cast thickness through the solid, sampled over the surface
  web         in-plane material between cutouts and the edge, for flat parts
  min hole    the smallest round hole, where the process has a floor for one
  kerf        the narrowest slot or gap, where the process has a kerf

The web rule exists because the wall rule cannot see the fault it catches. On
a 3 mm sheet every inward ray measures 3 mm, whether it starts in the middle
of the plate or in the 0.8 mm strip between two slots. The first car had
exactly that fault twice, and both times it took a human eye to notice.

A flat part with no cutout has no web: nothing sits between a cutout and the
edge, so the rule is N/A there. Its cutout count is still held to what the part
declares, so a plate whose holes all went missing does not slip through.

Every number in the table below is read by a rule, and a test holds it to that.
A process has a minimum hole only where a hole too small is a hole that cannot
be made. A printed part has none: a hole under 2 mm is drilled after printing
(an M2 tap drill is 1.6), and no geometry can say whether it will be.
"""
from __future__ import annotations

from ..geom import bbox, volume
from ..registry import TOL_MM
from .web import web_report

PROCESS = {
    "fdm": {
        "min_wall_mm": 0.8,        # 2 perimeters at a 0.4 mm nozzle
        "min_web_mm": 1.2,
        "max_bbox_mm": (250, 210, 210),
        "source": "0.4 mm nozzle, 2 perimeters; bed size assumption",
    },
    "laser_cut": {
        "min_wall_mm": 1.5,        # acrylic, at least the sheet thickness
        "min_web_mm": 1.5,         # a narrower strip melts through or snaps
        "min_hole_mm": 1.0,        # the beam does not cut a clean hole much below this
        "kerf_mm": 0.15,           # a slot or gap narrower than the beam's own cut cannot exist
        "max_bbox_mm": (600, 400, 25),
        "source": "CO2 on 3 mm acrylic, typical kerf",
    },
    "cnc": {
        "min_wall_mm": 1.0,
        "min_web_mm": 2.0,         # a thin web chatters and deflects
        "min_hole_mm": 1.0,        # smallest sane end mill or drill; a slot is cut with the same tool
        "max_bbox_mm": (300, 200, 100),
        "source": "3 mm end mill, small router assumption",
    },
}

# Below this ratio of smallest to largest dimension a part is treated as flat,
# and the in-plane web rule applies to it.
FLAT_RATIO = 0.25


def check_dfm(name: str, solid, process: str, min_feature_mm: float | None = None,
              expect_features: int | None = None, measure: bool = True,
              samples: int = 3000):
    if process not in PROCESS:
        raise ValueError(f"unknown process {process!r}; choose from {sorted(PROCESS)}")
    p = PROCESS[process]
    lo, hi = bbox(solid)
    dims = tuple(round(hi[i] - lo[i], 3) for i in range(3))
    rows = []

    def row(rule, state, measured, limit, source):
        rows.append({"part": name, "rule": rule, "state": state,
                     "measured": measured, "limit": limit, "source": source})

    fits = all(sorted(dims)[i] <= sorted(p["max_bbox_mm"])[i] + TOL_MM for i in range(3))
    row("envelope", "PASS" if fits else "FAIL",
        f"{dims[0]} x {dims[1]} x {dims[2]} mm",
        " x ".join(str(v) for v in p["max_bbox_mm"]) + " mm", p["source"])

    # ── wall thickness, measured through the solid ───────────────────────────
    if measure:
        from ..thickness import measure_min_wall
        t = measure_min_wall(solid, samples=samples)
        if t["state"] == "MEASURED":
            ok = t["p01_mm"] >= p["min_wall_mm"] - TOL_MM
            row("min wall", "PASS" if ok else "FAIL",
                f"{t['p01_mm']} mm at the 1st percentile "
                f"(min {t['min_mm']}, median {t['median_mm']}, {t['samples']} rays)",
                f"{p['min_wall_mm']} mm",
                "ray cast through the solid; p01 gates, since a grazing ray at "
                "an edge can return near zero")
        else:
            row("min wall", "UNCHECKED", t["state"].lower(),
                f"{p['min_wall_mm']} mm", t["note"])
    elif min_feature_mm is None:
        row("min wall", "UNCHECKED", "not measured", f"{p['min_wall_mm']} mm",
            "measurement disabled and nothing declared")
    else:
        ok = min_feature_mm >= p["min_wall_mm"] - TOL_MM
        row("min wall", "PASS" if ok else "FAIL",
            f"{min_feature_mm} mm (declared, not measured)",
            f"{p['min_wall_mm']} mm", "declared by the part")

    # ── in-plane web, for flat parts ─────────────────────────────────────────
    flat = min(dims) <= FLAT_RATIO * max(dims) + TOL_MM
    if not flat:
        row("web", "N/A", f"not a flat part (thinnest/longest = "
            f"{min(dims) / max(dims):.2f})", f"{p['min_web_mm']} mm",
            f"the in-plane rule applies below a ratio of {FLAT_RATIO}")
    else:
        w = web_report(solid)
        if w["state"] == "MEASURED":
            ok = w["min_web_mm"] >= p["min_web_mm"] - TOL_MM
            row("web", "PASS" if ok else "FAIL",
                f"{w['min_web_mm']} mm between {w['between']}, at "
                f"({w['at_xy'][0]}, {w['at_xy'][1]})",
                f"{p['min_web_mm']} mm",
                f"closest approach over {w['pairs_checked']} boundary pairs")
            if w["regions"] > 1:
                row("regions", "FAIL", f"{w['regions']} separate regions", "1",
                    "the part has been cut into pieces by its own features")
        elif w["state"] == "TRIVIAL":
            row("web", "N/A", "no cutout reaches the mid-plane", f"{p['min_web_mm']} mm",
                "a plain plate has no web between a cutout and the edge; its cutout "
                "count is still gated below")
        else:
            row("web", "UNCHECKED", w["state"].lower(), f"{p['min_web_mm']} mm",
                w.get("note", ""))
        if w["state"] in ("MEASURED", "TRIVIAL"):
            if expect_features is not None:
                got = w["features"]
                row("feature count", "PASS" if got == expect_features else "FAIL",
                    f"{got} cutouts", f"{expect_features} expected",
                    "a count that drops means one cutout has swallowed another "
                    "or broken out through an edge")
            else:
                row("feature count", "UNCHECKED", f"{w['features']} cutouts found",
                    "no expectation", "declare EXPECT_FEATURES in the part to "
                    "gate this (0 for a plain part); without it a swallowed cutout "
                    "goes unnoticed")

    _cutout_rows(row, solid, p)
    row("volume", "PASS", f"{volume(solid) / 1000.0:.2f} cm^3", "n/a", "computed")
    return rows


def _at(where) -> str:
    return "(" + ", ".join(f"{v:g}" for v in where) + ")"


def _cutout_rows(row, solid, p) -> None:
    """The smallest hole and the narrowest slot or gap, for a process that has a floor for each.

    Where a process has a kerf, slots and gaps answer to it and holes to the minimum hole. Where
    it has none (a mill cuts a slot with the same tool as a hole) a slot's width is a diameter too.
    """
    from .cuts import gap_report, hole_report
    rules = [(rule, key) for rule, key in (("min hole", "min_hole_mm"), ("kerf", "kerf_mm"))
             if key in p]
    if not rules:
        return
    try:
        found = hole_report(solid)
        gaps = gap_report(solid) if "kerf_mm" in p else []
    except Exception as e:  # noqa: BLE001 - say so, never pass what could not be read
        for rule, key in rules:
            row(rule, "UNCHECKED", f"{type(e).__name__}: {e}", f"{p[key]} mm",
                "the search for holes and walls raised, so nothing was judged")
        return

    if "min_hole_mm" in p:
        kerf = "kerf_mm" in p
        sized = found["holes"] + ([] if kerf else found["slots"])
        one, many = ("round hole", "round holes") if kerf else ("hole or slot", "holes and slots")
        if not sized:
            row("min hole", "N/A", f"no {one}", f"{p['min_hole_mm']} mm",
                "nothing to size; a slot is judged against the kerf" if kerf else
                "nothing to size")
        else:
            size, where = min(sized)
            ok = size >= p["min_hole_mm"] - TOL_MM
            row("min hole", "PASS" if ok else "FAIL",
                f"{size:g} mm at {_at(where)}, the smallest of {len(sized)} "
                f"{one if len(sized) == 1 else many}",
                f"{p['min_hole_mm']} mm",
                "the narrowest bore of each hole, read from its cylinders: a teardrop, a D or a "
                "slit bore counts at its diameter")

    if "kerf_mm" in p:
        narrow = sorted(found["slots"] + gaps)
        if not narrow:
            row("kerf", "N/A", "no slot or gap", f"{p['kerf_mm']} mm",
                "no slot, and no flat walls face each other across air; a round hole is "
                "judged as a hole")
        else:
            width, where = narrow[0]
            ok = width >= p["kerf_mm"] - TOL_MM
            row("kerf", "PASS" if ok else "FAIL",
                f"{width:.3g} mm at {_at(where)}, the narrowest slot or gap",
                f"{p['kerf_mm']} mm",
                "a slot's width, or the air between two flat walls that face each other; a "
                "curved gap other than a slot's ends is not read")
