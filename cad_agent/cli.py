"""cad: the command line for cad-agent.

Every MCP tool has a subcommand here that calls the same functions, so an
agent drives the whole loop from a shell, and nothing sits in its context
until it asks for `cad --help`. Output is a short report by default; `--json`
prints one JSON object on stdout instead. Errors go to stderr.

The exit code is the verdict, so `cad check slug && ...` means what it says:

    0  ok: every row PASS or N/A, or the query succeeded
    1  FAIL: a gate failed, parts interfere, or a part did not build
    2  UNCHECKED: something could not be settled, which is not a pass
    3  usage: bad arguments, or an unknown project, part or tool
    4  crash: an unexpected exception in cad-agent itself

Every command appends one line to an activity log: projects/<slug>/.cad/
log.jsonl for commands that name a project, projects/.cad/log.jsonl for the
rest. A line says what ran, how it ended, and which files it wrote. The
workbench reads it to show what the agent did and looked at.

Projects live in cad-agent/projects unless CAD_PROJECTS or --projects names
another directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import state as st

OK, FAIL, UNCHECKED, USAGE, CRASH = 0, 1, 2, 3, 4
TOOL_KINDS = ("drill", "end_mill", "collet_nose", "laser_cone", "needle")
SLUG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")

EXIT_CODES = """exit codes:
  0  ok        every row PASS or N/A, or the query succeeded
  1  FAIL      a gate failed, parts interfere, or a part did not build
  2  UNCHECKED something could not be settled (not a pass)
  3  usage     bad arguments, unknown project, part or tool
  4  crash     unexpected exception in cad-agent"""


class UsageError(Exception):
    """Bad arguments, or a project, part or tool that does not exist."""


class BuildFailed(Exception):
    """A part module raised: the design failed, not the tool."""


@dataclass
class Result:
    code: int
    data: dict
    text: str
    summary: str = ""
    files: list = field(default_factory=list)


# ─── Argument helpers ────────────────────────────────────────────────────────

def _value(text: str):
    """Read a value the way a person means it: 5 is a number, true a bool,
    [1, 2] a list, anything else a string."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def _pairs(items, what: str) -> dict:
    out = {}
    for item in items or []:
        key, sep, raw = item.partition("=")
        if not sep or not key:
            raise UsageError(f"{what} takes key=value, got {item!r}")
        out[key] = _value(raw)
    return out


def _project(slug: str) -> Path:
    try:
        return st.project_dir(slug)
    except FileNotFoundError:
        have = ", ".join(st.list_projects()) or "none"
        raise UsageError(f"no project {slug!r} (projects: {have})") from None


def _part(slug: str, name: str) -> Path:
    path = _project(slug) / "parts" / f"{name}.py"
    if not path.exists():
        have = ", ".join(st.part_names(slug)) or "none"
        raise UsageError(f"no part {name!r} in {slug} (parts: {have})")
    return path


def _overrides(a) -> dict:
    """--set values, checked against the part's PARAMS so a typo is a usage
    error naming the real parameters rather than a TypeError from build()."""
    ov = _pairs(getattr(a, "set", None), "--set")
    if not ov:
        return {}
    if not getattr(a, "part", None):
        raise UsageError("--set changes one part's PARAMS; name the part")
    path = _part(a.slug, a.part)
    try:
        known = set(getattr(st._load_module(path), "PARAMS", {}))
    except Exception as e:
        raise BuildFailed(f"{a.part} did not load: {type(e).__name__}: {e}") from e
    unknown = sorted(set(ov) - known)
    if unknown:
        raise UsageError(f"{a.part} has no parameter {', '.join(unknown)} "
                         f"(params: {', '.join(sorted(known))})")
    return ov


def _build(slug: str, name: str, overrides: dict | None = None):
    _part(slug, name)
    try:
        return st.build_part(slug, name, overrides)
    except Exception as e:
        raise BuildFailed(f"{name} did not build: {type(e).__name__}: {e}") from e


def _assembly(slug: str) -> dict:
    _project(slug)
    try:
        asm, *_ = st.load_assembly(slug)
    except Exception as e:
        raise BuildFailed(f"{slug} assembly did not build: {type(e).__name__}: {e}") from e
    if asm is None:
        raise UsageError(f"{slug} has no assembly.py")
    return asm


