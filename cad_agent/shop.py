"""`cad shop`: what goes to the shop for a design that is done, in out/shop/, and the proof of it.

    cad shop <slug>            write out/shop/ for the design `cad done` holds
    cad shop <slug> --draft    write it anyway, stamped NOT VERIFIED on everything
    cad shop <slug> --check    write nothing: regenerate it and compare with what is on disk

What is written, for the parts of the BOM that this project makes (bom.py):

    <part>.step                  every part
    <part>.dxf                   a laser_cut part: the outline, as FreeCAD writes one (dxf.py)
    <part>.3mf, <part>.stl       an fdm part: the same mesh in the two formats a slicer reads (threemf.py)
    drawings/...                 what piece E's `cad_agent.drawing.shop_drawings` returns (the hook, below)
    bom.csv, bom.json            the bill of materials, with the shop file of every line (bom.py)
    manifest.json                every file's sha256 and size, the commit, the verdict, the rows

A part that a project has but assembly.py does not use is left out, and the manifest says so. A project with no
assembly.py makes one of each part module.

How it is fenced
----------------
A file that goes to a shop is one a person may cut or print without looking, so:

  - it exits 2 unless `cad done` holds, which means the last `cad verify` passed in a fresh process, on exactly
    these files and these rules, and on committed work. A shop file is made for the commit that was verified;
    the manifest records that commit and the one now at HEAD
  - the parts are built from source, never from the build cache (verify does not trust it either)
  - the rules of a made part run on what is about to be written, and a row that is not PASS or N/A stops it:
    a laser part must be a through-cut and its DXF must read back to the mid-plane section, a printed part's 3MF
    must read back watertight with the solid's volume (dxf.py and threemf.py), and a body that assembly.py
    changes is not the part module the file is made from (bom.module_rows). FAIL exits 1, UNCHECKED exits 2,
    and in both nothing is written, so a folder left from an earlier run is never half replaced
  - `--draft` is for looking at what a design would send before it is done. It writes whatever there is, with
    the stamp inside each file where the format has room (the DXF's comment and a text on layer NOT_VERIFIED,
    the 3MF's title and description, the STL's header, the STEP's description, a Status column in bom.csv, the
    manifest's `draft: true` and `verdict: NOT VERIFIED`), and exits as the rows say: 1 if one fails, 2 if one
    is unchecked or the design is not done, 0 only if the design is done and every row passes

The bytes
---------
Every file is the same bytes whenever it is made, and the DXF, 3MF, STL and bom files on either kernel
(export.py says how). A STEP names the kernel that wrote it in one header line and is otherwise the same on both,
so `--check` compares a STEP without that line and says nothing of a folder written by the other kernel. The
manifest holds nothing that changes with the run: no time, no machine, no kernel version, only the verify
record's own time. So `--check` is exact.

`--check`
---------
Regenerates what a normal run would write, in memory, and compares it with out/shop/ file by file, by sha256:

    missing     the manifest lists it and it is not there
    edited      it is there and its bytes are not the ones the manifest recorded (someone changed it)
    stale       it is as the manifest recorded, but the design now makes other bytes
    new         the design now makes a file the manifest does not list
    gone        the manifest lists a file the design no longer makes
    extra       a file in out/shop/ that no manifest lists (not touched by `cad shop`, which only replaces its own)

Exit 0 when there are none, 1 when there are any, or when a fresh run's rows would fail; 2 when it cannot say: no
out/shop/ yet, the folder is a draft, the design is not done, or a row is unchecked. 3 for a bad argument.

The hook for drawings (piece E)
-------------------------------
`cad_agent.drawing.shop_drawings(slug, parts, processes, stamp) -> {"files": {path: bytes}, "skipped": {part: why}}`
is called if it exists, once, with the solids of every part the run makes (`parts`: name -> solid, built from
source), their PROCESS (`processes`: name -> "cnc", "laser_cut", ..., or None) and the stamp ("NOT VERIFIED" or
None). It returns the bytes of each drawing it makes, as paths under `drawings/` (`drawings/plate.dxf`,
`drawings/plate.pdf`), the same bytes for the same part, and a reason for each part it does not draw. Anything
else it returns, a path outside `drawings/`, or an exception is an UNCHECKED row, and a missing optional library
(matplotlib: pip install "cad-agent[drawings]") is said as such. Until the module has the function the manifest
says `drawings: {"built": false, "why": ...}`.

Exit codes: 0 written (or checked, and clean), 1 a row failed or a file differs, 2 not done or something could not
be settled, 3 usage (an unknown project, `--draft` with `--check`, a library the laser rows need missing), 4 crash.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import bom as bomlib
from . import cmdbase
from . import state as st
from .cmdbase import FAIL, OK, UNCHECKED, Result, UsageError
from .registry import Row

STAMP = "NOT VERIFIED"
OUT = "shop"                    # out/shop/
MANIFEST = "manifest.json"
DRAWINGS = "cad_agent.drawing:shop_drawings"
EXTRAS = {"matplotlib": "drawings", "bd_warehouse": "fasteners"}      # the optional libraries of pyproject.toml


@dataclass
class Plan:
    """Everything a run would write, made and judged but not yet written."""
    slug: str
    stamp: str | None
    bom: bomlib.Bom
    files: dict                 # path under out/shop/ -> bytes
    meta: dict                  # path -> (part or None, format)
    rows: list
    drawings: dict
    skipped: list
    missing: list = field(default_factory=list)      # files a part should have had and the rows say could not be made


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shop_spec(slug: str) -> dict | None:
    """The `[shop]` table of the project's spec.toml, or None: no spec, one that does not parse (the `spec` rule
    says so), or one without the table, which means the project has not opted in to the shop's rules."""
    import tomllib
    try:
        spec = tomllib.loads((st.project_dir(slug) / "spec.toml").read_text())
    except (OSError, ValueError):
        return None
    table = spec.get("shop")
    return table if isinstance(table, dict) else None


