"""cad-mcp — agent-driven mechanical CAD. Sibling of designer-mcp.

The agent writes parametric part modules and specs; these tools build,
measure, gate and render. Every number a report shows comes from checks.json,
written by a run, never typed. Headless: no GUI, no OpenGL, no license.
"""
from __future__ import annotations

import json
from pathlib import Path

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server, Image
except ModuleNotFoundError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server, Image

from . import bought as _bought
from . import state as st
from .registry import checks as _registry_checks
from .runner import (approve_views as _approve_views, check_all as _check_all,
                     done_check as _done_check, part_check as _part_check)
from .cutlist import cutlist as _cutlist
from .export import export_part as _export_part
from .render import tessellate, draw, merge, VIEWS, backend_status
from .geom import min_distance, intersection_volume, mass_g, bbox, DENSITY
from .parts import CLEARANCE_HOLE, TAP_DRILL, HEATSET_BORE, EXTRUSION

mcp = _Server(
    "cad",
    instructions=(
        "Agent-driven mechanical CAD (build123d / OCCT B-rep). Parts are "
        "parametric Python modules; tools build, measure, gate and render "
        "them headlessly. Fit and DFM gates fail the run rather than "
        "reporting. Bought parts come from vendor STEP, never modelled from "
        "memory. Layout of a machine and its fabrication are a human's job; "
        "this server produces specs, checked geometry and exports."
    ),
)


def _img(path: Path) -> Image:
    return Image(path=str(path))


# ─── Projects ────────────────────────────────────────────────────────────────

@mcp.tool()
def project_init(slug: str, brief: str = "") -> str:
    """[write] Create a project directory tree and a mech_profile.md stub."""
    d = st.project_dir(slug, create=True)
    prof = d / "mech_profile.md"
    if not prof.exists():
        prof.write_text(
            f"# {slug} — mechanical spec\n\n## Brief\n\n{brief or 'TODO'}\n\n"
            "## Assumptions\n\n1. TODO\n\n## Parts\n\n| Name | Process | Material | Role |\n"
            "|---|---|---|---|\n\n## Out of scope\n\nFabrication, assembly by hand.\n"
        )
    return f"project {slug} at {d}\nwrote {prof.name}" if prof.exists() else str(d)


@mcp.tool()
def project_list() -> str:
    """[read] List projects."""
    names = st.list_projects()
    return "\n".join(names) if names else "no projects yet"


@mcp.tool()
def project_status(slug: str) -> str:
    """[read] Parts present, and the last check run if there is one."""
    parts = st.part_names(slug)
    out = [f"## {slug}", f"parts: {', '.join(parts) if parts else 'none'}"]
    try:
        c = st.read_checks(slug)
        out.append(f"last run: {c['written_utc']}")
        out.append(json.dumps(c["summary"], indent=1))
    except FileNotFoundError:
        out.append("no checks.json yet — run check_all")
    return "\n".join(out)


# ─── Parts ───────────────────────────────────────────────────────────────────

@mcp.tool()
def part_list(slug: str) -> str:
    """[read] Part module names in a project."""
    return "\n".join(st.part_names(slug)) or "no parts"


@mcp.tool()
def part_build(slug: str, name: str, overrides: dict | None = None) -> str:
    """[read] Build one part and return its measured geometry.

    `overrides` replaces individual PARAMS values for this build only, which
    is how you sweep a dimension without editing the file.
    """
    solid, meta = st.build_part(slug, name, overrides)
    lo, hi = bbox(solid)
    dims = [round(hi[i] - lo[i], 3) for i in range(3)]
    lines = [
        f"## {slug} / {name}",
        meta["doc"] or "",
        f"built in {meta['build_s']} s",
        f"bbox: {dims[0]} x {dims[1]} x {dims[2]} mm",
        f"material: {meta['material']}   process: {meta['process']}",
    ]
    if meta["material"]:
        try:
            lines.append(f"mass: {mass_g(solid, meta['material']):.2f} g")
        except KeyError as e:
            lines.append(f"mass: unknown material ({e})")
    if overrides:
        lines.append(f"overrides: {overrides}")
    return "\n".join(x for x in lines if x)


@mcp.tool()
def part_render(slug: str, name: str, view: str = "iso",
                overrides: dict | None = None, tolerance: float = 0.05) -> Image:
    """[read] Render one part headlessly and return the PNG.

    Views: iso, iso2, top, bottom, front, back, left, right.
    """
    solid, _ = st.build_part(slug, name, overrides)
    mesh = tessellate(solid, tolerance, 0.2)
    out = st.project_dir(slug) / "out" / f"{name}_{view}.png"
    return _img(draw(mesh, out, view=view))


