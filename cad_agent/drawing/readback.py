"""The drawing's own gates: whether the sheet says what the plate is, read back from the files and not from the code
that made them.

A drawing is something a person cuts metal by. Three links can break between the B-rep and what they read, and each
has its own row (`cad drawing` shows them as drawing/<name>; onesheet.py adds `scope` and `views` before them):

  dimensions   the plate the numbers describe is the plate. The numbers are the plate's own (outline, corner radius,
               holes, slots, windows, from the B-rep); the plate they describe is built and compared with the end face
               of the solid, area in one and not the other both ways, which must be nothing. A cutout left out, one made
               into another kind, or one in the wrong place fails it (platefit.reconstruct)
  sheet        the sheet, read back from the DXF with ezdxf (which shares no code with the writer), draws that plate at
               the scale it states: the visible lines of the face view are as big as the plate and the side view as
               thick, every hole is a circle where the B-rep has it, each cutout has an ordinate line through its centre
               whose label is its distance from the corner at the scale of the sheet, the overall sizes are the lengths of
               their dimension lines, the through holes are dashed in the side view, and every number the notes print is
               one of the plate's
  layout       no two labels overlap, and nothing is outside the frame
  svg, pdf     the SVG and the PDF have an element for each entity of the DXF they were drawn from, of the same kind and
               in the same order, and the PDF is a well formed file (its cross reference table points at its objects and
               its page is the sheet's size)

A gate that raises is an UNCHECKED row too (onesheet.judge).
A row that cannot be settled is UNCHECKED and one that is wrong FAIL, and `cad drawing` writes nothing for either.
Tolerances are the printing's: a printed number is rounded to 0.01 mm, so it may differ from the plate's by 0.005; what
the DXF holds, a nanometre grid, may differ from the plate's by 0.001 mm times the scale.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections import Counter

from .. import dxf
from ..registry import Row
from . import arrange as L
from . import platefit as P
from . import writers as R
from . import paper as S

PRINT = 0.005                   # a number printed to 0.01 is the plate's within this
GEOM = 1e-3                     # mm in the plate: where a line or a circle of the sheet may be from where the B-rep has it
AREA = 1e-3                     # mm^2 left over by the rebuilt plate, however many boundaries it has
SOURCE = ("the DXF read back by ezdxf, against the solid's B-rep (outline and holes from OCCT, holes by spec.holes), "
          "and the plate rebuilt from the printed numbers against the solid's end face")


def row(part: str, rule: str, state: str, measured: str, limit: str, source: str = SOURCE) -> Row:
    return Row(subject=part, rule=rule, state=state, measured=measured, limit=limit, source=source, check="drawing")


def values_of(plate: P.Plate) -> dict:
    """What a sheet states of a plate, as `plate.rebuilt` takes it: from the lower-left corner, in full (the sheet prints
    them to 0.01, which the `sheet` row holds to the geometry it draws)."""
    lo = plate.lo
    return {"w": plate.width, "h": plate.height, "r": plate.corner_r, "step": 0.0,
            "holes": [(f.u - lo[0], f.v - lo[1], f.dia) for f in plate.holes],
            "slots": [(f.u - lo[0], f.v - lo[1], f.width, f.length, f.along) for f in plate.slots],
            "windows": [(f.u - lo[0], f.v - lo[1], f.w, f.h, f.r) for f in plate.windows]}


# ─── The plate the numbers describe ──────────────────────────────────────────

def dimensions_row(part: str, plate: P.Plate) -> Row:
    limit = f"the plate these numbers describe equals the solid's end face: no area in one and not the other beyond {AREA:g} mm^2"
    try:
        diff, _ = P.reconstruct(plate, values_of(plate))
    except Exception as e:      # noqa: BLE001 - say so, never pass what could not be built
        return row(part, "dimensions", "UNCHECKED", f"the plate the numbers describe could not be built: {type(e).__name__}: {e}", limit)
    if diff > AREA:
        return row(part, "dimensions", "FAIL",
                   f"the plate the numbers describe differs from the solid's end face by {diff:.4f} mm^2, over {AREA:g}: a "
                   "cutout is missing, of another kind or in another place", limit)
    return row(part, "dimensions", "PASS",
               f"the plate the numbers describe ({plate.describe()}) differs from the solid's end face by {diff:.4f} mm^2", limit)


# ─── The sheet, read back ────────────────────────────────────────────────────

def _box(g) -> tuple:
    pts = dxf.extent_points(g)
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def _clusters(ents: list) -> list:
    """The boxes (x0, y0, x1, y1) of the groups the entities fall into when they are further than 8 mm apart in x."""
    boxes = sorted(_box(g) for g in ents)
    out: list = []
    for b in boxes:
        if out and b[0] <= out[-1][2] + 8.0:
            out[-1] = (min(out[-1][0], b[0]), min(out[-1][1], b[1]), max(out[-1][2], b[2]), max(out[-1][3], b[3]))
        else:
            out.append(b)
    return out


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def _text_box(t: S.Text) -> tuple:
    """The box of a text on the paper (x0, y0, x1, y1): its width in Helvetica, its height a capital's."""
    w, h = S.text_width(t.value, t.height), t.height * S.CAP
    shift = {0: 0.0, 1: w / 2.0, 2: w}[t.halign]
    a = math.radians(t.rotation)
    c, s = math.cos(a), math.sin(a)
    corners = [(-shift, 0.0), (w - shift, 0.0), (w - shift, h), (-shift, h)]
    pts = [(t.at[0] + x * c - y * s, t.at[1] + x * s + y * c) for x, y in corners]
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def sheet_row(part: str, plate: P.Plate, doc: R.Doc, data: bytes, meta: dict, angle: str, stamp: str | None) -> Row:
    limit = (f"the DXF holds the plate at its stated scale: its lines and circles within {GEOM:g} mm of the B-rep's (in the "
             f"plate), every label the distance it names within {PRINT:g} mm, every dimension line its number's length, and the "
             "notes the plate's own numbers")
    problems: list = []
    facts: list = []

    # the file itself
    if b"AC1014" not in data[:2000]:
        problems.append("it does not say it is release 14")
    if doc.units != 4:
        problems.append("it does not say millimetres" if doc.units is None else f"its units are code {doc.units}, not 4 (millimetres)")
    if doc.problems:
        problems.append("ezdxf's audit of it found: " + "; ".join(doc.problems[:3]))
    if doc.stray:
        problems.append("it holds entities a drawing does not have: " + ", ".join(f"{n} {k}" for k, n in sorted(doc.stray.items())))
    for name in ("DASHED", "CENTER"):
        if name not in doc.linetypes:
            problems.append(f"its linetype {name} is missing")
    for layer in {l for l, _ in doc.items}:
        if layer not in doc.layers:
            problems.append(f"it has entities on layer {layer}, which its layer table does not declare")
    by: dict = {}
    for layer, g in doc.items:
        by.setdefault(layer, []).append(g)
    size = next((n for n, (w, h) in S.SIZES.items() if _close(w, doc.extmax[0], 1e-6) and _close(h, doc.extmax[1], 1e-6)), None)
    if size is None:
        problems.append(f"its extents {doc.extmax[0]:g} x {doc.extmax[1]:g} are not a sheet of ISO 5457")
    texts = [g for _, g in doc.items if isinstance(g, S.Text)]
    scales = [t.value for t in texts if re.fullmatch(r"\d+:\d+", t.value)]
    if len(scales) != 1:
        problems.append(f"it states {len(scales)} scales (it needs one)")
        return row(part, "sheet", "FAIL", "; ".join(problems), limit)
    a, _, b = scales[0].partition(":")
    s = int(a) / int(b)
    facts.append(f"sheet {size} at {scales[0]}")

    # the views
    visible = by.get("VISIBLE", [])
    groups = _clusters(visible)
    if len(groups) != 2:
        problems.append(f"the visible lines fall into {len(groups)} views, not two")
        return row(part, "sheet", "FAIL", "; ".join(problems), limit)
    (fx0, fy0, fx1, fy1), (sx0, sy0, sx1, sy1) = groups
    tol = GEOM * s
    if not (_close((fx1 - fx0) / s, plate.width, GEOM) and _close((fy1 - fy0) / s, plate.height, GEOM)):
        problems.append(f"the face view is {(fx1 - fx0) / s:.3f} x {(fy1 - fy0) / s:.3f} mm in the plate, which is "
                        f"{plate.width:.3f} x {plate.height:.3f}")
    if not (_close((sx1 - sx0) / s, plate.thickness, GEOM) and _close(sy0, fy0, tol) and _close(sy1, fy1, tol)):
        problems.append(f"the side view is {(sx1 - sx0) / s:.3f} thick and {(sy1 - sy0) / s:.3f} high, level with the face view "
                        f"(from {sy0:.3f} to {sy1:.3f}, not {fy0:.3f} to {fy1:.3f}); the plate is {plate.thickness:.3f} thick")
    facts.append(f"face view {(fx1 - fx0) / s:g} x {(fy1 - fy0) / s:g}, side view {(sx1 - sx0) / s:g} thick")
    inside = [g for g in visible if _box(g)[2] <= fx1 + tol]
    circles = sorted((round((g.c[0] - fx0) / s, 4), round((g.c[1] - fy0) / s, 4), round(2 * g.r / s, 4))
                     for g in inside if isinstance(g, dxf.Circle))
    want = sorted((round(f.u - plate.lo[0], 4), round(f.v - plate.lo[1], 4), round(f.dia, 4)) for f in plate.holes)
    if len(circles) != len(want) or any(not all(_close(x, y, GEOM) for x, y in zip(c, w)) for c, w in zip(circles, want)):
        problems.append(f"the face view has circles {circles} and the B-rep has holes {want}")
    facts.append(f"{len(want)} holes where the B-rep has them")
    # the through cutouts are dashed in the side view: the two extremes of each hole across the plate's thickness
    hidden = by.get("HIDDEN", [])
    for du, dv, dia in want:
        for edge in (dv - dia / 2.0, dv + dia / 2.0):
            y = fy0 + edge * s
            if not any(isinstance(g, dxf.Line) and _close(g.a[1], y, tol) and _close(g.b[1], y, tol)
                       and min(g.a[0], g.b[0]) <= sx0 + tol and max(g.a[0], g.b[0]) >= sx1 - tol for g in hidden):
                problems.append(f"the hole of {dia:g} at {du:g}, {dv:g} is not dashed through the side view at y = {edge:g}")
                break

    # the ordinates
    feats = L.features(plate)
    ords = by.get("DIM_ORD", [])
    otexts = [g for g in ords if isinstance(g, S.Text)]
    olines = [g for g in ords if isinstance(g, dxf.Line)]
    vertical = [g for g in olines if _close(g.a[0], g.b[0], 1e-6)]
    horizontal = [g for g in olines if _close(g.a[1], g.b[1], 1e-6)]
    for axis, lines in (("x", vertical), ("y", horizontal)):
        shown = []
        for g in lines:
            if axis == "x":
                pos = g.a[0]
                end = min(g.a[1], g.b[1])
                lab = [t for t in otexts if t.halign == 1 and _close(t.at[0], pos, 1e-3) and _close(t.at[1], end - 3.6, 1e-3)]
                value = (pos - fx0) / s
            else:
                pos = g.a[1]
                end = min(g.a[0], g.b[0])
                lab = [t for t in otexts if t.halign == 2 and _close(t.at[1], pos - 1.3, 1e-3) and _close(t.at[0], end - 1.0, 1e-3)]
                value = (pos - fy0) / s
            if len(lab) != 1:
                problems.append(f"an ordinate line of the {axis} axis has {len(lab)} labels at its end, not one")
                continue
            if not _close(float(lab[0].value), value, PRINT + 1e-9):
                problems.append(f"an ordinate label says {lab[0].value} and its line is {value:.3f} mm from the corner at {scales[0]}")
            shown.append(lab[0].value)
        u_texts, v_texts = L.ordinates(feats)
        expected = (u_texts if axis == "x" else v_texts).texts()
        if sorted(shown, key=float) != sorted(expected, key=float):
            problems.append(f"the {axis} ordinates read {sorted(shown, key=float)} and the plate's cutouts are at {sorted(expected, key=float)}")
    centres = [(f.du, f.dv) for f in feats]
    for du, dv in centres:
        x, y = fx0 + du * s, fy0 + dv * s
        if not any(_close(g.a[0], x, tol) and min(g.a[1], g.b[1]) - tol <= y <= max(g.a[1], g.b[1]) + tol for g in vertical):
            problems.append(f"no ordinate line of x runs through the centre of the cutout at {du:g}, {dv:g}")
        if not any(_close(g.a[1], y, tol) and min(g.a[0], g.b[0]) - tol <= x <= max(g.a[0], g.b[0]) + tol for g in horizontal):
            problems.append(f"no ordinate line of y runs through the centre of the cutout at {du:g}, {dv:g}")
    facts.append(f"{len(centres)} cutouts, each with its ordinates")

    # the overall dimensions
    dlines = [g for g in by.get("DIMENSION", []) if isinstance(g, dxf.Line)]
    dtexts = sorted(t.value for layer in ("DIM_TEXT",) for t in by.get(layer, []) if isinstance(t, S.Text))
    wanted = sorted([S.fmt(plate.width), S.fmt(plate.height), S.fmt(plate.thickness)])
    if dtexts != wanted:
        problems.append(f"the dimensions read {dtexts} and the plate is {wanted}")

    def spanning(lines, axis, lo, hi):
        return [g for g in lines if (_close(g.a[1], g.b[1], 1e-6) if axis == "x" else _close(g.a[0], g.b[0], 1e-6))
                and _close(min(g.a[axis == "y"], g.b[axis == "y"]), lo, tol) and _close(max(g.a[axis == "y"], g.b[axis == "y"]), hi, tol)]

    for name, axis, lo, hi, size_ in (("width", "x", fx0, fx1, plate.width), ("height", "y", fy0, fy1, plate.height),
                                      ("thickness", "x", sx0, sx1, plate.thickness)):
        if not spanning(dlines, axis, lo, hi):
            problems.append(f"no dimension line of the sheet is as long as the {name} ({(hi - lo) / s:g} mm at {scales[0]})")
    tips = [g.pts[0] for g in by.get("DIMENSION", []) if isinstance(g, S.Solid)]
    ends = [p for g in dlines for p in (g.a, g.b)]
    if not all(any(_close(t[0], e[0], 1e-3) and _close(t[1], e[1], 1e-3) for e in ends) for t in tips) or len(tips) != 6:
        problems.append(f"the arrowheads ({len(tips)}) are not six, each on the end of a dimension line")
    facts.append("overall sizes as long as their numbers")

    # the notes and the letters
    groups_ = L.grouped(L.features(plate))
    notes = [t.value for t in texts if t.value[:1].isalpha() and "  " in t.value and t.value[1:3] == "  "]
    for g in groups_:
        line = f"{g.tag}  {g.text}"
        if line not in notes:
            problems.append(f"the notes do not say {line!r}")
    tags = Counter(t.value for t in texts if len(t.value) == 1 and t.value in S.TAGS)
    for g in groups_:
        if tags.get(g.tag, 0) != len(g.members):
            problems.append(f"the letter {g.tag} is written {tags.get(g.tag, 0)} times and {len(g.members)} cutouts have it")
    facts.append(f"{len(groups_)} sizes of cutout in the notes")
    said = {t.value for t in texts}
    for line in L.tolerance_notes(plate):
        if line not in said:
            problems.append(f"the notes do not say {line!r}")
    if L.tolerance_notes(plate):
        facts.append(f"{len(L.tolerance_notes(plate))} sizes ISO 2768-m does not cover, said so")
    elif any(t.value.startswith("NO GENERAL TOLERANCE") for t in texts):
        problems.append("the notes say a size has no general tolerance and none lacks it")

    # the stamp and the title block
    stamped = any(isinstance(g, S.Text) and g.value == "NOT VERIFIED" for g in by.get(dxf.STAMP_LAYER, []))
    if bool(stamp) != stamped:
        problems.append("the stamp NOT VERIFIED is missing from the sheet" if stamp else "the sheet carries a stamp it should not")
    if bool(stamp) != R.comment_line(data).startswith("NOT VERIFIED"):
        problems.append("the comment of the file does not agree with the stamp")
    values = {t.value for t in texts}
    for what, expect in (("part", meta["part"]), ("number", f"{meta['project']}/{meta['part']}"), ("tolerance", L.TOLERANCE),
                         ("status", "NOT VERIFIED" if stamp else "VERIFIED"), ("scale", scales[0])):
        if expect not in values:
            problems.append(f"the title block does not say the {what}: {expect!r}")
    facts.append("title block" + (" and stamp" if stamp else ""))
    if problems:
        return row(part, "sheet", "FAIL", "; ".join(problems[:6]) + (f"; and {len(problems) - 6} more" if len(problems) > 6 else ""), limit)
    return row(part, "sheet", "PASS", "; ".join(facts), limit)


