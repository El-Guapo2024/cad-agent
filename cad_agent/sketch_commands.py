# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
#   src/Mod/Sketcher/Gui/Command.cpp: 2008 Jürgen Riegel (Sketcher_ReorientSketch, _MapSketch, _ValidateSketch,
#                                     _MirrorSketch, _MergeSketches)
#   src/Mod/Sketcher/Gui/SketchOrientationDialog.cpp: 2011 Jürgen Riegel
#   src/Mod/Sketcher/Gui/SketchMirrorDialog.cpp: 2015 Abdullah Tahiri
#   src/Mod/Sketcher/Gui/TaskSketcherValidation.cpp: 2012 Werner Mayer
#   src/Mod/Sketcher/App/SketchAnalysis.cpp: 2018 Abdullah Tahiri, 2013 Werner Mayer
#   src/Mod/Sketcher/App/SketchObjectOperations.cpp, SketchObjectConstraints.cpp, SketchObjectGeometry.cpp,
#   SketchObjectExternal.cpp, SketchObject.cpp: 2008 Jürgen Riegel (getSymmetric, addSymmetric, addCopyOfConstraints,
#                                     evaluateConstraint, validateConstraints, delGeometry, delConstraintsToExternal,
#                                     changeConstraintsLocking, port_reversedExternalArcs)
#   src/Mod/Sketcher/App/ConstraintPyImp.cpp: 2010 Jürgen Riegel (Sketcher.Constraint's argument forms)
#   libstdc++'s std::sort (bits/stl_algo.h, GPL-3.0 with the GCC Runtime Library Exception): its order, which
#                                     SketchAnalysis's tolerant comparison depends on
"""The Sketcher's commands on sketch objects, as FreeCAD 26.3 does them out of edit mode, on a part file's sketches.

    mirror(sketch, ref)            Sketcher_MirrorSketch: a new sketch, the geometry mirrored about the X axis ("X"),
                                   the Y axis ("Y") or the origin ("origin"), with the constraints addSymmetric keeps
    merge(sketches)                Sketcher_MergeSketches: a new sketch holding every geometry and constraint of the
                                   selected ones, in selection order (addCopyOfConstraints, importExternalGeometry)
    reorient(plane, reverse, off)  Sketcher_ReorientSketch: SketchOrientationDialog's Placement
    missing_coincidences(...)      Sketcher_ValidateSketch's Missing Coincidences (SketchAnalysis::
                                   detectMissingPointOnPointConstraints); Fix adds them (makeMissingPointOnPointCoincident)
    open_vertices, invalid_constraints, validate_constraints, degenerated, remove_degenerated,
    constraints_to_external, reversed_external_arcs, orientation_locking
                                   the rest of the Sketch Validation panel

A sketch here is the dict feature_edit.read() gives ({"geometry": [...], "constraints": [...], ...}); a constraint's
FreeCAD fields (First, FirstPos, Second, ...) come from its Sketcher.Constraint arguments as ConstraintPyImp.cpp reads
them (fields(), and args_of() back). Geometry is cad_agent.planegcs's dict form.

`cad feature mirror | merge | reorient | map | validate` (add_parser) are the commands: each works out the ops
FreeCAD's command amounts to and applies them as one undo step named as FreeCAD names its transaction, or with --dry
only answers with them (what the workbench sends through POST /api/<slug>/features/<part>).
"""
from __future__ import annotations

import copy
import json
import math

GEO_UNDEF, H_AXIS, V_AXIS, RT_PNT, REF_EXT = -2000, -1, -2, -1, -3
NONE, START, END, MID = 0, 1, 2, 3
CONFUSION = 1e-7                           # Precision::Confusion()
TWO_PI = 2.0 * math.pi
DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle", "Weight", "SnellsLaw")
# InternalAlignment's argument forms (ConstraintPyImp.cpp): (Geo, Geo), (Geo, Pos, Geo), (Geo, Pos, Geo, index)
ALIGN_TWO = ("EllipseMajorDiameter", "EllipseMinorDiameter", "HyperbolaMajor", "HyperbolaMinor", "ParabolaFocalAxis")
ALIGN_INDEXED = ("BSplineControlPoint", "BSplineKnotPoint")


class SketchCommandError(ValueError):
    """What FreeCAD's command refuses, in its words."""


# ── Sketcher::Constraint's fields from Sketcher.Constraint's arguments (ConstraintPyImp.cpp) ──────────────────────

def fields(c: dict, value=None) -> dict:
    """A constraint dict ({"type", "args", "value", "driving", "name"}) as Sketcher::Constraint holds it: type,
    first, first_pos, second, second_pos, third, third_pos, value (resolved: `value` when given), driving, name, and
    an InternalAlignment's alignment and index. The argument forms are ConstraintPyImp::PyInit's."""
    t, a = c["type"], [int(x) for x in c.get("args", [])]
    f = {"type": t, "first": GEO_UNDEF, "first_pos": NONE, "second": GEO_UNDEF, "second_pos": NONE,
         "third": GEO_UNDEF, "third_pos": NONE, "value": 0.0, "driving": c.get("driving", True) is not False,
         "name": c.get("name") or "", "alignment": None, "index": -1}
    v = c.get("value") if value is None else value
    if t in DIMENSIONAL and isinstance(v, (int, float)) and not isinstance(v, bool):
        f["value"] = float(v)

    def put(*xs):
        for k, x in zip(("first", "first_pos", "second", "second_pos", "third", "third_pos"), xs):
            f[k] = x
    if t.startswith("InternalAlignment:"):
        al = t.split(":", 1)[1]
        f["type"], f["alignment"] = "InternalAlignment", al
        if al in ALIGN_TWO:
            put(a[0], NONE, a[1])
        elif al in ALIGN_INDEXED:
            put(a[0], a[1], a[2])
            f["index"] = a[3] if len(a) > 3 else -1
        else:
            put(a[0], a[1], a[2])
        return f
    n = len(a)
    if t == "Coincident":
        put(a[0], a[1], a[2], a[3])
    elif t in ("Horizontal", "Vertical", "Block") and n == 1:
        put(a[0])
    elif t in ("Horizontal", "Vertical"):
        put(a[0], a[1], a[2], a[3])
    elif t in ("Parallel", "Equal"):
        put(a[0], NONE, a[1])
    elif t in ("Perpendicular", "Tangent"):
        if n == 2:
            put(a[0], NONE, a[1])
        elif n == 3:
            put(a[0], a[1], a[2])                       # "siiO": (Geo, Pos, Geo)
        else:
            put(a[0], a[1], a[2], a[3])
    elif t == "PointOnObject":
        put(a[0], a[1], a[2])
    elif t == "Symmetric":
        put(a[0], a[1], a[2], a[3], a[4], a[5] if n > 5 else NONE)
    elif t in ("Radius", "Diameter", "Weight"):
        put(a[0])
    elif t in ("DistanceX", "DistanceY"):
        if n == 1:
            put(a[0])
        elif n == 2:
            put(a[0], a[1])                             # "siiO" with a number: (Geo, Pos, value)
        else:
            put(a[0], a[1], a[2], a[3])
    elif t == "Distance":
        if n == 1:
            put(a[0])
        elif n == 2:
            put(a[0], NONE, a[1])                       # (Geo, Geo, value): circle-circle, line-circle
        elif n == 3:
            put(a[0], a[1], a[2])
        else:
            put(a[0], a[1], a[2], a[3])
    elif t == "Angle":
        if n == 1:
            put(a[0])
        elif n == 2:
            put(a[0], NONE, a[1])
        else:
            put(a[0], a[1], a[2], a[3])
    elif t == "SnellsLaw":
        put(a[0], a[1], a[2], a[3], a[4], NONE)
    else:
        put(*a)
    return f


