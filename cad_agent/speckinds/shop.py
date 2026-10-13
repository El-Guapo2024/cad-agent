"""[shop]: the bill of materials and the shop files a design promises. Opt-in, and judged once.

    [shop]
    bom = { chassis = 1, wheel = 2 }       # optional: how many of each BOM line there are, by its name
    orderable = true                       # optional: every bought line has a vendor and a part number
    mass = "known"                         # optional: every line has a mass with its source; "any" is the default
    files = ["chassis.dxf", "wheel.3mf"]   # optional: files `cad shop` must make

A spec with a `[shop]` table (empty is enough) says this design is going to a shop, and from then on three things
are held to it in `cad check` and `cad verify`, which a design without the table is not held to:

  - the part rules of the shop run on every part (ruleset/shop.py): a laser part is a through-cut and its DXF reads
    back to the mid-plane section, a printed part's 3MF reads back watertight with the solid's volume
  - this table's rows, below
  - for every made body, `shop file`: the part module the file is made from builds this body (bom.module_rows).
    A body assembly.py cuts, or builds with other parameters, would be made wrong, and that is a FAIL

What the keys judge, against the BOM that `cad bom` writes (bom.py: one line for each distinct thing, by `Name`;
a key may also be the name of one of a line's bodies):

  bom         for each name, the line's Quantity must be the number given. A name that is not a line, or is more
              than one, is an UNCHECKED row for that name. 0 says the thing must not be in the BOM: PASS if it is not
  orderable   true: each bought line needs a `vendor` and a `pn` in its declaration (bought.py). A line without
              them is UNCHECKED, naming what it lacks, because nothing is known and nothing is invented; none
              bought is N/A
  mass        "known": every line needs a mass with its source: volume x density of a MATERIAL for a made part,
              mass_g with a mass_source for a bought one. A stock body never has one, so a BOM with a stock line
              cannot ask for this. The lines without are one UNCHECKED row naming each and why. "any" asks nothing
  files       each name must be a file `cad shop` makes for this BOM: <part>.step for each made part, <part>.dxf for
              a laser_cut part, <part>.3mf and <part>.stl for an fdm part, bom.csv, bom.json, manifest.json. One that
              is not is a FAIL naming the part's process. A drawing, `drawings/<part>.dxf`, `.svg` or `.pdf`, is one
              cad shop makes for a cnc or laser_cut part that is a plate `cad drawing` can draw, and the BOM cannot say
              which are: so it is judged by asking what `cad shop` asks, `cad_agent.drawing.shop_drawings`, for the made
              parts of this project built from source. That is the list of the manifest's `drawings` block and of
              out/shop/drawings/, so a name that passes is a file the shop writes, and one that fails says why (the
              part is printed, is not a plate, its drawing did not pass its own gates: the reason `cad shop` gives in
              `skipped`). UNCHECKED when that cannot be asked: a part does not build, or the drawing module raised

and one summary row, `bom`, with the number of lines and bodies; UNCHECKED if the assembly has no bodies, since a
BOM of nothing says nothing. A key this section does not have is an UNCHECKED row for the entry, like any other kind.
Rows come after every other section's (order 90).
"""
from __future__ import annotations

from ..registry import spec_kind
from .kit import Unusable, row

KEYS = ("bom", "orderable", "mass", "files")
MASSES = ("known", "any")
ALWAYS = ("bom.csv", "bom.json", "manifest.json")      # what cad shop writes whatever the parts are


