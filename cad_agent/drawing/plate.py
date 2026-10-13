"""What `cad drawing` can draw: a plate, and everything a plate has recognised from its B-rep.

A plate here is a prism along its thinnest axis whose features all go through: the outline is a rectangle (sharp or
with one corner radius) and the cutouts are round holes, slots (obrounds) and rectangular windows with or without
corner radius, all with their sides along the part's own axes. That is a laser-cut sheet and the flat machined plate
of a bracket. Anything else (a pocket, a step, a chamfer, a counterbore, a blind hole, a cross hole, a fillet on the
top edge, an L-shaped outline, a slanted slot, a cutout of free form) is `Unfit`, with the sentence that says what
was found, and no drawing is made of it. The plan's scope is "machined plates only, no sections and no GD&T", and a
plate with a pocket needs a section to be understood.

How a plate is recognised
-------------------------
  scope        `dxf.through_cut`'s faces (piece D's laser rule): every face is an end plane or runs along the
               thickness. D wrote it to say a laser can cut the part; here it says a drawing of two views is the
               whole part, and its sentences are reused for what is wrong
  outline      the loops of the top end face (`dxf.end_cut`), as the entities FreeCAD's exportShape makes of the
               edges (lines, circles, arcs). A loop is recognised by building what it should be from its bounding
               box (a rounded rectangle, an obround, a circle) and comparing that with what the face has, entity by
               entity within 1e-4 mm. A loop that is not one of those is Unfit; nothing is guessed
  holes        `spec.holes`, the hole finder of the [[interface]] rule: the cylinders of one radius on one axis that turn
               270 degrees or more, and a slot from two half turns. They must be the same holes, one for one, as the
               circles and obrounds the outline found, or the plate is Unfit: two readings of one part that disagree
               are not drawn
  frame        the one `dxf` uses for a laser part (`dxf.FRAMES`): the face is looked at from the positive side of its
               thin axis, and the sheet's x and y are the part's other two axes, so a plate's face view is its DXF

`reconstruct` is the check that makes this honest. It takes the numbers a sheet prints (as the text the sheet shows,
rounded the way it prints them), builds the plate they describe, and compares it with the plate's end face:
the area that is in one and not the other, both ways, must be nothing within what the rounding allows. A hole that
is left out, a window misread as a hole or a number that does not belong to the part cannot get through it.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .. import dxf

TOL = 1e-4                  # mm: entities of an outline and of a rebuilt one are the same within this
FULL = 360.0


class Unfit(Exception):
    """A part `cad drawing` does not draw; the message says what was found and why it is not a plate."""


@dataclass(frozen=True)
class Hole:
    u: float
    v: float
    dia: float


@dataclass(frozen=True)
class Slot:
    """An obround through the plate. `along` is the axis its length runs on ("u" or "v"); `length` is overall."""
    u: float
    v: float
    width: float
    length: float
    along: str


@dataclass(frozen=True)
class Window:
    """A rectangle through the plate; `r` is the radius of its four corners (0 for sharp ones)."""
    u: float
    v: float
    w: float
    h: float
    r: float


@dataclass
class Plate:
    axis: int
    frame: dxf.Frame
    thickness: float
    lo: tuple                       # the outline's lower-left corner in the face frame (u, v): the datum
    hi: tuple
    corner_r: float
    holes: list = field(default_factory=list)
    slots: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    n_range: tuple = (0.0, 0.0)     # the part along its thin axis, as p . n
    top: list = field(default_factory=list)         # the end faces the outline was read from
    source: str = ""

    @property
    def width(self) -> float:
        return self.hi[0] - self.lo[0]

    @property
    def height(self) -> float:
        return self.hi[1] - self.lo[1]

    def features(self) -> int:
        return len(self.holes) + len(self.slots) + len(self.windows)

    def describe(self) -> str:
        name = dxf.AXIS_NAME[self.axis]
        bits = [f"{self.width:g} x {self.height:g} x {self.thickness:g} mm, thin in {name}"]
        if self.corner_r:
            bits.append(f"corners R{self.corner_r:g}")
        for n, word in ((len(self.holes), "hole"), (len(self.slots), "slot"), (len(self.windows), "window")):
            if n:
                bits.append(f"{n} {word}{'' if n == 1 else 's'}")
        return ", ".join(bits)


# ─── Recognising a loop ──────────────────────────────────────────────────────

def bbox(prims) -> tuple:
    xs, ys = zip(*(pt for p in prims for pt in dxf.extent_points(p)))
    return min(xs), min(ys), max(xs), max(ys)


def _line(a, b):
    if math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-9:
        return []
    return [dxf.Line(*sorted((dxf.snap2(a), dxf.snap2(b))))]


def rounded_rectangle(x0, y0, x1, y1, r) -> list:
    """The entities of a rectangle with equal corner radius r (sharp for 0), as the outline of a face has them."""
    out = (_line((x0 + r, y0), (x1 - r, y0)) + _line((x0 + r, y1), (x1 - r, y1))
           + _line((x0, y0 + r), (x0, y1 - r)) + _line((x1, y0 + r), (x1, y1 - r)))
    if r > 0:
        out += [dxf.Arc(dxf.snap2((x0 + r, y0 + r)), dxf.snap(r), 180.0, 270.0),
                dxf.Arc(dxf.snap2((x1 - r, y0 + r)), dxf.snap(r), 270.0, 0.0),
                dxf.Arc(dxf.snap2((x1 - r, y1 - r)), dxf.snap(r), 0.0, 90.0),
                dxf.Arc(dxf.snap2((x0 + r, y1 - r)), dxf.snap(r), 90.0, 180.0)]
    return out


def obround(x0, y0, x1, y1) -> list:
    """An obround filling the box: the long way is its length, the short its width, and its ends are half turns."""
    w, h = x1 - x0, y1 - y0
    if abs(w - h) < 1e-9:
        return [dxf.Circle(dxf.snap2(((x0 + x1) / 2, (y0 + y1) / 2)), dxf.snap(w / 2))]
    if w > h:
        r, cy = h / 2, (y0 + y1) / 2
        return (_line((x0 + r, y0), (x1 - r, y0)) + _line((x0 + r, y1), (x1 - r, y1))
                + [dxf.Arc(dxf.snap2((x1 - r, cy)), dxf.snap(r), 270.0, 90.0),
                   dxf.Arc(dxf.snap2((x0 + r, cy)), dxf.snap(r), 90.0, 270.0)])
    r, cx = w / 2, (x0 + x1) / 2
    return (_line((x0, y0 + r), (x0, y1 - r)) + _line((x1, y0 + r), (x1, y1 - r))
            + [dxf.Arc(dxf.snap2((cx, y1 - r)), dxf.snap(r), 0.0, 180.0),
               dxf.Arc(dxf.snap2((cx, y0 + r)), dxf.snap(r), 180.0, 0.0)])


def merged(prims) -> list:
    """The entities of a loop with the arcs of one circle joined (OCCT may cut a half turn in two at a seam)."""
    arcs: dict = {}
    rest = []
    for p in prims:
        if isinstance(p, dxf.Arc):
            arcs.setdefault((round(p.c[0], 4), round(p.c[1], 4), round(p.r, 4)), []).append(p)
        else:
            rest.append(p)
    for group in arcs.values():
        spans = sorted(((a.a0, (a.a1 - a.a0) % FULL or FULL) for a in group))
        a0, sweep = spans[0]
        joined = []
        for s0, sw in spans[1:]:
            if abs((a0 + sweep) % FULL - s0 % FULL) < 1e-4:
                sweep += sw
            else:
                joined.append((a0, sweep))
                a0, sweep = s0, sw
        joined.append((a0, sweep))
        if len(joined) > 1 and abs((joined[-1][0] + joined[-1][1]) % FULL - joined[0][0] % FULL) < 1e-4:
            first = joined.pop(0)                       # the last span runs on into the first
            joined[-1] = (joined[-1][0], joined[-1][1] + first[1])
        for s0, sw in joined:
            c, r = group[0].c, group[0].r
            if sw >= FULL - 1e-4:
                rest.append(dxf.Circle(c, r))
            else:
                rest.append(dxf.Arc(c, r, dxf.angle(s0), dxf.angle(s0 + sw)))
    return rest


def _numbers(p) -> list:
    return list(dxf._flat(p))


def same_entities(a, b, tol: float = TOL) -> bool:
    """Whether two lists of entities are the same ones, of the same kinds, each within `tol` of its partner."""
    if len(a) != len(b):
        return False
    left = list(b)
    for p in a:
        for i, q in enumerate(left):
            if type(p) is type(q) and all(abs(x - y) <= tol for x, y in zip(_numbers(p), _numbers(q))):
                del left[i]
                break
        else:
            return False
    return True


def recognise(prims, outer: bool):
    """('rect', box, r), ('round', box, d), ('obround', box, None) or None for a loop that is nothing the drawing can
    dimension. The box is (x0, y0, x1, y1)."""
    have = merged(prims)
    x0, y0, x1, y1 = bbox(have)
    arcs = [p for p in have if isinstance(p, dxf.Arc)]
    if len(have) == 1 and isinstance(have[0], dxf.Circle):
        return ("round", (x0, y0, x1, y1), x1 - x0)
    r = arcs[0].r if arcs else 0.0
    if outer or r > 0 or all(isinstance(p, dxf.Line) for p in have):
        if same_entities(have, rounded_rectangle(x0, y0, x1, y1, r)):
            return ("rect", (x0, y0, x1, y1), r)
    if len(arcs) == 2 and same_entities(have, obround(x0, y0, x1, y1)):
        return ("obround", (x0, y0, x1, y1), None)
    return None


def _kinds(prims) -> str:
    c = Counter(dxf.kind(p).lower() for p in prims)
    return ", ".join(f"{n} {k}{'' if n == 1 else 's'}" for k, n in sorted(c.items()))


# ─── The plate ───────────────────────────────────────────────────────────────

def _unfit_faces(solid, mid, name: str):
    """(faces, end) or Unfit saying what a laser rule would call not a through-cut, put as a drawing's complaint."""
    try:
        faces = dxf.faces_report(solid, mid.frame.axis)
        verdict = dxf.through_cut(solid, mid)
    except Exception as e:      # noqa: BLE001 - say what could not be settled
        raise Unfit(f"its faces could not be sorted: {type(e).__name__}: {e}") from None
    if faces.bad:
        said = Counter(faces.bad)
        shown = "; ".join((f"{n} x " if n > 1 else "") + text for text, n in list(said.items())[:3])
        more = f"; and {len(said) - 3} other kinds" if len(said) > 3 else ""
        raise Unfit(f"it is not a prism along {name}: it has {shown}{more}. A plate here is an outline cut all the way "
                    f"through its thickness, and anything else needs a section to be understood")
    if verdict.state != "PASS":
        raise Unfit("it is not a prism along " + name + ": " + verdict.measured.removeprefix("not a through-cut: "))
    return faces