def args_of(f: dict) -> dict:
    """fields() back to a constraint dict, in the argument form the part file writes (ui/src/sketch.ts's toArgs)."""
    t = f["type"]
    fi, fp, s, sp, th, tp = (f["first"], f["first_pos"], f["second"], f["second_pos"], f["third"], f["third_pos"])
    if t == "InternalAlignment":
        al = f["alignment"]
        args = [fi, s] if al in ALIGN_TWO else [fi, fp, s, f.get("index", -1)] if al in ALIGN_INDEXED else [fi, fp, s]
        out = {"type": f"InternalAlignment:{al}", "args": args}
    else:
        if t == "Coincident":
            args = [fi, fp, s, sp]
        elif t in ("Horizontal", "Vertical"):
            args = [fi] if s == GEO_UNDEF else [fi, fp, s, sp]
        elif t in ("Parallel", "Equal"):
            args = [fi, s]
        elif t in ("Perpendicular", "Tangent"):
            args = [fi, s] if fp == NONE and sp == NONE else [fi, fp, s] if sp == NONE else [fi, fp, s, sp]
        elif t == "PointOnObject":
            args = [fi, fp, s]
        elif t in ("Distance", "DistanceX", "DistanceY"):
            if s == GEO_UNDEF:
                args = [fi] if fp == NONE else [fi, fp]
            elif fp == NONE and sp == NONE:
                args = [fi, s]
            elif sp == NONE:
                args = [fi, fp, s]
            else:
                args = [fi, fp, s, sp]
        elif t in ("Radius", "Diameter", "Weight", "Block"):
            args = [fi]
        elif t == "Angle":
            args = [fi] if s == GEO_UNDEF else [fi, s] if fp == NONE and sp == NONE else [fi, fp, s, sp]
        elif t == "Symmetric":
            args = [fi, fp, s, sp, th] if tp == NONE else [fi, fp, s, sp, th, tp]
        elif t == "SnellsLaw":
            args = [fi, fp, s, sp, th]
        else:
            args = [fi, fp, s, sp, th, tp]
        out = {"type": t, "args": args}
    if t in DIMENSIONAL:
        out["value"] = f["value"]
    out["driving"] = bool(f.get("driving", True))
    out["name"] = f.get("name") or ""
    return out


def elements(f: dict):
    """Constraint::getElement(0..2): (GeoId, PosId) of First, Second and Third."""
    return [(f["first"], f["first_pos"]), (f["second"], f["second_pos"]), (f["third"], f["third_pos"])]


# ── the geometry's points (SketchObject::getPoint) ────────────────────────────────────────────────────────────

def _geo(d: dict):
    from .feature import geometry_from_dict
    return geometry_from_dict(d)


def point(geo: list, g: int, pos: int):
    """SketchObject::getPoint(GeoId, PosId) for internal geometry, None where the geometry has no such point."""
    if g == H_AXIS and pos == START:
        return (0.0, 0.0)
    if g < 0 or g >= len(geo):
        return None
    return _geo(geo[g]).points().get(pos)


def _construction(g: dict) -> bool:
    return bool(g.get("construction", False))


# ── Sketcher_MirrorSketch: SketchObject::getSymmetric and addSymmetric ─────────────────────────────────────────

def _fmod2pi(x: float) -> float:
    """Base::fmod(x, 2π): the remainder in [0, 2π)."""
    m = math.fmod(x, TWO_PI)
    return m if m >= 0 else m + TWO_PI


def _set_trim_periodic(u1: float, u2: float):
    """Geom_TrimmedCurve::SetTrim on a periodic basis curve: ElCLib::AdjustPeriodic with
    Min(|u2 - u1| / 2, Precision::PConfusion())."""
    preci = min(abs(u2 - u1) / 2.0, CONFUSION * 0.01)
    u1 -= math.floor(u1 / TWO_PI) * TWO_PI
    if TWO_PI - u1 < preci:
        u1 -= TWO_PI
    u2 -= math.floor((u2 - u1) / TWO_PI) * TWO_PI
    if u2 - u1 < preci:
        u2 += TWO_PI
    return u1, u2