@spec_kind("shop", order=90, table=True)
def shop(entry: dict, ctx):
    """The BOM and shop files a design promises: quantities, vendors and part numbers, masses, files (opt-in)."""
    from .. import bom as bomlib
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        raise Unusable(f"[shop] does not take {', '.join(unknown)} (keys: {', '.join(KEYS)})")
    quantities = _quantities(entry.get("bom"))
    orderable = entry.get("orderable", False)
    if not isinstance(orderable, bool):
        raise Unusable(f"orderable must be true or false, got {orderable!r}")
    mass = entry.get("mass", "any")
    if mass not in MASSES:
        raise Unusable(f"mass must be one of {', '.join(MASSES)}, got {mass!r}")
    files = entry.get("files", [])
    if not (isinstance(files, list) and all(isinstance(f, str) and f for f in files)):
        raise Unusable('files must be a list of file names, e.g. ["chassis.dxf", "wheel.3mf"]')

    if ctx.parts:
        bill = bomlib.from_parts(ctx.slug, ctx.parts, ctx.bodies)
        solids = ctx.parts
    else:
        bill = bomlib.build(ctx.slug, ctx.machine)
        solids = bill.solids
    leaves = [ln for ln in bill.lines if ln.kind != "assembly"]
    t = bill.totals()
    if not bill.lines:
        yield row("bom", "shop", "UNCHECKED", "the assembly has no bodies, so there is no BOM to hold anything to",
                  "a BOM with at least one line", bomlib.FREECAD)
        return
    yield row("bom", "shop", "PASS", f"{t['lines']} lines, {t['bodies']} bodies, {sum(1 for ln in leaves if ln.shop_files)} "
                                     "to be made here", "a BOM that can be built", bomlib.FREECAD)

    for name, want in quantities.items():
        yield _quantity(bill, name, want)
    if orderable:
        yield from _orderable(leaves)
    if mass == "known":
        yield _mass(leaves, t)
    if files:
        yield from _files(ctx.slug, bill, files)
    for r in bomlib.module_rows(ctx.slug, bill, solids, rule="spec/shop file"):
        yield r


def _quantities(raw) -> dict:
    if raw is None:
        return {}
    if not (isinstance(raw, dict) and all(isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0
                                          for k, v in raw.items())):
        raise Unusable("bom must map BOM line names to whole numbers, e.g. { wheel = 2 }")
    return raw


def _quantity(bill, name: str, want: int):
    hits = [ln for ln in bill.lines if ln.name == name or name in ln.bodies]
    limit = f"{want} of {name}"
    source = "the Quantity of the BOM line (bom.py)"
    if not hits:
        if want == 0:
            return row(name, "shop", "PASS", "not in the BOM", limit, source)
        return row(name, "shop", "UNCHECKED", f"no BOM line or body called {name!r} (lines: "
                   f"{', '.join(ln.name for ln in bill.lines)})", limit, source)
    if len(hits) > 1:
        return row(name, "shop", "UNCHECKED", f"{name!r} is more than one BOM line: "
                   f"{', '.join(f'{ln.index} {ln.name}' for ln in hits)}", limit, source)
    got = hits[0].quantity
    return row(name, "shop", "PASS" if got == want else "FAIL", f"{got} in the BOM ({', '.join(hits[0].bodies)})", limit, source)


def _orderable(leaves):
    bought = [ln for ln in leaves if ln.kind == "bought"]
    limit, source = "a vendor and a part number, declared", "vendor and pn in the bought part's sidecar or module (bought.py)"
    if not bought:
        yield row("bought parts", "shop", "N/A", "nothing bought", limit, source)
        return
    lacking = [(ln, [w for w, v in (("a vendor", ln.vendor), ("a part number", ln.pn)) if not v]) for ln in bought]
    lacking = [(ln, what) for ln, what in lacking if what]
    for ln, what in lacking:
        yield row(ln.name, "shop", "UNCHECKED", f"{ln.name} declares no {' and no '.join(w.split(' ', 1)[1] for w in what)}: "
                  "it cannot be ordered from the BOM", limit, source)
    if not lacking:
        yield row("bought parts", "shop", "PASS", f"{len(bought)} bought lines, each with a vendor and a part number", limit, source)


def _mass(leaves, totals):
    without = [ln for ln in leaves if ln.mass_g is None]
    limit, source = "a mass with its source for every line", "BodyInfo.mass_g (bodies.py): materials.py density, or a declared mass_g"
    if without:
        why = "; ".join(f"{ln.name} ({ln.mass_source.removeprefix('unknown: ')})" for ln in without)
        return row("masses", "shop", "UNCHECKED", f"{len(without)} of {len(leaves)} lines have no mass: {why}", limit, source)
    return row("masses", "shop", "PASS", f"every line has a mass, {totals['mass_known_g']:.2f} g in all", limit, source)