# ─── Making the files ────────────────────────────────────────────────────────

def prepare(slug: str, stamp: str | None) -> Plan:
    """Build the project from source and make every file, with the rows that judge them. Nothing is written."""
    from . import dxf, export, threemf
    with st.reusing_builds(), st.caching_builds(False):
        machine = st.load_machine(slug)
        bill = bomlib.build(slug, machine)
        made: dict = {}
        for ln in bill.lines:
            if ln.kind == "made" and ln.project == slug and ln.part:
                made.setdefault(ln.part, ln.process)
        files, meta, rows, missing = {}, {}, [], []

        def add(path: str, data: bytes | None, part, fmt: str) -> None:
            if data is None:
                missing.append(path)
                return
            files[path], meta[path] = data, (part, fmt)

        if any(p == "laser_cut" for p in made.values()):
            dxf.ezdxf_module()                      # a clear error before any work, not a row for every part
        solids = {}
        for part in sorted(made):
            solid, _ = st.build_part(slug, part)
            solids[part] = solid
            add(f"{part}.step", export.render(solid, part, "step", stamp), part, "step")
            if made[part] == "laser_cut":
                laser = dxf.laser_rows(part, solid, stamp)
                rows += laser.rows
                add(f"{part}.dxf", laser.dxf, part, "dxf")
            elif made[part] == "fdm":
                printed = threemf.print_rows(part, solid, stamp)
                rows += printed.rows
                add(f"{part}.3mf", printed.three_mf, part, "3mf")
                add(f"{part}.stl", printed.stl, part, "stl")
        for r in rows:
            r.check = "shop"
        body_rows = bomlib.module_rows(slug, bill, bill.solids)
        for r in body_rows:
            r.check = "shop"
        rows += body_rows
        drawings, drawing_rows = _drawings(slug, solids, made, stamp)
        rows += drawing_rows
        for path, data in drawings["files"].items():
            add(path, data, None, "drawing")
        add("bom.csv", bomlib.csv_text(bill, stamp).encode("utf-8"), None, "csv")
        add("bom.json", bomlib.json_text(bill, stamp).encode("utf-8"), None, "json")
        skipped = [{"part": p, "why": "assembly.py does not use it"} for p in st.part_names(slug) if p not in made] \
            if machine is not None else []
    return Plan(slug, stamp, bill, files, meta, rows, {**drawings, "files": sorted(drawings["files"])}, skipped, missing)