def _norm(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n else None


def _mirror_geometry(g: dict, refl, line: bool) -> tuple[dict, bool]:
    """One geometry of getSymmetric: its mirror image (refl maps a point) and whether its start and end swap."""
    t = g["type"]
    out = copy.deepcopy(g)
    if t == "LineSegment":
        out["start"], out["end"] = list(refl(g["start"])), list(refl(g["end"]))
        return out, False
    if t == "Circle":
        out["center"] = list(refl(g["center"]))
        return out, False
    if t == "Point":
        out["at"] = list(refl(g["at"] if "at" in g else g["point"]))
        out.pop("point", None)
        return out, False
    if t == "ArcOfCircle":
        c, r = g["center"], g["radius"]
        sp = (c[0] + r * math.cos(g["start_angle"]), c[1] + r * math.sin(g["start_angle"]))
        ep = (c[0] + r * math.cos(g["end_angle"]), c[1] + r * math.sin(g["end_angle"]))
        ssp, sep, scp = refl(sp), refl(ep), refl(c)
        if line:      # the arc's sense turns: its new start is the old end's image
            t1 = _fmod2pi(math.atan2(sep[1] - scp[1], sep[0] - scp[0]))
            t2 = _fmod2pi(math.atan2(ssp[1] - scp[1], ssp[0] - scp[0]))
        else:
            t1 = _fmod2pi(math.atan2(ssp[1] - scp[1], ssp[0] - scp[0]))
            t2 = _fmod2pi(math.atan2(sep[1] - scp[1], sep[0] - scp[0]))
        out["center"] = list(scp)
        out["start_angle"], out["end_angle"] = _set_trim_periodic(t1, t2)
        return out, line
    if t in ("Ellipse", "ArcOfEllipse", "ArcOfHyperbola", "ArcOfParabola"):
        c = g["center"]
        x = _norm(g.get("x_axis", (1.0, 0.0)))
        if t == "ArcOfParabola":                        # GeomArcOfParabola::getFocus
            f1 = (c[0] + g["focal"] * x[0], c[1] + g["focal"] * x[1])
        else:
            a, b = g["major_radius"], g["minor_radius"]
            df = math.sqrt(a * a + b * b) if t == "ArcOfHyperbola" else math.sqrt(a * a - b * b)
            f1 = (c[0] + df * x[0], c[1] + df * x[1])
        sf1, scp = refl(f1), refl(c)
        d = _norm((sf1[0] - scp[0], sf1[1] - scp[1]))
        if d is not None:                               # setMajorAxisDir keeps the old axis for a null vector
            out["x_axis"] = list(d)
        out["center"] = list(scp)
        inverted = False
        if line and t == "ArcOfEllipse":
            t1, t2 = TWO_PI - g["start_angle"], TWO_PI - g["end_angle"]
            t1, t2 = t2, t1
            if t1 < 0:
                t1 += TWO_PI
                t2 += TWO_PI
            out["start_angle"], out["end_angle"] = _set_trim_periodic(t1, t2)
            inverted = True
        elif line and t in ("ArcOfHyperbola", "ArcOfParabola"):
            out["start_angle"], out["end_angle"] = -g["end_angle"], -g["start_angle"]
            inverted = True
        for k in ("start_point", "end_point"):
            out.pop(k, None)
        return out, inverted
    if t == "BSplineCurve":
        out["poles"] = [list(refl(p)) for p in g["poles"]]
        return out, False
    return out, False                                   # "Unsupported Geometry!! Just copying it."


def internal_aligned(constraints: list[dict]) -> dict:
    """{geoId: the geometry it is internal to}: GeometryFacade::isInternalAligned, set by its InternalAlignment
    constraint (SketchObject::addGeometryState); the first such constraint names the geometry it defines."""
    out = {}
    for f in constraints:
        if f["type"] == "InternalAlignment" and f["first"] not in out:
            out[f["first"]] = f["second"]
    return out


def get_symmetric(geo: list, cons: list[dict], ids: list[int], ref_geo: int, ref_pos: int):
    """SketchObject::getSymmetric on a sketch with no external geometry but its axes (the Mirror command's temporary
    sketch): the mirrored geometries, {geoId: new geoId} and {geoId: start and end swapped}."""
    line = ref_pos == NONE
    aligned = internal_aligned(cons)
    out, gmap, inverted = [], {}, {}
    nxt = len(geo)
    if line:
        if ref_geo == H_AXIS:
            l1, l2 = (0.0, 0.0), (1.0, 0.0)
        elif ref_geo == V_AXIS:
            l1, l2 = (0.0, 0.0), (0.0, 1.0)
        elif 0 <= ref_geo < len(geo) and geo[ref_geo]["type"] == "LineSegment":
            l1, l2 = tuple(geo[ref_geo]["start"]), tuple(geo[ref_geo]["end"])
        else:
            return [], {}, {}
        vx, vy = l2[0] - l1[0], l2[1] - l1[1]
        sq = vx * vx + vy * vy

        def refl(p):            # p + 2 (p.Perpendicular(start, dir) - p)
            k = ((p[0] - l1[0]) * vx + (p[1] - l1[1]) * vy) / sq
            q = (l1[0] + k * vx, l1[1] + k * vy)
            return (p[0] + 2.0 * (q[0] - p[0]), p[1] + 2.0 * (q[1] - p[1]))
    else:
        if 0 <= ref_geo < len(geo) and geo[ref_geo]["type"] == "Point":
            rp = tuple(geo[ref_geo]["at"])
        elif ref_geo == RT_PNT and ref_pos == START:
            rp = (0.0, 0.0)
        else:
            rp = point(geo, ref_geo, ref_pos)
            if rp is None:
                return [], {}, {}

        def refl(p):
            return (p[0] + 2.0 * (rp[0] - p[0]), p[1] + 2.0 * (rp[1] - p[1]))
    for g in ids:
        if g in aligned and aligned[g] not in ids:      # shouldCopyGeometry
            continue
        m, inv = _mirror_geometry(geo[g], refl, line)
        out.append(m)
        inverted[g] = inv
        gmap[g] = nxt
        nxt += 1
    return out, gmap, inverted


def add_symmetric(geo: list, cons: list[dict], ids: list[int], ref_geo: int, ref_pos: int):
    """SketchObject::addSymmetric(geoIdList, refGeoId, refPosId) without symmetry constraints: the geometry and
    constraints after it (cons as fields())."""
    line = ref_pos == NONE
    axis_aligned = ref_geo in (V_AXIS, H_AXIS) or not line or any(
        c["first"] == ref_geo and c["type"] in ("Vertical", "Horizontal") for c in cons)
    sym, gmap, inverted = get_symmetric(geo, cons, ids, ref_geo, ref_pos)
    geo = geo + sym
    out = list(cons)

    def flip(el, pos):
        if inverted.get(el[0], False):
            return END if el[1] == START else START if el[1] == END else pos
        return pos
    for c in cons:
        els = elements(c)
        if els[0][0] not in gmap:
            continue
        if els[1][0] == GEO_UNDEF:
            if axis_aligned and c["type"] in ("DistanceX", "DistanceY"):
                continue
            if not axis_aligned and c["type"] in ("DistanceX", "DistanceY", "Vertical", "Horizontal"):
                continue
            n = dict(c, name="", first=gmap[els[0][0]])
            out.append(n)
            continue
        if els[1][0] not in gmap:
            continue
        if els[2][0] == GEO_UNDEF:
            if c["type"] not in ("Coincident", "Perpendicular", "Parallel", "Tangent", "Distance", "Equal", "Angle",
                                 "PointOnObject", "InternalAlignment"):
                continue
            n = dict(c, name="", first=gmap[els[0][0]], second=gmap[els[1][0]],
                     first_pos=flip(els[0], c["first_pos"]), second_pos=flip(els[1], c["second_pos"]))
            if c["type"] == "Angle" and ref_pos == NONE:
                n["value"] = -c["value"]
            out.append(n)
            continue
        if els[2][0] not in gmap:
            continue
        out.append(dict(c, name="", first=gmap[els[0][0]], second=gmap[els[1][0]], third=gmap[els[2][0]],
                        first_pos=flip(els[0], c["first_pos"]), second_pos=flip(els[1], c["second_pos"]),
                        third_pos=flip(els[2], c["third_pos"])))
    return geo, out


MIRROR_REFS = {"X": (H_AXIS, NONE), "Y": (V_AXIS, NONE), "origin": (RT_PNT, START)}


def mirror(sketch: dict, ref: str = "X", params: dict | None = None) -> dict:
    """CmdSketcherMirrorSketch for one sketch: {"geometry", "constraints"} of the new MirroredSketch. sketch holds the
    geometry as solved and its constraints (values resolved through params); ref is SketchMirrorDialog's choice:
    "X" (X-axis, its default), "Y" (Y-axis) or "origin"."""
    if ref not in MIRROR_REFS:
        raise SketchCommandError(f"mirror about {ref!r}: one of X, Y, origin (SketchMirrorDialog's choices)")
    ref_geo, ref_pos = MIRROR_REFS[ref]
    geo = [dict(g) for g in sketch.get("geometry", [])]
    cons = [fields(c, _resolved(c, params)) for c in sketch.get("constraints", [])]
    n = len(geo)
    allg, allc = add_symmetric(geo, cons, list(range(n)), ref_geo, ref_pos)
    mg, mc = allg[n:], allc[len(cons):]
    for c in mc:                                        # the new sketch's own numbering
        for k in ("first", "second", "third"):
            if c[k] != GEO_UNDEF:
                c[k] -= n
    return {"geometry": mg, "constraints": [args_of(c) for c in mc]}


def _resolved(c: dict, params):
    """A constraint's value in FreeCAD's units (mm, radians), a PARAMS expression evaluated."""
    if c.get("type") not in DIMENSIONAL or "value" not in c:
        return None
    from .feature import Constraint, FeatureError
    try:
        k = Constraint(c["type"], *c["args"], c["value"])
        return k.resolved(params or {})
    except (FeatureError, TypeError):
        v = c["value"]
        return float(v) if isinstance(v, (int, float)) else 0.0


# ── Sketcher_MergeSketches ─────────────────────────────────────────────────────────────────────────────────────

def merge(sketches: list[dict], params: dict | None = None, in_scope=None) -> dict:
    """CmdSketcherMergeSketches: {"geometry", "constraints", "external_geometry", "messages"} of the merged sketch.
    sketches are in selection order, each with its geometry (as solved), constraints, external_geometry
    ([(object, element)]) and "external_counts" (how many geometries each reference projects to, as
    rebuildExternalGeometry made them); in_scope(sketch, (object, element)) says whether the reference can be
    brought into the merged sketch (isExternalObjectInScope: the same Body), True when not given. messages are
    what FreeCAD prints in the Report view."""
    in_scope = in_scope or (lambda s, r: True)
    geo, cons, ext, ext_counts, messages, delete = [], [], [], [], [], []
    for sk in sketches:
        base_geometry, base_constraints = len(geo), len(cons)
        geo += [dict(g) for g in sk.get("geometry", [])]
        # importExternalGeometry: srcGeoId -> dstGeoId
        refs = [tuple(r) for r in sk.get("external_geometry") or []]
        counts = list(sk.get("external_counts") or [1] * len(refs))
        ext_map = {H_AXIS: H_AXIS, V_AXIS: V_AXIS}
        ids_of, gid = {}, REF_EXT
        for r, cnt in zip(refs, counts):
            ids_of[r] = list(range(gid, gid - cnt, -1))
            for g in ids_of[r]:
                ext_map[g] = GEO_UNDEF
            gid -= cnt
        for r in refs:
            src_ids = ids_of[r]
            if not in_scope(sk, r):
                messages.append(f"External geometry '{r[0]}.{r[1]}' is out of scope:\n")
                messages += [f"Skipping external geometry #{-g - 2}\n" for g in src_ids]
                continue
            have, at = [], REF_EXT
            for dr, dc in zip(ext, ext_counts):
                if dr == r:
                    have = list(range(at, at - dc, -1))
                at -= dc
            if not have:
                before = 2 + sum(ext_counts)
                ext.append(r)
                ext_counts.append(len(src_ids))
                have = [-j for j in range(before + 1, before + len(src_ids) + 1)]
            for s, d in zip(sorted(src_ids, reverse=True), sorted(have, reverse=True)):
                ext_map[s] = d
        # addCopyOfConstraints: copies (the expressions stay behind: FreeCAD 26.3's loop that would copy them starts
        # past the end of the list), then the GeoIds remapped
        src = [fields(c, _resolved(c, sk.get("params", params))) for c in sk.get("constraints", [])]
        cons += src
        for i, c in enumerate(src):
            ok = True
            for k in ("first", "second", "third"):
                g = c[k]
                if g in (GEO_UNDEF, H_AXIS, V_AXIS):
                    continue
                if g <= REF_EXT:
                    d = ext_map.get(g, GEO_UNDEF)
                    if d == GEO_UNDEF:
                        ok = False
                        break
                    c[k] = d
                    continue
                if g + base_geometry >= len(geo):
                    ok = False
                    break
                c[k] = g + base_geometry
            if not ok:
                delete.append(base_constraints + i)
                messages.append(f"Skipping constraint #{i + 1} of '{sk.get('name', '')}': references unmerged "
                                "geometry.\n")
    for i in sorted(delete, reverse=True):
        del cons[i]
    return {"geometry": geo, "constraints": [args_of(c) for c in cons], "external_geometry": [list(r) for r in ext],
            "messages": messages}


# ── Sketcher_ReorientSketch: SketchOrientationDialog::accept ──────────────────────────────────────────────────

# (plane, reverse): Base::Rotation(x, y, z, w), normalised, and the view the dialog's preview shows
ORIENTATIONS = {("XY", False): ((0.0, 0.0, 0.0, 1.0), "view-top"), ("XY", True): ((1.0, 0.0, 0.0, 0.0), "view-bottom"),
                ("XZ", False): ((1.0, 0.0, 0.0, 1.0), "view-front"), ("XZ", True): ((0.0, 1.0, 1.0, 0.0), "view-rear"),
                ("YZ", False): ((1.0, 1.0, 1.0, 1.0), "view-right"), ("YZ", True): ((-1.0, 1.0, 1.0, -1.0), "view-left")}


def _printed(x: float) -> float:
    """A number as Gui::cmdAppObjectArgs prints it, "%f", and Python reads it back."""
    return float("%f" % x)


def reorient(plane: str = "XY", reverse: bool = False, offset: float = 0.0):
    """The Placement CmdSketcherReorientSketch writes: (position, quaternion (x, y, z, w)), as the dialog makes it
    and as "App.Placement(App.Vector(%f, %f, %f), App.Rotation(%f, %f, %f, %f))" hands it to Python."""
    from .attacher import Rotation
    if (plane, bool(reverse)) not in ORIENTATIONS:
        raise SketchCommandError(f"orientation {plane!r}: one of XY, XZ, YZ (SketchOrientationDialog's planes)")
    q = Rotation(ORIENTATIONS[(plane, bool(reverse))][0]).q
    pos = {"XY": (0.0, 0.0, offset), "XZ": (0.0, offset, 0.0), "YZ": (offset, 0.0, 0.0)}[plane]
    return tuple(_printed(c) for c in pos), Rotation(tuple(_printed(c) for c in q)).q


def placement_value(pos, q):
    """A Placement as a part file writes it: ((x, y, z), (yaw, pitch, roll)) in degrees."""
    from .attacher import Rotation
    return [list(pos), list(Rotation(q).ypr())]


# ── Sketcher_ValidateSketch: SketchAnalysis ────────────────────────────────────────────────────────────────────

def _cpp_sort(a: list, less) -> None:
    """std::sort as libstdc++ does it (introsort, then insertion sort), in place. SketchAnalysis sorts with a
    tolerant comparison, which is not a strict weak order, so the order it leaves depends on the algorithm."""
    n = len(a)
    if n < 2:
        return

    def swap(i, j):
        a[i], a[j] = a[j], a[i]

    def median_to_first(result, x, y, z):
        if less(a[x], a[y]):
            if less(a[y], a[z]):
                swap(result, y)
            elif less(a[x], a[z]):
                swap(result, z)
            else:
                swap(result, x)
        elif less(a[x], a[z]):
            swap(result, x)
        elif less(a[y], a[z]):
            swap(result, z)
        else:
            swap(result, y)

    def partition(first, last, pivot):
        while True:
            while first < n and less(a[first], a[pivot]):
                first += 1
            last -= 1
            while last > 0 and less(a[pivot], a[last]):
                last -= 1
            if not first < last:
                return first
            swap(first, last)
            first += 1

    def adjust_heap(first, hole, length, value):
        top = hole
        child = hole
        while child < (length - 1) // 2:
            child = 2 * (child + 1)
            if less(a[first + child], a[first + child - 1]):
                child -= 1
            a[first + hole] = a[first + child]
            hole = child
        if (length & 1) == 0 and child == (length - 2) // 2:
            child = 2 * (child + 1)
            a[first + hole] = a[first + child - 1]
            hole = child - 1
        parent = (hole - 1) // 2
        while hole > top and less(a[first + parent], value):
            a[first + hole] = a[first + parent]
            hole = parent
            parent = (hole - 1) // 2
        a[first + hole] = value

    def heap_sort(first, last):
        length = last - first
        if length >= 2:
            parent = (length - 2) // 2
            while True:
                adjust_heap(first, parent, length, a[first + parent])
                if parent == 0:
                    break
                parent -= 1
        while last - first > 1:
            last -= 1
            value = a[last]
            a[last] = a[first]
            adjust_heap(first, 0, last - first, value)

    def introsort(first, last, depth):
        while last - first > 16:
            if depth == 0:
                heap_sort(first, last)
                return
            depth -= 1
            mid = first + (last - first) // 2
            median_to_first(first, first + 1, mid, last - 1)
            cut = partition(first + 1, last, first)
            introsort(cut, last, depth)
            last = cut

    def linear_insert(i):
        val = a[i]
        j = i - 1
        while j >= 0 and less(val, a[j]):
            a[i] = a[j]
            i = j
            j -= 1
        a[i] = val

    def insertion(first, last):
        for i in range(first + 1, last):
            if less(a[i], a[first]):
                val = a[i]
                a[first + 1:i + 1] = a[first:i]
                a[first] = val
            else:
                linear_insert(i)

    introsort(0, n, 2 * (n.bit_length() - 1))
    if n > 16:
        insertion(0, 16)
        for i in range(16, n):
            linear_insert(i)
    else:
        insertion(0, n)


def _vertices(geo: list, include_construction: bool):
    """PointConstraints::addGeometry: the start and end of every line, arc, conic arc and B-spline."""
    out = []
    for i, g in enumerate(geo):
        if _construction(g) and not include_construction:
            continue
        if g["type"] in ("LineSegment", "ArcOfCircle", "ArcOfEllipse", "ArcOfHyperbola", "ArcOfParabola",
                         "BSplineCurve"):
            pts = _geo(g).points()
            out.append({"v": pts[START], "geo": i, "pos": START})
            out.append({"v": pts[END], "geo": i, "pos": END})
    return out


def missing_coincidences(geo: list, cons: list[dict], precision: float = CONFUSION * 1000,
                         include_construction: bool = True) -> list[dict]:
    """SketchAnalysis::detectMissingPointOnPointConstraints(precision, includeconstruction): the Coincident
    constraints the sketch lacks between end points closer than precision in x and in y, as
    [{"first", "first_pos", "second", "second_pos", "type": "Coincident", "at": (x, y)}] (cons as fields()).
    Every constraint takes part in the grouping, a Coincident, Tangent or Perpendicular twice, as FreeCAD's does."""
    vs = _vertices(geo, include_construction)
    tol = precision

    def less(x, y):                                     # Vertex_Less
        if abs(x["v"][0] - y["v"][0]) > tol:
            return x["v"][0] < y["v"][0]
        if abs(x["v"][1] - y["v"][1]) > tol:
            return x["v"][1] < y["v"][1]
        return False

    def equal(x, y):                                    # Vertex_EqualTo
        return abs(x["v"][0] - y["v"][0]) <= tol and abs(x["v"][1] - y["v"][1]) <= tol
    _cpp_sort(vs, less)
    allc = list(cons) + [c for c in cons if c["type"] in ("Coincident", "Tangent", "Perpendicular")]
    out = []
    vt = 0
    while vt < len(vs):
        while vt + 1 < len(vs) and not equal(vs[vt], vs[vt + 1]):   # std::adjacent_find
            vt += 1
        if vt + 1 >= len(vs):
            break
        grp = {(vs[vt]["geo"], vs[vt]["pos"]): vs[vt]}  # std::set<VertexIds, VertexID_Less>
        vn = vt + 1
        while vn < len(vs):
            if equal(vs[vt], vs[vn]):
                grp.setdefault((vs[vn]["geo"], vs[vn]["pos"]), vs[vn])
                vn += 1
            else:
                break
        groups: list[dict] = []
        for c in allc:
            k1, k2 = (c["first"], c["first_pos"]), (c["second"], c["second_pos"])
            n1, n2 = grp.pop(k1, None), grp.pop(k2, None)
            if n1 is None and n2 is None:
                temp = None
                for gi, g in enumerate(groups):
                    if k1 in g or k2 in g:
                        if temp is None:
                            temp = g
                        else:
                            temp.update(g)
                            del groups[gi]
                            break
                continue
            for g in groups:
                if k1 in g or k2 in g:
                    if n1 is not None:
                        g.setdefault(k1, n1)
                    if n2 is not None:
                        g.setdefault(k2, n2)
            if n1 is None or n2 is None:
                continue
            groups.append({k1: n1, k2: n2})
        for k in sorted(grp):
            groups.append({k: grp[k]})
        for i in range(1, len(groups)):
            p, q = groups[i - 1][min(groups[i - 1])], groups[i][min(groups[i])]
            out.append({"type": "Coincident", "first": p["geo"], "first_pos": p["pos"], "second": q["geo"],
                        "second_pos": q["pos"], "at": tuple(p["v"])})
        vt = vn
    return out


def coincidence_constraints(missing: list[dict]) -> list[dict]:
    """makeMissingPointOnPointCoincident: the constraints Fix adds (SketchAnalysis::create)."""
    return [args_of({"type": m["type"], "first": m["first"], "first_pos": m["first_pos"], "second": m["second"],
                     "second_pos": m["second_pos"], "third": GEO_UNDEF, "third_pos": NONE, "value": 0.0,
                     "driving": True, "name": "", "alignment": None, "index": -1}) for m in missing]


def open_vertices(geo: list) -> list[tuple]:
    """SketchAnalysis::getOpenVertices: the vertices of the sketch's Shape (its non-construction edges joined into wires
    as SketchObject::buildShape joins them, and its points) that do not have exactly two edges."""
    from . import feature as F
    from .feature_curves import edge as curve_edge
    try:
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS, TopoDS_Compound
        from OCP.BRep import BRep_Builder
        try:
            from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
        except ImportError:
            from OCP.collections import (  # OCP 8 moved OCCT's collections
                IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as
                TopTools_IndexedDataMapOfShapeListOfShape)
    except ImportError as e:            # pragma: no cover
        raise SketchCommandError(f"open vertices need the kernel (OCP): {e}") from None
    edges, points = [], []
    for g in geo:
        if _construction(g):
            continue
        if g["type"] == "Point":
            points.append(tuple(g["at"]))
            continue
        obj = _geo(g)
        edges.append(curve_edge(obj) if isinstance(obj, F._curves.CURVES) else F._edge(obj))
    out = []
    if edges:
        comp = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(comp)
        for w in F._wires(edges):
            b.Add(comp, w)
        m = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(comp, TopAbs_VERTEX, TopAbs_EDGE, m)
        for i in range(1, m.Extent() + 1):
            if m.FindFromIndex(i).Extent() != 2:
                p = BRep_Tool.Pnt_s(TopoDS.Vertex(m.FindKey(i)))
                out.append((p.X(), p.Y()))
    return out + points


def evaluate_constraint(c: dict, n_internal: int, n_external: int) -> bool:
    """SketchObject::evaluateConstraint: First always, Second and Third where the type needs them, within
    -extGeoCount .. intGeoCount (n_external counts the two axes)."""
    need2 = c["type"] in ("Tangent", "Group", "Symmetric", "SnellsLaw")
    need3 = c["type"] in ("Symmetric", "SnellsLaw")

    def ok(g):
        return -n_external <= g < n_internal
    return ok(c["first"]) and ((c["second"] == GEO_UNDEF and not need2) or ok(c["second"])) and \
        ((c["third"] == GEO_UNDEF and not need3) or ok(c["third"]))


def invalid_constraints(geo: list, cons: list[dict], n_external: int = 0) -> list[int]:
    """The constraints evaluateConstraints finds invalid (validateConstraints drops them), by index."""
    return [i for i, c in enumerate(cons) if not evaluate_constraint(c, len(geo), 2 + n_external)]


def _curve_length(g: dict) -> float:
    """GeomCurve::length(first, last)."""
    t = g["type"]
    if t == "LineSegment":
        return math.dist(g["start"], g["end"])
    if t == "Circle":
        return TWO_PI * g["radius"]
    if t == "ArcOfCircle":
        a0, a1 = g["start_angle"], g["end_angle"]
        while a1 < a0:
            a1 += TWO_PI
        return g["radius"] * (a1 - a0)
    from .feature_curves import edge as curve_edge
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(curve_edge(_geo(g)), props)
    return props.Mass()


def degenerated(geo: list, tolerance: float = CONFUSION) -> list[int]:
    """SketchAnalysis::getDegeneratedGeometries: the non-construction curves shorter than tolerance."""
    return [i for i, g in enumerate(geo) if not _construction(g) and g["type"] != "Point"
            and _curve_length(g) < tolerance]


# SketchObject::delGeometry (ui/src/sketchops.ts has the same port, held to FreeCAD by tests/golden/sketchops)
def _involves(c, g):
    return c["first"] == g or c["second"] == g or c["third"] == g


def _involves_pos(c, g, pos):
    return (c["first"] == g and c["first_pos"] == pos) or (c["second"] == g and c["second_pos"] == pos) or \
        (c["third"] == g and c["third_pos"] == pos)


def _substitute(c, fg, fp, tg, tp):
    for k, kp in (("first", "first_pos"), ("second", "second_pos"), ("third", "third_pos")):
        if c[k] == fg and c[kp] == fp:
            c[k], c[kp] = tg, tp


def _directly_coincident(cons, g, pos):
    out = [(g, pos)]
    for c in cons:
        if c["type"] == "Coincident":
            if c["first"] == g and c["first_pos"] == pos:
                out.append((c["second"], c["second_pos"]))
            elif c["second"] == g and c["second_pos"] == pos:
                out.append((c["first"], c["first_pos"]))
        if c["type"] == "Tangent":
            if c["first"] == g and c["first_pos"] == pos and c["second_pos"] in (START, END):
                out.append((c["second"], c["second_pos"]))
            if c["second"] == g and c["second_pos"] == pos and c["first_pos"] in (START, END):
                out.append((c["first"], c["first_pos"]))
    return [] if len(out) == 1 else out


def _transfer(cons, fg, fp, tg, tp):
    out = []
    for c in cons:
        if c["type"] == "InternalAlignment" or not _involves_pos(c, fg, fp) or _involves_pos(c, tg, tp):
            out.append(c)
            continue
        n = dict(c)
        _substitute(n, fg, fp, tg, tp)
        if c["first"] < 0 and c["second"] < 0:
            out.append(c)
            continue
        if c["type"] in ("Tangent", "Perpendicular"):
            n["type"] = "Coincident"
        elif c["type"] == "Angle":
            out.append(c)
            continue
        out.append(n)
    return out


def _del_constraint_on_point(cons, g, pos, only_coincident):
    rg, rp = GEO_UNDEF, NONE
    for c in cons:
        if c["type"] == "Coincident" and _involves_pos(c, g, pos):
            if c["first"] == g and c["first_pos"] == pos:
                rg, rp = c["second"], c["second_pos"]
            else:
                rg, rp = c["first"], c["first_pos"]
            break

    def transfer(c, k, kp):
        if rg == GEO_UNDEF or g != c[k] or pos != c[kp]:
            return False
        c[k], c[kp] = rg, rp
        return True
    out = []
    for c0 in cons:
        if not _involves_pos(c0, g, pos):
            if c0["type"] in ("Distance", "DistanceX", "DistanceY") and c0["first"] == g and \
                    c0["first_pos"] == NONE and pos in (START, END):
                continue
            out.append(c0)
            continue
        c = dict(c0)
        keep = None
        if c["type"] != "Coincident" and only_coincident:
            keep = True
        elif c["type"] == "Coincident":
            if rg == GEO_UNDEF or _involves_pos(c, rg, rp):
                keep = False
            else:
                _substitute(c, g, pos, rg, rp)
                keep = True
        elif c["type"] in ("Distance", "DistanceX", "DistanceY"):
            keep = transfer(c, "first", "first_pos") or transfer(c, "second", "second_pos")
        elif c["type"] == "PointOnObject":
            keep = transfer(c, "first", "first_pos")
        elif c["type"] in ("Tangent", "Perpendicular", "Vertical", "Horizontal", "Symmetric"):
            keep = False
        if keep is None or keep:
            out.append(c)
    return out


def _after_deleting(c, deleted):
    if _involves(c, deleted):
        return None
    n = dict(c)
    for k in ("first", "second", "third"):
        g = n[k]
        n[k] = (g - 1 if g > deleted else g) if deleted >= 0 else (g + 1 if g < deleted and g != GEO_UNDEF else g)
    return n


def _del_exclusive(geo, cons, ids):
    s = sorted(set(ids))
    for g in reversed(s):
        for pos in (START, END, MID):
            lst = _directly_coincident(cons, g, pos)
            if len(lst) > 1:
                cons = _del_constraint_on_point(cons, g, pos, True)
                cons = _transfer(cons, lst[0][0], lst[0][1], lst[1][0], lst[1][1])
    for g in reversed(s):
        cons = [n for n in (_after_deleting(c, g) for c in cons) if n is not None]
    return [x for i, x in enumerate(geo) if i not in s], cons


def del_geometry(geo, cons, g):
    """SketchObject::delGeometry(GeoId) with its default options (UpdateGeometry | IncludeInternalGeometry)."""
    if geo[g]["type"] in ("Ellipse", "ArcOfEllipse", "ArcOfHyperbola", "ArcOfParabola", "BSplineCurve"):
        internal = [c["first"] for c in cons if c["type"] == "InternalAlignment" and c["second"] == g]
        for i in sorted(internal + [g], reverse=True):
            geo, cons = _del_exclusive(geo, cons, [i])
        return geo, cons
    return _del_exclusive(geo, cons, [g])


def remove_degenerated(geo, cons, tolerance: float = CONFUSION):
    """SketchAnalysis::removeDegeneratedGeometries: delGeometry on each, the last first."""
    for g in sorted(degenerated(geo, tolerance), reverse=True):
        geo, cons = del_geometry(geo, cons, g)
    return geo, cons


def constraints_to_external(cons: list[dict]) -> list[int]:
    """The constraints delConstraintsToExternal deletes: those naming external geometry (GeoId -3 or below)."""
    return [i for i, c in enumerate(cons) if not (
        c["first"] > REF_EXT and (c["second"] > REF_EXT or c["second"] == GEO_UNDEF)
        and (c["third"] > REF_EXT or c["third"] == GEO_UNDEF))]


def reversed_external_arcs(external: list[dict], cons: list[dict]):
    """The Reversed External Geometry box: the external arcs of circle whose axis is -Z (their end points), and the
    constraints port_reversedExternalArcs would swap. rebuildExternalGeometry makes every projected arc
    counter-clockwise since FreeCAD 0.15, as cad_agent/feature_attach.py's projection does."""
    pts, rev = [], set()
    for i, g in enumerate(external):
        if g.get("type") == "ArcOfCircle" and g.get("reversed"):
            o = _geo(g).points()
            pts += [o[START], o[END]]
            rev.add(REF_EXT - i)
    n = sum(1 for c in cons if any(gid in rev and p in (START, END) for gid, p in elements(c)))
    return pts, n


def orientation_locking(geo: list, cons: list[dict], lock: bool) -> int:
    """SketchObject::changeConstraintsLocking(bLock)'s count: the Tangent and Perpendicular constraints
    AutoLockTangencyAndPerpty succeeds on (unlocking succeeds on all; locking on those at an end point, not at a
    B-spline knot). Its change does not stay in FreeCAD 26.3 (the loop locks the constraint and then puts the
    unchanged clone back), and the part file does not hold the locking angle, so nothing is written."""
    knots = {c["first"] for c in cons if c["type"] == "InternalAlignment" and c.get("alignment") == "BSplineKnotPoint"}
    n = 0
    for c in cons:
        if c["type"] not in ("Tangent", "Perpendicular"):
            continue
        if not lock:
            n += 1
            continue
        if c["third"] == GEO_UNDEF:
            if c["first"] in knots:
                continue
            pos = c["first_pos"]
        else:
            pos = c["third_pos"]
        if pos != NONE:
            n += 1
    return n


# ── the Body: a part file's sketches as solved, and the ops each command amounts to ─────────────────────────────

def _load(path):
    from .feature_attach import _evaluate_upto, _load as load
    _, features, params, base = load(path)
    shapes, err = _evaluate_upto(features, params, base)
    return features, params, shapes, err


def solved_sketch(path, name: str) -> dict:
    """The sketch as the Body builds it: {"geometry" (solved), "constraints" (the file's), "external" (projected),
    "placement" (attacher.Placement), "params"}; the file's geometry when the Body does not get as far."""
    from .feature_edit import read
    doc = read(path)
    f = next((x for x in doc["features"] if x["name"] == name), None)
    if f is None or f.get("type") != "Sketcher::SketchObject":
        raise SketchCommandError(f"{name!r} is not a sketch of {doc['part']}")
    out = {"name": name, "geometry": f.get("geometry", []), "constraints": f.get("constraints", []),
           "external": [], "placement": None, "params": doc.get("params", {}), "feature": f}
    try:
        features, params, shapes, _ = _load(path)
    except Exception:                   # a part that does not run: what the file holds
        return out
    sk = shapes["_sketches"].get(name)
    if sk is not None:
        out["geometry"] = [g.as_dict() for g in sk.geometry]
        out["external"] = list(getattr(sk, "_external", []) or [])
        pos, rot = sk.placement()
        from . import attacher as A
        out["placement"] = A.Placement(pos, A.Rotation.from_matrix(rot))
    out["params"] = params
    return out


def _next_name(names, base):
    """Document::getUniqueObjectName: base, then base001, base002, ..."""
    if base not in names:
        return base
    i = 1
    while f"{base}{i:03d}" in names:
        i += 1
    return f"{base}{i:03d}"


def body_insert_after(doc: dict):
    """Where Body::addObject puts a new object (insertObject before getNextSolidFeature(), the solid after the Tip;
    at the end when there is none): the name of the feature it goes after."""
    feats = doc["features"]
    if not feats:
        return None
    names = [f["name"] for f in feats]
    tip = doc.get("tip")
    if tip not in names:
        return names[-1]
    solid = lambda f: f["type"] != "Sketcher::SketchObject" and not f["type"].startswith(("Part::Datum", "Part::Local")) \
        and f["type"] not in ("PartDesign::Plane", "PartDesign::Line", "PartDesign::Point", "PartDesign::CoordinateSystem")
    for i in range(names.index(tip) + 1, len(feats)):
        if solid(feats[i]):
            return names[i - 1]
    return names[-1]


def _sketch_feature(name, geometry, constraints, placement, external=None) -> dict:
    """A new Sketcher::SketchObject as feature_edit adds it: no support (MapMode Deactivated) and a Placement."""
    d = {"name": name, "type": "Sketcher::SketchObject", "attachment_support": [], "map_mode": "Deactivated",
         "placement": placement, "geometry": geometry, "constraints": constraints}
    if external:
        d["external_geometry"] = external
    return d


def mirror_ops(path, names: list[str], ref: str = "X") -> dict:
    """Sketcher_MirrorSketch on the named sketches: an add op per sketch, each MirroredSketch placed where its source
    is (Placement printed "%f" by the command)."""
    from .feature_edit import read
    if not names:
        raise SketchCommandError("Wrong selection: Select at least 1 sketch")
    doc = read(path)
    taken = {f["name"] for f in doc["features"]}
    ops, made = [], []
    after = body_insert_after(doc)
    for n in names:
        sk = solved_sketch(path, n)
        m = mirror(sk, ref, sk["params"])
        pl = sk["placement"]
        pos, q = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)) if pl is None else (pl.pos, pl.rot.q)
        from .attacher import Rotation
        pos = tuple(_printed(c) for c in pos)
        q = Rotation(tuple(_printed(c) for c in q)).q
        name = _next_name(taken, "MirroredSketch")
        taken.add(name)
        op = {"op": "add", "feature": _sketch_feature(name, m["geometry"], m["constraints"], placement_value(pos, q))}
        if after is not None:
            op["after"] = after
        after = name
        ops.append(op)
        made.append(name)
    return {"ops": ops, "made": made, "step": "Create a mirrored sketch for each selected sketch"}