def _verdict(states) -> int:
    states = set(states)
    if "FAIL" in states:
        return FAIL
    if "UNCHECKED" in states:
        return UNCHECKED
    return OK


def _rows_text(rows, show_all: bool) -> list[str]:
    shown = rows if show_all else [r for r in rows if r["state"] != "PASS"]
    lines = []
    for r in shown:
        rule = f"{r['check']}/{r['rule']}" if r.get("check") else r["rule"]
        limit = r.get("limit")
        tail = f"   [limit {limit}]" if limit not in (None, "n/a") else ""
        lines.append(f"  {r['state']:9} {rule:24} {r['subject']:20} {r['measured']}{tail}")
    if len(shown) < len(rows):
        lines.append(f"  ({len(rows) - len(shown)} passing rows hidden; --all shows them)")
    return lines


# ─── Projects ────────────────────────────────────────────────────────────────

def cmd_init(a) -> Result:
    if not SLUG.fullmatch(a.slug):
        raise UsageError(f"project name {a.slug!r}: letters, digits, - and _ only")
    d = st.project_dir(a.slug, create=True)
    prof = d / "mech_profile.md"
    wrote = []
    if not prof.exists():
        prof.write_text(
            f"# {a.slug} — mechanical spec\n\n## Brief\n\n{a.brief or 'TODO'}\n\n"
            "## Assumptions\n\n1. TODO\n\n## Parts\n\n| Name | Process | Material | Role |\n"
            "|---|---|---|---|\n\n## Out of scope\n\nFabrication, assembly by hand.\n")
        wrote.append(str(prof))
    text = f"project {a.slug} at {d}" + (f"\nwrote {prof.name}" if wrote else "")
    return Result(OK, {"project": a.slug, "path": str(d), "wrote": wrote}, text,
                  "created" if wrote else "already there", wrote)


def cmd_ls(a) -> Result:
    if not a.slug:
        names = st.list_projects()
        return Result(OK, {"projects": names}, "\n".join(names) or "no projects yet",
                      f"{len(names)} projects")
    pdir = _project(a.slug)
    from .bought import list_bought
    parts = st.part_names(a.slug)
    bought = [r["name"] for r in list_bought(a.slug)]
    assembly = (pdir / "assembly.py").exists()
    text = (f"{a.slug}\n  parts     {', '.join(parts) or 'none'}\n"
            f"  bought    {', '.join(bought) or 'none'}\n"
            f"  assembly  {'yes' if assembly else 'no'}")
    return Result(OK, {"project": a.slug, "parts": parts, "bought": bought,
                       "assembly": assembly}, text,
                  f"{len(parts)} parts, {len(bought)} bought")


def cmd_status(a) -> Result:
    _project(a.slug)
    parts = st.part_names(a.slug)
    data = {"project": a.slug, "parts": parts, "last_check": None, "summary": None}
    lines = [a.slug, f"  parts  {', '.join(parts) or 'none'}"]
    try:
        c = st.read_checks(a.slug)
        s = c.get("summary", {})
        data.update(last_check=c.get("written_utc"), summary=s)
        lines.append(f"  last check  {c.get('written_utc')}  ok={s.get('ok')}  "
                     f"{s.get('by_state')}")
    except FileNotFoundError:
        lines.append("  no checks.json yet: run `cad check`")
    return Result(OK, data, "\n".join(lines), f"{len(parts)} parts")


# ─── Parts ───────────────────────────────────────────────────────────────────

def cmd_build(a) -> Result:
    _part(a.slug, a.part)          # a typo fails here, before the 30 s kernel import
    ov = _overrides(a)
    from .geom import bbox, mass_g, volume
    solid, meta = _build(a.slug, a.part, ov)
    lo, hi = bbox(solid)
    dims = [round(hi[i] - lo[i], 3) for i in range(3)]
    mass = None
    if meta["material"]:
        try:
            mass = round(mass_g(solid, meta["material"]), 2)
        except KeyError:
            pass
    data = {"project": a.slug, "part": a.part, "bbox_mm": dims,
            "volume_cm3": round(volume(solid) / 1000.0, 3), "mass_g": mass,
            "material": meta["material"], "process": meta["process"],
            "build_s": meta["build_s"], "params": meta["params"],
            "overrides": ov, "doc": meta["doc"]}
    lines = [f"{a.slug}/{a.part}  {meta['doc']}".rstrip(),
             f"  bbox      {dims[0]} x {dims[1]} x {dims[2]} mm",
             f"  volume    {data['volume_cm3']} cm^3"
             + (f" · {mass} g {meta['material']}" if mass is not None else ""),
             f"  process   {meta['process']}   built in {meta['build_s']} s"]
    if ov:
        lines.append(f"  overrides {ov}")
    return Result(OK, data, "\n".join(lines), f"{dims[0]}x{dims[1]}x{dims[2]} mm")