def analyse(solid) -> Plate:
    """The Plate a solid is, or Unfit saying why it is not one (see the module docstring)."""
    try:
        mid = dxf.cut_at(solid)
    except Exception as e:      # noqa: BLE001
        raise Unfit(f"its mid-plane section could not be made: {type(e).__name__}: {e}") from None
    if mid.thickness <= 0 or mid.area <= 0:
        raise Unfit("its mid-plane cuts no material, so there is no outline to draw")
    axis = mid.frame.axis
    name = dxf.AXIS_NAME[axis]
    faces = _unfit_faces(solid, mid, name)
    if not faces.top or faces.unknown:
        raise Unfit(f"its end faces across {name} are not planes the outline can be read from"
                    + (f" ({faces.unknown} faces are B-spline surfaces)" if faces.unknown else ""))
    end = dxf.end_cut(solid, mid, faces)
    loops = dxf.loops_of(end)
    outers = [prims for is_outer, prims in loops if is_outer]
    if len(outers) != 1:
        raise Unfit(f"its outline is {len(outers)} separate pieces, and a plate here is one")
    kind, box, r = recognise(outers[0], True) or (None, None, None)
    if kind != "rect":
        raise Unfit("its outline is not a rectangle with square or equally rounded corners "
                    f"({_kinds(outers[0])}); a plate here has a rectangular outline")
    x0, y0, x1, y1 = box
    plate = Plate(axis, end.frame, mid.thickness, (x0, y0), (x1, y1), r, source=end.where())
    plate.top = list(faces.top)
    for is_outer, prims in loops:
        if is_outer:
            continue
        got = recognise(prims, False)
        if got is None:
            raise Unfit(f"it has a cutout that is not a round hole, a slot or a rectangle with equal corners "
                        f"({_kinds(prims)} at {bbox(prims)[0]:.2f}, {bbox(prims)[1]:.2f}); only those are dimensioned")
        what, (a0, b0, a1, b1), extra = got
        cu, cv = (a0 + a1) / 2, (b0 + b1) / 2
        if what == "round":
            plate.holes.append(Hole(dxf.snap(cu), dxf.snap(cv), dxf.snap(extra)))
        elif what == "obround":
            along = "u" if (a1 - a0) > (b1 - b0) else "v"
            plate.slots.append(Slot(dxf.snap(cu), dxf.snap(cv), dxf.snap(min(a1 - a0, b1 - b0)),
                                    dxf.snap(max(a1 - a0, b1 - b0)), along))
        else:
            plate.windows.append(Window(dxf.snap(cu), dxf.snap(cv), dxf.snap(a1 - a0), dxf.snap(b1 - b0), dxf.snap(extra)))
    _check_holes(solid, plate)
    lo, hi = _box(solid)
    n = plate.frame.n
    corners = [sum(c[i] * n[i] for i in range(3)) for c in _corners(lo, hi)]
    plate.n_range = (min(corners), max(corners))
    for group in (plate.holes, plate.slots, plate.windows):
        group.sort(key=lambda f: (f.v, f.u))
    return plate