def _external_counts(path, sk: dict) -> list[int]:
    """How many geometries each of a sketch's external references projects to (rebuildExternalGeometry)."""
    refs = sk["feature"].get("external_geometry") or []
    if not refs:
        return []
    from .feature_attach import project_query
    try:
        out = project_query(path, sk["name"], [tuple(r) for r in refs])
        return [len(g) for g in out["external"]]
    except Exception:
        return [1] * len(refs)


def merge_ops(path, names: list[str], others: dict | None = None) -> dict:
    """Sketcher_MergeSketches on the named sketches (others: {name: (part path, sketch name)} for sketches of
    another part's Body, whose external geometry is out of scope): one add op, the merged sketch placed as the
    first one is."""
    from .feature_edit import read
    if len(names) < 2:
        raise SketchCommandError("Wrong selection: Select at least 2 sketches")
    doc = read(path)
    others = others or {}
    srcs = []
    for n in names:
        p, sn = others.get(n, (path, n))
        sk = solved_sketch(p, sn)
        sk["external_geometry"] = sk["feature"].get("external_geometry") or []
        sk["external_counts"] = _external_counts(p, sk)
        sk["part_path"] = str(p)
        sk["name"] = sn
        srcs.append(sk)
    one_body = len({s["part_path"] for s in srcs}) == 1
    m = merge(srcs, None, lambda s, r: one_body and s["part_path"] == str(path))     # each with its own PARAMS
    name = _next_name({f["name"] for f in doc["features"]}, "Sketch")
    pl = srcs[0]["placement"]
    from .attacher import Placement
    pl = pl if pl is not None else Placement()
    op = {"op": "add", "feature": _sketch_feature(name, m["geometry"], m["constraints"],
                                                  placement_value(pl.pos, pl.rot.q), m["external_geometry"])}
    after = body_insert_after(doc)
    if after is not None:
        op["after"] = after
    return {"ops": [op], "made": [name], "step": "Merge sketches", "messages": m["messages"],
            "copied": [len(s["constraints"]) for s in srcs]}