def cmd_render(a) -> Result:
    pdir = _project(a.slug)
    if a.part:
        _part(a.slug, a.part)
    ov = _overrides(a)
    from .render import VIEWS, draw, merge, tessellate
    if a.view not in VIEWS:
        raise UsageError(f"unknown view {a.view!r} (views: {', '.join(sorted(VIEWS))})")
    if a.part:
        solid, _ = _build(a.slug, a.part, ov)
        mesh = tessellate(solid, a.tolerance, 0.2)
        subject = a.part
    else:
        if a.set:
            raise UsageError("--set changes one part's PARAMS; name the part")
        asm = _assembly(a.slug)
        mesh = merge([tessellate(s, a.tolerance, 0.2) for _, s in sorted(asm.items())])
        subject = "assembly"
    out = pdir / "out" / f"{subject}_{a.view}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    png = str(draw(mesh, out, view=a.view))
    return Result(OK, {"project": a.slug, "subject": subject, "view": a.view,
                       "png": png}, png, f"{subject} {a.view}", [png])


def cmd_export(a) -> Result:
    _part(a.slug, a.part)
    from .export import export_part
    try:
        path = str(export_part(a.slug, a.part, a.format))
    except ValueError as e:
        raise UsageError(str(e)) from e
    return Result(OK, {"project": a.slug, "part": a.part, "format": a.format,
                       "path": path}, path, f"{a.part} as {a.format}", [path])


# ─── Measurement and reference ───────────────────────────────────────────────

def cmd_measure(a) -> Result:
    _project(a.slug)
    if not a.posed:
        _part(a.slug, a.a)
        _part(a.slug, a.b)
    from .geom import intersection_volume, min_distance
    if a.posed:
        asm = _assembly(a.slug)
        missing = [n for n in (a.a, a.b) if n not in asm]
        if missing:
            raise UsageError(f"not in {a.slug}'s assembly: {', '.join(missing)} "
                             f"(bodies: {', '.join(sorted(asm))})")
        sa, sb = asm[a.a], asm[a.b]
    else:
        sa, _ = _build(a.slug, a.a)
        sb, _ = _build(a.slug, a.b)
    where = "as placed in the assembly" if a.posed else "each at its own origin"
    overlap = intersection_volume(sa, sb)
    data = {"project": a.slug, "a": a.a, "b": a.b, "posed": a.posed}
    if overlap > 1e-6:
        data.update(interferes=True, overlap_mm3=round(overlap, 4), min_distance_mm=0.0)
        return Result(FAIL, data,
                      f"{a.a} vs {a.b} ({where}): INTERFERENCE, overlap {overlap:.4f} mm^3",
                      f"interfere {overlap:.3f} mm^3")
    gap = min_distance(sa, sb)
    data.update(interferes=False, overlap_mm3=0.0, min_distance_mm=round(gap, 4))
    return Result(OK, data, f"{a.a} vs {a.b} ({where}): clear, minimum distance {gap:.4f} mm",
                  f"clear {gap:.3f} mm")


TABLE_ALIASES = {"holes": "clearance_hole_mm", "taps": "tap_drill_mm",
                 "inserts": "heatset_bore_mm", "extrusions": "extrusion",
                 "density": "density_g_cm3", "views": "views"}


def cmd_tables(a) -> Result:
    from .geom import DENSITY
    from .parts import CLEARANCE_HOLE, EXTRUSION, HEATSET_BORE, TAP_DRILL
    from .render import VIEWS, backend_status
    tables = {"clearance_hole_mm": CLEARANCE_HOLE, "tap_drill_mm": TAP_DRILL,
              "heatset_bore_mm": HEATSET_BORE, "extrusion": EXTRUSION,
              "density_g_cm3": DENSITY, "views": sorted(VIEWS),
              "render_backend": backend_status()}
    if a.section:
        key = TABLE_ALIASES.get(a.section, a.section)
        if key not in tables:
            raise UsageError(f"unknown table {a.section!r} "
                             f"(tables: {', '.join(TABLE_ALIASES)})")
        tables = {key: tables[key]}
    return Result(OK, tables, json.dumps(tables, indent=1, default=str),
                  a.section or "all tables")


