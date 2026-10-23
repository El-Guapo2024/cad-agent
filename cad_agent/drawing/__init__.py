"""`cad drawing`: a dimensioned drawing of one machined or laser-cut plate, a port of what TechDraw does for it.

    cad drawing <slug> <part>                        out/drawings/<part>.dxf, .svg and .pdf, first angle projection
    cad drawing <slug> <part> --angle third          third angle projection
    cad drawing <slug> <part> --format dxf,pdf       only these (the DXF is the master and is always made)
    cad drawing <slug> <part> --sheet A3 --scale 1:2 a sheet and a scale, from ISO 5457 and ISO 5455

What it draws. The face of the plate and its thickness, in two views, with the overall sizes, the position of every
hole, slot and window from the lower-left corner, a letter and a callout for each size of cutout, and the general
tolerance of ISO 2768-m. A title block carries the part, the project, the material, the process, the scale, the sheet,
the projection, the commit, and whether the design is verified: NOT VERIFIED, in red and in a banner, unless `cad done`
holds for the commit. arrange.py has the sheet, readback.py the gates, platefit.py what a plate is.

What it does not draw. Machined plates and laser-cut sheets only: a prism along its thinnest axis whose features all go
through (platefit.py says exactly which). No sections, no GD&T, no tolerances beyond the general one (so a fit that needs
a tighter one is not on the sheet), no threads, no countersinks or counterbores, no sheet metal, nothing printed (fdm),
and no zone grid on the frame (ISO 5457 recommends one). A part that is none of these is not drawn, and nothing is written
for it: exit 3 where the request is wrong (a printed part, a part with no PROCESS, a part of a sub-assembly), exit 2 with
the reason where it is the part that is not a plate. A wrong drawing is worse than none. A size ISO 2768-m has no tolerance
for (under 0.5 mm, over 4000 mm) is drawn, and the notes say it has none.

Where the drawing comes from, and what is ported
-------------------------------------------------
FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6, LGPL-2.1-or-later), src/Mod/TechDraw/App:

  GeometryObject.cpp   `projectShape` and `makeTDGeometry`: hidden line removal with OCCT's HLRBRep_Algo, the hard and
                       outline edges visible and hidden, and the smooth edges visible (hlr.py has the whole account).
                       That file only classes the edges; the hidden ones are dashed and the smooth ones drawn thin in
                       src/Mod/TechDraw/Gui/QGIViewPart.cpp:461-473
  DrawProjGroup.cpp    `ProjectionTypeEnums` and `getViewIndex`: first angle puts the view from the left to the right of the
                       front view, third angle the view from the right; the default, `Preferences::projectionAngle`, is
                       first angle, and so it is here, as it is in ISO 128-30
  DrawViewPart.cpp     `getProjectionCS`: the view direction is the Z of the coordinate system, XDirection the sheet's
                       horizontal, Y = Z x X
  src/Mod/Import/App/dxf/ImpExpDxf.cpp and dxf.cpp: the DXF, as dxf.py writes it, with layers, linetypes, text and
                       arrowheads added (R14 has no lineweights, so the SVG and PDF apply them per layer)

Dimensions are not TechDraw's: its dimension objects belong to the views of a document, and the sheet here is a file. They
are drawn the way ISO 129-1 draws them and their numbers come from the B-rep (the outline and `spec.holes`).

The formats
-----------
The DXF is the master. The SVG and the PDF are drawn from what ezdxf reads in it (writers.py), by code of this module and
no library: the PDF is written by hand (standard Helvetica, vector, uncompressed), so drawings have no extra of pyproject.toml
(ezdxf, which reads the DXF back, is a core dependency) and nothing here raises ImportError for a plotting package. Every
file is the same bytes for the same part on one kernel. OCCT 7.9 and 8.0 give the same lines to about 1e-9 mm, in another
order and cut in other places; hlr.py puts them on a 1e-4 mm grid, joins what touches and sorts it, and the sheet is the
same entities on both.

Gates and exit codes
--------------------
Every drawing is judged before it is written (readback.py): the plate the printed numbers describe equals the solid's end
face; the DXF read back by ezdxf draws that plate at its stated scale with each ordinate and dimension line at the length
its number says; no two labels overlap; the SVG and the PDF have an element for each entity of the DXF. Rows are PASS,
FAIL or UNCHECKED as everywhere else.

    0  drawn, every row PASS, and `cad done` holds, so the sheet is not stamped
    1  a row FAIL (the sheet would say something the plate does not) or the part did not build; nothing is written
    2  UNCHECKED: the part is not a plate, a row could not be settled (a label that cannot be kept off another, a
       plate no sheet holds), or the design is not done (then the files are written, stamped NOT VERIFIED, and it
       exits 2, as `cad shop --draft` does)
    3  usage: unknown project or part, a printed part, no PROCESS, a "/" in the part name (draw it from the child
       project), a bad --format, --sheet or --scale, or a sheet that cannot hold what the arguments asked for
    4  crash

`--json` gives project, part, process, angle, done and reasons (what `cad done` says), stamp, plate (what was recognised),
sheet (size and scale), rows (the ones not passing, all with --all), rows_total, wrote (paths), files (path, sha256, bytes)
and hlr_seconds (OCCT's hidden line removal for the face and the side view, and the whole drawing).

`cad shop` calls `shop_drawings` (below) for the parts it makes, which writes the same files under drawings/ of out/shop/,
so a drawing is made for each cnc and laser_cut plate of a verified design and the manifest lists it.

What it costs
-------------
Slow hidden line removal was a risk of the plan, and for a plate it is small. On the plates of the eval reference designs,
with the kernel loaded (best of five), OCCT 7.9 takes 2 to 6 ms for the face view and 5 to 54 ms for the side view, where the
dashed holes are (laser_panel/panel 4 and 54, nema17_mount/bracket 2 and 48, the pcb_enclosure lid 6 and 5); OCCT 8.0 is the
same within a few ms. The side view grows with the holes: about 150 ms with 20 and 450 ms with 40, the most a sheet takes.
A whole drawing (plate recognised, both views, sheet, three files, every gate) takes 75 to 180 ms on those plates and
0.7 s with 40 holes, plus the one time a process loads the kernel.
"""
from __future__ import annotations