def reorient_ops(path, name: str, plane: str, reverse: bool, offset: float) -> dict:
    """Sketcher_ReorientSketch: the sketch detached (when it has a support: "Sketch Has Support", which the caller
    asks first) and placed on the plane. FreeCAD keeps MapMode as it was with AttachmentSupport None, which places
    nothing; the part file says that with map_mode Deactivated."""
    pos, q = reorient(plane, reverse, offset)
    props = {"support": None, "attachment_support": [], "map_mode": "Deactivated", "placement": placement_value(pos, q)}
    return {"ops": [{"op": "set", "name": name, "props": props}], "step": "Reorient sketch",
            "placement": {"position": list(pos), "rotation": list(q)}}


def map_ops(path, name: str, support: list, mode: str | None) -> dict:
    """Sketcher_MapSketch's action: MapMode and AttachmentSupport set ("Attach sketch"), or MapMode Deactivated and no
    support ("Detach sketch"), the Placement left where the attachment last put it."""
    if mode in (None, "Deactivated") or not support:
        sk = solved_sketch(path, name)
        pl = sk["placement"]
        props = {"support": None, "attachment_support": [], "map_mode": "Deactivated"}
        if pl is not None:
            props["placement"] = placement_value(pl.pos, pl.rot.q)
        return {"ops": [{"op": "set", "name": name, "props": props}], "step": "Detach sketch"}
    from .feature_attach import support_list
    refs = support_list(f"Sketch {name}", support)
    return {"ops": [{"op": "set", "name": name, "props": {"support": None, "attachment_support": [list(r) for r in refs],
                                                             "map_mode": mode}}], "step": "Attach sketch"}


