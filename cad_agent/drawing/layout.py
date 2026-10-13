"""Putting a plate's two views and its dimensions on a sheet.

A plate is drawn in two views: the face, looked at from the positive side of its thin axis (the view a laser cuts), and
the thickness, from the left in first angle projection or the right in third, standing beside it with its y level with
the face view's. That is every dimension of a prism and every line of it: the face has the outline and the cutouts,
the side shows the thickness and, dashed, that the cutouts go through.

What is dimensioned, and where
------------------------------
  overall width and height   above the face view and to the right of it, arrowed, outermost (ISO 129-1)
  thickness                  above the side view, arrowed, on the line of the overall width
  every cutout's centre      ordinate dimensions from the lower-left corner of the outline, which is marked 0: the x of
                             each below the face view, the y of each to its left, each value at the end of an extension
                             line that starts at the centre. Values that are the same are written once; labels that
                             would touch go on another row (x) or further left (y)
  what each cutout is        a letter beside each, and a list in the notes: `A  4X %%c3.4 THRU`, `B  SLOT 6 X 26 THRU`,
                             `C  WINDOW 27.2 X 19.76 CORNERS R0.4 THRU`; the corner radius of the outline is a note
  the tolerance              the general tolerance of ISO 2768-m, in the notes and the title block

Which sheet and which scale. The smallest of A4 to A0 on which the views and their dimensions fit at 1:1 or larger, at
the largest scale of ISO 5455 up to 5:1 that fits on it; a plate too big for A0 at 1:1 goes on A0 at the largest
reduction that fits. `size` and `scale` fix either, and a plate that does not fit what was fixed is `DoesNotFit`.

The places are in millimetres on the paper (sheet.py), and nothing here reads a clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import dxf
from . import sheet as S
from .plate import Plate, Unfit
from .views import View

TOLERANCE = "ISO 2768-m"
PROCESS_NAMES = {"cnc": "CNC MACHINED", "laser_cut": "LASER CUT"}
BANNER_H = 8.0


class DoesNotFit(Exception):
    """The views and their dimensions do not fit the sheet or the scale that was asked for."""


@dataclass
class Feature:
    kind: str                   # hole | slot | window
    du: float                   # the centre from the datum corner
    dv: float
    w: float                    # its box along u and v
    h: float
    size: tuple                 # what the list says of it: (dia,), (width, length), (w, h, r)
    tag: str = ""


@dataclass
class Group:
    tag: str
    kind: str
    members: list
    text: str


def features(plate: Plate) -> list:
    lo = plate.lo
    out = []
    for f in plate.holes:
        out.append(Feature("hole", f.u - lo[0], f.v - lo[1], f.dia, f.dia, (f.dia,)))
    for f in plate.slots:
        w, h = (f.length, f.width) if f.along == "u" else (f.width, f.length)
        out.append(Feature("slot", f.u - lo[0], f.v - lo[1], w, h, (f.width, f.length, f.along)))
    for f in plate.windows:
        out.append(Feature("window", f.u - lo[0], f.v - lo[1], f.w, f.h, (f.w, f.h, f.r)))
    return out


def _key(f: Feature) -> tuple:
    return ({"hole": 0, "slot": 1, "window": 2}[f.kind],) + tuple(round(x, 2) if isinstance(x, float) else x for x in f.size)


def callout(kind: str, n: int, size: tuple) -> str:
    count = f"{n}X " if n > 1 else ""
    if kind == "hole":
        return f"{count}%%c{S.fmt(size[0])} THRU"
    if kind == "slot":
        return f"{count}SLOT {S.fmt(size[0])} X {S.fmt(size[1])} THRU"
    corners = f" CORNERS R{S.fmt(size[2])}" if size[2] else ""
    return f"{count}WINDOW {S.fmt(size[0])} X {S.fmt(size[1])}{corners} THRU"


def grouped(feats: list) -> list:
    """The features in groups of one kind and size, lettered A, B, C ... (the letters go on the features too)."""
    by: dict = {}
    for f in sorted(feats, key=lambda f: (_key(f), f.dv, f.du)):
        by.setdefault(_key(f), []).append(f)
    if len(by) > len(S.TAGS):
        raise Unfit(f"it has {len(by)} different sizes of cutout and the sheet has letters for {len(S.TAGS)}")
    out = []
    for letter, (key, members) in zip(S.TAGS, by.items()):
        for f in members:
            f.tag = letter
        out.append(Group(letter, members[0].kind, members, callout(members[0].kind, len(members), members[0].size)))
    return out


def place(p, ox: float, oy: float, s: float):
    """An entity of a view on the paper: scaled by s, then moved so that (0, 0) of the view lands on (ox, oy)."""
    def t(pt):
        return dxf.snap2((ox + pt[0] * s, oy + pt[1] * s))

    if isinstance(p, dxf.Line):
        return dxf.Line(*sorted((t(p.a), t(p.b))))
    if isinstance(p, dxf.Circle):
        return dxf.Circle(t(p.c), dxf.snap(p.r * s))
    if isinstance(p, dxf.Arc):
        return dxf.Arc(t(p.c), dxf.snap(p.r * s), p.a0, p.a1)
    if isinstance(p, dxf.Ellipse):
        return dxf.Ellipse(t(p.c), dxf.snap2((p.major[0] * s, p.major[1] * s)), p.ratio, p.t0, p.t1)
    if isinstance(p, dxf.Spline):
        return dxf.Spline(p.degree, p.knots, tuple(t(q) for q in p.poles))
    return dxf.Poly(tuple(t(q) for q in p.points), p.closed)


# ─── The room things take ────────────────────────────────────────────────────

@dataclass
class Labels:
    """The ordinate labels of one axis: (text, value from the datum, where the extension line starts)."""
    items: list = field(default_factory=list)

    def texts(self) -> list:
        return [t for t, _, _ in self.items]


def ordinates(feats: list) -> tuple:
    """(labels along u, labels along v), the datum 0 first, each value once."""
    if not feats:
        return Labels(), Labels()
    out = []
    for axis in (0, 1):
        seen: dict = {"0": [0.0, 0.0]}
        for f in feats:
            val = f.du if axis == 0 else f.dv
            other = f.dv if axis == 0 else f.du
            text = S.fmt(val)
            if text in seen:
                seen[text][1] = max(seen[text][1], other)
            else:
                seen[text] = [val, other]
        out.append(Labels([(t, v, o) for t, (v, o) in sorted(seen.items(), key=lambda kv: kv[1][0])]))
    return out[0], out[1]


@dataclass
class Plan:
    """The room around the face view at one scale, and the rows its labels go on."""
    lz: float
    bz: float
    tz: float
    rz: float
    levels_u: list
    levels_v: list
    wv: float                   # the widest label along v
    need_w: float
    need_h: float


def plan_for(plate: Plate, feats: list, labs: tuple, s: float, banner: bool) -> Plan:
    lu, lv = labs
    w, h, t = plate.width * s, plate.height * s, plate.thickness * s
    spans_u = [(v * s - S.text_width(txt, S.TEXT_H) / 2.0, v * s + S.text_width(txt, S.TEXT_H) / 2.0) for txt, v, _ in lu.items]
    spans_v = [(v * s - 1.3, v * s + 1.3) for _, v, _ in lv.items]
    levels_u = S.schedule(spans_u, 1.5)
    levels_v = S.schedule(spans_v, 1.5)
    nu, nv = (max(levels_u) + 1 if levels_u else 0), (max(levels_v) + 1 if levels_v else 0)
    wv = max((S.text_width(txt, S.TEXT_H) for txt, _, _ in lv.items), default=0.0)
    lz = 8.0 if not nv else 5.0 + (nv - 1) * (wv + 3.0) + 1.0 + wv + 4.0
    bz = 8.0 if not nu else 5.0 + (nu - 1) * S.LEVEL + 3.6 + 4.0
    tz = 18.0
    t_text = S.fmt(plate.thickness)
    outside = t < S.text_width(t_text, S.TEXT_H) + 1.0
    rz = (S.ARROW + 2.5 + S.text_width(t_text, S.TEXT_H) + 3.0) if outside else 6.0
    return Plan(lz, bz, tz, rz, levels_u, levels_v, wv, lz + w + S.GAP_VIEWS + t + rz, bz + h + tz)


def choose(plate: Plate, feats: list, labs: tuple, band: float, banner: bool, size: str | None, scale: tuple | None) -> tuple:
    """(sheet size, scale, plan) by the rule of the module docstring."""
    def fits(sz: str, sc: tuple) -> Plan | None:
        x0, y0, x1, y1 = S.drawing_space(sz)
        va_w, va_h = (x1 - x0) - 10.0, (y1 - y0) - band - 5.0 - (BANNER_H + 4.0 if banner else 0.0)
        p = plan_for(plate, feats, labs, sc[0] / sc[1], banner)
        return p if p.need_w <= va_w and p.need_h <= va_h else None

    sizes = [size] if size else list(S.SIZES)
    enlarge = [sc for sc in S.SCALES if sc[0] >= sc[1] and sc[0] / sc[1] <= S.MAX_ENLARGE]
    reduce = [sc for sc in S.SCALES if sc[0] < sc[1]]
    if scale:
        for sz in sizes:
            p = fits(sz, scale)
            if p:
                return sz, scale, p
        raise DoesNotFit(f"the views and their dimensions do not fit {', '.join(sizes)} at {S.scale_text(scale)}")
    candidates = [(sz, sc) for sz in sizes for sc in enlarge] + [(sz, sc) for sz in sizes for sc in reduce] if size else (
        [(sz, sc) for sz in sizes for sc in enlarge] + [(sizes[-1], sc) for sc in reduce])
    for sz, sc in candidates:
        p = fits(sz, sc)
        if p:
            return sz, sc, p
    raise DoesNotFit(f"the views and their dimensions do not fit {sizes[-1]} even at 1:1000")


# ─── The sheet ───────────────────────────────────────────────────────────────

def build(plate: Plate, face: View, side: View, meta: dict, angle: str = "first", size: str | None = None,
          scale: tuple | None = None) -> S.Sheet:
    """The sheet of a plate: `face` and `side` are its views (views.project), `meta` the title block's facts: part,
    project, material, process, commit, dirty and stamp ("NOT VERIFIED" or None)."""
    feats = features(plate)
    if len(feats) > S.MAX_FEATURES:
        raise Unfit(f"it has {len(feats)} cutouts and a sheet takes {S.MAX_FEATURES}; more would want a hole table")
    groups = grouped(feats)
    stamp = meta.get("stamp")
    notes = [f"{g.tag}  {g.text}" for g in groups]
    if plate.corner_r > 0:
        notes.append(f"ALL OUTLINE CORNERS R{S.fmt(plate.corner_r)}")
    if feats:
        notes.append("ORDINATES FROM LOWER LEFT CORNER")
    notes += ["DIMENSIONS IN mm", f"GENERAL TOLERANCES {TOLERANCE}"]
    band = max(S.TITLE_H, 6.0 + 5.0 * len(notes)) + 5.0
    labs = ordinates(feats)
    sz, sc, plan = choose(plate, feats, labs, band, bool(stamp), size, scale)
    s = sc[0] / sc[1]

    w, h = S.SIZES[sz]
    sh = S.Sheet(sz, w, h, sc, angle, stamp)
    space = S.frame(sh)
    x0, y0, x1, y1 = space
    S.title_block(sh, space, {
        "part": meta["part"], "number": f"{meta['project']}/{meta['part']}",
        "material": (meta.get("material") or "NOT DECLARED").upper(),
        "process": PROCESS_NAMES.get(meta.get("process"), (meta.get("process") or "NOT DECLARED").upper()),
        "scale": S.scale_text(sc), "size": f"{sz}   1/1", "commit": _commit(meta),
        "status": "NOT VERIFIED" if stamp else "VERIFIED", "status_ok": not stamp, "tolerance": TOLERANCE})
    sh.title = {"part": meta["part"], "scale": S.scale_text(sc), "size": sz, "status": "NOT VERIFIED" if stamp else "VERIFIED"}

    # the notes, left of the title block, from the top of the band down
    note_top = y0 + band - 5.0 - 6.0
    room = (space[2] - S.TITLE_W) - (x0 + 4.0) - 3.0
    for i, line in enumerate(notes):
        sh.text("TEXT", (x0 + 4.0, note_top - 5.0 * i), S.fitted(line, room, S.TEXT_H, 2.5), line)
    sh.notes = notes

    # the room the views take, centred in what is left of the drawing space
    va_x0, va_x1 = x0 + 5.0, x1 - 5.0
    va_y0, va_y1 = y0 + band, y1 - 5.0 - (BANNER_H + 4.0 if stamp else 0.0)
    gx = va_x0 + ((va_x1 - va_x0) - plan.need_w) / 2.0
    gy = va_y0 + ((va_y1 - va_y0) - plan.need_h) / 2.0
    fx, fy = gx + plan.lz, gy + plan.bz
    fw, fh, ft = plate.width * s, plate.height * s, plate.thickness * s
    sx = fx + fw + S.GAP_VIEWS
    sh.zero = (fx, fy)
    sh.regions["face"] = (fx, fy, fx + fw, fy + fh)
    sh.regions["side"] = (sx, fy, sx + ft, fy + fh)
    if stamp:
        sh.text(dxf.STAMP_LAYER, ((va_x0 + va_x1) / 2.0, va_y1 + 4.0), BANNER_H, stamp, 0.0, 1)

    # the views
    ox, oy = fx - plate.lo[0] * s, fy - plate.lo[1] * s
    for p in face.visible:
        sh.add("VISIBLE", place(p, ox, oy, s))
    for p in face.hidden:
        sh.add("HIDDEN", place(p, ox, oy, s))
    side_ox = sx - side.box[0] * s
    for p in side.visible:
        sh.add("VISIBLE", place(p, side_ox, oy, s))
    for p in side.hidden:
        sh.add("HIDDEN", place(p, side_ox, oy, s))

    # centre marks: a cross on each hole, the axis of each slot, the axis of each hole in the side view
    for f in feats:
        cx, cy = fx + f.du * s, fy + f.dv * s
        if f.kind == "hole":
            r = f.w * s / 2.0 + (2.5 if f.w * s >= 4.0 else 1.5)
            sh.line("CENTRE", (cx - r, cy), (cx + r, cy))
            sh.line("CENTRE", (cx, cy - r), (cx, cy + r))
        elif f.kind == "slot":
            if f.w >= f.h:
                sh.line("CENTRE", (cx - f.w * s / 2.0 - 2.5, cy), (cx + f.w * s / 2.0 + 2.5, cy))
            else:
                sh.line("CENTRE", (cx, cy - f.h * s / 2.0 - 2.5), (cx, cy + f.h * s / 2.0 + 2.5))
    for f in sorted({round(f.dv, 4): f for f in feats if f.kind == "hole" and f.w * s >= 1.5}.values(), key=lambda f: f.dv):
        sh.line("CENTRE", (sx - 2.5, fy + f.dv * s), (sx + ft + 2.5, fy + f.dv * s))

    # the letters of the features
    for f in feats:
        cx, cy = fx + f.du * s, fy + f.dv * s
        if f.kind == "hole":
            d = (f.w * s / 2.0 + 1.0) * 0.7071
            at = (cx + d, cy + d)
        else:
            at = (cx + f.w * s / 2.0 + 1.0, cy + f.h * s / 2.0 + 1.0)
        sh.text("TEXT", at, S.TEXT_H, f.tag)

    # overall sizes, outermost
    top = fy + fh + 10.0
    S.dim_horizontal(sh, fx, fx + fw, top, fy + fh, S.fmt(plate.width))
    sh.dims.append({"kind": "overall_u", "value": plate.width, "text": S.fmt(plate.width)})
    S.dim_vertical(sh, fy, fy + fh, fx + fw + 10.0, fx + fw, S.fmt(plate.height))
    sh.dims.append({"kind": "overall_v", "value": plate.height, "text": S.fmt(plate.height)})
    S.dim_horizontal(sh, sx, sx + ft, top, fy + fh, S.fmt(plate.thickness))
    sh.dims.append({"kind": "thickness", "value": plate.thickness, "text": S.fmt(plate.thickness)})

    # ordinates: the x of each cutout under the face view, the y of each to its left
    lu, lv = labs
    base_y, base_x = fy - 5.0, fx - 5.0
    for (text, val, start), level in zip(lu.items, plan.levels_u):
        x = fx + val * s
        end = base_y - level * S.LEVEL
        sh.line("DIM_ORD", (x, fy + start * s), (x, end))
        sh.text("DIM_ORD", (x, end - 3.6), S.TEXT_H, text, 0.0, 1)
        sh.dims.append({"kind": "ord_u", "value": val, "text": text})
    for (text, val, start), level in zip(lv.items, plan.levels_v):
        y = fy + val * s
        end = base_x - level * (plan.wv + 3.0)
        sh.line("DIM_ORD", (fx + start * s, y), (end, y))
        sh.text("DIM_ORD", (end - 1.0, y - 1.3), S.TEXT_H, text, 0.0, 2)
        sh.dims.append({"kind": "ord_v", "value": val, "text": text})
    for g in groups:
        sh.dims.append({"kind": "group", "tag": g.tag, "what": g.kind, "count": len(g.members), "text": g.text,
                        "size": list(g.members[0].size)})
    sh.dims.append({"kind": "corner", "value": plate.corner_r, "text": S.fmt(plate.corner_r)})
    return sh


def _commit(meta: dict) -> str:
    commit = meta.get("commit")
    if not commit:
        return "NONE (NOT IN GIT)"
    return commit[:12] + (" +UNCOMMITTED" if meta.get("dirty") else "")