def cmd_tool(a) -> Result:
    from . import tooling
    from .geom import bbox
    params = _pairs(a.params, "tool")
    try:
        solid = getattr(tooling, a.kind)(**params)
    except TypeError as e:
        raise UsageError(f"{a.kind}: {e}") from e
    lo, hi = bbox(solid)
    data = {"kind": a.kind, "params": params,
            "bbox_mm": [round(hi[i] - lo[i], 2) for i in range(3)],
            "z_mm": [round(lo[2], 2), round(hi[2], 2)]}
    lines = [f"{a.kind} {params}",
             f"  bbox  {data['bbox_mm'][0]} x {data['bbox_mm'][1]} x {data['bbox_mm'][2]} mm",
             f"  z     {data['z_mm'][0]} .. {data['z_mm'][1]} (tip at z = 0)"]
    if a.kind == "laser_cone":
        tilt = tooling.tilt_at_corner(params["focal_length"], params["field"])
        data["corner_tilt_deg"] = round(tilt, 2)
        lines.append(f"  beam tilt at a field corner {tilt:.2f} deg: what shadows a fixture wall")
    return Result(OK, data, "\n".join(lines), a.kind)


# ─── Gates ───────────────────────────────────────────────────────────────────

def cmd_check(a) -> Result:
    pdir = _project(a.slug)
    if a.part:
        _part(a.slug, a.part)
        ov = _overrides(a)
        from .runner import part_check
        try:
            r = part_check(a.slug, a.part, ov)
        except Exception as e:
            raise BuildFailed(f"{a.part} did not build: {type(e).__name__}: {e}") from e
        code = _verdict(x["state"] for x in r["rows"])
        d = r["bbox_mm"]
        lines = [f"{a.slug}/{a.part}  {'OK' if code == OK else ('FAIL' if code == FAIL else 'UNCHECKED')}",
                 f"  bbox {d[0]} x {d[1]} x {d[2]} mm · {r['volume_cm3']} cm^3 · {r['build_s']} s"]
        if ov:
            lines.append(f"  overrides {ov}")
        lines += _rows_text(r["rows"], a.all)
        lines.append(f"  ({r['scope']})")
        files = [str(pdir / r["render"])] if r.get("render") else []
        return Result(code, {"project": a.slug, **r}, "\n".join(lines),
                      f"{a.part}: {len(r['failing'])} not passing", files)
    if a.set:
        raise UsageError("--set changes one part's PARAMS; add --part")
    from .runner import check_all
    views = tuple(v.strip() for v in a.views.split(",") if v.strip()) or ("iso",)
    p = check_all(a.slug, render_views=views)
    s = p["summary"]
    code = FAIL if s.get("parts_failed") else _verdict(r["state"] for r in p["rows"])
    shown = p["rows"] if a.all else [r for r in p["rows"] if r["state"] != "PASS"]
    lines = [f"{a.slug}  {'OK' if code == OK else ('FAIL' if code == FAIL else 'UNCHECKED')}  "
             f"{s.get('parts_built')} parts built, {s.get('parts_failed')} failed · {s.get('by_state')}"]
    lines += _rows_text(p["rows"], a.all)
    files = [str(pdir / "checks.json")] + [str(pdir / r["path"]) for r in p["renders"]]
    data = {"project": a.slug, "summary": s, "rows": shown,
            "rows_total": len(p["rows"]), "parts": p["parts"]}
    return Result(code, data, "\n".join(lines),
                  f"{sum(1 for r in p['rows'] if r['state'] != 'PASS')} of {len(p['rows'])} rows not passing",
                  files)


def cmd_rules(a) -> Result:
    from . import runner  # noqa: F401  (importing the runner registers every rule)
    from .registry import checks
    rows = [{"name": c.name, "scope": c.scope, "order": c.order, "does": c.doc}
            for c in checks()]
    lines = [f"{r['scope']:9} {r['name']:14} {(r['does'] or '').strip().splitlines()[0] if r['does'] else ''}"
             for r in rows]
    return Result(OK, {"rules": rows}, "\n".join(lines), f"{len(rows)} rules")


