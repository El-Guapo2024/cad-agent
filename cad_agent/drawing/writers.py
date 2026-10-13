"""The sheet as files: the DXF (the master), and the SVG and the PDF drawn from it.

The DXF is written with piece D's R14 writer (dxf.DxfWriter) and read back with ezdxf, which shares no code with it.
The SVG and the PDF are not made from the sheet that was laid out: they are made from what ezdxf reads in the DXF, so
that what a person sees in them is what the master says, and a DXF that lost a line or moved a number is a SVG and a
PDF that did too, which the readback (readback.py) then sees.

  DXF  layers by function with the linetype of ISO 128-20 (DASHED, CENTER) and a colour for the pen, as R14 has no
       lineweight; model space, one unit a millimetre, the sheet's lower-left corner at 0, 0. The first comment names
       the part, the projection, the scale and the sheet, and carries the stamp if the design is not verified
  SVG  A plain SVG 1.1: one element for each entity in the file's order, the width of each layer's pen (sheet.LAYERS),
       the dash pattern of its linetype, text as text in Helvetica; y is turned over as SVG's points down. Nothing in it
       changes between runs: no date, no id
  PDF  A PDF 1.4 written by hand: one page of the sheet's size, the standard Helvetica (not embedded), vector lines and
       Bezier arcs, the same pens. No compression, no date, no id, so the same sheet is the same bytes. This is why
       the PDF needs no library: the `drawings` extra of pyproject.toml (matplotlib) is not used

All three are the same bytes for the same sheet, on either kernel when the sheet is (hlr.py says how the lines are
made so).
"""
from __future__ import annotations

import io
import math
from collections import Counter
from typing import NamedTuple

from .. import dxf
from . import paper as S

PT = 72.0 / 25.4                # points in a millimetre


# ─── The DXF ─────────────────────────────────────────────────────────────────

def comment_of(sheet: S.Sheet, meta: dict, source: str) -> str:
    text = (f"cad-agent drawing {meta['project']}/{meta['part']}: {sheet.angle} angle projection, scale "
            f"{S.scale_text(sheet.scale)}, sheet {sheet.size} ({sheet.width:g} x {sheet.height:g} mm); units mm; views by "
            f"{source}; entities as FreeCAD {dxf.FREECAD_COMMIT} ImpExpDxf, version {dxf.VERSION}")
    return f"{sheet.stamp}: not from a verified design. {text}" if sheet.stamp else text


def write(sheet: S.Sheet, meta: dict, source: str) -> bytes:
    layers = [dxf.Layer(name, st.colour, st.linetype) for name, st in S.LAYERS.items()
              if name != dxf.STAMP_LAYER or sheet.stamp or any(layer == name for layer, _ in sheet.items)]
    header = [("$LTSCALE", [(40, "1.0")]), ("$LIMMIN", [(10, "0.000000"), (20, "0.000000")]),
              ("$LIMMAX", [(10, dxf.num(sheet.width)), (20, dxf.num(sheet.height))])]
    w = dxf.DxfWriter(comment_of(sheet, meta, source), (0.0, 0.0), (sheet.width, sheet.height), layers, S.LINETYPES, header)
    for layer, g in sheet.items:
        if isinstance(g, S.Text):
            w.text(layer, g.at, g.height, g.value, g.rotation, g.halign, g.valign)
        elif isinstance(g, S.Solid):
            w.solid(layer, g.pts)
        else:
            w.entity(g, layer)
    return w.finish()


# ─── Reading it back ─────────────────────────────────────────────────────────

class Doc(NamedTuple):
    items: list             # [(layer, geometry)] in the file's order; lines are as written, not sorted
    units: int | None
    version: str
    extmax: tuple
    layers: dict            # name -> (colour, linetype)
    linetypes: dict         # name -> pattern
    comment: str
    problems: list          # what ezdxf's audit found wrong with the file, if anything
    stray: Counter          # entity types a drawing does not have


