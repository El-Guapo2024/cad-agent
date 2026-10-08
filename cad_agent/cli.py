"""cad: the command line for cad-agent.

Every tool the retired MCP server offered has a subcommand here, calling the
same functions, so an agent drives the whole loop from a shell, and nothing sits in its context
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
import contextlib
import difflib
import inspect
import io
import json
import os
import re
import shlex
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import gui_client
from . import macro
from . import state as st
from . import gui
from .gui import COMMAND_NAME_RE, FREECAD_PROP_NAMES, VIEW_CAMERA, VIEW_PROJECTION
from .placements import PlacementError
from .undo import UndoError

OK, FAIL, UNCHECKED, USAGE, CRASH = 0, 1, 2, 3, 4
_RUNS = 0     # commands run in this process: only the first one runs fresh
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


class WorkbenchDown(Exception):
    """`cad gui` found no running workbench to answer for a project: UNCHECKED,
    not a usage error — the command was fine, the workbench just is not up."""


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


def _views(text: str) -> tuple[str, ...]:
    """A comma list of views for check, verify and approve, each one the renderer draws."""
    from .render import VIEWS
    views = tuple(v.strip() for v in text.split(",") if v.strip()) or ("iso",)
    bad = [v for v in views if v not in VIEWS]
    if bad:
        raise UsageError(f"unknown view {', '.join(repr(v) for v in bad)} "
                         f"(views: {', '.join(sorted(VIEWS))})")
    return views


def _tolerance(value: float | None) -> None:
    """--tolerance is the tessellation tolerance in mm: the mesher fails on zero or less."""
    if value is not None and not 0 < value < float("inf"):
        raise UsageError(f"--tolerance is the tessellation tolerance in mm and must be above 0, "
                         f"got {value:g}")


def _actor(a) -> str:
    """Who to journal a change under: `--actor` when the caller passed it
    (the workbench server adds it to every command it runs; see undo.record's
    docstring), else undo.actor()'s own CAD_ACTOR-env fallback (default
    "agent")."""
    from . import undo as un
    return a.actor or un.actor()


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
        defaults = dict(getattr(st._load_module(path), "PARAMS", {}))
    except Exception as e:
        raise BuildFailed(f"{a.part} did not load: {st.why(e)}") from e
    unknown = sorted(set(ov) - set(defaults))
    if unknown:
        raise UsageError(f"{a.part} has no parameter {', '.join(unknown)} "
                         f"(params: {', '.join(sorted(defaults))})")
    from .params import ParamError, coerce
    for key, value in list(ov.items()):          # a number where the part has a number, as `cad set`
        if isinstance(defaults[key], (bool, int, float)):
            try:
                ov[key] = coerce(key, defaults[key], value)
            except ParamError as e:
                raise UsageError(str(e)) from None
    return ov


def _build(slug: str, name: str, overrides: dict | None = None):
    _part(slug, name)
    try:
        return st.build_part(slug, name, overrides)
    except Exception as e:
        raise BuildFailed(f"{name} did not build: {st.why(e)}") from e


def _assembly(slug: str) -> dict:
    _project(slug)
    try:
        asm, *_ = st.load_assembly(slug)
    except Exception as e:
        raise BuildFailed(f"{slug} assembly did not build: {st.why(e)}") from e
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
    try:
        existing = st.project_dir(a.slug)
    except FileNotFoundError:
        pass
    else:
        raise UsageError(f"project {a.slug!r} already exists at {existing}")
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
        none = "no projects yet" + ("" if st.ROOT.is_dir() else
                                    f" ({st.ROOT} does not exist; `cad init NAME` creates it)")
        return Result(OK, {"projects": names}, "\n".join(names) or none, f"{len(names)} projects")
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
    except ValueError as e:
        lines.append(f"  checks.json cannot be read ({e}): run `cad check` to write it again")
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
    _tolerance(a.tolerance)
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
    except Exception as e:                     # --format is checked by the parser: this is the part
        raise BuildFailed(f"{a.part} did not build: {st.why(e)}") from e
    return Result(OK, {"project": a.slug, "part": a.part, "format": a.format,
                       "path": path}, path, f"{a.part} as {a.format}", [path])


# ─── Measurement and reference ───────────────────────────────────────────────

def cmd_measure(a) -> Result:
    _project(a.slug)
    if not a.posed:
        try:
            _part(a.slug, a.a)
            _part(a.slug, a.b)
        except UsageError as e:
            raise UsageError(f"{e}; bought parts and placed bodies need --posed") from None
    from .geom import closest_points, intersection_volume
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
    gap, pa, pb = closest_points(sa, sb)
    data.update(interferes=False, overlap_mm3=0.0, min_distance_mm=round(gap, 4),
                points=[list(pa), list(pb)])
    return Result(OK, data, f"{a.a} vs {a.b} ({where}): clear, minimum distance {gap:.4f} mm",
                  f"clear {gap:.3f} mm")


def cmd_mass(a) -> Result:
    """FreeCAD's Mass Properties for bodies as the scene shows them."""
    _project(a.slug)
    from .geom import DENSITY, mass_properties
    from .scene import placed_solids
    try:
        shown, materials = placed_solids(a.slug)
    except (PlacementError, UsageError):
        raise
    except Exception as e:
        raise BuildFailed(f"{a.slug} did not build: {st.why(e)}") from e
    names = a.bodies or sorted(shown)
    missing = [n for n in names if n not in shown]
    if missing:
        raise UsageError(f"not in {a.slug}: {', '.join(missing)} (bodies: {', '.join(sorted(shown))})")
    items, per, defaulted = [], [], []
    for n in names:
        mat = (materials.get(n) or "").strip().lower()
        # FreeCAD uses 1e-6 kg/mm^3 (water) when an object has no density.
        density = DENSITY[mat] * 1e-6 if mat in DENSITY else 1e-6
        if mat not in DENSITY:
            defaulted.append(n)
        items.append((shown[n], density))
        one = mass_properties([(shown[n], density)])
        per.append({"body": n, "material": materials.get(n), "density_kg_mm3": density,
                    "volume_mm3": one.get("volume_mm3"), "mass_kg": one.get("mass_kg")})
    data = {"project": a.slug, "bodies": per, "default_density": defaulted, **mass_properties(items)}
    msg = (f"{len(names)} bod{'y' if len(names) == 1 else 'ies'}: volume {data['volume_mm3']:.3f} mm^3, "
           f"mass {data['mass_kg'] * 1000:.3f} g, centre of gravity "
           f"({', '.join(f'{round(c, 3) + 0.0:.3f}' for c in data['cog'])}) mm")
    if defaulted:
        msg += f"; no density for {', '.join(defaulted)}, used 1 g/cm^3 as FreeCAD does"
    return Result(OK, data, msg, f"{data['mass_kg'] * 1000:.2f} g")


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
    known = list(inspect.signature(getattr(tooling, a.kind)).parameters)
    unknown = [k for k in params if k not in known]
    if unknown:
        raise UsageError(f"{a.kind} has no parameter {', '.join(unknown)} (params: {', '.join(known)})")
    for key, value in params.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UsageError(f"{a.kind}: {key} must be a number in mm, got {value!r}")
    try:
        solid = getattr(tooling, a.kind)(**params)
    except (TypeError, ValueError) as e:
        raise UsageError(f"{a.kind}: {e}") from e
    lo, hi = bbox(solid)
    data = {"kind": a.kind, "params": params,
            "bbox_mm": [round(hi[i] - lo[i], 2) for i in range(3)],
            "z_mm": [round(lo[2], 2) + 0.0, round(hi[2], 2) + 0.0]}
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
        except PermissionError:
            raise
        except Exception as e:
            raise BuildFailed(f"{a.part} did not build: {st.why(e)}") from e
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
    p = check_all(a.slug, render_views=_views(a.views))
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
    if a.view:
        _views(a.view)
    try:
        done = approve_views(a.slug, a.part, a.view)
    except FileNotFoundError as e:             # nothing rendered yet: its message says to check first
        raise UsageError(str(e)) from None
    except Exception as e:
        raise BuildFailed(f"{a.slug} did not build: {st.why(e)}") from e
    print("approved renders become the baseline the visual gate compares against; "
          "look at the diff first", file=sys.stderr)
    return Result(OK, {"project": a.slug, "approved": done},
                  "approved:\n" + "\n".join(f"  {d}" for d in done),
                  f"approved {len(done)}", [str(pdir / d) for d in done])