def cmd_approve(a) -> Result:
    from .runner import approve_views
    pdir = _project(a.slug)
    if a.part:
        _part(a.slug, a.part)
    done = approve_views(a.slug, a.part, a.view)
    print("approved renders become the baseline the visual gate compares against; "
          "look at the diff first", file=sys.stderr)
    return Result(OK, {"project": a.slug, "approved": done},
                  "approved:\n" + "\n".join(f"  {d}" for d in done),
                  f"approved {len(done)}", [str(pdir / d) for d in done])


def cmd_done(a) -> Result:
    from .runner import done_check
    _project(a.slug)
    try:
        d = done_check(a.slug)
    except FileNotFoundError:
        msg = "no checks.json yet: run `cad check` first"
        return Result(UNCHECKED, {"ok": False, "failures": [msg]}, msg, "never checked")
    if d["ok"]:
        code = OK
    elif (d.get("by_state") or {}).get("FAIL") or any(
            "did not build" in f or f.startswith("no parts") for f in d["failures"]):
        code = FAIL
    else:
        code = UNCHECKED
    lines = [f"{a.slug}  {'DONE' if d['ok'] else 'NOT DONE'}  (checked {d.get('checked_utc')})"]
    lines += [f"  {f}" for f in d["failures"]]
    return Result(code, {"project": a.slug, **d}, "\n".join(lines),
                  "done" if d["ok"] else f"{len(d['failures'])} open")


def cmd_cutlist(a) -> Result:
    from .cutlist import cutlist
    _project(a.slug)
    c = cutlist(a.slug)
    return Result(OK, c, json.dumps(c, indent=1, default=str), "cutlist")


# ─── Bought parts ────────────────────────────────────────────────────────────

def _bought_call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except (ValueError, KeyError, FileNotFoundError) as e:
        raise UsageError(str(e).strip("'\"")) from e


def cmd_bought_ls(a) -> Result:
    from .bought import list_bought
    _project(a.slug)
    rows = list_bought(a.slug)
    lines = [f"  {r['name']:22} {r['kind']:9} {r.get('file', '')}" for r in rows]
    return Result(OK, {"project": a.slug, "bought": rows},
                  "\n".join(lines) or "no bought parts yet", f"{len(rows)} bought")


def cmd_bought_info(a) -> Result:
    from .bought import bought_info
    _project(a.slug)
    info = _bought_call(bought_info, a.slug, a.name)
    return Result(OK, info, json.dumps(info, indent=1, default=str), a.name)


def cmd_bought_add_step(a) -> Result:
    from .bought import bought_info, register_step
    _project(a.slug)
    path = _bought_call(register_step, a.slug, a.name, a.step_path, a.source, a.vendor)
    info = _bought_call(bought_info, a.slug, a.name)
    return Result(OK, info, f"registered {a.name} from {path}\n"
                  + json.dumps(info, indent=1, default=str),
                  f"added {a.name} (STEP)", [str(path)])


def cmd_bought_add_measured(a) -> Result:
    from .bought import bought_info, register_measured
    _project(a.slug)
    holes = []
    for h in a.hole or []:
        try:
            x, y = (float(v) for v in h.split(","))
        except ValueError:
            raise UsageError(f"--hole takes X,Y in mm, got {h!r}") from None
        holes.append([x, y])
    length, width, height = a.size
    path = _bought_call(register_measured, a.slug, a.name, length, width, height,
                        source=a.source, vendor=a.vendor, holes=holes or None,
                        hole_dia=a.hole_dia)
    info = _bought_call(bought_info, a.slug, a.name)
    text = (f"wrote {Path(path).name}\n  envelope {info['bbox_mm']} mm · UNVERIFIED\n"
            f"  source {info['source']}\n"
            "  the provenance gate reports UNCHECKED until `cad bought verify` records a measurement")
    return Result(OK, info, text, f"added {a.name} (measured, unverified)", [str(path)])


def cmd_bought_verify(a) -> Result:
    from .bought import verify
    _project(a.slug)
    info = _bought_call(verify, a.slug, a.name, a.note)
    return Result(OK, info, f"{a.name} verified\n  envelope {info['bbox_mm']} mm\n"
                  f"  source {info['source']}", f"verified {a.name}")