def read(data: bytes) -> Doc:
    """What a DXF holds, by ezdxf: entities, text and filled arrowheads by layer. Raises dxf.Unreadable."""
    ezdxf = dxf.ezdxf_module()

    def xy(v) -> tuple:
        return (float(v[0]), float(v[1]))

    try:
        doc = ezdxf.read(io.StringIO(data.decode("ascii", "replace")))
        items, stray = [], Counter()
        for e in doc.modelspace():
            t, layer = e.dxftype(), e.dxf.layer
            if t == "LINE":
                items.append((layer, dxf.Line(xy(e.dxf.start), xy(e.dxf.end))))
            elif t == "CIRCLE":
                items.append((layer, dxf.Circle(xy(e.dxf.center), float(e.dxf.radius))))
            elif t == "ARC":
                items.append((layer, dxf.Arc(xy(e.dxf.center), float(e.dxf.radius), float(e.dxf.start_angle), float(e.dxf.end_angle))))
            elif t == "ELLIPSE":
                items.append((layer, dxf.Ellipse(xy(e.dxf.center), xy(e.dxf.major_axis), float(e.dxf.ratio),
                                                 float(e.dxf.start_param), float(e.dxf.end_param))))
            elif t == "SPLINE":
                items.append((layer, dxf.Spline(int(e.dxf.degree), tuple(float(k) for k in e.knots),
                                                tuple(xy(v) for v in e.control_points))))
            elif t == "LWPOLYLINE":
                items.append((layer, dxf.Poly(tuple((float(x), float(y)) for x, y in e.get_points("xy")), bool(e.closed))))
            elif t == "TEXT":
                aligned = e.dxf.halign or e.dxf.valign
                at = xy(e.dxf.align_point if aligned else e.dxf.insert)
                items.append((layer, S.Text(at, float(e.dxf.height), str(e.dxf.text), float(e.dxf.rotation),
                                            int(e.dxf.halign), int(e.dxf.valign))))
            elif t == "SOLID":
                pts = [xy(e.dxf.vtx0), xy(e.dxf.vtx1), xy(e.dxf.vtx2), xy(e.dxf.vtx3)]
                if pts[3] == pts[2]:
                    pts.pop()
                items.append((layer, S.Solid(tuple(pts))))
            else:
                stray[t] += 1
        auditor = doc.audit()
        problems = [str(err.message) for err in auditor.errors] + [str(err.message) for err in auditor.fixes]
        layers = {l.dxf.name: (int(l.dxf.color), str(l.dxf.linetype).upper()) for l in doc.layers}
        linetypes = {str(lt.dxf.name).upper(): tuple(float(t.value) for t in lt.pattern_tags.tags if t.code == 49)
                     for lt in doc.linetypes}
        extmax = doc.header.get("$EXTMAX", (0, 0, 0))
        return Doc(items, doc.header.get("$INSUNITS"), doc.acad_release, xy(extmax), layers, linetypes, comment_line(data),
                   problems, stray)
    except dxf.NeedsExtra:
        raise
    except Exception as e:      # noqa: BLE001 - ezdxf's DXFError family, and whatever a malformed file raises
        raise dxf.Unreadable(f"ezdxf cannot read it: {type(e).__name__}: {e}") from None


def comment_line(data: bytes) -> str:
    """The comment (group 999) a file starts with."""
    lines = data.decode("ascii", "replace").split("\n", 2)
    return lines[1] if lines and lines[0].strip() == "999" and len(lines) > 1 else ""


# ─── Pens ────────────────────────────────────────────────────────────────────

def pattern_of(doc: Doc, layer: str) -> tuple:
    """The dash pattern, in mm, a layer draws with: its linetype's, as the file says."""
    colour, lt = doc.layers.get(layer, (7, "CONTINUOUS"))
    pat = doc.linetypes.get(lt, ())
    return tuple(abs(x) for x in pat) if pat else ()


def pen_of(layer: str) -> float:
    return S.LAYERS[layer].width if layer in S.LAYERS else 0.25


def stroke_of(layer: str) -> str:
    return "#cc0000" if layer == dxf.STAMP_LAYER else "#000000"