def _drawings(slug: str, solids: dict, processes: dict, stamp: str | None) -> tuple:
    """Piece E's hook (the module docstring has its contract): ({built, files, skipped, why}, [rows])."""
    nothing = {"built": False, "files": {}, "skipped": {}}

    def row(state: str, measured: str) -> Row:
        return Row(subject="drawings", rule="drawings", state=state, measured=measured, check="shop",
                   limit="the files cad_agent.drawing.shop_drawings returns, under drawings/",
                   source="the hook in cad_agent/shop.py")

    try:
        fn = cmdbase.resolve(DRAWINGS)
    except ImportError as e:        # the module is there and one of its libraries is not
        return {**nothing, "why": f"cad_agent.drawing needs {e.name}"}, [row("UNCHECKED", _needs(e))]
    if fn is None:
        return {**nothing, "why": "cad_agent.drawing does not provide shop_drawings: drawings are not built yet"}, []
    try:
        got = fn(slug, dict(solids), dict(processes), stamp)
        files = {str(k): bytes(v) for k, v in dict(got.get("files", {})).items()}
        skipped = {str(k): str(v) for k, v in dict(got.get("skipped", {})).items()}
        outside = sorted(p for p in files if not p.startswith("drawings/") or ".." in Path(p).parts)
        if outside:
            raise ValueError(f"a drawing is at {outside[0]!r}, which is not under drawings/")
    except ImportError as e:
        return {**nothing, "why": f"cad_agent.drawing needs {e.name}"}, [row("UNCHECKED", _needs(e))]
    except Exception as e:          # noqa: BLE001 - a drawing that cannot be made is not a pass
        return {**nothing, "why": f"{type(e).__name__}: {e}"}, [row("UNCHECKED", f"the drawings could not be made: "
                                                                    f"{type(e).__name__}: {e}")]
    return {"built": True, "files": files, "skipped": skipped}, [
        row("PASS", f"{len(files)} files for {len({Path(p).stem for p in files})} parts"
                    + (f"; not drawn: {'; '.join(f'{k} ({v})' for k, v in sorted(skipped.items()))}" if skipped else ""))]


def _needs(e: ImportError) -> str:
    extra = EXTRAS.get(e.name or "")
    return (f"the drawings need {e.name}, which is not installed: pip install \"cad-agent[{extra}]\"" if extra
            else f"the drawings need {e.name or 'a library'}, which is not installed: {e}")


# ─── The manifest and the folder ─────────────────────────────────────────────

def manifest_of(plan: Plan, status: dict, git: dict | None) -> dict:
    """manifest.json: nothing in it is the time of the run, the machine or the kernel (see the module docstring)."""
    draft = plan.stamp is not None
    t = plan.bom.totals()
    return {
        "project": plan.slug,
        "verdict": STAMP if draft else "PASS",
        "draft": draft,
        "commit": (git or {}).get("commit"),
        "tree": (git or {}).get("tree"),
        "dirty": bool((git or {}).get("dirty")),
        "done": bool(status["done"]),
        "reasons": list(status["reasons"]),
        "verified": {"verdict": status.get("verdict"), "at": status.get("verified_utc"), "commit": status.get("commit")},
        "files": [{"path": p, "part": plan.meta[p][0], "format": plan.meta[p][1], "sha256": sha256(plan.files[p]),
                   "bytes": len(plan.files[p])} for p in sorted(plan.files)],
        "missing": sorted(plan.missing),
        "bom": {"lines": t["lines"], "bodies": t["bodies"], "mass_known_g": t["mass_known_g"],
                "mass_complete": t["mass_complete"]},
        "rows": [{"rule": r.rule, "subject": r.subject, "state": r.state} for r in plan.rows],
        "drawings": plan.drawings,
        "skipped": plan.skipped,
    }