from .. import cmdbase
from .. import state as st
from ..cmdbase import OK, UNCHECKED, Result, UsageError

FORMATS = ("dxf", "svg", "pdf")
PROCESSES = ("cnc", "laser_cut")
SIZES = ("A4", "A3", "A2", "A1", "A0")
STAMP = "NOT VERIFIED"


def add_drawing_arguments(p) -> None:
    p.add_argument("slug")
    p.add_argument("part", help="a part module of the project (a child project's part is drawn from the child)")
    p.add_argument("--angle", choices=("first", "third"), default="first",
                   help="projection angle: first (ISO 128-30, TechDraw's default) or third")
    p.add_argument("--format", default=",".join(FORMATS), metavar="LIST",
                   help="comma list of dxf, svg, pdf; the DXF is always made, the others are drawn from it")
    p.add_argument("--sheet", default="auto", metavar="SIZE", help="A4, A3, A2, A1, A0 or auto (the smallest the views fit)")
    p.add_argument("--scale", default="auto", metavar="N:M", help="a scale of ISO 5455 such as 1:1, 1:2 or 2:1, or auto")
    p.add_argument("--out", metavar="DIR", help="write here instead of out/drawings in the project")
    p.add_argument("--all", action="store_true", help="show passing rows too")


ARGUMENTS = {"drawing": add_drawing_arguments}