def _n(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def arc_points(p) -> tuple:
    """(start angle, sweep) of an Arc in radians, counter-clockwise."""
    a0 = math.radians(p.a0)
    sweep = math.radians((p.a1 - p.a0) % 360.0 or 360.0)
    return a0, sweep


def flat(p) -> list:
    """An ellipse, spline or polyline as the points of a polyline."""
    if isinstance(p, dxf.Poly):
        return [tuple(q) for q in p.points] + ([tuple(p.points[0])] if p.closed else [])
    return [tuple(map(float, q)) for q in dxf.flatten(p, 0.01)]


# ─── SVG ─────────────────────────────────────────────────────────────────────

def svg(doc: Doc, title: str) -> bytes:
    """A plain SVG of the sheet, y turned over (SVG's y points down), one element for each entity of the file."""
    W, H = doc.extmax
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")      # noqa: E731
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(W)}mm" height="{_n(H)}mm" viewBox="0 0 {_n(W)} {_n(H)}">',
           f"<title>{esc(title)}</title>",
           f'<rect x="0" y="0" width="{_n(W)}" height="{_n(H)}" fill="#ffffff"/>']

    def attrs(layer: str) -> str:
        pat = pattern_of(doc, layer)
        dash = f' stroke-dasharray="{" ".join(_n(d) for d in pat)}"' if pat else ""
        return (f'class="{layer}" fill="none" stroke="{stroke_of(layer)}" stroke-width="{_n(pen_of(layer))}"'
                f'{dash} stroke-linecap="butt" stroke-linejoin="miter"')

    for layer, g in doc.items:
        if isinstance(g, dxf.Line):
            out.append(f'<line x1="{_n(g.a[0])}" y1="{_n(H - g.a[1])}" x2="{_n(g.b[0])}" y2="{_n(H - g.b[1])}" {attrs(layer)}/>')
        elif isinstance(g, dxf.Circle):
            out.append(f'<circle cx="{_n(g.c[0])}" cy="{_n(H - g.c[1])}" r="{_n(g.r)}" {attrs(layer)}/>')
        elif isinstance(g, dxf.Arc):
            a0, sweep = arc_points(g)
            p0 = (g.c[0] + g.r * math.cos(a0), g.c[1] + g.r * math.sin(a0))
            p1 = (g.c[0] + g.r * math.cos(a0 + sweep), g.c[1] + g.r * math.sin(a0 + sweep))
            large = 1 if sweep > math.pi else 0
            out.append(f'<path d="M {_n(p0[0])} {_n(H - p0[1])} A {_n(g.r)} {_n(g.r)} 0 {large} 0 {_n(p1[0])} {_n(H - p1[1])}" {attrs(layer)}/>')
        elif isinstance(g, S.Text):
            anchor = {0: "start", 1: "middle", 2: "end"}[g.halign]
            tr = f' transform="rotate({_n(-g.rotation)} {_n(g.at[0])} {_n(H - g.at[1])})"' if g.rotation else ""
            colour = stroke_of(layer)
            out.append(f'<text x="{_n(g.at[0])}" y="{_n(H - g.at[1])}" font-family="Helvetica, Arial, sans-serif" '
                       f'font-size="{_n(g.height)}" text-anchor="{anchor}" fill="{colour}" xml:space="preserve"{tr}>'
                       f'{esc(S.display(g.value))}</text>')
        elif isinstance(g, S.Solid):
            pts = " ".join(f"{_n(x)},{_n(H - y)}" for x, y in g.pts)
            out.append(f'<polygon points="{pts}" fill="{stroke_of(layer)}" stroke="none"/>')
        else:
            pts = " ".join(f"{_n(x)},{_n(H - y)}" for x, y in flat(g))
            out.append(f'<polyline points="{pts}" {attrs(layer)}/>')
    out.append("</svg>")
    return ("\n".join(out) + "\n").encode("utf-8")


# ─── PDF ─────────────────────────────────────────────────────────────────────