def _files(slug, bill, wanted: list):
    made = {ln.part: ln for ln in bill.lines if ln.shop_files}
    planned = {f for ln in made.values() for f in ln.shop_files} | set(ALWAYS)
    limit, source = "a file cad shop makes for this BOM", "the shop files of the BOM lines (bom.py)"
    drawn = None                                    # what cad shop draws, asked once and only if a drawing is named
    bad = 0
    for f in wanted:
        if f.startswith("drawings/"):
            drawn = drawn or _drawn(slug, bill)
            files, skipped, why = drawn
            if files is None:
                bad += 1
                yield row(f, "shop", "UNCHECKED", f"cannot say whether cad shop draws it: {why}", limit, _DRAWN)
            elif f not in files:
                bad += 1
                yield row(f, "shop", "FAIL", f"cad shop does not draw it: {_not_drawn(f, slug, bill, skipped)}", limit, _DRAWN)
        elif f not in planned:
            bad += 1
            stem, _, ext = f.rpartition(".")
            ln = made.get(stem)
            if ln is not None:
                why = f"{stem} is {ln.process or 'a part with no PROCESS'}, which gets {', '.join(ln.shop_files)}"
            elif stem and any(stem == (b.part or b.name) for b in bill.lines):
                why = f"{stem} is not made in this project"
            else:
                why = f"no part {stem!r} in the BOM"
            yield row(f, "shop", "FAIL", f"cad shop does not make it: {why}", limit, source)
    if not bad:
        yield row("files", "shop", "PASS", f"{len(wanted)} files, all made: {', '.join(wanted)}", limit, source)


_DRAWN = "the drawings cad_agent.drawing.shop_drawings makes for the made parts, which are the manifest's (shop.py)"


def _drawn(slug: str, bill) -> tuple:
    """(the paths `cad shop` would write under drawings/, why a part is not drawn by part, why not) for this project.

    It is the call `cad shop` makes (shop._drawings, on the parts built from source), so what it names is what the
    manifest's `drawings` block lists. The paths are None when it cannot be asked: a part that does not build (the
    part rules say so), a drawing module that is missing or raised."""
    from .. import shop as shoplib
    from .. import state as st
    made = {}
    for ln in bill.lines:
        if ln.kind == "made" and ln.project == slug and ln.part:
            made.setdefault(ln.part, ln.process)
    try:
        solids = {part: st.build_part(slug, part)[0] for part in sorted(made)}
    except Exception as e:      # noqa: BLE001 - a part that does not build is for the part rules to fail, not this
        return None, {}, f"{type(e).__name__}: {e}"
    drawings, rows = shoplib._drawings(slug, solids, made, None)
    if rows and rows[0].state != "PASS":
        return None, {}, rows[0].measured
    if not drawings["built"]:
        return None, {}, drawings.get("why") or "cad shop makes no drawings"
    return set(drawings["files"]), drawings["skipped"], None


def _not_drawn(name: str, slug: str, bill, skipped: dict) -> str:
    """Why `drawings/<part>.<ext>` is not among what cad shop draws."""
    stem, _, ext = name.removeprefix("drawings/").rpartition(".")
    if "/" in stem or not stem or ext not in ("dxf", "svg", "pdf"):
        return f"it writes drawings/<part>.dxf, .svg and .pdf, and {name} is none of them"
    if stem in skipped:
        return f"{stem} is not drawn: {skipped[stem]}"
    if any(ln.kind == "made" and ln.project == slug and ln.part == stem for ln in bill.lines):
        return f"{stem} is drawn, but not as {ext}"
    if any(stem == (ln.part or ln.name) for ln in bill.lines):
        return f"{stem} is not made in this project, so it is drawn by the project that makes it"
    return f"no part {stem!r} in the BOM"