def read_manifest(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / MANIFEST).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("files"), list) else None


def write_folder(folder: Path, plan: Plan, manifest: dict) -> list:
    """Replace what the previous run wrote with this run's files, the manifest last; other files are left alone."""
    previous = read_manifest(folder)
    old = {f["path"] for f in previous["files"]} if previous else set()
    written = []
    folder.mkdir(parents=True, exist_ok=True)
    for path, data in sorted(plan.files.items()):
        _write(folder / path, data)
        written.append(str(folder / path))
    _write(folder / MANIFEST, (json.dumps(manifest, indent=1) + "\n").encode("utf-8"))
    written.append(str(folder / MANIFEST))
    for path in sorted(old - set(plan.files)):
        try:
            (folder / path).unlink()
        except OSError:
            pass
    for d in sorted({(folder / p).parent for p in old}, key=lambda x: -len(x.parts)):
        if d != folder:
            try:
                d.rmdir()               # a folder a drawing used and no longer does, if nothing else is in it
            except OSError:
                pass
    return written


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def differences(folder: Path, plan: Plan, previous: dict) -> list:
    """What differs between a fresh run and the folder (the module docstring lists the kinds)."""
    from .export import kernel_free
    recorded = {f["path"]: f["sha256"] for f in previous["files"]}
    out = []
    for path in sorted(plan.files):
        want = sha256(plan.files[path])
        target = folder / path
        if path not in recorded:
            out.append({"path": path, "why": "new", "detail": "the design now makes a file the manifest does not list"})
        elif not target.is_file():
            out.append({"path": path, "why": "missing", "detail": "the manifest lists it and it is not there"})
        else:
            on_disk = sha256(target.read_bytes())
            if on_disk != recorded[path]:
                out.append({"path": path, "why": "edited", "detail": "its bytes are not the ones the manifest recorded"})
            elif on_disk != want and not (path.endswith(".step") and kernel_free(target.read_bytes()) == kernel_free(plan.files[path])):
                out.append({"path": path, "why": "stale", "detail": "the design now makes other bytes"})
    for path in sorted(set(recorded) - set(plan.files) - set(plan.missing)):
        out.append({"path": path, "why": "gone", "detail": "the manifest lists it and the design no longer makes it"})
    listed = set(recorded) | set(plan.files) | {MANIFEST}
    for found in sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()):
        if found not in listed and not found.endswith(".tmp"):
            out.append({"path": found, "why": "extra", "detail": "in out/shop/ and in no manifest"})
    return out


# ─── The command ─────────────────────────────────────────────────────────────

def add_shop_arguments(p) -> None:
    p.add_argument("slug")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--draft", action="store_true",
                      help="write out/shop/ even though the design is not done, with NOT VERIFIED in every file")
    mode.add_argument("--check", action="store_true",
                      help="write nothing: regenerate out/shop/ and compare it with what is on disk (exit 1 if it differs)")
    p.add_argument("--all", action="store_true", help="show passing rows too")


ARGUMENTS = {"shop": add_shop_arguments}


def _rows(plan: Plan) -> list:
    return [r.as_dict() for r in plan.rows]


def _summary(plan: Plan) -> str:
    kinds = {}
    for part, fmt in plan.meta.values():
        kinds[fmt] = kinds.get(fmt, 0) + 1
    return ", ".join(f"{n} {fmt}" for fmt, n in sorted(kinds.items())) or "nothing"