@mcp.tool()
def assembly_render(slug: str, view: str = "iso", tolerance: float = 0.05) -> Image:
    """[read] Render the whole assembly from assembly.py in one image."""
    asm, _, _, _ = st.load_assembly(slug)
    if asm is None:
        raise FileNotFoundError(f"{slug} has no assembly.py")
    big = merge([tessellate(s, tolerance, 0.2) for _, s in sorted(asm.items())])
    out = st.project_dir(slug) / "out" / f"assembly_{view}.png"
    return _img(draw(big, out, view=view))


@mcp.tool()
def part_export(slug: str, name: str, fmt: str = "step") -> str:
    """[write] Export a part as STEP (for a shop) or STL (for printing)."""
    return str(_export_part(slug, name, fmt))


# ─── Bought parts ────────────────────────────────────────────────────────────

@mcp.tool()
def bought_add_step(slug: str, name: str, step_path: str, source: str,
                    vendor: str = "") -> str:
    """[write] Register a vendor STEP file as a bought part.

    `source` is required and must name the page the file came from. Geometry
    without provenance is how an assembly passes every gate and still does not
    fit, so it is refused rather than trusted.
    """
    p = _bought.register_step(slug, name, step_path, source, vendor or None)
    return f"registered {name} from {p}\n{json.dumps(_bought.bought_info(slug, name), indent=1)}"


@mcp.tool()
def bought_list(slug: str) -> str:
    """[read] Bought parts in a project, with kind and provenance."""
    rows = _bought.list_bought(slug)
    return json.dumps(rows, indent=1) if rows else "no bought parts yet"


@mcp.tool()
def bought_info(slug: str, name: str) -> str:
    """[read] Measured envelope of a bought part, and where its geometry came from."""
    return json.dumps(_bought.bought_info(slug, name), indent=1)


# ─── Measurement ─────────────────────────────────────────────────────────────

@mcp.tool()
def measure_pair(slug: str, part_a: str, part_b: str) -> str:
    """[read] Minimum distance and overlap volume between two built parts.

    This is the raw query behind the fit gate. Overlap above zero means the
    parts interfere; a distance of zero means they touch.
    """
    a, _ = st.build_part(slug, part_a)
    b, _ = st.build_part(slug, part_b)
    ov = intersection_volume(a, b)
    if ov > 1e-6:
        return f"{part_a} vs {part_b}: INTERFERENCE, overlap {ov:.4f} mm^3"
    return f"{part_a} vs {part_b}: clear, minimum distance {min_distance(a, b):.4f} mm"


@mcp.tool()
def reference_tables() -> str:
    """[read] Standard hole sizes, insert bores, extrusion profiles, densities.

    Use these instead of recalling a drill size. ISO 273 medium fit for
    clearance holes, coarse-thread tapping drills.
    """
    return json.dumps({
        "clearance_hole_mm": CLEARANCE_HOLE,
        "tap_drill_mm": TAP_DRILL,
        "heatset_bore_mm": HEATSET_BORE,
        "extrusion": EXTRUSION,
        "density_g_cm3": DENSITY,
        "views": sorted(VIEWS),
        "render_backend": backend_status(),
    }, indent=1)


# ─── Gates ───────────────────────────────────────────────────────────────────

@mcp.tool()
def check_all(slug: str, views: list[str] | None = None,
              only_problems: bool = True) -> str:
    """[write] Build every part, run every registered check, write checks.json.

    This is the run that produces every number a report may quote. By default
    only rows that are not PASS come back, since a passing row is the absence
    of news; pass only_problems=false for the full list.
    """
    p = _check_all(slug, render_views=tuple(views or ("iso",)))
    rows = p["rows"]
    if only_problems:
        rows = [r for r in rows if r["state"] != "PASS"]
    return json.dumps({"summary": p["summary"], "rows": rows,
                       "note": ("only non-passing rows shown; "
                                f"{len(p['rows'])} in total")
                       if only_problems else None}, indent=1)


@mcp.tool()
def checks_list() -> str:
    """[read] Every registered check, its scope and what it verifies.

    Scope says what the runner hands the check: one part, the whole assembly,
    or the project. Adding a check is one decorated function in rules.py.
    """
    return json.dumps([
        {"name": c.name, "scope": c.scope, "order": c.order, "does": c.doc}
        for c in _registry_checks()], indent=1)