def layout_row(part: str, doc: R.Doc) -> Row:
    limit = "no two labels overlap; every entity is inside the sheet"
    texts = [g for _, g in doc.items if isinstance(g, S.Text)]
    boxes = [(_text_box(t), t) for t in texts]
    over = []
    for i, (a, ta) in enumerate(boxes):
        for b, tb in boxes[i + 1:]:
            if a[0] < b[2] - 1e-3 and b[0] < a[2] - 1e-3 and a[1] < b[3] - 1e-3 and b[1] < a[3] - 1e-3:
                over.append(f"{S.display(ta.value)!r} and {S.display(tb.value)!r}")
    W, H = doc.extmax
    outside = sum(1 for _, g in doc.items if not isinstance(g, S.Text)
                  and (lambda bx: bx[0] < -1e-6 or bx[1] < -1e-6 or bx[2] > W + 1e-6 or bx[3] > H + 1e-6)(_box_any(g)))
    if over or outside:
        what = ([f"labels overlap: {', '.join(over[:3])}"] if over else []) + ([f"{outside} entities are outside the sheet"] if outside else [])
        return row(part, "layout", "UNCHECKED", "; ".join(what) + ": the layout could not keep them apart, so no drawing is made", limit)
    return row(part, "layout", "PASS", f"{len(texts)} labels, none overlapping, all inside the {W:g} x {H:g} sheet", limit)