def _box(solid):
    from ..geom import bbox as solid_bbox
    return solid_bbox(solid)


def _corners(lo, hi):
    return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def _check_holes(solid, plate: Plate) -> None:
    """The hole finder of [[interface]] and the outline must find the same round holes and slots, one for one."""
    from ..spec import holes as find
    u, v, n = plate.frame.u, plate.frame.v, plate.frame.n

    def at(p) -> tuple:
        return (p.X * u[0] + p.Y * u[1] + p.Z * u[2], p.X * v[0] + p.Y * v[1] + p.Z * v[2])

    found_holes, found_slots = [], []
    for h in find(solid):
        d = h["dir"]
        if abs(d.X * n[0] + d.Y * n[1] + d.Z * n[2]) < 1 - 1e-6:
            raise Unfit(f"the hole finder reports a {h['kind']} that does not run along the thin axis: not a plate")
        if len(h["bores"]) > 1:
            raise Unfit(f"the hole finder reports a stepped hole (bores {', '.join(f'{b:g}' for b in h['bores'])}): "
                        "a counterbore needs a section")
        if h["kind"] == "hole":
            found_holes.append((at(h["point"]), h["dia"]))
        else:
            found_slots.append((at(h["point"]), h["dia"], (h["ends"][1] - h["ends"][0]).length + h["dia"]))
    mine = sorted(((x.u, x.v), x.dia) for x in plate.holes)
    theirs = sorted(found_holes)
    if len(mine) != len(theirs) or any(abs(a[0][0] - b[0][0]) > TOL or abs(a[0][1] - b[0][1]) > TOL or abs(a[1] - b[1]) > TOL
                                       for a, b in zip(mine, theirs)):
        raise Unfit(f"the outline has {len(mine)} round holes and the hole finder {len(theirs)}, or they differ in place "
                    "or size: two readings of the part that disagree are not drawn")
    mine_s = sorted(((s.u, s.v), s.width, s.length) for s in plate.slots)
    theirs_s = sorted(found_slots)
    if len(mine_s) != len(theirs_s) or any(abs(a[0][0] - b[0][0]) > TOL or abs(a[0][1] - b[0][1]) > TOL
                                           or abs(a[1] - b[1]) > TOL or abs(a[2] - b[2]) > TOL for a, b in zip(mine_s, theirs_s)):
        raise Unfit(f"the outline has {len(mine_s)} slots and the hole finder {len(theirs_s)}, or they differ in place "
                    "or size: two readings of the part that disagree are not drawn")