def _where(git: dict | None) -> str:
    if not git:
        return "no git repo"
    if not git.get("commit"):
        return "git repo with no commits"
    return f"commit {git['commit'][:10]}" + (" + uncommitted changes" if git.get("dirty") else "")


def cmd_verify(a) -> Result:
    """Rebuild from source in a fresh process, run every gate, write verify.json."""
    pdir = _project(a.slug)
    from . import verify
    views = _views(a.views)
    mode = (("warm-fork" if os.environ.get("CAD_WARM_CHILD") == "1" else "cold")
            if a._fresh else "reused")
    rec = verify.run(a.slug, fresh=a._fresh, mode=mode, views=views)
    code = {"PASS": OK, "FAIL": FAIL}.get(rec["verdict"], UNCHECKED)
    where = _where(rec["git"])
    lines = [f"{a.slug}  {rec['verdict']}  at {where} · {rec['design_files']} design files · "
             f"{mode} process · {rec['seconds']} s"]
    lines += _rows_text(rec["rows"], a.all)
    lines += [f"  note: {n}" for n in rec["notes"]]
    shown = rec["rows"] if a.all else [r for r in rec["rows"] if r["state"] != "PASS"]
    data = {**{k: v for k, v in rec.items() if k != "rows"}, "rows": shown}
    return Result(code, data, "\n".join(lines), f"{rec['verdict']} at {where}",
                  [str(pdir / "verify.json")])


def cmd_done(a) -> Result:
    """The gate: the last verdict must be PASS and must still describe the files."""
    _project(a.slug)
    from . import verify
    s = verify.status(a.slug)
    stale = [r for r in s["reasons"] if not r.startswith("the verdict was")]
    if s["done"]:
        code = OK
    elif s["verdict"] == "FAIL" and not stale:
        code = FAIL
    else:
        code = UNCHECKED
    if s["done"]:
        head = f"{a.slug}  DONE  verified {s['verified_utc']} at {_where(verify.git_info(st.project_dir(a.slug)))}"
    else:
        head = f"{a.slug}  NOT DONE"
    lines = [head] + [f"  {r}" for r in s["reasons"]]
    lines += [f"  {r['state']:9} {r['rule']:24} {r['subject']:20} {r['measured']}"
              for r in s.get("failing", [])[:10]]
    return Result(code, s, "\n".join(lines),
                  "done" if s["done"] else f"not done: {len(s['reasons'])} reasons")


def cmd_cutlist(a) -> Result:
    from .cutlist import cutlist
    _project(a.slug)
    try:
        c = cutlist(a.slug)
    except Exception as e:
        raise BuildFailed(f"{a.slug} cutlist did not build: {st.why(e)}") from e
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
    from .bought import bought_dir, bought_info, register_step
    pdir = _project(a.slug)
    src = Path(a.step_path).expanduser()
    dest = bought_dir(a.slug, create=True) / f"{a.name}{src.suffix.lower()}"
    sidecar = dest.with_suffix(".json")
    before = [dest.read_text() if dest.exists() else None,
             sidecar.read_text() if sidecar.exists() else None]
    path = _bought_call(register_step, a.slug, a.name, a.step_path, a.source, a.vendor)
    info = _bought_call(bought_info, a.slug, a.name)
    from . import undo as un
    cmd = shlex.join(["cad", "bought", "add-step", a.slug, a.name, a.step_path, "--source", a.source]
                     + (["--vendor", a.vendor] if a.vendor else []))
    un.record(pdir, "Add Bought Part", cmd,
              [{"path": dest.relative_to(pdir).as_posix(), "before": before[0], "after": dest.read_text()},
               {"path": sidecar.relative_to(pdir).as_posix(), "before": before[1],
                "after": sidecar.read_text()}], by=_actor(a))
    return Result(OK, info, f"registered {a.name} from {path}\n"
                  + json.dumps(info, indent=1, default=str),
                  f"added {a.name} (STEP)", [str(path)])


def cmd_bought_add_measured(a) -> Result:
    from .bought import bought_info, register_measured
    pdir = _project(a.slug)
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
    from . import undo as un
    cmd_parts = ["cad", "bought", "add-measured", a.slug, a.name,
                "--size", str(length), str(width), str(height), "--source", a.source]
    if a.vendor:
        cmd_parts += ["--vendor", a.vendor]
    cmd_parts += [f"--hole={x:g},{y:g}" for x, y in holes]
    if holes:
        cmd_parts += ["--hole-dia", str(a.hole_dia)]
    un.record(pdir, "Add Bought Part", shlex.join(cmd_parts),
              [{"path": Path(path).relative_to(pdir).as_posix(), "before": None,
                "after": Path(path).read_text()}], by=_actor(a))
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


# ─── Evals ───────────────────────────────────────────────────────────────────

def _eval_call(fn, *args, **kw):
    from . import evals
    try:
        return fn(*args, **kw)
    except evals.EvalError as e:
        raise UsageError(str(e)) from None


def _evals_root(a) -> Path:
    from . import evals
    return evals.tasks_dir(getattr(a, "evals", None))


def _eval_code(verdicts) -> int:
    verdicts = set(verdicts)
    return FAIL if "FAIL" in verdicts else UNCHECKED if "UNCHECKED" in verdicts else OK


def cmd_eval_ls(a) -> Result:
    from . import evals
    root = _evals_root(a)
    rows = [{"task": t.name, "title": t.title, "given": t.given,
             "reference": (t.path / "reference").is_dir()}
            for t in _eval_call(evals.list_tasks, root)]
    w = max([16] + [len(r["task"]) for r in rows])
    lines = [f"{len(rows)} tasks in {root}"]
    for r in rows:
        lines += [f"  {r['task']:{w}} {r['title']}",
                  f"  {'':{w}} given: {', '.join(r['given']) or 'nothing'}"]
    return Result(OK, {"evals": str(root), "tasks": rows}, "\n".join(lines), f"{len(rows)} tasks")


def cmd_eval_brief(a) -> Result:
    from . import evals
    task = _eval_call(evals.get_task, _evals_root(a), a.task)
    given = task.given
    text = (task.brief.rstrip() + f"\n\ngiven files, laid into projects/{task.name}/:\n"
            + "\n".join(f"  {g}" for g in given))
    return Result(OK, {"task": task.name, "brief": task.brief, "given": given}, text,
                  f"{task.name}: {len(given)} given files")


def cmd_eval_score(a) -> Result:
    from . import evals
    task = _eval_call(evals.get_task, _evals_root(a), a.task)
    r = _eval_call(evals.score, task, Path(a.design), keep=a.keep, show_all=a.all)
    lines = [f"{r['task']}  {r['verdict']}  {r['score']:.1%}  {r['passed']}/{r['graded']} rows pass · "
             f"{r['skipped']} render and {r['na']} n/a rows not counted · {r['seconds']} s"]
    lines += _rows_text(r["rows"], True)
    if not a.all and r["passed"]:
        lines.append(f"  ({r['passed']} passing rows hidden; --all shows them)")
    lines += [f"  note: {n}" for n in r["notes"]]
    if r.get("kept"):
        lines.append(f"  kept {r['kept']}")
    return Result(_eval_code([r["verdict"]]), r, "\n".join(lines), f"{r['verdict']} {r['score']:.1%}")