def _box_any(g) -> tuple:
    if isinstance(g, S.Solid):
        xs, ys = zip(*g.pts)
        return min(xs), min(ys), max(xs), max(ys)
    return _box(g)


# ─── SVG and PDF ─────────────────────────────────────────────────────────────

def _kinds(doc: R.Doc) -> list:
    out = []
    for _, g in doc.items:
        out.append("text" if isinstance(g, S.Text) else "polygon" if isinstance(g, S.Solid) else "line" if isinstance(g, dxf.Line)
                   else "circle" if isinstance(g, dxf.Circle) else "path" if isinstance(g, dxf.Arc) else "polyline")
    return out


def svg_row(part: str, doc: R.Doc, svg: bytes) -> Row:
    limit = "an element of the right kind for each entity of the DXF, in its order, the sheet's size, and the DXF's own text"
    source = "the SVG parsed as XML (xml.etree) against the entities ezdxf read from the DXF"
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        return row(part, "svg", "FAIL", f"it is not well formed XML: {e}", limit, source)
    ns = "{http://www.w3.org/2000/svg}"
    drawn = [el for el in root if el.tag.replace(ns, "") in ("line", "circle", "path", "polygon", "polyline", "text")]
    problems = []
    want = _kinds(doc)
    got = [el.tag.replace(ns, "") for el in drawn]
    if got != want:
        problems.append(f"it has {len(got)} drawn elements and the DXF {len(want)}, or they are not the same kinds in the same order")
    W, H = doc.extmax
    if root.get("viewBox") != f"0 0 {R._n(W)} {R._n(H)}":
        problems.append(f"its view box is {root.get('viewBox')}, not the sheet's 0 0 {R._n(W)} {R._n(H)}")
    texts = [S.display(g.value) for _, g in doc.items if isinstance(g, S.Text)]
    shown = [el.text for el in drawn if el.tag.replace(ns, "") == "text"]
    if shown != texts:
        problems.append("its texts are not the DXF's")
    hidden = [el for el in drawn if el.get("class") == "HIDDEN"]
    if not all(el.get("stroke-dasharray") for el in hidden):
        problems.append("a hidden line is not dashed")
    if b"<script" in svg or b"javascript" in svg.lower():
        problems.append("it holds a script")
    if problems:
        return row(part, "svg", "FAIL", "; ".join(problems), limit, source)
    return row(part, "svg", "PASS", f"{len(drawn)} elements, one for each entity of the DXF, in its order; {len(hidden)} dashed", limit, source)


