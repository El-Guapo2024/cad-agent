# cad-agent — mechanical design engine, sibling of hw-agent

**STATUS 2026-09-12: v1 BUILT.** Engine, gates, dual render backends (Metal default,
numpy fallback), 13 MCP tools, 42 tests, registered as the `cad` MCP server.
See README.md. Remaining items below are the backlog, not the build plan.

Written 2026-09-10. Purpose: an agent-driven mechanical CAD loop with the same shape as
~/ws/freight_flow_ai/hardware/hw_agent (spec → parametric parts → deterministic checks → render → page).
First customer: the Desk Fab Line (two cells, see memory personal-fab-line-from-scratch and the artifact
https://claude.ai/code/artifact/7156d42d-592e-47e4-99b3-eed2ff2f9123).

## Engine
- build123d (Python, OCCT B-rep). Reasons: STEP in/out, assemblies with joints, fillets/chamfers on real edges,
  import vendor STEP for bought parts and check fit against them. OpenSCAD kept only for legacy scad files in
  ~/ws/smart-printer/cad.
- Headless render: build123d → mesh → PNG (trimesh + pyrender or ocp_vscode offscreen). Must work with no GUI.
- Install: `pip install build123d trimesh pyrender ocp-tessellate` in a venv at ~/ws/cad-agent/.venv.

## Layout (mirror hw_agent)
```
cad_agent/
  mcp_app.py            # cad-mcp server, tools below
  project_state/        # docs/projects/<slug>/mech/ : mech_profile.md, parts/*.py, bought/*.step, checks.json
  parts/                # helpers: extrusion(profile,len), panel, standard holes (M3/M5 clearance+tap), heat inserts
  checks/               # fit (interference/clearance), dfm (min wall, overhang, kerf), bbox/mass, cutlist
  render/               # png from named views, exploded, section
  skills/               # mech-design.md (contract like hardware-design), research-bought-part.md
  tests/
```

## MCP tools (v1)
- project_init(slug), part_add(slug,name,params), part_build(slug,name) → bbox, volume, mass(material)
- bought_add(slug,name,step_path|url) — vendor STEP; never model a bought part from memory if a STEP exists
- assembly_set(slug, placements/joints)
- check_fit(slug) → per pair: interference volume, min clearance, PASS/FAIL vs required clearance
- check_dfm(slug,part,process=fdm|laser_cut|cnc) → min wall, overhang, hole-to-edge, kerf comp, PASS/FAIL
- cutlist(slug) → extrusion lengths, panel sizes, fastener counts, priced from a small vendor table
- render(slug, view=iso|top|front|section|exploded, zoom_to=part) → PNG path
- export(slug, step|stl|dxf)
- done_check(slug) → all checks PASS, every part rendered, cutlist priced

## Rules carried over from hw-agent
- The agent writes specs and parametric code; tools compute; the human approves on the page.
- Every number on the page comes from a check run (checks.json), never typed.
- Gates fail the run, not just report.
- Bought parts come from vendor STEP or a datasheet drawing, not from memory.

## First projects
1. desk_fab_line/mech/box_b — assembly box: 2040 frame, SecKit SK-Cube 200 footprint (get STEP or measure),
   hot-plate dock 100x100x10 Al with clamps, feeder rail, up-camera mount, head with NEMA8 + nozzle + syringe + ELP cam.
2. desk_fab_line/mech/box_a — laser box: ComMarker B4 galvo head mount, OD6 window, door interlock geometry, fume port.
3. hotplate — plate drawing for the machine shop (cartridge heater bores, thermocouple well, KSD301 pad).

## Resume prompt
"Build cad-agent per ~/ws/cad-agent/PLAN.md: venv with build123d, cad_agent package with the MCP tools listed,
render loop proven with one part (the hot plate) shown as PNG, then register the MCP and stop for review."
