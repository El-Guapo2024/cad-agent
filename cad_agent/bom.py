"""The bill of materials of a project's assembly: FreeCAD's BOM, with what a shop needs added.

`cad bom <slug>` lists what the machine is made of, one line for each distinct thing, with how many, and
writes `out/bom.csv` and `out/bom.json`. `cad shop` writes the same two files into out/shop/.

What it ports
-------------
FreeCAD's Assembly workbench makes a BOM with `Assembly_CreateBom` (src/Mod/Assembly/CommandCreateBom.py, which
holds the columns and the options, and App/BomObject.cpp, which fills the sheet; FreeCAD commit 3160daf1e2b6,
LGPL-2.1-or-later). This is that, for an assembly that is a dict of bodies:

  columns     Index, Name, Description, File Name, Quantity: the five FreeCAD starts a BOM with, first and in its
              order, so a tool that reads FreeCAD's reads these. The Index is hierarchical ("2", "2.1"), the
              Quantity counts the siblings that are the same thing (BomObject::addObjectChildrenToBom folds a
              link to an object it has listed into that line and adds one), and the File Name is the file that
              defines the thing (FreeCAD: the document's)
  options     `detailSubAssemblies` (default on): a sub-assembly is a line and its parts follow it, indented one
              level (`--flat` turns it off); `onlyParts` (default off): only made parts and sub-assemblies, the
              solids of FreeCAD's "Only parts" being what is bought or stock here (`--only-parts`);
              `detailParts` has nothing to do here, since a part of this harness is one solid
  mirrors     FreeCAD keeps a mirrored link on a line of its own. A body that `mirror()` made has lost what
              it was (bodies.py), so a stock body is joined to the made or bought line it has the shape and the
              name stem of (motor_right to motor_left, a tt_motor) and the line says so in Notes

and adds what a shop wants to know of each line, from the bodies (bodies.py) and the bought contract (bought.py):

  Kind        made (a part module), bought, stock (assembly.py builds it) or assembly (a sub-assembly)
  Material    the MATERIAL of a made part, the declared `material` of a bought one
  Process     the PROCESS of a made part: laser_cut, fdm, cnc
  Vendor, PN, Licence, Source
              what a bought part declares; Source is where its geometry came from, or parts/<part>.py
  Mass (g)    each: volume x density for a made part, the declared mass_g for a bought one, and the word
              `unknown` for the rest. Mass source says where the number came from, or why there is none; a
              mass is never filled in. The totals say how many bodies they leave out
  Shop file   what `cad shop` writes for it: <part>.dxf for a laser part, <part>.3mf for a printed one,
              <part>.step for the rest (the others it writes too are in bom.json)
  Bodies      the bodies of assembly.py the line stands for

Two bodies are the same thing when they are the same kind from the same part (or the same stock name stem) and
have the same shape: volume and area to one part in a million, and the same number of faces, wherever they stand
and however they are turned. A part module built twice with other parameters is therefore two lines, and so is
a part assembly.py cuts. A project with no assembly.py has one line for each part module and bought part.

A body whose project is not this one comes from a sub-assembly (step 6, piece B): its name is `child/body`, and
the BOM nests by those names without needing to know more of the sub-assembly than that.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field

from . import cmdbase
from . import state as st
from .cmdbase import OK, Result, UsageError
from .registry import Row

COLUMNS = ("Index", "Name", "Description", "File Name", "Quantity", "Kind", "Material", "Process", "Vendor", "PN",
           "Licence", "Source", "Mass (g)", "Mass source", "Shop file", "Bodies", "Notes")
PROCESS_FILES = {"laser_cut": ("dxf",), "fdm": ("3mf", "stl")}     # what a process gets besides the STEP
SAME = 1e-6                     # volumes and areas that differ by less than this fraction are one shape
FREECAD = ("FreeCAD 3160daf1e2b6 src/Mod/Assembly/CommandCreateBom.py and App/BomObject.cpp "
           "(Assembly_CreateBom: columns, hierarchical index, quantity, options)")


@dataclass
class Line:
    index: str
    name: str
    kind: str                   # made | bought | stock | assembly
    project: str
    part: str | None
    quantity: int = 1
    description: str = ""
    file_name: str = ""
    material: str | None = None
    process: str | None = None
    vendor: str | None = None
    pn: str | None = None
    licence: str | None = None
    source: str | None = None
    mass_g: float | None = None
    mass_source: str = ""
    shop_files: list = field(default_factory=list)
    bodies: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    depth: int = 0

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["mass_total_g"] = None if self.mass_g is None else round(self.mass_g * self.quantity, 2)
        return d

    def shop_file(self) -> str:
        """The one file a shop starts from: the DXF of a laser part, the 3MF of a printed one, else the STEP."""
        for ext in ("dxf", "3mf", "step"):
            for f in self.shop_files:
                if f.endswith("." + ext):
                    return f
        return ""


@dataclass
class Bom:
    project: str
    assembly: bool              # False: there is no assembly.py, so this is one of each part and bought part
    lines: list
    only_parts: bool = False
    detail: bool = True
    solids: dict = field(default_factory=dict, repr=False)      # body -> solid, for a caller that checks them (not in the files)
    infos: dict = field(default_factory=dict, repr=False)       # body -> BodyInfo

    def totals(self) -> dict:
        """Counts and the mass the lines know, leaving out and saying what they do not.

        A sub-assembly's bodies are counted under it only when `--flat` keeps them off the list; otherwise the
        lines under it have them.
        """
        bodies = known = without = 0
        for ln in self.lines:
            if ln.kind == "assembly":
                if self.detail:
                    continue
                masses = [self.infos[b].mass_g for b in ln.bodies]
                bodies += len(masses)
                known += sum(m for m in masses if m is not None)
                without += sum(m is None for m in masses)
            else:
                bodies += ln.quantity
                if ln.mass_g is None:
                    without += ln.quantity
                else:
                    known += ln.mass_g * ln.quantity
        return {"lines": len(self.lines), "bodies": bodies, "mass_known_g": round(known, 2),
                "bodies_without_mass": without, "mass_complete": without == 0 and bodies > 0}

    def as_dict(self) -> dict:
        return {"project": self.project, "assembly": self.assembly,
                "options": {"only_parts": self.only_parts, "detail_subassemblies": self.detail},
                "columns": list(COLUMNS), "lines": [ln.as_dict() for ln in self.lines], "totals": self.totals(),
                "source": FREECAD}


# ─── Building the lines ──────────────────────────────────────────────────────

def shop_files(kind: str, part: str | None, process: str | None, project: str, slug: str) -> list:
    """The files `cad shop` writes for a made part of this project: its STEP and what its process adds."""
    if kind != "made" or part is None or project != slug:
        return []
    return [f"{part}.{ext}" for ext in ("step",) + PROCESS_FILES.get(process or "", ())]


def stem(name: str) -> str:
    """A body's name without the words that only say which of several it is: rail_left is a rail."""
    from .bodies import POSITION
    words = name.split("/")[-1].split("_")
    while len(words) > 1 and (words[-1] in POSITION or words[-1].isdigit()):
        words.pop()
    return "_".join(words)