def _depends(doc: dict, name: str, on: str, seen=None) -> bool:
    """Whether feature name's out-list, followed through, reaches `on` (DocumentObject::getOutListRecursive)."""
    seen = seen if seen is not None else set()
    feats = {f["name"]: f for f in doc["features"]}
    f = feats.get(name)
    if f is None or name in seen:
        return False
    seen.add(name)

    def names(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from names(x)
        elif isinstance(v, dict):
            for x in v.values():
                yield from names(x)
    refs = {x for k, v in f.items() if k not in ("name", "type", "geometry", "constraints") for x in names(v)}
    refs &= set(feats) - {name}
    return on in refs or any(_depends(doc, r, on, seen) for r in refs)


def map_check(path, name: str, support: list) -> str | None:
    """CmdSketcherMapSketch's refusals for a selection: FreeCAD's message, or None."""
    from .feature_edit import read
    doc = read(path)
    for obj, _ in support:
        if obj == name or _depends(doc, obj, name):
            return ("Some of the selected objects depend on the sketch to be mapped. Circular dependencies are not "
                    "allowed.")
    names = [f["name"] for f in doc["features"]]
    for obj, _ in support:
        if obj in names and name in names and names.index(obj) > names.index(name):
            return (f"{obj} comes after {name} in the Body, and a part file's sketch can only be attached to what comes "
                    f"before it: move {name} after {obj} first")
    return None


def validate(path, name: str, what: str, tolerance: float = CONFUSION * 1000, include_construction: bool = False,
             fix: bool = False) -> dict:
    """The Sketch Validation panel's buttons on a sketch: what Find reports, or (fix) the ops Fix applies, with
    FreeCAD's notification (title, text, kind)."""
    sk = solved_sketch(path, name)
    geo = sk["geometry"]
    file_cons = sk["constraints"]
    params = sk["params"]
    cons = [dict(fields(c, _resolved(c, params)), _i=i) for i, c in enumerate(file_cons)]
    n_ext = len(sk["external"])
    out: dict = {"sketch": name, "what": what}

    def note(kind, title, text):
        out["notification"] = {"kind": kind, "title": title, "text": text}

    def set_op(geometry, constraints, step):
        out["ops"] = [{"op": "set", "name": name, "props": {"geometry": geometry, "constraints": constraints}}]
        out["step"] = step

    if what == "coincidences":
        miss = missing_coincidences(geo, cons, tolerance, include_construction)
        out["missing"] = [{**m, "at": list(m["at"])} for m in miss]
        if fix:
            new = list(file_cons) + coincidence_constraints(miss)
            set_op(_solve(sk, new, params), new, "Add coincident constraint")
        elif miss:
            note("warning", "Missing coincidences", f"{len(miss)} missing coincidences found")
        else:
            note("notification", "No missing coincidences", "No missing coincidences found")
    elif what == "open":
        out["points"] = [list(p) for p in open_vertices(geo)]
    elif what == "constraints":
        bad = invalid_constraints(geo, cons, n_ext)
        out["invalid"] = bad
        if fix:
            new = [c for i, c in enumerate(file_cons) if i not in bad]
            set_op(geo, new, "Validate constraints")
        elif bad:
            note("error", "Invalid constraints", "Invalid constraints found")
        else:
            note("notification", "No invalid constraints", "No invalid constraints found")
    elif what == "external":
        gone = constraints_to_external(cons)
        out["deleted"] = gone
        new = [c for i, c in enumerate(file_cons) if i not in gone]
        set_op(geo, new, "Delete constraints")
        note("notification", "Delete constraints to external geom.",
             "All constraints that deal with external geometry were deleted.")
    elif what == "degenerated":
        bad = degenerated(geo)
        out["degenerated"] = bad
        if fix:
            g2, c2 = remove_degenerated([dict(g) for g in geo], cons)
            kept = _carry_values(file_cons, c2)
            set_op(_solve(sk, kept, params, g2), kept, "Remove degenerated geometry")
        elif bad:
            note("warning", "Degenerated geometry", f"{len(bad)} degenerated geometry found")
        else:
            note("notification", "No degenerated geometry", "No degenerated geometry found")
    elif what == "reversed":
        pts, n = reversed_external_arcs(sk["external"], cons)
        out["points"] = [list(p) for p in pts]
        out["constraints"] = n
        if not pts:
            note("notification", "Reversed external geometry", "No reversed external geometry arcs were found.")
        elif n:
            note("warning", "Reversed external geometry",
                 f"{len(pts) // 2} reversed external geometry arcs were found. Their endpoints are encircled in the "
                 f"3D view.\n\n{n} constraints are linking to the endpoints. The constraints have been listed in the "
                 "report view (menu View -> Panels -> Report view).\n\nClick \"Swap endpoints in constraints\" button "
                 "to reassign endpoints. Do this only once to sketches created in FreeCAD older than v0.15")
        else:
            note("warning", "Reversed external geometry",
                 f"{len(pts) // 2} reversed external geometry arcs were found. Their endpoints are encircled in the "
                 "3D view.\n\nHowever, no constraints linking to the endpoints were found.")
    elif what in ("lock", "unlock"):
        n = orientation_locking(geo, cons, what == "lock")
        out["count"] = n
        note("notification", "Constraint orientation locking",
             f"Orientation locking was enabled and recomputed for {n} constraints. The constraints have been listed "
             "in the report view (menu View → Panels → Report view)." if what == "lock" else
             f"Orientation locking was disabled for {n} constraints. The constraints have been listed in the report "
             "view (menu View → Panels → Report view). Note that for all future constraints, the locking still "
             "defaults to ON.")
    else:
        raise SketchCommandError(f"validate {what!r}: one of coincidences, open, constraints, external, degenerated, "
                                 "reversed, lock, unlock")
    return out


def _carry_values(file_cons, new_fields):
    """The constraints left after a deletion (renumbered fields(), each knowing the file's constraint it came from),
    written back with the file's own values, PARAMS names kept."""
    out = []
    for nf in new_fields:
        d = args_of(nf)
        src = file_cons[nf["_i"]] if "_i" in nf else None
        if src is not None and "value" in d and "value" in src:
            d["value"] = src["value"]
        out.append(d)
    return out


def _solve(sk: dict, constraints: list[dict], params, geometry=None) -> list[dict]:
    """The sketch's geometry after a recompute with these constraints (SketchObject::solve): unchanged when it already
    satisfies them."""
    from .feature import Constraint, FeatureError, Sketch, geometry_from_dict
    geometry = sk["geometry"] if geometry is None else geometry
    try:
        s = Sketch(sk["name"], geometry=[geometry_from_dict(g) for g in geometry],
                   constraints=[Constraint(c["type"], *c["args"], *([c["value"]] if "value" in c else []),
                                           name=c.get("name") or None, driving=c.get("driving", True) is not False)
                                for c in constraints])
        s._external = list(sk.get("external") or [])
        return [g.as_dict() for g in s.solved(params).geometry]
    except (FeatureError, ValueError):
        return geometry


# ── `cad feature mirror | merge | reorient | map | validate` ───────────────────────────────────────────────────

def _run(a, out: dict, words: list[str]):
    from .cmdbase import OK, Result
    from .featurecmd import _cmd, apply_ops
    if a.dry or not out.get("ops"):
        lines = [f"{a.slug}/{a.part}: {out.get('step', a.feature_cmd)} (not written)"] if out.get("ops") else []
        lines += [json.dumps(o) for o in out.get("ops", [])]
        lines += [m.rstrip("\n") for m in out.get("messages", [])]
        if out.get("notification"):
            lines.append(f"{out['notification']['title']}: {out['notification']['text']}")
        return Result(OK, {"project": a.slug, "part": a.part, **out, "line": _cmd(a, *words)}, "\n".join(lines),
                      f"{a.part}: {out.get('step', a.feature_cmd)}")
    r = apply_ops(a, out["ops"], _cmd(a, *words), out["step"])
    r.data.update({k: v for k, v in out.items() if k != "ops"})
    if out.get("messages"):
        r.text = "\n".join([r.text] + [m.rstrip("\n") for m in out["messages"]])
    return r


def _guard(fn):
    def run(a):
        from .cmdbase import UsageError
        from .feature import FeatureError
        try:
            return fn(a)
        except (SketchCommandError, FeatureError) as e:
            raise UsageError(str(e)) from None
    return run


@_guard
def cmd_mirror(a):
    from .cmdbase import part
    out = mirror_ops(part(a.slug, a.part), a.sketches, a.ref)
    return _run(a, out, [*a.sketches, "--ref", a.ref])


@_guard
def cmd_merge(a):
    from .cmdbase import part
    others = {}
    names = []
    for s in a.sketches:
        if "/" in s:                                     # OTHERPART/SKETCH: a sketch of another Body
            p, n = s.split("/", 1)
            others[s] = (part(a.slug, p), n)
        names.append(s)
    out = merge_ops(part(a.slug, a.part), names, others)
    return _run(a, out, list(a.sketches))


@_guard
def cmd_reorient(a):
    from .cmdbase import part
    out = reorient_ops(part(a.slug, a.part), a.sketch, a.plane, a.reverse, a.offset)
    words = [a.sketch, "--plane", a.plane] + (["--reverse"] if a.reverse else []) + \
        (["--offset", repr(a.offset)] if a.offset else [])
    return _run(a, out, words)


@_guard
def cmd_map(a):
    from .cmdbase import part
    path = part(a.slug, a.part)
    sup = [tuple(s.partition(".")[::2]) for s in a.support or []]
    if a.check:                                         # the check before the modes dialog, nothing else
        from .cmdbase import OK, Result
        why = map_check(path, a.sketch, sup)
        return Result(OK, {"project": a.slug, "part": a.part, "sketch": a.sketch, "refusal": why}, why or "ok",
                      f"{a.part}: map check")
    if a.mode not in (None, "Deactivated"):
        why = map_check(path, a.sketch, sup)
        if why:
            raise SketchCommandError(f"Can't map a sketch to support:\n{why}")
    out = map_ops(path, a.sketch, sup, a.mode)
    words = [a.sketch] + [w for s in a.support or [] for w in ("--support", s)] + (["--mode", a.mode] if a.mode else [])
    return _run(a, out, words)


@_guard
def cmd_validate(a):
    from .cmdbase import part
    out = validate(part(a.slug, a.part), a.sketch, a.check, a.tolerance, a.include_construction, a.fix)
    words = [a.sketch, "--check", a.check] + (["--fix"] if a.fix else []) + \
        (["--tolerance", repr(a.tolerance)] if a.tolerance != CONFUSION * 1000 else []) + \
        (["--include-construction"] if a.include_construction else [])
    return _run(a, out, words)


def add_parser(add, fsub) -> None:
    """featurecmd.add_parsers hands its `add` and `cad feature`'s subparsers here."""
    def one(name, func, help):
        sp = add(name, func, help, parent=fsub)
        sp.set_defaults(cmd_name=f"feature {name}", feature_cmd=name)
        sp.add_argument("slug")
        sp.add_argument("part")
        sp.add_argument("--dry", action="store_true", help="answer with the ops, write nothing (the workbench sends them)")
        return sp
    sp = one("mirror", cmd_mirror, "Sketcher_MirrorSketch: a new MirroredSketch for each sketch, mirrored about the "
             "X axis, the Y axis or the origin")
    sp.add_argument("sketches", nargs="+", metavar="SKETCH")
    sp.add_argument("--ref", default="X", choices=tuple(MIRROR_REFS), help="SketchMirrorDialog's choice (default X)")
    sp = one("merge", cmd_merge, "Sketcher_MergeSketches: a new sketch with the geometry and constraints of the "
             "sketches, in this order (OTHERPART/SKETCH for another Body's)")
    sp.add_argument("sketches", nargs="+", metavar="SKETCH")
    sp = one("reorient", cmd_reorient, "Sketcher_ReorientSketch: detach the sketch and place it on a global plane "
             "(SketchOrientationDialog)")
    sp.add_argument("sketch")
    sp.add_argument("--plane", default="XY", choices=("XY", "XZ", "YZ"))
    sp.add_argument("--reverse", action="store_true", help="Reverse direction")
    sp.add_argument("--offset", type=float, default=0.0, help="Offset (mm)")
    sp = one("map", cmd_map, "Sketcher_MapSketch: attach the sketch to references with a mode (no --support, or "
             "--mode Deactivated: detach it)")
    sp.add_argument("sketch")
    sp.add_argument("--support", action="append", metavar="OBJ.ELEMENT")
    sp.add_argument("--mode", help="MapMode (FlatFace, ...)")
    sp.add_argument("--check", action="store_true", help="only say whether the references may take the sketch "
                    "(the circular dependency check), write nothing")
    sp = one("validate", cmd_validate, "Sketcher_ValidateSketch's panel: --check coincidences|open|constraints|"
             "external|degenerated|reversed|lock|unlock, --fix applies the fix")
    sp.add_argument("sketch")
    sp.add_argument("--check", required=True, choices=("coincidences", "open", "constraints", "external", "degenerated",
                                                       "reversed", "lock", "unlock"))
    sp.add_argument("--fix", action="store_true")
    sp.add_argument("--tolerance", type=float, default=CONFUSION * 1000, help="Missing Coincidences' tolerance "
                    "(default 0.0001)")
    sp.add_argument("--include-construction", action="store_true", help="untick Ignore construction geometry")