def cmd_shop(a) -> Result:
    from . import verify
    from .dxf import NeedsExtra
    pdir = cmdbase.project(a.slug)
    draft, check = bool(a.draft), bool(a.check)
    if draft and check:
        raise UsageError("--draft writes files and --check writes none; use one of them")
    status = verify.status(a.slug)
    git = verify.git_info(pdir)
    folder = pdir / "out" / OUT
    head = f"{a.slug}  cad shop" + (" --draft" if draft else " --check" if check else "")
    if not status["done"] and not draft:
        lines = [f"{head}: NOT DONE, so " + ("there is nothing to certify" if check else "nothing is written")]
        lines += [f"  {r}" for r in status["reasons"]]
        lines.append(f"  run `cad verify` on committed work" + ("" if check else f", or `cad shop {a.slug} --draft` to look at it stamped {STAMP}"))
        return Result(UNCHECKED, {"project": a.slug, "done": False, "reasons": status["reasons"], "wrote": []},
                      "\n".join(lines), "not done: " + (status["reasons"][0] if status["reasons"] else ""))
    previous = None
    if check:
        previous = read_manifest(folder)
        if previous is None:
            return Result(UNCHECKED, {"project": a.slug, "done": True, "differences": [], "reasons": ["no out/shop/manifest.json"]},
                          f"{head}: nothing to check, out/shop/ has no manifest; run `cad shop {a.slug}`", "nothing to check")
        if previous.get("draft"):
            return Result(UNCHECKED, {"project": a.slug, "done": True, "differences": [], "reasons": ["out/shop/ is a draft"]},
                          f"{head}: out/shop/ is a {STAMP} draft, which nothing can certify; run `cad shop {a.slug}`",
                          "out/shop is a draft")
    try:
        plan = prepare(a.slug, STAMP if draft else None)
    except NeedsExtra as e:
        raise UsageError(str(e)) from None
    except cmdbase.UsageError:
        raise
    except Exception as e:
        raise cmdbase.BuildFailed(f"{a.slug} did not build: {st.why(e)}") from e
    rows = _rows(plan)
    code = cmdbase.verdict(r["state"] for r in rows)
    bad = [r for r in rows if r["state"] in ("FAIL", "UNCHECKED")]
    data = {"project": a.slug, "draft": draft, "check": check, "done": status["done"], "reasons": status["reasons"],
            "rows": rows if a.all else bad, "rows_total": len(rows), "drawings": plan.drawings, "skipped": plan.skipped,
            "bom": plan.bom.totals(), "missing": sorted(plan.missing), "wrote": [],
            "files": [{"path": p, "sha256": sha256(plan.files[p]), "bytes": len(plan.files[p])} for p in sorted(plan.files)]}
    lines = [f"{head}: {_summary(plan)}, from the {len(plan.bom.lines)} lines of the BOM"]
    lines += cmdbase.rows_text(rows, a.all)
    if plan.skipped:
        lines.append("  left out: " + "; ".join(f"{s['part']} ({s['why']})" for s in plan.skipped))
    if not plan.drawings["built"]:
        lines.append(f"  drawings: not built ({plan.drawings.get('why')})")

    if check:
        diff = differences(folder, plan, previous)
        data["differences"] = diff
        if diff:
            code = FAIL
            lines += [f"  {d['why']:8} {d['path']}: {d['detail']}" for d in diff]
        elif code == OK:
            lines.append(f"  out/shop/ is what a fresh run writes: {len(plan.files)} files, byte for byte")
        return Result(code, data, "\n".join(lines),
                      f"{len(diff)} differences" if diff else ("clean" if code == OK else "rows not passing"))

    if code != OK and not draft:
        lines.append("  nothing was written: " + ("a row failed" if code == FAIL else "a row could not be settled")
                     + f"; fix it, or `cad shop {a.slug} --draft` writes what there is, stamped")
        return Result(code, data, "\n".join(lines), f"{len(bad)} rows not passing, nothing written")
    manifest = manifest_of(plan, status, git)
    written = write_folder(folder, plan, manifest)
    data["wrote"], data["manifest"] = written, manifest
    if draft and code == OK and not status["done"]:
        code = UNCHECKED                    # every row passed, and the design is still not one anybody verified
    lines.append(f"  wrote {len(written)} files to {folder}" + (f"  [{STAMP}]" if draft else ""))
    return Result(code, data, "\n".join(lines), f"{'draft: ' if draft else ''}wrote {len(written)} files", written)