# ─── Parser ──────────────────────────────────────────────────────────────────

class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on bad arguments; 2 means UNCHECKED here, so use 3."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(USAGE, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    # --json may come before or after the command. SUPPRESS keeps a subcommand
    # from resetting a --json given before it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print one JSON object on stdout")

    p = _Parser(prog="cad", description="cad-agent: parametric parts, deterministic "
                "gates, headless renders. Every command runs on build123d.",
                epilog=EXIT_CODES, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", default=False,
                   help="print one JSON object on stdout")
    p.add_argument("--projects", metavar="DIR",
                   help="projects directory (default: CAD_PROJECTS, else cad-agent/projects)")
    p.add_argument("--version", action="store_true", help="print version and render backend")
    sub = p.add_subparsers(dest="cmd", metavar="<command>", parser_class=_Parser)

    def add(name, func, help, parent=sub):
        sp = parent.add_parser(name, help=help, description=help, parents=[common],
                               epilog=EXIT_CODES,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
        sp.set_defaults(func=func, cmd_name=name, slug=None)
        return sp

    def sets(sp):
        sp.add_argument("--set", action="append", metavar="KEY=VALUE",
                        help="override one PARAMS value for this run (repeatable)")

    sp = add("init", cmd_init, "create a project")
    sp.add_argument("slug")
    sp.add_argument("--brief", default="", help="one paragraph for mech_profile.md")

    sp = add("ls", cmd_ls, "list projects, or one project's parts and bought parts")
    sp.add_argument("slug", nargs="?")

    sp = add("status", cmd_status, "parts and the last check run")
    sp.add_argument("slug")

    sp = add("build", cmd_build, "build one part and measure it")
    sp.add_argument("slug")
    sp.add_argument("part")
    sets(sp)

    sp = add("render", cmd_render, "render a part, or the assembly, to a PNG")
    sp.add_argument("slug")
    sp.add_argument("part", nargs="?", help="omit for the whole assembly")
    sp.add_argument("--view", default="iso", help="iso, iso2, top, bottom, front, back, left, right")
    sp.add_argument("--tolerance", type=float, default=0.05, help="tessellation tolerance, mm")
    sets(sp)

    sp = add("export", cmd_export, "export a part as STEP (for a shop) or STL (for a printer)")
    sp.add_argument("slug")
    sp.add_argument("part")
    sp.add_argument("--format", choices=("step", "stl"), default="step")

    sp = add("measure", cmd_measure, "minimum distance or overlap between two bodies "
             "(exit 1 if they interfere)")
    sp.add_argument("slug")
    sp.add_argument("a")
    sp.add_argument("b")
    sp.add_argument("--posed", action="store_true",
                    help="use the bodies as placed by assembly.py, not each part at its origin")

    sp = add("tables", cmd_tables, "hole sizes, tap drills, insert bores, extrusions, densities")
    sp.add_argument("section", nargs="?", help=", ".join(TABLE_ALIASES))

    sp = add("tool", cmd_tool, "generate a tool envelope and measure it")
    sp.add_argument("kind", choices=TOOL_KINDS)
    sp.add_argument("params", nargs="*", metavar="KEY=VALUE")

    sp = add("check", cmd_check, "run every gate and write checks.json "
             "(or, with --part, the fast part-only rules)")
    sp.add_argument("slug")
    sp.add_argument("--part", help="fast loop: one part, part rules only")
    sp.add_argument("--views", default="iso", help="views to render and gate, comma separated")
    sp.add_argument("--all", action="store_true", help="show passing rows too")
    sets(sp)

    add("rules", cmd_rules, "every registered check and what it verifies")

    sp = add("approve", cmd_approve, "promote current renders to approved baselines "
             "(your call: look at the diff first)")
    sp.add_argument("slug")
    sp.add_argument("--part")
    sp.add_argument("--view")

    sp = add("done", cmd_done, "the gate: exit 0 only if nothing is FAIL or UNCHECKED")
    sp.add_argument("slug")

    sp = add("cutlist", cmd_cutlist, "stock to order and cut, roughly priced")
    sp.add_argument("slug")

    bp = add("bought", None, "bought parts: vendor STEP or measured, always with a source")
    bsub = bp.add_subparsers(dest="bought_cmd", metavar="<action>", parser_class=_Parser)

    sp = add("ls", cmd_bought_ls, "bought parts in a project", parent=bsub)
    sp.add_argument("slug")
    sp.set_defaults(cmd_name="bought ls")

    sp = add("info", cmd_bought_info, "envelope and provenance of one bought part", parent=bsub)
    sp.add_argument("slug")
    sp.add_argument("name")
    sp.set_defaults(cmd_name="bought info")

    sp = add("add-step", cmd_bought_add_step, "register a vendor STEP file", parent=bsub)
    sp.add_argument("slug")
    sp.add_argument("name")
    sp.add_argument("step_path")
    sp.add_argument("--source", required=True, help="the page the file came from")
    sp.add_argument("--vendor")
    sp.set_defaults(cmd_name="bought add-step")

    sp = add("add-measured", cmd_bought_add_measured,
             "add a bought part from a datasheet envelope (UNVERIFIED until measured)", parent=bsub)
    sp.add_argument("slug")
    sp.add_argument("name")
    sp.add_argument("--size", nargs=3, type=float, required=True, metavar=("L", "W", "H"))
    sp.add_argument("--source", required=True, help="the drawing or datasheet page")
    sp.add_argument("--vendor")
    sp.add_argument("--hole", action="append", metavar="X,Y",
                    help="bolt hole in mm, repeatable; write --hole=-15.5,-15.5 when X is negative")
    sp.add_argument("--hole-dia", type=float, default=3.2)
    sp.set_defaults(cmd_name="bought add-measured")

    sp = add("verify", cmd_bought_verify, "record a calliper measurement for a measured part",
             parent=bsub)
    sp.add_argument("slug")
    sp.add_argument("name")
    sp.add_argument("--note", required=True, help="what was measured, and how")
    sp.set_defaults(cmd_name="bought verify")
    return p


# ─── Running ─────────────────────────────────────────────────────────────────

def _log(a, argv, res: Result, ms: int) -> None:
    """Append one line to the activity log. Never changes a verdict."""
    entry = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "cmd": getattr(a, "cmd_name", None), "argv": argv, "exit": res.code,
             "summary": res.summary, "files": res.files, "ms": ms}
    try:
        base = st.ROOT
        if getattr(a, "slug", None):
            try:
                base = st.project_dir(a.slug)
            except FileNotFoundError:
                pass
        d = base / ".cad"
        d.mkdir(parents=True, exist_ok=True)
        with (d / "log.jsonl").open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass


def _emit(a, res: Result) -> None:
    if getattr(a, "json", False):
        print(json.dumps({"cmd": getattr(a, "cmd_name", None), "exit": res.code,
                          "data": res.data}, default=str))
        if res.code in (USAGE, CRASH):
            print(res.text, file=sys.stderr)
    else:
        print(res.text, file=sys.stderr if res.code in (USAGE, CRASH) else sys.stdout)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        a = parser.parse_args(argv)
    except SystemExit as e:  # --help is 0, bad arguments are 3
        return e.code if isinstance(e.code, int) else USAGE

    projects = a.projects or os.environ.get("CAD_PROJECTS")
    if projects:
        st.ROOT = Path(projects).expanduser().resolve()

    if a.version:
        import build123d
        from .render import backend_status
        print(f"cad-agent 0.1.0  build123d {build123d.__version__}  render: {backend_status()}")
        return OK
    if not getattr(a, "func", None):
        (parser if not a.cmd else parser._subparsers._group_actions[0].choices[a.cmd]).print_help(sys.stderr)
        return USAGE

    t0 = time.perf_counter()
    try:
        res = a.func(a)
    except UsageError as e:
        res = Result(USAGE, {"error": str(e)}, f"cad {a.cmd_name}: {e}", str(e))
    except BuildFailed as e:
        res = Result(FAIL, {"error": str(e)}, str(e), str(e))
    except Exception as e:
        res = Result(CRASH, {"error": f"{type(e).__name__}: {e}"},
                     "cad crashed, this is a cad-agent bug:\n" + traceback.format_exc(),
                     f"crash: {type(e).__name__}")
    _emit(a, res)
    _log(a, argv, res, int((time.perf_counter() - t0) * 1000))
    return res.code


if __name__ == "__main__":
    sys.exit(main())