def shape_of(solid) -> tuple:
    """(volume, area, faces): what two copies of one solid share however they are placed or mirrored."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    wrapped = solid.wrapped if hasattr(solid, "wrapped") else solid
    v, s = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(wrapped, v)
    BRepGProp.SurfaceProperties_s(wrapped, s)
    return abs(v.Mass()), abs(s.Mass()), len(solid.faces())


def same_shape(a: tuple, b: tuple) -> bool:
    return a[2] == b[2] and all(abs(x - y) <= SAME * max(x, y) for x, y in zip(a[:2], b[:2]))


@dataclass
class _Group:
    names: list
    ref: str                    # the body whose BodyInfo speaks for the others: the first made or bought one
    shape: tuple
    first: int                  # where in assembly.py's order the first member stands


def groups_of(names: list, infos: dict, shapes: dict, order: dict) -> tuple:
    """(the groups of bodies that are one thing, the stock bodies that joined a made or bought group)."""
    groups: list[_Group] = []
    joined: set = set()

    def find(pred):
        return next((g for g in groups if pred(g)), None)

    for n in names:                                       # made and bought first: a stock body may join one of them
        i = infos[n]
        if i.kind == "stock":
            continue
        g = find(lambda g: (infos[g.ref].kind, infos[g.ref].project, infos[g.ref].part) == (i.kind, i.project, i.part)
                 and same_shape(g.shape, shapes[n]))
        if g:
            g.names.append(n)
        else:
            groups.append(_Group([n], n, shapes[n], order[n]))
    for n in names:
        i = infos[n]
        if i.kind != "stock":
            continue
        s = stem(n)
        g = find(lambda g: infos[g.ref].kind != "stock" and stem(g.names[0]) == s and same_shape(g.shape, shapes[n]))
        if g:
            g.names.append(n)
            g.first = min(g.first, order[n])
            joined.add(n)
            continue
        g = find(lambda g: infos[g.ref].kind == "stock" and stem(g.names[0]) == s and same_shape(g.shape, shapes[n]))
        if g:
            g.names.append(n)
        else:
            groups.append(_Group([n], n, shapes[n], order[n]))
    groups.sort(key=lambda g: g.first)
    for g in groups:
        g.names.sort(key=lambda n: order[n])
    return groups, joined


def _why_no_mass(info) -> str:
    if info.notes:
        return "; ".join(info.notes)
    if info.kind == "bought":
        return f"bought part {info.part!r} declares no mass_g with a mass_source"
    if info.kind == "made":
        return "its material has no density in materials.py" if info.material else f"parts/{info.part}.py declares no MATERIAL"
    return "assembly.py builds it itself: it has no material and declares no mass"


def _describe(slug: str, infos: dict, ref: str, module_doc: dict) -> dict:
    """The columns that come from one body's BodyInfo and the files behind it."""
    i = infos[ref]
    out = {"material": i.material, "process": i.process, "vendor": i.vendor, "pn": i.pn, "source": i.source,
           "licence": None, "description": "", "file_name": "assembly.py"}
    if i.kind == "made":
        out["file_name"] = f"parts/{i.part}.py"
        out["description"] = module_doc.get((i.project, i.part), "")
    elif i.kind == "bought":
        from .bought import bought_spec
        try:
            spec = bought_spec(i.project, i.part)
            out["file_name"], out["licence"] = f"bought/{spec.file}", spec.licence
        except FileNotFoundError:
            out["file_name"] = f"bought/{i.part}"
    if i.mass_g is not None:
        out["mass_g"], out["mass_source"] = round(i.mass_g, 2), i.mass_source or ""
    else:
        out["mass_g"], out["mass_source"] = None, "unknown: " + _why_no_mass(i)
    return out


