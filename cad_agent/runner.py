"""The run: build every part, execute every registered check, write checks.json.

The runner knows nothing about individual rules. It builds the three contexts,
asks the registry what to run, and collects rows. Adding a verifier does not
touch this file.
"""
from __future__ import annotations

import numpy as np

from . import rules  # noqa: F401  — importing is what registers the checks
from .geom import bbox, mass_g, volume
from .placements import PlacementError
from .registry import (AssemblyCtx, FAILING, PartCtx, ProjectCtx, Row, checks,
                       run as run_check)
from .render import draw, merge, tessellate
from .state import (build_part, load_assembly, part_names, project_dir,
                    read_checks, why, write_checks)


def check_all(slug: str, render_views=("iso",), tolerance: float = 0.05):
    pdir = project_dir(slug)
    out = pdir / "out"
    out.mkdir(parents=True, exist_ok=True)

    parts_out: dict = {}
    solids: dict = {}
    render_rows: list = []
    rows: list = []

    # ── build ────────────────────────────────────────────────────────────────
    for name in part_names(slug):
        try:
            solid, meta = build_part(slug, name)
        except Exception as e:
            parts_out[name] = {"state": "FAIL", "error": why(e)}
            continue
        solids[name] = solid
        lo, hi = bbox(solid)
        row = {
            "state": "BUILT", "doc": meta["doc"], "params": meta["params"],
            "material": meta["material"], "process": meta["process"],
            "build_s": meta["build_s"],
            "bbox_mm": [round(hi[i] - lo[i], 3) for i in range(3)],
            "volume_cm3": round(volume(solid) / 1000.0, 3),
        }
        if meta["material"]:
            try:
                row["mass_g"] = round(mass_g(solid, meta["material"]), 2)
            except KeyError as e:
                row["mass_g"] = None
                row["mass_note"] = str(e)
        parts_out[name] = row

    # ── per-part checks ──────────────────────────────────────────────────────
    part_specs = checks("part")
    for name, solid in solids.items():
        _, meta = build_part(slug, name)
        ctx = PartCtx(slug=slug, name=name, solid=solid, meta=meta, out_dir=out)
        for spec in part_specs:
            rows += run_check(spec, ctx)

        mesh = tessellate(solid, tolerance, 0.2)
        for view in render_views:
            p = draw(mesh, out / f"{name}_{view}.png", view=view)
            render_rows.append({"part": name, "view": view,
                                "path": str(p.relative_to(pdir)),
                                "triangles": int(len(mesh.tris))})

    # ── assembly checks ──────────────────────────────────────────────────────
    try:
        asm, clearance, allow_contact, axes = load_assembly(slug)
    except PlacementError:
        raise                         # fails closed with its own message: cli.main reports it
    except Exception as e:            # the design's failure to report, not a crash of the checker
        asm, clearance, allow_contact, axes = None, {}, set(), {}
        rows.append(Row(subject=slug, rule="build", state="FAIL", measured=why(e),
                        limit="an assembly.py whose parts() returns the bodies",
                        source="assembly.py", check="assembly"))
    actx = AssemblyCtx(slug=slug, parts=asm or {}, clearance=clearance,
                       allow_contact=allow_contact, out_dir=out, axes=axes)
    for spec in checks("assembly"):
        rows += run_check(spec, actx)

    if asm:
        big = merge([tessellate(s, tolerance, 0.2) for _, s in sorted(asm.items())])
        for view in render_views:
            p = draw(big, out / f"assembly_{view}.png", view=view)
            render_rows.append({"part": "assembly", "view": view,
                                "path": str(p.relative_to(pdir)),
                                "triangles": int(len(big.tris))})

    # ── project checks ───────────────────────────────────────────────────────
    pctx = ProjectCtx(slug=slug, dir=pdir, parts=parts_out, out_dir=out)
    for spec in checks("project"):
        rows += run_check(spec, pctx)

    dict_rows = [r.as_dict() for r in rows]
    by_state: dict = {}
    for r in dict_rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    by_check: dict = {}
    for r in dict_rows:
        b = by_check.setdefault(r["check"], {})
        b[r["state"]] = b.get(r["state"], 0) + 1

    failing = [r for r in dict_rows if r["state"] in FAILING]
    payload = {
        "project": slug,
        "parts": parts_out,
        "renders": render_rows,
        "rows": dict_rows,
        "summary": {
            "parts_built": sum(1 for r in parts_out.values()
                               if r.get("state") == "BUILT"),
            "parts_failed": sum(1 for r in parts_out.values()
                                if r.get("state") == "FAIL"),
            "checks_run": len(part_specs) * len(solids) + len(checks("assembly"))
                          + len(checks("project")),
            "rows": len(dict_rows),
            "by_state": by_state,
            "by_check": by_check,
            "ok": not failing and not any(
                r.get("state") == "FAIL" for r in parts_out.values()),
        },
    }
    write_checks(slug, payload)
    return payload