def cmd_eval_run(a) -> Result:
    from . import evals
    if not a.agent:
        raise UsageError("cad eval run needs --agent CMD, run through the shell in each task's repo "
                         "({brief} {dir} {task} {root} {plugin} are filled in), e.g. "
                         "--agent 'claude -p \"$(cat {brief})\" --plugin-dir {plugin}'")
    r = _eval_call(evals.run, _evals_root(a), a.agent, a.tasks, a.timeout, a.keep,
                   Path(a.out).expanduser() if a.out else None)
    w = max([16] + [len(t["task"]) for t in r["tasks"]])
    lines = [f"{'task':{w}} {'verdict':9} {'score':>6} {'rows':>9} {'agent s':>8} {'score s':>8}"]
    for t in r["tasks"]:
        lines.append(f"{t['task']:{w}} {t['verdict']:9} {t['score']:6.1%} "
                     f"{t['passed']:>4}/{t['graded']:<4} {t['agent_seconds']:8.0f} {t['seconds']:8.1f}"
                     + ("  agent timed out" if t["timed_out"] else ""))
        lines += [f"    {ln.strip()}" for ln in _rows_text(t["rows"][:3], True)]
    s = r["summary"]
    lines += [f"{s['tasks']} tasks, {s['pass']} PASS, mean score {s['mean_score']:.1%}",
              f"results: {r['file']}"]
    if r.get("plugin_dir"):
        lines.append(f"plugin copy kept at {r['plugin_dir']}")
    return Result(_eval_code(t["verdict"] for t in r["tasks"]), r, "\n".join(lines),
                  f"{s['pass']}/{s['tasks']} PASS, mean {s['mean_score']:.1%}", [r["file"]])


# ─── Macros: FreeCAD's macro recorder, for this CLI ──────────────────────────
# A macro is a text file of `cad` commands (macro.py owns the file format and
# the shared replay loop); see macro.py's module docstring for the contract.

_EXIT_LABEL = {OK: "OK", FAIL: "FAIL", UNCHECKED: "UNCHECKED", USAGE: "USAGE", CRASH: "CRASH"}


def _macro_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        raise UsageError(str(e).strip("'\"")) from e


def cmd_macro_ls(a) -> Result:
    rows = macro.list_macros()
    lines = [f"  {r['name']:24} {r['lines']:4} lines  {r['modified']}" for r in rows]
    return Result(OK, {"dir": str(macro.macro_dir()), "macros": rows},
                  "\n".join(lines) or "no macros yet", f"{len(rows)} macros")


def cmd_macro_show(a) -> Result:
    text = _macro_call(macro.read_macro, a.name)
    return Result(OK, {"name": a.name, "text": text}, text,
                  f"{a.name}: {len(text.splitlines())} lines")


def cmd_macro_rm(a) -> Result:
    path = _macro_call(macro.delete_macro, a.name)
    return Result(OK, {"name": a.name, "deleted": True}, f"deleted {path}", f"deleted {a.name}")


def cmd_macro_save(a) -> Result:
    if a.file == "-":
        text = sys.stdin.read()
    else:
        src = Path(a.file).expanduser()
        if not src.is_file():
            raise UsageError(f"no file {a.file!r}")
        text = src.read_text()
    path = _macro_call(macro.save_macro, a.name, text)
    return Result(OK, {"name": a.name, "path": str(path)}, f"saved {path}",
                  f"saved {a.name}", [str(path)])