def _pdf_text(value: str) -> bytes:
    """A string for a PDF literal in WinAnsiEncoding, escaped."""
    raw = S.display(value).encode("cp1252", "replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _bezier(cx: float, cy: float, r: float, a0: float, sweep: float) -> list:
    """Cubic Bezier segments (p1, p2, p3) from the arc's start point, at most a quarter turn each."""
    n = max(1, math.ceil(abs(sweep) / (math.pi / 2.0) - 1e-9))
    d = sweep / n
    k = 4.0 / 3.0 * math.tan(d / 4.0)
    segs = []
    for i in range(n):
        s, e = a0 + i * d, a0 + (i + 1) * d
        p0 = (cx + r * math.cos(s), cy + r * math.sin(s))
        p3 = (cx + r * math.cos(e), cy + r * math.sin(e))
        p1 = (p0[0] - k * r * math.sin(s), p0[1] + k * r * math.cos(s))
        p2 = (p3[0] + k * r * math.sin(e), p3[1] - k * r * math.cos(e))
        segs.append((p1, p2, p3))
    return segs


def content(doc: Doc) -> bytes:
    """The page's content stream: the sheet in millimetres (the first operator scales to points)."""
    ops = [f"q {PT:.9f} 0 0 {PT:.9f} 0 0 cm", "0 J 0 j 10 M"]
    pen = None
    for layer, g in doc.items:
        if isinstance(g, S.Text):
            r, gr, b = (0.8, 0.0, 0.0) if layer == dxf.STAMP_LAYER else (0.0, 0.0, 0.0)
            width = S.text_width(g.value, g.height)
            shift = {0: 0.0, 1: width / 2.0, 2: width}[g.halign]
            ang = math.radians(g.rotation)
            c, s_ = math.cos(ang), math.sin(ang)
            x, y = g.at[0] - shift * c, g.at[1] - shift * s_
            ops.append(f"{_n(r)} {_n(gr)} {_n(b)} rg BT /F1 {_n(g.height)} Tf {_n(c)} {_n(s_)} {_n(-s_)} {_n(c)} {_n(x)} {_n(y)} Tm "
                       + _pdf_text(g.value).decode("latin-1") + " Tj ET")
            continue
        if isinstance(g, S.Solid):
            r, gr, b = (0.8, 0.0, 0.0) if layer == dxf.STAMP_LAYER else (0.0, 0.0, 0.0)
            pts = list(g.pts)
            ops.append(f"{_n(r)} {_n(gr)} {_n(b)} rg {_n(pts[0][0])} {_n(pts[0][1])} m "
                       + " ".join(f"{_n(x)} {_n(y)} l" for x, y in pts[1:]) + " h f")
            continue
        if layer != pen:
            width = pen_of(layer)
            pat = pattern_of(doc, layer)
            r, gr, b = (0.8, 0.0, 0.0) if layer == dxf.STAMP_LAYER else (0.0, 0.0, 0.0)
            ops.append(f"{_n(width)} w [{' '.join(_n(d) for d in pat)}] 0 d {_n(r)} {_n(gr)} {_n(b)} RG")
            pen = layer
        if isinstance(g, dxf.Line):
            ops.append(f"{_n(g.a[0])} {_n(g.a[1])} m {_n(g.b[0])} {_n(g.b[1])} l S")
        elif isinstance(g, (dxf.Circle, dxf.Arc)):
            a0, sweep = (0.0, 2.0 * math.pi) if isinstance(g, dxf.Circle) else arc_points(g)
            start = (g.c[0] + g.r * math.cos(a0), g.c[1] + g.r * math.sin(a0))
            segs = " ".join(f"{_n(p1[0])} {_n(p1[1])} {_n(p2[0])} {_n(p2[1])} {_n(p3[0])} {_n(p3[1])} c"
                            for p1, p2, p3 in _bezier(g.c[0], g.c[1], g.r, a0, sweep))
            ops.append(f"{_n(start[0])} {_n(start[1])} m {segs} S")
        else:
            pts = flat(g)
            ops.append(f"{_n(pts[0][0])} {_n(pts[0][1])} m " + " ".join(f"{_n(x)} {_n(y)} l" for x, y in pts[1:]) + " S")
    ops.append("Q")
    return ("\n".join(ops) + "\n").encode("latin-1")


def pdf(doc: Doc, title: str) -> bytes:
    """A one page PDF of the sheet (see the module docstring)."""
    W, H = doc.extmax
    stream = content(doc)
    safe = S.display(title).encode("cp1252", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_n(W * PT)} {_n(H * PT)}] /Contents 4 0 R "
        f"/Resources << /Font << /F1 5 0 R >> >> >>".encode(),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Title (" + safe + b") /Creator (cad-agent) /Producer (cad-agent) >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)
