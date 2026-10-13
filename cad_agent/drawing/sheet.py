"""The sheet: an ISO 5457 frame, a title block, the views of a plate and its dimensions, as items on layers.

Everything here is in millimetres on the paper, origin at the sheet's lower-left corner, y up, which is also what the
DXF holds (`render.py` draws the SVG and the PDF from that file). An item is `(layer, geometry)`; the geometry is an
entity of dxf.py (Line, Circle, Arc), a `Text` or a `Solid` (a filled arrowhead). Nothing is random and nothing is a
clock: the same plate gives the same items.

Standards followed, and where
------------------------------
  ISO 5457     sheet sizes A4 to A0 (landscape), a frame 0.7 mm wide 20 mm from the left edge (for filing) and 10 mm
               from the other three (20 mm on A1 and A0), centring marks 0.5 mm wide at the middle of each side
  ISO 7200     a title block in the lower right corner of the frame, 180 x 40 mm: the part, its number, the material,
               the process, the scale, the sheet, the projection, the commit and whether the design is verified, and the
               general tolerance
  ISO 128-20   line types: visible edges continuous 0.5 mm (type 01.2), hidden edges dashed 0.25 mm (02.1, dash 12d and
               gap 3d at d = 0.25), centre lines long-dashed dotted 0.25 mm (04.1, dash 24d, gaps 3d, dot 0.5d),
               dimension, extension and leader lines continuous 0.25 mm (01.1)
  ISO 128-30   first angle projection is the default: the view from the left stands to the right of the front view.
               Third angle (`angle="third"`) puts the view from the right there. It is the default because ISO's is, and so
               is TechDraw's (Preferences::projectionAngle: FirstAngle, FreeCAD commit 3160daf1e2b6), and the sheet
               carries the ISO 5456-2 symbol of the one it uses
  ISO 129-1    dimension lines with closed filled arrowheads, extension lines 1 mm off the part and 2 mm past the
               dimension line, values 3.5 mm high above the line (ISO 3098), the overall sizes outermost, and the
               positions of the features by ordinate dimensioning: every value written at the end of an extension
               line that starts at the feature's centre, measured from the lower-left corner of the outline, which is
               marked 0
  ISO 2768-1   the general tolerance, class m, is named in the title block and the notes. The sheet gives sizes and
               positions and no tolerance of its own: a fit that needs a tighter one is not on this sheet
  ISO 5455     the scale is one of the series: 50:1, 20:1, 10:1, 5:1, 2:1, 1:1, 1:2, 1:5, 1:10, ... 1:1000

R14 has no lineweights, so the DXF says which line is which by layer and colour (LAYERS) and the SVG and PDF apply the
widths of ISO 128-20 per layer. Text is TEXT in the STANDARD style at the heights of ISO 3098 (2.5, 3.5, 5 mm);
%%c, %%p and %%d are the diameter, plus-minus and degree signs of AutoCAD.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple

from .. import dxf

SIZES = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}
SCALES = [(50, 1), (20, 1), (10, 1), (5, 1), (2, 1), (1, 1), (1, 2), (1, 5), (1, 10), (1, 20), (1, 50), (1, 100), (1, 200),
          (1, 500), (1, 1000)]
MAX_ENLARGE = 5                 # a part is not drawn bigger than 5:1 on its own (--scale asks for more)
MAX_FEATURES = 40               # holes, slots and windows on one sheet; more would want a table
TITLE_W, TITLE_H = 180.0, 40.0
LEFT_MARGIN = 20.0

TEXT_H, SMALL_H, TITLE_TEXT_H = 3.5, 2.5, 5.0
CAP = 0.72                      # the height of a capital as a fraction of the text height (Helvetica)
EXT_GAP, EXT_OVER = 1.0, 2.0    # ISO 129-1: the extension line starts 1 mm off the part and ends 2 mm past the dimension line
ARROW, ARROW_HALF = 3.5, 0.6    # a closed filled arrowhead, 3.5 long and 1.2 wide
LEVEL = 4.5                     # distance between the rows of ordinate values
GAP_VIEWS = 22.0                # between the face view and the view beside it
TAGS = "ABCDEFGHJKLMNPRSTUVWXYZ"        # the letters of the features: I, O and Q are left out so that they are not read as 1 and 0

# name -> (AutoCAD colour index, linetype, width in mm that SVG and PDF draw it with)
class Style(NamedTuple):
    colour: int
    linetype: str
    width: float


LAYERS = {
    "FRAME": Style(7, "CONTINUOUS", 0.7),
    "MARKS": Style(7, "CONTINUOUS", 0.5),
    "TITLE": Style(7, "CONTINUOUS", 0.35),
    "VISIBLE": Style(7, "CONTINUOUS", 0.5),
    "HIDDEN": Style(5, "DASHED", 0.25),
    "CENTRE": Style(1, "CENTER", 0.25),
    "DIMENSION": Style(3, "CONTINUOUS", 0.25),
    "DIM_ORD": Style(3, "CONTINUOUS", 0.25),
    "DIM_TEXT": Style(7, "CONTINUOUS", 0.25),
    "TEXT": Style(7, "CONTINUOUS", 0.25),
    dxf.STAMP_LAYER: Style(1, "CONTINUOUS", 0.25),
}
LINETYPES = [
    dxf.Linetype("DASHED", "ISO 128-20 type 02, dashed: 12d dash, 3d gap at d = 0.25", (3.0, -0.75)),
    dxf.Linetype("CENTER", "ISO 128-20 type 04, long-dashed dotted: 24d, 3d, 0.5d, 3d at d = 0.25", (6.0, -0.75, 0.125, -0.75)),
]

HELVETICA = (  # advance widths of codes 32 to 126 in 1/1000 em (Adobe's Helvetica AFM), then the four signs below
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 278 556 500 722 500 500 500 334 260 334 584")
WIDTHS = [int(w) for w in HELVETICA.split()]
SIGNS = {"Ø": 778, "±": 584, "×": 584, "°": 400}


class Text(NamedTuple):
    at: tuple
    height: float
    value: str                  # ASCII, with %%c %%p %%d
    rotation: float = 0.0
    halign: int = 0             # 0 left, 1 centre, 2 right
    valign: int = 0             # 0 baseline


class Solid(NamedTuple):
    pts: tuple


def display(value: str) -> str:
    """The string as it is read: %%c is the diameter sign, %%p plus-minus, %%d degrees."""
    for code, sign in (("%%c", "Ø"), ("%%p", "±"), ("%%d", "°")):
        value = value.replace(code, sign).replace(code.upper(), sign)
    return value


def text_width(value: str, height: float) -> float:
    """How wide a string is in Helvetica at this height, mm."""
    total = 0
    for ch in display(value):
        total += SIGNS.get(ch) or (WIDTHS[ord(ch) - 32] if 32 <= ord(ch) <= 126 else 556)
    return total * height / 1000.0


def fmt(v: float) -> str:
    """A size as the sheet prints it: two decimals at most, none that are zero."""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def scale_text(scale: tuple) -> str:
    return f"{scale[0]}:{scale[1]}"


def parse_scale(text: str) -> tuple:
    """'1:2' -> (1, 2). The ISO 5455 series only: another is a usage error to the caller."""
    a, _, b = text.partition(":")
    try:
        got = (int(a), int(b))
    except ValueError:
        raise ValueError(f"a scale is written 1:2 or 2:1, got {text!r}") from None
    if got not in SCALES:
        raise ValueError(f"{text} is not a scale of ISO 5455 ({', '.join(scale_text(s) for s in SCALES)})")
    return got


@dataclass
class Sheet:
    size: str
    width: float
    height: float
    scale: tuple
    angle: str
    stamp: str | None
    items: list = field(default_factory=list)       # [(layer, geometry)]
    dims: list = field(default_factory=list)        # what the sheet prints: {"kind", "value", "text", ...}
    regions: dict = field(default_factory=dict)     # name -> (x0, y0, x1, y1) on the paper: "face", "side", "frame", ...
    title: dict = field(default_factory=dict)       # what the title block says
    notes: list = field(default_factory=list)
    zero: tuple = (0.0, 0.0)                        # where the face view's datum corner is on the paper

    def add(self, layer: str, geom) -> None:
        self.items.append((layer, geom))

    def line(self, layer: str, a, b) -> None:
        self.items.append((layer, dxf.Line(*sorted((dxf.snap2(a), dxf.snap2(b))))))

    def text(self, layer: str, at, height: float, value: str, rotation: float = 0.0, halign: int = 0, valign: int = 0) -> None:
        self.items.append((layer, Text(dxf.snap2(at), height, value, rotation, halign, valign)))

    def solid(self, layer: str, pts) -> None:
        self.items.append((layer, Solid(tuple(dxf.snap2(p) for p in pts))))

    def rect(self, layer: str, x0, y0, x1, y1) -> None:
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            self.line(layer, a, b)


# ─── The frame and the title block ───────────────────────────────────────────

def border(size: str) -> float:
    return 20.0 if size in ("A1", "A0") else 10.0


def drawing_space(size: str) -> tuple:
    w, h = SIZES[size]
    m = border(size)
    return (LEFT_MARGIN, m, w - m, h - m)


def frame(sheet: Sheet) -> tuple:
    """The ISO 5457 frame and centring marks; returns the drawing space (x0, y0, x1, y1)."""
    w, h = sheet.width, sheet.height
    x0, y0, x1, y1 = drawing_space(sheet.size)
    sheet.rect("FRAME", x0, y0, x1, y1)
    cx, cy = w / 2.0, h / 2.0
    m = border(sheet.size)
    sheet.line("MARKS", (cx, 0.0), (cx, y0 + 5.0))
    sheet.line("MARKS", (cx, h), (cx, y1 - 5.0))
    sheet.line("MARKS", (0.0, cy), (x0 + 5.0, cy))
    sheet.line("MARKS", (w, cy), (x1 - 5.0, cy))
    sheet.regions["frame"] = (x0, y0, x1, y1)
    return x0, y0, x1, y1


def fitted(value: str, width: float, height: float, minimum: float = 2.0) -> float:
    """The text height, no more than `height`, at which the string is at most `width` wide."""
    h = height
    while h > minimum and text_width(value, h) > width:
        h -= 0.25
    return h


def projection_symbol(sheet: Sheet, x0: float, y0: float, angle: str) -> None:
    """The ISO 5456-2 symbol of the method: a truncated cone in two views. The cone is seen from the left in the circle
    view, narrow end toward the viewer, so both circles show and none is hidden. First angle puts that view to the right
    of the side view, third angle to its left."""
    side_w, gap, d_big, d_small = 12.0, 5.0, 10.0, 6.0
    circle_x = x0 + (side_w + gap + d_big / 2.0 if angle == "first" else d_big / 2.0)
    cone_x = x0 + (0.0 if angle == "first" else d_big + gap)
    cy = y0 + d_big / 2.0
    # the cone: narrow end (d_small) at the left, wide end (d_big) at the right, axis horizontal
    sheet.line("TITLE", (cone_x, cy - d_small / 2), (cone_x + side_w, cy - d_big / 2))
    sheet.line("TITLE", (cone_x, cy + d_small / 2), (cone_x + side_w, cy + d_big / 2))
    sheet.line("TITLE", (cone_x, cy - d_small / 2), (cone_x, cy + d_small / 2))
    sheet.line("TITLE", (cone_x + side_w, cy - d_big / 2), (cone_x + side_w, cy + d_big / 2))
    sheet.line("CENTRE", (cone_x - 2.5, cy), (cone_x + side_w + 2.5, cy))
    for r in (d_big / 2.0, d_small / 2.0):
        sheet.add("TITLE", dxf.Circle(dxf.snap2((circle_x, cy)), dxf.snap(r)))
    sheet.line("CENTRE", (circle_x - d_big / 2 - 2.5, cy), (circle_x + d_big / 2 + 2.5, cy))
    sheet.line("CENTRE", (circle_x, cy - d_big / 2 - 2.5), (circle_x, cy + d_big / 2 + 2.5))


def title_block(sheet: Sheet, space: tuple, fields: dict) -> tuple:
    """The title block in the lower right corner of the frame. Returns its box (x0, y0, x1, y1)."""
    fx1, fy0 = space[2], space[1]
    x0, y0 = fx1 - TITLE_W, fy0
    x1, y1 = fx1, fy0 + TITLE_H
    sheet.rect("FRAME", x0, y0, x1, y1)
    # rows from the bottom: A 0..13, B 13..26, C 26..40; columns in each
    ya, yb, yc = y0 + 13.0, y0 + 26.0, y0 + TITLE_H
    cells = []          # (label, value, x0, y0, x1, y1, layer)
    ok = fields["status_ok"]
    status_layer = "TEXT" if ok else dxf.STAMP_LAYER
    cells += [("PART", fields["part"], x0, yb, x0 + 110.0, yc, "TEXT"),
              ("DRAWING NUMBER", fields["number"], x0 + 110.0, yb, x1, yc, "TEXT"),
              ("MATERIAL", fields["material"], x0, ya, x0 + 45.0, yb, "TEXT"),
              ("PROCESS", fields["process"], x0 + 45.0, ya, x0 + 80.0, yb, "TEXT"),
              ("SCALE", fields["scale"], x0 + 80.0, ya, x0 + 105.0, yb, "TEXT"),
              ("SIZE   SHEET", fields["size"], x0 + 105.0, ya, x0 + 130.0, yb, "TEXT"),
              ("COMMIT", fields["commit"], x0, y0, x0 + 45.0, ya, "TEXT"),
              ("STATUS (cad done)", fields["status"], x0 + 45.0, y0, x0 + 90.0, ya, status_layer),
              ("GENERAL TOLERANCES", fields["tolerance"], x0 + 90.0, y0, x0 + 130.0, ya, "TEXT")]
    for _, _, cx0, cy0, cx1, cy1, _ in cells:
        sheet.rect("TITLE", cx0, cy0, cx1, cy1)
    sheet.rect("TITLE", x0 + 130.0, y0, x1, yb)
    for label, value, cx0, cy0, cx1, cy1, layer in cells:
        sheet.text("TEXT", (cx0 + 1.5, cy1 - 3.2), SMALL_H, label)
        big = TITLE_TEXT_H if label in ("PART",) else TEXT_H
        h = fitted(value, cx1 - cx0 - 3.0, big)
        sheet.text(layer, (cx0 + 1.5, cy0 + 2.5), h, value)
    sheet.text("TEXT", (x0 + 131.5, y0 + 22.8), SMALL_H, "PROJECTION")
    projection_symbol(sheet, x0 + 141.5, y0 + 8.0, sheet.angle)
    sheet.text("TEXT", (x0 + 131.5, y0 + 2.0), SMALL_H, f"{sheet.angle.upper()} ANGLE")
    sheet.regions["title"] = (x0, y0, x1, y1)
    return x0, y0, x1, y1


# ─── Dimensions ──────────────────────────────────────────────────────────────

def arrow(sheet: Sheet, tip, direction, layer: str = "DIMENSION") -> None:
    """A closed filled arrowhead with its tip at `tip`, pointing along `direction` (a unit vector): its body is behind the tip."""
    dx, dy = direction
    bx, by = tip[0] - dx * ARROW, tip[1] - dy * ARROW
    nx, ny = -dy * ARROW_HALF, dx * ARROW_HALF
    sheet.solid(layer, [tip, (bx + nx, by + ny), (bx - nx, by - ny)])


def dim_horizontal(sheet: Sheet, x1: float, x2: float, y: float, near_y: float, text: str) -> None:
    """A dimension from x1 to x2 on the line y, above the part (`near_y` is the part's edge it measures from, on the
    paper, below the line). The text sits above the line, centred between the extension lines if it fits there, else
    after the right one with the arrows outside (ISO 129-1)."""
    for x in (x1, x2):
        sheet.line("DIMENSION", (x, near_y + EXT_GAP), (x, y + EXT_OVER))
    sheet.line("DIMENSION", (x1, y), (x2, y))
    if x2 - x1 >= 2 * ARROW + 1.0:
        arrow(sheet, (x1, y), (-1.0, 0.0))
        arrow(sheet, (x2, y), (1.0, 0.0))
    else:                                   # arrows outside, pointing in, and the line goes on past them
        sheet.line("DIMENSION", (x1 - ARROW - 1.0, y), (x1, y))
        sheet.line("DIMENSION", (x2, y), (x2 + ARROW + 1.0, y))
        arrow(sheet, (x1, y), (1.0, 0.0))
        arrow(sheet, (x2, y), (-1.0, 0.0))
    if text_width(text, TEXT_H) + 1.0 <= x2 - x1:
        sheet.text("DIM_TEXT", ((x1 + x2) / 2.0, y + 1.2), TEXT_H, text, 0.0, 1)
    else:
        sheet.text("DIM_TEXT", (x2 + ARROW + 2.5, y + 1.2), TEXT_H, text, 0.0, 0)


def dim_vertical(sheet: Sheet, y1: float, y2: float, x: float, near_x: float, text: str) -> None:
    """A dimension from y1 to y2 on the line x, to the right of the part (`near_x` is the part's edge it measures from, to
    the left of the line). The text is turned to read from the right and stands on the part's side of the line."""
    for y in (y1, y2):
        sheet.line("DIMENSION", (near_x + EXT_GAP, y), (x + EXT_OVER, y))
    sheet.line("DIMENSION", (x, y1), (x, y2))
    if y2 - y1 >= 2 * ARROW + 1.0:
        arrow(sheet, (x, y1), (0.0, -1.0))
        arrow(sheet, (x, y2), (0.0, 1.0))
    else:
        sheet.line("DIMENSION", (x, y1 - ARROW - 1.0), (x, y1))
        sheet.line("DIMENSION", (x, y2), (x, y2 + ARROW + 1.0))
        arrow(sheet, (x, y1), (0.0, 1.0))
        arrow(sheet, (x, y2), (0.0, -1.0))
    sheet.text("DIM_TEXT", (x - 1.2, (y1 + y2) / 2.0), TEXT_H, text, 90.0, 1)


def schedule(spans: list, gap: float) -> list:
    """Levels 0, 1, 2 ... for labels so that no two on one level overlap: spans are (lo, hi) along the axis, in the order
    they are placed. A label takes the first level whose last label ends `gap` before it begins."""
    ends: list = []
    levels = []
    for lo, hi in spans:
        for k, end in enumerate(ends):
            if lo >= end + gap:
                ends[k] = hi
                levels.append(k)
                break
        else:
            ends.append(hi)
            levels.append(len(ends) - 1)
    return levels