def build(slug: str, machine=None, only_parts: bool = False, detail: bool = True) -> Bom:
    """The BOM of a project. `machine` is a bodies.Assembly the caller has loaded; else it is loaded here.

    The caller opens `state.reusing_builds()` around it, as every command that builds more than once does.
    """
    from .bodies import describe
    if machine is None:
        machine = st.load_machine(slug)
    if machine is None:
        return _without_assembly(slug, only_parts)
    infos = dict(machine.bodies) or describe(slug, machine.parts)
    return _bom(slug, True, dict(machine.parts), infos, only_parts, detail)


def from_parts(slug: str, parts: dict, infos: dict, only_parts: bool = False, detail: bool = True) -> Bom:
    """The BOM of bodies a caller already has (the positioned solids of a run, and their BodyInfo)."""
    return _bom(slug, True, dict(parts), dict(infos), only_parts, detail)


def _bom(slug: str, assembly: bool, solids: dict, infos: dict, only_parts: bool, detail: bool) -> Bom:
    shapes = {n: shape_of(s) for n, s in solids.items()}
    order = {n: k for k, n in enumerate(solids)}
    docs = {(i.project, i.part): None for i in infos.values() if i.kind == "made"}
    for project, part in docs:
        docs[(project, part)] = _doc(project, part)
    lines: list[Line] = []
    _level(slug, [(n, n) for n in solids], infos, shapes, order, docs, "", 0, lines, only_parts, detail)
    return Bom(slug, assembly, lines, only_parts, detail, solids, infos)


def _doc(project: str, part: str) -> str:
    """The first line of a part module's docstring: FreeCAD's BOM has a Description column to fill by hand, and a
    part's own one-line summary is what a shop wants there."""
    try:
        meta = st.built_meta(project, part) or st.build_part(project, part)[1]
        return meta["doc"]
    except Exception:           # noqa: BLE001 - a description is not worth a failed BOM
        return ""