def done_check(slug: str) -> dict:
    """The gate. Fails on FAIL and on UNCHECKED, never on silence."""
    c = read_checks(slug)
    failures = []

    if not c["parts"]:
        failures.append("no parts in the project")
    for name, row in c["parts"].items():
        if row.get("state") != "BUILT":
            failures.append(f"part {name} did not build: {row.get('error')}")

    for r in c.get("rows", []):
        if r["state"] in FAILING:
            failures.append(
                f"{r['state'].lower()} · {r['check']}/{r['rule']} · "
                f"{r['subject']}: {r['measured']}"
                + (f" (limit {r['limit']})" if r["limit"] != "n/a" else ""))

    rendered = {r["part"] for r in c["renders"]}
    for name in c["parts"]:
        if name not in rendered:
            failures.append(f"part {name} was never rendered")

    return {"ok": not failures, "failures": failures,
            "checked_utc": c.get("written_utc"),
            "rows": c["summary"].get("rows"),
            "by_state": c["summary"].get("by_state")}


def approve_views(slug: str, subject: str | None = None, view: str | None = None):
    """Promote current renders to approved images, so drift is gated from now on."""
    from .checks.visual import DEFAULT_VIEWS, approve
    pdir = project_dir(slug)
    out = pdir / "out"
    done = []
    subjects = [subject] if subject else (part_names(slug))
    for s in subjects:
        _, meta = build_part(slug, s)
        views = [view] if view else list(meta.get("views") or DEFAULT_VIEWS)
        for v in views:
            done.append(str(approve(pdir, out, s, v).relative_to(pdir)))
    return done


def part_check(slug: str, name: str, overrides: dict | None = None,
               render: bool = True, view: str = "iso",
               only: set | None = None, opts: dict | None = None):
    """The fast inner loop: build one part, run only the part-scope rules.

    `check_all` rebuilds every part, poses the assembly and sweeps every axis,
    which is the right thing before calling a design done and the wrong thing
    while a dimension is still moving. This does the one part, so changing a
    number and seeing whether it still holds costs a second rather than a
    minute.

    What it deliberately cannot tell you: anything about fit, travel or reach.
    Those are assembly facts, and a part that passes here can still crash. Run
    `check_all` before believing a design.
    """
    pdir = project_dir(slug)
    out = pdir / "out"
    out.mkdir(parents=True, exist_ok=True)

    solid, meta = build_part(slug, name, overrides)
    ctx = PartCtx(slug=slug, name=name, solid=solid, meta=meta, out_dir=out,
                  opts=dict(opts or {}))
    rows = []
    skipped = []
    for spec in checks("part"):
        if only is not None and spec.name not in only:
            skipped.append(spec.name)
            continue
        rows += run_check(spec, ctx)

    lo, hi = bbox(solid)
    result = {
        "part": name,
        "overrides": overrides or {},
        "bbox_mm": [round(hi[i] - lo[i], 3) for i in range(3)],
        "volume_cm3": round(volume(solid) / 1000.0, 3),
        "build_s": meta["build_s"],
        "rows": [r.as_dict() for r in rows],
        "failing": [r.as_dict() for r in rows if r.state in FAILING],
        "scope": "part rules only; fit, sweep and reach need check_all",
        "skipped_checks": skipped,
        "opts": dict(opts or {}),
    }
    result["ok"] = not result["failing"]
    if render:
        mesh = tessellate(solid, 0.05, 0.2)
        result["render"] = str(draw(mesh, out / f"_iter_{name}_{view}.png",
                                    view=view).relative_to(pdir))
    return result