@mcp.tool()
def approve_render(slug: str, part: str = "", view: str = "") -> str:
    """[write] Promote current renders to approved images, gating visual drift.

    Until a view is approved its drift rule is UNCHECKED, which fails the
    gate. After approval, any later run reports what fraction of the frame
    changed and writes a diff image marking it. Approve a change only after
    looking at that diff: approving blindly turns the rule off.
    """
    done = _approve_views(slug, part or None, view or None)
    return "approved:\n" + "\n".join(done)


@mcp.tool()
def done_check(slug: str) -> str:
    """[read] The gate. ok:false on any FAIL or UNCHECKED, never on silence."""
    return json.dumps(_done_check(slug), indent=1)


@mcp.tool()
def cutlist(slug: str) -> str:
    """[read] Stock to order and cut, from each part's CUTLIST, roughly priced."""
    return json.dumps(_cutlist(slug), indent=1)


@mcp.tool()
def part_check(slug: str, name: str, overrides: dict | None = None) -> str:
    """[read] Fast loop: build one part and run only its part-scope rules.

    Use this while a dimension is still moving. `overrides` sweeps a value
    without editing the file, so you can ask "does it still hold at 38?" in a
    second rather than rebuilding the project.

    It cannot see fit, travel or reach — those are assembly facts. Run
    check_all before believing a design is done.
    """
    r = _part_check(slug, name, overrides)
    d = r["bbox_mm"]
    lines = [f"## {slug} / {name}  {'OK' if r['ok'] else 'FAILING'}",
             f"bbox {d[0]} x {d[1]} x {d[2]} mm · {r['volume_cm3']} cm^3 · {r['build_s']} s"]
    if r["overrides"]:
        lines.append(f"overrides: {r['overrides']}")
    for row in r["rows"]:
        lines.append(f"  {row['state']:9} {row['rule']:16} {row['measured']}"
                     + (f"   [limit {row['limit']}]" if row["limit"] != "n/a" else ""))
    lines.append(f"\n{r['scope']}")
    return "\n".join(lines)


@mcp.tool()
def bought_add_measured(slug: str, name: str, length: float, width: float,
                        height: float, source: str, vendor: str = "",
                        holes: list | None = None, hole_dia: float = 3.2) -> str:
    """[write] Add a bought part you have a datasheet for but no STEP.

    Three envelope dimensions, an optional bolt pattern, and a source naming
    the drawing or datasheet page the numbers came from. The part is written
    UNVERIFIED, which holds the project gate open until callipers confirm it
    or a vendor STEP replaces it. That is deliberate: a dimension read off a
    drawing is a claim, not a measurement.
    """
    path = _bought.register_measured(
        slug, name, length, width, height, source=source,
        vendor=vendor or None, holes=holes, hole_dia=hole_dia)
    info = _bought.bought_info(slug, name)
    return (f"wrote {path.name}\n"
            f"envelope {info['bbox_mm']} mm · UNVERIFIED\n"
            f"source: {info['source']}\n"
            "The provenance gate will report this UNCHECKED until you call "
            "bought_verify with a calliper reading.")


@mcp.tool()
def bought_verify(slug: str, name: str, note: str) -> str:
    """[write] Confirm a measured part against the real thing.

    `note` must say what was measured and how; it is appended to the part's
    SOURCE. "Verified" with no record of the measurement is the same unchecked
    claim wearing a better label.
    """
    info = _bought.verify(slug, name, note)
    return (f"{name} verified\nenvelope {info['bbox_mm']} mm\n"
            f"source: {info['source']}")


@mcp.tool()
def tool_envelope(kind: str, params: dict) -> str:
    """[read] Generate a cutting or dispensing tool envelope and measure it.

    kind is one of: drill, end_mill, collet_nose, laser_cone, needle.
    These are generated from dimensions you supply, never from a catalogue —
    a tool is bought, so its numbers come off the tool or its datasheet.

    The envelope is the volume nothing else may occupy. Place it in an
    assembly to gate whether the spindle nose clears a clamp, or whether a
    fixture wall shadows a laser field corner.
    """
    from . import tooling
    fn = getattr(tooling, kind, None)
    if fn is None or kind.startswith("_"):
        return ("unknown tool kind; choose from drill, end_mill, collet_nose, "
                "laser_cone, needle")
    solid = fn(**params)
    lo, hi = bbox(solid)
    out = [f"## {kind} {params}",
           f"bbox {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f} mm",
           f"z {lo[2]:.2f} .. {hi[2]:.2f} (tip at z = 0)"]
    if kind == "laser_cone":
        out.append(f"beam tilt at a field corner: "
                   f"{tooling.tilt_at_corner(params['focal_length'], params['field']):.2f} deg "
                   "— this is what shadows a fixture wall")
    return "\n".join(out)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
