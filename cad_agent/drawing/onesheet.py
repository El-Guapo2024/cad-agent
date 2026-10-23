"""One plate to one sheet: analyse, project, lay out, write, read back, judge. Nothing here knows about the command."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..dxf import NeedsExtra
from ..registry import Row
from . import arrange as L
from . import hlr as V
from . import paper as S
from . import platefit as P
from . import readback as check
from . import writers as R

FORMATS = ("dxf", "svg", "pdf")
PROCESSES = ("cnc", "laser_cut")


@dataclass
class Made:
    part: str
    files: dict = field(default_factory=dict)       # extension -> bytes
    rows: list = field(default_factory=list)
    sheet: object = None
    plate: object = None
    seconds: dict = field(default_factory=dict)     # "face", "side": OCCT's hidden line removal; "total"
    unfit: str | None = None                        # why the part is not drawn

    def judged(self) -> bool:
        """Whether every row passed (a drawing that is not is not written)."""
        return not self.unfit and all(r.state in ("PASS", "N/A") for r in self.rows)


def scope_row(part: str, state: str, measured: str) -> Row:
    return Row(subject=part, rule="scope", state=state, measured=measured, check="drawing",
               limit="a prism along its thinnest axis: an outline of straight sides and equal corner radii, with round holes, "
                     "slots and rectangular windows all the way through, their sides along the part's own axes",
               source="dxf.faces_report and through_cut (the faces), the loops of the end face, and spec.holes (the hole finder)")


def judge(part: str, rule: str, gate, *args) -> Row:
    """The row of a gate. One that raises is UNCHECKED and says what it raised: never a crash, and never a pass."""
    try:
        return gate(*args)
    except Exception as e:      # noqa: BLE001 - a rule must not take the run down
        return check.row(part, rule, "UNCHECKED", f"the gate could not be run: {type(e).__name__}: {e}", "the gate runs and passes")


def views_of(solid, plate: P.Plate, angle: str) -> tuple:
    """(face view, side view): the face from the positive side of the thin axis, the side from the left in first angle
    projection and from the right in third, as TechDraw's ProjectionType puts them (DrawProjGroup::getViewIndex)."""
    u, n = plate.frame.u, plate.frame.n
    neg = lambda t: tuple(-x for x in t)                    # noqa: E731
    face = V.project(solid, "face", n, u)
    side = V.project(solid, "left", neg(u), n) if angle == "first" else V.project(solid, "right", u, neg(n))
    return face, side


def make(part: str, solid, meta: dict, angle: str = "first", size: str | None = None, scale: tuple | None = None,
         formats: tuple = FORMATS) -> Made:
    """The drawing of one plate. `meta` is the title block's facts: part, project, material, process, commit, dirty, stamp.

    A part that is not a plate comes back `unfit` with the sentence that says why, and nothing is drawn. Otherwise the
    files are made and every row of readback.py is judged; the caller writes them only if `judged()`.
    """
    t0 = time.perf_counter()
    made = Made(part)
    # a DXF of this kind holds ASCII: a part called after an accent is drawn without it (its files keep their names)
    meta = {**meta, **{k: S.ascii_text(meta[k]) for k in ("part", "project", "material", "process") if isinstance(meta.get(k), str)}}
    try:
        plate = P.analyse(solid)
    except P.Unfit as e:
        made.unfit = str(e)
        made.rows.append(scope_row(part, "UNCHECKED", f"{part} is not a plate this drawing can show: {e}"))
        return made
    made.plate = plate
    made.rows.append(scope_row(part, "PASS", plate.describe() + f" (outline read from the {plate.source})"))
    try:
        face, side = views_of(solid, plate, angle)
    except Exception as e:      # noqa: BLE001 - a kernel that cannot project is not a drawing
        made.rows.append(check.row(part, "views", "UNCHECKED", f"the views could not be made: {type(e).__name__}: {e}",
                                   "OCCT's hidden line removal gives both views", V.SOURCE))
        return made
    made.seconds = {"face": face.seconds, "side": side.seconds}
    made.rows.append(check.row(part, "views", "PASS",
                               f"face view {len(face.visible)} visible, {len(face.hidden)} hidden and {len(face.smooth)} smooth entities, "
                               f"side view {len(side.visible)}, {len(side.hidden)} and {len(side.smooth)}", "OCCT's hidden line removal gives both views", V.SOURCE))
    try:
        sheet = L.build(plate, face, side, meta, angle, size, scale)
    except L.DoesNotFit:
        raise
    except P.Unfit as e:
        made.unfit = str(e)
        made.rows[0] = scope_row(part, "UNCHECKED", f"{part} cannot be laid out on a sheet: {e}")
        return made
    made.sheet = sheet
    data = R.write(sheet, meta)
    made.files["dxf"] = data
    made.rows.append(judge(part, "dimensions", check.dimensions_row, part, plate))
    try:
        doc = R.read(data)
    except NeedsExtra:
        raise
    except Exception as e:      # noqa: BLE001 - the master that cannot be read back is not passed
        made.rows.append(check.row(part, "sheet", "FAIL", f"the DXF does not read back: {e}", "the DXF reads back with ezdxf"))
        return made
    title = f"{meta['project']}/{meta['part']}"
    made.rows.append(judge(part, "sheet", check.sheet_row, part, plate, doc, data, meta, angle, meta.get("stamp")))
    made.rows.append(judge(part, "layout", check.layout_row, part, doc))
    if "svg" in formats:
        made.files["svg"] = R.svg(doc, title)
        made.rows.append(judge(part, "svg", check.svg_row, part, doc, made.files["svg"]))
    if "pdf" in formats:
        made.files["pdf"] = R.pdf(doc, title)
        made.rows.append(judge(part, "pdf", check.pdf_row, part, doc, made.files["pdf"]))
    made.seconds["total"] = time.perf_counter() - t0
    return made