def _level(slug, bodies, infos, shapes, order, docs, index, depth, lines, only_parts, detail) -> None:
    """The lines for one level of the assembly, and under each sub-assembly its own.

    `bodies` is [(name at this level, full name)]; the dicts are keyed by the full name. A name with a "/" in it
    belongs to the sub-assembly before the first one.
    """
    direct = [full for rel, full in bodies if "/" not in rel]
    nested: dict = {}
    for rel, full in bodies:
        if "/" in rel:
            head, rest = rel.split("/", 1)
            nested.setdefault(head, []).append((rest, full))
    if only_parts:
        direct = [n for n in direct if infos[n].kind == "made"]
    groups, joined = groups_of(direct, infos, shapes, order)
    entries = [(g.first, g, None, None) for g in groups]
    entries += [(min(order[full] for _, full in members), None, head, members) for head, members in nested.items()]
    entries.sort(key=lambda e: e[0])
    prefix = (index + ".") if index else ""
    for k, (_, group, head, members) in enumerate(entries, 1):
        idx = f"{prefix}{k}"
        if group is not None:
            lines.append(_line(slug, idx, group, infos, docs, depth, joined))
            continue
        fulls = [full for _, full in members]
        project = infos[fulls[0]].project
        sub = Line(idx, head, "assembly", project, None, depth=depth, bodies=fulls, file_name=f"{project}/assembly.py",
                   source=f"sub-assembly of the project {project}")
        known = [infos[f].mass_g for f in fulls]
        if all(m is not None for m in known):
            sub.mass_g, sub.mass_source = round(sum(known), 2), "sum of the masses of its bodies"
        else:
            sub.mass_source = f"unknown: {sum(m is None for m in known)} of its {len(fulls)} bodies have no mass"
        lines.append(sub)
        if detail:
            _level(slug, members, infos, shapes, order, docs, idx, depth + 1, lines, only_parts, detail)


def _line(slug, idx, g: _Group, infos, docs, depth, joined) -> Line:
    ref = infos[g.ref]
    d = _describe(slug, infos, g.ref, docs)
    name = ref.part if ref.kind != "stock" else (stem(g.names[0]) if len(g.names) > 1 else g.names[0].split("/")[-1])
    notes = []
    stray = [n for n in g.names if n in joined]
    if stray:
        notes.append(f"{', '.join(stray)} is stock in assembly.py (mirror() drops what a body is) and has the shape and "
                     f"the name of {g.ref}, so it is counted with it")
    return Line(index=idx, name=name, kind=ref.kind, project=ref.project, part=ref.part, quantity=len(g.names),
                description=d["description"], file_name=d["file_name"], material=d["material"], process=d["process"],
                vendor=d["vendor"], pn=d["pn"], licence=d["licence"], source=d["source"], mass_g=d["mass_g"],
                mass_source=d["mass_source"], shop_files=shop_files(ref.kind, ref.part, ref.process, ref.project, slug),
                bodies=list(g.names), notes=notes, depth=depth)


def _without_assembly(slug: str, only_parts: bool) -> Bom:
    """No assembly.py: one line for each part module and bought part, the 'whole document' of FreeCAD's BOM."""
    from .bodies import bought_stems, describe
    solids = {name: st.build_part(slug, name)[0] for name in st.part_names(slug)}
    if not only_parts:
        for name in sorted(bought_stems(st.project_dir(slug))):
            solids[name] = st.bought_solid(slug, name)
    return _bom(slug, False, solids, describe(slug, solids), only_parts, True)


# ─── Files and text ──────────────────────────────────────────────────────────

def mass_cell(ln: Line) -> str:
    return "unknown" if ln.mass_g is None else f"{ln.mass_g:.2f}"