def pdf_row(part: str, doc: R.Doc, pdf: bytes) -> Row:
    limit = ("a well formed PDF of one page the sheet's size, whose cross reference table points at its objects, with a stroke "
             "for each line, circle and arc of the DXF, a fill for each arrowhead and a string for each text")
    source = "the PDF parsed by this module (header, xref, stream length, page box, drawing operators) against the DXF"
    problems = []
    if not pdf.startswith(b"%PDF-1.4\n") or not pdf.endswith(b"%%EOF\n"):
        return row(part, "pdf", "FAIL", "it does not start with %PDF-1.4 and end with %%EOF", limit, source)
    tail = pdf.rfind(b"startxref\n")
    try:
        xref = int(pdf[tail + 10:].split(b"\n", 1)[0])
        table = pdf[xref:].split(b"trailer", 1)[0].split(b"\n")
        count = int(table[1].split()[1])
        offsets = [int(t[:10]) for t in table[3:2 + count]]
        for i, off in enumerate(offsets, 1):
            if not pdf[off:].startswith(f"{i} 0 obj\n".encode()):
                problems.append(f"the cross reference points at {off} for object {i}, which is not it")
        m = re.search(rb"/Length (\d+) >>\nstream\n", pdf)
        start = m.end()
        stream = pdf[start:start + int(m.group(1))]
        if pdf[start + int(m.group(1)):].split(b"\n", 1)[0] != b"endstream":
            problems.append("a stream is not as long as its /Length says")
        box = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", pdf)
        W, H = doc.extmax
        if not (box and _close(float(box.group(1)), W * R.PT, 0.01) and _close(float(box.group(2)), H * R.PT, 0.01)):
            problems.append("its page is not the sheet's size")
        text = stream.decode("latin-1")
        strokes = len(re.findall(r" S$", text, re.M))
        fills = len(re.findall(r" f$", text, re.M))
        strings = len(re.findall(r" Tj ET$", text, re.M))
        kinds = Counter(_kinds(doc))
        want = (kinds["line"] + kinds["circle"] + kinds["path"] + kinds["polyline"], kinds["polygon"], kinds["text"])
        if (strokes, fills, strings) != want:
            problems.append(f"it has {strokes} strokes, {fills} fills and {strings} strings, and the DXF needs {want[0]}, {want[1]} and {want[2]}")
    except (ValueError, IndexError, AttributeError) as e:
        return row(part, "pdf", "FAIL", f"its structure cannot be read: {type(e).__name__}: {e}", limit, source)
    if problems:
        return row(part, "pdf", "FAIL", "; ".join(problems), limit, source)
    return row(part, "pdf", "PASS", f"{len(offsets)} objects at their offsets, one page of the sheet's size, {strokes} strokes, "
                                              f"{fills} fills, {strings} strings", limit, source)