def _meta(slug: str, part: str, meta: dict, git: dict | None, stamp: str | None) -> dict:
    return {"part": part, "project": slug, "material": meta.get("material"), "process": meta.get("process"),
            "commit": (git or {}).get("commit"), "dirty": bool((git or {}).get("dirty")), "stamp": stamp}


def _built(slug: str, part: str, process: str) -> dict:
    """What the title block needs of a part module: its MATERIAL, from the build `cad shop` already made if there is one.
    A part that cannot be got has no material the sheet can state, and says so."""
    try:
        return st.built_meta(slug, part) or st.build_part(slug, part)[1]
    except Exception:           # noqa: BLE001 - the solid is in hand; only the material is missing
        return {"material": None, "process": process}


def _options(a) -> tuple:
    from . import paper as S
    formats = tuple(f.strip().lower() for f in a.format.split(",") if f.strip())
    bad = [f for f in formats if f not in FORMATS]
    if bad or not formats:
        raise UsageError(f"--format takes a comma list of {', '.join(FORMATS)}, got {a.format!r}")
    size = None if a.sheet.lower() == "auto" else a.sheet.upper()
    if size is not None and size not in SIZES:
        raise UsageError(f"--sheet is one of {', '.join(SIZES)} or auto, got {a.sheet!r}")
    scale = None
    if a.scale.lower() != "auto":
        try:
            scale = S.parse_scale(a.scale)
        except ValueError as e:
            raise UsageError(str(e)) from None
    return formats, size, scale