def csv_text(bom: Bom, stamp: str | None = None) -> str:
    """The BOM as CSV: a header row and a row for each line; with a stamp, a Status column carries it on every row."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS + (("Status",) if stamp else ()))
    for ln in bom.lines:
        w.writerow([ln.index, ln.name, ln.description, ln.file_name, ln.quantity, ln.kind, ln.material or "",
                    ln.process or "", ln.vendor or "", ln.pn or "", ln.licence or "", ln.source or "", mass_cell(ln),
                    ln.mass_source, ln.shop_file(), ", ".join(ln.bodies), "; ".join(ln.notes)] + ([stamp] if stamp else []))
    return buf.getvalue()


def json_text(bom: Bom, stamp: str | None = None) -> str:
    d = bom.as_dict()
    if stamp:
        d["verified"], d["stamp"] = False, stamp
    return json.dumps(d, indent=1, sort_keys=False) + "\n"


def table_text(bom: Bom) -> str:
    """The BOM for a terminal."""
    t = bom.totals()
    head = (f"{bom.project}  bill of materials: {t['lines']} lines, {t['bodies']} bodies"
            + ("" if bom.assembly else " (no assembly.py: one of each part and bought part)"))
    rows = []
    for ln in bom.lines:
        rows.append(("  " * ln.depth + ln.index, ln.name, f"x{ln.quantity}", ln.kind, ln.material or "-", ln.process or "-",
                     mass_cell(ln) if ln.mass_g is None else f"{ln.mass_g:.2f} g", ln.shop_file() or "-"))
    widths = [max(len(r[c]) for r in rows) for c in range(8)] if rows else []
    out = [head]
    for r in rows:
        out.append("  " + "  ".join(r[c].ljust(widths[c]) for c in range(8)).rstrip())
    out.append(f"  mass: {t['mass_known_g']:.2f} g known"
               + ("" if t["mass_complete"] else f"; {t['bodies_without_mass']} of {t['bodies']} bodies have no known mass, "
                  "so this is not the weight of the machine"))
    return "\n".join(out)


# ─── Rows (what a spec and `cad shop` hold the BOM to) ───────────────────────

def module_rows(slug: str, bom: Bom, solids: dict, rule: str = "shop file") -> list:
    """One row for each made body: whether the file `cad shop` writes for it is that body.

    The file is made from the part module. A body assembly.py cuts, or builds with other parameters, is not that
    solid, and the shop would make something else than the machine holds. Volumes are compared (a placement,
    a turn or a mirror does not change one); the row is a FAIL where they differ and UNCHECKED where the module
    cannot be built here.
    """
    from .geom import volume
    rows = []
    built: dict = {}
    for ln in bom.lines:
        if ln.kind != "made" or ln.project != slug or not ln.shop_files:
            continue
        for body in ln.bodies:
            try:
                if ln.part not in built:
                    built[ln.part] = volume(st.build_part(slug, ln.part)[0])
                body_v, module_v = volume(solids[body]), built[ln.part]
            except Exception as e:      # noqa: BLE001 - say so, never pass what could not be measured
                rows.append(Row(subject=body, rule=rule, state="UNCHECKED",
                                measured=f"parts/{ln.part}.py or the body could not be measured: {type(e).__name__}: {e}",
                                limit="the body is what the part module builds", source="volume of the body against the module's"))
                continue
            same = abs(body_v - module_v) <= SAME * max(body_v, module_v)
            rows.append(Row(subject=body, rule=rule, state="PASS" if same else "FAIL",
                            measured=(f"{body_v:.2f} mm^3, what parts/{ln.part}.py builds, so {ln.shop_files[0]} is this body" if same else
                                      f"{body_v:.2f} mm^3 in assembly.py but parts/{ln.part}.py builds {module_v:.2f}: the shop file would "
                                      "not be this body (assembly.py cuts it, or builds it with other parameters)"),
                            limit="the volume of the part module's solid, to one part in a million",
                            source="geom.volume of the placed body and of build_part's solid"))
    return rows


# ─── The command ─────────────────────────────────────────────────────────────

def add_bom_arguments(p) -> None:
    p.add_argument("slug")
    p.add_argument("--only-parts", action="store_true",
                   help="only the parts made here and sub-assemblies, not what is bought or stock (FreeCAD's 'Only parts')")
    p.add_argument("--flat", action="store_true",
                   help="a sub-assembly is one line; its parts are not listed under it (FreeCAD's detailSubAssemblies off)")
    p.add_argument("--no-cache", action="store_true",
                   help="build every part from source, not from the project's build cache")


ARGUMENTS = {"bom": add_bom_arguments}


def write_bom(out_dir, bom: Bom, stamp: str | None = None) -> list:
    """bom.csv and bom.json into a folder; returns their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in (("bom.csv", csv_text(bom, stamp)), ("bom.json", json_text(bom, stamp))):
        (out_dir / name).write_bytes(text.encode("utf-8"))
        paths.append(str(out_dir / name))
    return paths


def cmd_bom(a) -> Result:
    """`cad bom <slug>`: the bill of materials, written to out/bom.csv and out/bom.json."""
    pdir = cmdbase.project(a.slug)
    try:
        with cmdbase.builds(a) as log:
            bom = build(a.slug, only_parts=a.only_parts, detail=not a.flat)
    except UsageError:
        raise
    except Exception as e:
        raise cmdbase.BuildFailed(f"{a.slug} did not build: {st.why(e)}") from e
    files = write_bom(pdir / "out", bom)
    data = bom.as_dict()
    data["files"] = files
    data["builds"] = log
    text = table_text(bom) + "".join(f"\n  {x}" for x in [cmdbase.from_cache(log)] if x) + "\n  wrote " + ", ".join(files)
    t = bom.totals()
    return Result(OK, data, text, f"{t['lines']} lines, {t['bodies']} bodies", files)