def _macro_exec_line(argv: list[str]) -> dict:
    """One macro line, replayed by re-entering `main` exactly as if it had been
    typed: a `cad gui ...` line falls through to `cmd_gui_*`, so it reaches the
    running workbench through `gui_client` like any other `cad gui` command
    (WorkbenchDown -> exit 2, UNCHECKED, if none is up — the line is skipped
    in effect and the macro carries on, the same as any other UNCHECKED line)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(["--json", "--with-text", *argv])
    out = [ln for ln in buf.getvalue().splitlines() if ln.startswith("{")]
    payload = json.loads(out[-1]) if out else {}
    return {"exit": code, "text": payload.get("text", "")}


def cmd_macro_run(a) -> Result:
    text = _macro_call(macro.read_macro, a.name)
    result = macro.run_lines(text.splitlines(), _macro_exec_line)
    verdict = _EXIT_LABEL.get(result["exit"], result["exit"])
    lines = [f"{a.name}: {len(result['ran'])} line(s) run, exit {verdict}"]
    for i, r in enumerate(result["ran"]):
        note = r["text"].strip().splitlines()[0] if r["text"].strip() else ""
        tag = _EXIT_LABEL.get(r["exit"], r["exit"])
        lines.append(f"  [{i}] {r['line']}  {tag}" + (f"  -- {note}" if note else ""))
    return Result(result["exit"], {"name": a.name, **result}, "\n".join(lines),
                  f"{a.name}: {len(result['ran'])} ran, exit {verdict}")


# ─── Parser ──────────────────────────────────────────────────────────────────

class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on bad arguments; 2 means UNCHECKED here, so use 3."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(USAGE, f"{self.prog}: error: {message}\n")


# ─── Workbench ───────────────────────────────────────────────────────────────

def _triple(text: str, flag: str) -> tuple[float, float, float]:
    try:
        vals = tuple(float(x) for x in text.split(","))
    except ValueError:
        vals = ()
    if len(vals) != 3:
        raise UsageError(f"{flag} takes X,Y,Z in mm or degrees, got {text!r} "
                         f"(write {flag}=-5,0,0 when the first value is negative)")
    return vals


def cmd_scene(a) -> Result:
    _project(a.slug)
    _tolerance(a.tolerance)
    from .placements import PlacementError
    from .scene import write_scene
    try:
        path, sc = write_scene(a.slug, a.tolerance)
    except (PlacementError, UsageError):
        raise
    except Exception as e:
        raise BuildFailed(f"{a.slug} did not build: {st.why(e)}") from e
    tris = sc["triangles"]
    size = path.stat().st_size
    data = {"project": a.slug, "path": str(path), "bytes": size, "triangles": tris,
            "bodies": [b["name"] for b in sc["bodies"]], "assembly": sc["assembly"],
            "axes": [x["name"] for x in sc["axes"]], "source_hash": sc["source_hash"],
            "unknown_placements": sc["unknown_placements"]}
    text = (f"{a.slug}: {len(sc['bodies'])} bodies, {tris} triangles -> {path} "
            f"({size / 1024:.0f} KB)")
    return Result(OK, data, text, f"scene: {len(sc['bodies'])} bodies", [str(path)])


def cmd_place(a) -> Result:
    pdir = _project(a.slug)
    from . import placements as pl
    from .checks.fit import check_fit
    from .geom import bbox
    from .motion import _bbox_gap
    try:
        base, clearance, allow, _ = st.load_assembly(a.slug, placed=False)
    except Exception as e:
        raise BuildFailed(f"{a.slug} assembly did not build: {st.why(e)}") from e
    if base is None:
        raise UsageError(f"{a.slug} has no assembly.py, so there is nothing to place parts in")
    if a.body not in base:
        raise UsageError(f"no body {a.body!r} in {a.slug}'s assembly (bodies: {', '.join(sorted(base))})")
    placed = pl.load(pdir)
    moves = [x for x in (a.move, a.turn, a.about, a.by) if x is not None]
    if a.reset:
        if moves:
            raise UsageError("--reset puts the part back where assembly.py puts it; it takes no other option")
        placed.pop(a.body, None)
        entry = None
    else:
        if not moves:
            raise UsageError("say how to move it: --move, --by, --turn, --about, or --reset")
        entry = dict(placed.get(a.body) or {})
        if not entry:
            lo, hi = bbox(base[a.body])
            entry = {"move": (0.0, 0.0, 0.0), "turn": (0.0, 0.0, 0.0),
                     "about": tuple(round((lo[i] + hi[i]) / 2, 4) for i in range(3))}
        if a.move is not None:
            entry["move"] = _triple(a.move, "--move")
        if a.turn is not None:
            entry["turn"] = _triple(a.turn, "--turn")
        if a.about is not None:
            entry["about"] = _triple(a.about, "--about")
        if a.by is not None:
            d = _triple(a.by, "--by")
            entry["move"] = tuple(entry["move"][i] + d[i] for i in range(3))
        if pl.is_identity(entry):
            placed.pop(a.body, None)          # back where the code puts it
            entry = None
        else:
            placed[a.body] = entry
    toml_path = pdir / pl.FILE
    before_text = toml_path.read_text() if toml_path.exists() else None
    path = pl.save(pdir, placed)
    after_text = toml_path.read_text() if toml_path.exists() else None
    from . import undo as un
    cmd_parts = ["cad", "place", a.slug, a.body]
    if a.reset:
        cmd_parts.append("--reset")
    else:
        if a.move is not None:
            cmd_parts.append(f"--move={a.move}")
        if a.by is not None:
            cmd_parts.append(f"--by={a.by}")
        if a.turn is not None:
            cmd_parts.append(f"--turn={a.turn}")
        if a.about is not None:
            cmd_parts.append(f"--about={a.about}")
    un.record(pdir, "Placement", shlex.join(cmd_parts),
              [{"path": pl.FILE, "before": before_text, "after": after_text}], by=_actor(a))

    # What the move did: the fit gate's own rules, the moved body against each
    # other body. Boxes far apart are settled without the exact query.
    parts = pl.apply(base, placed)
    req = {tuple(sorted(k.split("|"))) if isinstance(k, str) else tuple(sorted(k)): float(v)
           for k, v in clearance.items()}
    rows = []
    for other in sorted(parts):
        if other == a.body:
            continue
        need = req.get(tuple(sorted((a.body, other))), 0.0)
        gap = _bbox_gap(parts[a.body], parts[other])
        if gap > need + 1.0:
            pair = " vs ".join(sorted((a.body, other)))
            rows.append({"pair": pair, "state": "PASS", "check": "clearance",
                         "detail": f"clear: boxes {gap:.1f} mm apart",
                         "measured_mm": round(gap, 4), "required_mm": need})
            continue
        rows += check_fit({a.body: parts[a.body], other: parts[other]}, clearance,
                          allow_contact=allow)
    fails = [r for r in rows if r["state"] == "FAIL"]
    where = ("back where assembly.py puts it" if entry is None else
             f"move {list(entry['move'])} mm, turn {list(entry['turn'])} deg")
    lines = [f"{a.slug}/{a.body}: {where}"]
    lines += [f"  FAIL  {r['pair']}: {r['detail']}" for r in fails] or ["  clear of every other body"]
    data = {"project": a.slug, "body": a.body, "placement": entry, "file": str(path),
            "rows": rows, "fails": len(fails)}
    return Result(FAIL if fails else OK, data, "\n".join(lines),
                  f"placed {a.body}: {len(fails)} failing" if fails else f"placed {a.body}: clear",
                  [str(path)] if path.exists() else [])


def cmd_set(a) -> Result:
    path = _part(a.slug, a.part)
    from . import params as pm
    from .geom import mass_g
    changes = _pairs(a.values, "cad set")
    if not changes:
        raise UsageError("say what to change: cad set <slug> <part> key=value ...")
    try:
        current = pm.read(path)
    except (SyntaxError, ValueError) as e:        # a UnicodeDecodeError, or a null byte, is a ValueError
        raise BuildFailed(f"{a.part} does not parse: {e}") from e
    names = ", ".join(current) or "none"
    for key in changes:
        if key not in current:
            raise UsageError(f"{a.part} has no parameter {key!r} (params: {names})")
        if not current[key]["editable"]:
            raise UsageError(f"{a.part}.{key} is computed in the file ({current[key]['value']}); "
                             "edit the Python instead")
    try:
        new = {k: pm.coerce(k, current[k]["value"], v) for k, v in changes.items()}
    except pm.ParamError as e:
        raise UsageError(str(e)) from None
    # Build with the new values first: a value that breaks the part is not written.
    solid, meta = _build(a.slug, a.part, new)
    before = {k: current[k]["value"] for k in new}
    pdir = _project(a.slug)
    before_text = path.read_text()
    try:
        pm.write(path, new)
    except pm.ParamError as e:
        raise UsageError(str(e)) from None
    from . import undo as un
    un.record(pdir, "Edit Parameters", shlex.join(["cad", "set", a.slug, a.part, *a.values]),
              [{"path": path.relative_to(pdir).as_posix(), "before": before_text,
                "after": path.read_text()}], by=_actor(a))
    from .runner import part_check
    r = part_check(a.slug, a.part, {})
    code = _verdict(x["state"] for x in r["rows"])
    try:
        mass = round(mass_g(solid, meta["material"]), 2) if meta.get("material") else None
    except KeyError:
        mass = None
    moved = ", ".join(f"{k} {before[k]!r} -> {new[k]!r}" for k in new)
    d = r["bbox_mm"]
    lines = [f"{a.slug}/{a.part}: {moved}",
             f"  bbox {d[0]} x {d[1]} x {d[2]} mm" + (f" · {mass} g" if mass is not None else "")]
    lines += _rows_text(r["rows"], False)
    data = {"project": a.slug, "part": a.part, "changed": {k: [before[k], new[k]] for k in new},
            "bbox_mm": d, "mass_g": mass, "failing": r["failing"], "file": str(path)}
    return Result(code, data, "\n".join(lines), f"set {a.part}: {moved}", [str(path)])


# ─── Undo/redo: one journal shared by the UI and the agent ─────────────────
# `cad set`, `cad place` and `cad bought add-*` each call undo.record() right
# after they write their files (see those commands above). A macro is not a
# transaction of its own: replaying one just re-runs those same commands
# (macro._macro_exec_line re-enters `main`), so each line that changes
# something journals its own entry exactly as if it had been typed by hand —
# nothing macro-specific lives here.

def _undo_followup(slug: str, entry: dict) -> str | None:
    """The cheap re-check the original command itself would run, repeated
    after undo/redo rewrites an entry's files (e.g. a set's part gates).
    Anything heavier (`cad check`, a render) is left for the next `cad
    check`; the workbench's own file watcher picks up the rewritten file
    either way. Best-effort: any failure here is swallowed, since the files
    themselves were already written and verified by `undo.perform`."""
    try:
        if entry["name"] == "Edit Parameters" and len(entry["files"]) == 1:
            part = Path(entry["files"][0]["path"]).stem
            from .runner import part_check
            r = part_check(slug, part, {})
            code = _verdict(x["state"] for x in r["rows"])
            label = "OK" if code == OK else ("FAIL" if code == FAIL else "UNCHECKED")
            return f"part gates for {part}: {label}"
        if entry["name"] == "Placement":
            f = next((f for f in entry["files"] if f["path"] == "placements.toml"), None)
            if f is None:
                return None
            import tomllib

            def parse(text):
                try:
                    return tomllib.loads(text) if text else {}
                except tomllib.TOMLDecodeError:
                    return {}
            b, af = parse(f["before"]), parse(f["after"])
            bodies = sorted(n for n in set(b) | set(af) if b.get(n) != af.get(n))
            if not bodies:
                return None
            pdir = _project(slug)
            base, clearance, allow, _ = st.load_assembly(slug, placed=False)
            if base is None:
                return None
            from . import placements as pl
            from .checks.fit import check_fit
            parts = pl.apply(base, pl.load(pdir))
            rows = check_fit(parts, clearance, allow_contact=allow)
            touching = [r for r in rows if any(b in r["pair"].split(" vs ") for b in bodies)]
            fails = sum(1 for r in touching if r["state"] == "FAIL")
            return (f"fit check for {', '.join(bodies)}: {fails} failing" if fails
                    else f"fit check for {', '.join(bodies)}: clear")
    except Exception:
        return None
    return None


def _undo_redo(a, direction: str) -> Result:
    pdir = _project(a.slug)
    if a.steps < 1:
        raise UsageError("--steps must be at least 1")
    from . import undo as un
    before = un.load(pdir)
    if not before["undo" if direction == "undo" else "redo"]:
        off = " (undo is switched off: `cad pref MaxUndoSize 20` turns it on)" if un.max_steps() == 0 else ""
        raise UsageError(f"nothing to {direction} in {a.slug}{off}")
    result = un.perform(pdir, direction, steps=a.steps)
    applied = result["applied"]
    if not applied:
        raise UndoError(result["blocked"]["reason"])
    touched = sorted({f["path"] for e in applied for f in e["files"]})
    follow_up = _undo_followup(a.slug, applied[-1])
    after = un.load(pdir)
    lines = [f"{a.slug}: {direction} {len(applied)} step(s)"]
    lines += [f"  {e['name']} ({e['by']}, {e['t']})" for e in applied]
    lines += [f"  wrote {p}" for p in touched]
    if result["blocked"]:
        lines.append(f"  stopped: {result['blocked']['reason']}")
    if follow_up:
        lines.append(f"  {follow_up}")
    data = {"project": a.slug, "direction": direction,
            "applied": [{"id": e["id"], "name": e["name"], "by": e["by"], "t": e["t"]} for e in applied],
            "files": touched, "blocked": (result["blocked"] or {}).get("reason"),
            "remaining": {"undo": len(after["undo"]), "redo": len(after["redo"])},
            "follow_up": follow_up}
    summary = f"{direction}: {len(applied)} step(s)" + (" (stopped early)" if result["blocked"] else "")
    return Result(OK, data, "\n".join(lines), summary, [str(pdir / p) for p in touched])


def cmd_undo(a) -> Result:
    return _undo_redo(a, "undo")


def cmd_redo(a) -> Result:
    return _undo_redo(a, "redo")


def cmd_pref(a) -> Result:
    """User preferences the commands act on (userprefs.py): list, get or set one."""
    from . import userprefs as up
    clamped = ""
    if a.key is not None and a.key not in up.DEFAULTS:
        raise UsageError(f"unknown preference {a.key!r}; known: {', '.join(up.DEFAULTS)}")
    if a.key is not None and a.value is not None:
        try:
            stored = up.set_value(a.key, a.value)
        except ValueError:
            raise UsageError(f"{a.key} takes a whole number, not {a.value!r}")
        if stored != int(a.value):
            lo, hi = up.RANGES[a.key]
            clamped = f"  (asked for {a.value}; {a.key} runs from {lo} to {hi})"
    prefs = up.load()
    shown = {a.key: prefs[a.key]} if a.key else prefs
    lines = [f"{k} = {v}" + ("" if v == up.DEFAULTS[k] else f"  (default {up.DEFAULTS[k]})") for k, v in shown.items()]
    if clamped:
        lines[0] += clamped
    return Result(OK, {"prefs": shown, "path": str(up.path())}, "\n".join(lines),
                  ", ".join(f"{k}={v}" for k, v in shown.items()), [])


def cmd_cache(a) -> Result:
    """The user cache (appcache.py): where it is, its size against CacheLimit, --clear."""
    from . import appcache
    freed = appcache.clear() if a.clear else None
    total, limit = appcache.size(), appcache.limit_bytes()
    data = {"dir": str(appcache.directory()), "bytes": total, "limit": limit, "over": total > limit,
            "freed": freed}
    lines = [f"cache: {data['dir']}", f"  size {appcache.to_string(total)} (limit {appcache.to_string(limit)})"]
    if freed is not None:
        lines.append(f"  cleared {appcache.to_string(freed)}")
    elif total > limit:
        lines.append(f"  over the limit: `cad cache --clear` clears it")
    return Result(OK, data, "\n".join(lines), appcache.to_string(total), [])


def cmd_history(a) -> Result:
    pdir = _project(a.slug)
    from . import undo as un
    data = un.load(pdir)

    def rows(stack):
        return [{"id": e["id"], "name": e["name"], "by": e["by"], "t": e["t"]}
                for e in reversed(stack)]
    out = {"project": a.slug, "undo": rows(data["undo"]), "redo": rows(data["redo"])}
    lines = [a.slug, "  undo (newest first):"]
    lines += [f"    {r['t']}  {r['by']:5} {r['name']}" for r in out["undo"]] or ["    (none)"]
    lines.append("  redo (newest first):")
    lines += [f"    {r['t']}  {r['by']:5} {r['name']}" for r in out["redo"]] or ["    (none)"]
    return Result(OK, out, "\n".join(lines), f"{len(out['undo'])} undo, {len(out['redo'])} redo")


# ─── Workbench GUI: the shared selection, visibility and view ───────────────
# FreeCADGui's job (Gui.Selection, Visibility, SendMsgToActiveView) as HTTP
# calls to a running `cad serve`, so an agent in a shell and a person at the
# UI can point at the same model. See cad_agent/gui.py and gui_client.py.

_SUBELEM = re.compile(r"^(Face|Edge|Vertex)[1-9]\d*$")


def _gui_body_names(slug: str) -> set[str]:
    from .scene import placed_solids
    shown, _ = placed_solids(slug)
    return set(shown)


def _check_gui_names(slug: str, names: list[str], allow_sub: bool = False) -> None:
    """Unknown name -> usage error naming the real bodies, the same way a bad
    --part or --body does elsewhere in this file."""
    valid = _gui_body_names(slug)
    bad = []
    for n in names:
        base, dot, sub = n.partition(".")
        ok = (base in valid and _SUBELEM.fullmatch(sub)) if (dot and allow_sub) else n in valid
        if not ok:
            bad.append(n)
    if bad:
        raise UsageError(f"not in {slug}: {', '.join(bad)} "
                         f"(bodies: {', '.join(sorted(valid)) or 'none'})")


def _check_gui_command(slug: str, name: str, published) -> None:
    """`cad gui run`'s own guard: if the UI has told us what it can run (GET
    /api/gui's `commands`), an unknown name is a usage error naming close
    matches, the same spirit as `_check_gui_names`. No list published yet
    (the UI hasn't started, or doesn't offer this) -> nothing to check against,
    so the command is sent through regardless; the workbench decides."""
    known = {c["name"] for c in published or []}
    if not known or name in known:
        return
    close = difflib.get_close_matches(name, sorted(known), n=3)
    raise UsageError(f"not a published command in {slug}: {name!r} "
                     + (f"(close matches: {', '.join(close)})" if close
                        else f"(commands: {', '.join(sorted(known))})"))


def _gui_url(slug: str) -> str:
    try:
        return gui_client.find_server(st.ROOT, slug)
    except gui_client.NoWorkbench as e:
        raise WorkbenchDown(str(e)) from None


def _gui_send(fn, *a):
    try:
        return fn(*a)
    except gui_client.NoWorkbench as e:
        raise WorkbenchDown(str(e)) from None
    except gui_client.GuiRequestError as e:
        raise UsageError(str(e)) from None


def _fmt_gui_state(data: dict) -> str:
    v = data.get("view") or {}
    lines = [f"  connected     {data['connected']}",
             f"  selected      {', '.join(data['selected']) or '(none)'}",
             f"  preselected   {data['preselected'] or '(none)'}",
             f"  hidden        {', '.join(data['hidden']) or '(none)'}",
             f"  unselectable  {', '.join(data['unselectable']) or '(none)'}",
             f"  task          {data['task'] or '(none)'}",
             f"  view          camera={v.get('camera')} projection={v.get('projection')}"]
    if data.get("camera_node"):   # what the person sees, ready for `cad gui view PROJECT '<node>'`
        lines.append("  camera node   " + " ".join(data["camera_node"].split()))
    if data.get("view_props"):
        lines.append("  view props")
        for body in sorted(data["view_props"]):
            props = data["view_props"][body]
            lines.append(f"    {body}: " + gui.fmt_props(props))
    return "\n".join(lines)


def cmd_gui_state(a) -> Result:
    _project(a.slug)
    url = _gui_url(a.slug)
    data = _gui_send(gui_client.get_state, url, a.slug)
    return Result(OK, data, f"{a.slug}\n" + _fmt_gui_state(data), f"connected={data['connected']}")


def cmd_gui_select(a) -> Result:
    _project(a.slug)
    _check_gui_names(a.slug, a.names, allow_sub=True)
    url = _gui_url(a.slug)
    r = _gui_send(gui_client.do, url, a.slug, "select", a.names)
    return Result(OK, r, f"{a.slug}: selected {', '.join(a.names)} ({r['clients']} client(s) watching)",
                  f"selected {len(a.names)}")


def cmd_gui_clear(a) -> Result:
    _project(a.slug)
    url = _gui_url(a.slug)
    r = _gui_send(gui_client.do, url, a.slug, "clear", [])
    return Result(OK, r, f"{a.slug}: cleared the selection ({r['clients']} client(s) watching)", "cleared")


def cmd_gui_show(a) -> Result:
    _project(a.slug)
    _check_gui_names(a.slug, a.names, allow_sub=False)
    url = _gui_url(a.slug)
    r = _gui_send(gui_client.do, url, a.slug, "show", a.names)
    return Result(OK, r, f"{a.slug}: shown {', '.join(a.names)} ({r['clients']} client(s) watching)",
                  f"shown {len(a.names)}")


def cmd_gui_hide(a) -> Result:
    _project(a.slug)
    _check_gui_names(a.slug, a.names, allow_sub=False)
    url = _gui_url(a.slug)
    r = _gui_send(gui_client.do, url, a.slug, "hide", a.names)
    return Result(OK, r, f"{a.slug}: hidden {', '.join(a.names)} ({r['clients']} client(s) watching)",
                  f"hidden {len(a.names)}")


def cmd_gui_view(a) -> Result:
    _project(a.slug)
    from .gui import camera_projection
    if a.direction not in (*VIEW_CAMERA, *VIEW_PROJECTION) and not camera_projection(a.direction):
        raise UsageError(f"unknown view {a.direction!r} (one of: "
                         f"{', '.join((*VIEW_CAMERA, *VIEW_PROJECTION))}, or an Inventor camera node "
                         f"as Std_ViewIvIssueCamPos prints it)")
    url = _gui_url(a.slug)
    r = _gui_send(gui_client.do, url, a.slug, "view", [a.direction])
    what = "camera" if camera_projection(a.direction) else a.direction
    return Result(OK, r, f"{a.slug}: view {what} ({r['clients']} client(s) watching)", f"view {what}")


def cmd_gui_fit(a) -> Result:
    _project(a.slug)
    args = ["selection"] if a.selection else []
    url = _gui_url(a.slug)
    r = _gui_send(gui_client.do, url, a.slug, "fit", args)
    what = "the selection" if a.selection else "everything"
    return Result(OK, r, f"{a.slug}: fit {what} ({r['clients']} client(s) watching)", f"fit {what}")


def cmd_gui_say(a) -> Result:
    _project(a.slug)
    text = " ".join(a.text)
    url = _gui_url(a.slug)
    r = _gui_send(gui_client.do, url, a.slug, "say", [text])
    return Result(OK, r, f"{a.slug}: said {text!r} ({r['clients']} client(s) watching)", "said")


def cmd_gui_set(a) -> Result:
    _project(a.slug)
    _check_gui_names(a.slug, [a.body], allow_sub=False)
    try:
        props = gui.parse_prop_args(a.values)
    except gui.GuiError as e:
        raise UsageError(str(e)) from None
    url = _gui_url(a.slug)
    r = _gui_send(gui_client.do, url, a.slug, "set", [a.body], props)
    moved = gui.fmt_props(props)
    return Result(OK, r, f"{a.slug}/{a.body}: {moved} ({r['clients']} client(s) watching)", f"set {a.body}")


def cmd_gui_run(a) -> Result:
    _project(a.slug)
    name = a.command
    if not COMMAND_NAME_RE.fullmatch(name):
        raise UsageError("a command name is letters, digits and underscore only "
                         f"(Std_…, CADAgent_…), got {name!r}")
    url = _gui_url(a.slug)
    data = _gui_send(gui_client.get_state, url, a.slug)
    _check_gui_command(a.slug, name, data.get("commands"))
    r = _gui_send(gui_client.do, url, a.slug, "run", [name, *a.args])
    extra = (" " + " ".join(a.args)) if a.args else ""
    return Result(OK, r, f"{a.slug}: ran {name}{extra} ({r['clients']} client(s) watching)",
                  f"ran {name}")


def cmd_gui_commands(a) -> Result:
    _project(a.slug)
    url = _gui_url(a.slug)
    data = _gui_send(gui_client.get_state, url, a.slug)
    rows = data.get("commands") or []
    lines = [f"  {r['name']:24} {r['label']:24} {'enabled' if r['enabled'] else 'disabled'}" for r in rows]
    return Result(OK, {"project": a.slug, "commands": rows},
                  "\n".join(lines) or "no commands published yet", f"{len(rows)} commands")


def cmd_page(a) -> Result:
    _project(a.slug)
    from .page import build_page
    try:
        out, data = build_page(a.slug, Path(a.out).expanduser().resolve() if a.out else None)
    except Exception as e:
        raise BuildFailed(f"{a.slug} page did not build: {st.why(e)}") from e
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    st_ = data["status"]
    verdict = "DONE" if st_.get("done") else (st_.get("verdict") or "not verified")
    text = (f"{a.slug}: review page in {out} ({len(files)} files, verdict {verdict}).\n"
            "Publish index.html as an artifact with the other files next to it.")
    return Result(OK, {"project": a.slug, "path": str(out), "index": str(out / "index.html"),
                       "files": files, "verdict": verdict, "title": data["title"]},
                  text, f"page: {len(files)} files", [str(out / "index.html")])


def cmd_service(a) -> Result:
    from . import service
    try:
        if a.action == "install":
            roots = [Path(r).expanduser().resolve() for r in a.roots]
            missing = [str(r) for r in roots if not r.is_dir()]
            if missing:
                raise UsageError(f"not a folder: {', '.join(missing)}")
            s = service.install(roots, a.port)
        elif a.action == "uninstall":
            s = service.uninstall()
            return Result(OK, s, "workbench service removed" if s["removed"]
                          else "no workbench service was installed", "service removed")
        else:
            s = service.status()
    except RuntimeError as e:
        raise UsageError(str(e)) from None
    up = s["answering"]
    if up:
        text = f"workbench service up at {s['url']} (pid {s['pid']}); it starts at login"
    elif s["installed"]:
        text = f"workbench service installed but not answering at {s['url']}; see {s['log']}"
    else:
        text = "no workbench service installed (`cad service install [DIR ...]`)"
    return Result(OK if up else UNCHECKED, s, text, "service up" if up else "service down")


def cmd_serve(a) -> Result:
    from . import serve
    from .gui_client import _candidates
    roots = [st.ROOT, *[Path(r).expanduser().resolve() for r in a.roots]]
    st.ROOT.mkdir(parents=True, exist_ok=True)   # where `cad init` puts designs: watched while still empty
    # --port, else $PORT (what the app's Browser pane assigns), else 8733
    port = a.port
    if port is None:
        raw = os.environ.get("PORT", "").strip()
        if raw and not raw.isdigit():
            raise UsageError(f"PORT must be a port number, got {raw!r}")
        port = int(raw) if raw else None
    if port is None:
        # No port asked for: a workbench already serving these folders is the answer, and one
        # on other folders (a login service on the real projects, say) keeps 8733 while this
        # one takes the next free port.
        want = {Path(r).resolve() for r in roots}
        for s in _candidates():
            if want <= {Path(x).expanduser().resolve() for x in s.get("roots", [])}:
                url = f"{s['url']}/next/"
                return Result(OK, {"url": url, "reused": True}, f"workbench already running: {url}", url)
    ports = [port] if port is not None else range(8733, 8753)
    for p in ports:
        try:
            serve.run(roots, host=a.host, port=p, keep_warm=a.keep_warm)
            break
        except RuntimeError as e:
            if p == ports[-1]:
                raise UsageError(str(e)) from None
    return Result(OK, {}, "workbench stopped", "workbench stopped")


def build_parser() -> argparse.ArgumentParser:
    # --json may come before or after the command. SUPPRESS keeps a subcommand
    # from resetting a --json given before it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print one JSON object on stdout")
    common.add_argument("--projects", metavar="DIR", default=argparse.SUPPRESS,
                        help=argparse.SUPPRESS)       # as before the command (listed above), too

    p = _Parser(prog="cad", description="cad-agent: parametric parts, deterministic "
                "gates, headless renders. Every command runs on build123d, which a background "
                "worker keeps loaded (`cad warm status|start|stop`; CAD_WARM=0 runs cold).",
                epilog=EXIT_CODES, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", default=False,
                   help="print one JSON object on stdout")
    p.add_argument("--projects", metavar="DIR",
                   help="projects directory (default: CAD_PROJECTS, else cad-agent/projects)")
    # The workbench console: --json plus the text a terminal would show.
    p.add_argument("--with-text", action="store_true", default=False, help=argparse.SUPPRESS)
    # The undo journal's by="ui"/"agent": the workbench server passes this on
    # every command it runs, rather than an env var (see undo.record's
    # docstring for why an env var set in the server's own process does not
    # reach a warm-worker fork).
    p.add_argument("--actor", choices=("ui", "agent"), default=None, help=argparse.SUPPRESS)
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

    sp = add("mass", cmd_mass, "mass, volume, area, centre of gravity and inertia of bodies "
             "as placed (FreeCAD's Mass Properties)")
    sp.add_argument("slug")
    sp.add_argument("bodies", nargs="*", help="bodies to include (default: all)")

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

    sp = add("verify", cmd_verify, "the verifier: rebuild from source in a fresh process, "
             "run every gate, record the verdict with hashes and git commit")
    sp.add_argument("slug")
    sp.add_argument("--views", default="iso", help="views to render and gate, comma separated")
    sp.add_argument("--all", action="store_true", help="show passing rows too")

    sp = add("done", cmd_done, "the gate: exit 0 only if the last verify passed, still "
             "matches the files, ran fresh, and (in a repo) verified committed work")
    sp.add_argument("slug")

    sp = add("cutlist", cmd_cutlist, "stock to order and cut, roughly priced")
    sp.add_argument("slug")

    sp = add("scene", cmd_scene, "tessellate the assembly for the workbench: "
             "out/scene.json with faces, edges, moves and axes")
    sp.add_argument("slug")
    sp.add_argument("--tolerance", type=float, default=None,
                    help="force one Deviation (FreeCAD's tessellation percent-of-size) on every "
                         "body, overriding out/gui.json's per-body view_props; default: each "
                         "body's own Deviation/AngularDeflection, FreeCAD's 0.2 / 28.65 deg when "
                         "a body has neither set")

    sp = add("place", cmd_place, "move a body by hand (placements.toml) and report what it "
             "now hits (exit 1 if a fit rule fails)")
    sp.add_argument("slug")
    sp.add_argument("body")
    sp.add_argument("--move", metavar="X,Y,Z", help="offset from where assembly.py puts it, mm")
    sp.add_argument("--by", metavar="DX,DY,DZ", help="add to the current offset, mm")
    sp.add_argument("--turn", metavar="RX,RY,RZ", help="rotation, degrees, applied X then Y then Z")
    sp.add_argument("--about", metavar="X,Y,Z", help="pivot for --turn (default: the body's centre)")
    sp.add_argument("--reset", action="store_true", help="put it back where assembly.py puts it")

    sp = add("serve", cmd_serve, "the workbench: a local page with the live 3D view, "
             "draggable parts, checks and the activity feed")
    sp.add_argument("roots", nargs="*", metavar="DIR", help="more projects directories to show")
    sp.add_argument("--port", type=int, default=None, help="default: $PORT, else the first free one from 8733 "
                    "(a workbench already serving these folders is reused)")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--keep-warm", action="store_true",
                    help="keep the CAD kernel loaded while serving (the login service uses this)")

    sp = add("set", cmd_set, "change a part's PARAMS in its file (checked first: a value that "
             "breaks the part is not written), then run its part gates")
    sp.add_argument("slug")
    sp.add_argument("part")
    sp.add_argument("values", nargs="+", metavar="KEY=VALUE")

    sp = add("undo", cmd_undo, "undo the last journaled change (cad set, cad place, or a "
             "bought add): refuses if the file was edited by hand since")
    sp.add_argument("slug")
    sp.add_argument("--steps", type=int, default=1, help="undo this many steps at once")

    sp = add("redo", cmd_redo, "redo the last change `cad undo` took back")
    sp.add_argument("slug")
    sp.add_argument("--steps", type=int, default=1, help="redo this many steps at once")

    sp = add("pref", cmd_pref, "user preferences the commands act on, shared with the UI's "
             "Preferences (e.g. MaxUndoSize, the undo/redo steps kept): list, get or set")
    sp.add_argument("key", nargs="?")
    sp.add_argument("value", nargs="?")

    sp = add("cache", cmd_cache, "the user cache directory: location and size against the "
             "CacheLimit preference; --clear empties what no running worker is using")
    sp.add_argument("--clear", action="store_true", help="delete the cache files not in use")

    sp = add("history", cmd_history, "the undo and redo stacks: what changed, who made the "
             "change (ui or agent), and when")
    sp.add_argument("slug")

    sp = add("page", cmd_page, "write a review page to share: the model to turn, cut and "
             "measure, every gate, parts and renders (publish it as an artifact)")
    sp.add_argument("slug")
    sp.add_argument("--out", metavar="DIR", help="folder to write (default: <project>/out/page)")

    gp = add("gui", None, "the workbench's selection, visibility and view: read them, "
             "or point at things for the person at the UI (talks to a running `cad serve`)")
    gsub = gp.add_subparsers(dest="gui_cmd", metavar="<action>", parser_class=_Parser)

    sp = add("state", cmd_gui_state, "the workbench's shared state for one project: "
             "selection, hidden bodies, view props, camera", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.set_defaults(cmd_name="gui state")

    sp = add("select", cmd_gui_select, "point the UI at one or more bodies, replacing the "
             "selection (names: a body, or body.Face3 / body.Edge2 / body.Vertex1)", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.add_argument("names", nargs="+", metavar="NAME")
    sp.set_defaults(cmd_name="gui select")

    sp = add("clear", cmd_gui_clear, "clear the UI's selection", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.set_defaults(cmd_name="gui clear")

    sp = add("show", cmd_gui_show, "make one or more bodies visible in the UI", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.add_argument("names", nargs="+", metavar="NAME")
    sp.set_defaults(cmd_name="gui show")

    sp = add("hide", cmd_gui_hide, "hide one or more bodies in the UI", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.add_argument("names", nargs="+", metavar="NAME")
    sp.set_defaults(cmd_name="gui hide")

    sp = add("view", cmd_gui_view, "set the UI's camera direction or projection", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.add_argument("direction", metavar="DIR",
                    help=", ".join((*VIEW_CAMERA, *VIEW_PROJECTION))
                    + ', or a camera: "OrthographicCamera { position X Y Z orientation X Y Z A ... }"')
    sp.set_defaults(cmd_name="gui view")

    sp = add("fit", cmd_gui_fit, "fit the UI's camera to the assembly, or to the selection",
             parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.add_argument("--selection", action="store_true", help="fit the current selection, "
                    "not the whole assembly")
    sp.set_defaults(cmd_name="gui fit")

    sp = add("say", cmd_gui_say, "show a message in the UI's Report view", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.add_argument("text", nargs="+", metavar="TEXT")
    sp.set_defaults(cmd_name="gui say")

    sp = add("set", cmd_gui_set, "set one body's view properties (FreeCAD ViewObject names: "
             + ", ".join(FREECAD_PROP_NAMES) + ")", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.add_argument("body", metavar="BODY")
    sp.add_argument("values", nargs="+", metavar="PROP=VALUE")
    sp.set_defaults(cmd_name="gui set")

    sp = add("run", cmd_gui_run, "run one of the workbench's commands by its FreeCAD name, "
             "as Gui.runCommand does", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.add_argument("command", metavar="COMMAND", help="e.g. Std_ViewFitAll, CADAgent_Something")
    sp.add_argument("args", nargs="*", metavar="ARG", help="passed through as-is")
    sp.set_defaults(cmd_name="gui run")

    sp = add("commands", cmd_gui_commands, "the commands the workbench has published for "
             "`cad gui run` (name, label, enabled)", parent=gsub)
    sp.add_argument("slug", metavar="PROJECT")
    sp.set_defaults(cmd_name="gui commands")

    sp = add("service", cmd_service, "run the workbench at login (macOS launchd), so it is "
             "always up with the kernel warm: install, uninstall or status")
    sp.add_argument("action", choices=("install", "uninstall", "status"))
    sp.add_argument("roots", nargs="*", metavar="DIR", help="projects directories to show")
    sp.add_argument("--port", type=int, default=8733)

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

    ep = add("eval", None, "the eval set: design tasks scored by the verifier, so a change to "
             "cad-agent is a number")
    ep.add_argument("--evals", metavar="DIR", help="tasks folder (default: CAD_EVALS, else cad-agent/evals)")
    esub = ep.add_subparsers(dest="eval_cmd", metavar="<action>", parser_class=_Parser)

    def evals_dir(sp):
        sp.add_argument("--evals", metavar="DIR", default=argparse.SUPPRESS,
                        help="tasks folder (default: CAD_EVALS, else cad-agent/evals)")

    sp = add("ls", cmd_eval_ls, "the tasks: the brief's first line and what is given", parent=esub)
    evals_dir(sp)
    sp.set_defaults(cmd_name="eval ls")

    sp = add("brief", cmd_eval_brief, "what an agent is given for one task: the brief and the "
             "given files", parent=esub)
    sp.add_argument("task")
    evals_dir(sp)
    sp.set_defaults(cmd_name="eval brief")

    sp = add("score", cmd_eval_score, "grade a design folder against a task's hidden spec: copy "
             "it, lay the given files and the spec over the copy, `cad verify` it in a fresh "
             "process (exit 0 PASS, 1 FAIL, 2 UNCHECKED)", parent=esub)
    sp.add_argument("task")
    sp.add_argument("design", metavar="DESIGN_DIR", help="a project folder: parts/, assembly.py, ...")
    sp.add_argument("--keep", action="store_true", help="keep the scratch project and say where it is")
    sp.add_argument("--all", action="store_true", help="show passing rows too")
    evals_dir(sp)
    sp.set_defaults(cmd_name="eval score")

    sp = add("run", cmd_eval_run, "run an agent on tasks and score what it leaves: per task a "
             "fresh git repo with the given files and BRIEF.md, the agent command run in it, "
             "then `score`", parent=esub)
    sp.add_argument("tasks", nargs="*", metavar="TASK", help="default: every task")
    sp.add_argument("--agent", metavar="CMD", help="shell command; {brief} {dir} {task} {root} "
                    "{plugin} are replaced by quoted paths and the task name ({plugin} is a copy "
                    "of this repo as a plugin, without evals/); CAD_PROJECTS is set")
    sp.add_argument("--timeout", type=float, default=1800, metavar="S",
                    help="seconds the agent gets per task (default 1800)")
    sp.add_argument("--keep", action="store_true",
                    help="keep each task's repo (and the plugin copy) and say where")
    sp.add_argument("--out", metavar="FILE", help="results JSON (default: evals/results/<UTC stamp>.json)")
    evals_dir(sp)
    sp.set_defaults(cmd_name="eval run")

    mp = add("macro", None, "record and replay a sequence of cad commands "
             "(FreeCAD's macros, for this CLI)")
    msub = mp.add_subparsers(dest="macro_cmd", metavar="<action>", parser_class=_Parser)

    sp = add("ls", cmd_macro_ls, "list saved macros: name, line count, last modified",
             parent=msub)
    sp.set_defaults(cmd_name="macro ls")

    sp = add("show", cmd_macro_show, "print one macro's text", parent=msub)
    sp.add_argument("name")
    sp.set_defaults(cmd_name="macro show")

    sp = add("run", cmd_macro_run, "replay a macro's lines in order (`cad gui` lines reach a "
             "running `cad serve` the normal way; UNCHECKED and skipped in effect if none is "
             "up); stops at the first line that is a usage error or a crash", parent=msub)
    sp.add_argument("name")
    sp.set_defaults(cmd_name="macro run")

    sp = add("rm", cmd_macro_rm, "delete a saved macro", parent=msub)
    sp.add_argument("name")
    sp.set_defaults(cmd_name="macro rm")

    sp = add("save", cmd_macro_save, "save a macro from a file, or stdin with -", parent=msub)
    sp.add_argument("name")
    sp.add_argument("file", metavar="FILE|-")
    sp.set_defaults(cmd_name="macro save")
    return p


# ─── Running ─────────────────────────────────────────────────────────────────

def log_activity(pdir: Path, cmd: str, argv: list, code: int, summary: str,
                 files: list | None = None, ms: int = 0) -> None:
    """Append one line to a project's (or the root's) activity log: what ran,
    how it ended, what it wrote. Used by every `cad` command (via `_log`
    below) and by the workbench for UI/agent actions that are not `cad`
    subcommands themselves (the gui.* entries POST /api/gui/do writes)."""
    entry = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "cmd": cmd, "argv": argv, "exit": code, "summary": summary,
             "files": files or [], "ms": ms}
    try:
        d = Path(pdir) / ".cad"
        d.mkdir(parents=True, exist_ok=True)
        with (d / "log.jsonl").open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass


def _strip_internal_flags(argv: list[str]) -> list[str]:
    """Flags the workbench server (or a nested `main()` call) adds that are
    not part of what a person or agent typed: --with-text (no value) and
    --actor <ui|agent> (one). Dropped before the activity log ever sees them."""
    out, skip = [], False
    for x in argv:
        if skip:
            skip = False
            continue
        if x == "--with-text":
            continue
        if x == "--actor":
            skip = True
            continue
        out.append(x)
    return out


def _log(a, argv, res: Result, ms: int) -> None:
    """Append one line to the activity log. Never changes a verdict."""
    base = st.ROOT
    if getattr(a, "slug", None):
        try:
            base = st.project_dir(a.slug)
        except FileNotFoundError:
            pass
    log_activity(base, getattr(a, "cmd_name", None), _strip_internal_flags(argv),
                 res.code, res.summary, res.files, ms)


def _emit(a, res: Result) -> None:
    if getattr(a, "json", False):
        out = {"cmd": getattr(a, "cmd_name", None), "exit": res.code, "data": res.data}
        if getattr(a, "with_text", False):
            out["text"] = res.text
        print(json.dumps(out, default=str))
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
        print(f"cad-agent 0.1.2  build123d {build123d.__version__}  render: {backend_status()}")
        return OK
    if not getattr(a, "func", None):
        (parser if not a.cmd else parser._subparsers._group_actions[0].choices[a.cmd]).print_help(sys.stderr)
        return USAGE

    # Fresh means nothing ran here before this command: no earlier command and no
    # gate code loaded. A warm-worker fork and a new interpreter both qualify; a
    # long-lived process calling main() again (the test suite) does not.
    if st.ROOT.exists() and not st.ROOT.is_dir():      # a typo like --projects part.py, not a folder
        msg = (f"{st.ROOT} is not a folder; --projects (or CAD_PROJECTS) names the folder "
               "that holds the projects")
        _emit(a, Result(USAGE, {"error": msg}, f"cad {a.cmd_name}: {msg}", msg))
        return USAGE

    global _RUNS
    a._fresh = _RUNS == 0 and "cad_agent.runner" not in sys.modules
    _RUNS += 1

    t0 = time.perf_counter()
    try:
        res = a.func(a)
    except UsageError as e:
        res = Result(USAGE, {"error": str(e)}, f"cad {a.cmd_name}: {e}", str(e))
    except BuildFailed as e:
        res = Result(FAIL, {"error": str(e)}, str(e), str(e))
    except PlacementError as e:
        res = Result(FAIL, {"error": str(e)}, str(e), str(e))
    except UndoError as e:
        res = Result(FAIL, {"error": str(e)}, str(e), str(e))
    except WorkbenchDown as e:
        res = Result(UNCHECKED, {"error": str(e)}, str(e), str(e))
    except PermissionError as e:       # a folder we may not write to is the caller's to change
        msg = (f"cannot write {e.filename}: {e.strerror}; `cad {a.cmd_name}` writes into the "
               "project, so it needs a folder you can write to")
        res = Result(USAGE, {"error": msg}, f"cad {a.cmd_name}: {msg}", msg)
    except Exception as e:
        res = Result(CRASH, {"error": f"{type(e).__name__}: {e}"},
                     "cad crashed, this is a cad-agent bug:\n" + traceback.format_exc(),
                     f"crash: {type(e).__name__}")
    _emit(a, res)
    _log(a, argv, res, int((time.perf_counter() - t0) * 1000))
    return res.code


if __name__ == "__main__":
    sys.exit(main())