# ─── The check: a plate rebuilt from what a sheet prints ─────────────────────

def rebuilt(values: dict):
    """The plate described by printed numbers, as a build123d sketch in the datum frame (lower-left corner at 0, 0).

    `values` holds `w`, `h`, `r` for the outline, and `holes` [(u, v, dia)], `slots` [(u, v, width, length, along)],
    `windows` [(u, v, w, h, r)], every one a number as printed.
    """
    from build123d import Circle, Pos, Rectangle, RectangleRounded, SlotOverall
    w, h, r = values["w"], values["h"], values["r"]
    base = Pos(w / 2, h / 2) * (RectangleRounded(w, h, r) if r > 0 else Rectangle(w, h))
    for u, v, d in values["holes"]:
        base = base - Pos(u, v) * Circle(d / 2)
    for u, v, width, length, along in values["slots"]:
        base = base - Pos(u, v) * SlotOverall(length, width, rotation=0 if along == "u" else 90)
    for u, v, ww, hh, rr in values["windows"]:
        base = base - Pos(u, v) * (RectangleRounded(ww, hh, rr) if rr > 0 else Rectangle(ww, hh))
    return base


def reconstruct(plate: Plate, values: dict) -> tuple:
    """(area in one and not the other, mm^2; the most the printing may account for, mm^2) for the plate and the
    plate `values` describe, both put in the face frame.

    The printed numbers are rounded, so every boundary may have moved by up to half of the last place; the allowance
    is that distance along the whole boundary.
    """
    from build123d import Compound, Plane, Vector
    u, v, n = plate.frame.u, plate.frame.v, plate.frame.n
    origin = Vector(*(plate.frame.origin[i] + plate.lo[0] * u[i] + plate.lo[1] * v[i] for i in range(3)))
    sketch = rebuilt(values)
    placed = Plane(origin=origin, x_dir=Vector(*u), z_dir=Vector(*n)) * sketch
    actual = Compound(plate.top)
    less = sum(f.area for f in actual.cut(placed).faces()) if actual.cut(placed) else 0.0
    more = sum(f.area for f in placed.cut(actual).faces()) if placed.cut(actual) else 0.0
    perimeter = sum(e.length for f in plate.top for w in [f.outer_wire(), *f.inner_wires()] for e in w.edges())
    return less + more, perimeter * values.get("step", 0.01) / 2