def cmd_drawing(a) -> Result:
    """`cad drawing <slug> <part>`: the part as a dimensioned drawing in DXF, SVG and PDF."""
    import hashlib
    from pathlib import Path

    from .. import subassembly, verify
    from ..dxf import NeedsExtra
    from . import onesheet as draw
    from .arrange import DoesNotFit
    pdir = cmdbase.project(a.slug)
    if "/" in a.part:
        child, _, rest = a.part.partition("/")
        project = subassembly.instance_project(pdir, child) or child       # the instance's name is not its project's
        raise UsageError(f"{a.part!r} is a body of the sub-assembly {child!r}, not a part of {a.slug}: a child's part is drawn "
                         f"by the child project, `cad drawing {project} {rest}`")
    cmdbase.part(a.slug, a.part)
    formats, size, scale = _options(a)
    try:
        solid, built = cmdbase.build(a.slug, a.part)
    except cmdbase.BuildFailed:
        raise
    process = built.get("process")
    if process not in PROCESSES:
        what = (f"{a.part} declares no PROCESS in parts/{a.part}.py" if process is None
                else f"{a.part} is made by {process!r} (PROCESS in parts/{a.part}.py)")
        raise UsageError(f"{what}: cad drawing draws parts made by 'cnc' (machined) or 'laser_cut', and says so in the module")
    status = verify.status(a.slug)
    git = verify.git_info(pdir)
    stamp = None if status["done"] else STAMP
    meta = _meta(a.slug, a.part, built, git, stamp)
    try:
        made = draw.make(a.part, solid, meta, a.angle, size, scale, formats)
    except DoesNotFit as e:
        if size or scale:
            raise UsageError(str(e)) from None
        made = draw.Made(a.part, unfit=str(e))
        made.rows.append(draw.scope_row(a.part, "UNCHECKED", f"{a.part} does not fit a sheet: {e}"))
    except NeedsExtra as e:
        raise UsageError(str(e)) from None
    rows = [r.as_dict() for r in made.rows]
    code = cmdbase.verdict(r["state"] for r in rows)
    bad = [r for r in rows if r["state"] in ("FAIL", "UNCHECKED")]
    folder = (pdir / "out" / "drawings") if not a.out else Path(a.out).expanduser()
    stem = subassembly.file_stem(a.part)
    data = {"project": a.slug, "part": a.part, "process": process, "angle": a.angle, "done": status["done"],
            "reasons": status["reasons"], "stamp": stamp, "plate": made.plate.describe() if made.plate else None,
            "sheet": {"size": made.sheet.size, "scale": f"{made.sheet.scale[0]}:{made.sheet.scale[1]}"} if made.sheet else None,
            "rows": rows if a.all else bad, "rows_total": len(rows), "wrote": [],
            "hlr_seconds": {k: round(v, 4) for k, v in made.seconds.items()},
            "files": [{"path": f"{stem}.{ext}", "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
                      for ext, b in sorted(made.files.items()) if ext in formats]}
    head = f"{a.slug}/{a.part}  cad drawing"
    lines = [head + (f": {made.sheet.size} {made.sheet.scale[0]}:{made.sheet.scale[1]}, {a.angle} angle"
                     + (f"  [{STAMP}]" if stamp else "") if made.sheet else "")]
    lines += cmdbase.rows_text(rows, a.all)
    if not made.judged():
        lines.append("  nothing was written: " + ("the part is not a plate this drawing can show" if made.unfit
                                                   else "a row failed" if code == 1 else "a row could not be settled"))
        return Result(code if code != OK else UNCHECKED, data, "\n".join(lines),
                      f"not drawn: {made.unfit or f'{len(bad)} rows not passing'}")
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for ext in formats:
        path = folder / f"{stem}.{ext}"
        _write(path, made.files[ext])
        written.append(str(path))
    data["wrote"] = written
    lines.append(f"  wrote {', '.join(written)}")
    if stamp:
        code = UNCHECKED            # every row passed, and the design is not one anybody verified
    return Result(code, data, "\n".join(lines), f"{'draft: ' if stamp else ''}wrote {len(written)} files", written)


def _write(path, data: bytes) -> None:
    import os
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


# ─── The hook of `cad shop` ──────────────────────────────────────────────────

def shop_drawings(slug: str, parts: dict, processes: dict, stamp: str | None) -> dict:
    """The drawings `cad shop` puts in out/shop/drawings/ (shop.py has the contract of the hook).

    `parts` maps each part the run makes to its solid, `processes` to its PROCESS, `stamp` is "NOT VERIFIED" or None.
    Every cnc and laser_cut part that is a plate is drawn in first angle projection as DXF, SVG and PDF, named by
    `subassembly.file_stem`; a part of a child project is not here, the child draws its own. A part that is not drawn
    is in `skipped` with the reason, and a part whose drawing does not pass its own gates is skipped, never written:
    the shop is not stopped by a plate that cannot be drawn, it just goes without one.
    """
    from .. import subassembly, verify
    from . import onesheet as draw
    from .arrange import DoesNotFit
    pdir = st.project_dir(slug)
    git = verify.git_info(pdir)
    files: dict = {}
    skipped: dict = {}
    for part in sorted(parts):
        process = processes.get(part)
        if process not in PROCESSES:
            skipped[part] = (f"made by {process!r}, and drawings are for cnc and laser_cut parts" if process
                             else "declares no PROCESS, so it is not known to be machined or cut")
            continue
        try:
            made = draw.make(part, parts[part], _meta(slug, part, _built(slug, part, process), git, stamp))
        except DoesNotFit as e:
            skipped[part] = str(e)
            continue
        except Exception as e:      # noqa: BLE001 - a part that cannot be drawn is skipped and says why, it does not stop the shop
            skipped[part] = f"its drawing could not be made: {type(e).__name__}: {e}"
            continue
        if made.unfit:
            skipped[part] = f"not a plate this drawing can show: {made.unfit}"
        elif not made.judged():
            why = "; ".join(f"{r.rule}: {r.measured}" for r in made.rows if r.state not in ("PASS", "N/A"))
            skipped[part] = f"its drawing did not pass its own gates: {why}"
        else:
            for ext in draw.FORMATS:
                files[f"drawings/{subassembly.file_stem(part)}.{ext}"] = made.files[ext]
    return {"files": files, "skipped": skipped}
